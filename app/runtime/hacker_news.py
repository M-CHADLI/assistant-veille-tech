"""Hacker News integration for real-time tech news (4th source)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.schemas import Article

logger = logging.getLogger(__name__)

FETCH_WINDOW_HOURS = 24       # "récent" = publié dans les 24 dernières heures
REQUEST_TIMEOUT_S = 5.0       # respecter le budget de latence du chat


class HackerNewsRuntime:
    """Récupère les top stories Hacker News en temps réel."""

    API_BASE = "https://hacker-news.firebaseio.com/v0"

    def __init__(self, timeout: float = REQUEST_TIMEOUT_S) -> None:
        self.timeout = timeout

    async def fetch_recent_stories(self, hours: int = FETCH_WINDOW_HOURS) -> list[Article]:
        """Récupère les stories HN publiées dans les X dernières heures."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Récupère les top 30 stories
                top_ids_resp = await client.get(f"{self.API_BASE}/topstories.json")
                top_ids_resp.raise_for_status()
                top_ids = top_ids_resp.json()[:30]

                articles = []
                for story_id in top_ids:
                    try:
                        story_resp = await client.get(f"{self.API_BASE}/item/{story_id}.json")
                        story_resp.raise_for_status()
                        item = story_resp.json()

                        article = self._parse_story(item, cutoff)
                        if article:
                            articles.append(article)
                    except httpx.HTTPError:
                        continue

                logger.info(f"Fetched {len(articles)} HN stories from last {hours}h")
                return articles

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch HN stories: {e}")
            return []

    def _parse_story(self, item: dict[str, Any], cutoff: datetime) -> Article | None:
        """Convertit un item HN en Article."""
        if not item.get("type") == "story":
            return None

        story_time = datetime.fromtimestamp(item.get("time", 0), tz=timezone.utc)
        if story_time < cutoff:
            return None

        title = item.get("title", "")
        url = item.get("url", "")
        score = item.get("score", 0)

        if not (title and url):
            return None

        # Le "contenu" est le titre + score (pas de body sur HN)
        content = f"{title} (Score: {score} points, {item.get('descendants', 0)} comments)"

        return Article(
            id=f"hn-{item['id']}",
            title=title,
            source="HackerNews",
            date=story_time,
            content=content,
            url=url,
            author=item.get("by", "anonymous"),
            type="online",
        )


class HackerNewsAPI:
    """Interface pour chat.py : convertit les Articles en dicts pour le prompt."""

    def __init__(self) -> None:
        self.runtime = HackerNewsRuntime()

    async def fetch(self, hours: int = FETCH_WINDOW_HOURS) -> list[dict[str, Any]]:
        """Récupère HN stories et les formate pour le chat."""
        articles = await self.runtime.fetch_recent_stories(hours=hours)
        return [
            {
                "title": art.title,
                "source": art.source,
                "date": art.date.isoformat() if art.date else None,
                "content": art.content,
                "url": str(art.url),
                "tags": [],  # HN n'a pas de tags, will be auto-detected via detect_tags()
            }
            for art in articles
        ]


_api = HackerNewsAPI()


async def fetch(hours: int = FETCH_WINDOW_HOURS) -> list[dict[str, Any]]:
    """Hook appelé par chat.py — retourne les HN stories de l'heure."""
    return await _api.fetch(hours=hours)
