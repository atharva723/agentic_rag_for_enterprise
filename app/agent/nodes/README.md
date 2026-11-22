# nodes/

The steps of the agent, one small file per job. A step is a plain function. It reads the state, does one thing, and returns only what it changed.

- `router.py` - `route_question`: is this an IT question or just chat? It also cleans the question into a short search query (fixes typos, drops names and secrets), adds a second search for a second topic, and decides if public web pages could answer it at all. In a follow-up it first restates the message as a complete question, using the earlier messages of the chat; every later step works on that restated question. A chat's first message is routed exactly as before.
- `retriever.py` - `retrieve_kb` and `search_web`: collect the evidence. If the web search fails, the flow carries on without it.
- `grader.py` - `grade_evidence`: is the evidence good enough? (`good` or `weak`). Used for both KB and web evidence. Web pages are judged by the bigger model, because they are noisier.
- `rewriter.py` - `rewrite_query`: make a weak query better, and count the retry.
- `answerer.py` - `generate_answer`, `answer_direct`, `fallback_answer`: write the reply. A web answer always starts with a notice that it is not from company documents, plus a "Heads up" line when a "now" or "latest" question only found old pages. The fallback always starts with a notice that the evidence was too weak. Every reply is tidied for the chat page: no markdown symbols, and look-alike spaces and hyphens made plain, so file names and links can be copied.

Steps never call each other. Only `../graph.py` decides the order. Each step adds lines to the decision path (the "trace") that the chat page shows.

To add a step: write a function here, then add it to `graph.py`.
