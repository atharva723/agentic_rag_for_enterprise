"""The shared notes every step reads from and writes to, plus the shapes of the LLM's decisions."""
import operator
from typing import Annotated, Literal

from langchain_core.documents import Document
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

Route = Literal["kb", "direct"]
Grade = Literal["good", "weak"]
Source = Literal["private_kb", "web_search", "direct", "fallback"]


class RouteDecision(BaseModel):
    """What the router LLM returns."""

    route: Route
    query: str = Field(description="A short search query for the message. For 'direct', repeat the message.")
    also: str = Field(description="A second short search query, only if the message asks about two separate things. Otherwise an empty string.")
    public: bool = Field(description="True if public web pages could answer it. False if it needs the company's own information.")


class Restated(BaseModel):
    """Listed first on purpose: the model fills the fields in order, so it has understood the message before it decides anything else."""

    standalone: str = Field(description="The new message rewritten as one complete question that makes sense without the earlier messages. The same words only if it is about a new topic.")


class FollowUpDecision(RouteDecision, Restated):
    """What the router LLM returns when the message is part of a conversation: the usual decision, plus the restated message."""


class EvidenceGrade(BaseModel):
    """What the grader LLM returns."""

    grade: Grade


class QueryRewrite(BaseModel):
    """What the rewriter LLM returns."""

    query: str = Field(description="The new search query.")


class AgentState(TypedDict):
    question: str  # what the user asked (never changes)
    history: list[dict]  # earlier exchanges of this chat, oldest first: [{"question": ..., "answer": ...}]. Empty for a first message
    standalone: str  # a follow-up restated so it makes sense on its own. Only set for a follow-up: read it with asked()
    query: str  # what we search with (changes when the question is rewritten)
    also: str  # a second search for a second topic in the question ("" if there is only one)
    public: bool  # can public web pages answer this? False means it needs company information, so the web is never searched
    web_allowed: bool  # the person turned web search on for this question. Set by ask(), read only by the router, which then opens the web (public)
    route: Route
    docs: list[Document]  # current evidence, from the KB or the web
    grade: Grade  # is the current evidence good enough?
    retries: int  # how many times the query was rewritten
    answer: str
    source_used: Source
    citations: list[dict]  # [{"source": file or url, "type": "kb" | "web"}]
    trace: Annotated[list[str], operator.add]  # decision path; steps return new lines, they are appended
    tokens: dict[str, int]  # LLM tokens used per model for this question. Filled in by ask(), not by the steps


def asked(state: AgentState) -> str:
    """The question every step after the router works on: a follow-up restated to stand alone, otherwise what the user typed."""
    return state.get("standalone") or state["question"]
