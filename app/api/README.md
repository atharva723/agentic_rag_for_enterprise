# api/

The web door. It checks the input, calls the right code, and returns JSON. No business logic here.

- `chat.py` - for employees: `GET /api/health` and `POST /api/chat`.
- `admin.py` - for staff. Needs the `X-Admin-Key` header: `POST /api/ingest` (upload a document) and `GET /api/audit` (recent questions).

If `ADMIN_API_KEY` is empty, the staff endpoints are off.
