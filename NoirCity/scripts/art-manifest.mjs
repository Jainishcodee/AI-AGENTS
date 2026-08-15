/**
 * Lists every image slot the game can use, whether it is filled, and the prompt
 * to generate it with.
 *
 * Slots are derived from the case files rather than kept in a hand-written list,
 * so adding a location to a case adds its slot here automatically and nothing
 * can silently go missing.
 *
 *   node scripts/art-manifest.mjs            # status
 *   node scripts/art-manifest.mjs --prompts  # regenerate docs/art-prompts.md
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const CASES = "cases";
const ART = join("public", "art");

const city = JSON.parse(readFileSync(join("public", "city.json"), "utf8"));
const byId = new Map(city.locations.map((l) => [l.id, l]));
const boroughs = new Map(city.boroughs.map((b) => [b.id, b]));

/**
 * The look every generated plate is asked for.
 *
 * This said "1984 film noir" and nothing else, which produced Los Angeles. The
 * city underneath it is not Los Angeles - the generator gives Marrowgate a
 * winding old core, tenement lanes and a civic quarter, and the cases are full
 * of solicitors, inquests and prescription books. So the plates were fighting
 * their own setting.
 *
 * The setting stays 1984 - the cases turn on answering machines and laboratory
 * reports and cannot move - but the city it happens in never stopped looking
 * Victorian. Gaslight beside sodium, soot brick, fog off the Ebb. That is
 * the register the whole thing has been reaching for, and it is what makes an
 * occult case read as ordinary business rather than as a costume.
 *
 * Monochrome is not a style choice here: `build-art.mjs` greys every source and
 * maps it onto the game's own paper-on-black duotone, so asking for colour
 * would only give the grader something to throw away. Asking for monochrome up
 * front gets better tonal separation out of the generator.
 */
const WORLD =
  "Marrowgate 1984 - a city that never stopped looking Victorian. Gaslight beside sodium, wet cobbles, soot-blackened brick, ornate ironwork, heavy furniture, patterned wallpaper, fog off the river. A quiet occult undertone: this is a world where a seance is an ordinary evening's business.";

/**
 * The lighting doctrine, and the part that actually makes the picture.
 *
 * Taken from the reference frame: ONE practical source visible inside the shot -
 * a hanging lamp, a candle, a window - doing all the work, and everything
 * outside its reach falling to true black rather than to grey. Most of the
 * canvas is empty. That emptiness is the composition, not a failure to light it.
 *
 * This is the single most useful instruction in the whole prompt. A generator
 * told only "noir" returns evenly-lit grey; told "one practical, everything else
 * black" it returns the frame we want.
 */
const LIGHT =
  "Lit by ONE practical light source visible in the frame, doing all the work. Everything beyond its reach falls to true black, not grey - most of the image is empty shadow, and that emptiness is the composition. Deep foreground darkness framing the shot.";

/** Film stock. Monochrome is load-bearing - see the note above. */
const STOCK =
  "Monochrome, fine 35mm grain, high contrast, no text, no watermark, no border, no letterboxing.";

/**
 * How the camera behaves.
 *
 * Locked off and observational, at eye level, symmetrical. The reference frame
 * works because the camera is a witness sitting in the room rather than a
 * participant moving through it - which is exactly the register a detective game
 * wants, since the player is the one who has to notice things.
 */
const CAMERA =
  "Locked-off camera at eye level, static and observational, symmetrical centred staging, deep space receding into shadow.";

/**
 * People.
 *
 * Only in covers and scenes, and always turned away. A face looking back makes
 * the picture about that person; a figure seen from behind keeps it about the
 * room, which is what the player is meant to be reading. Portraits are the
 * deliberate exception and get their own clause - an identity photograph that
 * would not face the camera is not an identity photograph.
 */
const TURNED_AWAY =
  "Any figures are seen from behind or in silhouette, faces never visible, never looking at the camera.";

const slots = [];

for (const dir of readdirSync(CASES)) {
  const file = join(CASES, dir, "case.json");
  if (!existsSync(file)) continue;
  const c = JSON.parse(readFileSync(file, "utf8"));

  slots.push({
    kind: "covers",
    id: c.id,
    label: c.title,
    prompt: `The opening frame of a detective case titled "${c.title}". ${firstSentence(c.brief)} A wide cinematic interior, 21:9, the whole room in one shot. ${LIGHT} ${TURNED_AWAY} ${CAMERA} ${WORLD} ${STOCK}`,
  });

  for (const loc of c.locations) {
    const place = byId.get(loc.cityLocationId);
    if (!place) continue;
    const borough = boroughs.get(place.boroughId);
    slots.push({
      kind: "scenes",
      id: loc.cityLocationId,
      label: `${place.name} — ${c.title}`,
      prompt: `${place.name}, a ${place.type} on ${place.address} in ${borough?.name ?? "Marrowgate"}. ${firstSentence(loc.description)} A wide interior, 16:9, empty of people - the room as somebody walking in would first see it. ${LIGHT} ${CAMERA} ${WORLD} ${STOCK}`,
    });
  }

  for (const s of c.suspects) {
    slots.push({
      kind: "portraits",
      id: s.id,
      label: `${s.name} — ${c.title}`,
      prompt: `Head and shoulders photograph of ${s.name}, ${s.occupation}, Marrowgate 1984. Facing camera, neutral expression, plain dark backdrop, 4:5 portrait. Lit from one side, the other side of the face falling into shadow. ${WORLD} ${STOCK}`,
    });
  }
  for (const n of c.npcs ?? []) {
    slots.push({
      kind: "portraits",
      id: n.id,
      label: `${n.name} — ${c.title}`,
      prompt: `Head and shoulders photograph of ${n.name}, ${n.role}, Marrowgate 1984. Facing camera, neutral expression, plain dark backdrop, 4:5 portrait. Lit from one side, the other side of the face falling into shadow. ${WORLD} ${STOCK}`,
    });
  }
}

function firstSentence(text) {
  const s = String(text).split(/(?<=[.!?])\s/)[0] ?? "";
  return s.length > 220 ? `${s.slice(0, 217)}...` : s;
}

// Two cases can share a location; the plate is the place, not the case.
const unique = [...new Map(slots.map((s) => [`${s.kind}/${s.id}`, s])).values()];
const filled = unique.filter((s) => existsSync(join(ART, s.kind, `${s.id}.webp`)));

// Which plates actually exist, so the client never requests one that does not.
// Without this every unfilled slot costs a 404 per page load — 59 of them today
// — and buries real errors in the console.
writeFileSync(
  join("lib", "art", "available.json"),
  `${JSON.stringify(
    filled.map((s) => `${s.kind}/${s.id}`).sort(),
    null,
    1,
  )}\n`,
);

if (process.argv.includes("--prompts")) {
  const lines = [
    "# Artwork slots",
    "",
    "Generated by `node scripts/art-manifest.mjs --prompts`. Do not edit by hand —",
    "it is derived from the case files, so adding a location adds its slot here.",
    "",
    "## How to fill one",
    "",
    "1. Generate the image with the prompt below (Midjourney, SDXL, whatever).",
    "2. Save it as `art-raw/<kind>/<id>.<png|jpg|webp>` — **the filename is the id**.",
    "3. `npm run art:build`",
    "",
    "The build greys it, maps it onto the game's duotone, and writes",
    "`public/art/<kind>/<id>.webp`. Every source ends up in the same look, which is",
    "what stops a mixed set from looking borrowed.",
    "",
    "## The look",
    "",
    "Every prompt below is built from four fixed clauses. If you are generating by",
    "hand, or steering a model that ignores part of a long prompt, these are the",
    "ones that matter, in order:",
    "",
    "**1. One light.** A single practical source *visible in the frame* — a hanging",
    "lamp, a candle, a window — doing all the work, and everything beyond its reach",
    "falling to **true black, not grey**. Most of the picture is empty shadow, and",
    "that emptiness is the composition. This is the single most useful instruction",
    "here: a model told only \"noir\" returns evenly-lit grey, and a model told this",
    "returns the frame we want.",
    "",
    "**2. Faces turned away.** In covers and scenes, figures are seen from behind or",
    "in silhouette, never looking back. A face looking at camera makes the picture",
    "about that person; a figure from behind keeps it about the room, which is what",
    "the player is meant to be reading. Portraits are the deliberate exception.",
    "",
    "**3. A locked-off camera.** Eye level, static, symmetrical, deep space",
    "receding into shadow. The camera is a witness sitting in the room, not a",
    "participant moving through it.",
    "",
    "**4. Marrowgate, 1984 — a city that never stopped looking Victorian.** Gaslight",
    "beside sodium, soot brick, heavy furniture, patterned wallpaper, fog off the",
    "Ebb. A world where a seance is an ordinary evening's business.",
    "",
    "Monochrome throughout, and that is not a style preference: `npm run art:build`",
    "greys every source and maps it onto the game's own paper-on-black duotone, so",
    "colour is only something the grader has to throw away. Asking for monochrome up",
    "front gets better tonal separation out of the model.",
    "",
    "Ask for **no letterboxing** — the build crops to the slot's aspect ratio, and",
    "baked-in black bars get cropped as if they were picture.",
    "",
    "Any slot left empty draws a deterministic procedural plate instead, so the",
    "game is complete and shippable with none of this done.",
    "",
    `**${filled.length} of ${unique.length} slots filled.**`,
    "",
  ];

  for (const kind of ["covers", "scenes", "portraits"]) {
    const group = unique.filter((s) => s.kind === kind);
    if (!group.length) continue;
    lines.push(`## ${kind}`, "");
    for (const s of group) {
      const done = existsSync(join(ART, s.kind, `${s.id}.webp`));
      lines.push(
        `### \`${s.id}\`${done ? " ✅" : ""}`,
        "",
        `*${s.label}*`,
        "",
        "```",
        s.prompt,
        "```",
        "",
      );
    }
  }

  writeFileSync(join("docs", "art-prompts.md"), lines.join("\n"));
  console.log(`  wrote docs/art-prompts.md — ${unique.length} slots`);
} else {
  for (const kind of ["covers", "scenes", "portraits"]) {
    const group = unique.filter((s) => s.kind === kind);
    const have = group.filter((s) => existsSync(join(ART, s.kind, `${s.id}.webp`)));
    console.log(`  ${kind.padEnd(10)} ${have.length}/${group.length}`);
  }
  console.log(
    `\n  ${filled.length}/${unique.length} filled. The rest draw procedural plates.`,
  );
}
