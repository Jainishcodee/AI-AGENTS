import { NextResponse } from "next/server";
import { z } from "zod";
import { createRoom, isFail, joinRoom } from "@/lib/server/rooms";
import { currentUserId, multiplayerReady } from "@/lib/supabase/server";

const bodySchema = z.union([
  z.object({
    intent: z.literal("create"),
    caseId: z.string(),
    displayName: z.string().trim().min(1).max(24),
  }),
  z.object({
    intent: z.literal("join"),
    roomCode: z.string().trim().min(3).max(8),
    displayName: z.string().trim().min(1).max(24),
  }),
]);

export async function POST(request: Request) {
  if (!multiplayerReady()) {
    return NextResponse.json(
      { error: "Multiplayer is not configured on this server." },
      { status: 503 },
    );
  }

  const userId = await currentUserId();
  if (!userId) {
    return NextResponse.json({ error: "Sign in first." }, { status: 401 });
  }

  const parsed = bodySchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "Malformed request." }, { status: 400 });
  }

  const result =
    parsed.data.intent === "create"
      ? await createRoom(userId, parsed.data.caseId, parsed.data.displayName)
      : await joinRoom(userId, parsed.data.roomCode, parsed.data.displayName);

  if (isFail(result)) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }
  return NextResponse.json(result);
}
