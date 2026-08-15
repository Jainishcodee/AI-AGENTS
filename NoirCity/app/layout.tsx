import type { Metadata, Viewport } from "next";
import { Courier_Prime, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

/**
 * Two webfonts, each doing one job it is actually good at.
 *
 * Courier Prime is the face screenplays are set in - period-correct for 1984,
 * and it makes an evidence document read as a typed page. It is kept for
 * document *bodies* and nothing else: as a numeral face it is poor, with narrow
 * digits and an unmarked zero.
 *
 * Everything else uses `font-serif`, which resolves to Georgia from the system:
 * no download at all, and it reads well over the long prose the journal carries.
 */
// Regular only: nothing in the game sets bold on a mono element, and asking for
// 700 as well doubles the files Next emits for a weight that never renders.
//
// `preload: false` because this face is now reached from exactly one component -
// the body of an open evidence document. Preloading it put a font on the
// critical path of every page that never draws a glyph with it, which is what
// the browser was warning about. It arrives well before anyone opens a document.
const typewriter = Courier_Prime({
  variable: "--font-typewriter",
  subsets: ["latin"],
  weight: "400",
  preload: false,
});

/**
 * Every digit the player reads.
 *
 * The clock is on screen for the whole session and is the thing under the most
 * scrutiny, so the figures have to hold still and read at a glance. Plex Mono
 * has properly engineered tabular figures and a slashed zero - the mark a clerk
 * puts through a nought so it cannot be mistaken for an O. That is a ledger
 * hand, which is exactly the register a case file wants.
 *
 * Applied through the `.numeral` utility in `globals.css`, never directly.
 */
// One weight, and it is preloaded: unlike the typewriter, figures are on screen
// at first paint on every route - the case statistics on the landing page, the
// countdown in a session.
//
// 500 was tried for the countdown and the score and then dropped. Google splits
// Plex Mono into five unicode-range chunks per weight, so a second weight cost
// another preloaded file for slightly heavier digits on four elements, and left
// an unused-preload warning on any page that never draws them. Size and the
// `bright` token carry that emphasis instead, for nothing.
const figures = IBM_Plex_Mono({
  variable: "--font-figures",
  subsets: ["latin"],
  weight: "400",
});

export const metadata: Metadata = {
  title: "Noir City",
  description:
    "A detective game set in Marrowgate, 1984. Work the case alone or with five others, on one shared clock.",
};

// Next injects `width=device-width, initial-scale=1` already; this is here for
// the phone browser chrome, which otherwise frames a very dark game in white.
// Zoom is deliberately left alone - pinching a map is the whole point.
export const viewport: Viewport = {
  themeColor: "#08090b",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${typewriter.variable} ${figures.variable} h-full antialiased`}
    >
      {/* overscroll-none: dragging the map on a phone must not pull-to-refresh
          the page out from under the case. */}
      <body className="flex min-h-full flex-col overscroll-none">{children}</body>
    </html>
  );
}
