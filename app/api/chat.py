"""Employee endpoints: health check and chat."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.graph import ask
from app.audit import write_audit

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=3000)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/chat")
def chat(req: ChatRequest):
    try:
        result = ask(req.question)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 429:  # the AI provider's rate limit. Free plans are small.
            raise HTTPException(
                status_code=429, detail="The AI service is busy or its daily limit is used up. Please try again in a few minutes."
            ) from exc
        raise
    write_audit(req.question, result["source_used"], result["trace"])
    return {
        "answer": result["answer"],
        "source_used": result["source_used"],
        "citations": result["citations"],
        "trace": result["trace"],
    }
