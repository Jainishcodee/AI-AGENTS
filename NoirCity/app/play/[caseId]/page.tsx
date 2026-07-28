import { notFound } from "next/navigation";
import { loadCase } from "@/lib/server/cases";
import { GameScreen } from "./GameScreen";

export default async function PlayPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  // Fail here rather than after the client has mounted a map for a case that
  // does not exist.
  if (!loadCase(caseId)) notFound();

  return <GameScreen caseId={caseId} />;
}
