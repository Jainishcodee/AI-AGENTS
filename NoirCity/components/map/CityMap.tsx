"use client";

import { useEffect, useRef } from "react";
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

export default function CityMap({
  city,
  visited,
  hereId = null,
  focusedId = null,
  onSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<CityCanvasLayer | null>(null);
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
      // Nothing exists outside the city, so do not let the user drift into the void.
      maxBounds: L.latLngBounds([-height * 0.15, -width * 0.15], [height * 1.15, width * 1.15]),
      maxBoundsViscosity: 0.9,
    });

    const bounds = L.latLngBounds([0, 0], [height, width]);
    const PAD = L.point(8, 8);

    // Backlund is far wider than it is tall, so the zoom that shows all of it
    // depends entirely on how wide the container is - a fixed floor that framed
    // the city on a desktop cropped both ends of it on a phone. Derive the
    // floor instead, and make it the limit: you can always see the whole city,
    // and you can never zoom out past it into the void.
    const fitZoom = () => map.getBoundsZoom(bounds, false, PAD);
    const fitCity = () => {
      map.setMinZoom(-8);
      map.fitBounds(bounds, { padding: [8, 8] });
      map.setMinZoom(fitZoom());
    };
    fitCity();

    // Whether the view is still the whole city rather than somewhere in it.
    // Re-derived from the zoom itself, so zooming back out to the floor puts
    // the map back under the resize handler's care.
    let showingAll = true;
    map.on("zoomend", () => {
      showingAll = map.getZoom() <= fitZoom() + 0.05;
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
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ pan: false });
      // A shorter container needs a wider view to hold the same city, so the
      // floor moves with it. Re-frame too, but only for someone who was looking
      // at the whole city - anyone zoomed into a street keeps their place
      // rather than being thrown back out every time the sheet moves.
      if (showingAll) fitCity();
      else map.setMinZoom(fitZoom());
    });
    observer.observe(container);

    mapRef.current = map;
    layerRef.current = layer;

    // Dev-only handle so end-to-end tests can convert city coordinates to screen
    // pixels and click a specific address. Stripped from production builds.
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __cityMap?: L.Map }).__cityMap = map;
    }

    return () => {
      observer.disconnect();
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

  return <div ref={containerRef} className="h-full w-full bg-[#0a0b0d]" />;
}
