import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "katex/dist/katex.min.css";
import type { AskCard, AskProblem, AskRequest } from "../../api";
import { useAuth } from "../../state/auth";
import { Icon, type IconName } from "../../components/Icon";
import { Settings } from "../../components/Settings";
import { downscaleImage } from "../../lib/image";
import { AiBubble, MeBubble } from "./Turns";
import { Composer } from "./Composer";
import { Camera } from "./Camera";
import { CourseSheet, useAddCourse } from "./Courses";
import { logEvent } from "../../lib/events";
import { useAsk } from "./useAsk";

/** hs-08 Hỏi đáp: one thread for the session (no history), the composer pinned at the bottom. */
export default function Ask() {
  const { t, i18n } = useTranslation();
  const { token, user } = useAuth();
  const nav = useNavigate();
  const lang = i18n.language === "en" ? "en" : "vi";
  const kid = user?.age_band === "g1_5";
  const ask = useAsk(token, lang);
  const { turns } = ask.state;

  const [camera, setCamera] = useState(false);
  const [sheet, setSheet] = useState<AskCard | null>(null);
  const [starting, setStarting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const last = useRef<{ req: Omit<AskRequest, "lang" | "thread_id">; me?: Parameters<typeof ask.send>[1]; inPlace?: boolean } | null>(null);
  const urls = useRef<string[]>([]);
  const end = useRef<HTMLDivElement>(null);
  const device = useRef<HTMLInputElement>(null);

  const adder = useAddCourse(
    useCallback((c: AskCard) => {
      setFailed(false);
      setToast(c.title);
    }, []),
    useCallback(() => setFailed(true), []),
  );

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(id);
  }, [toast]);

  useEffect(() => () => urls.current.forEach((u) => URL.revokeObjectURL(u)), []);

  // follow the answer as it grows
  const size = turns.length;
  useEffect(() => {
    if (size) end.current?.scrollIntoView?.({ block: "end", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [size, ask.state.turns]);

  const send = (req: Omit<AskRequest, "lang" | "thread_id">, me?: Parameters<typeof ask.send>[1], inPlace?: boolean) => {
    last.current = { req, me, inPlace };
    void ask.send(req, me, { inPlace });
  };

  const sendPhoto = async (file: Blob) => {
    setCamera(false);
    const image = await downscaleImage(file);
    const url = URL.createObjectURL(image);
    urls.current.push(url);
    send({ image }, { photo: url });
  };

  const openCamera = () => {
    if (typeof navigator.mediaDevices?.getUserMedia === "function") {
      window.scrollTo(0, 0);
      setCamera(true);
    }
    else device.current?.click(); // no live camera API: the phone's own camera app takes the photo
  };

  const startCourse = async (c: AskCard) => {
    if (!token || !user || !c.first_lesson) return;
    setStarting(true);
    try {
      if (adder.stateOf(c) !== "added" && !(await adder.add(c))) return;
      nav(`/khoa-hoc/${c.course_id}/hoc?lesson=${encodeURIComponent(c.first_lesson.lesson_id)}`);
    } finally {
      setStarting(false);
    }
  };

  const chips: { icon: IconName; text: string; photo?: boolean }[] = kid
    ? [
        { icon: "text" as IconName, text: t("ask.chipsKid.learn") },
        { icon: "camera", text: t("ask.chipsKid.solve"), photo: true },
        { icon: "quiz", text: t("ask.chipsKid.add") },
        { icon: "quiz", text: t("ask.chipsKid.what") },
      ]
    : [
        { icon: "text" as IconName, text: t("ask.chips.learn") },
        { icon: "camera", text: t("ask.chips.solve"), photo: true },
        { icon: "flag", text: t("ask.chips.exam") },
        { icon: "quiz", text: t("ask.chips.what") },
      ];

  const latestAi = (() => {
    for (let i = turns.length - 1; i >= 0; i--) if (turns[i].role === "ai") return i;
    return -1;
  })();

  return (
    <div className="app ask-app">
      <header className="topbar">
        <Link className="icon-btn" to="/" aria-label={t("back")} data-guide="back" data-guide-label={t("back")}>
          <Icon name="grid" />
        </Link>
        <h1 className="page-title">{t("hub.ask")}</h1>
        <span className="grow" />
        <Settings />
      </header>

      {camera ? (
        <main className="chat-main">
          <Camera onShot={(b) => void sendPhoto(b)} onFile={(f) => void sendPhoto(f)} onClose={() => setCamera(false)} />
        </main>
      ) : (
        <>
          <main className="chat-main" data-guide="ask" data-guide-label={t("hub.ask")}>
            {turns.length === 0 && (
              <section className="greet">
                <h2>{t("ask.greet")}</h2>
                <div className="starters">
                  {chips.map((c) => (
                    <button key={c.text} className="starter" type="button" onClick={() => (c.photo ? openCamera() : send({ text: c.text }, { text: c.text }))}>
                      <Icon name={c.icon} />
                      <span>{c.text}</span>
                    </button>
                  ))}
                </div>
              </section>
            )}
            {turns.map((turn, i) =>
              turn.role === "me" ? (
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
                    onOpenCourse: (c: AskCard) => {
                      logEvent("ask_course_open", { course_id: c.course_id });
                      setSheet(c);
                    },
                    onChoose: (p: AskProblem, partial: boolean) => send({ action: "choose", problem_id: p.id }, { text: t(partial ? "ask.choose.only" : "ask.choose.asked", { label: p.label.toLowerCase() }) }),
                    onLastStep: () => send({ action: "last_step" }, undefined, true),
                    onSimpler: () => send({ action: "simpler" }, { text: t("ask.solve.simpler") }),
                    onSimilar: () => send({ action: "similar" }, { text: t("ask.solve.similar") }),
                    onRetake: openCamera,
                    onRetry: () => last.current && send(last.current.req, undefined, last.current.inPlace),
                  }}
                />
              ),
            )}
            <div ref={end} className="chat-end" data-latest={latestAi} />
          </main>

          <Composer
            notice={
              (toast || failed) ? (
                <p className={`added-bar${failed && !toast ? " fail" : ""}`} role="status">
                  <Icon name={failed && !toast ? "x" : "check"} />
                  {failed && !toast ? t("ask.courses.failed") : t("ask.courses.toast", { title: toast })}
                </p>
              ) : null
            }
              busy={ask.busy}
              onSend={(text) => send({ text }, { text })}
              onCancel={ask.cancel}
              onCamera={openCamera}
              onPhoto={(f) => void sendPhoto(f)}
              onAudio={(audio) => send({ audio }, { audio: true })}
          />
        </>
      )}
      <input ref={device} type="file" accept="image/*" capture="environment" hidden onChange={(e) => {
        const f = e.target.files?.[0];
        e.target.value = "";
        if (f) void sendPhoto(f);
      }} />

      {sheet && <CourseSheet card={sheet} adder={adder} onClose={() => setSheet(null)} onStart={(c) => void startCourse(c)} starting={starting} />}
    </div>
  );
}

