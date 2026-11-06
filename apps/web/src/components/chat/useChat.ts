"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { getApi, isApiError, type ChatSocket } from "@/lib/api";
import { cardActionFor, type CardEvent } from "@/lib/chat/cards";
import {
  chatReducer,
  historySuggestions,
  historyToMessages,
  initialChatState,
  toChatNotification,
  type ChatMessage,
  type ChatNotification,
  type ChatState,
} from "@/lib/chat/reducer";
import { setActiveConversation } from "@/lib/conversationNav";
import { isDesktopMode, reportUnread } from "@/lib/desktop";
import { emitTourSignal } from "@/lib/tour";
import { localDateStamp, randomId } from "@/lib/format";
import type { ApprovalDecisionValue, ApprovalScope, ChatAttachment, ChatCard } from "@/lib/types";

/** Offline fallback only: the gateway's GET /chat/history is the source of truth. */
const STORE_KEY = "mentor-chat-messages";
/** Same as the gateway's per-learner warm-up throttle; avoids a request on every focus. */
const WARM_INTERVAL_MS = 60_000;

function readLocal(): { date: string; messages: ChatMessage[] } | null {
  try {
    const raw = sessionStorage.getItem(STORE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { date?: string; messages?: ChatMessage[] } | ChatMessage[];
    if (Array.isArray(parsed)) return null; // old format without a date
    return parsed.date && parsed.messages ? { date: parsed.date, messages: parsed.messages } : null;
  } catch {
    return null;
  }
}

/** OS notification while the tab is hidden. Always silent: the mentor never makes a sound. */
function systemNotify(text: string, title = "Mentor", tag = "mentor") {
  try {
    // Desktop pop-up: the shell's Notification shim has no permission behind it; desktop_nudge is the channel there.
    if (isDesktopMode()) return;
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    if (!document.hidden) return;
    new Notification(title, { body: text, tag, silent: true });
  } catch {
    // some browsers forbid the constructor (e.g. Android); ignore
  }
}

export interface ChatApi {
  state: ChatState;
  send: (text: string, attachments: ChatAttachment[]) => boolean;
  decide: (approvalId: string, decision: ApprovalDecisionValue, scope: ApprovalScope) => void;
  /** A learner action on a card: updates it at once and sends `card_action` (plus a short echo bubble). */
  cardAction: (card: ChatCard, event: CardEvent) => void;
  dispatch: React.Dispatch<Parameters<typeof chatReducer>[1]>;
}


/** Owns the chat WebSocket and today's transcript for the lifetime of the component. */
export function useChat(
  opts: {
    onUploadReceived?: (path: string) => void;
    onNotification?: (n: ChatNotification) => void;
    /** A named conversation (`c-<id>`, CONTRACTS 10.5); null/undefined = today's main chat. Remount to switch. */
    conversationId?: string | null;
  } = {},
): ChatApi {
  const conversationId = opts.conversationId ?? null;
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const sock = useRef<ChatSocket | null>(null);
  const onUpload = useRef(opts.onUploadReceived);
  const onNotification = useRef(opts.onNotification);
  useEffect(() => {
    onUpload.current = opts.onUploadReceived;
    onNotification.current = opts.onNotification;
  }, [opts.onUploadReceived, opts.onNotification]);

  // Today's history from the gateway; this tab's saved copy if that fails (offline, gateway down).
  useEffect(() => {
    let alive = true;
    const today = localDateStamp();
    const load = conversationId ? getApi().getConversationHistory(conversationId) : getApi().getChatHistory(today);
    load.then(
        (entries) =>
          alive &&
          dispatch({ type: "history_loaded", messages: historyToMessages(entries, today), suggestions: historySuggestions(entries) }),
        (e: unknown) => {
          if (!alive || isApiError(e, 401)) return;
          // A conversation deleted elsewhere: fall back to the main chat.
          if (conversationId && isApiError(e, 404)) {
            setActiveConversation(null);
            return;
          }
          const local = conversationId ? null : readLocal();
          dispatch({ type: "restore", messages: local && local.date === today ? local.messages : [] });
        },
      );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const s = getApi().connectChat({
      onMessage: (msg) => {
        if (msg.type === "upload_received") {
          onUpload.current?.(msg.path);
          return;
        }
        const id = randomId("m_");
        dispatch({ type: "server", msg, id, now: new Date().toISOString() });
        if (msg.type === "notification") {
          const n = toChatNotification(msg, id);
          systemNotify(n.body || n.text, n.title || "Mentor", n.serverId ? `mentor-${n.serverId}` : "mentor");
          onNotification.current?.(n);
        }
        if (msg.type === "approval_request") systemNotify(`Cần bạn duyệt: ${msg.approval.summary}`);
        // Desktop pop-up: badge on the bubble when this arrives while the panel is collapsed.
        if (msg.type === "notification" || msg.type === "approval_request" || msg.type === "turn_done") reportUnread(msg.type);
      },
      onConnectionChange: (c) => dispatch({ type: "connection", state: c }),
    });
    sock.current = s;
    return () => {
      s.close();
      sock.current = null;
    };
  }, []);

  // Pre-warm the sandbox when the learner comes back to the chat or the pop-up, so the first message skips the
  // cold start. Opening the socket already warms it (gateway side), hence `last` starts now. A sandbox that is
  // already awake sends no sandbox_status, so this causes no status flicker.
  useEffect(() => {
    let last = Date.now();
    const warm = () => {
      if (document.visibilityState === "hidden" || Date.now() - last < WARM_INTERVAL_MS) return;
      last = Date.now();
      getApi()
        .warmSandbox()
        .catch(() => {}); // best effort: the turn wakes the sandbox anyway
    };
    window.addEventListener("focus", warm);
    document.addEventListener("visibilitychange", warm);
    return () => {
      window.removeEventListener("focus", warm);
      document.removeEventListener("visibilitychange", warm);
    };
  }, []);

  // Keep an offline copy of today's transcript for this tab.
  useEffect(() => {
    if (state.historySource === "loading" || conversationId) return;
    try {
      sessionStorage.setItem(STORE_KEY, JSON.stringify({ date: localDateStamp(), messages: state.messages.slice(-200) }));
    } catch {
      // ignore
    }
  }, [state.messages, state.historySource, conversationId]);

  // Expire approval cards client-side.
  const hasPending = state.approvals.some((a) => a.status === "pending");
  const approvalsRef = useRef(state.approvals);
  useEffect(() => {
    approvalsRef.current = state.approvals;
  }, [state.approvals]);
  useEffect(() => {
    if (!hasPending) return;
    const t = setInterval(() => {
      const now = Date.now();
      for (const a of approvalsRef.current) {
        if (a.status === "pending" && Date.parse(a.approval.expires_at) <= now) {
          dispatch({ type: "approval_expired", approvalId: a.approval.approval_id });
        }
      }
    }, 5000);
    return () => clearInterval(t);
  }, [hasPending]);

  const send = useCallback((text: string, attachments: ChatAttachment[]) => {
    const clientMsgId = randomId("c_");
    dispatch({ type: "send", clientMsgId, text, attachments, now: new Date().toISOString() });
    const ok = sock.current?.send({
        type: "user_message",
        client_msg_id: clientMsgId,
        text,
        attachments,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      }) ?? false;
    if (!ok) dispatch({ type: "send_failed", clientMsgId, error: "Chưa kết nối được với mentor. Tin nhắn chưa được gửi." });
    else emitTourSignal("message-sent"); // the first-run tour waits for this
    return ok;
  }, [conversationId]);

  const decide = useCallback((approvalId: string, decision: ApprovalDecisionValue, scope: ApprovalScope) => {
    const ok = sock.current?.send({ type: "approval_decision", approval_id: approvalId, decision, scope }) ?? false;
    if (ok) dispatch({ type: "approval_decided", approvalId, decision, scope });
    else
      dispatch({
        type: "server",
        msg: { type: "error", error: "Chưa gửi được quyết định: mất kết nối." },
        id: randomId("m_"),
        now: new Date().toISOString(),
      });
  }, []);

  const cardAction = useCallback((card: ChatCard, event: CardEvent) => {
    const a = cardActionFor(card, event);
    if (!a) {
      dispatch({ type: "card_event", cardId: card.id, event });
      return;
    }
    // The card answers at once; the gateway's card_echo draws the learner's bubble and turn_done echoes the id.
    const clientMsgId = randomId("c_");
    dispatch({ type: "card_send", cardId: card.id, clientMsgId, event });
    const ok =
      sock.current?.send({ type: "card_action", card_id: card.id, action: a.action, value: a.value, client_msg_id: clientMsgId, ...(conversationId ? { conversation_id: conversationId } : {}) }) ?? false;
    if (!ok) dispatch({ type: "card_send_failed", clientMsgId, error: "Chưa gửi được lựa chọn: mất kết nối với mentor." });
  }, [conversationId]);

  return { state, send, decide, cardAction, dispatch };
}
