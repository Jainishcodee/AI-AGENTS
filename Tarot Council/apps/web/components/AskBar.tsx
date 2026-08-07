"use client";

import { useState } from "react";
import type { Depth, ModuleSpec, PresetSpec } from "@/lib/types";
import { Button, Chip, Label, accentOf } from "./ui";

const DEPTHS: { id: Depth; label: string; hint: string }[] = [
  { id: "quick", label: "quick", hint: "no debate round — cheapest first look" },
  { id: "standard", label: "standard", hint: "one critique and revision round" },
  { id: "deep", label: "deep", hint: "one call per stage, two debate rounds" },
];

const EXAMPLES = [
  "Should I quit my internship to work on my own product? My manager keeps promising a full-time offer but nothing is in writing, and I have four months of savings.",
  "My best engineer wants the CTO title. My cofounder thinks it's premature and threatened to reduce his own equity if I agree. We close a seed round in six weeks.",
  "I have three half-finished side projects and a full-time job. I keep switching every week and shipping nothing.",
];

export function AskBar({
  presets,
  modules,
  busy,
  onRun,
  onCancel,
}: {
  presets: PresetSpec[];
  modules: Record<string, ModuleSpec>;
  busy: boolean;
  onRun: (input: { question: string; preset: string; depth: Depth; notes: string }) => void;
  onCancel: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [notes, setNotes] = useState("");
  const [showNotes, setShowNotes] = useState(false);
  const [preset, setPreset] = useState("strategy");
  const [depth, setDepth] = useState<Depth>("quick");

  const active = presets.find((p) => p.id === preset);
  const running = active ? [...active.primary, ...active.advisory] : [];
  const critics = active?.critic ?? [];

  // Roughly what the run will cost, from the API's own per-depth call counts. Worth
  // showing up front: on a free key the per-minute quota, not model quality, is what
  // decides whether a deep run finishes.
  const estimate =
    running.reduce((total, id) => total + (modules[id]?.calls_per_depth[depth] ?? 0), 0) +
    (depth === "quick" ? 0 : critics.length + running.length) +
    2;

  const submit = () => {
    const trimmed = question.trim();
    if (trimmed.length >= 8 && !busy) onRun({ question: trimmed, preset, depth, notes });
  };

  return (
    <div className="space-y-3">
      <div className="rounded-lg border bg-[var(--color-surface)] hair">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
          }}
          rows={3}
          placeholder="Describe the decision. Include the constraints and who else is involved — the modules will not invent them."
          className="serif w-full resize-y bg-transparent px-4 py-3.5 text-[16px] leading-relaxed outline-none placeholder:text-[var(--color-faint)]"
        />

        {showNotes && (
          <div className="border-t px-4 py-3 hair">
            <Label className="mb-1.5">extra context</Label>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={2}
              placeholder="Money, deadlines, obligations, what you've already tried, what you care about."
              className="w-full resize-y bg-transparent text-[13.5px] leading-relaxed outline-none placeholder:text-[var(--color-faint)]"
            />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t px-3 py-2.5 hair">
          <select
            value={preset}
            onChange={(event) => setPreset(event.target.value)}
            className="rounded border bg-[var(--color-raised)] px-2 py-1 text-[12.5px] outline-none hair"
          >
            {presets.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>

          <div className="flex rounded border hair">
            {DEPTHS.map((option) => (
              <button
                key={option.id}
                type="button"
                title={option.hint}
                onClick={() => setDepth(option.id)}
                className={`px-2.5 py-1 text-[12px] transition-colors first:rounded-l last:rounded-r ${
                  depth === option.id
                    ? "bg-[var(--color-raised)] text-[var(--color-text)]"
                    : "text-[var(--color-faint)] hover:text-[var(--color-muted)]"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setShowNotes(!showNotes)}
            className="text-[12px] text-[var(--color-faint)] underline decoration-dotted underline-offset-2 transition-colors hover:text-[var(--color-text)]"
          >
            {showNotes ? "hide context" : "add context"}
          </button>

          <span className="mono ml-auto text-[11px] text-[var(--color-faint)]">
            ≈{estimate} calls
          </span>

          {busy ? (
            <Button onClick={onCancel}>stop</Button>
          ) : (
            <Button variant="primary" onClick={submit} disabled={question.trim().length < 8}>
              Convene
            </Button>
          )}
        </div>
      </div>

      {active && (
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[11.5px]">
          <span className="text-[var(--color-faint)]">{active.description}</span>
          <span className="flex flex-wrap gap-1">
            {running.map((id) => (
              <Chip key={id} colour={accentOf(id, modules[id]?.skin.accent)}>
                {modules[id]?.skin.name ?? id}
              </Chip>
            ))}
            {critics.map((id) => (
              <Chip key={id} title="Critique only — one call, no full program">
                {modules[id]?.skin.name ?? id} (critic)
              </Chip>
            ))}
          </span>
        </div>
      )}

      {!question && (
        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((example, index) => (
            <button
              key={index}
              type="button"
              onClick={() => setQuestion(example)}
              className="max-w-full truncate rounded border px-2 py-1 text-left text-[11.5px] text-[var(--color-faint)] transition-colors hair hover:text-[var(--color-text)]"
            >
              {example.slice(0, 68)}…
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
