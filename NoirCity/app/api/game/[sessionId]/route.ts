import { NextResponse } from "next/server";
import { z } from "zod";
import { actOnSession, getSession } from "@/lib/server/sessions";

/**
 * Every action the player takes lands here. The server owns the case file and
 * the game state; the client sends an intent and gets back a redacted view.
 * A rejected action costs nothing, so spamming it is pointless.
 */
const actionSchema = z.discriminatedUnion("type", [
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
]);

type Params = { params: Promise<{ sessionId: string }> };

export async function GET(_request: Request, { params }: Params) {
  const { sessionId } = await params;
  const snapshot = getSession(sessionId);
  if (!snapshot) {
    return NextResponse.json({ error: "That case file is no longer open." }, { status: 404 });
  }
  return NextResponse.json(snapshot);
}

export async function POST(request: Request, { params }: Params) {
  const { sessionId } = await params;
  const parsed = actionSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "Malformed action." }, { status: 400 });
  }

  const outcome = actOnSession(sessionId, parsed.data);
  if (!outcome.ok) {
    return NextResponse.json({ error: outcome.error }, { status: outcome.status });
  }
  return NextResponse.json(outcome.snapshot);
}
