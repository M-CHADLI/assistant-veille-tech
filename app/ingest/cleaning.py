from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from markdownify import markdownify as md

BOILERPLATE_TAGS = ("nav", "header", "footer", "aside", "form", "script", "style", "noscript", "head")


def clean_html_to_markdown(html: str) -> str:
    soup = strip_boilerplate(BeautifulSoup(html, "lxml"))
    text = md(str(soup), heading_style="ATX", strip=["img"])
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def dedupe(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []

    for article in articles:
        url = article.get("url")
        key_title = (article.get("source", ""), article.get("title", ""))

        if url in seen_urls or key_title in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(key_title)
        out.append(article)

    return out


def chunk(text: str, max_chars: int = 1200, overlap: int = 120) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=min(overlap, max_chars // 2),
        separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""],
        keep_separator="end",
    )
    return splitter.split_text(text)


def strip_boilerplate(soup: BeautifulSoup) -> BeautifulSoup:
    for tag_name in BOILERPLATE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for tag in soup.select('[class*="cookie"], [id*="cookie"], [class*="advert"], [id*="advert"]'):
        tag.decompose()

    return soup


# Heuristiques de tags par mots-clés (section 2.3 du brief)
TAG_KEYWORDS = {
    "LLM": ["llm", "gpt", "claude", "llama", "prompt", "embedding", "langchain", "openai", "transformer"],
    "DevOps": ["docker", "k8s", "kubernetes", "ci/cd", "deploy", "terraform", "jenkins", "github actions"],
    "Frontend": ["react", "vue", "svelte", "css", "html", "typescript", "next.js", "angular", "tailwind"],
    "Backend": ["node", "python", "api", "database", "server", "fastapi", "django", "express", "sql"],
    "Data": ["sql", "bigquery", "analytics", "dataviz", "pandas", "spark", "dbt", "warehouse"],
    "FinOps": ["cost", "billing", "budget", "pricing", "cloud spending", "aws", "gcp", "azure"],
}


def detect_tags(text: str, title: str = "") -> list[str]:
    """Détecte les catégories (tags) d'un article via heuristiques de mots-clés.

    Retourne une liste de tags (peut être vide, peut en avoir plusieurs).
    """
    combined = (text + " " + title).lower()
    detected: set[str] = set()

    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            detected.add(tag)

    return sorted(detected)
