import { readFileSync } from "node:fs";
import { join } from "node:path";
import "server-only";
import { indexCase, parseCase, type CaseIndex } from "@/lib/engine/caseSchema";
import { indexCity, parseCity, type CityIndex } from "@/lib/engine/citySchema";

/**
 * Case files are read on the server and never sent to the browser. Everything
 * the client sees goes through `buildView`, which strips the solution.
 *
 * `server-only` makes that a build error rather than a code review question: if
 * any client component ever imports this, the build fails.
 */

const CASE_DIRS: Record<string, string> = {
  "the-quiet-room": "case-00-the-quiet-room",
  "harbor-lights": "case-01-harbor-lights",
};

import type { CaseSummary } from "@/lib/game/types";

export type { CaseSummary };

const caseCache = new Map<string, CaseIndex>();
let cityCache: CityIndex | null = null;

export function loadCity(): CityIndex {
  if (!cityCache) {
    cityCache = indexCity(
      parseCity(
        JSON.parse(readFileSync(join(process.cwd(), "public", "city.json"), "utf8")),
      ),
    );
  }
  return cityCache;
}

export function loadCase(caseId: string): CaseIndex | null {
  const cached = caseCache.get(caseId);
  if (cached) return cached;

  const dir = CASE_DIRS[caseId];
  if (!dir) return null;

  const raw = JSON.parse(
    readFileSync(join(process.cwd(), "cases", dir, "case.json"), "utf8"),
  );
  const index = indexCase(parseCase(raw));
  caseCache.set(caseId, index);
  return index;
}

export function listCases(): CaseSummary[] {
  return Object.keys(CASE_DIRS)
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
