"use client";

/**
 * The critique mesh.
 *
 * Grouped by target rather than by critic, because the question a reader has is
 * "what did everyone say about *this* module", not "what did the optimizer think
 * about everything". Each critique shows the artifact row it targets, which is the
 * difference between a debate and two paragraphs disagreeing.
 *
 * `strong_agreement` is rendered as agreement, not as an attack. Independent
 * convergence is real evidence, and filing it under "critiques" in the same visual
 * language as an attack would misrepresent the record.
 */

import type { Critique, CritiqueKind, ModuleSpec, Revision } from "@/lib/types";
import { Chip, Label, accentOf } from "./ui";

const KIND_LABEL: Record<CritiqueKind, string> = {
  unsupported: "unsupported",
  missing_factor: "missing factor",
  wrong_frame: "wrong frame",
  overweighted: "overweighted",
  bias_fired: "bias fired",
  boundary_violation: "boundary violation",
  strong_agreement: "independently agrees",
};

const KIND_COLOUR: Partial<Record<CritiqueKind, string>> = {
  strong_agreement: "var(--color-given)",
  bias_fired: "var(--color-assumed)",
  boundary_violation: "var(--color-speculative)",
};

export function DebateView({
  critiques,
  revisions,
  specs,
}: {
  critiques: Critique[];
  revisions: Revision[];
  specs: Record<string, ModuleSpec>;
}) {
  if (!critiques.length) {
    return (
      <p className="text-[13px] text-[var(--color-faint)]">
        No critique round ran. `quick` depth skips the debate; use `standard` or `deep`
        to have the modules attack each other.
      </p>
    );
  }

  const byTarget = new Map<string, Critique[]>();
  for (const critique of critiques) {
    const bucket = byTarget.get(critique.target) ?? [];
    bucket.push(critique);
    byTarget.set(critique.target, bucket);
  }
  const revisionOf = new Map(revisions.map((r) => [r.module, r]));

  return (
    <div className="space-y-5">
      {[...byTarget.entries()].map(([target, against]) => {
        const accent = accentOf(target, specs[target]?.skin.accent);
        const revision = revisionOf.get(target);
        const agreements = against.filter((c) => c.kind === "strong_agreement");
        const attacks = against.filter((c) => c.kind !== "strong_agreement");

        return (
          <div key={target}>
            <div className="mb-2 flex flex-wrap items-baseline gap-x-2.5 gap-y-1 border-b pb-1.5 hair">
              <h3 className="text-[13.5px] font-medium" style={{ color: accent }}>
                {specs[target]?.skin.name ?? target}
              </h3>
              <span className="text-[11.5px] text-[var(--color-faint)]">
                {attacks.length} attacked
                {agreements.length > 0 && `, ${agreements.length} agreed`}
              </span>
              {revision && (
                <span className="ml-auto text-[11.5px] text-[var(--color-muted)]">
                  accepted {revision.accepted.length} · held against {revision.rejected.length}
                </span>
              )}
            </div>

            <ul className="space-y-2">
              {[...attacks, ...agreements].map((critique, index) => (
                <li key={index} className="flex gap-2.5">
                  <span
                    className="mono mt-[3px] w-[86px] shrink-0 truncate text-[11px]"
                    style={{ color: accentOf(critique.critic, specs[critique.critic]?.skin.accent) }}
                    title={critique.critic}
                  >
                    {critique.critic}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="mb-0.5 flex flex-wrap items-center gap-1.5">
                      <Chip colour={KIND_COLOUR[critique.kind]}>{KIND_LABEL[critique.kind]}</Chip>
                      {critique.bias_id && (
                        <Chip colour="var(--color-assumed)" title="A declared failure mode of the target">
                          {critique.bias_id}
                        </Chip>
                      )}
                      {critique.target_ref && (
                        <span className="mono text-[10.5px] text-[var(--color-faint)]">
                          → {critique.target_ref.kind}
                          {critique.target_ref.row_id ? `#${critique.target_ref.row_id}` : ""}
                        </span>
                      )}
                      <span
                        className="mono text-[10px] text-[var(--color-faint)]"
                        title={`severity ${critique.severity}/5`}
                      >
                        sev {critique.severity}
                      </span>
                    </div>
                    <p className="text-[12.5px] leading-relaxed">{critique.statement}</p>
                  </div>
                </li>
              ))}
            </ul>

            {revision && (revision.accepted.length > 0 || revision.rejected.length > 0) && (
              <div className="mt-2.5 space-y-1.5 border-l-2 border-[var(--color-line)] pl-3">
                {revision.accepted.map((accepted, index) => (
                  <p key={`a${index}`} className="text-[12px] leading-snug">
                    <span className="label mr-1.5">conceded to {accepted.from_module}</span>
                    {accepted.how_it_changes_my_view}
                  </p>
                ))}
                {revision.rejected.map((rejected, index) => (
                  <p
                    key={`r${index}`}
                    className="text-[12px] leading-snug text-[var(--color-muted)]"
                  >
                    <span className="label mr-1.5">held against {rejected.from_module}</span>
                    {rejected.why_rejected}
                  </p>
                ))}
              </div>
            )}
          </div>
        );
      })}

      <p className="border-t pt-3 text-[11.5px] leading-relaxed text-[var(--color-faint)] hair">
        Routing is derived from the specs: a module critiques another only where it is
        listed as one of that module&apos;s critics. Each critic was shown the
        target&apos;s declared failure modes — which the target itself was never told
        about.
      </p>
    </div>
  );
}
