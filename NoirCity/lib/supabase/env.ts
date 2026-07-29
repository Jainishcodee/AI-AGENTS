/**
 * Multiplayer is optional. With no Supabase project configured the game still
 * runs single-player against an in-memory store, which keeps local development
 * a one-command affair and means a missing env var degrades rather than crashes.
 */

export const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
export const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

/** True when the browser has enough configuration to talk to Supabase. */
export const multiplayerConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
