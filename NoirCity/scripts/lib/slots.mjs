/**
 * Every image slot the game can use, and the prompt that would fill it.
 *
 * Shared by `art-manifest.mjs` (which documents them) and `art-sheet.mjs`
 * (which batches ten of them into one contact sheet). This lived inside the
 * manifest script and was duplicated the moment a second tool needed it, which
 * is how a prompt vocabulary drifts.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const CASES = "cases";
export const ART = join("public", "art");

const city = JSON.parse(readFileSync(join("public", "city.json"), "utf8"));
const byId = new Map(city.locations.map((l) => [l.id, l]));
const boroughs = new Map(city.boroughs.map((b) => [b.id, b]));

/** Target aspect of each kind, as the build will crop it. */
export const KIND_ASPECT = {
  covers: 21 / 9,
  scenes: 16 / 9,
  portraits: 4 / 5,
};

// ---------------------------------------------------------------------------
// The look
// ---------------------------------------------------------------------------

const WORLD =
  "Marrowgate 1984 - a city that never stopped looking Victorian. Gaslight beside sodium, wet cobbles, soot-blackened brick, ornate ironwork, heavy furniture, patterned wallpaper, fog off the river. A quiet occult undertone: this is a world where a seance is an ordinary evening's business.";

/**
 * The lighting doctrine, and the part that actually makes the picture.
 *
 * ONE practical source visible inside the shot - a hanging lamp, a candle, a
 * window - doing all the work, and everything outside its reach falling to true
 * black rather than to grey. Most of the canvas is empty, and that emptiness is
 * the composition.
 *
 * This is the single most useful instruction in the whole prompt. A model told
 * only "noir" returns evenly-lit grey; told this, it returns the frame we want.
 */
const LIGHT =
  "Lit by ONE practical light source visible in the frame, doing all the work. Everything beyond its reach falls to true black, not grey - most of the image is empty shadow, and that emptiness is the composition. Deep foreground darkness framing the shot.";

/** Film stock. Monochrome is load-bearing: the build greys everything anyway. */
const STOCK =
  "Monochrome, fine 35mm grain, high contrast, no text, no watermark, no border, no letterboxing.";

/**
 * How the camera behaves. Locked off and observational - a witness sitting in
 * the room rather than a participant moving through it, which is the register a
 * detective game wants, since the player is the one who has to notice things.
 */
const CAMERA =
  "Locked-off camera at eye level, static and observational, symmetrical centred staging, deep space receding into shadow.";

/**
 * People, in covers and scenes only, and always turned away. A face looking
 * back makes the picture about that person; a figure seen from behind keeps it
 * about the room. Portraits are the deliberate exception and get their own
 * clause - an identity photograph that would not face the camera is not one.
 */
const TURNED_AWAY =
  "Any figures are seen from behind or in silhouette, faces never visible, never looking at the camera.";

export const CLAUSES = { WORLD, LIGHT, STOCK, CAMERA, TURNED_AWAY };

// ---------------------------------------------------------------------------
// Prose helpers
// ---------------------------------------------------------------------------

/** Abbreviations whose full stop does not end a sentence. */
const ABBREV = new Set([
  "dr",
  "mr",
  "mrs",
  "ms",
  "messrs",
  "st",
  "sgt",
  "insp",
  "supt",
  "no",
  "jr",
  "sr",
  "vs",
  "etc",
  "co",
  "ltd",
]);

/**
 * The first real sentence of a description.
 *
 * Scanned rather than split on a regex, because the naive version cut
 * "where Dr. Vane keeps consulting rooms" down to "where Dr." and handed the
 * model a fragment plus a stray article. Abbreviations are common in this
 * writing - doctors, saints, street numbers - so the check has to be explicit.
 */
function firstSentence(text) {
  const t = String(text ?? "").trim();
  const clip = (x) => (x.length > 220 ? `${x.slice(0, 217)}...` : x);
  for (let i = 0; i < t.length - 1; i++) {
    if (!".!?".includes(t[i])) continue;
    if (!/\s/.test(t[i + 1])) continue;
    const word = (t.slice(0, i).match(/([A-Za-z]+)$/) || [])[1] || "";
    if (ABBREV.has(word.toLowerCase())) continue;
    return clip(t.slice(0, i + 1));
  }
  return clip(t);
}

/**
 * Drops a place's own name off the front of its description.
 *
 * Case descriptions open by naming the place, and the city now carries the same
 * name - so a subject line said it twice, which tells a model nothing and costs
 * a tenth of a contact sheet's prompt budget.
 *
 * Returns empty when what is left is a continuation rather than a sentence:
 * "where Dr. Vane keeps rooms" reads as a fragment on its own, and the caller
 * falls back to the city's own blurb instead.
 */
function withoutName(text, name) {
  const t = String(text ?? "").trim();
  if (!t.toLowerCase().startsWith(name.toLowerCase())) return t;
  const rest = t.slice(name.length).replace(/^[\s,.:;–—-]+/, "");
  return /^[a-z]/.test(rest) ? "" : rest;
}

/** "a office" reads as a typo to a language model as much as to a person. */
function article(word) {
  return /^[aeiou]/i.test(String(word)) ? "an" : "a";
}

// ---------------------------------------------------------------------------
// The slots
// ---------------------------------------------------------------------------

export const slots = [];

for (const dir of readdirSync(CASES)) {
  const file = join(CASES, dir, "case.json");
  if (!existsSync(file)) continue;
  const c = JSON.parse(readFileSync(file, "utf8"));

  slots.push({
    kind: "covers",
    id: c.id,
    label: c.title,
    subject: `The opening frame of a detective case titled "${c.title}". ${firstSentence(c.brief)} A wide cinematic interior, the whole room in one shot, figures seen only from behind.`,
    prompt: `The opening frame of a detective case titled "${c.title}". ${firstSentence(c.brief)} A wide cinematic interior, 21:9, the whole room in one shot. ${LIGHT} ${TURNED_AWAY} ${CAMERA} ${WORLD} ${STOCK}`,
  });

  for (const loc of c.locations) {
    const place = byId.get(loc.cityLocationId);
    if (!place) continue;
    const borough = boroughs.get(place.boroughId);
    const said =
      firstSentence(withoutName(loc.description, place.name)) ||
      firstSentence(place.blurb);
    slots.push({
      kind: "scenes",
      id: loc.cityLocationId,
      label: `${place.name} — ${c.title}`,
      subject: `${place.name}, ${article(place.type)} ${place.type} in ${borough?.name ?? "Marrowgate"}. ${said} A wide interior, empty of people.`,
      prompt: `${place.name}, ${article(place.type)} ${place.type} on ${place.address} in ${borough?.name ?? "Marrowgate"}. ${said} A wide interior, 16:9, empty of people - the room as somebody walking in would first see it. ${LIGHT} ${CAMERA} ${WORLD} ${STOCK}`,
    });
  }

  for (const s of c.suspects) {
    slots.push({
      kind: "portraits",
      id: s.id,
      label: `${s.name} — ${c.title}`,
      subject: `${s.name}, ${s.occupation} - head and shoulders, facing camera, neutral expression, plain dark backdrop, lit from one side with the other side of the face in shadow.`,
      prompt: `Head and shoulders photograph of ${s.name}, ${s.occupation}, Marrowgate 1984. Facing camera, neutral expression, plain dark backdrop, 4:5 portrait. Lit from one side, the other side of the face falling into shadow. ${WORLD} ${STOCK}`,
    });
  }

  for (const n of c.npcs ?? []) {
    slots.push({
      kind: "portraits",
      id: n.id,
      label: `${n.name} — ${c.title}`,
      subject: `${n.name}, ${n.role} - head and shoulders, facing camera, neutral expression, plain dark backdrop, lit from one side with the other side of the face in shadow.`,
      prompt: `Head and shoulders photograph of ${n.name}, ${n.role}, Marrowgate 1984. Facing camera, neutral expression, plain dark backdrop, 4:5 portrait. Lit from one side, the other side of the face falling into shadow. ${WORLD} ${STOCK}`,
    });
  }
}

/** Two cases can share a location; the plate is the place, not the case. */
export const uniqueSlots = [
  ...new Map(slots.map((s) => [`${s.kind}/${s.id}`, s])).values(),
];

export const isFilled = (s) => existsSync(join(ART, s.kind, `${s.id}.webp`));

/** Slots of one kind that still have no artwork, in a stable order. */
export function unfilled(kind) {
  return uniqueSlots.filter((s) => s.kind === kind && !isFilled(s));
}
