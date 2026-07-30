import "server-only";
import { applyAction, initialState, type Action } from "@/lib/engine/reducer";
import { buildView } from "@/lib/engine/view";
import { tutorialProgress } from "@/lib/engine/tutorial";
import type { FeedEntry, GameSnapshot } from "@/lib/game/types";
import { loadCase, loadCity } from "./cases";
import { clockFields, sessionExpired, toFeedEntry } from "./journal";
import { signSession, verifySession, type SessionPayload } from "./sessionToken";

export type { FeedEntry, GameSnapshot };

/**
 * Solo play. The session lives in a signed token the client carries, not in
 * server memory - see `sessionToken.ts` for why.
 */

async function snapshot(payload: SessionPayload): Promise<GameSnapshot | null> {
  const caseIndex = loadCase(payload.caseId);
  if (!caseIndex) return null;
  return {
    sessionId: await signSession(payload),
    view: buildView(caseIndex, loadCity(), payload.state),
    feed: payload.feed,
    tutorial: tutorialProgress(caseIndex, payload.state),
    ...clockFields(caseIndex, payload.state, Date.now()),
  };
}

export async function startSession(caseId: string): Promise<GameSnapshot | null> {
  const caseIndex = loadCase(caseId);
  if (!caseIndex) return null;
  // The real clock starts the moment the file is opened.
  const state = initialState(caseIndex, { startedAt: Date.now() });
  return snapshot({ caseId, state, feed: [] });
}

export async function getSession(token: string): Promise<GameSnapshot | null> {
  const payload = await verifySession(token);
  if (!payload) return null;
  return snapshot(closeIfExpired(payload));
}

/**
 * A group that runs out of real time has the case closed for them. Enforced on
 * read as well as on write, so leaving the tab open past the deadline does not
 * quietly buy you extra minutes.
 */
function closeIfExpired(payload: SessionPayload): SessionPayload {
  const caseIndex = loadCase(payload.caseId);
  if (!caseIndex) return payload;
  if (payload.state.status === "finished") return payload;
  if (!sessionExpired(caseIndex, payload.state, Date.now())) return payload;

  return {
    ...payload,
    state: { ...payload.state, status: "finished", timeRemaining: 0 },
  };
}

export type ActionOutcome =
  | { ok: true; snapshot: GameSnapshot }
  | { ok: false; error: string; status: number };

export async function actOnSession(
  token: string,
  action: Action,
): Promise<ActionOutcome> {
  const verified = await verifySession(token);
  if (!verified) {
    return { ok: false, error: "That case file is no longer open.", status: 404 };
  }

  const caseIndex = loadCase(verified.caseId);
  if (!caseIndex) return { ok: false, error: "Case not found.", status: 500 };

  const payload = closeIfExpired(verified);
  if (payload.state.status === "finished" && verified.state.status !== "finished") {
    const built = await snapshot(payload);
    return built
      ? { ok: false, error: "Time is up. The case is closed.", status: 409 }
      : { ok: false, error: "Case not found.", status: 500 };
  }

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
      toFeedEntry(caseIndex, result.state, result.effect, payload.feed.length),
    ],
  };

  const built = await snapshot(next);
  if (!built) return { ok: false, error: "Case not found.", status: 500 };
  return { ok: true, snapshot: built };
}
