"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Action } from "@/lib/engine/reducer";
import type { GameSnapshot } from "./types";

/**
 * Drives one investigation. Every action round-trips to the server, which owns
 * the case file - so there is no optimistic prediction here and no way for the
 * client to grant itself a clue.
 *
 * The session id is kept in sessionStorage so a refresh resumes the same case
 * rather than silently starting a new one.
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

export function useGame(caseId: string): UseGame {
  const [snapshot, setSnapshot] = useState<GameSnapshot | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Guards against a double-click firing two actions against the same state.
  const busy = useRef(false);

  const begin = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/game", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ caseId }),
      });
      if (!res.ok) throw new Error((await res.json()).error ?? "Could not open the case.");
      const next: GameSnapshot = await res.json();
      sessionStorage.setItem(storageKey(caseId), next.sessionId);
      setSnapshot(next);
      setFatal(null);
    } catch (e) {
      setFatal((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    let alive = true;

    (async () => {
      const existing = sessionStorage.getItem(storageKey(caseId));
      if (existing) {
        const res = await fetch(`/api/game/${existing}`);
        if (res.ok && alive) {
          setSnapshot(await res.json());
          setLoading(false);
          return;
        }
        // Server restarted and lost the in-memory session; start over.
        sessionStorage.removeItem(storageKey(caseId));
      }
      if (alive) await begin();
    })();

    return () => {
      alive = false;
    };
  }, [caseId, begin]);

  const act = useCallback(
    async (action: Action) => {
      if (!snapshot || busy.current) return;
      busy.current = true;
      try {
        const res = await fetch(`/api/game/${snapshot.sessionId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(action),
        });
        const body = await res.json();
        if (!res.ok) {
          setRefusal(body.error ?? "That will not work.");
          return;
        }
        setRefusal(null);
        setSnapshot(body);
      } catch {
        setRefusal("Lost contact with the office.");
      } finally {
        busy.current = false;
      }
    },
    [snapshot],
  );

  const restart = useCallback(async () => {
    sessionStorage.removeItem(storageKey(caseId));
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
