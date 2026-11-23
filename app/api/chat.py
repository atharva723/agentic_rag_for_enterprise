"""Employee endpoints: health check and chat."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.graph import ask
from app.audit import write_audit

router = APIRouter()


class Exchange(BaseModel):
    """One earlier question of this chat and the answer it got."""

    question: str = Field(min_length=1, max_length=3000)
    answer: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=3000)
    history: list[Exchange] = Field(default_factory=list, max_length=20)  # earlier exchanges of THIS chat, oldest first. The agent reads only the last few


def run_agent(question: str, history: list[dict]) -> dict:
    """Run the agent. The AI provider's rate limit (free plans are small) becomes a plain 429 "busy" message."""
    try:
        return ask(question, history)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 429:
            raise HTTPException(
                status_code=429, detail="The AI service is busy or its daily limit is used up. Please try again in a few minutes."
            ) from exc
        raise


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/chat")
def chat(req: ChatRequest):
    result = run_agent(req.question, [exchange.model_dump() for exchange in req.history])
    write_audit(req.question, result["source_used"], result["trace"])
    return {
        "answer": result["answer"],
        "source_used": result["source_used"],
        "citations": result["citations"],
        "trace": result["trace"],
    }
