/**
 * The in-fiction clock.
 *
 * Every action costs hours, and those hours move a date and time that appears on
 * each journal entry. It is what turns a list of actions into a case file: not
 * "searched the parlour" but "Friday, 25 May 1984, 11:20 — 85 Threadneedle Walk".
 *
 * Deliberately free of `Date` arithmetic on the game's part: the case declares a
 * start, the state carries elapsed hours, and this renders the two together. No
 * timezone can get into it and nothing here depends on when you are playing.
 */

const DAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
] as const;

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const;

export interface StoryMoment {
  /** "Friday, 25 May 1984" */
  dateline: string;
  /** "11:20" */
  time: string;
  /** Which day of the case this is, from 1. */
  day: number;
}

export function storyMoment(startsAt: string, hoursElapsed: number): StoryMoment {
  const start = new Date(`${startsAt}Z`);
  const at = new Date(start.getTime() + hoursElapsed * 3600_000);

  const dayOfCase =
    Math.floor(
      (Date.UTC(at.getUTCFullYear(), at.getUTCMonth(), at.getUTCDate()) -
        Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate())) /
        86_400_000,
    ) + 1;

  return {
    dateline: `${DAYS[at.getUTCDay()]}, ${at.getUTCDate()} ${MONTHS[at.getUTCMonth()]} ${at.getUTCFullYear()}`,
    time: `${String(at.getUTCHours()).padStart(2, "0")}:${String(at.getUTCMinutes()).padStart(2, "0")}`,
    day: dayOfCase,
  };
}

/** "01:23:40" from milliseconds, for the session countdown. */
export function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}
