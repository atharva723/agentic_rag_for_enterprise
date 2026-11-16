"""The whole agent flow on one screen. Nodes do the work; the two rules below decide what runs next."""
import logging
from functools import lru_cache
from typing import Literal

from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.graph import END, START, StateGraph

from app.agent.nodes.answerer import answer_direct, fallback_answer, generate_answer
from app.agent.nodes.grader import grade_evidence
from app.agent.nodes.retriever import retrieve_kb, search_web
from app.agent.nodes.rewriter import rewrite_query
from app.agent.nodes.router import route_question
from app.agent.state import AgentState
from app.config import get_settings

log = logging.getLogger(__name__)


def after_router(state: AgentState) -> Literal["retrieve_kb", "answer_direct"]:
    return "retrieve_kb" if state["route"] == "kb" else "answer_direct"


def after_grade(state: AgentState) -> Literal["generate_answer", "search_web", "rewrite_query", "fallback_answer"]:
    if state["grade"] == "good":
        return "generate_answer"
    if state["source_used"] == "private_kb" and state["public"]:
        return "search_web"  # the KB was weak and public pages could help: try the web
    if state["retries"] < get_settings().max_retries:
        return "rewrite_query"  # still weak: rewrite once, then search the KB again
    return "fallback_answer"  # out of retries: answer as best we can, and say so


def build_graph():
    g = StateGraph(AgentState)
    g.add_node(route_question)
    g.add_node(retrieve_kb)
    g.add_node(search_web)
    g.add_node(grade_evidence)
    g.add_node(rewrite_query)
    g.add_node(generate_answer)
    g.add_node(answer_direct)
    g.add_node(fallback_answer)

    g.add_edge(START, "route_question")
    g.add_conditional_edges("route_question", after_router)
    g.add_edge("retrieve_kb", "grade_evidence")
    g.add_edge("search_web", "grade_evidence")
    g.add_conditional_edges("grade_evidence", after_grade)
    g.add_edge("rewrite_query", "retrieve_kb")
    g.add_edge("generate_answer", END)
    g.add_edge("answer_direct", END)
    g.add_edge("fallback_answer", END)
    return g.compile()


@lru_cache
def _graph():
    return build_graph()


def ask(question: str) -> AgentState:
    """Run the agent on one question and return the final state.

    result["tokens"] says how many LLM tokens each model used for this question. It is also logged, so you can watch the free budget.
    """
    with get_usage_metadata_callback() as usage:
        result = _graph().invoke(
            {"question": question, "query": question, "also": "", "public": False, "retries": 0, "docs": [], "citations": [], "trace": []}
        )
    result["tokens"] = {model: counts["total_tokens"] for model, counts in usage.usage_metadata.items()}
    log.info("Tokens used: %s", result["tokens"] or "none")
    return result
