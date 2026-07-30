"use client";

import { useMemo, useState } from "react";
import type { City, CityLocation } from "@/lib/engine/citySchema";
import type { Action } from "@/lib/engine/reducer";

/**
 * You travel by writing down an address and going there.
 *
 * This is the difference between the map being a menu and the map being a
 * reference. A clue says "Center 176" and you have to have been paying
 * attention; the map tells you which borough that is and what the trip will
 * cost, but it will not do the remembering for you.
 *
 * Resolution is client-side on purpose. The browser already has every address in
 * Backlund, so hiding the lookup would protect nothing — the puzzle is knowing
 * which address matters, not being unable to look one up.
 */

interface Match {
  location: CityLocation;
  /** Lower is better. */
  score: number;
}

function normalise(text: string) {
  return text.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
}

function search(city: City, query: string, limit = 6): Match[] {
  const q = normalise(query);
  if (q.length < 2) return [];

  const words = q.split(" ");
  const matches: Match[] = [];

  for (const location of city.locations) {
    const address = normalise(location.address);
    const name = normalise(location.name);

    let score: number | null = null;
    if (address === q) score = 0;
    else if (address.startsWith(q)) score = 1;
    else if (name === q) score = 2;
    else if (address.includes(q) || name.includes(q)) score = 3;
    else if (words.length > 1 && words.every((w) => address.includes(w) || name.includes(w))) {
      score = 4;
    }

    if (score !== null) matches.push({ location, score });
    if (matches.length > 400) break;
  }

  return matches
    .sort((a, b) => a.score - b.score || a.location.name.localeCompare(b.location.name))
    .slice(0, limit);
}

export function AddressBook({
  city,
  visitedIds,
  hereId,
  travelCostTo,
  act,
  busy,
}: {
  city: City;
  visitedIds: string[];
  hereId: string;
  travelCostTo: (id: string) => number;
  act: (a: Action) => void;
  busy: boolean;
}) {
  const [query, setQuery] = useState("");
  const matches = useMemo(() => search(city, query), [city, query]);

  const visited = useMemo(() => {
    const byId = new Map(city.locations.map((l) => [l.id, l]));
    return visitedIds
      .map((id) => byId.get(id))
      .filter((l): l is CityLocation => Boolean(l));
  }, [city, visitedIds]);

  return (
    <div className="space-y-6 px-5 py-5 sm:px-7">
      <section>
        <p className="text-[10px] tracking-[0.3em] text-neutral-600">
          WHERE TO
        </p>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="176 Cannon Yard"
          // 16px below sm, or focusing this zooms the page on iOS.
          className="mt-3 w-full border border-neutral-800 bg-transparent px-3 py-2.5 font-serif text-[16px] text-neutral-100 outline-none placeholder:text-neutral-700 focus:border-amber-200/40 sm:text-[15px]"
        />
        <p className="mt-2 text-[11px] leading-relaxed text-neutral-700">
          Write down addresses as you hear them. Nobody will hand you a list.
        </p>

        {query.length >= 2 && !matches.length && (
          <p className="mt-4 font-serif text-[13px] italic text-neutral-600">
            No such address in Backlund. Check what you wrote down.
          </p>
        )}

        <ul className="mt-4 space-y-1.5">
          {matches.map(({ location }) => {
            const cost = travelCostTo(location.id);
            const here = location.id === hereId;
            return (
              <li key={location.id}>
                <button
                  disabled={busy || here}
                  onClick={() => {
                    act({ type: "travel", locationId: location.id });
                    setQuery("");
                  }}
                  className="w-full border border-neutral-800 px-3 py-2.5 text-left transition hover:border-amber-200/40 disabled:opacity-40"
                >
                  <span className="block font-serif text-[14px] text-neutral-100">
                    {location.name}
                  </span>
                  <span className="mt-0.5 flex items-baseline justify-between gap-3">
                    <span className="text-[12px] text-neutral-500">
                      {location.address}
                    </span>
                    <span className="shrink-0 text-[10px] tracking-[0.15em] text-neutral-600">
                      {here ? "YOU ARE HERE" : `${cost}H`}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      {visited.length > 0 && (
        <section className="border-t border-neutral-800 pt-5">
          <p className="text-[10px] tracking-[0.3em] text-neutral-600">
            PLACES YOU HAVE BEEN
          </p>
          <ul className="mt-3 space-y-1">
            {visited.map((location) => {
              const cost = travelCostTo(location.id);
              const here = location.id === hereId;
              return (
                <li key={location.id}>
                  <button
                    disabled={busy || here}
                    onClick={() => act({ type: "travel", locationId: location.id })}
                    className="flex w-full items-baseline justify-between gap-3 py-1.5 text-left transition disabled:opacity-100"
                  >
                    <span
                      className={`font-serif text-[13px] ${here ? "text-amber-100" : "text-neutral-400 hover:text-neutral-200"}`}
                    >
                      {location.name}
                      <span className="ml-2 text-[11px] text-neutral-600">
                        {location.address}
                      </span>
                    </span>
                    <span className="shrink-0 text-[10px] tracking-[0.15em] text-neutral-700">
                      {here ? "HERE" : `${cost}H`}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
