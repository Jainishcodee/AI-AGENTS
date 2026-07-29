import { defineCloudflareConfig } from "@opennextjs/cloudflare";

/**
 * Deliberately plain.
 *
 * OpenNext can wire up KV or R2 for incremental caching, but nothing here needs
 * it: every page is either static or rendered per request, solo sessions live in
 * a signed token the player carries, and multiplayer state lives in Supabase.
 * There is no server-side cache worth persisting, so there is no cache binding
 * to get wrong.
 */
export default defineCloudflareConfig();
