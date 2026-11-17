import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "katex/dist/katex.min.css";
import { api, ApiError, AskError, isMock, postGuide, postNotes, practice, PracticeError, type AskCard, type AskProblem, type AskRequest, type NotesResult, type PHome, type StartSource } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon } from "../../components/Icon";
import { Settings } from "../../components/Settings";
import { pickLang, useToday } from "../../lib/today";
import { resolveDeepLink } from "../../lib/deeplink";
import { speak } from "../../lib/speak";
import { downscaleImage } from "../../lib/image";
import { askGuide } from "../../lib/guides";
import { hasSeen, markSeen, REPLAY_EVENT } from "../../lib/tours";
import { refreshReminders } from "../../lib/behaviour";
import { enableWebNotifications, isTauri, notifyState } from "../../lib/platform";
import { useMyCourses } from "../courses/useMyCourses";
import { CourseCover } from "../courses/common";
import { useAsk } from "../ask/useAsk";
import { AiBubble, MeBubble } from "../ask/Turns";
import { Composer } from "../ask/Composer";
import { Camera } from "../ask/Camera";
import { CourseSheet, useAddCourse } from "../ask/Courses";
import { ProgressBody } from "../Progress";
import { KidAsk, KidPath, MeMessage, MucMessage, type Reply } from "./Thread";

/** One line of the conversation: Mực, the learner, or a stretch of Hỏi đáp turns (from `start` up to the next stretch). */
type Item =
  | { kind: "muc"; id: number; text: ReactNode; rich?: ReactNode; replies?: Reply[]; used?: boolean; typing?: boolean }
  | { kind: "me"; id: number; text: string }
  | { kind: "ask"; id: number; start: number };

const HELP = /(ở đâu|nút nào|chỗ nào|cách dùng|dùng app|where is|where do|how do i use)/i;
const MOCK = /(thi thử|mock exam)/i;
const PRACTICE = /^(cho (em|mình|tôi) )?(luyện|ôn)|^practi[cs]e|^review/i;
const NOTES = /(chụp vở|vở ghi|ảnh vở|photo (of )?my notes|my notes)/i;
const GOAL = /(mục tiêu|muốn (được|đạt)|\bgoal\b|i want an? \d)/i;

/**
 * The student's one screen (mockups/hs-03): Mực speaks first with what to do now and quick replies; the box at the bottom
 * continues the same conversation (homework, courses, goals, how to use the app); courses sit in a strip at the top and
 * the week opens from the ring. Practice lives inside each course.
 */
export function Today() {
  const { t, i18n } = useTranslation();
  const { token, user } = useAuth();
  const nav = useNavigate();
  const lang = i18n.language === "en" ? "en" : "vi";
  const band = user?.age_band === "g1_5" ? "kid" : user?.age_band === "uni" ? "uni" : "school";
  const you = t(`today.you.${band}`);
  const name = user?.display_name ?? "";
  const { today, status } = useToday();
  const my = useMyCourses();
  const ask = useAsk(token, lang);
  const { turns } = ask.state;

  const [items, setItems] = useState<Item[]>([]);
  const [sheet, setSheet] = useState(false);
  const [camera, setCamera] = useState(false);
  const [course, setCourse] = useState<AskCard | null>(null);
  const [starting, setStarting] = useState(false);
  const next = useRef(1);
  const opened = useRef(false);
  const acted = useRef(false);
  const lastAsk = useRef<{ req: Omit<AskRequest, "lang" | "thread_id">; inPlace?: boolean } | null>(null);
  const ring = useRef<HTMLButtonElement>(null);
  const device = useRef<HTMLInputElement>(null);
  const notesInput = useRef<HTMLInputElement>(null);
  const urls = useRef<string[]>([]);
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- the conversation
  const push = useCallback((it: Omit<Extract<Item, { kind: "me" }>, "id"> | Omit<Extract<Item, { kind: "ask" }>, "id">) => {
    setItems((l) => [...l, { ...it, id: next.current++ } as Item]);
  }, []);
  const me = useCallback(
    (text: string) => {
      acted.current = true;
      push({ kind: "me", text });
    },
    [push],
  );
  /** Mực says something: a short "typing" first, then the message. */
  const say = useCallback(
    (m: { text: ReactNode; rich?: ReactNode; replies?: Reply[] }) => {
      const id = next.current++;
      setItems((l) => [...l, { kind: "muc", id, ...m, typing: !reduce }]);
      if (!reduce) setTimeout(() => setItems((l) => l.map((x) => (x.id === id && x.kind === "muc" ? { ...x, typing: false } : x))), 550);
    },
    [reduce],
  );
  const use = (id: number, r: Reply) => {
    setItems((l) => l.map((x) => (x.id === id && x.kind === "muc" ? { ...x, used: true } : x)));
    if (r.to) return; // a link: the screen changes
    me(r.label);
    r.run?.();
  };

  // follow the conversation once the learner has said something (opening the screen never scrolls)
  const size = items.length + turns.length;
  useEffect(() => {
    if (acted.current) window.scrollTo({ top: document.documentElement.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, [size, reduce]);
  useEffect(() => () => urls.current.forEach((u) => URL.revokeObjectURL(u)), []);

  // ---- practice and other things to do today
  const startPractice = useCallback(
    async (source: StartSource) => {
      if (!token) return;
      try {
        const s = await practice.start(token, { source });
        nav(`/luyen-tap/${encodeURIComponent(s.id)}`, { state: { back: "/" } });
      } catch (e) {
        if (e instanceof PracticeError && e.code === "active_session" && typeof e.body.session_id === "string") nav(`/luyen-tap/${encodeURIComponent(e.body.session_id)}`, { state: { back: "/" } });
        else say({ text: t(e instanceof PracticeError && e.code === "insufficient_content" ? "today.quickNone" : "today.startFailed") });
      }
    },
    [nav, say, t, token],
  );
  const home = useRef<Promise<PHome | null> | null>(null);
  const loadHome = () => {
    if (!token) return Promise.resolve(null);
    home.current ??= practice.home(token).catch(() => null);
    return home.current;
  };
  const sessionCourse = today?.today?.course_id ?? null;

  const offerOthers = async () => {
    const h = await loadHome();
    const opts: Reply[] = [];
    if (h && h.quick.count > 0) opts.push({ label: t("today.opt.quick", { count: h.quick.count }), dur: t("today.min", { count: h.quick.minutes }), run: () => void startPractice("quick") });
    if (h && band !== "kid" && h.mocks[0]) opts.push({ label: h.mocks[0].title, dur: t("today.min", { count: h.mocks[0].minutes }), run: () => void startPractice(`mock:${h.mocks[0].profile_id}`) });
    for (const c of my.courses.filter((c) => !c.finished && c.enrollment.course_id !== sessionCourse).slice(0, 2))
      opts.push({ label: c.info.title, to: `/khoa-hoc/${encodeURIComponent(c.enrollment.course_id)}/hoc` });
    if (band !== "kid") opts.push({ label: t("today.notes.reply"), icon: "camera", run: askNotes });
    say(opts.length ? { text: t("today.otherIntro", { you }), replies: opts } : { text: t("today.otherNone") });
  };
  // ---- "Chụp vở": photos of class notes -> review questions (hs-03, CONTRACTS 16.4)
  const askNotes = () => say({ text: t("today.notes.asking"), replies: [{ primary: true, label: t("today.notes.pick"), run: () => notesInput.current?.click() }] });
  const whenOf = (iso: string) => {
    const d = new Date(iso);
    const time = hhmm(d);
    const days = Math.round((new Date(d).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000);
    return days <= 0 ? t("today.whenToday", { time }) : days === 1 ? t("today.whenTomorrow", { time }) : `${time} ${d.toLocaleDateString(lang === "en" ? "en-GB" : "vi-VN", { day: "numeric", month: "numeric" })}`;
  };
  const sendNotes = async (files: File[]) => {
    if (!token || files.length === 0) return;
    acted.current = true;
    me(t("today.notes.shot"));
    try {
      const images = await Promise.all(files.slice(0, 6).map((f) => downscaleImage(f)));
      const r: NotesResult = await postNotes(token, images);
      say({
        text: t("today.notes.line", { title: r.title, pages: r.pages, n: r.items }),
        replies: [
          {
            primary: true,
            label: t("today.notes.make"),
            run: () =>
              say({
                text: t("today.notes.done", { n: r.items, first: whenOf(r.first_review_at) }),
                replies: [{ primary: true, label: t("today.notes.now"), dur: t("today.min", { count: Math.max(3, Math.round(r.items * 0.8)) }), run: () => void startPractice(`notes:${r.notes_id}`) }],
              }),
          },
          { label: t("today.notes.no"), run: () => say({ text: t("today.notes.noAck") }) },
        ],
      });
    } catch (e) {
      const unreadable = e instanceof AskError && e.code === "unreadable";
      say({ text: t(unreadable ? "today.notes.unreadable" : "today.notes.failed"), replies: unreadable ? [{ label: t("today.notes.reply"), icon: "camera", run: () => notesInput.current?.click() }] : undefined });
    }
  };
  const offerMocks = async () => {
    const h = await loadHome();
    const mocks = h?.mocks ?? [];
    say(
      mocks.length
        ? { text: t("today.mockIntro"), replies: mocks.slice(0, 3).map((m) => ({ label: m.title, dur: t("today.min", { count: m.minutes }), run: () => void startPractice(`mock:${m.profile_id}`) })) }
        : { text: t("today.mockNone", { you }) },
    );
  };
  const offerQuick = async () => {
    const h = await loadHome();
    say(
      h && h.quick.count > 0
        ? { text: t("today.quickOffer"), replies: [{ primary: true, label: t("today.go.practice"), dur: t("today.min", { count: h.quick.minutes }), run: () => void startPractice("quick") }] }
        : { text: t("today.quickNone") },
    );
  };
  // ---- "Để sau": a real reminder, shown by the system even with the app closed (POST /reminders, CONTRACTS 12.1)
  const hhmm = (d: Date) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const at = (dayOffset: number, time: string) => {
    const [h, m] = time.split(":").map(Number);
    const d = new Date();
    d.setDate(d.getDate() + dayOffset);
    d.setHours(h, m, 0, 0);
    return d;
  };
  const enableNotify = () =>
    token &&
    void enableWebNotifications(
      () => api.vapidPublicKey(token),
      (sub) => api.pushSubscribe(token, sub),
    ).then((st) => {
      void refreshReminders();
      say({ text: t(st === "granted" ? "today.notifyOn" : "today.notifyOff", { you }) });
    });
  const remindAt = async (when: Date, tomorrow: boolean) => {
    if (!token) return;
    const s = today?.today ?? null;
    const course = s?.course_id ? my.courses.find((c) => c.enrollment.course_id === s.course_id) : undefined;
    try {
      await api.remindLater(token, {
        at: when.toISOString(),
        title_vi: course?.info.title ?? (s ? pickLang(s, "title", "vi") : ""),
        title_en: course?.info.title ?? (s ? pickLang(s, "title", "en") : ""),
        deep_link: s ? resolveDeepLink(s.deep_link).to : "/",
      });
      void refreshReminders(); // the device schedules it right away
      const time = t(tomorrow ? "today.whenTomorrow" : "today.whenToday", { time: hhmm(when) });
      // on the web a reminder only reaches a closed tab with notifications allowed: offer it once
      const ask = !isTauri() && notifyState() === "default";
      say({ text: t("today.remindSet", { time, you }), replies: ask ? [{ label: t("today.enableNotify"), run: enableNotify }] : undefined });
    } catch (e) {
      const code = e instanceof ApiError ? e.code : "unknown";
      if (code === "bedtime" && !tomorrow) say({ text: t("today.remindBedtime", { you }), replies: [tomorrowReply()] });
      else if (code === "quiet") say({ text: t("today.remindQuiet", { you }) });
      else say({ text: t("today.startFailed") });
    }
  };
  /** the session's own time when it is still ahead, else the usual evening slot */
  const slot = () => {
    const s = today?.today;
    return s?.start && s.start >= "06:30" ? s.start : band === "kid" ? "18:00" : "19:30";
  };
  const tomorrowReply = (): Reply => ({ label: t("today.tomorrowAt", { time: slot() }), run: () => void remindAt(at(1, slot()), true) });
  const later = () => {
    const now = new Date();
    const opts: Reply[] = [{ label: t("today.in1h"), run: () => void remindAt(new Date(now.getTime() + 3600000), false) }];
    const tonight = today?.today?.is_today && at(0, slot()).getTime() > now.getTime() + 30 * 60000 ? slot() : now.getHours() < 19 ? "20:00" : null;
    if (tonight) opts.push({ label: t("today.tonightAt", { time: tonight }), run: () => void remindAt(at(0, tonight), false) });
    opts.push(tomorrowReply());
    say({ text: t("today.laterAsk", { you }), replies: opts });
  };

  // ---- open the day: Mực speaks first (an introduction the very first time)
  const open = useCallback(() => {
    const uid = user?.id ?? null;
    const first = !hasSeen(uid, "today");
    if (first) {
      markSeen(uid, "today");
      say({ text: t("today.intro", { name }) });
    }
    const s = today?.today ?? null;
    const hi = first ? "" : `${t("today.hello", { name })} `; // the introduction already said hello
    const st = today?.streak;
    const streakLine = st && st.days >= 2 ? ` ${t(st.today_done ? "today.streakDone" : "today.streakKeep", { count: st.days, you })}` : "";
    const firstCourse = my.courses.find((c) => !c.finished);
    if (band === "kid" && (s || firstCourse)) {
      // the course's own name reads better to a child than the plan's line ("Tối nay: 15 phút ...")
      const sc = s?.course_id ? my.courses.find((c) => c.enrollment.course_id === s.course_id) : undefined;
      const title = sc?.info.title ?? firstCourse?.info.title ?? (s ? pickLang(s, "title", lang) : "");
      const to = s ? resolveDeepLink(s.deep_link).to : `/khoa-hoc/${encodeURIComponent(firstCourse!.enrollment.course_id)}/hoc`;
      const ord = (sc ?? firstCourse)?.ordinal ?? { n: 1, total: 3 };
      say({
        text: t("today.kidNext", { title }),
        rich: <KidPath done={Math.max(0, ord.n - 1)} total={Math.max(ord.total, 2)} />,
        replies: [{ primary: true, label: t("today.kidStart"), to }, { label: t("today.listen"), icon: "volume", run: () => speak(t("today.kidNext", { title }), lang) }],
      });
      return;
    }
    if (s && s.kind !== "break") {
      const goKey = s.kind === "lesson" ? "lesson" : s.kind === "research" ? "research" : s.kind === "review" ? "review" : "practice";
      const reason = pickLang(s, "reason", lang);
      const sc = s.kind === "lesson" && s.course_id ? my.courses.find((c) => c.enrollment.course_id === s.course_id) : undefined;
      say({
        text: (
          <>
            {hi}
            {t(`today.ask.${goKey}`)} <b>{sc?.info.title ?? pickLang(s, "title", lang)}</b>
            {t("today.askEnd")}
            {reason ? ` ${reason}` : ""}
            {streakLine}
          </>
        ),
        replies: [
          { primary: true, label: t(`today.go.${goKey}`), dur: t("today.min", { count: s.minutes }), to: resolveDeepLink(s.deep_link).to },
          { label: t("today.later"), run: later },
          { label: t("today.other"), run: () => void offerOthers() },
        ],
      });
    } else if (s) {
      say({ text: `${hi}${t("today.breakDay")}`, replies: [{ label: t("today.other"), run: () => void offerOthers() }] });
    } else if (firstCourse) {
      say({
        text: (
          <>
            {hi}
            {t("today.continueCourse")} <b>{firstCourse.info.title}</b>? {t("today.lessonOf", { n: firstCourse.ordinal.n, total: firstCourse.ordinal.total })}
          </>
        ),
        replies: [
          { primary: true, label: t("today.go.lesson"), to: `/khoa-hoc/${encodeURIComponent(firstCourse.enrollment.course_id)}/hoc` },
          { label: t("today.other"), run: () => void offerOthers() },
        ],
      });
    } else {
      say({ text: `${hi}${t("today.empty", { you })}`, replies: [{ label: t("today.findCourse"), icon: "search", to: "/khoa-hoc/tim-kiem" }] });
    }
    // reminders kept being ignored: say so plainly instead of nagging (they come every other day until the learner studies)
    if (today?.reminders_backoff) say({ text: t("today.backoff", { you }) });
    const research = band === "uni" && today?.hub.research ? pickLang(today.hub.research, "line", lang) : "";
    if (research) say({ text: research, replies: [{ label: t("today.openResearch"), to: "/nghien-cuu" }] });
  }, [today, my.courses, band, lang, name, user?.id]);

  useEffect(() => {
    if (opened.current || !user) return;
    if (status === "loading" && !today) return;
    if (my.status === "loading") return;
    opened.current = true;
    open();
  }, [status, today, my.status, user, open]);

  // Settings > "Xem lại từ đầu": Mực introduces itself again
  useEffect(() => {
    const again = () => {
      acted.current = false;
      setItems([]);
      opened.current = true;
      setTimeout(open, 300); // tours were just forgotten, so the introduction comes first
    };
    window.addEventListener(REPLAY_EVENT, again);
    return () => window.removeEventListener(REPLAY_EVENT, again);
  }, [open]);

  // ---- the box
  const sendAsk = (req: Omit<AskRequest, "lang" | "thread_id">, shown?: Parameters<typeof ask.send>[1], inPlace?: boolean) => {
    acted.current = true;
    lastAsk.current = { req, inPlace };
    if (!inPlace) push({ kind: "ask", start: turns.length });
    void ask.send(req, shown, { inPlace });
  };
  const onText = async (text: string) => {
    if (HELP.test(text)) {
      me(text);
      let answer = "";
      try {
        answer = token && !isMock ? await postGuide(token, { question: text.slice(0, 300), lang, screen: "today" }) : await askGuide(text, lang);
      } catch {
        answer = await askGuide(text, lang);
      }
      return say({ text: answer });
    }
    if (band !== "kid" && NOTES.test(text)) return me(text), askNotes();
    if (band !== "kid" && MOCK.test(text)) return me(text), void offerMocks();
    if (PRACTICE.test(text)) return me(text), void offerQuick();
    if (GOAL.test(text) && token) {
      me(text);
      try {
        const g = await api.createGoal(token, { title: text.slice(0, 120) });
        void refreshReminders();
        return say({ text: t("today.goalAdded", { title: g.title }), replies: [{ label: t("today.seeWeek"), run: () => setSheet(true) }] });
      } catch {
        return sendAsk({ text }, { text }); // not a goal after all: Hỏi đáp answers it
      }
    }
    sendAsk({ text }, { text });
  };
  const sendPhoto = async (file: Blob) => {
    setCamera(false);
    const image = await downscaleImage(file);
    const url = URL.createObjectURL(image);
    urls.current.push(url);
    sendAsk({ image }, { photo: url });
  };
  const openCamera = () => {
    if (typeof navigator.mediaDevices?.getUserMedia === "function") {
      window.scrollTo(0, 0);
      setCamera(true);
    } else device.current?.click();
  };
  const adder = useAddCourse(
    useCallback((c: AskCard) => say({ text: t("today.courseAdded", { title: c.title, you }) }), [say, t, you]),
    useCallback(() => say({ text: t("ask.courses.failed") }), [say, t]),
  );
  const startCourse = async (c: AskCard) => {
    if (!c.first_lesson) return;
    setStarting(true);
    try {
      if (adder.stateOf(c) !== "added" && !(await adder.add(c))) return;
      nav(`/khoa-hoc/${c.course_id}/hoc?lesson=${encodeURIComponent(c.first_lesson.lesson_id)}`, { state: { back: "/" } });
    } finally {
      setStarting(false);
    }
  };

  // ---- the progress sheet
  useEffect(() => {
    if (!sheet) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setSheet(false);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("keydown", esc);
      ring.current?.focus({ preventScroll: true });
    };
  }, [sheet]);

  const week = today?.week;
  const askStretch = (start: number, end: number) =>
    turns.slice(start, end).map((turn, k) => {
      const i = start + k;
      return turn.role === "me" ? (
        <MeBubble key={turn.id} turn={turn} />
      ) : (
        <AiBubble
          key={turn.id}
          turn={turn}
          latest={i === turns.length - 1}
          busy={ask.busy}
          lang={lang}
          h={{
            adder,
            onOpenCourse: (c: AskCard) => setCourse(c),
            onChoose: (p: AskProblem, partial: boolean) => sendAsk({ action: "choose", problem_id: p.id }, { text: t(partial ? "ask.choose.only" : "ask.choose.asked", { label: p.label.toLowerCase() }) }),
            onLastStep: () => sendAsk({ action: "last_step" }, undefined, true),
            onSimpler: () => sendAsk({ action: "simpler" }, { text: t("ask.solve.simpler") }),
            onSimilar: () => sendAsk({ action: "similar" }, { text: t("ask.solve.similar") }),
            onRetake: openCamera,
            onRetry: () => lastAsk.current && sendAsk(lastAsk.current.req, undefined, lastAsk.current.inPlace),
          }}
        />
      );
    });
  const askStarts = items.filter((x): x is Extract<Item, { kind: "ask" }> => x.kind === "ask").map((x) => x.start);

  return (
    <div className="app today-app">
      <header className="topbar">
        <span className="logo">
          <span className="logo-mark">M</span>
          <span>Mentor</span>
        </span>
        <span className="grow" />
        <button ref={ring} className="td-ring" type="button" onClick={() => setSheet(true)} aria-label={t("today.ringAria", { done: week?.done ?? 0, planned: week?.planned ?? 0 })} data-guide="progress" data-guide-label={t("hub.progress")}>
          <svg viewBox="0 0 36 36" aria-hidden="true">
            <circle className="trk" cx="18" cy="18" r="14" fill="none" strokeWidth="5" />
            <circle className="val" cx="18" cy="18" r="14" fill="none" strokeWidth="5" strokeDasharray={`${week && week.planned ? Math.min(1, week.done / week.planned) * 88 : 0} 88`} />
          </svg>
          <span>{t("today.ring", { done: week?.done ?? 0, planned: week?.planned ?? 0 })}</span>
        </button>
        <Settings />
      </header>

      {camera ? (
        <main className="chat-main">
          <Camera onShot={(b) => void sendPhoto(b)} onFile={(f) => void sendPhoto(f)} onClose={() => setCamera(false)} />
        </main>
      ) : (
        <main className="main td-main">
          <section className="td-strip-sec" aria-labelledby="td-strip-h" data-guide="courses" data-guide-label={t("today.strip")}>
            <h2 className="sr" id="td-strip-h">
              {t("today.strip")}
            </h2>
            <div className="td-strip">
              {my.courses.map((c) => (
                <Link key={c.enrollment.course_id} className="td-crs" to={`/khoa-hoc/${encodeURIComponent(c.enrollment.course_id)}`}>
                  <CourseCover courseId={c.enrollment.course_id} className="td-cover" />
                  <span className="td-crs-t">{c.info.title}</span>
                  {band !== "kid" && (
                    <span className="bar" aria-hidden="true">
                      <i style={{ width: `${c.percent}%` }} />
                    </span>
                  )}
                </Link>
              ))}
              {band === "uni" && (
                <Link className="td-crs" to="/nghien-cuu">
                  <span className="td-cover td-ph" aria-hidden="true">
                    <Icon name="file" />
                  </span>
                  <span className="td-crs-t">{t("today.research")}</span>
                </Link>
              )}
              <Link className="td-crs" to="/khoa-hoc/tim-kiem">
                <span className="td-cover td-ph" aria-hidden="true">
                  <Icon name="plus" />
                </span>
                <span className="td-crs-t">{t("today.findCourse")}</span>
              </Link>
            </div>
          </section>

          <section className="td-thread" role="log" aria-live="polite" aria-label={t("today.threadAria")} data-guide="ask" data-guide-label={t("hub.ask")}>
            {items.map((it, k) => {
              if (it.kind === "me") return <MeMessage key={it.id} text={it.text} />;
              if (it.kind === "muc")
                return <MucMessage key={it.id} text={it.text} rich={it.rich} replies={it.replies} used={it.used} typing={it.typing} onUse={(r) => use(it.id, r)} />;
              const end = askStarts.find((s) => s > it.start) ?? turns.length;
              return <div key={`a${it.id}-${k}`} className="td-ask">{askStretch(it.start, end)}</div>;
            })}
          </section>
        </main>
      )}

      {!camera &&
        (band === "kid" ? (
          <div className="td-kid-wrap">
            <KidAsk busy={ask.busy} onCamera={openCamera} onAudio={(audio) => sendAsk({ audio }, { audio: true })} />
          </div>
        ) : (
          <Composer
            busy={ask.busy}
            placeholder={t("today.placeholder")}
            onSend={(text) => void onText(text)}
            onCancel={ask.cancel}
            onCamera={openCamera}
            onPhoto={(f) => void sendPhoto(f)}
            onAudio={(audio) => sendAsk({ audio }, { audio: true })}
          />
        ))}
      <input
        ref={notesInput}
        type="file"
        accept="image/*"
        multiple
        hidden
        aria-label={t("today.notes.pick")}
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

      {course && <CourseSheet card={course} adder={adder} onClose={() => setCourse(null)} onStart={(c) => void startCourse(c)} starting={starting} />}

      {sheet && (
        <>
          <div className="td-scrim" onClick={() => setSheet(false)} />
          <section className="td-sheet" role="dialog" aria-modal="true" aria-labelledby="td-sheet-h">
            <span className="td-grab" aria-hidden="true" />
            <div className="td-sheet-h">
              <h2 id="td-sheet-h">{t("progress.week")}</h2>
              <button className="icon-btn" type="button" autoFocus onClick={() => setSheet(false)} aria-label={t("today.close")}>
                <Icon name="x" />
              </button>
            </div>
            <div className="pg-main td-sheet-body pg-sheet">
              <ProgressBody compact back="/" />
            </div>
          </section>
        </>
      )}
    </div>
  );
}
