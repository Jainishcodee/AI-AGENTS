import "server-only";
import { createServerClient } from "@supabase/ssr";
import { createClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { SUPABASE_ANON_KEY, SUPABASE_URL, multiplayerConfigured } from "./env";
import type { Database } from "./types";

/**
 * Two server clients, for two different jobs.
 *
 * `supabaseFromRequest` runs AS THE USER, so RLS applies. Use it to answer
 * "who is this, and do they belong to this room".
 *
 * `supabaseAdmin` uses the service role and bypasses RLS entirely. Use it only
 * to write game state, and only after the question above has been answered.
 * Never expose it to a client component - the `server-only` import makes that a
 * build error rather than a review comment.
 */

export function supabaseFromRequest() {
  if (!multiplayerConfigured) return null;

  return createServerClient<Database>(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      async getAll() {
        return (await cookies()).getAll();
      },
      async setAll(list) {
        try {
          const store = await cookies();
          for (const { name, value, options } of list) {
            store.set(name, value, options);
          }
        } catch {
          // Called from a Server Component, where cookies are read-only. The
          // middleware refreshes the session instead, so this is safe to ignore.
        }
      },
    },
  });
}

export function supabaseAdmin() {
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!SUPABASE_URL || !serviceKey) return null;

  return createClient<Database>(SUPABASE_URL, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

/** True when the server has everything it needs to run a multiplayer room. */
export function multiplayerReady(): boolean {
  return multiplayerConfigured && Boolean(process.env.SUPABASE_SERVICE_ROLE_KEY);
}

/** The signed-in user, or null. Never throws - callers decide what that means. */
export async function currentUserId(): Promise<string | null> {
  const supabase = supabaseFromRequest();
  if (!supabase) return null;
  const { data } = await supabase.auth.getUser();
  return data.user?.id ?? null;
}
