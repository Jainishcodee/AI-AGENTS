"use client";

import Link from "next/link";
import type { ClientView } from "@/lib/engine/view";

/**
 * The reveal. Shown over everything, because once the case is closed there is
 * nothing else to look at and the epilogue is the payoff for ninety minutes.
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

  const named = view.suspects.find((s) => s.id === result.accusation.culpritId);

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
          className={`mt-3 font-serif text-2xl leading-tight sm:text-3xl ${
            result.solved ? "text-paper" : "text-muted"
          }`}
        >
          You named {named?.name}.
        </h1>

        <div className="mt-8 grid grid-cols-3 gap-px border border-line bg-raised text-center">
          <Cell label="CULPRIT" ok={result.culpritCorrect} />
          <Cell label="MOTIVE" ok={result.motiveCorrect} />
          <Cell
            label="EVIDENCE"
            ok={result.correctEvidenceIds.length === 3}
            note={`${result.correctEvidenceIds.length} of 3`}
          />
        </div>

        <div className="mt-8 flex flex-wrap items-baseline gap-x-8 gap-y-4 border-y border-line py-5">
          <div>
            <p className="numeral text-4xl text-bright" data-testid="score">
              {result.score}
            </p>
            <p className="mt-1 text-[10px] tracking-[0.2em] text-faint">
              POINTS
            </p>
          </div>
          {/* Every figure the player reads takes the numeral face, down to the
              ones in a breakdown - a column of points that half aligns and half
              does not is worse than one that never tried. */}
          <ul className="space-y-1 text-[12px] text-faint">
            {result.culpritCorrect && (
              <li>
                Right person &mdash; <span className="numeral">50</span>
              </li>
            )}
            {result.motiveCorrect && (
              <li>
                Right reason &mdash; <span className="numeral">25</span>
              </li>
            )}
            {result.correctEvidenceIds.length > 0 && (
              <li>
                Evidence that held up &mdash;{" "}
                <span className="numeral">
                  {result.correctEvidenceIds.length * 5}
                </span>
              </li>
            )}
            {result.timeBonus > 0 && (
              <li>
                Hours to spare &mdash;{" "}
                <span className="numeral">{result.timeBonus}</span>
              </li>
            )}
            {result.redHerringIds.length > 0 && (
              <li className="text-danger">
                Evidence that fell apart &mdash;{" "}
                <span className="numeral">{result.redHerringIds.length * 10}</span>
              </li>
            )}
          </ul>
        </div>

        {result.redHerringIds.length > 0 && (
          <p className="mt-6 font-serif text-[13px] italic leading-relaxed text-danger/70">
            {result.redHerringIds.length === 1
              ? "One of the things you submitted proved nothing at all."
              : `${result.redHerringIds.length} of the things you submitted proved nothing at all.`}
          </p>
        )}

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

function Cell({ label, ok, note }: { label: string; ok: boolean; note?: string }) {
  return (
    <div className="bg-surface px-3 py-4">
      <p className={`font-serif text-xl ${ok ? "text-paper" : "text-ghost"}`}>
        {ok ? "✓" : "✕"}
      </p>
      <p className="mt-1.5 text-[10px] tracking-[0.2em] text-faint">{label}</p>
      {note && <p className="numeral mt-0.5 text-[10px] text-ghost">{note}</p>}
    </div>
  );
}
