"use client";

import type { CityLocation } from "@/lib/engine/citySchema";
import { Plate } from "@/components/art/Plate";

/**
 * What you get when you click an address on the map: a look at the place, and
 * its name.
 *
 * Nothing else. A card over the map is answering "what is this?" while you are
 * still looking at the street it stands on - the hours, the blurb, the search
 * and the interviews all belong in the notebook, where there is room to read
 * them and where you are no longer comparing this address against its
 * neighbours. Anything more here is a second panel competing with the first.
 *
 * The whole card opens the file, so getting to those things is one click and
 * there is no button to hunt for.
 */
export function PlaceCard({
  location,
  onOpen,
  onClose,
}: {
  location: CityLocation;
  /** Show the full entry in the notebook. */
  onOpen: () => void;
  onClose: () => void;
}) {
  return (
    <div
      data-testid="place-card"
      className="reveal absolute bottom-3 left-3 z-[1150] w-[220px] border border-edge bg-surface/95 shadow-[0_18px_50px_-16px_rgba(0,0,0,0.95)] backdrop-blur-md sm:bottom-6 sm:left-6 sm:w-[240px]"
    >
      <button
        onClick={onClose}
        aria-label="Close"
        className="absolute right-0 top-0 z-10 flex h-8 w-8 items-center justify-center bg-ink/60 text-[15px] leading-none text-muted lift hover:text-bright"
      >
        ×
      </button>

      <button onClick={onOpen} className="block w-full text-left">
        <Plate
          kind="scene"
          id={location.id}
          alt={location.name}
          ratio="aspect-[4/3]"
        />
        <p className="px-3.5 py-3 font-serif text-[14px] leading-tight text-bright">
          {location.name}
        </p>
      </button>
    </div>
  );
}
