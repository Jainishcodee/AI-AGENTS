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
    if (!containerRef.current || mapRef.current) return;

    const [width, height] = city.size;
    const map = L.map(containerRef.current, {
      crs: L.CRS.Simple,
      minZoom: -3.5,
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
    map.fitBounds(bounds, { padding: [8, 8] });

    const layer = new CityCanvasLayer(city);
    layer.addTo(map);

    map.on("click", (e: L.LeafletMouseEvent) => {
      const hit = hitTest(city, map, e.containerPoint);
      if (hit) onSelectRef.current?.(hit);
    });

    // Leaflet has no notion of our canvas pins, so the cursor has to be driven
    // off the same hit test the click uses.
    map.on("mousemove", (e: L.LeafletMouseEvent) => {
      const hit = hitTest(city, map, e.containerPoint);
      map.getContainer().style.cursor = hit ? "pointer" : "grab";
    });

    mapRef.current = map;
    layerRef.current = layer;

    // Dev-only handle so end-to-end tests can convert city coordinates to screen
    // pixels and click a specific address. Stripped from production builds.
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __cityMap?: L.Map }).__cityMap = map;
    }

    return () => {
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
