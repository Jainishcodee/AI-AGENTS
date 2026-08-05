"use client";

import { useState } from "react";
import type { Action } from "@/lib/engine/reducer";
import type { ClientView } from "@/lib/engine/view";
import { ARGUMENT_LIMIT } from "@/lib/engine/scoring";

/** Below this it is not an argument, it is a shrug. */
const MIN_ARGUMENT = 20;

/**
 * One attempt, written out.
 *
 * There is no list to pick from and that is the whole point. A menu of three
 * motives is a one-in-three guess for a player who never worked out the reason,
 * and being able to shrug your way to the right answer is the opposite of a
 * detective game. Here you have to be able to say what happened.
 *
 * Nothing on this screen hints at whether any of it is right. The form will
 * happily take a confident, wrong, beautifully written accusation.
 */
export function AccusePanel({
  view,
  act,
  busy,
}: {
  view: ClientView;
  act: (a: Action) => void;
  busy: boolean;
}) {
  const [culpritName, setCulpritName] = useState("");
  const [argument, setArgument] = useState("");
  const [confirming, setConfirming] = useState(false);

  const named = culpritName.trim().length > 0;
  const said = argument.trim().length >= MIN_ARGUMENT;
  const ready = named && said;
  const left = ARGUMENT_LIMIT - argument.length;

  return (
    <div className="space-y-7 px-5 py-5 sm:px-6">
      <p className="border border-danger/40 bg-danger/10 px-4 py-3 font-serif text-[13px] leading-relaxed text-muted">
        You get one attempt. Name them, then say what happened and what proves
        it &mdash; in your own words. Nobody will tell you when you are ready.
      </p>

      <section>
        <p className="text-[10px] tracking-[0.3em] text-faint">WHO KILLED THEM</p>
        <input
          value={culpritName}
          onChange={(e) => setCulpritName(e.target.value.slice(0, 120))}
          placeholder="A name"
          // 16px below sm, or focusing this zooms the page on iOS.
          className="mt-3 w-full border border-line bg-transparent px-3 py-2.5 font-serif text-[16px] text-bright outline-none placeholder:text-ghost focus:border-muted sm:text-[15px]"
        />
        <p className="mt-2 text-[11px] leading-relaxed text-ghost">
          As you have it written down. A surname is enough.
        </p>
      </section>

      <section>
        <div className="flex items-baseline justify-between">
          <p className="text-[10px] tracking-[0.3em] text-faint">MAKE YOUR CASE</p>
          {/* Only once it is close enough to matter. A counter ticking from
              1,500 the moment you start typing reads as a limit to fill. */}
          {left < 300 && (
            <p className="numeral text-[10px] tracking-[0.2em] text-faint">{left}</p>
          )}
        </div>
        <textarea
          value={argument}
          onChange={(e) => setArgument(e.target.value.slice(0, ARGUMENT_LIMIT))}
          rows={9}
          placeholder="What happened, why, and what proves it."
          className="mt-3 w-full resize-none border border-line bg-transparent px-3 py-2.5 font-serif text-[16px] leading-relaxed text-bright outline-none placeholder:text-ghost focus:border-muted sm:text-[14px]"
        />
        <p className="mt-2 text-[11px] leading-relaxed text-ghost">
          Write it as you would say it to a magistrate. Every separate thing you
          establish is worth something on its own.
        </p>
      </section>

      {!confirming ? (
        <button
          disabled={!ready || busy}
          onClick={() => setConfirming(true)}
          className="w-full border border-danger/60 px-4 py-3 text-[11px] tracking-[0.25em] text-danger lift hover:bg-danger/30 disabled:cursor-not-allowed disabled:border-line disabled:text-ghost"
        >
          FILE THE ACCUSATION
        </button>
      ) : (
        <div className="border border-danger/60 p-4">
          <p className="font-serif text-[13px] leading-relaxed text-muted">
            You are naming{" "}
            <span className="text-bright">{culpritName.trim()}</span>. This
            closes the case.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => setConfirming(false)}
              className="flex-1 border border-edge px-3 py-2 text-[11px] tracking-[0.2em] text-muted"
            >
              WAIT
            </button>
            <button
              disabled={busy}
              onClick={() =>
                act({
                  type: "accuse",
                  culpritName: culpritName.trim(),
                  argument: argument.trim(),
                })
              }
              className="flex-1 border border-danger bg-danger/40 px-3 py-2 text-[11px] tracking-[0.2em] text-danger disabled:opacity-40"
            >
              GO AHEAD
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
