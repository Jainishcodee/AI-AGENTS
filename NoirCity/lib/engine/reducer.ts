import type { CaseIndex } from "./caseSchema";
import { travelCost, type CityIndex } from "./citySchema";
import { scoreAccusation, type AccusationResult } from "./scoring";
import { gradeOffline, type Grade } from "./grade";

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
  /**
   * Wall-clock epoch (ms) when the case opened, set by the server. The REAL
   * deadline is derived from this and the case's `sessionMinutes`; the reducer
   * never reads a clock itself, so it stays pure and testable.
   */
  startedAt: number;
  result: AccusationResult | null;
}

export type Action =
  | { type: "travel"; locationId: string }
  | { type: "search" }
  | { type: "interview"; npcId: string; questionId: string }
  | { type: "lab"; clueId: string }
  | {
      type: "accuse";
      /** As typed by the player. Matched against the suspects, not an id. */
      culpritName: string;
      /** Why, and what proves it, in the player's own words. */
      argument: string;
      /**
       * How the argument was marked.
       *
       * Attached by the server after grading, never by the caller. The action
       * schemas at both API routes do not declare this field, so a client that
       * sends one has it stripped by zod before it is ever seen here - which is
       * the only thing standing between a written accusation and a player
       * awarding themselves full marks.
       *
       * Absent means "mark it offline", which is what every local caller and
       * every test gets, and is why neither needs a network.
       */
      grade?: Grade;
    };

/**
 * What just happened. This becomes one entry in the case journal, so it carries
 * a heading and prose rather than only a log line. Never contains the solution.
 */
export interface ActionEffect {
  kind: "travel" | "search" | "interview" | "lab" | "accuse";
  /** Where it happened, for the journal's dateline. */
  locationId: string;
  /** Heading: the place you arrived at, or the person you pressed. */
  title: string;
  /** The body of the entry. */
  body: string;
  /** One line, for the compact feed over the map. */
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
    startedAt: 0,
    result: null,
    ...overrides,
  };
}

/** Hours consumed so far, which is what the story clock runs on. */
export function hoursElapsed(caseIndex: CaseIndex, state: GameState): number {
  return caseIndex.file.timeBudget - state.timeRemaining;
}

/** Milliseconds of real session time left, or Infinity if it never started. */
export function sessionRemaining(
  caseIndex: CaseIndex,
  state: GameState,
  now: number,
): number {
  if (!state.startedAt) return Infinity;
  return state.startedAt + caseIndex.file.sessionMinutes * 60_000 - now;
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
      const caseTarget = caseIndex.locations.get(action.locationId);
      return {
        ok: true,
        state: next,
        effect: {
          kind: "travel",
          locationId: action.locationId,
          title: target.name,
          // The case's own words if it has any, the city's otherwise. This is
          // the prose the journal is built from.
          body: caseTarget?.description ?? target.blurb,
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
            kind: "search",
            locationId: locId,
            title: `Searched ${cityLoc.name}`,
            body: "You went through it properly, and there was nothing here that had anything to do with anything. It happens more often than the pictures admit.",
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
          kind: "search",
          locationId: locId,
          title: `Searched ${cityLoc.name}`,
          body: fresh.length
            ? fresh
                .map((id) => caseIndex.clues.get(id)?.body ?? "")
                .filter(Boolean)
                .join("\n\n")
            : "You went over the same ground a second time and it gave up nothing it had not already given up. Whatever is still here needs something you do not have yet.",
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
          kind: "interview",
          locationId: state.currentLocationId,
          title: npc.name,
          body: `"${q.text}"\n\n${q.answer}`,
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
          kind: "lab",
          locationId: state.currentLocationId,
          title: "The laboratory",
          body: fresh.length
            ? fresh
                .map((id) => caseIndex.clues.get(id)?.body ?? "")
                .filter(Boolean)
                .join("\n\n")
            : `${clue.title} came back with nothing they could use.`,
          summary: `Sent ${clue.title} to the lab.`,
          timeSpent: ACTION_COST.lab,
          newClueIds: fresh,
        },
      };
    }

    case "accuse": {
      const scored = scoreAccusation(
        caseIndex,
        state,
        { culpritName: action.culpritName, argument: action.argument },
        action.grade ?? gradeOffline(caseIndex, action.argument),
      );
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
          kind: "accuse",
          locationId: state.currentLocationId,
          title: "Accusation filed",
          body: `You named ${scored.result.accusation.culpritName}.\n\n${scored.result.accusation.argument}`,
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
