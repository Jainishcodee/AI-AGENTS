"use client";

/**
 * Answering an unknown while the council is still thinking.
 *
 * The council states what it was not told — `missing_inputs` from intake, and the
 * modules' own `EvidenceGaps`. Before this existed the UI displayed those and left the
 * user to watch six modules reason around a hole they could have filled in ten seconds.
 *
 * The honesty here matters: a fact supplied now reaches only the stages that have not
 * started, so the panel says which modules have already finished rather than implying
 * the whole council will reconsider. Facts already applied are listed, because a
 * transcript that quietly absorbed late information would be unreadable afterwards.
 */

import { useMemo, useState } from "react";
import type { Artifact, DecisionContext } from "@/lib/types";
import type { LiveModule } from "@/lib/useDeliberation";
import { Chip, Label } from "./ui";

export function GapPanel({
  context,
  modules,
  injected,
  running,
  onInject,
}: {
  context: DecisionContext | null;
  modules: LiveModule[];
  injected: string[];
  running: boolean;
  onInject: (facts: string[]) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The gaps worth showing are the ones a module said would change its answer.
  const gaps = useMemo(() => {
    const out: { text: string; from: string }[] = [];
    for (const item of context?.missing_inputs ?? []) {
      out.push({ text: item, from: "intake" });
    }
    for (const live of modules) {
      for (const artifact of live.artifacts) {
        if (artifact.kind !== "EvidenceGaps") continue;
        for (const row of rowsOf(artifact)) {
          if (row.would_change_decision) {
            out.push({ text: String(row.question ?? ""), from: live.module });
          }
        }
      }
    }
    return out.filter((gap) => gap.text.trim()).slice(0, 6);
  }, [context, modules]);

  const finished = modules.filter((m) => !m.running).map((m) => m.module);
  const stillRunning = modules.filter((m) => m.running).map((m) => m.module);

  if (!gaps.length && !injected.length && !running) return null;

  const submit = async () => {
    const fact = draft.trim();
    if (!fact || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onInject([fact]);
      setDraft("");
    } catch (cause) {
      setError(String(cause instanceof Error ? cause.message : cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-4 rounded-lg border bg-[var(--color-surface)] px-4 py-3 hair">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Label>what the council was not told</Label>
        {running && stillRunning.length > 0 && (
          <span className="mono text-[10.5px] text-[var(--color-faint)]">
            {stillRunning.length} module{stillRunning.length === 1 ? "" : "s"} still reasoning
          </span>
        )}
      </div>

      {gaps.length > 0 && (
        <ul className="mt-2 space-y-1">
          {gaps.map((gap, index) => (
            <li key={index} className="flex flex-wrap items-baseline gap-2 text-[12.5px] leading-snug">
              <span className="mono shrink-0 text-[10.5px] text-[var(--color-faint)]">
                {gap.from}
              </span>
              <span className="min-w-0 flex-1">{gap.text}</span>
              <button
                type="button"
                onClick={() => setDraft(gap.text.endsWith("?") ? "" : draft)}
                className="hidden"
                aria-hidden
              />
            </li>
          ))}
        </ul>
      )}

      {running ? (
        <div className="mt-3">
          <div className="flex flex-wrap gap-2">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submit();
              }}
              placeholder="Tell them now — e.g. “The offer arrived in writing this morning.”"
              className="min-w-[240px] flex-1 rounded border bg-[var(--color-ink)] px-3 py-1.5 text-[13px] outline-none hair placeholder:text-[var(--color-faint)] focus:border-[#34343c]"
            />
            <button
              type="button"
              onClick={submit}
              disabled={!draft.trim() || busy}
              className="rounded border px-3 py-1.5 text-[12.5px] transition-colors hair hover:border-[#34343c] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? "sending…" : "Tell the council"}
            </button>
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--color-faint)]">
            Reaches every stage that has not started yet.
            {finished.length > 0 && (
              <> Already finished, so unaffected: {finished.join(", ")}.</>
            )}
          </p>
          {error && (
            <p className="mt-1.5 text-[11.5px] text-[var(--color-speculative)]">{error}</p>
          )}
        </div>
      ) : (
        gaps.length > 0 && (
          <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--color-faint)]">
            The council has finished, so these can no longer be answered mid-run — use{" "}
            <span className="mono">refine</span> to answer them and deliberate again
            knowing them.
          </p>
        )
      )}

      {injected.length > 0 && (
        <div className="mt-3 border-t pt-2.5 hair">
          <Label className="mb-1">supplied mid-deliberation</Label>
          <ul className="space-y-1">
            {injected.map((fact, index) => (
              <li key={index} className="flex items-baseline gap-2 text-[12.5px] leading-snug">
                <Chip colour="var(--color-assumed)">late</Chip>
                <span>{fact}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--color-faint)]">
            Marked late in the transcript rather than merged silently — the earlier stages
            genuinely did not have it.
          </p>
        </div>
      )}
    </div>
  );
}

function rowsOf(artifact: Artifact): Record<string, unknown>[] {
  const rows = artifact.data?.rows;
  return Array.isArray(rows) ? (rows as Record<string, unknown>[]) : [];
}
