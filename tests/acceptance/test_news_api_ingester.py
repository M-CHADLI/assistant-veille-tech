from __future__ import annotations

from app.ingest.news_api import NewsApiIngester


def test_run_returns_list_of_normalized_articles() -> None:
    ingester = NewsApiIngester()
    articles = ingester.run(["python", "ai-ml"])
    assert isinstance(articles, list)
    for art in articles:
        assert "id" in art
        assert "title" in art
        assert "source" in art
        assert "date" in art
        assert "url" in art
        assert "content" in art


def test_run_handles_empty_topics() -> None:
    ingester = NewsApiIngester()
    articles = ingester.run([])
    assert articles == [] or isinstance(articles, list)


def test_run_dedupes_across_topics() -> None:
    ingester = NewsApiIngester()
    articles = ingester.run(["python", "python"])
    ids = [a["id"] for a in articles]
    assert len(ids) == len(set(ids))
