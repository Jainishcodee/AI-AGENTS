"use client";

import type { TutorialProgress } from "@/lib/engine/tutorial";

/**
 * Teaches the five verbs and then disappears for good. It never says anything
 * about the solution - a player who finishes the tutorial still has to work out
 * who did it on their own.
 */
export function TutorialPanel({ progress }: { progress: TutorialProgress }) {
  const step = progress.current;
  if (!step) return null;

  return (
    <section className="shrink-0 border-b border-line bg-raised/50 px-5 py-5 sm:px-6">
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] tracking-[0.3em] text-muted">{step.verb}</p>
        <p className="numeral text-[10px] tracking-[0.2em] text-faint">
          {progress.index + 1} / {progress.total}
        </p>
      </div>

      <h2 className="mt-2 font-serif text-base text-bright">{step.title}</h2>

      {step.body.split("\n\n").map((para, i) => (
        <p key={i} className="mt-2 text-[13px] leading-relaxed text-muted">
          {para}
        </p>
      ))}

      <div className="mt-4 flex gap-1">
        {Array.from({ length: progress.total }, (_, i) => (
          <span
            key={i}
            className={`h-px flex-1 ${i < progress.index ? "bg-muted" : "bg-line"}`}
          />
        ))}
      </div>
    </section>
  );
}
