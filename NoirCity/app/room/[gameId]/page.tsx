import { RoomScreen } from "./RoomScreen";

export default async function RoomPage({
  params,
}: {
  params: Promise<{ gameId: string }>;
}) {
  const { gameId } = await params;
  return <RoomScreen gameId={gameId} />;
}
