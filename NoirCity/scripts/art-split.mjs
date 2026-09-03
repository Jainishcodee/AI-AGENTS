/**
 * Cuts a contact sheet back into its ten slots.
 *
 * The mapping from cell to slot is read from the manifest `art-sheet.mjs` wrote,
 * not inferred - nothing in the returned pixels says which room is which, and
 * guessing would silently file the morgue as somebody's flat.
 *
 *   npm run art:split -- sheet.png                 # newest manifest
 *   npm run art:split -- sheet.png --sheet scenes-1
 *   npm run art:split -- sheet.png --gutter 8      # if the model drew gutters
 *   npm run art:split -- sheet.png --trim 4        # shave every cell edge
 */
import sharp from "sharp";
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const SHEETS = join("art-raw", ".sheets");

const args = process.argv.slice(2);
const file = args.find((a) => !a.startsWith("--"));
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? Number(args[i + 1]) : fallback;
};
const named = args.indexOf("--sheet") >= 0 ? args[args.indexOf("--sheet") + 1] : null;

if (!file || !existsSync(file)) {
  console.error("  usage: npm run art:split -- <sheet-image> [--sheet name] [--gutter px] [--trim px]");
  process.exit(1);
}

function newestManifest() {
  const files = readdirSync(SHEETS).filter((f) => f.endsWith(".json"));
  if (!files.length) return null;
  return files
    .map((f) => ({ f, t: statSync(join(SHEETS, f)).mtimeMs }))
    .sort((a, b) => b.t - a.t)[0].f;
}

const manifestFile = named ? `${named}.json` : newestManifest();
if (!manifestFile || !existsSync(join(SHEETS, manifestFile))) {
  console.error("  no sheet manifest. Run `npm run art:sheet -- <kind>` first.");
  process.exit(1);
}

const { kind, cols, rows, ids } = JSON.parse(
  readFileSync(join(SHEETS, manifestFile), "utf8"),
);

const gutter = flag("gutter", 0);
const trim = flag("trim", 0);

const meta = await sharp(file).metadata();
// Gutters eat into the picture area, so the cell size is what is left after
// them - getting this wrong by a few pixels slides every cell after the first.
const cellW = Math.floor((meta.width - gutter * (cols - 1)) / cols);
const cellH = Math.floor((meta.height - gutter * (rows - 1)) / rows);

console.log(`\n  ${manifestFile}: ${cols} x ${rows}, cells ${cellW}x${cellH} from ${meta.width}x${meta.height}`);
if (cellW - trim * 2 < 200 || cellH - trim * 2 < 200) {
  console.log(`  ! cells are small — the plates will be soft. A larger sheet would help.`);
}

const outDir = join("art-raw", kind);
mkdirSync(outDir, { recursive: true });

let n = 0;
for (let r = 0; r < rows; r++) {
  for (let c = 0; c < cols; c++) {
    const id = ids[n];
    if (!id) break;
    const out = join(outDir, `${id}.png`);
    await sharp(file)
      .extract({
        left: c * (cellW + gutter) + trim,
        top: r * (cellH + gutter) + trim,
        width: cellW - trim * 2,
        height: cellH - trim * 2,
      })
      .png()
      .toFile(out);
    console.log(`   ${String(n + 1).padStart(2)}. ${out}`);
    n++;
  }
}

console.log(`\n  ${n} cell(s) written. Now: npm run art:build\n`);
