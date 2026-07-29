"use client";

import { createBrowserClient } from "@supabase/ssr";
import { SUPABASE_ANON_KEY, SUPABASE_URL, multiplayerConfigured } from "./env";
import type { Database } from "./types";

/**
 * The browser client. Anonymous sign-in only - a detective agency does not need
 * a password, and asking six friends to make accounts before a game night is how
 * you lose four of them.
 *
 * This client can READ the rooms you belong to and WRITE nothing but chat. Every
 * game action goes through a server route instead.
 */

let cached: ReturnType<typeof createBrowserClient<Database>> | null = null;

export function supabaseBrowser() {
  if (!multiplayerConfigured) return null;
  if (!cached) {
    cached = createBrowserClient<Database>(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return cached;
}

/** Signs in anonymously if there is no session yet. Returns the user id. */
export async function ensureAnonymousUser(): Promise<string | null> {
  const supabase = supabaseBrowser();
  if (!supabase) return null;

  const { data } = await supabase.auth.getSession();
  if (data.session?.user) return data.session.user.id;

  const { data: signed, error } = await supabase.auth.signInAnonymously();
  if (error) throw new Error(`Could not sign in: ${error.message}`);
  return signed.user?.id ?? null;
}
