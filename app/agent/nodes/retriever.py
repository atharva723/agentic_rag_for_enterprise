"""Steps 2 and 5: collect evidence. First the private knowledge base, then the web."""
import logging
from itertools import zip_longest

from langchain_core.documents import Document

from app.agent.state import AgentState
from app.config import get_settings
from app.rag import store
from app.tools import web_search
from app.tools.web_search import WebSearchError

log = logging.getLogger(__name__)


def _merge(first: list[Document], second: list[Document], limit: int) -> list[Document]:
    """Take turns from two result lists so both topics are represented. Skip repeats and stop at `limit`."""
    merged, seen = [], set()
    for pair in zip_longest(first, second):
        for doc in pair:
            if doc is not None and (doc.metadata["source"], doc.page_content) not in seen:
                seen.add((doc.metadata["source"], doc.page_content))
                merged.append(doc)
    return merged[:limit]


def retrieve_kb(state: AgentState) -> dict:
    """Reads: query, also. Writes: docs, source_used="private_kb", trace.

    A second topic in the question (also) gets its own search, and the two result lists take turns.
    """
    docs = store.search(state["query"])
    if state["also"]:
        docs = _merge(docs, store.search(state["also"]), get_settings().top_k + 2)
    return {"docs": docs, "source_used": "private_kb", "trace": [f"Private KB retrieval → {len(docs)} chunks"]}


def search_web(state: AgentState) -> dict:
    """Reads: query. Writes: docs, source_used="web_search", trace. Only runs when the KB evidence was weak.

    If the search fails, the flow carries on with no web evidence (and says why in the trace) instead of crashing the chat.
    """
    try:
        docs = web_search.search(state["query"])
        line = f"Web search → {len(docs)} results"
    except WebSearchError as exc:
        log.warning("Web search failed: %s", exc)
        docs, line = [], f"Web search failed → {exc}"
    return {"docs": docs, "source_used": "web_search", "trace": [line]}
