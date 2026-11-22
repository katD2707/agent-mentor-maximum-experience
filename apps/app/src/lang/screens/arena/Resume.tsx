import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { practice, type PSession } from "../../../api";
import { useAuth } from "../../../state/auth";
import { answeredCount, clockText, initialRemaining, unfinished } from "../../../lib/practice";

/** "Làm tiếp bài đang dở": the unfinished session the server still holds (a running exam or a half-done practice). */
export function ResumeCard({ back, only }: { back: string; only?: (s: PSession) => boolean }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [active, setActive] = useState<PSession | null>(null);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    practice.active(token).then(
      (s) => alive && setActive(unfinished(s) && (!only || only(s)) ? s : null),
      () => undefined,
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  if (!active) return null;
  return (
    <div className="ar-resume" data-testid="resume">
      <div>
        <h2>{t("lg.ar.resumeTitle")}</h2>
        <p className="ar-muted">{active.kind === "practice" ? t("lg.ar.resumeBody", { done: answeredCount(active), total: active.items.length }) : t("lg.ar.resumeMock", { time: clockText(initialRemaining(active, Date.now()) ?? 0) })}</p>
      </div>
      <Link className="ar-btn" to={`/luyen-tap/${encodeURIComponent(active.id)}`} state={{ back }}>
        {t("lg.ar.resumeBtn")}
      </Link>
    </div>
  );
}
