"""Mode "fresh news" : injecte l'actualité chaude (< 7 jours) au moment du chat.

Pipeline runtime (déclenché à chaque question, budget < 3 s) :

    fetch_raw()           NewsAPI live, topics en PARALLÈLE (asyncio.gather)
      → process_and_clean()   normalisation + skip sans contenu + dedupe (cleaning.py)
      → upsert_to_chroma()    chunk + metadata (fetched_at, type="online") + upsert,
                              délégué à ChromaIngester — zéro duplication
      → fetch_and_index()     orchestration ; retourne des Documents LangChain

`FreshNewsAPI` est l'interface consommée par chat.py via le hook module-level
`fetch()` (signature imposée par les tests d'acceptance).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from langchain_core.documents import Document

from app.config import get_settings
from app.ingest.chroma_store import ChromaIngester
from app.ingest.cleaning import clean_html_to_markdown, dedupe
from app.rag.chroma_client import get_collection
from app.rag.retrieval import embed
from app.schemas import Article

logger = logging.getLogger(__name__)

FRESH_WINDOW_DAYS = 7        # "frais" = publié dans la semaine
MAX_PER_TOPIC = 5            # peu d'articles mais récents : on épice, on ne ré-ingère pas le web
REQUEST_TIMEOUT_S = 5.0      # une source lente ne doit pas exploser le budget des 3 s


class FreshNewsRuntime:
    """Récupère, nettoie, indexe et restitue l'actualité fraîche."""

    def __init__(self, timeout: float = REQUEST_TIMEOUT_S) -> None:
        self.settings = get_settings()
        self.timeout = timeout

    # ── 1. EXTRACTION ────────────────────────────────────────────────

    async def fetch_raw(
        self, topics: list[str], since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Appelle NewsAPI pour chaque topic, EN PARALLÈLE.

        Même pattern que news_api.py (endpoint /everything) mais calibré
        chat : pageSize réduit, fenêtre `from=since`, gather pour la latence.
        """
        if not topics or not self.settings.news_api_key:
            return []

        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=FRESH_WINDOW_DAYS)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            batches = await asyncio.gather(
                *(self._fetch_topic(client, topic, since) for topic in topics),
                return_exceptions=True,
            )

        raw: list[dict[str, Any]] = []
        for topic, batch in zip(topics, batches):
            if isinstance(batch, BaseException):
                # Un topic en échec (quota, réseau) ne coûte que ce topic.
                logger.warning("fresh_news: topic %r failed: %s", topic, batch)
                continue
            for article in batch:
                article["_topic"] = topic
            raw.extend(batch)
        return raw

    async def _fetch_topic(
        self, client: httpx.AsyncClient, topic: str, since: datetime
    ) -> list[dict[str, Any]]:
        response = await client.get(
            f"{self.settings.news_api_base_url}/everything",
            params={
                "q": topic,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": MAX_PER_TOPIC,
                "from": since.date().isoformat(),
                "apiKey": self.settings.news_api_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "ok":
            raise RuntimeError(f"NewsAPI: {payload.get('code')} — {payload.get('message')}")
        return payload.get("articles", [])

    # ── 2. NETTOYAGE ─────────────────────────────────────────────────

    def process_and_clean(self, raw_articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Format NewsAPI → format interne, en réutilisant cleaning.py."""
        normalized: list[dict[str, Any]] = []
        for raw in raw_articles:
            url = raw.get("url") or ""
            content = raw.get("description") or raw.get("content") or ""
            if not url or not content:
                continue  # sans contenu, l'embedding ne vaudrait rien
            if "<" in content:  # certaines sources renvoient du HTML
                content = clean_html_to_markdown(content)

            normalized.append(
                {
                    "id": hashlib.md5(url.encode()).hexdigest(),
                    "title": raw.get("title") or "",
                    "source": (raw.get("source") or {}).get("name") or "NewsAPI",
                    "date": raw.get("publishedAt"),
                    "content": content,
                    "url": url,
                    "tags": [raw.get("_topic")] if raw.get("_topic") else [],
                }
            )
        return dedupe(normalized)

    # ── 3. INDEXATION ────────────────────────────────────────────────

    def upsert_to_chroma(self, articles: list[dict[str, Any]]) -> int:
        """Chunk + metadata (fetched_at, type="online") + UPSERT.

        Tout est délégué à ChromaIngester.store() : même découpage,
        mêmes métadonnées et même idempotence que l'ingestion batch.
        """
        models = [
            Article(
                id=art["id"],
                title=art["title"],
                source=art["source"],
                date=art["date"],
                content=art["content"],
                url=art["url"],
                tags=art["tags"],
                type="online",  # distingue le live du batch dans Chroma
            )
            for art in articles
        ]
        return ChromaIngester().store(models)

    # ── 4. RESTITUTION ───────────────────────────────────────────────

    def to_documents(self, articles: list[dict[str, Any]]) -> list[Document]:
        """Format LangChain Document : prêt pour le contexte du LLM."""
        return [
            Document(
                page_content=art["content"],
                metadata={
                    "title": art["title"],
                    "source": art["source"],
                    "date": art["date"] or "",
                    "url": art["url"],
                    "tags": ",".join(art["tags"]),
                    "type": "online",
                },
            )
            for art in articles
        ]

    def retrieve_and_format(self, question: str, k: int = 4) -> list[Document]:
        """Recherche sémantique restreinte aux chunks "online" déjà indexés."""
        try:
            result = get_collection().query(
                query_embeddings=[embed(question)],
                n_results=k,
                where={"type": "online"},
            )
        except Exception as exc:
            logger.warning("fresh_news: retrieve failed: %s", exc)
            return []

        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        return [
            Document(page_content=doc, metadata=meta or {})
            for doc, meta in zip(docs, metas)
        ]

    # ── ORCHESTRATION ────────────────────────────────────────────────

    async def fetch_and_index(
        self, topics: list[str], since: datetime | None = None
    ) -> list[Document]:
        """Le point d'entrée : fetch → clean → index → Documents."""
        raw = await self.fetch_raw(topics, since)
        articles = self.process_and_clean(raw)

        if articles:
            try:
                # L'embedding est du calcul CPU : on le sort de l'event loop
                # pour ne pas bloquer les autres requêtes pendant ce temps.
                await asyncio.to_thread(self.upsert_to_chroma, articles)
            except Exception as exc:
                # Chroma indisponible ≠ pas de fresh news : on renvoie
                # quand même les articles au chat, l'index attendra.
                logger.warning("fresh_news: indexing failed (%s) — articles still served", exc)

        return self.to_documents(articles)


class FreshNewsAPI:
    """Interface pour chat.py : convertit les Documents en dicts pour le prompt."""

    def __init__(self) -> None:
        self.runtime = FreshNewsRuntime()

    async def fetch(
        self, topics: list[str], since: datetime | None = None
    ) -> list[dict[str, Any]]:
        documents = await self.runtime.fetch_and_index(topics, since)
        return [
            {
                "title": doc.metadata.get("title", ""),
                "source": doc.metadata.get("source", ""),
                "date": doc.metadata.get("date") or None,
                "content": doc.page_content,
                "url": doc.metadata.get("url", ""),
                "tags": [t for t in doc.metadata.get("tags", "").split(",") if t],
            }
            for doc in documents
        ]


_api = FreshNewsAPI()


async def fetch(
    topics: list[str],
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Hook appelé par chat.py (signature imposée par les tests d'acceptance)."""
    return await _api.fetch(topics=topics, since=since)



