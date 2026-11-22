# supabase/ (inside app/)

All the Python code that talks to Supabase lives here, so the rest of the app never needs to know how it works. The database side (the SQL) is in `supabase/` at the project root.

- `client.py` - `request()`: the one place that calls Supabase over HTTP and builds the headers. A call is made as nobody (the publishable key only) or as a signed-in user (the publishable key plus that user's login token, so the database's privacy rules apply). The running app never uses the secret key. If Supabase is not set up or cannot be reached, it raises `SupabaseError` with a plain message that never holds a key.
- `check.py` - `python -m app.supabase.check`: is the project set up right? It checks the settings, that the project answers, that login tokens use a public key, and that both tables exist and are closed to anyone not signed in. With `--isolation` it also makes two test users, proves that one cannot see or change the other's chats, and deletes them again. It is not part of `pytest` and never prints a key.

Next steps will add `auth.py` (check a login token) and `conversations.py` (list, create, rename and delete chats, and save messages).
