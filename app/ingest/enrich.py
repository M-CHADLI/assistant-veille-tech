"""Hook d'enrichissement post-retrieval : l'expansion par chunks voisins.

Les ids de chunks sont composés "{id_article}-{index}" (cf. chroma_store.py).
Quand la recherche remonte le chunk 2 d'un article, ses voisins (1 et 3)
contiennent souvent la suite ou le début de l'idée : on les récupère par id
(lookup direct, pas de recherche vectorielle → quasi gratuit) et on les ajoute
au contexte donné au LLM.

C'est la technique RAG classique du "neighbor / window expansion".
"""

from __future__ import annotations

import logging
from typing import Any

from app.rag.chroma_client import get_collection

logger = logging.getLogger(__name__)

# On n'étend que les premiers chunks (les plus pertinents) : étendre les 8
# résultats doublerait le contexte pour un gain marginal sur les derniers.
MAX_CHUNKS_TO_EXPAND = 3


def enrich_retrieval(retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not retrieved:
        return []

    already_have = {chunk.get("id") for chunk in retrieved}
    wanted: list[str] = []

    for chunk in retrieved[:MAX_CHUNKS_TO_EXPAND]:
        chunk_id = str(chunk.get("id") or "")
        base, sep, index = chunk_id.rpartition("-")
        if not sep or not index.isdigit():
            continue  # id sans index de chunk : rien à étendre

        i = int(index)
        for neighbor_index in (i - 1, i + 1):
            if neighbor_index < 0:
                continue
            neighbor_id = f"{base}-{neighbor_index}"
            if neighbor_id not in already_have and neighbor_id not in wanted:
                wanted.append(neighbor_id)

    if not wanted:
        return []

    try:
        result = get_collection().get(ids=wanted)
    except Exception as exc:
        # L'enrichissement est un bonus : s'il échoue, le chat continue
        # avec les chunks déjà retrouvés.
        logger.warning("enrich: neighbor lookup failed: %s", exc)
        return []

    enriched: list[dict[str, Any]] = []
    for doc_id, doc, meta in zip(
        result.get("ids", []),
        result.get("documents") or [],
        result.get("metadatas") or [],
    ):
        enriched.append(
            {
                "id": doc_id,
                "content": doc,
                "metadata": meta or {},
                "distance": None,  # pas issu d'une recherche : pas de score
            }
        )
    return enriched
