from __future__ import annotations

import logging

from app.ingest import enrich as ingest_enrich
from app.rag import retrieval
from app.rag.llm import compose_answer
from app.runtime import fresh_news
from app.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


async def handle_chat(req: ChatRequest) -> ChatResponse:
    query = _expand_query(req.question, req.topics)

    retrieved = retrieval.retrieve(query, k=8)

    try:
        enriched = ingest_enrich.enrich_retrieval(retrieved)
    except NotImplementedError:
        enriched = []
    if enriched:
        retrieved = retrieved + enriched

    try:
        fresh = await fresh_news.fetch(topics=req.topics, since=None)
    except NotImplementedError:
        fresh = []

    return await compose_answer(
        question=req.question,
        topics=req.topics,
        retrieved_chunks=retrieved,
        fresh_articles=fresh,
    )


def _expand_query(question: str, topics: list[str]) -> str:
    if not topics:
        return question
    return f"{question} | {', '.join(topics)}"
