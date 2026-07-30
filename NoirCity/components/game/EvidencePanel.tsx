"use client";

import { useState } from "react";
import type { Action } from "@/lib/engine/reducer";
import type { ClientView, PublicClue } from "@/lib/engine/view";

const TYPE_LABEL: Record<PublicClue["type"], string> = {
  physical: "PHYSICAL",
  document: "DOCUMENT",
  statement: "STATEMENT",
  forensic: "FORENSIC",
  photo: "PHOTOGRAPH",
};

/**
 * Everything the team holds. Documents render as paper rather than as another
 * card in a list, because reading a torn ledger page should not feel like
 * reading a database row.
 */
export function EvidencePanel({
  view,
  act,
  busy,
}: {
  view: ClientView;
  act: (a: Action) => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState<string | null>(view.clues[0]?.id ?? null);
  const closed = view.state.status === "finished";

  if (!view.clues.length) {
    return (
      <p className="px-5 py-8 font-serif text-[14px] leading-relaxed text-faint sm:px-6">
        Nothing yet. Evidence turns up by searching places and pressing people —
        and both cost hours you will want back later.
      </p>
    );
  }

  return (
    <div className="divide-y divide-line">
      {view.clues.map((clue) => {
        const isOpen = open === clue.id;
        const suspect = clue.implicates
          ? view.suspects.find((s) => s.id === clue.implicates)
          : null;

        return (
          <article key={clue.id}>
            <button
              onClick={() => setOpen(isOpen ? null : clue.id)}
              className="flex w-full items-baseline justify-between px-5 py-3.5 text-left lift hover:bg-surface/40 sm:px-6"
            >
              <span>
                <span className="block font-serif text-[15px] leading-tight text-bright">
                  {clue.title}
                </span>
                <span className="mt-0.5 block text-[10px] tracking-[0.2em] text-faint">
                  {TYPE_LABEL[clue.type]}
                  {suspect && ` · POINTS AT ${suspect.name.toUpperCase()}`}
                </span>
              </span>
              <span className="ml-3 text-ghost">{isOpen ? "−" : "+"}</span>
            </button>

            {isOpen && (
              <div className="px-5 pb-5 sm:px-6">
                <div
                  className={
                    clue.type === "document" || clue.type === "forensic"
                      ? "border-l-2 border-edge bg-bright/[0.02] py-3 pl-4 pr-3 font-mono text-[12.5px] leading-relaxed text-muted"
                      : "font-serif text-[14px] leading-relaxed text-muted"
                  }
                >
                  {clue.body}
                </div>

                {clue.labTestable && (
                  <button
                    disabled={busy || closed || clue.labTested}
                    onClick={() => act({ type: "lab", clueId: clue.id })}
                    className="mt-4 w-full border border-edge px-4 py-2 text-[11px] tracking-[0.2em] text-muted lift hover:border-muted hover:text-bright disabled:cursor-not-allowed disabled:opacity-30"
                  >
                    {clue.labTested
                      ? "SENT TO THE LAB"
                      : "SEND TO THE LAB — 4 HOURS"}
                  </button>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
