"""Tavily web search. Returns Documents, the same shape as the KB, so grading and answering treat both alike."""
import logging
from email.utils import parsedate_to_datetime
from functools import lru_cache

import httpx
from langchain_core.documents import Document

from app.config import get_settings

log = logging.getLogger(__name__)

URL = "https://api.tavily.com/search"
MAX_QUERY_CHARS = 400  # a web search query should be short (Tavily's own limit is 1500)
MAX_SNIPPET_CHARS = 1000  # per result: keeps the LLM prompt about as small as the KB evidence
MAX_RESULTS = 20  # the most Tavily will return
SKIP_DOMAINS = ["youtube.com", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com", "reddit.com", "pinterest.com", "quora.com"]  # social media and video are not reliable IT guidance

# What Tavily's error codes mean, in plain words
PROBLEMS = {
    401: "Tavily rejected the API key. Check TAVILY_API_KEY in .env.",
    429: "Tavily says there were too many searches too fast. Try again in a minute.",
    432: "The Tavily plan limit is used up (the free plan has 1,000 searches a month).",
    433: "The Tavily pay-as-you-go limit is used up.",
}


class WebSearchError(RuntimeError):
    """The web search failed. The message is plain text and never contains the API key."""


def _problem(code: int) -> str:
    if code in PROBLEMS:
        return PROBLEMS[code]
    if code >= 500:
        return f"Tavily had a problem on its side (HTTP {code}). Try again later."
    return f"Tavily rejected the search (HTTP {code})."


@lru_cache
def _client() -> httpx.Client:
    key = get_settings().tavily_api_key
    if not key:
        raise WebSearchError("TAVILY_API_KEY is missing. Put it in .env (see app/tools/README.md).")
    return httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=10)


def _date(text: str) -> str:
    """Tavily sends 'Thu, 22 Jan 2026 19:59:04 GMT'. A short '2026-01-22' is easier to read. Odd values stay as they are."""
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return text


def search(query: str) -> list[Document]:
    """Search the web. Each result: page_content = the snippet, metadata = {"source": url, "title", "score", "published_date"}.

    The search text is sent to Tavily, so it leaves your network. Raises WebSearchError if the search fails.
    """
    query = " ".join(query.split())[:MAX_QUERY_CHARS]  # one line, not too long
    if not query:
        return []  # nothing to look for, so don't spend a credit
    body = {
        "query": query,
        "search_depth": "basic",  # 1 credit per search ("advanced" costs 2)
        "max_results": min(get_settings().top_k, MAX_RESULTS),
        "chunks_per_source": 2,  # about 500 characters per chunk: enough to judge and answer, small enough for the LLM
        "include_published_date": True,  # lets the answer say how old a source is
        "exclude_domains": SKIP_DOMAINS,
    }
    try:
        response = _client().post(URL, json=body)
    except httpx.HTTPError as exc:  # no internet, DNS failure, timeout
        raise WebSearchError(f"The web search could not be reached ({type(exc).__name__}).") from exc
    if response.status_code != 200:
        raise WebSearchError(_problem(response.status_code))
    try:
        results = response.json()["results"]
    except (ValueError, KeyError, TypeError) as exc:
        raise WebSearchError("Tavily sent a reply that could not be read.") from exc

    docs, seen = [], set()
    for item in results:
        url, text = item.get("url"), (item.get("content") or "").strip()
        if not url or not text or url in seen:
            continue
        seen.add(url)
        meta = {"source": url, "title": item.get("title") or url, "score": round(float(item.get("score") or 0), 4)}
        if item.get("published_date"):
            meta["published_date"] = _date(item["published_date"])
        docs.append(Document(page_content=text[:MAX_SNIPPET_CHARS], metadata=meta))
    log.info("Web search returned %d results", len(docs))
    return docs


if __name__ == "__main__":
    # python -m app.tools.web_search "your question"   (uses 1 free Tavily credit)
    import sys

    try:
        found = search(" ".join(sys.argv[1:]) or "latest Microsoft Teams outage")
    except WebSearchError as exc:
        sys.exit(f"Web search failed: {exc}")
    print(f"{len(found)} results")
    for doc in found:
        m = doc.metadata
        print(f"  {m.get('published_date', 'no date'):10}  {m['title'][:60]}\n              {m['source']}")
