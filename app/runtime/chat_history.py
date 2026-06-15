"""Chat history: store conversation context in Chroma for future context."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from app.ingest.chroma_store import ChromaIngester
from app.rag.chroma_client import get_collection
from app.rag.retrieval import embed
from app.schemas import Article

logger = logging.getLogger(__name__)


class ChatHistoryManager:
    """Stocke et récupère l'historique de chat comme type="chat" dans Chroma."""

    def store_question(
        self,
        question: str,
        answer: str,
        topics: list[str],
    ) -> None:
        """Stocke une Q&A dans Chroma pour contexte futur."""
        try:
            article = Article(
                id=hashlib.md5(f"{question}{datetime.now()}".encode()).hexdigest(),
                title=f"Q: {question[:100]}",
                source="ChatHistory",
                date=datetime.now(timezone.utc),
                content=f"Q: {question}\nA: {answer[:500]}",  # limiter la taille
                url="",
                author="user",
                type="chat",
            )

            ChromaIngester().store([article])
            logger.info(f"Stored chat message: {question[:50]}…")
        except Exception as exc:
            logger.warning(f"Failed to store chat message: {exc}")

    def retrieve_context(self, question: str, k: int = 3) -> list[dict[str, Any]]:
        """Récupère les messages précédents similaires pour enrichir le contexte."""
        try:
            result = get_collection().query(
                query_embeddings=[embed(question)],
                n_results=k,
                where={"type": "chat"},
            )

            docs = (result.get("documents") or [[]])[0]
            metas = (result.get("metadatas") or [[]])[0]

            return [
                {
                    "content": doc,
                    "title": meta.get("title", "") if meta else "",
                    "date": meta.get("date", "") if meta else "",
                }
                for doc, meta in zip(docs, metas)
                if doc
            ]
        except Exception as exc:
            logger.warning(f"Failed to retrieve chat context: {exc}")
            return []


_manager = ChatHistoryManager()


def store(question: str, answer: str, topics: list[str]) -> None:
    """Hook pour stocker un message de chat."""
    _manager.store_question(question, answer, topics)


def retrieve(question: str, k: int = 3) -> list[dict[str, Any]]:
    """Hook pour récupérer le contexte de conversation."""
    return _manager.retrieve_context(question, k)
