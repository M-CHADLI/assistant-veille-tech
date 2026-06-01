from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings


@lru_cache(maxsize=1)
def get_client() -> chromadb.HttpClient:
    settings = get_settings()
    parsed = urlparse(settings.chroma_url)
    host = parsed.hostname or "chromadb"
    port = parsed.port or 8000
    return chromadb.HttpClient(
        host=host,
        port=port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_collection() -> Collection:
    settings = get_settings()
    client = get_client()
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )
