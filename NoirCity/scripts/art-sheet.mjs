/**
 * Batches empty slots into a single contact-sheet prompt.
 *
 * One generation instead of ten. The catch is that the model returns one image
 * with ten pictures inside it, so this also writes down which slot belongs in
 * which cell - `art-split.mjs` needs that mapping and cannot recover it from
 * the pixels.
 *
 *   npm run art:sheet -- scenes        # next 10 unfilled scenes
 *   npm run art:sheet -- portraits 6   # six of them
 *   npm run art:sheet -- plan          # what is left, and how many sheets
 */
import { mkdirSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { KIND_ASPECT, CLAUSES, unfilled } from "./lib/slots.mjs";

const SHEETS = join("art-raw", ".sheets");
const BATCH = 10;

const kind = process.argv[2];
const want = Number(process.argv[3] ?? BATCH);

// --- the plan ---------------------------------------------------------------

if (kind === "plan") {
  console.log("");
  for (const k of ["covers", "scenes", "portraits"]) {
    const n = unfilled(k).length;
    if (!n) {
      console.log(`  ${k.padEnd(10)} all filled`);
      continue;
    }
    if (k === "covers") {
      console.log(`  ${k.padEnd(10)} ${n} left - one at a time, see docs/art-prompts.md`);
      continue;
    }
    const sheets = Math.ceil(n / BATCH);
    const sizes = Array.from({ length: sheets }, (_, i) =>
      Math.min(BATCH, n - i * BATCH),
    );
    console.log(
      `  ${k.padEnd(10)} ${n} left - ${sheets} sheet(s) of ${sizes.join(" + ")}`,
    );
  }
  console.log("\n  Run `npm run art:sheet -- scenes` for the next batch.\n");
  process.exit(0);
}

if (!KIND_ASPECT[kind]) {
  console.error("  usage: npm run art:sheet -- <scenes|portraits|plan> [count]");
  process.exit(1);
}

/**
 * Covers are generated one at a time, and the tool refuses rather than trusting
 * anyone to remember why.
 *
 * A cover is the largest image in the game and the first thing a player sees -
 * it fills the opening screen at full width. Ten cells sharing one canvas come
 * back about a third the width they would be alone, which is invisible on a
 * scene and very visible on a cover.
 */
if (kind === "covers") {
  console.error(`
  Covers are not batched.

  A cover fills the whole opening screen, so it needs a canvas to itself.
  There are only three, and their prompts are in docs/art-prompts.md under
  "## covers" - generate each on its own, then:

     art-raw/covers/<case-id>.png
     npm run art:build
`);
  process.exit(1);
}

// --- the grid ---------------------------------------------------------------

/**
 * How to arrange the cells.
 *
 * Cell aspect is fixed by the kind, so the only choice is the arrangement - and
 * that decides the shape of the whole sheet. Squarest wins: generators output
 * roughly square canvases, so a 5x2 sheet of portraits uses pixels a 1x10 strip
 * would waste, and every cell comes back bigger.
 *
 * A partial last row is allowed. Requiring an exact factorisation looked tidier
 * and fell apart on a batch of seven, where the only options are a 1-wide strip
 * and a 7-wide one.
 */
function grid(n, cellAspect) {
  let best = null;
  for (let cols = 1; cols <= n; cols++) {
    const rows = Math.ceil(n / cols);
    const overall = (cols * cellAspect) / rows;
    const score = Math.abs(Math.log(overall)) + (cols * rows - n) * 0.08;
    if (!best || score < best.score) best = { cols, rows, score };
  }
  return best;
}

const picked = unfilled(kind).slice(0, want);
if (!picked.length) {
  console.log(`  nothing unfilled in ${kind}.`);
  process.exit(0);
}

const { cols, rows } = grid(picked.length, KIND_ASPECT[kind]);

// Shared clauses stated once at the end rather than repeated per cell: ten
// copies of the lighting doctrine is most of the prompt's budget spent saying
// the same thing, and models weight a repeated instruction oddly.
const prompt = [
  `A contact sheet: a ${cols} x ${rows} grid of exactly ${picked.length} separate film frames.`,
  "Cells are equal size, edge to edge, with NO gutters, NO borders, NO captions, NO numbers, and NO text anywhere.",
  "Each cell is a different subject. Reading left to right, top to bottom:",
  "",
  picked.map((s, i) => `${i + 1}. ${s.subject}`).join("\n"),
  "",
  `Every frame shares the same look. ${CLAUSES.LIGHT} ${CLAUSES.CAMERA} ${CLAUSES.WORLD} ${CLAUSES.STOCK}`,
].join("\n");

mkdirSync(SHEETS, { recursive: true });
let seq = 1;
while (existsSync(join(SHEETS, `${kind}-${seq}.json`))) seq++;
const name = `${kind}-${seq}`;

writeFileSync(
  join(SHEETS, `${name}.json`),
  `${JSON.stringify({ kind, cols, rows, ids: picked.map((s) => s.id) }, null, 2)}\n`,
);

// The prompt goes in its own file. "Copy the whole file" has no start or end to
// get wrong; a prompt printed into a terminal next to a slot list does.
const promptFile = join(SHEETS, `${name}.txt`);
writeFileSync(promptFile, `${prompt}\n`);

const left = unfilled(kind).length - picked.length;

console.log(`\n  sheet ${name} - ${cols} x ${rows}, ${picked.length} cells\n`);
picked.forEach((s, i) => console.log(`   ${String(i + 1).padStart(2)}. ${s.label}`));

console.log(`
  THE PROMPT IS THIS WHOLE FILE - copy all of it, top to bottom:

     ${promptFile}

  Then save the image anywhere and run:

     npm run art:split -- <image>
     npm run art:build
`);

console.log(
  left > 0
    ? `  ${left} more ${kind} after this. Same command again for the next batch.\n`
    : `  That is every ${kind} slot.\n`,
);
