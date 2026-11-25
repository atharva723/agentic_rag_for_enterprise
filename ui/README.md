# ui/

The web pages. Plain HTML, CSS and JavaScript. No build step. FastAPI serves this folder at `/`, and tells the browser to re-check the files each time, so an update shows up at once. The look is the "neo-arcade" design: warm cream surfaces, black outlines, hard offset shadows, and the Space Grotesk, Plus Jakarta Sans and Space Mono fonts (loaded from Google Fonts, as are the Material Symbols icons).

- `index.html` + `landing.css` + `landing.js` + `flow.js` - the landing page at `/`: a retro collage on blue felt, with torn-paper section edges and floating stickers. The textures and torn edges are drawn in code (SVG filters at the top of `index.html`), so no texture images are needed.
  - It opens with a headline, one "Open the Chat" button and a small retro window that types an example question and shows how it is answered. It cycles through three example paths (company documents, web search, fallback). These are fixed example texts, not live calls.
  - Below that it explains the agent flow, the knowledge base and the safety rules, with a "Decision Path Viewer" (▲ ▼) you can step through yourself.
  - The only link to the vault (staff tools) is a small, quiet "IT staff: manage documents" link in the footer.
- `flow.js` draws the "How a question travels" window in the knowledge-base section: an animated map of the agent's real graph (`app/agent/graph.py`) with four routes to pick from (company answer, web fallback, not confirmed, just chat).
  - A glowing packet follows the route, nodes light up as it arrives, the grader shows a GOOD or WEAK verdict, and a caption names the function and the model (fast, answer, or none) used at each step.
  - The route texts are written by hand from what the graph does, so if `graph.py` changes, update the routes in `flow.js` too.
  - It uses no library, pauses when the section is off screen or the tab is hidden, and with "reduce motion" switched on it shows the whole route lit at once with every step written out.
- `chat.html` + `app.js` - the chat workspace: a sidebar of your saved chats (with your email and **Sign out** at the bottom), a "new chat" view with suggested questions, and an active thread with the answer, its source cards and a one-line summary of the steps the agent took. **Rename** and **Delete** are the two buttons in the open chat's header. Nothing shows until the sign-in is checked: a signed-out visitor is sent to the login page, and if accounts are not set up the page says so.
- `login.html` + `login.js` - the login page: **Sign In** and **Create Account** on one card. When email confirmation is on, creating an account says "check your email" and offers to send the email again. The link in that email opens this page, which signs the person in and opens the chat.
- `auth.js` - the only file that talks to Supabase Auth. It asks `/api/config` which project to use, keeps the login, gives `common.js` the token for each `/api/` call, and turns the service's errors into plain sentences. Only the chat and login pages load it. The Vault and Settings pages use the admin key and need no sign-in.
- `vendor/` - the official Supabase browser library, unmodified, with its version, source and hash in `vendor/README.md`.
- `vault.html` + `vault.js` - the Knowledge Vault: drag and drop upload, a progress strip, and a searchable, filterable list of what was uploaded from this browser.
- `settings.html` + `settings.js` - the staff key, a live service check, the recent-questions log, and a button that clears old chats left in this browser from before accounts.
- `common.js` - helpers used by all the pages (server calls, admin key, saved lists). On a page that loads `auth.js`, every call to `/api/...` carries the person's token.
  - `call()` is for an ordinary reply.
  - `stream()` is for a reply that arrives as server-sent events: it hands each `step` event to the page the moment it arrives and returns the final `answer` or `error` in the same `{ok, status, body}` shape as `call()`. Its small event reader copes with text that is cut anywhere (even in the middle of a character), CRLF line endings and keep-alive comments.
  - All the scripts of one page share one global space, so a new helper must not reuse a name another script of that page already declares (`pytest` checks this).
- `style.css` - the design for the chat, login, vault and settings pages (the landing page has its own `landing.css`). Works on phones too.
- `assets/` - the sticker images.

What the pages do:

- **Chat** uses the saved-chat routes under `/api/conversations`.
  - While a question runs, the send buttons ignore clicks (so one question is never sent twice), and a screen reader hears the step that is running, then which source answered.
  - The steps show live: each finished step appears as a ticked line ("Router → KB (search: vpn)"), and the step running now shows its plain-words status with a pulsing dot ("Searching the company documents…", then "Not enough in the company documents, searching the public web…").
  - When the answer arrives, the steps fold into one quiet line above it ("Searched company documents · 4 steps · 6.3s ›"). Click it, or press Enter or Space on it, to open the list. The line says "Searched company documents", "Searched company documents, then the web", "Searched, but could not confirm" or "Replied without searching". An older chat shows the same line from its saved decision path and time.
  - If the question fails part-way, the line says "Stopped after N steps" and the steps that did run are listed. If the person is over their question limit, the answer card shows the server's plain message ("You are asking too fast. The limit is 5 questions a minute. Please wait 29 seconds and ask again."), and nothing is saved.
  - The "Decision Path" chip hides these lines: it hides the finished steps while a question runs (the running step stays) and the summary line after it.
  - Web sources are links. Company documents show their title and file name.
- **Saved chats** live on the server for the signed-in person, so they follow them to any browser.
  - The list comes from `GET /api/conversations`, a chat's messages are fetched when it is opened, and a question goes to `POST /api/conversations/{id}/messages/stream` (the live version of `.../messages`, see `app/api/README.md`).
  - The page sends only the question: the server loads the chat's earlier messages itself, so a follow-up works and nobody can invent a history. The first question of a new chat creates the chat, and the server names it.
  - If an answer could not be saved, its card says so. If the connection drops while an answer is being made, the server still finishes and saves it, but the page says no reply came back: reload the chat to see the answer (pressing Try again would ask a second time).
  - Rename and Delete (which asks first) work on the open chat. A chat deleted on another device is dropped from the list the next time it is used.
- A login the server refuses (401) signs the person out of this browser and opens the login page with "Your sign-in ended". Chats made in this browser before accounts existed are not shown. Settings can remove them.
- The vault uploads through `/api/ingest` and needs the admin key. The key is kept in this tab's session storage only. The server has no "list documents" endpoint, so the list is this browser's own upload history, and "Remove" only edits that list: it never deletes anything from the knowledge base.
- Settings reads `/api/health` and `/api/audit`. If `ADMIN_API_KEY` is not set on the server, it says the staff tools are switched off.
- Text from answers, sources, chat titles and the audit log is added with `textContent`, never `innerHTML`, so web text cannot inject HTML.
- The server sends a Content-Security-Policy with every page file (`app/headers.py`). The pages may run only scripts from their own files, and may talk only to the server and the Supabase project. So there are no inline scripts, `onclick=` handlers or `<style>` blocks in these pages, and a new script, font or image must come from `ui/` (or Google Fonts). Inline `style="..."` attributes are allowed. `tests/test_api.py` checks all of this, so a change the browser would block fails `pytest` first.
