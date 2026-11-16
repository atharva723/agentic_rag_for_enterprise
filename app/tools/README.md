# tools/

Things the agent can use besides the knowledge base.

- `web_search.py` - Tavily web search. `search(query)` returns a list of `Document`, the same shape as KB search, so grading and answering treat both sources the same way. Each result has the snippet as `page_content`, and `source` (the page URL), `title`, `score` and `published_date` in `metadata`.

To add a new source (tickets, HR docs, SQL): add one file here with a `search(query)` function.

## Set up Tavily (free)

1. Sign up at https://app.tavily.com. No credit card is needed.
2. Copy your API key. It starts with `tvly-`.
3. Put it in `.env` as `TAVILY_API_KEY=...`. Use `.env`, not `.env.example`: the app reads only `.env`.
4. Try it: `python -m app.tools.web_search "latest Microsoft Teams outage"`

## Cost

- One search costs 1 credit (the `basic` depth). The free plan gives 1,000 credits a month.
- The web is only searched when the knowledge base answer is weak, so most questions cost nothing. If the question is rewritten and retried, that is a second search.
- Each search returns up to `TOP_K` results (default 4), cut to about 1,000 characters each, so the evidence stays small for the LLM.

## What leaves your network

Only the search text is sent to Tavily. No documents and no knowledge base text are sent. Do not put secrets in a question that may reach the web.

## When it fails

`search` raises `WebSearchError` with a plain message: wrong key, too many searches, plan limit used up, no internet, or an unreadable reply. The message never contains the key. The agent step that calls it catches the error, adds a line to the trace, and goes on without web evidence.
