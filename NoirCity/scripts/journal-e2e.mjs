/**
 * Exercises the journal and the address book: read the brief as an entry, type
 * an address to travel there, search, and confirm the journal fills up with
 * dated prose rather than log lines.
 *
 *   node scripts/journal-e2e.mjs <shot-dir>
 */
import { chromium } from "playwright";
import { enterStudy } from "./e2e-lib.mjs";

const shots = process.argv[2] ?? ".";
const BASE = process.env.BASE_URL ?? "http://localhost:3000";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });

const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

const log = (m) => console.log(`  ${m}`);

await page.goto(`${BASE}/play/the-quiet-room`, { waitUntil: "networkidle" });
await page.waitForSelector("canvas.citymap-canvas", { timeout: 20000 });
await page.waitForTimeout(1200);
await page.getByRole("button", { name: "GET TO WORK" }).click();
await page.waitForTimeout(400);
await page.screenshot({ path: `${shots}/01-journal-open.png` });

const opening = await page.locator("article").first().innerText();
log(`journal opens on: ${opening.split("\n")[0]}`);

// --- the address book -----------------------------------------------------
await page.getByRole("button", { name: "HERE", exact: true }).click();
await page.waitForTimeout(400);

const field = page.getByPlaceholder("176 Cannon Yard");
await field.fill("74 Threadneedle");
await page.waitForTimeout(500);
await page.screenshot({ path: `${shots}/02-address-book.png` });

const matches = await page.locator("button", { hasText: "74 Threadneedle Circle" }).count();
log(`typing "74 Threadneedle" offers ${matches} address(es)`);
if (matches < 1) throw new Error("address book found nothing");

// A nonsense address must say so rather than silently offering the world.
await field.fill("999 Nowhere At All");
await page.waitForTimeout(400);
const noSuch = await page.getByText("No such address in Marrowgate").count();
log(`nonsense address rejected: ${noSuch === 1}`);
if (noSuch !== 1) throw new Error("bad address was not rejected");

await field.fill("74 Threadneedle Circle");
await page.waitForTimeout(400);
await page.locator("button", { hasText: "74 Threadneedle Circle" }).first().click();
await page.waitForTimeout(900);

await page.getByRole("button", { name: /SEARCH THIS PLACE/ }).click();
await page.waitForTimeout(800);

// --- the journal should now read like a case file -------------------------
await page.getByRole("button", { name: "JOURNAL" }).click();
await page.waitForTimeout(700);
await page.screenshot({ path: `${shots}/03-journal-entries.png` });

const entries = await page.locator("article").count();
log(`journal entries: ${entries}`);
if (entries < 3) throw new Error(`expected brief + travel + search, saw ${entries}`);

const text = await page.locator("article").last().innerText();
log(`latest entry heading: ${text.split("\n").slice(0, 3).join(" | ")}`);

const hasDateline = await page.getByText(/1984/).count();
log(`datelines rendered: ${hasDateline > 0}`);
if (!hasDateline) throw new Error("no in-fiction dateline on any entry");

const countdown = (await page.getByTestId("countdown").innerText()).trim();
log(`session countdown: ${countdown}`);
if (!/^\d{2}:\d{2}:\d{2}$/.test(countdown)) {
  throw new Error(`countdown not ticking: "${countdown}"`);
}

await page.waitForTimeout(2200);
const later = (await page.getByTestId("countdown").innerText()).trim();
log(`two seconds later:  ${later}`);
if (later === countdown) throw new Error("countdown is frozen");

console.log(errors.length ? `\n  ${errors.length} console error(s):` : "\n  no console errors");
for (const e of errors.slice(0, 6)) console.log("    " + e);

await browser.close();
