"use client";

import Link from "next/link";
import type { ClientView } from "@/lib/engine/view";

/**
 * The reveal. Shown over everything, because once the case is closed there is
 * nothing else to look at and the epilogue is the payoff for ninety minutes.
 *
 * The marking is shown in full, point by point. A score on its own tells a
 * player they were wrong without telling them what they missed, and what they
 * missed is the only part worth knowing.
 */
export function Verdict({
  view,
  onRestart,
}: {
  view: ClientView;
  /** Absent in a shared room - the case is closed for everybody. */
  onRestart?: () => void;
}) {
  const result = view.result;
  if (!result) return null;

  return (
    <div className="absolute inset-0 z-[2000] overflow-y-auto overscroll-contain bg-ink/97 backdrop-blur-sm">
      <div className="mx-auto max-w-2xl px-5 py-10 sm:px-8 sm:py-16">
        <p
          className="text-[10px] tracking-[0.4em] text-faint"
          data-testid="verdict-banner"
        >
          {result.solved
            ? "CASE CLOSED"
            : result.culpritCorrect
              ? "PARTLY RIGHT"
              : "THEY WALKED"}
        </p>

        <h1
          data-testid="verdict-headline"
          className={`mt-3 font-serif text-2xl leading-tight sm:text-3xl ${
            result.solved ? "text-paper" : "text-muted"
          }`}
        >
          You named {result.accusation.culpritName}.
        </h1>

        {/* What they wrote, quoted back. It is the thing being marked, and a
            mark you cannot see the working for is just a number. */}
        <blockquote className="mt-6 border-l-2 border-edge pl-4 font-mono text-[12.5px] leading-relaxed text-paper-dim">
          {result.accusation.argument}
        </blockquote>

        <section className="mt-8">
          <p className="text-[10px] tracking-[0.3em] text-faint">
            WHAT YOU ESTABLISHED
          </p>
          <ul className="mt-3 divide-y divide-line border-y border-line">
            {result.points.map((p) => (
              <li key={p.id} className="flex gap-3 py-3">
                <span
                  className={`shrink-0 font-serif text-[15px] leading-snug ${
                    p.credit >= 0.999
                      ? "text-paper"
                      : p.credit > 0
                        ? "text-muted"
                        : "text-ghost"
                  }`}
                >
                  {p.credit >= 0.999 ? "✓" : p.credit > 0 ? "±" : "✕"}
                </span>
                <div className="min-w-0">
                  <p
                    className={`font-serif text-[13.5px] leading-relaxed ${
                      p.credit > 0 ? "text-muted" : "text-faint"
                    }`}
                  >
                    {p.claim}
                  </p>
                  {p.note && (
                    <p className="mt-1 text-[11.5px] italic leading-relaxed text-ghost">
                      {p.note}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {/* Said plainly rather than hidden. A player comparing two runs
              deserves to know whether the same words were marked the same way. */}
          <p className="mt-2 text-[10px] tracking-[0.2em] text-ghost">
            {result.gradedBy === "model"
              ? "MARKED ON MEANING"
              : "MARKED OFFLINE — ON WORDING ALONE"}
          </p>
        </section>

        <div className="mt-8 flex flex-wrap items-baseline gap-x-8 gap-y-4 border-y border-line py-5">
          <div>
            <p className="numeral text-4xl text-bright" data-testid="score">
              {result.score}
            </p>
            <p className="mt-1 text-[10px] tracking-[0.2em] text-faint">POINTS</p>
          </div>
          <ul className="space-y-1 text-[12px] text-faint">
            {result.culpritCorrect ? (
              <li>
                Right person &mdash; <span className="numeral">50</span>
              </li>
            ) : (
              <li className="text-danger">Wrong person &mdash; nothing else counts</li>
            )}
            {result.argumentScore > 0 && (
              <li>
                The case you made &mdash;{" "}
                <span className="numeral">{result.argumentScore}</span>
              </li>
            )}
            {result.timeBonus > 0 && (
              <li>
                Hours to spare &mdash;{" "}
                <span className="numeral">{result.timeBonus}</span>
              </li>
            )}
          </ul>
        </div>

        <div className="mt-8 space-y-4">
          {result.epilogue.split("\n\n").map((para, i) => (
            <p
              key={i}
              className="font-serif text-[15px] leading-relaxed text-muted"
            >
              {para}
            </p>
          ))}
        </div>

        <div className="mt-12 flex flex-wrap gap-3">
          {onRestart && (
            <button
              onClick={onRestart}
              className="border border-edge px-6 py-3.5 text-[11px] tracking-[0.2em] text-muted lift hover:border-muted hover:text-bright sm:py-3"
            >
              RUN IT AGAIN
            </button>
          )}
          <Link
            href="/"
            className="border border-line px-6 py-3.5 text-[11px] tracking-[0.2em] text-faint lift hover:text-muted sm:py-3"
          >
            ANOTHER CASE
          </Link>
        </div>
      </div>
    </div>
  );
}
