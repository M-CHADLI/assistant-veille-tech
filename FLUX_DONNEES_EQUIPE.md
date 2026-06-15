# Flux de données bout à bout — Guide équipe

**Destiné à :** Développeurs, DevOps, Product Managers  
**Objectif :** Comprendre le flux complet des données du projet  
**Temps de lecture :** 5 min

---

## TL;DR (résumé 30 sec)

```
Articles (NewsAPI, HackerNews, Web) 
  → Nettoyage (HTML, dedupe, tagging)
  → Chroma (vecteurs, indexation)
  → Chat (recherche sémantique + LLM)
  → Frontend (cartes, tendances)
```

**Architecture :** Backend Python (FastAPI) + Database (Chroma) + Frontend (Next.js)  
**Latency :** Batch ingestion ~30 min, Chat query < 3s  
**Tests :** 25/25 passing

---

## 1. Comment les articles arrivent (Ingestion)

### Option A : Batch (Daily, CLI)

```bash
# Terminal
make ingest

# What happens:
1. NewsApiIngester.run()
   └─ Fetch from newsapi.org/v2/everything
   └─ 5 articles per topic (ai, devops, frontend, backend, data, finops)
   └─ Parse JSON

2. Scraper.run()
   └─ Fetch RSS feeds + GitHub Releases
   └─ Parse HTML with BeautifulSoup
   └─ Extract title, content, date

3. cleaning.dedupe()
   └─ Remove duplicates (same URL = skip)

4. ChromaIngester.store(articles)
   └─ Process each article:
      ├─ Split into chunks (1200 chars, 120 overlap)
      ├─ Auto-detect tags (6 categories)
      ├─ Convert to vectors (384-dim)
      └─ Save to Chroma with metadata

# Result: Articles indexed in ChromaDB
```

### Option B : Runtime Fresh News (during chat)

```
User asks question in UI
  ↓
Backend POST /chat
  ↓
Parallel fetch (async):
  ├─ NewsAPI live (5 articles, last 7 days)
  ├─ HackerNews (top 30 stories, last 24h)
  └─ Chat history (previous Q&A)
  ↓
Combine with Chroma search results (8 chunks)
  ↓
→ Total ~16 articles for LLM context
```

**Speed comparison :**
- Batch: 30 min, bulk index, persistent
- Fresh: < 3s, live data, temporary

---

## 2. Métadonnées stockées

**Chaque article dans Chroma a :**

```json
{
  "id": "md5-hash-of-url",
  "title": "Python 3.13 released",
  "source": "HackerNews",  // or "NewsAPI", "Scraper", "ChatHistory"
  "date": "2026-06-14T10:30:00Z",
  "url": "https://...",
  "content": "Chunk text (1200 chars max)",
  "tags": "Backend,LLM",  // Auto-detected: comma-separated
  "type": "batch",        // or "online" (fresh), "chat" (history)
  "chunk_index": 0,
  "fetched_at": "2026-06-15T08:45:00Z"
}
```

**Why these fields?**

| Field | Used by | Purpose |
|-------|---------|---------|
| `id` | Chroma | Prevent duplicates (upsert idempotent) |
| `title`, `url` | Frontend | Display in card, click link |
| `source` | Frontend + Trending | Show origin, aggregate stats |
| `date` | Frontend | Timeline, freshness indicator |
| `tags` | Trending detection, filters | Categorization, insights |
| `type` | Chroma where clause | Distinguish batch vs fresh vs history |
| `chunk_index` | Neighbor expansion | Fetch adjacent chunks (±1) |
| `fetched_at` | Monitoring | When indexed (freshness) |

---

## 3. Recherche (Query)

### Phase 1 : User enters question

```
Frontend: Question = "What's new in DevOps?"
Topics = ["DevOps"]

  ↓ (POST /chat)

Backend chat.py:
  query = "What's new in DevOps? | DevOps"
```

### Phase 2 : 4 parallel sources fetch

```python
# All happen at the same time (asyncio.gather)

Source 1: Chroma semantic search
  query_embedding = embed(question)  # 384-dim vector
  results = chroma.query(
    query_embeddings=[query_embedding],
    n_results=8,
    where={"type": {"$ne": "chat"}}  # Only batch + online
  )
  → Returns: 8 chunks (most similar by cosine similarity)

Source 2: NewsAPI live fetch
  response = newsapi.get_everything(
    q="DevOps",
    sortBy="publishedAt",
    pageSize=5,
    language="en"
  )
  → Returns: 5 recent articles about DevOps

Source 3: HackerNews live fetch
  top_stories = GET /v0/topstories.json
  for each story_id:
    story_detail = GET /v0/item/{story_id}.json
    if relevant: add to results
  → Returns: 3-4 top stories (if any about DevOps)

Source 4: Chat history semantic search
  results = chroma.query(
    query_embeddings=[query_embedding],
    n_results=2,
    where={"type": "chat"}  # Only previous Q&A
  )
  → Returns: 2 previous messages (if similar)

# Total: 8 + 5 + 3 + 2 = ~18 articles/chunks
```

**Speed :** Each source is independent, run in parallel = ~2-2.5s total

### Phase 3 : Augment & tag

```python
# Combine all results
articles = chroma_results + newsapi_results + hn_results + history_results

# For each article: ensure it has tags
for article in articles:
  if not article.tags:
    article.tags = detect_tags(article.content, article.title)
    # detect_tags scans for keywords → ["DevOps"] or ["Backend", "DevOps"]

# Aggregate tags: which tags appear 3+ times?
tag_counts = {}
for article in articles:
  for tag in article.tags:
    tag_counts[tag] += 1

trending = [tag for tag, count in tag_counts.items() if count >= 3]
# Example: if "DevOps" appears 7 times → trending = ["DevOps"]
```

---

## 4. Synthèse (LLM)

```python
# Backend calls Azure AI LLM

prompt = {
  "question": "What's new in DevOps?",
  "topics": ["DevOps"],
  "context": "[18 articles with snippets]"
}

lm_response = llm.generate(prompt)
# LLM reads all 18 articles, synthesizes key insights
# Returns: "Cette semaine, Kubernetes 1.30 apporte... Docker 25.0..."

answer = extract_answer(lm_response)
# Result: factual summary with citations
```

**If LLM fails:** Backend returns raw articles (status="degraded") instead of crashing.

---

## 5. Response to frontend

```json
{
  "answer": "Cette semaine, DevOps tools ont...",
  "cards": [
    {
      "title": "Kubernetes 1.30 stable",
      "source": "HackerNews",
      "date": "2026-06-14",
      "snippet": "New orchestration features...",
      "url": "https://...",
      "tags": ["DevOps"]
    },
    // ... 17 more cards
  ],
  "trending": ["DevOps"],  // ← appears 7+ times
  "status": "ok"
}
```

---

## 6. Frontend rendering

```
Next.js receives response
  ↓
Display:
  ├─ Synthesis section (LLM text)
  ├─ Trending section (if trending.length > 0)
  │  └─ "📈 Tendances: [DevOps]"
  └─ Cards grid (3 columns, responsive)
     └─ 18 cards with:
        ├─ Title (clickable link)
        ├─ Source + date
        ├─ Snippet (preview)
        └─ Tags (colored badges)
```

---

## 7. Storage for next time

```python
# Store this Q&A for future context
chat_history.store(
  question="What's new in DevOps?",
  answer="Cette semaine, DevOps tools...",
  topics=["DevOps"]
)

# What happens:
1. Create Article with:
   id = MD5(question + timestamp)
   source = "ChatHistory"
   content = "Q: What's new in DevOps?\nA: Cette semaine..."
   type = "chat"  ← Important: marked as chat history

2. Store in Chroma (same DB as batch articles!)
   → Next question "Tell me more" finds this Q&A
   → Semantic search: "Tell me more" is similar to previous Q&A
   → Natural conversation context
```

---

## 8. Complete data flow diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER INTERACTION                             │
│  Frontend (Next.js) → User selects topic + asks question       │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ POST /chat { question, topics }
         ↓
┌────────────────────────────────────────────────────────────────┐
│                  BACKEND (Python FastAPI)                       │
│                                                                  │
│  1. Build search query: "{question} | {topics}"                │
│  2. Embed question → 384-dim vector                            │
│  3. Parallel fetch (asyncio.gather):                           │
│     ├─ Chroma.query(vector, k=8)  ← ~200ms                    │
│     ├─ NewsAPI.fetch(topics)      ← ~500ms                    │
│     ├─ HackerNews.fetch()         ← ~1s                       │
│     └─ ChatHistory.retrieve()     ← ~100ms                    │
│  4. Combine: ~18 articles                                       │
│  5. detect_tags() + _detect_trending()                         │
│  6. Call LLM: compose_answer()    ← ~1-2s (Azure)            │
│  7. Build ChatResponse: {answer, cards, trending, status}     │
│  8. chat_history.store(Q&A)                                    │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ JSON response
         ↓
┌────────────────────────────────────────────────────────────────┐
│                FRONTEND (Next.js/React)                         │
│                                                                  │
│  Render:                                                        │
│  ├─ Synthesis text (LLM answer)                               │
│  ├─ Trending badges (if 3+ articles per tag)                   │
│  └─ Cards grid (18 articles)                                   │
│     └─ Click → open article in new tab                        │
└────────────────────────────────────────────────────────────────┘
         │
         │ User reads + clicks articles
         ↓
┌────────────────────────────────────────────────────────────────┐
│              STORAGE (ChromaDB)                                 │
│                                                                  │
│  Persistent index:                                              │
│  ├─ Batch articles (type="batch") ← ingested daily            │
│  ├─ Fresh articles (type="online") ← added at chat time       │
│  └─ Chat history (type="chat") ← stored after each Q&A        │
│                                                                  │
│  Query flow:                                                    │
│  ├─ Semantic search (cosine similarity) on embeddings         │
│  ├─ Metadata filtering (by type, date, source)                │
│  └─ Neighbor expansion (±1 chunks for context)                │
└────────────────────────────────────────────────────────────────┘
```

---

## 9. Common scenarios

### Scenario 1: First time user, no chat history

```
Q: "What's new in AI?"
  ├─ Chroma: Find AI articles (batch index)
  ├─ NewsAPI: Fetch latest AI news
  ├─ HackerNews: Top AI stories
  └─ ChatHistory: Empty (first time)
  
Result: ~15 articles → LLM synthesis → display
Trending: "LLM" appears 8 times → marked trending
```

### Scenario 2: User asks follow-up

```
Q1: "What's new in AI?"
  → Stored in Chroma (type="chat")

Q2: "Tell me more"  (few seconds later)
  ├─ Chroma: Find articles about "tell me more" (will find Q1!)
  ├─ NewsAPI: Fresh fetch
  ├─ HackerNews: Fresh fetch
  └─ ChatHistory: Find Q1 (because embedding of Q2 is similar to Q1)
  
Result: LLM has Q1 context → says "Regarding AI, ..."
Natural conversation!
```

### Scenario 3: offline mode (Azure LLM down)

```
Q: "Latest DevOps tools"

LLM call fails → Fallback:
  ├─ status = "degraded"
  ├─ answer = "16 articles found. LLM synthesis unavailable."
  └─ cards = [display raw articles]

User still gets useful results (articles list with tags)
Not a crash, graceful degradation.
```

---

## 10. Performance checklist

| Component | Target | Actual | Status |
|-----------|--------|--------|--------|
| Batch ingestion | < 30 min | ~15-20 min | ✅ |
| Chroma query | < 500ms | ~200ms | ✅ |
| NewsAPI fetch | < 2s | ~500ms | ✅ |
| HackerNews fetch | < 2s | ~1s | ✅ |
| LLM synthesis | < 2s | ~1-2s | ✅ |
| **Total /chat latency** | **< 3s** | **~2-3s** | ✅ |
| Parallel efficiency | > 50% | ~80% | ✅ |

---

## 11. Failure modes & recovery

| Failure | Impact | Recovery |
|---------|--------|----------|
| Chroma down | High | Status="empty", no articles |
| NewsAPI quota exceeded | Medium | Skip topic, continue others |
| HackerNews API slow | Low | Timeout=1s, skip if slow |
| LLM Azure down | Medium | status="degraded", raw articles |
| ChatHistory store fails | Low | Log warning, continue chat |

All errors are **logged** not crashed. System degrades gracefully.

---

## 12. How to extend

**Add a 5th source (e.g., Dev.to):**

```python
# 1. Create ingester in app/ingest/devto.py
class DevToIngester:
    async def fetch(self) → list[dict]: ...

# 2. Add to CLI (scripts/ingest_cli.py)
@app.command()
def devto(): ...

# 3. Add to chat parallel fetch (app/chat.py)
devto_task = devto_ingester.fetch()
results = await asyncio.gather(..., devto_task)
```

**Add a 7th tag category:**

```python
# 1. Add to TAG_KEYWORDS in app/ingest/cleaning.py
TAG_KEYWORDS = {
    ...
    "Security": ["tls", "ssl", "encryption", "vulnerability"],  # ← New
}

# 2. Next ingestion automatically tags articles with "Security"
```

---

## Summary

| Phase | What | Time | Output |
|-------|------|------|--------|
| **Ingest** | Fetch + clean + chunk + embed | ~20 min | ChromaDB |
| **Query** | Parallel search 4 sources | ~2-3s | 18 articles |
| **Synthesize** | LLM reads articles | ~1-2s | Factual summary |
| **Display** | Frontend renders | ~100ms | Cards + trending |
| **Store** | Save Q&A for context | ~50ms | type="chat" |

Total time per user query: **< 3 seconds ✅**

---

**Questions? Check GUIDE_COMPLET_PROJET.md for deeper dive.**
