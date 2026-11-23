# tests/

Run from the project root with `pytest`. No API keys needed.

- `conftest.py` - shared fakes: an in-memory Pinecone, a fake embedder, a fake LLM and a fake Supabase, so no test needs keys, a network or a model download.
- `test_graph.py` - the "what runs next" rules, and that the graph builds.
- `test_api.py` - health check, the page files (never cached, every page present and every file the pages link to served), the admin key rules (including "switched off"), upload, chat answers and errors (and a chat's earlier exchanges reaching the agent, a bad history refused), and the start-up warm-up.
- `test_ingest.py` - reading and cutting pdf, txt, md and docx files, and the ingest command.
- `test_memory.py` - short-term memory: only the last few exchanges are kept, each cut short, and memory can be switched off.
- `test_store.py` - the Pinecone side: replace on re-upload, safe ids, clear errors, never deleting an index, and the warm-up (the embedding model loads only once).
- `test_web_search.py` - the Tavily side, against a fake Tavily: results become documents, the key stays in a header, and every failure (bad key, limits, no internet, unreadable reply) gives a plain message.
- `test_nodes.py` - every agent step, and the whole graph on all five paths (KB answer, web answer, rewrite and retry, fallback, small talk), using a fake LLM, fake KB and fake web search. Also follow-ups: a first message is routed exactly as before, a follow-up is restated, later steps use the restated question, and chats never mix.
- `test_supabase.py` - the Supabase helper, against the fake Supabase: the right address and headers, the secret key only when a caller passes it in, plain errors that never hold a key. Also telling a publishable key from a secret key.
- `test_audit.py` - the audit log: it records who asked and in which chat, leaves both empty for a question asked without an account, and upgrades an audit file made before accounts existed in place, keeping its rows.
- `test_conversations.py` - saved chats: the six routes and the calls behind them, against a small in-memory stand-in for Supabase's database that enforces the same privacy rule as `supabase/schema.sql`. Covers creating, listing (newest first, only your own), renaming, deleting with its messages, reading a thread, and asking in a chat: the earlier messages come from the database (a history in the request is ignored, only the last few are loaded), the first question names the chat and a title you chose is kept, the audit log gets the user and chat. Someone else's chat is a 404 and costs no AI tokens. A Supabase problem still answers the question with a warning, a busy AI service is a plain 429, and every route needs a sign-in.
- `test_auth.py` - login tokens, all offline (the keys are made inside the tests): a good token (ES256 and RSA), then every kind of token that must be refused (expired, wrong audience or project, signed by another key, changed after signing, unsigned, signed with HS256 using the public key as the secret, anon and service roles, anonymous guests, junk). It also covers how the public keys are kept (fetched once, refreshed when old, a new key picked up at most once a minute, junk cannot hammer Supabase, 503 and not 401 when Supabase is down, a refused token never reaches the log) and the routes `GET /api/me` and `GET /api/config` (the secret key is never handed out).
- `test_llm.py` - the LLM helper: strict JSON decisions, safe defaults, and the two-model setup.
- `test_config.py` - `.env.example` holds no real key, and its defaults match `app/config.py`.

## `run_eval.py` - the real check

Not a test. It asks the agent the questions in `eval_questions.json` with the real Groq, Pinecone and Tavily, and reports which path each question took, whether the right documents were cited, and how many tokens it cost.

```
python -m tests.run_eval                  a sample of 10 questions covering every path
python -m tests.run_eval Q01 Q23          only these questions
python -m tests.run_eval --all            all 33 (a big bite out of the free daily Groq budget)
python -m tests.run_eval --followups      the follow-up questions in eval_followups.json (about 35,000 tokens)
python -m tests.run_eval --budget 20000   stop before any one model could go over 20,000 tokens
```

`eval_questions.json` holds the 33 questions from the project brief. `eval_followups.json` holds follow-ups: each one comes with the earlier question and answer of its chat. Besides "pronoun" follow-ups ("what if it keeps dropping?"), it checks a topic switch (the old topic must not leak in), a closing "thanks", a public follow-up that goes to the web, and a company-only follow-up after a public topic (it must never search the web).

It is paced to stay under Groq's per-minute limit, and it stops at the first error so a broken setup never wastes tokens.

The Supabase project has its own real check, which is not part of `pytest` either: `python -m app.supabase.check --full` (see `app/supabase/README.md`).
