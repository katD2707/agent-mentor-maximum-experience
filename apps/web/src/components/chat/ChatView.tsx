"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import { getApi } from "@/lib/api";
import { gradeFlashcard, type CardEvent } from "@/lib/chat/cards";
import { crisisFlags, currentTurnCrisis } from "@/lib/chat/crisis";
import { guessMime, isTurnInFlight, type ChatNotification, type ChatState } from "@/lib/chat/reducer";
import { queueChatIntent, useChatIntent } from "@/lib/chatIntent";
import {
  clearMessageFocus,
  FOCUS_MESSAGE_EVENT,
  OPEN_CONVERSATIONS_EVENT,
  OPEN_SEARCH_EVENT,
  peekMessageFocus,
  scrollToMessage,
  setActiveConversation,
  useActiveConversation,
  type MessageFocus,
} from "@/lib/conversationNav";
import { parseSlash, slashHintsFor } from "@/lib/slashCommands";
import { fold } from "@/lib/text";
import {
  desktopMascotFor,
  forwardNudge,
  inTauri,
  listenDesktop,
  NUDGE_ACTION_EVENT,
  reportMascot,
  type DesktopMascot,
} from "@/lib/desktop";
import { useAsync } from "@/lib/hooks";
import { deriveMascotState, ONE_SHOT_MS, sanitizeMascot } from "@/lib/mascot";
import { FADE, SPRING, useReducedMotion } from "@/lib/motion";
import { performNudgeAction } from "@/lib/nudges";
import { isQuietNow } from "@/lib/quietHours";
import type { ChatCard, MascotState } from "@/lib/types";
import { Icon } from "../Icon";
import { Mascot } from "../Mascot";
import { NotificationBell } from "../notifications/NotificationBell";
import { showNudgeToast } from "../notifications/NudgeToast";
import { NextSteps } from "../progress/NextSteps";
import { useMe } from "../session";
import { useToast } from "../toast";
import { errorText, Loading } from "../ui";
import { ApprovalCard } from "./ApprovalCard";
import { ConversationsDialog, createConversation, subjectTag } from "./ConversationsDialog";
import { cardAnnouncement } from "./ChatCards";
import { HistoryDialog } from "./HistoryDialog";
import { MessageView } from "./Message";
import { MobileUploadDialog } from "./MobileUploadDialog";
import { useChat } from "./useChat";
import { captureScreen, useUploads } from "./useUploads";

function statusInfo(state: ChatState): { key: string; label: string } {
  if (state.connection === "connecting") return { key: "waking", label: "Đang kết nối…" };
  if (state.connection === "closed") return { key: "offline", label: "Mất kết nối" };
  switch (state.sandbox) {
    case "sleeping":
      return { key: "sleeping", label: "Mentor đang nghỉ" };
    case "waking":
      return { key: "waking", label: "Mentor đang thức dậy…" };
    case "busy":
      return { key: "busy", label: "Mentor đang làm việc…" };
    case "ready":
      return { key: "ready", label: "Sẵn sàng" };
    default:
      return { key: "waking", label: "Đang chuẩn bị…" };
  }
}

/** `?notification=<id>` from a push click (Built N). */
function notificationFromUrl(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("notification");
}

/** Transient playful mascot state: celebrate → happy → back to the derived state. */
function useOneShot() {
  const [oneShot, setOneShot] = useState<MascotState | null>(null);
  const timer = useRef<number | null>(null);
  const clear = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };
  const play = useCallback((s: MascotState) => {
    clear();
    setOneShot(s);
    // Safety net when no mascot-done arrives (element missing, tab hidden).
    const ms = (ONE_SHOT_MS[s] ?? 3000) + 1500;
    timer.current = window.setTimeout(() => setOneShot(null), ms);
  }, []);
  const done = useCallback(
    (s: MascotState, interrupted: boolean) => {
      if (interrupted) return; // something more important took over (e.g. a calm turn)
      if (s === "celebrate") play("happy");
      else {
        clear();
        setOneShot(null);
      }
    },
    [play],
  );
  useEffect(() => clear, []);
  return { oneShot, play, done };
}

/** Chat for the active conversation (main daily chat, or a named one from CONTRACTS 10.5). Remounts on switch. */
export function ChatView({ compact = false, desktopNudges = false }: { compact?: boolean; desktopNudges?: boolean }) {
  const active = useActiveConversation();
  return <ChatInner key={active ?? "main"} compact={compact} desktopNudges={desktopNudges} conversationId={active} />;
}

function ChatInner({
  compact = false,
  desktopNudges = false,
  conversationId,
}: {
  compact?: boolean;
  desktopNudges?: boolean;
  conversationId: string | null;
}) {
  const router = useRouter();
  const me = useMe();
  const toast = useToast();
  const reduce = useReducedMotion();
  const uploads = useUploads();
  const { addExisting } = uploads;
  const settings = useAsync(() => getApi().getSettings(), []);
  const quietRange = settings.data?.quiet_hours ?? null;
  const quietRef = useRef(quietRange);
  useEffect(() => {
    quietRef.current = quietRange;
  }, [quietRange]);

  const onUploadReceived = useCallback(
    (path: string) => {
      addExisting({ path, mime_type: guessMime(path) });
      toast(`Đã nhận ${path.split("/").pop()} từ điện thoại và đính kèm vào tin nhắn.`, "ok");
    },
    [addExisting, toast],
  );

  const [bellOpen, setBellOpen] = useState(() => notificationFromUrl() !== null);

  // Nudge actions from the toast, the notification centre and the desktop balloon all land here.
  const [busyNudge, setBusyNudge] = useState<string | null>(null);
  const dispatchRef = useRef<((a: Parameters<ReturnType<typeof useChat>["dispatch"]>[0]) => void) | null>(null);
  const runNudgeAction = useCallback(
    async (n: ChatNotification, action: string) => {
      setBusyNudge(n.id);
      try {
        const out = await performNudgeAction(n.serverId, action, { fallbackPrefill: n.prefill, actions: n.actions });
        dispatchRef.current?.({ type: "notification_handled", id: n.id, action });
        if (action === "open") queueChatIntent({ kind: "prefill", text: out.prefill ?? "" });
        else if (out.message) toast(out.message, "ok");
      } catch (e) {
        toast(errorText(e), "error");
      } finally {
        setBusyNudge(null);
      }
    },
    [toast],
  );

  const onNotification = useCallback(
    (n: ChatNotification) => {
      const pop = () => {
        // Quiet hours: nothing pops; the notification waits in the centre. No sound, ever.
        if (!isQuietNow(quietRef.current, Date.now())) showNudgeToast(n, (x, a) => void runNudgeAction(x, a));
      };
      if (desktopNudges && inTauri()) {
        // The shell shows the balloon or a native toast; only when the panel is open does the page show it inline.
        void forwardNudge({
          id: n.serverId ?? n.id,
          kind: n.kind ?? "nudge",
          title: n.title || "Mentor",
          body: n.body || n.text,
          actions: n.actions ?? [],
          mascot: sanitizeMascot(n.mascot),
        }).then((route) => {
          if (route === "panel" || route === undefined) pop();
        });
        return;
      }
      pop();
    },
    [desktopNudges, runNudgeAction],
  );

  const { state, send, decide, cardAction, dispatch } = useChat({ onUploadReceived, onNotification, conversationId });
  useEffect(() => {
    dispatchRef.current = dispatch;
  }, [dispatch]);

  const notificationsRef = useRef(state.notifications);
  useEffect(() => {
    notificationsRef.current = state.notifications;
  }, [state.notifications]);

  // The centre starts from GET /notifications (Built N), so nudges that arrived while the chat was closed are there.
  // A push click lands on /chat?notification=<id> (or messages an open tab): open the bell on it.
  const [focusNotification, setFocusNotification] = useState<string | null>(notificationFromUrl);
  useEffect(() => {
    let alive = true;
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("notification");
    getApi()
      .getNotifications(30)
      .then(
        (items) => alive && dispatch({ type: "notifications_loaded", items }),
        () => {}, // older gateway: the centre fills from the socket only
      );
    if (fromUrl) {
      // focusNotification and bellOpen already started from it; only tidy the URL.
      params.delete("notification");
      const rest = params.toString();
      window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : "") + window.location.hash);
    }
    const onSw = (e: MessageEvent) => {
      const d = e.data as { type?: string; id?: string | number } | null;
      if (d?.type !== "mentor:notification" || d.id === undefined) return;
      setFocusNotification(String(d.id));
      setBellOpen(true);
      void getApi()
        .getNotifications(30)
        .then((items) => dispatch({ type: "notifications_loaded", items }), () => {});
    };
    navigator.serviceWorker?.addEventListener("message", onSw);
    return () => {
      alive = false;
      navigator.serviceWorker?.removeEventListener("message", onSw);
    };
  }, [dispatch]);

  // Desktop pop-up: the shell reports balloon clicks as mentor://nudge-action {id, action}.
  useEffect(() => {
    if (!desktopNudges || !inTauri()) return;
    let off: (() => void) | null = null;
    let alive = true;
    void listenDesktop<{ id?: string; action?: string }>(NUDGE_ACTION_EVENT, (p) => {
      if (!p?.id || !p.action) return;
      const n = notificationsRef.current.find((x) => x.serverId === p.id || x.id === p.id);
      if (n) void runNudgeAction(n, p.action);
      else if (p.action !== "open") void performNudgeAction(p.id, p.action).catch(() => {});
    }).then((fn) => {
      if (alive) off = fn;
      else fn();
    });
    return () => {
      alive = false;
      off?.();
    };
  }, [desktopNudges, runNudgeAction]);

  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyFocus, setHistoryFocus] = useState<MessageFocus | null>(null);
  const [convOpen, setConvOpen] = useState(false);

  // Search hits: an earlier day of the main chat opens the history dialog on that day; anything else scrolls here.
  // Checked when the hit is picked (event) and right after mount (picked on another page, or the chat remounted
  // for a conversation switch).
  useEffect(() => {
    const onFocus = () => {
      const f = peekMessageFocus();
      if (!f) return;
      if (f.date) {
        clearMessageFocus();
        setHistoryFocus(f);
        setHistoryOpen(true);
      } else if (scrollToMessage(document, f.ts)) {
        clearMessageFocus();
      }
    };
    window.addEventListener(FOCUS_MESSAGE_EVENT, onFocus);
    const t = window.setTimeout(onFocus, 0);
    return () => {
      window.removeEventListener(FOCUS_MESSAGE_EVENT, onFocus);
      window.clearTimeout(t);
    };
  }, []);
  // Other parts of the UI (sidebar, shortcuts) can ask for the conversations list.
  useEffect(() => {
    const open = () => setConvOpen(true);
    window.addEventListener(OPEN_CONVERSATIONS_EVENT, open);
    return () => window.removeEventListener(OPEN_CONVERSATIONS_EVENT, open);
  }, []);
  // History may still be loading when the hit is picked: retry the scroll as messages arrive.
  useEffect(() => {
    const f = peekMessageFocus();
    if (f && !f.date && scrollToMessage(document, f.ts)) clearMessageFocus();
  }, [state.messages.length]);
  const [convTitle, setConvTitle] = useState<{ title: string; subject: string | null } | null>(null);
  const [hintIdx, setHintIdx] = useState(0);
  const [hintsOff, setHintsOff] = useState(false);

  // Title and subject tag of the open named conversation, for the header.
  useEffect(() => {
    if (!conversationId) return;
    let alive = true;
    getApi()
      .listConversations("all")
      .then(
        (list) => {
          const c = list.find((x) => x.id === conversationId);
          if (alive && c) setConvTitle({ title: c.title, subject: c.subject ?? null });
        },
        () => {},
      );
    return () => {
      alive = false;
    };
  }, [conversationId, convOpen]);

  // Ctrl+N: a new conversation (the browser may keep Ctrl+N for itself; the header button always works).
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "n") {
        e.preventDefault();
        createConversation().then(
          (c) => setActiveConversation(c.id),
          (err) => toast(errorText(err), "error"),
        );
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toast]);
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [welcomeMascot, setWelcomeMascot] = useState<MascotState>("wave");
  const dragDepth = useRef(0);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const stick = useRef(true);
  const { oneShot, play: playMascot, done: mascotDone } = useOneShot();

  const resizeInput = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(200, el.scrollHeight)}px`;
  };

  // From the setup guide or a nudge: a prompt to put in the box, or the phone-upload QR.
  useChatIntent((intent) => {
    if (intent.kind === "mobile-upload") {
      setMobileOpen(true);
      return;
    }
    if (intent.text) setText(intent.text);
    requestAnimationFrame(() => {
      resizeInput();
      inputRef.current?.focus();
    });
  });

  const inFlight = isTurnInFlight(state);
  const status = statusInfo(state);
  const pendingApprovals = state.approvals.filter((a) => a.status === "pending").length;
  const canSend = state.connection === "open" && !uploads.uploading && (text.trim().length > 0 || uploads.ready.length > 0);

  // ---- mascot ----
  const flags = useMemo(() => crisisFlags(state.messages), [state.messages]);
  const crisis = useMemo(() => currentTurnCrisis(state.messages, state.approvals), [state.messages, state.approvals]);
  let lastMentor = -1;
  for (let i = state.messages.length - 1; i >= 0; i--) {
    if (state.messages[i].role === "mentor") {
      lastMentor = i;
      break;
    }
  }
  const openReply = state.messages.findLast((m) => m.role === "mentor" && m.status === "streaming");
  const mascotState = deriveMascotState({
    connection: state.connection,
    sandbox: state.sandbox,
    toolsRunning: !!openReply?.tools.some((t) => t.status === "running"),
    streaming: !!openReply?.text,
    inFlight,
    composing: text.trim().length > 0,
    crisis,
    oneShot,
  });

  // Quiet hours are re-checked each minute (centre note, desktop bubble).
  // Desktop bubble: tell the shell what the chat is doing, sent only on change.
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setClock(Date.now()), 60_000);
    return () => window.clearInterval(t);
  }, []);
  const quietNow = isQuietNow(quietRange, clock);
  const desktopMascot = desktopMascotFor({
    crisis,
    quiet: quietNow,
    sleeping: state.sandbox === "sleeping",
    inFlight,
    celebrating: oneShot === "celebrate",
  });
  const lastDesktopMascot = useRef<DesktopMascot | null>(null);
  useEffect(() => {
    if (!desktopNudges || !inTauri() || lastDesktopMascot.current === desktopMascot) return;
    lastDesktopMascot.current = desktopMascot;
    reportMascot(desktopMascot);
  }, [desktopNudges, desktopMascot]);

  const onCardEvent = useCallback(
    (card: ChatCard, ev: CardEvent) => {
      cardAction(card, ev);
      if (crisis) return;
      if (ev.type === "focus_done") {
        playMascot("happy");
      }
      if (ev.type === "flash_choose" && card.kind === "flashcard" && gradeFlashcard(card, ev.value) === true) playMascot("happy");
    },
    [cardAction, crisis, playMascot],
  );
  const onCelebrate = useCallback(() => {
    if (crisis) return;
    playMascot("celebrate");
  }, [crisis, playMascot]);

  // Keep the log pinned to the bottom unless the user scrolled up.
  useLayoutEffect(() => {
    const el = logRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [state.messages, state.suggestions]);

  // Announce completed replies, new cards and approvals to screen readers (not every delta).
  const lastDone = state.messages.findLast((m) => m.role === "mentor" && m.status === "done");
  const announce =
    pendingApprovals > 0
      ? `Có ${pendingApprovals} yêu cầu cần bạn duyệt.`
      : lastDone?.card && lastDone.live
        ? cardAnnouncement(lastDone.card)
        : lastDone && !inFlight
          ? `Mentor đã trả lời: ${lastDone.text.slice(0, 200)}`
          : "";

  useEffect(() => {
    if (state.error) toast(state.error, "error");
  }, [state.error, toast]);

  function sendText(t: string) {
    const ok = send(t, uploads.ready);
    if (ok) {
      setText("");
      uploads.clear();
      stick.current = true;
      requestAnimationFrame(resizeInput);
    }
    inputRef.current?.focus();
  }

  const slash = parseSlash(text);
  const hints = hintsOff ? [] : slashHintsFor(text);
  const hintAt = hints.length > 0 ? Math.min(hintIdx, hints.length - 1) : 0;

  function openRoute(href: string) {
    // The pop-up is too small for practice screens: open the full app there.
    if (compact) window.open(href, "_blank");
    else router.push(href);
  }

  function completeHint(i: number) {
    const h = hints[i];
    if (!h) return;
    setText(h.command + " ");
    setHintIdx(0);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function submit() {
    const t = text.trim();
    if (slash.kind === "route") {
      setText("");
      requestAnimationFrame(resizeInput);
      openRoute(slash.href);
      return;
    }
    if (slash.kind === "error") {
      toast(slash.message, "error");
      return;
    }
    if (!canSend) return;
    sendText(t);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (hints.length > 0 && !e.nativeEvent.isComposing) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setHintIdx((hintAt + (e.key === "ArrowDown" ? 1 : hints.length - 1)) % hints.length);
        return;
      }
      if (e.key === "Tab" && !e.shiftKey) {
        e.preventDefault();
        completeHint(hintAt);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setHintsOff(true);
        return;
      }
      if (e.key === "Enter" && !e.shiftKey && fold(text) !== fold(hints[hintAt].command)) {
        e.preventDefault();
        completeHint(hintAt);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  function onPaste(e: ClipboardEvent) {
    const files = Array.from(e.clipboardData.files);
    if (files.length > 0) {
      e.preventDefault();
      uploads.addFiles(files);
    }
  }

  function hasFiles(e: DragEvent) {
    return Array.from(e.dataTransfer.types).includes("Files");
  }

  async function screenshot() {
    try {
      uploads.addFiles([await captureScreen()]);
    } catch (e) {
      if (e instanceof DOMException && e.name === "NotAllowedError") return; // user cancelled
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  }

  const starters =
    me.role === "ncs"
      ? ["Chuẩn bị agenda họp GVHD tuần này", "Mình vừa đọc xong một paper, giúp mình phản biện", "Đặt lịch viết luận án sáng thứ Sáu"]
      : ["Hôm nay mình nên ôn gì?", "Giải thích lại cách xét dấu tam thức bậc hai", "Nhắc em ôn bài tối mai"];

  const approvalCards = (
    <AnimatePresence initial={false}>
      {state.approvals
        .filter((c) => c.status === "pending")
        .map((c) => (
        <motion.div
          key={c.approval.approval_id}
          layout={reduce ? false : "position"}
          initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={reduce ? { opacity: 0, transition: FADE } : { opacity: 0, x: 12, transition: { duration: 0.16 } }}
          transition={reduce ? FADE : SPRING}
        >
          <ApprovalCard card={c} onDecide={decide} onDismiss={(id) => dispatch({ type: "dismiss_approval", approvalId: id })} />
        </motion.div>
        ))}
    </AnimatePresence>
  );

  // Chips belong to the newest transcript item only (Built H): anything newer hides them.
  const newest = state.messages[state.messages.length - 1];
  const showSuggestions =
    !inFlight &&
    state.connection === "open" &&
    state.suggestions.length > 0 &&
    !crisis &&
    !!newest &&
    newest.id === state.suggestionsAnchor;

  return (
    <div
      className={compact ? "chat compact" : "chat"}
      onDragEnter={(e) => {
        if (!hasFiles(e)) return;
        dragDepth.current++;
        setDragging(true);
      }}
      onDragOver={(e) => {
        if (hasFiles(e)) e.preventDefault();
      }}
      onDragLeave={() => {
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragging(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        uploads.addFiles(Array.from(e.dataTransfer.files));
      }}
      onPaste={onPaste}
    >
      <header className="chat-head">
        <Mascot state={mascotState} size={compact ? 28 : 34} label={`Mentor (${mascotLabel(mascotState)})`} onDone={mascotDone} />
        {compact ? (
          <strong>Mentor</strong>
        ) : (
          <h1 style={{ fontSize: "1.05rem", margin: 0 }}>Trò chuyện</h1>
        )}
        <span className="status-pill" data-state={status.key} role="status" aria-live="polite">
          {(status.key === "waking" || status.key === "busy") && <span className="spinner" aria-hidden="true" />}
          {status.label}
        </span>
        <span className="spacer" />
        <button
          type="button"
          className="btn btn-ghost btn-sm conv-switch"
          onClick={() => setConvOpen(true)}
          title="Các cuộc trò chuyện"
          aria-label={`Các cuộc trò chuyện. Đang mở: ${conversationId ? (convTitle?.title ?? "cuộc trò chuyện riêng") : "trò chuyện hằng ngày"}`}
        >
          <Icon name="chat" size={16} />
          <span className="conv-switch-name">{conversationId ? (convTitle?.title ?? "Cuộc trò chuyện") : "Hằng ngày"}</span>
          {conversationId && subjectTag(convTitle?.subject) && <span className="badge">{subjectTag(convTitle?.subject)}</span>}
        </button>
        {!compact && (
          <button
            type="button"
            className="btn btn-ghost btn-icon btn-sm"
            onClick={() => window.dispatchEvent(new Event(OPEN_SEARCH_EVENT))}
            title="Tìm trong các cuộc trò chuyện (Ctrl+K)"
            aria-label="Tìm trong các cuộc trò chuyện (Ctrl+K)"
          >
            <Icon name="research" size={16} />
          </button>
        )}
        {!compact && !conversationId && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setHistoryOpen(true)} title="Xem trò chuyện các ngày trước">
            <Icon name="history" size={16} />
            <span>Hôm trước</span>
          </button>
        )}
        <NotificationBell
          open={bellOpen}
          onOpenChange={setBellOpen}
          notifications={state.notifications}
          quiet={quietNow}
          quietRange={quietRange}
          busyId={busyNudge}
          focusId={focusNotification}
          onAction={(n, act) => void runNudgeAction(n, act)}
          onDismiss={(id) => dispatch({ type: "dismiss_notification", id })}
          onMarkRead={() => dispatch({ type: "notifications_read" })}
        />
        {compact && (
          <Link href="/chat" className="btn btn-ghost btn-icon btn-sm" target="_blank" aria-label="Mở trang đầy đủ" title="Mở trang đầy đủ">
            <Icon name="external" size={16} />
          </Link>
        )}
      </header>

      <div
        className="chat-log"
        ref={logRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
      >
        {dragging && <div className="drop-overlay">Thả tệp vào đây để gửi cho mentor</div>}
        <div className="chat-log-inner" role="log" aria-label="Cuộc trò chuyện" aria-busy={inFlight} aria-live="off">
          {state.historySource === "local" && (
            <p className="alert alert-warn" style={{ fontSize: "0.88rem" }}>
              Không tải được lịch sử từ máy chủ. Đang hiện bản lưu tạm trên trình duyệt này.
            </p>
          )}
          {state.historySource === "loading" && state.messages.length === 0 ? (
            <Loading label="Đang tải trò chuyện hôm nay…" />
          ) : state.messages.length === 0 ? (
            <div className="chat-welcome">
              <Mascot state={welcomeMascot} size={compact ? 56 : 72} onDone={() => setWelcomeMascot("idle")} />
              <p className="chat-welcome-title">Chào {me.display_name}! Hôm nay bạn muốn bắt đầu từ đâu?</p>
              <p>Bạn có thể kéo thả, dán ảnh (Ctrl+V) hoặc chụp màn hình để gửi đề bài.</p>
              <div className="suggestions">
                {starters.map((s, i) => (
                  <motion.button
                    key={s}
                    type="button"
                    className="btn btn-sm"
                    onClick={() => {
                      setText(s);
                      requestAnimationFrame(() => {
                        resizeInput();
                        inputRef.current?.focus();
                      });
                    }}
                    initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={reduce ? FADE : { ...SPRING, delay: 0.25 + i * 0.05 }}
                  >
                    {s}
                  </motion.button>
                ))}
              </div>
              {me.role === "thpt" && !compact && !crisis && (
                <div className="chat-welcome-next">
                  <NextSteps limit={1} compact />
                </div>
              )}
            </div>
          ) : (
            state.messages.map((m, i) => (
              <MessageView
                key={m.id}
                m={m}
                avatar={i === lastMentor ? mascotState : null}
                crisis={flags[i]}
                busy={inFlight}
                onCardEvent={onCardEvent}
                onCelebrate={onCelebrate}
              />
            ))
          )}
          <AnimatePresence>
            {showSuggestions && (
              <motion.div
                key={state.suggestions.map((s) => s.text).join("|")}
                className="quick-replies"
                role="group"
                aria-label="Gợi ý trả lời nhanh"
                exit={{ opacity: 0, transition: { duration: 0.12 } }}
              >
                {state.suggestions.map((s, i) => (
                  <motion.button
                    key={s.text}
                    type="button"
                    className="quick-reply"
                    title={s.text}
                    onClick={() => sendText(s.text)}
                    disabled={state.connection !== "open"}
                    initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={reduce ? FADE : { ...SPRING, delay: 0.12 + i * 0.06 }}
                  >
                    {s.label}
                  </motion.button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <div className="sr-only" aria-live="polite">
          {announce}
        </div>
      </div>

      <div className="composer">
        <div className="composer-inner">
          {pendingApprovals > 0 && <div className="approvals-inline">{approvalCards}</div>}
          {uploads.items.length > 0 && (
            <ul className="chips" aria-label="Tệp đính kèm" style={{ listStyle: "none", padding: 0, margin: "0 0 6px" }}>
              {uploads.items.map((u) => (
                <li key={u.id} className="chip" data-state={u.status}>
                  {u.status === "uploading" ? <span className="spinner" aria-hidden="true" /> : <Icon name="file" size={14} />}
                  <span className="name" title={u.error ?? u.result?.path ?? u.name}>
                    {u.name}
                  </span>
                  {u.status === "uploading" && <span className="sr-only">đang tải lên</span>}
                  {u.status === "error" && <span style={{ fontSize: "0.78rem" }}>{u.error}</span>}
                  <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => uploads.remove(u.id)} aria-label={`Bỏ ${u.name}`}>
                    <Icon name="close" size={12} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {hints.length > 0 && (
            <ul className="slash-hints" id="slash-hints" role="listbox" aria-label="Lệnh gợi ý">
              {hints.map((h, i) => (
                <li key={h.command} role="option" aria-selected={i === hintAt}>
                  <button
                    type="button"
                    tabIndex={-1}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => completeHint(i)}
                    data-active={i === hintAt}
                  >
                    <code>{h.usage}</code>
                    <span className="hint">{h.description}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {slash.kind === "route" && (
            <p className="hint slash-note" role="status">
              Nhấn Enter: {slash.label}
            </p>
          )}
          {slash.kind === "error" && (
            <p className="hint slash-note" role="status">
              {slash.message}
            </p>
          )}
          <div className="composer-box" data-tour="composer">
            <label htmlFor="chat-input" className="sr-only">
              Tin nhắn cho mentor
            </label>
            <textarea
              id="chat-input"
              ref={inputRef}
              rows={1}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setHintsOff(false);
                resizeInput();
              }}
              onKeyDown={onKeyDown}
              placeholder={
                state.connection !== "open"
                  ? "Đang kết nối với mentor…"
                  : compact
                    ? "Nhắn cho mentor…"
                    : "Nhắn cho mentor… (Enter để gửi, Shift+Enter xuống dòng)"
              }
              aria-describedby="composer-hint"
              aria-controls={hints.length > 0 ? "slash-hints" : undefined}
            />
            <button type="button" className="btn btn-primary btn-icon" onClick={submit} disabled={!canSend && slash.kind !== "route"} aria-label="Gửi">
              <Icon name="send" />
            </button>
          </div>
          <div className="composer-tools">
            <input
              ref={fileRef}
              type="file"
              multiple
              hidden
              accept="image/*,application/pdf,.docx,.md,.txt"
              onChange={(e) => {
                uploads.addFiles(Array.from(e.target.files ?? []));
                e.target.value = "";
              }}
            />
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => fileRef.current?.click()}>
              <Icon name="attach" size={16} /> Đính kèm
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void screenshot()}>
              <Icon name="camera" size={16} /> Chụp màn hình
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMobileOpen(true)}>
              <Icon name="phone" size={16} /> Từ điện thoại
            </button>
            <span id="composer-hint" className="hint" style={{ marginLeft: "auto" }}>
              {inFlight ? "Mentor đang trả lời…" : "Kéo thả hoặc dán ảnh để gửi kèm"}
            </span>
          </div>
        </div>
      </div>

      <ConversationsDialog open={convOpen} onClose={() => setConvOpen(false)} activeId={conversationId} onSelect={setActiveConversation} />
      <HistoryDialog
        open={historyOpen}
        focus={historyFocus}
        onClose={() => {
          setHistoryOpen(false);
          setHistoryFocus(null);
        }}
      />
      <MobileUploadDialog
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        onAttach={(a) => {
          uploads.addExisting(a);
          toast(`Đã đính kèm ${a.path}`, "ok");
        }}
      />
    </div>
  );
}

const MASCOT_LABELS: Record<MascotState, string> = {
  idle: "đang chờ",
  listening: "đang lắng nghe",
  thinking: "đang suy nghĩ",
  talking: "đang trả lời",
  happy: "vui",
  celebrate: "đang ăn mừng",
  sleepy: "đang nghỉ",
  calm: "bình tĩnh, ở bên bạn",
  wave: "chào bạn",
};

function mascotLabel(s: MascotState): string {
  return MASCOT_LABELS[s];
}
