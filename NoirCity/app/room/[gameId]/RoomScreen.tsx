"use client";

import { useState } from "react";
import Link from "next/link";
import { useRoom } from "@/lib/game/useRoom";
import { useChat } from "@/lib/game/useChat";
import { usePresence } from "@/lib/game/usePresence";
import { Investigation } from "@/components/game/Investigation";
import { ChatPanel } from "@/components/game/ChatPanel";
import { Refusal } from "@/app/play/[caseId]/GameScreen";
import type { RoomSnapshot } from "@/lib/game/types";

export function RoomScreen({ gameId }: { gameId: string }) {
  const { room, refusal, loading, fatal, syncing, act, start } = useRoom(gameId);
  const chat = useChat(gameId, room?.players ?? []);
  const online = usePresence(gameId, room?.youId ?? null);

  if (fatal) {
    return (
      <Shell>
        <p className="text-neutral-400">{fatal}</p>
        <Link
          href="/"
          className="mt-4 inline-block text-[11px] tracking-[0.2em] text-neutral-600 hover:text-neutral-300"
        >
          BACK TO THE CASE FILES
        </Link>
      </Shell>
    );
  }

  if (loading || !room) {
    return (
      <Shell>
        <p className="text-[11px] tracking-[0.3em] text-neutral-700">
          JOINING THE ROOM...
        </p>
      </Shell>
    );
  }

  if (room.status === "lobby") {
    return <Lobby room={room} online={online} onStart={start} />;
  }

  return (
    <Investigation
      view={room.view}
      tutorial={room.tutorial}
      feed={room.feed}
      act={act}
      busy={syncing}
      gameId={gameId}
      aside={<Roster room={room} online={online} />}
      banner={refusal ? <Refusal message={refusal} /> : null}
      overlay={
        <ChatPanel
          messages={chat.messages}
          youId={room.youId}
          unread={chat.unread}
          onSend={chat.send}
          onOpen={chat.clearUnread}
        />
      }
    />
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex h-dvh flex-col items-center justify-center bg-[#08090b] text-neutral-300">
      {children}
    </main>
  );
}

function Lobby({
  room,
  online,
  onStart,
}: {
  room: RoomSnapshot;
  online: Set<string>;
  onStart: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const isHost = room.youId === room.hostId;

  async function copy() {
    await navigator.clipboard.writeText(room.roomCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <main className="min-h-dvh bg-[#08090b] text-neutral-300">
      <div className="mx-auto max-w-2xl px-5 py-12 sm:px-8 sm:py-20">
        <p className="text-[10px] tracking-[0.4em] text-neutral-600">
          THE FIRM IS ASSEMBLING
        </p>
        <h1 className="mt-3 font-serif text-3xl text-neutral-100 sm:text-4xl">
          {room.view.title}
        </h1>

        <button
          onClick={copy}
          className="mt-10 block w-full border border-neutral-800 py-6 text-center transition hover:border-amber-200/40 sm:py-8"
        >
          <span className="block text-[10px] tracking-[0.3em] text-neutral-600">
            {copied ? "COPIED" : "ROOM CODE — CLICK TO COPY"}
          </span>
          {/* The code is the whole point of this screen, but eight characters
              at 0.3em tracking will not fit across a phone. */}
          <span className="mt-2 block font-serif text-4xl tracking-[0.2em] text-amber-100 sm:text-6xl sm:tracking-[0.3em]">
            {room.roomCode}
          </span>
        </button>

        <p className="mt-5 text-center font-serif text-[13px] text-neutral-500">
          Read that out to your people. They enter it on the front page.
        </p>

        <section className="mt-12">
          <p className="text-[10px] tracking-[0.3em] text-neutral-600">
            ON THE CASE ({room.players.length} OF {room.maxPlayers})
          </p>
          <ul className="mt-4 divide-y divide-neutral-900 border-y border-neutral-900">
            {room.players.map((p) => (
              <li
                key={p.userId}
                className="flex items-baseline justify-between py-3"
              >
                <span className="flex items-baseline gap-2 font-serif text-[15px] text-neutral-200">
                  <span
                    title={online.has(p.userId) ? "Connected" : "Not connected"}
                    className={`inline-block h-1.5 w-1.5 rounded-full ${
                      online.has(p.userId) ? "bg-emerald-400" : "bg-neutral-700"
                    }`}
                  />
                  {p.displayName}
                  {p.userId === room.youId && (
                    <span className="text-[10px] tracking-[0.2em] text-neutral-600">
                      YOU
                    </span>
                  )}
                </span>
                {p.isHost && (
                  <span className="text-[10px] tracking-[0.2em] text-amber-200/60">
                    HOST
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>

        <div className="mt-12">
          {isHost ? (
            <button
              onClick={onStart}
              className="w-full border border-amber-200/40 py-4 text-[11px] tracking-[0.3em] text-amber-100 transition hover:bg-amber-100/[0.04]"
            >
              OPEN THE CASE FILE
            </button>
          ) : (
            <p className="text-center font-serif text-[14px] italic text-neutral-600">
              Waiting on{" "}
              {room.players.find((p) => p.isHost)?.displayName ?? "the host"} to
              start.
            </p>
          )}
        </div>

        <p className="mt-10 text-center text-[11px] leading-relaxed text-neutral-700">
          Everyone shares one clock and one board. Any of you can act, and all of
          you will see it.
        </p>
      </div>
    </main>
  );
}

/** Who else is on this case, shown under the HUD during play. */
function Roster({ room, online }: { room: RoomSnapshot; online: Set<string> }) {
  return (
    <div className="shrink-0 border-b border-neutral-800 px-5 py-3 sm:px-6">
      <div className="flex items-center justify-between">
        <p className="text-[10px] tracking-[0.25em] text-neutral-600">
          ROOM {room.roomCode}
        </p>
        <p className="text-[10px] tracking-[0.2em] text-neutral-600">
          {online.size} OF {room.players.length} HERE
        </p>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
        {room.players.map((p) => (
          <li
            key={p.userId}
            className={`flex items-center gap-1.5 text-[12px] ${
              p.userId === room.youId ? "text-amber-100" : "text-neutral-500"
            } ${online.has(p.userId) ? "" : "opacity-40"}`}
          >
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                online.has(p.userId) ? "bg-emerald-400" : "bg-neutral-700"
              }`}
            />
            {p.displayName}
          </li>
        ))}
      </ul>
    </div>
  );
}
