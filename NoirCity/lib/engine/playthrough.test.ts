import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { indexCase, parseCase, type CaseIndex } from "./caseSchema";
import { indexCity, parseCity, type CityIndex } from "./citySchema";
import { applyAction, initialState, type Action, type GameState } from "./reducer";
import { tutorialProgress } from "./tutorial";
import { buildView } from "./view";

/**
 * Plays the real cases against the real city, end to end.
 *
 * The linter proves a case is *theoretically* solvable by walking its
 * dependency graph. This proves it is *actually* solvable by taking the actions
 * a player would take and seeing the accusation land. If an author moves a clue
 * and breaks the route, this fails.
 */

const root = process.cwd();

function loadCity(): CityIndex {
  return indexCity(
    parseCity(JSON.parse(readFileSync(join(root, "public", "city.json"), "utf8"))),
  );
}

function loadCase(dir: string): CaseIndex {
  return indexCase(
    parseCase(JSON.parse(readFileSync(join(root, "cases", dir, "case.json"), "utf8"))),
  );
}

const city = loadCity();

/** Runs a script, failing loudly on the first rejected action. */
function play(caseIndex: CaseIndex, script: Action[]) {
  let state: GameState = initialState(caseIndex);
  const trace: string[] = [];

  script.forEach((action, i) => {
    const result = applyAction(caseIndex, city, state, action);
    if (!result.ok) {
      throw new Error(
        `step ${i + 1} (${action.type}) rejected: ${result.error}\ntrace:\n  ${trace.join("\n  ")}`,
      );
    }
    state = result.state;
    trace.push(`${action.type} -> ${result.effect.summary} [${state.timeRemaining}h left]`);
  });

  return { state, trace };
}

// ---------------------------------------------------------------------------

describe("case 00 - The Quiet Room", () => {
  const c = loadCase("case-00-the-quiet-room");

  const script: Action[] = [
    { type: "travel", locationId: "loc_0269" },
    { type: "search" },
    { type: "interview", npcId: "n_sabine", questionId: "q_night" },
    { type: "lab", clueId: "c_teacup" },
    { type: "travel", locationId: "loc_0023" },
    { type: "search" },
    { type: "travel", locationId: "loc_0272" },
    { type: "search" },
  ];

  it("can be solved, and the accusation is accepted", () => {
    const { state } = play(c, script);
    const final = applyAction(c, city, state, {
      type: "accuse",
      culpritId: "s_vane",
      motiveId: "m_ledger",
      evidenceIds: ["c_lab_digitalis", "c_prescription", "c_ledger_debt"],
    });
    expect(final.ok).toBe(true);
    if (final.ok) {
      expect(final.state.result?.solved).toBe(true);
      expect(final.state.result?.culpritCorrect).toBe(true);
    }
  });

  it("leaves real slack for a player who wanders", () => {
    const { state } = play(c, script);
    expect(state.timeRemaining).toBeGreaterThanOrEqual(8);
  });

  it("walks every tutorial step in order, without skipping any", () => {
    let state = initialState(c);

    // Nothing done yet: the first step is showing.
    expect(tutorialProgress(c, state).current?.id).toBe("t_travel");

    const expected = ["t_travel", "t_search", "t_interview", "t_lab", "t_accuse"];
    const seen: string[] = [];

    for (const action of script) {
      const before = tutorialProgress(c, state).current?.id;
      const result = applyAction(c, city, state, action);
      expect(result.ok).toBe(true);
      if (!result.ok) return;
      state = result.state;
      const after = tutorialProgress(c, state).current?.id;
      if (before && before !== after) seen.push(before);
    }

    // The first four steps clear through play; the last needs the accusation.
    expect(seen).toEqual(expected.slice(0, 4));
    expect(tutorialProgress(c, state).current?.id).toBe("t_accuse");

    const closed = applyAction(c, city, state, {
      type: "accuse",
      culpritId: "s_vane",
      motiveId: "m_ledger",
      evidenceIds: ["c_lab_digitalis", "c_prescription", "c_ledger_debt"],
    });
    expect(closed.ok).toBe(true);
    if (closed.ok) {
      const done = tutorialProgress(c, closed.state);
      expect(done.current).toBeNull();
      expect(done.completed).toHaveLength(expected.length);
    }
  });

  it("does not rewind the tutorial when the player drives away", () => {
    // Regression: `atLocation` is transient, so naive "first unmet step" logic
    // snapped a player who had done four steps back to step one.
    let state = initialState(c);
    for (const action of script.slice(0, 4)) {
      const r = applyAction(c, city, state, action);
      expect(r.ok).toBe(true);
      if (!r.ok) return;
      state = r.state;
    }
    expect(tutorialProgress(c, state).current?.id).toBe("t_accuse");

    const away = applyAction(c, city, state, {
      type: "travel",
      locationId: "loc_0023",
    });
    expect(away.ok).toBe(true);
    if (away.ok) {
      expect(tutorialProgress(c, away.state).current?.id).toBe("t_accuse");
      expect(tutorialProgress(c, away.state).index).toBe(4);
    }
  });

  it("misdirects: the fraudulent medium is not the killer", () => {
    // The obvious suspect confesses to fraud and nothing else. If this ever
    // starts scoring as solved, the case has lost its twist.
    const { state } = play(c, script);
    const wrong = applyAction(c, city, state, {
      type: "accuse",
      culpritId: "s_sabine",
      motiveId: "m_exposure",
      evidenceIds: ["c_lab_digitalis"],
    });
    expect(wrong.ok).toBe(true);
    if (wrong.ok) expect(wrong.state.result?.solved).toBe(false);
  });
});

describe("case 01 - Harbor Lights", () => {
  const c = loadCase("case-01-harbor-lights");

  const script: Action[] = [
    { type: "travel", locationId: "loc_1102" },
    { type: "search" },
    { type: "travel", locationId: "loc_lm_no_4_dry_dock" },
    { type: "search" },
    { type: "travel", locationId: "loc_lm_the_county_morgue" },
    { type: "interview", npcId: "n_sokolov", questionId: "q_cause" },
    { type: "travel", locationId: "loc_lm_no_4_dry_dock" },
    { type: "search" },
    { type: "lab", clueId: "c_paint_flake" },
    { type: "travel", locationId: "loc_lm_the_backlund_exchange" },
    { type: "search" },
    { type: "interview", npcId: "n_ashe", questionId: "q_manifest" },
    { type: "travel", locationId: "loc_1098" },
    { type: "search" },
  ];

  it("can be solved within the budget", () => {
    const { state } = play(c, script);
    expect(state.timeRemaining).toBeGreaterThan(0);

    const final = applyAction(c, city, state, {
      type: "accuse",
      culpritId: "s_pell",
      motiveId: "m_manifest",
      evidenceIds: ["c_lab_paint", "c_manifest_copy", "c_signet"],
    });
    expect(final.ok).toBe(true);
    if (final.ok) expect(final.state.result?.solved).toBe(true);
  });

  it("requires the second visit to the dry dock", () => {
    // c_paint_flake is gated behind the coroner's finding, so a player who
    // searches once and never returns cannot finish. That gate is the case.
    const shortcut: Action[] = [
      { type: "travel", locationId: "loc_lm_no_4_dry_dock" },
      { type: "search" },
    ];
    const { state } = play(c, shortcut);
    expect(state.discoveredClues).toContain("c_body");
    expect(state.discoveredClues).not.toContain("c_paint_flake");
  });

  it("never leaks the solution mid-play", () => {
    const { state } = play(c, script);
    const wire = JSON.stringify(buildView(c, city, state));
    expect(wire).not.toContain(c.file.solution.epilogue);
    expect(wire).not.toContain("isRedHerring");
    expect(wire).not.toContain("solution");
  });
});

describe("every case ships against the same city", () => {
  for (const dir of ["case-00-the-quiet-room", "case-01-harbor-lights"]) {
    it(`${dir} targets a real start location`, () => {
      const c = loadCase(dir);
      expect(c.file.cityId).toBe(city.city.id);
      expect(city.locations.has(c.file.startLocationId)).toBe(true);
      for (const loc of c.file.locations) {
        expect(city.locations.has(loc.cityLocationId)).toBe(true);
      }
    });
  }
});
