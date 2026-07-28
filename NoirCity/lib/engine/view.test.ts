import { describe, expect, it } from "vitest";
import { toyCase, toyCity } from "./testFixtures";
import { applyAction, initialState, type GameState } from "./reducer";
import { buildView } from "./view";

const caseIndex = toyCase();
const cityIndex = toyCity();

/**
 * The redaction layer is the only thing standing between a player and the
 * answer. If any of these fail, the game is spoiled by opening devtools.
 *
 * Note the culprit's *id* is necessarily present - it is one of the suspects,
 * and you have to be able to accuse them. What must not be present is anything
 * that singles them out, which is what the invariance test below actually pins.
 */
describe("the client view never leaks the solution", () => {
  const state = initialState(caseIndex);
  const view = buildView(caseIndex, cityIndex, state);
  const serialised = JSON.stringify(view);

  it("is byte-identical when the solution changes", () => {
    // The decisive test. Re-point the case at a different culprit, motive,
    // evidence set and epilogues; if a single byte of the view moves, something
    // about the answer is crossing the wire.
    const rigged = {
      ...caseIndex,
      file: {
        ...caseIndex.file,
        solution: {
          culpritId: "s_innocent",
          motiveId: "m_spite",
          requiredEvidence: ["c_talk"],
          epilogue: "A COMPLETELY DIFFERENT ENDING.",
          failureEpilogue: "ANOTHER DIFFERENT ENDING.",
        },
      },
    };
    expect(JSON.stringify(buildView(rigged, cityIndex, state))).toBe(serialised);
  });

  it("does not contain either epilogue", () => {
    expect(serialised).not.toContain(caseIndex.file.solution.epilogue);
    expect(serialised).not.toContain(caseIndex.file.solution.failureEpilogue);
  });

  it("does not carry a red-herring flag on any clue", () => {
    expect(serialised).not.toContain("isRedHerring");
  });

  it("does not name what a clue would unlock, or what gates it", () => {
    expect(serialised).not.toContain("labResult");
    expect(serialised).not.toContain("c_labresult");
    expect(serialised).not.toContain("requires");
  });

  it("carries no `solution` key at any depth", () => {
    expect(serialised).not.toContain("solution");
  });
});

describe("the view shows only what the team has earned", () => {
  function advance(actions: Parameters<typeof applyAction>[3][]): GameState {
    let s = initialState(caseIndex);
    for (const a of actions) {
      const r = applyAction(caseIndex, cityIndex, s, a);
      if (!r.ok) throw new Error(r.error);
      s = r.state;
    }
    return s;
  }

  it("starts with no clues at all", () => {
    expect(buildView(caseIndex, cityIndex, initialState(caseIndex)).clues).toHaveLength(0);
  });

  it("shows a clue's body only after it is found", () => {
    const s = advance([
      { type: "travel", locationId: "bar" },
      { type: "search" },
    ]);
    const view = buildView(caseIndex, cityIndex, s);
    expect(view.clues.map((c) => c.id)).toEqual(["c_open"]);
    expect(view.clues[0].body).toBe("Found freely.");
  });

  it("hides locked questions and their answers", () => {
    const s = advance([{ type: "travel", locationId: "bar" }]);
    const view = buildView(caseIndex, cityIndex, s);
    const sal = view.here.npcs.find((n) => n.id === "n_sal");
    expect(sal?.questions.map((q) => q.id)).toEqual(["q_open"]);
    expect(JSON.stringify(view)).not.toContain("Fine, I took it.");
  });

  it("reveals a question once its requirement is met", () => {
    const s = advance([
      { type: "travel", locationId: "bar" },
      { type: "search" },
      { type: "search" },
    ]);
    const view = buildView(caseIndex, cityIndex, s);
    const sal = view.here.npcs.find((n) => n.id === "n_sal");
    expect(sal?.questions.map((q) => q.id)).toContain("q_locked");
  });

  it("says a clue is lab-testable without saying what the lab would find", () => {
    const s = advance([
      { type: "travel", locationId: "shop" },
      { type: "search" },
    ]);
    const view = buildView(caseIndex, cityIndex, s);
    const rag = view.clues.find((c) => c.id === "c_lab");
    expect(rag?.labTestable).toBe(true);
    expect(rag?.labTested).toBe(false);
  });

  it("withholds the result until the case is closed", () => {
    const open = buildView(caseIndex, cityIndex, initialState(caseIndex));
    expect(open.result).toBeNull();

    const closed = advance([
      {
        type: "accuse",
        culpritId: "s_guilty",
        motiveId: "m_money",
        evidenceIds: [],
      },
    ]);
    expect(buildView(caseIndex, cityIndex, closed).result).not.toBeNull();
  });
});
