/**
 * Plays "The Quiet Room" through the actual UI, start to accusation.
 *
 * The unit tests prove the engine solves the case. This proves a person with a
 * mouse can. Screenshots land in the directory given as the first argument.
 *
 *   node scripts/play-e2e.mjs <shot-dir>
 */
import { chromium } from "playwright";
import {travelTo, QUIET_ROOM_CASE, enterStudy } from "./e2e-lib.mjs";

const shots = process.argv[2] ?? ".";
// Points at `npm run dev` by default; set BASE_URL to run the same script
// against the Cloudflare Workers runtime (`npm run cf:preview`).
const BASE = process.env.BASE_URL ?? "http://localhost:3000";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });

const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

if (process.env.TRACE_API) {
  page.on("request", (r) => {
    if (r.url().includes("/api/")) {
      console.log(`    -> ${r.method()} ${r.url().replace(BASE, "")} ${r.postData() ?? ""}`);
    }
  });
  page.on("response", async (r) => {
    if (r.url().includes("/api/")) {
      const body = await r.text().catch(() => "");
      console.log(`    <- ${r.status()} ${body.slice(0, 120)}`);
    }
  });
}

const shot = (name) => page.screenshot({ path: `${shots}/${name}.png` });
const log = (m) => console.log(`  ${m}`);

// Read through `data-testid`, not through styling classes. This used to select
// `p.tabular-nums`, which meant a purely visual change - swapping that class for
// the `.numeral` utility - broke a test that cares about none of it.
async function hoursLeft() {
  const text = await page.getByTestId("hours-left").first().textContent();
  return Number(text.trim());
}

// --- open the case ---------------------------------------------------------
await page.goto(BASE, { waitUntil: "networkidle" });
 await enterStudy(page);
await shot("01-case-files");
log("case files listed");

await page
  .locator("li", { hasText: "The Quiet Room" })
  .getByRole("link", { name: /PLAY ALONE/ })
  .click();
await page.waitForSelector("canvas.citymap-canvas", { timeout: 20000 });
await page.waitForTimeout(1200);
await shot("02-brief");
log(`brief shown, ${await hoursLeft()}h on the clock`);

await page.getByRole("button", { name: "GET TO WORK" }).click();
await page.waitForTimeout(400);

// --- tutorial step 1: travel ----------------------------------------------
const step1 = await page.locator("h2").first().textContent();
log(`tutorial: ${step1}`);
await travelTo(page, "loc_0360");
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
await travelTo(page, "loc_0023");
await page.getByRole("button", { name: /SEARCH THIS PLACE/ }).click();
await page.waitForTimeout(600);
log("searched the clinic");

await travelTo(page, "loc_0385");
await page.getByRole("button", { name: /SEARCH THIS PLACE/ }).click();
await page.waitForTimeout(600);
log(`searched the apartment, ${await hoursLeft()}h left`);
await shot("08-mid-case");

// --- accuse ----------------------------------------------------------------
await page.getByRole("button", { name: /^ACCUSE/ }).click();
await page.waitForTimeout(300);

// Written out, not picked from a list. This is the whole point of the form:
// there is nothing here to guess from, so the test has to actually make the
// case the same way a player would.
await page.getByPlaceholder("A name").fill("Dr. Vane");
await page
  .getByPlaceholder("What happened, why, and what proves it.")
  .fill(QUIET_ROOM_CASE);
await shot("09-accusation-form");

await page.getByRole("button", { name: "FILE THE ACCUSATION" }).click();
await page.waitForTimeout(300);
await page.getByRole("button", { name: "GO AHEAD" }).click();
await page.waitForTimeout(1000);
await shot("10-verdict");

const verdict = await page.getByTestId("verdict-headline").textContent();
const banner = await page.getByTestId("verdict-banner").textContent();
log(`verdict: ${banner?.trim()} — ${verdict?.trim()}`);

const score = await page.getByTestId("score").textContent();
log(`score: ${score?.trim()}`);

console.log(
  errors.length ? `\n  ${errors.length} console error(s):` : "\n  no console errors",
);
for (const e of errors.slice(0, 6)) console.log("    " + e);

await browser.close();
