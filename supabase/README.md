# supabase/

The database side of accounts and saved chats. SQL only. The Python side is in `app/supabase/`.

- `schema.sql` - the two tables (`conversations` and `messages`), a small trigger that moves a chat to the top of the list when a message is saved, and the row-level security rules that keep each user's chats private. It is safe to run again.

## Set up (free)

1. Sign up at https://supabase.com and create a project. The free plan is enough. Pick the region nearest you. The database password is not used anywhere in this app.
2. Project Settings > API Keys: copy the Project URL, the publishable key (`sb_publishable_...`) and the secret key (`sb_secret_...`). Put them in `.env` as `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_SECRET_KEY`. Use `.env`, not `.env.example`. Never paste a key into a chat or commit it.
3. SQL Editor > New query: paste all of `schema.sql` and press Run. The result at the bottom shows both tables with `rls_on = true`.
4. Check it: `python -m app.supabase.check` (quick and read-only), then `python -m app.supabase.check --isolation` (proves that one user cannot see or change another's chats: it makes two test users and deletes them again).

## How the privacy rules work

- Every chat and message has an owner (`user_id`). The database fills it in from the login token, so nobody can set it to someone else.
- Row-level security (RLS) is on for both tables. A signed-in user can read and change only their own rows. Someone who is not signed in gets no access at all.
- A saved message is never edited or deleted on its own. Deleting a chat deletes its messages, and deleting a user deletes their chats.
- The publishable key is safe to show in a browser, because these rules live in the database and not in our server. The secret key skips them, so only the isolation check uses it. The running app never does.
- A signed-in user can call the database directly with their own token, so they can write their own messages in any words they like. They can never reach anyone else's.

## Good to know

- Email confirmation is on in a new project. Supabase's built-in email sender is for testing: it only mails people in your Supabase team, about 2 emails an hour. For a demo with several accounts, either switch confirmation off in the Authentication settings, or add your own email service (SMTP).
- Free plan: 500 MB of database, and a project that nobody uses for a week is paused. Open the dashboard to wake it.
- To change the tables or rules later, edit `schema.sql` (keep it safe to run again) and run it again in the SQL Editor.
