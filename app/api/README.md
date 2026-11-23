# api/

The web door. It checks the input, calls the right code, and returns JSON. No business logic here.

- `chat.py` - for employees: `GET /api/health` and `POST /api/chat`. A chat message is `{"question": ..., "history": [{"question": ..., "answer": ...}]}`. `history` is optional: the earlier exchanges of the same chat, oldest first (at most 20 accepted; the agent reads only the last few). The chat does not need a sign-in yet.
- `account.py` - accounts. `current_user` is the dependency that makes a route need a sign-in: add `user: User = Depends(current_user)` to the route. It reads `Authorization: Bearer <login token>` and answers 401 (no valid token: sign in, or sign in again) or 503 (the check cannot be done right now). `GET /api/me` returns the signed-in user's `id` and `email`. `GET /api/config` returns what the sign-in page needs, `{"supabase": {"url": ..., "publishable_key": ...}}`, or `{"supabase": null}` when accounts are switched off. It never returns the secret key. See `supabase/README.md`.
- `admin.py` - for staff. Needs the `X-Admin-Key` header: `POST /api/ingest` (upload a document) and `GET /api/audit` (recent questions). The Knowledge Vault and Settings pages use these two.

If `ADMIN_API_KEY` is empty, the staff endpoints are off: they answer 403 "Staff tools are switched off…" to everyone. With a key set, a wrong or missing key gets 401.
