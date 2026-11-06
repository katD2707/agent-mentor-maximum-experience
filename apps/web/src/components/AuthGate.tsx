"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import type { Role } from "@/lib/types";
import { useSession } from "./session";
import { ErrorBox, Loading } from "./ui";

/** Renders children only for a signed-in user who finished onboarding. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status, me, error, refresh } = useSession();
  const router = useRouter();

  const target =
    status === "anon" ? "/login" : status === "ready" && me && me.onboarding_state !== "active" ? "/onboarding" : null;

  useEffect(() => {
    if (target) router.replace(target);
  }, [target, router]);

  if (status === "error") {
    return (
      <div className="center-screen">
        <div className="auth-card">
          <ErrorBox error={new Error(error ?? "Lỗi không xác định")} onRetry={() => void refresh()} />
        </div>
      </div>
    );
  }
  if (status !== "ready" || !me || target) return <Loading full />;
  return <>{children}</>;
}

/** Sends users of the other role to `fallback` (e.g. NCS on /learning → /research). */
export function RoleGate({ role, fallback, children }: { role: Role; fallback: string; children: ReactNode }) {
  const { me } = useSession();
  const router = useRouter();
  const wrong = !!me && me.role !== role;
  useEffect(() => {
    if (wrong) router.replace(fallback);
  }, [wrong, fallback, router]);
  if (wrong) return <Loading />;
  return <>{children}</>;
}
