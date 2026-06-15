from __future__ import annotations

import asyncio
import hashlib
import logging

import typer

from app.ingest import sources
from app.ingest.chroma_store import ChromaIngester
from app.ingest.cleaning import dedupe
from app.ingest.news_api import NewsApiIngester
from app.ingest.scraper import Scraper
from app.schemas import Article

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = typer.Typer(help="Ingestion CLI for the veille tech index.")


@app.command()
def news(
    topics: list[str] = typer.Option(
        None, "--topic", "-t", help="Topic to query (ai, devops, frontend, backend, data, finops)."
    ),
) -> None:
    """
    Fetch and index articles from NewsAPI for specified topics.

    Example:
        python scripts/ingest_cli.py news -t ai -t devops
    """
    if not topics:
        typer.echo("Error: At least one topic must be specified with -t/--topic", err=True)
        raise typer.Exit(1)

    typer.echo(f"Starting NewsAPI ingestion for topics: {', '.join(topics)}")

    ingester = NewsApiIngester()
    raw_articles = asyncio.run(ingester.run(topics))

    if not raw_articles:
        typer.echo("⚠️  No articles found")
        raise typer.Exit(0)

    # Convert to Article objects and store in Chroma
    articles = [
        Article(
            id=hashlib.md5(art["url"].encode()).hexdigest(),
            title=art.get("title", ""),
            source=art.get("source", "NewsAPI"),
            date=art.get("date"),
            content=art.get("content", ""),
            url=art.get("url", ""),
            author=art.get("author"),
            type="batch",
        )
        for art in raw_articles
        if art.get("url") and art.get("content")
    ]

    count = ChromaIngester().store(articles)

    typer.echo(f"✓ Fetched {len(raw_articles)} articles, indexed {count} in Chroma")
    for article in articles[:5]:  # Show first 5
        typer.echo(f"  - {article.title[:60]}...")


@app.command()
def scrape(
    urls: list[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="RSS feed or GitHub Releases API URL to scrape. Defaults to the configured batch sources.",
    ),
) -> None:
    """
    Scrape RSS feeds and GitHub Releases, then index the resulting articles in Chroma.

    Example:
        python scripts/ingest_cli.py scrape -u https://dev.to/feed
    """
    target_urls = urls or sources.default_scrape_urls()
    typer.echo(f"Scraping {len(target_urls)} source(s)...")

    raw_articles = Scraper().run(target_urls)
    raw_articles = dedupe(raw_articles)

    articles = [
        Article(
            id=hashlib.md5(art["url"].encode()).hexdigest(),
            title=art.get("title", ""),
            source=art.get("source", ""),
            date=art.get("date"),
            content=art.get("content", ""),
            url=art.get("url", ""),
        )
        for art in raw_articles
        if art.get("url") and art.get("content")
    ]

    count = ChromaIngester().store(articles)

    typer.echo(f"✓ Scraped {len(articles)} article(s), indexed {count} in Chroma")
    for article in articles[:5]:
        typer.echo(f"  - {article.title[:60]}...")


if __name__ == "__main__":
    app()
