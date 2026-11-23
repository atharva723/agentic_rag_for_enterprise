-- NovaRetail IT Support Copilot: the chat tables, and the rules that keep each user's chats private.
--
-- How to use: Supabase dashboard > SQL Editor > New query > paste this whole file > Run.
-- The last line shows both tables with rls_on = true. It is safe to run again: it only creates what is
-- missing and replaces its own rules. Then, from the project folder:  python -m app.supabase.check --full
--
-- Who is who in the database:
--   anon           = nobody signed in (the publishable key alone)      -> no access at all
--   authenticated  = a signed-in user (publishable key + their token)  -> sees and changes only their own rows
--   service_role   = the secret key, which skips every rule below      -> the running app never uses it

-- One row per chat ---------------------------------------------------------------------------------------------
create table if not exists public.conversations (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,  -- the owner, filled in from the login token
  title      text not null default 'New chat' check (char_length(title) between 1 and 200),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()  -- the time of the last message: the chat list is sorted by it
);

-- One row per message. Oldest first: order by id --------------------------------------------------------------
create table if not exists public.messages (
  id              bigint generated always as identity primary key,
  conversation_id uuid not null references public.conversations (id) on delete cascade,  -- deleting a chat deletes its messages
  user_id         uuid not null default auth.uid(),  -- the owner again, so the privacy rule below is one cheap check
  role            text not null check (role in ('user', 'assistant')),
  content         text not null check (char_length(content) between 1 and 10000),
  source_used     text check (source_used in ('private_kb', 'web_search', 'direct', 'fallback')),  -- answers: which path replied
  citations       jsonb,    -- answers: the sources, [{"source", "type", "title"}]
  trace           jsonb,    -- answers: the decision path, a list of lines
  latency_ms      integer,  -- answers: how long the reply took
  created_at      timestamptz not null default now()
);

comment on table public.conversations is 'One chat per row. A user sees only their own.';
comment on table public.messages is 'The questions and answers of a chat, oldest first (order by id). A saved message is never edited.';

create index if not exists conversations_user_recent_idx on public.conversations (user_id, updated_at desc);
create index if not exists messages_conversation_idx on public.messages (conversation_id, id);

-- Saving a message moves its chat to the top of the list --------------------------------------------------------
create or replace function public.touch_conversation() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  update public.conversations set updated_at = now() where id = new.conversation_id;
  return new;
end;
$$;

drop trigger if exists messages_touch_conversation on public.messages;
create trigger messages_touch_conversation after insert on public.messages
  for each row execute function public.touch_conversation();

-- Who may do what ------------------------------------------------------------------------------------------------
alter table public.conversations enable row level security;
alter table public.messages      enable row level security;

-- Start from nothing, whatever this project's defaults were, then give signed-in users only what the app needs.
revoke all on public.conversations, public.messages from anon, authenticated;
grant select, insert, update, delete on public.conversations to authenticated;
grant select, insert                 on public.messages      to authenticated;  -- a saved message is never edited or deleted on its own

drop policy if exists "own chats" on public.conversations;
create policy "own chats" on public.conversations
  for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "read own messages" on public.messages;
create policy "read own messages" on public.messages
  for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "add messages to own chats" on public.messages;
create policy "add messages to own chats" on public.messages
  for insert to authenticated
  with check (
    (select auth.uid()) = user_id
    and exists (select 1 from public.conversations c where c.id = conversation_id and c.user_id = (select auth.uid()))
  );

-- Check: both tables should show rls_on = true and at least one policy -----------------------------------------------
select c.relname as "table",
       c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.schemaname = 'public' and p.tablename = c.relname) as policies
from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relname in ('conversations', 'messages')
order by c.relname;
