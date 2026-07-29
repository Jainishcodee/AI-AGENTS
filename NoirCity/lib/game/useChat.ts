"use client";

import { useCallback, useEffect, useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/browser";
import type { ChatMessage, RoomPlayer } from "./types";

/**
 * Team chat. The one table players write to directly, because a message is not
 * a game action — nothing about the case changes because somebody typed.
 *
 * Names are resolved from the roster rather than joined in the query: the client
 * already has every player, and RLS on `profiles` would not let it read theirs.
 */
export function useChat(gameId: string | null, players: RoomPlayer[]) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [unread, setUnread] = useState(0);

  const nameOf = useCallback(
    (userId: string) =>
      players.find((p) => p.userId === userId)?.displayName ?? "Somebody",
    [players],
  );

  useEffect(() => {
    if (!gameId) return;
    const supabase = supabaseBrowser();
    if (!supabase) return;
    let alive = true;

    void supabase
      .from("chat_messages")
      .select("id, user_id, body, created_at")
      .eq("game_id", gameId)
      .order("created_at")
      .limit(200)
      .then(({ data }) => {
        if (!alive) return;
        setMessages(
          (data ?? []).map((r) => ({
            id: r.id,
            userId: r.user_id,
            displayName: nameOf(r.user_id),
            body: r.body,
            createdAt: r.created_at,
          })),
        );
      });

    const channel = supabase
      .channel(`chat:${gameId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "chat_messages",
          filter: `game_id=eq.${gameId}`,
        },
        (payload) => {
          const r = payload.new as {
            id: number;
            user_id: string;
            body: string;
            created_at: string;
          };
          setMessages((prev) =>
            prev.some((m) => m.id === r.id)
              ? prev
              : [
                  ...prev,
                  {
                    id: r.id,
                    userId: r.user_id,
                    displayName: nameOf(r.user_id),
                    body: r.body,
                    createdAt: r.created_at,
                  },
                ],
          );
          setUnread((n) => n + 1);
        },
      )
      .subscribe();

    return () => {
      alive = false;
      void supabase.removeChannel(channel);
    };
  }, [gameId, nameOf]);

  const send = useCallback(
    async (body: string) => {
      const trimmed = body.trim();
      if (!gameId || !trimmed) return;
      const supabase = supabaseBrowser();
      if (!supabase) return;
      const { data } = await supabase.auth.getUser();
      if (!data.user) return;
      await supabase.from("chat_messages").insert({
        game_id: gameId,
        user_id: data.user.id,
        body: trimmed.slice(0, 500),
      });
    },
    [gameId],
  );

  return { messages, send, unread, clearUnread: () => setUnread(0) };
}
