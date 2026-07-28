"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCity } from "@/lib/city/useCity";
import { useGame } from "@/lib/game/useGame";
import { indexCity, travelCost, type CityLocation } from "@/lib/engine/citySchema";
import { Hud } from "@/components/game/Hud";
import { TutorialPanel } from "@/components/game/TutorialPanel";
import { HerePanel } from "@/components/game/HerePanel";
import { EvidencePanel } from "@/components/game/EvidencePanel";
import { AccusePanel } from "@/components/game/AccusePanel";
import { Verdict } from "@/components/game/Verdict";

const CityMap = dynamic(() => import("@/components/map/CityMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-[11px] tracking-[0.3em] text-neutral-700">
      DEVELOPING PLATE...
    </div>
  ),
});

type Tab = "here" | "evidence" | "accuse";

export function GameScreen({ caseId }: { caseId: string }) {
  const { city } = useCity();
  const { snapshot, refusal, loading, fatal, act, restart } = useGame(caseId);
  const [tab, setTab] = useState<Tab>("here");
  const [selected, setSelected] = useState<CityLocation | null>(null);
  const [briefOpen, setBriefOpen] = useState(true);

  const index = useMemo(() => (city ? indexCity(city) : null), [city]);

  // Travelling makes the old selection stale; clear it so the panel snaps back
  // to wherever the team actually is.
  const hereId = snapshot?.view.here.id;
  useEffect(() => {
    setSelected(null);
  }, [hereId]);

  const visited = useMemo(
    () => new Set(Object.keys(snapshot?.view.state.searchCounts ?? {})),
    [snapshot],
  );

  if (fatal) {
    return (
      <main className="flex h-dvh flex-col items-center justify-center gap-4 bg-[#08090b] text-neutral-400">
        <p>{fatal}</p>
        <Link href="/" className="text-[11px] tracking-[0.2em] text-neutral-600 hover:text-neutral-300">
          BACK TO THE CASE FILES
        </Link>
      </main>
    );
  }

  if (loading || !snapshot) {
    return (
      <main className="flex h-dvh items-center justify-center bg-[#08090b] text-[11px] tracking-[0.3em] text-neutral-700">
        OPENING THE FILE...
      </main>
    );
  }

  const { view, tutorial, feed } = snapshot;
  const cost =
    index && selected ? travelCost(index, view.here.id, selected.id) : 0;

  return (
    <main className="relative flex h-dvh bg-[#08090b] text-neutral-300">
      <div className="relative flex-1">
        {city && (
          <CityMap
            city={city}
            visited={visited}
            hereId={view.here.id}
            focusedId={selected?.id ?? null}
            onSelect={setSelected}
          />
        )}

        {briefOpen && (
          <div className="absolute inset-x-6 top-6 z-[1000] max-w-lg border border-neutral-800 bg-[#0e0f11]/95 p-6 backdrop-blur">
            <p className="text-[10px] tracking-[0.3em] text-amber-200/60">
              THE JOB
            </p>
            <h2 className="mt-2 font-serif text-xl text-neutral-100">
              {view.title}
            </h2>
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

        {refusal && (
          <p className="absolute bottom-6 left-1/2 z-[1000] -translate-x-1/2 border border-red-900/50 bg-[#0e0f11]/95 px-5 py-2.5 font-serif text-[13px] text-red-300 backdrop-blur">
            {refusal}
          </p>
        )}

        <ActionFeed feed={feed} />
      </div>

      <aside className="flex w-[400px] shrink-0 flex-col border-l border-neutral-800 bg-[#0e0f11]">
        <Hud view={view} onRestart={restart} />
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
              busy={false}
            />
          )}
          {tab === "evidence" && (
            <EvidencePanel view={view} act={act} busy={false} />
          )}
          {tab === "accuse" && (
            <AccusePanel view={view} act={act} busy={false} />
          )}
        </div>
      </aside>

      {view.state.status === "finished" && (
        <Verdict view={view} onRestart={restart} />
      )}
    </main>
  );
}

/** The last few things that happened, so a team can see what just changed. */
function ActionFeed({ feed }: { feed: Array<{ seq: number; summary: string; timeSpent: number; newClues: Array<{ id: string; title: string }> }> }) {
  const recent = feed.slice(-4);
  if (!recent.length) return null;

  return (
    <ul className="pointer-events-none absolute bottom-6 left-6 z-[1000] max-w-md space-y-1.5">
      {recent.map((entry, i) => (
        <li
          key={entry.seq}
          className="border-l-2 border-neutral-700 bg-[#0e0f11]/85 py-1.5 pl-3 pr-4 backdrop-blur"
          style={{ opacity: 0.35 + (i / recent.length) * 0.65 }}
        >
          <span className="font-serif text-[13px] text-neutral-300">
            {entry.summary}
          </span>
          {entry.timeSpent > 0 && (
            <span className="ml-2 text-[10px] tracking-widest text-neutral-600">
              −{entry.timeSpent}H
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
