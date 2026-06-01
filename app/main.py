from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.chat import handle_chat
from app.schemas import ChatRequest, ChatResponse, Topic

POPULAR_TOPICS: list[Topic] = [
    Topic(slug="python", label="Python"),
    Topic(slug="javascript", label="JavaScript"),
    Topic(slug="ai-ml", label="AI/ML"),
    Topic(slug="devops", label="DevOps"),
    Topic(slug="web", label="Web"),
]


app = FastAPI(
    title="Nauda Palisse — Veille Tech",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/topics", response_model=list[Topic])
def topics() -> list[Topic]:
    return POPULAR_TOPICS


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    return await handle_chat(req)
