import { describe, expect, it } from "vitest";
import type { ChatCard, ChatHistoryEntry, ServerMessage } from "../types";
import { crisisFlags, currentTurnCrisis } from "./crisis";
import { chatReducer, historySuggestions, historyToMessages, initialChatState, type ChatAction, type ChatState } from "./reducer";

const NOW = "2026-11-03T13:00:00.000Z";
let n = 0;
const srv = (msg: ServerMessage): ChatAction => ({ type: "server", msg, id: `m${++n}`, now: NOW });
const run = (actions: ChatAction[], s: ChatState = initialChatState) => actions.reduce(chatReducer, s);

const focus: ChatCard = {
  id: "card-20261103-0123456789ab",
  kind: "focus",
  created_at: "2026-11-03T20:00:00+07:00",
  task: "Ôn bài",
  minutes: 25,
  ends_at: "2026-11-03T20:25:00+07:00",
};
const flash: ChatCard = {
  id: "card-20261103-ffffffffffff",
  kind: "flashcard",
  created_at: "2026-11-03T20:00:00+07:00",
  skill: "x",
  front: "?",
  choices: ["a", "b"],
  reveal: "a",
};

describe("cards in the chat log", () => {
  it("adds a live card, seals the bubble before it and trims the text that follows", () => {
    const s = run([
      { type: "send", clientMsgId: "c1", text: "hi", attachments: [], now: NOW },
      srv({ type: "text_delta", text: "Trước thẻ." }),
      srv({ type: "card", card: focus }),
      srv({ type: "text_delta", text: "\n\nSau thẻ." }),
      srv({ type: "turn_done", client_msg_id: "c1" }),
    ]);
    expect(s.messages.map((m) => (m.card ? "card" : `${m.role}:${m.text}`))).toEqual(["user:hi", "mentor:Trước thẻ.", "card", "mentor:Sau thẻ."]);
    expect(s.messages[2]).toMatchObject({ live: true, cardUi: {} });
  });

  it("treats a known card id as an update in place", () => {
    const s = run([
      srv({ type: "card", card: focus }),
      srv({ type: "text_delta", text: "ok" }),
      srv({ type: "card", card: { ...focus, ended_at: "2026-11-03T20:10:00+07:00" } as ChatCard }),
    ]);
    const cards = s.messages.filter((m) => m.card);
    expect(cards).toHaveLength(1);
    expect(s.messages[0].card).toMatchObject({ ended_at: "2026-11-03T20:10:00+07:00" });
    expect(s.messages[0].cardUi).toMatchObject({ focusDone: true });
  });

  it("runs a card click as a turn: optimistic card, server echo bubble, turn_done with the same id", () => {
    let s = run([srv({ type: "card", card: flash })]);
    s = chatReducer(s, { type: "card_send", cardId: flash.id, clientMsgId: "k1", event: { type: "flash_choose", value: "a" } });
    expect(s.queuedTurns).toEqual(["k1"]);
    expect(s.messages[0].cardUi).toMatchObject({ chosen: "a", correct: true });
    s = run(
      [
        srv({ type: "card_echo", client_msg_id: "k1", card_id: flash.id, action: "answer", value: "A", text: "Đã chọn: A. a" }),
        srv({ type: "text_delta", text: "Chính xác!" }),
        srv({ type: "turn_done", client_msg_id: "k1" }),
      ],
      s,
    );
    expect(s.messages.map((m) => m.role)).toEqual(["mentor", "user", "mentor"]);
    expect(s.messages[1]).toMatchObject({ text: "Đã chọn: A. a", clientMsgId: "k1" });
    expect(s.queuedTurns).toEqual([]);
    expect(s.pendingCards).toEqual({});
  });

  it("rolls the card back when the gateway refuses the click", () => {
    let s = run([srv({ type: "card", card: flash })]);
    s = chatReducer(s, { type: "card_send", cardId: flash.id, clientMsgId: "k1", event: { type: "flash_skip" } });
    s = chatReducer(s, srv({ type: "error", error: "Mentor đang bận", card_id: flash.id }));
    expect(s.messages[0].cardUi).toEqual({});
    expect(s.queuedTurns).toEqual([]);
    expect(s.error).toBe("Mentor đang bận");
  });

  it("keeps quick replies anchored to the newest item", () => {
    let s = run([
      { type: "send", clientMsgId: "c1", text: "hi", attachments: [], now: NOW },
      srv({ type: "text_delta", text: "Chào" }),
      srv({ type: "suggestions", client_msg_id: "c1", items: [{ label: "A", text: "a" }, { label: "", text: "" }, { label: "B", text: "b" }, { label: "C", text: "c" }, { label: "D", text: "d" }] }),
      srv({ type: "turn_done", client_msg_id: "c1" }),
    ]);
    expect(s.suggestions.map((x) => x.label)).toEqual(["A", "B", "C"]);
    expect(s.suggestionsAnchor).toBe(s.messages[s.messages.length - 1].id);
    s = chatReducer(s, srv({ type: "card", card: focus }));
    expect(s.suggestionsAnchor).not.toBe(s.messages[s.messages.length - 1].id);
    s = chatReducer(s, { type: "send", clientMsgId: "c2", text: "x", attachments: [], now: NOW });
    expect(s.suggestions).toEqual([]);
  });
});

describe("history replay", () => {
  const entries: ChatHistoryEntry[] = [
    { ts: "2026-11-03T20:00:00+07:00", role: "user", text: "cho mình một thẻ", attachments: [] },
    { ts: "2026-11-03T20:00:05+07:00", role: "card", card: flash },
    { ts: "2026-11-03T20:00:09+07:00", role: "user", text: "Đã chọn: B. b", card_action: { card_id: flash.id, kind: "flashcard", action: "answer", value: "B" } },
    { ts: "2026-11-03T20:00:12+07:00", role: "mentor", text: "Chưa đúng.", suggestions: [{ label: "Thêm thẻ", text: "thêm thẻ" }] },
  ];

  it("replays cards statically with the learner's recorded click", () => {
    const ms = historyToMessages(entries, "2026-11-03");
    expect(ms.map((m) => (m.card ? "card" : m.role))).toEqual(["user", "card", "user", "mentor"]);
    expect(ms[1]).toMatchObject({ live: false, cardUi: { played: true, chosen: "b", correct: false } });
    expect(historySuggestions(entries)).toEqual([{ label: "Thêm thẻ", text: "thêm thẻ" }]);
  });

  it("shows history suggestions only when nothing newer is on screen", () => {
    const s = chatReducer(initialChatState, {
      type: "history_loaded",
      messages: historyToMessages(entries, "2026-11-03"),
      suggestions: historySuggestions(entries),
    });
    expect(s.suggestions).toHaveLength(1);
    expect(s.suggestionsAnchor).toBe(s.messages[s.messages.length - 1].id);
  });

  it("does not duplicate a card that is already live", () => {
    const live = run([srv({ type: "card", card: flash })]);
    const s = chatReducer(live, { type: "history_loaded", messages: historyToMessages(entries, "2026-11-03") });
    expect(s.messages.filter((m) => m.card?.id === flash.id)).toHaveLength(1);
  });
});

describe("notifications", () => {
  it("keeps int ids as strings, defaults the mascot by kind and counts bundles", () => {
    const s = run([
      srv({ type: "notification", id: 7, kind: "checkin", title: "Chào", body: "b", actions: [], text: "t", created_at: NOW, bundled_ids: [5, 6] }),
      srv({ type: "notification", id: 7, kind: "checkin", text: "dup", created_at: NOW }),
    ]);
    expect(s.notifications).toHaveLength(1);
    expect(s.notifications[0]).toMatchObject({ serverId: "7", mascot: "wave", bundled: 2 });
  });

  it("merges GET /notifications under live ones", () => {
    const s = run([
      srv({ type: "notification", id: 9, kind: "review", text: "live", created_at: "2026-11-03T13:00:00Z" }),
      {
        type: "notifications_loaded",
        items: [
          { id: 9, kind: "review", title: "", body: "x", actions: [], mascot: "happy", prefill: null, text: "x", created_at: "2026-11-03T13:00:00Z" },
          { id: 3, kind: "deadline", title: "Hạn", body: "y", actions: [], mascot: "bogus", prefill: null, text: "y", created_at: "2026-11-02T13:00:00Z", read_at: "2026-11-02T14:00:00Z", status: "dismissed" },
        ],
      },
    ]);
    expect(s.notifications.map((x) => x.serverId)).toEqual(["9", "3"]);
    expect(s.notifications[1]).toMatchObject({ read: true, handled: "done", mascot: "idle" });
  });
});

describe("crisis context", () => {
  const msgs = run([
    { type: "send", clientMsgId: "c1", text: "chào", attachments: [], now: NOW },
    srv({ type: "text_delta", text: "Chào bạn" }),
    srv({ type: "turn_done", client_msg_id: "c1" }),
    { type: "send", clientMsgId: "c2", text: "mình mệt lắm", attachments: [], now: NOW },
    srv({ type: "card", card: { id: "c", kind: "celebration", created_at: NOW, title: "x" } }),
    srv({ type: "text_delta", text: "Bạn có thể gọi tổng đài 111 bất cứ lúc nào." }),
    srv({ type: "turn_done", client_msg_id: "c2" }),
  ]).messages;

  it("flags the whole turn, including a card that came before the crisis text", () => {
    expect(crisisFlags(msgs)).toEqual([false, false, true, true, true]);
    expect(currentTurnCrisis(msgs, [])).toBe(true);
  });

  it("stays calm until the next reply text arrives", () => {
    const next = chatReducer({ ...initialChatState, messages: msgs }, { type: "send", clientMsgId: "c3", text: "ừ", attachments: [], now: NOW });
    expect(currentTurnCrisis(next.messages, [])).toBe(true);
    const replied = chatReducer(next, srv({ type: "text_delta", text: "Mình ở đây." }));
    expect(currentTurnCrisis(replied.messages, [])).toBe(false);
  });
});
