/**
 * SSE over POST.
 *
 * `EventSource` cannot POST, and the deliberation request carries a body, so the
 * stream is read off `fetch`'s ReadableStream and framed by hand. That is a dozen
 * lines and avoids both a dependency and the usual workaround of stuffing the
 * question into a query string.
 */

import type { StreamEvent } from "./types";

const FRAME_SEPARATOR = /\r?\n\r?\n/;

export async function* streamEvents(
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch("/api/council/council/deliberate", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok || !response.body) {
    let detail = `HTTP ${response.status}`;
    try {
      const parsed = await response.json();
      detail = parsed?.detail ?? detail;
    } catch {
      /* non-JSON error body; the status is all we have */
    }
    yield { type: "error", payload: { message: detail, recoverable: false } };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // A frame is complete only at a blank line; anything after the last one is
      // a partial frame and must stay in the buffer.
      const frames = buffer.split(FRAME_SEPARATOR);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = parseFrame(frame);
        if (event) yield event;
      }
    }
    const trailing = parseFrame(buffer);
    if (trailing) yield trailing;
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): StreamEvent | null {
  const trimmed = frame.trim();
  if (!trimmed) return null;

  let type = "";
  const dataLines: string[] = [];
  for (const line of trimmed.split(/\r?\n/)) {
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;

  try {
    const parsed = JSON.parse(dataLines.join("\n"));
    return { type: (parsed.type ?? type) as StreamEvent["type"], payload: parsed.payload ?? {} };
  } catch {
    return null;
  }
}

export async function getJSON<T>(path: string): Promise<T> {
  const response = await fetch(`/api/council/${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json() as Promise<T>;
}
