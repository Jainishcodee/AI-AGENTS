-- The corkboard: clue cards, string between them, and sticky notes.
--
-- A DELIBERATE DEPARTURE from the rest of the schema. Game tables are read-only
-- to players because a write there changes what is true. The corkboard changes
-- nothing — it is six people arguing over which pieces connect, and being wrong
-- on the corkboard costs you nothing but the argument.
--
-- So these tables ARE writable by members, directly from the browser. That is
-- what makes dragging a card feel instant instead of costing a server round trip
-- per pointer move. The worst a malicious member can do here is move their own
-- team's index cards around, which they could do by asking anyway.

-- ---------------------------------------------------------------------------
-- board_cards - where each discovered clue sits on the board
-- ---------------------------------------------------------------------------

create table if not exists public.board_cards (
  game_id    uuid not null references public.games on delete cascade,
  -- A clue id from the case JSON. Not a foreign key: case content lives in git,
  -- not in this database.
  clue_id    text not null,
  x          real not null,
  y          real not null,
  updated_at timestamptz not null default now(),
  updated_by uuid references auth.users on delete set null,
  primary key (game_id, clue_id)
);

alter table public.board_cards enable row level security;

create policy "members read the board"
  on public.board_cards for select
  using (public.is_member(game_id));

create policy "members place cards"
  on public.board_cards for insert
  with check (public.is_member(game_id));

create policy "members move cards"
  on public.board_cards for update
  using (public.is_member(game_id));

-- ---------------------------------------------------------------------------
-- board_links - the string
-- ---------------------------------------------------------------------------

create table if not exists public.board_links (
  id           uuid primary key default gen_random_uuid(),
  game_id      uuid not null references public.games on delete cascade,
  from_clue_id text not null,
  to_clue_id   text not null,
  label        text not null default '',
  created_by   uuid references auth.users on delete set null,
  created_at   timestamptz not null default now(),
  -- One string per pair, in one direction. Stops a double-click producing two
  -- identical threads stacked on top of each other.
  unique (game_id, from_clue_id, to_clue_id),
  check (from_clue_id <> to_clue_id)
);

create index if not exists board_links_game_idx on public.board_links (game_id);

alter table public.board_links enable row level security;

create policy "members read links"
  on public.board_links for select
  using (public.is_member(game_id));

create policy "members add links"
  on public.board_links for insert
  with check (public.is_member(game_id));

create policy "members cut links"
  on public.board_links for delete
  using (public.is_member(game_id));

-- ---------------------------------------------------------------------------
-- board_notes - what somebody scrawled and pinned up
-- ---------------------------------------------------------------------------

create table if not exists public.board_notes (
  id         uuid primary key default gen_random_uuid(),
  game_id    uuid not null references public.games on delete cascade,
  x          real not null,
  y          real not null,
  body       text not null default '' check (char_length(body) <= 300),
  created_by uuid references auth.users on delete set null,
  created_at timestamptz not null default now()
);

create index if not exists board_notes_game_idx on public.board_notes (game_id);

alter table public.board_notes enable row level security;

create policy "members read notes"
  on public.board_notes for select
  using (public.is_member(game_id));

create policy "members pin notes"
  on public.board_notes for insert
  with check (public.is_member(game_id));

create policy "members edit notes"
  on public.board_notes for update
  using (public.is_member(game_id));

create policy "members tear notes down"
  on public.board_notes for delete
  using (public.is_member(game_id));

-- ---------------------------------------------------------------------------
-- Realtime
-- ---------------------------------------------------------------------------

alter publication supabase_realtime add table public.board_cards;
alter publication supabase_realtime add table public.board_links;
alter publication supabase_realtime add table public.board_notes;

-- Deletes need the old row to tell subscribers which link vanished.
alter table public.board_links replica identity full;
alter table public.board_notes replica identity full;
