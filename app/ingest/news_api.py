from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

import httpx

from app.config import Settings, get_settings
from app.rag.chroma_client import get_collection
from app.schemas import Article

logger = logging.getLogger(__name__)


@dataclass
class NewsApiIngester:
    settings: Settings = field(default_factory=get_settings)

    async def run(self, topics: list[str], pages_per_topic: int = 2) -> list[dict[str, Any]]:
        """Récupère et normalise les articles de NewsAPI."""
        if not topics:
            return []

        all_articles: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for topic in topics:
                for page in range(1, pages_per_topic + 1):
                    try:
                        response = await client.get(
                            f"{self.settings.news_api_base_url}/everything",
                            params={
                                "q": topic,
                                "language": "en",
                                "sortBy": "publishedAt",
                                "pageSize": 100,
                                "page": page,
                                "apiKey": self.settings.news_api_key,
                            },
                        )
                        response.raise_for_status()
                        data = response.json()

                        if data.get("status") != "ok":
                            logger.warning(f"NewsAPI error: {data.get('code')}")
                            break

                        articles = data.get("articles", [])
                        if not articles:
                            break

                        for article in articles:
                            normalized = self._normalize_article(article)
                            if normalized:
                                all_articles.append(normalized)

                    except httpx.HTTPError as e:
                        logger.warning(f"Failed to fetch {topic} page {page}: {e}")
                        break

        return all_articles

    def _normalize_article(self, article: dict[str, Any]) -> dict[str, Any] | None:
        """Normalise un article NewsAPI. Retourne None si contenu insuffisant."""
        url = article.get("url", "")
        title = article.get("title", "")
        content = article.get("description") or article.get("content") or ""

        if not content:
            return None

        return {
            "id": hashlib.md5(url.encode()).hexdigest(),
            "title": title,
            "source": "NewsAPI",
            "date": article.get("publishedAt"),
            "content": content,
            "url": url,
            "author": article.get("author"),
        }

    def format_article(self, article: dict[str, Any]) -> Article:
        """Formate un article NewsAPI en objet Article (pour compatibilité tests pédagogiques)."""
        url = article.get("url", "")
        title = article.get("title", "")
        content = article.get("description") or article.get("content") or ""
        published_at = article.get("publishedAt")

        date = None
        if published_at:
            try:
                date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return Article(
            id=hashlib.md5(url.encode()).hexdigest(),
            title=title,
            source=article.get("source", {}).get("name", "NewsAPI"),
            date=date,
            content=content,
            url=url,
            author=article.get("author"),
        )
