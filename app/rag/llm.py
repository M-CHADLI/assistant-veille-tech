from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.schemas import ArticleCard, ChatResponse

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Tu es l'assistant de veille technologique interne de Nauda Palisse.\n"
    "Réponds en français, factuel, concis. Cite tes sources via les cartes d'articles.\n"
    "Si aucun article n'est fourni, dis-le poliment et ne fabrique rien.\n"
    "Format de sortie attendu : JSON strict avec les clés `answer` (string) "
    "et `cards` (liste d'objets {title, source, date, snippet, url, tags})."
)


@lru_cache(maxsize=1)
def get_llm() -> AzureAIChatCompletionsModel | None:
    settings = get_settings()
    if not settings.azure_ai_inference_endpoint or not settings.azure_ai_inference_api_key:
        logger.info("Azure AI inference not configured — running in degraded mode")
        return None
    return AzureAIChatCompletionsModel(
        endpoint=settings.azure_ai_inference_endpoint,
        credential=settings.azure_ai_inference_api_key,
        model=settings.azure_ai_inference_model,
        temperature=0.2,
    )


def _format_context(retrieved: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if retrieved:
        parts.append("## Index interne")
        for i, chunk in enumerate(retrieved, 1):
            meta = chunk.get("metadata") or {}
            parts.append(
                f"[{i}] {meta.get('title', '')} — {meta.get('source', '')} "
                f"({meta.get('date', '')})\n{chunk.get('content', '')[:600]}"
            )
    if fresh:
        parts.append("## Actualité fraîche")
        for i, art in enumerate(fresh, 1):
            parts.append(
                f"[F{i}] {art.get('title', '')} — {art.get('source', '')} "
                f"({art.get('date', '')})\n{art.get('content', '')[:600]}\n{art.get('url', '')}"
            )
    return "\n\n".join(parts) if parts else "(aucune source disponible)"


def _build_cards(
    retrieved: list[dict[str, Any]], fresh: list[dict[str, Any]]
) -> list[ArticleCard]:
    cards: list[ArticleCard] = []
    for chunk in retrieved:
        meta = chunk.get("metadata") or {}
        snippet = (chunk.get("content") or "")[:280]
        cards.append(
            ArticleCard(
                title=meta.get("title", "Sans titre"),
                source=meta.get("source", "interne"),
                date=meta.get("date"),
                snippet=snippet,
                url=meta.get("url", ""),
                tags=_split_tags(meta.get("tags")),
            )
        )
    for art in fresh:
        cards.append(
            ArticleCard(
                title=art.get("title", "Sans titre"),
                source=art.get("source", "newsapi"),
                date=art.get("date"),
                snippet=(art.get("content") or art.get("description") or "")[:280],
                url=art.get("url", ""),
                tags=art.get("tags", []),
            )
        )
    return cards


def _split_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


def _detect_trending(cards: list[ArticleCard], threshold: int = 3) -> list[str]:
    """Détecte les tendances : tags qui apparaissent 3+ fois dans les résultats."""
    tag_counts: dict[str, int] = {}
    for card in cards:
        for tag in card.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return sorted([tag for tag, count in tag_counts.items() if count >= threshold])


async def compose_answer(
    *,
    question: str,
    topics: list[str],
    retrieved_chunks: list[dict[str, Any]],
    fresh_articles: list[dict[str, Any]],
) -> ChatResponse:
    cards = _build_cards(retrieved_chunks, fresh_articles)
    trending = _detect_trending(cards)

    if not retrieved_chunks and not fresh_articles:
        return ChatResponse(
            answer=(
                "Aucun article ne couvre encore ce sujet dans l'index ou dans "
                "l'actualité collectée. Lance une ingestion pour alimenter la veille."
            ),
            cards=[],
            trending=[],
            status="empty",
        )

    llm = get_llm()
    if llm is None:
        return ChatResponse(
            answer=(
                f"{len(cards)} article(s) trouvé(s) pour : {question}. "
                "LLM non configuré — voici les sources brutes."
            ),
            cards=cards,
            trending=trending,
            status="degraded",
        )

    user_payload = {
        "question": question,
        "topics": topics,
        "context": _format_context(retrieved_chunks, fresh_articles),
    }

    try:
        msg = await llm.ainvoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
            ]
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        answer = _extract_answer(raw)
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        answer = f"Synthèse indisponible (erreur LLM). {len(cards)} article(s) référencé(s)."

    return ChatResponse(answer=answer, cards=cards, trending=trending, status="ok")


def _extract_answer(raw: str) -> str:
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "answer" in data:
            return str(data["answer"])
    except json.JSONDecodeError:
        pass
    return raw.strip()
