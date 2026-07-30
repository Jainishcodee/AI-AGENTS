"use client";

import { useState } from "react";
import type { Action } from "@/lib/engine/reducer";
import type { ClientView } from "@/lib/engine/view";

const EVIDENCE_SLOTS = 3;

/**
 * One attempt, and the game says so up front. Nothing here hints at whether a
 * choice is right - the form will happily let you file a confident, wrong
 * accusation, which is the point.
 */
export function AccusePanel({
  view,
  act,
  busy,
}: {
  view: ClientView;
  act: (a: Action) => void;
  busy: boolean;
}) {
  const [culpritId, setCulprit] = useState<string | null>(null);
  const [motiveId, setMotive] = useState<string | null>(null);
  const [evidenceIds, setEvidence] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);

  const ready = culpritId && motiveId && evidenceIds.length === EVIDENCE_SLOTS;

  function toggleEvidence(id: string) {
    setEvidence((prev) =>
      prev.includes(id)
        ? prev.filter((x) => x !== id)
        : prev.length < EVIDENCE_SLOTS
          ? [...prev, id]
          : prev,
    );
  }

  return (
    <div className="space-y-7 px-5 py-5 sm:px-6">
      <p className="border border-danger/40 bg-danger/10 px-4 py-3 font-serif text-[13px] leading-relaxed text-muted">
        You get one attempt. Name a person, a reason, and three pieces of
        evidence that prove it. Nobody will tell you when you are ready.
      </p>

      <section>
        <p className="text-[10px] tracking-[0.3em] text-faint">
          WHO KILLED THEM
        </p>
        <ul className="mt-3 space-y-2">
          {view.suspects.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => setCulprit(s.id)}
                className={`w-full border px-4 py-3 text-left lift ${
                  culpritId === s.id
                    ? "border-danger/50 bg-danger/20"
                    : "border-line hover:border-edge"
                }`}
              >
                <span className="block font-serif text-[15px] text-bright">
                  {s.name}
                </span>
                <span className="mt-0.5 block text-[11px] text-faint">
                  {s.occupation}
                </span>
                <span className="mt-2 block font-serif text-[12.5px] leading-relaxed text-faint">
                  {s.summary}
                </span>
                <span className="mt-2 block text-[12px] italic leading-relaxed text-faint">
                  Alibi: {s.alibi}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <p className="text-[10px] tracking-[0.3em] text-faint">WHY</p>
        <ul className="mt-3 space-y-2">
          {view.motives.map((m) => (
            <li key={m.id}>
              <button
                onClick={() => setMotive(m.id)}
                className={`w-full border px-4 py-2.5 text-left lift ${
                  motiveId === m.id
                    ? "border-danger/50 bg-danger/20"
                    : "border-line hover:border-edge"
                }`}
              >
                <span className="block font-serif text-[14px] text-bright">
                  {m.label}
                </span>
                <span className="mt-1 block font-serif text-[12.5px] leading-relaxed text-faint">
                  {m.description}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <div className="flex items-baseline justify-between">
          <p className="text-[10px] tracking-[0.3em] text-faint">
            WHAT PROVES IT
          </p>
          <p className="numeral text-[10px] tracking-[0.2em] text-faint">
            {evidenceIds.length} / {EVIDENCE_SLOTS}
          </p>
        </div>
        {!view.clues.length && (
          <p className="mt-3 font-serif text-[13px] text-faint">
            You have not found anything to submit.
          </p>
        )}
        <ul className="mt-3 space-y-1.5">
          {view.clues.map((c) => {
            const picked = evidenceIds.includes(c.id);
            return (
              <li key={c.id}>
                <button
                  onClick={() => toggleEvidence(c.id)}
                  className={`w-full border px-3 py-2 text-left font-serif text-[13px] lift ${
                    picked
                      ? "border-danger/50 bg-danger/20 text-bright"
                      : "border-line text-muted hover:border-edge"
                  }`}
                >
                  <span className="mr-2 text-ghost">{picked ? "■" : "□"}</span>
                  {c.title}
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      {!confirming ? (
        <button
          disabled={!ready || busy}
          onClick={() => setConfirming(true)}
          className="w-full border border-danger/60 px-4 py-3 text-[11px] tracking-[0.25em] text-danger lift hover:bg-danger/30 disabled:cursor-not-allowed disabled:border-line disabled:text-ghost"
        >
          FILE THE ACCUSATION
        </button>
      ) : (
        <div className="border border-danger/60 p-4">
          <p className="font-serif text-[13px] leading-relaxed text-muted">
            You are naming{" "}
            <span className="text-bright">
              {view.suspects.find((s) => s.id === culpritId)?.name}
            </span>
            . This closes the case.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => setConfirming(false)}
              className="flex-1 border border-edge px-3 py-2 text-[11px] tracking-[0.2em] text-muted"
            >
              WAIT
            </button>
            <button
              disabled={busy}
              onClick={() =>
                culpritId &&
                motiveId &&
                act({ type: "accuse", culpritId, motiveId, evidenceIds })
              }
              className="flex-1 border border-danger bg-danger/40 px-3 py-2 text-[11px] tracking-[0.2em] text-danger disabled:opacity-40"
            >
              GO AHEAD
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
