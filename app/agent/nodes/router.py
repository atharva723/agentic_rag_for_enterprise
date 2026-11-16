"""Step 1: decide if the question needs the knowledge base or is just chat, and tidy the search query."""
from app.agent import llm, prompts
from app.agent.state import AgentState, RouteDecision


def route_question(state: AgentState) -> dict:
    """Reads: question. Writes: route, query, also, public, trace.

    also = a second search for a second topic in the question. public = can public web pages answer this at all?
    """
    question = state["question"]
    unsure = RouteDecision(route="kb", query=question, also="", public=False)  # unreadable reply: search the KB only, never the web
    decision = llm.decide(RouteDecision, prompts.ROUTER.format(question=question), unsure)
    kb = decision.route == "kb"
    query = llm.one_line(decision.query, question) if kb else question
    also = llm.one_line(decision.also, "") if kb else ""
    if also == query:
        also = ""
    line = f"Router → {decision.route.upper()}"
    if kb and query != question:
        line += f" (search: {query})"
    if also:
        line += f" + also: {also}"
    return {"route": decision.route, "query": query, "also": also, "public": kb and decision.public, "trace": [line]}
