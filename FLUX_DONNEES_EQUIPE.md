# Flux de données — Guide équipe

## 1. Ingestion (Batch)

```bash
make ingest
```

### Commands

**Fetch NewsAPI :**
```bash
python -m scripts.ingest_cli news -t ai -t devops
```
- Récupère 5 articles/topic
- Déduplique, nettoie HTML
- Détecte tags automatiquement
- Stock dans Chroma (type="batch")

**Web Scraping :**
```bash
python -m scripts.ingest_cli scrape
```
- Scrape URLs configurées
- Parse HTML, nettoie boilerplate
- Chunk et embed
- Stock dans Chroma

## 2. Chat Query (Runtime)

```
User question → FastAPI /chat endpoint
  ↓
1. Embed question → 384-dim vector
2. Parallel fetch (asyncio.gather):
   - Chroma semantic search (k=8) → ~200ms
   - NewsAPI live fetch → ~500ms
   - HackerNews fetch → ~1s
   - Chat history retrieve → ~100ms
  ↓
3. Combine ~16 articles
  ↓
4. detect_tags() + _detect_trending() (3+ rule)
  ↓
5. LLM synthesis (Azure AI)
  ↓
6. ChatResponse {answer, cards, trending, status}
  ↓
7. Store Q&A in chat_history (type="chat")
  ↓
Frontend renders
```

## 3. Métadonnées

Chaque article dans Chroma a :
- `title`, `source`, `url`, `date`
- `tags` : détectés automatiquement (CSV)
- `type` : batch | online | chat
- `chunk_index`, `fetched_at`

## 4. Tagging & Trending

**detect_tags()** scans text pour mots-clés :
- 6 catégories : LLM, DevOps, Frontend, Backend, Data, FinOps

**_detect_trending()** compte tags dans résultats :
- Si tag apparaît 3+ fois → marked trending

## 5. Performance

| Component | Target | Actual |
|-----------|--------|--------|
| Batch ingest | < 30 min | ~20 min |
| Chroma query | < 500ms | ~200ms |
| Total /chat | < 3s | ~2-3s |

## 6. Failure modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Chroma down | High | Status="empty" |
| NewsAPI quota | Medium | Skip topic, continue |
| LLM Azure down | Medium | Status="degraded", raw articles |
| Chat history fail | Low | Log warning, continue |

---

**All requests are logged. System degrades gracefully on errors.**
