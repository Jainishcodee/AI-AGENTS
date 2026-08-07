"use client";

/**
 * One module's execution, top to bottom: its stages as they validate, then its
 * conclusion.
 *
 * Stages are collapsed by default and the conclusion is not, because the conclusion
 * is what a reader wants first and the artifacts are what they want when they stop
 * believing it. The stage list doubles as a progress indicator — a module's shape is
 * visible before its content arrives, which is what makes six parallel columns
 * legible rather than chaotic.
 */

import { useState } from "react";
import type { Critique, ModuleSpec } from "@/lib/types";
import type { LiveModule } from "@/lib/useDeliberation";
import { ArtifactBody } from "./artifacts";
import { Chip, Label, Meter, accentOf } from "./ui";

export function ModuleColumn({
  live,
  spec,
  critiquesAgainst,
  defaultOpen,
}: {
  live: LiveModule;
  spec: ModuleSpec | undefined;
  critiquesAgainst: Critique[];
  defaultOpen: boolean;
}) {
  const accent = accentOf(live.module, spec?.skin.accent);
  const stages = spec?.stages ?? [];
  const done = new Set(live.artifacts.map((a) => a.stage_id));
  const terminalId = stages.find((s) => s.terminal)?.id;
  const [open, setOpen] = useState<string | null>(null);

  return (
    <article
      className="flex min-w-0 flex-col rounded-lg border bg-[var(--color-surface)] hair"
      style={{ borderTopColor: accent, borderTopWidth: 2 }}
    >
      <header className="border-b px-3.5 py-3 hair">
        <div className="flex items-baseline justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-[14px] font-medium" style={{ color: accent }}>
              {spec?.skin.name ?? live.module}
            </h3>
            <div className="truncate text-[11px] text-[var(--color-faint)]">
              {live.module} · {live.role}
            </div>
          </div>
          {live.running && !live.abstained && (
            <span className="working mono shrink-0 text-[10px] text-[var(--color-faint)]">
              running
            </span>
          )}
        </div>
        {spec?.summary && (
          <p className="mt-2 text-[11.5px] leading-relaxed text-[var(--color-faint)]">
            {spec.summary}
          </p>
        )}
      </header>

      {/* Stage rail */}
      <div className="border-b px-3.5 py-2.5 hair">
        <ul className="space-y-[3px]">
          {(stages.length ? stages : live.artifacts.map((a) => ({ id: a.stage_id, name: a.title, produces: a.kind, terminal: false }))).map(
            (stage) => {
              const complete = done.has(stage.id);
              const artifact = live.artifacts.find((a) => a.stage_id === stage.id);
              const repaired = live.problems.some((p) => p.stageId === stage.id);
              const failed = live.abstained && live.abstainReason?.includes(stage.id);
              const isOpen = open === stage.id;
              const isTerminal = stage.id === terminalId;

              return (
                <li key={stage.id}>
                  <button
                    type="button"
                    disabled={!artifact || isTerminal}
                    onClick={() => setOpen(isOpen ? null : stage.id)}
                    className="group flex w-full items-baseline gap-2 rounded px-1 py-[3px] text-left transition-colors enabled:hover:bg-[var(--color-raised)] disabled:cursor-default"
                  >
                    <span
                      className="mt-[5px] size-[5px] shrink-0 rounded-full"
                      style={{
                        background: failed
                          ? "var(--color-speculative)"
                          : complete
                            ? accent
                            : "var(--color-line)",
                      }}
                    />
                    <span
                      className={`min-w-0 flex-1 truncate text-[12px] ${
                        complete ? "text-[var(--color-text)]" : "text-[var(--color-faint)]"
                      }`}
                    >
                      {stage.name}
                    </span>
                    {repaired && (
                      <span
                        className="mono shrink-0 text-[9.5px] text-[var(--color-assumed)]"
                        title="This stage failed validation once and was repaired"
                      >
                        repaired
                      </span>
                    )}
                    {artifact && !isTerminal && (
                      <span className="mono shrink-0 text-[9.5px] text-[var(--color-faint)] opacity-0 transition-opacity group-hover:opacity-100">
                        {isOpen ? "hide" : "open"}
                      </span>
                    )}
                  </button>

                  {isOpen && artifact && (
                    <div className="rise mb-1.5 ml-3 mt-1.5 border-l border-[var(--color-line-soft)] pl-3">
                      <Label className="mb-1.5">{artifact.kind}</Label>
                      <ArtifactBody artifact={artifact} accent={accent} />
                    </div>
                  )}
                </li>
              );
            },
          )}
        </ul>
      </div>

      {live.abstained ? (
        <div className="px-3.5 py-3">
          <Chip colour="var(--color-speculative)">abstained</Chip>
          <p className="mt-2 text-[12px] leading-relaxed text-[var(--color-muted)]">
            {live.abstainReason}
          </p>
          <p className="mt-2 text-[11.5px] text-[var(--color-faint)]">
            The council continued without it, and the synthesiser was told who was missing.
          </p>
        </div>
      ) : live.conclusion ? (
        <ConclusionBlock
          live={live}
          accent={accent}
          critiquesAgainst={critiquesAgainst}
          defaultOpen={defaultOpen}
        />
      ) : (
        <div className="px-3.5 py-4 text-[12px] italic text-[var(--color-faint)]">
          reasoning…
        </div>
      )}
    </article>
  );
}

function ConclusionBlock({
  live,
  accent,
  critiquesAgainst,
  defaultOpen,
}: {
  live: LiveModule;
  accent: string;
  critiquesAgainst: Critique[];
  defaultOpen: boolean;
}) {
  const conclusion = live.conclusion!;
  const [showWhy, setShowWhy] = useState(defaultOpen);

  return (
    <div className="flex flex-1 flex-col gap-2.5 px-3.5 py-3">
      <p className="text-[13.5px] font-medium leading-snug">{conclusion.stance}</p>

      <div>
        <Label className="mb-0.5">first action</Label>
        <p className="text-[12.5px] leading-snug text-[var(--color-muted)]">
          {conclusion.first_action}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="flex items-center gap-2">
          <span className="label">confidence</span>
          <Meter value={conclusion.confidence.score} colour={accent} />
        </span>
        {live.revision && live.revision.delta !== "unchanged" && (
          <Chip colour="var(--color-inferred)" title={live.revision.delta}>
            revised
          </Chip>
        )}
        {conclusion.ethical_veto && <Chip colour="var(--color-speculative)">veto</Chip>}
      </div>

      <div className="rounded border border-[var(--color-line-soft)] bg-[var(--color-raised)] px-2.5 py-2">
        <Label className="mb-0.5">would change its mind if</Label>
        <p className="text-[12px] leading-snug">{conclusion.confidence.falsifier}</p>
      </div>

      <button
        type="button"
        onClick={() => setShowWhy(!showWhy)}
        className="self-start text-[11.5px] text-[var(--color-faint)] underline decoration-dotted underline-offset-2 transition-colors hover:text-[var(--color-text)]"
      >
        {showWhy ? "hide reasoning" : "why"}
      </button>

      {showWhy && (
        <div className="rise space-y-2.5">
          <p className="text-[12.5px] leading-relaxed text-[var(--color-muted)]">
            {conclusion.reasoning}
          </p>

          {conclusion.key_claims.length > 0 && (
            <div>
              <Label className="mb-1">rests on</Label>
              <div className="flex flex-wrap gap-1">
                {conclusion.key_claims.map((ref, index) => (
                  <Chip key={index} title={`${ref.module}/${ref.stage_id}`}>
                    {ref.kind}
                    {ref.row_id ? `#${ref.row_id}` : ""}
                  </Chip>
                ))}
              </div>
            </div>
          )}

          {conclusion.cheapest_decisive_test && (
            <div>
              <Label className="mb-0.5">cheapest decisive test</Label>
              <p className="text-[12px] leading-snug">{conclusion.cheapest_decisive_test}</p>
            </div>
          )}

          {conclusion.ethical_veto && conclusion.veto_grounds && (
            <div
              className="rounded border-l-2 px-2.5 py-2"
              style={{ borderColor: "var(--color-speculative)" }}
            >
              <Label className="mb-0.5">veto grounds</Label>
              <p className="text-[12px] leading-snug">{conclusion.veto_grounds}</p>
            </div>
          )}

          {critiquesAgainst.length > 0 && (
            <div>
              <Label className="mb-1">{critiquesAgainst.length} critiques of this</Label>
              <ul className="space-y-1.5">
                {critiquesAgainst.map((critique, index) => (
                  <li key={index} className="text-[12px] leading-snug">
                    <span className="mono text-[10.5px] text-[var(--color-faint)]">
                      {critique.critic}
                    </span>{" "}
                    {critique.statement}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {live.revision && (
            <div className="border-t border-[var(--color-line-soft)] pt-2">
              <Label className="mb-0.5">after the debate</Label>
              <p className="text-[12px] leading-snug text-[var(--color-muted)]">
                {live.revision.delta}
              </p>
              {live.revision.rejected.length > 0 && (
                <p className="mt-1 text-[11.5px] text-[var(--color-faint)]">
                  held its ground against{" "}
                  {live.revision.rejected.map((r) => r.from_module).join(", ")}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
