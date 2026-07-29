"use client";

import { useEffect, useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/browser";

/**
 * Who is actually here right now.
 *
 * The roster in `game_players` says who joined; it will happily list somebody
 * who shut their laptop an hour ago. Presence is ephemeral and lives only in the
 * realtime channel, so a closed tab drops out on its own without any cleanup job.
 */
export function usePresence(gameId: string | null, userId: string | null) {
  const [online, setOnline] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!gameId || !userId) return;
    const supabase = supabaseBrowser();
    if (!supabase) return;

    const channel = supabase.channel(`presence:${gameId}`, {
      config: { presence: { key: userId } },
    });

    channel
      .on("presence", { event: "sync" }, () => {
        setOnline(new Set(Object.keys(channel.presenceState())));
      })
      .subscribe(async (status) => {
        if (status === "SUBSCRIBED") {
          await channel.track({ at: Date.now() });
        }
      });

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [gameId, userId]);

  return online;
}
