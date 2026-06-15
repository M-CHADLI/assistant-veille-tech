from __future__ import annotations

import asyncio
import logging

from app.ingest import enrich as ingest_enrich
from app.rag import retrieval
from app.rag.llm import compose_answer
from app.runtime import chat_history, fresh_news, hacker_news
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

    # Récupère les sources fraîches en parallèle (NewsAPI + HackerNews)
    fresh_tasks = [
        fresh_news.fetch(topics=req.topics, since=None),
        hacker_news.fetch(hours=24),
    ]
    fresh_results = await asyncio.gather(*fresh_tasks, return_exceptions=True)

    fresh = []
    for result in fresh_results:
        if isinstance(result, BaseException):
            logger.warning("fresh_news or hacker_news fetch failed: %s", result)
            continue
        fresh.extend(result)

    # Récupère le contexte de chat précédent (historique)
    chat_ctx = chat_history.retrieve(req.question, k=2)
    for ctx in chat_ctx:
        fresh.append({
            "title": ctx.get("title", ""),
            "source": "ChatHistory",
            "date": ctx.get("date"),
            "content": ctx.get("content", ""),
            "url": "",
            "tags": [],
        })

    response = await compose_answer(
        question=req.question,
        topics=req.topics,
        retrieved_chunks=retrieved,
        fresh_articles=fresh,
    )

    # Stocke cette Q&A dans l'historique pour le contexte futur
    try:
        chat_history.store(
            question=req.question,
            answer=response.answer,
            topics=req.topics,
        )
    except Exception as exc:
        logger.warning("Failed to store chat history: %s", exc)

    return response


def _expand_query(question: str, topics: list[str]) -> str:
    if not topics:
        return question
    return f"{question} | {', '.join(topics)}"
