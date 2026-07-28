"use client";

import { useEffect, useState } from "react";
import { parseCity, type City } from "@/lib/engine/citySchema";

/**
 * Fetches public/city.json once per page load. It is half a megabyte of static
 * geometry, so it stays out of the JS bundle and rides the browser cache.
 */
let cached: City | null = null;
let inflight: Promise<City> | null = null;

export function loadCity(): Promise<City> {
  if (cached) return Promise.resolve(cached);
  if (!inflight) {
    inflight = fetch("/city.json")
      .then((r) => {
        if (!r.ok) throw new Error(`city.json: ${r.status}`);
        return r.json();
      })
      .then((raw) => {
        cached = parseCity(raw);
        return cached;
      })
      .catch((err) => {
        inflight = null;
        throw err;
      });
  }
  return inflight;
}

export function useCity() {
  const [city, setCity] = useState<City | null>(cached);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cached) return;
    let alive = true;
    loadCity()
      .then((c) => alive && setCity(c))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, []);

  return { city, error };
}
