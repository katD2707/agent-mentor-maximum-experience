import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import i18n from "./i18n";
import { App } from "./App";
import { AuthProvider } from "./state/auth";
import type { QuizItem, TextBlock } from "./api";
import { PracticeError, type PItem } from "./api";
import { createMockPractice } from "./api/mock-practice-api";
import { canSubmit, checkAnswer, shuffled, stemPieces } from "./lib/quiz";
import { canCheck, stepDecode, stepEncode, stepText } from "./lib/practice";
import { GlossChip, StaticBlock } from "./screens/courses/blocks";
import { fmtVal } from "./screens/courses/StepBlocks";

const q = (over: Partial<QuizItem> & Pick<QuizItem, "type" | "answer_key">): QuizItem => ({ id: "q", stem: "s", options: [], statements: [], option_feedback: {}, skill_ids: [], difficulty: 2, explanation: "", ...over });
const parts = [{ id: "a", text: "r" }, { id: "b", text: "q" }, { id: "c", text: "r²" }];

describe("grading the stepped kinds", () => {
  it("FILL_TILES: every gap needs its tile", () => {
    const it = q({ type: "FILL_TILES", stem: "x {{gap}} y {{gap}}", parts, answer_key: { gaps: ["c", "a"] } });
    expect(stemPieces(it.stem)).toHaveLength(3);
    expect(canSubmit(it, { kind: "gaps", ids: ["c", null] })).toBe(false);
    expect(checkAnswer(it, { kind: "gaps", ids: ["c", "a"] }).correct).toBe(true);
    expect(checkAnswer(it, { kind: "gaps", ids: ["a", "c"] }).correct).toBe(false);
  });
  it("MATCH_PAIRS: right pairs with no slip; ORDER_STEPS: the exact order", () => {
    const pairs = q({ type: "MATCH_PAIRS", parts: [{ id: "l1", text: "a", side: "left" }, { id: "r1", text: "b", side: "right" }], answer_key: { pairs: { l1: "r1" } } });
    expect(canSubmit(pairs, { kind: "pairs", map: {}, slips: 0 })).toBe(false);
    expect(checkAnswer(pairs, { kind: "pairs", map: { l1: "r1" }, slips: 0 }).correct).toBe(true);
    expect(checkAnswer(pairs, { kind: "pairs", map: { l1: "r1" }, slips: 1 }).correct).toBe(false);
    const order = q({ type: "ORDER_STEPS", parts, answer_key: { order: ["a", "b", "c"] } });
    expect(canSubmit(order, { kind: "order", ids: ["a", "b"] })).toBe(false);
    expect(checkAnswer(order, { kind: "order", ids: ["a", "b", "c"] }).correct).toBe(true);
    expect(checkAnswer(order, { kind: "order", ids: ["b", "a", "c"] }).correct).toBe(false);
  });
  it("tiles are shuffled the same way every time and never in the answer order", () => {
    const many = ["a", "b", "c", "d", "e"].map((id) => ({ id, text: id }));
    expect(shuffled(many, "x").map((p) => p.id)).toEqual(shuffled(many, "x").map((p) => p.id));
    expect(shuffled(many.slice(0, 2), "y").map((p) => p.id)).toEqual(["b", "a"]);
  });
});

describe("practice answers of the stepped kinds", () => {
  const item = { position: 0, id: "s", stem: "s", topic: "t", topic_title: "T", type: "ORDER_STEPS", parts } as PItem;
  it("travel as JSON, blank when empty, readable for the chosen line", () => {
    expect(stepEncode(item, { order: [] })).toBe("");
    expect(stepEncode(item, { order: ["c", "a", "b"] })).toBe('{"order":["c","a","b"]}');
    expect(stepDecode('{"order":["a"]}').order).toEqual(["a"]);
    expect(stepText(item, '{"order":["c","a"]}')).toBe("r² → r");
    expect(canCheck(item, '{"order":["a","b"]}')).toBe(false);
    expect(canCheck(item, '{"order":["a","b","c"]}')).toBe(true);
  });
  it("the mock fixes wrong items once: wrong again shows the answer", async () => {
    const api = createMockPractice({ steps: true });
    const s = await api.start("t", { source: "quick" });
    const at = s.items.findIndex((it) => it.type === "FILL_TILES");
    await api.answer("t", s.id, { position: at, answer: '{"gaps":["a"]}', time_spent_sec: 1 });
    await expect(api.fix("t", s.id, { item_id: s.items[at].id, answer: "" })).rejects.toBeInstanceOf(PracticeError); // not finished yet
    const report = await api.finish("t", s.id);
    expect(report.wrong).toEqual([{ position: at, item_id: s.items[at].id, type: "FILL_TILES", chosen: '{"gaps":["a"]}' }]);
    const again = await api.fix("t", s.id, { item_id: s.items[at].id, answer: '{"gaps":["a"]}' });
    expect(again).toMatchObject({ correct: false, right: '{"gaps":["c"]}' });
    await expect(api.fix("t", s.id, { item_id: s.items[at].id, answer: '{"gaps":["c"]}' })).rejects.toMatchObject({ code: "already_fixed" });
  });
});

describe("English: the Vietnamese gloss", () => {
  beforeEach(() => i18n.changeLanguage("vi"));
  const b: TextBlock = { id: "t", kind: "text", md: "We **study** every day.", gloss: "Chúng tôi **học** mỗi ngày." };
  const ctx = (glossPct?: number) => ({ lang: "en" as const, url: () => "", glossPct });
  it("a VI button shows the Vietnamese; the chip says how much is still offered", async () => {
    const ui = userEvent.setup();
    render(<StaticBlock b={b} ctx={ctx(30)} />);
    expect(screen.queryByText(/Chúng tôi/)).toBeNull();
    await ui.click(screen.getByRole("button", { name: "Xem nghĩa tiếng Việt" }));
    expect(screen.getByText(/Chúng tôi/)).toBeInTheDocument();
    render(<GlossChip pct={25} />);
    expect(screen.getByText("Tiếng Việt 25%")).toBeInTheDocument();
  });
  it("no button once nothing is offered or when the text has no gloss", () => {
    render(<StaticBlock b={b} ctx={ctx(0)} />);
    render(<StaticBlock b={{ ...b, gloss: null }} ctx={ctx(30)} />);
    expect(screen.queryByRole("button", { name: "Xem nghĩa tiếng Việt" })).toBeNull();
  });
  it("numbers read with the decimal comma", () => {
    expect(fmtVal(18000, "vi")).toBe("18 000");
    expect(fmtVal(0.25, "vi")).toBe("0,25");
    expect(fmtVal(0.25, "en")).toBe("0.25");
  });
});

describe("Nghe tóm tắt on the course page", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("vi");
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
      Object.defineProperty(this, "paused", { value: false, configurable: true });
      this.dispatchEvent(new Event("play"));
      return Promise.resolve();
    });
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
      Object.defineProperty(this, "paused", { value: true, configurable: true });
      this.dispatchEvent(new Event("pause"));
    });
  });
  afterEach(() => vi.restoreAllMocks());
  const open = (band: string, birth: number) => {
    localStorage.setItem("mentor.mock.users", JSON.stringify({ hocsinh: { password: "123456", user: { id: "u-hs", role: "student", username: "hocsinh", display_name: "Lan", age_band: band, birth_year: birth, language: "vi", theme: "system", quiet_until: null } } }));
    localStorage.setItem("mentor.token", "mock-u-hs");
    localStorage.setItem("mentor.tour.seen.u-hs", JSON.stringify(["today", "course"]));
    render(
      <MemoryRouter initialEntries={["/khoa-hoc/vat-li-11-dien-truong"]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    );
  };
  it("a row opens the docked player: play, 10 s back, speed 1x / 1,25x, progress", async () => {
    const ui = userEvent.setup();
    open("g10_12", 2009);
    await ui.click(await screen.findByRole("button", { name: /Nghe tóm tắt · 4 phút/ }));
    const mini = await screen.findByRole("region", { name: "Nghe tóm tắt" });
    expect(within(mini).getByRole("button", { name: "Lùi 10 giây" })).toBeInTheDocument();
    expect(within(mini).getByRole("slider", { name: "Tiến độ bài nghe" })).toBeInTheDocument();
    expect(await within(mini).findByRole("button", { name: "Tạm dừng" })).toBeInTheDocument(); // starts at once
    await ui.click(within(mini).getByRole("button", { name: "Tốc độ 1x" }));
    expect(within(mini).getByRole("button", { name: "Tốc độ 1.25x" })).toHaveTextContent("1.25x");
    await ui.click(within(mini).getByRole("button", { name: "Tạm dừng" }));
    expect(within(mini).getByRole("button", { name: "Phát" })).toBeInTheDocument();
    await ui.click(within(mini).getByRole("button", { name: "Đóng trình nghe" }));
    expect(screen.queryByRole("region", { name: "Nghe tóm tắt" })).toBeNull();
  });
});

describe("review reminder deep link", () => {
  it("keeps the notes id on the practice route and nothing else", async () => {
    const { resolveDeepLink } = await import("./lib/deeplink");
    expect(resolveDeepLink("/luyen-tap?notes=n-1").to).toBe("/luyen-tap?notes=n-1");
    expect(resolveDeepLink("/luyen-tap?notes=../x").to).toBe("/luyen-tap");
    expect(resolveDeepLink("/luyen-tap").to).toBe("/luyen-tap");
  });
});
