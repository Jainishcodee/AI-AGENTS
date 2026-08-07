"use client";

/**
 * The analyst's tree, drawn as a tree.
 *
 * Rendering it as a nested list rather than a node graph is deliberate: the thing a
 * reader needs from it is "which branch is likely, and what happens at the end",
 * which is a reading task, not a spatial one. Probability mass gets a bar so
 * sibling comparison is instant, and each node shows the running joint probability
 * — the number people actually want and never compute themselves.
 */

import { Empty } from "@/components/ui";

interface Outcome {
  description: string;
  valence: number;
  magnitude: number;
}

interface Node {
  id: string;
  label: string;
  probability: number | null;
  condition: string | null;
  outcome: Outcome | null;
  children: Node[];
}

export function ProbabilityTree({ data, accent }: { data: Record<string, unknown>; accent: string }) {
  const root = data.root as Node | undefined;
  if (!root) return <Empty>No tree.</Empty>;
  return (
    <div className="space-y-1">
      <Branch node={root} accent={accent} joint={1} depth={0} isLast />
    </div>
  );
}

function Branch({
  node,
  accent,
  joint,
  depth,
  isLast,
}: {
  node: Node;
  accent: string;
  joint: number;
  depth: number;
  isLast: boolean;
}) {
  const own = node.probability ?? 1;
  const cumulative = joint * own;
  const children = node.children ?? [];

  return (
    <div className="relative">
      <div className="flex items-baseline gap-2">
        {depth > 0 && (
          <span className="mono shrink-0 text-[10px] text-[var(--color-line)]">
            {isLast ? "└" : "├"}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            {depth > 0 && (
              <span
                className="mono shrink-0 text-[11px] tabular-nums"
                style={{ color: accent }}
                title={`branch ${(own * 100).toFixed(0)}% · joint ${(cumulative * 100).toFixed(1)}%`}
              >
                {(own * 100).toFixed(0)}%
              </span>
            )}
            <span className="text-[13px] leading-snug">{node.label}</span>
            {depth > 1 && (
              <span className="mono text-[10px] text-[var(--color-faint)]">
                joint {(cumulative * 100).toFixed(1)}%
              </span>
            )}
          </div>

          {depth > 0 && (
            <div className="mt-1 h-[2px] max-w-[220px] overflow-hidden rounded-full bg-[var(--color-line-soft)]">
              <div
                className="h-full rounded-full"
                style={{ width: `${own * 100}%`, background: `${accent}99` }}
              />
            </div>
          )}

          {node.condition && (
            <div className="mt-1 text-[11.5px] italic text-[var(--color-faint)]">
              when: {node.condition}
            </div>
          )}

          {node.outcome && (
            <div className="mt-1.5 flex items-start gap-2 rounded border border-[var(--color-line-soft)] bg-[var(--color-raised)] px-2 py-1.5">
              <ValenceMark valence={node.outcome.valence} magnitude={node.outcome.magnitude} />
              <span className="text-[12.5px] leading-snug text-[var(--color-muted)]">
                {node.outcome.description}
              </span>
            </div>
          )}
        </div>
      </div>

      {children.length > 0 && (
        <div className="ml-3 mt-1.5 space-y-1.5 border-l border-[var(--color-line-soft)] pl-3">
          {children.map((child, index) => (
            <Branch
              key={child.id ?? index}
              node={child}
              accent={accent}
              joint={cumulative}
              depth={depth + 1}
              isLast={index === children.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Valence is a signed magnitude, so it gets a signed glyph rather than a colour
 *  alone — colour-only encoding fails for a meaningful share of readers. */
function ValenceMark({ valence, magnitude }: { valence: number; magnitude: number }) {
  const good = valence >= 0.15;
  const bad = valence <= -0.15;
  const colour = good ? "var(--color-given)" : bad ? "var(--color-speculative)" : "var(--color-faint)";
  return (
    <span
      className="mono mt-[1px] shrink-0 text-[11px]"
      style={{ color: colour }}
      title={`valence ${valence.toFixed(2)}, magnitude ${magnitude}/5`}
    >
      {good ? "+" : bad ? "−" : "="}
      {magnitude}
    </span>
  );
}
