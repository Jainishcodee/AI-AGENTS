"use client";

/**
 * Recording what actually happened.
 *
 * The single highest-value screen in the product, and the one that was missing: the
 * council's programs are copyable in an afternoon, the resolved corpus is not, and the
 * corpus only exists if this form is easy enough that somebody fills it in.
 *
 * Three deliberate choices:
 *
 * - **"What did you actually do" is free text, not a picker.** People do not choose
 *   from the menu, and a card where they did something no module proposed is a direct
 *   measurement of the council's option-generation blindness. Constraining it to the
 *   options would delete the most informative rows in the dataset.
 * - **Surprises are a first-class field**, not a note. "What nobody predicted" is its
 *   own signal and feeds a council-level prior.
 * - **The prediction is shown while you write.** It was recorded before the outcome
 *   was known; seeing it here is what makes this a check rather than a reminiscence.
 */

import { useState } from "react";
import type { DecisionCard } from "@/lib/types";
import { sendJSON } from "@/lib/stream";
import { Button, Chip, Label } from "./ui";

export function ResolveForm({
  card,
  onResolved,
}: {
  card: DecisionCard;
  onResolved: (updated: DecisionCard) => void;
}) {
  const [chose, setChose] = useState("");
  const [outcome, setOutcome] = useState("");
  const [surprises, setSurprises] = useState<string[]>([""]);
  const [notes, setNotes] = useState("");
  const [happenedAt, setHappenedAt] = useState(() => new Date().toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = chose.trim().length > 2 && outcome.trim().length > 2;

  const submit = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await sendJSON<DecisionCard>(`cards/${card.id}/resolve`, {
        chose: chose.trim(),
        actual_outcome: outcome.trim(),
        happened_at: happenedAt,
        surprises: surprises.map((s) => s.trim()).filter(Boolean),
        notes: notes.trim(),
      });
      onResolved(updated);
    } catch (cause) {
      // The API saves the resolution before grading, so a grader failure has not
      // lost the outcome — say so rather than implying the work was wasted.
      setError(String(cause instanceof Error ? cause.message : cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      {card.expected_outcome && (
        <div className="rounded border-l-2 border-l-[var(--color-inferred)] bg-[var(--color-raised)] px-3 py-2.5">
          <Label className="mb-1">what the council predicted, before it knew</Label>
          <p className="text-[13.5px] leading-relaxed">{card.expected_outcome.statement}</p>
          {card.expected_outcome.measurable_by && (
            <p className="mt-1 text-[11.5px] text-[var(--color-faint)]">
              measured by {card.expected_outcome.measurable_by}
            </p>
          )}
        </div>
      )}

      <Field
        label="what did you actually do?"
        hint="In your own words. If you did something no module suggested, say that — it is the most useful answer in here."
      >
        <textarea
          value={chose}
          onChange={(event) => setChose(event.target.value)}
          rows={2}
          placeholder="Stayed, but asked for the offer in writing with a deadline."
          className="w-full resize-y rounded border bg-[var(--color-surface)] px-3 py-2 text-[13.5px] leading-relaxed outline-none hair placeholder:text-[var(--color-faint)] focus:border-[#34343c]"
        />
      </Field>

      <Field label="what happened as a result?">
        <textarea
          value={outcome}
          onChange={(event) => setOutcome(event.target.value)}
          rows={3}
          placeholder="The offer arrived nine days later. My manager was relieved I asked directly."
          className="w-full resize-y rounded border bg-[var(--color-surface)] px-3 py-2 text-[13.5px] leading-relaxed outline-none hair placeholder:text-[var(--color-faint)] focus:border-[#34343c]"
        />
      </Field>

      <Field
        label="did anything happen that nobody predicted?"
        hint="Its own field, not a note — it feeds a council-level prior about what the six keep missing."
      >
        <div className="space-y-1.5">
          {surprises.map((value, index) => (
            <input
              key={index}
              value={value}
              onChange={(event) => {
                const next = [...surprises];
                next[index] = event.target.value;
                // Grow the list as it is filled, so there is always one empty row and
                // never a button to press first.
                if (index === surprises.length - 1 && event.target.value.trim()) next.push("");
                setSurprises(next);
              }}
              placeholder={index === 0 ? "Someone nobody mentioned turned out to decide it." : ""}
              className="w-full rounded border bg-[var(--color-surface)] px-3 py-1.5 text-[13px] outline-none hair placeholder:text-[var(--color-faint)] focus:border-[#34343c]"
            />
          ))}
        </div>
      </Field>

      <div className="flex flex-wrap items-end gap-5">
        <Field label="when">
          <input
            type="date"
            value={happenedAt}
            onChange={(event) => setHappenedAt(event.target.value)}
            className="rounded border bg-[var(--color-surface)] px-2.5 py-1.5 text-[13px] outline-none hair focus:border-[#34343c]"
          />
        </Field>
        <Field label="anything else">
          <input
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            className="w-full min-w-[220px] rounded border bg-[var(--color-surface)] px-3 py-1.5 text-[13px] outline-none hair focus:border-[#34343c]"
          />
        </Field>
      </div>

      {error && (
        <div className="rounded border border-[var(--color-speculative)]/40 px-3 py-2 text-[12.5px] leading-relaxed">
          <span className="text-[var(--color-speculative)]">{error}</span>
          <p className="mt-1 text-[var(--color-faint)]">
            If grading failed, the outcome itself was still saved — reload and grade again
            rather than retyping it.
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t pt-3 hair">
        <Button variant="primary" onClick={submit} disabled={!ready || busy}>
          {busy ? "scoring the council…" : "Record and score"}
        </Button>
        <span className="text-[11.5px] leading-relaxed text-[var(--color-faint)]">
          Every module gets graded against what it said. The grader is never shown how
          confident any of them were.
        </span>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <Label className="mb-1">{label}</Label>
      {hint && (
        <p className="mb-1.5 text-[11.5px] leading-relaxed text-[var(--color-faint)]">{hint}</p>
      )}
      {children}
    </div>
  );
}

/** What the grader concluded, once a card has been scored. */
export function ScoringPanel({ card }: { card: DecisionCard }) {
  const scoring = card.scoring;
  if (!scoring) return null;

  const VERDICT_COLOUR: Record<string, string> = {
    right: "var(--color-given)",
    partial: "var(--color-assumed)",
    wrong: "var(--color-speculative)",
    untested: "var(--color-unknown)",
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Label>prediction</Label>
        <Chip
          colour={
            scoring.expected_outcome_met === "yes"
              ? "var(--color-given)"
              : scoring.expected_outcome_met === "no"
                ? "var(--color-speculative)"
                : "var(--color-assumed)"
          }
        >
          {scoring.expected_outcome_met}
        </Chip>
        {!scoring.chose_was_proposed && (
          <Chip
            colour="var(--color-assumed)"
            title="A finding about the council, not about you — it feeds back as a prior"
          >
            you did something no module proposed
          </Chip>
        )}
      </div>

      <div>
        <Label className="mb-2">how each module fared</Label>
        <div className="space-y-2">
          {scoring.module_verdicts.map((verdict) => (
            <div key={verdict.module} className="flex gap-3">
              <span className="mono w-[92px] shrink-0 truncate pt-[2px] text-[11.5px] text-[var(--color-muted)]">
                {verdict.module}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Chip colour={VERDICT_COLOUR[verdict.verdict]}>{verdict.verdict}</Chip>
                  {verdict.followed && <Chip>you acted on it</Chip>}
                  {verdict.falsifier_fired && (
                    <Chip colour="var(--color-assumed)" title="The observation it named as disqualifying did occur">
                      its falsifier fired
                    </Chip>
                  )}
                  {verdict.overridden && <Chip colour="var(--color-inferred)">you overrode this</Chip>}
                </div>
                {verdict.justification && (
                  <p className="mt-1 text-[12.5px] leading-snug text-[var(--color-muted)]">
                    {verdict.justification}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {scoring.unpredicted.length > 0 && (
        <div>
          <Label className="mb-1">nobody predicted</Label>
          <ul className="space-y-1">
            {scoring.unpredicted.map((item, index) => (
              <li key={index} className="text-[13px] leading-relaxed">
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="border-t pt-3 text-[11.5px] leading-relaxed text-[var(--color-faint)] hair">
        `untested` means you never acted on that module, so nothing here shows whether it
        would have worked. It is excluded from accuracy but still counts against how often
        the module&apos;s advice gets taken.
      </p>
    </div>
  );
}
