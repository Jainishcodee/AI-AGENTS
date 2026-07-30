/**
 * Where the artwork lives, and what to draw when it does not exist yet.
 *
 * Art is static files under `public/art/`, served straight off Cloudflare's edge
 * - no egress cost, no keys, no rate limits, and it versions with the code so a
 * deploy can never lose an image.
 *
 * Every slot has a deterministic procedural fallback. That matters more than it
 * sounds: it means the game is complete and shippable with zero artwork, and
 * each image can be dropped in later without a code change. Nothing ever renders
 * as a broken frame or a grey box.
 */

import available from "./available.json";

export type PlateKind = "cover" | "scene" | "portrait";

const ROOT = "/art";

/**
 * Which plates exist, written by `npm run art:slots`. Consulted before the
 * browser asks for one: with 59 slots and none filled, guessing would cost 59
 * failed requests per page load and drown any real error in the console.
 */
const EXISTS = new Set(available as string[]);

export function platePath(kind: PlateKind, id: string): string {
  return `${ROOT}/${kind}s/${id}.webp`;
}

export function plateExists(kind: PlateKind, id: string): boolean {
  return EXISTS.has(`${kind}s/${id}`);
}

/** Stable 32-bit hash, so the same id always draws the same fallback. */
export function plateSeed(id: string): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export interface PlateLook {
  /** Two-stop duotone, warm sodium into cold shadow. */
  from: string;
  to: string;
  /** Angle of the light, degrees. */
  angle: number;
  /** Whether to draw slats (blinds), a lamp glow, or plain haze. */
  motif: "blinds" | "lamp" | "haze";
}

// Light ends are deliberately well above the page background. An empty plate
// has to read as a photograph nobody has replaced yet, not as a failed request.
const PALETTES: Array<[string, string]> = [
  ["#8a6a44", "#14110f"], // tobacco and night
  ["#7d7156", "#12110e"], // paper and ink
  ["#8c5a42", "#151010"], // brick and soot
  ["#4f7080", "#0d1114"], // river and fog
  ["#a07444", "#171110"], // sodium and tar
  ["#5c6a80", "#0e1014"], // rain and slate
];

const MOTIFS: PlateLook["motif"][] = ["blinds", "lamp", "haze"];

/**
 * A look derived entirely from the id. Two different locations never collide by
 * accident, and the same location looks the same on every machine.
 */
export function plateLook(id: string): PlateLook {
  const seed = plateSeed(id);
  const [from, to] = PALETTES[seed % PALETTES.length];
  return {
    from,
    to,
    angle: 20 + ((seed >> 8) % 140),
    motif: MOTIFS[(seed >> 16) % MOTIFS.length],
  };
}
