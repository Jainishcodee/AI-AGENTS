import type { CaseIndex, ClueType } from "./caseSchema";
import type { CityIndex } from "./citySchema";
import { isQuestionUnlocked, type GameState } from "./reducer";
import type { AccusationResult } from "./scoring";

/**
 * Redaction layer. The client NEVER receives the case file - it receives this.
 *
 * Everything the solution depends on is stripped here: which clues are red
 * herrings, what a clue unlocks, what an unasked question would reveal, and the
 * solution block itself. If any of those crossed the wire, a player could read
 * the culprit out of devtools and the game would be over before it started.
 */

export interface PublicClue {
  id: string;
  type: ClueType;
  title: string;
  body: string;
  asset: string | null;
  /** Which suspect this points at - red herrings point too, so this is safe. */
  implicates: string | null;
  /** Whether the lab could do something with it. Not what it would find. */
  labTestable: boolean;
  labTested: boolean;
}

export interface PublicQuestion {
  id: string;
  text: string;
  asked: boolean;
}

export interface PublicNpc {
  id: string;
  name: string;
  role: string;
  portrait: string | null;
  /** Only questions the team has earned the right to ask. */
  questions: PublicQuestion[];
}

export interface PublicLocation {
  id: string;
  name: string;
  type: string;
  address: string;
  boroughId: string;
  boroughName: string;
  bank: string;
  x: number;
  y: number;
  description: string;
  searchCount: number;
  npcs: PublicNpc[];
}

export interface ClientView {
  caseId: string;
  title: string;
  brief: string;
  timeBudget: number;
  suspects: CaseIndex["file"]["suspects"];
  motives: CaseIndex["file"]["motives"];
  state: GameState;
  /** Only what the team has actually found. */
  clues: PublicClue[];
  here: PublicLocation;
  /** Revealed only once the case is closed. */
  result: AccusationResult | null;
}

export function publicClue(
  caseIndex: CaseIndex,
  state: GameState,
  clueId: string,
): PublicClue | null {
  const c = caseIndex.clues.get(clueId);
  if (!c) return null;
  return {
    id: c.id,
    type: c.type,
    title: c.title,
    body: c.body,
    asset: c.asset,
    implicates: c.implicates,
    labTestable: c.labResult !== null,
    labTested: state.labTested.includes(c.id),
  };
}

export function publicLocation(
  caseIndex: CaseIndex,
  cityIndex: CityIndex,
  state: GameState,
  locationId: string,
): PublicLocation | null {
  const loc = cityIndex.locations.get(locationId);
  if (!loc) return null;
  const caseLoc = caseIndex.locations.get(locationId);
  const borough = cityIndex.boroughs.get(loc.boroughId);

  const npcs: PublicNpc[] = (caseIndex.npcsByLocation.get(locationId) ?? []).map(
    (npc) => ({
      id: npc.id,
      name: npc.name,
      role: npc.role,
      portrait: npc.portrait,
      questions: npc.questions
        .filter((q) => isQuestionUnlocked(caseIndex, state, npc.id, q.id))
        .map((q) => ({
          id: q.id,
          text: q.text,
          asked: state.askedQuestions.includes(`${npc.id}:${q.id}`),
        })),
    }),
  );

  return {
    id: loc.id,
    name: loc.name,
    type: loc.type,
    address: loc.address,
    boroughId: loc.boroughId,
    boroughName: borough?.name ?? "Unknown",
    bank: borough?.bank ?? "north",
    x: loc.x,
    y: loc.y,
    description: caseLoc?.description ?? loc.blurb,
    searchCount: state.searchCounts[locationId] ?? 0,
    npcs,
  };
}

export function buildView(
  caseIndex: CaseIndex,
  cityIndex: CityIndex,
  state: GameState,
): ClientView {
  const { file } = caseIndex;
  const here = publicLocation(
    caseIndex,
    cityIndex,
    state,
    state.currentLocationId,
  );
  if (!here) throw new Error(`Unknown location ${state.currentLocationId}`);

  return {
    caseId: file.id,
    title: file.title,
    brief: file.brief,
    timeBudget: file.timeBudget,
    suspects: file.suspects,
    motives: file.motives,
    state,
    clues: state.discoveredClues
      .map((id) => publicClue(caseIndex, state, id))
      .filter((c): c is PublicClue => c !== null),
    here,
    result: state.status === "finished" ? state.result : null,
  };
}
