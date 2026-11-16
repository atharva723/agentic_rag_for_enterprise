"""The one place that creates the LLM clients. To switch provider, change only this file."""
import logging
from functools import lru_cache
from typing import TypeVar

from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

from app.config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


@lru_cache
def get_llm(fast: bool = False):
    """The answer model (bigger, writes the final text) or the fast model (small, makes yes/no decisions).

    Call it as get_llm() or get_llm(fast=True), so the cache keeps exactly one client for each.
    """
    from langchain_groq import ChatGroq  # imported here so the app starts fast and tests need no LLM package

    s = get_settings()
    if not s.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Put it in .env (see README.md).")
    return ChatGroq(
        model=s.groq_fast_model if fast else s.groq_model,
        temperature=0,
        reasoning_effort="low",  # these models think before they answer. "low" keeps that hidden thinking (and its tokens) short
        max_tokens=800 if fast else 1200,  # a ceiling, not a target: Groq charges the tokens actually used. Too low cuts a reply off.
        timeout=30,
        api_key=s.groq_api_key,
    )


def decide(schema: type[T], prompt: str, default: T, *, fast: bool = True) -> T:
    """Ask a model for a small decision as strict JSON. If its reply cannot be read, return the safe `default`.

    The small fast model by default. Pass fast=False for the bigger model when the judgement is harder.
    """
    from groq import BadRequestError  # the provider's own error type, so it is imported here with the rest of the Groq code

    model = get_llm(fast=fast).with_structured_output(schema, method="json_schema", strict=True)
    try:
        return model.invoke(prompt)
    except (OutputParserException, ValidationError) as exc:
        log.warning("Could not read the model's decision (%s). Using the safe default.", type(exc).__name__)
        return default
    except BadRequestError as exc:
        if "json_validate_failed" not in str(exc):  # only "the model did not finish its JSON" is safe to work around
            raise
        log.warning("The model did not finish its decision (reply too long). Using the safe default.")
        return default


def one_line(text: str, fallback: str, limit: int = 300) -> str:
    """Tidy a search query written by the LLM: one line, not too long. Use `fallback` if nothing is left."""
    return " ".join(text.split())[:limit] or fallback
