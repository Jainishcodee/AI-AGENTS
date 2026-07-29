"use client";

import { useCallback, useRef, useState } from "react";
import type { PublicClue } from "@/lib/engine/view";
import type { Suspect } from "@/lib/engine/caseSchema";
import { CARD, type Board } from "@/lib/game/useBoard";

/**
 * Where six people argue.
 *
 * The corkboard has no mechanical effect whatsoever — no clue is worth more for
 * being linked, no accusation is helped by a tidy board. It exists because a
 * shared surface is what turns "I think it was the doctor" into an argument with
 * evidence on it, and that argument is the game.
 */
export function Corkboard({
  clues,
  suspects,
  board,
  onClose,
}: {
  clues: PublicClue[];
  suspects: Suspect[];
  /** Owned by the caller, which stays mounted - closing the board must not
   *  throw away an arrangement the team spent the last twenty minutes on. */
  board: Board;
  onClose: () => void;
}) {
  const surfaceRef = useRef<HTMLDivElement>(null);

  const [dragging, setDragging] = useState<string | null>(null);
  const [linkFrom, setLinkFrom] = useState<string | null>(null);
  const offset = useRef({ x: 0, y: 0 });
  // A drag ends with a click event, and by then `dragging` has already been
  // cleared - so without this, repositioning a card would also arm it for
  // string. Anything past a few pixels was a drag, not a click.
  const dragOrigin = useRef({ x: 0, y: 0 });
  const wasDrag = useRef(false);

  const byId = new Map(clues.map((c) => [c.id, c]));
  const cardOf = (id: string) => board.cards.find((c) => c.clueId === id);

  const pointFromEvent = useCallback((e: { clientX: number; clientY: number }) => {
    const rect = surfaceRef.current?.getBoundingClientRect();
    const scroll = surfaceRef.current;
    if (!rect || !scroll) return { x: 0, y: 0 };
    return {
      x: e.clientX - rect.left + scroll.scrollLeft,
      y: e.clientY - rect.top + scroll.scrollTop,
    };
  }, []);

  function startDrag(e: React.PointerEvent, clueId: string) {
    const card = cardOf(clueId);
    if (!card) return;
    const p = pointFromEvent(e);
    offset.current = { x: p.x - card.x, y: p.y - card.y };
    dragOrigin.current = { x: e.clientX, y: e.clientY };
    wasDrag.current = false;
    setDragging(clueId);
    (e.target as Element).setPointerCapture?.(e.pointerId);
  }

  const DRAG_THRESHOLD = 4;

  function onMove(e: React.PointerEvent) {
    if (!dragging) return;
    if (
      Math.hypot(
        e.clientX - dragOrigin.current.x,
        e.clientY - dragOrigin.current.y,
      ) > DRAG_THRESHOLD
    ) {
      wasDrag.current = true;
    }
    const p = pointFromEvent(e);
    board.moveCard(
      dragging,
      Math.max(0, p.x - offset.current.x),
      Math.max(0, p.y - offset.current.y),
      false,
    );
  }

  function endDrag() {
    if (!dragging) return;
    const card = cardOf(dragging);
    // One write, on release.
    if (card) board.moveCard(dragging, card.x, card.y, true);
    setDragging(null);
  }

  function handleCardClick(clueId: string) {
    if (wasDrag.current) {
      wasDrag.current = false;
      return;
    }
    if (!linkFrom) {
      setLinkFrom(clueId);
      return;
    }
    if (linkFrom === clueId) {
      setLinkFrom(null);
      return;
    }
    board.toggleLink(linkFrom, clueId);
    setLinkFrom(null);
  }

  const bounds = board.cards.reduce(
    (acc, c) => ({
      w: Math.max(acc.w, c.x + CARD.width + 120),
      h: Math.max(acc.h, c.y + CARD.height + 120),
    }),
    { w: 1200, h: 800 },
  );

  /** Pins a note in the top-left of whatever the board is currently showing. */
  function addNoteInView() {
    const scroll = surfaceRef.current;
    board.addNote((scroll?.scrollLeft ?? 0) + 24, (scroll?.scrollTop ?? 0) + 24);
  }

  return (
    // Beside the map on a desktop, so the evidence list stays readable next to
    // it; over everything on a phone, where sharing the screen with a 68dvh
    // sheet would leave the cork about two cards tall.
    <div className="absolute inset-0 z-[1900] flex flex-col bg-[#0b0a09] max-md:fixed">
      <header className="flex items-center justify-between gap-3 border-b border-neutral-800 px-4 py-2.5 sm:px-6 sm:py-3">
        <div className="min-w-0">
          <h2 className="font-serif text-base text-neutral-100 sm:text-lg">
            The Board
          </h2>
          {/* The linking prompt is live feedback and always shows. The idle
              instructions are desktop-only - they name a double-click a phone
              cannot perform, and the buttons beside them say the same thing. */}
          {linkFrom ? (
            <p className="mt-0.5 text-[10px] leading-tight tracking-[0.2em] text-neutral-600">
              PICK A SECOND CARD TO RUN STRING — OR THE SAME ONE TO CANCEL
            </p>
          ) : (
            <p className="mt-0.5 hidden text-[10px] tracking-[0.2em] text-neutral-600 sm:block">
              DRAG TO ARRANGE · CLICK TWO CARDS TO CONNECT · DOUBLE-CLICK THE CORK
              FOR A NOTE
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={addNoteInView}
            className="border border-neutral-700 px-3 py-2 text-[10px] tracking-[0.2em] text-neutral-400 transition hover:border-amber-200/50 hover:text-amber-100 sm:hidden"
          >
            + NOTE
          </button>
          <button
            onClick={onClose}
            className="border border-neutral-700 px-3 py-2 text-[10px] tracking-[0.2em] text-neutral-400 transition hover:border-amber-200/50 hover:text-amber-100 sm:px-4 sm:py-1.5"
          >
            <span className="sm:hidden">DONE</span>
            <span className="hidden sm:inline">BACK TO THE CASE</span>
          </button>
        </div>
      </header>

      <div
        ref={surfaceRef}
        onPointerMove={onMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className="relative flex-1 overflow-auto"
        style={{
          // Cork, approximated: warm base plus a fine speckle.
          backgroundColor: "#241c14",
          backgroundImage:
            "radial-gradient(rgba(255,220,170,0.05) 1px, transparent 1px), radial-gradient(rgba(0,0,0,0.25) 1px, transparent 1px)",
          backgroundSize: "7px 7px, 11px 11px",
          backgroundPosition: "0 0, 3px 5px",
        }}
      >
        {/* The cork itself. Always at least as big as the viewport, so a
            double-click on empty space lands here and not on the scroll box. */}
        <div
          onDoubleClick={(e) => {
            if (e.target !== e.currentTarget) return;
            const p = pointFromEvent(e);
            board.addNote(Math.max(0, p.x - 84), Math.max(0, p.y - 40));
          }}
          style={{
            width: bounds.w,
            height: bounds.h,
            minWidth: "100%",
            minHeight: "100%",
            position: "relative",
          }}
        >
          <svg
            className="pointer-events-none absolute inset-0"
            width={bounds.w}
            height={bounds.h}
          >
            {board.links.map((link) => {
              const a = cardOf(link.from);
              const b = cardOf(link.to);
              if (!a || !b) return null;
              const ax = a.x + CARD.width / 2;
              const ay = a.y + CARD.height / 2;
              const bx = b.x + CARD.width / 2;
              const by = b.y + CARD.height / 2;
              // A slight sag, because string does not run straight.
              const midY = (ay + by) / 2 + Math.abs(bx - ax) * 0.06 + 10;
              return (
                <path
                  key={link.id}
                  className="board-string"
                  d={`M ${ax} ${ay} Q ${(ax + bx) / 2} ${midY} ${bx} ${by}`}
                  fill="none"
                  stroke="#b1402f"
                  strokeWidth="2"
                  opacity="0.75"
                />
              );
            })}
          </svg>

          {board.notes.map((note) => (
            <StickyNote
              key={note.id}
              note={note}
              onChange={(body) => board.updateNote(note.id, body)}
              onRemove={() => board.removeNote(note.id)}
            />
          ))}

          {board.cards.map((card) => {
            const clue = byId.get(card.clueId);
            if (!clue) return null;
            const suspect = clue.implicates
              ? suspects.find((s) => s.id === clue.implicates)
              : null;
            const selected = linkFrom === card.clueId;

            return (
              <article
                key={card.clueId}
                onPointerDown={(e) => startDrag(e, card.clueId)}
                onClick={() => handleCardClick(card.clueId)}
                style={{
                  left: card.x,
                  top: card.y,
                  width: CARD.width,
                  minHeight: CARD.height,
                }}
                className={`absolute cursor-grab touch-none select-none border p-3 shadow-lg transition-colors active:cursor-grabbing ${
                  selected
                    ? "border-amber-300 bg-[#f3ead6]"
                    : "border-neutral-400/40 bg-[#e8e0cf]"
                }`}
              >
                {/* The pin */}
                <span className="absolute -top-1.5 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full bg-red-700 shadow" />
                <p className="text-[8px] tracking-[0.2em] text-neutral-500">
                  {clue.type.toUpperCase()}
                </p>
                <h3 className="mt-1 font-serif text-[13px] leading-tight text-neutral-900">
                  {clue.title}
                </h3>
                {suspect && (
                  <p className="mt-1.5 text-[10px] italic text-red-900/80">
                    points at {suspect.name}
                  </p>
                )}
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function StickyNote({
  note,
  onChange,
  onRemove,
}: {
  note: { id: string; x: number; y: number; body: string };
  onChange: (body: string) => void;
  onRemove: () => void;
}) {
  return (
    <div
      style={{ left: note.x, top: note.y }}
      className="absolute w-[168px] bg-[#d8cf7a] p-2 shadow-lg"
    >
      <button
        onClick={onRemove}
        className="absolute right-0 top-0 flex h-7 w-7 items-center justify-center text-[15px] leading-none text-neutral-700/60 hover:text-neutral-900"
        aria-label="Remove note"
      >
        ×
      </button>
      <textarea
        value={note.body}
        onChange={(e) => onChange(e.target.value.slice(0, 300))}
        placeholder="..."
        rows={3}
        // 16px on a phone: anything smaller and Safari zooms the whole board in
        // the moment the note takes focus.
        className="w-full resize-none bg-transparent pr-3 font-serif text-[16px] leading-snug text-neutral-900 outline-none placeholder:text-neutral-700/50 sm:text-[12px]"
      />
    </div>
  );
}
