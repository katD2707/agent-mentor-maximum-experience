import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { researchApi, type Experiment } from "../../api/research";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { errCode } from "./util";

/** "Nhật ký thí nghiệm": a one-line composer with an optional photo of a result table, and the latest entries. */
export function ExperimentLog({ items, onChanged }: { items: Experiment[]; onChanged: () => void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const pick = useRef<HTMLInputElement>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || busy || !text.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const photo_path = photo ? (await researchApi.upload(token, photo, photo.name)).path : undefined;
      await researchApi.createExperiment(token, { text: text.trim(), ...(photo_path ? { photo_path } : {}) });
      setText("");
      setPhoto(null);
      onChanged();
    } catch (e2) {
      setErr(t(`research.err.${errCode(e2)}`, { defaultValue: t("research.err.unknown") }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rs-card rs-log" data-guide="research-log" data-guide-label={t("research.log.title")}>
      <h2 className="rs-s">{t("research.log.title")}</h2>
      <form className="rs-logbox" onSubmit={submit}>
        <textarea
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          aria-label={t("research.log.label")}
          placeholder={t("research.log.placeholder")}
          disabled={busy}
        />
        <button className={"rs-c-btn" + (photo ? " on" : "")} type="button" aria-label={t("research.log.photo")} aria-pressed={!!photo} onClick={() => pick.current?.click()}>
          <Icon name="camera" />
        </button>
        <input ref={pick} type="file" accept="image/*" hidden onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
        <button className="rs-c-btn rs-c-send" type="submit" aria-label={t("research.log.send")} disabled={busy || !text.trim()}>
          <Icon name="up" />
        </button>
      </form>
      {photo && (
        <p className="rs-photo small">
          <Icon name="image" />
          <span>{photo.name}</span>
          <button type="button" className="rs-iconbtn" aria-label={t("research.log.removePhoto")} onClick={() => setPhoto(null)}>
            <Icon name="x" />
          </button>
        </p>
      )}
      {busy && (
        <p className="rs-working" role="status">
          <span className="rs-spin" aria-hidden="true" />
          {t("research.log.saving")}
        </p>
      )}
      {err && (
        <p className="rs-alert" role="alert">
          {err}
        </p>
      )}
      {items.length === 0 && !busy && <p className="muted small">{t("research.log.empty")}</p>}
      <ul className="rs-exps">
        {items.map((x) => (
          <li key={x.id} className={"rs-exp" + (x.status === "failed" ? " fail" : "")}>
            <div className="rs-top">
              <span className="rs-code">{x.id}</span>
              <span className={x.status === "failed" ? "tag err" : x.status === "done" ? "tag ok" : x.status === "running" ? "tag wait" : "tag"}>{t(`research.log.status.${x.status}`)}</span>
            </div>
            <b>{x.title}</b>
            {x.structured ? (
              <>
                {(x.result || x.user_note || x.next) && (
                  <p>
                    {[x.result, x.user_note && t("research.log.yourNote", { note: x.user_note }), x.next && t("research.log.next", { next: x.next })].filter(Boolean).join(" ")}
                  </p>
                )}
              </>
            ) : (
              x.raw_text !== x.title && <p>{x.raw_text}</p>
            )}
            {x.missing.length > 0 && <p className="rs-nudge">{t(`research.log.missing.${x.missing.join("_")}`)}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
