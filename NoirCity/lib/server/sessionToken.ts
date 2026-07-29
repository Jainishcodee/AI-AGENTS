import "server-only";
import type { GameState } from "@/lib/engine/reducer";
import type { FeedEntry } from "@/lib/game/types";

/**
 * Stateless solo sessions.
 *
 * The old version kept a Map in server memory. That cannot work on Cloudflare —
 * a Worker isolate is torn down between requests, so the second action in a game
 * may well land somewhere that has never heard of the first.
 *
 * So the session travels with the player instead, as an opaque token: the game
 * state, plus an HMAC over it. The client cannot read anything useful out of it
 * and cannot forge one, because it does not have the key. The server trusts the
 * signature, not the client.
 *
 * This is strictly better than the Map even off Cloudflare: a game now survives
 * a server restart, and there is nothing to evict.
 */

export interface SessionPayload {
  caseId: string;
  state: GameState;
  feed: FeedEntry[];
}

/** Long games are finite; this only stops a pathological token from growing. */
const MAX_FEED = 250;

function secretMaterial(): string {
  const secret = process.env.SESSION_SECRET;
  if (secret && secret.length >= 16) return secret;

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "SESSION_SECRET must be set (32+ random characters) in production.",
    );
  }
  // Development only. Tokens do not survive a change of this value, which is
  // exactly what you want if it ever reaches production by accident.
  return "noircity-development-only-session-secret";
}

let keyPromise: Promise<CryptoKey> | null = null;

function hmacKey(): Promise<CryptoKey> {
  if (!keyPromise) {
    keyPromise = crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(secretMaterial()),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign", "verify"],
    );
  }
  return keyPromise;
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64Url(text: string): Uint8Array {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

export async function signSession(payload: SessionPayload): Promise<string> {
  const trimmed: SessionPayload = {
    ...payload,
    feed: payload.feed.slice(-MAX_FEED),
  };
  const body = new TextEncoder().encode(JSON.stringify(trimmed));
  const signature = await crypto.subtle.sign("HMAC", await hmacKey(), body);
  return `${toBase64Url(body)}.${toBase64Url(new Uint8Array(signature))}`;
}

/** Returns null for anything tampered with, truncated, or from another secret. */
export async function verifySession(
  token: string,
): Promise<SessionPayload | null> {
  const dot = token.indexOf(".");
  if (dot < 1) return null;

  try {
    const body = fromBase64Url(token.slice(0, dot));
    const signature = fromBase64Url(token.slice(dot + 1));

    // Constant-time comparison, courtesy of the platform.
    const ok = await crypto.subtle.verify(
      "HMAC",
      await hmacKey(),
      signature as BufferSource,
      body as BufferSource,
    );
    if (!ok) return null;

    return JSON.parse(new TextDecoder().decode(body)) as SessionPayload;
  } catch {
    return null;
  }
}
