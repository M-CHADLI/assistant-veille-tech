type Step = {
  n: string;
  title: string;
  file: string;
  lang: "python" | "tsx";
  intro: string;
  code: string;
};

// Phase A : tout ce qui se passe EN ARRIÈRE-PLAN, avant qu'un utilisateur
// ne pose la moindre question. Le but : remplir une "table" (la base
// vectorielle Chroma) avec des articles déjà nettoyés et indexés.
const INDEX_STEPS: Step[] = [
  {
    n: "1",
    title: "Collecte des sources",
    file: "app/ingest/scraper.py",
    lang: "python",
    intro:
      "On boucle sur une liste d'URLs (flux RSS, API GitHub Releases, NewsAPI, pages web). Chaque source a un format différent, mais le scraper renvoie toujours la même structure en sortie.",
    code: `def run(self, urls: list[str]) -> list[dict[str, Any]]:
    # "urls" est une liste hétérogène : flux RSS, endpoints GitHub
    # Releases, pages HTML... un peu comme une liste de fichiers
    # source de formats différents (csv, json, xml) à charger.
    articles: list[dict[str, Any]] = []

    for url in urls:
        try:
            # _fetch() détecte le type de source à partir de l'URL
            # et choisit le bon "parseur" -> équivalent d'une fonction
            # qui regarde l'extension d'un fichier avant de choisir
            # pd.read_csv / pd.read_json / pd.read_xml.
            articles.extend(self._fetch(url))
        except Exception as exc:
            # Une source down (timeout, 404...) ne doit pas faire
            # planter tout le batch : on logue et on continue.
            # -> dans un pipeline ETL, c'est l'équivalent d'un
            #    "skip + log" sur une ligne d'entrée corrompue,
            #    plutôt que de stopper tout le job.
            logger.warning("scraper: failed to fetch %s: %s", url, exc)

    return articles`,
  },
  {
    n: "2",
    title: "Nettoyage : HTML → texte propre + dédoublonnage",
    file: "app/ingest/cleaning.py",
    lang: "python",
    intro:
      "Le HTML brut contient du bruit (menus, pubs, scripts). On le convertit en texte lisible, puis on retire les articles déjà vus.",
    code: `def clean_html_to_markdown(html: str) -> str:
    # 1) On retire les blocs qui ne sont jamais le "contenu" :
    #    nav/header/footer/pubs/cookies...
    #    -> comme supprimer des colonnes inutiles d'un export brut
    #    avant de l'analyser.
    soup = strip_boilerplate(BeautifulSoup(html, "lxml"))

    # 2) Le HTML restant (titres, paragraphes, listes) est converti
    #    en Markdown : un format texte simple, facile à découper
    #    et à donner à un LLM.
    text = md(str(soup), heading_style="ATX", strip=["img"])

    # 3) On compresse les sauts de ligne multiples laissés par la
    #    conversion ("\\n\\n\\n\\n" -> "\\n\\n").
    return re.sub(r"\\n{3,}", "\\n\\n", text).strip()


def dedupe(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # L'équivalent d'un df.drop_duplicates(), mais avec DEUX clés
    # possibles : l'URL exacte, OU le couple (source, titre) — car
    # le même article est parfois republié sous une URL différente.
    seen_urls: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []

    for article in articles:
        url = article.get("url")
        key_title = (article.get("source", ""), article.get("title", ""))

        if url in seen_urls or key_title in seen_titles:
            continue  # déjà vu -> on saute cette "ligne"

        seen_urls.add(url)
        seen_titles.add(key_title)
        out.append(article)

    return out`,
  },
  {
    n: "3",
    title: "Découpage en chunks (LangChain)",
    file: "app/ingest/cleaning.py",
    lang: "python",
    intro:
      "Un article peut faire plusieurs milliers de mots. On le découpe en morceaux (\"chunks\") d'environ 1200 caractères via le RecursiveCharacterTextSplitter de LangChain — l'outil standard des pipelines RAG.",
    code: `from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk(text: str, max_chars: int = 1200, overlap: int = 120) -> list[str]:
    # Pourquoi découper ? La recherche (étape 7) et le LLM (étape 9)
    # fonctionnent mieux sur des passages courts et ciblés que sur
    # un article entier de 5000 mots.
    #
    # Analogie : transformer un gros rapport PDF en plusieurs
    # "fiches" d'une page, chacune indexable et citable séparément.
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]  # déjà assez court : pas besoin de découper

    splitter = RecursiveCharacterTextSplitter(
        # Taille max d'un chunk (en caractères).
        chunk_size=max_chars,

        # L'OVERLAP : la fin d'un chunk est RÉPÉTÉE au début du
        # suivant (~10%). Une idée à cheval sur la coupure reste
        # ainsi lisible en entier dans au moins un des deux chunks.
        # Coût accepté : ~10% de texte stocké en double.
        chunk_overlap=min(overlap, max_chars // 2),

        # Découpage RÉCURSIF : essaie de couper d'abord entre les
        # paragraphes, puis les lignes, puis les phrases, puis les
        # mots — et ne descend d'un niveau que si le morceau est
        # encore trop gros. Les coupures tombent donc aux frontières
        # les plus "naturelles" possibles.
        separators=["\\n\\n", "\\n", ". ", "! ", "? ", " ", ""],

        # Garde la ponctuation à la FIN du chunk (pas au début du
        # suivant) : chaque chunk se termine sur une phrase complète.
        keep_separator="end",
    )
    return splitter.split_text(text)`,
  },
  {
    n: "4",
    title: "Embeddings + indexation dans Chroma",
    file: "app/rag/retrieval.py + app/ingest/chroma_store.py",
    lang: "python",
    intro:
      "Chaque chunk de texte est transformé en vecteur de nombres (\"embedding\"), puis stocké dans ChromaDB avec ses métadonnées (titre, source, date, url).",
    code: `def embed(text: str) -> list[float]:
    # Transforme un texte en un vecteur d'environ 384 nombres
    # décimaux (un "embedding").
    #
    # Analogie data analyst : un peu comme une "feature vector"
    # obtenue par réduction de dimension (PCA / UMAP) — sauf que
    # le modèle a appris à placer les textes de SENS PROCHE à des
    # coordonnées proches dans cet espace à 384 dimensions.
    #
    # "Bug dans mon script Python" et "Erreur lors de l'exécution
    # d'un programme Python" auront des vecteurs quasi identiques,
    # même si presque aucun mot n'est en commun.
    embedder = get_embedder()
    vec = embedder.encode([text], normalize_embeddings=True)
    return vec[0].tolist()


# --- app/ingest/chroma_store.py --------------------------------
def store(self, articles: list[Article]) -> int:
    ids, texts, metadatas = [], [], []

    for article in articles:
        pieces = chunk(article.content, max_chars=self.chunk_max_chars)
        for index, piece in enumerate(pieces):
            ids.append(f"{article.id}-{index}")  # clé primaire du chunk
            texts.append(piece)                   # le texte du chunk
            metadatas.append({                    # ~ les colonnes "à côté"
                "title": article.title,
                "source": article.source,
                "url": str(article.url),
                "date": article.date.isoformat() if article.date else "",
                "tags": ",".join(article.tags),
                "chunk_index": index,
            })

    # On vectorise TOUS les chunks d'un coup -> plus rapide qu'un
    # par un, comme un .apply() vectorisé plutôt qu'une boucle
    # ligne par ligne.
    embeddings = embedder.encode(texts, normalize_embeddings=True).tolist()

    # "upsert" = met à jour si l'id existe déjà, insère sinon.
    # -> équivalent d'un INSERT ... ON CONFLICT DO UPDATE en SQL.
    collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
    return len(articles)`,
  },
];

// Phase B : tout ce qui se passe EN DIRECT, à chaque question posée
// par l'utilisateur dans l'interface ci-dessus.
const QUERY_STEPS: Step[] = [
  {
    n: "5",
    title: "La question part vers le backend",
    file: "web/lib/api.ts",
    lang: "tsx",
    intro:
      "Le frontend envoie la question + les sujets cochés au backend FastAPI, en JSON, via une requête POST.",
    code: `export async function postChat(
  question: string,
  topics: string[],
): Promise<ChatResponse> {
  // Équivalent d'un appel à une API REST externe pour récupérer
  // un résultat, sauf qu'ici on ENVOIE des paramètres (la question,
  // les filtres "topics") et on reçoit en retour un objet structuré
  // { answer, cards, status }.
  const res = await fetch(\`\${API_URL}/chat\`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, topics }),
  });
  if (!res.ok) throw new Error(\`chat: \${res.status}\`);
  return res.json();
}`,
  },
  {
    n: "6",
    title: "Expansion de la question avec les sujets",
    file: "app/chat.py",
    lang: "python",
    intro:
      "Avant de chercher dans l'index, le backend ajoute les sujets sélectionnés (Python, AI/ML...) à la question.",
    code: `def _expand_query(question: str, topics: list[str]) -> str:
    # Si l'utilisateur a coché des sujets, on les colle à la question
    # avant de la transformer en vecteur (étape 7).
    #
    # Important : ce N'EST PAS un filtre strict du type
    # "WHERE topic = 'Python'". C'est juste un indice supplémentaire
    # donné au moteur de similarité, qui va orienter (sans garantir)
    # les résultats vers ces sujets.
    if not topics:
        return question
    return f"{question} | {', '.join(topics)}"

# Exemple :
# question = "Quelles tendances reviennent cette semaine ?"
# topics   = ["Python", "AI/ML"]
# -> "Quelles tendances reviennent cette semaine ? | Python, AI/ML"`,
  },
  {
    n: "7",
    title: "Recherche sémantique dans Chroma",
    file: "app/rag/retrieval.py",
    lang: "python",
    intro:
      "La question (enrichie) est vectorisée à son tour, puis comparée aux vecteurs déjà stockés pour Chroma renvoie les 8 chunks les plus proches en SENS.",
    code: `def retrieve(query: str, k: int = 8) -> list[dict[str, Any]]:
    try:
        collection = get_collection()

        # Même fonction d'embedding qu'à l'indexation (étape 4) :
        # la question et les articles doivent être projetés dans
        # le MÊME espace vectoriel pour être comparables.
        query_vec = embed(query)

        # On demande à Chroma : "donne-moi les k=8 chunks dont le
        # vecteur est le plus proche de query_vec".
        # -> l'équivalent d'un ORDER BY similarité DESC LIMIT 8,
        #    mais la "similarité" porte sur le SENS du texte,
        #    pas sur une correspondance de mots-clés.
        result = collection.query(query_embeddings=[query_vec], n_results=k)
    except Exception as exc:
        # Si Chroma est indisponible, on ne plante pas tout le
        # /chat : on renvoie une liste vide, le LLM répondra
        # sans contexte (ou le mode "degraded" prendra le relais).
        logger.warning("retrieval failed: %s", exc)
        return []

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]
    # "distance" = inverse de la similarité : plus c'est petit,
    # plus le chunk est proche du sens de la question.
    distances = (result.get("distances") or [[]])[0]

    chunks: list[dict[str, Any]] = []
    for doc_id, doc, meta, dist in zip(ids, docs, metas, distances, strict=False):
        chunks.append({"id": doc_id, "content": doc, "metadata": meta or {}, "distance": dist})
    return chunks`,
  },
  {
    n: "8",
    title: "Injection d'actualité fraîche (fresh news)",
    file: "app/runtime/fresh_news.py",
    lang: "python",
    intro:
      "En parallèle de l'index (qui couvre le fond), on appelle NewsAPI EN DIRECT pour les articles de moins de 7 jours sur les sujets choisis. Les articles sont nettoyés, indexés (upsert) et ajoutés au contexte du LLM.",
    code: `class FreshNewsRuntime:
    async def fetch_and_index(self, topics, since=None):
        # 1. EXTRACTION : NewsAPI live, tous les topics EN PARALLÈLE
        #    (asyncio.gather) pour tenir le budget latence < 3 s.
        raw = await self.fetch_raw(topics, since)   # since = 7 derniers jours

        # 2. NETTOYAGE : on réutilise cleaning.py (dedupe, HTML→texte)
        #    -> pas de duplication de code, mêmes règles que le batch.
        articles = self.process_and_clean(raw)

        if articles:
            try:
                # 3. INDEXATION : délégué à ChromaIngester.store()
                #    -> chunk + metadata (fetched_at, type="online") + UPSERT.
                #    L'upsert garantit zéro doublon si le même article
                #    revient à la prochaine question.
                #    asyncio.to_thread : l'embedding est du calcul CPU,
                #    on le sort de l'event loop pour ne pas bloquer
                #    les autres utilisateurs pendant ce temps.
                await asyncio.to_thread(self.upsert_to_chroma, articles)
            except Exception as exc:
                # Chroma en panne ≠ pas de fresh news : on sert quand
                # même les articles au chat, l'index attendra.
                logger.warning("indexing failed (%s)", exc)

        # 4. RESTITUTION : Documents LangChain prêts pour le prompt
        return self.to_documents(articles)

# Bonus, dans app/ingest/enrich.py : "neighbor expansion".
# Les ids de chunks sont composés "{id_article}-{index}" : si la
# recherche remonte le chunk 2 d'un article, on récupère aussi les
# chunks 1 et 3 (lookup direct par id, quasi gratuit) pour donner
# plus de contexte au LLM.`,
  },
  {
    n: "9",
    title: "Le LLM rédige la synthèse",
    file: "app/rag/llm.py",
    lang: "python",
    intro:
      "Les chunks trouvés sont injectés dans un prompt envoyé au LLM (Kimi-K2.6 via Azure AI Inference). Le LLM répond en JSON : un texte de synthèse + une liste de cartes.",
    code: `# Le "system prompt" = la consigne fixe donnée au LLM AVANT chaque
# conversation. Analogie : un template de rapport qu'on redonnerait
# à un analyste à chaque mission, avec les règles à respecter.
SYSTEM_PROMPT = (
    "Tu es l'assistant de veille technologique interne de Nauda Palisse.\\n"
    "Réponds en français, factuel, concis. Cite tes sources via les "
    "cartes d'articles.\\n"
    "Si aucun article n'est fourni, dis-le poliment et ne fabrique rien.\\n"
    "Format de sortie attendu : JSON strict avec les clés \`answer\` "
    "(string) et \`cards\` (liste d'objets {title, source, date, "
    "snippet, url, tags})."
)


async def compose_answer(*, question, topics, retrieved_chunks, fresh_articles):
    # On transforme déjà les chunks en "cartes" affichables, qu'on
    # ait ou non un LLM disponible -> l'utilisateur voit toujours
    # les sources, même si la synthèse écrite échoue.
    cards = _build_cards(retrieved_chunks, fresh_articles)

    if not retrieved_chunks and not fresh_articles:
        # Aucune donnée trouvée -> pas la peine d'appeler le LLM.
        # Comme un rapport vide quand la requête SQL ne renvoie
        # aucune ligne : pas d'analyse à faire.
        return ChatResponse(answer="Aucun article ne couvre ce sujet...", cards=[], status="empty")

    llm = get_llm()
    if llm is None:
        # Pas de clé Azure configurée -> "mode dégradé" :
        # on renvoie quand même les sources brutes trouvées,
        # sans synthèse rédigée.
        return ChatResponse(
            answer=f"{len(cards)} article(s) trouvé(s) pour : {question}. LLM non configuré.",
            cards=cards,
            status="degraded",
        )

    # On envoie au LLM : la question, les sujets, et le "contexte"
    # = les extraits de chunks (étape 7), formatés en texte numéroté
    # ([1], [2]...) pour que le LLM puisse les citer.
    user_payload = {
        "question": question,
        "topics": topics,
        "context": _format_context(retrieved_chunks, fresh_articles),
    }

    msg = await llm.ainvoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
    ])

    # Le LLM renvoie du texte ; on essaie de le parser en JSON pour
    # n'en garder que le champ "answer" (la synthèse).
    answer = _extract_answer(msg.content)
    return ChatResponse(answer=answer, cards=cards, status="ok")`,
  },
  {
    n: "10",
    title: "Affichage des cartes",
    file: "web/app/page.tsx",
    lang: "tsx",
    intro:
      "Le frontend affiche la synthèse (answer) en haut, puis une grille de cartes : titre, source, date, extrait, tags et lien vers l'article original.",
    code: `// Chaque "card" reçue de l'API devient un bloc visuel.
// -> un peu comme générer une grille de fiches produit à partir
//    des lignes d'un tableau de résultats (une carte = une ligne).
function Card({ card }: { card: ArticleCard }) {
  return (
    <article>
      <h3>{card.title}</h3>
      <div>
        {card.source}
        {/* date stockée en ISO côté backend, reformatée en français ici */}
        {card.date && \` · \${new Date(card.date).toLocaleDateString("fr-FR")}\`}
      </div>
      <p>{card.snippet}</p>

      {/* tags = liste libre de mots-clés, colorés via une fonction
          de hash -> le même tag a toujours la même couleur */}
      {card.tags.map((t) => (
        <span key={t}>{t}</span>
      ))}

      {/* Toujours un lien vers la source d'origine : l'utilisateur
          peut vérifier l'information, le LLM ne remplace pas la
          source, il la résume. */}
      {card.url && <a href={card.url}>Lire l'article →</a>}
    </article>
  );
}`,
  },
];

const GLOSSARY: { term: string; def: string }[] = [
  {
    term: "RAG (Retrieval-Augmented Generation)",
    def: "On cherche d'abord les documents pertinents dans une base, puis on demande au LLM de répondre EN S'APPUYANT sur ces documents — plutôt que de compter sur ce qu'il a mémorisé pendant son entraînement.",
  },
  {
    term: "Embedding",
    def: "Représentation d'un texte sous forme de vecteur de nombres. Deux textes de sens proche ont des vecteurs proches : c'est ce qui permet une recherche « par sens » plutôt que par mot-clé exact.",
  },
  {
    term: "Base vectorielle (ChromaDB)",
    def: "Base de données spécialisée pour stocker des vecteurs et retrouver très vite les plus proches d'un vecteur de requête (recherche par similarité, pas par égalité).",
  },
  {
    term: "Chunk",
    def: "Petit morceau de texte (ici ~1200 caractères, découpé par LangChain avec un chevauchement de ~10% entre morceaux). Unité de base pour l'indexation, la recherche et la citation des sources.",
  },
  {
    term: "Prompt système",
    def: "Instruction fixe donnée au LLM avant la conversation : son rôle, son ton, le format de réponse attendu (ici : JSON avec `answer` et `cards`).",
  },
  {
    term: "Mode dégradé (status: degraded)",
    def: "Quand la clé du LLM n'est pas configurée, l'API renvoie quand même les articles trouvés par la recherche sémantique, mais sans synthèse rédigée.",
  },
];

export function HowItWorks() {
  return (
    <section id="comment-ca-marche" className="mt-16 scroll-mt-6">
      <div className="mb-8 border-t border-white/10 pt-8">
        <h2 className="text-2xl font-semibold tracking-tight">
          Comment ça marche ?
        </h2>
        <p className="mt-2 max-w-3xl text-sm text-neutral-400">
          L'assistant ci-dessus repose sur un pipeline RAG (Retrieval-Augmented
          Generation) en deux temps : une phase d'indexation en arrière-plan,
          et une phase de conversation à chaque question. Chaque étape
          ci-dessous montre le code réel du projet, commenté avec des
          analogies « data analyst ».
        </p>
      </div>

      <div className="mb-10 rounded-2xl border border-white/10 bg-white/5 p-6">
        <h3 className="mb-4 text-base font-semibold text-white">
          Schéma global
        </h3>
        <div className="space-y-4 text-sm">
          <div>
            <div className="mb-2 text-xs uppercase tracking-wider text-indigo-300">
              Phase A — Indexation (en arrière-plan)
            </div>
            <FlowChain
              steps={[
                "Sources (RSS, GitHub, NewsAPI, web)",
                "Nettoyage (HTML→texte, dédoublonnage)",
                "Découpage en chunks",
                "Embeddings",
                "ChromaDB",
              ]}
              accent="indigo"
            />
          </div>
          <div>
            <div className="mb-2 text-xs uppercase tracking-wider text-emerald-300">
              Phase B — Conversation (à chaque question)
            </div>
            <FlowChain
              steps={[
                "Question + sujets",
                "Expansion de la requête",
                "Recherche sémantique (ChromaDB)",
                "Fresh news (NewsAPI live, < 7 jours)",
                "LLM (Kimi-K2.6)",
                "Synthèse + cartes",
              ]}
              accent="emerald"
            />
          </div>
        </div>
      </div>

      <div className="space-y-8">
        <div>
          <h3 className="mb-1 text-base font-semibold text-white">
            Phase A — Indexation
          </h3>
          <p className="mb-4 text-sm text-neutral-400">
            Construit petit à petit la base de connaissances, indépendamment
            des questions des utilisateurs (lancé via{" "}
            <code className="rounded bg-black/40 px-1 py-0.5 text-xs">
              scripts/ingest_cli.py
            </code>
            ).
          </p>
          <div className="space-y-4">
            {INDEX_STEPS.map((step) => (
              <StepCard key={step.n} step={step} accent="indigo" />
            ))}
          </div>
        </div>

        <div>
          <h3 className="mb-1 text-base font-semibold text-white">
            Phase B — Conversation
          </h3>
          <p className="mb-4 text-sm text-neutral-400">
            Se déroule en quelques secondes lorsqu'un utilisateur clique sur
            « Lancer la veille ».
          </p>
          <div className="space-y-4">
            {QUERY_STEPS.map((step) => (
              <StepCard key={step.n} step={step} accent="emerald" />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-10">
        <h3 className="mb-4 text-base font-semibold text-white">Glossaire</h3>
        <dl className="grid gap-4 sm:grid-cols-2">
          {GLOSSARY.map((g) => (
            <div
              key={g.term}
              className="rounded-xl border border-white/10 bg-white/5 p-4"
            >
              <dt className="mb-1 text-sm font-semibold text-indigo-200">
                {g.term}
              </dt>
              <dd className="text-sm text-neutral-300">{g.def}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function FlowChain({
  steps,
  accent,
}: {
  steps: string[];
  accent: "indigo" | "emerald";
}) {
  const box =
    accent === "indigo"
      ? "border-indigo-400/30 bg-indigo-500/10"
      : "border-emerald-400/30 bg-emerald-500/10";

  return (
    <div className="flex flex-wrap items-center gap-2">
      {steps.map((s, i) => (
        <div key={s} className="flex items-center gap-2">
          <span className={`rounded-lg border px-3 py-1.5 text-xs ${box}`}>
            {s}
          </span>
          {i < steps.length - 1 && (
            <span className="text-neutral-600">→</span>
          )}
        </div>
      ))}
    </div>
  );
}

function StepCard({
  step,
  accent,
}: {
  step: Step;
  accent: "indigo" | "emerald";
}) {
  const ring =
    accent === "indigo" ? "border-indigo-400/40" : "border-emerald-400/40";
  const badge =
    accent === "indigo"
      ? "bg-indigo-500/20 text-indigo-200"
      : "bg-emerald-500/20 text-emerald-200";

  return (
    <article className={`rounded-xl border ${ring} bg-white/5 p-4`}>
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${badge}`}
        >
          {step.n}
        </span>
        <div className="flex-1">
          <h4 className="font-medium text-white">{step.title}</h4>
          <div className="mt-0.5 text-xs text-neutral-500">{step.file}</div>
          <p className="mt-1 text-sm text-neutral-300">{step.intro}</p>
        </div>
      </div>
      <pre className="mt-3 overflow-x-auto rounded-lg bg-black/40 p-3 text-xs leading-relaxed text-neutral-300">
        <code>{step.code}</code>
      </pre>
    </article>
  );
}
