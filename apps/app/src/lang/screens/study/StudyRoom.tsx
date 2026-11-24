import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../state/auth";
import { Icon } from "../../../components/Icon";
import { holdFocus } from "../../../lib/behaviour";
import { lg, type Chicken, type FocusActive, type Village } from "../../api";
import { chickenName, XP_PER_LEVEL } from "../../subjects";
import { chickenSrc, jumpSrc } from "../../chickenArt";
import { Crown } from "../../components/Crown";
import { ChickenImg, FlameIcon } from "./icons";
import "../../styles/fonts";
import { emitXp } from "../../xp";
import "../../styles/lang.css";
import "../../styles/study.css";

const base = import.meta.env.BASE_URL;
const DURATIONS = [15, 25, 45];
const MORE_MIN = 15;
const STREAK_MIN = 10;
const FULL_BONUS = 5;
const TICK_MS = 250;
/** a tab hidden longer than this pauses the clock (the hidden time is not counted) */
const HIDE_GRACE_MS = 30000;
const RING = 2 * Math.PI * 100;

type Phase = "choose" | "run" | "pause" | "stop" | "done";
interface Run {
  id: string;
  chicken: string;
  minutes: number;
  /** when the countdown began (ms); a pause moves it forward so the countdown simply stands still */
  startMs: number;
}
interface Result {
  gain: number;
  done: number;
  planned: number;
  full: boolean;
  before: Chicken;
  after: Chicken;
}

const mmss = (sec: number) => `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

/** The sprite of a chicken in the pond: the standing sheet where there is one, else its picture at its growth stage. */
function pondSprite(c: Chicken | undefined, mode: "idle" | "still" | "jump"): string {
  if (!c) return `${base}ga/toan.webp`;
  if (mode === "jump") return jumpSrc(c.art, c.stage, !!c.angry) ?? chickenSrc(c.art, c.stage, "stand", true, !!c.angry);
  return chickenSrc(c.art, c.stage, "stand", mode !== "idle", !!c.angry);
}

/** The two rings of rocks around the pond (the same stones every time). */
function rocks(from: number, to: number, n: number, seed: number) {
  let r = seed;
  const rnd = () => (r = (r * 9301 + 49297) % 233280) / 233280;
  const fills = ["#a3a9b5", "#8a909d", "#b8bdc8", "#7d8391"];
  return Array.from({ length: n }, (_, i) => {
    const a = ((from + ((to - from) * (i + 0.5)) / n) * Math.PI) / 180;
    const cx = 400 + 318 * Math.cos(a);
    const cy = 250 + 118 * Math.sin(a);
    const rx = 22 + rnd() * 16;
    const ry = rx * (0.62 + rnd() * 0.2);
    return (
      <g key={i}>
        <ellipse cx={cx.toFixed(1)} cy={cy.toFixed(1)} rx={rx.toFixed(1)} ry={ry.toFixed(1)} fill={fills[i % 4]} stroke="#5d6371" strokeWidth="2" />
        <ellipse cx={(cx - rx * 0.25).toFixed(1)} cy={(cy - ry * 0.35).toFixed(1)} rx={(rx * 0.5).toFixed(1)} ry={(ry * 0.3).toFixed(1)} fill="#fff" opacity=".28" />
      </g>
    );
  });
}
const ROCKS_BACK = rocks(180, 360, 15, 7);
const ROCKS_FRONT = rocks(0, 180, 15, 3);

/** lg-06 Phòng tự học: pick a chicken and the minutes, study while the countdown runs, the chicken earns XP. */
export function StudyRoom() {
  const { t, i18n } = useTranslation();
  const { token } = useAuth();
  const nav = useNavigate();
  const lang: "vi" | "en" = i18n.language === "en" ? "en" : "vi";
  const [village, setVillage] = useState<Village | null>(null);
  const [failedLoad, setFailedLoad] = useState(false);
  const [reload, setReload] = useState(0);
  const [activeReady, setActiveReady] = useState(false);
  const [autoPaused, setAutoPaused] = useState(false);
  const [phase, setPhase] = useState<Phase>("choose");
  const [pick, setPick] = useState<string>("");
  const [dur, setDur] = useState(25);
  const [topic, setTopic] = useState<"goiy" | "sach">("goiy");
  const [run, setRun] = useState<Run | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [pausedAt, setPausedAt] = useState<number | null>(null);
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [streak, setStreak] = useState<Village["streak"] | null>(null);
  const finishing = useRef(false);

  const chickens = village?.chickens ?? [];
  const mine = chickens.find((c) => c.id === (run?.chicken ?? pick));
  const name = (c: Chicken | undefined) => (c ? (lang === "en" ? c.name_en : c.name_vi) : run ? chickenName(run.chicken, lang) : "");
  const stageName = (c: Chicken) => t(`lg.study.stage${c.stage}`);

  // a session that is still running (or paused) on the server comes first: it needs no village; the village (our chickens) fills in after
  useEffect(() => {
    if (!token) return;
    let alive = true;
    setFailedLoad(false);
    lg.getVillage(token).then(
      (v) => {
        if (!alive) return;
        setVillage(v);
        setStreak(v.streak);
        setPick((p) => p || v.chickens.find((c) => c.id === v.speaker?.chicken)?.id || v.chickens[0]?.id || "");
      },
      () => alive && setFailedLoad(true),
    );
    lg.focusActive(token).then((a: FocusActive | null) => {
      if (alive) setActiveReady(true);
      if (!alive || !a || !a.chicken || !a.minutes) return;
      const endMs = new Date(a.ends_at).getTime();
      if (Number.isNaN(endMs)) return;
      // the server's remaining seconds (not its clock) decide where the countdown stands
      const remaining = typeof a.remaining_sec === "number" ? a.remaining_sec : Math.max(0, (endMs - Date.now()) / 1000);
      const startMs = Date.now() - (a.minutes * 60 - remaining) * 1000;
      setRun({ id: a.id, chicken: a.chicken, minutes: a.minutes, startMs });
      setPick(a.chicken);
      setDur(a.minutes);
      setNow(Date.now());
      if (a.status === "paused") {
        setPausedAt(Date.now());
        setPhase("pause");
      } else setPhase("run");
    }, () => alive && setActiveReady(true));
    return () => {
      alive = false;
    };
  }, [token, reload]);

  // the countdown ticks only while it runs
  useEffect(() => {
    if (phase !== "run") return;
    const id = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(id);
  }, [phase]);

  // the visible countdown is focus time for the behaviour tracker (no second clock, no double counting)
  useEffect(() => {
    holdFocus(phase === "run");
    return () => holdFocus(false);
  }, [phase]);

  const elapsedMs = run ? Math.max(0, (pausedAt ?? now) - run.startMs) : 0;
  const total = (run?.minutes ?? dur) * 60;
  const elapsedSec = Math.min(total, elapsedMs / 1000);
  const doneMin = Math.floor(elapsedSec / 60);
  const left = Math.max(0, total - elapsedSec);
  const xpNow = run ? Math.min(doneMin, run.minutes) + (elapsedSec >= total ? FULL_BONUS : 0) : 0;

  const finish = useCallback(
    async (minutes: number, to: "stop" | "done") => {
      if (!token || !run || finishing.current) return;
      finishing.current = true;
      setBusy(true);
      setErr(null);
      const before = chickens.find((c) => c.id === run.chicken);
      try {
        const r = await lg.focusFinish(token, run.id, minutes);
        if (r.xp > 0) emitXp([{ chicken: run.chicken, source: "focus", amount: r.xp, level_up: !!before && r.chicken.level > before.level }], run.id);
        setRes({ gain: r.xp, done: r.minutes_done, planned: run.minutes, full: r.minutes_done >= run.minutes, before: before ?? r.chicken, after: r.chicken });
        setPhase(to);
        lg.getVillage(token).then(
          (v) => {
            setVillage(v);
            setStreak(v.streak);
          },
          () => undefined,
        );
      } catch {
        setErr(t("lg.study.finishFailed"));
      } finally {
        finishing.current = false;
        setBusy(false);
      }
    },
    [token, run, chickens, t],
  );

  // the whole planned time is over
  useEffect(() => {
    if (phase === "run" && run && elapsedSec >= total && !busy && !err) void finish(run.minutes, "done");
  }, [phase, run, elapsedSec, total, busy, err, finish]);

  const start = async (minutes: number, chicken: string) => {
    if (!token || busy || !chicken) return;
    setBusy(true);
    setErr(null);
    try {
      const f = await lg.focusStart(token, { minutes, chicken });
      setRun({ id: f.id, chicken, minutes, startMs: Date.now() });
      setPausedAt(null);
      setNow(Date.now());
      setRes(null);
      setPhase("run");
      window.scrollTo?.(0, 0);
    } catch {
      setErr(t("lg.study.startFailed"));
    } finally {
      setBusy(false);
    }
  };
  const pause = (auto = false, agoMs = 0) => {
    setPausedAt(Date.now() - agoMs);
    setAutoPaused(auto);
    setPhase("pause");
    if (token && run) void lg.focusPause(token, run.id, agoMs / 1000).catch(() => undefined);
  };
  const resume = async () => {
    if (!run || pausedAt === null || !token || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const f = await lg.focusResume(token, run.id);
      const remaining = typeof f.remaining_sec === "number" ? f.remaining_sec : Math.max(0, run.minutes * 60 - (pausedAt - run.startMs) / 1000);
      setRun({ ...run, startMs: Date.now() - (run.minutes * 60 - remaining) * 1000 });
      setPausedAt(null);
      setAutoPaused(false);
      setNow(Date.now());
      setPhase("run");
    } catch {
      setErr(t("lg.study.resumeFailed"));
    } finally {
      setBusy(false);
    }
  };
  // leaving the tab: after a short grace the clock pauses on the server and the hidden time is not counted; closing the page pauses at once
  const pauseRef = useRef<(auto?: boolean, agoMs?: number) => void>(() => undefined);
  pauseRef.current = pause;
  const live2 = useRef({ phase, run, token });
  live2.current = { phase, run, token };
  useEffect(() => {
    let hiddenAt: number | null = null;
    let timer: number | undefined;
    const onVis = () => {
      const l = live2.current;
      if (document.visibilityState === "hidden") {
        if (l.phase !== "run") return;
        hiddenAt = Date.now();
        timer = window.setTimeout(() => {
          if (live2.current.phase === "run" && hiddenAt !== null) pauseRef.current(true, Date.now() - hiddenAt);
          hiddenAt = null;
        }, HIDE_GRACE_MS);
      } else {
        window.clearTimeout(timer);
        if (hiddenAt !== null && l.phase === "run" && Date.now() - hiddenAt > HIDE_GRACE_MS) pauseRef.current(true, Date.now() - hiddenAt);
        hiddenAt = null;
      }
    };
    const onLeave = () => {
      const l = live2.current;
      if (l.phase === "run" && l.run && l.token) lg.focusPauseOnLeave(l.token, l.run.id);
    };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("pagehide", onLeave);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("pagehide", onLeave);
    };
  }, []);
  const stop = () => run && void finish(doneMin, "stop");
  const again = (minutes: number) => {
    setDur(minutes);
    void start(minutes, run?.chicken ?? pick);
  };

  const lessonTitle = mine?.active_course?.title ?? null;
  const lessonTo = mine?.active_course ? `/khoa-hoc/${encodeURIComponent(mine.active_course.id)}` : null;

  const say = useMemo(() => {
    const n = res?.done ?? doneMin;
    if (phase === "choose") return t("lg.study.sayChoose");
    if (phase === "run") return t("lg.study.sayRun");
    if (phase === "pause") return t("lg.study.sayPause");
    if (phase === "stop") return n < 1 ? t("lg.study.sayStopNone") : t("lg.study.sayStop", { m: n });
    return t("lg.study.sayDone", { n: res?.planned ?? dur });
  }, [phase, res, doneMin, dur, t]);

  const shown = phase === "stop" || phase === "done" ? res?.after ?? mine : mine;
  const sprite = pondSprite(shown, phase === "done" ? "jump" : phase === "run" ? "idle" : "still");

  const live = phase === "choose" ? "" : t(`lg.study.live.${phase === "run" ? "run" : phase === "pause" ? "pause" : phase}`);

  return (
    <div className="lg lg-back lg-sr" data-age="g10_12" data-phase={phase}>
      <main className="lg-sr-wrap">
        <section className="lg-sr-board" aria-labelledby="lg-sr-t">
          <h1 className="lg-sr-ribbon" id="lg-sr-t">
            {t("lg.study.title")}
          </h1>
          {phase === "choose" && (
            <Link className="lg-sr-back" to="/" replace>
              <Icon name="back" />
              <span>{t("lg.study.back")}</span>
            </Link>
          )}

          <div className="lg-sr-stage">
            <div className="lg-sr-scene" role="img" aria-label={t("lg.study.pondAria")}>
              <div className="bgclip">
                <svg viewBox="0 0 800 400" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
                  <defs>
                    <linearGradient id="lg-sr-sky" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="#bfe6fa" />
                      <stop offset="1" stopColor="#e6f6d6" />
                    </linearGradient>
                    <linearGradient id="lg-sr-grass" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="#a6d97f" />
                      <stop offset="1" stopColor="#79b857" />
                    </linearGradient>
                  </defs>
                  <rect width="800" height="400" fill="url(#lg-sr-sky)" />
                  <ellipse cx="170" cy="150" rx="260" ry="70" fill="#9ccf78" />
                  <ellipse cx="640" cy="160" rx="300" ry="80" fill="#8cc468" />
                  <rect y="150" width="800" height="250" fill="url(#lg-sr-grass)" />
                  <g fill="#6aa94b" opacity=".5">
                    <ellipse cx="60" cy="350" rx="40" ry="10" />
                    <ellipse cx="740" cy="340" rx="46" ry="11" />
                    <ellipse cx="120" cy="190" rx="30" ry="7" />
                    <ellipse cx="700" cy="200" rx="34" ry="8" />
                  </g>
                  <ellipse cx="400" cy="262" rx="338" ry="136" fill="#5d9141" opacity=".45" />
                  <ellipse cx="400" cy="250" rx="326" ry="126" fill="#9097a4" />
                  <ellipse cx="400" cy="250" rx="300" ry="110" fill="#49a6e6" />
                  <ellipse cx="400" cy="250" rx="300" ry="110" fill="#7fd0ff" opacity=".35" transform="translate(0 -14) scale(1 .78)" style={{ transformOrigin: "400px 250px" }} />
                  <g className="rip" fill="none" stroke="#fff" strokeOpacity=".5" strokeWidth="2">
                    <ellipse cx="400" cy="262" rx="190" ry="52" />
                    <ellipse cx="400" cy="262" rx="250" ry="76" strokeOpacity=".3" />
                  </g>
                  <g>{ROCKS_BACK}</g>
                </svg>
              </div>
              {shown && (
                <img
                  className="chick"
                  src={sprite}
                  alt=""
                  onError={(e) => {
                    const img = e.currentTarget;
                    const fb = `${base}ga/${shown.art}.webp`;
                    if (!img.src.endsWith(fb)) img.src = fb;
                  }}
                />
              )}
              <svg className="front" viewBox="0 0 800 400" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
                <path d="M101 240 Q150 234 200 240 T300 240 T400 240 T500 240 T600 240 T699 240 A300 110 0 1 1 101 240 Z" fill="#3f9be0" fillOpacity=".62" />
                <path d="M101 240 Q150 234 200 240 T300 240 T400 240 T500 240 T600 240 T699 240" fill="none" stroke="#d9f0ff" strokeOpacity=".75" strokeWidth="3" strokeLinecap="round" />
                <g>{ROCKS_FRONT}</g>
              </svg>
              <div className="steam" aria-hidden="true">
                {[22, 36, 50, 64, 76].map((l, i) => (
                  <i key={l} style={{ left: `${l}%`, animationDelay: `${[0, 1.8, 3.4, 0.9, 2.6][i]}s` }} />
                ))}
              </div>
              {shown && (
                <span className="tag">
                  <span className="lv">{(phase === "stop" || phase === "done" ? res?.after.level : shown.level) ?? shown.level}</span>
                  <span>{name(shown)}</span>
                  <small>{stageName(shown)} <Crown stage={shown.stage} /></small>
                </span>
              )}
              <p className="say">{say}</p>
            </div>

            {/* 1. choose */}
            {phase === "choose" && (
              <div className="lg-sr-panel">
                {(!village || !activeReady) && !failedLoad && (
                  <p className="lg-sr-quiet" role="status">
                    {t("lg.study.loadingRoom")}
                  </p>
                )}
                {failedLoad && (
                  <p className="lg-sr-note" role="alert">
                    {t("lg.study.loadFailed")}{" "}
                    <button className="lg-sr-linkbtn" type="button" onClick={() => setReload((n) => n + 1)}>
                      {t("lg.study.reload")}
                    </button>
                  </p>
                )}
                {village && activeReady && chickens.length === 0 && (
                  <div className="lg-sr-note">
                    <b>{t("lg.study.noChicken")}</b>
                    <Link className="lg-sr-link" to="/" replace>
                      {t("lg.study.toVillage")}
                    </Link>
                  </div>
                )}
                {chickens.length > 0 && activeReady && (
                  <>
                    <fieldset className="lg-sr-opts cards3">
                      <legend>{t("lg.study.who")}</legend>
                      {chickens.map((c) => (
                        <span key={c.id} style={{ display: "contents" }}>
                          <input className="lg-vh" type="radio" name="ga" id={`lg-sr-ga-${c.id}`} value={c.id} checked={pick === c.id} onChange={() => setPick(c.id)} />
                          <label className="lg-sr-card" htmlFor={`lg-sr-ga-${c.id}`}>
                            <span className="th">
                              <ChickenImg art={c.art} stage={c.stage} />
                            </span>
                            <span>
                              <b>{name(c)}</b>
                              <small>{t("lg.study.lv", { n: c.level })}</small>
                            </span>
                            <span className="chk" aria-hidden="true">
                              <Icon name="check" />
                            </span>
                          </label>
                        </span>
                      ))}
                    </fieldset>
                    <fieldset className="lg-sr-opts durs">
                      <legend>{t("lg.study.dur")}</legend>
                      {DURATIONS.map((d) => (
                        <span key={d} style={{ display: "contents" }}>
                          <input className="lg-vh" type="radio" name="dur" id={`lg-sr-d${d}`} value={d} checked={dur === d} onChange={() => setDur(d)} />
                          <label className="lg-sr-card" htmlFor={`lg-sr-d${d}`}>
                            <span>
                              <b>{d}</b> {lang === "en" ? "min" : "phút"}
                            </span>
                          </label>
                        </span>
                      ))}
                    </fieldset>
                    <fieldset className="lg-sr-opts topic">
                      <legend>
                        {t("lg.study.topic")} <span className="lg-sr-opt">{t("lg.study.topicOpt")}</span>
                      </legend>
                      {lessonTitle && (
                        <span style={{ display: "contents" }}>
                          <input className="lg-vh" type="radio" name="topic" id="lg-sr-tp-goiy" checked={topic === "goiy"} onChange={() => setTopic("goiy")} />
                          <label className="lg-sr-card" htmlFor="lg-sr-tp-goiy">
                            <i>
                              <Icon name="target" />
                            </i>
                            <span>
                              <b>{t("lg.study.hint", { name: name(mine) })}</b>
                              <small>{lessonTitle}</small>
                            </span>
                            <span className="chk" aria-hidden="true">
                              <Icon name="check" />
                            </span>
                          </label>
                        </span>
                      )}
                      <span style={{ display: "contents" }}>
                        <input className="lg-vh" type="radio" name="topic" id="lg-sr-tp-sach" checked={topic === "sach" || !lessonTitle} onChange={() => setTopic("sach")} />
                        <label className="lg-sr-card" htmlFor="lg-sr-tp-sach">
                          <i>
                            <Icon name="book" />
                          </i>
                          <span>
                            <b>{t("lg.study.books")}</b>
                            <small>{t("lg.study.booksSub")}</small>
                          </span>
                          <span className="chk" aria-hidden="true">
                            <Icon name="check" />
                          </span>
                        </label>
                      </span>
                    </fieldset>
                    <p className="lg-sr-rule">
                      <FlameIcon />
                      <span>
                        {t("lg.study.ruleA")}
                        <b>{t("lg.study.plusOne")}</b>
                        {t("lg.study.ruleB")}
                        <b>{t("lg.study.plusFive")}</b>
                        {t("lg.study.ruleC")}
                      </span>
                    </p>
                    {err && <p className="lg-sr-note" role="alert">{err}</p>}
                    <button className="lg-sr-btn go big" type="button" disabled={busy || !pick} onClick={() => void start(dur, pick)}>
                      <Icon name="play" />
                      <span>{t("lg.study.start", { n: dur })}</span>
                    </button>
                  </>
                )}
              </div>
            )}

            {/* 2. studying or paused */}
            {(phase === "run" || phase === "pause") && run && (
              <div className="lg-sr-panel timer">
                <p className="lg-sr-study">
                  <span>{t("lg.study.with", { name: name(mine) })}</span>
                  {lessonTitle && topic === "goiy" && <small>{lessonTitle}</small>}
                  {lessonTo && topic === "goiy" && (
                    <Link className="lg-sr-link" to={lessonTo} state={{ back: "/phong-tu-hoc" }}>
                      {t("lg.study.openLesson")}
                    </Link>
                  )}
                </p>
                <div className="ringbox" role="timer" aria-label={t("lg.study.timerLeft", { n: Math.ceil(left / 60) })}>
                  <svg viewBox="0 0 220 220" aria-hidden="true">
                    <circle className="trk" cx="110" cy="110" r="100" />
                    <circle className="bar" cx="110" cy="110" r="100" style={{ strokeDasharray: RING, strokeDashoffset: RING * (1 - Math.min(1, elapsedSec / total)) }} />
                  </svg>
                  <div>
                    <div className="time">{mmss(Math.ceil(left))}</div>
                    <small>{phase === "pause" ? t("lg.study.paused") : t("lg.study.left")}</small>
                  </div>
                </div>
                <p className="lg-sr-xp">
                  {t("lg.study.xp")} <b>+{xpNow}</b>
                </p>
                {phase === "pause" && (
                  <p className="lg-sr-note pause">
                    <b>{t("lg.study.pauseTitle")}</b>
                    <span>{autoPaused ? t("lg.study.autoPaused") : t("lg.study.pauseBody")}</span>
                  </p>
                )}
                {err && (
                  <p className="lg-sr-note" role="alert">
                    {err}{" "}
                    <button className="lg-sr-linkbtn" type="button" onClick={() => void finish(doneMin, "stop")}>
                      {t("lg.study.retry")}
                    </button>
                  </p>
                )}
                {phase === "run" ? (
                  <div className="lg-sr-btns">
                    <button className="lg-sr-btn alt" type="button" onClick={() => pause()}>
                      <Icon name="clock" />
                      {t("lg.study.pause")}
                    </button>
                    <button className="lg-sr-btn alt" type="button" disabled={busy} onClick={stop}>
                      <Icon name="x" />
                      {t("lg.study.stop")}
                    </button>
                  </div>
                ) : (
                  <div className="lg-sr-btns">
                    <button className="lg-sr-btn go" type="button" disabled={busy} onClick={() => void resume()}>
                      <Icon name="play" />
                      {t("lg.study.resume")}
                    </button>
                    <button className="lg-sr-btn alt" type="button" disabled={busy} onClick={stop}>
                      <Icon name="x" />
                      {t("lg.study.stopHere")}
                    </button>
                  </div>
                )}
                {phase === "run" && <p className="lg-sr-quiet">{t("lg.study.keepOpen")}</p>}
              </div>
            )}

            {/* 3. stopped early, 4. done */}
            {(phase === "stop" || phase === "done") && res && (
              <ResultPanel
                res={res}
                phase={phase}
                name={name(res.after)}
                streak={streak}
                busy={busy}
                onAgain={() => again(res.planned)}
                onMore={() => again(MORE_MIN)}
                onHome={() => nav("/", { replace: true })}
              />
            )}
          </div>
        </section>
        <p className="lg-vh" role="status">
          {live}
        </p>
      </main>
    </div>
  );
}

function ResultPanel({ res, phase, name, streak, busy, onAgain, onMore, onHome }: { res: Result; phase: "stop" | "done"; name: string; streak: Village["streak"] | null; busy: boolean; onAgain(): void; onMore(): void; onHome(): void }) {
  const { t } = useTranslation();
  const up = res.after.level > res.before.level;
  const m = res.done;
  const [fill, setFill] = useState(res.before.level === res.after.level ? res.before.xp_in_level : 0);
  useEffect(() => {
    const id = setTimeout(() => setFill(res.after.xp_in_level), 120);
    return () => clearTimeout(id);
  }, [res]);
  const kept = streak?.today_done || m >= STREAK_MIN;
  const bonus = res.full ? FULL_BONUS : 0;
  return (
    <div className="lg-sr-panel">
      {phase === "stop" && (
        <div className="lg-sr-note">
          <b>{m < 1 ? t("lg.study.stopTitleNone") : t("lg.study.stopTitle", { m })}</b>
          <span>{m < 1 ? t("lg.study.stopBodyNone") : t("lg.study.stopBody", { n: res.gain })}</span>
        </div>
      )}
      <p className="lg-sr-gain">
        {phase === "stop" && <span>{t("lg.study.keep")}</span>}
        <b>+{res.gain}</b>
        <span>{phase === "stop" ? t("lg.study.points") : t("lg.study.gain")}</span>
      </p>
      {phase === "done" && <p className="lg-sr-why">{bonus ? t("lg.study.whyFull", { m, b: bonus }) : t("lg.study.why", { m })}</p>}
      <div className="lg-sr-grow">
        <div className="row">
          <span>
            {name}
            {phase === "stop" && up ? ` ${t("lg.study.levelUp")}` : ""}
          </span>
          <span>
            {up ? (
              <>
                <span className="lvl">{t("lg.study.lv", { n: res.before.level })}</span> → <span className="lvl">{t("lg.study.lv", { n: res.after.level })}</span> <span className="up">{t("lg.study.levelUp")}</span>
              </>
            ) : (
              <span className="lvl">{t("lg.study.lv", { n: res.after.level })}</span>
            )}
          </span>
        </div>
        <div className="meter" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={res.after.xp_in_level} aria-label={t("lg.study.meterAria")}>
          <i style={{ width: `${(fill / XP_PER_LEVEL) * 100}%` }} />
        </div>
        <small>
          {res.after.xp_in_level}/{XP_PER_LEVEL} · {t("lg.study.need", { n: XP_PER_LEVEL - res.after.xp_in_level, l: res.after.level + 1 })}
        </small>
      </div>
      <p className="lg-sr-streak">
        <FlameIcon />
        <span>{kept ? t("lg.study.streak", { n: Math.max(1, streak?.days ?? 1) }) : t("lg.study.streakLeft")}</span>
      </p>
      <div className="lg-sr-btns">
        {phase === "stop" ? (
          <>
            <button className="lg-sr-btn go" type="button" disabled={busy} onClick={onAgain}>
              <Icon name="play" />
              {t("lg.study.again")}
            </button>
            <button className="lg-sr-btn alt" type="button" onClick={onHome}>
              <Icon name="back" />
              {t("lg.study.toVillage")}
            </button>
          </>
        ) : (
          <>
            <button className="lg-sr-btn go" type="button" onClick={onHome}>
              <Icon name="back" />
              {t("lg.study.toVillage")}
            </button>
            <button className="lg-sr-btn sun" type="button" disabled={busy} onClick={onMore}>
              <Icon name="plus" />
              {t("lg.study.more")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
