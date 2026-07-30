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

/**
 * Colour for the story clock, by how much of the budget is left.
 *
 * One of only three places gold is allowed: a clock under pressure. It means
 * something precisely because nothing else on the screen is that colour.
 */
export function timeTone(fraction: number): string {
  if (fraction > 0.5) return "text-bright";
  if (fraction > 0.25) return "text-gold";
  return "text-danger";
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
    <header className="shrink-0 border-b border-line px-5 py-3 sm:px-6 sm:py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate font-serif text-base leading-tight text-bright sm:text-lg">
            {view.title}
          </h1>
          <p
            className="mt-1 text-[10px] tracking-[0.2em] text-faint"
            data-testid="story-clock"
          >
            {/* The figures take the numeral face even mid-label: `now.time`
                changes as the team spends, and unequal digit widths make the
                whole line shuffle sideways when it does. */}
            DAY <span className="numeral">{now.day}</span> &middot;{" "}
            <span className="numeral">{now.time}</span> &middot;{" "}
            <span className={timeTone(view.state.timeRemaining / view.timeBudget)}>
              <span className="numeral" data-testid="hours-left">
                {view.state.timeRemaining}
              </span>
              H IN HAND
            </span>
          </p>
        </div>

        <div className="shrink-0 text-right">
          <p
            data-testid="countdown"
            className={`numeral text-lg leading-none sm:text-xl ${countdownTone(remaining, closed)}`}
          >
            {closed ? "--:--:--" : formatCountdown(remaining)}
          </p>
          <p className="mt-1 text-[9px] tracking-[0.2em] text-faint">
            {closed ? "CLOSED" : "AT THE TABLE"}
          </p>
        </div>
      </div>

      {onRestart && (
        <button
          onClick={onRestart}
          className="mt-2 text-[10px] tracking-[0.2em] text-ghost lift hover:text-muted"
        >
          RESTART
        </button>
      )}
    </header>
  );
}

function countdownTone(remainingMs: number, closed: boolean): string {
  if (closed) return "text-faint";
  const minutes = remainingMs / 60_000;
  if (minutes > 15) return "text-bright";
  if (minutes > 5) return "text-gold";
  return "animate-pulse text-danger";
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
