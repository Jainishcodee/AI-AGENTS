/**
 * Two browsers, one room. The test that proves the multiplayer half.
 *
 * Separate browser contexts so each gets its own anonymous user and its own
 * cookies - sharing a context would quietly test one player twice.
 *
 *   node scripts/room-e2e.mjs <shot-dir>
 */
import { chromium } from "playwright";
import { enterStudy } from "./e2e-lib.mjs";
import { readFileSync } from "node:fs";

const shots = process.argv[2] ?? ".";
const BASE = process.env.BASE_URL ?? "http://localhost:3000";

function env(file = ".env.local") {
  const out = {};
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (m) out[m[1]] = m[2].trim().replace(/^["']|["']$/g, "");
  }
  return out;
}

const log = (m) => console.log(`  ${m}`);
const assert = (c, m) => {
  if (!c) throw new Error(m);
};

const browser = await chromium.launch();
const errors = [];

async function newPlayer(name) {
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(`${name}: ${e}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`${name}: ${m.text()}`));
  return page;
}

// --- host opens a room -----------------------------------------------------
const host = await newPlayer("host");
await host.goto(BASE, { waitUntil: "networkidle" });
await enterStudy(host);

// The landing page carries two "Your name" fields - one per case card and one
// in the join box - so both selectors have to be scoped to their own card.
const hostCard = host.locator("li", { hasText: "The Quiet Room" });
await hostCard.getByRole("button", { name: /PLAY WITH FRIENDS/ }).click();
await hostCard.getByPlaceholder("Your name").fill("Marlowe");
await hostCard.getByRole("button", { name: /OPEN A ROOM/ }).click();

await host.waitForURL(/\/room\//, { timeout: 20000 });
await host.waitForSelector("text=ROOM CODE", { timeout: 15000 });

// Sized responsively, so match on the button that holds it rather than a class.
const code = (
  await host
    .locator("button", { hasText: "ROOM CODE" })
    .getByTestId("room-code")
    .first()
    .innerText()
).trim();
log(`host opened room ${code}`);
assert(/^[A-Z0-9]{4}$/.test(code), `room code looks wrong: "${code}"`);
await host.screenshot({ path: `${shots}/room-01-lobby.png` });

// --- second player joins ---------------------------------------------------
const guest = await newPlayer("guest");
await guest.goto(BASE, { waitUntil: "networkidle" });
await enterStudy(guest);
const joinBox = guest.locator("section", { hasText: "SOMEBODY GAVE YOU A CODE" });
await joinBox.getByPlaceholder("CODE").fill(code);
await joinBox.getByPlaceholder("Your name").fill("Spade");
await joinBox.getByRole("button", { name: /JOIN THE CASE/ }).click();
await guest.waitForURL(/\/room\//, { timeout: 20000 });
log("guest joined");

// The host's roster must update on its own - that is realtime doing its job.
await host.waitForSelector("text=Spade", { timeout: 15000 });
log("host saw the guest arrive without reloading");
await host.screenshot({ path: `${shots}/room-02-both-in-lobby.png` });

// Presence: both should show as connected. It arrives over its own channel and
// settles a beat after the roster does, so this waits rather than sampling once.
await host
  .waitForFunction(
    () => document.querySelectorAll('[data-testid="presence-dot"][data-online="true"]').length >= 2,
    null,
    { timeout: 15000 },
  )
  .catch(() => {});
const dots = await host.locator('[data-testid="presence-dot"][data-online="true"]').count();
log(`presence dots lit: ${dots} of 2`);
assert(dots >= 2, "presence did not register both players");

// Only the host may start.
const guestStart = await guest.getByRole("button", { name: /OPEN THE CASE FILE/ }).count();
assert(guestStart === 0, "guest was offered the host's start button");
log("guest correctly has no start button");

// --- start ------------------------------------------------------------------
await host.getByRole("button", { name: /OPEN THE CASE FILE/ }).click();
await host.waitForSelector("canvas.citymap-canvas", { timeout: 25000 });
await guest.waitForSelector("canvas.citymap-canvas", { timeout: 25000 });
log("both players are in the game");
await host.waitForTimeout(1500);

// --- the guest acts, the host must see it -----------------------------------
await guest.getByRole("button", { name: "GET TO WORK" }).click();
await guest.getByRole("button", { name: "HERE", exact: true }).click();
await guest.getByPlaceholder("176 Cannon Yard").fill("74 Threadneedle Circle");
await guest.waitForTimeout(600);
await guest.locator("button", { hasText: "74 Threadneedle Circle" }).first().click();
await guest.waitForTimeout(2500);

await host.getByRole("button", { name: "JOURNAL" }).click();
await host.waitForTimeout(1200);
const hostJournal = await host.locator("article").allInnerTexts();
const sawTravel = hostJournal.some((t) => t.includes("Rosewood Rooms"));
log(`host's journal shows the guest's move: ${sawTravel}`);
assert(sawTravel, "the guest's travel never reached the host");

// The shared clock must agree.
const hostHours = await host.getByTestId("story-clock").innerText();
const guestHours = await guest.getByTestId("story-clock").innerText();
log(`host clock:  ${hostHours.replace(/\s+/g, " ")}`);
log(`guest clock: ${guestHours.replace(/\s+/g, " ")}`);
assert(hostHours === guestHours, "the two players disagree about the clock");

await host.screenshot({ path: `${shots}/room-03-shared-journal.png` });

// --- chat --------------------------------------------------------------------
await host.getByRole("button", { name: /^CHAT/ }).click();
await host.getByPlaceholder("Say something").fill("The medium is lying about something.");
await host.keyboard.press("Enter");
await guest.waitForTimeout(2500);
await guest.getByRole("button", { name: /^CHAT/ }).click();
await guest.waitForTimeout(800);
const guestChat = await guest.locator("text=The medium is lying").count();
log(`chat delivered: ${guestChat > 0}`);
assert(guestChat > 0, "chat message never arrived");
await guest.screenshot({ path: `${shots}/room-04-chat.png` });

// --- row level security ------------------------------------------------------
// A stranger holding the public anon key must see nothing at all.
{
  const e = env();
  const res = await fetch(`${e.NEXT_PUBLIC_SUPABASE_URL}/rest/v1/games?select=*`, {
    headers: { apikey: e.NEXT_PUBLIC_SUPABASE_ANON_KEY },
  });
  const rows = await res.json();
  const leaked = Array.isArray(rows) ? rows.length : "error";
  log(`RLS - rows visible to a non-member: ${leaked}`);
  assert(Array.isArray(rows) && rows.length === 0, "RLS LEAK: outsider can read games");
}

console.log(errors.length ? `\n  ${errors.length} console error(s):` : "\n  no console errors");
for (const e of errors.slice(0, 8)) console.log("    " + e);

await browser.close();
