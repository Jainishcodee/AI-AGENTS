import type { CaseIndex, KeyPoint } from "./caseSchema";

/**
 * Marking a written accusation.
 *
 * Two jobs, and they are deliberately separate. Naming the killer is a lookup -
 * the player types a name and it either is or is not one of the suspects, and
 * fuzzy matching is enough to forgive "Dr Vane" for "Dr. Emmanuel Vane". Making
 * the case is a judgement, and judgement is what a model is for.
 *
 * Everything here is the offline half: exact enough to test against, good
 * enough to play with, and the thing that runs when no model is configured.
 * `lib/server/aiGrade.ts` layers the model on top and falls back to this.
 */

/** Points on offer. Naming them is half; proving it is the other half. */
export const SCORE = {
  culprit: 50,
  /** Split evenly across the case's key points. */
  argument: 50,
  /** Per unused hour, rewarding a tight investigation. */
  perHourLeft: 1,
} as const;

export interface PointVerdict {
  id: string;
  claim: string;
  /** 0-1. Whole numbers offline; a model may land between. */
  credit: number;
  /** One line on why, when the grader can say. Never reveals an unmade point. */
  note: string | null;
}

export interface Grade {
  points: PointVerdict[];
  /** 0-1 across the whole argument. */
  fraction: number;
  /** Which grader produced this, so the verdict can be honest about it. */
  by: "model" | "offline";
}

function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const TITLES = new Set([
  "mr", "mrs", "miss", "ms", "dr", "doctor", "madame", "mme",
  "sir", "lady", "prof", "professor", "inspector",
]);

/**
 * How firmly a written name picks out this suspect. 0 is not at all.
 *
 * A number rather than a boolean because a bare surname is a weaker claim than
 * a full name, and the difference decides real cases. Two suspects in the same
 * family share a surname, so "Frayne" is a shortlist while "Gilbert Frayne" is
 * an accusation - a predicate cannot express that and would have to reject both.
 *
 * Generous within a rank, though. Somebody who has worked the case for ninety
 * minutes and types "vane" has named him; failing them over a missing honorific
 * would be marking their typing rather than their detection.
 */
export function nameStrength(written: string, suspectName: string): number {
  const w = normalise(written);
  if (!w) return 0;

  const full = normalise(suspectName);
  if (w === full) return 3;

  const parts = full.split(" ").filter((p) => !TITLES.has(p));
  const typed = w.split(" ").filter((p) => !TITLES.has(p));
  if (!parts.length || !typed.length) return 0;

  // Every word they typed belongs to the name, and they gave more than one -
  // "emmanuel vane", "vane emmanuel", "dr vane" all land here.
  if (typed.length > 1 && typed.every((t) => parts.includes(t))) return 2;

  // The surname alone. What people actually write, and enough on its own only
  // when nobody else on the case shares it.
  const surname = parts[parts.length - 1];
  if (surname.length >= 4 && typed.includes(surname)) return 1;

  if (typed.every((t) => parts.includes(t))) return 1;
  return 0;
}

/** Whether a written name picks out this suspect at all. */
export function namesSuspect(written: string, suspectName: string): boolean {
  return nameStrength(written, suspectName) > 0;
}

/**
 * Which suspect a written name picks out.
 *
 * The strongest match wins, and a tie at the top is not an accusation - it is a
 * shortlist, and the player is asked to be more specific rather than having one
 * of them chosen for them.
 */
export function matchSuspect(
  caseIndex: CaseIndex,
  written: string,
): { id: string; name: string } | null {
  const ranked = [...caseIndex.suspects.values()]
    .map((s) => ({ s, strength: nameStrength(written, s.name) }))
    .filter((r) => r.strength > 0)
    .sort((a, b) => b.strength - a.strength);

  if (!ranked.length) return null;
  if (ranked.length > 1 && ranked[1].strength === ranked[0].strength) return null;
  return { id: ranked[0].s.id, name: ranked[0].s.name };
}

/**
 * Keyword coverage, used only when there is no model.
 *
 * A point counts as made when the argument contains at least half its keywords,
 * minimum two. One keyword would fire on any argument that happened to mention
 * a noun from the case, which most wrong arguments do.
 */
function offlineCredit(argument: string, point: KeyPoint): number {
  const text = normalise(argument);
  const hit = point.keywords.filter((k) => text.includes(normalise(k))).length;
  const needed = Math.max(2, Math.ceil(point.keywords.length / 2));
  return hit >= needed ? 1 : 0;
}

export function gradeOffline(caseIndex: CaseIndex, argument: string): Grade {
  const points = caseIndex.file.solution.keyPoints.map((p) => ({
    id: p.id,
    claim: p.claim,
    credit: offlineCredit(argument, p),
    note: null,
  }));
  return { points, fraction: fractionOf(points), by: "offline" };
}

export function fractionOf(points: PointVerdict[]): number {
  if (!points.length) return 0;
  const total = points.reduce((sum, p) => sum + clamp01(p.credit), 0);
  return total / points.length;
}

export function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.min(1, Math.max(0, n));
}
