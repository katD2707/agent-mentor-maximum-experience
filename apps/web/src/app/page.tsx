"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useSession } from "@/components/session";
import { Loading } from "@/components/ui";

export default function Home() {
  const { status, me } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "anon") router.replace("/login");
    else if (status === "ready" && me) router.replace(me.onboarding_state === "active" ? "/chat" : "/onboarding");
  }, [status, me, router]);

  return <Loading full />;
}
