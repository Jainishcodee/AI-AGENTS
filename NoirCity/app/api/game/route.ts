import { NextResponse } from "next/server";
import { z } from "zod";
import { startSession } from "@/lib/server/sessions";

const bodySchema = z.object({ caseId: z.string() });

export async function POST(request: Request) {
  const parsed = bodySchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "Expected { caseId }." }, { status: 400 });
  }

  const snapshot = startSession(parsed.data.caseId);
  if (!snapshot) {
    return NextResponse.json({ error: "No such case." }, { status: 404 });
  }
  return NextResponse.json(snapshot);
}
