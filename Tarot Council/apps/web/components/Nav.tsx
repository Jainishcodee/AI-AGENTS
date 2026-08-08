"use client";

/**
 * The app shell.
 *
 * Added because the single-screen version was the product's biggest lie: it made
 * Cognitive OS look like something you ask once, when the whole argument is that it
 * accumulates. A reload lost everything, and nothing showed the corpus.
 *
 * The due-count badge is load-bearing, not decoration. The learning loop only closes
 * if somebody comes back and records what happened, and a number sitting in the nav is
 * the cheapest thing that makes that visible.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getJSON } from "@/lib/stream";

const LINKS: { href: string; label: string }[] = [
  { href: "/", label: "Decide" },
  { href: "/history", label: "History" },
  { href: "/calibration", label: "Track record" },
];

export function Nav() {
  const pathname = usePathname();
  const [due, setDue] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getJSON<{ count: number }>("reminders")
      .then((data) => !cancelled && setDue(data.count))
      .catch(() => !cancelled && setDue(null));
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return (
    <header className="sticky top-0 z-20 border-b bg-[var(--color-ink)]/90 backdrop-blur hair">
      <div className="mx-auto flex w-full max-w-[1680px] items-center gap-6 px-4 py-2.5 sm:px-6 lg:px-8">
        <Link href="/" className="shrink-0">
          <span className="text-[13.5px] font-medium tracking-tight">Cognitive OS</span>
        </Link>

        <nav className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active =
              link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded px-2.5 py-1 text-[12.5px] transition-colors ${
                  active
                    ? "bg-[var(--color-raised)] text-[var(--color-text)]"
                    : "text-[var(--color-faint)] hover:text-[var(--color-muted)]"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {due !== null && due > 0 && (
          <Link
            href="/history?status=due"
            title="Decisions whose check-in date has arrived"
            className="ml-auto flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11.5px] transition-colors hover:brightness-125"
            style={{ borderColor: "var(--color-assumed)44", color: "var(--color-assumed)" }}
          >
            <span
              className="inline-block size-1.5 rounded-full"
              style={{ background: "var(--color-assumed)" }}
            />
            {due} due for a check-in
          </Link>
        )}
      </div>
    </header>
  );
}
