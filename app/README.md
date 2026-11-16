# app/

All the Python code. Each sub-folder has one job.

- `agent/` - the brain. Decides what to do next for each question.
- `rag/` - the knowledge base. Puts documents in and searches them.
- `tools/` - things the agent can use besides the knowledge base (web search).
- `api/` - the web endpoints. No logic, it just hands work to the others.

Files here:

- `main.py` - starts the web app. Serves the API and the chat page, and warms up the knowledge base in the background.
- `config.py` - reads every setting from `.env`.
- `audit.py` - saves each question and its decision path to a small SQLite file.

One rule: calls only go downhill. `api` can call `agent` and `rag`. `agent` can call `rag` and `tools`. Nothing calls back up.
