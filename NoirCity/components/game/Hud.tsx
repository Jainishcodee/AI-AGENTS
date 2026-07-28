"use client";

import type { ClientView } from "@/lib/engine/view";

/**
 * The clock. Colour shifts as it runs down, because the shared time budget is
 * the only real pressure in the game and it should be impossible to ignore.
 */
export function Hud({ view, onRestart }: { view: ClientView; onRestart: () => void }) {
  const { timeRemaining } = view.state;
  const fraction = timeRemaining / view.timeBudget;

  const tone =
    fraction > 0.5
      ? "text-neutral-200"
      : fraction > 0.25
        ? "text-amber-300"
        : "text-red-400";

  return (
    <header className="flex items-baseline justify-between border-b border-neutral-800 px-6 py-4">
      <div>
        <h1 className="font-serif text-lg leading-tight text-neutral-100">
          {view.title}
        </h1>
        <p className="mt-0.5 text-[10px] tracking-[0.25em] text-neutral-600">
          BACKLUND &middot; {view.clues.length}{" "}
          {view.clues.length === 1 ? "ITEM" : "ITEMS"} IN EVIDENCE
        </p>
      </div>

      <div className="flex items-center gap-5">
        <div className="text-right">
          <p className={`font-serif text-2xl leading-none tabular-nums ${tone}`}>
            {timeRemaining}
          </p>
          <p className="mt-1 text-[10px] tracking-[0.2em] text-neutral-600">
            HOURS LEFT
          </p>
        </div>
        <button
          onClick={onRestart}
          className="text-[10px] tracking-[0.2em] text-neutral-600 transition hover:text-neutral-300"
        >
          RESTART
        </button>
      </div>
    </header>
  );
}
