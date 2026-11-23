import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { practice, PracticeError } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { lg, type NotesSet } from "../../api";

type Load = { s: "loading" } | { s: "error" } | { s: "ready"; rows: NotesSet[] };

/**
 * "Vở ghi": the photo-notes sets the student made in the village chat, to open again and review. Opening a set starts a notes
 * review (`notes:<id>`) from the questions already stored; no AI is called.
 */
export function NotesShelf() {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const nav = useNavigate();
  const [st, setSt] = useState<Load>({ s: "loading" });
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const lang = i18n.language === "en" ? "en-GB" : "vi-VN";

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setSt({ s: "loading" });
    lg.listNotes(token).then(
      (rows) => alive && setSt({ s: "ready", rows }),
      () => alive && setSt({ s: "error" }),
    );
    return () => {
      alive = false;
    };
  }, [token, attempt]);

  const open = useCallback(
    async (id: string) => {
      if (!token || busy) return;
      setBusy(id);
      setErr(false);
      const state = { back: "/thu-vien" };
      try {
        const s = await practice.start(token, { source: `notes:${id}` });
        nav(`/luyen-tap/${encodeURIComponent(s.id)}`, { state });
      } catch (e) {
        if (e instanceof PracticeError && e.code === "active_session" && typeof e.body.session_id === "string") nav(`/luyen-tap/${encodeURIComponent(e.body.session_id)}`, { state });
        else {
          setErr(true);
          setBusy(null);
        }
      }
    },
    [busy, nav, token],
  );

  const day = (iso: string) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(lang, { day: "numeric", month: "numeric" });
  };

  return (
    <section className="lg-notes" aria-labelledby="lg-notes-h" data-guide="notes-shelf">
      <h2 id="lg-notes-h">{t("lg.lib.notes.title")}</h2>
      {st.s === "loading" && (
        <p className="lg-notes-quiet" role="status">
          {t("lg.lib.notes.loading")}
        </p>
      )}
      {st.s === "error" && (
        <p className="lg-notes-quiet" role="alert">
          {t("lg.lib.notes.failed")}{" "}
          <button className="btn-link" type="button" onClick={() => setAttempt((n) => n + 1)}>
            {t("practice.retry")}
          </button>
        </p>
      )}
      {st.s === "ready" && st.rows.length === 0 && <p className="lg-notes-quiet">{t("lg.lib.notes.empty")}</p>}
      {st.s === "ready" && st.rows.length > 0 && (
        <ul className="lg-notes-list">
          {st.rows.map((n) => (
            <li key={n.notes_id}>
              <span className="ico" aria-hidden="true">
                <Icon name="image" />
              </span>
              <div>
                <b>{n.title}</b>
                <small>{[t("lg.lib.notes.meta", { items: n.items, pages: n.pages }), n.created_at ? t("lg.lib.notes.made", { date: day(n.created_at) }) : null, n.next_review_at ? t("lg.lib.notes.next", { date: day(n.next_review_at) }) : null].filter(Boolean).join(" · ")}</small>
              </div>
              <button className="btn btn-primary" type="button" disabled={busy !== null} onClick={() => void open(n.notes_id)}>
                {t("lg.lib.notes.review")}
              </button>
            </li>
          ))}
        </ul>
      )}
      {err && (
        <p className="lg-notes-quiet" role="alert">
          {t("lg.lib.notes.startFailed")}
        </p>
      )}
    </section>
  );
}
