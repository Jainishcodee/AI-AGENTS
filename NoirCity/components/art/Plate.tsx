"use client";

import { useState } from "react";
import {
  plateExists,
  plateLook,
  platePath,
  plateSeed,
  type PlateKind,
} from "@/lib/art/plates";

/**
 * An illustration, or a convincing stand-in for one.
 *
 * If `public/art/<kind>s/<id>.webp` exists it is shown, graded to match the rest
 * of the game. If it does not - and today most do not - a deterministic noir
 * plate is drawn from the id instead: duotone, a motif, and grain.
 *
 * The point is that the game is finished and shippable with no artwork at all,
 * and every image can be added later by dropping a file in. A missing plate
 * never looks like a bug.
 */
export function Plate({
  kind,
  id,
  alt,
  className = "",
  ratio = "aspect-[3/2]",
}: {
  kind: PlateKind;
  id: string;
  alt: string;
  className?: string;
  ratio?: string;
}) {
  // `failed` still matters: the manifest can go stale against a deploy, and a
  // plate that vanishes should fall back rather than leave a hole.
  const [failed, setFailed] = useState(!plateExists(kind, id));
  const look = plateLook(id);
  const seed = plateSeed(id);

  return (
    <div
      className={`relative overflow-hidden bg-ink ${ratio} ${className}`}
      role="img"
      aria-label={alt}
    >
      {!failed && (
        // eslint-disable-next-line @next/next/no-img-element -- static art on a
        // CDN with known dimensions; the optimiser adds a Worker round trip for
        // no benefit.
        <img
          src={platePath(kind, id)}
          alt={alt}
          onError={() => setFailed(true)}
          className="absolute inset-0 h-full w-full object-cover"
          loading="lazy"
        />
      )}

      {failed && <ProceduralPlate look={look} seed={seed} />}

      {/* Grain and a vignette sit over both, so a real photograph and a drawn
          fallback end up in the same world. */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.16] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_35%,rgba(0,0,0,0.55)_100%)]" />
    </div>
  );
}

function ProceduralPlate({
  look,
  seed,
}: {
  look: ReturnType<typeof plateLook>;
  seed: number;
}) {
  return (
    <div
      className="absolute inset-0"
      style={{
        background: `linear-gradient(${look.angle}deg, ${look.from} 0%, ${look.to} 82%)`,
      }}
    >
      {look.motif === "blinds" && (
        <div
          className="absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              "repeating-linear-gradient(0deg, rgba(0,0,0,0.92) 0px, rgba(0,0,0,0.92) 9px, transparent 9px, transparent 22px)",
            transform: `rotate(${(seed % 9) - 4}deg) scale(1.3)`,
          }}
        />
      )}

      {look.motif === "lamp" && (
        <div
          className="absolute inset-0"
          style={{
            background: `radial-gradient(circle at ${18 + (seed % 60)}% ${14 + ((seed >> 5) % 40)}%, rgba(255,220,165,0.55) 0%, rgba(255,200,140,0.16) 28%, transparent 58%)`,
          }}
        />
      )}

      {look.motif === "haze" && (
        <div
          className="absolute inset-0"
          style={{
            background: `linear-gradient(${look.angle + 90}deg, transparent 0%, rgba(215,225,235,0.30) 42%, transparent 74%)`,
          }}
        />
      )}
    </div>
  );
}
