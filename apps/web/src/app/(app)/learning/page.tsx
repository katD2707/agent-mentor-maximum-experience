"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useMe } from "@/components/session";
import { Loading } from "@/components/ui";

/** Old URL: learning moved into Tiến bộ (THPT); NCS has no such page. */
export default function LearningRedirect() {
  const me = useMe();
  const router = useRouter();
  useEffect(() => {
    router.replace(me.role === "ncs" ? "/research" : "/progress");
  }, [me.role, router]);
  return <Loading />;
}
