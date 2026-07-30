/**
 * Screenshots every screen at phone and desktop width, into `shots/`.
 *
 * Not a test - it asserts nothing. It exists so a change to the look can be
 * looked at, which is the only way to review one.
 *
 *   node scripts/shots.mjs
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = "shots";
mkdirSync(OUT, { recursive: true });

const SIZES = {
  phone: { width: 430, height: 900 },
  desktop: { width: 1500, height: 950 },
};

const browser = await chromium.launch();

for (const [size, viewport] of Object.entries(SIZES)) {
  const page = await browser.newPage({ viewport });
  const shot = (name) =>
    page.screenshot({ path: `${OUT}/${size}-${name}.png` });

  await page.goto(BASE, { waitUntil: "networkidle" });
  await shot("01-landing");

  await page.goto(`${BASE}/play/the-quiet-room`, { waitUntil: "networkidle" });
  await page.waitForSelector("canvas.citymap-canvas", { timeout: 20000 });
  await page.waitForTimeout(1800);
  await shot("02-brief");

  await page.getByRole("button", { name: "GET TO WORK" }).click();
  await page.waitForTimeout(600);
  await shot("03-map");

  // The phone starts with the sheet folded; raise it to see the panel at all.
  if (size === "phone") {
    await page.locator('button[aria-label*="case panel"]').click();
    await page.waitForTimeout(600);
    await shot("04-panel");
  }

  for (const tab of ["HERE", "EVIDENCE", "ACCUSE"]) {
    await page.getByRole("button", { name: new RegExp(`^${tab}`) }).first().click();
    await page.waitForTimeout(400);
    await shot(`05-${tab.toLowerCase()}`);
  }

  await page.getByRole("button", { name: /THE BOARD/ }).click();
  await page.waitForTimeout(700);
  await shot("06-board");

  await page.close();
  console.log(`  ${size} done`);
}

await browser.close();
console.log(`\n  written to ${OUT}/`);
