/**
 * Solves a case through the HTTP API alone, no browser.
 *
 * This is the test that matters for the Cloudflare port: it exercises bundled
 * case JSON, the navigation-only city, and signed stateless sessions — all the
 * things that changed when the server stopped having a filesystem and a memory.
 *
 *   node scripts/api-e2e.mjs                       # against npm run dev
 *   BASE_URL=http://127.0.0.1:8787 node scripts/api-e2e.mjs   # against the Worker
 */

const BASE = process.env.BASE_URL ?? "http://localhost:3000";

async function post(body) {
  const res = await fetch(`${BASE}/api/game`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${res.status} returned non-JSON: ${text.slice(0, 200)}`);
  }
  return { ok: res.ok, status: res.status, body: parsed };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const CASES = {
  "the-quiet-room": {
    script: [
      { type: "travel", locationId: "loc_0269" },
      { type: "search" },
      { type: "interview", npcId: "n_sabine", questionId: "q_night" },
      { type: "lab", clueId: "c_teacup" },
      { type: "travel", locationId: "loc_0023" },
      { type: "search" },
      { type: "travel", locationId: "loc_0272" },
      { type: "search" },
    ],
    accusation: {
      type: "accuse",
      culpritId: "s_vane",
      motiveId: "m_ledger",
      evidenceIds: ["c_lab_digitalis", "c_prescription", "c_ledger_debt"],
    },
  },
  "the-bell-does-not-lie": {
    script: [
      { type: "travel", locationId: "loc_0398" },
      { type: "search" },
      { type: "travel", locationId: "loc_lm_the_county_morgue" },
      { type: "interview", npcId: "n_coroner", questionId: "q_time" },
      { type: "travel", locationId: "loc_lm_the_bell_of_order" },
      { type: "search" },
      { type: "search" },
    ],
    accusation: {
      type: "accuse",
      culpritId: "s_vole",
      motiveId: "m_committee",
      evidenceIds: ["c_doctor_estimate", "c_bell_jam", "c_maintenance_log"],
    },
  },
};

console.log(`  target ${BASE}\n`);

for (const [caseId, plan] of Object.entries(CASES)) {
  const started = await post({ intent: "start", caseId });
  assert(started.ok, `start ${caseId}: ${started.body.error}`);

  let token = started.body.sessionId;
  const budget = started.body.view.timeBudget;

  for (const action of plan.script) {
    const res = await post({ intent: "act", token, action });
    assert(res.ok, `${caseId} ${action.type}: ${res.body.error}`);
    token = res.body.sessionId;
  }

  // A session must survive being put down and picked up again - which on
  // Cloudflare means being handled by an isolate that never saw the earlier
  // moves.
  const resumed = await post({ intent: "resume", token });
  assert(resumed.ok, `${caseId} resume: ${resumed.body.error}`);
  assert(
    resumed.body.view.state.discoveredClues.length ===
      started.body.view.state.discoveredClues.length +
        (resumed.body.view.clues.length - started.body.view.clues.length),
    `${caseId}: resume lost clues`,
  );
  token = resumed.body.sessionId;

  const clues = resumed.body.view.clues.length;
  const left = resumed.body.view.state.timeRemaining;

  const final = await post({ intent: "act", token, action: plan.accusation });
  assert(final.ok, `${caseId} accuse: ${final.body.error}`);
  const result = final.body.view.result;
  assert(result, `${caseId}: no result returned`);
  assert(result.solved, `${caseId}: accusation not accepted as solved`);

  console.log(
    `  ${caseId.padEnd(24)} solved · ${clues} clues · ${left}/${budget}h left · ${result.score} pts`,
  );
}

// --- the token must not be editable ---------------------------------------
{
  const started = await post({ intent: "start", caseId: "the-quiet-room" });
  const [body, signature] = started.body.sessionId.split(".");
  const decoded = JSON.parse(Buffer.from(body, "base64url").toString("utf8"));
  decoded.state.timeRemaining = 9999;
  const forged =
    Buffer.from(JSON.stringify(decoded)).toString("base64url") + "." + signature;

  const attempt = await post({ intent: "resume", token: forged });
  assert(!attempt.ok, "SECURITY: a forged token was accepted");
  console.log(`  ${"forged token".padEnd(24)} rejected (${attempt.status})`);
}

// --- the solution must not be on the wire ---------------------------------
{
  const started = await post({ intent: "start", caseId: "the-quiet-room" });
  const wire = JSON.stringify(started.body);
  for (const leak of ["isRedHerring", "requiredEvidence", "labResult", "epilogue"]) {
    assert(!wire.includes(leak), `SECURITY: "${leak}" reached the client`);
  }
  console.log(`  ${"solution on the wire".padEnd(24)} absent`);
}

console.log("\n  all API checks passed");
