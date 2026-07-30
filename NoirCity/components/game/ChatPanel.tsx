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
        // `md:right-[var(--notebook-clear)]`: above `md` the right of the map
        // belongs to the notebook, and chat has to stay out from under it. The
        // offset is derived from the notebook's own width token rather than
        // guessed, so the two cannot drift apart.
        className="absolute bottom-3 right-3 z-[1000] border border-line bg-surface/95 px-4 py-2.5 text-[10px] tracking-[0.2em] text-muted backdrop-blur lift hover:border-edge hover:text-bright sm:bottom-6 sm:right-6 sm:py-2 md:right-[var(--notebook-clear)]"
      >
        CHAT
        {unread > 0 && (
          <span className="numeral ml-2 bg-bright px-1.5 text-[10px] text-ink">
            {unread}
          </span>
        )}
      </button>
    );
  }

  return (
    // On a phone the map pane is short, so chat takes the width and only as
    // much height as it can have without covering the whole city.
    <div className="absolute inset-x-3 bottom-3 z-[1000] flex h-[min(320px,60%)] flex-col border border-line bg-surface/97 backdrop-blur sm:inset-x-auto sm:right-6 sm:bottom-6 sm:h-[340px] sm:w-[320px] md:right-[var(--notebook-clear)]">
      <header className="flex items-center justify-between border-b border-line px-4 py-2">
        <span className="text-[10px] tracking-[0.25em] text-faint">
          THE FIRM
        </span>
        <button
          onClick={() => setOpen(false)}
          className="text-[13px] leading-none text-faint hover:text-muted"
          aria-label="Close chat"
        >
          ×
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto overscroll-contain px-4 py-3">
        {!messages.length && (
          <p className="font-serif text-[13px] italic text-ghost">
            Nobody has said anything yet.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id}>
            <span
              className={`text-[10px] tracking-[0.15em] ${
                m.userId === youId ? "text-muted" : "text-faint"
              }`}
            >
              {m.userId === youId ? "YOU" : m.displayName.toUpperCase()}
            </span>
            <p className="font-serif text-[13px] leading-snug text-muted">
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
        className="border-t border-line p-2"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={500}
          placeholder="Say something"
          // 16px on a phone, or focusing the field zooms the map behind it.
          className="w-full bg-transparent px-2 py-1.5 font-serif text-[16px] text-bright outline-none placeholder:text-ghost sm:text-[13px]"
        />
      </form>
    </div>
  );
}
