import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigationType, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, type CatalogItem, type CatalogPage, type FacetKey, type Suggestions } from "../../api";
import { useAuth } from "../../state/auth";
import { fold } from "../../lib/text";
import { Icon } from "../../components/Icon";
import { subjectName } from "../../lib/subjectNames";
import { addRecent, loadRecent, removeRecent } from "../../lib/recentSearches";
import { activeCount, emptyFilters, parseState, toParams, toQuery, type CatState } from "../../lib/catalogUrl";
import { saveScroll, peekScroll } from "../../lib/scrollMemory";
import { CourseCard, ListCover, Pager, useFacetLabel } from "./catalogUi";

const ORDER: FacetKey[] = ["subject", "band", "language", "level", "duration", "media", "status", "teacher"];
const POPULAR = ["Toán 12", "IELTS", "Python", "Vật lí", "Hóa học", "Machine learning"];
const LONG = new Set<FacetKey>(["subject", "teacher"]);
const SHOWN = 6;

type Load = { status: "loading" | "ready" | "error"; data: CatalogPage | null };

/**
 * hs-03: the course catalog. Search (with autocomplete), sort tabs, facets with live counts, filter chips, product cards
 * and a pager. The whole state lives in the URL (`?q=&subject=&sort=&page=`), so coming back from a course restores it.
 * A g1_5 learner gets the simple version: big search box, subject pictures, two-column tiles.
 */
export function CourseSearch() {
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const [params, setParams] = useSearchParams();
  const loc = useLocation();
  const own = user?.age_band ?? null;
  const kid = own === "g1_5";
  const st = useMemo(() => parseState(params, own), [params, own]);
  const from = `${loc.pathname}${loc.search}`;
  // coming back (browser back, or the back arrow of a course page, which sets state.restore): put the list where it was
  const navType = useNavigationType();
  const wantsRestore = navType === "POP" || (loc.state as { restore?: boolean } | null)?.restore === true;
  const restoreY = useRef<number | null | undefined>(undefined);
  if (restoreY.current === undefined) restoreY.current = wantsRestore ? peekScroll(from) : null;
  const label = useFacetLabel();

  const [load, setLoad] = useState<Load>({ status: "loading", data: null });
  const [sheet, setSheet] = useState(false);
  const [recent, setRecent] = useState<string[]>(() => (user ? loadRecent(user.id) : []));
  const [expanded, setExpanded] = useState<Partial<Record<FacetKey, boolean>>>({});
  const sbarRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const fbtnRef = useRef<HTMLButtonElement>(null);
  const moved = useRef(false);

  const go = useCallback(
    (next: CatState, opts?: { keepPage?: boolean }) => {
      const s = opts?.keepPage ? next : { ...next, page: 1 };
      setParams(toParams(s, own), { replace: true });
    },
    [own, setParams],
  );

  // ---- results
  const key = params.toString();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    setLoad((l) => ({ status: "loading", data: l.data }));
    api
      .queryCatalog(token, toQuery(st))
      .then((data) => alive && setLoad({ status: "ready", data }))
      .catch(() => alive && setLoad((l) => ({ status: "error", data: l.data })));
    return () => {
      alive = false;
    };
    // st is derived from the URL; key is its serialisation
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, key, own, tick]);

  const data = load.data;
  const words = useMemo(() => fold(st.q).split(/\s+/).filter(Boolean), [st.q]);

  useEffect(() => {
    const y = restoreY.current;
    if (y == null || load.status !== "ready" || !data) return;
    restoreY.current = null;
    const id = requestAnimationFrame(() => window.scrollTo(0, y));
    return () => cancelAnimationFrame(id);
  }, [data, load.status]);

  // ---- a new page: scroll so the first card sits under the sticky search bar, and focus it
  useEffect(() => {
    if (!moved.current || load.status !== "ready" || !data || data.page !== st.page) return;
    moved.current = false;
    const first = listRef.current?.firstElementChild as HTMLElement | null;
    if (!first) return;
    const bar = sbarRef.current;
    const sticky = bar && getComputedStyle(bar).position === "sticky" ? bar.getBoundingClientRect().height : 0;
    first.style.scrollMarginTop = `${sticky + 12}px`;
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    first.scrollIntoView?.({ behavior: calm ? "auto" : "smooth", block: "start" });
    first.focus({ preventScroll: true });
  }, [data, load.status, st.page]);

  const goPage = (n: number) => {
    moved.current = true;
    setParams(toParams({ ...st, page: n }, own), { replace: true });
  };

  // ---- the filter sheet (phones)
  useEffect(() => {
    document.body.classList.toggle("cat-sheet", sheet);
    document.body.style.overflow = sheet ? "hidden" : "";
    return () => {
      document.body.classList.remove("cat-sheet");
      document.body.style.overflow = "";
    };
  }, [sheet]);
  const closeSheet = useCallback(() => {
    setSheet(false);
    fbtnRef.current?.focus({ preventScroll: true });
  }, []);
  useEffect(() => {
    if (!sheet) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && closeSheet();
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [sheet, closeSheet]);

  const toggle = (k: FacetKey, v: string) => {
    const cur = st.f[k];
    go({ ...st, f: { ...st.f, [k]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] } });
  };
  const resetAll = () => go({ ...st, q: "", f: { ...emptyFilters(), band: own ? [own] : [] } });
  const clearAll = () => go({ ...st, f: { ...emptyFilters(), band: kid && own ? [own] : [] } });
  const setQuery = (q: string, save = false) => {
    if (save && user) setRecent(addRecent(user.id, q));
    go({ ...st, q });
  };

  const total = data?.total ?? 0;
  const chips: { k: FacetKey; v: string }[] = ORDER.flatMap((k) => st.f[k].map((v) => ({ k, v })));
  const badge = activeCount(st, own);
  const list = !kid && st.view === "list";

  return (
    <div className="app">
      <header className="topbar">
        <Link className="icon-btn" to="/khoa-hoc" aria-label={t("courses.intro.back")}>
          <Icon name="back" />
        </Link>
        <h1 className="page-title">{t("courses.catalog.title")}</h1>
      </header>
      <main className="main courses-main catalog-main">
        <div id="cat" className={kid ? "kid" : ""}>
          <div className="sbar" ref={sbarRef}>
            <SearchBox
              q={st.q}
              kid={kid}
              recent={recent}
              userId={user?.id ?? ""}
              onCommit={(q) => setQuery(q, true)}
              onLive={(q) => go({ ...st, q })}
              onFilter={(k, v) => go({ ...st, q: "", f: { ...st.f, [k]: [v] } })}
              onRecent={setRecent}
            />
            {!kid && (
              <button ref={fbtnRef} type="button" className="fbtn" onClick={() => setSheet(true)} aria-haspopup="dialog">
                <span>{t("courses.catalog.filters")}</span>
                {badge > 0 && <b data-testid="filter-badge">{badge}</b>}
              </button>
            )}
          </div>

          <div className={`cat${kid ? " kid" : ""}`}>
            {!kid && (
              <aside className="filters" aria-label={t("courses.catalog.filters")} {...(sheet ? { role: "dialog", "aria-modal": true } : {})} data-open={sheet}>
                <div className="fh">
                  <h2>{t("courses.catalog.filters")}</h2>
                  <button type="button" className="reset" onClick={resetAll}>
                    {t("courses.catalog.reset")}
                  </button>
                  <button type="button" className="x" onClick={closeSheet} aria-label={t("courses.catalog.close")}>
                    ×
                  </button>
                </div>
                <div className="fbody">
                  {data &&
                    ORDER.map((k) => {
                      let opts = data.facets[k] ?? [];
                      if (LONG.has(k)) opts = opts.filter((o) => o.n > 0 || st.f[k].includes(o.v));
                      const all = !!expanded[k];
                      const shown = opts.filter((o, i) => all || i < SHOWN || st.f[k].includes(o.v));
                      return (
                        <section className="facet" key={k} data-facet={k}>
                          <h3>{t(`courses.catalog.facet.${k}`)}</h3>
                          <div className={k === "teacher" && all ? "tlist" : undefined}>
                            {shown.map((o) => (
                              <label key={o.v} className={`fo${o.n === 0 && !st.f[k].includes(o.v) ? " zero" : ""}`}>
                                <input type="checkbox" checked={st.f[k].includes(o.v)} onChange={() => toggle(k, o.v)} />
                                <span className="fl">{label(k, o.v)}</span>
                                <span className="fn">{o.n}</span>
                              </label>
                            ))}
                          </div>
                          {opts.length > SHOWN && (
                            <button type="button" className="more" onClick={() => setExpanded({ ...expanded, [k]: !all })}>
                              {all ? t("courses.catalog.less") : t("courses.catalog.more", { n: opts.length - shown.length })}
                            </button>
                          )}
                        </section>
                      );
                    })}
                </div>
                <div className="ff">
                  <button type="button" className="btn btn-primary" onClick={closeSheet}>
                    {t("courses.catalog.apply", { n: total })}
                  </button>
                </div>
              </aside>
            )}

            <div className="col">
              {!kid && (
                <div className="sortbar">
                  <div className="tabs" role="group" aria-label={t("courses.catalog.sortLabel")}>
                    {(["rel", "new", "pop", "dur"] as const).map((s) => (
                      <button
                        key={s}
                        type="button"
                        aria-pressed={st.sort === s}
                        aria-label={s === "dur" ? `${t("courses.catalog.sort.dur")} ${st.sort === "dur" && st.dir === "desc" ? t("courses.catalog.sortDesc") : t("courses.catalog.sortAsc")}` : undefined}
                        onClick={() => go({ ...st, sort: s, dir: s === "dur" && st.sort === "dur" ? (st.dir === "asc" ? "desc" : "asc") : "asc" })}
                      >
                        {t(`courses.catalog.sort.${s}`)}
                        {s === "dur" ? (st.sort === "dur" && st.dir === "desc" ? " ↓" : " ↑") : ""}
                      </button>
                    ))}
                  </div>
                  <div className="sbtm">
                    <span className="count" aria-live="polite">
                      {data ? t(total === 1 ? "courses.catalog.countOne" : "courses.catalog.count", { count: total }) : ""}
                    </span>
                    <span className="vt">
                      <button type="button" aria-pressed={!list} aria-label={t("courses.catalog.viewGrid")} onClick={() => go({ ...st, view: "grid" }, { keepPage: true })}>
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                          <rect x="4" y="4" width="6.5" height="6.5" rx="1.5" />
                          <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" />
                          <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" />
                          <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" />
                        </svg>
                      </button>
                      <button type="button" aria-pressed={list} aria-label={t("courses.catalog.viewList")} onClick={() => go({ ...st, view: "list" }, { keepPage: true })}>
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                          <path d="M4 7h16M4 12h16M4 17h16" />
                        </svg>
                      </button>
                    </span>
                  </div>
                </div>
              )}

              {!kid && chips.length > 0 && (
                <div className="chips" data-testid="active-chips">
                  {chips.map(({ k, v }) => (
                    <button key={`${k}:${v}`} type="button" className="chip" aria-label={t("courses.catalog.removeFilter", { what: label(k, v) })} onClick={() => toggle(k, v)}>
                      {t(`courses.catalog.facet.${k}`)}: {label(k, v)} <span className="x" aria-hidden="true">×</span>
                    </button>
                  ))}
                  {chips.length > 1 && (
                    <button type="button" className="chip clear" onClick={clearAll}>
                      {t("courses.catalog.clearAll")}
                    </button>
                  )}
                </div>
              )}

              {kid && <KidSubjects current={st.f.subject[0] ?? ""} onPick={(s) => go({ ...st, f: { ...st.f, subject: s ? [s] : [] } })} />}

              {load.status === "error" && (
                <p className="muted" role="alert">
                  {t("courses.catalog.failed")}{" "}
                  <button type="button" className="btn-link" onClick={() => setTick((n) => n + 1)}>
                    {t("courses.catalog.retry")}
                  </button>
                </p>
              )}
              {load.status === "loading" && !data && (
                <p className="muted" role="status">
                  {t("courses.catalog.loading")}
                </p>
              )}

              <ul ref={listRef} onClickCapture={() => saveScroll(from, window.scrollY)} className={`grid pager-list${list ? " list" : ""}`} aria-busy={load.status === "loading"} data-testid="results">
                {(data?.items ?? []).map((c: CatalogItem) => (
                  <CourseCard key={c.id} c={c} words={words} kid={kid} from={from} />
                ))}
              </ul>

              {data && data.total < 4 && <FewResults data={data} st={st} own={own} kid={kid} go={go} onQuery={(q) => setQuery(q, true)} />}

              <Pager page={data?.page ?? st.page} pages={data?.pages ?? 1} onGo={goPage} />
            </div>
          </div>
          {sheet && <div className="backdrop" onClick={closeSheet} data-testid="backdrop" />}
        </div>
      </main>
    </div>
  );
}

// ------------------------------------------------------------------ search box and autocomplete
function SearchBox({ q, kid, recent, userId, onCommit, onLive, onFilter, onRecent }: { q: string; kid: boolean; recent: string[]; userId: string; onCommit: (q: string) => void; onLive: (q: string) => void; onFilter: (k: FacetKey, v: string) => void; onRecent: (r: string[]) => void }) {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const [draft, setDraft] = useState(q);
  const [open, setOpen] = useState(false);
  const [sug, setSug] = useState<Suggestions | null>(null);
  const [note, setNote] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const live = useRef(q);
  const onLiveRef = useRef(onLive);
  onLiveRef.current = onLive;

  useEffect(() => {
    if (q !== live.current) setDraft(q); // changed from outside (a chip, "did you mean")
    live.current = q;
  }, [q]);

  // type to search: wait for a short pause
  useEffect(() => {
    const s = draft.trim();
    if (s === live.current) return;
    const id = setTimeout(() => {
      live.current = s;
      onLiveRef.current(s);
    }, 300);
    return () => clearTimeout(id);
  }, [draft]);

  // suggestions for what is typed
  useEffect(() => {
    const s = draft.trim();
    if (!token || !open || !s || kid) {
      setSug(null);
      return;
    }
    let alive = true;
    const id = setTimeout(() => {
      api
        .suggest(token, s)
        .then((r) => alive && setSug(r))
        .catch(() => alive && setSug(null));
    }, 120);
    return () => {
      alive = false;
      clearTimeout(id);
    };
  }, [draft, open, token, kid]);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  const pick = (s: string) => {
    live.current = s;
    setDraft(s);
    setOpen(false);
    onCommit(s);
  };
  const hits = (text: string) => highlightBold(text, draft);
  const items = () => Array.from(box.current?.querySelectorAll<HTMLElement>(".ac .it") ?? []);
  const keys = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") return setOpen(false);
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const list = items();
    if (!list.length) return;
    e.preventDefault();
    const at = list.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "ArrowDown" ? (at + 1) % list.length : at <= 0 ? -1 : at - 1;
    (next < 0 ? input.current : list[next])?.focus();
  };

  const listen = () => {
    const SR = (window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec }).SpeechRecognition ?? (window as unknown as { webkitSpeechRecognition?: new () => SpeechRec }).webkitSpeechRecognition;
    if (!SR) return setNote(t("courses.catalog.micNone"));
    const r = new SR();
    r.lang = i18n.language.startsWith("en") ? "en-US" : "vi-VN";
    r.onresult = (e) => pick(e.results[0][0].transcript);
    r.onend = () => setNote("");
    r.onerror = () => setNote(t("courses.catalog.micNone"));
    setNote(t("courses.catalog.micListening"));
    r.start();
  };

  const s = draft.trim();
  return (
    <div className="search-wrap" ref={box} onKeyDown={keys}>
      <form
        className="search"
        role="search"
        data-guide="course-search"
        data-guide-label={t("courses.catalog.title")}
        onSubmit={(e) => {
          e.preventDefault();
          pick(draft.trim());
          input.current?.blur();
        }}
      >
        <Icon name="search" />
        <input
          ref={input}
          type="search"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={kid ? t("courses.catalog.kidPlaceholder") : t("courses.catalog.placeholder")}
          aria-label={t("courses.catalog.label")}
          aria-autocomplete="list"
          aria-controls="cat-ac"
          aria-expanded={open}
          autoComplete="off"
        />
        {kid && (
          <button className="mic" type="button" aria-label={t("courses.catalog.mic")} onClick={listen}>
            <Icon name="mic" />
          </button>
        )}
      </form>
      {note && (
        <p className="mic-note" role="status">
          {note}
        </p>
      )}
      {open && !kid && (
        <div className="ac" id="cat-ac">
          {!s ? (
            <>
              {recent.length > 0 && (
                <>
                  <h4>{t("courses.catalog.recent")}</h4>
                  {recent.map((r) => (
                    <div className="row" key={r}>
                      <button type="button" className="it" onClick={() => pick(r)}>
                        <span>{r}</span>
                      </button>
                      <button type="button" className="it x" aria-label={t("courses.catalog.removeRecent", { q: r })} onClick={() => onRecent(removeRecent(userId, r))}>
                        ×
                      </button>
                    </div>
                  ))}
                </>
              )}
              <h4>{t("courses.catalog.popularTitle")}</h4>
              <div className="chipset">
                {POPULAR.map((p) => (
                  <button key={p} type="button" className="chip" onClick={() => pick(p)}>
                    {p}
                  </button>
                ))}
              </div>
            </>
          ) : (
            sug && (
              <>
                {sug.courses.length > 0 && <h4>{t("courses.catalog.groupCourses")}</h4>}
                {sug.courses.map((c) => (
                  <button key={c.id} type="button" className="it" onClick={() => pick(c.title)}>
                    <span>{hits(c.title)}</span>
                  </button>
                ))}
                {sug.subjects.length > 0 && <h4>{t("courses.catalog.groupSubjects")}</h4>}
                {sug.subjects.map((x) => (
                  <button key={x} type="button" className="it" onClick={() => (setDraft(""), live.current = "", setOpen(false), onFilter("subject", x))}>
                    <span>{hits(subjectName(x, i18n.language))}</span>
                  </button>
                ))}
                {sug.teachers.length > 0 && <h4>{t("courses.catalog.groupTeachers")}</h4>}
                {sug.teachers.map((x) => (
                  <button key={x} type="button" className="it" onClick={() => (setDraft(""), live.current = "", setOpen(false), onFilter("teacher", x))}>
                    <span>{hits(x)}</span>
                  </button>
                ))}
                {!sug.courses.length && !sug.subjects.length && !sug.teachers.length && (
                  <p className="hint">
                    {t("courses.catalog.noSuggest")}
                    {sug.did_you_mean && (
                      <>
                        {" "}
                        {t("courses.catalog.didYouMean")} <button type="button" onClick={() => pick(sug.did_you_mean!)}>{sug.did_you_mean}</button>?
                      </>
                    )}
                  </p>
                )}
              </>
            )
          )}
        </div>
      )}
    </div>
  );
}

interface SpeechRec {
  lang: string;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
}

/** The matched words in bold, accent-insensitive (the folded text keeps one character per input character). */
function highlightBold(text: string, q: string): React.ReactNode {
  const toks = fold(q).split(/\s+/).filter(Boolean);
  const chars = Array.from(text);
  const folded = chars.map((c) => fold(c)[0] ?? c.toLowerCase()).join("");
  const on = chars.map(() => false);
  for (const tk of toks) for (let at = folded.indexOf(tk); at !== -1; at = folded.indexOf(tk, at + 1)) for (let j = at; j < at + tk.length; j++) on[j] = true;
  const out: React.ReactNode[] = [];
  let buf = "";
  let cur = false;
  const flush = (i: number) => {
    if (buf) out.push(cur ? <b key={i}>{buf}</b> : buf);
    buf = "";
  };
  chars.forEach((c, i) => {
    if (on[i] !== cur) {
      flush(i);
      cur = on[i];
    }
    buf += c;
  });
  flush(chars.length);
  return <>{out}</>;
}

// ------------------------------------------------------------------ kids: subject pictures
function KidSubjects({ current, onPick }: { current: string; onPick: (s: string) => void }) {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const [subs, setSubs] = useState<CatalogItem[]>([]);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    api
      .queryCatalog(token, { filters: { band: ["g1_5"] }, page_size: 50 })
      .then((r) => {
        if (!alive) return;
        const seen = new Set<string>();
        setSubs(r.items.filter((c) => (seen.has(c.subject) ? false : (seen.add(c.subject), true))));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [token]);
  return (
    <div className="kidsubj" data-testid="kid-subjects">
      <button type="button" className={`chip all${current ? "" : " on"}`} aria-pressed={!current} onClick={() => onPick("")}>
        {t("courses.catalog.allKids")}
      </button>
      {subs.map((c) => (
        <button key={c.subject} type="button" className={`chip${current === c.subject ? " on" : ""}`} aria-pressed={current === c.subject} onClick={() => onPick(c.subject)}>
          <ListCover course={c} />
          {subjectName(c.subject, i18n.language)}
        </button>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ few or no results
function FewResults({ data, st, own, kid, go, onQuery }: { data: CatalogPage; st: CatState; own: CatState["f"]["band"][number] | null; kid: boolean; go: (s: CatState) => void; onQuery: (q: string) => void }) {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const label = useFacetLabel();
  const [gains, setGains] = useState<{ k: FacetKey; v: string; g: number }[]>([]);
  const [related, setRelated] = useState<string[]>([]);
  const sig = JSON.stringify([st.q, st.f, data.total]);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    const own1 = own && st.f.band.length === 1 && st.f.band[0] === own;
    const tries: { k: FacetKey; v: string }[] = [];
    for (const k of ORDER) for (const v of st.f[k]) if (!(k === "band" && own1) && !(kid && k === "band")) tries.push({ k, v });
    void Promise.all(
      tries.map(async ({ k, v }) => {
        const f = { ...st.f, [k]: st.f[k].filter((x) => x !== v) };
        const r = await api.queryCatalog(token, { q: st.q, filters: f, page_size: 1 });
        return { k, v, g: r.total - data.total };
      }),
    )
      .then((all) => alive && setGains(all.filter((x) => x.g > 0).sort((a, b) => b.g - a.g).slice(0, 4)))
      .catch(() => alive && setGains([]));
    api
      .queryCatalog(token, { filters: { band: st.f.band }, page_size: 1 })
      .then((r) => alive && setRelated(r.facets.subject.filter((o) => !st.f.subject.includes(o.v)).slice(0, 5).map((o) => o.v)))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
    // sig covers q, filters and the total
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, sig]);

  return (
    <div className="none" data-testid="few-results">
      {data.total === 0 ? <h2>{t("courses.catalog.noneTitle")}</h2> : <h4>{t("courses.catalog.fewTitle")}</h4>}
      {st.q && data.did_you_mean && (
        <p className="hint">
          {t("courses.catalog.didYouMean")}{" "}
          <button type="button" onClick={() => onQuery(data.did_you_mean!)}>
            {data.did_you_mean}
          </button>
          ?
        </p>
      )}
      {gains.length > 0 && (
        <div className="chipset">
          {gains.map((g) => (
            <button key={`${g.k}:${g.v}`} type="button" className="chip" onClick={() => go({ ...st, f: { ...st.f, [g.k]: st.f[g.k].filter((x) => x !== g.v) } })}>
              {t("courses.catalog.removeGain", { what: label(g.k, g.v), n: g.g })}
            </button>
          ))}
        </div>
      )}
      {related.length > 0 && (
        <>
          <h4>{t("courses.catalog.related")}</h4>
          <div className="chipset">
            {related.map((s) => (
              <button key={s} type="button" className="chip" onClick={() => go({ ...st, q: "", f: { ...st.f, subject: [s] } })}>
                {subjectName(s, i18n.language)}
              </button>
            ))}
          </div>
        </>
      )}
      {data.total === 0 && !kid && (
        <p className="actions">
          <Link className="btn btn-ghost" to="/hoi-dap">
            <Icon name="chat" />
            <span>{t("courses.catalog.askMentor")}</span>
          </Link>
        </p>
      )}
    </div>
  );
}
