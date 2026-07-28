import type { CaseIndex } from "./caseSchema";
import { travelCost, type CityIndex } from "./citySchema";
import { scoreAccusation, type AccusationResult } from "./scoring";

/**
 * The authoritative game rules. Pure functions - no React, no network, no clock.
 * The server runs this against the full case file; the client runs the same code
 * for optimistic prediction against a redacted view (see `view.ts`).
 */

export const ACTION_COST = {
  interview: 1,
  lab: 4,
} as const;

export type GameStatus = "active" | "finished";

export interface GameState {
  caseId: string;
  status: GameStatus;
  timeRemaining: number;
  currentLocationId: string;
  /** Clue ids the team holds. Order is discovery order. */
  discoveredClues: string[];
  /** City location id -> number of times searched. */
  searchCounts: Record<string, number>;
  /** `${npcId}:${questionId}` for every question already asked. */
  askedQuestions: string[];
  /** Clue ids already sent to the lab. */
  labTested: string[];
  /** Bumped on every accepted action. Rejects stale writes from other clients. */
  version: number;
  result: AccusationResult | null;
}

export type Action =
  | { type: "travel"; locationId: string }
  | { type: "search" }
  | { type: "interview"; npcId: string; questionId: string }
  | { type: "lab"; clueId: string }
  | {
      type: "accuse";
      culpritId: string;
      motiveId: string;
      evidenceIds: string[];
    };

/** What just happened, for the shared action feed. Never contains the solution. */
export interface ActionEffect {
  summary: string;
  timeSpent: number;
  newClueIds: string[];
  /** NPC answer text, when the action was an interview. */
  answer?: string;
}

export type ActionResult =
  | { ok: true; state: GameState; effect: ActionEffect }
  | { ok: false; error: string };

export function initialState(
  caseIndex: CaseIndex,
  overrides: Partial<GameState> = {},
): GameState {
  const { file } = caseIndex;
  return {
    caseId: file.id,
    status: "active",
    timeRemaining: file.timeBudget,
    currentLocationId: file.startLocationId,
    discoveredClues: [],
    searchCounts: {},
    askedQuestions: [],
    labTested: [],
    version: 0,
    result: null,
    ...overrides,
  };
}

/** A clue surfaces only once every clue it depends on is already held. */
export function isClueUnlocked(
  caseIndex: CaseIndex,
  state: GameState,
  clueId: string,
): boolean {
  const clue = caseIndex.clues.get(clueId);
  if (!clue) return false;
  return clue.requires.every((r) => state.discoveredClues.includes(r));
}

export function isQuestionUnlocked(
  caseIndex: CaseIndex,
  state: GameState,
  npcId: string,
  questionId: string,
): boolean {
  const q = caseIndex.questions.get(`${npcId}:${questionId}`);
  if (!q) return false;
  return q.requires.every((r) => state.discoveredClues.includes(r));
}

function grant(
  state: GameState,
  caseIndex: CaseIndex,
  clueIds: string[],
): string[] {
  const fresh: string[] = [];
  for (const id of clueIds) {
    if (state.discoveredClues.includes(id) || fresh.includes(id)) continue;
    if (!caseIndex.clues.has(id)) continue;
    fresh.push(id);
  }
  return fresh;
}

function spend(state: GameState, cost: number): GameState {
  // Callers check affordability first, so this floor is a guard against a bad
  // cost table, not a silent clamp of a real overspend.
  return {
    ...state,
    timeRemaining: Math.max(0, state.timeRemaining - cost),
    version: state.version + 1,
  };
}

export function applyAction(
  caseIndex: CaseIndex,
  cityIndex: CityIndex,
  state: GameState,
  action: Action,
): ActionResult {
  if (state.status === "finished") {
    return { ok: false, error: "The case is closed." };
  }

  switch (action.type) {
    case "travel": {
      const target = cityIndex.locations.get(action.locationId);
      if (!target) return { ok: false, error: "No such place in this city." };
      if (action.locationId === state.currentLocationId) {
        return { ok: false, error: "You are already there." };
      }
      const cost = travelCost(
        cityIndex,
        state.currentLocationId,
        action.locationId,
      );
      if (cost > state.timeRemaining) {
        return { ok: false, error: "Not enough time left to make that trip." };
      }
      const next = spend(state, cost);
      next.currentLocationId = action.locationId;
      return {
        ok: true,
        state: next,
        effect: {
          summary: `Drove to ${target.name}.`,
          timeSpent: cost,
          newClueIds: [],
        },
      };
    }

    case "search": {
      const locId = state.currentLocationId;
      const cityLoc = cityIndex.locations.get(locId);
      if (!cityLoc) return { ok: false, error: "Nowhere to search." };
      const caseLoc = caseIndex.locations.get(locId);
      const cost = caseLoc?.searchCost ?? 2;
      if (cost > state.timeRemaining) {
        return { ok: false, error: "Not enough time left to search." };
      }

      // Irrelevant locations still cost time. That is the game.
      if (!caseLoc?.searchable) {
        const next = spend(state, cost);
        next.searchCounts = {
          ...state.searchCounts,
          [locId]: (state.searchCounts[locId] ?? 0) + 1,
        };
        return {
          ok: true,
          state: next,
          effect: {
            summary: `Turned over ${cityLoc.name}. Nothing worth the shoe leather.`,
            timeSpent: cost,
            newClueIds: [],
          },
        };
      }

      const unlocked = caseLoc.clues.filter((id) =>
        isClueUnlocked(caseIndex, state, id),
      );
      const fresh = grant(state, caseIndex, unlocked);
      const next = spend(state, cost);
      next.discoveredClues = [...state.discoveredClues, ...fresh];
      next.searchCounts = {
        ...state.searchCounts,
        [locId]: (state.searchCounts[locId] ?? 0) + 1,
      };
      return {
        ok: true,
        state: next,
        effect: {
          summary: fresh.length
            ? `Searched ${cityLoc.name}. Turned up ${fresh.length} thing${fresh.length === 1 ? "" : "s"}.`
            : `Searched ${cityLoc.name}. Nothing new.`,
          timeSpent: cost,
          newClueIds: fresh,
        },
      };
    }

    case "interview": {
      const npc = caseIndex.npcs.get(action.npcId);
      if (!npc) return { ok: false, error: "Nobody here by that name." };
      if (npc.locationId !== state.currentLocationId) {
        return { ok: false, error: `${npc.name} is not here.` };
      }
      const key = `${action.npcId}:${action.questionId}`;
      const q = caseIndex.questions.get(key);
      if (!q) return { ok: false, error: "You do not know to ask that." };
      if (
        !isQuestionUnlocked(caseIndex, state, action.npcId, action.questionId)
      ) {
        return {
          ok: false,
          error: "You have nothing to make that question stick.",
        };
      }
      if (state.askedQuestions.includes(key)) {
        return { ok: false, error: "You already asked that." };
      }
      if (ACTION_COST.interview > state.timeRemaining) {
        return { ok: false, error: "Not enough time left to talk." };
      }
      const fresh = grant(state, caseIndex, q.grants);
      const next = spend(state, ACTION_COST.interview);
      next.discoveredClues = [...state.discoveredClues, ...fresh];
      next.askedQuestions = [...state.askedQuestions, key];
      return {
        ok: true,
        state: next,
        effect: {
          summary: `Pressed ${npc.name}: "${q.text}"`,
          timeSpent: ACTION_COST.interview,
          newClueIds: fresh,
          answer: q.answer,
        },
      };
    }

    case "lab": {
      const clue = caseIndex.clues.get(action.clueId);
      if (!clue) return { ok: false, error: "No such evidence." };
      if (!state.discoveredClues.includes(action.clueId)) {
        return { ok: false, error: "You do not have that evidence." };
      }
      if (!clue.labResult) {
        return { ok: false, error: "The lab can do nothing with that." };
      }
      if (state.labTested.includes(action.clueId)) {
        return { ok: false, error: "Already tested." };
      }
      if (ACTION_COST.lab > state.timeRemaining) {
        return { ok: false, error: "Not enough time left for lab work." };
      }
      const fresh = grant(state, caseIndex, [clue.labResult]);
      const next = spend(state, ACTION_COST.lab);
      next.discoveredClues = [...state.discoveredClues, ...fresh];
      next.labTested = [...state.labTested, action.clueId];
      return {
        ok: true,
        state: next,
        effect: {
          summary: `Sent ${clue.title} to the lab.`,
          timeSpent: ACTION_COST.lab,
          newClueIds: fresh,
        },
      };
    }

    case "accuse": {
      const scored = scoreAccusation(caseIndex, state, {
        culpritId: action.culpritId,
        motiveId: action.motiveId,
        evidenceIds: action.evidenceIds,
      });
      if ("error" in scored) return { ok: false, error: scored.error };
      return {
        ok: true,
        state: {
          ...state,
          status: "finished",
          version: state.version + 1,
          result: scored.result,
        },
        effect: {
          summary: "Accusation filed.",
          timeSpent: 0,
          newClueIds: [],
        },
      };
    }
  }
}

/**
 * Hitting zero does not close the case on its own - the team still gets to name
 * someone. It only closes the door on gathering anything new.
 */
export function isOutOfTime(state: GameState): boolean {
  return state.timeRemaining <= 0;
}
