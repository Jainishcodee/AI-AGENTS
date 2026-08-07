"use client";

/**
 * The Thinking Trace.
 *
 * A layered map of how the council actually got there: question → context → six
 * lanes of stage artifacts → the critique mesh → conflicts → consensus →
 * recommendation.
 *
 * Two properties matter more than the visuals. Every node references a real
 * validated artifact — nothing here was generated *for* the diagram, so the map
 * cannot disagree with the territory. And layout is a pure function of the graph's
 * `depth` field (computed server-side by longest-path layering), with lanes ordered
 * by module, so the same deliberation always renders identically. No force
 * simulation, no animation, no layout library: a reasoning record that reshuffles
 * every time you open it is not a record.
 */

import { useMemo, useRef, useState } from "react";
import type { ModuleSpec, TraceEdge, TraceGraph, TraceNode } from "@/lib/types";
import { Chip, Label, accentOf } from "./ui";

const NODE_W = 156;
const NODE_H = 34;
const COL_GAP = 66;
const ROW_GAP = 12;
const PAD = 24;

const EDGE_STYLE: Record<
  TraceEdge["kind"],
  { colour: string; dash?: string; width: number }
> = {
  derives_from: { colour: "var(--color-line)", width: 1 },
  concludes: { colour: "#3a3a44", width: 1.4 },
  critiques: { colour: "var(--color-assumed)", dash: "3 3", width: 1 },
  revises: { colour: "var(--color-inferred)", dash: "2 3", width: 1 },
  conflicts_with: { colour: "var(--color-speculative)", width: 1.2 },
  supports: { colour: "var(--color-given)", dash: "1 3", width: 1 },
};

const KIND_LABEL: Record<TraceNode["kind"], string> = {
  question: "question",
  context: "context",
  stage_artifact: "artifact",
  conclusion: "conclusion",
  critique: "critique",
  revision: "revision",
  conflict: "conflict",
  consensus: "consensus",
  recommendation: "recommendation",
  abstention: "abstention",
};

interface Placed {
  node: TraceNode;
  x: number;
  y: number;
}

export function TraceMap({
  trace,
  specs,
  moduleOrder,
}: {
  trace: TraceGraph;
  specs: Record<string, ModuleSpec>;
  moduleOrder: string[];
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  const { placed, width, height } = useMemo(
    () => layout(trace, moduleOrder),
    [trace, moduleOrder],
  );
  const position = useMemo(() => new Map(placed.map((p) => [p.node.id, p])), [placed]);

  const neighbours = useMemo(() => {
    if (!selected) return null;
    const keep = new Set<string>([selected]);
    for (const edge of trace.edges) {
      if (edge.src === selected) keep.add(edge.dst);
      if (edge.dst === selected) keep.add(edge.src);
    }
    return keep;
  }, [selected, trace.edges]);

  const active = selected ? trace.nodes.find((n) => n.id === selected) : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex flex-wrap gap-1.5">
          <Chip colour="var(--color-line)">data flow</Chip>
          <Chip colour="var(--color-assumed)">critique</Chip>
          <Chip colour="var(--color-inferred)">revision</Chip>
          <Chip colour="var(--color-speculative)">conflict</Chip>
          <Chip colour="var(--color-given)">supports</Chip>
        </div>
        <div className="ml-auto flex items-center gap-2 text-[11.5px] text-[var(--color-faint)]">
          <span>
            {trace.nodes.length} nodes · {trace.edges.length} edges
          </span>
          <button
            type="button"
            onClick={() => {
              setScale(1);
              setPan({ x: 0, y: 0 });
              setSelected(null);
            }}
            className="rounded border px-2 py-0.5 transition-colors hair hover:text-[var(--color-text)]"
          >
            reset
          </button>
        </div>
      </div>

      <div
        className="relative cursor-grab overflow-hidden rounded-lg border bg-[var(--color-ink)] hair active:cursor-grabbing"
        style={{ height: 460 }}
        onPointerDown={(event) => {
          drag.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
          (event.target as Element).setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (!drag.current) return;
          setPan({
            x: drag.current.panX + (event.clientX - drag.current.x),
            y: drag.current.panY + (event.clientY - drag.current.y),
          });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onWheel={(event) => {
          event.preventDefault();
          setScale((current) =>
            Math.min(2, Math.max(0.35, current * (event.deltaY > 0 ? 0.92 : 1.08))),
          );
        }}
      >
        <svg
          width={width}
          height={height}
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            transformOrigin: "0 0",
          }}
          role="img"
          aria-label="Reasoning trace: a layered map of artifacts, critiques and the final recommendation"
        >
          <g>
            {trace.edges.map((edge, index) => {
              const from = position.get(edge.src);
              const to = position.get(edge.dst);
              if (!from || !to) return null;
              const style = EDGE_STYLE[edge.kind];
              const dim = neighbours && !(neighbours.has(edge.src) && neighbours.has(edge.dst));
              const x1 = from.x + NODE_W;
              const y1 = from.y + NODE_H / 2;
              const x2 = to.x;
              const y2 = to.y + NODE_H / 2;
              const mid = (x2 - x1) / 2;
              return (
                <path
                  key={index}
                  d={`M ${x1} ${y1} C ${x1 + mid} ${y1}, ${x2 - mid} ${y2}, ${x2} ${y2}`}
                  fill="none"
                  stroke={style.colour}
                  strokeWidth={style.width}
                  strokeDasharray={style.dash}
                  opacity={dim ? 0.1 : 0.75}
                />
              );
            })}
          </g>

          {placed.map(({ node, x, y }) => {
            const accent = node.module
              ? accentOf(node.module, specs[node.module]?.skin.accent)
              : "#4a4a55";
            const dim = neighbours && !neighbours.has(node.id);
            const isFinal = node.kind === "recommendation";
            const failed = node.status === "failed" || node.kind === "abstention";

            return (
              <g
                key={node.id}
                opacity={dim ? 0.22 : 1}
                className="cursor-pointer"
                onClick={(event) => {
                  event.stopPropagation();
                  setSelected(selected === node.id ? null : node.id);
                }}
              >
                <rect
                  x={x}
                  y={y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={4}
                  fill={isFinal ? "#1c1c22" : "var(--color-surface)"}
                  stroke={failed ? "var(--color-speculative)" : selected === node.id ? accent : "var(--color-line)"}
                  strokeWidth={selected === node.id ? 1.6 : 1}
                />
                <rect x={x} y={y} width={2.5} height={NODE_H} rx={1} fill={accent} />
                <text
                  x={x + 9}
                  y={y + 13}
                  fontSize={9}
                  fill="var(--color-faint)"
                  className="select-none"
                >
                  {node.module ?? KIND_LABEL[node.kind]}
                </text>
                <text
                  x={x + 9}
                  y={y + 26}
                  fontSize={10.5}
                  fill={isFinal ? "#fff" : "var(--color-text)"}
                  className="select-none"
                >
                  {clip(node.artifact_kind ?? node.label, 22)}
                </text>
                <title>{node.detail || node.label}</title>
              </g>
            );
          })}
        </svg>
      </div>

      {active ? (
        <div className="rise rounded border border-[var(--color-line-soft)] bg-[var(--color-raised)] p-3">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="text-[13px] font-medium">{active.label}</span>
            <Chip
              colour={
                active.module ? accentOf(active.module, specs[active.module]?.skin.accent) : undefined
              }
            >
              {KIND_LABEL[active.kind]}
            </Chip>
            {active.artifact_kind && <Chip>{active.artifact_kind}</Chip>}
            {active.status === "failed" && <Chip colour="var(--color-speculative)">failed</Chip>}
            <span className="mono ml-auto text-[10.5px] text-[var(--color-faint)]">
              layer {active.depth}
            </span>
          </div>
          {active.detail && (
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-muted)]">
              {active.detail}
            </p>
          )}
        </div>
      ) : (
        <p className="text-[11.5px] leading-relaxed text-[var(--color-faint)]">
          Drag to pan, scroll to zoom, click a node to isolate it and its neighbours.
          Every node is a validated artifact from the run — nothing here was generated
          for the diagram.
        </p>
      )}
    </div>
  );
}

/**
 * Deterministic layered layout.
 *
 * Column = server-computed `depth`. Within a column, nodes are ordered by module
 * lane (so a module keeps a consistent vertical position across columns) and then by
 * kind, which makes the six parallel programs read as parallel.
 */
function layout(trace: TraceGraph, moduleOrder: string[]) {
  const lane = new Map(moduleOrder.map((module, index) => [module, index]));
  const columns = new Map<number, TraceNode[]>();

  for (const node of trace.nodes) {
    const bucket = columns.get(node.depth) ?? [];
    bucket.push(node);
    columns.set(node.depth, bucket);
  }

  const placed: Placed[] = [];
  let tallest = 0;

  for (const [depth, nodes] of [...columns.entries()].sort((a, b) => a[0] - b[0])) {
    nodes.sort((a, b) => {
      const laneA = a.module ? (lane.get(a.module) ?? 90) : 99;
      const laneB = b.module ? (lane.get(b.module) ?? 90) : 99;
      if (laneA !== laneB) return laneA - laneB;
      return (a.stage_id ?? a.id).localeCompare(b.stage_id ?? b.id);
    });
    nodes.forEach((node, index) => {
      placed.push({
        node,
        x: PAD + depth * (NODE_W + COL_GAP),
        y: PAD + index * (NODE_H + ROW_GAP),
      });
    });
    tallest = Math.max(tallest, nodes.length);
  }

  const maxDepth = Math.max(0, ...trace.nodes.map((n) => n.depth));
  return {
    placed,
    width: PAD * 2 + (maxDepth + 1) * (NODE_W + COL_GAP),
    height: PAD * 2 + tallest * (NODE_H + ROW_GAP),
  };
}

const clip = (text: string, limit: number) =>
  text.length <= limit ? text : `${text.slice(0, limit - 1)}…`;
