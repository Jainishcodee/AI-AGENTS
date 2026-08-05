import type { CaseIndex } from "./caseSchema";
import type { GameState } from "./reducer";
import { SCORE, fractionOf, matchSuspect, type Grade, type PointVerdict } from "./grade";

export { SCORE } from "./grade";

/** The longest case anybody should have to write. Guards the model call too. */
export const ARGUMENT_LIMIT = 1500;

/**
 * What the player files.
 *
 * Two fields and no lists. The name is checked against the suspects because a
 * name either is or is not one of them; the argument is written prose because
 * "why, and what proves it" is not a thing you should be able to guess from
 * three options - and being able to guess it was the problem. A player who has
 * not worked out the motive could previously get it right one time in three by
 * shrugging.
 */
export interface Accusation {
  /** As typed. Kept verbatim so the verdict can quote it back. */
  culpritName: string;
  /** The case, in the player's own words. */
  argument: string;
}

export interface AccusationResult {
  accusation: Accusation;
  /** The suspect the written name picked out, if it picked out exactly one. */
  culpritId: string | null;
  culpritCorrect: boolean;
  /** Per key point: did the argument establish it? */
  points: PointVerdict[];
  /** 0-1 across the argument as a whole. */
  argumentFraction: number;
  argumentScore: number;
  timeBonus: number;
  score: number;
  /** Which grader marked it, so the verdict can say so. */
  gradedBy: Grade["by"];
  /** True only on a full solve: right person, and every point made. */
  solved: boolean;
  epilogue: string;
}

export type ScoreOutcome = { result: AccusationResult } | { error: string };

/**
 * Marks a filed accusation.
 *
 * `grade` is handed in rather than computed here because grading may involve a
 * model, which means it may be async and may fail - neither of which belongs
 * inside a pure scoring function that the reducer calls synchronously. The
 * caller does the grading, this turns it into a result.
 */
export function scoreAccusation(
  caseIndex: CaseIndex,
  state: GameState,
  accusation: Accusation,
  grade: Grade,
): ScoreOutcome {
  const { file } = caseIndex;

  const name = accusation.culpritName.trim();
  if (!name) {
    return { error: "Name somebody." };
  }
  if (accusation.argument.trim().length < 20) {
    return { error: "Say why. An accusation without a reason is a guess." };
  }
  if (accusation.argument.length > ARGUMENT_LIMIT) {
    return { error: `Keep it under ${ARGUMENT_LIMIT} characters.` };
  }

  const matched = matchSuspect(caseIndex, name);
  if (!matched) {
    // Deliberately not "that is not a suspect" - the player may have typed
    // something that matches two of them, and saying which would be a hint.
    return {
      error: "Nobody on this case answers to that. Use the name as you have it.",
    };
  }

  const culpritCorrect = matched.id === file.solution.culpritId;

  // A wrong name makes the argument moot: it is an argument about somebody who
  // did not do it, however well written. Marking it anyway would hand out most
  // of the points for a confident, wrong case.
  const points = culpritCorrect
    ? grade.points
    : grade.points.map((p) => ({ ...p, credit: 0 }));
  const argumentFraction = culpritCorrect ? fractionOf(points) : 0;
  const argumentScore = Math.round(argumentFraction * SCORE.argument);

  const timeBonus = culpritCorrect ? state.timeRemaining * SCORE.perHourLeft : 0;

  const score = Math.max(
    0,
    (culpritCorrect ? SCORE.culprit : 0) + argumentScore + timeBonus,
  );

  const solved = culpritCorrect && points.every((p) => p.credit >= 0.999);

  return {
    result: {
      accusation: { culpritName: name, argument: accusation.argument.trim() },
      culpritId: matched.id,
      culpritCorrect,
      points,
      argumentFraction,
      argumentScore,
      timeBonus,
      score,
      gradedBy: grade.by,
      solved,
      epilogue: culpritCorrect
        ? file.solution.epilogue
        : file.solution.failureEpilogue,
    },
  };
}
