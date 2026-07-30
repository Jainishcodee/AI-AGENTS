"use client";

/**
 * The four sections of the case file, and how you move between them.
 *
 * Two shapes for two places. On a desktop these are index tabs down the outside
 * edge of the notebook, the way a case file has tabs stitched into it - the
 * active one runs into the page it belongs to, which is what makes it read as
 * one object rather than a toolbar sitting next to a box. On a phone there is no
 * room beside anything, so the same four become a row across the top of the
 * sheet.
 *
 * Icons carry the recognition and the words carry the meaning; neither alone is
 * enough at this size, so both are always shown.
 */

export type Tab = "journal" | "here" | "evidence" | "accuse";

const TABS: Array<{ id: Tab; label: string; icon: React.ReactNode }> = [
  {
    id: "journal",
    label: "JOURNAL",
    // A written page.
    icon: (
      <>
        <rect x="3" y="2" width="10" height="12" rx="1" />
        <path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" />
      </>
    ),
  },
  {
    id: "here",
    label: "HERE",
    // A pin in a map.
    icon: (
      <>
        <path d="M8 14s4.3-4.3 4.3-7.4a4.3 4.3 0 1 0-8.6 0C3.7 9.7 8 14 8 14z" />
        <circle cx="8" cy="6.5" r="1.5" />
      </>
    ),
  },
  {
    id: "evidence",
    label: "EVIDENCE",
    // A glass held over something.
    icon: (
      <>
        <circle cx="7" cy="7" r="4" />
        <path d="M10 10l3.4 3.4" />
      </>
    ),
  },
  {
    id: "accuse",
    label: "ACCUSE",
    // A person, named.
    icon: (
      <>
        <circle cx="8" cy="8" r="6" />
        <circle cx="8" cy="6.3" r="1.8" />
        <path d="M4.7 12.5a3.5 3.5 0 0 1 6.6 0" />
      </>
    ),
  },
];

function Icon({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.1"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="h-4 w-4"
    >
      {children}
    </svg>
  );
}

/** Count shown against a section, when it has one worth showing. */
function Count({ n }: { n: number }) {
  if (!n) return null;
  return <span className="numeral text-[9px] leading-none text-faint">{n}</span>;
}

export function CaseTabs({
  active,
  onSelect,
  evidenceCount,
  variant,
  className = "",
  style,
}: {
  active: Tab;
  onSelect: (tab: Tab) => void;
  evidenceCount: number;
  /** `rail` is the desktop notebook's stitched-in tabs; `row` is the phone. */
  variant: "rail" | "row";
  className?: string;
  /** The rail's offset is derived from the notebook's width token. */
  style?: React.CSSProperties;
}) {
  const rail = variant === "rail";

  return (
    <nav
      aria-label="Case file sections"
      style={style}
      className={`${rail ? "flex flex-col gap-1.5" : "flex border-b border-line"} ${className}`}
    >
      {TABS.map(({ id, label, icon }) => {
        const on = active === id;
        return (
          <button
            key={id}
            onClick={() => onSelect(id)}
            aria-current={on ? "page" : undefined}
            className={
              rail
                ? // A tab: rounded on the outside edge, square where it meets the
                  // page. The active one loses its right border and shares the
                  // notebook's background, so the seam between them disappears.
                  `relative flex h-[66px] w-[var(--rail-w)] flex-col items-center justify-center gap-1.5 rounded-l-sm border border-r-0 backdrop-blur-md lift focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-muted ${
                    on
                      ? // Same fill and blur as the notebook, and it overlaps
                        // the notebook's border by a pixel - so the active tab
                        // and the page it opens read as one piece of card.
                        "border-edge bg-surface/92 text-bright"
                      : "border-line bg-ink/60 text-faint hover:bg-surface/70 hover:text-muted"
                  }`
                : `flex flex-1 flex-col items-center justify-center gap-1 border-b-2 px-2 py-2.5 lift focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-2 focus-visible:outline-muted ${
                    on
                      ? "border-paper-dim text-bright"
                      : "border-transparent text-faint hover:text-muted"
                  }`
            }
          >
            <Icon>{icon}</Icon>
            {/* Stacked on the rail, side by side in the phone's row. `EVIDENCE`
                is eight characters and a count; on a 66px tab that only fits if
                the two are on separate lines and the tracking is nearly nil. */}
            <span
              className={
                rail
                  ? "flex flex-col items-center gap-0.5 text-[8px] leading-none tracking-[0.04em]"
                  : "flex items-baseline gap-1 text-[8px] leading-none tracking-[0.12em]"
              }
            >
              {label}
              {id === "evidence" && <Count n={evidenceCount} />}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
