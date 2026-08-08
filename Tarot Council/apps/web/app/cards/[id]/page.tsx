"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ResolveForm, ScoringPanel } from "@/components/ResolveForm";
import { Bullets, Chip, Label, Meter, Panel, accentOf } from "@/components/ui";
import { getJSON, sendJSON } from "@/lib/stream";
import type { DecisionCard, ModuleSpec, Verdict } from "@/lib/types";

const VERDICTS: Verdict[] = ["right", "partial", "wrong", "untested"];

export default function CardPage() {
  const params = useParams<{ id: string }>();
  const [card, setCard] = useState<DecisionCard | null>(null);
  const [specs, setSpecs] = useState<Record<string, ModuleSpec>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getJSON<DecisionCard>(`cards/${params.id}`),
      getJSON<ModuleSpec[]>("modules"),
    ])
      .then(([found, moduleList]) => {
        if (cancelled) return;
        setCard(found);
        setSpecs(Object.fromEntries(moduleList.map((m) => [m.id, m])));
      })
      .catch((cause) => !cancelled && setError(String(cause?.message ?? cause)));
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  if (error) {
    return (
      <main className="mx-auto w-full max-w-[900px] px-4 py-7 sm:px-6">
        <p className="text-[13px] text-[var(--color-speculative)]">{error}</p>
        <Link href="/history" className="mt-3 inline-block text-[13px] text-[var(--color-muted)] underline decoration-dotted underline-offset-2">
          ← all decisions
        </Link>
      </main>
    );
  }
  if (!card) {
    return (
      <main className="mx-auto w-full max-w-[900px] px-4 py-7 sm:px-6">
        <p className="text-[13px] text-[var(--color-faint)]">loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-[900px] px-4 py-7 sm:px-6 lg:px-8">
      <Link
        href="/history"
        className="text-[12px] text-[var(--color-faint)] transition-colors hover:text-[var(--color-text)]"
      >
        ← all decisions
      </Link>

      <h1 className="serif mt-3 text-[20px] leading-snug">{card.question}</h1>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Chip>{card.preset}</Chip>
        <Chip>{card.depth}</Chip>
        {card.domains.map((domain) => (
          <Chip key={domain}>{domain}</Chip>
        ))}
        <span className="mono text-[10.5px] text-[var(--color-faint)]">
          {card.created_at.slice(0, 10)} · card {card.id}
        </span>
        <Link
          href={`/?deliberation=${card.deliberation_id}`}
          className="mono text-[10.5px] text-[var(--color-faint)] underline decoration-dotted underline-offset-2 hover:text-[var(--color-text)]"
        >
          full transcript
        </Link>
      </div>

      <section className="mt-6 space-y-2">
        <Label>what the council recommended</Label>
        <p className="text-[15px] leading-relaxed">{card.recommendation.action}</p>
        <p className="text-[13px] leading-relaxed text-[var(--color-muted)]">
          <span className="label mr-1.5">first step</span>
          {card.recommendation.first_action}
        </p>
        {card.recommendation.do_not.length > 0 && (
          <div className="pt-1">
            <Label className="mb-1">do not</Label>
            <Bullets items={card.recommendation.do_not} colour="var(--color-speculative)" />
          </div>
        )}
      </section>

      <section className="mt-6">
        <Label className="mb-2">what each module said at the time</Label>
        <div className="space-y-2.5">
          {card.per_module.map((stance) => {
            const accent = accentOf(stance.module, specs[stance.module]?.skin.accent);
            const verdict = card.scoring?.module_verdicts.find((v) => v.module === stance.module);
            return (
              <div key={stance.module} className="border-l-2 pl-3" style={{ borderColor: accent }}>
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-[12.5px] font-medium" style={{ color: accent }}>
                    {specs[stance.module]?.skin.name ?? stance.module}
                  </span>
                  {stance.confidence && <Meter value={stance.confidence.score} width={40} />}
                  {stance.abstained && <Chip colour="var(--color-speculative)">abstained</Chip>}
                  {verdict && <VerdictControl card={card} module={stance.module} current={verdict.verdict} onChange={setCard} />}
                </div>
                {stance.stance && (
                  <p className="mt-0.5 text-[13px] leading-snug">{stance.stance}</p>
                )}
                {stance.confidence && (
                  <p className="mt-0.5 text-[11.5px] leading-snug text-[var(--color-faint)]">
                    said it would be wrong if: {stance.confidence.falsifier}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {card.minority_opinions.length > 0 && (
        <section className="mt-6">
          <Label className="mb-2">minority opinions, kept on the record</Label>
          <div className="space-y-2">
            {card.minority_opinions.map((minority, index) => (
              <div key={index} className="text-[13px] leading-relaxed">
                <span className="mono mr-2 text-[11px] text-[var(--color-muted)]">
                  {minority.module}
                </span>
                {minority.position}
                <div className="text-[12px] text-[var(--color-faint)]">
                  right if: {minority.when_it_would_be_right}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <hr className="my-7 border-0 border-t hair" />

      {card.resolution ? (
        <section className="space-y-5">
          <div>
            <Label className="mb-2">what happened</Label>
            <p className="text-[13.5px] leading-relaxed">
              <span className="label mr-1.5">you did</span>
              {card.resolution.chose}
            </p>
            <p className="mt-1.5 text-[13.5px] leading-relaxed text-[var(--color-muted)]">
              {card.resolution.actual_outcome}
            </p>
            {card.resolution.surprises.length > 0 && (
              <div className="mt-2">
                <Label className="mb-1">nobody predicted</Label>
                <Bullets items={card.resolution.surprises} colour="var(--color-assumed)" />
              </div>
            )}
            <p className="mt-2 mono text-[10.5px] text-[var(--color-faint)]">
              recorded for {card.resolution.happened_at}
            </p>
          </div>

          {card.scoring ? (
            <Panel className="p-4">
              <ScoringPanel card={card} />
            </Panel>
          ) : (
            <RegradeButton cardId={card.id} onGraded={setCard} />
          )}
        </section>
      ) : (
        <section>
          <h2 className="mb-1 text-[14px] font-medium">Record what actually happened</h2>
          <p className="mb-4 text-[12.5px] leading-relaxed text-[var(--color-faint)]">
            Until this is filled in, nothing in the system learns anything — there is no
            ground truth about a decision except the outcome.
          </p>
          <ResolveForm card={card} onResolved={setCard} />
        </section>
      )}
    </main>
  );
}

/**
 * Overriding a verdict.
 *
 * The grader is a labour-saving first pass, not an authority: the user is the final
 * judge of their own life, and a wrong verdict left in place would quietly corrupt
 * their calibration history. Overrides are flagged in the record.
 */
function VerdictControl({
  card,
  module,
  current,
  onChange,
}: {
  card: DecisionCard;
  module: string;
  current: Verdict;
  onChange: (card: DecisionCard) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const set = async (verdict: Verdict) => {
    setBusy(true);
    try {
      const updated = await sendJSON<DecisionCard>(
        `cards/${card.id}/verdict/${module}`,
        { verdict },
        "PATCH",
      );
      onChange(updated);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  };

  const COLOUR: Record<Verdict, string> = {
    right: "var(--color-given)",
    partial: "var(--color-assumed)",
    wrong: "var(--color-speculative)",
    untested: "var(--color-unknown)",
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Disagree with this verdict? You are the final judge."
        className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10.5px] leading-none transition-colors hover:brightness-125"
        style={{
          borderColor: `${COLOUR[current]}55`,
          color: COLOUR[current],
          background: `${COLOUR[current]}12`,
        }}
      >
        {current}
      </button>
    );
  }

  return (
    <span className="inline-flex gap-1">
      {VERDICTS.map((verdict) => (
        <button
          key={verdict}
          type="button"
          disabled={busy}
          onClick={() => set(verdict)}
          className="rounded border px-1.5 py-0.5 text-[10.5px] leading-none transition-colors disabled:opacity-40"
          style={{
            borderColor: verdict === current ? COLOUR[verdict] : "var(--color-line)",
            color: COLOUR[verdict],
          }}
        >
          {verdict}
        </button>
      ))}
    </span>
  );
}

function RegradeButton({
  cardId,
  onGraded,
}: {
  cardId: string;
  onGraded: (card: DecisionCard) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="rounded border border-[var(--color-assumed)]/40 px-3 py-2.5">
      <p className="text-[13px] leading-relaxed">
        The outcome was saved but the modules were not scored — grading failed or was
        skipped.
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            onGraded(await sendJSON<DecisionCard>(`cards/${cardId}/grade`, {}));
          } catch (cause) {
            setError(String(cause instanceof Error ? cause.message : cause));
          } finally {
            setBusy(false);
          }
        }}
        className="mt-2 rounded border px-2.5 py-1 text-[12.5px] transition-colors hair hover:border-[#34343c] disabled:opacity-40"
      >
        {busy ? "grading…" : "Score the council now"}
      </button>
      {error && <p className="mt-2 text-[12px] text-[var(--color-speculative)]">{error}</p>}
    </div>
  );
}
