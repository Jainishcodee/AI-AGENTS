import { NextResponse } from "next/server";
import { z } from "zod";
import { ARGUMENT_LIMIT } from "@/lib/engine/scoring";
import { actInRoom, getRoom, isFail, startRoom } from "@/lib/server/rooms";
import { currentUserId, multiplayerReady } from "@/lib/supabase/server";

/**
 * Every in-game move for a multiplayer room. Identical validation to the
 * single-player route, because it is the same engine underneath - the only
 * difference is who else finds out about it.
 */
const bodySchema = z.union([
  z.object({ intent: z.literal("start") }),
  z.object({
    intent: z.literal("act"),
    action: z.discriminatedUnion("type", [
      z.object({ type: z.literal("travel"), locationId: z.string() }),
      z.object({ type: z.literal("search") }),
      z.object({ type: z.literal("interview"), npcId: z.string(), questionId: z.string() }),
      z.object({ type: z.literal("lab"), clueId: z.string() }),
      z.object({
        type: z.literal("accuse"),
        // No `grade` field, deliberately. Zod strips what it does not
        // declare, so a client cannot mark its own accusation.
        culpritName: z.string().min(1).max(120),
        argument: z.string().min(1).max(ARGUMENT_LIMIT),
      }),
    ]),
  }),
]);

type Params = { params: Promise<{ gameId: string }> };

async function requireUser() {
  if (!multiplayerReady()) {
    return {
      response: NextResponse.json(
        { error: "Multiplayer is not configured on this server." },
        { status: 503 },
      ),
    };
  }
  const userId = await currentUserId();
  if (!userId) {
    return { response: NextResponse.json({ error: "Sign in first." }, { status: 401 }) };
  }
  return { userId };
}

export async function GET(_request: Request, { params }: Params) {
  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  const { gameId } = await params;
  const result = await getRoom(auth.userId, gameId);
  if (isFail(result)) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }
  return NextResponse.json(result);
}

export async function POST(request: Request, { params }: Params) {
  const auth = await requireUser();
  if ("response" in auth) return auth.response;

  const { gameId } = await params;
  const parsed = bodySchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "Malformed request." }, { status: 400 });
  }

  const result =
    parsed.data.intent === "start"
      ? await startRoom(auth.userId, gameId)
      : await actInRoom(auth.userId, gameId, parsed.data.action);

  if (isFail(result)) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }
  return NextResponse.json(result);
}
