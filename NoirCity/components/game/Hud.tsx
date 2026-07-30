"use client";

import { useEffect, useState } from "react";
import type { ClientView } from "@/lib/engine/view";
import { formatCountdown } from "@/lib/engine/storyClock";

/**
 * Two clocks, measuring two different pressures.
 *
 * The countdown is real minutes at the table and is the HARD limit - it is what
 * a group actually feels, and when it hits zero the case closes. The story clock
 * is the in-fiction date and time, moved by what the team spends; it gates what
 * you can still afford and stamps every journal entry.
 */

/** Colour for the story clock, by how much of the budget is left. */
export function timeTone(fraction: number): string {
  if (fraction > 0.5) return "text-neutral-200";
  if (fraction > 0.25) return "text-amber-300";
  return "text-red-400";
}

export function Hud({
  view,
  now,
  sessionRemainingMs,
  onRestart,
}: {
  view: ClientView;
  now: { dateline: string; time: string; day: number };
  sessionRemainingMs: number;
  /** Absent in a shared room - one player cannot reset everyone's case. */
  onRestart?: () => void;
}) {
  const closed = view.state.status === "finished";
  const remaining = useLocalCountdown(sessionRemainingMs, closed);

  return (
    <header className="shrink-0 border-b border-neutral-800 px-5 py-3 sm:px-6 sm:py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate font-serif text-base leading-tight text-neutral-100 sm:text-lg">
            {view.title}
          </h1>
          <p className="mt-1 text-[10px] tracking-[0.2em] text-neutral-600">
            DAY {now.day} &middot; {now.time} &middot;{" "}
            <span className={timeTone(view.state.timeRemaining / view.timeBudget)}>
              {view.state.timeRemaining}H IN HAND
            </span>
          </p>
        </div>

        <div className="shrink-0 text-right">
          <p
            className={`font-mono text-lg leading-none tabular-nums sm:text-xl ${countdownTone(remaining, closed)}`}
          >
            {closed ? "--:--:--" : formatCountdown(remaining)}
          </p>
          <p className="mt-1 text-[9px] tracking-[0.2em] text-neutral-600">
            {closed ? "CLOSED" : "AT THE TABLE"}
          </p>
        </div>
      </div>

      {onRestart && (
        <button
          onClick={onRestart}
          className="mt-2 text-[10px] tracking-[0.2em] text-neutral-700 transition hover:text-neutral-400"
        >
          RESTART
        </button>
      )}
    </header>
  );
}

function countdownTone(remainingMs: number, closed: boolean): string {
  if (closed) return "text-neutral-600";
  const minutes = remainingMs / 60_000;
  if (minutes > 15) return "text-neutral-100";
  if (minutes > 5) return "text-amber-300";
  return "animate-pulse text-red-400";
}

/**
 * Ticks the server's figure down locally rather than polling, and re-syncs
 * whenever a fresh one arrives - so drift never accumulates and the deadline
 * itself is still decided by the server.
 */
export function useLocalCountdown(fromServer: number, frozen: boolean): number {
  const [remaining, setRemaining] = useState(fromServer);

  useEffect(() => {
    setRemaining(fromServer);
  }, [fromServer]);

  useEffect(() => {
    if (frozen) return;
    const id = setInterval(() => setRemaining((r) => Math.max(0, r - 1000)), 1000);
    return () => clearInterval(id);
  }, [frozen]);

  return remaining;
}
