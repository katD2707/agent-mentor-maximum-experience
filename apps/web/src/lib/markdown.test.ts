import { describe, expect, it } from "vitest";
import { buildSeed } from "./api/mock/seed";
import { parseChecklist, parseMemoryItems, removeLine, splitFrontmatter, toggleChecklistLine } from "./markdown";

describe("workspace markdown parsers", () => {
  const thpt = buildSeed("thpt").files;
  const ncs = buildSeed("ncs").files;

  it("parses thesis milestones with dates only under the milestone heading", () => {
    const items = parseChecklist(ncs["research/thesis.md"].content, /mốc/i);
    expect(items.length).toBe(6);
    expect(items[0]).toMatchObject({ done: true, date: "2026-03-20", text: "Bảo vệ đề cương" });
    expect(items.find((i) => !i.done)?.date).toBe("2026-11-03");
  });

  it("toggles a checklist line in place", () => {
    const text = ncs["research/reading-queue.md"].content;
    const [first] = parseChecklist(text);
    const next = toggleChecklistLine(text, first.line, true);
    expect(parseChecklist(next)[0].done).toBe(true);
    expect(next.split("\n").length).toBe(text.split("\n").length);
  });

  it("lists forgettable memory items and flags inferences", () => {
    const text = thpt["me/now.md"].content;
    const items = parseMemoryItems(text);
    expect(items.some((i) => i.inferred)).toBe(true);
    expect(items[0].section).toBe("Tuần này");
    const after = removeLine(text, items[0].line);
    expect(after).not.toContain(items[0].text);
    expect(parseMemoryItems(after)).toHaveLength(items.length - 1);
  });

  it("splits report frontmatter", () => {
    const { meta, body } = splitFrontmatter(thpt["reports/2026-10-24.md"].content);
    expect(meta).toMatchObject({ period_start: "2026-10-10", period_end: "2026-10-23", includes_wellbeing_nudge: "false" });
    expect(body.startsWith("# Báo cáo")).toBe(true);
    expect(body).toContain("Báo cáo được tạo tự động bởi AI mentor, chỉ mang tính tham khảo.");
  });
});

describe("inline milestones (goal-planning skill format)", () => {
  const text = "## Đang theo đuổi\n### Toán ≥ 8\n- Mốc: [x] 31/10 xong hàm số · [ ] 03/11 dấu tam thức · [ ] 05/11 đề thử\n";
  it("reads one item per checkbox and toggles the right one", () => {
    const items = parseChecklist(text);
    expect(items.map((i) => [i.text, i.done, i.slot])).toEqual([
      ["31/10 xong hàm số", true, 0],
      ["03/11 dấu tam thức", false, 1],
      ["05/11 đề thử", false, 2],
    ]);
    const next = toggleChecklistLine(text, items[1].line, true, items[1].slot);
    expect(parseChecklist(next).map((i) => i.done)).toEqual([true, true, false]);
  });
});
