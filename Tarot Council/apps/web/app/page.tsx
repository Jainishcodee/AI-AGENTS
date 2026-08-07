"use client";

import { useEffect, useMemo, useState } from "react";
import { AskBar } from "@/components/AskBar";
import { DebateView } from "@/components/DebateView";
import { ModuleColumn } from "@/components/ModuleColumn";
import { SynthesisView } from "@/components/SynthesisView";
import { TraceMap } from "@/components/TraceMap";
import { Label } from "@/components/ui";
import { getJSON } from "@/lib/stream";
import type { ModuleSpec, PresetSpec } from "@/lib/types";
import { isBusy, useDeliberation } from "@/lib/useDeliberation";

type Tab = "modules" | "debate" | "synthesis" | "trace";

export default function Page() {
  const { state, run, cancel, reset } = useDeliberation();
  const [modules, setModules] = useState<Record<string, ModuleSpec>>({});
  const [presets, setPresets] = useState<PresetSpec[]>([]);
  const [offline, setOffline] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("modules");

  useEffect(() => {
    Promise.all([getJSON<ModuleSpec[]>("modules"), getJSON<PresetSpec[]>("presets")])
      .then(([moduleList, presetList]) => {
        setModules(Object.fromEntries(moduleList.map((m) => [m.id, m])));
        setPresets(presetList);
        setOffline(null);
      })
      .catch((error) => setOffline(String(error)));
  }, []);

  const busy = isBusy(state.phase);

  // Follow the pipeline: the debate and the synthesis are the interesting views once
  // they exist, but never yank the user out of a tab they chose themselves.
  const [pinned, setPinned] = useState(false);
  useEffect(() => {
    if (pinned) return;
    if (state.synthesis) setTab("synthesis");
    else if (state.critiques.length) setTab("debate");
    else setTab("modules");
  }, [state.synthesis, state.critiques.length, pinned]);

  const critiquesByTarget = useMemo(() => {
    const map = new Map<string, typeof state.critiques>();
    for (const critique of state.critiques) {
      const bucket = map.get(critique.target) ?? [];
      bucket.push(critique);
      map.set(critique.target, bucket);
    }
    return map;
  }, [state.critiques]);

  const columns = state.order.map((id) => state.modules[id]!).filter(Boolean);
  const primaryCount = columns.filter((c) => c.role === "primary").length;

  return (
    <main className="mx-auto w-full max-w-[1680px] px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[15px] font-medium tracking-tight">Cognitive OS</h1>
          <p className="mt-0.5 text-[12px] text-[var(--color-faint)]">
            Six reasoning engines. Different algorithms, not different voices.
          </p>
        </div>
        {state.deliberation && (
          <div className="mono flex flex-wrap items-center gap-x-3 text-[11px] text-[var(--color-faint)]">
            <span>{state.deliberation.preset}</span>
            <span>{state.deliberation.depth}</span>
            <span>{state.usage?.calls ?? 0} calls</span>
            {(state.usage?.repairs ?? 0) > 0 && <span>{state.usage?.repairs} repaired</span>}
            <button
              type="button"
              onClick={() => {
                reset();
                setPinned(false);
              }}
              className="underline decoration-dotted underline-offset-2 hover:text-[var(--color-text)]"
            >
              new
            </button>
          </div>
        )}
      </header>

      {offline && (
        <div className="mb-5 rounded-lg border border-[var(--color-speculative)]/40 bg-[var(--color-surface)] p-4">
          <Label className="mb-1.5">the reasoning core is not reachable</Label>
          <p className="text-[13px] leading-relaxed text-[var(--color-muted)]">
            Start it from <code className="mono">apps/api</code>:
          </p>
          <pre className="mono mt-2 overflow-x-auto rounded bg-[var(--color-ink)] px-3 py-2 text-[12px]">
            uvicorn app.main:app --reload --port 8787
          </pre>
        </div>
      )}

      <AskBar
        presets={presets}
        modules={modules}
        busy={busy}
        onRun={(input) => {
          setPinned(false);
          run(input);
        }}
        onCancel={cancel}
      />

      {state.phase !== "idle" && (
        <>
          <div className="mt-7 flex flex-wrap items-center gap-x-4 gap-y-2 border-b pb-2 hair">
            <nav className="flex gap-1">
              {(
                [
                  ["modules", `modules${columns.length ? ` (${columns.length})` : ""}`],
                  ["debate", `debate${state.critiques.length ? ` (${state.critiques.length})` : ""}`],
                  ["synthesis", "synthesis"],
                  ["trace", "trace"],
                ] as [Tab, string][]
              ).map(([id, label]) => {
                const disabled =
                  (id === "synthesis" && !state.synthesis) || (id === "trace" && !state.trace);
                return (
                  <button
                    key={id}
                    type="button"
                    disabled={disabled}
                    onClick={() => {
                      setTab(id);
                      setPinned(true);
                    }}
                    className={`rounded px-2.5 py-1 text-[12.5px] transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
                      tab === id
                        ? "bg-[var(--color-raised)] text-[var(--color-text)]"
                        : "text-[var(--color-faint)] hover:text-[var(--color-muted)]"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </nav>

            {busy && (
              <span className="working ml-auto text-[12px] text-[var(--color-muted)]">
                {state.phaseLabel || "working"}…
              </span>
            )}
            {state.phase === "done" && state.cardId && (
              <span className="mono ml-auto text-[11px] text-[var(--color-faint)]">
                card {state.cardId}
              </span>
            )}
          </div>

          {state.error && (
            <p className="mt-4 text-[13px] text-[var(--color-speculative)]">{state.error}</p>
          )}
          {state.warnings.map((warning, index) => (
            <p key={index} className="mt-3 text-[12px] text-[var(--color-assumed)]">
              {warning}
            </p>
          ))}

          {state.context && tab === "modules" && <ContextStrip context={state.context} />}

          <div className="mt-5">
            {tab === "modules" && (
              <div
                className="grid gap-4"
                style={{
                  gridTemplateColumns: `repeat(auto-fit, minmax(${
                    primaryCount <= 2 ? 380 : 300
                  }px, 1fr))`,
                }}
              >
                {columns.map((live) => (
                  <ModuleColumn
                    key={live.module}
                    live={live}
                    spec={modules[live.module]}
                    critiquesAgainst={critiquesByTarget.get(live.module) ?? []}
                    defaultOpen={columns.length <= 3}
                  />
                ))}
              </div>
            )}

            {tab === "debate" && (
              <div className="max-w-4xl">
                <DebateView
                  critiques={state.critiques}
                  revisions={state.revisions}
                  specs={modules}
                />
              </div>
            )}

            {tab === "synthesis" && state.synthesis && (
              <div className="max-w-3xl">
                <SynthesisView synthesis={state.synthesis} specs={modules} />
              </div>
            )}

            {tab === "trace" && state.trace && (
              <TraceMap trace={state.trace} specs={modules} moduleOrder={state.order} />
            )}
          </div>
        </>
      )}

      {state.phase === "idle" && !offline && <Explainer modules={modules} />}
    </main>
  );
}

function ContextStrip({ context }: { context: NonNullable<ReturnType<typeof useDeliberation>["state"]["context"]> }) {
  const facts: [string, string][] = [];
  if (context.normalised) facts.push(["the decision", context.normalised]);
  if (context.options.length)
    facts.push(["options", context.options.map((o) => `${o.id} ${o.label}`).join(" · ")]);
  if (context.actors.length) facts.push(["actors", context.actors.join(" · ")]);
  if (context.constraints.length) facts.push(["constraints", context.constraints.join(" · ")]);
  if (context.missing_inputs.length)
    facts.push(["never supplied", context.missing_inputs.join(" · ")]);

  return (
    <div className="mt-4 rounded-lg border bg-[var(--color-surface)] px-4 py-3 hair">
      <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {facts.map(([label, value]) => (
          <div key={label} className="flex gap-2.5">
            <dt className="label w-[104px] shrink-0 pt-[3px]">{label}</dt>
            <dd
              className={`flex-1 text-[12.5px] leading-snug ${
                label === "never supplied"
                  ? "text-[var(--color-assumed)]"
                  : "text-[var(--color-muted)]"
              }`}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Explainer({ modules }: { modules: Record<string, ModuleSpec> }) {
  const list = Object.values(modules);
  if (!list.length) return null;
  return (
    <section className="mt-12 max-w-4xl">
      <Label className="mb-3">what each engine is forced to produce</Label>
      <div className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
        {list.map((spec) => (
          <div key={spec.id} className="border-l-2 pl-3" style={{ borderColor: spec.skin.accent }}>
            <div className="flex items-baseline gap-2">
              <span className="text-[13px] font-medium" style={{ color: spec.skin.accent }}>
                {spec.skin.name}
              </span>
              <span className="text-[11px] text-[var(--color-faint)]">{spec.id}</span>
              {spec.veto_enabled && (
                <span className="text-[10.5px] text-[var(--color-speculative)]">holds the veto</span>
              )}
            </div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
              {spec.summary}
            </p>
            <p className="mono mt-1.5 text-[10.5px] leading-relaxed text-[var(--color-faint)]">
              {spec.stages.filter((s) => !s.terminal).map((s) => s.produces).join(" → ")}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-6 max-w-2xl text-[12px] leading-relaxed text-[var(--color-faint)]">
        Each engine runs an ordered program, one stage at a time, and every stage must
        produce a validated artifact before the next one runs. Only the final stage of
        each program is even allowed to hold a stance — so nothing here can decide its
        answer first and fill in the reasoning afterwards.
      </p>
    </section>
  );
}
