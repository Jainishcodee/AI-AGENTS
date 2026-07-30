import type { ClientView } from "@/lib/engine/view";
import type { TutorialProgress } from "@/lib/engine/tutorial";

/**
 * The wire format between server and client. Deliberately not in `lib/server`,
 * because the client needs these types and importing a `server-only` module
 * from a client component is a build error.
 */

/** One entry in the case journal. Rendered chronologically, newest last. */
export interface FeedEntry {
  seq: number;
  kind: "travel" | "search" | "interview" | "lab" | "accuse";
  /** In-fiction moment, precomputed on the server so every client agrees. */
  dateline: string;
  time: string;
  day: number;
  locationId: string;
  title: string;
  body: string;
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
  /** Where the story clock stands now, for the header. */
  now: { dateline: string; time: string; day: number };
  /**
   * Milliseconds of real session time left, measured when the server answered.
   * The client ticks it down locally rather than polling.
   */
  sessionRemainingMs: number;
  sessionMinutes: number;
}

export interface RoomPlayer {
  userId: string;
  displayName: string;
  isHost: boolean;
  joinedAt: string;
}

export type RoomStatus = "lobby" | "active" | "finished";

/** A game snapshot plus everything that only exists when other people are in it. */
export interface RoomSnapshot extends GameSnapshot {
  gameId: string;
  roomCode: string;
  status: RoomStatus;
  hostId: string;
  players: RoomPlayer[];
  /** The viewer, so the UI can tell "you" from everyone else. */
  youId: string;
  maxPlayers: number;
}

export interface ChatMessage {
  id: number;
  userId: string;
  displayName: string;
  body: string;
  createdAt: string;
}

export interface CaseSummary {
  id: string;
  title: string;
  brief: string;
  timeBudget: number;
  /** Real minutes at the table - the number a group actually plans around. */
  sessionMinutes: number;
  suspectCount: number;
  locationCount: number;
  isTutorial: boolean;
}
