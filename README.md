# Assistant Veille Tech — Nauda Palisse

Nauda Palisse — assistant de veille technologique. RAG sur Chroma + injection de news fraîches + scraping de sources tech.

## Fonctionnalités

- Sélection de sujets populaires (Python, JavaScript, AI/ML, DevOps, Web) + saisie libre
- Question en langage naturel → réponse synthétique citant ses sources
- Retrieval sémantique sur une base vectorielle (Chroma) alimentée par scraping et NewsAPI
- Injection d'articles récents au moment du chat pour couvrir l'actualité chaude
- UI Next.js : grille de cards (titre, source, date, snippet, tags couleur, lien)

## Stack

- **Backend** : Python 3.11, uv, FastAPI ≥0.115, Pydantic 2
- **RAG** : ChromaDB 0.5, sentence-transformers 3 (`intfloat/multilingual-e5-small`)
- **LLM** : LangChain 0.3 + `langchain-azure-ai` → Azure AI Inference (Kimi-K2.6)
- **Scraping / HTTP** : httpx 0.27, BeautifulSoup 4, markdownify
- **Frontend** : Next.js 15 (App Router), React 19, TypeScript 5, Tailwind CSS 4
- **Orchestration** : Docker Compose (chromadb + backend + frontend)

## Layout

```
.
├── app/                      # backend FastAPI
│   ├── main.py               # endpoints /health, /topics, /chat
│   ├── chat.py               # orchestration retrieval + fresh news + LLM
│   ├── config.py             # settings (env)
│   ├── schemas.py            # modèles pydantic
│   ├── rag/
│   │   ├── chroma_client.py  # client HTTP Chroma + collection `articles`
│   │   ├── retrieval.py      # embedding + query top-k
│   │   └── llm.py            # pipeline LangChain → Azure AI (Kimi-K2.6)
│   ├── ingest/
│   │   ├── news_api.py       # ingester NewsAPI → Chroma
│   │   ├── scraper.py        # scraping de sources tech
│   │   ├── cleaning.py       # HTML→Markdown, dedup, chunking, boilerplate
│   │   └── enrich.py         # hook d'enrichissement post-retrieval
│   └── runtime/
│       └── fresh_news.py     # fetch live NewsAPI au moment du chat
├── scripts/
│   └── ingest_cli.py         # CLI d'ingestion (news / scrape)
├── tests/
│   └── acceptance/           # tests d'acceptance de la chaîne d'ingestion
├── web/                      # frontend Next.js 15
│   ├── app/                  # App Router (page principale + layout)
│   ├── lib/api.ts            # client REST vers le backend
│   └── Dockerfile
├── Dockerfile.backend
├── docker-compose.yml
├── Makefile
├── pyproject.toml
└── .env.example
```

## Setup

```bash
cp .env.example .env          # renseigner AZURE_AI_INFERENCE_*, NEWS_API_KEY
make install                  # uv sync (backend)
make up                       # docker compose up -d (chromadb + backend + frontend)
```

- Backend : http://localhost:8000 (`/health`, `/topics`, `/chat`)
- Frontend : http://localhost:3000
- ChromaDB : http://localhost:8002

Tests :

```bash
make test                     # uv run pytest
```

Ingestion (CLI) :

```bash
make ingest                   # passe par scripts/ingest_cli.py
```

## Sources potentielles

Voici quelques pistes de sources publiques utilisables pour alimenter l'index :

- **NewsAPI v2** (`/everything`, `/top-headlines`) — documentation : https://newsapi.org/docs
- **Blogs et agrégateurs techniques** — par exemple Hacker News (front page / item API), DEV.to, Smashing Magazine, lobste.rs
- **Changelogs produits** — par exemple Vercel, OpenAI, GitHub, Anthropic, Stripe
- **Pages de docs / annonces** — par exemple les release notes des frameworks de l'écosystème (Next.js, FastAPI, LangChain), les changelogs Python / Node

Le choix exact des sources reste à arbitrer en fonction des sujets ciblés et de la fraîcheur attendue.

## Aller plus loin (optionnel)

La stack est extensible vers **Postgres** pour porter des comptes utilisateur (sign-up / sign-in), des sujets favoris et un historique des recherches — non couvert ici. Cela ajouterait des endpoints `/users`, `/me/favorites`, `/me/history` et une page « Mon compte » côté frontend, avec un schéma user-scoped et les obligations RGPD associées (hash des mots de passe, durée de conservation, droit à l'effacement).

## Utiles

```bash
make fmt        # ruff format + autofix
make lint       # ruff check
make typecheck  # mypy
make logs       # docker compose logs -f
make down       # stop services
```

## Licence

Interne Nauda Palisse.

## Contact

veille@nauda-palisse.example
