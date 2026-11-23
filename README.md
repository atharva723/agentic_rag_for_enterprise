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

**Follow-ups.** The agent keeps nothing between questions. For a saved chat, the server loads the chat's last few question-and-answer pairs from the database and hands them to the agent with the new question (`MEMORY_TURNS`, 3 by default). The router uses them only to restate a follow-up as a complete question ("what if it keeps dropping?" becomes "what should I do if the VPN keeps dropping?"), and every later step works on that. Evidence is always searched fresh.

## Project map

- `app/` - all Python code. Start reading at `app/agent/graph.py`.
- `supabase/` - the database side of accounts and saved chats (SQL only): the two tables and the rules that keep each user's chats private. People sign in with email and password, and their chats are saved on the server, one list per user. Set-up steps are in `supabase/README.md`.
- `ui/` - the web pages (plain HTML, CSS and JavaScript, no build step): a landing page, the login page, the chat (a list of your saved chats), the Knowledge Vault (staff uploads) and Settings (staff key, service status, recent questions).
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
8. Set up accounts (free): make a Supabase project, run `supabase/schema.sql`, put the keys in `.env`, and set the site address and the email service, all in `supabase/README.md`. Then `python -m app.supabase.check --full` proves it works (no AI tokens spent). The chat needs a sign-in, so without this step it says "Accounts are not set up".
9. `uvicorn app.main:app --reload`, then open http://127.0.0.1:8000. That is the landing page: click **Open the Chat**, create an account (or sign in), and ask a question. The server is ready at once and loads the embedding model in the background, so a question asked in the first half minute may wait a little.
10. Staff tools: the **Knowledge Vault** page (`/vault.html`, upload documents) and the **Settings** page (`/settings.html`, check the key and see the recent questions) stay locked until you set `ADMIN_API_KEY` in `.env`. Make a key with `python -c "import secrets; print(secrets.token_urlsafe(32))"`, paste it in `.env`, restart the app, then paste the same key on either page. Employees never need it, and staff pages do not need a sign-in.
11. `pytest` (uses no keys and no tokens)
12. Optional, with the real services: `python -m tests.run_eval` asks a sample of 10 questions and reports the path, the sources and the tokens used (about 30,000 Groq tokens, roughly 8% of one day's free budget). `python -m tests.run_eval --followups` does the same for 11 follow-up questions that come with the earlier messages of their chat (about 35,000 tokens).

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
- The Vault or Settings page says "switched off": `ADMIN_API_KEY` is empty in `.env`. Set it (step 10 above) and restart the app.
- The chat says "Accounts are not set up": the Supabase keys are missing in `.env`, or `SUPABASE_PUBLISHABLE_KEY` holds a secret key. Follow `supabase/README.md`, then restart the app.
- Sign-up says "Emails can only go to the project's team members" or "Too many emails were sent": Supabase's built-in email sender is only for testing. Add your own email service (Mailjet steps in `supabase/README.md`), or make the users yourself in the Supabase dashboard under Authentication > Users.
- The link in the confirmation email opens a page that does not exist (`localhost:3000`): set the Site URL and Redirect URLs in Supabase (see `supabase/README.md`).
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
- how a login token is checked: `app/supabase/auth.py`. To make a route need a sign-in, add `user: User = Depends(current_user)` (from `app/api/account.py`)
- how saved chats work: the database calls are in `app/supabase/conversations.py`, the routes in `app/api/conversations.py`
- how the browser signs in: `ui/auth.js` is the only file that talks to Supabase Auth. The login page is `ui/login.html` + `ui/login.js`, and the chat page shows its list of chats from `ui/app.js`

## Status

All the MVP parts work: settings, the knowledge base (`app/rag/`), web search (`app/tools/`), the agent (`app/agent/`), the API, the audit log (SQLite, with a viewer on the Settings page), the web pages and the tests. `pytest` passes without any key. `python -m tests.run_eval` checks the real thing.

Known limits:
- A question that needs facts from three different documents may only get part of them. The agent then says so, or falls back and says what it could not confirm.
- Web answers are only as good as what the search finds, and the results change from day to day. The search cannot show live status, only what pages said when they were saved. For a "now" or "latest" question, the answer gets a "Heads up" line if even the newest page is more than a week old.
- No checker can tell look-alike names apart (a test accepted a page about "NovaERA" for "NovaERP"). That is why the router keeps passwords, tickets, people, stores and equipment questions away from the web. This guard is a model's judgement, not a guarantee: keep the answer prompt's rule that credentials are never written out.
- The free Groq plan allows about 3,000 tokens per question from the knowledge base and 4,000 to 5,000 with web search, so roughly 60 to 90 questions a day (each model has its own 200,000-token daily limit).
- The chat page shows plain text. People sign in with a Supabase account (email and password; a forgot-password link is not built yet). Staff use one shared admin key, which travels in a header, so put the app behind HTTPS before real use.
- Chats are saved on the server, one list per user, so they follow a person to another browser or computer. Chats made in a browser before accounts existed stay in that browser, are not shown, and can be removed on the Settings page. The Vault's upload list is still saved in each browser only. The server has no "list documents" or "delete document" call yet: the Vault list is that browser's own upload history, and its Remove button only edits the list. It never deletes anything from the knowledge base.
- Follow-ups work because the server loads the chat's earlier questions and answers from the database with each new question, so they survive a new sign-in, another browser and a restart. The agent reads only the last `MEMORY_TURNS` of them, cut short. A new chat starts fresh. A follow-up that changes topic is searched as a new question.
- The pages load fonts and icons from Google Fonts. On a network that blocks it, icons show as words and the look is plainer. Everything still works.
- Every question needs a sign-in, but sign-ups are open and each question spends free Groq tokens. There is no per-user rate limit yet (it is planned next). Add the limit, and keep the app inside the company network, before a production rollout.
- The audit log keeps every question as typed, with no clean-up. For a question asked in a saved chat it also records who asked (the user id) and in which chat. Treat it as private, and trim it from time to time.
