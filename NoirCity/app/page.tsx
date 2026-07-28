import Link from "next/link";
import { listCases } from "@/lib/server/cases";

export default function Home() {
  const cases = listCases();

  return (
    <main className="min-h-dvh bg-[#08090b] text-neutral-300">
      <div className="mx-auto max-w-3xl px-8 py-20">
        <p className="text-[10px] tracking-[0.4em] text-neutral-600">
          BACKLUND &middot; 1984
        </p>
        <h1 className="mt-3 font-serif text-5xl tracking-[0.12em] text-neutral-100">
          NOIR CITY
        </h1>
        <p className="mt-5 max-w-xl font-serif text-[15px] leading-relaxed text-neutral-400">
          You are a private investigator with two rooms above a tobacconist on
          Iron Cross Street. The police are bought, the courts are slow, and the
          only clock that matters is the one running down while you decide where
          to go next.
        </p>

        <ul className="mt-14 space-y-4">
          {cases.map((c) => (
            <li key={c.id}>
              <Link
                href={`/play/${c.id}`}
                className="group block border border-neutral-800 p-6 transition hover:border-amber-200/40"
              >
                <div className="flex items-baseline justify-between gap-4">
                  <h2 className="font-serif text-2xl text-neutral-100">
                    {c.title}
                  </h2>
                  {c.isTutorial && (
                    <span className="shrink-0 border border-amber-200/30 px-2 py-0.5 text-[9px] tracking-[0.2em] text-amber-200/70">
                      START HERE
                    </span>
                  )}
                </div>

                <p className="mt-1.5 text-[10px] tracking-[0.2em] text-neutral-600">
                  {c.suspectCount} SUSPECTS &middot; {c.locationCount} ADDRESSES
                  &middot; {c.timeBudget} HOURS
                </p>

                <p className="mt-4 font-serif text-[14px] leading-relaxed text-neutral-400">
                  {c.brief}
                </p>

                <p className="mt-5 text-[11px] tracking-[0.2em] text-neutral-600 transition group-hover:text-amber-100">
                  TAKE THE CASE &rarr;
                </p>
              </Link>
            </li>
          ))}
        </ul>

        <p className="mt-16 text-[11px] tracking-[0.2em] text-neutral-700">
          <Link href="/map" className="transition hover:text-neutral-400">
            OR WALK THE CITY WITHOUT A CASE &rarr;
          </Link>
        </p>
      </div>
    </main>
  );
}
