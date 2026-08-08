"use client";

/**
 * Decision Cards, due ones first.
 *
 * Ordering matters more than it looks: a card whose check-in date has passed is the
 * only thing in the product actively asking for something, and it is also the only
 * action that makes the council better. Burying it under newest-first would make the
 * learning loop depend on the user remembering.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON } from "@/lib/stream";
import type { CardStatus, DecisionCard } from "@/lib/types";
import { Chip, Label } from "@/components/ui";

const FILTERS: { id: CardStatus | "all"; label: string; hint: string }[] = [
  { id: "all", label: "all", hint: "Everything, due first" },
  { id: "due", label: "due", hint: "The check-in date has arrived" },
  { id: "open", label: "open", hint: "Decided, not yet due for a check-in" },
  { id: "resolved", label: "resolved", hint: "Outcome recorded and scored" },
];

export default function HistoryPage() {
  const [cards, setCards] = useState<DecisionCard[] | null>(null);
  const [filter, setFilter] = useState<CardStatus | "all">("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Read the initial filter from the URL so the nav badge can deep-link to `due`.
    const params = new URLSearchParams(window.location.search);
    const wanted = params.get("status");
    if (wanted && FILTERS.some((f) => f.id === wanted)) setFilter(wanted as CardStatus);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setCards(null);
    const query = filter === "all" ? "" : `?status=${filter}`;
    getJSON<DecisionCard[]>(`cards${query}`)
      .then((data) => !cancelled && setCards(data))
      .catch((cause) => !cancelled && setError(String(cause?.message ?? cause)));
    return () => {
      cancelled = true;
    };
  }, [filter]);

  const counts = useMemo(() => {
    if (!cards) return null;
    return {
      total: cards.length,
      resolved: cards.filter((c) => c.resolution).length,
    };
  }, [cards]);

  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 py-7 sm:px-6 lg:px-8">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[15px] font-medium tracking-tight">Decisions</h1>
          <p className="mt-0.5 text-[12px] text-[var(--color-faint)]">
            Every deliberation leaves a card with a dated prediction. Recording the
            outcome is what makes the council yours.
          </p>
        </div>
        {counts && (
          <span className="mono text-[11px] text-[var(--color-faint)]">
            {counts.resolved} of {counts.total} resolved
          </span>
        )}
      </div>

      <div className="mb-4 flex flex-wrap gap-1">
        {FILTERS.map((option) => (
          <button
            key={option.id}
            type="button"
            title={option.hint}
            onClick={() => setFilter(option.id)}
            className={`rounded px-2.5 py-1 text-[12.5px] transition-colors ${
              filter === option.id
                ? "bg-[var(--color-raised)] text-[var(--color-text)]"
                : "text-[var(--color-faint)] hover:text-[var(--color-muted)]"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {error && <p className="text-[13px] text-[var(--color-speculative)]">{error}</p>}
      {!cards && !error && <p className="text-[13px] text-[var(--color-faint)]">loading…</p>}

      {cards?.length === 0 && (
        <div className="rounded-lg border bg-[var(--color-surface)] p-6 hair">
          <p className="text-[13.5px] leading-relaxed">
            {filter === "all"
              ? "No decisions yet."
              : `Nothing ${filter}.`}
          </p>
          <Link
            href="/"
            className="mt-2 inline-block text-[13px] underline decoration-dotted underline-offset-2 text-[var(--color-muted)] hover:text-[var(--color-text)]"
          >
            Put a decision to the council →
          </Link>
        </div>
      )}

      <div className="space-y-2">
        {cards?.map((card) => <CardRow key={card.id} card={card} />)}
      </div>
    </main>
  );
}

function CardRow({ card }: { card: DecisionCard }) {
  const due = card.expected_outcome?.check_on ?? null;
  const isDue = !card.resolution && due !== null && due <= new Date().toISOString().slice(0, 10);
  const verdicts = card.scoring?.module_verdicts ?? [];
  const right = verdicts.filter((v) => v.verdict === "right").length;
  const tested = verdicts.filter((v) => v.verdict !== "untested").length;

  return (
    <Link
      href={`/cards/${card.id}`}
      className="block rounded-lg border bg-[var(--color-surface)] px-4 py-3 transition-colors hair hover:border-[#34343c]"
      style={isDue ? { borderLeftColor: "var(--color-assumed)", borderLeftWidth: 2 } : undefined}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="min-w-0 flex-1 text-[13.5px] leading-snug">{card.question}</span>
        <span className="mono shrink-0 text-[10.5px] text-[var(--color-faint)]">
          {card.created_at.slice(0, 10)}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {card.resolution ? (
          <Chip colour="var(--color-given)">resolved</Chip>
        ) : isDue ? (
          <Chip colour="var(--color-assumed)">due {due}</Chip>
        ) : (
          <Chip>check in {due ?? "—"}</Chip>
        )}
        <Chip>{card.preset}</Chip>
        {card.domains.slice(0, 2).map((domain) => (
          <Chip key={domain}>{domain}</Chip>
        ))}
        {tested > 0 && (
          <span
            className="mono text-[10.5px] text-[var(--color-faint)]"
            title="modules scored right, of those actually tested"
          >
            {right}/{tested} right
          </span>
        )}
        {card.scoring && !card.scoring.chose_was_proposed && (
          <Chip colour="var(--color-assumed)" title="You did something no module proposed">
            off-menu
          </Chip>
        )}
      </div>

      {card.resolution && (
        <p className="mt-2 line-clamp-2 text-[12.5px] leading-snug text-[var(--color-muted)]">
          <span className="label mr-1.5">you did</span>
          {card.resolution.chose}
        </p>
      )}
      {!card.resolution && card.expected_outcome && (
        <p className="mt-2 line-clamp-1 text-[12.5px] leading-snug text-[var(--color-faint)]">
          <span className="label mr-1.5">predicted</span>
          {card.expected_outcome.statement}
        </p>
      )}
    </Link>
  );
}
