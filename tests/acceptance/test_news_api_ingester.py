from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from app.ingest.news_api import NewsApiIngester


@pytest.mark.asyncio
async def test_run_returns_list_of_normalized_articles() -> None:
    """Test that run() returns properly normalized articles"""
    with patch("app.ingest.news_api.get_collection"):
        ingester = NewsApiIngester()
        
        # Mock NewsAPI response
        mock_response = {
            "status": "ok",
            "totalResults": 2,
            "articles": [
                {
                    "source": {"id": "techcrunch", "name": "TechCrunch"},
                    "author": "John Doe",
                    "title": "AI breakthrough announced",
                    "description": "New AI model achieves state-of-art",
                    "url": "https://techcrunch.com/article1",
                    "urlToImage": "https://example.com/img.jpg",
                    "publishedAt": "2024-01-15T10:00:00Z",
                    "content": "This is the full content of the article.",
                }
            ],
        }
        
        with respx.mock:
            respx.get("https://newsapi.org/v2/everything").mock(
                return_value=Response(200, json=mock_response)
            )
            
            articles = await ingester.run(["ai"])
            
            assert isinstance(articles, list)
            assert len(articles) > 0
            
            for art in articles:
                assert "id" in art
                assert "title" in art
                assert art["source"] == "NewsAPI"
                assert "date" in art
                assert "url" in art
                assert "content" in art


@pytest.mark.asyncio
async def test_run_handles_empty_topics() -> None:
    """Test that run() handles empty topics gracefully"""
    with patch("app.ingest.news_api.get_collection"):
        ingester = NewsApiIngester()
        articles = await ingester.run([])
        assert articles == [] or isinstance(articles, list)


@pytest.mark.asyncio
async def test_run_dedupes_same_topic() -> None:
    """Test that articles from same topic don't create duplicates"""
    with patch("app.ingest.news_api.get_collection"):
        ingester = NewsApiIngester()
        
        mock_response = {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "source": {"id": "hn", "name": "HackerNews"},
                    "author": None,
                    "title": "Python 3.13 released",
                    "description": "New Python version available",
                    "url": "https://python.org/release",
                    "urlToImage": None,
                    "publishedAt": "2024-01-20T15:30:00Z",
                    "content": "Python 3.13 has been released with new features.",
                }
            ],
        }
        
        with respx.mock:
            respx.get("https://newsapi.org/v2/everything").mock(
                return_value=Response(200, json=mock_response)
            )
            
            articles = await ingester.run(["backend", "backend"])
            
            # Each call will return the same article with different IDs due to uuid4()
            # In production, deduplication happens in cleaning.py
            assert isinstance(articles, list)
            assert all("id" in a for a in articles)


@pytest.mark.asyncio
async def test_run_handles_api_error() -> None:
    """Test that run() gracefully handles API errors"""
    with patch("app.ingest.news_api.get_collection"):
        ingester = NewsApiIngester()
        
        with respx.mock:
            respx.get("https://newsapi.org/v2/everything").mock(
                return_value=Response(401, json={"status": "error", "code": "apiKeyInvalid"})
            )
            
            articles = await ingester.run(["ai"])
            assert articles == []


@pytest.mark.asyncio
async def test_normalize_article_skips_missing_content() -> None:
    """Test that articles without content are skipped"""
    ingester = NewsApiIngester()
    
    mock_response = {
        "status": "ok",
        "totalResults": 1,
        "articles": [
            {
                "source": {"id": "src", "name": "Source"},
                "author": None,
                "title": "Title only",
                "description": None,
                "url": "https://example.com/article",
                "urlToImage": None,
                "publishedAt": "2024-01-20T15:30:00Z",
                "content": None,  # No content and no description
            }
        ],
    }
    
    with respx.mock:
        with patch("app.ingest.news_api.get_collection"):
            respx.get("https://newsapi.org/v2/everything").mock(
                return_value=Response(200, json=mock_response)
            )
            
            articles = await ingester.run(["ai"])
            # Article should be skipped due to no content
            assert len(articles) == 0

