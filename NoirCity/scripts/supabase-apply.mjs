/**
 * Applies the migrations and switches on anonymous sign-in, using a Supabase
 * personal access token.
 *
 * The service role key cannot do this: it talks to PostgREST, which does not run
 * DDL, and auth providers are project configuration rather than data. The
 * Management API needs a token from
 * https://supabase.com/dashboard/account/tokens
 *
 *   node scripts/supabase-apply.mjs
 *
 * Safe to re-run. Anything already in place is reported and skipped.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const MIGRATIONS = "supabase/migrations";
const API = "https://api.supabase.com";

function loadEnv(file = ".env.local") {
  const env = {};
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (m) env[m[1]] = m[2].trim().replace(/^["']|["']$/g, "");
  }
  return env;
}

const env = loadEnv();
const token = env.SUPABASE_ACCESS_TOKEN;
const url = env.NEXT_PUBLIC_SUPABASE_URL;

if (!url) {
  console.error("  NEXT_PUBLIC_SUPABASE_URL is not set in .env.local");
  process.exit(2);
}
if (!token) {
  console.error(
    "  SUPABASE_ACCESS_TOKEN is not set in .env.local\n\n" +
      "  Generate one at https://supabase.com/dashboard/account/tokens\n" +
      "  then add:  SUPABASE_ACCESS_TOKEN=sbp_...\n",
  );
  process.exit(2);
}

// The project ref is public - it is right there in the URL.
const ref = new URL(url).hostname.split(".")[0];
const auth = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

console.log(`  project  ${ref}\n`);

async function runSql(sql) {
  const res = await fetch(`${API}/v1/projects/${ref}/database/query`, {
    method: "POST",
    headers: auth,
    body: JSON.stringify({ query: sql }),
  });
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, body };
}

/** Re-running a migration is normal during setup and must not look like a fault. */
function isAlreadyApplied(message = "") {
  return /already exists|duplicate|is already member/i.test(message);
}

// --- migrations, in filename order ----------------------------------------
const files = readdirSync(MIGRATIONS).filter((f) => f.endsWith(".sql")).sort();

for (const file of files) {
  const sql = readFileSync(join(MIGRATIONS, file), "utf8");
  const { ok, body } = await runSql(sql);

  if (ok) {
    console.log(`  applied  ${file}`);
    continue;
  }

  const message = body.message ?? body.error ?? JSON.stringify(body);
  if (isAlreadyApplied(message)) {
    console.log(`  skipped  ${file} — already applied`);
    continue;
  }

  console.error(`\n  FAILED   ${file}\n  ${message}\n`);
  process.exit(1);
}

// --- anonymous sign-in ----------------------------------------------------
// Without this every room request comes back 401, and nothing in the client
// makes the reason obvious.
const authRes = await fetch(`${API}/v1/projects/${ref}/config/auth`, {
  method: "PATCH",
  headers: auth,
  body: JSON.stringify({ external_anonymous_users_enabled: true }),
});

if (authRes.ok) {
  console.log("  enabled  anonymous sign-in");
} else {
  const body = await authRes.json().catch(() => ({}));
  console.error(
    `\n  Could not enable anonymous sign-in (${authRes.status}): ${body.message ?? ""}\n` +
      "  Do it by hand: Authentication -> Providers -> Anonymous Sign-Ins\n",
  );
}

console.log("\n  now run:  node scripts/supabase-check.mjs");
