import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { researchApi, streamPaperAsk, SUMMARY_MIN_CHARS, type FeedbackKind, type PaperCard, type PaperDetail, type PaperFeedback, type PaperQA, type RelatedPapers, type ReadStatus } from "../../api/research";
import { useAuth } from "../../state/auth";
import { Settings } from "../../components/Settings";
import { Icon } from "../../components/Icon";
import { resolveDeepLink } from "../../lib/deeplink";
import { RecorderError, startRecording, type Recording } from "../../lib/recorder";
import { SourceChip, SOURCE_NAMES, useSourceKeys } from "./Sources";
import { byline, errCode, extProps, pk, STATUS_TAG } from "./util";

type Load<T> = { status: "loading" } | { status: "error"; code: string } | { status: "ready"; data: T };

const FB_ICON: Record<FeedbackKind, "check" | "x" | "edit"> = { right: "check", inaccurate: "x", missing: "edit" };

/** hs-12: one paper. You write your own summary first; only then Mentor's feedback. Questions and related papers follow. */
export default function Paper() {
  const { t } = useTranslation();
  const { id = "" } = useParams();
  const { token } = useAuth();
  const [d, setD] = useState<Load<PaperDetail>>({ status: "loading" });

  const load = useCallback(() => {
    if (!token) return;
    setD({ status: "loading" });
    researchApi.paper(token, id).then(
      (data) => setD({ status: "ready", data }),
      (e) => setD({ status: "error", code: errCode(e) }),
    );
  }, [token, id]);
  useEffect(load, [load]);

  return (
    <div className="app rs-page">
      <header className="topbar">
        <Link className="icon-btn" to="/nghien-cuu" aria-label={t("research.backToResearch")} data-guide="back" data-guide-label={t("research.backToResearch")}>
          <Icon name="back" />
        </Link>
        <h1 className="page-title">{t("research.paper.title")}</h1>
        <span className="grow" />
        <Settings />
      </header>
      <main className="main rs-main">
        {d.status === "loading" && <p className="muted" role="status">…</p>}
        {d.status === "error" && (
          <p className="rs-rempty" role="alert">
            {t(`research.err.${d.code}`, { defaultValue: t("research.err.unknown") })}{" "}
            <button className="btn-link" type="button" onClick={load}>
              {t("research.retry")}
            </button>
          </p>
        )}
        {d.status === "ready" && <PaperBody id={id} detail={d.data} />}
      </main>
    </div>
  );
}

function PaperBody({ id, detail }: { id: string; detail: PaperDetail }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [entry, setEntry] = useState(detail.entry);
  const [note, setNote] = useState(detail.note);
  const [text, setText] = useState(detail.note.my_summary ?? "");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<"" | "save" | "feedback">("");
  const [err, setErr] = useState<string | null>(null);
  const card = entry.paper;
  const thread = useThread(id);
  const enough = text.trim().length >= SUMMARY_MIN_CHARS;
  const hasSummary = !!note.my_summary && !editing;

  const getFeedback = async (summary: string | null) => {
    if (!token) return;
    setErr(null);
    try {
      if (summary !== null) {
        setBusy("save");
        setNote(await researchApi.putSummary(token, id, summary));
        setEditing(false);
      }
      setBusy("feedback");
      const fb = await researchApi.feedback(token, id);
      setNote((n) => ({ ...n, feedback: fb }));
    } catch (e) {
      setErr(t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") }));
    } finally {
      setBusy("");
    }
  };
  const setStatus = async (s: ReadStatus) => {
    if (!token) return;
    try {
      setEntry(await researchApi.setStatus(token, id, s));
      setErr(null);
    } catch (e) {
      setErr(t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") }));
    }
  };

  const tag = entry.status === "reading" ? t("research.status.reading") : entry.status === "read" ? t("research.status.read") : t("research.status.new");
  return (
    <>
      <div className="rs-wrap rs-paper">
        <header className="rs-head-p">
          <h2>{card.title}</h2>
          <p className="rs-by-l">{[byline(card), card.venue].filter(Boolean).join(" · ")}</p>
          <div className="rs-meta-row">
            <span className={STATUS_TAG[entry.status]}>{tag}</span>
            {detail.thesis_tag && <span className="tag">{detail.thesis_tag}</span>}
            {card.citation_count !== null && <span className="muted small">{t(pk("research.paper.cited", card.citation_count), { count: card.citation_count })}</span>}
            {detail.pdf_url && (
              <a className="btn btn-quiet rs-mini" href={detail.pdf_url} {...extProps}>
                <Icon name="file" />
                <span>{t("research.paper.openPdf")}</span>
              </a>
            )}
          </div>
        </header>

        {entry.reason && (
          <p className="rs-why-p">
            <Icon name="target" />
            <span>{entry.reason}</span>
          </p>
        )}

        <section className="rs-abstract">
          <span className="rs-eyebrow">Abstract</span>
          <p lang="en">{detail.abstract}</p>
        </section>

        {/* 1. the learner writes first */}
        <section className="rs-mine oli" data-guide="research-summary" data-guide-label={t("research.paper.mySummary")}>
          <h3>{t("research.paper.mySummary")}</h3>
          {hasSummary ? (
            <p className="rs-done-text">{note.my_summary}</p>
          ) : (
            <textarea aria-label={t("research.paper.mySummary")} placeholder={t("research.paper.summaryPlaceholder")} value={text} onChange={(e) => setText(e.target.value)} />
          )}
          <div className="rs-act">
            {hasSummary ? (
              <>
                {!note.feedback && (
                  <button className="btn btn-primary" type="button" disabled={busy !== ""} onClick={() => void getFeedback(null)}>
                    {t("research.paper.seeFeedback")}
                  </button>
                )}
                <button className="btn btn-quiet" type="button" onClick={() => { setText(note.my_summary ?? ""); setEditing(true); }}>
                  {t("research.paper.editSummary")}
                </button>
              </>
            ) : (
              <button
                className="btn btn-primary"
                type="button"
                aria-disabled={!enough || busy !== ""}
                onClick={() => enough && busy === "" && void getFeedback(text.trim())}
              >
                {t("research.paper.seeFeedback")}
              </button>
            )}
            {!note.feedback && entry.status !== "read" && (
              <button className="btn btn-quiet" type="button" onClick={() => void setStatus("read")}>
                {t("research.paper.markRead")}
              </button>
            )}
          </div>
          {busy !== "" && (
            <p className="rs-working" role="status">
              <span className="rs-spin" aria-hidden="true" />
              {t(busy === "save" ? "research.paper.saving" : "research.paper.reviewing")}
            </p>
          )}
          {err && (
            <p className="rs-alert" role="alert">
              {err}
            </p>
          )}
        </section>

        {/* 2. feedback, only after the summary */}
        {hasSummary && note.feedback && <FeedbackCard fb={note.feedback} read={entry.status === "read"} onStatus={(s) => void setStatus(s)} />}

        {/* 3. questions about the paper, with sources */}
        <Thread thread={thread} />

        {/* related papers */}
        <Related id={id} />
      </div>
      <AskBar id={id} thread={thread} />
    </>
  );
}

function FeedbackCard({ fb, read, onStatus }: { fb: PaperFeedback; read: boolean; onStatus(s: ReadStatus): void }) {
  const { t } = useTranslation();
  return (
    <section className="rs-fb" aria-labelledby="rs-fb-h">
      <h3 id="rs-fb-h">
        <span className="logo-mark">M</span>
        <span>{t("research.paper.feedbackTitle")}</span>
      </h3>
      {fb.rows.map((r, i) => (
        <div key={i} className={`rs-fr ${r.kind}`}>
          <span className="rs-ic">
            <Icon name={FB_ICON[r.kind]} />
          </span>
          <span className="rs-tx">
            <span className="rs-k">{t(`research.paper.kind.${r.kind}`)}</span>
            <span>{r.text}</span>
          </span>
        </div>
      ))}
      {fb.for_thesis && (
        <p className="rs-link-note">
          <Icon name="target" />
          <span>
            <b>{t("research.paper.forThesis")}</b> {fb.for_thesis}
          </span>
        </p>
      )}
      <div className="rs-act">
        <button className="btn btn-primary" type="button" onClick={() => onStatus(read ? "reading" : "read")}>
          {t(read ? "research.paper.readAgain" : "research.paper.markRead")}
        </button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- questions
interface Pending {
  question: string;
  stage: "searching" | "reading";
}

interface ThreadApi {
  qa: PaperQA[];
  pending: Pending | null;
  error: string | null;
  start(question: string): void;
  stage(s: "searching" | "reading"): void;
  add(qa: PaperQA): void;
  end(error?: string): void;
}

/** The questions asked about this paper (loaded once) and the one being answered. */
function useThread(id: string): ThreadApi {
  const { token } = useAuth();
  const [qa, setQa] = useState<PaperQA[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    researchApi.qa(token, id).then(
      (list) => alive && setQa(list),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [token, id]);
  return {
    qa,
    pending,
    error,
    start: (question) => {
      setError(null);
      setPending({ question, stage: "searching" });
    },
    stage: (stage) => setPending((p) => (p ? { ...p, stage } : p)),
    add: (m) => {
      setQa((l) => [...l.filter((x) => x.id !== m.id), m]);
      setPending(null);
    },
    end: (e) => {
      setPending(null);
      if (e) setError(e);
    },
  };
}

function Thread({ thread }: { thread: ThreadApi }) {
  const { t } = useTranslation();
  const { qa, pending, error } = thread;
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (pending || qa.length) end.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [qa.length, pending]);

  if (!qa.length && !pending && !error) return null;
  return (
    <section className="rs-thread" aria-label={t("research.paper.askTitle")} aria-live="polite">
      {qa.map((m) => (
        <div key={m.id} className="rs-turn">
          <div className="rs-msg-me">{m.question}</div>
          <Answer qa={m} />
        </div>
      ))}
      {pending && (
        <div className="rs-turn">
          <div className="rs-msg-me">{pending.question}</div>
          <div className="rs-msg-ai">
            <span className="logo-mark">M</span>
            <div className="rs-body" role="status">
              <p className="rs-working">
                <span className="rs-spin" aria-hidden="true" />
                {t(pending.stage === "searching" ? "research.paper.searching" : "research.paper.readingPaper")}
              </p>
            </div>
          </div>
        </div>
      )}
      {error && (
        <p className="rs-alert" role="alert">
          {error}
        </p>
      )}
      <div ref={end} />
    </section>
  );
}

function Answer({ qa }: { qa: PaperQA }) {
  const { t } = useTranslation();
  const fallback = qa.not_found_reason === "no_fulltext" ? t("research.paper.noFulltext") : t("research.paper.notFound");
  return (
    <div className="rs-msg-ai">
      <span className="logo-mark">M</span>
      <div className={"rs-body" + (qa.found ? "" : " rs-notfound")}>
        <p className={qa.found ? undefined : "rs-nf"}>{qa.found ? qa.answer : qa.answer || fallback}</p>
        {qa.citations.map((c, i) => (
          <div className="rs-src" key={i}>
            <b>{c.section}</b>
            <q lang="en">{c.snippet}</q>
            {c.url && (
              <a href={c.url} {...extProps}>
                {t("research.paper.openPassage")}
              </a>
            )}
          </div>
        ))}
        {qa.course_hint && (
          <>
            <p>{t("research.paper.courseHint")}</p>
            <Link className="rs-chipc" to={resolveDeepLink(qa.course_hint.deep_link).to}>
              <span className="rs-chipc-ic">
                <Icon name="play" />
              </span>
              {qa.course_hint.title}
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

function AskBar({ id, thread }: { id: string; thread: ThreadApi }) {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const abort = useRef<AbortController | null>(null);
  const rec = useRef<Recording | null>(null);
  const lang = i18n.language === "en" ? "en" : "vi";

  useEffect(
    () => () => {
      abort.current?.abort();
      rec.current?.cancel();
    },
    [],
  );
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [text]);

  const ask = async (body: { text: string } | { audio: Blob }, label: string) => {
    if (!token || busy) return;
    setBusy(true);
    thread.start(label);
    const ac = new AbortController();
    abort.current = ac;
    let failed: string | undefined;
    try {
      await streamPaperAsk(
        token,
        id,
        "audio" in body ? { audio: body.audio, lang } : { text: body.text, lang },
        (ev) => {
          if (ev.event === "status") thread.stage(ev.data.stage);
          else if (ev.event === "qa") thread.add(ev.data);
          else if (ev.event === "error") failed = ev.data.code === "model_unavailable" ? t("research.err.model_unavailable") : t("research.err.unknown");
        },
        ac.signal,
      );
    } catch (e) {
      if (!ac.signal.aborted) failed = t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") });
    } finally {
      if (!ac.signal.aborted) thread.end(failed);
      setBusy(false);
    }
  };
  const submit = () => {
    const q = text.trim();
    if (!q || busy) return;
    setText("");
    void ask({ text: q }, q);
  };
  const mic = async () => {
    if (listening && rec.current) {
      const r = rec.current;
      rec.current = null;
      setListening(false);
      try {
        void ask({ audio: await r.stop() }, t("research.paper.voice"));
      } catch {
        /* nothing recorded */
      }
      return;
    }
    try {
      rec.current = await startRecording({ onAutoStop: () => void mic() });
      setListening(true);
    } catch (e) {
      thread.end(t(e instanceof RecorderError && e.code === "denied" ? "research.paper.micDenied" : "research.paper.micFailed"));
    }
  };

  return (
    <div className="rs-composer-wrap" data-guide="research-ask" data-guide-label={t("research.paper.askPlaceholder")}>
      <form
        className="rs-composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          ref={area}
          className="rs-c-input"
          rows={1}
          aria-label={t("research.paper.askPlaceholder")}
          placeholder={t("research.paper.askPlaceholder")}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className={"rs-c-btn" + (listening ? " on" : "")} type="button" aria-pressed={listening} aria-label={t(listening ? "research.paper.micStop" : "research.paper.mic")} onClick={() => void mic()}>
          <Icon name={listening ? "stop" : "mic"} />
        </button>
        <button className="rs-c-btn rs-c-send" type="submit" aria-label={t("research.paper.send")} disabled={busy || !text.trim()}>
          <Icon name="up" />
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------- related papers
function Related({ id }: { id: string }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const ctx = useSourceKeys();
  const [rel, setRel] = useState<RelatedPapers | null>(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<"citing" | "cited">("citing");
  const [added, setAdded] = useState<Record<string, string | null>>({});
  const [note, setNote] = useState<string | null>(null);
  const status = ctx?.status;

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setFailed(false);
    researchApi.related(token, id).then(
      (r) => alive && setRel(r),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [token, id, status]);

  if (failed) return null;
  const list = rel?.available ? (tab === "citing" ? rel.citing : rel.cited) : null;
  const isAdded = (key: string, was: boolean) => (key in added ? added[key] !== null : was);
  const toggle = async (c: PaperCard) => {
    if (!token) return;
    setNote(null);
    try {
      const on = isAdded(c.key, c.in_reading_list);
      if (on) {
        const pid = c.key in added ? added[c.key] : c.paper_id;
        if (pid) await researchApi.removePaper(token, pid);
        setAdded((a) => ({ ...a, [c.key]: null }));
      } else {
        const e = await researchApi.addPaper(token, { card: c });
        setAdded((a) => ({ ...a, [c.key]: e.id }));
      }
    } catch (e) {
      setNote(t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") }));
    }
  };

  return (
    <section className="rs-rel" aria-labelledby="rs-rel-h" data-guide="research-related" data-guide-label={t("research.related.title")}>
      <div className="rs-rel-head">
        <h3 id="rs-rel-h">{t("research.related.title")}</h3>
        {rel?.available && (
          <>
            <span className="rs-rel-tabs" role="group" aria-label={t("research.related.kind")}>
              <button type="button" aria-pressed={tab === "citing"} onClick={() => setTab("citing")}>
                {t("research.related.citing", { count: rel.citing.count })}
              </button>
              <button type="button" aria-pressed={tab === "cited"} onClick={() => setTab("cited")}>
                {t("research.related.cited", { count: rel.cited.count })}
              </button>
            </span>
            <span className="muted small">{t("research.related.from", { names: rel.sources.map((s) => SOURCE_NAMES[s]).join(" · ") })}</span>
          </>
        )}
      </div>
      {rel && !rel.available && (
        <p className="rs-rel-none">
          <span>{t("research.related.invite")}</span>
          <SourceChip src="s2" />
        </p>
      )}
      {rel?.partial && <p className="muted small">{t("research.related.partial")}</p>}
      {note && (
        <p className="rs-alert" role="alert">
          {note}
        </p>
      )}
      {list && list.items.length === 0 && <p className="muted">{t("research.related.empty")}</p>}
      {list && list.items.length > 0 && (
        <ul>
          {list.items.map((c) => {
            const on = isAdded(c.key, c.in_reading_list);
            return (
              <li key={c.key}>
                <a className="rs-rt" href={c.url} {...extProps}>
                  {c.title}
                </a>
                <span className="rs-rm">{[c.authors.join(", "), c.year, c.citation_count !== null ? t(pk("research.related.citedBy", c.citation_count), { count: c.citation_count }) : null].filter(Boolean).join(" · ")}</span>
                <button className="rs-radd" type="button" aria-pressed={on} aria-label={t(on ? "research.card.added" : "research.card.add")} onClick={() => void toggle(c)}>
                  <Icon name={on ? "check" : "plus"} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
