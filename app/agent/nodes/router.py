"""Step 1: decide if the question needs the knowledge base or is just chat, and tidy the search query."""
from app.agent import llm, prompts
from app.agent.state import AgentState, FollowUpDecision, RouteDecision

WEB_ON = "Web search turned on by you"


def route_question(state: AgentState) -> dict:
    """Reads: question, history, web_allowed. Writes: route, query, also, public, trace. A follow-up also writes: standalone.

    also = a second search for a second topic in the question. public = can public web pages answer this at all?
    web_allowed = the person turned web search on for this question: the web may then be used even if the router judged it company-only.
    A follow-up ("what if it keeps disconnecting?") is restated so it makes sense on its own, and every later step works on that.
    The first message of a chat has no history, so it is routed exactly as before.
    """
    question = state["question"]
    history = state.get("history")
    unsure = dict(route="kb", query=question, also="", public=False)  # unreadable reply: search the KB only, never the web
    if history:
        prompt = prompts.ROUTER.format(question=prompts.FOLLOW_UP.format(question=question, history=prompts.format_history(history)))
        default = FollowUpDecision(**unsure, standalone=question)
        decision = llm.decide(FollowUpDecision, prompt, default)
        standalone = llm.one_line(decision.standalone, question)
    else:
        default = RouteDecision(**unsure)
        decision = llm.decide(RouteDecision, prompts.ROUTER.format(question=question), default)
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
    # The person turned web search on, so a question that looks company-only may use the web. Not when the router's reply was unreadable
    # (the decision is the default): the query is then the question as typed, never cleaned of names and secrets, so it stays off the web.
    opened = kb and not decision.public and bool(state.get("web_allowed")) and decision is not default
    if opened:
        trace.append(WEB_ON)
    out = {"route": decision.route, "query": query, "also": also, "public": (kb and decision.public) or opened, "trace": trace}
    if history:
        out["standalone"] = standalone
    return out
