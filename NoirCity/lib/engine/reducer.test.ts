import { describe, expect, it } from "vitest";
import { toyCase, toyCity } from "./testFixtures";
import { travelCost } from "./citySchema";
import {
  ACTION_COST,
  applyAction,
  initialState,
  isOutOfTime,
  type Action,
  type GameState,
} from "./reducer";

const caseIndex = toyCase();
const cityIndex = toyCity();

function start(overrides: Partial<GameState> = {}) {
  return initialState(caseIndex, overrides);
}

/** Applies a run of actions, asserting each one is accepted. */
function run(state: GameState, actions: Action[]): GameState {
  let s = state;
  for (const a of actions) {
    const r = applyAction(caseIndex, cityIndex, s, a);
    if (!r.ok) throw new Error(`unexpected rejection of ${a.type}: ${r.error}`);
    s = r.state;
  }
  return s;
}

describe("travel cost", () => {
  it("is free to stay put and cheapest within a borough", () => {
    expect(travelCost(cityIndex, null, "bar")).toBe(0);
    expect(travelCost(cityIndex, "office", "office")).toBe(0);
    expect(travelCost(cityIndex, "office", "bar")).toBe(1);
  });

  it("charges more for an adjacent borough than for the same one", () => {
    expect(travelCost(cityIndex, "office", "shop")).toBe(2);
  });

  it("adds the Tussock surcharge when the banks differ", () => {
    // office (north) -> dock (south), non-adjacent boroughs: 3 across town + 1 river.
    expect(travelCost(cityIndex, "office", "dock")).toBe(4);
  });
});

describe("time accounting", () => {
  it("never goes negative", () => {
    let s = start({ timeRemaining: 20 });
    s = run(s, [{ type: "travel", locationId: "bar" }, { type: "search" }]);
    expect(s.timeRemaining).toBe(20 - 1 - 2);
    expect(s.timeRemaining).toBeGreaterThanOrEqual(0);
  });

  it("refuses an action the team cannot afford, and spends nothing", () => {
    const s = start({ timeRemaining: 1, currentLocationId: "bar" });
    const r = applyAction(caseIndex, cityIndex, s, { type: "search" });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/not enough time/i);
  });

  it("reports being out of time without closing the case", () => {
    const s = start({ timeRemaining: 0 });
    expect(isOutOfTime(s)).toBe(true);
    expect(s.status).toBe("active");
  });

  it("bumps the version on every accepted action, for optimistic locking", () => {
    const s = start();
    const after = run(s, [{ type: "travel", locationId: "bar" }]);
    expect(after.version).toBe(s.version + 1);
  });
});

describe("clue gating", () => {
  it("does not surface a gated clue on the first search", () => {
    const s = run(start(), [
      { type: "travel", locationId: "bar" },
      { type: "search" },
    ]);
    expect(s.discoveredClues).toContain("c_open");
    expect(s.discoveredClues).not.toContain("c_gated");
  });

  it("surfaces it on a second search, once its requirement is held", () => {
    const s = run(start(), [
      { type: "travel", locationId: "bar" },
      { type: "search" },
      { type: "search" },
    ]);
    expect(s.discoveredClues).toContain("c_gated");
  });

  it("never grants the same clue twice", () => {
    const s = run(start(), [
      { type: "travel", locationId: "bar" },
      { type: "search" },
      { type: "search" },
      { type: "search" },
    ]);
    const open = s.discoveredClues.filter((c) => c === "c_open");
    expect(open).toHaveLength(1);
  });

  it("still charges time for searching somewhere with nothing in it", () => {
    const s = run(start(), [
      { type: "travel", locationId: "dock" },
      { type: "search" },
    ]);
    expect(s.discoveredClues).toHaveLength(0);
    expect(s.timeRemaining).toBe(20 - 4 - 2);
  });
});

describe("interviews", () => {
  it("refuses an NPC who is somewhere else", () => {
    const s = start();
    const r = applyAction(caseIndex, cityIndex, s, {
      type: "interview",
      npcId: "n_sal",
      questionId: "q_open",
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/not here/i);
  });

  it("grants a clue and returns the answer text", () => {
    const s = run(start(), [{ type: "travel", locationId: "bar" }]);
    const r = applyAction(caseIndex, cityIndex, s, {
      type: "interview",
      npcId: "n_sal",
      questionId: "q_open",
    });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.state.discoveredClues).toContain("c_talk");
      expect(r.effect.answer).toBe("Nothing.");
      expect(r.effect.timeSpent).toBe(ACTION_COST.interview);
    }
  });

  it("locks a question until the team holds the clue that unlocks it", () => {
    const s = run(start(), [{ type: "travel", locationId: "bar" }]);
    const blocked = applyAction(caseIndex, cityIndex, s, {
      type: "interview",
      npcId: "n_sal",
      questionId: "q_locked",
    });
    expect(blocked.ok).toBe(false);

    const armed = run(s, [{ type: "search" }, { type: "search" }]);
    const allowed = applyAction(caseIndex, cityIndex, armed, {
      type: "interview",
      npcId: "n_sal",
      questionId: "q_locked",
    });
    expect(allowed.ok).toBe(true);
  });

  it("refuses to ask the same question twice", () => {
    let s = run(start(), [{ type: "travel", locationId: "bar" }]);
    s = run(s, [{ type: "interview", npcId: "n_sal", questionId: "q_open" }]);
    const again = applyAction(caseIndex, cityIndex, s, {
      type: "interview",
      npcId: "n_sal",
      questionId: "q_open",
    });
    expect(again.ok).toBe(false);
    if (!again.ok) expect(again.error).toMatch(/already asked/i);
  });
});

describe("lab work", () => {
  it("refuses evidence the team does not hold", () => {
    const r = applyAction(caseIndex, cityIndex, start(), {
      type: "lab",
      clueId: "c_lab",
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/do not have/i);
  });

  it("turns a testable clue into its result, once", () => {
    let s = run(start(), [
      { type: "travel", locationId: "shop" },
      { type: "search" },
      { type: "lab", clueId: "c_lab" },
    ]);
    expect(s.discoveredClues).toContain("c_labresult");

    const again = applyAction(caseIndex, cityIndex, s, {
      type: "lab",
      clueId: "c_lab",
    });
    expect(again.ok).toBe(false);
    if (!again.ok) expect(again.error).toMatch(/already tested/i);
    s = s;
  });

  it("refuses clues the lab can do nothing with", () => {
    const s = run(start(), [
      { type: "travel", locationId: "bar" },
      { type: "search" },
    ]);
    const r = applyAction(caseIndex, cityIndex, s, {
      type: "lab",
      clueId: "c_open",
    });
    expect(r.ok).toBe(false);
  });
});

describe("a closed case stays closed", () => {
  it("rejects further actions after an accusation", () => {
    const s = run(start(), [
      {
        type: "accuse",
        culpritId: "s_guilty",
        motiveId: "m_money",
        evidenceIds: [],
      },
    ]);
    expect(s.status).toBe("finished");
    const r = applyAction(caseIndex, cityIndex, s, { type: "search" });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/closed/i);
  });
});
