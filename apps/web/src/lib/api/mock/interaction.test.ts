import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { desktopMascotFor } from "../../desktop";
import type { ChatCard, ServerMessage } from "../../types";
import { ApiError } from "../client";
import { MockApiClient } from "./mockApi";

/** The mock speaks the whole interaction layer (CONTRACTS 9), so the UI works with NEXT_PUBLIC_API_MOCK=1. */

async function connect(persona: "thpt" | "ncs" = "thpt") {
  const api = new MockApiClient({ persona, now: () => Date.now(), origin: "http://localhost:3000" });
  const { dev_link } = await api.requestLink("hs@example.com");
  await api.verifyLink(new URL(dev_link!).searchParams.get("token")!);
  const msgs: ServerMessage[] = [];
  const sock = api.connectChat({ onMessage: (m) => msgs.push(m) });
  await vi.advanceTimersByTimeAsync(3000);
  msgs.length = 0;
  return { api, sock, msgs };
}

const cardsIn = (msgs: ServerMessage[]) => msgs.flatMap((m) => (m.type === "card" ? [m.card] : []));

describe("mock interaction layer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-03T13:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("/the shows every card kind with contract ids, suggestions before turn_done, celebration last", async () => {
    const { api, sock, msgs } = await connect();
    sock.send({ type: "user_message", client_msg_id: "c1", text: "/the", attachments: [] });
    await vi.advanceTimersByTimeAsync(20_000);
    const cards = cardsIn(msgs);
    expect(cards.map((c) => c.kind)).toEqual(["checkin", "flashcard", "deadline", "focus", "weekly", "celebration"]);
    for (const c of cards) {
      expect(c.id).toMatch(/^card-20261103-[0-9a-f]{12}$/);
      expect(c.created_at).toMatch(/\+07:00$/);
    }
    const types = msgs.map((m) => m.type);
    expect(types.indexOf("suggestions")).toBeLessThan(types.indexOf("turn_done"));
    expect(types.lastIndexOf("card")).toBeLessThan(types.indexOf("suggestions"));
    const history = await api.getChatHistory();
    expect(history.filter((e) => e.role === "card")).toHaveLength(6);
    sock.close();
  });

  it("answers a flashcard by letter: card_echo first, turn_done echoes client_msg_id, history records the click", async () => {
    const { api, sock, msgs } = await connect();
    sock.send({ type: "user_message", client_msg_id: "c1", text: "cho mình một thẻ", attachments: [] });
    await vi.advanceTimersByTimeAsync(10_000);
    const card = cardsIn(msgs)[0] as Extract<ChatCard, { kind: "flashcard" }>;
    expect(card.kind).toBe("flashcard");
    msgs.length = 0;
    sock.send({ type: "card_action", card_id: card.id, action: "answer", value: "A", client_msg_id: "k1" });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(msgs[0]).toEqual({
      type: "card_echo",
      client_msg_id: "k1",
      card_id: card.id,
      action: "answer",
      value: "A",
      text: `Đã chọn: A. ${card.choices![0]}`,
    });
    expect(msgs.find((m) => m.type === "turn_done")).toEqual({ type: "turn_done", client_msg_id: "k1" });
    const history = await api.getChatHistory();
    expect(history.find((e) => e.card_action)).toMatchObject({ role: "user", card_action: { card_id: card.id, action: "answer", value: "A" } });
    sock.close();
  });

  it("refuses bad clicks with card_id and no turn", async () => {
    const { sock, msgs } = await connect();
    sock.send({ type: "card_action", card_id: "card-20261103-000000000000", action: "answer", value: "A" });
    await vi.advanceTimersByTimeAsync(100);
    expect(msgs).toEqual([{ type: "error", error: "Không tìm thấy thẻ này.", card_id: "card-20261103-000000000000" }]);
    sock.close();
  });

  it("extends and ends a focus card in place (same id), history keeps it once", async () => {
    const { api, sock, msgs } = await connect();
    sock.send({ type: "user_message", client_msg_id: "c1", text: "tập trung 25 phút", attachments: [] });
    await vi.advanceTimersByTimeAsync(10_000);
    const focus = cardsIn(msgs)[0] as Extract<ChatCard, { kind: "focus" }>;
    expect(focus).toMatchObject({ kind: "focus", minutes: 25 });
    msgs.length = 0;
    sock.send({ type: "card_action", card_id: focus.id, action: "extend", value: "10", client_msg_id: "k1" });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(cardsIn(msgs)[0]).toMatchObject({ id: focus.id, minutes: 35 });
    msgs.length = 0;
    sock.send({ type: "card_action", card_id: focus.id, action: "done", client_msg_id: "k2" });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(cardsIn(msgs)[0]).toMatchObject({ id: focus.id, ended_at: expect.stringMatching(/\+07:00$/) });
    const inHistory = (await api.getChatHistory()).filter((e) => e.card?.id === focus.id);
    expect(inHistory).toHaveLength(1);
    expect(inHistory[0].card).toMatchObject({ minutes: 35, ended_at: expect.any(String) });
    expect((await api.getEngagement()).today.focus_minutes).toBeGreaterThan(0);
    sock.close();
  });

  it("sends rich nudges with int ids and applies their actions like the gateway", async () => {
    const { api, sock, msgs } = await connect();
    api.nudge("review");
    const n = msgs.find((m) => m.type === "notification") as Extract<ServerMessage, { type: "notification" }>;
    expect(n).toMatchObject({ kind: "review", mascot: "happy", title: expect.any(String) });
    expect(typeof n.id).toBe("number");
    expect((await api.getNotifications())[0]).toMatchObject({ id: n.id, read_at: null });
    expect(await api.notificationAction(String(n.id), "open")).toMatchObject({ ok: true, prefill: n.prefill });
    expect((await api.getNotifications())[0].read_at).not.toBeNull();
    expect(await api.notificationAction(String(n.id), "snooze_1h")).toHaveProperty("snoozed_until");
    await expect(api.notificationAction(String(n.id), "answer:x")).rejects.toMatchObject({ status: 422 });
    await expect(api.notificationAction("999", "open")).rejects.toBeInstanceOf(ApiError);
    expect(await api.getVapidPublicKey()).toMatchObject({ enabled: true, public_key: expect.any(String) });
    sock.close();
  });

  it("answers a crisis turn calmly: no cards, no suggestions", async () => {
    const { sock, msgs } = await connect();
    sock.send({ type: "user_message", client_msg_id: "c1", text: "/khunghoang", attachments: [] });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(cardsIn(msgs)).toEqual([]);
    expect(msgs.some((m) => m.type === "suggestions")).toBe(false);
    const text = msgs.flatMap((m) => (m.type === "text_delta" ? [m.text] : [])).join("");
    expect(text).toMatch(/111/);
    sock.close();
  });
});

describe("desktop bubble mascot", () => {
  it("is calm over everything, then celebrate, thinking, sleepy, idle", () => {
    const base = { crisis: false, quiet: false, sleeping: false, inFlight: false, celebrating: false };
    expect(desktopMascotFor({ ...base, crisis: true, celebrating: true, inFlight: true })).toBe("calm");
    expect(desktopMascotFor({ ...base, celebrating: true })).toBe("celebrate");
    expect(desktopMascotFor({ ...base, inFlight: true, quiet: true })).toBe("thinking");
    expect(desktopMascotFor({ ...base, quiet: true })).toBe("sleepy");
    expect(desktopMascotFor({ ...base, sleeping: true })).toBe("sleepy");
    expect(desktopMascotFor(base)).toBe("idle");
  });
});
