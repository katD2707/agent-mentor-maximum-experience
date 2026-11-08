import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { isTauri } from "../lib/platform";
import { canRestart, checkNow, CHECK_EVERY_MS, getUpdateStatus, installUpdate, isBusyRoute, setUpdateStatus, subscribeUpdate } from "../lib/updater";

/** Desktop only: a quiet line while a new version downloads, then it restarts the app when the learner is idle. */
export function UpdateNotice() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const status = useSyncExternalStore(subscribeUpdate, getUpdateStatus);
  const setStatus = setUpdateStatus;
  const path = useRef(pathname);
  path.current = pathname;
  const lastInput = useRef(Date.now());
  const desktop = isTauri();

  const check = useCallback(() => void checkNow(), []);

  useEffect(() => {
    if (!desktop) return;
    const first = setTimeout(check, 15_000);
    const every = setInterval(check, CHECK_EVERY_MS);
    const touch = () => (lastInput.current = Date.now());
    const events = ["pointerdown", "keydown", "wheel"] as const;
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    return () => {
      clearTimeout(first);
      clearInterval(every);
      events.forEach((e) => window.removeEventListener(e, touch));
    };
  }, [desktop, check]);

  const ready = status.kind === "ready" ? status.version : null;
  useEffect(() => {
    if (!ready) return;
    const tick = setInterval(() => {
      if (canRestart({ path: path.current, hidden: document.visibilityState === "hidden", idleMs: Date.now() - lastInput.current })) void installUpdate(ready, setStatus);
    }, 5_000);
    return () => clearInterval(tick);
  }, [ready]);

  if (!desktop || status.kind === "none") return null;
  return (
    <div className="update-note" role="status">
      <span>
        {status.kind === "downloading" && t("update.downloading")}
        {status.kind === "downloading" && status.percent !== null && <b className="upd-pct">{status.percent}%</b>}
        {status.kind === "ready" && t("update.ready")}
        {status.kind === "installing" && t("update.installing")}
        {status.kind === "failed" && t("update.failed")}
      </span>
      {status.kind === "downloading" && status.percent !== null && (
        <span className="upd-bar" role="progressbar" aria-label={t("update.downloading")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={status.percent}>
          <i style={{ width: `${status.percent}%` }} />
        </span>
      )}
      {status.kind === "ready" && !isBusyRoute(pathname) && (
        <button type="button" onClick={() => void installUpdate(status.version, setStatus)}>
          {t("update.restart")}
        </button>
      )}
      {status.kind === "failed" && (
        <button type="button" onClick={check}>
          {t("update.retry")}
        </button>
      )}
    </div>
  );
}
