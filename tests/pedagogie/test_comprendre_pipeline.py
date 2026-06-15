"""
🎓 SÉRIE DE TESTS PÉDAGOGIQUES — comprendre le pipeline en l'exécutant.

Chaque test démontre UN concept de ce qu'on a implémenté, dans l'ordre
du pipeline :

  PARTIE 1 (tests 01-03) : NORMALISATION    — news_api.py
  PARTIE 2 (tests 04-06) : NETTOYAGE        — cleaning.py
  PARTIE 3 (test  07)    : LE BUG DU QUOTA  — news_api.py (pourquoi ça plante)
  PARTIE 4 (tests 08-09) : EMBEDDINGS & RECHERCHE SÉMANTIQUE — retrieval.py

Lance-les avec :

    uv run pytest tests/pedagogie -v

Astuce : ajoute -s pour voir les print() explicatifs :

    uv run pytest tests/pedagogie -v -s
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ingest.cleaning import chunk, clean_html_to_markdown, dedupe
from app.ingest.news_api import NewsApiIngester
from app.schemas import Article

# ---------------------------------------------------------------------------
# PARTIE 1 — NORMALISATION : du JSON brut de NewsAPI vers notre format Article
# ---------------------------------------------------------------------------

# Voici à quoi ressemble UN article tel que NewsAPI nous le renvoie.
# Remarque : "source" est un objet imbriqué, les dates sont des strings,
# et certains champs peuvent manquer.
ARTICLE_NEWSAPI_BRUT = {
    "source": {"id": "techcrunch", "name": "TechCrunch"},
    "author": "Jane Doe",
    "title": "OpenAI releases a new model",
    "description": "Un résumé court et propre de l'article.",
    "url": "https://techcrunch.com/2026/06/09/openai-new-model/",
    "publishedAt": "2026-06-09T10:30:00Z",
    "content": "Les 200 premiers caractères seulement… [+1234 chars]",
}


def test_01_format_article_normalise_le_json_brut():
    """format_article() convertit le format NewsAPI vers NOTRE format Article.

    C'est le concept de NORMALISATION : peu importe la source (NewsAPI,
    RSS, GitHub…), tout le reste du pipeline ne manipule qu'un seul
    format. La conversion se fait ICI, à la frontière.
    """
    ingester = NewsApiIngester()

    article = ingester.format_article(ARTICLE_NEWSAPI_BRUT)

    # Le résultat est un objet Article (notre modèle Pydantic), plus un dict
    assert isinstance(article, Article)

    # "source" était un objet {"id":…, "name":…} → on n'a gardé que le nom
    assert article.source == "TechCrunch"

    # Le titre et l'URL sont repris tels quels
    assert article.title == "OpenAI releases a new model"
    assert str(article.url) == "https://techcrunch.com/2026/06/09/openai-new-model/"

    # La date string ISO a été parsée en VRAI objet datetime par Pydantic
    # (on peut maintenant la comparer, la trier, calculer une ancienneté)
    assert article.date is not None
    assert article.date.year == 2026


def test_02_id_idempotent_meme_url_meme_id():
    """L'ID est un hash md5 de l'URL → DÉTERMINISTE.

    Concept clé : l'IDEMPOTENCE. Si on ré-ingère le même article demain,
    il aura le même ID, donc un upsert dans Chroma ÉCRASE l'ancien au
    lieu de créer un doublon. On peut relancer l'ingestion sans risque.
    """
    ingester = NewsApiIngester()

    article_lundi = ingester.format_article(ARTICLE_NEWSAPI_BRUT)
    article_mardi = ingester.format_article(ARTICLE_NEWSAPI_BRUT)

    # Même URL → même ID, même si on l'ingère deux jours de suite
    assert article_lundi.id == article_mardi.id

    # URL différente → ID différent
    autre = dict(ARTICLE_NEWSAPI_BRUT, url="https://autre-site.com/article")
    article_autre = ingester.format_article(autre)
    assert article_autre.id != article_lundi.id


def test_03_fallback_description_puis_content_puis_vide():
    """Le pattern `a or b or ""` : une chaîne de plans B pour le contenu.

    NewsAPI tronque "content" à ~200 caractères, donc on PRÉFÈRE
    "description" (le résumé complet). Si les deux manquent, on retombe
    sur "" — c'est une limite : un article vide passe quand même
    (pas de validation stricte ici).
    """
    ingester = NewsApiIngester()

    # Cas 1 : description présente → c'est elle qui gagne
    article = ingester.format_article(ARTICLE_NEWSAPI_BRUT)
    assert article.content == "Un résumé court et propre de l'article."

    # Cas 2 : pas de description → on se rabat sur content
    sans_description = dict(ARTICLE_NEWSAPI_BRUT, description=None)
    article = ingester.format_article(sans_description)
    assert article.content.startswith("Les 200 premiers caractères")

    # Cas 3 : ni l'un ni l'autre → chaîne vide (l'article passe quand même !)
    sans_rien = dict(ARTICLE_NEWSAPI_BRUT, description=None, content=None)
    article = ingester.format_article(sans_rien)
    assert article.content == ""


# ---------------------------------------------------------------------------
# PARTIE 2 — NETTOYAGE : HTML → texte propre, dédoublonnage, découpage
# ---------------------------------------------------------------------------


def test_04_clean_html_retire_le_bruit():
    """clean_html_to_markdown() garde le contenu, jette le 'boilerplate'.

    Une page web contient le contenu utile (l'article) noyé dans du
    bruit : menus, footer, bandeaux cookies, scripts… Si on indexait
    tout ça, la recherche sémantique trouverait des "articles" qui
    parlent de cookies et de navigation.
    """
    page_html = """
    <html>
      <head><title>Mon blog</title><script>tracking();</script></head>
      <body>
        <nav>Accueil | Articles | Contact</nav>
        <div class="cookie-banner">Acceptez nos cookies !</div>
        <article>
          <h1>Python 3.13 est sorti</h1>
          <p>Le GIL devient optionnel, voici ce que ça change.</p>
        </article>
        <footer>© 2026 Mon blog — mentions légales</footer>
      </body>
    </html>
    """

    texte = clean_html_to_markdown(page_html)

    # ✅ Le contenu de l'article est conservé (converti en Markdown)
    assert "Python 3.13 est sorti" in texte
    assert "Le GIL devient optionnel" in texte

    # ❌ Le bruit a disparu : nav, cookies, footer, scripts
    assert "Accueil | Articles" not in texte
    assert "cookies" not in texte
    assert "mentions légales" not in texte
    assert "tracking" not in texte


def test_05_dedupe_supprime_les_doublons():
    """dedupe() = drop_duplicates() avec DEUX clés possibles.

    Pourquoi deux clés ? Le même article est parfois republié sous une
    URL différente (ex : prnewswire.com ET prnewswire.co.uk). L'URL ne
    suffit donc pas : on déduplique AUSSI sur le couple (source, titre).
    """
    articles = [
        {"url": "https://a.com/1", "source": "A", "title": "Titre 1"},
        # Doublon exact par URL (republié tel quel)
        {"url": "https://a.com/1", "source": "A", "title": "Titre 1 modifié"},
        # URL différente MAIS même (source, titre) → doublon quand même
        {"url": "https://a.com/1-bis", "source": "A", "title": "Titre 1"},
        # Vraiment un autre article → conservé
        {"url": "https://b.com/2", "source": "B", "title": "Titre 2"},
    ]

    uniques = dedupe(articles)

    # 4 entrées → 2 articles réellement distincts
    assert len(uniques) == 2
    assert uniques[0]["url"] == "https://a.com/1"
    assert uniques[1]["url"] == "https://b.com/2"


def test_06_chunk_decoupe_avec_langchain():
    """chunk() délègue le découpage au RecursiveCharacterTextSplitter
    de LangChain — l'outil standard des pipelines RAG.

    Deux idées à comprendre :

    1. Le découpage RÉCURSIF : le splitter essaie de couper d'abord
       entre les paragraphes ("\\n\\n"), puis entre les lignes, puis
       entre les phrases (". "), puis entre les mots — il ne descend
       d'un niveau que si le morceau est encore trop gros.

    2. L'OVERLAP (chevauchement) : la fin d'un chunk est RÉPÉTÉE au
       début du suivant. Ainsi, une idée à cheval sur la coupure reste
       lisible en entier dans au moins un des deux chunks.
    """
    # Un texte court n'est PAS découpé : un seul chunk
    court = "Une seule phrase courte."
    assert chunk(court, max_chars=100) == [court]

    # Un texte long est découpé en plusieurs morceaux
    longue_phrase = "Voici une phrase qui fait à peu près soixante caractères. "
    texte_long = longue_phrase * 10  # ~600 caractères

    morceaux = chunk(texte_long, max_chars=200, overlap=60)

    assert len(morceaux) > 1  # il y a bien eu découpage
    for morceau in morceaux:
        # Chaque morceau respecte la taille max…
        assert len(morceau) <= 200
        # …et se termine à une frontière de phrase (pas en plein milieu)
        assert morceau.endswith(".")

    # L'OVERLAP en action : la dernière phrase du chunk 1 est répétée
    # au début du chunk 2 (le filet de sécurité aux coupures).
    fin_chunk_1 = morceaux[0][-len(longue_phrase.strip()):]
    assert morceaux[1].startswith(fin_chunk_1)

    # Le découpage HIÉRARCHIQUE : avec deux paragraphes séparés par
    # "\n\n", le splitter coupe à la frontière de paragraphe (niveau 1)
    # plutôt qu'au milieu d'un paragraphe.
    para_1 = "Premier paragraphe sur Python. " * 3
    para_2 = "Second paragraphe sur Docker. " * 3
    deux_paras = f"{para_1.strip()}\n\n{para_2.strip()}"

    morceaux = chunk(deux_paras, max_chars=120, overlap=0)
    # Aucun chunk ne mélange les deux sujets : la coupure de paragraphe
    # a été préférée à une coupure en plein milieu.
    for morceau in morceaux:
        assert not ("Python" in morceau and "Docker" in morceau)


# ---------------------------------------------------------------------------
# PARTIE 3 — LE BUG DU QUOTA : pourquoi `news` plante en conditions réelles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_07_le_bug_du_quota_un_echec_tue_tout_le_batch():
    """Démontre la ROBUSTESSE : même si une page échoue, les articles récupérés sont gardés.

    Le plan gratuit NewsAPI limite à 100 résultats par recherche.
    Ancienne implémentation sync → exception = tout perdu.
    Nouvelle implémentation async → try/except = articles gardés, topic suivant.

    Le test utilise respx pour mocker les appels HTTP directement.
    """
    from httpx import Response
    import respx

    page_1_ok = {
        "status": "ok",
        "articles": [dict(ARTICLE_NEWSAPI_BRUT, url=f"https://x.com/{i}") for i in range(10)],
    }
    page_2_erreur = {
        "status": "error",
        "code": "maximumResultsReached",
        "message": "Developer accounts are limited to a max of 100 results.",
    }

    with patch("app.ingest.news_api.get_collection"):
        ingester = NewsApiIngester()

        with respx.mock:
            # Page 1 OK, page 2 erreur
            respx.get("https://newsapi.org/v2/everything").mock(
                side_effect=[
                    Response(200, json=page_1_ok),
                    Response(400, json=page_2_erreur),
                ]
            )

            # L'implémentation async attrape l'erreur et continue
            articles = await ingester.run(["python"], pages_per_topic=2)

            # ✅ La leçon : les 10 articles de la page 1 sont gardés
            assert len(articles) == 10
            assert all("id" in a for a in articles)


# ---------------------------------------------------------------------------
# PARTIE 4 — EMBEDDINGS & RECHERCHE SÉMANTIQUE : le cœur du RAG
# ---------------------------------------------------------------------------


def test_08_les_embeddings_capturent_le_sens_pas_les_mots():
    """Deux phrases de même SENS ont des vecteurs proches, même sans
    mots en commun. C'est ça, la magie des embeddings.

    On vectorise 3 phrases et on compare les similarités :
      A et B parlent toutes deux d'erreurs Python (mots différents)
      C parle de cuisine

    Attendu : similarité(A, B) > similarité(A, C)

    NB : nos vecteurs sont normalisés (longueur 1), donc le produit
    scalaire EST la similarité cosinus (entre -1 et 1, 1 = identique).
    """
    from app.rag.retrieval import embed  # import ici : charge le modèle (~5s)

    vec_a = embed("Mon script Python plante avec une exception")
    vec_b = embed("Une erreur survient pendant l'exécution de mon programme Python")
    vec_c = embed("La recette de la tarte aux pommes de ma grand-mère")

    def similarite(v1: list[float], v2: list[float]) -> float:
        return sum(x * y for x, y in zip(v1, v2))

    sim_meme_sens = similarite(vec_a, vec_b)
    sim_sens_different = similarite(vec_a, vec_c)

    print(f"\n  sim(bug Python, erreur programme) = {sim_meme_sens:.3f}")
    print(f"  sim(bug Python, tarte aux pommes) = {sim_sens_different:.3f}")

    # Le modèle "comprend" que A et B parlent de la même chose
    assert sim_meme_sens > sim_sens_different

    # Au passage : un embedding = simple liste de nombres (384 dimensions)
    assert len(vec_a) == 384


def _chroma_local_disponible() -> bool:
    """Vrai si le conteneur Chroma tourne (port 8002 mappé par docker-compose)."""
    try:
        return httpx.get("http://localhost:8002/api/v1/heartbeat", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(
    not _chroma_local_disponible(),
    reason="Chroma n'est pas lancé — démarre la stack avec `docker compose up -d`",
)
def test_09_recherche_semantique_dans_la_vraie_base(monkeypatch):
    """Le test final : interroger la VRAIE base Chroma remplie par le scraping.

    C'est exactement ce que fait le backend quand tu poses une question
    dans l'interface (app/rag/retrieval.py → retrieve()).

    Subtilité d'environnement : dans Docker, Chroma s'appelle
    `chromadb:8000` ; depuis ta machine, c'est `localhost:8002` (le port
    mappé). On surcharge donc CHROMA_URL le temps du test.
    """
    from app.config import get_settings
    from app.rag import retrieval
    from app.rag.chroma_client import get_client

    # get_settings() et get_client() sont mémorisés (@lru_cache) : on vide
    # leurs caches pour que la nouvelle valeur de CHROMA_URL soit relue.
    monkeypatch.setenv("CHROMA_URL", "http://localhost:8002")
    get_settings.cache_clear()
    get_client.cache_clear()
    try:
        resultats = retrieval.retrieve("nouvelles versions de FastAPI", k=5)

        # La base contient ~390 articles scrapés : on doit trouver des chunks
        assert len(resultats) > 0

        # Chaque résultat a la structure attendue par le reste du pipeline
        premier = resultats[0]
        assert {"id", "content", "metadata", "distance"} <= set(premier)

        # Les résultats sont triés du plus proche au plus lointain
        # (distance PETITE = sens PROCHE de la question)
        distances = [r["distance"] for r in resultats]
        assert distances == sorted(distances)

        print("\n  Top 5 pour « nouvelles versions de FastAPI » :")
        for r in resultats:
            titre = r["metadata"].get("title", "?")[:60]
            print(f"  distance={r['distance']:.3f}  {titre}")
    finally:
        # On remet les caches à zéro pour ne pas polluer d'autres tests
        get_settings.cache_clear()
        get_client.cache_clear()
