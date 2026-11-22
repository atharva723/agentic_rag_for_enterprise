"""Step 1: decide if the question needs the knowledge base or is just chat, and tidy the search query."""
from app.agent import llm, prompts
from app.agent.state import AgentState, FollowUpDecision, RouteDecision


def route_question(state: AgentState) -> dict:
    """Reads: question, history. Writes: route, query, also, public, trace. A follow-up also writes: standalone.

    also = a second search for a second topic in the question. public = can public web pages answer this at all?
    A follow-up ("what if it keeps disconnecting?") is restated so it makes sense on its own, and every later step works on that.
    The first message of a chat has no history, so it is routed exactly as before.
    """
    question = state["question"]
    history = state.get("history")
    unsure = dict(route="kb", query=question, also="", public=False)  # unreadable reply: search the KB only, never the web
    if history:
        prompt = prompts.ROUTER.format(question=prompts.FOLLOW_UP.format(question=question, history=prompts.format_history(history)))
        decision = llm.decide(FollowUpDecision, prompt, FollowUpDecision(**unsure, standalone=question))
        standalone = llm.one_line(decision.standalone, question)
    else:
        decision = llm.decide(RouteDecision, prompts.ROUTER.format(question=question), RouteDecision(**unsure))
        standalone = question
    kb = decision.route == "kb"
    query = llm.one_line(decision.query, standalone) if kb else standalone
    also = llm.one_line(decision.also, "") if kb else ""
    if also == query:
        also = ""
    line = f"Router → {decision.route.upper()}"
    if kb and query != standalone:
        line += f" (search: {query})"
    if also:
        line += f" + also: {also}"
    trace = [f"Follow-up understood as: {standalone}", line] if standalone != question else [line]
    out = {"route": decision.route, "query": query, "also": also, "public": kb and decision.public, "trace": trace}
    if history:
        out["standalone"] = standalone
    return out
