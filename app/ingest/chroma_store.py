from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from chromadb.api.types import Metadata

from app.ingest.cleaning import chunk, detect_tags
from app.rag.chroma_client import get_collection
from app.rag.retrieval import get_embedder
from app.schemas import Article


@dataclass
class ChromaIngester:
    chunk_max_chars: int = 1200

    def store(self, articles: list[Article]) -> int:
        if not articles:
            return 0

        fetched_at = datetime.now(timezone.utc).isoformat()

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[Metadata] = []
        stored = 0

        for article in articles:
            pieces = chunk(article.content, max_chars=self.chunk_max_chars)
            if not pieces:
                continue

            # Détection automatique de tags par heuristiques + tags existants
            detected_tags = detect_tags(article.content, article.title)
            all_tags = sorted(set(article.tags + detected_tags))

            stored += 1
            for index, piece in enumerate(pieces):
                ids.append(f"{article.id}-{index}")
                texts.append(piece)
                metadatas.append(
                    {
                        "title": article.title,
                        "source": article.source,
                        "url": str(article.url),
                        "date": article.date.isoformat() if article.date else "",
                        "author": article.author or "",
                        "tags": ",".join(all_tags),
                        "chunk_index": index,
                        "fetched_at": fetched_at,
                        "type": article.type,
                    }
                )

        if not texts:
            return 0

        embedder = get_embedder()
        embeddings = embedder.encode(texts, normalize_embeddings=True).tolist()

        collection = get_collection()
        collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return stored
