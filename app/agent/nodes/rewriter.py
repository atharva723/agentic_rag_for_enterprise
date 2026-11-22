"""Retry step: rewrite a weak query so the next search works better."""
from app.agent import llm, prompts
from app.agent.state import AgentState, QueryRewrite, asked


def rewrite_query(state: AgentState) -> dict:
    """Reads: question (restated, for a follow-up), query, retries. Writes: query, retries (+1), trace.

    retries always goes up, even if the reply is unreadable, so the retry limit in graph.py can never be skipped.
    """
    prompt = prompts.REWRITER.format(question=asked(state), query=state["query"])
    decision = llm.decide(QueryRewrite, prompt, QueryRewrite(query=state["query"]))
    query = llm.one_line(decision.query, state["query"])
    return {"query": query, "retries": state["retries"] + 1, "trace": [f"Query rewritten → {query}"]}
