from __future__ import annotations

from app.ingest.scraper import Scraper


def test_run_returns_articles_with_required_fields() -> None:
    scraper = Scraper()
    articles = scraper.run(["https://example.com/changelog"])
    assert isinstance(articles, list)
    for art in articles:
        assert "title" in art
        assert "url" in art
        assert "content" in art
        assert "source" in art


def test_run_handles_unreachable_url_gracefully() -> None:
    scraper = Scraper()
    out = scraper.run(["http://127.0.0.1:1/does-not-exist"])
    assert isinstance(out, list)
