# supabase/ (inside app/)

All the Python code that talks to Supabase lives here, so the rest of the app never needs to know how it works. The database side (the SQL) is in `supabase/` at the project root.

- `client.py` - `request()`: the one place that calls Supabase over HTTP and builds the headers. A call is made as nobody (the publishable key only) or as a signed-in user (the publishable key plus that user's login token, so the database's privacy rules apply). The running app never uses the secret key. If Supabase is not set up or cannot be reached, it raises `SupabaseError` with a plain message that never holds a key. `key_kind()` tells a publishable key from a secret key without ever showing it.
- `auth.py` - `verify_token()`: who is calling? It checks a user's login token on our own server, using Supabase's public keys (kept in memory, fetched again about every 10 minutes), so there is no call to Supabase per request. A token is refused if it is expired, signed by anyone else, meant for another project or audience, unsigned, or from an anonymous guest or the `anon` / `service_role` role. It returns a `User` (`id`, `email` and the token itself, which later steps pass to Supabase so the database applies that user's rules). `AuthError` carries the plain message and the status: 401 sign in again, 503 cannot check right now.
- `check.py` - `python -m app.supabase.check`: is the project set up right? It checks the settings, that the project answers, that login tokens use a public key we accept, and that both tables exist and are closed to anyone not signed in. With `--full` it also makes two test users and proves, with their real login tokens, that our server accepts the real tokens and refuses forged ones, that `/api/me` and `/api/config` answer correctly, and that one user cannot see or change the other's chats. Then it deletes both users again. It is not part of `pytest` and never prints a key or a token.

The web routes that use `auth.py` are in `app/api/account.py`. Next steps will add `conversations.py` (list, create, rename and delete chats, and save messages).

## How the key list is kept

- It is fetched the first time a token arrives, kept in memory, and fetched again after 10 minutes.
- A token that names a key we do not know (Supabase may have rotated its keys) makes us look again, but never more than once a minute. Junk tokens cannot make us hammer Supabase.
- If Supabase cannot be reached, keys already loaded keep working. If none were ever loaded, the answer is 503, not 401, so a user is not told to sign in again because of a Supabase outage.
- Only ES256 and RS256 are accepted. If the project still uses the old shared secret, switch it to the new signing keys (Project Settings > JWT Keys). `python -m app.supabase.check` says so.
