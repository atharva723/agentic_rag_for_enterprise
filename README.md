# IT Support Agentic RAG Copilot

An IT help assistant for employees. It answers from the company's private knowledge base first. It checks whether that evidence is good enough, and uses web search only when it is not. Every answer shows the path it took.

Built with LangGraph, FastAPI, Pinecone, Groq and Tavily.

## How one question flows

```
Question
  -> Router: IT question, or just chat? (chat -> direct answer)
     It also cleans the question into a search query, adds a second search when
     the question has two parts, and decides if public web pages could answer it at all.
  -> Search the private KB (Pinecone)
  -> Grade the evidence
       good -> answer from the KB
       weak -> public web pages could help?
                 yes -> search the web (Tavily) -> grade again
                          good -> answer from the web (with a notice that it is not from company documents)
                          weak -> rewrite the question once and try the KB again
                 no  -> (passwords, tickets, people, equipment: the web is never searched)
                        rewrite the question once and try the KB again
               still weak -> fallback answer that says what it could not confirm
```

**Follow-ups.** Each chat sends its last few question-and-answer pairs with a new question (`MEMORY_TURNS`, 3 by default). The router uses them only to restate a follow-up as a complete question ("what if it keeps dropping?" becomes "what should I do if the VPN keeps dropping?"), and every later step works on that. Evidence is always searched fresh, and the server stores nothing between questions.

## Project map

- `app/` - all Python code. Start reading at `app/agent/graph.py`.
- `supabase/` - the database side of accounts and saved chats (SQL only). Being added in steps: the tables and their privacy rules are ready, sign-in and saved chats come next. Set-up steps are in `supabase/README.md`.
- `ui/` - the web pages (plain HTML, CSS and JavaScript, no build step): a landing page, the chat, the Knowledge Vault (staff uploads) and Settings (staff key, service status, recent questions).
- `data/` - the knowledge base documents (`data/kb/`). Uploads and the audit log appear here when the app runs.
- `tests/` - tests. They need no API keys.
- `BRD/` - the customer's problem statement (PDF), the architecture picture and the prototype notebook.
- `docs/` - our own notes: the prompts that made the knowledge base.
- `notebooks/` - empty for now: a place for experiments.
- Root files: `requirements.txt`, `.env.example`, `Dockerfile`, `pytest.ini`.

Every folder has its own short README.

## Run it

You need Python 3.11 or newer (tested on 3.11).

1. Make an isolated environment that has its own Python: `python -m venv .venv`, then activate it. Using conda instead? See the box below.
2. `pip install -r requirements.txt` (the first install is big: it includes PyTorch for the embedding model).
3. Copy `.env.example` to `.env` and add your keys there. The app reads only `.env`. Never put real keys in `.env.example`.
4. Make a free Pinecone account and key (steps in `app/rag/README.md`), then load the knowledge base: `python -m app.rag.ingest`
5. Check it: `python -m app.rag.store "How do I connect to the VPN from home?"`
6. Check web search (uses 1 free Tavily credit): `python -m app.tools.web_search "latest Microsoft Teams outage"`
7. Make a free Groq key at https://console.groq.com and put it in `.env` as `GROQ_API_KEY=...`
8. `uvicorn app.main:app --reload`, then open http://127.0.0.1:8000. That is the landing page: click **Open the Chat** and ask a question. The server is ready at once and loads the embedding model in the background, so a question asked in the first half minute may wait a little.
9. Staff tools: the **Knowledge Vault** page (`/vault.html`, upload documents) and the **Settings** page (`/settings.html`, check the key and see the recent questions) stay locked until you set `ADMIN_API_KEY` in `.env`. Make a key with `python -c "import secrets; print(secrets.token_urlsafe(32))"`, paste it in `.env`, restart the app, then paste the same key on either page. Employees never need it.
10. `pytest` (uses no keys and no tokens)
11. Optional, with the real services: `python -m tests.run_eval` asks a sample of 10 questions and reports the path, the sources and the tokens used (about 30,000 Groq tokens, roughly 8% of one day's free budget). `python -m tests.run_eval --followups` does the same for 11 follow-up questions that come with the earlier messages of their chat (about 35,000 tokens).

**Using conda?** Create the env with Python in it, and switch off the shared "user" packages (a conda env still sees the ones in `AppData\Roaming\Python`, and they win over the env's own):

```
conda create -n agentic-rag python=3.11 -y
conda activate agentic-rag
conda env config vars set PYTHONNOUSERSITE=1
conda deactivate
conda activate agentic-rag
python -c "import sys; print(sys.executable)"
```

The last line must print a path inside the env (`...\envs\agentic-rag\python.exe`). Then do step 2 onward.

**Using Docker (optional)?** Load the knowledge base once (step 4), then:

```
docker build -t it-support-copilot .
docker run --env-file .env -p 8000:8000 it-support-copilot
```

The keys come from `.env` at run time and are never copied into the image. The image uses CPU-only PyTorch. The model downloads on the first start. The audit log and uploads live inside the container, so they disappear when the container is removed: mount a volume on `/app/data` to keep them. This Dockerfile has not been test-built yet, so build it once before relying on it.

## Troubleshooting

- The page looks old or broken after an update: press Ctrl+F5 once. The server now tells browsers to re-check the page files, but a copy cached earlier can linger.
- The icons show as words (`add_circle`, `folder_open`) and the fonts look plain: the pages load their fonts and icons from Google Fonts, so the browser must be able to reach `fonts.googleapis.com`. Everything still works without it.
- The Vault or Settings page says "switched off": `ADMIN_API_KEY` is empty in `.env`. Set it (step 9 above) and restart the app.
- `data/audit.db` is missing: the file is created when the first question is asked, not when the app starts. It is a SQLite file, so it will not open as text. Read it on the Settings page, under Recent Questions.
- `PyTorch >= 2.6 is required but found 2.5.0`, then `NameError: name 'nn' is not defined`: the embedding library found an old PyTorch. Usually the environment is empty or shares packages with another project. Check which Python runs with `python -c "import sys; print(sys.executable)"` (it must be inside your env), then run `pip install -r requirements.txt` again.
- Chat says "The AI service is busy or its daily limit is used up": Groq's free limit was reached (8,000 tokens a minute and 200,000 a day, per model). Wait a minute for the per-minute limit. For the daily limit, wait until tomorrow, or point the busy model's setting (`GROQ_MODEL` or `GROQ_FAST_MODEL` in `.env`) at the other `openai/gpt-oss-*` model, which has its own budget. Only those two models give the strict JSON replies the decisions need. See `app/agent/README.md`.
- Every answer comes from the web, or says it could not confirm anything: the KB is empty or ingest and chat use different index names. Run `python -m app.rag.store` to see how many chunks are stored.

## Where do I change...?

- the flow or the retry rules: `app/agent/graph.py`
- what the LLM is told: `app/agent/prompts.py`
- what one step does: its file in `app/agent/nodes/`
- a new source (tickets, HR docs, SQL): add a file in `app/tools/`
- file types or chunking: `app/rag/ingest.py`
- which folder of documents to load: `kb_dir` in `app/config.py` (or pass a folder to the ingest command)
- a setting: `.env` (the full list is in `app/config.py`)
- how much of a chat a follow-up remembers: `MEMORY_TURNS` in `.env` (`0` answers every question on its own)
- the chat tables or their privacy rules: `supabase/schema.sql` (then run it again in the Supabase SQL Editor)

## Status

All the MVP parts work: settings, the knowledge base (`app/rag/`), web search (`app/tools/`), the agent (`app/agent/`), the API, the audit log (SQLite, with a viewer on the Settings page), the web pages and the tests. `pytest` passes without any key. `python -m tests.run_eval` checks the real thing.

Known limits:
- A question that needs facts from three different documents may only get part of them. The agent then says so, or falls back and says what it could not confirm.
- Web answers are only as good as what the search finds, and the results change from day to day. The search cannot show live status, only what pages said when they were saved. For a "now" or "latest" question, the answer gets a "Heads up" line if even the newest page is more than a week old.
- No checker can tell look-alike names apart (a test accepted a page about "NovaERA" for "NovaERP"). That is why the router keeps passwords, tickets, people, stores and equipment questions away from the web. This guard is a model's judgement, not a guarantee: keep the answer prompt's rule that credentials are never written out.
- The free Groq plan allows about 3,000 tokens per question from the knowledge base and 4,000 to 5,000 with web search, so roughly 60 to 90 questions a day (each model has its own 200,000-token daily limit).
- The chat page shows plain text. There are no logins: staff use one shared admin key, which travels in a header, so put the app behind HTTPS before real use.
- Chats and the Vault's upload list are saved in each browser only, so another browser or computer starts empty. The server has no "list documents" or "delete document" call yet: the Vault list is that browser's own upload history, and its Remove button only edits the list. It never deletes anything from the knowledge base.
- Follow-ups work because the chat page sends the last few earlier questions and answers of that chat with each new question. The server keeps nothing, so a chat cleared from the browser is forgotten, and a new chat always starts fresh. The agent reads only the last `MEMORY_TURNS` of them, cut short. A follow-up that changes topic is searched as a new question.
- The pages load fonts and icons from Google Fonts. On a network that blocks it, icons show as words and the look is plainer. Everything still works.
- Anyone who can reach the app can ask questions, and each question spends free Groq tokens. There is no rate limit. Keep it inside the company network, or add a limit, before a production rollout.
- The audit log keeps every question as typed, with no clean-up. Treat it as private, and trim it from time to time.
