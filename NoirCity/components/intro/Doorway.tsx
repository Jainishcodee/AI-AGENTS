"use client";

import { IntroSequence, useIntro } from "./IntroSequence";

/**
 * Puts the intro in front of whatever it wraps, once.
 *
 * A client boundary and nothing else, so the study underneath can stay a server
 * component and keep rendering its case list on the server. The intro is laid
 * over the top rather than swapped in: by the time somebody skips it, the page
 * behind is already there, already hydrated, and there is nothing to wait for.
 */
export function Doorway({ children }: { children: React.ReactNode }) {
  const [show, dismiss] = useIntro();

  return (
    <>
      {children}
      {show && <IntroSequence onDone={dismiss} />}
    </>
  );
}
