/**
 * Grades raw artwork into the game's look.
 *
 * Drop anything into `art-raw/<kind>s/<id>.<ext>` and run this. Whatever the
 * source — a photograph, an AI generation, a scan — comes out the far side as
 * the same duotone with the same grain, so a set assembled from three different
 * generators still reads as one world. That consistency is most of what makes
 * mixed artwork look deliberate rather than borrowed.
 *
 *   npm run art:build
 */
import sharp from "sharp";
import { existsSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { join, parse } from "node:path";

const RAW = "art-raw";
const OUT = join("public", "art");

/** Warm paper to cold ink. Same two ends as the map palette. */
const DUOTONE = { light: [232, 224, 207], dark: [12, 11, 14] };

const KINDS = {
  covers: { width: 1200, height: 500 },
  scenes: { width: 1000, height: 562 },
  portraits: { width: 512, height: 640 },
};

/** A duotone LUT: map luminance onto the line between two colours. */
function duotoneLut() {
  const lut = Buffer.alloc(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    for (let c = 0; c < 3; c++) {
      lut[i * 3 + c] = Math.round(
        DUOTONE.dark[c] + (DUOTONE.light[c] - DUOTONE.dark[c]) * t,
      );
    }
  }
  return lut;
}

async function grade(input, output, { width, height }) {
  const lut = duotoneLut();

  // Greyscale first so the duotone maps luminance rather than whatever hue the
  // generator happened to pick; then linear() lifts the blacks a little so the
  // grain has something to sit on.
  const base = await sharp(input)
    .resize(width, height, { fit: "cover", position: "attention" })
    .greyscale()
    .linear(1.08, -8)
    .raw()
    .toBuffer({ resolveWithObject: true });

  const { data, info } = base;
  const out = Buffer.alloc(info.width * info.height * 3);
  for (let p = 0; p < info.width * info.height; p++) {
    const v = data[p * info.channels];
    out[p * 3] = lut[v * 3];
    out[p * 3 + 1] = lut[v * 3 + 1];
    out[p * 3 + 2] = lut[v * 3 + 2];
  }

  await sharp(out, { raw: { width: info.width, height: info.height, channels: 3 } })
    .webp({ quality: 82 })
    .toFile(output);
}

if (!existsSync(RAW)) {
  console.log(
    `  ${RAW}/ does not exist yet.\n\n` +
      `  Create it and drop files in:\n` +
      Object.keys(KINDS)
        .map((k) => `    ${RAW}/${k}/`)
        .join("\n") +
      `\n\n  Filenames become ids — see docs/art-prompts.md for the list.\n`,
  );
  process.exit(0);
}

let graded = 0;

for (const [kind, size] of Object.entries(KINDS)) {
  const dir = join(RAW, kind);
  if (!existsSync(dir) || !statSync(dir).isDirectory()) continue;

  const outDir = join(OUT, kind);
  mkdirSync(outDir, { recursive: true });

  for (const file of readdirSync(dir)) {
    if (!/\.(png|jpe?g|webp|tiff?)$/i.test(file)) continue;
    const { name } = parse(file);
    const output = join(outDir, `${name}.webp`);
    await grade(join(dir, file), output, size);
    console.log(`  ${kind.padEnd(10)} ${name}`);
    graded++;
  }
}

console.log(
  graded
    ? `\n  ${graded} plate(s) graded into public/art/`
    : `\n  Nothing to grade. Drop images into ${RAW}/<kind>/ first.`,
);
