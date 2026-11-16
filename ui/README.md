# ui/

The chat page. Plain HTML, CSS and JavaScript. No build step. FastAPI serves this folder at `/`.

- `index.html` - the page: question box, answer, sources, decision path, and staff upload.
- `style.css` - how it looks.
- `app.js` - calls `/api/chat` and `/api/ingest` and shows the results.
