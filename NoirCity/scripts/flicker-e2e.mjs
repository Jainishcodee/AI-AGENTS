/**
 * Catches map flicker.
 *
 * Toggles the panel repeatedly and samples the map canvas throughout, checking
 * that it is never blank. A single blank frame is the whole defect: assigning to
 * `canvas.width` clears it synchronously, and if the redraw is deferred you see
 * the hole.
 *
 * Sampling reads pixels straight off the canvas rather than screenshotting, so a
 * blank frame cannot hide between two screenshots.
 *
 *   node scripts/flicker-e2e.mjs
 */
import { chromium } from "playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const log = (m) => console.log(`  ${m}`);

const browser = await chromium.launch();

/**
 * Installs a sampler that inspects the canvas on every animation frame and
 * records any frame whose pixels are all one colour - which is what "blank"
 * looks like. Runs in the page so it sees frames Playwright never could.
 */
const SAMPLER = () => {
  const w = window;
  w.__blankFrames = 0;
  w.__sampledFrames = 0;

  const tick = () => {
    const canvas = document.querySelector("canvas.citymap-canvas");
    if (canvas && canvas.width > 0) {
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      // A thin horizontal strip across the middle - cheap, and it crosses the
      // whole city rather than sampling one unlucky corner.
      const y = Math.floor(canvas.height / 2);
      const strip = ctx.getImageData(0, y, canvas.width, 1).data;
      let distinct = 0;
      let last = -1;
      for (let i = 0; i < strip.length; i += 4 * 8) {
        const v = (strip[i] << 16) | (strip[i + 1] << 8) | strip[i + 2];
        if (v !== last) {
          distinct++;
          last = v;
        }
      }
      w.__sampledFrames++;
      // A drawn city has many colour changes across a full-width strip. Fewer
      // than three means flat fill or nothing at all.
      if (distinct < 3) {
        w.__blankFrames++;
        w.__blankDetail = w.__blankDetail || [];
        if (w.__blankDetail.length < 8) {
          // Alpha 0 means genuinely cleared; alpha 255 with one colour means a
          // flat fill, which is a different bug with a different fix.
          w.__blankDetail.push({
            distinct,
            w: canvas.width,
            h: canvas.height,
            firstPx: [strip[0], strip[1], strip[2], strip[3]].join(","),
          });
        }
      }
    }
    w.__samplerHandle = requestAnimationFrame(tick);
  };
  tick();
};

async function run(label, viewport, toggle) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto(`${BASE}/play/the-quiet-room`, { waitUntil: "networkidle" });
  await page.waitForSelector("canvas.citymap-canvas", { timeout: 20000 });
  await page.waitForTimeout(1800);
  await page.getByRole("button", { name: "GET TO WORK" }).click().catch(() => {});
  await page.waitForTimeout(600);

  await page.evaluate(SAMPLER);
  await page.waitForTimeout(400);

  await toggle(page);

  await page.waitForTimeout(600);
  const { blank, sampled, detail } = await page.evaluate(() => {
    cancelAnimationFrame(window.__samplerHandle);
    return {
      blank: window.__blankFrames,
      sampled: window.__sampledFrames,
      detail: window.__blankDetail ?? [],
    };
  });

  log(`${label.padEnd(22)} ${blank} blank of ${sampled} frames sampled`);
  if (process.env.FLICKER_DETAIL) {
    for (const d of detail) {
      log(`    distinct=${d.distinct} canvas=${d.w}x${d.h} rgba=${d.firstPx}`);
    }
  }
  await page.close();
  return { blank, sampled, errors };
}

const results = [];

// --- phone: the sheet resizes the map container -----------------------------
results.push(
  await run("phone sheet x6", { width: 430, height: 900 }, async (page) => {
    const handle = page.locator('button[aria-label*="case panel"]');
    for (let i = 0; i < 6; i++) {
      await handle.click();
      await page.waitForTimeout(450);
    }
  }),
);

// --- desktop: the notebook and the corkboard --------------------------------
results.push(
  await run("desktop board x4", { width: 1500, height: 950 }, async (page) => {
    for (let i = 0; i < 4; i++) {
      await page.getByRole("button", { name: /THE BOARD/ }).click();
      await page.waitForTimeout(400);
      await page.getByRole("button", { name: /BACK TO THE CASE/ }).click();
      await page.waitForTimeout(400);
    }
  }),
);

// --- desktop: window resize, the coarsest possible resize -------------------
results.push(
  await run("window resize x4", { width: 1500, height: 950 }, async (page) => {
    for (const w of [1100, 1500, 900, 1400]) {
      await page.setViewportSize({ width: w, height: 950 });
      await page.waitForTimeout(500);
    }
  }),
);

// --- the map must not re-render because a clock ticked ----------------------
{
  const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
  await page.goto(`${BASE}/play/the-quiet-room`, { waitUntil: "networkidle" });
  await page.waitForSelector("canvas.citymap-canvas", { timeout: 20000 });
  await page.getByRole("button", { name: "GET TO WORK" }).click().catch(() => {});
  await page.waitForTimeout(1500);

  const before = await page.evaluate(() => window.__cityMapRenders ?? 0);
  // Long enough for the countdown to tick several times over.
  await page.waitForTimeout(6000);
  const after = await page.evaluate(() => window.__cityMapRenders ?? 0);

  log(`idle 6s${" ".repeat(15)}map re-rendered ${after - before} time(s)`);
  results.push({ blank: 0, sampled: 0, errors: [], idleRenders: after - before });
  await page.close();
}

await browser.close();

const idle = results.find((r) => r.idleRenders !== undefined)?.idleRenders ?? 0;
const totalBlank = results.reduce((a, r) => a + r.blank, 0);
const totalErrors = results.flatMap((r) => r.errors);

console.log("");
if (totalErrors.length) {
  console.log(`  ${totalErrors.length} page error(s):`);
  for (const e of totalErrors.slice(0, 5)) console.log(`    ${e.slice(0, 160)}`);
}

let failed = false;
if (totalBlank > 0) {
  console.log(`  FAIL — ${totalBlank} blank frame(s). The map flickers.`);
  failed = true;
}
if (idle > 0) {
  console.log(`  FAIL — the map re-rendered ${idle}x while merely sitting there.`);
  failed = true;
}
if (failed) process.exit(1);

console.log("  PASS — canvas never blank, and idle costs the map nothing.");
