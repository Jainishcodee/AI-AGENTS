"use client";

import { memo, useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { City, CityLocation } from "@/lib/engine/citySchema";
import { CityCanvasLayer, hitTest, type CityLayerState } from "./CityCanvasLayer";

interface Props {
  city: City;
  visited?: Set<string>;
  hereId?: string | null;
  focusedId?: string | null;
  onSelect?: (location: CityLocation) => void;
}

function CityMapImpl({
  city,
  visited,
  hereId = null,
  focusedId = null,
  onSelect,
}: Props) {
  // Dev-only render counter. The map is the most expensive thing on the page,
  // so "did a clock tick just re-render it" needs to be answerable rather than
  // argued about. Stripped from production builds.
  if (process.env.NODE_ENV !== "production" && typeof window !== "undefined") {
    const w = window as unknown as { __cityMapRenders?: number };
    w.__cityMapRenders = (w.__cityMapRenders ?? 0) + 1;
  }

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<CityCanvasLayer | null>(null);
  // See the probe element at the bottom of this file.
  const reserveRef = useRef<HTMLDivElement>(null);
  // Kept in a ref so changing the handler never tears down the map.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    const [width, height] = city.size;
    const map = L.map(container, {
      crs: L.CRS.Simple,
      // Deliberately permissive: the real floor is worked out from the
      // container below, once there is a container to measure.
      minZoom: -8,
      maxZoom: 1.5,
      // Free-floating zoom, so fitBounds lands on an exact fit instead of
      // rounding down to the next step and leaving dead margin.
      zoomSnap: 0,
      zoomDelta: 0.4,
      wheelPxPerZoomLevel: 140,
      attributionControl: false,
      zoomControl: false,
      // Nothing exists outside the city, so do not let the user drift into the
      // void. The actual clamp is set in `fitCity` once we know what we framed.
      maxBoundsViscosity: 0.9,
    });

    const bounds = L.latLngBounds([0, 0], [height, width]);
    const EDGE = 8;
    // Wide enough to be no constraint at all. `setMaxBounds` cannot be given a
    // null to mean "unclamped", so this stands in for one while re-framing.
    const UNCLAMPED = L.latLngBounds(
      [-height * 4, -width * 4],
      [height * 5, width * 5],
    );

    /**
     * How much of the right-hand side the notebook is sitting on.
     *
     * The map is full-bleed under the notebook, which is what makes the city
     * carry on behind it instead of stopping at a panel edge - but the city
     * itself has to stay in the part you can still reach, or the addresses
     * under the notebook are unclickable.
     *
     * Read off a probe element rather than hard-coded, so this stays correct
     * when the notebook is resized and correct at every breakpoint, including
     * the phone where the notebook is not an overlay at all and this is 0.
     */
    const reserved = () => reserveRef.current?.offsetWidth ?? 0;

    // Backlund is far wider than it is tall, so the zoom that shows all of it
    // depends entirely on how wide the container is - a fixed floor that framed
    // the city on a desktop cropped both ends of it on a phone. Derive the
    // floor instead, and make it the limit: you can always see the whole city,
    // and you can never zoom out past it into the void.
    // Leaflet subtracts this as a total, not per side, so it has to match the
    // sum of what `fitCity` pads with or the floor and the fit disagree and the
    // city jumps a fraction of a zoom level every re-fit.
    const fitZoom = () =>
      map.getBoundsZoom(bounds, false, L.point(EDGE * 2 + reserved(), EDGE * 2));
    // `animate: false` is load-bearing during a resize. Animated, fitBounds
    // fires `zoomanim` on every frame of the transition, and each one re-enters
    // the layer's reposition - which is how one panel toggle turned into sixty
    // repaints fighting each other.
    /**
     * Whether we are still showing the frame we chose, as opposed to somewhere
     * the player has gone deliberately. It decides whether a layout change is
     * allowed to re-frame the map or has to leave the view where it is.
     *
     * This used to be derived by comparing the current zoom against `fitZoom()`,
     * which is wrong the moment `fitZoom()` itself moves - and it moves whenever
     * the notebook's footprint changes. After a first fit measured before the
     * stylesheet landed, every later comparison read "the player has zoomed in",
     * so the map refused to re-frame and left a third of the city permanently
     * under the notebook. Recording intent is not comparable to a moving target.
     */
    let framed = true;
    let refitting = false;

    const fitCity = (animate = false) => {
      refitting = true;
      map.setMinZoom(-8);
      // The clamp has to come off first. Framing the city clear of the notebook
      // means deliberately leaving empty space on the right, and a maxBounds
      // drawn round the city alone calls that space illegal - Leaflet then
      // recentres on moveend and silently undoes the offset, which looks exactly
      // like the padding having no effect at all.
      map.setMaxBounds(UNCLAMPED);
      map.fitBounds(bounds, {
        paddingTopLeft: [EDGE, EDGE],
        paddingBottomRight: [EDGE + reserved(), EDGE],
        animate,
      });
      map.setMinZoom(fitZoom());
      // Now clamp to what we actually framed - the city, plus whatever void the
      // notebook is sitting on. This is the most zoomed-out the map can get, so
      // it bounds every closer view too.
      map.setMaxBounds(map.getBounds().pad(0.02).extend(bounds));
      refitting = false;
      framed = true;
    };

    /**
     * The zoom that shows roughly a district across the part of the map you can
     * actually reach. Derived from the usable width rather than fixed, so a
     * phone and a wide desktop open on the same amount of *city* instead of the
     * same amount of pixels.
     *
     * Never below the fit: on a container too small to hold a district, the
     * whole city is what you get.
     */
    const OPEN_METRES = 1600;
    const openZoom = () => {
      const usable = Math.max(240, map.getSize().x - reserved());
      // CRS.Simple puts one city metre on 2^zoom pixels, so the zoom that fits
      // OPEN_METRES across `usable` is just the log of the ratio.
      const wanted = Math.log2(usable / OPEN_METRES);
      return Math.max(fitZoom(), Math.min(map.getMaxZoom(), wanted));
    };

    /**
     * Where the map starts.
     *
     * `fitCity` first, because it is what establishes the zoom floor and the
     * pan clamp, and both have to be right before anything moves. Then in to
     * the team's own doorstep.
     *
     * Opening on the whole city looked deliberate and read as useless: at that
     * scale Backlund is a grey web of twelve hundred identical dots, no address
     * is legible, and on a phone the city is a 300px band with black above and
     * below it. You are a detective standing somewhere specific, so the map
     * opens where you are standing. The whole city is still one pinch away, and
     * the floor guarantees you can always get back to it.
     */
    const openHere = () => {
      fitCity();
      const at = hereId ? city.locations.find((l) => l.id === hereId) : null;
      if (!at) return;
      refitting = true;
      // Offset so the team sits in the middle of the *usable* width, not behind
      // the notebook - `setView` centres on the container, which is wider.
      const z = openZoom();
      const point = map.project([at.y, at.x], z).add([reserved() / 2, 0]);
      map.setView(map.unproject(point, z), z, { animate: false });
      refitting = false;
      // Deliberately not `framed`: this is a chosen place, not the default
      // frame, so a later resize must keep it rather than throw you back out.
      framed = false;
    };
    openHere();

    // Anything the player does to the view is theirs to keep; anything we do
    // ourselves is still ours. Both fire the same events, so the difference has
    // to be recorded rather than inferred.
    map.on("zoomend", () => {
      if (!refitting) framed = false;
    });
    map.on("dragend", () => {
      framed = false;
    });

    const layer = new CityCanvasLayer(city);
    layer.addTo(map);

    // A fingertip is not a mouse pointer. Widening the catch radius on touch is
    // the difference between picking an address and picking the river.
    const coarse =
      typeof window !== "undefined" &&
      window.matchMedia?.("(pointer: coarse)").matches;

    map.on("click", (e: L.LeafletMouseEvent) => {
      const hit = hitTest(city, map, e.containerPoint, coarse ? 26 : 16);
      if (hit) onSelectRef.current?.(hit);
    });

    // Leaflet has no notion of our canvas pins, so the cursor has to be driven
    // off the same hit test the click uses.
    map.on("mousemove", (e: L.LeafletMouseEvent) => {
      const hit = hitTest(city, map, e.containerPoint);
      map.getContainer().style.cursor = hit ? "pointer" : "grab";
    });

    // Leaflet only watches the window, so raising the phone sheet - which
    // resizes the map's container but not the window - would otherwise leave
    // the canvas the wrong size and every pin's hit box offset from its pin.
    // A CSS transition fires this on every frame. Coalescing into a single rAF
    // turns sixty re-fits into one, and the map settles at the end of the
    // transition instead of chasing it.
    let pending = 0;
    const observer = new ResizeObserver(() => {
      if (pending) return;
      pending = requestAnimationFrame(() => {
        pending = 0;
        // Re-fitting is several operations, each firing events that ask the
        // layer to draw. Mid-sequence the view is inconsistent and a draw would
        // put the whole city off-screen. Hold the picture across the lot, then
        // release for exactly one correct frame.
        layer.hold();
        try {
          map.invalidateSize({ pan: false, animate: false });
          // A shorter container needs a wider view to hold the same city, so the
          // floor and the pan clamp move with it. Re-frame too, but only for
          // someone who was looking at the frame we chose - anyone who has gone
          // to a street keeps their place rather than being thrown back out
          // every time the sheet moves.
          if (framed) {
            fitCity();
          } else {
            // Both the floor and the clamp are side effects of fitting, and
            // both are now wrong. Fit to recompute them, then put the player
            // back exactly where they were - all inside the same held frame, so
            // none of it is ever drawn.
            const centre = map.getCenter();
            const zoom = map.getZoom();
            fitCity();
            refitting = true;
            map.setView(centre, zoom, { animate: false });
            refitting = false;
            framed = false;
          }
        } finally {
          layer.release();
        }
      });
    });
    observer.observe(container);
    // The probe too, and this is not belt-and-braces.
    //
    // The container is a fixed full-bleed box, so it never resizes on its own -
    // but how much of it the notebook is sitting on very much does. It changes
    // when the viewport crosses `md` in either direction, and it changes once
    // more on first load: the effect runs before the stylesheet has necessarily
    // applied, so the very first measurement can be 0 and the city gets framed
    // to the whole window with a third of it under the notebook. Watching the
    // probe means that 0 corrects itself the moment the styles land.
    if (reserveRef.current) observer.observe(reserveRef.current);

    mapRef.current = map;
    layerRef.current = layer;

    // Dev-only handle so end-to-end tests can convert city coordinates to screen
    // pixels and click a specific address. Stripped from production builds.
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __cityMap?: L.Map }).__cityMap = map;
    }

    return () => {
      observer.disconnect();
      if (pending) cancelAnimationFrame(pending);
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, [city]);

  useEffect(() => {
    layerRef.current?.setState({
      visited: visited ?? new Set<string>(),
      hereId,
      focusedId,
    } satisfies CityLayerState);
  }, [visited, hereId, focusedId]);

  // A slow ring around wherever the team is standing. Leaflet keeps a marker in
  // the right place on its own as you pan and zoom, and the ring itself is a CSS
  // animation on the compositor - so the one thing that moves on this map costs
  // neither a React render nor a canvas redraw. See `.here-pulse`.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const at = hereId ? city.locations.find((l) => l.id === hereId) : null;
    if (!at) return;

    const marker = L.marker([at.y, at.x], {
      // Purely decorative: clicks belong to the canvas hit test underneath,
      // and a marker that ate them would make your own address unselectable.
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: "",
        html: '<span class="here-pulse"></span>',
        iconSize: [0, 0],
      }),
    }).addTo(map);

    return () => {
      marker.remove();
    };
  }, [city, hereId]);

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full bg-ink" />
      {/*
        A probe, not a spacer. It draws nothing and catches nothing; it exists
        so the map can ask the stylesheet how wide the notebook's footprint is
        at the current breakpoint, instead of being handed a number that has to
        be kept in step with the CSS by hand.

        `--notebook-clear` is a calc() over rem and px, so reading the custom
        property as a string would not give a usable figure - laying it out and
        reading `offsetWidth` does. Below `md` the class does not apply and this
        measures 0, which is exactly right: down there the notebook is a sheet
        below the map, not something sitting on top of it.
      */}
      <div
        ref={reserveRef}
        aria-hidden="true"
        className="pointer-events-none invisible absolute left-0 top-0 h-0 md:w-[var(--notebook-clear)]"
      />
    </div>
  );
}

/**
 * Memoised because the map is the most expensive thing on the page and the least
 * often genuinely changed. `onSelect` is held in a ref inside, so an unstable
 * handler from a parent cannot force a re-render either.
 */
export default memo(CityMapImpl);
