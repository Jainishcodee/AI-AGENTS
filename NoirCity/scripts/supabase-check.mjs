/**
 * Checks a Supabase project without printing any secret.
 *
 * Answers three things: are the keys live, is the schema applied, and is
 * anonymous sign-in switched on. Run it before a game night rather than finding
 * out from six people staring at an error.
 *
 *   node scripts/supabase-check.mjs
 */
import { readFileSync } from "node:fs";

function loadEnv(file = ".env.local") {
  const env = {};
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    console.error(`  ${file} not found`);
    process.exit(2);
  }
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (m) env[m[1]] = m[2].trim().replace(/^["']|["']$/g, "");
  }
  return env;
}

const env = loadEnv();
const url = env.NEXT_PUBLIC_SUPABASE_URL;
const anon = env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const service = env.SUPABASE_SERVICE_ROLE_KEY;

if (!url || !anon || !service) {
  console.error("  Missing one of URL / anon key / service role key.");
  process.exit(2);
}

// The project ref is public (it is in the URL), so this is safe to show.
const ref = new URL(url).hostname.split(".")[0];
console.log(`  project  ${ref}\n`);

const TABLES = [
  "profiles",
  "games",
  "game_players",
  "game_events",
  "chat_messages",
  "board_cards",
  "board_links",
  "board_notes",
];

let missing = 0;

for (const table of TABLES) {
  const res = await fetch(`${url}/rest/v1/${table}?select=*&limit=1`, {
    headers: { apikey: service, Authorization: `Bearer ${service}` },
  });

  if (res.ok) {
    console.log(`  ok       ${table}`);
  } else {
    const body = await res.json().catch(() => ({}));
    const relationMissing =
      res.status === 404 || body.code === "42P01" || /does not exist/i.test(body.message ?? "");
    if (relationMissing) {
      missing++;
      console.log(`  MISSING  ${table}`);
    } else {
      console.log(`  error    ${table} — ${res.status} ${body.message ?? ""}`);
    }
  }
}

// Anonymous sign-in has to be enabled in the dashboard; without it every room
// request comes back 401 and the cause is not obvious from the client.
const signIn = await fetch(`${url}/auth/v1/signup`, {
  method: "POST",
  headers: { apikey: anon, "Content-Type": "application/json" },
  body: JSON.stringify({ data: {} }),
});
const signInBody = await signIn.json().catch(() => ({}));
const anonOk = signIn.ok && Boolean(signInBody.access_token || signInBody.user);

console.log(
  `\n  anonymous sign-in  ${anonOk ? "enabled" : `DISABLED — ${signInBody.msg ?? signInBody.error_description ?? signIn.status}`}`,
);

if (missing) {
  console.log(
    `\n  ${missing} of ${TABLES.length} tables missing. Apply supabase/migrations/*.sql in order.`,
  );
  process.exit(1);
}
console.log("\n  schema is in place");
