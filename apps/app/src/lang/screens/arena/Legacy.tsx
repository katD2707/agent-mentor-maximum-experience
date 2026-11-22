import { useEffect } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { practice, PracticeError } from "../../../api";
import { useAuth } from "../../../state/auth";

/**
 * `/luyen-tap` without a session id. Quick practice and notes review start from the village tray, so a bare link lands in the
 * village; `/luyen-tap?notes=<id>` (a notes review reminder) still starts that review and opens its session.
 */
export function PracticeEntry() {
  const [params] = useSearchParams();
  const notes = params.get("notes");
  const { token } = useAuth();
  const nav = useNavigate();
  useEffect(() => {
    if (!token || !notes) return;
    const state = { back: "/" };
    practice.start(token, { source: `notes:${notes}` }).then(
      (s) => nav(`/luyen-tap/${encodeURIComponent(s.id)}`, { replace: true, state }),
      (e) => {
        if (e instanceof PracticeError && e.code === "active_session" && typeof e.body.session_id === "string") nav(`/luyen-tap/${encodeURIComponent(e.body.session_id)}`, { replace: true, state });
        else nav("/", { replace: true });
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, notes]);
  if (notes) return <div className="boot" />;
  return <Navigate to="/" replace />;
}
