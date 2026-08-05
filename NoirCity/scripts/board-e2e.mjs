/**
 * Exercises the corkboard in solo play: gather clues, open the board, drag a
 * card, run string between two, pin a note.
 *
 * Solo uses the in-memory backing, so this proves the interaction model without
 * needing a Supabase project. The shared backing behind the same interface is
 * still unverified.
 *
 *   node scripts/board-e2e.mjs <shot-dir>
 */
import { chromium } from "playwright";
import { travelTo } from "./e2e-lib.mjs";

const shots = process.argv[2] ?? ".";
const BASE = process.env.BASE_URL ?? "http://localhost:3000";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });

const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

const log = (m) => console.log(`  ${m}`);

await page.goto(BASE, { waitUntil: "networkidle" });
await page
  .locator("li", { hasText: "The Quiet Room" })
  .getByRole("link", { name: /PLAY ALONE/ })
  .click();
await page.waitForSelector("canvas.citymap-canvas", { timeout: 20000 });
await page.waitForTimeout(1000);
await page.getByRole("button", { name: "GET TO WORK" }).click();

// Gather enough evidence that the board has something on it.
await travelTo(page, "loc_0269");
await page.getByRole("button", { name: /SEARCH THIS PLACE/ }).click();
await page.waitForTimeout(500);
await page.getByRole("button", { name: /Take me through Thursday evening/ }).click();
await page.waitForTimeout(500);
log("gathered 4 clues");

await page.getByRole("button", { name: /THE BOARD/ }).click();
await page.waitForTimeout(700);
await page.screenshot({ path: `${shots}/board-01-open.png` });

const cards = page.locator("article.absolute");
const count = await cards.count();
log(`board shows ${count} cards`);
if (count < 4) throw new Error(`expected at least 4 cards, saw ${count}`);

// --- drag the first card -------------------------------------------------
const before = await cards.first().boundingBox();
await page.mouse.move(before.x + 90, before.y + 40);
await page.mouse.down();
await page.mouse.move(before.x + 330, before.y + 250, { steps: 12 });
await page.mouse.up();
await page.waitForTimeout(300);
const after = await cards.first().boundingBox();
const moved = Math.hypot(after.x - before.x, after.y - before.y);
log(`card moved ${Math.round(moved)}px`);
if (moved < 100) throw new Error("card did not move");

// --- run string between two cards ---------------------------------------
await cards.nth(1).click();
await page.waitForTimeout(200);
await cards.nth(2).click();
await page.waitForTimeout(400);
const strings = await page.locator("path.board-string").count();
log(`strings on the board: ${strings}`);
if (strings < 1) throw new Error("no string was drawn");

// clicking the same pair again should cut it
await cards.nth(1).click();
await cards.nth(2).click();
await page.waitForTimeout(400);
const afterCut = await page.locator("path.board-string").count();
log(`after re-click: ${afterCut}`);
if (afterCut !== strings - 1) throw new Error("string did not toggle off");

// put it back for the screenshot
await cards.nth(1).click();
await cards.nth(2).click();
await page.waitForTimeout(300);

// --- pin a note ----------------------------------------------------------
const surface = page.locator("div.relative.flex-1.overflow-auto");
const box = await surface.boundingBox();
await page.mouse.dblclick(box.x + box.width - 220, box.y + box.height - 160);
await page.waitForTimeout(300);
const notes = await page.locator("textarea").count();
log(`notes pinned: ${notes}`);
if (notes < 1) throw new Error("double-click did not pin a note");

await page.locator("textarea").first().fill("Vane wrote the prescription. Why?");
await page.waitForTimeout(300);
await page.screenshot({ path: `${shots}/board-02-linked.png` });

// --- back to the case ----------------------------------------------------
await page.getByRole("button", { name: /BACK TO THE CASE/ }).click();
await page.waitForTimeout(500);
await page.getByRole("button", { name: /THE BOARD/ }).click();
await page.waitForTimeout(600);
const kept = await page.locator("path.board-string").count();
const keptNotes = await page.locator("textarea").count();
log(`after reopening — strings: ${kept}, notes: ${keptNotes}`);
if (kept < 1 || keptNotes < 1) throw new Error("board did not survive a close");

await page.screenshot({ path: `${shots}/board-03-reopened.png` });

console.log(errors.length ? `\n  ${errors.length} console error(s):` : "\n  no console errors");
for (const e of errors.slice(0, 6)) console.log("    " + e);

await browser.close();
