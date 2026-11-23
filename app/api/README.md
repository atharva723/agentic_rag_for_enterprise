# api/

The web door. It checks the input, calls the right code, and returns JSON. Almost no logic here: the one exception is the send-message route of saved chats, which ties the agent, the audit log and the saved chat together in a few lines.

- `chat.py` - `GET /api/health` (no sign-in needed) and `run_agent()`, which runs the agent and turns the AI provider's rate limit into a plain 429 "busy" answer. The saved-chat routes use it. There is no open `POST /api/chat` any more: it took questions from anyone, without a sign-in, and spent AI tokens on them. Every question now goes through a saved chat of a signed-in user.
- `account.py` - accounts. `current_user` is the dependency that makes a route need a sign-in: add `user: User = Depends(current_user)` to the route. It reads `Authorization: Bearer <login token>` and answers 401 (no valid token: sign in, or sign in again) or 503 (the check cannot be done right now). `GET /api/me` returns the signed-in user's `id` and `email`. `GET /api/config` returns what the sign-in page needs, `{"supabase": {"url": ..., "publishable_key": ...}}`, or `{"supabase": null}` when accounts are switched off. It never returns the secret key. See `supabase/README.md`.
- `conversations.py` - saved chats of a signed-in user. Every route needs a sign-in. A chat that is not yours looks exactly like a chat that does not exist (404).
  - `GET /api/conversations?limit=50` - your chats, the most recently used first: `[{"id", "title", "created_at", "updated_at"}]`.
  - `POST /api/conversations` - a new chat. The body `{"title": "..."}` is optional. Answers 201 with the chat.
  - `PATCH /api/conversations/{id}` with `{"title": "..."}` - rename. `DELETE /api/conversations/{id}` - delete the chat and its messages (204).
  - `GET /api/conversations/{id}/messages?limit=200` - the newest `limit` messages, oldest first: `[{"id", "role", "content", "source_used", "citations", "trace", "latency_ms", "created_at"}]`. A new chat answers `[]`.
  - `POST /api/conversations/{id}/messages` with `{"question": "..."}` - ask in this chat. The server loads the chat's earlier messages from the database (a `history` in the request is ignored), the agent answers, and the question and answer are saved together. The answer is `{"answer", "source_used", "citations", "trace", "saved", "title", "warnings"}`. `title` is the chat's title after this message: the first question names a chat that still has the default title, and a title you chose is never replaced.
  - If the chat's earlier messages cannot be loaded, the question is still answered, on its own, with a warning in `warnings`. If the answer cannot be saved, it is still returned, with `saved: false` and a warning. Whether the chat is yours is checked before the agent runs, so a chat that is not yours costs no AI tokens.
  - 401 = no valid login (sign in again). 429 = the AI service is busy. 503 = Supabase cannot be reached, try again.
- `admin.py` - for staff. Needs the `X-Admin-Key` header: `POST /api/ingest` (upload a document) and `GET /api/audit` (recent questions, now with the `user_id` and `conversation_id` of questions asked in a saved chat). The Knowledge Vault and Settings pages use these two.

If `ADMIN_API_KEY` is empty, the staff endpoints are off: they answer 403 "Staff tools are switched off…" to everyone. With a key set, a wrong or missing key gets 401.
