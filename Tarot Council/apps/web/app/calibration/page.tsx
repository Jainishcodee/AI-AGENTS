"use client";

/**
 * Track record.
 *
 * The screen the whole product is for, and the one where it is easiest to lie. Two
 * honesty rules are visible here rather than implicit:
 *
 * - Nothing is reported below n=8, and the withheld count is shown. An accuracy figure
 *   over three decisions is not a measurement, and presenting one as though it were
 *   would be the most damaging thing this page could do.
 * - Brier is displayed against 0.25 — what always-saying-50% scores — because a number
 *   like "0.21" means nothing without knowing what chance looks like.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { getJSON } from "@/lib/stream";
import type { ModuleScore, ModuleSpec, Prior, ScoresResponse } from "@/lib/types";
import { Chip, Label, Meter, Panel, accentOf } from "@/components/ui";

export default function CalibrationPage() {
  const [scores, setScores] = useState<ScoresResponse | null>(null);
  const [priors, setPriors] = useState<Record<string, Prior[]>>({});
  const [specs, setSpecs] = useState<Record<string, ModuleSpec>>({});
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getJSON<ScoresResponse>(`scores${showAll ? "?all=true" : ""}`),
      getJSON<Record<string, Prior[]>>("priors"),
      getJSON<ModuleSpec[]>("modules"),
    ])
      .then(([scoreData, priorData, moduleList]) => {
        if (cancelled) return;
        setScores(scoreData);
        setPriors(priorData);
        setSpecs(Object.fromEntries(moduleList.map((m) => [m.id, m])));
      })
      .catch((cause) => !cancelled && setError(String(cause?.message ?? cause)));
    return () => {
      cancelled = true;
    };
  }, [showAll]);

  const overall = scores?.scores.filter((s) => s.domain === null) ?? [];
  const byDomain = scores?.scores.filter((s) => s.domain !== null) ?? [];
  const priorCount = Object.values(priors).reduce((total, items) => total + items.length, 0);

  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 py-7 sm:px-6 lg:px-8">
      <div className="mb-5">
        <h1 className="text-[15px] font-medium tracking-tight">Track record</h1>
        <p className="mt-0.5 max-w-2xl text-[12px] leading-relaxed text-[var(--color-faint)]">
          How each module has actually performed on your decisions. Every number here is
          computed from recorded outcomes — the grader that judged them was never shown
          how confident any module was.
        </p>
      </div>

      {error && <p className="text-[13px] text-[var(--color-speculative)]">{error}</p>}

      {scores && overall.length === 0 && (
        <Panel className="p-6">
          <p className="text-[13.5px] leading-relaxed">
            {scores.withheld > 0 ? (
              <>
                {scores.withheld} module/domain combination
                {scores.withheld === 1 ? " has" : "s have"} data, but fewer than{" "}
                {scores.min_n_to_display} resolved decisions each.
              </>
            ) : (
              "Nothing scored yet."
            )}
          </p>
          <p className="mt-2 max-w-xl text-[12.5px] leading-relaxed text-[var(--color-faint)]">
            An accuracy figure over three decisions is not a measurement, so nothing is
            reported below {scores.min_n_to_display}. There is no shortcut — the council
            can only become yours if you come back and record what happened.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <Link
              href="/history?status=due"
              className="text-[13px] text-[var(--color-muted)] underline decoration-dotted underline-offset-2 hover:text-[var(--color-text)]"
            >
              Decisions waiting on a check-in →
            </Link>
            {scores.withheld > 0 && (
              <button
                type="button"
                onClick={() => setShowAll(true)}
                className="text-[13px] text-[var(--color-faint)] underline decoration-dotted underline-offset-2 hover:text-[var(--color-text)]"
              >
                show them anyway (not measurements)
              </button>
            )}
          </div>
        </Panel>
      )}

      {overall.length > 0 && (
        <>
          {showAll && (
            <p className="mb-3 text-[12px] text-[var(--color-assumed)]">
              Showing samples below n={scores?.min_n_to_display}. These are not
              measurements yet.
            </p>
          )}
          <ScoreTable scores={overall} specs={specs} title="overall" />
          {byDomain.length > 0 && (
            <div className="mt-6">
              <ScoreTable scores={byDomain} specs={specs} title="by domain" showDomain />
            </div>
          )}
          <p className="mt-3 max-w-2xl text-[11.5px] leading-relaxed text-[var(--color-faint)]">
            <strong className="font-medium">brier</strong> — squared error of stated
            confidence against outcome; lower is better, and{" "}
            {overall[0]?.chance_brier ?? 0.25} is what always saying 50% scores.{" "}
            <strong className="font-medium">over</strong> — stated confidence minus what
            happened; positive means it overclaims.{" "}
            <strong className="font-medium">taken</strong> — how often you acted on it. A
            module with a high hit rate on advice you never take is advising a different
            person.
          </p>
        </>
      )}

      <section className="mt-9">
        <div className="mb-2 flex flex-wrap items-baseline gap-2">
          <Label>what each module will be told about you next run</Label>
          {priorCount > 0 && (
            <span className="mono text-[10.5px] text-[var(--color-faint)]">
              {priorCount} prior{priorCount === 1 ? "" : "s"}
            </span>
          )}
        </div>
        {priorCount === 0 ? (
          <p className="text-[12.5px] leading-relaxed text-[var(--color-faint)]">
            None yet. Each prior needs at least three graded decisions, because two data
            points is an anecdote — and an anecdote injected as a prior is how a system
            becomes confidently wrong about one specific person.
          </p>
        ) : (
          <div className="space-y-4">
            {Object.entries(priors).map(([module, items]) => {
              const accent = accentOf(module, specs[module]?.skin.accent);
              return (
                <div key={module} className="border-l-2 pl-3" style={{ borderColor: accent }}>
                  <div className="text-[12.5px] font-medium" style={{ color: accent }}>
                    {specs[module]?.skin.name ?? module}
                  </div>
                  <ul className="mt-1 space-y-2">
                    {items.map((prior, index) => (
                      <li key={index}>
                        <p className="text-[13px] leading-relaxed">{prior.pattern}</p>
                        <p className="mono mt-0.5 text-[10.5px] text-[var(--color-faint)]">
                          n={prior.evidence_count}
                          {prior.domain ? ` · ${prior.domain}` : ""}
                          {prior.module !== module ? ` · from ${prior.module}` : ""}
                          {" · "}
                          {prior.derived_from.slice(0, 3).map((cardId, cardIndex) => (
                            <span key={cardId}>
                              {cardIndex > 0 && ", "}
                              <Link
                                href={`/cards/${cardId}`}
                                className="underline decoration-dotted underline-offset-2 hover:text-[var(--color-text)]"
                              >
                                {cardId.slice(0, 8)}
                              </Link>
                            </span>
                          ))}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
        <p className="mt-4 max-w-2xl text-[11.5px] leading-relaxed text-[var(--color-faint)]">
          Priors arrive as evidence a module may argue with, never as changed
          instructions. A system that rewrites its own prompts from its own scoring
          drifts, and then you can no longer tell whether the module improved or the
          yardstick moved.
        </p>
      </section>
    </main>
  );
}

function ScoreTable({
  scores,
  specs,
  title,
  showDomain = false,
}: {
  scores: ModuleScore[];
  specs: Record<string, ModuleSpec>;
  title: string;
  showDomain?: boolean;
}) {
  return (
    <div>
      <Label className="mb-2">{title}</Label>
      <div className="overflow-x-auto rounded-lg border bg-[var(--color-surface)] hair">
        <table className="w-full min-w-[680px] border-collapse text-[12.5px]">
          <thead>
            <tr className="border-b hair">
              <th className="label px-4 py-2 text-left font-medium">module</th>
              {showDomain && <th className="label px-2 py-2 text-left font-medium">domain</th>}
              <th className="label px-2 py-2 text-right font-medium">n</th>
              <th className="label px-2 py-2 text-left font-medium">right</th>
              <th className="label px-2 py-2 text-right font-medium">said</th>
              <th className="label px-2 py-2 text-right font-medium">over</th>
              <th className="label px-2 py-2 text-right font-medium">brier</th>
              <th className="label px-2 py-2 text-left font-medium">taken</th>
            </tr>
          </thead>
          <tbody>
            {scores.map((score) => {
              const accent = accentOf(score.module, specs[score.module]?.skin.accent);
              const over = score.overconfidence;
              return (
                <tr
                  key={`${score.module}:${score.domain ?? ""}`}
                  className="border-b border-[var(--color-line-soft)] last:border-0"
                >
                  <td className="px-4 py-2" style={{ color: accent }}>
                    {specs[score.module]?.skin.name ?? score.module}
                  </td>
                  {showDomain && (
                    <td className="px-2 py-2 text-[var(--color-muted)]">{score.domain}</td>
                  )}
                  <td className="mono px-2 py-2 text-right text-[var(--color-faint)]">{score.n}</td>
                  <td className="px-2 py-2">
                    {score.hit_rate === null ? (
                      "—"
                    ) : (
                      <Meter value={score.hit_rate} colour={accent} width={46} />
                    )}
                  </td>
                  <td className="mono px-2 py-2 text-right text-[var(--color-faint)]">
                    {score.mean_confidence === null
                      ? "—"
                      : `${Math.round(score.mean_confidence * 100)}%`}
                  </td>
                  <td className="mono px-2 py-2 text-right">
                    {over === null ? (
                      "—"
                    ) : (
                      <span
                        style={{
                          color:
                            Math.abs(over) < 0.1
                              ? "var(--color-given)"
                              : over > 0
                                ? "var(--color-speculative)"
                                : "var(--color-inferred)",
                        }}
                        title={
                          over > 0
                            ? "Claims more certainty than the outcomes justify"
                            : "Understates its own accuracy"
                        }
                      >
                        {over > 0 ? "+" : ""}
                        {over.toFixed(2)}
                      </span>
                    )}
                  </td>
                  <td className="mono px-2 py-2 text-right">
                    {score.brier === null ? (
                      "—"
                    ) : (
                      <span
                        style={{
                          color:
                            score.brier <= score.chance_brier
                              ? "var(--color-given)"
                              : "var(--color-speculative)",
                        }}
                        title={`${score.chance_brier} is what always saying 50% scores`}
                      >
                        {score.brier.toFixed(3)}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    {score.execution_rate === null ? (
                      "—"
                    ) : (
                      <span className="flex items-center gap-1.5">
                        <Meter
                          value={score.execution_rate}
                          colour="var(--color-faint)"
                          width={40}
                        />
                        {score.execution_rate < 0.5 && (
                          <Chip
                            colour="var(--color-assumed)"
                            title="You rarely act on this module — its hit rate describes advice you did not take"
                          >
                            rarely
                          </Chip>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
