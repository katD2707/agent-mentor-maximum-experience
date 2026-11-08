import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { researchApi, type PaperCard, type SearchResponse } from "../../api/research";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { DEPTHS, DEPTH_NEEDS, SOURCE_NAMES, useSourceKeys } from "./Sources";
import { ReviewPanel, useReview } from "./Review";
import { byline, errCode, extProps, pk } from "./util";

/** The search bar of hs-11: suggestions from the topic, and the search depth picker. */
export function SearchBar({ keywords, value, onSearch }: { keywords: string[]; value: string; onSearch(q: string): void }) {
  const { t } = useTranslation();
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const chips = keywords.slice(0, 5).map((k, i) => ({ label: k, q: i === 0 ? keywords.slice(0, 4).join(" ") : k }));
  return (
    <div className="rs-sbar" data-guide="research-search" data-guide-label={t("research.search.label")}>
      <form
        className="rs-sform"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) onSearch(text.trim());
        }}
      >
        <label className="rs-search">
          <Icon name="search" />
          <input type="text" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" aria-label={t("research.search.label")} placeholder={t("research.search.placeholder")} />
        </label>
        {chips.length > 0 && (
          <div className="rs-sugg" id="rs-sugg">
            <span className="rs-eyebrow rs-eyebrow-soft">{t("research.search.suggested")}</span>
            <div className="rs-chips">
              {chips.map((c) => (
                <button key={c.label} className="rs-fchip" type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => onSearch(c.q)}>
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </form>
      <DepthPicker />
    </div>
  );
}

const Meter = ({ level }: { level: number }) => (
  <span className="rs-depth-m" aria-hidden="true">
    {[0, 1, 2].map((i) => (
      <i key={i} className={i <= level ? "on" : undefined} />
    ))}
  </span>
);

/** Quick / Thorough / Deep, picked like a reasoning-effort level. A level whose key is missing opens the key dialog. */
function DepthPicker() {
  const { t } = useTranslation();
  const ctx = useSourceKeys();
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    pop.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
    const away = (e: PointerEvent) => {
      const n = e.target as Node;
      if (!pop.current?.contains(n) && !btn.current?.contains(n)) setOpen(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  if (!ctx) return null;
  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) btn.current?.focus();
  };
  const name = (i: number) => t(`research.depth.${DEPTHS[i]}.name`);
  const desc = (i: number) => t(`research.depth.${DEPTHS[i]}.desc`);
  const pick = (i: number) => {
    const need = DEPTH_NEEDS[i];
    if (need && !ctx.connected(need)) {
      close(false);
      ctx.open(need, btn.current, i);
      return;
    }
    ctx.setDepth(i);
    close(true);
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const items = [...(pop.current?.querySelectorAll<HTMLElement>(".rs-depth-i") ?? [])];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const go = (i: number) => items[(i + items.length) % items.length]?.focus();
    if (e.key === "ArrowDown") go(at + 1);
    else if (e.key === "ArrowUp") go(at - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(items.length - 1);
    else if (e.key === "Escape") close(true);
    else if (e.key === "Tab") return close(false);
    else return;
    e.preventDefault();
  };
  return (
    <span className="rs-depth">
      <button
        ref={btn}
        className="rs-depth-btn"
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("research.depth.aria", { name: name(ctx.depth), desc: desc(ctx.depth) })}
        onClick={() => setOpen((o) => !o)}
      >
        <Meter level={ctx.depth} />
        <span>{name(ctx.depth)}</span>
        <Icon name="chev" />
      </button>
      {open && (
        <div ref={pop} className="rs-depth-pop" role="menu" aria-labelledby="rs-depth-h" data-mascot-avoid onKeyDown={onKey}>
          <p className="rs-depth-h" id="rs-depth-h">
            {t("research.depth.title")}
          </p>
          {DEPTHS.map((_, i) => {
            const need = DEPTH_NEEDS[i];
            const locked = !!need && !ctx.connected(need);
            const sel = i === ctx.depth;
            return (
              <button key={i} type="button" role="menuitemradio" aria-checked={sel} className="rs-depth-i" data-locked={locked || undefined} tabIndex={-1} onClick={() => pick(i)}>
                <Meter level={i} />
                <span className="rs-depth-t">
                  <b>{name(i)}</b>
                  <span>{desc(i)}</span>
                </span>
                {locked ? (
                  <span className="rs-depth-key">
                    <Icon name="lock" />
                    {t("research.depth.needsKey")}
                  </span>
                ) : (
                  <span className="rs-depth-ok">{sel && <Icon name="check" />}</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </span>
  );
}

const thisYear = new Date().getFullYear();

/** Results of one search, with the filters, the quick review and the card per source. */
export function Results({ query, onClear, onSearch, onChanged }: { query: string; onClear(): void; onSearch(q: string): void; onChanged(): void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [yearMin, setYearMin] = useState(0);
  const [pdf, setPdf] = useState(false);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [cards, setCards] = useState<PaperCard[]>([]);
  const [busy, setBusy] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [added, setAdded] = useState<Record<string, string | null>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const seq = useRef(0);
  const review = useReview(query, yearMin || undefined);
  const sources = useSourceKeys();
  const depth = sources ? DEPTHS[sources.depth] : undefined;

  const run = useCallback(
    (page: number) => {
      if (!token) return;
      const mine = ++seq.current;
      if (page === 1) setBusy(true);
      else setMore(true);
      setError(null);
      researchApi.search(token, { q: query, year_min: yearMin || undefined, pdf: pdf || undefined, page, depth }).then(
        (r) => {
          if (mine !== seq.current) return;
          setData(r);
          setCards((c) => (page === 1 ? r.results : [...c, ...r.results.filter((x) => !c.some((y) => y.key === x.key))]));
          setBusy(false);
          setMore(false);
        },
        (e) => {
          if (mine !== seq.current) return;
          setError(errCode(e));
          setBusy(false);
          setMore(false);
        },
      );
    },
    [token, query, yearMin, pdf, depth],
  );
  useEffect(() => run(1), [run]);
  useEffect(() => () => void (seq.current += 1), []);

  const isAdded = (c: PaperCard) => (c.key in added ? added[c.key] !== null : c.in_reading_list);
  const entryId = (c: PaperCard) => (c.key in added ? added[c.key] : c.paper_id);
  const toggle = async (c: PaperCard) => {
    if (!token || pending[c.key]) return;
    setPending((p) => ({ ...p, [c.key]: true }));
    setNotice(null);
    try {
      if (isAdded(c)) {
        const id = entryId(c);
        if (id) await researchApi.removePaper(token, id);
        setAdded((a) => ({ ...a, [c.key]: null }));
      } else {
        const e = await researchApi.addPaper(token, { card: c });
        setAdded((a) => ({ ...a, [c.key]: e.id }));
      }
      onChanged();
    } catch (e) {
      setNotice(t(`research.err.${errCode(e)}`, { defaultValue: t("research.err.unknown") }));
    } finally {
      setPending((p) => ({ ...p, [c.key]: false }));
    }
  };

  const years = useMemo(
    () => [
      { v: 0, label: t("research.filters.anyYear") },
      { v: thisYear - 4, label: t("research.filters.last5") },
      { v: thisYear, label: t("research.filters.thisYear") },
    ],
    [t],
  );
  const failed = data?.sources.filter((s) => s.status === "failed") ?? [];

  return (
    <section className="rs-results" aria-live="polite">
      <div className="rs-rhead">
        <h2 className="rs-s">
          {t("research.search.resultsFor")} “<span>{query}</span>”
        </h2>
        {data && !busy && <span className="muted small">{t(pk("research.search.count", cards.length), { count: cards.length })}</span>}
        <span className="rs-grow" />
        <button className="btn btn-ghost rs-rbtn" type="button" disabled={review.state.phase === "running" || busy || cards.length === 0} onClick={() => void review.start()}>
          {t("research.review.button")}
        </button>
        <button className="btn btn-quiet rs-rbtn" type="button" onClick={onClear}>
          {t("research.search.clear")}
        </button>
      </div>
      <ReviewPanel state={review.state} onSearch={onSearch} onHide={review.hide} />
      <div className="rs-fbar" role="group" aria-label={t("research.filters.label")}>
        {years.map((y) => (
          <button key={y.v} className="rs-fchip" type="button" aria-pressed={yearMin === y.v} onClick={() => setYearMin(y.v)}>
            {y.label}
          </button>
        ))}
        <span className="rs-fgap" />
        <button className="rs-fchip" type="button" aria-pressed={pdf} onClick={() => setPdf((p) => !p)}>
          <Icon name="file" />
          <span>{t("research.filters.pdf")}</span>
        </button>
      </div>
      {failed.length > 0 && (
        <p className="muted small" role="status">
          {t("research.search.failedSources", { names: failed.map((f) => (f.source === "asta" ? SOURCE_NAMES.asta : f.source === "s2" ? SOURCE_NAMES.s2 : "arXiv")).join(", ") })}
        </p>
      )}
      {notice && (
        <p className="rs-alert" role="alert">
          {notice}
        </p>
      )}
      {busy && (
        <ul className="rs-rcards" aria-hidden="true">
          {[0, 1].map((i) => (
            <li key={i}>
              <div className="rs-card rs-pcard rs-skel">
                <span className="rs-l" />
                <span className="rs-l" />
              </div>
            </li>
          ))}
        </ul>
      )}
      {error && !busy && (
        <p className="rs-rempty" role="alert">
          {t(`research.err.${error}`, { defaultValue: t("research.err.unknown") })}{" "}
          <button className="btn-link" type="button" onClick={() => run(1)}>
            {t("research.retry")}
          </button>
        </p>
      )}
      {!busy && !error && cards.length === 0 && <p className="rs-rempty">{t(yearMin || pdf ? "research.search.emptyFiltered" : "research.search.empty")}</p>}
      <ul className="rs-rcards">
        {cards.map((c) => (
          <li key={c.key}>
            <ResultCard card={c} added={isAdded(c)} busy={!!pending[c.key]} onToggle={() => void toggle(c)} />
          </li>
        ))}
      </ul>
      {data?.has_more && !busy && (
        <div>
          <button className="btn btn-ghost rs-rbtn" type="button" disabled={more} onClick={() => run((data?.page ?? 1) + 1)}>
            {t("research.search.more")}
          </button>
        </div>
      )}
    </section>
  );
}

/** One result. arXiv gives title, authors, year and the abstract's start only: no citations, no TL;DR. */
export function ResultCard({ card: c, added, busy, onToggle }: { card: PaperCard; added: boolean; busy: boolean; onToggle(): void }) {
  const { t } = useTranslation();
  const src = c.source === "asta" ? SOURCE_NAMES.asta : c.source === "s2" ? SOURCE_NAMES.s2 : "arXiv";
  const by = `${byline(c)}${c.source === "arxiv" ? " · arXiv" : c.venue ? ` · ${c.venue}` : ""}`;
  let line: { cls: string; label: string; text: string };
  if (c.source === "asta" && c.snippet) line = { cls: "rs-tldr rs-abs", label: t("research.card.snippet"), text: c.snippet };
  else if (c.tldr) line = { cls: "rs-tldr", label: c.source === "s2" ? "TL;DR · Semantic Scholar" : "TL;DR", text: c.tldr };
  else line = { cls: "rs-tldr rs-abs", label: t("research.card.abstract"), text: c.excerpt };
  return (
    <article className={`rs-card rs-pcard rs-rcard rs-from-${c.source}`}>
      <span className="rs-by">{by}</span>
      <h3 className="rs-t">
        {c.paper_id ? <Link to={`/nghien-cuu/paper/${encodeURIComponent(c.paper_id)}`}>{c.title}</Link> : <a href={c.url} {...extProps}>{c.title}</a>}
      </h3>
      <span className="rs-meta">
        {c.citation_count !== null && <span>{t(pk("research.card.cited", c.citation_count), { count: c.citation_count })}</span>}
        {c.has_pdf ? <span className="tag ok">{t("research.card.pdf")}</span> : <span className="tag">{t("research.card.abstractOnly")}</span>}
      </span>
      <p className={line.cls}>
        <b>{line.label}</b>
        <span lang="en">{line.text}</span>
      </p>
      <div className="rs-foot">
        <button className="btn btn-ghost rs-addbtn" type="button" aria-pressed={added} disabled={busy} onClick={onToggle}>
          {added ? (
            <>
              <Icon name="check" />
              <span>{t("research.card.added")}</span>
            </>
          ) : (
            <>
              <Icon name="plus" />
              <span>{t("research.card.add")}</span>
            </>
          )}
        </button>
        <span className="muted small">{src}</span>
      </div>
    </article>
  );
}
