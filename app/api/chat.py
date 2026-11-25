"""What the saved-chat routes share: run_agent() (the one place the agent is called from) and the health check."""
from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from app.agent.graph import ask

router = APIRouter()


def run_agent(question: str, history: list[dict], on_step: Callable[[dict], None] | None = None) -> dict:
    """Run the agent. The AI provider's rate limit (free plans are small) becomes a plain 429 "busy" message.
    on_step, when given, hears about each step as it starts and finishes (see app/agent/progress.py)."""
    try:
        return ask(question, history, on_step) if on_step else ask(question, history)
    except Exception as exc:
        if getattr(exc, "status_code", None) == 429:
            raise HTTPException(
                status_code=429, detail="The AI service is busy or its daily limit is used up. Please try again in a few minutes."
            ) from exc
        raise


@router.get("/health")
def health():
    return {"status": "ok"}
