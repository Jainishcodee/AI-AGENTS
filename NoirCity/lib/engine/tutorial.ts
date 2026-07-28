import type { CaseIndex, TutorialCondition, TutorialStep } from "./caseSchema";
import type { GameState } from "./reducer";

/**
 * Tutorial progress is derived from game state, never stored. A player who
 * happens to do step 4 before step 2 is not held back, and a reconnecting
 * player picks up exactly where the team actually is.
 */

export function isConditionMet(
  condition: TutorialCondition,
  state: GameState,
): boolean {
  switch (condition.type) {
    case "atLocation":
      return state.currentLocationId === condition.locationId;
    case "searched":
      return (state.searchCounts[condition.locationId] ?? 0) > 0;
    case "hasClue":
      return state.discoveredClues.includes(condition.clueId);
    case "askedQuestion":
      return state.askedQuestions.includes(
        `${condition.npcId}:${condition.questionId}`,
      );
    case "labTested":
      return state.labTested.includes(condition.clueId);
    case "caseClosed":
      return state.status === "finished";
  }
}

export interface TutorialProgress {
  /** The step to show, or null once the player is off the rails and free. */
  current: TutorialStep | null;
  completed: string[];
  index: number;
  total: number;
}

/**
 * Progress is the step after the LAST satisfied one - not the first unsatisfied
 * one. That distinction matters because `atLocation` is transient: a player who
 * drives away from the scene would otherwise see the tutorial snap back to step
 * one, having already done four of them.
 *
 * The behaviour it keeps is the useful one. Arrive somewhere and leave without
 * searching, and step one does come back - because you do need to go back.
 */
export function tutorialProgress(
  caseIndex: CaseIndex,
  state: GameState,
): TutorialProgress {
  const steps = caseIndex.file.tutorial;
  const satisfied = steps.map((s) => isConditionMet(s.done, state));
  const index = satisfied.lastIndexOf(true) + 1;

  return {
    current: steps[index] ?? null,
    completed: steps.slice(0, index).map((s) => s.id),
    index,
    total: steps.length,
  };
}
