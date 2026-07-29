"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ensureAnonymousUser } from "@/lib/supabase/browser";
import type { RoomSnapshot } from "@/lib/game/types";

const NAME_KEY = "noircity:name";

function rememberedName(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(NAME_KEY) ?? "";
}

async function openRoom(body: unknown): Promise<RoomSnapshot> {
  await ensureAnonymousUser();
  const res = await fetch("/api/rooms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const parsed = await res.json();
  if (!res.ok) throw new Error(parsed.error ?? "Could not open the room.");
  return parsed;
}

/** "Play with friends" on a case card. */
export function HostButton({
  caseId,
  enabled,
}: {
  caseId: string;
  enabled: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(rememberedName);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!enabled) {
    return (
      <span
        title="Set NEXT_PUBLIC_SUPABASE_URL and friends to enable rooms"
        className="cursor-not-allowed text-[11px] tracking-[0.2em] text-neutral-800"
      >
        WITH FRIENDS &mdash; NOT CONFIGURED
      </span>
    );
  }

  async function host() {
    setBusy(true);
    setError(null);
    try {
      const room = await openRoom({ intent: "create", caseId, displayName: name.trim() });
      localStorage.setItem(NAME_KEY, name.trim());
      router.push(`/room/${room.gameId}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-[11px] tracking-[0.2em] text-neutral-500 transition hover:text-amber-100"
      >
        PLAY WITH FRIENDS &rarr;
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && name.trim() && host()}
        placeholder="Your name"
        maxLength={24}
        className="border border-neutral-800 bg-transparent px-3 py-1.5 font-serif text-[13px] text-neutral-200 outline-none placeholder:text-neutral-700 focus:border-amber-200/40"
      />
      <button
        disabled={busy || !name.trim()}
        onClick={host}
        className="border border-neutral-700 px-4 py-1.5 text-[11px] tracking-[0.2em] text-neutral-300 transition hover:border-amber-200/50 hover:text-amber-100 disabled:opacity-30"
      >
        {busy ? "OPENING..." : "OPEN A ROOM"}
      </button>
      {error && <span className="text-[11px] text-red-400">{error}</span>}
    </div>
  );
}

/** Join-by-code, for the five people who did not open the room. */
export function JoinBox({ enabled }: { enabled: boolean }) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [name, setName] = useState(rememberedName);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!enabled) return null;

  async function join() {
    setBusy(true);
    setError(null);
    try {
      const room = await openRoom({
        intent: "join",
        roomCode: code.trim().toUpperCase(),
        displayName: name.trim(),
      });
      localStorage.setItem(NAME_KEY, name.trim());
      router.push(`/room/${room.gameId}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const ready = code.trim().length >= 3 && name.trim().length > 0;

  return (
    <section className="mt-16 border-t border-neutral-900 pt-10">
      <p className="text-[10px] tracking-[0.3em] text-neutral-600">
        SOMEBODY GAVE YOU A CODE
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && ready && join()}
          placeholder="CODE"
          maxLength={8}
          className="w-28 border border-neutral-800 bg-transparent px-3 py-2 text-center font-serif text-lg tracking-[0.3em] text-amber-100 outline-none placeholder:text-neutral-700 focus:border-amber-200/40"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ready && join()}
          placeholder="Your name"
          maxLength={24}
          className="border border-neutral-800 bg-transparent px-3 py-2 font-serif text-[14px] text-neutral-200 outline-none placeholder:text-neutral-700 focus:border-amber-200/40"
        />
        <button
          disabled={busy || !ready}
          onClick={join}
          className="border border-neutral-700 px-5 py-2 text-[11px] tracking-[0.2em] text-neutral-300 transition hover:border-amber-200/50 hover:text-amber-100 disabled:opacity-30"
        >
          {busy ? "JOINING..." : "JOIN THE CASE"}
        </button>
      </div>
      {error && <p className="mt-3 text-[12px] text-red-400">{error}</p>}
    </section>
  );
}
