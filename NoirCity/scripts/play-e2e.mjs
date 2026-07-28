/**
 * Plays "The Quiet Room" through the actual UI, start to accusation.
 *
 * The unit tests prove the engine solves the case. This proves a person with a
 * mouse can. Screenshots land in the directory given as the first argument.
 *
 *   node scripts/play-e2e.mjs <shot-dir>
 */
import { chromium } from "playwright";

const shots = process.argv[2] ?? ".";
const BASE = "http://localhost:3000";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });

const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

const shot = (name) => page.screenshot({ path: `${shots}/${name}.png` });
const log = (m) => console.log(`  ${m}`);

/** Clicks a map pin by its city location id. */
async function travelTo(locationId) {
  const pt = await page.evaluate(async (id) => {
    const city = await fetch("/city.json").then((r) => r.json());
    const loc = city.locations.find((l) => l.id === id);
    if (!loc) return null;
    const map = window.__cityMap;
    if (!map) return null;
    const p = map.latLngToContainerPoint({ lat: loc.y, lng: loc.x });
    const rect = map.getContainer().getBoundingClientRect();
    return { x: rect.left + p.x, y: rect.top + p.y };
  }, locationId);
  if (!pt) throw new Error(`could not locate ${locationId} on screen`);

  await page.mouse.click(pt.x, pt.y);
  await page.getByRole("button", { name: /DRIVE OVER/ }).click();
  await page.waitForTimeout(500);
}

async function hoursLeft() {
  const text = await page.locator("p.tabular-nums").first().textContent();
  return Number(text.trim());
}

// --- open the case ---------------------------------------------------------
await page.goto(BASE, { waitUntil: "networkidle" });
await shot("01-case-files");
log("case files listed");

await page.getByRole("link", { name: /The Quiet Room/ }).click();
await page.waitForSelector("canvas.citymap-canvas", { timeout: 20000 });
await page.waitForTimeout(1200);
await shot("02-brief");
log(`brief shown, ${await hoursLeft()}h on the clock`);

await page.getByRole("button", { name: "GET TO WORK" }).click();
await page.waitForTimeout(400);

// --- tutorial step 1: travel ----------------------------------------------
const step1 = await page.locator("h2").first().textContent();
log(`tutorial: ${step1}`);
await travelTo("loc_0269");
await shot("03-at-the-scene");

// --- step 2: search --------------------------------------------------------
await page.getByRole("button", { name: /SEARCH THIS PLACE/ }).click();
await page.waitForTimeout(600);
await shot("04-searched");
log(`searched the parlour, ${await hoursLeft()}h left`);

// --- step 3: interview -----------------------------------------------------
await page.getByRole("button", { name: /Take me through Thursday evening/ }).click();
await page.waitForTimeout(600);
await shot("05-interviewed");
log("questioned Madame Roux");

// --- step 4: lab -----------------------------------------------------------
await page.getByRole("button", { name: /^EVIDENCE/ }).click();
await page.waitForTimeout(300);
await page.getByRole("button", { name: /A cup at her place/ }).click();
await page.waitForTimeout(300);
await shot("06-evidence");
await page.getByRole("button", { name: /SEND TO THE LAB/ }).click();
await page.waitForTimeout(700);
await shot("07-lab-result");
log(`lab report back, ${await hoursLeft()}h left`);

// --- the rest of the investigation ----------------------------------------
await page.getByRole("button", { name: "HERE" }).click();
await travelTo("loc_0023");
await page.getByRole("button", { name: /SEARCH THIS PLACE/ }).click();
await page.waitForTimeout(600);
log("searched the clinic");

await travelTo("loc_0272");
await page.getByRole("button", { name: /SEARCH THIS PLACE/ }).click();
await page.waitForTimeout(600);
log(`searched the apartment, ${await hoursLeft()}h left`);
await shot("08-mid-case");

// --- accuse ----------------------------------------------------------------
await page.getByRole("button", { name: "ACCUSE" }).click();
await page.waitForTimeout(300);
await page.getByRole("button", { name: /Dr\. Emmanuel Vane/ }).click();
await page.getByRole("button", { name: /To close an account/ }).click();
for (const title of [
  "Analysis of the dregs",
  "The prescription book",
  "The Frayne accounts",
]) {
  await page.getByRole("button", { name: title, exact: false }).last().click();
}
await shot("09-accusation-form");

await page.getByRole("button", { name: "FILE THE ACCUSATION" }).click();
await page.waitForTimeout(300);
await page.getByRole("button", { name: "GO AHEAD" }).click();
await page.waitForTimeout(1000);
await shot("10-verdict");

const verdict = await page.locator("h1").first().textContent();
const banner = await page.locator("p.tracking-\\[0\\.4em\\]").first().textContent();
log(`verdict: ${banner?.trim()} — ${verdict?.trim()}`);

const score = await page.locator("p.tabular-nums").last().textContent();
log(`score: ${score?.trim()}`);

console.log(
  errors.length ? `\n  ${errors.length} console error(s):` : "\n  no console errors",
);
for (const e of errors.slice(0, 6)) console.log("    " + e);

await browser.close();
