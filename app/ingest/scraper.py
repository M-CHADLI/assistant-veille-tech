from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.ingest.cleaning import clean_html_to_markdown

logger = logging.getLogger(__name__)


@dataclass
class Scraper:
    """Generic batch fetcher for the non-NewsAPI sources of the brief.

    `run()` dispatches each URL to the right parser:
      - GitHub Releases API endpoints (api.github.com/repos/.../releases)
      - RSS/Atom feeds (Dev.to, CSS-Tricks, LogRocket, Changelog, ...)
      - any other URL is treated as a single HTML page (e.g. a changelog page)
    """

    user_agent: str = "nauda-palisse-veille/0.1"
    timeout: float = 10.0

    def run(self, urls: list[str]) -> list[dict[str, Any]]:
        articles: list[dict[str, Any]] = []

        for url in urls:
            try:
                articles.extend(self._fetch(url))
            except Exception as exc:
                logger.warning("scraper: failed to fetch %s: %s", url, exc)

        return articles

    def _fetch(self, url: str) -> list[dict[str, Any]]:
        if _is_github_releases_url(url):
            return self._fetch_github_releases(url)

        with httpx.Client(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        body = response.text

        if _looks_like_feed(content_type, body):
            return self._parse_feed(body, source_url=url)

        return [self._parse_html_page(body, url)]

    def _fetch_github_releases(self, url: str) -> list[dict[str, Any]]:
        with httpx.Client(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent, "Accept": "application/vnd.github+json"},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        repo = _repo_name_from_releases_url(url)
        articles: list[dict[str, Any]] = []

        for release in response.json():
            if release.get("draft"):
                continue

            label = release.get("name") or release.get("tag_name") or "release"
            articles.append(
                {
                    "title": f"{repo} {label}".strip(),
                    "url": release.get("html_url", url),
                    "content": release.get("body") or "",
                    "source": "GitHub",
                    "date": _normalize_date(release.get("published_at") or release.get("created_at")),
                }
            )

        return articles

    def _parse_feed(self, body: str, source_url: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(body, "xml")
        source = _hostname(source_url)
        items = soup.find_all("item") or soup.find_all("entry")

        articles: list[dict[str, Any]] = []
        for item in items:
            raw_content = (
                _tag_text(item, "content:encoded")
                or _tag_text(item, "content")
                or _tag_text(item, "description")
                or _tag_text(item, "summary")
            )
            articles.append(
                {
                    "title": _tag_text(item, "title"),
                    "url": _feed_link(item),
                    "content": clean_html_to_markdown(raw_content) if raw_content else "",
                    "source": source,
                    "date": _normalize_date(
                        _tag_text(item, "pubDate")
                        or _tag_text(item, "published")
                        or _tag_text(item, "updated")
                    ),
                }
            )

        return articles

    def _parse_html_page(self, html: str, url: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else url

        return {
            "title": title,
            "url": url,
            "content": clean_html_to_markdown(html),
            "source": _hostname(url),
            "date": None,
        }


def _is_github_releases_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == "api.github.com" and "/releases" in parsed.path


def _repo_name_from_releases_url(url: str) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "repos":
        return f"{parts[1]}/{parts[2]}"
    return ""


def _looks_like_feed(content_type: str, body: str) -> bool:
    if any(token in content_type for token in ("xml", "rss", "atom")):
        return True
    head = body.lstrip()[:200].lower()
    return head.startswith("<?xml") or "<rss" in head or "<feed" in head


def _hostname(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def _tag_text(item: Any, name: str) -> str:
    tag = item.find(name)
    return tag.get_text(strip=True) if tag else ""


def _feed_link(item: Any) -> str:
    link_tag = item.find("link")
    if link_tag is None:
        return ""
    return link_tag.get("href") or link_tag.get_text(strip=True)


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass

    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return None
