"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import { useCity } from "@/lib/city/useCity";
import { indexCity, travelCost, type CityLocation } from "@/lib/engine/citySchema";
import type { Action } from "@/lib/engine/reducer";
import type { ClientView } from "@/lib/engine/view";
import type { TutorialProgress } from "@/lib/engine/tutorial";
import type { FeedEntry } from "@/lib/game/types";
import { Hud, timeTone } from "./Hud";
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
  // Phone only. Above `md` the panel is a permanent column and this is inert -
  // the sheet starts down so the first thing a player sees is the city.
  const [sheetOpen, setSheetOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

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

  // Whenever the panel changes what it is about - or reappears from behind a
  // folded sheet - start it at the top. Has to be an effect rather than part of
  // the click: while the sheet is down the panel is display:none, and scrolling
  // something nobody can see does nothing at all.
  useEffect(() => {
    panelRef.current?.scrollTo({ top: 0 });
  }, [tab, sheetOpen, selected]);

  const visited = useMemo(
    () => new Set(Object.keys(view.state.searchCounts)),
    [view.state.searchCounts],
  );

  const cost = index && selected ? travelCost(index, hereId, selected.id) : 0;

  // Picking a pin is a question about that address, so answer it: surface the
  // panel that can, and on a phone raise the sheet that is hiding it.
  function pickLocation(location: CityLocation) {
    setSelected(location);
    showPanel("here");
  }

  function showPanel(next: Tab) {
    setTab(next);
    setSheetOpen(true);
  }

  return (
    <main className="relative flex h-dvh flex-col bg-[#08090b] text-neutral-300 md:flex-row">
      {/* min-h-0 so the map yields to the sheet instead of overflowing the
          column - a flex child defaults to min-height:auto and would not. */}
      <div className="relative min-h-0 flex-1">
        {city && (
          <CityMap
            city={city}
            visited={visited}
            hereId={hereId}
            focusedId={selected?.id ?? null}
            onSelect={pickLocation}
          />
        )}

        {briefOpen && (
          <div className="absolute inset-x-3 top-3 z-[1100] max-h-[70dvh] max-w-lg overflow-y-auto border border-neutral-800 bg-[#0e0f11]/95 p-5 backdrop-blur sm:inset-x-6 sm:top-6 sm:p-6">
            <p className="text-[10px] tracking-[0.3em] text-amber-200/60">THE JOB</p>
            <h2 className="mt-2 font-serif text-lg text-neutral-100 sm:text-xl">
              {view.title}
            </h2>
            <p className="mt-3 font-serif text-[14px] leading-relaxed text-neutral-400">
              {view.brief}
            </p>
            <button
              onClick={() => setBriefOpen(false)}
              className="mt-5 border border-neutral-700 px-5 py-2.5 text-[11px] tracking-[0.2em] text-neutral-300 transition hover:border-amber-200/50 hover:text-amber-100"
            >
              GET TO WORK
            </button>
          </div>
        )}

        {!briefOpen && (
          <button
            onClick={() => setBriefOpen(true)}
            className="absolute left-3 top-3 z-[1000] border border-neutral-800 bg-[#0e0f11]/90 px-3 py-2 text-[10px] tracking-[0.2em] text-neutral-500 backdrop-blur transition hover:text-neutral-300 sm:left-6 sm:top-6 sm:py-1.5"
          >
            THE JOB
          </button>
        )}

        <button
          onClick={() => setBoardOpen(true)}
          className="absolute right-3 top-3 z-[1000] border border-neutral-800 bg-[#0e0f11]/90 px-3 py-2 text-[10px] tracking-[0.2em] text-neutral-400 backdrop-blur transition hover:border-amber-200/40 hover:text-amber-100 sm:right-6 sm:top-6 sm:px-4"
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

      {/* One element, two shapes: a fixed column beside the map on a desktop,
          a bottom sheet under it on a phone. Kept in flow rather than floated
          over the map so the city never hides behind the panel you are using
          to decide where to go next. */}
      <aside
        className={`flex shrink-0 flex-col border-t border-neutral-800 bg-[#0e0f11] md:h-auto md:w-[400px] md:border-l md:border-t-0 ${
          sheetOpen ? "h-[68dvh]" : "h-auto"
        }`}
      >
        <button
          type="button"
          onClick={() => setSheetOpen((v) => !v)}
          aria-expanded={sheetOpen}
          aria-label={sheetOpen ? "Collapse the case panel" : "Expand the case panel"}
          className="relative flex shrink-0 items-center justify-end border-b border-neutral-800 px-5 pb-2.5 pt-4 md:hidden"
        >
          <span className="absolute left-1/2 top-2 h-1 w-10 -translate-x-1/2 rounded-full bg-neutral-700" />
          {/* The clock lives here in both states - folded or not - so it is the
              one thing on a phone that never moves and never goes away. */}
          <span className="flex items-baseline gap-1.5">
            <span
              className={`font-serif text-lg leading-none tabular-nums ${timeTone(
                view.state.timeRemaining / view.timeBudget,
              )}`}
            >
              {view.state.timeRemaining}
            </span>
            <span className="text-[9px] tracking-[0.2em] text-neutral-600">
              HOURS LEFT
            </span>
          </span>
        </button>

        <div className={sheetOpen ? "contents" : "hidden md:contents"}>
          <Hud view={view} onRestart={onRestart} />
          {aside}
          {/* Pinned above the tabs where there is room for it. On a phone there
              is not: a five-line tutorial step plus the HUD fills the sheet and
              pushes the accusation form off the bottom, so down there the same
              panel is rendered inside the scrolling half instead. */}
          <div className="hidden md:contents">
            <TutorialPanel progress={tutorial} />
          </div>
        </div>

        <nav className="flex shrink-0 border-b border-neutral-800">
          {(
            [
              ["here", "HERE"],
              ["evidence", `EVIDENCE (${view.clues.length})`],
              ["accuse", "ACCUSE"],
            ] as Array<[Tab, string]>
          ).map(([id, label]) => (
            <button
              key={id}
              onClick={() => showPanel(id)}
              className={`flex-1 border-b-2 px-2 py-3.5 text-[10px] tracking-[0.2em] transition sm:py-3 ${
                tab === id
                  ? "border-amber-200/60 text-amber-100"
                  : "border-transparent text-neutral-600 hover:text-neutral-400"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        <div
          ref={panelRef}
          className={`min-h-0 flex-1 overflow-y-auto overscroll-contain ${
            sheetOpen ? "" : "hidden md:block"
          }`}
        >
          <div className="md:hidden">
            <TutorialPanel progress={tutorial} />
          </div>
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
    <ul className="pointer-events-none absolute bottom-3 left-3 right-3 z-[1000] max-w-md space-y-1.5 sm:bottom-6 sm:left-6 sm:right-6">
      {recent.map((entry, i) => (
        <li
          key={entry.seq}
          // The map pane is a third of a phone screen; four entries would bury
          // it. The older two are desktop-only.
          className={`border-l-2 border-neutral-700 bg-[#0e0f11]/95 py-1.5 pl-3 pr-4 backdrop-blur ${
            i < recent.length - 2 ? "hidden sm:block" : ""
          }`}
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
