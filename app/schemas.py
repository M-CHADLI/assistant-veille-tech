from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class Article(BaseModel):
    id: str
    title: str
    source: str
    date: datetime | None = None
    content: str
    url: HttpUrl | str
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    type: Literal["batch", "online", "chat"] = "batch"


class ArticleCard(BaseModel):
    title: str
    source: str
    date: str | None = None
    snippet: str
    url: str
    tags: list[str] = Field(default_factory=list)


class Topic(BaseModel):
    slug: str
    label: str


class ChatRequest(BaseModel):
    question: str
    topics: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    cards: list[ArticleCard]
    status: Literal["ok", "empty", "degraded"] = "ok"
    trending: list[str] = Field(default_factory=list)  # tags qui apparaissent 3+ fois
