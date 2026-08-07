"use client";

/**
 * The psychologist's nine dimensions, one column per person.
 *
 * A matrix rather than a stack of cards, because uniformity is the entire point of
 * that module: the same nine fields for everyone, every time. Laid out as a matrix,
 * comparison across people is free and a thin profile is visible at a glance — which
 * is what makes "did it really profile the awkward one" checkable by eye as well as
 * by validator.
 */

import { Chip, Empty, Meter, Pips } from "@/components/ui";

interface Profile {
  person_id: string;
  driving_emotion: string;
  fear: string;
  unmet_need: string;
  motivation: string;
  stress_level: number;
  reaction_if_accepted: string;
  reaction_if_rejected: string;
  what_they_wont_say: string;
  confidence: number;
}

const DIMENSIONS: { key: keyof Profile; label: string; emphasise?: boolean }[] = [
  { key: "driving_emotion", label: "driving emotion" },
  { key: "fear", label: "fear" },
  { key: "unmet_need", label: "unmet need" },
  { key: "motivation", label: "motivation" },
  { key: "reaction_if_accepted", label: "if it goes their way" },
  { key: "reaction_if_rejected", label: "if it does not" },
  { key: "what_they_wont_say", label: "will not say", emphasise: true },
];

export function ProfileSet({
  data,
  accent,
}: {
  data: Record<string, unknown>;
  accent: string;
}) {
  const profiles = (data.profiles ?? []) as Profile[];
  if (!profiles.length) return <Empty>No profiles.</Empty>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] border-collapse text-[12.5px]">
        <thead>
          <tr className="border-b hair">
            <th className="label pb-2 text-left font-medium" style={{ width: 118 }} />
            {profiles.map((profile) => (
              <th key={profile.person_id} className="pb-2 pr-3 text-left align-bottom last:pr-0">
                <div className="text-[13px] font-medium" style={{ color: accent }}>
                  {profile.person_id}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="label">stress</span>
                  <Pips value={profile.stress_level} colour="var(--color-speculative)" />
                </div>
                <div className="mt-1">
                  <Meter
                    value={profile.confidence}
                    colour={profile.confidence <= 0.5 ? "var(--color-assumed)" : accent}
                    title={`read confidence ${profile.confidence.toFixed(2)}`}
                  />
                </div>
                {profile.confidence <= 0.5 && (
                  <div className="mt-1">
                    <Chip colour="var(--color-assumed)" title="Capped: the user never named this person">
                      inferred
                    </Chip>
                  </div>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {DIMENSIONS.map(({ key, label, emphasise }) => (
            <tr key={key} className="border-b border-[var(--color-line-soft)] last:border-0">
              <td className="label py-2 pr-3 align-top">{label}</td>
              {profiles.map((profile) => (
                <td
                  key={profile.person_id}
                  className={`py-2 pr-3 align-top leading-snug last:pr-0 ${
                    emphasise ? "text-[var(--color-text)]" : "text-[var(--color-muted)]"
                  }`}
                >
                  {String(profile[key] ?? "") || (
                    <span className="italic text-[var(--color-faint)]">—</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
