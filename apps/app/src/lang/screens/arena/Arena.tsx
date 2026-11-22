import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { lg, type ArenaPaper } from "../../api";
import { practice, PracticeError, type PHome } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { fmtScore10 } from "../../../lib/practice";
import { subjectOf } from "../../subjects";
import { BossArt } from "./Bosses";
import { ResumeCard } from "./Resume";
import { Shell, useLang } from "./common";

type Mock = PHome["mocks"][number];
type Load = { s: "loading" } | { s: "error" } | { s: "ready"; papers: ArenaPaper[]; mocks: Mock[] };

const BACK = { back: "/dau-truong" };

/** The red gate banner at the top of the hub (mockups/lg-05). */
function Gate() {
  return (
    <div className="ar-gate" aria-hidden="true">
      <svg viewBox="0 0 800 130" preserveAspectRatio="xMidYMax slice">
        <ellipse cx="400" cy="126" rx="520" ry="30" fill="#9ccf78" />
        <ellipse cx="400" cy="108" rx="300" ry="22" fill="#e9cf98" />
        <g transform="translate(200 20)">
          <path d="M20 70 Q20 44 56 44 L344 44 Q380 44 380 70 L380 82 Q380 90 340 90 L60 90 Q20 90 20 82Z" fill="#c2402a" />
          <path d="M20 58 L380 58" stroke="#fff" strokeWidth="4" opacity=".85" />
          <path d="M20 74 L380 74" stroke="#8f2d1c" strokeWidth="3" />
          <g stroke="#7d4c22" strokeWidth="3">
            <path d="M70 44V12M150 44V6M250 44V6M330 44V12" />
          </g>
          <path d="M70 12l24 6-24 6z" fill="#ffcf3d" />
          <path d="M150 6l24 6-24 6z" fill="#e2573a" />
          <path d="M250 6l24 6-24 6z" fill="#ffcf3d" />
          <path d="M330 12l24 6-24 6z" fill="#e2573a" />
          <g fill="#fff">
            <circle cx="112" cy="66" r="3" />
            <circle cx="200" cy="66" r="3" />
            <circle cx="288" cy="66" r="3" />
          </g>
        </g>
      </svg>
    </div>
  );
}

/** `/dau-truong` (the list of real papers and practice papers) and `/dau-truong/:paper` (the confirm card). */
export function Arena() {
  const { t } = useTranslation();
  const lang = useLang();
  const { token, user } = useAuth();
  const nav = useNavigate();
  const { paper: paperId } = useParams();
  const uni = user?.age_band === "uni";
  const [st, setSt] = useState<Load>({ s: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [subj, setSubj] = useState("all");
  const [year, setYear] = useState("all");
  const [bank, setBank] = useState<Mock | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setSt({ s: "loading" });
    Promise.all([lg.arenaPapers(token), practice.home(token).then((h) => h.mocks, () => [] as Mock[])]).then(
      ([papers, mocks]) => alive && setSt({ s: "ready", papers, mocks }),
      () => alive && setSt({ s: "error" }),
    );
    return () => {
      alive = false;
    };
  }, [token, attempt]);

  const papers = st.s === "ready" ? st.papers : [];
  // practice papers of the bank are written for one age band (grades 10-12 unless it says so): not shown to the others
  const mocks = st.s === "ready" ? st.mocks.filter((m) => (m.band ?? "g10_12") === (user?.age_band ?? "g10_12")) : [];
  // the "sample" tag says it: the title does not repeat "(đề mẫu)"
  const title = (p: ArenaPaper) => (lang === "en" ? p.title_en || p.title_vi : p.title_vi).replace(/\s*\((đề mẫu|sample)\)\s*$/i, "");
  const bossName = (p: ArenaPaper) => (lang === "en" ? p.boss.name_en : p.boss.name_vi);
  const chickens = useMemo(() => [...new Set(papers.map((p) => p.chicken))], [papers]);
  const years = useMemo(() => [...new Set(papers.map((p) => p.year))].sort((a, b) => b - a), [papers]);
  const rows = papers.filter((p) => (subj === "all" || p.chicken === subj) && (year === "all" || String(p.year) === year));
  const picked = paperId ? papers.find((p) => p.id === paperId) : undefined;

  const start = useCallback(
    async (source: `paper:${string}` | `mock:${string}`) => {
      if (!token || starting) return;
      setStarting(true);
      setError(null);
      try {
        const s = await practice.start(token, { source });
        nav(`/luyen-tap/${encodeURIComponent(s.id)}`, { state: BACK });
      } catch (e) {
        if (e instanceof PracticeError && e.code === "active_session" && typeof e.body.session_id === "string") nav(`/luyen-tap/${encodeURIComponent(e.body.session_id)}`, { state: BACK });
        else {
          setError(e instanceof PracticeError && e.code === "unknown_paper" ? "unknown" : e instanceof PracticeError && e.code === "band_mismatch" ? "mismatch" : "startFailed");
          setStarting(false);
        }
      }
    },
    [nav, starting, token],
  );

  const chip = (p: ArenaPaper) => <span className="ar-chip real">{t(p.placeholder ? "lg.ar.sample" : "lg.ar.real")}</span>;

  // ---- confirm card of a real paper
  if (paperId && st.s === "ready" && picked) {
    const p = picked;
    return (
      <Shell title={t("lg.ar.ready")}>
        <div className="ar-cf">
          <BossArt art={p.boss.art} className="ar-btile big" />
          <div>
            <h2>{title(p)}</h2> {chip(p)}
          </div>
          <p className="ar-bossline">{t(p.placeholder ? "lg.ar.bossLineSample" : "lg.ar.bossLine", { name: bossName(p) })}</p>
          <ul className="ar-facts" aria-label={t("lg.ar.title")}>
            {[t("lg.ar.minutes", { count: p.minutes }), t("lg.ar.questions", { count: p.items }), t("lg.ar.factAuto"), t("lg.ar.factNoHint")].map((x) => (
              <li className="ar-chip" key={x}>
                {x}
              </li>
            ))}
          </ul>
          {error && (
            <p className="ar-note crit" role="alert">
              {t(`lg.ar.${error}`)}
            </p>
          )}
          <div className="ar-acts" style={{ justifyContent: "center" }}>
            <button className="ar-btn big" type="button" disabled={starting} onClick={() => void start(`paper:${p.id}`)}>
              <Icon name="play" />
              <span>{t("lg.ar.start")}</span>
            </button>
            <Link className="ar-btn quiet" to="/dau-truong" replace>
              {t("lg.ar.cancel")}
            </Link>
          </div>
        </div>
      </Shell>
    );
  }

  // ---- confirm card of a practice paper (bank mock)
  if (bank) {
    return (
      <Shell title={t("lg.ar.ready")}>
        <div className="ar-cf">
          <span className="ar-btile big" aria-hidden="true">
            <Icon name="clock" />
          </span>
          <div>
            <h2>{bank.title}</h2> <span className="ar-chip mock">{t("lg.ar.practiceTag")}</span>
          </div>
          <ul className="ar-facts" aria-label={t("lg.ar.practiceTitle")}>
            {[t("lg.ar.minutes", { count: bank.minutes }), t("lg.ar.questions", { count: bank.items }), t("lg.ar.factAuto"), t("lg.ar.factHidden")].map((x) => (
              <li className="ar-chip" key={x}>
                {x}
              </li>
            ))}
          </ul>
          {error && (
            <p className="ar-note crit" role="alert">
              {t("lg.ar.startFailed")}
            </p>
          )}
          <div className="ar-acts" style={{ justifyContent: "center" }}>
            <button className="ar-btn big" type="button" disabled={starting} onClick={() => void start(`mock:${bank.profile_id}`)}>
              <Icon name="play" />
              <span>{t("lg.ar.start")}</span>
            </button>
            <button className="ar-btn quiet" type="button" onClick={() => (setBank(null), setError(null))}>
              {t("lg.ar.cancel")}
            </button>
          </div>
        </div>
      </Shell>
    );
  }

  return (
    <Shell title={t("lg.ar.title")}>
      <div className="ar-stack">
        <div className="ar-hubtop">
          <Link className="ar-btn wood" to="/">
            <Icon name="back" />
            <span>{t("lg.ar.back")}</span>
          </Link>
        </div>
        <Gate />
        <ResumeCard back="/dau-truong" />
        <p className="ar-muted" style={{ margin: 0 }}>
          {t(uni ? "lg.ar.leadUni" : "lg.ar.leadSchool")}
        </p>

        {st.s === "loading" && (
          <p className="ar-muted" role="status">
            {t("lg.loading")}
          </p>
        )}
        {st.s === "error" && (
          <div className="ar-stack">
            <p role="alert">{t("lg.ar.loadFailed")}</p>
            <button className="ar-btn wood" type="button" onClick={() => setAttempt((n) => n + 1)}>
              {t("practice.retry")}
            </button>
          </div>
        )}
        {paperId && st.s === "ready" && !picked && (
          <p className="ar-note crit" role="alert">
            {t("lg.ar.unknown")}
          </p>
        )}

        {st.s === "ready" && papers.length > 0 && (
          <>
            <div className="ar-filters">
              <div className="ar-fgrp" role="group" aria-label={t("lg.ar.subjects")}>
                {["all", ...chickens].map((c) => (
                  <button key={c} type="button" className="ar-fchip" aria-pressed={subj === c} onClick={() => setSubj(c)}>
                    {c === "all" ? t("lg.ar.all") : lang === "en" ? subjectOf(c)?.en ?? c : subjectOf(c)?.vi ?? c}
                  </button>
                ))}
              </div>
              <label className="ar-yr">
                <span className="lg-vh">{t("lg.ar.year")}</span>
                <select value={year} onChange={(e) => setYear(e.target.value)} aria-label={t("lg.ar.year")}>
                  <option value="all">{t("lg.ar.anyYear")}</option>
                  {years.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <ul className="ar-rows" aria-label={t("lg.ar.title")}>
              {rows.map((p) => (
                <li key={p.id}>
                  <BossArt art={p.boss.art} />
                  <div>
                    <h3>
                      {title(p)} {chip(p)}
                    </h3>
                    <p>
                      {[t("lg.ar.minutes", { count: p.minutes }), t("lg.ar.questions", { count: p.items }), t("lg.ar.boss", { name: bossName(p) }), p.best_score != null ? t("lg.ar.best", { score: fmtScore10(p.best_score, lang) }) : null, p.beaten ? t("lg.ar.beaten") : null].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <Link className="ar-btn wood" to={`/dau-truong/${encodeURIComponent(p.id)}`}>
                    {t("lg.ar.take")}
                  </Link>
                </li>
              ))}
            </ul>
            {rows.length === 0 && <p className="ar-muted ar-empty">{t("lg.ar.empty")}</p>}
          </>
        )}
        {st.s === "ready" && papers.length === 0 && <p className="ar-muted ar-empty">{t("lg.ar.empty")}</p>}

        {st.s === "ready" && mocks.length > 0 && (
          <>
            <h2 className="ar-sec">{t("lg.ar.practiceTitle")}</h2>
            <p className="ar-muted" style={{ margin: "-8px 0 0" }}>
              {t("lg.ar.practiceLead")}
            </p>
            <ul className="ar-rows" aria-label={t("lg.ar.practiceTitle")}>
              {mocks.map((m) => (
                <li key={m.profile_id}>
                  <span className="ar-ico" aria-hidden="true">
                    <Icon name="clock" />
                  </span>
                  <div>
                    <h3>
                      {m.title} <span className="ar-chip mock">{t("lg.ar.practiceTag")}</span>
                    </h3>
                    <p>{[t("lg.ar.minutes", { count: m.minutes }), t("lg.ar.questions", { count: m.items }), m.last_score != null ? t("lg.ar.last", { score: fmtScore10(m.last_score, lang) }) : null].filter(Boolean).join(" · ")}</p>
                  </div>
                  <button className="ar-btn wood" type="button" onClick={() => setBank(m)}>
                    {t("lg.ar.take")}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Shell>
  );
}
