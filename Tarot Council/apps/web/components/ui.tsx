"use client";

/**
 * The handful of primitives this app needs.
 *
 * Deliberately not shadcn/ui: it is a generator, and for six primitives it adds a
 * dependency chain and a components.json to maintain while nearly every surface
 * here is bespoke data display rather than a button or a dialog. The design tokens
 * live in globals.css instead, which is the part worth sharing.
 */

import type { ReactNode } from "react";
import type { EvidenceStatus, ModuleId } from "@/lib/types";

export const STATUS_COLOUR: Record<EvidenceStatus, string> = {
  given: "var(--color-given)",
  inferred: "var(--color-inferred)",
  assumed: "var(--color-assumed)",
  speculative: "var(--color-speculative)",
  unknown: "var(--color-unknown)",
};

export function Label({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`label ${className}`}>{children}</div>;
}

export function Panel({
  children,
  className = "",
  accent,
}: {
  children: ReactNode;
  className?: string;
  accent?: string;
}) {
  return (
    <section
      className={`rounded-lg border bg-[var(--color-surface)] hair ${className}`}
      style={accent ? { borderTopColor: accent, borderTopWidth: 2 } : undefined}
    >
      {children}
    </section>
  );
}

export function Chip({
  children,
  colour,
  title,
}: {
  children: ReactNode;
  colour?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10.5px] leading-none tracking-wide"
      style={{
        borderColor: colour ? `${colour}55` : "var(--color-line)",
        color: colour ?? "var(--color-muted)",
        background: colour ? `${colour}12` : "transparent",
      }}
    >
      {children}
    </span>
  );
}

export function StatusDot({ status }: { status: EvidenceStatus }) {
  return (
    <span
      title={status}
      aria-label={status}
      className="inline-block size-1.5 shrink-0 rounded-full"
      style={{ background: STATUS_COLOUR[status] ?? "var(--color-unknown)" }}
    />
  );
}

/** A 0..1 meter. Used for confidence, authority, influence, applicability. */
export function Meter({
  value,
  colour = "var(--color-muted)",
  width = 44,
  title,
}: {
  value: number;
  colour?: string;
  width?: number;
  title?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <span
      title={title ?? value.toFixed(2)}
      className="inline-flex items-center gap-1.5 align-middle"
    >
      <span
        className="relative inline-block h-1 overflow-hidden rounded-full bg-[var(--color-line)]"
        style={{ width }}
      >
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${pct}%`, background: colour }}
        />
      </span>
      <span className="mono text-[10.5px] text-[var(--color-faint)]">{value.toFixed(2)}</span>
    </span>
  );
}

/** 1..5 scores render as pips: faster to compare across rows than digits. */
export function Pips({ value, max = 5, colour }: { value: number; max?: number; colour?: string }) {
  return (
    <span className="inline-flex items-center gap-[3px] align-middle" title={`${value}/${max}`}>
      {Array.from({ length: max }, (_, i) => (
        <span
          key={i}
          className="inline-block size-[5px] rounded-full"
          style={{
            background:
              i < value ? (colour ?? "var(--color-muted)") : "var(--color-line)",
          }}
        />
      ))}
    </span>
  );
}

export function Table({
  head,
  children,
}: {
  head: (string | { label: string; align?: "left" | "right" })[];
  children: ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr className="border-b hair">
            {head.map((column, index) => {
              const spec = typeof column === "string" ? { label: column } : column;
              return (
                <th
                  key={index}
                  className={`label pb-1.5 pt-0 font-medium ${
                    spec.align === "right" ? "text-right" : "text-left"
                  }`}
                >
                  {spec.label}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Row({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <tr
      data-row-id={id}
      className="border-b border-[var(--color-line-soft)] align-top last:border-0"
    >
      {children}
    </tr>
  );
}

export function Cell({
  children,
  align = "left",
  className = "",
  width,
}: {
  children: ReactNode;
  align?: "left" | "right";
  className?: string;
  width?: string;
}) {
  return (
    <td
      className={`py-1.5 pr-3 last:pr-0 ${align === "right" ? "text-right" : ""} ${className}`}
      style={width ? { width } : undefined}
    >
      {children}
    </td>
  );
}

export function RowId({ id }: { id: string }) {
  return (
    <span className="mono text-[10px] text-[var(--color-faint)]" title={`row ${id}`}>
      {id}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-2 text-[12px] italic text-[var(--color-faint)]">{children}</div>;
}

export function Bullets({ items, colour }: { items: string[]; colour?: string }) {
  if (!items?.length) return null;
  return (
    <ul className="space-y-1">
      {items.map((item, index) => (
        <li key={index} className="flex gap-2 text-[13px] leading-relaxed">
          <span className="select-none pt-[3px] text-[10px]" style={{ color: colour ?? "var(--color-faint)" }}>
            ▪
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "default",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "default" | "primary" | "ghost";
  type?: "button" | "submit";
}) {
  const styles = {
    default:
      "border-[var(--color-line)] bg-[var(--color-raised)] hover:border-[#34343c] text-[var(--color-text)]",
    primary:
      "border-transparent bg-[#e9e6e1] text-[#0b0b0d] hover:bg-white font-medium",
    ghost: "border-transparent text-[var(--color-muted)] hover:text-[var(--color-text)]",
  }[variant];

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md border px-3 py-1.5 text-[13px] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${styles}`}
    >
      {children}
    </button>
  );
}

export const MODULE_FALLBACK_ACCENT: Record<string, string> = {
  analyst: "#7c93b8",
  tactician: "#c9a227",
  strategist: "#b08968",
  psychologist: "#c98da7",
  optimizer: "#7fae9b",
  ethicist: "#a8a29e",
};

export const accentOf = (module: ModuleId, accent?: string) =>
  accent ?? MODULE_FALLBACK_ACCENT[module] ?? "#8a8a8a";
