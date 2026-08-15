"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * The way in.
 *
 * Fog off the Ebb, a lamp catching, and the city's name resolving out of the
 * dark. Roughly five seconds, skippable at any point, and shown once.
 *
 * Built from a canvas and two CSS animations rather than a video file, and that
 * is a deliberate trade. A video would be sharper, but it is also five to ten
 * megabytes served on every cold visit, a decode on a phone that may not have
 * the headroom, and a black rectangle for anybody whose connection stalls. This
 * weighs nothing, starts on the first frame, and cannot fail to load. If a real
 * film is ever made, this stays as its poster and its fallback.
 *
 * Nothing here is on the critical path: the study is rendered underneath the
 * whole time, so a player who skips is not waiting for anything to start.
 */

/** Remembered so a returning player is not made to sit through it again. */
const SEEN_KEY = "noircity:intro-seen";

/** Beat boundaries in milliseconds. The whole thing is `END`. */
const FOG_IN = 900;
const LAMP_IN = 2600;
const TITLE_IN = 3100;
const END = 6200;

export function IntroSequence({ onDone }: { onDone: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const doneRef = useRef(false);
  const [beat, setBeat] = useState(0);

  const finish = useCallback(() => {
    if (doneRef.current) return;
    doneRef.current = true;
    try {
      window.localStorage.setItem(SEEN_KEY, "1");
    } catch {
      // Private browsing refuses storage. Showing the intro twice is a far
      // smaller problem than throwing on the way into the game.
    }
    onDone();
  }, [onDone]);

  // Any input at all ends it. Somebody reaching for the skip button has already
  // told you what they want, so a stray click should not be ignored on the way.
  useEffect(() => {
    const skip = () => finish();
    window.addEventListener("pointerdown", skip);
    window.addEventListener("keydown", skip);
    return () => {
      window.removeEventListener("pointerdown", skip);
      window.removeEventListener("keydown", skip);
    };
  }, [finish]);

  useEffect(() => {
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    // Asked not to animate: show the last frame, hold it briefly so the title
    // can actually be read, and move on. Never a blank screen.
    if (reduced) {
      setBeat(3);
      const id = setTimeout(finish, 1400);
      return () => clearTimeout(id);
    }

    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) {
      const id = setTimeout(finish, END);
      return () => clearTimeout(id);
    }

    let frame = 0;
    const started = performance.now();

    /**
     * Fog, as a handful of big soft discs drifting at different speeds.
     *
     * Not noise and not a texture: at this scale and this alpha the eye reads
     * overlapping gradients as fog perfectly well, and it costs a dozen fills a
     * frame instead of a per-pixel pass.
     */
    const BLOBS = Array.from({ length: 9 }, (_, i) => ({
      // Spread across the width, biased low - fog sits on the water.
      x: (i + 0.5) / 9,
      y: 0.55 + (i % 3) * 0.14,
      r: 0.22 + (i % 4) * 0.06,
      speed: 0.006 + (i % 5) * 0.0035,
      phase: i * 1.7,
    }));

    const draw = (now: number) => {
      const t = now - started;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      ctx.fillStyle = "#08090b";
      ctx.fillRect(0, 0, w, h);

      const fog = Math.min(1, Math.max(0, (t - FOG_IN) / 1600));
      const lamp = Math.min(1, Math.max(0, (t - LAMP_IN) / 1500));

      // The lamp, under the fog, so the fog is lit from within rather than laid
      // over the top of a glow.
      if (lamp > 0) {
        const lx = w * 0.5;
        const ly = h * 0.46;
        const lr = Math.max(w, h) * (0.12 + lamp * 0.5);
        const g = ctx.createRadialGradient(lx, ly, 0, lx, ly, lr);
        g.addColorStop(0, `rgba(201, 162, 39, ${0.16 * lamp})`);
        g.addColorStop(0.4, `rgba(160, 128, 60, ${0.07 * lamp})`);
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, w, h);
      }

      if (fog > 0) {
        for (const b of BLOBS) {
          // Drift right, wrap, and bob a little. Sine on its own phase so the
          // bank never moves as one sheet.
          const x = (((b.x + t * b.speed * 0.0004) % 1.4) - 0.2) * w;
          const y = (b.y + Math.sin(t * 0.00035 + b.phase) * 0.03) * h;
          const r = b.r * Math.max(w, h);
          const g = ctx.createRadialGradient(x, y, 0, x, y, r);
          // The fog is the only thing in the sequence that moves, so it has to
          // be visible enough to read as weather. Below about 0.07 it reads as
          // another vignette and the whole frame looks static.
          const a = 0.085 * fog * (0.6 + 0.4 * Math.sin(t * 0.0004 + b.phase));
          g.addColorStop(0, `rgba(150, 172, 186, ${a})`);
          g.addColorStop(1, "rgba(150, 172, 186, 0)");
          ctx.fillStyle = g;
          ctx.fillRect(x - r, y - r, r * 2, r * 2);
        }
      }

      // Corners stay shut, so the frame never reads as a rectangle of weather.
      const vg = ctx.createRadialGradient(
        w / 2,
        h / 2,
        Math.min(w, h) * 0.25,
        w / 2,
        h / 2,
        Math.max(w, h) * 0.8,
      );
      vg.addColorStop(0, "rgba(0,0,0,0)");
      vg.addColorStop(1, "rgba(0,0,0,0.85)");
      ctx.fillStyle = vg;
      ctx.fillRect(0, 0, w, h);

      if (t >= END) {
        finish();
        return;
      }
      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);

    // The text is CSS, driven off these rather than off animation-delay, so a
    // skip cannot leave a half-faded title behind.
    const marks = [
      setTimeout(() => setBeat(1), LAMP_IN),
      setTimeout(() => setBeat(2), TITLE_IN),
      setTimeout(() => setBeat(3), TITLE_IN + 1200),
    ];

    return () => {
      cancelAnimationFrame(frame);
      for (const m of marks) clearTimeout(m);
    };
  }, [finish]);

  return (
    <div
      className="fixed inset-0 z-[5000] cursor-pointer select-none bg-ink"
      role="presentation"
      data-testid="intro"
    >
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />

      <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
        <p
          className={`text-[10px] tracking-[0.5em] text-faint duration-[1200ms] ease-[var(--ease-noir)] [transition-property:opacity] ${
            beat >= 2 ? "opacity-100" : "opacity-0"
          }`}
        >
          MARROWGATE &middot; <span className="numeral">1984</span>
        </p>

        <h1
          className={`mt-4 font-serif text-4xl text-bright duration-[1600ms] ease-[var(--ease-noir)] [transition-property:opacity,letter-spacing] sm:text-6xl ${
            beat >= 2
              ? "tracking-[0.12em] opacity-100"
              : "tracking-[0.4em] opacity-0"
          }`}
        >
          NOIR CITY
        </h1>

        <p
          className={`mt-6 max-w-md font-serif text-[14px] italic leading-relaxed text-muted duration-[1200ms] ease-[var(--ease-noir)] [transition-property:opacity] ${
            beat >= 3 ? "opacity-100" : "opacity-0"
          }`}
        >
          The fog comes up off the Ebb at four, and it does not lift until
          somebody has been found.
        </p>
      </div>

      <button
        onClick={finish}
        className="absolute bottom-6 right-6 border border-line px-4 py-2 text-[10px] tracking-[0.3em] text-faint lift hover:border-edge hover:text-muted"
      >
        SKIP
      </button>
    </div>
  );
}

/**
 * Whether the intro is owed this visit.
 *
 * Read in an effect rather than during render: `localStorage` does not exist on
 * the server, and reading it while rendering would make the first client paint
 * disagree with the HTML that was sent.
 */
export function useIntro(): [boolean, () => void] {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      if (!window.localStorage.getItem(SEEN_KEY)) setShow(true);
    } catch {
      // No storage, no intro. Better than showing it on every navigation.
    }
  }, []);

  return [show, useCallback(() => setShow(false), [])];
}
