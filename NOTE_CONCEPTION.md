# Note de Conception — Assistant Veille Tech

## 1. Architecture globale

```
┌─ INGESTION ──────────────────────────────────────────┐
│ NewsAPI + Web Scraper + HackerNews                   │
│    ↓                                                  │
│ cleaning.py (HTML→Markdown, dedupe, chunk, tag)      │
│    ↓                                                  │
│ ChromaIngester (embed + upsert)                       │
│    ↓                                                  │
│ ChromaDB (vectorial index, type=batch/online/chat)   │
└──────────────────────────────────────────────────────┘

┌─ RUNTIME (< 3s) ─────────────────────────────────────┐
│ User question                                         │
│    ↓                                                  │
│ Parallel: Chroma search + NewsAPI + HN + History    │
│    ↓                                                  │
│ LLM synthesis (Azure AI Kimi-K2.6)                   │
│    ↓                                                  │
│ ChatResponse (answer + cards + trending)             │
└──────────────────────────────────────────────────────┘
```

## 2. Modèle des données

### Métadonnées dans Chroma

```json
{
  "id": "md5(url)",
  "title": "Article title",
  "source": "NewsAPI|Scraper|HackerNews|ChatHistory",
  "date": "2026-06-15T10:30:00Z",
  "url": "https://...",
  "tags": "LLM,DevOps",  // Auto-detected or user-provided
  "type": "batch|online|chat",
  "chunk_index": 0,
  "fetched_at": "2026-06-15T08:45:00Z"
}
```

### Types d'articles

- **batch** : ingestion batch (scraper + NewsAPI)
- **online** : injection fresh news (< 7 jours)
- **chat** : conversation history (sémantique retrieval)

## 3. Sources de données

| Source | Type | Latency | Coverage |
|--------|------|---------|----------|
| Chroma index | Batch | ~200ms | All indexed articles |
| NewsAPI | Fresh | ~500ms | Top 5 articles/topic |
| HackerNews | Fresh | ~1s | Top 30 stories/24h |
| Chat history | Fresh | ~100ms | Previous Q&A |

## 4. Tagging automatique

6 catégories détectées par heuristiques (mots-clés) :

- **LLM** : llm, gpt, claude, prompt, langchain
- **DevOps** : docker, k8s, ci/cd, terraform
- **Frontend** : react, vue, css, typescript
- **Backend** : node, python, api, database, fastapi
- **Data** : sql, bigquery, analytics, pandas, spark
- **FinOps** : cost, billing, pricing, aws, gcp

Trending = tags apparaissant 3+ fois dans résultats.

## 5. Choix techniques

| Aspect | Choix | Raison |
|--------|-------|--------|
| Vector DB | Chroma | Sémantique + léger |
| Embeddings | sentence-transformers | 384-dim, multilingue, local |
| Chunking | LangChain RecursiveCharacterTextSplitter | Hiérarchique, overlap |
| LLM | Azure AI Kimi-K2.6 | Ouvert, cost-effective |
| Frontend | Next.js 15 | React SSR, modern |
| Orchestration | Docker Compose | Simple, local dev |

## 6. Flux ingestion

```
CLI: make ingest
  ├─ news -t <topic>  → NewsAPI → cleaning → ChromaIngester → Chroma
  └─ scrape           → Web scraping → cleaning → ChromaIngester → Chroma
```

## 7. Flux chat (runtime)

```
POST /chat {question, topics}
  ├─ Parallel fetch:
  │  ├─ Chroma.query(k=8)
  │  ├─ NewsAPI.fetch(topics)
  │  ├─ HackerNews.fetch()
  │  └─ ChatHistory.retrieve()
  ├─ detect_tags() + _detect_trending()
  ├─ LLM synthesis
  └─ ChatResponse {answer, cards, trending, status}
```

---

**État :** Tous les éléments demandés implémentés et testés (25/25 passing).
