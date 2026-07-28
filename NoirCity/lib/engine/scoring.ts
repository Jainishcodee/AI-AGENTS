import type { CaseIndex } from "./caseSchema";
import type { GameState } from "./reducer";

export const SCORE = {
  culprit: 50,
  motive: 25,
  perEvidence: 5,
  /** Points per unused time unit, rewarding a tight investigation. */
  perTimeUnitLeft: 1,
  /** Deducted for each red herring submitted as proof. */
  redHerringPenalty: 10,
} as const;

/** Evidence slots on the accusation form. */
export const EVIDENCE_SLOTS = 3;

export interface Accusation {
  culpritId: string;
  motiveId: string;
  evidenceIds: string[];
}

export interface AccusationResult {
  accusation: Accusation;
  culpritCorrect: boolean;
  motiveCorrect: boolean;
  /** Submitted evidence ids that are genuinely part of the proof. */
  correctEvidenceIds: string[];
  /** Submitted evidence ids that are red herrings. */
  redHerringIds: string[];
  timeBonus: number;
  score: number;
  /** True only on a full solve: right person, right motive, all proof. */
  solved: boolean;
  epilogue: string;
}

export type ScoreOutcome =
  | { result: AccusationResult }
  | { error: string };

export function scoreAccusation(
  caseIndex: CaseIndex,
  state: GameState,
  accusation: Accusation,
): ScoreOutcome {
  const { file } = caseIndex;

  if (!caseIndex.suspects.has(accusation.culpritId)) {
    return { error: "That is not one of the suspects." };
  }
  if (!caseIndex.motives.has(accusation.motiveId)) {
    return { error: "That is not one of the motives." };
  }

  const unique = Array.from(new Set(accusation.evidenceIds));
  if (unique.length !== accusation.evidenceIds.length) {
    return { error: "You cannot submit the same evidence twice." };
  }
  if (unique.length > EVIDENCE_SLOTS) {
    return { error: `You may submit at most ${EVIDENCE_SLOTS} pieces of evidence.` };
  }
  for (const id of unique) {
    if (!state.discoveredClues.includes(id)) {
      return { error: "You cannot submit evidence you never found." };
    }
  }

  const culpritCorrect = accusation.culpritId === file.solution.culpritId;
  const motiveCorrect = accusation.motiveId === file.solution.motiveId;

  const correctEvidenceIds = unique.filter((id) =>
    file.solution.requiredEvidence.includes(id),
  );
  const redHerringIds = unique.filter(
    (id) => caseIndex.clues.get(id)?.isRedHerring ?? false,
  );

  const timeBonus = culpritCorrect
    ? state.timeRemaining * SCORE.perTimeUnitLeft
    : 0;

  const score = Math.max(
    0,
    (culpritCorrect ? SCORE.culprit : 0) +
      (motiveCorrect ? SCORE.motive : 0) +
      correctEvidenceIds.length * SCORE.perEvidence +
      timeBonus -
      redHerringIds.length * SCORE.redHerringPenalty,
  );

  const solved =
    culpritCorrect &&
    motiveCorrect &&
    file.solution.requiredEvidence.every((id) => unique.includes(id));

  return {
    result: {
      accusation: { ...accusation, evidenceIds: unique },
      culpritCorrect,
      motiveCorrect,
      correctEvidenceIds,
      redHerringIds,
      timeBonus,
      score,
      solved,
      epilogue: culpritCorrect
        ? file.solution.epilogue
        : file.solution.failureEpilogue,
    },
  };
}
