"""The whole agent flow on one screen. Nodes do the work; the two rules below decide what runs next."""
import logging
from functools import lru_cache
from typing import Callable, Literal

from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.graph import END, START, StateGraph

from app.agent import memory, progress
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


def _tell(on_step: Callable[[dict], None], event: dict) -> None:
    """Pass one progress event on. A callback that fails must never cost the person their answer, so it only logs."""
    try:
        on_step(event)
    except Exception as exc:
        log.warning("Progress callback failed, carrying on: %s", exc)


def _invoke_with_progress(start: dict, on_step: Callable[[dict], None]) -> AgentState:
    """The same run as invoke(), told step by step. LangGraph's "tasks" stream says when a step is about to run (before it does the work)
    and when it finished, with what it wrote. The "values" stream carries the notes after each step, so the last one is the final state."""
    result = start
    for mode, chunk in _graph().stream(start, stream_mode=["tasks", "values"]):
        if mode == "values":
            result = chunk
        elif "result" in chunk:  # a step finished
            if chunk.get("error"):
                continue  # it failed. The error is raised in a moment, and the caller reports it
            written = chunk["result"] if isinstance(chunk["result"], dict) else {}
            _tell(on_step, {"step": chunk["name"], "status": "done", "lines": list(written.get("trace", []))})
        else:  # a step is about to run
            _tell(on_step, {"step": chunk["name"], "status": "start", "label": progress.running_label(chunk["name"], chunk["input"])})
    return result


def ask(question: str, history: list[dict] | None = None, on_step: Callable[[dict], None] | None = None, web: bool = False) -> AgentState:
    """Run the agent on one question and return the final state.

    history = the earlier exchanges of the SAME chat, oldest first: [{"question": ..., "answer": ...}]. Pass nothing for a chat's first message.
    Only the last MEMORY_TURNS are used, cut short, and only to understand a follow-up. Nothing is kept after the answer is written.

    on_step = optional. Called with a small dict as each step starts and finishes, so a page can show the path live (see progress.py).
    The answer is the same with or without it.

    web = True when the person turned web search on for this question. The company documents are still searched first, but the web may
    then be used even for a question the router judged company-only (see route_question). The search text is still the router's cleaned one.

    result["tokens"] says how many LLM tokens each model used for this question. It is also logged, so you can watch the free budget.
    """
    start = {
        "question": question,
        "history": memory.recent(history),
        "query": question,
        "also": "",
        "public": False,
        "web_allowed": web,
        "retries": 0,
        "docs": [],
        "citations": [],
        "trace": [],
    }
    with get_usage_metadata_callback() as usage:
        result = _graph().invoke(start) if on_step is None else _invoke_with_progress(start, on_step)
    result["tokens"] = {model: counts["total_tokens"] for model, counts in usage.usage_metadata.items()}
    log.info("Tokens used: %s", result["tokens"] or "none")
    return result
