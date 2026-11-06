"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { getApi } from "@/lib/api";
import { useSession } from "@/components/session";
import { ErrorBox, Loading } from "@/components/ui";

// One verification per token, even if the effect runs twice (StrictMode) or the page re-renders.
const inflight = new Map<string, Promise<string | null>>();
function verifyOnce(token: string): Promise<string | null> {
  let p = inflight.get(token);
  if (!p) {
    p = getApi().verifyLink(token);
    inflight.set(token, p);
  }
  return p;
}

function Verify() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const router = useRouter();
  const { refresh } = useSession();
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (!token) throw new Error("Thiếu mã đăng nhập trong liên kết.");
        const redirect = await verifyOnce(token);
        if (redirect) {
          // Real gateway: GET /auth/verify sets the cookie and redirects back to the app.
          window.location.replace(redirect);
          return;
        }
        const me = await refresh();
        if (alive) router.replace(me?.onboarding_state === "active" ? "/chat" : "/onboarding");
      } catch (e) {
        if (alive) setError(e);
      }
    })();
    return () => {
      alive = false;
    };
  }, [token, refresh, router]);

  if (error) {
    return (
      <div className="center-screen">
        <div className="auth-card card">
          <h1>Không đăng nhập được</h1>
          <ErrorBox error={error} />
          <Link className="btn" href="/login">
            Quay lại đăng nhập
          </Link>
        </div>
      </div>
    );
  }
  return <Loading full label="Đang đăng nhập…" />;
}

export default function VerifyPage() {
  return (
    <Suspense fallback={<Loading full />}>
      <Verify />
    </Suspense>
  );
}
