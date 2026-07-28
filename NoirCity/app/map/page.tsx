"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCity } from "@/lib/city/useCity";
import { indexCity, travelCost, type CityLocation } from "@/lib/engine/citySchema";

/**
 * The city with no case running - useful for finding your way around Backlund,
 * and for checking the map renderer without starting an investigation.
 */
const CityMap = dynamic(() => import("@/components/map/CityMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-[11px] tracking-[0.3em] text-neutral-700">
      DEVELOPING PLATE...
    </div>
  ),
});

/** The detective's own office. Where every case starts. */
const HOME_OFFICE = "loc_lm_blackthorn_security_company";

export default function MapPage() {
  const { city, error } = useCity();
  const [selected, setSelected] = useState<CityLocation | null>(null);
  const [hereId, setHereId] = useState<string | null>(null);
  const [visited, setVisited] = useState<Set<string>>(new Set());

  const index = useMemo(() => (city ? indexCity(city) : null), [city]);

  // Travel costs are meaningless without somewhere to travel from.
  useEffect(() => {
    if (city && !hereId) {
      setHereId(HOME_OFFICE);
      setVisited(new Set([HOME_OFFICE]));
    }
  }, [city, hereId]);

  const cost = index && selected ? travelCost(index, hereId, selected.id) : 0;
  const here = index && hereId ? index.locations.get(hereId) : null;
  const borough = index && selected ? index.boroughs.get(selected.boroughId) : null;
  const hereBorough = index && here ? index.boroughs.get(here.boroughId) : null;

  if (error) {
    return (
      <main className="flex h-dvh items-center justify-center bg-[#08090b] text-red-400">
        Could not load the city: {error}
      </main>
    );
  }

  return (
    <main className="flex h-dvh bg-[#08090b] text-neutral-300">
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
        <div className="absolute left-6 top-6 z-[1000] select-none">
          <h1 className="font-serif text-2xl tracking-[0.35em] text-neutral-200">
            BACKLUND
          </h1>
          <p className="mt-1 text-[11px] tracking-[0.2em] text-neutral-600">
            {city ? city.locations.length : "—"} LOCATIONS &middot;{" "}
            {city?.boroughs.length ?? "—"}&nbsp;BOROUGHS &middot; THE TUSSOCK
          </p>
          <Link
            href="/"
            className="mt-3 inline-block text-[10px] tracking-[0.2em] text-neutral-600 transition hover:text-amber-100"
          >
            &larr; THE CASE FILES
          </Link>
        </div>
      </div>

      <aside className="w-[360px] shrink-0 overflow-y-auto border-l border-neutral-800 bg-[#0e0f11] p-7">
        {!selected && (
          <p className="font-serif text-[15px] leading-relaxed text-neutral-500">
            Click anywhere on the map. Gold pins are ordinary addresses; red ones
            are the places everybody in this city has heard of.
          </p>
        )}

        {selected && (
          <div>
            <p className="text-[10px] tracking-[0.25em] text-neutral-600">
              {selected.type.toUpperCase()}
              {selected.isLandmark && " · LANDMARK"}
            </p>
            <h2 className="mt-2 font-serif text-xl leading-tight text-neutral-100">
              {selected.name}
            </h2>
            <p className="mt-1 text-sm text-neutral-500">{selected.address}</p>
            <p className="mt-1 text-xs tracking-wider text-neutral-600">
              {borough?.name} &middot;{" "}
              {borough?.bank === "north" ? "North bank" : "South bank"}
            </p>

            <p className="mt-5 font-serif text-[15px] leading-relaxed text-neutral-400">
              {selected.blurb}
            </p>

            <div className="mt-7 border-t border-neutral-800 pt-5">
              {hereId === selected.id ? (
                <p className="text-xs tracking-[0.2em] text-amber-200/80">
                  YOU ARE HERE
                </p>
              ) : (
                <>
                  <button
                    onClick={() => {
                      setHereId(selected.id);
                      setVisited((prev) => new Set(prev).add(selected.id));
                    }}
                    className="w-full border border-neutral-700 px-4 py-2.5 text-xs tracking-[0.2em] text-neutral-300 transition hover:border-amber-200/50 hover:text-amber-100"
                  >
                    DRIVE OVER &mdash; {cost} {cost === 1 ? "HOUR" : "HOURS"}
                  </button>
                  {here && (
                    <p className="mt-3 text-[11px] leading-relaxed text-neutral-600">
                      From {here.name}.{" "}
                      {hereBorough?.bank !== borough?.bank
                        ? "Crossing the Tussock costs an extra hour."
                        : "Same side of the river."}
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </aside>
    </main>
  );
}
