import { NextResponse } from "next/server";
import { z } from "zod";
import { actOnSession, getSession, startSession } from "@/lib/server/sessions";

/**
 * Solo play, in one endpoint.
 *
 * The session is a signed token rather than a server-side id, and a token runs
 * to tens of kilobytes, so it travels in the body. That also keeps game state
 * out of URLs, logs and browser history.
 */
const bodySchema = z.discriminatedUnion("intent", [
  z.object({ intent: z.literal("start"), caseId: z.string() }),
  z.object({ intent: z.literal("resume"), token: z.string() }),
  z.object({
    intent: z.literal("act"),
    token: z.string(),
    action: z.discriminatedUnion("type", [
      z.object({ type: z.literal("travel"), locationId: z.string() }),
      z.object({ type: z.literal("search") }),
      z.object({ type: z.literal("interview"), npcId: z.string(), questionId: z.string() }),
      z.object({ type: z.literal("lab"), clueId: z.string() }),
      z.object({
        type: z.literal("accuse"),
        culpritId: z.string(),
        motiveId: z.string(),
        evidenceIds: z.array(z.string()),
      }),
    ]),
  }),
]);

export async function POST(request: Request) {
  try {
    return await handle(request);
  } catch (e) {
    // Without this, a thrown error becomes an empty 500 and the client reports
    // "Unexpected end of JSON input" - which says nothing about the real cause.
    // The most likely one by far is a missing SESSION_SECRET in production.
    console.error("[/api/game]", e);
    return NextResponse.json(
      { error: (e as Error).message ?? "The office is not answering." },
      { status: 500 },
    );
  }
}

async function handle(request: Request) {
  const parsed = bodySchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "Malformed request." }, { status: 400 });
  }

  if (parsed.data.intent === "start") {
    const snapshot = await startSession(parsed.data.caseId);
    if (!snapshot) return NextResponse.json({ error: "No such case." }, { status: 404 });
    return NextResponse.json(snapshot);
  }

  if (parsed.data.intent === "resume") {
    const snapshot = await getSession(parsed.data.token);
    if (!snapshot) {
      return NextResponse.json(
        { error: "That case file is no longer open." },
        { status: 404 },
      );
    }
    return NextResponse.json(snapshot);
  }

  const outcome = await actOnSession(parsed.data.token, parsed.data.action);
  if (!outcome.ok) {
    return NextResponse.json({ error: outcome.error }, { status: outcome.status });
  }
  return NextResponse.json(outcome.snapshot);
}
