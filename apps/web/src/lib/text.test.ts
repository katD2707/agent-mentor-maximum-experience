import { describe, expect, it } from "vitest";
import { fold, highlightSegments, snippetAround } from "./text";

describe("fold", () => {
  it("strips diacritics and đ", () => {
    expect(fold("Phương trình Đại số")).toBe("phuong trinh dai so");
  });
});

describe("highlightSegments", () => {
  const marked = (t: string, q: string) => highlightSegments(t, q).filter((s) => s.match).map((s) => s.text);

  it("matches without typing accents and keeps the original text", () => {
    expect(marked("Giải phương trình bậc hai", "phuong trinh")).toEqual(["phương", "trình"]);
  });
  it("is case-insensitive and handles đ", () => {
    expect(marked("Đạo hàm của hàm số", "dao ham")).toEqual(["Đạo", "hàm", "hàm"]);
  });
  it("merges overlapping matches and reassembles the text", () => {
    const segs = highlightSegments("abcabc", "abc bca");
    expect(segs.map((s) => s.text).join("")).toBe("abcabc");
    expect(marked("abcabc", "abc bca")).toEqual(["abcabc"]);
  });
  it("returns one plain segment when nothing matches or the query is empty", () => {
    expect(highlightSegments("hello", "zzz")).toEqual([{ text: "hello", match: false }]);
    expect(highlightSegments("hello", "  ")).toEqual([{ text: "hello", match: false }]);
  });
});

describe("snippetAround", () => {
  it("cuts a window around the first match with ellipses", () => {
    const text = "x".repeat(200) + " phương trình " + "y".repeat(200);
    const s = snippetAround(text, "phuong");
    expect(s.startsWith("…")).toBe(true);
    expect(s.endsWith("…")).toBe(true);
    expect(s).toContain("phương");
    expect(s.length).toBeLessThan(140);
  });
  it("keeps short text whole", () => {
    expect(snippetAround("ngắn thôi", "ngan")).toBe("ngắn thôi");
  });
});
