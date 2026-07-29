import "server-only";
import { applyAction, initialState, type Action, type ActionEffect } from "@/lib/engine/reducer";
import { buildView } from "@/lib/engine/view";
import { tutorialProgress } from "@/lib/engine/tutorial";
import type { FeedEntry, GameSnapshot } from "@/lib/game/types";
import { loadCase, loadCity } from "./cases";
import { signSession, verifySession, type SessionPayload } from "./sessionToken";

export type { FeedEntry, GameSnapshot };

/**
 * Solo play. The session lives in a signed token the client carries, not in
 * server memory - see `sessionToken.ts` for why.
 */

function toFeedEntry(
  effect: ActionEffect,
  seq: number,
  clueTitle: (id: string) => string,
): FeedEntry {
  return {
    seq,
    summary: effect.summary,
    timeSpent: effect.timeSpent,
    newClues: effect.newClueIds.map((id) => ({ id, title: clueTitle(id) })),
    ...(effect.answer ? { answer: effect.answer } : {}),
  };
}

async function snapshot(payload: SessionPayload): Promise<GameSnapshot | null> {
  const caseIndex = loadCase(payload.caseId);
  if (!caseIndex) return null;
  return {
    sessionId: await signSession(payload),
    view: buildView(caseIndex, loadCity(), payload.state),
    feed: payload.feed,
    tutorial: tutorialProgress(caseIndex, payload.state),
  };
}

export async function startSession(caseId: string): Promise<GameSnapshot | null> {
  const caseIndex = loadCase(caseId);
  if (!caseIndex) return null;
  return snapshot({ caseId, state: initialState(caseIndex), feed: [] });
}

export async function getSession(token: string): Promise<GameSnapshot | null> {
  const payload = await verifySession(token);
  if (!payload) return null;
  return snapshot(payload);
}

export type ActionOutcome =
  | { ok: true; snapshot: GameSnapshot }
  | { ok: false; error: string; status: number };

export async function actOnSession(
  token: string,
  action: Action,
): Promise<ActionOutcome> {
  const payload = await verifySession(token);
  if (!payload) {
    return { ok: false, error: "That case file is no longer open.", status: 404 };
  }

  const caseIndex = loadCase(payload.caseId);
  if (!caseIndex) return { ok: false, error: "Case not found.", status: 500 };

  const result = applyAction(caseIndex, loadCity(), payload.state, action);
  if (!result.ok) {
    // A rejected action costs nothing and changes nothing.
    return { ok: false, error: result.error, status: 400 };
  }

  const next: SessionPayload = {
    caseId: payload.caseId,
    state: result.state,
    feed: [
      ...payload.feed,
      toFeedEntry(
        result.effect,
        payload.feed.length,
        (id) => caseIndex.clues.get(id)?.title ?? id,
      ),
    ],
  };

  const built = await snapshot(next);
  if (!built) return { ok: false, error: "Case not found.", status: 500 };
  return { ok: true, snapshot: built };
}
