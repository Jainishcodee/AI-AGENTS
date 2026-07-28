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
  onRestart: () => void;
}) {
  const result = view.result;
  if (!result) return null;

  const named = view.suspects.find((s) => s.id === result.accusation.culpritId);

  return (
    <div className="absolute inset-0 z-[2000] overflow-y-auto bg-[#08090b]/97 backdrop-blur-sm">
      <div className="mx-auto max-w-2xl px-8 py-16">
        <p className="text-[10px] tracking-[0.4em] text-neutral-600">
          {result.solved
            ? "CASE CLOSED"
            : result.culpritCorrect
              ? "PARTLY RIGHT"
              : "THEY WALKED"}
        </p>

        <h1
          className={`mt-3 font-serif text-3xl leading-tight ${
            result.solved ? "text-amber-100" : "text-neutral-300"
          }`}
        >
          You named {named?.name}.
        </h1>

        <div className="mt-8 grid grid-cols-3 gap-px border border-neutral-800 bg-neutral-800 text-center">
          <Cell label="CULPRIT" ok={result.culpritCorrect} />
          <Cell label="MOTIVE" ok={result.motiveCorrect} />
          <Cell
            label="EVIDENCE"
            ok={result.correctEvidenceIds.length === 3}
            note={`${result.correctEvidenceIds.length} of 3`}
          />
        </div>

        <div className="mt-8 flex items-baseline gap-8 border-y border-neutral-800 py-5">
          <div>
            <p className="font-serif text-4xl tabular-nums text-neutral-100">
              {result.score}
            </p>
            <p className="mt-1 text-[10px] tracking-[0.2em] text-neutral-600">
              POINTS
            </p>
          </div>
          <ul className="space-y-1 text-[12px] text-neutral-500">
            {result.culpritCorrect && <li>Right person &mdash; 50</li>}
            {result.motiveCorrect && <li>Right reason &mdash; 25</li>}
            {result.correctEvidenceIds.length > 0 && (
              <li>Evidence that held up &mdash; {result.correctEvidenceIds.length * 5}</li>
            )}
            {result.timeBonus > 0 && <li>Hours to spare &mdash; {result.timeBonus}</li>}
            {result.redHerringIds.length > 0 && (
              <li className="text-red-400">
                Evidence that fell apart &mdash; {result.redHerringIds.length * 10}
              </li>
            )}
          </ul>
        </div>

        {result.redHerringIds.length > 0 && (
          <p className="mt-6 font-serif text-[13px] italic leading-relaxed text-red-300/70">
            {result.redHerringIds.length === 1
              ? "One of the things you submitted proved nothing at all."
              : `${result.redHerringIds.length} of the things you submitted proved nothing at all.`}
          </p>
        )}

        <div className="mt-8 space-y-4">
          {result.epilogue.split("\n\n").map((para, i) => (
            <p
              key={i}
              className="font-serif text-[15px] leading-relaxed text-neutral-300"
            >
              {para}
            </p>
          ))}
        </div>

        <div className="mt-12 flex gap-3">
          <button
            onClick={onRestart}
            className="border border-neutral-700 px-6 py-3 text-[11px] tracking-[0.2em] text-neutral-300 transition hover:border-amber-200/50 hover:text-amber-100"
          >
            RUN IT AGAIN
          </button>
          <Link
            href="/"
            className="border border-neutral-800 px-6 py-3 text-[11px] tracking-[0.2em] text-neutral-500 transition hover:text-neutral-300"
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
    <div className="bg-[#0e0f11] px-3 py-4">
      <p className={`font-serif text-xl ${ok ? "text-amber-200" : "text-neutral-700"}`}>
        {ok ? "✓" : "✕"}
      </p>
      <p className="mt-1.5 text-[10px] tracking-[0.2em] text-neutral-600">{label}</p>
      {note && <p className="mt-0.5 text-[10px] text-neutral-700">{note}</p>}
    </div>
  );
}
