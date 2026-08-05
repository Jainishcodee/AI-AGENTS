# Deploying to Cloudflare

Runs as a Cloudflare Worker via [OpenNext](https://opennext.js.org/cloudflare).
Verified locally against the real `workerd` runtime — both cases solvable end to
end, forged sessions rejected, no solution on the wire.

## Three things the port had to change

Cloudflare is not Node with a CDN in front. Two assumptions in the original build
would have failed in production, silently and intermittently:

**1. There is no filesystem.** Case files and the city were read with
`fs.readFileSync`. They are now static imports, bundled into the Worker.

**2. There is no memory between requests.** Solo sessions lived in a `Map` on the
server. A Worker isolate is torn down between requests, so the second action in a
game could easily land somewhere that had never heard of the first.

Sessions are now a **signed token the player carries**: the game state plus an
HMAC over it. The client cannot forge one without the key, so the server trusts
the signature rather than the client. This is strictly better than the `Map` even
off Cloudflare — a game now survives a restart, and there is nothing to evict.

**3. Production means production.** `npm run dev` reports development; the
Workers runtime does not. `SESSION_SECRET` has a development fallback and
**throws in production if unset** — a signing key that silently defaults is worse
than a loud failure. This is why `cf:preview` needs `.dev.vars`.

## Local preview against the real runtime

```bash
cp .dev.vars.example .dev.vars
node -e "console.log(crypto.randomUUID()+crypto.randomUUID())"   # paste as SESSION_SECRET
npm run cf:preview
```

Serves on `http://127.0.0.1:8787` under `workerd` — the same engine that runs in
production, not an emulation of it.

Verify it:

```bash
BASE_URL=http://127.0.0.1:8787 npm run test:api
```

## Deploying

```bash
npx wrangler login
npm run cf:deploy
```

Then set the production secrets — these are **not** read from `.dev.vars`:

```bash
npx wrangler secret put SESSION_SECRET

# only if multiplayer is on
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
```

The two `NEXT_PUBLIC_SUPABASE_*` values are inlined into the client bundle at
build time, so they belong in `.env.local` (or your CI environment) **before**
`cf:build` — putting them in `wrangler secret` will not work.

## Marking accusations

An accusation is two written fields: a name, and the case in the player's own
words. The name is matched against the suspects in code. The written case is
marked against the solution's `keyPoints` by **Workers AI**, declared as the
`AI` binding in `wrangler.jsonc`. There is no key and no API call — it runs in
this worker, on Cloudflare's free daily neuron allowance.

**It is optional, and that is deliberate.** With no binding — every local run,
every test, any other host — `lib/server/aiGrade.ts` falls back to keyword
coverage and the verdict says `MARKED OFFLINE — ON WORDING ALONE`. The game is
never unplayable because a model is missing; it is marked more bluntly, which is
a different thing. The model is also given a hard 8-second timeout and a
try/catch, so a slow or failing one costs a player nothing but a coarser mark.

Grading is server-side and cannot move. `keyPoints` are the solution written out
as plain sentences — the single most spoiler-heavy field in a case file, and the
one thing a player could read out of a network response and win with. That is
what `lib/engine/view.ts` redacts, and `view.test.ts` asserts no key point or
keyword ever appears in a client view.

To watch what the grader is actually doing:

```bash
npx wrangler tail --format pretty
```

## Sizes

| | |
|---|---|
| Worker entry | ~2 KB |
| Static assets | ~2.1 MB (mostly `city.json` at 556 KB) |
| Server bundle | ~24 MB uncompressed |

`city.json` is served as a static asset, not bundled — the browser fetches it
once and caches it. The server gets `content/city-nav.json` instead (296 KB:
locations, boroughs and bridges, no streets or blocks), because the server never
draws anything and would otherwise carry half a megabyte of geometry for nothing.

Cloudflare's Worker size limit applies to the compressed bundle. If it ever
becomes a problem, the case JSON is the thing to move out to assets.

## Gotchas

- **`nodejs_compat` is required** and set in `wrangler.jsonc`. Without it the
  OpenNext shims fail at startup with an unhelpful error.
- **Node built-ins**: nothing in the app calls `fs`, `path` or `node:crypto` at
  runtime. Signing uses Web Crypto, which Workers implement natively. Keep it
  that way — `scripts/` may use Node freely, `lib/server/` may not.
- **`window.__cityMap`** is a development-only hook for browser tests and is
  stripped from production builds. That is why `play-e2e.mjs` cannot drive the
  map against `cf:preview`; use `api-e2e.mjs` there, which covers everything the
  port actually changed.
