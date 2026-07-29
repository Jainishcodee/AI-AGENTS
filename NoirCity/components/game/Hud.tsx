"use client";

import type { ClientView } from "@/lib/engine/view";

/**
 * How urgent the clock looks. Lives out here because on a phone the HUD is
 * folded away most of the time and the sheet handle has to carry the same
 * signal - the same number in the same colour, or it stops meaning anything.
 */
export function timeTone(fraction: number): string {
  return fraction > 0.5
    ? "text-neutral-200"
    : fraction > 0.25
      ? "text-amber-300"
      : "text-red-400";
}

/**
 * The clock. Colour shifts as it runs down, because the shared time budget is
 * the only real pressure in the game and it should be impossible to ignore.
 */
export function Hud({
  view,
  onRestart,
}: {
  view: ClientView;
  /** Absent in a shared room - one player cannot reset everyone's case. */
  onRestart?: () => void;
}) {
  const { timeRemaining } = view.state;
  const tone = timeTone(timeRemaining / view.timeBudget);

  return (
    // The strapline gets its own line rather than sharing one with the clock:
    // a 400px column cannot hold both, and squeezing it made it wrap into the
    // hours instead.
    <header className="shrink-0 border-b border-neutral-800 px-5 py-4 sm:px-6">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="min-w-0 truncate font-serif text-lg leading-tight text-neutral-100">
          {view.title}
        </h1>

        <div className="flex shrink-0 items-center gap-5">
          {/* Phone-hidden: the sheet header above already shows this clock, and
              it stays put when the sheet is folded away. Two of them side by
              side just crowds the title off the screen. */}
          <div className="hidden text-right md:block">
            <p className={`font-serif text-2xl leading-none tabular-nums ${tone}`}>
              {timeRemaining}
            </p>
            <p className="mt-1 text-[10px] tracking-[0.2em] text-neutral-600">
              HOURS LEFT
            </p>
          </div>
          {onRestart && (
            <button
              onClick={onRestart}
              className="text-[10px] tracking-[0.2em] text-neutral-600 transition hover:text-neutral-300"
            >
              RESTART
            </button>
          )}
        </div>
      </div>

      <p className="mt-0.5 text-[10px] tracking-[0.25em] text-neutral-600">
        BACKLUND &middot; {view.clues.length}{" "}
        {view.clues.length === 1 ? "ITEM" : "ITEMS"} IN EVIDENCE
      </p>
    </header>
  );
}
