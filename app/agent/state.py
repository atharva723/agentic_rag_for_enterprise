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


class EvidenceGrade(BaseModel):
    """What the grader LLM returns."""

    grade: Grade


class QueryRewrite(BaseModel):
    """What the rewriter LLM returns."""

    query: str = Field(description="The new search query.")


class AgentState(TypedDict):
    question: str  # what the user asked (never changes)
    query: str  # what we search with (changes when the question is rewritten)
    also: str  # a second search for a second topic in the question ("" if there is only one)
    public: bool  # can public web pages answer this? False means it needs company information, so the web is never searched
    route: Route
    docs: list[Document]  # current evidence, from the KB or the web
    grade: Grade  # is the current evidence good enough?
    retries: int  # how many times the query was rewritten
    answer: str
    source_used: Source
    citations: list[dict]  # [{"source": file or url, "type": "kb" | "web"}]
    trace: Annotated[list[str], operator.add]  # decision path; steps return new lines, they are appended
    tokens: dict[str, int]  # LLM tokens used per model for this question. Filled in by ask(), not by the steps
