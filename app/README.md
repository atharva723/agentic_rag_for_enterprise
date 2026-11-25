# app/

All the Python code. Each sub-folder has one job.

- [`agent/`](agent/README.md) - the brain. Decides what to do next for each question.
- [`rag/`](rag/README.md) - the knowledge base. Puts documents in and searches them.
- [`tools/`](tools/README.md) - things the agent can use besides the knowledge base (web search).
- [`supabase/`](supabase/README.md) - accounts and saved chats (Supabase). Nothing else in the app talks to Supabase directly.
- [`api/`](api/README.md) - the web endpoints. No logic, it just hands work to the others.

Files here:

- `main.py` - starts the web app. Serves the API and the web pages (each page file with the security headers), trims the audit log, and warms up the knowledge base in the background. When the server stops, it first waits (up to 30 seconds) for answers that are still being made.
- `config.py` - reads every setting from `.env`.
- `audit.py` - saves each question and its decision path to a small SQLite file, and (for a question asked in a saved chat) who asked and in which chat. Rows older than `AUDIT_RETENTION_DAYS` (90) are deleted at start-up and whenever a question is saved.
- `ratelimit.py` - the per-person rate limiter: sliding windows kept in memory, no extra service. It knows nothing about the web. `api/limits.py` joins it to the routes.
- `headers.py` - the security headers for the pages, mainly the Content-Security-Policy: what a page may load and run.

One rule: calls only go downhill. `api` can call `agent`, `rag` and `supabase`. `agent` can call `rag` and `tools`. Nothing calls back up (the one exception is `supabase/check.py`, a command-line check that runs our own routes to prove they work).
