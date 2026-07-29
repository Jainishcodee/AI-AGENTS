"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import { useCity } from "@/lib/city/useCity";
import { indexCity, travelCost, type CityLocation } from "@/lib/engine/citySchema";
import type { Action } from "@/lib/engine/reducer";
import type { ClientView } from "@/lib/engine/view";
import type { TutorialProgress } from "@/lib/engine/tutorial";
import type { FeedEntry } from "@/lib/game/types";
import { Hud } from "./Hud";
import { TutorialPanel } from "./TutorialPanel";
import { HerePanel } from "./HerePanel";
import { EvidencePanel } from "./EvidencePanel";
import { AccusePanel } from "./AccusePanel";
import { Verdict } from "./Verdict";
import { Corkboard } from "./Corkboard";
import { useBoard } from "@/lib/game/useBoard";

const CityMap = dynamic(() => import("@/components/map/CityMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-[11px] tracking-[0.3em] text-neutral-700">
      DEVELOPING PLATE...
    </div>
  ),
});

type Tab = "here" | "evidence" | "accuse";

/**
 * The board. Identical whether one person is playing or six - the only
 * difference is where the snapshot comes from, so both callers hand it in.
 */
export function Investigation({
  view,
  tutorial,
  feed,
  act,
  busy = false,
  onRestart,
  aside,
  banner,
  overlay,
  gameId,
}: {
  view: ClientView;
  tutorial: TutorialProgress;
  feed: FeedEntry[];
  act: (a: Action) => void;
  busy?: boolean;
  /** Solo only - a shared room cannot be reset by one player. */
  onRestart?: () => void;
  /** Multiplayer roster, slotted under the HUD. */
  aside?: ReactNode;
  /** Refusal message, or anything else worth putting over the map. */
  banner?: ReactNode;
  /** Chat and anything else that floats over the map in a shared room. */
  overlay?: ReactNode;
  /** Present in a room; the corkboard then syncs instead of living in memory. */
  gameId?: string | null;
}) {
  const { city } = useCity();
  const [tab, setTab] = useState<Tab>("here");
  const [selected, setSelected] = useState<CityLocation | null>(null);
  const [briefOpen, setBriefOpen] = useState(true);
  const [boardOpen, setBoardOpen] = useState(false);

  const index = useMemo(() => (city ? indexCity(city) : null), [city]);

  // Held here, not inside the corkboard, so the arrangement outlives closing it.
  const clueIds = useMemo(() => view.clues.map((c) => c.id), [view.clues]);
  const board = useBoard(clueIds, gameId);

  // Travelling makes the old selection stale; clear it so the panel snaps back
  // to wherever the team actually is.
  const hereId = view.here.id;
  useEffect(() => {
    setSelected(null);
  }, [hereId]);

  const visited = useMemo(
    () => new Set(Object.keys(view.state.searchCounts)),
    [view.state.searchCounts],
  );

  const cost = index && selected ? travelCost(index, hereId, selected.id) : 0;

  return (
    <main className="relative flex h-dvh bg-[#08090b] text-neutral-300">
      <div className="relative flex-1">
        {city && (
          <CityMap
            city={city}
            visited={visited}
            hereId={hereId}
            focusedId={selected?.id ?? null}
            onSelect={setSelected}
          />
        )}

        {briefOpen && (
          <div className="absolute inset-x-6 top-6 z-[1000] max-w-lg border border-neutral-800 bg-[#0e0f11]/95 p-6 backdrop-blur">
            <p className="text-[10px] tracking-[0.3em] text-amber-200/60">THE JOB</p>
            <h2 className="mt-2 font-serif text-xl text-neutral-100">{view.title}</h2>
            <p className="mt-3 font-serif text-[14px] leading-relaxed text-neutral-400">
              {view.brief}
            </p>
            <button
              onClick={() => setBriefOpen(false)}
              className="mt-5 border border-neutral-700 px-5 py-2 text-[11px] tracking-[0.2em] text-neutral-300 transition hover:border-amber-200/50 hover:text-amber-100"
            >
              GET TO WORK
            </button>
          </div>
        )}

        {!briefOpen && (
          <button
            onClick={() => setBriefOpen(true)}
            className="absolute left-6 top-6 z-[1000] border border-neutral-800 bg-[#0e0f11]/90 px-3 py-1.5 text-[10px] tracking-[0.2em] text-neutral-500 backdrop-blur transition hover:text-neutral-300"
          >
            THE JOB
          </button>
        )}

        <button
          onClick={() => setBoardOpen(true)}
          className="absolute right-6 top-6 z-[1000] border border-neutral-800 bg-[#0e0f11]/90 px-4 py-2 text-[10px] tracking-[0.2em] text-neutral-400 backdrop-blur transition hover:border-amber-200/40 hover:text-amber-100"
        >
          THE BOARD
          {view.clues.length > 0 && (
            <span className="ml-2 text-neutral-600">{view.clues.length}</span>
          )}
        </button>

        {banner}
        {overlay}
        <ActionFeed feed={feed} />

        {boardOpen && (
          <Corkboard
            clues={view.clues}
            suspects={view.suspects}
            board={board}
            onClose={() => setBoardOpen(false)}
          />
        )}
      </div>

      <aside className="flex w-[400px] shrink-0 flex-col border-l border-neutral-800 bg-[#0e0f11]">
        <Hud view={view} onRestart={onRestart} />
        {aside}
        <TutorialPanel progress={tutorial} />

        <nav className="flex border-b border-neutral-800">
          {(
            [
              ["here", "HERE"],
              ["evidence", `EVIDENCE (${view.clues.length})`],
              ["accuse", "ACCUSE"],
            ] as Array<[Tab, string]>
          ).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex-1 border-b-2 px-2 py-3 text-[10px] tracking-[0.2em] transition ${
                tab === id
                  ? "border-amber-200/60 text-amber-100"
                  : "border-transparent text-neutral-600 hover:text-neutral-400"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="flex-1 overflow-y-auto">
          {tab === "here" && (
            <HerePanel
              view={view}
              selected={selected}
              travelCost={cost}
              feed={feed}
              act={act}
              busy={busy}
            />
          )}
          {tab === "evidence" && <EvidencePanel view={view} act={act} busy={busy} />}
          {tab === "accuse" && <AccusePanel view={view} act={act} busy={busy} />}
        </div>
      </aside>

      {view.state.status === "finished" && (
        <Verdict view={view} onRestart={onRestart} />
      )}
    </main>
  );
}

/** The last few things that happened, so a team can see what just changed. */
function ActionFeed({ feed }: { feed: FeedEntry[] }) {
  const recent = feed.slice(-4);
  if (!recent.length) return null;

  return (
    <ul className="pointer-events-none absolute bottom-6 left-6 z-[1000] max-w-md space-y-1.5 pr-6">
      {recent.map((entry, i) => (
        <li
          key={entry.seq}
          className="border-l-2 border-neutral-700 bg-[#0e0f11]/95 py-1.5 pl-3 pr-4 backdrop-blur"
          // Older entries recede, but never so far that they stop being legible
          // against the map underneath.
          style={{ opacity: 0.6 + (i / recent.length) * 0.4 }}
        >
          <span className="font-serif text-[13px] text-neutral-300">
            {entry.summary}
          </span>
          {entry.timeSpent > 0 && (
            <span className="ml-2 text-[10px] tracking-widest text-neutral-600">
              &minus;{entry.timeSpent}H
            </span>
          )}
          {entry.newClues.map((c) => (
            <span key={c.id} className="mt-0.5 block text-[12px] text-amber-200/70">
              + {c.title}
            </span>
          ))}
        </li>
      ))}
    </ul>
  );
}
