import "server-only";
import type { CaseIndex } from "@/lib/engine/caseSchema";
import {
  hoursElapsed,
  sessionRemaining,
  type ActionEffect,
  type GameState,
} from "@/lib/engine/reducer";
import { storyMoment } from "@/lib/engine/storyClock";
import type { FeedEntry, GameSnapshot } from "@/lib/game/types";

/**
 * Shared between solo and multiplayer: turning an accepted action into a journal
 * entry, and answering "how much real time is left".
 *
 * Datelines are computed here rather than on the client so that six people in a
 * room never disagree about what time it is in the story.
 */

export function toFeedEntry(
  caseIndex: CaseIndex,
  stateAfter: GameState,
  effect: ActionEffect,
  seq: number,
): FeedEntry {
  const moment = storyMoment(
    caseIndex.file.startsAt,
    hoursElapsed(caseIndex, stateAfter),
  );

  return {
    seq,
    kind: effect.kind,
    dateline: moment.dateline,
    time: moment.time,
    day: moment.day,
    locationId: effect.locationId,
    title: effect.title,
    body: effect.body,
    summary: effect.summary,
    timeSpent: effect.timeSpent,
    newClues: effect.newClueIds.map((id) => ({
      id,
      title: caseIndex.clues.get(id)?.title ?? id,
    })),
    ...(effect.answer ? { answer: effect.answer } : {}),
  };
}

/** The clock fields every snapshot carries. */
export function clockFields(
  caseIndex: CaseIndex,
  state: GameState,
  now: number,
): Pick<GameSnapshot, "now" | "sessionRemainingMs" | "sessionMinutes"> {
  const moment = storyMoment(
    caseIndex.file.startsAt,
    hoursElapsed(caseIndex, state),
  );
  const left = sessionRemaining(caseIndex, state, now);

  return {
    now: moment,
    // Infinity does not survive JSON, so an unstarted session reports its full
    // budget rather than becoming null on the wire.
    sessionRemainingMs: Number.isFinite(left)
      ? Math.max(0, left)
      : caseIndex.file.sessionMinutes * 60_000,
    sessionMinutes: caseIndex.file.sessionMinutes,
  };
}

/** True once the group has run out of real time at the table. */
export function sessionExpired(
  caseIndex: CaseIndex,
  state: GameState,
  now: number,
): boolean {
  return sessionRemaining(caseIndex, state, now) <= 0;
}
