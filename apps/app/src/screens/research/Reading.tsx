import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { researchApi, READING_LIST_LIMIT, type ReadingEntry, type ReadNext, type Suggestion } from "../../api/research";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { usePaperIntake } from "./Topic";
import { byline, errCode, extProps, STATUS_TAG } from "./util";

/** "Đọc tiếp": the paper to pick up today and why. */
export function Hero({ hero }: { hero: ReadNext }) {
  const { t } = useTranslation();
  const tag = hero.status === "reading" ? t("research.status.reading") : hero.status === "read" ? t("research.status.read") : t("research.status.new");
  return (
    <section className="rs-today oli rs-hero" data-guide="research-hero" data-guide-label={t("research.hero.keep")}>
      <div className="rs-top">
        <span className={STATUS_TAG[hero.status]}>{tag}</span>
        {hero.minutes_spent > 0 && <span className="muted small">{t("research.hero.minutes", { count: hero.minutes_spent })}</span>}
        <span className="muted small">{hero.authors_line}</span>
      </div>
      <h2>{hero.title}</h2>
      {hero.reason && (
        <p className="rs-why">
          <Icon name="flag" />
          <span>{hero.reason}</span>
        </p>
      )}
      <div className="rs-act">
        <Link className="btn btn-primary" to={`/nghien-cuu/paper/${encodeURIComponent(hero.paper_id)}`}>
          {t(hero.status === "new" ? "research.hero.open" : "research.hero.keep")}
        </Link>
      </div>
    </section>
  );
}

/** "Cần đọc": the reading list, then Mentor's suggestions after it until there are five rows. */
export function ReadList({ items, suggestions, searching, onChanged }: { items: ReadingEntry[]; suggestions: Suggestion[]; searching: boolean; onChanged: () => void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [adding, setAdding] = useState(false);
  const [link, setLink] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const intake = usePaperIntake(() => {
    setLink("");
    setAdding(false);
    onChanged();
  });
  const rows = Math.max(0, READING_LIST_LIMIT - items.length);
  const sugg = suggestions.slice(0, rows);

  const act = async (key: string, fn: () => Promise<unknown>) => {
    if (!token || busy) return;
    setBusy(key);
    setNote(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setNote(t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rs-papers-col" data-guide="research-reading" data-guide-label={t("research.reading.title")}>
      <div className="rs-sec-head">
        <h2 className="rs-s">{t("research.reading.title")}</h2>
        <span className="muted small">{t("research.reading.weekly")}</span>
        <span className="rs-grow" />
        <button className="btn btn-quiet rs-mini" type="button" aria-expanded={adding} onClick={() => setAdding((a) => !a)}>
          <Icon name="plus" />
          <span>{t("research.reading.add")}</span>
        </button>
      </div>
      {adding && (
        <form
          className="rs-add-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (link.trim()) void intake.addLink(link);
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files[0];
            if (f) void intake.addFile(f);
          }}
        >
          <label className="rs-search">
            <Icon name="file" />
            <input autoFocus type="text" value={link} onChange={(e) => setLink(e.target.value)} autoComplete="off" aria-label={t("research.add.label")} placeholder={t("research.add.placeholder")} />
          </label>
          <div className="rs-act">
            <button className="btn btn-primary rs-mini" type="submit" disabled={intake.busy || !link.trim()}>
              {t("research.add.go")}
            </button>
            <button className="btn btn-quiet rs-mini" type="button" disabled={intake.busy} onClick={() => file.current?.click()}>
              <Icon name="upload" />
              <span>{t("research.add.pdf")}</span>
            </button>
            <input ref={file} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => e.target.files?.[0] && void intake.addFile(e.target.files[0])} />
          </div>
          {intake.err && (
            <p className="rs-alert" role="alert">
              {intake.err}
            </p>
          )}
        </form>
      )}
      {note && (
        <p className="rs-alert" role="alert">
          {note}
        </p>
      )}
      {items.length === 0 && sugg.length === 0 && !searching && <p className="rs-rempty">{t("research.reading.empty")}</p>}
      <ul className="rs-papers rs-scroller">
        {searching && [0, 1].map((i) => (
          <li key={`s${i}`} aria-hidden="true">
            <div className="rs-card rs-pcard rs-skel">
              <span className="rs-l" />
              <span className="rs-l" />
            </div>
          </li>
        ))}
        {items.map((e) => (
          <li key={e.id}>
            <EntryCard e={e} busy={busy === e.id} onStatus={(s) => void act(e.id, () => researchApi.setStatus(token!, e.id, s))} onRemove={() => void act(e.id, () => researchApi.removePaper(token!, e.id))} />
          </li>
        ))}
        {sugg.map((s) => (
          <li key={s.id}>
            <SuggestionCard s={s} busy={busy === s.id} onAccept={() => void act(s.id, () => researchApi.acceptSuggestion(token!, s.id))} onDismiss={() => void act(s.id, () => researchApi.dismissSuggestion(token!, s.id))} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function EntryCard({ e, busy, onStatus, onRemove }: { e: ReadingEntry; busy: boolean; onStatus(s: "reading" | "read"): void; onRemove(): void }) {
  const { t } = useTranslation();
  const tag = e.status === "reading" ? t("research.status.reading") : e.status === "read" ? t("research.status.read") : e.new_this_week ? t("research.status.new") : t("research.status.unread");
  const cls = e.status === "reading" ? "tag wait" : e.status === "read" ? "tag ok" : e.new_this_week ? "tag new" : "tag";
  return (
    <article className={"rs-card rs-pcard rs-entry" + (e.status === "reading" ? " reading" : "")}>
      <span className="rs-top">
        <span className="rs-by">{byline(e.paper)}</span>
        <span className={`${cls} rs-tagw`}>{tag}</span>
      </span>
      <Link className="rs-t rs-stretch" to={`/nghien-cuu/paper/${encodeURIComponent(e.id)}`}>
        {e.paper.title}
      </Link>
      {e.reason && (
        <span className="rs-reason">
          <Icon name={e.status === "read" ? "check" : "target"} />
          <span>{e.reason}</span>
        </span>
      )}
      <span className="rs-foot rs-over">
        <button className="btn btn-quiet rs-mini" type="button" disabled={busy} onClick={() => onStatus(e.status === "read" ? "reading" : "read")}>
          {t(e.status === "read" ? "research.reading.readAgain" : "research.reading.markRead")}
        </button>
        <button className="rs-iconbtn" type="button" disabled={busy} aria-label={t("research.reading.remove", { title: e.paper.title })} onClick={onRemove}>
          <Icon name="trash" />
        </button>
      </span>
    </article>
  );
}

function SuggestionCard({ s, busy, onAccept, onDismiss }: { s: Suggestion; busy: boolean; onAccept(): void; onDismiss(): void }) {
  const { t } = useTranslation();
  return (
    <article className="rs-card rs-pcard rs-entry rs-suggest">
      <span className="rs-top">
        <span className="rs-by">{byline(s.paper)}</span>
        <span className="tag rs-tagw">{t("research.reading.suggested")}</span>
      </span>
      <a className="rs-t" href={s.paper.url} {...extProps}>
        {s.paper.title}
      </a>
      <span className="rs-reason">
        <Icon name="target" />
        <span>{s.reason}</span>
      </span>
      <span className="rs-foot">
        <button className="btn btn-ghost rs-mini" type="button" disabled={busy} onClick={onAccept}>
          <Icon name="plus" />
          <span>{t("research.reading.accept")}</span>
        </button>
        <button className="btn btn-quiet rs-mini" type="button" disabled={busy} onClick={onDismiss}>
          {t("research.reading.dismiss")}
        </button>
      </span>
    </article>
  );
}
