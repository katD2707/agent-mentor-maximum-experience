"use client";

import { useParams } from "next/navigation";
import { Player } from "@/components/practice/Player";

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  return <Player sessionId={id} />;
}
