import { mascotForKind, sanitizeMascot } from "../mascot";
import type {
  AppNotification,
  ApprovalDecisionValue,
  ApprovalRequest,
  ApprovalScope,
  ChatAttachment,
  ChatCard,
  ChatHistoryEntry,
  MascotState,
  NotificationAction,
  NotificationKind,
  NotificationPayload,
  SandboxState,
  ServerMessage,
  SuggestionItem,
} from "../types";
import type { ConnectionState } from "../api/client";
import { cardReducer, eventFromCardAction, mergeCardUpdate, type CardEvent, type CardUiState } from "./cards";

export interface ToolActivity {
  tool: string;
  summary: string;
  status: "running" | "done";
}

export interface ChatMessage {
  id: string;
  role: "user" | "mentor";
  text: string;
  attachments: ChatAttachment[];
  /** user: sending → done | error. mentor: streaming → done | error. */
  status: "sending" | "streaming" | "done" | "error";
  /** For user messages and the mentor reply they produced. */
  clientMsgId?: string;
  tools: ToolActivity[];
  createdAt: string;
  /** A card (CONTRACTS 9) instead of text. */
  card?: ChatCard;
  cardUi?: CardUiState;
  /**
   * Arrived on the socket in this tab (may animate, may celebrate once). False/absent for history and the
   * offline copy, which replay statically.
   */
  live?: boolean;
}

export interface ApprovalCardState {
  approval: ApprovalRequest;
  status: "pending" | "approved" | "denied" | "expired";
  scope?: ApprovalScope;
}

export interface ChatNotification {
  id: string;
  /** Gateway notification id (for POST /notifications/{id}/action); absent on older gateways. */
  serverId?: string;
  text: string;
  createdAt: string;
  read: boolean;
  kind?: NotificationKind;
  title?: string;
  body?: string;
  actions?: NotificationAction[];
  mascot?: MascotState;
  prefill?: string | null;
  /** The action the learner took (buttons hide after one). */
  handled?: string;
  /** How many other notifications were bundled into this one (`bundled_ids`, normal proactivity). */
  bundled?: number;
}

export interface ChatState {
  connection: ConnectionState;
  sandbox: SandboxState | null;
  messages: ChatMessage[];
  /** client_msg_id of the turn being processed, if any. */
  activeTurn: string | null;
  /** Queued turns not yet acknowledged with turn_done (oldest first). */
  queuedTurns: string[];
  approvals: ApprovalCardState[];
  notifications: ChatNotification[];
  /** Quick replies for the last finished turn (cleared when the learner sends). */
  suggestions: SuggestionItem[];
  /** Id of the newest message when the suggestions came: chips show only while it is still the newest. */
  suggestionsAnchor: string | null;
  /** Card clicks waiting for their turn: client_msg_id -> card and its state before the click (for a refusal). */
  pendingCards: Record<string, { cardId: string; prevUi: CardUiState }>;
  error: string | null;
  /** Where earlier messages of today came from: the gateway, or this tab's offline copy. */
  historySource: "loading" | "server" | "local";
}

export const initialChatState: ChatState = {
  connection: "connecting",
  sandbox: null,
  messages: [],
  activeTurn: null,
  queuedTurns: [],
  approvals: [],
  notifications: [],
  suggestions: [],
  suggestionsAnchor: null,
  pendingCards: {},
  error: null,
  historySource: "loading",
};

export type ChatAction =
  | { type: "connection"; state: ConnectionState }
  | { type: "server"; msg: ServerMessage; id: string; now: string }
  | { type: "send"; clientMsgId: string; text: string; attachments: ChatAttachment[]; now: string }
  | { type: "send_failed"; clientMsgId: string; error: string }
  | { type: "approval_decided"; approvalId: string; decision: ApprovalDecisionValue; scope: ApprovalScope }
  | { type: "approval_expired"; approvalId: string }
  | { type: "dismiss_approval"; approvalId: string }
  | { type: "notifications_read" }
  | { type: "dismiss_notification"; id: string }
  | { type: "notification_handled"; id: string; action: string }
  /** GET /notifications: fills the centre (live ones win). */
  | { type: "notifications_loaded"; items: AppNotification[] }
  /** Local-only card change (e.g. a celebration played). */
  | { type: "card_event"; cardId: string; event: CardEvent }
  /** A card click sent as `card_action`: updates the card at once and queues its turn. */
  | { type: "card_send"; cardId: string; clientMsgId: string; event: CardEvent }
  /** The click could not be sent: roll the card back. */
  | { type: "card_send_failed"; clientMsgId: string; error: string }
  | { type: "clear_suggestions" }
  | { type: "clear_error" }
  | { type: "history_loaded"; messages: ChatMessage[]; suggestions?: SuggestionItem[] }
  | { type: "restore"; messages: ChatMessage[] };

function updateMentorReply(
  state: ChatState,
  id: string,
  now: string,
  fn: (m: ChatMessage) => ChatMessage,
): ChatState {
  const turn = state.activeTurn ?? state.queuedTurns[0] ?? null;
  const messages = [...state.messages];
  // Find the open mentor message for the current turn (or an unsolicited one).
  let idx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "mentor" && m.status === "streaming" && (m.clientMsgId ?? null) === turn) {
      idx = i;
      break;
    }
  }
  if (idx === -1) {
    messages.push({
      id,
      role: "mentor",
      text: "",
      attachments: [],
      status: "streaming",
      clientMsgId: turn ?? undefined,
      tools: [],
      createdAt: now,
    });
    idx = messages.length - 1;
  }
  messages[idx] = fn(messages[idx]);
  return { ...state, messages, activeTurn: turn, queuedTurns: state.queuedTurns.filter((t) => t !== turn) };
}

function finishTurn(state: ChatState, clientMsgId: string | null, status: "done" | "error"): ChatState {
  const messages = state.messages.map((m) => {
    if (clientMsgId !== null && m.clientMsgId !== clientMsgId) {
      // Unsolicited mentor messages are closed by any turn end.
      if (!(m.role === "mentor" && m.status === "streaming" && m.clientMsgId === undefined)) return m;
    }
    if (m.role === "user" && m.status === "sending") return { ...m, status: status === "done" ? "done" : "error" } as ChatMessage;
    if (m.role === "mentor" && m.status === "streaming") {
      return {
        ...m,
        status,
        tools: m.tools.map((t) => ({ ...t, status: "done" as const })),
      };
    }
    return m;
  });
  return {
    ...state,
    messages,
    activeTurn: null,
    queuedTurns: clientMsgId ? state.queuedTurns.filter((t) => t !== clientMsgId) : state.queuedTurns.slice(1),
  };
}

/** The notification as the reducer stores it, for toasts and the desktop bridge. */
export function toChatNotification(msg: NotificationPayload, id: string): ChatNotification {
  return {
    id,
    serverId: msg.id !== undefined && msg.id !== null && msg.id !== "" ? String(msg.id) : undefined,
    text: msg.text ?? msg.body ?? msg.title ?? "",
    createdAt: msg.created_at,
    read: false,
    kind: msg.kind,
    title: msg.title,
    body: msg.body,
    actions: Array.isArray(msg.actions) ? msg.actions.slice(0, 3) : undefined,
    mascot: msg.mascot ? sanitizeMascot(msg.mascot, mascotForKind(msg.kind)) : mascotForKind(msg.kind),
    prefill: msg.prefill ?? null,
    bundled: Array.isArray(msg.bundled_ids) && msg.bundled_ids.length > 0 ? msg.bundled_ids.length : undefined,
  };
}

/** A stored notification (GET /notifications) as the centre shows it. */
export function fromAppNotification(n: AppNotification): ChatNotification {
  return {
    ...toChatNotification({ ...n, mascot: sanitizeMascot(n.mascot, mascotForKind(n.kind)) }, `n-${n.id}`),
    read: !!n.read_at,
    handled: n.answer ? `answer:${n.answer}` : n.status === "dismissed" ? "done" : undefined,
  };
}

/** Puts a live card into the log. Text already streamed in this turn stays above it; later text goes below. */
function addCard(state: ChatState, card: ChatCard, id: string, now: string): ChatState {
  if (!card || typeof card !== "object" || typeof card.id !== "string" || typeof card.kind !== "string") return state;
  // A known id is an update (focus extended or ended): replace that card in place, keep its position.
  if (state.messages.some((m) => m.card?.id === card.id)) {
    return {
      ...state,
      messages: state.messages.map((m) =>
        m.card?.id === card.id ? { ...m, card, cardUi: mergeCardUpdate(card, m.cardUi ?? {}) } : m,
      ),
    };
  }
  const turn = state.activeTurn ?? state.queuedTurns[0] ?? null;
  const messages = state.messages.map((m) => {
    const open = m.role === "mentor" && m.status === "streaming" && !m.card && (m.clientMsgId ?? null) === turn;
    const hasContent = m.text.length > 0 || m.tools.length > 0;
    const toolRunning = m.tools.some((t) => t.status === "running");
    // Seal the open bubble so text after the card starts a new bubble below it.
    return open && hasContent && !toolRunning ? { ...m, status: "done" as const } : m;
  });
  messages.push({
    id,
    role: "mentor",
    text: "",
    attachments: [],
    status: "done",
    clientMsgId: turn ?? undefined,
    tools: [],
    createdAt: card.created_at || now,
    card,
    cardUi: {},
    live: true,
  });
  return { ...state, messages };
}

function cleanSuggestions(items: unknown): SuggestionItem[] {
  return (Array.isArray(items) ? (items as SuggestionItem[]) : [])
    .filter((i) => i && typeof i.label === "string" && typeof i.text === "string" && i.text.trim())
    .slice(0, 3);
}

function rollbackCard(state: ChatState, clientMsgId: string, error: string): ChatState {
  const pending = state.pendingCards[clientMsgId];
  const pendingCards = { ...state.pendingCards };
  delete pendingCards[clientMsgId];
  return {
    ...state,
    error,
    pendingCards,
    queuedTurns: state.queuedTurns.filter((t) => t !== clientMsgId),
    activeTurn: state.activeTurn === clientMsgId ? null : state.activeTurn,
    messages: pending
      ? state.messages.map((m) => (m.card?.id === pending.cardId ? { ...m, cardUi: pending.prevUi } : m))
      : state.messages,
  };
}

function applyServer(state: ChatState, msg: ServerMessage, id: string, now: string): ChatState {
  switch (msg.type) {
    case "sandbox_status":
      return { ...state, sandbox: msg.state };
    case "text_delta":
      // A bubble never starts with whitespace (text streamed right after a card may begin with a blank line).
      return updateMentorReply(state, id, now, (m) => ({ ...m, text: m.text ? m.text + msg.text : msg.text.trimStart() }));
    case "tool_started":
      return updateMentorReply(state, id, now, (m) => ({
        ...m,
        tools: [...m.tools, { tool: msg.tool, summary: msg.summary, status: "running" }],
      }));
    case "tool_finished":
      return updateMentorReply(state, id, now, (m) => {
        const tools = [...m.tools];
        for (let i = tools.length - 1; i >= 0; i--) {
          if (tools[i].tool === msg.tool && tools[i].status === "running") {
            tools[i] = { tool: msg.tool, summary: msg.summary, status: "done" };
            return { ...m, tools };
          }
        }
        tools.push({ tool: msg.tool, summary: msg.summary, status: "done" });
        return { ...m, tools };
      });
    case "approval_request":
      if (state.approvals.some((a) => a.approval.approval_id === msg.approval.approval_id)) return state;
      return { ...state, approvals: [...state.approvals, { approval: msg.approval, status: "pending" }] };
    case "turn_done": {
      const next = finishTurn(state, msg.client_msg_id, "done");
      if (!(msg.client_msg_id in next.pendingCards)) return next;
      const pendingCards = { ...next.pendingCards };
      delete pendingCards[msg.client_msg_id];
      return { ...next, pendingCards };
    }
    case "notification": {
      const n = toChatNotification(msg, id);
      if (n.serverId && state.notifications.some((x) => x.serverId === n.serverId)) return state;
      return { ...state, notifications: [n, ...state.notifications].slice(0, 50) };
    }
    case "suggestions":
      return {
        ...state,
        suggestions: cleanSuggestions(msg.items),
        suggestionsAnchor: state.messages[state.messages.length - 1]?.id ?? null,
      };
    case "card_echo": {
      if (state.messages.some((m) => m.role === "user" && m.id === msg.client_msg_id)) return state;
      const tracked = msg.client_msg_id in state.pendingCards || state.queuedTurns.includes(msg.client_msg_id);
      return {
        ...state,
        suggestions: [],
        // A click from another tab or device: track its turn too.
        queuedTurns: tracked || !msg.client_msg_id ? state.queuedTurns : [...state.queuedTurns, msg.client_msg_id],
        messages: [
          ...state.messages,
          {
            id: msg.client_msg_id || id,
            role: "user",
            text: msg.text,
            attachments: [],
            status: "done",
            clientMsgId: msg.client_msg_id || undefined,
            tools: [],
            createdAt: now,
          },
        ],
      };
    }
    case "card":
      return addCard(state, msg.card, id, now);
    case "error": {
      if (msg.card_id) {
        // A refused card click: no turn ran. Roll that card back so the learner can try again.
        const entry = Object.entries(state.pendingCards).find(([, v]) => v.cardId === msg.card_id);
        return entry ? rollbackCard(state, entry[0], msg.error) : { ...state, error: msg.error };
      }
      const busy = state.activeTurn !== null || state.queuedTurns.length > 0;
      const next = busy ? finishTurn(state, state.activeTurn ?? state.queuedTurns[0], "error") : state;
      return { ...next, error: msg.error };
    }
    default:
      return state;
  }
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "connection": {
      if (action.state === "closed" && (state.activeTurn || state.queuedTurns.length)) {
        // The turn cannot complete on a dead socket.
        let s = state;
        for (const t of [state.activeTurn, ...state.queuedTurns].filter(Boolean) as string[]) s = finishTurn(s, t, "error");
        return { ...s, connection: "closed", sandbox: null, error: "Mất kết nối với mentor. Đang thử kết nối lại…" };
      }
      return {
        ...state,
        connection: action.state,
        sandbox: action.state === "closed" ? null : state.sandbox,
      };
    }
    case "server":
      return applyServer(state, action.msg, action.id, action.now);
    case "send":
      return {
        ...state,
        error: null,
        suggestions: [],
        queuedTurns: [...state.queuedTurns, action.clientMsgId],
        messages: [
          ...state.messages,
          {
            id: action.clientMsgId,
            role: "user",
            text: action.text,
            attachments: action.attachments,
            status: "sending",
            clientMsgId: action.clientMsgId,
            tools: [],
            createdAt: action.now,
          },
        ],
      };
    case "send_failed":
      return {
        ...state,
        error: action.error,
        queuedTurns: state.queuedTurns.filter((t) => t !== action.clientMsgId),
        messages: state.messages.map((m) => (m.clientMsgId === action.clientMsgId && m.role === "user" ? { ...m, status: "error" } : m)),
      };
    case "approval_decided":
      return {
        ...state,
        approvals: state.approvals.map((a) =>
          a.approval.approval_id === action.approvalId
            ? { ...a, status: action.decision === "approve" ? "approved" : "denied", scope: action.scope }
            : a,
        ),
      };
    case "approval_expired":
      return {
        ...state,
        approvals: state.approvals.map((a) =>
          a.approval.approval_id === action.approvalId && a.status === "pending" ? { ...a, status: "expired" } : a,
        ),
      };
    case "dismiss_approval":
      return { ...state, approvals: state.approvals.filter((a) => a.approval.approval_id !== action.approvalId) };
    case "notifications_read":
      return { ...state, notifications: state.notifications.map((n) => ({ ...n, read: true })) };
    case "dismiss_notification":
      return { ...state, notifications: state.notifications.filter((n) => n.id !== action.id) };
    case "notifications_loaded": {
      const have = new Set(state.notifications.map((n) => n.serverId).filter(Boolean));
      const loaded = action.items.map(fromAppNotification).filter((n) => !have.has(n.serverId));
      const notifications = [...state.notifications, ...loaded]
        .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
        .slice(0, 50);
      return { ...state, notifications };
    }
    case "notification_handled":
      return {
        ...state,
        notifications: state.notifications.map((n) => (n.id === action.id ? { ...n, handled: action.action, read: true } : n)),
      };
    case "card_event":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.card?.id === action.cardId ? { ...m, cardUi: cardReducer(m.card, m.cardUi ?? {}, action.event) } : m,
        ),
      };
    case "card_send": {
      const target = state.messages.find((m) => m.card?.id === action.cardId);
      if (!target?.card) return state;
      const card = target.card;
      return {
        ...state,
        error: null,
        suggestions: [],
        queuedTurns: [...state.queuedTurns, action.clientMsgId],
        pendingCards: { ...state.pendingCards, [action.clientMsgId]: { cardId: action.cardId, prevUi: target.cardUi ?? {} } },
        messages: state.messages.map((m) => (m === target ? { ...m, cardUi: cardReducer(card, m.cardUi ?? {}, action.event) } : m)),
      };
    }
    case "card_send_failed":
      return rollbackCard(state, action.clientMsgId, action.error);
    case "clear_suggestions":
      return { ...state, suggestions: [] };
    case "clear_error":
      return { ...state, error: null };
    case "history_loaded": {
      // Server history goes before anything already live in this tab (a card already live stays once).
      const live = new Set(state.messages.flatMap((m) => (m.card ? [m.card.id] : [])));
      const messages = [...action.messages.filter((m) => !m.card || !live.has(m.card.id)), ...state.messages];
      // The newest history item's quick replies, when nothing newer is on screen yet.
      const fromHistory = state.messages.length === 0 && (action.suggestions?.length ?? 0) > 0;
      return {
        ...state,
        historySource: "server",
        messages,
        ...(fromHistory
          ? { suggestions: cleanSuggestions(action.suggestions), suggestionsAnchor: messages[messages.length - 1]?.id ?? null }
          : {}),
      };
    }
    case "restore":
      return {
        ...state,
        historySource: "local",
        messages: [
          ...action.messages.map((m) => {
            const r = m.status === "sending" || m.status === "streaming" ? { ...m, status: "error" as const } : m;
            // The offline copy replays like history: no entrance, no second celebration.
            return r.card ? { ...r, live: false, cardUi: { ...r.cardUi, played: true } } : { ...r, live: false };
          }),
          ...state.messages,
        ],
      };
    default:
      return state;
  }
}

/** Is the mentor still working on something the user sent? */
export function isTurnInFlight(state: ChatState): boolean {
  return state.activeTurn !== null || state.queuedTurns.length > 0;
}

const MIME_BY_EXT: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  gif: "image/gif",
  heic: "image/heic",
  pdf: "application/pdf",
  md: "text/markdown",
  txt: "text/plain",
};

export function guessMime(path: string): string {
  return MIME_BY_EXT[path.split(".").pop()?.toLowerCase() ?? ""] ?? "application/octet-stream";
}

/** GET /chat/history entries -> finished chat messages (cards replay statically). */
export function historyToMessages(entries: ChatHistoryEntry[], date: string): ChatMessage[] {
  // Clicks recorded on user items, replayed onto their card so it shows what the learner already did.
  const clicks = new Map<string, { action: string; value?: string | null }[]>();
  for (const e of entries) {
    const a = e.role === "user" ? e.card_action : undefined;
    if (a?.card_id) clicks.set(a.card_id, [...(clicks.get(a.card_id) ?? []), a]);
  }
  const out: ChatMessage[] = [];
  entries.forEach((e, i) => {
    const card = e.card && typeof e.card === "object" && typeof e.card.kind === "string" ? e.card : null;
    if (card) {
      out.push({
        id: "h-" + date + "-" + i + "-card",
        role: "mentor",
        text: "",
        attachments: [],
        status: "done",
        tools: [],
        createdAt: e.ts,
        card,
        // Static replay: no entrance, no confetti, no second celebration.
        cardUi: (clicks.get(card.id) ?? []).reduce<CardUiState>(
          (ui, a) => {
            const ev = eventFromCardAction(card, a.action, a.value);
            return ev ? cardReducer(card, ui, ev) : ui;
          },
          { played: true, ...(card.kind === "focus" && card.ended_at ? { focusDone: true } : {}) },
        ),
        live: false,
      });
    }
    if (e.role === "card") return;
    const attachments = (e.attachments ?? []).map((a) => (typeof a === "string" ? { path: a, mime_type: guessMime(a) } : a));
    if (!e.text && attachments.length === 0) return;
    out.push({
      id: "h-" + date + "-" + i,
      role: e.role === "user" ? "user" : "mentor",
      text: e.text ?? "",
      attachments,
      status: "done",
      tools: [],
      createdAt: e.ts,
    });
  });
  return out;
}

/** Quick replies carried by the newest history item (Built H: on the turn's last mentor item). */
export function historySuggestions(entries: ChatHistoryEntry[]): SuggestionItem[] {
  const last = entries[entries.length - 1];
  return last && last.role === "mentor" && Array.isArray(last.suggestions) ? cleanSuggestions(last.suggestions) : [];
}
