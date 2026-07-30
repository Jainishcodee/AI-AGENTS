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
    <div className="space-y-6 px-5 py-5 sm:px-6">
      {isElsewhere && selected && (
        <section className="border border-line p-4">
          <p className="text-[10px] tracking-[0.25em] text-faint">
            {selected.type.toUpperCase()}
            {selected.isLandmark && " · LANDMARK"}
          </p>
          <h3 className="mt-1.5 font-serif text-lg leading-tight text-bright">
            {selected.name}
          </h3>
          <p className="mt-0.5 text-xs text-faint">{selected.address}</p>
          <p className="mt-3 font-serif text-[13px] leading-relaxed text-muted">
            {selected.blurb}
          </p>
          <button
            disabled={busy || closed || travelCost > view.state.timeRemaining}
            onClick={() => act({ type: "travel", locationId: selected.id })}
            className="mt-4 w-full border border-edge px-4 py-2.5 text-[11px] tracking-[0.2em] text-muted lift hover:border-muted hover:text-bright disabled:cursor-not-allowed disabled:opacity-30"
          >
            DRIVE OVER &mdash; <span className="numeral">{travelCost}</span>{" "}
            {travelCost === 1 ? "HOUR" : "HOURS"}
          </button>
        </section>
      )}

      <section>
        {/* Gold's third and last permitted use: where you are standing. */}
        <p className="text-[10px] tracking-[0.3em] text-gold">YOU ARE AT</p>
        <h3 className="mt-1.5 font-serif text-xl leading-tight text-bright">
          {here.name}
        </h3>
        <p className="mt-0.5 text-xs text-faint">
          {here.address} &middot; {here.boroughName}
        </p>
        <p className="mt-3 font-serif text-[14px] leading-relaxed text-muted">
          {here.description}
        </p>

        <button
          disabled={busy || closed}
          onClick={() => act({ type: "search" })}
          className="mt-4 w-full border border-edge px-4 py-2.5 text-[11px] tracking-[0.2em] text-bright lift hover:border-muted hover:text-bright disabled:cursor-not-allowed disabled:opacity-30"
        >
          SEARCH THIS PLACE
          {here.searchCount > 0 && (
            <>
              {" ("}
              <span className="numeral">{here.searchCount}</span>
              {"× ALREADY)"}
            </>
          )}
        </button>
      </section>

      {here.npcs.length > 0 && (
        <section className="space-y-4">
          <p className="text-[10px] tracking-[0.3em] text-faint">
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
    <div className="border border-line p-4">
      <h4 className="font-serif text-base text-bright">{npc.name}</h4>
      <p className="mt-0.5 text-[11px] tracking-wide text-faint">{npc.role}</p>

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
                className={`w-full text-left font-serif text-[13px] leading-snug lift ${
                  q.asked
                    ? "text-faint hover:text-muted"
                    : "text-muted hover:text-bright"
                } disabled:cursor-not-allowed`}
              >
                <span className="mr-1.5 text-ghost">
                  {q.asked ? "✓" : "›"}
                </span>
                &ldquo;{q.text}&rdquo;
                {!q.asked && (
                  <span className="ml-1.5 text-[10px] tracking-widest text-faint">
                    <span className="numeral">1</span>H
                  </span>
                )}
              </button>
              {q.asked && open === q.id && answer && (
                <p className="mt-2 border-l border-line pl-3 font-serif text-[13px] leading-relaxed text-muted">
                  {answer}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      {npc.questions.every((q) => q.asked) && (
        <p className="mt-3 text-[11px] italic text-ghost">
          Nothing further, unless you turn something up.
        </p>
      )}
    </div>
  );
}
