import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { practice, PracticeError, type PCourseLevels, type StartSource } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { ArDialog } from "../practice/Dialog";
import { ResumeCard } from "./Resume";
import { Shell } from "./common";

const MIN_MOCK_ITEMS = 6;
const MOCK_ITEMS = 22;

/** Same sizing as the gateway: 22 questions or all of them, 2 minutes each, at most 45. */
export const courseMockSize = (n: number): { items: number; minutes: number } => {
  const items = Math.min(MOCK_ITEMS, n);
  return { items, minutes: Math.min(45, items * 2) };
};

type Load = { s: "loading" } | { s: "error" } | { s: "ready"; data: PCourseLevels };

/**
 * `/kiem-tra/:courseId` (mockups/lg-07): the course mock exam (only questions of this course) and the practice levels of the
 * course, from easy to hard. Runs opened here return here. `?state=thi` opens the mock exam's "ready?" dialog and
 * `?state=luyen&level=N` starts that practice level at once (what a link from outside lands on); `from=chuong` is the default way back.
 */
export function CourseTests() {
  const { courseId = "" } = useParams();
  const { t } = useTranslation();
  const { token, user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [params, setParams] = useSearchParams();
  const band = user?.age_band === "g1_5" ? "kid" : user?.age_band === "uni" ? "uni" : "school";
  const [st, setSt] = useState<Load>({ s: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const here = `/kiem-tra/${encodeURIComponent(courseId)}`;
  const back = (loc.state as { back?: string } | null)?.back ?? `/khoa-hoc/${encodeURIComponent(courseId)}`;

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setSt({ s: "loading" });
    practice.courseLevels(token, courseId).then(
      (data) => alive && setSt({ s: "ready", data }),
      () => alive && setSt({ s: "error" }),
    );
    return () => {
      alive = false;
    };
  }, [token, courseId, attempt]);

  const start = useCallback(
    async (key: string, source: StartSource, level?: number) => {
      if (!token || starting) return;
      setStarting(key);
      setError(null);
      setConfirm(false);
      const state = { back: here };
      try {
        const s = await practice.start(token, { source, ...(level ? { level } : {}) });
        nav(`/luyen-tap/${encodeURIComponent(s.id)}`, { state });
      } catch (e) {
        if (e instanceof PracticeError && e.code === "active_session" && typeof e.body.session_id === "string") nav(`/luyen-tap/${encodeURIComponent(e.body.session_id)}`, { state });
        else setError(e instanceof PracticeError ? (e.code === "insufficient_content" ? "insufficient" : e.code === "coming_soon" ? "coming" : e.code === "course_not_found" ? "none" : "failed") : "failed");
        setStarting(null);
      }
    },
    [here, nav, starting, token],
  );

  // a link with ?state= goes straight to what it names, once
  const want = useRef({ state: params.get("state"), level: Number(params.get("level")) || 0 });
  const data = st.s === "ready" ? st.data : null;
  useEffect(() => {
    if (!data || !want.current.state) return;
    const { state, level } = want.current;
    want.current = { state: null, level: 0 };
    setParams(new URLSearchParams(params.get("from") ? { from: params.get("from") as string } : {}), { replace: true });
    if (state === "thi" && band !== "kid" && data.levels.reduce((n, l) => n + l.items, 0) >= MIN_MOCK_ITEMS) setConfirm(true);
    else if (state === "luyen" && level && data.levels.some((l) => l.level === level && l.items > 0 && l.studied >= data.min_items)) void start(`l${level}`, `course:${courseId}`, level);
    // only when the levels arrive
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  const levels = (data?.levels ?? []).filter((l) => l.items > 0 && (band !== "kid" || l.level <= 3));
  const totalItems = (data?.levels ?? []).reduce((s, l) => s + l.items, 0);
  const mock = courseMockSize(totalItems);
  const canMock = band !== "kid" && totalItems >= MIN_MOCK_ITEMS;

  return (
    <Shell title={t("lg.kt.title")}>
      <div className="ar-stack">
        <div className="ar-hubtop">
          <Link className="ar-btn wood" to={back} replace>
            <Icon name="back" />
            <span>{t("lg.kt.back")}</span>
          </Link>
        </div>
        {st.s === "loading" && (
          <p className="ar-muted" role="status">
            {t("lg.loading")}
          </p>
        )}
        {st.s === "error" && (
          <div className="ar-stack">
            <p role="alert">{t("lg.kt.loadFailed")}</p>
            <button className="ar-btn wood" type="button" onClick={() => setAttempt((n) => n + 1)}>
              {t("lg.kt.retry")}
            </button>
          </div>
        )}
        {data && (
          <>
            <ResumeCard back={here} only={(s) => !!s.source && s.source.endsWith(`:${courseId}`)} />
            <p className="ar-muted" style={{ margin: 0 }}>
              {data.title ? <b>{data.title}. </b> : null}
              {t("lg.kt.lead")}
            </p>

            {band !== "kid" && (
              <div className="ar-course">
                <span className="ar-ico" aria-hidden="true">
                  <Icon name="clock" />
                </span>
                <div>
                  <h2>{t("lg.kt.mock")}</h2>
                  <p>{canMock ? t("lg.kt.mockMeta", { items: mock.items, minutes: mock.minutes }) : t("lg.kt.notEnough")}</p>
                </div>
                <button className="ar-btn" type="button" disabled={!canMock || !!starting} onClick={() => setConfirm(true)}>
                  {t("lg.kt.mockGo")}
                </button>
              </div>
            )}

            {levels.length > 0 && (
              <>
                <h2 className="ar-sec">{t("lg.kt.ladder")}</h2>
                <p className="ar-muted" style={{ margin: "-8px 0 0" }}>
                  {t("lg.kt.ladderLead")}
                </p>
                <ul className="ar-levels" aria-label={t("lg.kt.ladder")}>
                  {levels.map((l) => {
                    const open = l.studied >= data.min_items;
                    const now = data.suggested === l.level && !l.solid;
                    const pct = l.answered ? Math.round((l.correct / l.answered) * 100) : 0;
                    const name = t(`lg.kt.level.${band}.${l.level}`);
                    return (
                      <li key={l.level} className={`${now ? "now" : ""}${open ? "" : " ar-later"}`}>
                        <span className="ar-lvno" aria-hidden="true">
                          {band === "kid" ? "★".repeat(l.level) : l.level}
                        </span>
                        <div>
                          <h3>{name}</h3>
                          <p>{open ? [l.answered ? t("lg.kt.levelMeta", { items: l.items, pct }) : t("lg.kt.levelItems", { items: l.items }), l.solid ? t("lg.kt.levelSolid") : now ? t("lg.kt.levelNow") : null].filter(Boolean).join(" · ") : t("lg.kt.levelLater")}</p>
                        </div>
                        {open && (
                          <button className={`ar-btn ${now ? "" : "wood"}`} type="button" disabled={!!starting} aria-label={`${name}: ${t(band === "kid" ? "lg.kt.levelStartKid" : "lg.kt.levelStart")}`} onClick={() => void start(`l${l.level}`, `course:${courseId}`, l.level)}>
                            {t(band === "kid" ? "lg.kt.levelStartKid" : "lg.kt.levelStart")}
                          </button>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
            {error && (
              <p className="ar-note crit" role="alert">
                {t(`lg.kt.${error}`)}
              </p>
            )}
          </>
        )}
      </div>

      {confirm && (
        <ArDialog title={t("lg.ar.ready")} onClose={() => setConfirm(false)}>
          <p>
            <b>{t("lg.kt.mock")}</b>
          </p>
          <p>{t("lg.kt.mockConfirmBody", { items: mock.items, minutes: mock.minutes })}</p>
          <div className="ar-acts">
            <button className="ar-btn wood" type="button" onClick={() => setConfirm(false)}>
              {t("lg.kt.mockLater")}
            </button>
            <button className="ar-btn" type="button" onClick={() => void start("mock", `course-mock:${courseId}`)}>
              {t("lg.ar.start")}
            </button>
          </div>
        </ArDialog>
      )}
    </Shell>
  );
}
