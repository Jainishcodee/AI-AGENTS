/**
 * Refuses to let a broken case ship.
 *
 * Hand-authored mysteries fail in one particular way: an author gates clue C
 * behind clue B, moves B somewhere else, and now the case cannot be solved by
 * anyone. Nothing catches that by reading the JSON. This does.
 *
 *   npx tsx scripts/lint-case.ts cases/case-01-harbor-lights
 *
 * Exits non-zero on any error. Warnings are advisory and do not fail the run.
 */

import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { caseSchema, indexCase, type CaseFile, type CaseIndex } from "../lib/engine/caseSchema";
import { indexCity, parseCity, travelCost, type CityIndex } from "../lib/engine/citySchema";
import { ACTION_COST } from "../lib/engine/reducer";

const errors: string[] = [];
const warnings: string[] = [];

const err = (m: string) => errors.push(m);
const warn = (m: string) => warnings.push(m);

/** Minimum red herrings before a case is just a checklist. */
const MIN_RED_HERRINGS = 3;

// ---------------------------------------------------------------------------

function checkReferences(c: CaseFile, ci: CaseIndex, city: CityIndex) {
  const clueIds = new Set(c.clues.map((x) => x.id));

  if (!city.locations.has(c.startLocationId)) {
    err(`startLocationId "${c.startLocationId}" is not a location in the city`);
  }

  for (const loc of c.locations) {
    if (!city.locations.has(loc.cityLocationId)) {
      err(`location "${loc.cityLocationId}" does not exist in the city`);
    }
    for (const id of loc.clues) {
      if (!clueIds.has(id)) err(`location "${loc.cityLocationId}" lists unknown clue "${id}"`);
    }
  }

  for (const clue of c.clues) {
    for (const id of clue.requires) {
      if (!clueIds.has(id)) err(`clue "${clue.id}" requires unknown clue "${id}"`);
    }
    if (clue.labResult && !clueIds.has(clue.labResult)) {
      err(`clue "${clue.id}" has unknown labResult "${clue.labResult}"`);
    }
    if (clue.implicates && !ci.suspects.has(clue.implicates)) {
      err(`clue "${clue.id}" implicates unknown suspect "${clue.implicates}"`);
    }
  }

  for (const npc of c.npcs) {
    if (!city.locations.has(npc.locationId)) {
      err(`npc "${npc.id}" stands at unknown location "${npc.locationId}"`);
    }
    if (!ci.locations.has(npc.locationId)) {
      warn(`npc "${npc.id}" is at "${npc.locationId}", which the case never describes`);
    }
    for (const q of npc.questions) {
      for (const id of [...q.grants, ...q.requires]) {
        if (!clueIds.has(id)) err(`question "${npc.id}:${q.id}" references unknown clue "${id}"`);
      }
    }
  }

  if (!ci.suspects.has(c.solution.culpritId)) {
    err(`solution names unknown culprit "${c.solution.culpritId}"`);
  }
  if (!ci.motives.has(c.solution.motiveId)) {
    err(`solution names unknown motive "${c.solution.motiveId}"`);
  }
  for (const id of c.solution.requiredEvidence) {
    if (!clueIds.has(id)) err(`solution requires unknown evidence "${id}"`);
  }
}

/** A clue that depends on itself, directly or through a chain, can never surface. */
function checkNoCycles(c: CaseFile) {
  const state = new Map<string, "open" | "done">();

  const walk = (id: string, trail: string[]): void => {
    if (state.get(id) === "done") return;
    if (state.get(id) === "open") {
      err(`circular requirement: ${[...trail, id].join(" -> ")}`);
      return;
    }
    state.set(id, "open");
    const clue = c.clues.find((x) => x.id === id);
    for (const dep of clue?.requires ?? []) walk(dep, [...trail, id]);
    state.set(id, "done");
  };

  for (const clue of c.clues) walk(clue.id, []);
}

/**
 * Fixed-point reachability. A clue is obtainable if it can be searched up, asked
 * about, or produced by the lab - once everything it depends on is obtainable.
 */
function reachableClues(c: CaseFile): Set<string> {
  const reachable = new Set<string>();
  const satisfied = (ids: string[]) => ids.every((id) => reachable.has(id));

  for (let pass = 0; pass < c.clues.length + 2; pass++) {
    const before = reachable.size;

    for (const loc of c.locations) {
      if (!loc.searchable) continue;
      for (const id of loc.clues) {
        const clue = c.clues.find((x) => x.id === id);
        if (clue && satisfied(clue.requires)) reachable.add(id);
      }
    }
    for (const npc of c.npcs) {
      for (const q of npc.questions) {
        if (!satisfied(q.requires)) continue;
        for (const id of q.grants) reachable.add(id);
      }
    }
    for (const clue of c.clues) {
      if (clue.labResult && reachable.has(clue.id)) reachable.add(clue.labResult);
    }

    if (reachable.size === before) break;
  }
  return reachable;
}

function checkSolvable(c: CaseFile, reachable: Set<string>) {
  for (const clue of c.clues) {
    if (!reachable.has(clue.id)) {
      warn(`clue "${clue.id}" (${clue.title}) can never be found by anyone`);
    }
  }
  for (const id of c.solution.requiredEvidence) {
    if (!reachable.has(id)) {
      err(`UNSOLVABLE: required evidence "${id}" can never be obtained`);
    }
  }
}

function checkRedHerrings(c: CaseFile) {
  const herrings = c.clues.filter((x) => x.isRedHerring);
  if (herrings.length < MIN_RED_HERRINGS) {
    err(`only ${herrings.length} red herring(s); at least ${MIN_RED_HERRINGS} required`);
  }
  for (const id of c.solution.requiredEvidence) {
    const clue = c.clues.find((x) => x.id === id);
    if (clue?.isRedHerring) err(`required evidence "${id}" is flagged as a red herring`);
  }
}

/**
 * Walks back from the required evidence through everything that gates it. The
 * evidence itself is never the whole cost - a clue that needs a lab result that
 * needs a second search that needs a coroner's statement is four actions deep.
 */
function solutionClosure(c: CaseFile) {
  const searches = new Map<string, number>(); // location -> distinct clues wanted
  const interviews = new Set<string>(); // `npcId:questionId`
  const labs = new Set<string>(); // clue id sent to the lab
  const locations = new Set<string>();
  const seen = new Set<string>();

  const obtain = (clueId: string) => {
    if (seen.has(clueId)) return;
    seen.add(clueId);

    const fromLab = c.clues.find((x) => x.labResult === clueId);
    if (fromLab) {
      labs.add(fromLab.id);
      obtain(fromLab.id);
      return;
    }

    for (const npc of c.npcs) {
      const q = npc.questions.find((x) => x.grants.includes(clueId));
      if (!q) continue;
      interviews.add(`${npc.id}:${q.id}`);
      locations.add(npc.locationId);
      q.requires.forEach(obtain);
      return;
    }

    const loc = c.locations.find((l) => l.searchable && l.clues.includes(clueId));
    if (loc) {
      searches.set(loc.cityLocationId, (searches.get(loc.cityLocationId) ?? 0) + 1);
      locations.add(loc.cityLocationId);
      c.clues.find((x) => x.id === clueId)?.requires.forEach(obtain);
    }
  };

  c.solution.requiredEvidence.forEach(obtain);
  return { searches, interviews, labs, locations };
}

/**
 * Two budget checks. The floor - one search per location, no travel at all - is
 * a hard error, because no route can possibly beat it. The greedy estimate is
 * advisory, since a smarter route may exist.
 */
function checkBudget(c: CaseFile, city: CityIndex) {
  const { searches, interviews, labs, locations } = solutionClosure(c);
  const searchCost = (id: string) =>
    c.locations.find((l) => l.cityLocationId === id)?.searchCost ?? 2;

  // Lower bound: every location searched exactly once, however many clues it holds.
  let actionFloor = interviews.size * ACTION_COST.interview + labs.size * ACTION_COST.lab;
  for (const id of searches.keys()) actionFloor += searchCost(id);

  // Realistic: a gated clue needs its own return search.
  let actionEstimate = interviews.size * ACTION_COST.interview + labs.size * ACTION_COST.lab;
  for (const [id, count] of searches) actionEstimate += searchCost(id) * count;

  if (actionFloor > c.timeBudget) {
    err(
      `UNSOLVABLE: the solution chain costs at least ${actionFloor} of a ${c.timeBudget} budget, before any travel`,
    );
    return;
  }

  const needed = locations;

  // Greedy nearest-neighbour tour from the start location.
  let travel = 0;
  let at = c.startLocationId;
  const remaining = new Set(needed);
  remaining.delete(at);
  while (remaining.size) {
    let best: string | null = null;
    let bestCost = Infinity;
    for (const id of remaining) {
      const cost = travelCost(city, at, id);
      if (cost < bestCost) {
        bestCost = cost;
        best = id;
      }
    }
    if (!best) break;
    travel += bestCost;
    at = best;
    remaining.delete(best);
  }

  const estimate = actionEstimate + travel;
  const slack = c.timeBudget - estimate;
  if (slack < 0) {
    warn(
      `tight: a direct route to the solution costs ~${estimate} of ${c.timeBudget}. Likely unsolvable in practice.`,
    );
  } else if (slack < c.timeBudget * 0.3) {
    warn(
      `little room to explore: solution needs ~${estimate} of ${c.timeBudget}, leaving only ${slack} for wrong turns.`,
    );
  }
  console.log(
    `  solution    ${searches.size} locations searched, ${interviews.size} interviews, ${labs.size} lab tests`,
  );
  console.log(
    `  budget      ${c.timeBudget} hours; direct route ~${estimate} (${actionEstimate} actions + ${travel} travel), ${slack} spare`,
  );
}

/**
 * A tutorial step whose condition can never be met soft-locks the one player
 * who most needs it not to. Every reference is checked, and every step has to
 * be reachable given the clues the case can actually produce.
 */
function checkTutorial(c: CaseFile, city: CityIndex, reachable: Set<string>) {
  if (!c.tutorial.length) return;

  const ids = new Set<string>();
  for (const step of c.tutorial) {
    if (ids.has(step.id)) err(`duplicate tutorial step id "${step.id}"`);
    ids.add(step.id);

    const d = step.done;
    switch (d.type) {
      case "atLocation":
      case "searched": {
        if (!city.locations.has(d.locationId)) {
          err(`tutorial step "${step.id}" targets unknown location "${d.locationId}"`);
          break;
        }
        const caseLoc = c.locations.find((l) => l.cityLocationId === d.locationId);
        if (d.type === "searched" && !caseLoc?.searchable) {
          err(`tutorial step "${step.id}" asks to search "${d.locationId}", which is not searchable`);
        }
        break;
      }
      case "hasClue":
        if (!c.clues.some((x) => x.id === d.clueId)) {
          err(`tutorial step "${step.id}" targets unknown clue "${d.clueId}"`);
        } else if (!reachable.has(d.clueId)) {
          err(`tutorial step "${step.id}" waits on clue "${d.clueId}", which can never be found`);
        }
        break;
      case "askedQuestion": {
        const npc = c.npcs.find((n) => n.id === d.npcId);
        if (!npc) {
          err(`tutorial step "${step.id}" targets unknown npc "${d.npcId}"`);
          break;
        }
        const q = npc.questions.find((x) => x.id === d.questionId);
        if (!q) {
          err(`tutorial step "${step.id}" targets unknown question "${d.npcId}:${d.questionId}"`);
        } else if (!q.requires.every((r) => reachable.has(r))) {
          err(`tutorial step "${step.id}" waits on a question gated behind an unobtainable clue`);
        }
        break;
      }
      case "labTested": {
        const clue = c.clues.find((x) => x.id === d.clueId);
        if (!clue) {
          err(`tutorial step "${step.id}" targets unknown clue "${d.clueId}"`);
        } else if (!clue.labResult) {
          err(`tutorial step "${step.id}" asks to lab-test "${d.clueId}", which the lab cannot process`);
        } else if (!reachable.has(d.clueId)) {
          err(`tutorial step "${step.id}" waits on clue "${d.clueId}", which can never be found`);
        }
        break;
      }
      case "caseClosed":
        break;
    }
  }

  if (c.tutorial[c.tutorial.length - 1]?.done.type !== "caseClosed") {
    warn("the last tutorial step should be `caseClosed`, or the panel never clears");
  }
}

function checkTexture(c: CaseFile, city: CityIndex) {
  const relevant = c.locations.length;
  // A demo case is deliberately small - that is the point of it.
  const floor = c.tutorial.length ? 4 : 8;
  if (relevant < floor) warn(`only ${relevant} case locations; the map will feel empty`);
  const ratio = relevant / city.city.locations.length;
  if (ratio > 0.1) {
    warn(`${(ratio * 100).toFixed(1)}% of the city is case-relevant; deduction needs more chaff`);
  }
  const unreferenced = c.suspects.filter(
    (s) => !c.clues.some((cl) => cl.implicates === s.id),
  );
  for (const s of unreferenced) {
    warn(`suspect "${s.name}" is implicated by no clue at all`);
  }
}

// ---------------------------------------------------------------------------

function main() {
  const dir = process.argv[2];
  if (!dir) {
    console.error("usage: npx tsx scripts/lint-case.ts <case-directory>");
    process.exit(2);
  }

  const casePath = join(resolve(dir), "case.json");
  const raw = JSON.parse(readFileSync(casePath, "utf8"));
  const parsed = caseSchema.safeParse(raw);
  if (!parsed.success) {
    console.error(`\n  ${casePath}\n`);
    for (const issue of parsed.error.issues) {
      console.error(`  schema  ${issue.path.join(".")}: ${issue.message}`);
    }
    process.exit(1);
  }

  const c = parsed.data;
  const ci = indexCase(c);
  const city = indexCity(
    parseCity(JSON.parse(readFileSync(join(process.cwd(), "public", "city.json"), "utf8"))),
  );

  console.log(`\n  ${c.title}  (${c.id})`);
  console.log(
    `  ${c.suspects.length} suspects, ${c.clues.length} clues, ${c.npcs.length} npcs, ${c.locations.length} locations`,
  );

  if (c.cityId !== city.city.id) {
    err(`case targets city "${c.cityId}" but public/city.json is "${city.city.id}"`);
  }

  checkReferences(c, ci, city);
  checkNoCycles(c);
  const reachable = reachableClues(c);
  checkSolvable(c, reachable);
  checkRedHerrings(c);
  checkTutorial(c, city, reachable);
  if (!errors.length) checkBudget(c, city);
  checkTexture(c, city);

  console.log("");
  for (const w of warnings) console.log(`  warn    ${w}`);
  for (const e of errors) console.log(`  ERROR   ${e}`);

  if (errors.length) {
    console.log(`\n  FAILED - ${errors.length} error(s), ${warnings.length} warning(s)\n`);
    process.exit(1);
  }
  console.log(`\n  OK - ${warnings.length} warning(s)\n`);
}

main();
