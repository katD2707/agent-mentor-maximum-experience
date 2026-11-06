"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  countdown,
  countdownTickMs,
  DEADLINE_FOCUS_MINUTES,
  deadlineTone,
  flashcardAnswered,
  FOCUS_EXTEND_MINUTES,
  focusProgress,
  formatClock,
  formatCountdown,
  formatDue,
  type CardEvent,
  type CardUiState,
} from "@/lib/chat/cards";
import { fireConfetti, originOf } from "@/lib/confetti";
import { DUR, EASE_IN_OUT, EASE_OUT, FADE, rise, SPRING, useReducedMotion } from "@/lib/motion";
import type {
  CelebrationCard,
  ChatCard,
  CheckinCard,
  DeadlineCard,
  FlashcardCard,
  FocusCard,
  WeeklyCard,
} from "@/lib/types";
import { CountUp } from "../CountUp";
import { Icon, type IconName } from "../Icon";
import { PracticeLinkCard } from "../practice/PracticeLinkCard";

export interface CardProps<C extends ChatCard> {
  card: C;
  ui: CardUiState;
  /** Arrived live in this tab: animates in, accepts clicks. False = history replay, static. */
  live: boolean;
  /** A turn is running: the gateway refuses clicks then, so buttons wait. */
  busy?: boolean;
  /** The turn looks crisis-related: no celebration, no streak, nothing playful. */
  crisis: boolean;
  onEvent: (card: ChatCard, ev: CardEvent) => void;
  /** A celebration card played (confetti fired); ChatView makes the mascot celebrate. */
  onCelebrate?: (card: ChatCard) => void;
}

/** Current time, re-rendered every `tickFor(now)` ms (0 = stop). */
function useNow(tickFor: (now: number) => number): number {
  const [now, setNow] = useState(() => Date.now());
  const tickMs = tickFor(now);
  useEffect(() => {
    if (tickMs <= 0) return;
    const t = window.setInterval(() => setNow(Date.now()), tickMs);
    return () => window.clearInterval(t);
  }, [tickMs]);
  return now;
}

function CardShell({
  card,
  live,
  icon,
  title,
  meta,
  children,
  bounce = false,
  innerRef,
}: {
  card: ChatCard;
  live: boolean;
  icon: IconName;
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  bounce?: boolean;
  innerRef?: React.Ref<HTMLElement>;
}) {
  const reduce = useReducedMotion();
  const titleId = useId();
  const r = rise(reduce, { y: 10, scale: 0.97 });
  return (
    <motion.section
      ref={innerRef}
      className={`cc cc-${card.kind}`}
      aria-labelledby={titleId}
      initial={live ? r.initial : false}
      animate={r.animate}
      transition={!reduce && bounce ? { type: "spring", duration: 0.55, bounce: 0.32 } : r.transition}
    >
      <header className="cc-head">
        <span className="cc-icon" aria-hidden="true">
          <Icon name={icon} size={18} />
        </span>
        <div className="cc-titles">
          <h3 id={titleId} className="cc-title">
            {title}
          </h3>
          {meta && <p className="cc-meta">{meta}</p>}
        </div>
      </header>
      {children}
    </motion.section>
  );
}

// ---------------------------------------------------------------- flashcard

const LETTERS = "ABCD";

function FlashcardView({ card, ui, live, busy, onEvent }: CardProps<FlashcardCard>) {
  const reduce = useReducedMotion();
  const backHeading = useRef<HTMLHeadingElement>(null);
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const choices = (card.choices ?? []).slice(0, 4);
  const answered = flashcardAnswered(ui);
  const canAct = live && !answered && !busy;

  // Let the choice feedback land (450 ms) before the card turns over; a state restored as answered flips at once.
  const [settled, setSettled] = useState(answered);
  const flipped = answered && settled;
  useEffect(() => {
    if (!answered || settled) return;
    const t = window.setTimeout(() => setSettled(true), reduce ? 150 : 450);
    return () => window.clearTimeout(t);
  }, [answered, settled, reduce]);
  // Keyboard users land on the answer once it shows (only for a card answered in this tab).
  useEffect(() => {
    if (flipped && live) backHeading.current?.focus({ preventScroll: true });
  }, [flipped, live]);

  function submitText(e: FormEvent) {
    e.preventDefault();
    if (draft.trim()) onEvent(card, { type: "flash_answer", text: draft.trim() });
  }

  const verdict = ui.skipped
    ? { cls: "neutral", text: "Đã bỏ qua thẻ này" }
    : ui.correct === true
      ? { cls: "ok", text: "Chính xác!" }
      : ui.correct === false
        ? { cls: "soft", text: "Chưa đúng, không sao" }
        : answered
          ? { cls: "neutral", text: "Đã gửi, mentor sẽ nhận xét" }
          : null;

  const front = (
    <div className="flip-face flip-front" aria-hidden={flipped} inert={flipped}>
      <p className="cc-question">{card.front}</p>
      {choices.length > 0 ? (
        <div className="cc-choices" role="group" aria-label="Các lựa chọn">
          {choices.map((c, i) => {
            const chosen = ui.chosen === c;
            const state = chosen ? (ui.correct === true ? "right" : ui.correct === false ? "wrong" : "picked") : undefined;
            return (
              <motion.button
                key={c}
                type="button"
                className="cc-choice"
                data-state={state}
                aria-pressed={chosen}
                disabled={!canAct}
                onClick={() => onEvent(card, { type: "flash_choose", value: c })}
                animate={state === "wrong" && !reduce ? { x: [0, -4, 4, -2, 0] } : { x: 0 }}
                transition={{ duration: 0.32, ease: EASE_OUT }}
              >
                <span className="cc-letter" aria-hidden="true">
                  {LETTERS[i]}
                </span>
                <span>{c}</span>
              </motion.button>
            );
          })}
        </div>
      ) : (
        <form className="cc-answer" onSubmit={submitText}>
          <label htmlFor={inputId} className="sr-only">
            Câu trả lời của bạn
          </label>
          <input
            id={inputId}
            className="input"
            value={draft}
            maxLength={300}
            placeholder="Câu trả lời của bạn…"
            onChange={(e) => setDraft(e.target.value)}
            disabled={!canAct}
          />
          <button type="submit" className="btn btn-sm btn-primary" disabled={!canAct || !draft.trim()}>
            Gửi
          </button>
        </form>
      )}
      {live && !answered && (
        <div className="cc-actions">
          <button type="button" className="btn btn-sm btn-ghost" disabled={!canAct} onClick={() => onEvent(card, { type: "flash_skip" })}>
            Bỏ qua
          </button>
        </div>
      )}
    </div>
  );

  const back = (
    <div className="flip-face flip-back" aria-hidden={!flipped} inert={!flipped}>
      <h4 className="cc-back-title" ref={backHeading} tabIndex={-1}>
        {ui.answerText ? `Bạn trả lời: ${ui.answerText}` : ui.chosen ? `Bạn chọn: ${ui.chosen}` : "Đáp án"}
      </h4>
      {/* reveal only after the learner answered (Built H) */}
      {answered && <p className="cc-reveal">{card.reveal || "Mentor sẽ giải thích trong trò chuyện."}</p>}
      <div aria-live="polite">
        {verdict && flipped && (
          <motion.p
            key={verdict.text}
            className={`cc-verdict cc-verdict-${verdict.cls}`}
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={reduce ? FADE : { type: "spring", duration: 0.4, bounce: 0.35 }}
          >
            {verdict.cls === "ok" && <Icon name="check" size={16} />}
            {verdict.text}
          </motion.p>
        )}
      </div>
    </div>
  );

  return (
    <CardShell card={card} live={live} icon="cards" title="Thẻ ôn nhanh" meta={card.skill}>
      <div className="flip" data-reduce={reduce || undefined}>
        <motion.div
          className="flip-inner"
          initial={false}
          animate={reduce ? {} : { rotateY: flipped ? 180 : 0 }}
          transition={{ duration: 0.42, ease: EASE_IN_OUT }}
          data-flipped={flipped}
        >
          {front}
          {back}
        </motion.div>
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------- deadline

function DeadlineView({ card, ui, live, busy, onEvent }: CardProps<DeadlineCard>) {
  const reduce = useReducedMotion();
  const now = useNow((t) => (live ? countdownTickMs(countdown(card.due_at, t)) : 0));
  const c = countdown(card.due_at, now);
  const tone = ui.deadline === "done" ? "past" : deadlineTone(c);
  const text = ui.deadline === "done" ? "đã xong" : formatCountdown(c);
  return (
    <CardShell card={card} live={live} icon="clock" title={card.title} meta={card.source ? `Nguồn: ${card.source}` : undefined}>
      <div className="cc-deadline" data-tone={tone}>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.p
            key={text}
            className="cc-countdown"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6, filter: "blur(2px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6, filter: "blur(2px)" }}
            transition={{ duration: DUR.slow, ease: EASE_OUT }}
          >
            {text}
          </motion.p>
        </AnimatePresence>
        <p className="cc-due">
          Hạn: <time dateTime={card.due_at}>{formatDue(card.due_at)}</time> (giờ Việt Nam)
        </p>
      </div>
      {live && !ui.deadline && (
        <div className="cc-actions">
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={busy}
            onClick={() => onEvent(card, { type: "deadline_focus", minutes: DEADLINE_FOCUS_MINUTES })}
          >
            Tập trung {DEADLINE_FOCUS_MINUTES} phút
          </button>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => onEvent(card, { type: "deadline_done" })}>
            Đã xong
          </button>
        </div>
      )}
      {ui.deadline === "start_focus" && <p className="cc-detail cc-after">Đã bắt đầu một phiên tập trung cho việc này.</p>}
    </CardShell>
  );
}

// ---------------------------------------------------------------- focus

const RING_R = 34;
const RING_C = 2 * Math.PI * RING_R;

function FocusView({ card, ui, live, busy, onEvent }: CardProps<FocusCard>) {
  const reduce = useReducedMotion();
  const ended = ui.focusDone === true || !!card.ended_at;
  const now = useNow(() => (live && !ended ? 1000 : 0));
  const p = focusProgress(card, ui, now);
  const remainingMin = Math.ceil(p.remainingMs / 60_000);
  const status = p.ended ? "Đã xong phiên tập trung" : p.finished ? "Hết giờ rồi" : `Còn khoảng ${remainingMin} phút`;
  return (
    <CardShell card={card} live={live} icon="clock" title={card.task} meta={`Phiên tập trung ${card.minutes} phút`}>
      <div className="cc-focus" data-done={p.ended || undefined} data-finished={p.finished || undefined}>
        <div className="ring" role="timer" aria-label={status}>
          <svg viewBox="0 0 80 80" width="88" height="88" aria-hidden="true">
            <circle className="ring-track" cx="40" cy="40" r={RING_R} />
            <circle
              className="ring-fill"
              cx="40"
              cy="40"
              r={RING_R}
              strokeDasharray={RING_C}
              strokeDashoffset={RING_C * (1 - p.fraction)}
              style={{ transition: reduce ? "none" : `stroke-dashoffset ${live && !p.ended ? "1s linear" : `${DUR.slow}s ease-out`}` }}
            />
          </svg>
          <span className="ring-center" aria-hidden="true">
            <AnimatePresence mode="popLayout" initial={false}>
              {p.ended ? (
                <motion.span
                  key="check"
                  className="ring-check"
                  initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={reduce ? FADE : { type: "spring", duration: 0.4, bounce: 0.4 }}
                >
                  <Icon name="check" size={26} />
                </motion.span>
              ) : (
                <motion.span key="clock" className="ring-clock" exit={{ opacity: 0 }}>
                  {formatClock(p.remainingMs)}
                </motion.span>
              )}
            </AnimatePresence>
          </span>
        </div>
        <div className="cc-focus-side">
          <p className="cc-focus-status" aria-live="polite">
            {status}
          </p>
          {live && !p.ended && (
            <div className="cc-actions">
              <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={() => onEvent(card, { type: "focus_done" })}>
                Xong rồi
              </button>
              <button
                type="button"
                className="btn btn-sm"
                disabled={busy}
                onClick={() => onEvent(card, { type: "focus_extend", minutes: FOCUS_EXTEND_MINUTES, now: Date.now() })}
              >
                Thêm {FOCUS_EXTEND_MINUTES} phút
              </button>
            </div>
          )}
        </div>
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------- celebration

function CelebrationView({ card, ui, live, crisis, onEvent, onCelebrate }: CardProps<CelebrationCard>) {
  const ref = useRef<HTMLElement>(null);
  const started = useRef(false);
  // Decided once at mount: a live, unplayed card outside a crisis turn. Never on history replay.
  const [celebrating] = useState(() => live && !ui.played && !crisis);
  useEffect(() => {
    if (!celebrating || started.current) return;
    started.current = true;
    // Once only: mark it played at once, so the offline copy and remounts never fire again.
    onEvent(card, { type: "celebration_played" });
    window.setTimeout(() => {
      void fireConfetti({ origin: originOf(ref.current) });
      onCelebrate?.(card);
    }, 180);
  }, [celebrating, card, onEvent, onCelebrate]);
  return (
    <CardShell card={card} live={live} icon="spark" title={card.title} bounce={celebrating} innerRef={ref}>
      {card.detail && <p className="cc-detail">{card.detail}</p>}
    </CardShell>
  );
}

// ---------------------------------------------------------------- weekly

function WeeklyView({ card, live, crisis }: CardProps<WeeklyCard>) {
  const reduce = useReducedMotion();
  const run = live && !reduce;
  const stats: { label: string; value: number }[] = [
    { label: "phút tập trung", value: card.focus_minutes },
    { label: "cột mốc xong", value: card.milestones_done },
    { label: "lỗi đã sửa", value: card.mistakes_fixed },
  ];
  // No streak in crisis context (CONTRACTS 9).
  if (!crisis && card.streak_days > 0) stats.push({ label: "ngày học liền mạch", value: card.streak_days });
  return (
    <CardShell card={card} live={live} icon="chart" title="Tuần này của bạn">
      <dl className="cc-stats">
        {stats.map((s, i) => (
          <motion.div
            key={s.label}
            className="cc-stat"
            initial={live ? (reduce ? { opacity: 0 } : { opacity: 0, y: 6 }) : false}
            animate={{ opacity: 1, y: 0 }}
            transition={reduce ? FADE : { ...SPRING, delay: 0.08 + i * 0.06 }}
          >
            <dt>{s.label}</dt>
            <dd>
              <CountUp value={s.value} run={run} delay={0.1 + i * 0.06} />
            </dd>
          </motion.div>
        ))}
      </dl>
      {card.highlight && <p className="cc-detail">{card.highlight}</p>}
    </CardShell>
  );
}

// ---------------------------------------------------------------- check-in

function CheckinView({ card, ui, live, busy, onEvent }: CardProps<CheckinCard>) {
  const reduce = useReducedMotion();
  const picked = ui.picked;
  return (
    <CardShell card={card} live={live} icon="heart" title={card.prompt}>
      <div className="cc-options" role="group" aria-label={card.prompt}>
        {card.options.map((o, i) => (
          <motion.button
            key={o}
            type="button"
            className="cc-option"
            aria-pressed={picked === o}
            data-dim={picked !== undefined && picked !== o ? true : undefined}
            disabled={!live || picked !== undefined || busy}
            onClick={() => onEvent(card, { type: "checkin_pick", value: o })}
            initial={live ? (reduce ? { opacity: 0 } : { opacity: 0, y: 6 }) : false}
            animate={{ opacity: 1, y: 0 }}
            transition={reduce ? FADE : { ...SPRING, delay: 0.1 + i * 0.05 }}
          >
            {picked === o && <Icon name="check" size={14} />}
            {o}
          </motion.button>
        ))}
      </div>
    </CardShell>
  );
}

// ---------------------------------------------------------------- dispatcher

export function ChatCardView(props: CardProps<ChatCard>) {
  const { card } = props;
  switch (card.kind) {
    case "flashcard":
      return <FlashcardView {...(props as CardProps<FlashcardCard>)} />;
    case "deadline":
      return <DeadlineView {...(props as CardProps<DeadlineCard>)} />;
    case "focus":
      return <FocusView {...(props as CardProps<FocusCard>)} />;
    case "celebration":
      return <CelebrationView {...(props as CardProps<CelebrationCard>)} />;
    case "weekly":
      return <WeeklyView {...(props as CardProps<WeeklyCard>)} />;
    case "checkin":
      return <CheckinView {...(props as CardProps<CheckinCard>)} />;
    case "practice":
    case "mock":
      return <PracticeLinkCard card={card} live={props.live} />;
    default:
      return null; // unknown kind from a newer gateway: skip quietly
  }
}

/** One-line screen reader announcement for a card that just arrived. */
export function cardAnnouncement(card: ChatCard): string {
  switch (card.kind) {
    case "flashcard":
      return `Mentor gửi một thẻ ôn: ${card.front}`;
    case "deadline":
      return `Hạn sắp tới: ${card.title}, ${formatDue(card.due_at)}`;
    case "focus":
      return card.ended_at ? `Đã xong phiên tập trung: ${card.task}` : `Phiên tập trung ${card.minutes} phút: ${card.task}`;
    case "celebration":
      return `Cột mốc mới: ${card.title}`;
    case "weekly":
      return "Mentor gửi tổng kết tuần của bạn";
    case "checkin":
      return `Mentor hỏi: ${card.prompt}`;
    case "practice":
      return `Mentor gợi ý một buổi luyện tập: ${card.title}`;
    case "mock":
      return `Mentor gợi ý một bài thi thử: ${card.title}`;
    default:
      return "";
  }
}
