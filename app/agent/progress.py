"""Live progress: what the flow is doing right now, in plain words, for a caller that wants to show it as it happens.

`ask(question, history, on_step)` calls `on_step` with one small dict at the start and at the end of every step:
    {"step": "retrieve_kb", "status": "start", "label": "Searching the company documents…"}
    {"step": "retrieve_kb", "status": "done", "lines": ["Private KB retrieval → 4 chunks"]}
`lines` are the decision-path lines the step wrote (the same ones that end up in result["trace"]).
"""


def running_label(step: str, state: dict) -> str:
    """What the step is doing, said while it runs. Steps that do one job in two situations (searching again after a rewrite, grading
    company documents or web pages, writing from either) read the shared notes to say which one this is."""
    web = state.get("source_used") == "web_search"
    labels = {
        "route_question": "Understanding your question…",
        "retrieve_kb": "Searching the company documents again with the new wording…" if state.get("retries") else "Searching the company documents…",
        "grade_evidence": "Checking whether the web results are good enough…" if web else "Checking whether the company documents answer it…",
        "search_web": "Not enough in the company documents, searching the public web…",
        "rewrite_query": "Still not enough, rewriting the question to search again…",
        "generate_answer": "Writing the answer from the web results…" if web else "Writing the answer from the company documents…",
        "answer_direct": "Writing a reply…",
        "fallback_answer": "Nothing could be confirmed, writing a careful answer…",
    }
    return labels.get(step, "Working…")
