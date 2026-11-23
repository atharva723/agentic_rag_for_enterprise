# supabase/

The database side of accounts and saved chats. SQL only. The Python side is in `app/supabase/`.

- `schema.sql` - the two tables (`conversations` and `messages`), a small trigger that moves a chat to the top of the list when a message is saved, and the row-level security rules that keep each user's chats private. It is safe to run again.

## Set up (free)

1. Sign up at https://supabase.com and create a project. The free plan is enough. Pick the region nearest you. The database password is not used anywhere in this app.
2. Project Settings > API Keys: copy the Project URL, the publishable key (`sb_publishable_...`) and the secret key (`sb_secret_...`). Put them in `.env` as `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_SECRET_KEY`. Use `.env`, not `.env.example`. Never paste a key into a chat or commit it.
3. SQL Editor > New query: paste all of `schema.sql` and press Run. The result at the bottom shows both tables with `rls_on = true`.
4. Check it: `python -m app.supabase.check` (quick and read-only), then `python -m app.supabase.check --full` (makes two test users and deletes them again. It proves that sign-in works, that our server accepts real login tokens and refuses forged ones, that saved chats work through our own routes, and that one user cannot see or change another's chats. It spends no AI tokens).
5. The project must sign its login tokens with the new asymmetric keys (ES256 or RS256), which is the default for new projects. The quick check says so. If it complains, open Project Settings > JWT Keys and migrate.
6. Set the site address and the sign-up emails (next section). Until then, creating an account will not work.

## Set up sign-up emails

Email confirmation is on in a new project: a person who creates an account must open the link in an email before they can sign in. That needs two settings in the Supabase dashboard (they are not in this repo):

1. **Site URL and Redirect URLs** (Authentication > URL Configuration).
   - Site URL: `http://127.0.0.1:8000`. A new project says `http://localhost:3000`, where nothing runs.
   - Redirect URLs: add `http://127.0.0.1:8000/**` and `http://localhost:8000/**` (use your own port if it is not 8000). The confirmation link opens `login.html` on the address the person used to sign up, and Supabase only sends people to addresses on this list.
2. **Your own email service.** Supabase's built-in sender is only for testing: it mails nobody outside your Supabase team ("Email address not authorized"), at about 2 emails an hour. With Mailjet (free plan):
   1. In Mailjet: Account Settings > Senders & Domains > Add a domain or sender address > Add a sender address. Mailjet sends a link to that address: open it to confirm. This address is the "From" of every email.
   2. In Mailjet: Account Settings > API Key Management. Copy the API Key and the Secret Key. Use these, not your Mailjet login password.
   3. In Supabase: Authentication > SMTP (`https://supabase.com/dashboard/project/_/auth/smtp`). Turn on custom SMTP and fill in: Sender email = the address from step 1, Sender name = `Agentic RAG`, Host = `in-v3.mailjet.com`, Port = `587`, Username = the Mailjet API Key, Password = the Mailjet Secret Key. Save.
   4. Supabase now allows 30 emails an hour. Raise it under Authentication > Rate Limits if you need more.
   5. Try it: create an account in the app with an address you can read, then open the link in the email.

The Mailjet keys live only in the Supabase dashboard, never in `.env` or in this repo. Mailjet uses one key pair for both email and its own API, so treat the Secret Key like a password.

The checks and the tests never send an email: `--full` makes its test users through the admin API, already confirmed.

## How the server knows who you are

1. The login page (`ui/login.html`) signs the user in with Supabase, through the official library kept in `ui/vendor/`, and gets a login token. It lasts about an hour, and the library renews it by itself. `ui/auth.js` is the only file in the browser that talks to Supabase Auth. If a person follows the link in a confirmation email, the login page reads the token from the link and opens the chat.
2. The page sends it with every request: `Authorization: Bearer <login token>`.
3. Our server checks it itself, with Supabase's public keys, without calling Supabase. The checks are the signature, that it was issued by our project, that it is for a signed-in user, and that it has not expired. A forged or damaged token gets 401.
4. A route that needs a sign-in adds `user: User = Depends(current_user)` (see `app/api/account.py`). `GET /api/me` is the simplest one: it returns the user's id and email.
5. When our server talks to the database for a user, it passes that user's token on, so the database applies that user's privacy rules. The server never uses the secret key for this.

`GET /api/config` gives the sign-in page the project address and the publishable key, so they live only in `.env`. It refuses to answer (503) if a secret key was pasted into `SUPABASE_PUBLISHABLE_KEY`, so a secret key is never handed to a visitor. If Supabase is not set up it answers `{"supabase": null}`, and the chat page says "Accounts are not set up" (the landing, Vault and Settings pages still work).

Limits to know:
- A login token cannot be called back. After sign-out, or after an account is deleted, it still passes our server's check until it expires (up to an hour). The database rules still hold: a deleted account has no data.
- When Supabase rotates its signing keys, a token signed with the new key can be refused for up to a minute, until our server looks at the key list again.
- Anonymous guests (Supabase's "anonymous sign-ins") are refused on purpose, so that per-user limits cannot be dodged by signing in again and again.
- The login is kept in the browser's local storage, which is the library's default. The pages only ever add text with `textContent`, never `innerHTML`, so text from an answer or from the web cannot run as script.
- Signing out in the chat page ends the login in that browser only. Other browsers stay signed in until their login runs out.

## How a saved chat works

1. The page creates a chat (`POST /api/conversations`) and asks in it (`POST /api/conversations/{id}/messages`). The routes are listed in `app/api/README.md`.
2. The server loads the chat's last few messages from the database, so a follow-up such as "what if it keeps dropping?" makes sense. The page never sends the history, so nobody can invent one. Because it lives in the database, it survives a new sign-in, another browser and a server restart. Each chat has its own history: a new chat starts blank.
3. The agent answers (see `app/agent/README.md`). The question and the answer are then saved together in one request, and the first question names the chat.
4. Every database call is made as the signed-in user, so the privacy rules apply to each one. Whether a chat is yours is checked before the agent runs, so someone else's chat costs no AI tokens.

Good to know:
- If the earlier messages cannot be loaded (a Supabase problem), the question is still answered, on its own, with a warning. If the answer cannot be saved, it is still returned, with a warning, but it is not in the chat history.
- A question is saved only after it was answered. If the page gives up waiting and asks again, the first answer may have been saved after all, so the chat can hold the question twice. Reload the page to see what was saved.
- The login token is checked when a request arrives. If it runs out while the agent is still working (rare), the answer is shown but not saved.
- Reading a chat returns its newest 200 messages (500 at most), oldest first.
- The staff audit log is still a local SQLite file (`data/audit.db`), not part of Supabase. It records the user id and the chat id of every question asked in a saved chat.

## How the privacy rules work

- Every chat and message has an owner (`user_id`). The database fills it in from the login token, so nobody can set it to someone else.
- Row-level security (RLS) is on for both tables. A signed-in user can read and change only their own rows. Someone who is not signed in gets no access at all.
- A saved message is never edited or deleted on its own. Deleting a chat deletes its messages, and deleting a user deletes their chats.
- The publishable key is safe to show in a browser, because these rules live in the database and not in our server. The secret key skips them, so only the `--full` check uses it. The running app never does.
- A signed-in user can call the database directly with their own token, so they can write their own messages in any words they like. They can never reach anyone else's.

## Good to know

- Email confirmation is on in a new project, and the built-in email sender is for testing only. See "Set up sign-up emails" above. For a quick demo with a few accounts you can also create users yourself in the dashboard (Authentication > Users), or switch confirmation off in the Authentication settings.
- Free plan: 500 MB of database, and a project that nobody uses for a week is paused. Open the dashboard to wake it.
- To change the tables or rules later, edit `schema.sql` (keep it safe to run again) and run it again in the SQL Editor.
