import { describe, expect, it } from "vitest";
import { routeText } from "./logic";

describe("routeText", () => {
  it.each([
    ["Mảng và danh sách liên kết khác nhau thế nào?", "chat"],
    ["Làm sao giải phương trình bậc hai?", "chat"],
    ["Đạo hàm của hàm hợp tính thế nào", "chat"],
    ["Tìm điểm cực trị ở đâu", "chat"],
    ["Cấp số cộng là gì, làm sao tìm công sai?", "chat"],
    ["How do I prove this by induction?", "chat"],
    ["Đấu trường ở đâu?", "help"],
    ["Nút nào để vào phòng tự học?", "help"],
    ["Làm sao để đổi cài đặt ngôn ngữ?", "help"],
    ["Điểm kinh nghiệm tính thế nào?", "help"],
    ["Chuồng gà dùng thế nào", "help"],
    ["Cách dùng app này", "help"],
    ["Where is the study room?", "help"],
    ["How do I level up my chicken?", "help"],
    ["Chụp vở ở đâu", "help"],
    ["Em muốn chụp vở ghi", "notes"],
    ["Cho em thi thử", "mock"],
    ["Luyện tập nhé", "practice"],
  ])("%s -> %s", (text, route) => {
    expect(routeText(text)).toBe(route);
  });
});

import { streamSafeMd } from "./logic";
describe("streamSafeMd", () => {
  it.each([
    ["Độ phức tạp là $O(n", "Độ phức tạp là"],
    ["Độ phức tạp là $O(n)$ nhé", "Độ phức tạp là $O(n)$ nhé"],
    ["Ta có $$x^2 +", "Ta có"],
    ["Ta có $$x^2$$ và $y", "Ta có $$x^2$$ và"],
    [String.raw`Giá \(a+`, "Giá"],
    [String.raw`Công thức $\frac{a}{b}$ và \fr`, String.raw`Công thức $\frac{a}{b}$ và `],
    ["Không có công thức", "Không có công thức"],
  ])("%s", (inp, out) => {
    expect(streamSafeMd(inp)).toBe(out);
  });
});

import { toChatEvent } from "../../api/chat";
describe("toChatEvent", () => {
  it("reads the gateway's `actions` list (and the older `items`)", () => {
    const a = [{ key: "lesson", label_vi: "Học tiếp", label_en: "Keep learning", deep_link: "/khoa-hoc/c1/hoc" }];
    expect(toChatEvent({ event: "actions", data: JSON.stringify({ actions: a }) })).toEqual({ event: "actions", data: { items: a } });
    expect(toChatEvent({ event: "actions", data: JSON.stringify({ items: a }) })).toEqual({ event: "actions", data: { items: a } });
  });
});
