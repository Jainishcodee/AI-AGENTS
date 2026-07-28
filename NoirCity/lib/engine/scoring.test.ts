import { describe, expect, it } from "vitest";
import { toyCase, toyCity } from "./testFixtures";
import { applyAction, initialState, type GameState } from "./reducer";
import { EVIDENCE_SLOTS, SCORE, scoreAccusation } from "./scoring";

const caseIndex = toyCase();
const cityIndex = toyCity();

/** Team holding every clue, with `left` hours still on the clock. */
function armed(left = 5): GameState {
  return initialState(caseIndex, {
    timeRemaining: left,
    discoveredClues: [
      "c_open",
      "c_gated",
      "c_lab",
      "c_labresult",
      "c_talk",
      "c_herring",
    ],
  });
}

function score(state: GameState, culpritId: string, motiveId: string, evidenceIds: string[]) {
  const out = scoreAccusation(caseIndex, state, { culpritId, motiveId, evidenceIds });
  if ("error" in out) throw new Error(out.error);
  return out.result;
}

describe("a perfect accusation", () => {
  const r = score(armed(5), "s_guilty", "m_money", [
    "c_open",
    "c_gated",
    "c_labresult",
  ]);

  it("is marked solved", () => {
    expect(r.solved).toBe(true);
    expect(r.culpritCorrect).toBe(true);
    expect(r.motiveCorrect).toBe(true);
  });

  it("scores culprit + motive + evidence + the time left over", () => {
    expect(r.score).toBe(
      SCORE.culprit + SCORE.motive + 3 * SCORE.perEvidence + 5 * SCORE.perTimeUnitLeft,
    );
  });

  it("plays the winning epilogue", () => {
    expect(r.epilogue).toBe("You got them.");
  });
});

describe("a partial accusation", () => {
  it("credits the right person but not the wrong motive", () => {
    const r = score(armed(0), "s_guilty", "m_spite", ["c_open"]);
    expect(r.culpritCorrect).toBe(true);
    expect(r.motiveCorrect).toBe(false);
    expect(r.solved).toBe(false);
    expect(r.score).toBe(SCORE.culprit + SCORE.perEvidence);
  });

  it("gives no time bonus when the culprit is wrong", () => {
    const r = score(armed(9), "s_innocent", "m_money", ["c_open"]);
    expect(r.timeBonus).toBe(0);
    expect(r.score).toBe(SCORE.motive + SCORE.perEvidence);
    expect(r.epilogue).toBe("They walked.");
  });
});

describe("red herrings", () => {
  it("cost points when submitted as proof", () => {
    const clean = score(armed(0), "s_guilty", "m_money", ["c_open"]);
    const dirty = score(armed(0), "s_guilty", "m_money", ["c_open", "c_herring"]);
    expect(dirty.redHerringIds).toEqual(["c_herring"]);
    expect(dirty.score).toBe(clean.score - SCORE.redHerringPenalty);
  });

  it("are never part of the real proof", () => {
    const required = caseIndex.file.solution.requiredEvidence;
    for (const id of required) {
      expect(caseIndex.clues.get(id)?.isRedHerring).toBe(false);
    }
  });
});

describe("the accusation form rejects nonsense", () => {
  it("refuses a suspect who is not in the case", () => {
    const out = scoreAccusation(caseIndex, armed(), {
      culpritId: "s_nobody",
      motiveId: "m_money",
      evidenceIds: [],
    });
    expect(out).toHaveProperty("error");
  });

  it("refuses evidence the team never found", () => {
    const state = initialState(caseIndex, { discoveredClues: [] });
    const out = scoreAccusation(caseIndex, state, {
      culpritId: "s_guilty",
      motiveId: "m_money",
      evidenceIds: ["c_open"],
    });
    expect(out).toHaveProperty("error");
  });

  it("refuses duplicate evidence", () => {
    const out = scoreAccusation(caseIndex, armed(), {
      culpritId: "s_guilty",
      motiveId: "m_money",
      evidenceIds: ["c_open", "c_open"],
    });
    expect(out).toHaveProperty("error");
  });

  it("refuses more than the available slots", () => {
    const out = scoreAccusation(caseIndex, armed(), {
      culpritId: "s_guilty",
      motiveId: "m_money",
      evidenceIds: ["c_open", "c_gated", "c_labresult", "c_talk"],
    });
    expect(out).toHaveProperty("error");
    expect(EVIDENCE_SLOTS).toBe(3);
  });

  it("never returns a negative score", () => {
    // Nothing right, and every submitted card a herring.
    const r = score(armed(0), "s_innocent", "m_spite", ["c_herring"]);
    expect(r.score).toBe(0);
  });
});

describe("the accusation closes the case through the reducer", () => {
  it("records the result on the state", () => {
    const out = applyAction(caseIndex, cityIndex, armed(4), {
      type: "accuse",
      culpritId: "s_guilty",
      motiveId: "m_money",
      evidenceIds: ["c_open", "c_gated", "c_labresult"],
    });
    expect(out.ok).toBe(true);
    if (out.ok) {
      expect(out.state.status).toBe("finished");
      expect(out.state.result?.solved).toBe(true);
    }
  });
});
