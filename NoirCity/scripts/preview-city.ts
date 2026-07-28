/**
 * Rasterises content/city.json to a PNG so the generated geometry can be eyeballed
 * without booting the app. Development aid only - the real map is drawn by the
 * Leaflet renderer in components/map.
 *
 *   npx tsx scripts/preview-city.ts
 */

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import sharp from "sharp";
import { parseCity, type Point } from "../lib/engine/citySchema";

const OUT_WIDTH = 1600;

const PALETTE = {
  water: "#101d24",
  ink: "#0b0c0e",
  block: "#1a1a1d",
  blockEdge: "#242427",
  park: "#16221a",
  parkEdge: "#22301f",
  yard: "#1e1c18",
  yardEdge: "#2b2721",
  lane: "#3a3a3f",
  street: "#4c4c52",
  avenue: "#6d6a63",
  bridge: "#8a7f6a",
  rail: "#55504a",
  pin: "#c9a227",
  landmark: "#e2503f",
  label: "#8e8a80",
};

function main() {
  const city = parseCity(
    JSON.parse(readFileSync(join(process.cwd(), "public", "city.json"), "utf8")),
  );
  const [w, h] = city.size;
  const scale = OUT_WIDTH / w;
  const outHeight = Math.round(h * scale);

  // City space has y increasing north; SVG has y increasing down.
  const px = (p: Point) => `${(p[0] * scale).toFixed(1)},${((h - p[1]) * scale).toFixed(1)}`;
  const path = (pts: Point[]) => pts.map(px).join(" ");

  const parts: string[] = [];
  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${OUT_WIDTH}" height="${outHeight}" viewBox="0 0 ${OUT_WIDTH} ${outHeight}">`,
    `<rect width="100%" height="100%" fill="${PALETTE.ink}"/>`,
  );

  const blockFill = { built: PALETTE.block, park: PALETTE.park, yard: PALETTE.yard };
  const blockEdge = { built: PALETTE.blockEdge, park: PALETTE.parkEdge, yard: PALETTE.yardEdge };
  for (const b of city.blocks) {
    parts.push(
      `<polygon points="${path(b.polygon)}" fill="${blockFill[b.kind]}" stroke="${blockEdge[b.kind]}" stroke-width="0.4"/>`,
    );
  }

  parts.push(
    `<polygon points="${path(city.river.polygon)}" fill="${PALETTE.water}"/>`,
  );

  for (const rw of city.railways) {
    parts.push(
      `<polyline points="${path(rw.points)}" fill="none" stroke="${PALETTE.rail}" stroke-width="2.2" stroke-dasharray="7 4"/>`,
    );
  }

  const widthFor = { avenue: 2.6, street: 1.5, lane: 0.9 } as const;
  const colorFor = {
    avenue: PALETTE.avenue,
    street: PALETTE.street,
    lane: PALETTE.lane,
  } as const;
  for (const s of city.streets) {
    parts.push(
      `<polyline points="${path(s.points)}" fill="none" stroke="${colorFor[s.kind]}" stroke-width="${widthFor[s.kind]}" stroke-linecap="round"/>`,
    );
  }

  for (const br of city.bridges) {
    parts.push(
      `<polyline points="${path(br.points)}" fill="none" stroke="${PALETTE.bridge}" stroke-width="${br.kind === "bridge" ? 4 : 2}" stroke-dasharray="${br.kind === "ferry" ? "6 5" : "none"}" stroke-linecap="round"/>`,
    );
  }

  for (const l of city.locations) {
    if (l.isLandmark) continue;
    parts.push(
      `<circle cx="${(l.x * scale).toFixed(1)}" cy="${((h - l.y) * scale).toFixed(1)}" r="1.5" fill="${PALETTE.pin}" opacity="0.7"/>`,
    );
  }

  for (const l of city.locations) {
    if (!l.isLandmark) continue;
    const cx = (l.x * scale).toFixed(1);
    const cy = ((h - l.y) * scale).toFixed(1);
    parts.push(
      `<circle cx="${cx}" cy="${cy}" r="3.4" fill="${PALETTE.landmark}"/>`,
      `<text x="${cx}" y="${(Number(cy) - 7).toFixed(1)}" fill="#d8d2c4" font-family="Georgia,serif" font-size="9" text-anchor="middle">${l.name.replace(/&/g, "&amp;")}</text>`,
    );
  }

  for (const b of city.boroughs) {
    const cx = b.polygon.reduce((a, p) => a + p[0], 0) / b.polygon.length;
    const cy = b.polygon.reduce((a, p) => a + p[1], 0) / b.polygon.length;
    parts.push(
      `<text x="${(cx * scale).toFixed(1)}" y="${((h - cy) * scale).toFixed(1)}" fill="${PALETTE.label}" font-family="Georgia,serif" font-size="17" letter-spacing="3" text-anchor="middle">${b.name.toUpperCase()}</text>`,
    );
  }

  parts.push("</svg>");
  const svg = parts.join("\n");

  const outPath = join(process.cwd(), "content", "city-preview.png");
  sharp(Buffer.from(svg))
    .png()
    .toFile(outPath)
    .then(() => console.log(`Wrote ${outPath} (${OUT_WIDTH}x${outHeight})`))
    .catch((err) => {
      writeFileSync(join(process.cwd(), "content", "city-preview.svg"), svg);
      console.error("Rasterise failed, wrote SVG instead:", err.message);
    });
}

main();
