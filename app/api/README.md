# api/

The web door. It checks the input, calls the right code, and returns JSON. No business logic here.

- `chat.py` - for employees: `GET /api/health` and `POST /api/chat`.
- `admin.py` - for staff. Needs the `X-Admin-Key` header: `POST /api/ingest` (upload a document) and `GET /api/audit` (recent questions). The Knowledge Vault and Settings pages use these two.

If `ADMIN_API_KEY` is empty, the staff endpoints are off: they answer 403 "Staff tools are switched off…" to everyone. With a key set, a wrong or missing key gets 401.
