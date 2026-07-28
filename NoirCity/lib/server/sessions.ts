import "server-only";
import { randomUUID } from "node:crypto";
import type { ActionEffect, Action, GameState } from "@/lib/engine/reducer";
import { applyAction, initialState } from "@/lib/engine/reducer";
import { buildView } from "@/lib/engine/view";
import { tutorialProgress } from "@/lib/engine/tutorial";
import type { FeedEntry, GameSnapshot } from "@/lib/game/types";
import { loadCase, loadCity } from "./cases";

export type { FeedEntry, GameSnapshot };

/**
 * Single-player sessions, held in memory.
 *
 * This is deliberately the throwaway version. Phase 3 replaces it with the
 * Supabase `games` + `game_events` tables, at which point sessions survive a
 * restart and can be shared by six people. Until then: one process, one map,
 * and a hard cap so a long-running dev server cannot leak forever.
 */

interface Session {
  id: string;
  caseId: string;
  state: GameState;
  feed: FeedEntry[];
  touchedAt: number;
}

const sessions = new Map<string, Session>();
const MAX_SESSIONS = 200;
const MAX_AGE_MS = 6 * 60 * 60 * 1000;

function evictStale() {
  const now = Date.now();
  for (const [id, s] of sessions) {
    if (now - s.touchedAt > MAX_AGE_MS) sessions.delete(id);
  }
  while (sessions.size > MAX_SESSIONS) {
    // Oldest first; Map preserves insertion order.
    const oldest = sessions.keys().next().value;
    if (!oldest) break;
    sessions.delete(oldest);
  }
}

function snapshot(session: Session): GameSnapshot {
  const caseIndex = loadCase(session.caseId);
  if (!caseIndex) throw new Error(`unknown case ${session.caseId}`);
  return {
    sessionId: session.id,
    view: buildView(caseIndex, loadCity(), session.state),
    feed: session.feed,
    tutorial: tutorialProgress(caseIndex, session.state),
  };
}

export function startSession(caseId: string): GameSnapshot | null {
  const caseIndex = loadCase(caseId);
  if (!caseIndex) return null;

  evictStale();
  const session: Session = {
    id: randomUUID(),
    caseId,
    state: initialState(caseIndex),
    feed: [],
    touchedAt: Date.now(),
  };
  sessions.set(session.id, session);
  return snapshot(session);
}

export function getSession(sessionId: string): GameSnapshot | null {
  const session = sessions.get(sessionId);
  if (!session) return null;
  session.touchedAt = Date.now();
  return snapshot(session);
}

export type ActionOutcome =
  | { ok: true; snapshot: GameSnapshot }
  | { ok: false; error: string; status: number };

export function actOnSession(sessionId: string, action: Action): ActionOutcome {
  const session = sessions.get(sessionId);
  if (!session) {
    return { ok: false, error: "That case file is no longer open.", status: 404 };
  }
  const caseIndex = loadCase(session.caseId);
  if (!caseIndex) {
    return { ok: false, error: "Case not found.", status: 500 };
  }

  const result = applyAction(caseIndex, loadCity(), session.state, action);
  if (!result.ok) {
    // A rejected action costs nothing and changes nothing.
    return { ok: false, error: result.error, status: 400 };
  }

  session.state = result.state;
  session.touchedAt = Date.now();
  session.feed = [...session.feed, toFeedEntry(result.effect, session.feed.length, caseIndex)];

  return { ok: true, snapshot: snapshot(session) };
}

function toFeedEntry(
  effect: ActionEffect,
  seq: number,
  caseIndex: ReturnType<typeof loadCase>,
): FeedEntry {
  return {
    seq,
    summary: effect.summary,
    timeSpent: effect.timeSpent,
    newClues: effect.newClueIds.map((id) => ({
      id,
      title: caseIndex?.clues.get(id)?.title ?? id,
    })),
    answer: effect.answer,
  };
}
