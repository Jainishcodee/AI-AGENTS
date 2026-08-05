import { describe, expect, it } from "vitest";
import { toyCase, toyCity } from "./testFixtures";
import { applyAction, initialState, type GameState } from "./reducer";
import { SCORE, scoreAccusation, type Accusation } from "./scoring";
import { gradeOffline, matchSuspect, nameStrength, namesSuspect } from "./grade";

const caseIndex = toyCase();
const cityIndex = toyCity();

/** Team with `left` hours still on the clock. */
function armed(left = 5): GameState {
  return initialState(caseIndex, { timeRemaining: left });
}

/** An argument that makes both of the toy case's points. */
const BOTH =
  "They were being paid money to keep quiet and it stopped, and they were at the bar an hour before anybody says they arrived.";
/** An argument that makes only the first. */
const ONE = "They were being paid money to keep quiet, and the payments stopped.";
/** An argument that makes neither, at length, confidently. */
const NEITHER =
  "It is obvious from the moment you walk in that this was done by somebody who knew the building well and had every reason to want it over with.";

function score(state: GameState, accusation: Accusation) {
  const out = scoreAccusation(
    caseIndex,
    state,
    accusation,
    gradeOffline(caseIndex, accusation.argument),
  );
  if ("error" in out) throw new Error(out.error);
  return out.result;
}

describe("naming a suspect in writing", () => {
  it("takes the full name, and ignores an honorific", () => {
    expect(namesSuspect("Dr. Guilty Party", "Guilty Party")).toBe(true);
    expect(namesSuspect("guilty party", "Guilty Party")).toBe(true);
  });

  it("ignores punctuation and case", () => {
    expect(namesSuspect("  GUILTY   PARTY.  ", "Guilty Party")).toBe(true);
  });

  it("refuses somebody with no name in common at all", () => {
    expect(namesSuspect("Nobody At All", "Guilty Party")).toBe(false);
  });

  it("refuses a fragment too short to be an accusation", () => {
    expect(namesSuspect("g", "Guilty Party")).toBe(false);
  });

  it("ranks a full name above a shared surname", () => {
    // Both toy suspects are called "... Party". Writing one of them in full is
    // an accusation; writing the surname alone matches both weakly and is a
    // shortlist. A predicate could not tell those apart - it would have to
    // reject the full name too, which is why strength is a number.
    expect(nameStrength("Guilty Party", "Guilty Party")).toBeGreaterThan(
      nameStrength("Guilty Party", "Innocent Party"),
    );
  });

  it("resolves a full name to the right suspect despite the shared surname", () => {
    expect(matchSuspect(caseIndex, "Guilty Party")?.id).toBe("s_guilty");
    expect(matchSuspect(caseIndex, "Innocent Party")?.id).toBe("s_innocent");
  });

  it("refuses a name that fits two suspects equally", () => {
    expect(matchSuspect(caseIndex, "Party")).toBeNull();
  });
});

describe("a complete case", () => {
  const r = score(armed(5), { culpritName: "Guilty Party", argument: BOTH });

  it("is marked solved", () => {
    expect(r.solved).toBe(true);
    expect(r.culpritCorrect).toBe(true);
    expect(r.argumentFraction).toBe(1);
  });

  it("scores the person, the argument, and the time left over", () => {
    expect(r.score).toBe(SCORE.culprit + SCORE.argument + 5 * SCORE.perHourLeft);
  });

  it("plays the winning epilogue", () => {
    expect(r.epilogue).toBe("You got them.");
  });
});

describe("a half-made case", () => {
  const r = score(armed(0), { culpritName: "Guilty Party", argument: ONE });

  it("credits the point that was made and not the one that was not", () => {
    expect(r.points.find((p) => p.id === "kp_money")?.credit).toBe(1);
    expect(r.points.find((p) => p.id === "kp_time")?.credit).toBe(0);
    expect(r.solved).toBe(false);
  });

  it("scores half the argument", () => {
    expect(r.score).toBe(SCORE.culprit + SCORE.argument / 2);
  });
});

describe("naming the wrong person", () => {
  const r = score(armed(9), { culpritName: "Innocent Party", argument: BOTH });

  it("earns nothing, however good the writing", () => {
    // The argument makes both points, and both are about somebody who did not
    // do it. Marking it anyway would hand out most of the score for a
    // confident, wrong case.
    expect(r.culpritCorrect).toBe(false);
    expect(r.argumentScore).toBe(0);
    expect(r.timeBonus).toBe(0);
    expect(r.score).toBe(0);
    expect(r.epilogue).toBe("They walked.");
  });
});

describe("length and confidence are not the same as being right", () => {
  it("gives nothing for a long argument that establishes nothing", () => {
    const r = score(armed(0), { culpritName: "Guilty Party", argument: NEITHER });
    expect(r.argumentScore).toBe(0);
    expect(r.score).toBe(SCORE.culprit);
  });
});

describe("the form rejects nonsense", () => {
  const bad = (a: Accusation) =>
    scoreAccusation(caseIndex, armed(), a, gradeOffline(caseIndex, a.argument));

  it("refuses an empty name", () => {
    expect(bad({ culpritName: "   ", argument: BOTH })).toHaveProperty("error");
  });

  it("refuses a name nobody on the case answers to", () => {
    expect(bad({ culpritName: "Nobody At All", argument: BOTH })).toHaveProperty(
      "error",
    );
  });

  it("refuses an accusation with no reasoning behind it", () => {
    expect(bad({ culpritName: "Guilty Party", argument: "him" })).toHaveProperty(
      "error",
    );
  });

  it("never returns a negative score", () => {
    const r = score(armed(0), { culpritName: "Innocent Party", argument: NEITHER });
    expect(r.score).toBe(0);
  });
});

describe("the accusation closes the case through the reducer", () => {
  it("records the result, marked offline when no grader is attached", () => {
    const out = applyAction(caseIndex, cityIndex, armed(4), {
      type: "accuse",
      culpritName: "Guilty Party",
      argument: BOTH,
    });
    expect(out.ok).toBe(true);
    if (out.ok) {
      expect(out.state.status).toBe("finished");
      expect(out.state.result?.solved).toBe(true);
      expect(out.state.result?.gradedBy).toBe("offline");
    }
  });

  it("quotes the accusation into the journal", () => {
    const out = applyAction(caseIndex, cityIndex, armed(4), {
      type: "accuse",
      culpritName: "Guilty Party",
      argument: BOTH,
    });
    if (!out.ok) throw new Error(out.error);
    expect(out.effect.body).toContain("Guilty Party");
    expect(out.effect.body).toContain("paid money to keep quiet");
  });
});
