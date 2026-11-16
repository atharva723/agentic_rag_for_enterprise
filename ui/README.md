# ui/

The chat page. Plain HTML, CSS and JavaScript. No build step. FastAPI serves this folder at `/`, and tells the browser to re-check the files each time, so an update shows up at once.

- `index.html` - the page: question box with example questions, the answer with its "Answered from" label, the sources, the decision path, and the Staff Tools.
- `style.css` - how it looks. Works on phones too.
- `app.js` - calls `/api/chat`, `/api/ingest` and `/api/audit` and shows the results.

What the page does:

- While a question runs, the Ask button ignores clicks (so one question is never sent twice) and a screen reader hears "Thinking…" and then which source answered.
- Web sources are links. Company documents show their title and file name.
- **Staff Tools** (closed by default) needs the admin key. It uploads a document and shows the last 20 questions with their decision paths. If `ADMIN_API_KEY` is not set on the server, it says the tools are switched off.
- Text from answers, sources and the audit log is added with `textContent`, never `innerHTML`, so web text cannot inject HTML.
