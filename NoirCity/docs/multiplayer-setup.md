# Multiplayer setup

Rooms are optional. With no Supabase project the game runs solo against an
in-memory store — every case fully playable, just not shareable. The "play with
friends" button stands down rather than erroring on click.

To turn rooms on:

## 1. Create a project

Free tier at [supabase.com](https://supabase.com). Any region; pick one near
your players since realtime latency is the thing you will feel.

## 2. Run the migration

**Dashboard route** — SQL Editor → paste
[`0001_init.sql`](../supabase/migrations/0001_init.sql), Run, then
[`0002_corkboard.sql`](../supabase/migrations/0002_corkboard.sql), Run. Order
matters: the corkboard policies use the `is_member` function from the first file.

**CLI route:**

```bash
npx supabase link --project-ref <your-ref>
npx supabase db push
```

## 3. Enable anonymous sign-in

Dashboard → Authentication → Providers → **Anonymous Sign-Ins** → on.

This is what lets six friends join from a link without making accounts. Without
it, every room request comes back 401.

## 4. Fill in `.env.local`

Copy `.env.example` and take the values from Project Settings → API:

```
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

The service role key **bypasses row level security**. It is what lets the server
write game state that no player is allowed to write themselves. Never prefix it
with `NEXT_PUBLIC_`, and never commit it.

Restart `npm run dev` — env vars are read at boot.

## How to tell it worked

The front page grows a **PLAY WITH FRIENDS** button on each case and a join-by-code
box at the bottom. Open a room, then join it from a private window with the code.

## The security model

One line: **players may read the rooms they belong to and write nothing except
chat.**

- Every game mutation goes through a server route, because the server is the
  only party holding the case file and able to decide whether an action is legal.
- `games`, `game_players` and `game_events` have **no INSERT or UPDATE policy at
  all**. That is deliberate, not an oversight — those tables are writable only by
  the service role. It is what stops a player opening devtools and awarding
  themselves the murder weapon or another forty hours on the clock.
- `lib/supabase/server.ts` imports `server-only`, so if the admin client is ever
  pulled into a client component the **build fails** rather than shipping the key.
- Case content never enters the database. What is stored is discovered clue ids
  and counters — already safe for a member to see, since that is what their own
  screen shows them. RLS only has to keep non-members out.

## Concurrency

Six people share one clock, and any of them can act at any moment. Writes are
conditional on `state_version`:

```sql
update games set state = ..., state_version = $n + 1
where id = $game and state_version = $n
```

If two players search at the same instant, one write lands and the other affects
zero rows. The loser re-reads and retries (three attempts), so the same hour can
never be spent twice. A player who still ends up stale gets *"The board moved
under you"* rather than a silently wrong clock.

Realtime carries a **nudge, not the state** — when the row changes, every client
re-reads the authoritative snapshot from the server. That costs one extra round
trip and buys immunity to a class of bug where clients apply a broadcast twice
and drift apart.

## Free tier limits worth knowing

| Limit | Meaning for this game |
|---|---|
| 200 concurrent realtime connections | ~33 simultaneous six-player rooms |
| 500 MB database | Effectively unlimited; rows are tiny |
| Pauses after 7 days idle | Fine in development. Before sharing a link publicly, either ping it on a schedule or expect to resume it by hand. |

## The corkboard makes a different call

Game tables are read-only to players because a write there changes what is true.
The corkboard changes nothing — it is six people arguing over which pieces
connect, and being wrong on the corkboard costs you nothing but the argument.

So `board_cards`, `board_links` and `board_notes` **are** writable by members,
directly from the browser. That is what makes dragging a card feel instant
instead of costing a server round trip per pointer move; the database only hears
about it when you let go. The worst a malicious member can do is rearrange their
own team's index cards, which they could achieve by asking.

## Not done yet

- **Reconnect on the corkboard** — a card moved while you were offline arrives on
  the next realtime event, but there is no conflict resolution if two people drag
  the same card at once. Last write wins.
- **Chat history limit** — the last 200 messages, no pagination.
