import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { researchApi, type ResearchProfile } from "../../api/research";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { errCode } from "./util";

/** A PDF is dropped, picked, or a link or DOI pasted: the paper joins the reading list (and sets the topic when there is none). */
export function usePaperIntake(onAdded: () => void) {
  const { token } = useAuth();
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fail = (e: unknown) => setErr(t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") }));
  const run = async (fn: () => Promise<unknown>) => {
    if (!token || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onAdded();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  return {
    busy,
    err,
    clear: () => setErr(null),
    addLink: (link: string) => run(() => researchApi.addPaper(token!, { link: link.trim() })),
    addFile: (file: File) => {
      if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") return setErr(t("research.add.notPdf"));
      return run(async () => {
        const up = await researchApi.upload(token!, file, file.name);
        return researchApi.addPaper(token!, { upload_path: up.path });
      });
    },
  };
}

const isLink = (s: string) => /^(https?:\/\/|10\.\d{4,}\/|doi:|arxiv:)/i.test(s.trim());

/** First use: one sentence of topic, or a paper dropped in. */
export function EmptyTopic({ onSaved }: { onSaved: () => void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const intake = usePaperIntake(onSaved);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || busy) return;
    if (!title.trim()) return setErr(t("research.topic.needTitle"));
    setBusy(true);
    setErr(null);
    try {
      await researchApi.putProfile(token, { title: title.trim() });
      onSaved();
    } catch (er) {
      setErr(t(`research.err.${errCode(er)}`, { defaultValue: t("research.err.unknown") }));
      setBusy(false);
    }
  };
  return (
    <div className="rs-narrow">
      <form className="rs-ask-topic oli" onSubmit={submit} noValidate data-guide="research-topic" data-guide-label={t("research.topic.askTitle")}>
        <h2>{t("research.topic.askTitle")}</h2>
        <label className="rs-search">
          <Icon name="edit" />
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} autoComplete="off" aria-label={t("research.topic.label")} placeholder={t("research.topic.placeholder")} maxLength={300} />
        </label>
        <div
          className={"rs-drop" + (over ? " over" : "")}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            const f = e.dataTransfer.files[0];
            if (f) void intake.addFile(f);
          }}
          onPaste={(e) => {
            const txt = e.clipboardData.getData("text");
            if (isLink(txt)) {
              e.preventDefault();
              void intake.addLink(txt);
            }
          }}
        >
          <Icon name="upload" />
          <button type="button" className="btn-link" disabled={intake.busy} onClick={() => file.current?.click()}>
            {t("research.topic.drop")}
          </button>
          <input ref={file} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => e.target.files?.[0] && void intake.addFile(e.target.files[0])} />
          <span className="rs-kinds">
            <span className="tag">PDF</span>
            <span className="tag">Link</span>
            <span className="tag">DOI</span>
          </span>
        </div>
        {(err || intake.err) && (
          <p className="rs-alert" role="alert">
            {err ?? intake.err}
          </p>
        )}
        <div>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {t("research.topic.start")}
          </button>
        </div>
      </form>
    </div>
  );
}

export function Keywords({ words, onRemove }: { words: string[]; onRemove?: (w: string) => void }) {
  const { t } = useTranslation();
  return (
    <ul className="rs-kw">
      {words.map((w) => (
        <li key={w}>
          {w}
          {onRemove && words.length > 1 && (
            <button type="button" aria-label={t("research.topic.removeKeyword", { word: w })} onClick={() => onRemove(w)}>
              <Icon name="x" />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

/** "Đề tài": the question, the keywords (each can go), and Edit for the title and for adding a keyword. */
export function TopicCard({ profile, onChanged }: { profile: ResearchProfile; onChanged: () => void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(profile.title);
  const [kw, setKw] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const put = async (body: Parameters<typeof researchApi.putProfile>[1]) => {
    if (!token) return false;
    setErr(null);
    try {
      await researchApi.putProfile(token, body);
      onChanged();
      return true;
    } catch (e) {
      setErr(t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") }));
      return false;
    }
  };
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const body: Parameters<typeof researchApi.putProfile>[1] = {};
    if (title.trim() && title.trim() !== profile.title) body.title = title.trim();
    const word = kw.trim();
    if (word && !profile.keywords.includes(word)) body.keywords = [...profile.keywords, word].slice(0, 8);
    if (!Object.keys(body).length) return setEditing(false);
    if (await put(body)) {
      setKw("");
      setEditing(false);
    }
  };
  return (
    <section className="rs-card rs-topic" data-guide="research-topic" data-guide-label={t("research.topic.eyebrow")}>
      <div className="rs-sec-head">
        <span className="rs-eyebrow">{t("research.topic.eyebrow")}</span>
        <span className="rs-grow" />
        <button className="btn btn-quiet rs-mini" type="button" aria-expanded={editing} onClick={() => { setTitle(profile.title); setEditing((x) => !x); }}>
          {t("research.topic.edit")}
        </button>
      </div>
      {editing ? (
        <form className="rs-edit" onSubmit={save}>
          <label className="rs-search">
            <Icon name="edit" />
            <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} aria-label={t("research.topic.label")} maxLength={300} />
          </label>
          <label className="rs-search">
            <Icon name="plus" />
            <input type="text" value={kw} onChange={(e) => setKw(e.target.value)} aria-label={t("research.topic.addKeyword")} placeholder={t("research.topic.addKeyword")} maxLength={60} disabled={profile.keywords.length >= 8} />
          </label>
          <div className="rs-act">
            <button className="btn btn-primary" type="submit">
              {t("research.topic.save")}
            </button>
            <button className="btn btn-quiet" type="button" onClick={() => setEditing(false)}>
              {t("research.topic.cancel")}
            </button>
          </div>
        </form>
      ) : (
        <p className="rs-q">{profile.question || profile.title}</p>
      )}
      <Keywords words={profile.keywords} onRemove={(w) => void put({ keywords: profile.keywords.filter((x) => x !== w) })} />
      {err && (
        <p className="rs-alert" role="alert">
          {err}
        </p>
      )}
    </section>
  );
}

/** Topic just set: Mentor is still on its first search. */
export function SavedTopic({ profile }: { profile: ResearchProfile }) {
  const { t } = useTranslation();
  return (
    <div className="rs-narrow">
      <div className="rs-today oli">
        <h2 className="rs-plain-h">{t("research.topic.saved")}</h2>
        <p className="rs-q">{profile.question || profile.title}</p>
        <Keywords words={profile.keywords} />
      </div>
      <div className="rs-waiting" role="status">
        <Icon name="clock" />
        <span>{t("research.topic.firstSearch")}</span>
      </div>
    </div>
  );
}
