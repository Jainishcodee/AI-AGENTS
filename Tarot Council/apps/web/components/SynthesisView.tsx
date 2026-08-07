"use client";

/**
 * The recommendation, with the dissent kept where a reader will actually see it.
 *
 * Order is deliberate and is the product's argument in layout form: the
 * recommendation, then the disagreements, then what the council *failed* to examine,
 * then the minority opinions with the conditions under which each would be right.
 * Putting `council_blind_spot` above the fold rather than in a footnote is the point
 * — six modules with fixed algorithms have fixed collective blindness, and burying
 * that would make structural coverage read as completeness.
 */

import type { ModuleSpec, Synthesis } from "@/lib/types";
import { Bullets, Chip, Label, Meter, Panel, accentOf } from "./ui";

export function SynthesisView({
  synthesis,
  specs,
  checkOnDays,
}: {
  synthesis: Synthesis;
  specs: Record<string, ModuleSpec>;
  checkOnDays?: number;
}) {
  const s = synthesis;

  return (
    <div className="space-y-6">
      {s.ethical_veto_response && (
        <Panel className="border-l-2 border-l-[var(--color-speculative)] p-4">
          <Label className="mb-1.5">ethical veto — the synthesis had to answer this</Label>
          <p className="text-[13.5px] leading-relaxed">{s.ethical_veto_response}</p>
        </Panel>
      )}

      <div>
        <Label className="mb-2">recommendation</Label>
        <p className="serif text-[19px] leading-snug">{s.recommendation.action}</p>

        <div className="mt-3.5 space-y-2.5">
          <Line label="start with" value={s.recommendation.first_action} emphasise />
          {s.recommendation.timeline && <Line label="timeline" value={s.recommendation.timeline} />}
          {s.recommendation.do_not.length > 0 && (
            <div>
              <Label className="mb-1">do not</Label>
              <Bullets items={s.recommendation.do_not} colour="var(--color-speculative)" />
            </div>
          )}
          {s.recommendation.conditions.length > 0 && (
            <div>
              <Label className="mb-1">only if</Label>
              <Bullets items={s.recommendation.conditions} colour="var(--color-assumed)" />
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-3 hair">
          <span className="flex items-center gap-2">
            <span className="label">confidence</span>
            <Meter value={s.confidence.score} width={64} />
          </span>
          <span className="text-[12px] text-[var(--color-muted)]">{s.confidence.basis}</span>
        </div>
        <div className="mt-2 rounded border border-[var(--color-line-soft)] bg-[var(--color-raised)] px-3 py-2">
          <Label className="mb-0.5">this recommendation is wrong if</Label>
          <p className="text-[12.5px] leading-snug">{s.confidence.falsifier}</p>
        </div>
        {s.calibration_note && (
          <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--color-faint)]">
            {s.calibration_note}
          </p>
        )}
      </div>

      {s.debate_summary && (
        <div>
          <Label className="mb-1.5">what the disagreement was about</Label>
          <p className="text-[13px] leading-relaxed text-[var(--color-muted)]">
            {s.debate_summary}
          </p>
        </div>
      )}

      {s.disagreements.length > 0 && (
        <div>
          <Label className="mb-2">unresolved disagreements</Label>
          <div className="space-y-3.5">
            {s.disagreements.map((disagreement, index) => (
              <div key={index} className="border-l-2 border-[var(--color-line)] pl-3">
                <p className="text-[13.5px] leading-snug">{disagreement.issue}</p>
                <ul className="mt-1.5 space-y-1">
                  {disagreement.positions.map((position, positionIndex) => (
                    <li key={positionIndex} className="flex gap-2 text-[12.5px] leading-snug">
                      <span
                        className="mono w-[86px] shrink-0 truncate text-[11px]"
                        style={{
                          color: accentOf(position.module, specs[position.module]?.skin.accent),
                        }}
                      >
                        {position.module}
                      </span>
                      <span className="text-[var(--color-muted)]">{position.position}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-1.5 text-[11.5px] text-[var(--color-faint)]">
                  matters because {disagreement.why_it_matters} · resolves if{" "}
                  {disagreement.what_would_resolve_it}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {s.blind_spots_fired.length > 0 && (
        <div>
          <Label className="mb-2">declared failure modes that actually fired</Label>
          <ul className="space-y-1.5">
            {s.blind_spots_fired.map((fired, index) => (
              <li key={index} className="text-[12.5px] leading-snug">
                <span className="mono text-[11px] text-[var(--color-faint)]">{fired.module}</span>{" "}
                <Chip colour={fired.corrected ? "var(--color-given)" : "var(--color-assumed)"}>
                  {fired.bias_id}
                  {fired.corrected ? " · corrected" : " · uncorrected"}
                </Chip>{" "}
                <span className="text-[var(--color-muted)]">{fired.evidence}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Panel className="border-l-2 border-l-[var(--color-assumed)] p-4">
        <Label className="mb-1.5">what no module examined</Label>
        <p className="text-[13.5px] leading-relaxed">{s.council_blind_spot}</p>
        <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--color-faint)]">
          Six fixed algorithms have fixed collective blindness. The synthesiser is
          required to name a gap rather than let structural coverage read as
          completeness.
        </p>
      </Panel>

      {s.minority_opinions.length > 0 && (
        <div>
          <Label className="mb-2">minority opinions — kept, not averaged away</Label>
          <div className="space-y-3">
            {s.minority_opinions.map((minority, index) => {
              const accent = accentOf(minority.module, specs[minority.module]?.skin.accent);
              return (
                <div key={index} className="border-l-2 pl-3" style={{ borderColor: accent }}>
                  <div className="text-[12px] font-medium" style={{ color: accent }}>
                    {specs[minority.module]?.skin.name ?? minority.module}
                  </div>
                  <p className="mt-0.5 text-[13px] leading-relaxed">{minority.position}</p>
                  <p className="mt-1 text-[12px] leading-snug text-[var(--color-muted)]">
                    <span className="label mr-1.5">right if</span>
                    {minority.when_it_would_be_right}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="grid gap-6 sm:grid-cols-2">
        {s.alternative_strategy && (
          <div>
            <Label className="mb-1.5">alternative</Label>
            <p className="text-[13px] leading-relaxed">{s.alternative_strategy.action}</p>
            <p className="mt-1 text-[12px] text-[var(--color-muted)]">
              <span className="label mr-1.5">switch if</span>
              {s.alternative_strategy.trigger}
            </p>
          </div>
        )}

        {s.information_to_gather.length > 0 && (
          <div>
            <Label className="mb-1.5">find out, in this order</Label>
            <ol className="space-y-1">
              {s.information_to_gather.map((item, index) => (
                <li key={index} className="flex gap-2 text-[13px] leading-relaxed">
                  <span className="mono shrink-0 text-[11px] text-[var(--color-faint)]">
                    {index + 1}
                  </span>
                  <span>{item}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {s.long_term_prediction.length > 0 && (
        <div>
          <Label className="mb-2">prediction</Label>
          <div className="space-y-2">
            {s.long_term_prediction.map((horizon, index) => (
              <div key={index} className="flex gap-3">
                <span className="mono w-[34px] shrink-0 pt-[2px] text-[11.5px] text-[var(--color-faint)]">
                  {horizon.horizon}
                </span>
                <span className="flex-1 text-[13px] leading-relaxed">{horizon.prediction}</span>
                <Meter value={horizon.confidence} width={34} />
              </div>
            ))}
          </div>
        </div>
      )}

      <Panel className="p-4">
        <Label className="mb-1.5">the bet on record</Label>
        <p className="text-[13.5px] leading-relaxed">{s.expected_outcome.statement}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11.5px] text-[var(--color-faint)]">
          <Chip>check in {checkOnDays ?? s.expected_outcome.check_in_days} days</Chip>
          {s.expected_outcome.measurable_by && <span>measured by {s.expected_outcome.measurable_by}</span>}
        </div>
        <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--color-faint)]">
          Written now, dated now. When you record what actually happened, every module
          gets scored against what it said here — which is what turns this into your
          decision engine rather than a clever one.
        </p>
      </Panel>
    </div>
  );
}

function Line({
  label,
  value,
  emphasise,
}: {
  label: string;
  value: string;
  emphasise?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
      <div className="label shrink-0 pt-[3px] sm:w-[92px]">{label}</div>
      <div
        className={`flex-1 leading-relaxed ${
          emphasise ? "text-[14px]" : "text-[13px] text-[var(--color-muted)]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
