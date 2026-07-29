"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Action } from "@/lib/engine/reducer";
import type { GameSnapshot } from "./types";

/**
 * Drives one solo investigation. Every action round-trips to the server, which
 * owns the case file - so there is no optimistic prediction here and no way for
 * the client to grant itself a clue.
 *
 * `snapshot.sessionId` is a signed token carrying the whole game. It is opaque
 * and unforgeable, so keeping it in sessionStorage is safe, and a refresh (or a
 * server restart, or a different Worker isolate) resumes exactly where you were.
 */

const storageKey = (caseId: string) => `noircity:session:${caseId}`;

interface UseGame {
  snapshot: GameSnapshot | null;
  /** Set when the last action was refused. Clears on the next successful one. */
  refusal: string | null;
  loading: boolean;
  fatal: string | null;
  act: (action: Action) => Promise<void>;
  restart: () => Promise<void>;
  dismissRefusal: () => void;
}

async function post(body: unknown) {
  const res = await fetch("/api/game", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { ok: res.ok, status: res.status, body: await res.json() };
}

export function useGame(caseId: string): UseGame {
  const [snapshot, setSnapshot] = useState<GameSnapshot | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Guards against a double-click firing two actions against the same state.
  const busy = useRef(false);
  // Which case we have already opened a session for. Without this, React's
  // development double-invoke starts two investigations, and the slower
  // response overwrites the faster one - silently discarding moves the player
  // has already made.
  const booted = useRef<string | null>(null);

  const remember = useCallback(
    (next: GameSnapshot) => {
      try {
        sessionStorage.setItem(storageKey(caseId), next.sessionId);
      } catch {
        // Private browsing, or a token past the storage quota. The game still
        // works; it just will not survive a refresh.
      }
      setSnapshot(next);
    },
    [caseId],
  );

  const begin = useCallback(async () => {
    setLoading(true);
    try {
      const res = await post({ intent: "start", caseId });
      if (!res.ok) throw new Error(res.body.error ?? "Could not open the case.");
      remember(res.body);
      setFatal(null);
    } catch (e) {
      setFatal((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId, remember]);

  useEffect(() => {
    if (booted.current === caseId) return;
    booted.current = caseId;
    let alive = true;

    (async () => {
      const existing = sessionStorage.getItem(storageKey(caseId));
      if (existing) {
        const res = await post({ intent: "resume", token: existing });
        if (res.ok && alive) {
          remember(res.body);
          setLoading(false);
          return;
        }
        // Signed with a different secret, or truncated. Start over.
        sessionStorage.removeItem(storageKey(caseId));
      }
      if (alive) await begin();
    })();

    return () => {
      alive = false;
    };
  }, [caseId, begin, remember]);

  const act = useCallback(
    async (action: Action) => {
      if (!snapshot || busy.current) return;
      busy.current = true;
      try {
        const res = await post({
          intent: "act",
          token: snapshot.sessionId,
          action,
        });
        if (!res.ok) {
          setRefusal(res.body.error ?? "That will not work.");
          return;
        }
        setRefusal(null);
        remember(res.body);
      } catch {
        setRefusal("Lost contact with the office.");
      } finally {
        busy.current = false;
      }
    },
    [snapshot, remember],
  );

  const restart = useCallback(async () => {
    sessionStorage.removeItem(storageKey(caseId));
    booted.current = caseId;
    setSnapshot(null);
    setRefusal(null);
    await begin();
  }, [caseId, begin]);

  return {
    snapshot,
    refusal,
    loading,
    fatal,
    act,
    restart,
    dismissRefusal: () => setRefusal(null),
  };
}
