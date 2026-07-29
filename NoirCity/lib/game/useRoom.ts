"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { RealtimeChannel } from "@supabase/supabase-js";
import type { Action } from "@/lib/engine/reducer";
import { ensureAnonymousUser, supabaseBrowser } from "@/lib/supabase/browser";
import type { RoomSnapshot } from "./types";

/**
 * Drives a shared investigation.
 *
 * Realtime carries a *nudge*, not the state. When somebody moves, everyone hears
 * that the row changed and re-reads the authoritative snapshot from the server.
 * That costs one extra round trip and buys immunity to a whole class of bug
 * where two clients apply the same broadcast twice and drift apart.
 */

interface UseRoom {
  room: RoomSnapshot | null;
  refusal: string | null;
  loading: boolean;
  fatal: string | null;
  /** Somebody else is mid-action; used to disable buttons briefly. */
  syncing: boolean;
  act: (action: Action) => Promise<void>;
  start: () => Promise<void>;
  dismissRefusal: () => void;
}

export function useRoom(gameId: string): UseRoom {
  const [room, setRoom] = useState<RoomSnapshot | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const busy = useRef(false);
  const channelRef = useRef<RealtimeChannel | null>(null);

  const refresh = useCallback(async () => {
    const res = await fetch(`/api/rooms/${gameId}`);
    const body = await res.json();
    if (!res.ok) {
      setFatal(body.error ?? "Lost the room.");
      return;
    }
    setRoom(body);
    setFatal(null);
  }, [gameId]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        await ensureAnonymousUser();
        if (alive) await refresh();
      } catch (e) {
        if (alive) setFatal((e as Error).message);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [refresh]);

  // Subscribe once per room. Any change to the game row, the roster or the feed
  // means somebody did something, so pull the authoritative view again.
  useEffect(() => {
    const supabase = supabaseBrowser();
    if (!supabase) return;

    const channel = supabase
      .channel(`room:${gameId}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "games", filter: `id=eq.${gameId}` },
        () => {
          setSyncing(true);
          void refresh().finally(() => setSyncing(false));
        },
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "game_players", filter: `game_id=eq.${gameId}` },
        () => void refresh(),
      )
      .subscribe();

    channelRef.current = channel;
    return () => {
      void supabase.removeChannel(channel);
      channelRef.current = null;
    };
  }, [gameId, refresh]);

  const post = useCallback(
    async (body: unknown) => {
      if (busy.current) return;
      busy.current = true;
      try {
        const res = await fetch(`/api/rooms/${gameId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const parsed = await res.json();
        if (!res.ok) {
          setRefusal(parsed.error ?? "That will not work.");
          // A version conflict means our picture is stale, not that the move
          // was illegal - so re-read rather than leaving the player confused.
          if (res.status === 409) await refresh();
          return;
        }
        setRefusal(null);
        setRoom(parsed);
      } catch {
        setRefusal("Lost contact with the office.");
      } finally {
        busy.current = false;
      }
    },
    [gameId, refresh],
  );

  return {
    room,
    refusal,
    loading,
    fatal,
    syncing,
    act: (action) => post({ intent: "act", action }),
    start: () => post({ intent: "start" }),
    dismissRefusal: () => setRefusal(null),
  };
}
