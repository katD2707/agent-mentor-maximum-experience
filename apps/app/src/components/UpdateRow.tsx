import { useState } from "react";
import { useTranslation } from "react-i18next";
import { isTauri } from "../lib/platform";
import { APP_VERSION } from "../lib/version";
import { checkNow, getChannel, setChannel, type CheckResult } from "../lib/updater";

/** Settings popover, desktop only: "Kiểm tra cập nhật" and the early-versions (beta) choice. The web build updates itself on the next launch. */
export function UpdateRow() {
  const { t } = useTranslation();
  const [beta, setBeta] = useState(() => getChannel() === "beta");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);
  if (!isTauri()) return null;

  const run = async () => {
    setBusy(true);
    setResult(null);
    // the check itself ends when the answer is known; a found version keeps downloading in the notice below
    await checkNow((r) => {
      setResult(r);
      setBusy(false);
    });
  };
  const state = busy
    ? t("update.checking")
    : result?.kind === "latest"
      ? t("update.latest", { version: APP_VERSION })
      : result?.kind === "found"
        ? t("update.found", { version: result.version })
        : result?.kind === "error"
          ? t("update.checkFailed")
          : "";

  return (
    <div className="set-row set-upd">
      <span className="set-label">{t("update.title")}</span>
      <span className="upd-line">
        <button type="button" className="set-chip-btn upd-check" disabled={busy} onClick={() => void run()}>
          {t("update.check")}
        </button>
        <span className="upd-state" role="status" aria-live="polite">
          {state}
        </span>
      </span>
      <label className="upd-beta">
        <span>{t("update.beta")}</span>
        <button
          className="set-switch"
          type="button"
          role="switch"
          aria-checked={beta}
          aria-label={t("update.beta")}
          onClick={() => {
            setBeta(!beta);
            setChannel(beta ? "stable" : "beta");
            setResult(null);
          }}
        />
      </label>
    </div>
  );
}
