import "server-only";
import { indexCase, parseCase, type CaseIndex } from "@/lib/engine/caseSchema";
import { indexCity, parseCity, type CityIndex } from "@/lib/engine/citySchema";
import type { CaseSummary } from "@/lib/game/types";

// Static imports, not `fs.readFileSync`. Cloudflare Workers have no filesystem
// at runtime, so anything the server needs has to be part of the bundle.
import cityNav from "@/content/city-nav.json";
import quietRoom from "@/cases/case-00-the-quiet-room/case.json";
import harborLights from "@/cases/case-01-harbor-lights/case.json";
import bellDoesNotLie from "@/cases/case-02-the-bell-does-not-lie/case.json";

export type { CaseSummary };

/**
 * Case files are read on the server and never sent to the browser. Everything
 * the client sees goes through `buildView`, which strips the solution.
 *
 * `server-only` makes that a build error rather than a code review question: if
 * any client component ever imports this, the build fails.
 */

const CASE_SOURCES: Record<string, unknown> = {
  "the-quiet-room": quietRoom,
  "harbor-lights": harborLights,
  "the-bell-does-not-lie": bellDoesNotLie,
};

const caseCache = new Map<string, CaseIndex>();
let cityCache: CityIndex | null = null;

/**
 * Navigation-only city: locations, boroughs and bridges, with the streets and
 * blocks stripped. The server never draws anything, and the full geometry is
 * 556 KB the Worker would carry for nothing.
 */
export function loadCity(): CityIndex {
  if (!cityCache) cityCache = indexCity(parseCity(cityNav));
  return cityCache;
}

export function loadCase(caseId: string): CaseIndex | null {
  const cached = caseCache.get(caseId);
  if (cached) return cached;

  const source = CASE_SOURCES[caseId];
  if (!source) return null;

  const index = indexCase(parseCase(source));
  caseCache.set(caseId, index);
  return index;
}

export function listCases(): CaseSummary[] {
  return Object.keys(CASE_SOURCES)
    .map((id) => loadCase(id))
    .filter((c): c is CaseIndex => c !== null)
    .map(({ file }) => ({
      id: file.id,
      title: file.title,
      brief: file.brief,
      timeBudget: file.timeBudget,
      suspectCount: file.suspects.length,
      locationCount: file.locations.length,
      isTutorial: file.tutorial.length > 0,
    }))
    // The demo case first - it is the one a new player should take.
    .sort((a, b) => Number(b.isTutorial) - Number(a.isTutorial));
}
