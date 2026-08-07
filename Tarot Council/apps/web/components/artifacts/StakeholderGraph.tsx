"use client";

/**
 * The strategist's graph, drawn as an actual graph.
 *
 * The single most important thing on screen is the *gap* between formal authority
 * and real influence, so the layout encodes it directly: x = formal authority,
 * y = real influence (inverted, so up means more influential). A node far from the
 * diagonal is a node whose title lies about its power, and that reads instantly
 * without anyone explaining the chart.
 *
 * Layout is deterministic — no force simulation, no animation, no library. The same
 * graph always renders identically, which matters because this is a reasoning
 * record people will revisit and compare.
 */

import { useMemo, useState } from "react";
import { Chip, Empty, Meter } from "@/components/ui";

interface GraphNode {
  id: string;
  label: string;
  role: string;
  formal_authority: number;
  real_influence: number;
  controls: string[];
  fears: string[];
  optimising_for: string;
  stated_position: string | null;
  actual_interest: string | null;
  power_gap: boolean;
}

interface GraphEdge {
  src: string;
  dst: string;
  kind: string;
  weight: number;
  is_hidden: boolean;
  note: string;
}

const W = 520;
const H = 300;
const PAD = 40;

const EDGE_LABEL: Record<string, string> = {
  reports_to: "reports to",
  depends_on: "depends on",
  owes: "owes",
  allied_with: "allied",
  competes_with: "competes",
  can_veto: "can veto",
  informs: "informs",
  gatekeeps: "gatekeeps",
};

export function StakeholderGraph({
  data,
  accent,
}: {
  data: Record<string, unknown>;
  accent: string;
}) {
  const nodes = (data.nodes ?? []) as GraphNode[];
  const edges = (data.edges ?? []) as GraphEdge[];
  const [selected, setSelected] = useState<string | null>(null);

  const placed = useMemo(() => {
    const seen = new Map<string, number>();
    return nodes.map((node) => {
      // Nudge exact collisions apart so two identically-scored actors stay legible.
      const key = `${node.formal_authority.toFixed(2)}:${node.real_influence.toFixed(2)}`;
      const collisions = seen.get(key) ?? 0;
      seen.set(key, collisions + 1);
      const jitter = collisions * 13;
      return {
        node,
        x: PAD + node.formal_authority * (W - PAD * 2) + jitter,
        y: PAD + (1 - node.real_influence) * (H - PAD * 2) + jitter,
      };
    });
  }, [nodes]);

  const position = new Map(placed.map((p) => [p.node.id, p]));
  if (!nodes.length) return <Empty>No graph.</Empty>;

  const active = selected ? nodes.find((n) => n.id === selected) : null;

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full min-w-[440px]"
          role="img"
          aria-label="Stakeholder graph: horizontal axis is formal authority, vertical axis is real influence"
        >
          {/* The diagonal is where title and power agree. Distance from it is the
              whole point of the chart. */}
          <line
            x1={PAD}
            y1={H - PAD}
            x2={W - PAD}
            y2={PAD}
            stroke="var(--color-line)"
            strokeDasharray="3 4"
            strokeWidth={1}
          />
          <text x={W - PAD} y={PAD - 10} textAnchor="end" className="label" fill="var(--color-faint)" fontSize={9}>
            title matches power
          </text>
          <text x={PAD} y={H - PAD + 22} className="label" fill="var(--color-faint)" fontSize={9}>
            formal authority →
          </text>
          <text
            x={PAD - 14}
            y={PAD}
            className="label"
            fill="var(--color-faint)"
            fontSize={9}
            transform={`rotate(-90 ${PAD - 14} ${PAD})`}
          >
            real influence →
          </text>

          {edges.map((edge, index) => {
            const from = position.get(edge.src);
            const to = position.get(edge.dst);
            if (!from || !to) return null;
            const dim = selected && edge.src !== selected && edge.dst !== selected;
            return (
              <g key={index} opacity={dim ? 0.18 : 1}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={edge.is_hidden ? "var(--color-assumed)" : "var(--color-line)"}
                  strokeWidth={0.6 + edge.weight * 1.8}
                  strokeDasharray={edge.is_hidden ? "4 3" : undefined}
                />
                <title>
                  {edge.src} {EDGE_LABEL[edge.kind] ?? edge.kind} {edge.dst}
                  {edge.is_hidden ? " (not on the org chart)" : ""}
                  {edge.note ? ` — ${edge.note}` : ""}
                </title>
              </g>
            );
          })}

          {placed.map(({ node, x, y }) => {
            const isUser = node.id === "me";
            const dim = selected && selected !== node.id;
            return (
              <g
                key={node.id}
                opacity={dim ? 0.35 : 1}
                className="cursor-pointer"
                onClick={() => setSelected(selected === node.id ? null : node.id)}
              >
                {node.power_gap && (
                  <circle cx={x} cy={y} r={11} fill="none" stroke="var(--color-assumed)" strokeWidth={1} />
                )}
                <circle
                  cx={x}
                  cy={y}
                  r={isUser ? 6 : 5}
                  fill={isUser ? accent : "var(--color-raised)"}
                  stroke={isUser ? accent : "var(--color-muted)"}
                  strokeWidth={1.4}
                />
                <text
                  x={x}
                  y={y - 14}
                  textAnchor="middle"
                  fontSize={10.5}
                  fill={isUser ? "var(--color-text)" : "var(--color-muted)"}
                >
                  {node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label}
                </text>
                <title>{`${node.label} — authority ${node.formal_authority.toFixed(2)}, influence ${node.real_influence.toFixed(2)}`}</title>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <Chip colour="var(--color-assumed)">ringed = power gap ≥ 0.4</Chip>
        <Chip colour="var(--color-assumed)">dashed edge = not on the org chart</Chip>
        {edges.some((e) => e.kind === "can_veto") && <Chip>a veto edge exists</Chip>}
      </div>

      {active ? (
        <NodeDetail node={active} edges={edges} accent={accent} />
      ) : (
        <div className="text-[11.5px] text-[var(--color-faint)]">
          Select an actor for their incentives and what they will not say.
        </div>
      )}
    </div>
  );
}

function NodeDetail({
  node,
  edges,
  accent,
}: {
  node: GraphNode;
  edges: GraphEdge[];
  accent: string;
}) {
  const related = edges.filter((e) => e.src === node.id || e.dst === node.id);
  return (
    <div className="rise space-y-2 rounded border border-[var(--color-line-soft)] bg-[var(--color-raised)] p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="text-[13px] font-medium">{node.label}</div>
        {node.role && <div className="text-[11.5px] text-[var(--color-faint)]">{node.role}</div>}
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11.5px]">
        <span className="flex items-center gap-2">
          <span className="label">authority</span>
          <Meter value={node.formal_authority} colour="var(--color-faint)" />
        </span>
        <span className="flex items-center gap-2">
          <span className="label">influence</span>
          <Meter value={node.real_influence} colour={accent} />
        </span>
        {node.power_gap && <Chip colour="var(--color-assumed)">power gap</Chip>}
      </div>

      <dl className="space-y-1.5 text-[12.5px]">
        {node.optimising_for && <Field label="optimising for" value={node.optimising_for} />}
        {node.stated_position && <Field label="says" value={node.stated_position} />}
        {node.actual_interest && <Field label="actually wants" value={node.actual_interest} />}
        {node.controls?.length > 0 && <Field label="controls" value={node.controls.join(" · ")} />}
        {node.fears?.length > 0 && <Field label="fears" value={node.fears.join(" · ")} />}
      </dl>

      {related.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {related.map((edge, index) => (
            <Chip key={index} colour={edge.is_hidden ? "var(--color-assumed)" : undefined}>
              {edge.src === node.id ? "→ " : "← "}
              {EDGE_LABEL[edge.kind] ?? edge.kind} {edge.src === node.id ? edge.dst : edge.src}
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="label w-[104px] shrink-0 pt-[3px]">{label}</dt>
      <dd className="flex-1 leading-snug">{value}</dd>
    </div>
  );
}
