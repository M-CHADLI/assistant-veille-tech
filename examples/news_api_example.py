#!/usr/bin/env python3
"""
Example: Using NewsApiIngester programmatically

This script demonstrates how to use the NewsApiIngester directly
without the CLI, for custom workflows or scheduled tasks.
"""

import asyncio
import logging
from datetime import datetime

from app.ingest.news_api import NewsApiIngester

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main example function"""
    
    logger.info("=== NewsAPI Ingester Example ===")
    
    # Initialize ingester (Settings loaded from .env automatically)
    ingester = NewsApiIngester()
    
    # Example 1: Fetch articles for multiple topics
    logger.info("Fetching articles for: ai, devops")
    articles = await ingester.run(topics=["ai", "devops"])
    
    logger.info(f"Total articles fetched: {len(articles)}")
    
    # Display first 3 articles
    for i, article in enumerate(articles[:3], 1):
        logger.info(
            f"\n[{i}] {article['title']}\n"
            f"    Source: {article['source']}\n"
            f"    Date: {article['date']}\n"
            f"    URL: {article['url']}\n"
            f"    Tags: {', '.join(article.get('tags', []))}"
        )
    
    # Example 2: Fetch all available topics
    logger.info("\n=== Fetching all default topics ===")
    all_articles = await ingester.run()  # Uses all topics if None
    logger.info(f"Total articles from all topics: {len(all_articles)}")
    
    # Example 3: Custom workflow - filter articles by date
    logger.info("\n=== Filtering recent articles (last 7 days) ===")
    recent_articles = [
        a for a in articles
        if a.get("date") and (datetime.utcnow() - a["date"]).days <= 7
    ]
    logger.info(f"Recent articles: {len(recent_articles)}")
    
    # Example 4: Group by topic
    logger.info("\n=== Grouping articles by topic ===")
    by_topic = {}
    for article in articles:
        for tag in article.get("tags", []):
            if tag not in by_topic:
                by_topic[tag] = []
            by_topic[tag].append(article)
    
    for topic, articles_list in by_topic.items():
        logger.info(f"Topic '{topic}': {len(articles_list)} articles")
    
    logger.info("\n✓ Example complete!")


if __name__ == "__main__":
    asyncio.run(main())
