"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/game/types";

/** Team chat, docked bottom-right over the map. Collapsed until you want it. */
export function ChatPanel({
  messages,
  youId,
  unread,
  onSend,
  onOpen,
}: {
  messages: ChatMessage[];
  youId: string;
  unread: number;
  onSend: (body: string) => void;
  onOpen: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  if (!open) {
    return (
      <button
        onClick={() => {
          setOpen(true);
          onOpen();
        }}
        className="absolute bottom-3 right-3 z-[1000] border border-neutral-800 bg-[#0e0f11]/95 px-4 py-2.5 text-[10px] tracking-[0.2em] text-neutral-400 backdrop-blur transition hover:border-amber-200/40 hover:text-amber-100 sm:bottom-6 sm:right-6 sm:py-2"
      >
        CHAT
        {unread > 0 && (
          <span className="ml-2 bg-amber-200/80 px-1.5 text-[10px] text-neutral-900">
            {unread}
          </span>
        )}
      </button>
    );
  }

  return (
    // On a phone the map pane is short, so chat takes the width and only as
    // much height as it can have without covering the whole city.
    <div className="absolute inset-x-3 bottom-3 z-[1000] flex h-[min(320px,60%)] flex-col border border-neutral-800 bg-[#0e0f11]/97 backdrop-blur sm:inset-x-auto sm:right-6 sm:bottom-6 sm:h-[340px] sm:w-[320px]">
      <header className="flex items-center justify-between border-b border-neutral-800 px-4 py-2">
        <span className="text-[10px] tracking-[0.25em] text-neutral-500">
          THE FIRM
        </span>
        <button
          onClick={() => setOpen(false)}
          className="text-[13px] leading-none text-neutral-600 hover:text-neutral-300"
          aria-label="Close chat"
        >
          ×
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto overscroll-contain px-4 py-3">
        {!messages.length && (
          <p className="font-serif text-[13px] italic text-neutral-700">
            Nobody has said anything yet.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id}>
            <span
              className={`text-[10px] tracking-[0.15em] ${
                m.userId === youId ? "text-amber-200/70" : "text-neutral-600"
              }`}
            >
              {m.userId === youId ? "YOU" : m.displayName.toUpperCase()}
            </span>
            <p className="font-serif text-[13px] leading-snug text-neutral-300">
              {m.body}
            </p>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSend(draft);
          setDraft("");
        }}
        className="border-t border-neutral-800 p-2"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={500}
          placeholder="Say something"
          // 16px on a phone, or focusing the field zooms the map behind it.
          className="w-full bg-transparent px-2 py-1.5 font-serif text-[16px] text-neutral-200 outline-none placeholder:text-neutral-700 sm:text-[13px]"
        />
      </form>
    </div>
  );
}
