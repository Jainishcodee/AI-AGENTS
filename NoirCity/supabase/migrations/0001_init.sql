-- NoirCity: multiplayer schema.
--
-- The security model in one line: players may READ the rooms they belong to and
-- may WRITE nothing except chat. Every game mutation goes through a server route
-- using the service role, because the server is the only party that holds the
-- case file and can decide whether an action is legal.
--
-- Case content lives in git as JSON and is never stored here. What is stored is
-- runtime state: which clues the team has found, where they are, what time is
-- left. All of that is already safe for a member to see - it is what the UI
-- shows them - so RLS only has to keep NON-members out.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------

create table if not exists public.profiles (
  id           uuid primary key references auth.users on delete cascade,
  display_name text not null default 'Investigator',
  avatar_seed  text not null default gen_random_uuid()::text,
  created_at   timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "read own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "insert own profile"
  on public.profiles for insert
  with check (auth.uid() = id);

create policy "update own profile"
  on public.profiles for update
  using (auth.uid() = id);

-- ---------------------------------------------------------------------------
-- games
-- ---------------------------------------------------------------------------

create table if not exists public.games (
  id             uuid primary key default gen_random_uuid(),
  room_code      text not null unique,
  case_id        text not null,
  host_id        uuid not null references auth.users on delete cascade,
  status         text not null default 'lobby'
                 check (status in ('lobby', 'active', 'finished')),
  -- The engine's GameState, verbatim. Safe for members: it is discovered clue
  -- ids and counters, never the solution.
  state          jsonb not null,
  -- Optimistic lock. Every accepted action bumps this, and writes carry the
  -- expected value so two players clicking at once cannot double-spend an hour.
  state_version  integer not null default 0,
  max_players    smallint not null default 6 check (max_players between 1 and 8),
  created_at     timestamptz not null default now(),
  started_at     timestamptz,
  finished_at    timestamptz
);

create index if not exists games_room_code_idx on public.games (room_code);
create index if not exists games_created_at_idx on public.games (created_at desc);

alter table public.games enable row level security;

-- ---------------------------------------------------------------------------
-- game_players
-- ---------------------------------------------------------------------------

create table if not exists public.game_players (
  game_id      uuid not null references public.games on delete cascade,
  user_id      uuid not null references auth.users on delete cascade,
  display_name text not null,
  is_host      boolean not null default false,
  joined_at    timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  primary key (game_id, user_id)
);

create index if not exists game_players_user_idx on public.game_players (user_id);

alter table public.game_players enable row level security;

-- Membership test, used by every policy below.
--
-- SECURITY DEFINER is load-bearing: without it, a policy on game_players that
-- queries game_players would recurse. Definer rights break that cycle by running
-- the lookup outside RLS.
create or replace function public.is_member(target_game uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.game_players
    where game_id = target_game and user_id = auth.uid()
  );
$$;

revoke all on function public.is_member(uuid) from public;
grant execute on function public.is_member(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- game_events - the action feed, and the realtime spine
-- ---------------------------------------------------------------------------

create table if not exists public.game_events (
  id         bigserial primary key,
  game_id    uuid not null references public.games on delete cascade,
  seq        integer not null,
  actor_id   uuid references auth.users on delete set null,
  type       text not null,
  payload    jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (game_id, seq)
);

create index if not exists game_events_game_idx on public.game_events (game_id, seq);

alter table public.game_events enable row level security;

-- ---------------------------------------------------------------------------
-- chat_messages - the one table players write to directly
-- ---------------------------------------------------------------------------

create table if not exists public.chat_messages (
  id         bigserial primary key,
  game_id    uuid not null references public.games on delete cascade,
  user_id    uuid not null references auth.users on delete cascade,
  body       text not null check (char_length(body) between 1 and 500),
  created_at timestamptz not null default now()
);

create index if not exists chat_messages_game_idx on public.chat_messages (game_id, created_at);

alter table public.chat_messages enable row level security;

-- ---------------------------------------------------------------------------
-- Policies
--
-- Read: members only. Write: nothing, except your own chat.
-- The absence of INSERT/UPDATE policies on games, game_players and game_events
-- is deliberate - those are denied to every client, and only the service role
-- (which bypasses RLS) can write them. That is what stops a player opening
-- devtools and awarding themselves the murder weapon.
-- ---------------------------------------------------------------------------

create policy "members read their game"
  on public.games for select
  using (public.is_member(id));

create policy "members read the roster"
  on public.game_players for select
  using (public.is_member(game_id));

create policy "members read the feed"
  on public.game_events for select
  using (public.is_member(game_id));

create policy "members read the chat"
  on public.chat_messages for select
  using (public.is_member(game_id));

create policy "members post chat as themselves"
  on public.chat_messages for insert
  with check (public.is_member(game_id) and user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- Realtime
-- ---------------------------------------------------------------------------

alter publication supabase_realtime add table public.games;
alter publication supabase_realtime add table public.game_players;
alter publication supabase_realtime add table public.game_events;
alter publication supabase_realtime add table public.chat_messages;

-- Realtime respects RLS, so a subscriber only receives rows they could have
-- selected. REPLICA IDENTITY FULL lets the client see old values on UPDATE,
-- which the game state diff needs.
alter table public.games replica identity full;
alter table public.game_players replica identity full;
