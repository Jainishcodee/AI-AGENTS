"use client";

import Link from "next/link";
import { useGame } from "@/lib/game/useGame";
import { Investigation } from "@/components/game/Investigation";

/** Solo play. One detective, an in-memory session, nobody to argue with. */
export function GameScreen({ caseId }: { caseId: string }) {
  const { snapshot, refusal, loading, fatal, act, restart } = useGame(caseId);

  if (fatal) {
    return (
      <main className="flex h-dvh flex-col items-center justify-center gap-4 bg-[#08090b] text-neutral-400">
        <p>{fatal}</p>
        <Link
          href="/"
          className="text-[11px] tracking-[0.2em] text-neutral-600 hover:text-neutral-300"
        >
          BACK TO THE CASE FILES
        </Link>
      </main>
    );
  }

  if (loading || !snapshot) {
    return (
      <main className="flex h-dvh items-center justify-center bg-[#08090b] text-[11px] tracking-[0.3em] text-neutral-700">
        OPENING THE FILE...
      </main>
    );
  }

  return (
    <Investigation
      view={snapshot.view}
      tutorial={snapshot.tutorial}
      feed={snapshot.feed}
      act={act}
      onRestart={restart}
      banner={refusal ? <Refusal message={refusal} /> : null}
    />
  );
}

export function Refusal({ message }: { message: string }) {
  return (
    <p className="absolute bottom-6 left-1/2 z-[1000] -translate-x-1/2 border border-red-900/50 bg-[#0e0f11]/95 px-5 py-2.5 font-serif text-[13px] text-red-300 backdrop-blur">
      {message}
    </p>
  );
}
