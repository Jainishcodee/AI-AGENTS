import Link from "next/link";
import { listCases } from "@/lib/server/cases";
import { multiplayerReady } from "@/lib/supabase/server";
import { HostButton, JoinBox } from "@/components/game/RoomControls";
import { Plate } from "@/components/art/Plate";

export default function Home() {
  const cases = listCases();
  // Rooms need a Supabase project. Without one the game still plays solo, so
  // the multiplayer controls stand down rather than erroring on click.
  const rooms = multiplayerReady();

  return (
    <main className="min-h-dvh bg-ink text-muted">
      <div className="mx-auto max-w-3xl px-5 py-12 sm:px-8 sm:py-20">
        <p className="text-[10px] tracking-[0.4em] text-faint">
          BACKLUND &middot; 1984
        </p>
        <h1 className="mt-3 font-serif text-4xl tracking-[0.12em] text-bright sm:text-5xl">
          NOIR CITY
        </h1>
        <p className="mt-5 max-w-xl font-serif text-[15px] leading-relaxed text-muted">
          You are a private investigator with two rooms above a tobacconist on
          Iron Cross Street. The police are bought, the courts are slow, and the
          only clock that matters is the one running down while you decide where
          to go next.
        </p>

        <ul className="mt-10 space-y-4 sm:mt-14">
          {cases.map((c) => (
            <li key={c.id} className="border border-line">
              <Plate
                kind="cover"
                id={c.id}
                alt={c.title}
                ratio="aspect-[21/8]"
              />
              <div className="p-5 sm:p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
                <h2 className="font-serif text-xl text-bright sm:text-2xl">
                  {c.title}
                </h2>
                {c.isTutorial && (
                  <span className="shrink-0 border border-edge px-2 py-0.5 text-[9px] tracking-[0.2em] text-muted">
                    START HERE
                  </span>
                )}
              </div>

              <p className="mt-1.5 text-[10px] tracking-[0.2em] text-faint">
                <span className="numeral">{c.suspectCount}</span>&nbsp;SUSPECTS
                &middot; <span className="numeral">{c.locationCount}</span>
                &nbsp;ADDRESSES &middot;{" "}
                <span className="numeral">{c.sessionMinutes}</span>&nbsp;MIN
              </p>

              <p className="mt-4 font-serif text-[14px] leading-relaxed text-muted">
                {c.brief}
              </p>

              <div className="mt-6 flex flex-wrap items-center gap-x-8 gap-y-3">
                <Link
                  href={`/play/${c.id}`}
                  className="text-[11px] tracking-[0.2em] text-muted lift hover:text-bright"
                >
                  PLAY ALONE &rarr;
                </Link>
                <HostButton caseId={c.id} enabled={rooms} />
              </div>
              </div>
            </li>
          ))}
        </ul>

        <JoinBox enabled={rooms} />

        <p className="mt-16 text-[11px] tracking-[0.2em] text-ghost">
          <Link href="/map" className="lift hover:text-muted">
            OR WALK THE CITY WITHOUT A CASE &rarr;
          </Link>
        </p>
      </div>
    </main>
  );
}
