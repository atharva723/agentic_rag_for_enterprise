# tests/

Run from the project root with `pytest`. No API keys, internet access or model download are needed: the tests use fakes. Test names are written as sentences, so `pytest -v` reads like a list of what the app promises.

- `conftest.py` - shared fakes: an in-memory Pinecone, a fake embedder, a fake LLM and a fake Supabase, so no test needs keys, the internet or a model download. Also a clock a test can move, a reader for an event stream (`parse_events`), and the question limits switched off in every test unless a test turns them on.
- `test_graph.py` - the "what runs next" rules, and that the graph builds.
- `test_api.py` - the web server and the pages.
  - Health check, the admin key rules (including "switched off"), upload, and that the old open `/api/chat` route is gone.
  - The start-up steps (warm-up, audit trim) and the shut-down step (it waits for an answer that is still being made).
  - The page files: never cached, every page present, every file they link to served, the order the sign-in pages load their scripts in (the staff pages must not load `auth.js`), and that no page loads two scripts that declare the same top-level name (the second would silently replace the first).
  - The security headers: every page file carries a strict Content-Security-Policy (no inline script, no eval, no framing), the policy lets the sign-in reach only your own Supabase project (a damaged setting cannot add rules), and the API docs are left alone. A guard test fails when a page has an inline script, an event handler, a `<style>` block or an unlisted host, or when our own scripts use `innerHTML`, `eval` or `document.write`, so a change the browser would block is found by `pytest`.
- `test_ingest.py` - reading and cutting pdf, txt, md and docx files, and the ingest command.
- `test_memory.py` - short-term memory: only the last few exchanges are kept, each cut short, and memory can be switched off.
- `test_store.py` - the Pinecone side: replace on re-upload, safe ids, clear errors, never deleting an index, and the warm-up (the embedding model loads only once).
- `test_web_search.py` - the Tavily side, against a fake Tavily: results become documents, the key stays in a header, and every failure (bad key, limits, no internet, unreadable reply) gives a plain message.
- `test_nodes.py` - every agent step, and the whole graph on all five paths (KB answer, web answer, rewrite and retry, fallback, small talk), using a fake LLM, fake KB and fake web search.
  - Follow-ups: a first message is routed exactly as before, a follow-up is restated, later steps use the restated question, and chats never mix.
  - The live step reports (`on_step`): the same answer as without it, each step announced before it does its work (the one thing only a timing check can prove), the right wording on every path including the retry, a callback that fails never costing the answer, and a step that crashes not being reported as finished.
  - The Web search switch (`web`): turned on, a question the router judged company-only does search the web (after the company documents, with "Web search turned on by you" in the decision path). Turned off or left out, nothing changes. It does not apply to small talk, nor when the router's reply was unreadable (the raw question must not leave the network), and it adds no note when the question was public anyway.
- `test_streaming.py` + `stream_stop_check.py` - the Server-Sent Events helper (`app/api/streaming.py`).
  - One event is one line of JSON, events reach the reader while the job is still running (not in a lump at the end), keep-alive comments, a reader that goes away not stopping the job, the job running in its own thread, an HTTP error in the job becoming an `error` event with its status and message, and any other error being a plain 500 with the details only in the log.
  - The server stopping: the shut-down wait holds back while a job is running and lets go when it finishes, gives up after its time limit and says so, and does not delay a server with nothing running.
  - One test does it for real: `stream_stop_check.py` runs a real uvicorn server in a second process, a page asks and goes away, and the server gets a real `SIGTERM` (what `docker stop` sends). The answer is saved only if the shut-down step waits, because uvicorn ends the process right after that step (a job thread that is merely not a daemon is not enough).
- `test_ui_stream.py` + `ui_stream_check.js` - the page's own code for a live reply (`stream()` and its event reader in `ui/common.js`), run under Node.js (skipped if Node.js is not installed).
  - It cuts a reply in two at every byte position (inside a character and inside the blank line between events), one byte at a time, with CRLF line endings.
  - It checks that an error event, a broken connection and a failure before the stream starts are each told apart from an answer, that a bug in the drawing code does not cost the answer, and that a step is drawn the moment it arrives.
- `test_supabase.py` - the Supabase helper, against the fake Supabase: the right address and headers, the secret key only when a caller passes it in, plain errors that never hold a key. Also telling a publishable key from a secret key.
- `test_audit.py` - the audit log: it records who asked and in which chat, leaves both empty for a question asked without an account, and upgrades an audit file made before accounts existed in place, keeping its rows. Also retention: rows older than the retention period are deleted when a question is saved and at start-up, the period is a setting, `0` keeps everything, and a clean-up never makes a file that is not there or stops the server from starting.
- `test_ratelimit.py` - the rate limiter, with a clock the test moves: up to the limit is allowed and the next use is refused with how long to wait, the window slides, a refused use is not counted, everyone is counted on their own, two limits report the longer wait, `0` means no limit, a use can be given back, forgotten people are swept out, and 40 threads at once cannot get past the limit.
- `test_conversations.py` - saved chats: the seven routes and the calls behind them, against a small in-memory stand-in for Supabase's database that enforces the same privacy rule as `supabase/schema.sql`.
  - The basics: creating, listing (newest first, only your own), renaming, deleting with its messages, and reading a thread. Every route needs a sign-in.
  - Asking in a chat: the earlier messages come from the database (a history in the request is ignored, only the last few are loaded), the first question names the chat and a title you chose is kept, and the audit log gets the user and chat. Someone else's chat is a 404 and costs no AI tokens. A Supabase problem still answers the question with a warning, and a busy AI service is a plain 429.
  - The per-person limits through the real routes: the minute and the daily limit (429, a plain message and `Retry-After`), each person counted on their own, the other routes still working when the questions are used up, waiting being enough, a busy-AI question not counting, a refused question making no database or AI call, a missing login staying a 401, and every chat route counting towards the request limit.
  - The live route (`/messages/stream`): the steps arrive and then the answer, with the same saved result, audit row and memory as the plain route. A chat that is not yours, a limit or a lost login is refused before any stream opens. A busy AI service ends the stream with an error event and gives the question back, a crash is a plain error with the details only in the log, and a failure to save still returns the answer.
  - The Web search switch (`web` in the request): off when the page says nothing, passed on to the agent by both routes when it is true, never remembered by the server, and refused with 422 when it is not true or false.
- `test_auth.py` - login tokens, all offline (the keys are made inside the tests).
  - A good token (ES256 and RSA) is accepted, and every kind of token that must be refused is refused: expired, wrong audience or project, signed by another key, changed after signing, unsigned, signed with HS256 using the public key as the secret, anon and service roles, anonymous guests, junk.
  - How the public keys are kept: fetched once, refreshed when old, a new key picked up at most once a minute, junk cannot hammer Supabase, 503 and not 401 when Supabase is down, and a refused token never reaches the log.
  - The routes `GET /api/me` and `GET /api/config` (the secret key is never handed out).
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
