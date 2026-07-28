import type { ClientView } from "@/lib/engine/view";
import type { TutorialProgress } from "@/lib/engine/tutorial";

/**
 * The wire format between server and client. Deliberately not in `lib/server`,
 * because the client needs these types and importing a `server-only` module
 * from a client component is a build error.
 */

export interface FeedEntry {
  seq: number;
  summary: string;
  timeSpent: number;
  /** Resolved titles, so the client never has to look a clue up. */
  newClues: Array<{ id: string; title: string }>;
  answer?: string;
}

export interface GameSnapshot {
  sessionId: string;
  view: ClientView;
  feed: FeedEntry[];
  tutorial: TutorialProgress;
}

export interface CaseSummary {
  id: string;
  title: string;
  brief: string;
  timeBudget: number;
  suspectCount: number;
  locationCount: number;
  isTutorial: boolean;
}
