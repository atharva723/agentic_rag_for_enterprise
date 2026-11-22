# tests/

Run from the project root with `pytest`. No API keys needed.

- `conftest.py` - shared fakes: an in-memory Pinecone and a fake embedder, so no test needs keys, a network or a model download.
- `test_graph.py` - the "what runs next" rules, and that the graph builds.
- `test_api.py` - health check, the page files (never cached, every page present and every file the pages link to served), the admin key rules (including "switched off"), upload, chat answers and errors, and the start-up warm-up.
- `test_ingest.py` - reading and cutting pdf, txt, md and docx files, and the ingest command.
- `test_store.py` - the Pinecone side: replace on re-upload, safe ids, clear errors, never deleting an index, and the warm-up (the embedding model loads only once).
- `test_web_search.py` - the Tavily side, against a fake Tavily: results become documents, the key stays in a header, and every failure (bad key, limits, no internet, unreadable reply) gives a plain message.
- `test_nodes.py` - every agent step, and the whole graph on all five paths (KB answer, web answer, rewrite and retry, fallback, small talk), using a fake LLM, fake KB and fake web search.
- `test_llm.py` - the LLM helper: strict JSON decisions, safe defaults, and the two-model setup.
- `test_config.py` - `.env.example` holds no real key, and its defaults match `app/config.py`.

## `run_eval.py` - the real check

Not a test. It asks the agent the questions in `eval_questions.json` with the real Groq, Pinecone and Tavily, and reports which path each question took, whether the right documents were cited, and how many tokens it cost.

```
python -m tests.run_eval                  a sample of 10 questions covering every path
python -m tests.run_eval Q01 Q23          only these questions
python -m tests.run_eval --all            all 33 (a big bite out of the free daily Groq budget)
python -m tests.run_eval --budget 20000   stop before any one model could go over 20,000 tokens
```

It is paced to stay under Groq's per-minute limit, and it stops at the first error so a broken setup never wastes tokens.
