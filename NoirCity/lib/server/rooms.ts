import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import { applyAction, initialState, type Action, type GameState } from "@/lib/engine/reducer";
import { withGrade } from "./aiGrade";
import { buildView } from "@/lib/engine/view";
import { tutorialProgress } from "@/lib/engine/tutorial";
import type { FeedEntry, RoomPlayer, RoomSnapshot } from "@/lib/game/types";
import { loadCase, loadCity } from "./cases";
import { clockFields, sessionExpired, toFeedEntry } from "./journal";
import { supabaseAdmin } from "@/lib/supabase/server";

/**
 * Multiplayer rooms, backed by Supabase.
 *
 * The invariant this file exists to hold: the server owns the case file and the
 * clock. A client can ask to search a warehouse; only this code decides whether
 * that costs two hours and what it turns up.
 */

const MAX_PLAYERS = 6;

/** No O/0 or I/1 - room codes get read aloud over a call. */
const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

function roomCode(length = 4): string {
  let out = "";
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  for (const b of bytes) out += CODE_ALPHABET[b % CODE_ALPHABET.length];
  return out;
}

export type RoomError =
  | { error: string; status: number };

function fail(error: string, status: number): RoomError {
  return { error, status };
}

function isFail(x: unknown): x is RoomError {
  return typeof x === "object" && x !== null && "error" in x;
}

// ---------------------------------------------------------------------------

interface GameRow {
  id: string;
  room_code: string;
  case_id: string;
  host_id: string;
  status: "lobby" | "active" | "finished";
  state: GameState;
  state_version: number;
  max_players: number;
}

async function loadRoom(
  db: SupabaseClient,
  gameId: string,
): Promise<GameRow | null> {
  const { data } = await db.from("games").select("*").eq("id", gameId).single();
  return (data as GameRow) ?? null;
}

async function loadPlayers(
  db: SupabaseClient,
  gameId: string,
): Promise<RoomPlayer[]> {
  const { data } = await db
    .from("game_players")
    .select("user_id, display_name, is_host, joined_at")
    .eq("game_id", gameId)
    .order("joined_at");

  return (data ?? []).map((r) => ({
    userId: r.user_id as string,
    displayName: r.display_name as string,
    isHost: r.is_host as boolean,
    joinedAt: r.joined_at as string,
  }));
}

async function loadFeed(db: SupabaseClient, gameId: string): Promise<FeedEntry[]> {
  const { data } = await db
    .from("game_events")
    .select("seq, payload")
    .eq("game_id", gameId)
    .order("seq");

  return (data ?? []).map((r) => ({
    seq: r.seq as number,
    ...(r.payload as Omit<FeedEntry, "seq">),
  }));
}

async function isMember(
  db: SupabaseClient,
  gameId: string,
  userId: string,
): Promise<boolean> {
  const { data } = await db
    .from("game_players")
    .select("user_id")
    .eq("game_id", gameId)
    .eq("user_id", userId)
    .maybeSingle();
  return Boolean(data);
}

async function snapshot(
  db: SupabaseClient,
  row: GameRow,
  userId: string,
): Promise<RoomSnapshot | RoomError> {
  const caseIndex = loadCase(row.case_id);
  if (!caseIndex) return fail("That case no longer exists.", 500);

  const [players, feed] = await Promise.all([
    loadPlayers(db, row.id),
    loadFeed(db, row.id),
  ]);

  return {
    sessionId: row.id,
    gameId: row.id,
    roomCode: row.room_code,
    status: row.status,
    hostId: row.host_id,
    players,
    youId: userId,
    maxPlayers: row.max_players,
    view: buildView(caseIndex, loadCity(), row.state),
    feed,
    tutorial: tutorialProgress(caseIndex, row.state),
    ...clockFields(caseIndex, row.state, Date.now()),
  };
}

// ---------------------------------------------------------------------------

export async function createRoom(
  userId: string,
  caseId: string,
  displayName: string,
): Promise<RoomSnapshot | RoomError> {
  const db = supabaseAdmin();
  if (!db) return fail("Multiplayer is not configured on this server.", 503);

  const caseIndex = loadCase(caseId);
  if (!caseIndex) return fail("No such case.", 404);

  // Codes are short enough to collide occasionally; the unique index is the
  // real guard and a few retries make that invisible.
  for (let attempt = 0; attempt < 6; attempt++) {
    const code = roomCode();
    const { data, error } = await db
      .from("games")
      .insert({
        room_code: code,
        case_id: caseId,
        host_id: userId,
        status: "lobby",
        state: initialState(caseIndex),
        max_players: MAX_PLAYERS,
      })
      .select("*")
      .single();

    if (error) {
      if (error.code === "23505") continue; // duplicate room_code, try again
      return fail(error.message, 500);
    }

    const row = data as GameRow;
    const { error: joinError } = await db.from("game_players").insert({
      game_id: row.id,
      user_id: userId,
      display_name: displayName,
      is_host: true,
    });
    if (joinError) return fail(joinError.message, 500);

    return snapshot(db, row, userId);
  }

  return fail("Could not allocate a room code. Try again.", 503);
}

export async function joinRoom(
  userId: string,
  code: string,
  displayName: string,
): Promise<RoomSnapshot | RoomError> {
  const db = supabaseAdmin();
  if (!db) return fail("Multiplayer is not configured on this server.", 503);

  const { data } = await db
    .from("games")
    .select("*")
    .eq("room_code", code.toUpperCase())
    .maybeSingle();

  const row = data as GameRow | null;
  if (!row) return fail("No room with that code.", 404);

  const already = await isMember(db, row.id, userId);
  if (!already) {
    if (row.status !== "lobby") {
      return fail("That case is already under way.", 409);
    }
    const players = await loadPlayers(db, row.id);
    if (players.length >= row.max_players) {
      return fail("That room is full.", 409);
    }
    const { error } = await db.from("game_players").insert({
      game_id: row.id,
      user_id: userId,
      display_name: displayName,
      is_host: false,
    });
    if (error) return fail(error.message, 500);
  }

  return snapshot(db, row, userId);
}

export async function getRoom(
  userId: string,
  gameId: string,
): Promise<RoomSnapshot | RoomError> {
  const db = supabaseAdmin();
  if (!db) return fail("Multiplayer is not configured on this server.", 503);

  const row = await loadRoom(db, gameId);
  if (!row) return fail("No such room.", 404);
  if (!(await isMember(db, gameId, userId))) {
    return fail("You are not on this case.", 403);
  }
  return snapshot(db, row, userId);
}

export async function startRoom(
  userId: string,
  gameId: string,
): Promise<RoomSnapshot | RoomError> {
  const db = supabaseAdmin();
  if (!db) return fail("Multiplayer is not configured on this server.", 503);

  const row = await loadRoom(db, gameId);
  if (!row) return fail("No such room.", 404);
  if (row.host_id !== userId) return fail("Only the host can start.", 403);
  if (row.status !== "lobby") return fail("Already started.", 409);

  // The real session clock starts when the host opens the file, not when the
  // room was created - people take a while to assemble.
  const { data, error } = await db
    .from("games")
    .update({
      status: "active",
      started_at: new Date().toISOString(),
      state: { ...row.state, startedAt: Date.now() },
      state_version: row.state_version + 1,
    })
    .eq("id", gameId)
    .eq("status", "lobby")
    .select("*")
    .single();

  if (error) return fail(error.message, 500);
  return snapshot(db, data as GameRow, userId);
}

/**
 * Applies one action. The UPDATE is conditional on `state_version`, so if two
 * players act on the same state only one write lands - the other is told to
 * re-read rather than silently spending the same hour twice.
 */
export async function actInRoom(
  userId: string,
  gameId: string,
  action: Action,
): Promise<RoomSnapshot | RoomError> {
  const db = supabaseAdmin();
  if (!db) return fail("Multiplayer is not configured on this server.", 503);

  if (!(await isMember(db, gameId, userId))) {
    return fail("You are not on this case.", 403);
  }

  for (let attempt = 0; attempt < 3; attempt++) {
    const row = await loadRoom(db, gameId);
    if (!row) return fail("No such room.", 404);
    if (row.status === "lobby") return fail("The case has not started.", 409);
    if (row.status === "finished") return fail("The case is closed.", 409);

    const caseIndex = loadCase(row.case_id);
    if (!caseIndex) return fail("That case no longer exists.", 500);

    // Real time at the table is a hard limit. Checked here rather than on a
    // timer, so a tab left open past the deadline buys nobody extra minutes.
    if (sessionExpired(caseIndex, row.state, Date.now())) {
      await db
        .from("games")
        .update({
          status: "finished",
          state: { ...row.state, status: "finished", timeRemaining: 0 },
          state_version: row.state_version + 1,
          finished_at: new Date().toISOString(),
        })
        .eq("id", gameId)
        .eq("state_version", row.state_version);
      return fail("Time is up. The case is closed.", 409);
    }

    // Same as the solo path: the grade is attached server-side or not at all.
    const result = applyAction(
      caseIndex,
      loadCity(),
      row.state,
      await withGrade(caseIndex, action),
    );
    if (!result.ok) return fail(result.error, 400);

    const finished = result.state.status === "finished";
    const { data: updated, error } = await db
      .from("games")
      .update({
        state: result.state,
        state_version: row.state_version + 1,
        ...(finished
          ? { status: "finished", finished_at: new Date().toISOString() }
          : {}),
      })
      .eq("id", gameId)
      .eq("state_version", row.state_version)
      .select("*")
      .maybeSingle();

    if (error) return fail(error.message, 500);
    if (!updated) continue; // somebody else moved first; re-read and retry

    const { seq: _seq, ...entry } = toFeedEntry(
      caseIndex,
      result.state,
      result.effect,
      row.state_version,
    );

    await db.from("game_events").insert({
      game_id: gameId,
      seq: row.state_version,
      actor_id: userId,
      type: action.type,
      payload: entry as Omit<FeedEntry, "seq">,
    });

    return snapshot(db, updated as GameRow, userId);
  }

  return fail("The board moved under you. Try that again.", 409);
}

export { isFail };
