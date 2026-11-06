"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getApi, isApiError } from "@/lib/api";
import {
  canCheck,
  currentAnswer,
  cycleStatement,
  errorCode,
  initialElapsed,
  isOver,
  keyAction,
  nextStreak,
  partOf,
  shouldAutoSubmit,
  shouldTick,
  statementOutcome,
  timeLimitOf,
  timerView,
  type KeyAction,
  type PlayerMode,
} from "@/lib/practice/logic";
import { cacheReport } from "@/lib/practice/reportCache";
import { playCue } from "@/lib/practice/sfx";
import type { AnswerResult, RevealResult, Session } from "@/lib/practice/types";
import { errorText } from "../ui";
import { emitTourSignal } from "@/lib/tour";
import { useToast } from "../toast";
import type { FeedbackData } from "./Feedback";

export const summaryRoute = (id: string) => `/practice/summary/${encodeURIComponent(id)}`;

function toFeedback(r: AnswerResult, answer: string | null): FeedbackData {
  const fb = typeof r.option_feedback === "string" ? (answer ? { [answer]: r.option_feedback } : null) : (r.option_feedback ?? null);
  return {
    correct: r.correct === true,
    unanswered: r.correct == null,
    points: r.points,
    maxPoints: r.max_points,
    correctAnswer: r.correct_answer ?? "",
    statementResults: r.statement_results ? statementOutcome(r.statement_results) : undefined,
    optionFeedback: fb,
    statementExplanations: Array.isArray(r.statement_results)
      ? r.statement_results.flatMap((x) => (typeof x === "object" && x && "truth" in x && typeof x.id === "string" && typeof x.truth === "boolean" ? [{ id: x.id, truth: x.truth, explanation: (x as { explanation?: string | null }).explanation }] : []))
      : undefined,
  };
}

/** State machine of one session (practice, mock or diagnostic). All grading is the gateway's; this only tracks the screen. */
export function usePlayer(sessionId: string) {
  const api = getApi().practice;
  const router = useRouter();
  const toast = useToast();

  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [position, setPosition] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string | null>>({});
  const [flags, setFlags] = useState<Record<number, boolean>>({});
  const [results, setResults] = useState<Record<number, FeedbackData>>({});
  const [hints, setHints] = useState<Record<number, string>>({});
  const [reveals, setReveals] = useState<Record<number, RevealResult>>({});
  const [showSolution, setShowSolution] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [streak, setStreak] = useState(0);
  const [effect, setEffect] = useState({ shake: 0, bounce: 0 });
  const [busy, setBusy] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [dialog, setDialog] = useState<"none" | "exit" | "finish" | "grid" | "report">("none");

  // Latest values for timers and cleanup (no stale closures).
  const live = useRef({ session, position, answers, elapsed, finishing });
  useEffect(() => {
    live.current = { session, position, answers, elapsed, finishing };
  });
  const clock = useRef({ base: 0, t0: 0 });
  const shownAt = useRef(0);
  const expiredRef = useRef<() => void>(() => {});
  const pendingSave = useRef<{ pos: number; answer: string | null; timer: ReturnType<typeof setTimeout> | null } | null>(null);

  const mode: PlayerMode = (session?.kind ?? "practice") as PlayerMode;
  const items = session?.items ?? [];
  const item = items[position];
  const limitSec = session ? timeLimitOf(session) : null;
  const timer = useMemo(() => timerView(elapsed, limitSec), [elapsed, limitSec]);
  const result = results[position] ?? null;
  const phase = mode === "practice" && result ? "feedback" : "answering";
  const answer = answers[position] ?? null;

  // The gateway wants seconds spent on the item so far (answer.time_spent_sec, tick.elapsed_sec): cumulative per position.
  const acc = useRef<Record<number, number>>({});
  const itemSeconds = useCallback((pos: number) => (acc.current[pos] ?? 0) + Math.max(0, Math.round((Date.now() - shownAt.current) / 1000)), []);
  const bank = useCallback(
    (pos: number) => {
      acc.current[pos] = itemSeconds(pos);
      shownAt.current = Date.now();
    },
    [itemSeconds],
  );

  // ---- load
  useEffect(() => {
    let alive = true;
    api.get(sessionId).then(
      (s) => {
        if (!alive) return;
        if (isOver(s)) {
          router.replace(summaryRoute(s.id));
          return;
        }
        const a: Record<number, string | null> = {};
        const f: Record<number, boolean> = {};
        const rs: Record<number, FeedbackData> = {};
        const hs: Record<number, string> = {};
        let firstOpen = -1;
        s.items.forEach((it) => {
          const st = s.answers[String(it.position)];
          a[it.position] = currentAnswer(st);
          if (st?.flagged) f[it.position] = true;
          if (s.kind === "practice") {
            if (st?.result) rs[it.position] = toFeedback(st.result, st.answer ?? null);
            if (st?.hint) hs[it.position] = st.hint;
          }
          if (firstOpen < 0 && !st?.checked) firstOpen = it.position;
        });
        const clamp = (n: number) => Math.min(Math.max(0, n), s.items.length - 1);
        const start = s.kind === "practice" && typeof s.position !== "number" ? clamp(firstOpen >= 0 ? firstOpen : s.items.length - 1) : clamp(s.position ?? 0);
        setResults(rs);
        setHints(hs);
        const el = initialElapsed(s, timeLimitOf(s), Date.now());
        clock.current = { base: el, t0: Date.now() };
        shownAt.current = Date.now();
        setAnswers(a);
        setFlags(f);
        setPosition(start);
        setElapsed(el);
        setSession(s);
      },
      (e: unknown) => alive && setError(e),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // ---- saving drafts (mock, diagnostic)
  const flush = useCallback(async () => {
    const p = pendingSave.current;
    if (!p) return;
    if (p.timer) clearTimeout(p.timer);
    pendingSave.current = null;
    try {
      await api.answer(sessionId, { position: p.pos, answer: p.answer, time_spent_sec: itemSeconds(p.pos) });
      if (p.answer) emitTourSignal("diagnostic-answered"); // the first-run tour waits for this (a no-op otherwise)
    } catch (e) {
      if (isApiError(e) && errorCode(e.body) === "expired") expiredRef.current();
      else toast(`Chưa lưu được câu trả lời: ${errorText(e)}`, "error");
    }
  }, [api, itemSeconds, sessionId, toast]);

  const queueSave = useCallback(
    (pos: number, ans: string | null, immediate: boolean) => {
      const prev = pendingSave.current;
      if (prev?.timer) clearTimeout(prev.timer);
      if (prev && prev.pos !== pos) void flush();
      pendingSave.current = { pos, answer: ans, timer: null };
      if (immediate) void flush();
      else pendingSave.current.timer = setTimeout(() => void flush(), 500);
    },
    [flush],
  );

  // ---- answering
  const setAnswer = useCallback(
    (next: string | null) => {
      const s = live.current.session;
      if (!s || (s.kind === "practice" && results[live.current.position])) return;
      const pos = live.current.position;
      setAnswers((a) => ({ ...a, [pos]: next }));
      if (s.kind !== "practice") queueSave(pos, next, s.items[pos]?.type !== "SHORT_ANSWER");
    },
    [queueSave, results],
  );

  const check = useCallback(async () => {
    const s = live.current.session;
    const pos = live.current.position;
    const it = s?.items[pos];
    const ans = live.current.answers[pos] ?? null;
    if (!s || !it || s.kind !== "practice" || results[pos] || busy || !canCheck(it.type, ans, it)) return;
    setBusy(true);
    try {
      const r = await api.answer(sessionId, { position: pos, answer: ans, time_spent_sec: itemSeconds(pos) });
      setResults((m) => ({ ...m, [pos]: toFeedback(r, ans) }));
      if (r.correct != null) {
        setStreak((n) => nextStreak(n, r.correct === true));
        setEffect((e) => (r.correct ? { ...e, bounce: e.bounce + 1 } : { ...e, shake: e.shake + 1 }));
        playCue(r.correct ? "correct" : "wrong");
      }
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  }, [api, busy, itemSeconds, results, sessionId, toast]);

  // ---- navigation and finishing
  const goTo = useCallback(
    async (pos: number) => {
      const s = live.current.session;
      if (!s || pos < 0 || pos >= s.items.length || pos === live.current.position) return;
      await flush();
      bank(live.current.position);
      setPosition(pos);
      setShowSolution(false);
      setDialog((d) => (d === "grid" ? "none" : d));
      void api.tick(sessionId, pos, acc.current[pos] ?? 0).catch(() => {});
    },
    [api, bank, flush, sessionId],
  );

  const finish = useCallback(
    async (auto = false) => {
      if (live.current.finishing) return;
      setFinishing(true);
      setDialog("none");
      try {
        await flush();
        await api.tick(sessionId, live.current.position, itemSeconds(live.current.position)).catch(() => {});
        const report = await api.finish(sessionId);
        cacheReport(sessionId, report);
        playCue("complete");
        if (auto) toast("Hết giờ, bài thi thử đã được nộp tự động.", "info");
        router.replace(summaryRoute(sessionId));
      } catch (e) {
        setFinishing(false);
        toast(errorText(e), "error");
      }
    },
    [api, flush, itemSeconds, router, sessionId, toast],
  );

  useEffect(() => {
    expiredRef.current = () => void finish(true);
  }, [finish]);

  const next = useCallback(() => {
    const s = live.current.session;
    if (!s) return;
    if (live.current.position < s.items.length - 1) void goTo(live.current.position + 1);
    else if (s.kind === "mock") setDialog("finish");
    else void finish();
  }, [finish, goTo]);

  const primary = useCallback(() => {
    const s = live.current.session;
    if (!s) return;
    const pos = live.current.position;
    if (s.kind === "practice") {
      if (results[pos]) next();
      else void check();
    } else next();
  }, [check, next, results]);

  const hint = useCallback(async () => {
    const pos = live.current.position;
    if (mode !== "practice" || results[pos] || hints[pos]) return;
    try {
      const r = await api.hint(sessionId, pos);
      setHints((h) => ({ ...h, [pos]: r.hint }));
    } catch (e) {
      toast(errorText(e), "error");
    }
  }, [api, hints, mode, results, sessionId, toast]);

  const toggleSolution = useCallback(async () => {
    const pos = live.current.position;
    if (!results[pos]) return;
    if (!reveals[pos]) {
      try {
        const r = await api.reveal(sessionId, pos);
        setReveals((m) => ({ ...m, [pos]: r }));
      } catch (e) {
        toast(errorText(e), "error");
        return;
      }
    }
    setShowSolution((v) => !v);
  }, [api, results, reveals, sessionId, toast]);

  const toggleFlag = useCallback(async () => {
    if (mode !== "mock") return;
    const pos = live.current.position;
    const v = !flags[pos];
    setFlags((f) => ({ ...f, [pos]: v }));
    try {
      await api.flag(sessionId, pos, v);
    } catch (e) {
      setFlags((f) => ({ ...f, [pos]: !v }));
      toast(errorText(e), "error");
    }
  }, [api, flags, mode, sessionId, toast]);

  // ---- clock, autosave, auto-submit
  useEffect(() => {
    if (!session) return;
    const id = window.setInterval(() => {
      if (live.current.finishing) return;
      const e = clock.current.base + Math.floor((Date.now() - clock.current.t0) / 1000);
      setElapsed(e);
      live.current.elapsed = e;
      const lim = timeLimitOf(session);
      if (shouldAutoSubmit(session.kind as PlayerMode, e, lim)) {
        void finish(true);
        return;
      }
      if (shouldTick(e, lim)) {
        void api.tick(sessionId, live.current.position, itemSeconds(live.current.position)).then(
          (r) => {
            if ((r as { expired?: boolean }).expired) {
              void finish(true);
              return;
            }
            // The server's clock wins when it disagrees by more than a couple of seconds.
            if (lim != null && typeof r.remaining_sec === "number") {
              const serverElapsed = lim - r.remaining_sec;
              if (Math.abs(serverElapsed - e) > 2) clock.current = { base: serverElapsed, t0: Date.now() };
            }
          },
          () => {},
        );
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [api, finish, itemSeconds, session, sessionId]);

  // Save on leave (route change, tab hidden or closed).
  useEffect(() => {
    if (!session) return;
    const save = () => {
      void flush();
      if (!live.current.finishing) void api.tick(sessionId, live.current.position, itemSeconds(live.current.position)).catch(() => {});
    };
    const onHide = () => document.visibilityState === "hidden" && save();
    window.addEventListener("pagehide", save);
    document.addEventListener("visibilitychange", onHide);
    return () => {
      window.removeEventListener("pagehide", save);
      document.removeEventListener("visibilitychange", onHide);
      save();
    };
  }, [api, flush, itemSeconds, session, sessionId]);

  // ---- skip (practice): a blank answer tells the gateway the item was passed
  const skip = useCallback(async () => {
    const s = live.current.session;
    const pos = live.current.position;
    if (!s || s.kind !== "practice" || results[pos] || busy) return;
    try {
      await api.answer(sessionId, { position: pos, answer: "", time_spent_sec: itemSeconds(pos) });
    } catch (e) {
      toast(errorText(e), "error");
      return;
    }
    next();
  }, [api, busy, itemSeconds, next, results, sessionId, toast]);

  // ---- keyboard
  const onAction = useCallback(
    (a: KeyAction) => {
      const s = live.current.session;
      if (!s) return;
      const it = s.items[live.current.position];
      switch (a.type) {
        case "select": {
          if (!it) return;
          if (it.type === "TRUE_FALSE_GROUP") setAnswer(cycleStatement(live.current.answers[live.current.position] ?? null, a.index));
          else setAnswer(it.options?.[a.index]?.id ?? null);
          return;
        }
        case "primary":
          return primary();
        case "prev":
          return void goTo(live.current.position - 1);
        case "next":
          return next();
        case "hint":
          return void hint();
        case "reveal":
          return void toggleSolution();
        case "skip":
          return void skip();
        case "flag":
          return void toggleFlag();
        case "grid":
          return setDialog((d) => (d === "grid" ? "none" : "grid"));
        case "pause":
          return setDialog("exit");
        case "report":
          return setDialog("report");
      }
    },
    [goTo, hint, next, primary, setAnswer, skip, toggleFlag, toggleSolution],
  );

  useEffect(() => {
    if (!session || !item) return;
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.isComposing) return;
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || !!t?.isContentEditable;
      // A focused control keeps its own Enter/Space, except the answer buttons (Enter there means "Kiểm tra").
      const ownKey = (tag === "BUTTON" || tag === "A") && t?.dataset.pkey !== "option";
      if (ownKey && (e.key === "Enter" || e.key === " ")) return;
      const a = keyAction(e, {
        mode,
        phase,
        itemType: item!.type,
        optionCount: item!.options?.length ?? 0,
        hasHint: item!.has_hint !== false,
        typing,
        modalOpen: dialog !== "none" || !!document.querySelector("dialog[open]"),
      });
      if (!a) return;
      e.preventDefault();
      onAction(a);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dialog, item, mode, onAction, phase, session]);

  return {
    session,
    error,
    mode,
    items,
    item,
    position,
    answer,
    answers,
    flags,
    result,
    results,
    hint: hints[position] ?? null,
    reveal: reveals[position] ?? null,
    showSolution,
    elapsed,
    timer,
    limitSec,
    streak,
    effect,
    busy,
    finishing,
    dialog,
    setDialog,
    phase,
    part: session && item ? partOf(session, position) : null,
    canCheck: item ? canCheck(item.type, answer, item) : false,
    setAnswer,
    check,
    primary,
    next,
    skip,
    goTo,
    finish,
    requestHint: hint,
    toggleSolution,
    toggleFlag,
  };
}
