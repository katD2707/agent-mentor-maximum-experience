import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { coverUrl, type CatalogItem, type CatalogPage, type CourseDetail } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { fold } from "../../../lib/text";
import { onMediaError } from "../../../lib/mediaRetry";
import { addRecent, loadRecent, removeRecent } from "../../../lib/recentSearches";
import { enrollCourse } from "../../../lib/enrollCourse";
import { getCourseInfo } from "../../../lib/courseInfo";
import { formatMinutes, Highlight } from "../../kit/common";
import { FIND_FACETS, FIND_PER_PAGE, queryChicken, type FindFacet } from "../../api/chuong";
import { activeFilters, emptyFind, parseFind, toggleFacet, writeFind, type FindState } from "./logic";

type Load = { status: "loading" | "ready" | "error"; data: CatalogPage | null };

const Cover = ({ id, sha }: { id: string; sha: string }) => {
  const { token } = useAuth();
  const url = token ? coverUrl(token, id) : "";
  return <img src={url ? `${url}${url.includes("?") ? "&" : "?"}v=${sha}` : undefined} alt="" loading="lazy" onError={onMediaError} />;
};

/** The facet value in words. */
function useLabel() {
  const { t } = useTranslation();
  return (k: FindFacet, v: string) => t(`lg.cg.find.${k === "level" ? "level" : k === "language" ? "langName" : k === "duration" ? "duration" : "media"}.${v}`);
}

interface Props {
  chicken: string;
  name: string;
  band: NonNullable<ReturnType<typeof useAuth>["user"]>["age_band"];
  /** ids the student already has (enrolled) */
  owned: ReadonlySet<string>;
  /** a course was added: reload the coop; open it when the student taps "Xem" */
  onAdded(courseId: string): void;
  onSee(courseId: string): void;
  /** the preview's "Bắt đầu học" */
  onStart(courseId: string, lessonId?: string): void;
}

/** "Tìm thêm khóa" (lg-03): search, filters, sort and a 12-per-page list of more courses of this one chicken (free to add). */
export function FindBoard({ chicken, name, band, owned, onAdded, onSee, onStart }: Props) {
  const { t, i18n } = useTranslation();
  const { token, user } = useAuth();
  const [params, setParams] = useSearchParams();
  const kid = band === "g1_5";
  const st = useMemo(() => parseFind(params), [params]);
  const key = params.toString();
  const label = useLabel();
  const [load, setLoad] = useState<Load>({ status: "loading", data: null });
  const [tick, setTick] = useState(0);
  const [panel, setPanel] = useState(false);
  const [added, setAdded] = useState<Set<string>>(() => new Set());
  const [toast, setToast] = useState<{ text: string; id: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState(false);
  const listRef = useRef<HTMLUListElement>(null);
  const moved = useRef(false);
  const own = (id: string) => owned.has(id) || added.has(id);

  const go = useCallback(
    (next: FindState, keepPage = false) => setParams(writeFind(params, keepPage ? next : { ...next, page: 1 }), { replace: true }),
    [params, setParams],
  );

  useEffect(() => {
    if (!token || !band) return;
    let alive = true;
    setLoad((l) => ({ status: "loading", data: l.data }));
    queryChicken(token, chicken, band, st).then(
      (data) => alive && setLoad({ status: "ready", data }),
      () => alive && setLoad((l) => ({ status: "error", data: l.data })),
    );
    return () => {
      alive = false;
    };
    // st is derived from the address; key is its serialisation
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, band, chicken, key, tick]);
  const data = load.data;
  const words = useMemo(() => fold(st.q).split(/\s+/).filter(Boolean), [st.q]);

  // a new page: the first card scrolls into view and takes focus
  useEffect(() => {
    if (!moved.current || load.status !== "ready" || !data) return;
    moved.current = false;
    const first = listRef.current?.firstElementChild as HTMLElement | null;
    if (!first) return;
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    first.style.scrollMarginTop = "96px";
    first.scrollIntoView?.({ behavior: calm ? "auto" : "smooth", block: "start" });
    first.focus({ preventScroll: true });
  }, [data, load.status]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(id);
  }, [toast]);

  const add = async (id: string) => {
    if (!token || !user || busy || own(id)) return;
    setBusy(id);
    setErr(false);
    try {
      await enrollCourse(token, user.id, id);
      setAdded((s) => new Set(s).add(id));
      setToast({ text: t("lg.cg.find.toast", { name }), id });
      onAdded(id);
    } catch {
      setErr(true);
    } finally {
      setBusy(null);
    }
  };

  const total = data?.total ?? 0;
  const facetGroups = FIND_FACETS.map((k) => ({ k, opts: (data?.facets?.[k] ?? []).filter((o) => o.n > 0 || st.f[k].includes(o.v)) })).filter((g) => g.opts.length > 1 || g.opts.some((o) => st.f[g.k].includes(o.v)));
  const badge = activeFilters(st);
  const chips = FIND_FACETS.flatMap((k) => st.f[k].map((v) => ({ k, v })));
  const openPreview = (id: string | null) => go({ ...st, c: id }, true);

  return (
    <section className="ck-board" id="tim-khoa" aria-labelledby="ft">
      <h2 className="ck-ribbon" id="ft">
        {t("lg.cg.find.title")}
      </h2>
      <p className="ck-lead">{t("lg.cg.find.lead", { name })}</p>
      <SearchBox q={st.q} kid={kid} chicken={chicken} band={band} userId={user?.id ?? ""} onCommit={(q) => go({ ...st, q })} onLive={(q) => go({ ...st, q })}>
        {!kid && facetGroups.length > 0 && (
          <button className="ck-fbtn" type="button" aria-expanded={panel} aria-controls="fpanel" onClick={() => setPanel((p) => !p)}>
            <span>{t("lg.cg.find.filters")}</span>
            <b data-testid="filter-badge">{badge || ""}</b>
          </button>
        )}
      </SearchBox>
      {!kid && panel && (
        <div className="ck-fpanel" id="fpanel">
          {facetGroups.map((g) => (
            <div className="ck-fgroup" role="group" aria-label={t(`lg.cg.find.facet.${g.k}`)} key={g.k}>
              <span>{t(`lg.cg.find.facet.${g.k}`)}</span>
              <div className="ck-chipset">
                {g.opts.map((o) => (
                  <button key={o.v} type="button" className={`ck-chip${st.f[g.k].includes(o.v) ? " ck-on" : ""}${!o.n && !st.f[g.k].includes(o.v) ? " ck-zero" : ""}`} aria-pressed={st.f[g.k].includes(o.v)} onClick={() => go(toggleFacet(st, g.k, o.v))}>
                    {label(g.k, o.v)} <small>{o.n}</small>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="ck-sortbar">
        {!kid && (data?.total ?? 0) > 1 && (
          <div className="ck-sorts" role="group" aria-label={t("lg.cg.find.sortLabel")}>
            {(["rel", "new", "pop", "dur"] as const).map((s) => (
              <button key={s} type="button" aria-pressed={st.sort === s} onClick={() => go({ ...st, sort: s })}>
                {t(`lg.cg.find.sort.${s}`)}
              </button>
            ))}
          </div>
        )}
        <span className="ck-cnt" aria-live="polite">
          {data ? t(total === 1 ? "lg.cg.find.countOne" : "lg.cg.find.count", { count: total }) : ""}
        </span>
      </div>

      {!kid && chips.length > 0 && (
        <div className="ck-chips" data-testid="active-chips">
          {chips.map(({ k, v }) => (
            <button key={`${k}:${v}`} type="button" className="ck-chip" aria-label={t("lg.cg.find.removeFilter", { what: label(k, v) })} onClick={() => go(toggleFacet(st, k, v))}>
              {label(k, v)} <span aria-hidden="true">×</span>
            </button>
          ))}
          {chips.length > 1 && (
            <button type="button" className="ck-chip ck-clear" onClick={() => go({ ...st, page: 1, f: emptyFind().f })}>
              {t("lg.cg.find.clear")}
            </button>
          )}
        </div>
      )}

      {load.status === "error" && (
        <p className="ck-msg" role="alert">
          {t("lg.cg.find.failed")}
          <button type="button" onClick={() => setTick((n) => n + 1)}>
            {t("lg.cg.retry")}
          </button>
        </p>
      )}
      {load.status === "loading" && !data && (
        <p className="ck-msg" role="status">
          {t("lg.cg.find.loading")}
        </p>
      )}
      {err && (
        <p className="ck-msg" role="alert">
          {t("lg.cg.find.addFailed")}
        </p>
      )}

      <ul ref={listRef} className={`ck-pcs ck-pager-list${kid ? " ck-kid" : ""}`} aria-busy={load.status === "loading"} data-testid="results">
        {(data?.items ?? []).map((c: CatalogItem) => {
          const got = own(c.id);
          const soon = c.status === "coming_soon";
          return (
            <li key={c.id} className={`ck-pc${got ? " ck-got" : ""}`} tabIndex={-1} data-testid="course-card">
              <a className="ck-pcl" href={`#/chuong/${chicken}?c=${encodeURIComponent(c.id)}`} onClick={(e) => (e.preventDefault(), openPreview(c.id))}>
                <span className="ck-pimg">
                  <Cover id={c.id} sha={c.cover_sha256} />
                </span>
                <span className="ck-pbody">
                  <h3>
                    <Highlight text={c.title} words={words} />
                  </h3>
                  {!kid && (
                    <span className="ck-pm">
                      <Highlight text={c.teacher_name} words={words} /> · {t("lg.cg.find.lessonsN", { count: c.lessons_count })} · {formatMinutes(t, c.est_minutes)}
                    </span>
                  )}
                  <Tags lang={c.language} level={c.level ?? null} kid={kid} />
                </span>
              </a>
              <div className="ck-pfoot">
                {got ? (
                  <span className="ck-own ck-got">
                    <Icon name="check" />
                    {t("lg.cg.find.added")}
                  </span>
                ) : soon ? (
                  <button type="button" className="ck-soon" onClick={() => openPreview(c.id)}>
                    {t("lg.cg.find.soon")}
                  </button>
                ) : (
                  <button type="button" className="ck-own" disabled={busy === c.id} onClick={() => void add(c.id)}>
                    {busy === c.id ? t("lg.cg.find.adding") : t("lg.cg.find.add")}
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {data && (data.total === 0 || data.total < 4) && load.status === "ready" && <Few chicken={chicken} band={band} data={data} st={st} go={go} />}

      <Pager
        page={data?.page ?? st.page}
        pages={data?.pages ?? 1}
        hidden={!data || data.total === 0}
        onGo={(n) => {
          moved.current = true;
          go({ ...st, page: n }, true);
        }}
      />

      {st.c && <Preview id={st.c} name={name} chicken={chicken} owned={own(st.c)} busy={busy === st.c} onClose={() => openPreview(null)} onAdd={() => void add(st.c as string)} onStart={onStart} onSee={onSee} lang={i18n.language} />}
      <div id="fmsg-host" role="status" aria-live="polite">
        {toast && (
          <div className="ck-fmsg">
            <span>{toast.text}</span>
            <button type="button" onClick={() => (setToast(null), onSee(toast.id))}>
              {t("lg.cg.find.see")}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function Tags({ lang, level, kid }: { lang: string; level: string | null; kid: boolean }) {
  const { t } = useTranslation();
  const n = level === "advanced" ? 3 : level === "intermediate" ? 2 : level === "basic" ? 1 : 0;
  return (
    <span className="ck-ctags">
      {!kid && (lang === "en" ? <span className="ck-ct ck-ct-en"><b>EN</b> English</span> : <span className="ck-ct">{t("lg.cg.find.langName.vi")}</span>)}
      {n > 0 && (
        <span className="ck-ct">
          <span className="ck-bars" aria-hidden="true">
            <i className="ck-on" />
            <i className={n > 1 ? "ck-on" : ""} />
            <i className={n > 2 ? "ck-on" : ""} />
          </span>
          {t(`lg.cg.find.level.${level}`)}
        </span>
      )}
    </span>
  );
}

function Pager({ page, pages, hidden, onGo }: { page: number; pages: number; hidden: boolean; onGo(n: number): void }) {
  const { t } = useTranslation();
  if (hidden) return null;
  const lo = Math.max(1, Math.min(page - 2, pages - 4));
  const hi = Math.min(pages, lo + 4);
  const nums: number[] = [];
  for (let i = lo; i <= hi; i++) nums.push(i);
  const chev = (d: "l" | "r") => (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d={d === "l" ? "M14.5 5.5 8 12l6.5 6.5" : "M9.5 5.5 16 12l-6.5 6.5"} />
    </svg>
  );
  return (
    <nav className="ck-pager" aria-label={t("lg.cg.find.page")}>
      <button type="button" disabled={page <= 1} onClick={() => onGo(page - 1)} aria-label={t("lg.cg.find.prev")}>
        {chev("l")}
      </button>
      {nums.map((n) => (
        <button key={n} type="button" aria-current={n === page ? "page" : undefined} onClick={() => n !== page && onGo(n)} aria-label={t("lg.cg.find.pageN", { n })}>
          {n}
        </button>
      ))}
      <button type="button" disabled={page >= pages} onClick={() => onGo(page + 1)} aria-label={t("lg.cg.find.next")}>
        {chev("r")}
      </button>
    </nav>
  );
}

// ------------------------------------------------------------------ search box and autocomplete
interface SpeechRec {
  lang: string;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
}

function SearchBox({ q, kid, chicken, band, userId, onCommit, onLive, children }: { q: string; kid: boolean; chicken: string; band: Props["band"]; userId: string; onCommit(q: string): void; onLive(q: string): void; children?: React.ReactNode }) {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const [draft, setDraft] = useState(q);
  const [open, setOpen] = useState(false);
  const [recent, setRecent] = useState<string[]>(() => (userId ? loadRecent(userId) : []));
  const [sug, setSug] = useState<{ courses: string[]; teachers: string[] } | null>(null);
  const [note, setNote] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const live = useRef(q);
  const onLiveRef = useRef(onLive);
  onLiveRef.current = onLive;

  useEffect(() => {
    if (q !== live.current) setDraft(q); // changed from outside ("did you mean", a reset)
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

  // suggestions come from this chicken's own courses
  useEffect(() => {
    const s = draft.trim();
    if (!token || !band || !open || !s || kid) return void setSug(null);
    let alive = true;
    const id = setTimeout(() => {
      queryChicken(token, chicken, band, { ...emptyFind(), q: s }).then(
        (r) => alive && setSug({ courses: r.items.slice(0, 4).map((c) => c.title), teachers: [...new Set(r.items.map((c) => c.teacher_name))].filter((x) => fold(x).includes(fold(s))).slice(0, 3) }),
        () => alive && setSug(null),
      );
    }, 120);
    return () => {
      alive = false;
      clearTimeout(id);
    };
  }, [draft, open, token, band, chicken, kid]);

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
    if (userId && s) setRecent(addRecent(userId, s));
    onCommit(s);
  };
  const items = () => Array.from(box.current?.querySelectorAll<HTMLElement>(".ck-ac .ck-it") ?? []);
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
    const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
    const SR = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!SR) return setNote(t("lg.cg.find.micNone"));
    const r = new SR();
    r.lang = i18n.language.startsWith("en") ? "en-US" : "vi-VN";
    r.onresult = (e) => pick(e.results[0][0].transcript);
    r.onend = () => setNote("");
    r.onerror = () => setNote(t("lg.cg.find.micNone"));
    setNote(t("lg.cg.find.micListening"));
    r.start();
  };

  const s = draft.trim();
  const bold = (text: string) => <Highlight text={text} words={fold(draft).split(/\s+/).filter(Boolean)} />;
  return (
    <div className="ck-sbar" ref={box} onKeyDown={keys}>
      <form
        className="ck-msearch"
        role="search"
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
          onChange={(e) => (setDraft(e.target.value), setOpen(true))}
          onFocus={() => setOpen(true)}
          placeholder={kid ? t("lg.cg.find.kidPlaceholder") : t("lg.cg.find.placeholder")}
          aria-label={t("lg.cg.find.label")}
          aria-autocomplete="list"
          aria-controls="ac"
          aria-expanded={open}
          autoComplete="off"
        />
        <button className="ck-mic" type="button" aria-label={t("lg.cg.find.mic")} onClick={listen}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
          </svg>
        </button>
      </form>
      {children}
      {note && (
        <p className="ck-msg" role="status">
          {note}
        </p>
      )}
      {open && !kid && (
        <div className="ck-ac" id="ac">
          {!s
            ? recent.length > 0 && (
                <>
                  <h4>{t("lg.cg.find.recent")}</h4>
                  {recent.map((r) => (
                    <div className="ck-row" key={r}>
                      <button type="button" className="ck-it" onClick={() => pick(r)}>
                        <span>{r}</span>
                      </button>
                      <button type="button" className="ck-it ck-x" aria-label={t("lg.cg.find.removeRecent", { q: r })} onClick={() => setRecent(removeRecent(userId, r))}>
                        ×
                      </button>
                    </div>
                  ))}
                </>
              )
            : sug && (
                <>
                  {sug.courses.length > 0 && <h4>{t("lg.cg.find.groupCourses")}</h4>}
                  {sug.courses.map((c) => (
                    <button key={c} type="button" className="ck-it" onClick={() => pick(c)}>
                      <span>{bold(c)}</span>
                    </button>
                  ))}
                  {sug.teachers.length > 0 && <h4>{t("lg.cg.find.groupTeachers")}</h4>}
                  {sug.teachers.map((x) => (
                    <button key={x} type="button" className="ck-it" onClick={() => pick(x)}>
                      <span>{bold(x)}</span>
                    </button>
                  ))}
                  {!sug.courses.length && !sug.teachers.length && <p className="ck-hint">{t("lg.cg.find.noSuggest")}</p>}
                </>
              )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ few or no results
function Few({ chicken, band, data, st, go }: { chicken: string; band: Props["band"]; data: CatalogPage; st: FindState; go(s: FindState): void }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const label = useLabel();
  const [gains, setGains] = useState<{ k: FindFacet; v: string; g: number }[]>([]);
  const sig = JSON.stringify([st.q, st.f, data.total]);
  useEffect(() => {
    if (!token || !band) return;
    let alive = true;
    const tries = FIND_FACETS.flatMap((k) => st.f[k].map((v) => ({ k, v })));
    void Promise.all(
      tries.map(async ({ k, v }) => {
        const f = { ...st.f, [k]: st.f[k].filter((x) => x !== v) };
        const r = await queryChicken(token, chicken, band, { ...st, f, page: 1 });
        return { k, v, g: r.total - data.total };
      }),
    )
      .then((all) => alive && setGains(all.filter((x) => x.g > 0).sort((a, b) => b.g - a.g).slice(0, 3)))
      .catch(() => alive && setGains([]));
    return () => {
      alive = false;
    };
    // sig covers the query and the total
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, chicken, sig]);
  const filtered = !!st.q || activeFilters(st) > 0;
  if (data.total >= 4) return null;
  if (!filtered && data.total > 0) return null; // a chicken with a handful of courses is not a problem
  return (
    <div className="ck-none" data-testid="few-results">
      {data.total === 0 && (filtered ? <h3>{t("lg.cg.find.noneTitle")}</h3> : <><h3>{t("lg.cg.find.empty")}</h3><p>{t("lg.cg.find.emptyLead")}</p></>)}
      {data.total > 0 && filtered && <h3>{t("lg.cg.find.fewTitle")}</h3>}
      {st.q && data.did_you_mean && (
        <p className="ck-hint">
          {t("lg.cg.find.didYouMean")}{" "}
          <button type="button" onClick={() => go({ ...st, q: data.did_you_mean as string })}>
            {data.did_you_mean}
          </button>
          ?
        </p>
      )}
      {filtered && (
        <div className="ck-chipset">
          {gains.map((g) => (
            <button key={`${g.k}:${g.v}`} type="button" className="ck-chip" onClick={() => go(toggleFacet(st, g.k, g.v))}>
              {t("lg.cg.find.drop", { what: label(g.k, g.v), n: g.g })}
            </button>
          ))}
          {data.total === 0 && (
            <button type="button" className="ck-chip ck-clear" onClick={() => go({ ...emptyFind(), sort: st.sort })}>
              {t("lg.cg.find.showAll")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ course preview: a dialog over the page
function Preview({ id, name, chicken, owned, busy, onClose, onAdd, onStart, onSee, lang }: { id: string; name: string; chicken: string; owned: boolean; busy: boolean; onClose(): void; onAdd(): void; onStart(courseId: string, lessonId?: string): void; onSee(courseId: string): void; lang: string }) {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [info, setInfo] = useState<CourseDetail | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const x = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setState("loading");
    getCourseInfo(token, id).then(
      (i) => alive && (setInfo(i), setState("ready")),
      () => alive && setState("error"),
    );
    return () => {
      alive = false;
    };
  }, [token, id]);

  useEffect(() => {
    opener.current = document.activeElement;
    document.body.style.overflow = "hidden";
    x.current?.focus({ preventScroll: true });
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("keydown", esc);
      document.body.style.overflow = "";
      (opener.current as HTMLElement | null)?.focus?.({ preventScroll: true });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const soon = info?.status === "coming_soon";
  const lessons = info?.tree.flatMap((c) => c.lessons) ?? [];
  let no = 0;
  return (
    <div className="ck-pv-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ck-pv" role="dialog" aria-modal="true" aria-labelledby="pv-t" data-chicken={chicken} data-lang={lang}>
        <button className="ck-pv-x" type="button" ref={x} aria-label={t("lg.cg.pv.close")} onClick={onClose}>
          <Icon name="x" />
        </button>
        <div className="ck-pv-in">
          {state === "loading" && <p className="ck-msg" role="status">{t("lg.cg.pv.loading")}</p>}
          {state === "error" && <p className="ck-msg" role="alert">{t("lg.cg.pv.failed")}</p>}
          {state === "ready" && info && (
            <>
              <section className="ck-pv-hero">
                <span className="ck-hi">
                  <Cover id={info.id} sha="" />
                </span>
                <div>
                  <h2 id="pv-t">{info.title}</h2>
                  <p className="ck-pm">
                    {info.teacher_name} · {t("lg.cg.find.lessonsN", { count: info.lessons_count })} · {formatMinutes(t, info.est_minutes)}
                  </p>
                  <Tags lang={info.language} level={info.level ?? null} kid={false} />
                </div>
              </section>
              {info.description_short && <p className="ck-pv-about">{info.description_short}</p>}
              <div className="ck-pv-cta">
                {soon ? (
                  <span className="ck-note">{t("lg.cg.pv.soonNote")}</span>
                ) : owned ? (
                  <>
                    <button type="button" className="ck-gbtn" onClick={() => onStart(id, lessons[0]?.id)}>
                      {t("lg.cg.pv.start")}
                    </button>
                    <button type="button" className="ck-gbtn" style={{ background: "#e9dcc4", color: "#4a3220", boxShadow: "none" }} onClick={() => (onClose(), onSee(id))}>
                      {t("lg.cg.find.see")}
                    </button>
                    <span className="ck-note">{t("lg.cg.pv.have")}</span>
                  </>
                ) : (
                  <>
                    <button type="button" className="ck-gbtn" disabled={busy} onClick={onAdd}>
                      {t("lg.cg.pv.addTo", { name })}
                    </button>
                    <span className="ck-note">{t("lg.cg.pv.free")}</span>
                  </>
                )}
              </div>
              <nav className="ck-tree" aria-label={t("lg.cg.treeAria", { title: info.title })}>
                {info.tree.map((ch, i) => (
                  <details key={ch.id} className="ck-grp" open={i === 0 || info.tree.length <= 3}>
                    <summary className="ck-node">
                      <span className="ck-chev">
                        <Icon name="chev" />
                      </span>
                      <span className="ck-ic">
                        <Icon name="book" />
                      </span>
                      <span className="ck-t">{ch.title}</span>
                      <span className="ck-end">{ch.lessons.length}</span>
                    </summary>
                    <div className="ck-kids">
                      {ch.lessons.map((l) => {
                        no += 1;
                        return (
                          <div className="ck-node" key={l.id}>
                            <span className="ck-no">{no}</span>
                            <span className="ck-t">{l.title}</span>
                            <span className="ck-end" />
                          </div>
                        );
                      })}
                    </div>
                  </details>
                ))}
                {info.outcomes.length > 0 && (
                  <details className="ck-grp">
                    <summary className="ck-node">
                      <span className="ck-chev">
                        <Icon name="chev" />
                      </span>
                      <span className="ck-ic">
                        <Icon name="target" />
                      </span>
                      <span className="ck-t">{t("lg.cg.pv.after")}</span>
                      <span className="ck-end" />
                    </summary>
                    <div className="ck-kids">
                      {info.outcomes.map((o) => (
                        <div className="ck-node ck-out" key={o}>
                          <span className="ck-t">{o}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </nav>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export { FIND_PER_PAGE };
