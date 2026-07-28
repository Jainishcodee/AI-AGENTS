"use client";

import { useState } from "react";
import type { Action } from "@/lib/engine/reducer";
import type { ClientView, PublicNpc } from "@/lib/engine/view";
import type { CityLocation } from "@/lib/engine/citySchema";
import type { FeedEntry } from "@/lib/game/types";

/**
 * Where you are and what you can do about it. Search cost is shown before the
 * click, never after - the player has to be able to weigh it.
 */
export function HerePanel({
  view,
  selected,
  travelCost,
  feed,
  act,
  busy,
}: {
  view: ClientView;
  selected: CityLocation | null;
  travelCost: number;
  feed: FeedEntry[];
  act: (a: Action) => void;
  busy: boolean;
}) {
  const here = view.here;
  const closed = view.state.status === "finished";
  const isElsewhere = selected !== null && selected.id !== here.id;

  return (
    <div className="space-y-6 px-6 py-5">
      {isElsewhere && selected && (
        <section className="border border-neutral-800 p-4">
          <p className="text-[10px] tracking-[0.25em] text-neutral-600">
            {selected.type.toUpperCase()}
            {selected.isLandmark && " · LANDMARK"}
          </p>
          <h3 className="mt-1.5 font-serif text-lg leading-tight text-neutral-100">
            {selected.name}
          </h3>
          <p className="mt-0.5 text-xs text-neutral-500">{selected.address}</p>
          <p className="mt-3 font-serif text-[13px] leading-relaxed text-neutral-400">
            {selected.blurb}
          </p>
          <button
            disabled={busy || closed || travelCost > view.state.timeRemaining}
            onClick={() => act({ type: "travel", locationId: selected.id })}
            className="mt-4 w-full border border-neutral-700 px-4 py-2.5 text-[11px] tracking-[0.2em] text-neutral-300 transition hover:border-amber-200/50 hover:text-amber-100 disabled:cursor-not-allowed disabled:opacity-30"
          >
            DRIVE OVER &mdash; {travelCost} {travelCost === 1 ? "HOUR" : "HOURS"}
          </button>
        </section>
      )}

      <section>
        <p className="text-[10px] tracking-[0.3em] text-amber-200/60">YOU ARE AT</p>
        <h3 className="mt-1.5 font-serif text-xl leading-tight text-neutral-100">
          {here.name}
        </h3>
        <p className="mt-0.5 text-xs text-neutral-500">
          {here.address} &middot; {here.boroughName}
        </p>
        <p className="mt-3 font-serif text-[14px] leading-relaxed text-neutral-400">
          {here.description}
        </p>

        <button
          disabled={busy || closed}
          onClick={() => act({ type: "search" })}
          className="mt-4 w-full border border-neutral-700 px-4 py-2.5 text-[11px] tracking-[0.2em] text-neutral-200 transition hover:border-amber-200/50 hover:text-amber-100 disabled:cursor-not-allowed disabled:opacity-30"
        >
          SEARCH THIS PLACE
          {here.searchCount > 0 && ` (${here.searchCount}× ALREADY)`}
        </button>
      </section>

      {here.npcs.length > 0 && (
        <section className="space-y-4">
          <p className="text-[10px] tracking-[0.3em] text-neutral-600">
            PEOPLE HERE
          </p>
          {here.npcs.map((npc) => (
            <NpcBlock key={npc.id} npc={npc} feed={feed} act={act} busy={busy || closed} />
          ))}
        </section>
      )}
    </div>
  );
}

function NpcBlock({
  npc,
  feed,
  act,
  busy,
}: {
  npc: PublicNpc;
  feed: FeedEntry[];
  act: (a: Action) => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);

  // Answers live in the action feed, so they survive a refresh without the
  // client ever caching case text of its own.
  const answerFor = (questionText: string) =>
    feed.find((f) => f.answer && f.summary.includes(questionText))?.answer;

  return (
    <div className="border border-neutral-800 p-4">
      <h4 className="font-serif text-base text-neutral-100">{npc.name}</h4>
      <p className="mt-0.5 text-[11px] tracking-wide text-neutral-600">{npc.role}</p>

      <ul className="mt-3 space-y-2">
        {npc.questions.map((q) => {
          const answer = q.asked ? answerFor(q.text) : undefined;
          return (
            <li key={q.id}>
              <button
                disabled={busy || (q.asked && !answer)}
                onClick={() =>
                  q.asked
                    ? setOpen(open === q.id ? null : q.id)
                    : act({ type: "interview", npcId: npc.id, questionId: q.id })
                }
                className={`w-full text-left font-serif text-[13px] leading-snug transition ${
                  q.asked
                    ? "text-neutral-600 hover:text-neutral-400"
                    : "text-amber-100/80 hover:text-amber-100"
                } disabled:cursor-not-allowed`}
              >
                <span className="mr-1.5 text-neutral-700">
                  {q.asked ? "✓" : "›"}
                </span>
                &ldquo;{q.text}&rdquo;
                {!q.asked && (
                  <span className="ml-1.5 text-[10px] tracking-widest text-neutral-600">
                    1H
                  </span>
                )}
              </button>
              {q.asked && open === q.id && answer && (
                <p className="mt-2 border-l border-neutral-800 pl-3 font-serif text-[13px] leading-relaxed text-neutral-400">
                  {answer}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      {npc.questions.every((q) => q.asked) && (
        <p className="mt-3 text-[11px] italic text-neutral-700">
          Nothing further, unless you turn something up.
        </p>
      )}
    </div>
  );
}
