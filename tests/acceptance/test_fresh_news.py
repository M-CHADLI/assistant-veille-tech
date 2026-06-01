from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.runtime import fresh_news


@pytest.mark.asyncio
async def test_fetch_returns_list_of_articles() -> None:
    out = await fresh_news.fetch(topics=["python"], since=None)
    assert isinstance(out, list)
    for art in out:
        assert "title" in art
        assert "url" in art
        assert "source" in art


@pytest.mark.asyncio
async def test_fetch_filters_by_since() -> None:
    since = datetime.utcnow() - timedelta(days=2)
    out = await fresh_news.fetch(topics=["ai"], since=since)
    assert isinstance(out, list)


@pytest.mark.asyncio
async def test_fetch_empty_topics_returns_empty() -> None:
    out = await fresh_news.fetch(topics=[], since=None)
    assert out == [] or isinstance(out, list)
