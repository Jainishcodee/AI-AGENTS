import Link from "next/link";
import { listCases } from "@/lib/server/cases";
import { multiplayerReady } from "@/lib/supabase/server";
import { HostButton, JoinBox } from "@/components/game/RoomControls";
import { Plate } from "@/components/art/Plate";
import { Doorway } from "@/components/intro/Doorway";
import { StudyBackdrop } from "@/components/intro/StudyBackdrop";

export default function Home() {
  const cases = listCases();
  // Rooms need a Supabase project. Without one the game still plays solo, so
  // the multiplayer controls stand down rather than erroring on click.
  const rooms = multiplayerReady();

  return (
    <Doorway>
      <main className="relative min-h-dvh bg-ink text-muted">
        <StudyBackdrop />
        <div className="mx-auto max-w-3xl px-5 py-12 sm:px-8 sm:py-20">
        {/* The name on the door, not a page heading. Small, and above the
            fold only because you walk past it on the way in. */}
        <p className="text-[10px] tracking-[0.35em] text-faint">
          E. CROWE &middot; ENQUIRIES
        </p>
        <h1 className="mt-3 font-serif text-4xl tracking-[0.12em] text-bright sm:text-5xl">
          NOIR CITY
        </h1>
        <p className="mt-2 text-[10px] tracking-[0.35em] text-faint">
          MARROWGATE &middot; <span className="numeral">1984</span>
        </p>
        <p className="mt-6 max-w-xl font-serif text-[15px] leading-relaxed text-muted">
          Two rooms above a tobacconist on Cripplegate Lane, and your name on
          the glass. The police are bought, the courts are slow, and the only
          clock that matters is the one running down while you decide where to
          go next.
        </p>

        <p className="mt-10 text-[10px] tracking-[0.3em] text-faint sm:mt-14">
          ON THE DESK
        </p>

        <ul className="mt-4 space-y-5">
          {cases.map((c) => (
            // A folder lying on a desk, not a row in a table. The warm left
            // edge is the spine; the shadow is what lifts it off the wood.
            <li
              key={c.id}
              className="border border-line border-l-2 border-l-paper-dim/40 bg-surface/60 shadow-[0_16px_40px_-20px_rgba(0,0,0,0.9)] backdrop-blur-[2px] settle hover:border-l-paper-dim hover:bg-surface/80"
            >
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
    </Doorway>
  );
}
