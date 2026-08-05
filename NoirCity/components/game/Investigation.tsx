"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import dynamic from "next/dynamic";
import { useCity } from "@/lib/city/useCity";
import { indexCity, travelCost, type CityLocation } from "@/lib/engine/citySchema";
import type { Action } from "@/lib/engine/reducer";
import type { ClientView } from "@/lib/engine/view";
import type { TutorialProgress } from "@/lib/engine/tutorial";
import type { FeedEntry } from "@/lib/game/types";
import { Hud, useLocalCountdown } from "./Hud";
import { formatCountdown } from "@/lib/engine/storyClock";
import { TutorialPanel } from "./TutorialPanel";
import { Journal } from "./Journal";
import { AddressBook } from "./AddressBook";
import { HerePanel } from "./HerePanel";
import { EvidencePanel } from "./EvidencePanel";
import { AccusePanel } from "./AccusePanel";
import { Verdict } from "./Verdict";
import { Corkboard } from "./Corkboard";
import { CaseTabs, type Tab } from "./CaseTabs";
import { PlaceCard } from "./PlaceCard";
import { useBoard } from "@/lib/game/useBoard";

const CityMap = dynamic(() => import("@/components/map/CityMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-[11px] tracking-[0.3em] text-ghost">
      DEVELOPING PLATE...
    </div>
  ),
});

/**
 * The board. Identical whether one person is playing or six - the only
 * difference is where the snapshot comes from, so both callers hand it in.
 */
export function Investigation({
  view,
  tutorial,
  feed,
  now,
  sessionRemainingMs,
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
  now: { dateline: string; time: string; day: number };
  sessionRemainingMs: number;
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
  // The journal opens first: the case brief is its first entry, so a new player
  // starts by reading the job rather than staring at a map of a city they have
  // no reason to care about yet.
  const [tab, setTab] = useState<Tab>("journal");
  const [selected, setSelected] = useState<CityLocation | null>(null);
  // The card over the map. Separate from `selected` so dismissing the card
  // leaves the address still selected in the notebook and still lit on the map.
  const [cardOpen, setCardOpen] = useState(false);
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
    setCardOpen(false);
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

  // Somewhere counts as known once you have been there. The address book will
  // take you back without making you write the address down twice.
  const visitedIds = useMemo(() => {
    const seen = new Set<string>([hereId]);
    for (const entry of feed) {
      if (entry.kind === "travel") seen.add(entry.locationId);
    }
    return [...seen];
  }, [feed, hereId]);

  const travelCostTo = (id: string) =>
    index ? travelCost(index, hereId, id) : 0;


  function showPanel(next: Tab) {
    setTab(next);
    setSheetOpen(true);
  }

  // Picking a pin asks one question - what is this, and is it worth the drive -
  // so it opens a card on the map that answers exactly that. It deliberately
  // does not raise the notebook any more: you click a pin while comparing it
  // against the three others around it, and throwing a panel over the city mid
  // comparison was answering a question nobody asked.
  //
  // Stable identity matters here - this is a prop on the memoised map, and a
  // fresh closure every render would defeat the memo entirely.
  const pickLocation = useCallback((location: CityLocation) => {
    setSelected(location);
    setCardOpen(true);
  }, []);

  return (
    <main className="relative flex h-dvh flex-col overflow-hidden bg-ink text-muted md:block">
      {/*
        The city.

        On a desktop it is the entire screen and the notebook lies on top of it,
        so the map never changes size and the city is never cut down to whatever
        is left over beside a panel.

        On a phone it stays a pane above the sheet rather than behind it. An
        overlay there would cover the pin you just tapped to open the thing -
        the sheet is two thirds of a phone screen, and tapping an address to
        read about it must not hide the address.

        min-h-0 so the pane yields to the sheet instead of overflowing the
        column; a flex child defaults to min-height:auto and would not.
      */}
      <div className="relative min-h-0 flex-1 md:absolute md:inset-0">
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
          <div className="reveal absolute inset-x-3 top-3 z-[1100] max-h-[70dvh] max-w-lg overflow-y-auto border border-line bg-surface/95 p-5 backdrop-blur sm:inset-x-6 sm:top-6 sm:p-6">
            <p className="text-[10px] tracking-[0.3em] text-faint">THE JOB</p>
            <h2 className="mt-2 font-serif text-lg text-bright sm:text-xl">
              {view.title}
            </h2>
            <p className="mt-3 font-serif text-[14px] leading-relaxed text-muted">
              {view.brief}
            </p>
            <button
              onClick={() => setBriefOpen(false)}
              className="mt-5 border border-edge px-5 py-2.5 text-[11px] tracking-[0.2em] text-muted lift hover:border-muted hover:text-bright"
            >
              GET TO WORK
            </button>
          </div>
        )}

        {/* One cluster in the corner rather than a button pinned to each end.
            The right-hand end of a desktop screen now belongs to the notebook,
            and two controls that read as a pair should sit as one. */}
        <div className="absolute left-3 top-3 z-[1000] flex gap-2 sm:left-6 sm:top-6">
          {!briefOpen && (
            <button
              onClick={() => setBriefOpen(true)}
              className="border border-line bg-surface/85 px-3 py-2 text-[10px] tracking-[0.2em] text-faint backdrop-blur lift hover:border-edge hover:text-muted sm:py-1.5"
            >
              THE JOB
            </button>
          )}

          <button
            onClick={() => setBoardOpen(true)}
            className="border border-line bg-surface/85 px-3 py-2 text-[10px] tracking-[0.2em] text-muted backdrop-blur lift hover:border-edge hover:text-bright sm:px-4 sm:py-1.5"
          >
            THE BOARD
            {view.clues.length > 0 && (
              <span className="numeral ml-2 text-faint">{view.clues.length}</span>
            )}
          </button>
        </div>

        {cardOpen && selected && (
          <PlaceCard
            location={selected}
            onOpen={() => {
              setCardOpen(false);
              showPanel("here");
            }}
            onClose={() => setCardOpen(false)}
          />
        )}

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

      {/* The index tabs, stitched into the notebook's outer edge. Desktop only -
          on a phone they run across the top of the sheet instead, further down.
          Positioned a pixel inside the notebook so the active tab's fill covers
          the seam and the two read as one piece of card. */}
      <CaseTabs
        variant="rail"
        active={tab}
        onSelect={showPanel}
        evidenceCount={view.clues.length}
        // Centred on the notebook rather than hung from its top corner: tabs
        // level with the header read as part of the chrome, tabs level with the
        // middle read as stitched into the edge of the file.
        className="absolute top-1/2 z-[1210] hidden -translate-y-1/2 md:flex"
        style={{
          right: "calc(var(--notebook-w) + var(--notebook-inset) - 1px)",
        }}
      />

      {/* One element, two shapes.
          Desktop: a notebook lying on the map - inset from every edge so it
          reads as an object on a surface rather than a wall bolted to the side
          of the window, and translucent enough that the city stays present
          underneath it.
          Phone: a bottom sheet in flow, which is the right shape at that size
          and keeps the map above it usable. */}
      <aside
        className={`z-[1200] flex shrink-0 flex-col border-t border-line bg-surface md:absolute md:top-[var(--notebook-inset)] md:bottom-[var(--notebook-inset)] md:right-[var(--notebook-inset)] md:h-auto md:w-[var(--notebook-w)] md:overflow-hidden md:rounded-sm md:border md:border-edge md:bg-surface/92 md:shadow-[0_28px_70px_-20px_rgba(0,0,0,0.95)] md:backdrop-blur-md ${
          sheetOpen ? "h-[68dvh]" : "h-auto"
        }`}
      >
        <button
          type="button"
          onClick={() => setSheetOpen((v) => !v)}
          aria-expanded={sheetOpen}
          aria-label={sheetOpen ? "Collapse the case panel" : "Expand the case panel"}
          className="relative flex shrink-0 items-center justify-end border-b border-line px-5 pb-2.5 pt-4 md:hidden"
        >
          <span className="absolute left-1/2 top-2 h-1 w-10 -translate-x-1/2 rounded-full bg-ghost" />
          {/* Only while the sheet is folded. Raised, the HUD sits directly
              underneath this and carries the same two figures - printing the
              clock twice, a centimetre apart, reads as a bug rather than as
              emphasis. Folded, this is the only clock on the screen. */}
          {!sheetOpen && (
            <span className="flex items-baseline gap-2">
              <SheetClock
                remainingMs={sessionRemainingMs}
                frozen={view.state.status === "finished"}
              />
              <span className="text-[9px] tracking-[0.2em] text-faint">
                <span className="numeral">{view.state.timeRemaining}</span>H IN
                HAND
              </span>
            </span>
          )}
        </button>

        <div className={sheetOpen ? "contents" : "hidden md:contents"}>
          <Hud
            view={view}
            now={now}
            sessionRemainingMs={sessionRemainingMs}
            onRestart={onRestart}
          />
          {aside}
          {/* Pinned above the tabs where there is room for it. On a phone there
              is not: a five-line tutorial step plus the HUD fills the sheet and
              pushes the accusation form off the bottom, so down there the same
              panel is rendered inside the scrolling half instead. */}
          <div className="hidden md:contents">
            <TutorialPanel progress={tutorial} />
          </div>
        </div>

        {/* The phone's copy of the same four. Above `md` the rail outside the
            notebook does this job and this one is not rendered at all. */}
        <CaseTabs
          variant="row"
          active={tab}
          onSelect={showPanel}
          evidenceCount={view.clues.length}
          className="shrink-0 md:hidden"
        />

        <div
          ref={panelRef}
          className={`min-h-0 flex-1 overflow-y-auto overscroll-contain ${
            sheetOpen ? "" : "hidden md:block"
          }`}
        >
          <div className="md:hidden">
            <TutorialPanel progress={tutorial} />
          </div>
          {/* Keyed on the tab so the arrival animation restarts each time the
              section changes. Behaviour-neutral: every panel below is already
              conditionally rendered, so switching tabs already unmounts the one
              you left - the key adds nothing to throw away. */}
          <div key={tab} className="reveal">
          {tab === "journal" && (
            <Journal view={view} feed={feed} brief={now} />
          )}
          {tab === "here" && (
            <>
              {city && (
                <AddressBook
                  city={city}
                  visitedIds={visitedIds}
                  hereId={hereId}
                  travelCostTo={travelCostTo}
                  act={act}
                  busy={busy}
                />
              )}
              <HerePanel
                view={view}
                selected={selected}
                travelCost={cost}
                feed={feed}
                act={act}
                busy={busy}
              />
            </>
          )}
          {tab === "evidence" && <EvidencePanel view={view} act={act} busy={busy} />}
          {tab === "accuse" && <AccusePanel view={view} act={act} busy={busy} />}
          </div>
        </div>
      </aside>

      {view.state.status === "finished" && (
        <Verdict view={view} onRestart={onRestart} />
      )}
    </main>
  );
}

/**
 * The clock on the folded phone sheet.
 *
 * A leaf of its own so that ticking it re-renders one span rather than the whole
 * screen. Held at the top level it re-rendered the map once a second for the
 * entire session, which is both wasteful and makes profiling anything else
 * impossible.
 */
function SheetClock({
  remainingMs,
  frozen,
}: {
  remainingMs: number;
  frozen: boolean;
}) {
  const remaining = useLocalCountdown(remainingMs, frozen);
  return (
    <span className="numeral text-base leading-none text-bright">
      {frozen ? "--:--:--" : formatCountdown(remaining)}
    </span>
  );
}

/**
 * One line, for when you are looking at the map rather than the journal. The
 * journal is the record now, so repeating four entries here just says the same
 * thing twice in two places.
 */
function ActionFeed({ feed }: { feed: FeedEntry[] }) {
  const recent = feed.slice(-1);
  if (!recent.length) return null;

  return (
    <ul className="pointer-events-none absolute bottom-3 left-3 right-3 z-[1000] max-w-md space-y-1.5 sm:bottom-6 sm:left-6 sm:right-6">
      {recent.map((entry) => (
        <li
          key={entry.seq}
          // Gold's second permitted use, and it is conditional: the edge lights
          // up only when the action actually turned something up. Most actions
          // do not, so the colour stays rare enough to be worth looking at.
          className={`reveal border-l-2 bg-surface/95 py-1.5 pl-3 pr-4 backdrop-blur ${
            entry.newClues.length ? "border-gold" : "border-line"
          }`}
        >
          <span className="font-serif text-[13px] text-muted">
            {entry.summary}
          </span>
          {entry.timeSpent > 0 && (
            <span className="ml-2 text-[10px] tracking-widest text-faint">
              &minus;<span className="numeral">{entry.timeSpent}</span>H
            </span>
          )}
          {entry.newClues.map((c) => (
            <span key={c.id} className="mt-0.5 block text-[12px] text-gold">
              + {c.title}
            </span>
          ))}
        </li>
      ))}
    </ul>
  );
}
