import { describe, expect, it } from "vitest";
import { parseSlash, parseSubject, slashHintsFor, snapMinutes } from "./slashCommands";

describe("parseSubject (accent-insensitive)", () => {
  it.each([
    ["Toán", "math"],
    ["toan", "math"],
    ["math", "math"],
    ["Lý", "physics"],
    ["ly", "physics"],
    ["vat ly", "physics"],
    ["Vật lý", "physics"],
    ["physics", "physics"],
    ["Anh", "english"],
    ["tieng anh", "english"],
    ["Tiếng Anh", "english"],
    ["english", "english"],
  ])("%s -> %s", (raw, id) => expect(parseSubject(raw)).toBe(id));

  it("returns null for unknown names", () => {
    expect(parseSubject("hoa")).toBeNull();
    expect(parseSubject("")).toBeNull();
  });
});

describe("parseSlash", () => {
  it("ignores normal text", () => {
    expect(parseSlash("xin chào")).toEqual({ kind: "none" });
    expect(parseSlash("/khongco abc")).toEqual({ kind: "none" });
  });

  it("/luyen with subject and minutes", () => {
    const r = parseSlash("/luyen toan 20");
    expect(r).toMatchObject({ kind: "route", href: "/practice?subject=math&minutes=20" });
  });

  it("/luyen snaps minutes to the allowed set and accepts any order", () => {
    expect(parseSlash("/luyen 25 vat ly")).toMatchObject({ kind: "route", href: "/practice?subject=physics&minutes=20" });
    expect(parseSlash("/luyen anh 60")).toMatchObject({ href: "/practice?subject=english&minutes=45" });
    expect(snapMinutes(32)).toBe(30);
  });

  it("/luyen alone opens the setup", () => {
    expect(parseSlash("/luyen")).toMatchObject({ kind: "route", href: "/practice" });
  });

  it("accepts accented command names and a unit suffix", () => {
    expect(parseSlash("/luyện Toán 30p")).toMatchObject({ href: "/practice?subject=math&minutes=30" });
  });

  it("/thithu and /tienbo", () => {
    expect(parseSlash("/thithu Lý")).toMatchObject({ kind: "route", href: "/practice/mock?subject=physics" });
    expect(parseSlash("/tienbo anh")).toMatchObject({ kind: "route", href: "/progress?subject=english" });
    expect(parseSlash("/tienbo")).toMatchObject({ href: "/progress" });
  });

  it("unknown subject is an error, not a route", () => {
    expect(parseSlash("/thithu hoa")).toMatchObject({ kind: "error" });
  });

  it("/nhac and /nho are sent as normal messages", () => {
    expect(parseSlash("/nhac ôn bài lúc 20h")).toEqual({ kind: "send", text: "/nhac ôn bài lúc 20h" });
    expect(parseSlash("  /nho em hay quên dấu  ")).toEqual({ kind: "send", text: "/nho em hay quên dấu" });
    expect(parseSlash("/nhac")).toMatchObject({ kind: "error" });
  });
});

describe("slashHintsFor", () => {
  it("lists everything for a bare slash", () => {
    expect(slashHintsFor("/").map((h) => h.command)).toEqual(["/luyen", "/thithu", "/tienbo", "/nhac", "/nho"]);
  });
  it("filters by prefix, ignoring accents", () => {
    expect(slashHintsFor("/th").map((h) => h.command)).toEqual(["/thithu"]);
    expect(slashHintsFor("/luy").map((h) => h.command)).toEqual(["/luyen"]);
    expect(slashHintsFor("/n").map((h) => h.command)).toEqual(["/nhac", "/nho"]);
  });
  it("shows nothing once arguments start or for normal text", () => {
    expect(slashHintsFor("/luyen toan")).toEqual([]);
    expect(slashHintsFor("hello")).toEqual([]);
    expect(slashHintsFor("/zzz")).toEqual([]);
  });
});
