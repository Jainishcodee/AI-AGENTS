"use client";

import { Plate } from "@/components/art/Plate";

/**
 * How a case starts.
 *
 * This was a small panel of text in the corner of the map - the brief arrived
 * as a tooltip, and the plate that had been generated for it was buried three
 * screens away in the journal. So the game opened on a grey web of streets and
 * asked you to read a paragraph about somebody you had no picture of.
 *
 * Now it opens on the picture, full width, with the type small and quiet
 * underneath it. The image is doing the establishing; the words only have to
 * say what the job is. That is the order those two things belong in, and it is
 * why the reference this was built from opens on a room rather than on a menu.
 *
 * Deliberately not dismissible by clicking away: this is the one screen the
 * player should read, and it costs a single click to leave.
 */
export function CaseOpening({
  caseId,
  title,
  brief,
  onBegin,
}: {
  caseId: string;
  title: string;
  brief: string;
  onBegin: () => void;
}) {
  return (
    <div
      data-testid="case-opening"
      className="reveal absolute inset-0 z-[1400] overflow-y-auto overscroll-contain bg-ink/97 backdrop-blur-sm"
    >
      <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-5 py-10 sm:px-8">
        {/* The plate first, and given room. An unfilled slot draws a
            deterministic procedural plate rather than a hole, so this composes
            the same whether the artwork exists yet or not. */}
        <Plate
          kind="cover"
          id={caseId}
          alt={title}
          ratio="aspect-[21/9]"
          className="border border-line"
        />

        <p className="mt-8 text-center text-[10px] tracking-[0.4em] text-faint">
          THE JOB
        </p>
        <h1 className="mt-3 text-center font-serif text-2xl leading-tight text-bright sm:text-3xl">
          {title}
        </h1>

        {/* Measured to about 70 characters. The brief is four or five sentences
            of the only prose that has to land before anybody has done anything,
            and a full-width line at this size is unreadable. */}
        <div className="mx-auto mt-6 max-w-[60ch] space-y-4">
          {brief.split("\n\n").map((para, i) => (
            <p
              key={i}
              className="font-serif text-[15px] leading-relaxed text-muted"
            >
              {para}
            </p>
          ))}
        </div>

        <div className="mt-10 flex justify-center">
          <button
            onClick={onBegin}
            className="border border-paper-dim/50 px-8 py-3.5 text-[11px] tracking-[0.3em] text-paper lift hover:border-paper-dim hover:bg-bright/[0.04]"
          >
            GET TO WORK
          </button>
        </div>
      </div>
    </div>
  );
}
