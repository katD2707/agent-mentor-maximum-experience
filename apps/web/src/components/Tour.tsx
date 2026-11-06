"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactNode,
} from "react";
import { getApi } from "@/lib/api";
import { queueChatIntent } from "@/lib/chatIntent";
import { fireConfetti } from "@/lib/confetti";
import { prefersReducedMotion } from "@/lib/motion";
import { diagnosticRoute } from "@/lib/practice/routes";
import { hourLabel, STUDY_HOURS } from "@/lib/studyTime";
import {
  onTourSignal,
  SAMPLE_PROMPTS,
  shouldAutoStart,
  shouldResume,
  stepCounter,
  STEP_TEXT,
  tipFor,
  tourFinished,
  tourSteps,
  welcomeText,
  type TourSurface,
} from "@/lib/tour";
import { TourController, type TourView } from "@/lib/tourController";
import type { MascotState, TourStepId } from "@/lib/types";
import { Icon } from "./Icon";
import { Mascot } from "./Mascot";
import { useMe, useSession } from "./session";
import { errorText } from "./ui";

// ---- provider ----

const TourContext = createContext<{ replay: () => void } | null>(null);

/** Replay the tour (Settings -> "Xem lại hướng dẫn"). A no-op outside the provider. */
export function useTour(): { replay: () => void } {
  return useContext(TourContext) ?? { replay: () => {} };
}

/** Practice sessions, mock exams and the diagnostic are focus mode: the tour waits until the learner leaves them. */
function inFocusMode(pathname: string): boolean {
  return /^\/practice\/.+/.test(pathname);
}

export function TourProvider({ surface = "app", children }: { surface?: TourSurface; children: ReactNode }) {
  const me = useMe();
  const { setMe } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [controller] = useState(
    () =>
      new TourController({
        api: getApi(),
        role: me.role,
        surface,
        onState: () => {},
        reducedMotion: prefersReducedMotion,
        confetti: () => void fireConfetti({ size: "pop", origin: { x: 0.5, y: 0.7 } }),
        errorText,
      }),
  );
  const view = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);

  // Saved progress flows back into Me, so every screen sees the current tour state.
  useEffect(() => {
    controller.configure({ onState: (tour) => setMe({ ...me, tour }) });
  }, [controller, me, setMe]);

  // Start once for a new learner, or pick up where an unfinished tour stopped (other device, other page).
  const first = useRef(me);
  useEffect(() => {
    const m = first.current;
    if (shouldResume(m)) controller.resume(m.tour!.tour_step);
    else if (shouldAutoStart(m)) controller.start();
    return () => controller.dispose();
  }, [controller]);

  // Screens report what the learner did (a message sent, a diagnostic answer).
  useEffect(() => onTourSignal((s) => controller.signal(s)), [controller]);

  const toChat = useCallback(() => {
    if (surface === "app" && !/^\/chat(\/|$)/.test(window.location.pathname)) router.push("/chat");
  }, [router, surface]);

  const value = useMemo(
    () => ({
      replay: () => {
        controller.restart();
        toChat();
      },
    }),
    [controller, toChat],
  );

  const hidden = view.phase === "idle" || (surface === "app" && inFocusMode(pathname));
  return (
    <TourContext.Provider value={value}>
      {children}
      {!hidden && <TourLayer controller={controller} view={view} surface={surface} onToChat={toChat} />}
      {surface === "app" && <TipStrip tourOpen={view.phase !== "idle"} pathname={pathname} />}
    </TourContext.Provider>
  );
}

// ---- positioning ----

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

const TARGETS: Partial<Record<TourStepId, string>> = {
  ask: '[data-tour="composer"]',
  practice: '[data-tour="nav-practice"]',
};

function sameBox(a: Box | null, b: Box | null): boolean {
  return a === b || (!!a && !!b && a.left === b.left && a.top === b.top && a.width === b.width && a.height === b.height);
}

/** Where the target is on screen right now; null when it is missing or not visible (drawer closed, other page). */
function useTargetBox(selector: string | undefined): Box | null {
  const [box, setBox] = useState<Box | null>(null);
  useEffect(() => {
    if (!selector) return;
    const read = () => {
      const el = document.querySelector(selector);
      let next: Box | null = null;
      if (el) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && r.right > 0 && r.bottom > 0 && r.left < window.innerWidth && r.top < window.innerHeight) {
          next = { left: r.left, top: r.top, width: r.width, height: r.height };
        }
      }
      setBox((prev) => (sameBox(prev, next) ? prev : next));
    };
    const first = requestAnimationFrame(read);
    const poll = window.setInterval(read, 300); // layout moves with the keyboard, the drawer and page loads
    window.addEventListener("resize", read);
    window.addEventListener("scroll", read, true);
    return () => {
      cancelAnimationFrame(first);
      window.clearInterval(poll);
      window.removeEventListener("resize", read);
      window.removeEventListener("scroll", read, true);
    };
  }, [selector]);
  return selector ? box : null;
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Card next to the target, or null = dock it at the bottom of the screen. */
function placeCard(box: Box | null, vw: number, vh: number, narrowCard: number): CSSProperties | null {
  if (!box) return null;
  const w = Math.min(narrowCard, vw - 24);
  const right = box.left + box.width;
  const bottom = box.top + box.height;
  if (right < 320 && vw >= 720) return { left: right + 16, top: clamp(box.top - 8, 12, vh - 300), width: w };
  const left = clamp(box.left, 12, vw - w - 12);
  if (vh - bottom >= 290) return { left, top: bottom + 14, width: w };
  if (box.top >= 290) return { left, bottom: vh - box.top + 14, width: w };
  return null;
}

// ---- the coach card ----

const MASCOT: Record<TourStepId, MascotState> = { welcome: "wave", ask: "listening", practice: "happy", time: "calm" };

function TourLayer({
  controller,
  view,
  surface,
  onToChat,
}: {
  controller: TourController;
  view: TourView;
  surface: TourSurface;
  onToChat: () => void;
}) {
  const me = useMe();
  const router = useRouter();
  const pathname = usePathname();
  const cardRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const you = me.role === "ncs" ? "bạn" : "em";
  const role = me.role === "ncs" ? "ncs" : "thpt";
  const list = tourSteps(me.role, surface);
  const step = view.phase === "step" ? view.step : null;
  const box = useTargetBox(step ? TARGETS[step] : undefined);
  const [size, setSize] = useState({ w: 1024, h: 768 });
  useEffect(() => {
    const read = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    const t = requestAnimationFrame(read);
    window.addEventListener("resize", read);
    return () => {
      cancelAnimationFrame(t);
      window.removeEventListener("resize", read);
    };
  }, []);
  const style = placeCard(box, size.w, size.h, surface === "popup" ? 340 : 380);

  // Focus moves to the card's heading on every step, so a keyboard or screen-reader user lands on it.
  const focusKey = view.phase === "finish" ? "finish" : `${step}${view.ack ? "-ack" : ""}`;
  useEffect(() => {
    titleRef.current?.focus({ preventScroll: true });
  }, [focusKey]);

  // Esc = skip, unless it was meant for something else (typing in the chat box, an open dialog, a handled key).
  useEffect(() => {
    if (view.phase === "idle") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || document.querySelector("dialog[open]")) return;
      const t = e.target as HTMLElement | null;
      const typing = !!t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT" || t.tagName === "SELECT" || t.isContentEditable);
      if (typing && !cardRef.current?.contains(t)) return;
      if (view.phase === "finish") controller.close();
      else controller.skip();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [controller, view.phase]);

  // When the card goes away while focus is inside it, hand focus back to the page instead of dropping it on <body>.
  useEffect(() => {
    const card = cardRef.current;
    return () => {
      if (card && card.contains(document.activeElement)) document.getElementById("main")?.focus({ preventScroll: true });
    };
  }, []);

  const counter = step ? stepCounter(list, step) : null;
  const mascot: MascotState = view.phase === "finish" ? (view.celebrate ? "celebrate" : "happy") : view.ack ? "happy" : MASCOT[step ?? "welcome"];
  const docked = !style;

  let title = "";
  let body: ReactNode = null;
  let actions: ReactNode = null;
  if (view.phase === "finish") {
    title = "Xong!";
    body = (
      <>
        <p className="tour-body">
          {view.hour === null
            ? `Mầm sẽ không nhắc ${you}. Khi cần, ${you} bật lại ở Cài đặt.`
            : `Mầm sẽ nhắc ${you} lúc ${hourLabel(view.hour)}.`}
        </p>
        {view.blockedBy === "quiet_hours" && <p className="tour-note">Giờ yên lặng đang chặn giờ này. Đổi ở Cài đặt nếu {you} muốn.</p>}
        {view.blockedBy === "proactivity" && <p className="tour-note">Mức chủ động đang tắt trong Cài đặt nên Mầm chưa nhắc được.</p>}
      </>
    );
    actions = (
      <button type="button" className="btn btn-primary btn-sm" onClick={() => controller.close()}>
        Xong
      </button>
    );
  } else if (step === "welcome") {
    title = "Chào mừng";
    body = <p className="tour-body">{welcomeText(me.display_name, me.role)}</p>;
    actions = (
      <>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => {
            controller.advance();
            onToChat();
          }}
        >
          Bắt đầu
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => controller.skip()}>
          Tự khám phá
        </button>
      </>
    );
  } else if (step === "ask") {
    const t = STEP_TEXT.ask[role];
    title = view.ack ? "Mầm nhận được rồi!" : t.title;
    const onChat = surface === "popup" || /^\/chat(\/|$)/.test(pathname);
    body = view.ack ? (
      <p className="tour-body">Mầm đang xem. Mầm sẽ gợi ý từng bước chứ không đưa đáp án ngay nhé.</p>
    ) : (
      <>
        <p className="tour-body">{t.body}</p>
        {onChat ? (
          <ul className="tour-prompts" aria-label="Câu mẫu">
            {SAMPLE_PROMPTS[role].map((p) => (
              <li key={p}>
                <button type="button" className="tour-prompt" onClick={() => queueChatIntent({ kind: "prefill", text: p })}>
                  {p}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="tour-note">Mầm ở trang Trò chuyện.</p>
        )}
      </>
    );
    actions = view.ack ? null : (
      <>
        {!onChat && (
          <button type="button" className="btn btn-primary btn-sm" onClick={onToChat}>
            Mở trò chuyện
          </button>
        )}
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => controller.advance()}>
          Để sau
        </button>
      </>
    );
  } else if (step === "practice") {
    const t = STEP_TEXT.practice;
    title = t.title;
    body = <p className="tour-body">{t.body}</p>;
    actions = (
      <>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => router.push(diagnosticRoute({ subject: "math" }))}>
          Làm 5 câu
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => controller.advance()}>
          Bỏ qua
        </button>
      </>
    );
  } else if (step === "time") {
    const t = STEP_TEXT.time[role];
    title = t.title;
    body = (
      <>
        <p className="tour-body">{t.body}</p>
        <div className="tour-chips" role="group" aria-label={t.title}>
          {STUDY_HOURS.map((h) => (
            <button key={h} type="button" className="btn btn-sm tour-chip" disabled={view.busy} onClick={() => void controller.chooseHour(h)}>
              {h}h
            </button>
          ))}
          <button type="button" className="btn btn-sm tour-chip" disabled={view.busy} onClick={() => void controller.chooseHour(null)}>
            Không cần nhắc
          </button>
        </div>
        {view.busy && (
          <p className="tour-note" role="status">
            Đang lưu…
          </p>
        )}
        {view.error && (
          <p className="tour-error" role="alert">
            Chưa lưu được: {view.error}. Thử lại hoặc chọn “Để sau”.
          </p>
        )}
      </>
    );
    actions = (
      <button type="button" className="btn btn-ghost btn-sm" disabled={view.busy} onClick={() => controller.advance()}>
        Để sau
      </button>
    );
  }
  if (!title) return null;

  return (
    <>
      {box && step && <div className="tour-ring" aria-hidden="true" style={{ left: box.left - 6, top: box.top - 6, width: box.width + 12, height: box.height + 12 }} />}
      <div
        ref={cardRef}
        className={`tour-card${docked ? " tour-card--dock" : ""}${surface === "popup" ? " tour-card--popup" : ""}`}
        style={style ?? undefined}
        role={view.phase === "finish" ? "status" : "dialog"}
        aria-modal={view.phase === "finish" ? undefined : false}
        aria-labelledby="tour-title"
        data-step={view.phase === "finish" ? "finish" : step}
      >
        <div className="tour-head">
          <Mascot state={mascot} size={surface === "popup" ? 36 : 44} />
          <div className="tour-titles">
            <h2 id="tour-title" ref={titleRef} tabIndex={-1} className="tour-title">
              {title}
            </h2>
            {counter && !view.ack && (
              <span className="tour-count" aria-label={`Bước ${counter.index} trên ${counter.total}`}>
                Bước {counter.index}/{counter.total}
              </span>
            )}
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-icon btn-sm"
            aria-label={view.phase === "finish" ? "Đóng" : "Bỏ qua hướng dẫn"}
            onClick={() => (view.phase === "finish" ? controller.close() : controller.skip())}
          >
            <Icon name="close" size={16} />
          </button>
        </div>
        {body}
        {actions && <div className="tour-actions">{actions}</div>}
      </div>
    </>
  );
}

// ---- contextual tips ----

function TipStrip({ tourOpen, pathname }: { tourOpen: boolean; pathname: string }) {
  const me = useMe();
  const { setMe } = useSession();
  const tip = tourFinished(me.tour) ? tipFor(pathname, me.role, me.tour, tourOpen) : null;
  const [ready, setReady] = useState<string | null>(null);
  const [gone, setGone] = useState<ReadonlySet<string>>(new Set());
  const id = tip?.id ?? null;

  // A beat after the page appears, so it does not compete with the page loading.
  useEffect(() => {
    if (!id) return;
    const t = window.setTimeout(() => setReady(id), 700);
    return () => window.clearTimeout(t);
  }, [id]);

  if (!tip || ready !== tip.id || gone.has(tip.id)) return null;

  function seen(tipId: string) {
    setGone((g) => new Set(g).add(tipId));
    getApi()
      .updateTour({ tip: tipId })
      .then(
        (tour) => setMe({ ...me, tour }),
        (e) => console.warn("tip: could not save", e),
      );
  }

  return (
    <div className="tour-tip" role="status">
      <Mascot state="happy" size={28} />
      <span className="tour-tip-text">{tip.text}</span>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => seen(tip.id)}>
        Đã hiểu
      </button>
    </div>
  );
}
