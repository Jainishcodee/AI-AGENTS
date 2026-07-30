"use client";

import { useEffect, useRef } from "react";
import type { FeedEntry } from "@/lib/game/types";
import type { ClientView } from "@/lib/engine/view";

/**
 * The case file, written as you work.
 *
 * This is the game's spine. Every action appends a dated entry — where you were,
 * what time it was, and what happened in prose. A player scrolling back is
 * reading their own investigation, not a log of button presses, and that is the
 * whole difference between a detective game and a control panel.
 */
export function Journal({
  view,
  feed,
  brief,
}: {
  view: ClientView;
  feed: FeedEntry[];
  /** The opening entry, before anyone has done anything. */
  brief: { dateline: string; time: string };
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const count = feed.length;

  // Newest entry to the bottom, the way a journal fills up.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [count]);

  let lastDateline = "";

  return (
    <div className="space-y-7 px-5 py-6 sm:px-7">
      <Entry
        dateline={brief.dateline}
        time={brief.time}
        title="Your office"
        showDateline
      >
        <p className="whitespace-pre-line font-serif text-[14px] leading-relaxed text-neutral-400">
          {view.brief}
        </p>
      </Entry>

      {feed.map((entry) => {
        const showDateline = entry.dateline !== lastDateline;
        lastDateline = entry.dateline;

        return (
          <Entry
            key={entry.seq}
            dateline={entry.dateline}
            time={entry.time}
            title={entry.title}
            kind={entry.kind}
            showDateline={showDateline}
          >
            <p className="whitespace-pre-line font-serif text-[14px] leading-relaxed text-neutral-400">
              {entry.body}
            </p>

            {entry.newClues.length > 0 && (
              <ul className="mt-4 space-y-1 border-l-2 border-amber-200/30 pl-3">
                {entry.newClues.map((c) => (
                  <li key={c.id} className="text-[12.5px] text-amber-200/80">
                    Into evidence &mdash; {c.title}
                  </li>
                ))}
              </ul>
            )}

            {entry.timeSpent > 0 && (
              <p className="mt-3 text-[10px] tracking-[0.2em] text-neutral-700">
                {entry.timeSpent} {entry.timeSpent === 1 ? "HOUR" : "HOURS"} GONE
              </p>
            )}
          </Entry>
        );
      })}

      <div ref={endRef} />
    </div>
  );
}

const KIND_LABEL: Record<NonNullable<FeedEntry["kind"]>, string> = {
  travel: "ARRIVED",
  search: "SEARCHED",
  interview: "SPOKE TO",
  lab: "LABORATORY",
  accuse: "ACCUSATION",
};

function Entry({
  dateline,
  time,
  title,
  kind,
  showDateline,
  children,
}: {
  dateline: string;
  time: string;
  title: string;
  kind?: FeedEntry["kind"];
  showDateline: boolean;
  children: React.ReactNode;
}) {
  return (
    <article>
      {showDateline && (
        <p className="mb-3 border-b border-neutral-800 pb-2 font-serif text-[15px] text-neutral-200">
          {dateline}
        </p>
      )}

      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[10px] tracking-[0.25em] text-neutral-600">
          {kind ? KIND_LABEL[kind] : "THE JOB"}
        </p>
        <p className="shrink-0 font-mono text-[11px] tabular-nums text-neutral-600">
          {time}
        </p>
      </div>

      <h3 className="mt-1 font-serif text-lg leading-tight text-neutral-100">
        {title}
      </h3>

      <div className="mt-2.5">{children}</div>
    </article>
  );
}
