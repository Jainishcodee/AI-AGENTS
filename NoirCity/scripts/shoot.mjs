/**
 * Screenshots the running dev server. Development aid for checking the canvas
 * map renders, since none of that is visible from a type check.
 *
 *   node scripts/shoot.mjs [out.png] [zoomSteps] [panX] [panY]
 */
import { chromium } from "playwright";

const out = process.argv[2] ?? "shot.png";
const zoomSteps = Number(process.argv[3] ?? 0);
const panX = Number(process.argv[4] ?? 0);
const panY = Number(process.argv[5] ?? 0);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });

const errors = [];
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
await page.waitForSelector("canvas.citymap-canvas", { timeout: 20000 });
await page.waitForTimeout(1200);

if (zoomSteps || panX || panY) {
  const box = await page.locator("canvas.citymap-canvas").boundingBox();
  const cx = box.x + box.width / 2 + panX;
  const cy = box.y + box.height / 2 + panY;
  await page.mouse.move(cx, cy);
  for (let i = 0; i < Math.abs(zoomSteps); i++) {
    await page.mouse.wheel(0, zoomSteps > 0 ? -300 : 300);
    await page.waitForTimeout(350);
  }
  await page.waitForTimeout(900);
}

// `clickLandmark` proves the whole chain: canvas hit test -> React state ->
// side panel -> travel cost. None of that is visible from a type check.
if (process.env.CLICK_LANDMARK) {
  const found = await page.evaluate(async (name) => {
    const city = await fetch("/city.json").then((r) => r.json());
    const loc = city.locations.find((l) => l.name === name);
    return loc ? { x: loc.x, y: loc.y } : null;
  }, process.env.CLICK_LANDMARK);
  if (!found) throw new Error(`no location named ${process.env.CLICK_LANDMARK}`);

  const pt = await page.evaluate(({ x, y }) => {
    const map = window.__cityMap;
    if (!map) return null;
    const p = map.latLngToContainerPoint({ lat: y, lng: x });
    const rect = map.getContainer().getBoundingClientRect();
    return { x: rect.left + p.x, y: rect.top + p.y };
  }, found);
  if (!pt) throw new Error("window.__cityMap missing - is this a dev build?");

  await page.mouse.click(pt.x, pt.y);
  await page.waitForTimeout(700);
}

await page.screenshot({ path: out });
console.log(`wrote ${out}`);
if (errors.length) {
  console.log(`\n${errors.length} console error(s):`);
  for (const e of errors.slice(0, 8)) console.log("  " + e);
} else {
  console.log("no console errors");
}

await browser.close();
