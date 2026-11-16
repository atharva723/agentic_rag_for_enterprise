import json

import httpx
import pytest

from app.config import get_settings
from app.tools import web_search
from app.tools.web_search import WebSearchError

KEY = "tvly-test-key"


class FakeTavily:
    """Stands in for the Tavily server. Set what it answers, then read what it was sent."""

    def __init__(self):
        self.status, self.payload, self.raw, self.error, self.requests = 200, {"results": []}, None, None, []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error:
            raise self.error
        if self.raw is not None:
            return httpx.Response(self.status, content=self.raw)
        return httpx.Response(self.status, json=self.payload)

    @property
    def body(self) -> dict:
        return json.loads(self.requests[-1].content)


@pytest.fixture
def tavily(monkeypatch):
    """Swap the network for a fake Tavily. The real _client() still runs, so key and header handling are tested."""
    fake = FakeTavily()
    settings = get_settings()
    monkeypatch.setattr(settings, "tavily_api_key", KEY)
    monkeypatch.setattr(settings, "top_k", 4)
    real_client = httpx.Client
    monkeypatch.setattr(web_search.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(fake.handle), **kwargs))
    web_search._client.cache_clear()
    yield fake
    web_search._client.cache_clear()


def result(n, **extra):
    return {"title": f"Title {n}", "url": f"https://site{n}.example/page", "content": f"snippet {n}", "score": 0.5, **extra}


def test_results_become_documents_with_the_url_as_source(tavily):
    tavily.payload = {
        "results": [
            result(1, content="  alpha  ", score=0.91234567, published_date="Thu, 22 Jan 2026 19:59:04 GMT"),
            result(2, content="beta"),
        ]
    }
    first, second = web_search.search("teams outage")
    assert first.page_content == "alpha"
    assert first.metadata == {"source": "https://site1.example/page", "title": "Title 1", "score": 0.9123, "published_date": "2026-01-22"}
    assert second.page_content == "beta"
    assert "published_date" not in second.metadata


def test_it_sends_one_cheap_small_search_with_the_key_in_a_header(tavily):
    web_search.search("how do I reset my password")
    (request,) = tavily.requests
    assert str(request.url) == web_search.URL
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert tavily.body == {
        "query": "how do I reset my password",
        "search_depth": "basic",
        "max_results": 4,
        "chunks_per_source": 2,
        "include_published_date": True,
        "exclude_domains": web_search.SKIP_DOMAINS,
    }
    assert "youtube.com" in web_search.SKIP_DOMAINS and "facebook.com" in web_search.SKIP_DOMAINS
    assert KEY not in str(request.url) and KEY.encode() not in request.content


def test_the_query_is_made_one_line_and_short(tavily):
    web_search.search("  hello \n   world  ")
    assert tavily.body["query"] == "hello world"
    web_search.search("word " * 500)
    assert len(tavily.body["query"]) <= web_search.MAX_QUERY_CHARS


def test_a_blank_query_makes_no_call_and_costs_no_credit(tavily):
    assert web_search.search("  \n ") == []
    assert tavily.requests == []


def test_a_long_snippet_is_cut_to_keep_the_prompt_small(tavily):
    tavily.payload = {"results": [result(1, content="x" * 5000)]}
    (doc,) = web_search.search("q")
    assert len(doc.page_content) == web_search.MAX_SNIPPET_CHARS


def test_results_without_a_url_or_text_and_repeated_urls_are_dropped(tavily):
    tavily.payload = {
        "results": [
            result(1),
            result(1, content="the same page again"),
            {"title": "no url", "content": "text", "score": 0.4},
            {"title": "no text", "url": "https://empty.example", "content": "  ", "score": 0.4},
            {"title": "null text", "url": "https://null.example", "content": None, "score": None},
            result(2),
        ]
    }
    assert [d.metadata["source"] for d in web_search.search("q")] == ["https://site1.example/page", "https://site2.example/page"]


def test_no_results_is_an_empty_list_not_an_error(tavily):
    assert web_search.search("something very odd") == []


def test_how_many_results_follows_top_k_but_never_exceeds_what_tavily_allows(tavily, monkeypatch):
    monkeypatch.setattr(get_settings(), "top_k", 50)
    web_search.search("q")
    assert tavily.body["max_results"] == web_search.MAX_RESULTS == 20


def test_a_missing_key_says_where_to_put_it_and_makes_no_call(tavily, monkeypatch):
    monkeypatch.setattr(get_settings(), "tavily_api_key", "")
    with pytest.raises(WebSearchError, match=r"TAVILY_API_KEY.*\.env"):
        web_search.search("q")
    assert tavily.requests == []


@pytest.mark.parametrize(
    "status, words",
    [
        (401, "API key"),
        (429, "too many searches"),
        (432, "plan limit"),
        (433, "pay-as-you-go"),
        (500, "problem on its side"),
        (503, "problem on its side"),
        (400, "rejected the search"),
        (422, "rejected the search"),
    ],
)
def test_tavily_errors_become_a_plain_message_without_the_key(tavily, status, words):
    tavily.status = status
    tavily.payload = {"detail": {"error": f"secret detail {KEY}"}}
    with pytest.raises(WebSearchError, match=words) as caught:
        web_search.search("q")
    assert KEY not in str(caught.value)


@pytest.mark.parametrize("problem", [httpx.ConnectError("no internet"), httpx.ReadTimeout("too slow")])
def test_network_problems_become_a_clear_error(tavily, problem):
    tavily.error = problem
    with pytest.raises(WebSearchError, match="could not be reached") as caught:
        web_search.search("q")
    assert KEY not in str(caught.value)


@pytest.mark.parametrize("raw", [b"<html>maintenance</html>", b'{"unexpected": true}', b"[]"])
def test_a_reply_that_cannot_be_read_is_a_clear_error(tavily, raw):
    tavily.raw = raw
    with pytest.raises(WebSearchError, match="could not be read"):
        web_search.search("q")


def test_dates_are_shortened_and_odd_ones_are_kept_as_they_are():
    assert web_search._date("Fri, 13 Nov 2026 02:57:33 GMT") == "2026-11-13"
    assert web_search._date("sometime last week") == "sometime last week"
