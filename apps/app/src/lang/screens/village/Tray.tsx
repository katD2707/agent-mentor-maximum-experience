import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError, AskError, isMock, postGuide, postNotes, practice, PracticeError, type AskStep, type NotesResult, type StartSource } from "../../../api";
import { useAuth } from "../../../state/auth";
import { Icon, type IconName } from "../../../components/Icon";
import { Camera } from "../../kit/Camera";
import { resolveDeepLink } from "../../../lib/deeplink";
import { downscaleImage } from "../../../lib/image";
import { RecorderError, startRecording, type Recording } from "../../../lib/recorder";
import { speak } from "../../../lib/speak";
import { refreshReminders } from "../../../lib/behaviour";
import { logEvent } from "../../../lib/events";
import { enableWebNotifications, isTauri, notifyState } from "../../../lib/platform";
import { hasSeen, markSeen, REPLAY_EVENT } from "../../../lib/tours";
import { streamChat, type ChatEvent, type ChatRequest, type Village } from "../../api";
import { mockRememberNotes } from "../../api/mock";
import { ResumeCard } from "../arena/Resume";
import { artFile, chickenName, subjectOf } from "../../subjects";
import { cropVars } from "../../chickenArt";
import { helpTopic, hhmm, laterOptions, routeText, watchSlow, type SlowWatch } from "./logic";

export type SheetKey = "none" | "market" | "news" | "progress" | "settings";

/** A quick reply under a chicken's message: a link (the main action) or a step in the conversation. */
export interface Reply {
  label: string;
  dur?: string;
  primary?: boolean;
  /** do not echo the label as a message of the learner (a retry) */
  quiet?: boolean;
  icon?: IconName;
  to?: string;
  run?: () => void;
}

type Item =
  | { kind: "ga"; id: number; who: string; text?: ReactNode; html?: string; rich?: ReactNode; replies?: Reply[]; used?: boolean; typing?: boolean; thinking?: boolean; slow?: boolean }
  | { kind: "me"; id: number; text?: string; photo?: string; shot?: "photo" | "notes" | "voice" };

const KID_STAR = "M0 -13 L4 -4 L14 -3 L7 4 L9 13 L0 8 L-9 13 L-7 4 L-14 -3 L-4 -4 Z";

/** Primary school: the next step is a spot on a path (done, this one, the next, the star at the end). */
function KidPath({ done, total, label }: { done: number; total: number; label: string }) {
  return (
    <div className="lg-pathbox">
      <svg className="lg-path" viewBox="0 0 300 130" role="img" aria-label={label}>
        <path className="road" d="M30 96 C70 30, 110 30, 140 64 S 210 112, 266 46" />
        {done > 0 && (
          <g className="done">
            <circle cx="30" cy="96" r="20" />
            <path d="M21 96 l6 6 11-12" fill="none" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        )}
        <g className="now">
          <circle className="halo" cx="140" cy="64" r="36" />
          <circle className="dot" cx="140" cy="64" r="28" />
          <path d="M132 51 L153 64 L132 77 Z" />
        </g>
        {total - done > 1 && (
          <g className="todo">
            <circle cx="212" cy="104" r="17" />
          </g>
        )}
        <g transform="translate(268 44)">
          <circle r="24" fill="#ffe9a8" stroke="#ffcf3d" strokeWidth="4" />
          <path d={KID_STAR} fill="#f5a623" />
        </g>
      </svg>
    </div>
  );
}

/** The face of the speaking chicken (a crop of its picture). */
function Face({ id, stage }: { id: string; stage: number }) {
  const art = subjectOf(id)?.art ?? id;
  return (
    <span className="lg-ava" aria-hidden="true">
      <img className="ga-crop" alt="" src={`${import.meta.env.BASE_URL}ga/${artFile(art, stage)}`} style={cropVars(art, stage, { fill: 2.3, pad: 0.12 })} />
    </span>
  );
}

export interface TrayProps {
  village: Village;
  openSheet(s: SheetKey): void;
  /** the learner's data changed (a chicken took XP, a goal was added ...) */
  onChanged?(): void;
}

/**
 * The answer tray (mockups/lg-01): the speaking chicken says one thing to do now with quick replies; the box under it
 * continues the talk (homework photo, notes, goals, how to use the app, anything else goes to the chicken).
 * Everything the old Today screen did lives here: Học / Để sau / Việc khác, Chụp vở, goals, help.
 */
const MdHtml = lazy(() => import("../../kit/MdHtml"));
const Md = ({ md }: { md: string }) => (
  <Suspense fallback={null}>
    <MdHtml md={md} />
  </Suspense>
);

export function Tray({ village, openSheet, onChanged }: TrayProps) {
  const { t, i18n } = useTranslation();
  const { token, user } = useAuth();
  const nav = useNavigate();
  const lang: "vi" | "en" = i18n.language === "en" ? "en" : "vi";
  const band = user?.age_band === "g1_5" ? "kid" : user?.age_band === "uni" ? "uni" : "school";
  const kid = band === "kid";
  const you = t(`lg.you.${band}`);
  const name = user?.display_name ?? "";
  const speakerId = village.speaker?.chicken ?? village.chickens[0]?.id ?? "toan";
  const speakerName = chickenName(speakerId, lang);

  const [items, setItems] = useState<Item[]>([]);
  const [text, setText] = useState("");
  const [suggest, setSuggest] = useState(false);
  // phones and laptops (up to 1366 wide) start with the tray folded: the short line over the chicken says it, the village stays in view
  const [min, setMin] = useState(() => typeof matchMedia === "function" && matchMedia("(max-width: 1366px)").matches);
  const [camera, setCamera] = useState(false);
  const [listening, setListening] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const next = useRef(1);
  const opened = useRef(false);
  const threadEl = useRef<HTMLDivElement>(null);
  const notesInput = useRef<HTMLInputElement>(null);
  const device = useRef<HTMLInputElement>(null);
  const rec = useRef<Recording | null>(null);
  const ctl = useRef<AbortController | null>(null);
  const watch = useRef<SlowWatch | null>(null);
  const threads = useRef<Record<string, string>>({});
  const urls = useRef<string[]>([]);
  const home = useRef<ReturnType<typeof practice.home> | null>(null);
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const live = useRef({ speakerId, village });
  live.current = { speakerId, village };

  // ---- the conversation
  const me = useCallback((m: Omit<Extract<Item, { kind: "me" }>, "kind" | "id">) => {
    const id = next.current++;
    setItems((l) => [...l, { kind: "me", id, ...m }]);
    return id;
  }, []);
  /** a chicken speaks: a short "typing" first, then the message */
  const say = useCallback(
    (m: { text?: ReactNode; html?: string; rich?: ReactNode; replies?: Reply[] }, who?: string) => {
      const id = next.current++;
      const w = who ?? live.current.speakerId;
      setItems((l) => [...l, { kind: "ga", id, who: w, ...m, typing: !reduce }]);
      if (!reduce) setTimeout(() => setItems((l) => l.map((x) => (x.id === id && x.kind === "ga" && !x.thinking ? { ...x, typing: false } : x))), 550);
      return id;
    },
    [reduce],
  );
  const patch = (id: number, p: Partial<Extract<Item, { kind: "ga" }>>) => setItems((l) => l.map((x) => (x.id === id && x.kind === "ga" ? { ...x, ...p } : x)));
  const use = (id: number, r: Reply) => {
    setItems((l) => l.map((x) => (x.id === id && x.kind === "ga" ? { ...x, used: true } : x)));
    if (r.to) return;
    if (!r.quiet) me({ text: r.label });
    r.run?.();
  };

  useEffect(() => {
    const el = threadEl.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items]);
  useEffect(
    () => () => {
      urls.current.forEach((u) => URL.revokeObjectURL(u));
      ctl.current?.abort();
      rec.current?.cancel();
    },
    [],
  );

  /**
   * A chicken is working on a slow server call: "Gà đang nghĩ…" at once, a soft "taking a while" line with Cancel after 15 s,
   * a friendly error with Try again on failure or after 50 s. `lost` shows that error; `end` releases the box.
   */
  const think = (who: string) => {
    if (ctl.current) return null;
    const c = new AbortController();
    ctl.current = c;
    setBusy(true);
    const id = next.current++;
    // an older "Thử lại" is stale once the learner asks something else
    setItems((l) => [...l.map((x) => (x.kind === "ga" && x.replies?.some((r) => r.quiet) ? { ...x, used: true } : x)), { kind: "ga", id, who, typing: true, thinking: true }]);
    const w = watchSlow(c, () => patch(id, { slow: true }));
    watch.current = w;
    const finish = (p: Partial<Extract<Item, { kind: "ga" }>> = {}) => patch(id, { typing: false, thinking: false, slow: false, ...p });
    const retry = (run: () => void): Reply[] => [{ primary: true, quiet: true, label: t("lg.tray.retry"), run }];
    const lost = (e: unknown, run: () => void) => {
      if (w.cancelled) return finish({ text: t("lg.tray.cancelled") });
      if (c.signal.aborted && !w.timedOut) return;
      finish({ text: t(e instanceof AskError && e.code === "network" && !w.timedOut ? "lg.tray.offline" : "lg.tray.chatFailed"), replies: retry(run) });
    };
    const end = () => {
      w.stop();
      if (ctl.current === c) ctl.current = null;
      if (watch.current === w) watch.current = null;
      setBusy(false);
    };
    return { id, signal: c.signal, finish, lost, retry, end };
  };

  // ---- practice and other things to do today
  const startPractice = useCallback(
    async (source: StartSource) => {
      if (!token) return;
      try {
        const s = await practice.start(token, { source });
        nav(`/luyen-tap/${encodeURIComponent(s.id)}`, { state: { back: "/" } });
      } catch (e) {
        if (e instanceof PracticeError && e.code === "active_session" && typeof e.body.session_id === "string") nav(`/luyen-tap/${encodeURIComponent(e.body.session_id)}`, { state: { back: "/" } });
        else say({ text: t(e instanceof PracticeError && e.code === "insufficient_content" ? "lg.tray.quickNone" : "lg.tray.startFailed") });
      }
    },
    [nav, say, t, token],
  );
  const loadHome = () => {
    if (!token) return Promise.resolve(null);
    home.current ??= practice.home(token);
    return home.current.catch(() => null);
  };

  const askNotes = () => say({ text: t("lg.notes.asking"), replies: [{ primary: true, label: t("lg.notes.pick"), run: () => notesInput.current?.click() }] });
  const whenOf = (iso: string) => {
    const d = new Date(iso);
    const time = hhmm(d);
    const days = Math.round((new Date(d).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
    return days <= 0 ? t("lg.tray.whenToday", { time }) : days === 1 ? t("lg.tray.whenTomorrow", { time }) : `${time} ${d.toLocaleDateString(lang === "en" ? "en-GB" : "vi-VN", { day: "numeric", month: "numeric" })}`;
  };
  const sendNotes = async (files: File[]) => {
    if (!token || files.length === 0) return;
    me({ text: t("lg.notes.shot"), shot: "notes" });
    const upload = async () => {
      const th = think(speakerId);
      if (!th) return;
      try {
        const images = await Promise.all(files.slice(0, 6).map((f) => downscaleImage(f)));
        const r: NotesResult = await postNotes(token, images, th.signal);
        if (isMock) mockRememberNotes(token, { notes_id: r.notes_id, title: r.title, pages: r.pages, items: r.items, created_at: new Date().toISOString(), next_review_at: r.next_review_at });
        th.finish({
          text: t("lg.notes.line", { title: r.title, pages: r.pages, n: r.items }),
          replies: [
            {
              primary: true,
              label: t("lg.notes.make"),
              run: () =>
                say({
                  text: t("lg.notes.done", { n: r.items, first: whenOf(r.first_review_at) }),
                  replies: [{ primary: true, label: t("lg.notes.now"), dur: t("lg.min", { count: Math.max(3, Math.round(r.items * 0.8)) }), run: () => void startPractice(`notes:${r.notes_id}`) }],
                }),
            },
            { label: t("lg.notes.no"), run: () => say({ text: t("lg.notes.noAck") }) },
          ],
        });
      } catch (e) {
        if (e instanceof AskError && e.code === "unreadable") th.finish({ text: t("lg.notes.unreadable"), replies: [{ label: t("lg.notes.reply"), icon: "camera", run: () => notesInput.current?.click() }] });
        else th.lost(e, () => void upload());
      } finally {
        th.end();
      }
    };
    await upload();
  };
  // real papers and mock exams live in the arena (one feature, one place): the tray only points there
  const offerArena = () => say({ text: t("lg.tray.mockGo", { you }), replies: [{ primary: true, label: t("lg.place.arena"), to: "/dau-truong" }] });
  const offerQuick = async () => {
    const h = await loadHome();
    say(h && h.quick.count > 0 ? { text: t("lg.tray.quickOffer"), replies: [{ primary: true, label: t("lg.go.practice"), dur: t("lg.min", { count: h.quick.minutes }), run: () => void startPractice("quick") }] } : { text: t("lg.tray.quickNone") });
  };
  const offerOthers = async () => {
    const h = await loadHome();
    const opts: Reply[] = [];
    if (h && h.quick.count > 0) opts.push({ label: t("lg.tray.optQuick", { count: h.quick.count }), dur: t("lg.min", { count: h.quick.minutes }), run: () => void startPractice("quick") });
    if (!kid) opts.push({ label: t("lg.place.arena"), to: "/dau-truong" });
    for (const c of village.chickens.filter((c) => c.active_course).slice(0, 2)) opts.push({ label: c.active_course!.title, to: `/khoa-hoc/${encodeURIComponent(c.active_course!.id)}/hoc` });
    if (!kid) opts.push({ label: t("lg.notes.reply"), icon: "camera", run: askNotes });
    say(opts.length ? { text: t("lg.tray.otherIntro", { you }), replies: opts } : { text: t("lg.tray.otherNone") });
  };

  // ---- "Để sau": a real reminder, shown by the system even with the app closed (POST /reminders)
  const enableNotify = () =>
    token &&
    void enableWebNotifications(
      () => api.vapidPublicKey(token),
      (sub) => api.pushSubscribe(token, sub),
    ).then((st) => {
      void refreshReminders();
      say({ text: t(st === "granted" ? "lg.tray.notifyOn" : "lg.tray.notifyOff", { you }) });
    });
  const remindAt = async (when: Date, tomorrow: boolean) => {
    if (!token) return;
    const sp = village.speaker;
    try {
      await api.remindLater(token, { at: when.toISOString(), title_vi: sp?.line_vi ?? "", title_en: sp?.line_en ?? sp?.line_vi ?? "", deep_link: sp?.action ? resolveDeepLink(sp.action.deep_link).to : "/" });
      void refreshReminders();
      const time = t(tomorrow ? "lg.tray.whenTomorrow" : "lg.tray.whenToday", { time: hhmm(when) });
      const ask = !isTauri() && notifyState() === "default";
      say({ text: t("lg.tray.remindSet", { time, you }), replies: ask ? [{ label: t("lg.tray.enableNotify"), run: enableNotify }] : undefined });
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "unknown";
      if (code === "bedtime" && !tomorrow) say({ text: t("lg.tray.remindBedtime", { you }), replies: [laterReply(laterOptions(new Date(), { kid }).at(-1)!)] });
      else if (code === "quiet") say({ text: t("lg.tray.remindQuiet", { you }) });
      else say({ text: t("lg.tray.startFailed") });
    }
  };
  const laterReply = (o: ReturnType<typeof laterOptions>[number]): Reply => ({
    label: o.key === "in1h" ? t("lg.tray.in1h") : o.key === "tonight" ? t("lg.tray.tonightAt", { time: o.time }) : t("lg.tray.tomorrowAt", { time: o.time }),
    run: () => void remindAt(o.when, o.key === "tomorrow"),
  });
  const later = () => {
    const sp = village.speaker;
    const opts = laterOptions(new Date(), { kid, sessionToday: !!sp?.action });
    say({ text: t("lg.tray.laterAsk", { you }), replies: opts.map(laterReply) });
  };

  // ---- help: the guide map of the village first, the server's guide for anything else
  const answerHelp = async (q: string) => {
    const topic = helpTopic(q);
    if (topic) return say({ text: t(`lg.help.${topic}`) });
    if (!token || isMock) return say({ text: t("lg.help.default") });
    const ask = async () => {
      const th = think(speakerId);
      if (!th) return;
      try {
        const answer = (await postGuide(token, { question: q.slice(0, 300), lang, screen: "village" }, th.signal));
        th.finish({ text: answer || t("lg.help.default") });
      } catch (e) {
        th.lost(e, () => void ask());
      } finally {
        th.end();
      }
    };
    await ask();
  };

  // ---- talk to the chicken (POST /chat/{chicken}: streamed)
  const chat = async (req: Omit<ChatRequest, "lang" | "thread_id">, who: string = speakerId) => {
    if (!token) return;
    const th = think(who);
    if (!th) return;
    const reply = th.id;
    let acc = "";
    let steps: AskStep[] = [];
    const finish = th.finish;
    const onEvent = (ev: ChatEvent) => {
      if (ev.event !== "thread" && ev.event !== "status") watch.current?.stop();
      switch (ev.event) {
        case "thread":
          threads.current[who] = ev.data.thread_id;
          break;
        case "transcript":
          setItems((l) => {
            const k = [...l].reverse().find((x) => x.kind === "me" && x.shot === "voice");
            return k ? l.map((x) => (x === k ? { ...x, text: ev.data.text } : x)) : l;
          });
          break;
        case "delta":
          acc += ev.data.text;
          patch(reply, { text: acc, typing: false });
          break;
        case "answer":
        case "message":
          acc = ev.data.text;
          patch(reply, { text: acc, typing: false });
          break;
        case "intent":
          if (!req.action) logEvent("ask_question", { intent: ev.data.intent, input: req.image ? "photo" : req.audio ? "voice" : "text" });
          break;
        case "actions":
          patch(reply, {
            typing: false,
            replies: ev.data.items.map((a, i) => ({ primary: i === 0, label: lang === "en" ? a.label_en : a.label_vi, to: resolveDeepLink(a.deep_link).to })),
          });
          break;
        case "courses":
          patch(reply, { typing: false, replies: ev.data.items.slice(0, 3).map((cd, i) => ({ primary: i === 0, label: cd.title, to: `/khoa-hoc/${encodeURIComponent(cd.course_id)}` })) });
          break;
        case "choices":
          patch(reply, {
            typing: false,
            text: acc || t("lg.tray.choose"),
            replies: ev.data.problems.map((p) => ({ label: p.label, run: () => void chat({ action: "choose", problem_id: p.id }, who) })),
          });
          break;
        case "solution":
          steps = ev.data.steps;
          patch(reply, {
            typing: false,
            text: acc || t("lg.tray.solveIntro"),
            rich: <ol className="lg-steps">{steps.map((s, i) => <li key={i}><Md md={s.title ? `**${s.title}** ${s.md}` : s.md} /></li>)}</ol>,
            replies: [
              ...(ev.data.last_step_withheld ? [{ primary: true, label: t("lg.tray.lastStep"), run: () => void chat({ action: "last_step" }, who) }] : []),
              { label: t("lg.tray.simpler"), run: () => void chat({ action: "simpler" }, who) },
              { label: t("lg.tray.similar"), run: () => void chat({ action: "similar" }, who) },
            ],
          });
          break;
        case "last_step":
          patch(reply, { typing: false, text: undefined, rich: <Md md={ev.data.step.md} /> });
          break;
        case "similar":
          patch(reply, { typing: false, text: undefined, rich: <ol className="lg-steps">{ev.data.items.map((s, i) => <li key={i}><Md md={s.problem_md} /></li>)}</ol> });
          break;
        case "error":
          finish({ text: t("lg.tray.chatFailed"), replies: th.retry(() => void chat(req, who)) });
          break;
        default:
          break;
      }
    };
    try {
      await streamChat(token, who, { ...req, lang, thread_id: threads.current[who] ?? null }, onEvent, th.signal);
      finish();
      onChanged?.();
    } catch (e) {
      th.lost(e, () => void chat(req, who));
    } finally {
      th.end();
    }
  };

  const onText = async (raw: string) => {
    const v = raw.trim();
    if (!v || busy) return;
    setText("");
    setSuggest(false);
    me({ text: v });
    switch (routeText(v, kid)) {
      case "help":
        return void (await answerHelp(v));
      case "notes":
        return askNotes();
      case "mock":
        return offerArena();
      case "practice":
        return void (await offerQuick());
      case "goal":
        if (token) {
          try {
            const g = await api.createGoal(token, { title: v.slice(0, 120) });
            void refreshReminders();
            onChanged?.();
            return say({ text: t("lg.tray.goalAdded", { title: g.title }), replies: [{ label: t("lg.tray.seeWeek"), run: () => openSheet("progress") }] });
          } catch {
            /* not a goal after all: the chicken answers it */
          }
        }
        return void (await chat({ text: v }));
      default:
        return void (await chat({ text: v }));
    }
  };

  const sendPhoto = async (file: Blob) => {
    setCamera(false);
    const image = await downscaleImage(file);
    const url = URL.createObjectURL(image);
    urls.current.push(url);
    me({ text: t("lg.tray.photo"), photo: url, shot: "photo" });
    void chat({ image });
  };
  const openCamera = () => {
    setSuggest(false);
    if (typeof navigator.mediaDevices?.getUserMedia === "function") setCamera(true);
    else device.current?.click();
  };
  const talk = async () => {
    if (busy && !listening) return;
    if (listening) {
      const r = rec.current;
      rec.current = null;
      setListening(false);
      if (!r) return;
      try {
        const audio = await r.stop();
        me({ text: t("lg.tray.voice"), shot: "voice" });
        void chat({ audio });
      } catch {
        setNote(t("ask.micFailed"));
      }
      return;
    }
    setNote(null);
    try {
      rec.current = await startRecording({ onAutoStop: () => void talk() });
      setListening(true);
    } catch (e) {
      const code = e instanceof RecorderError ? e.code : "failed";
      setNote(t(code === "denied" ? "ask.micDenied" : code === "unsupported" ? "ask.micUnsupported" : "ask.micFailed"));
    }
  };

  // ---- the chips under the box
  const tryIt = (k: "photo" | "notes" | "learn" | "mock" | "practice") => {
    setSuggest(false);
    if (k === "photo") return openCamera();
    if (k === "notes") {
      me({ text: t("lg.notes.reply") });
      return askNotes();
    }
    if (k === "learn") {
      me({ text: t("lg.tray.learnSay") });
      return say({ text: t("lg.tray.learnReply", { name: chickenName(speakerId, lang) }), replies: [{ primary: true, label: t("lg.market.open"), run: () => openSheet("market") }, { label: t("lg.tray.inCoop"), to: `/chuong/${speakerId}` }] });
    }
    if (k === "mock") return nav("/dau-truong", { state: { back: "/" } });
    me({ text: t("lg.chips.practice") });
    return void offerQuick();
  };

  // ---- open the day: the chicken speaks first (an introduction the very first time)
  const open = useCallback(() => {
    const uid = user?.id ?? null;
    const first = !hasSeen(uid, "lg-hello");
    const sp = village.speaker;
    const who = sp?.chicken ?? village.chickens[0]?.id ?? "toan";
    if (first) {
      markSeen(uid, "lg-hello");
      say({ text: t("lg.tray.intro", { name, chicken: chickenName(who, lang) }) }, who);
    }
    const hi = first ? "" : `${t("lg.tray.hello", { name })} `;
    const st = village.streak;
    const streakLine = st && st.days >= 2 ? ` ${t(st.today_done ? "lg.tray.streakDone" : "lg.tray.streakKeep", { count: st.days })}` : "";
    const line = lang === "en" ? sp?.line_en || sp?.line_vi : sp?.line_vi;
    const act = sp?.action;
    if (kid && act) {
      const c = village.chickens.find((x) => x.id === who);
      const done = Math.min(2, Math.floor((c?.active_course?.percent ?? 0) / 34));
      say(
        {
          text: line,
          rich: <KidPath done={done} total={3} label={t("lg.tray.pathAria", { done, total: 3 })} />,
          replies: [{ primary: true, label: t("lg.tray.kidStart"), to: resolveDeepLink(act.deep_link).to }, { label: t("lg.tray.listen"), icon: "volume", run: () => speak(line ?? "", lang) }],
        },
        who,
      );
    } else if (act && act.kind !== "break") {
      const goKey = act.kind === "lesson" ? "lesson" : act.kind === "research" ? "research" : act.kind === "review" ? "review" : "practice";
      say(
        {
          text: (
            <>
              {hi}
              <b>{line}</b>
              {streakLine}
            </>
          ),
          replies: [
            { primary: true, label: t(`lg.go.${goKey}`), dur: t("lg.min", { count: act.minutes }), to: resolveDeepLink(act.deep_link).to },
            { label: t("lg.tray.later"), run: later },
            { label: t("lg.tray.other"), run: () => void offerOthers() },
          ],
        },
        who,
      );
    } else if (act) {
      say({ text: `${hi}${t("lg.tray.breakDay")}`, replies: [{ label: t("lg.tray.other"), run: () => void offerOthers() }] }, who);
    } else {
      say({ text: `${hi}${t("lg.tray.empty", { you })}`, replies: [{ label: t("lg.tray.other"), run: () => void offerOthers() }, { label: t("lg.market.open"), run: () => openSheet("market") }] }, who);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [village, kid, lang, name, user?.id]);

  useEffect(() => {
    if (opened.current) return;
    opened.current = true;
    open();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Settings > "Xem lại từ đầu": the chicken introduces itself again
  useEffect(() => {
    const again = () => {
      setItems([]);
      setTimeout(open, 300);
    };
    window.addEventListener(REPLAY_EVENT, again);
    return () => window.removeEventListener(REPLAY_EVENT, again);
  }, [open]);

  const hints = useMemo(() => [t("lg.tray.ph0", { name: speakerName }), t("lg.tray.ph1"), t("lg.tray.ph2"), t("lg.tray.ph3")], [t, speakerName]);
  const [hint, setHint] = useState(0);
  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => {
      if (document.activeElement?.id === "lg-q") return;
      setHint((h) => (h + 1) % hints.length);
    }, 3200);
    return () => clearInterval(id);
  }, [hints.length, reduce]);

  const tall = items.some((i) => i.kind === "ga" && i.rich);
  return (
    <>
      <section className={"lg-hud lg-tray" + (min ? " min" : "")} id="lg-tray" aria-label={t("lg.tray.aria", { name: speakerName })} onKeyDown={(e) => e.key === "Escape" && setSuggest(false)}>
        <div className="lg-g-head">
          <span className="lg-ribbon">
            {speakerName} <small>{t("lg.tray.says")}</small>
          </span>
          <span className="grow" />
          <button className="lg-g-min" type="button" aria-expanded={!min} aria-controls="lg-g-body" aria-label={min ? t("lg.tray.expand") : t("lg.tray.collapse")} onClick={() => setMin((m) => !m)}>
            <Icon name="chev" />
          </button>
        </div>
        <div className="lg-g-body" id="lg-g-body">
          <div className={"lg-thread" + (tall ? " tall" : "")} ref={threadEl} role="log" aria-live="polite" aria-label={t("lg.tray.threadAria")}>
            {items.map((it) =>
              it.kind === "me" ? (
                <div className="lg-msg mine" key={it.id}>
                  <div className="lg-body">
                    <div className="lg-bub">
                      {it.shot && (
                        <span className="lg-shot" aria-hidden="true">
                          {it.photo ? <img src={it.photo} alt="" /> : <Icon name={it.shot === "voice" ? "mic" : it.shot === "notes" ? "image" : "camera"} />}
                        </span>
                      )}
                      <span>{it.text}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="lg-msg ga" key={it.id}>
                  <Face id={it.who} stage={village.chickens.find((c) => c.id === it.who)?.stage ?? 3} />
                  <div className="lg-body">
                    {it.typing ? (
                      <>
                        <div className="lg-bub lg-typing" role="status" aria-label={t(it.thinking ? "lg.tray.thinking" : "lg.tray.typing")}>
                          <i />
                          <i />
                          <i />
                          {it.thinking && <span className="lg-think">{t("lg.tray.thinking")}</span>}
                        </div>
                        {it.thinking && it.slow && (
                          <div className="lg-slow" role="status">
                            <span>{t("lg.tray.slow")}</span>
                            <button type="button" onClick={() => watch.current?.cancel()}>
                              {t("lg.tray.cancel")}
                            </button>
                          </div>
                        )}
                      </>
                    ) : (
                      <>
                        {(it.text !== undefined || it.html) && <div className="lg-bub">{it.html ? <span dangerouslySetInnerHTML={{ __html: it.html }} /> : it.text}</div>}
                        {it.rich && <div className="lg-rich">{it.rich}</div>}
                        {it.replies && it.replies.length > 0 && !it.used && (
                          <div className="lg-replies">
                            {it.replies.map((r, i) => {
                              const inner = (
                                <>
                                  {r.primary && <Icon name="play" />}
                                  {!r.primary && r.icon && <Icon name={r.icon} />}
                                  <span>{r.label}</span>
                                  {r.dur && <span className="dur">· {r.dur}</span>}
                                </>
                              );
                              const cls = `lg-reply${r.primary ? " p" : ""}`;
                              return r.to ? (
                                <Link key={i} className={cls} to={r.to} state={{ back: "/" }} onClick={() => use(it.id, { ...r, run: undefined })}>
                                  {inner}
                                </Link>
                              ) : (
                                <button key={i} className={cls} type="button" onClick={() => use(it.id, r)}>
                                  {inner}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ),
            )}
          </div>

          <div className="lg-g-in">
            <ResumeCard back="/" />
            {note && (
              <p className="lg-note" role="status">
                {note}
              </p>
            )}
            {kid ? (
              <div className="lg-kid-ask">
                <button type="button" onClick={openCamera} disabled={busy}>
                  <Icon name="camera" />
                  <span>{t("lg.tray.kidSnap")}</span>
                </button>
                <button type="button" className="alt" onClick={() => void talk()} disabled={busy && !listening} aria-pressed={listening}>
                  <Icon name={listening ? "stop" : "mic"} />
                  <span>{listening ? t("lg.tray.kidDone") : t("lg.tray.kidTalk", { name: speakerName })}</span>
                </button>
              </div>
            ) : (
              <>
                {suggest && (
                  <div className="lg-suggest" role="group" aria-label={t("lg.tray.ideas")} onPointerDown={(e) => e.preventDefault()}>
                    <button type="button" onClick={() => tryIt("photo")}>
                      <Icon name="camera" />
                      <span>{t("lg.chips.photo")}</span>
                    </button>
                    <button type="button" onClick={() => tryIt("notes")}>
                      <Icon name="image" />
                      <span>{t("lg.chips.notes")}</span>
                    </button>
                    <button type="button" onClick={() => tryIt("learn")}>
                      <Icon name="search" />
                      <span>{t("lg.chips.learn")}</span>
                    </button>
                    <button type="button" onClick={() => tryIt("mock")}>
                      <Icon name="clock" />
                      <span>{t("lg.chips.mock")}</span>
                    </button>
                    <button type="button" onClick={() => tryIt("practice")}>
                      <Icon name="quiz" />
                      <span>{t("lg.chips.practice")}</span>
                    </button>
                  </div>
                )}
                <form
                  className="lg-composer"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void onText(text);
                  }}
                >
                  <button className="lg-c-btn" type="button" aria-label={t("lg.chips.photo")} onClick={openCamera} disabled={busy}>
                    <Icon name="camera" />
                  </button>
                  <input
                    id="lg-q"
                    className="lg-c-input"
                    type="text"
                    autoComplete="off"
                    value={text}
                    placeholder={hints[hint]}
                    aria-label={t("lg.tray.msgAria")}
                    onChange={(e) => {
                      setText(e.target.value);
                      setSuggest(!e.target.value.trim());
                    }}
                    onFocus={() => setSuggest(!text.trim())}
                    onClick={() => setSuggest(!text.trim())}
                    onBlur={() => setTimeout(() => setSuggest(false), 120)}
                  />
                  <button className="lg-c-btn" type="button" aria-label={listening ? t("lg.tray.kidDone") : t("lg.tray.talk")} aria-pressed={listening} onClick={() => void talk()}>
                    <Icon name={listening ? "stop" : "mic"} />
                  </button>
                  <button className="lg-c-btn lg-c-send" type="submit" aria-label={t("lg.tray.send")} disabled={busy}>
                    <Icon name="send" />
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      </section>

      <input
        ref={notesInput}
        type="file"
        accept="image/*"
        multiple
        hidden
        aria-label={t("lg.notes.pick")}
        onChange={(e) => {
          const fs = [...(e.target.files ?? [])];
          e.target.value = "";
          void sendNotes(fs);
        }}
      />
      <input
        ref={device}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) void sendPhoto(f);
        }}
      />
      {camera && (
        <div className="lg-cam">
          <Camera onShot={(b) => void sendPhoto(b)} onFile={(f) => void sendPhoto(f)} onClose={() => setCamera(false)} />
        </div>
      )}
    </>
  );
}
