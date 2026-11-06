import { describe, expect, it } from "vitest";
import {
  dueLabel,
  hasRealInboundDomain,
  isToolFailure,
  mistakeSentence,
  parseDueSkills,
  parseMistakes,
  plainStep,
  refDate,
  relativeDay,
  stripRefs,
  toolHeadline,
  weekPlan,
} from "./learner";

describe("stripRefs", () => {
  it("removes source refs and file paths", () => {
    expect(stripRefs("Thích học buổi tối. (chat 1/11)")).toBe("Thích học buổi tối.");
    expect(stripRefs("Ôn lại 3 lỗi trong learning/math/mistakes.md")).toBe("Ôn lại 3 lỗi trong sổ lỗi");
    expect(stripRefs("Đề thi 0/18 (events 6/11) không tính (nguồn: ảnh 25/10)")).toBe("Đề thi 0/18 không tính");
  });
  it("keeps ordinary parentheses", () => {
    expect(stripRefs("Toán (giữa kỳ)")).toBe("Toán (giữa kỳ)");
  });
});

describe("refDate / relativeDay", () => {
  it("reads d/m from the ref", () => {
    expect(refDate("x (chat 1/11)")).toEqual({ day: 1, month: 11 });
    expect(refDate("no ref")).toBeNull();
  });
  it("words recent days", () => {
    const now = new Date(2026, 10, 6);
    expect(relativeDay({ day: 6, month: 11 }, now)).toBe("hôm nay");
    expect(relativeDay({ day: 5, month: 11 }, now)).toBe("hôm qua");
    expect(relativeDay({ day: 1, month: 11 }, now)).toBe("5 ngày trước");
    expect(relativeDay({ day: 20, month: 10 }, now)).toBe("2 tuần trước");
    expect(relativeDay({ day: 3, month: 8 }, now)).toBe("3/8");
  });
});

describe("mistakes", () => {
  it("turns a bullet into one short sentence", () => {
    expect(mistakeSentence("[cẩu thả] Quên đổi dấu b khi tính nghiệm. algebra.quadratic.formula. (chat 30/10) ×2")).toBe(
      "Quên đổi dấu b khi tính nghiệm.",
    );
    expect(mistakeSentence("[kiến thức] Đặt t = sin x nhưng quên điều kiện. chưa gắn kỹ năng. (chat 4/11) ×1")).toBe(
      "Đặt t = sin x nhưng quên điều kiện.",
    );
  });
  it("reads only the current section", () => {
    const md = "# Lỗi\n## Đang gặp\n- [cẩu thả] A. a.b. (chat 1/1) ×1\n## Đã khắc phục\n- [kiến thức] B. c.d. ×1\n";
    expect(parseMistakes(md)).toEqual(["A."]);
  });
  it("accepts a flat list", () => {
    expect(parseMistakes("# Lỗi\n- **Nhầm dấu**: 3 lần (18/10, 24/10).\n")).toHaveLength(1);
  });
});

describe("parseDueSkills", () => {
  it("reads the bkt_update table", () => {
    const md =
      "# H\n\n| skill_id | Tên | Mastery | Đến hạn | Ghi chú |\n|---|---|---|---|---|\n| a.b | Đỉnh parabol | 0.5 | 2026-11-08 | x |\n| c.d | Bất PT | 0.4 | 2026-11-06 | y |\n";
    expect(parseDueSkills(md)).toEqual([
      { title: "Bất PT", due: "2026-11-06" },
      { title: "Đỉnh parabol", due: "2026-11-08" },
    ]);
  });
  it("reads the older short table", () => {
    const md = "| Kỹ năng | Đến hạn | Lý do |\n|---|---|---|\n| Bất PT | 29/10 | thấp |\n";
    expect(parseDueSkills(md, new Date(2026, 9, 1))).toEqual([{ title: "Bất PT", due: "2026-10-29" }]);
  });
  it("labels days", () => {
    expect(dueLabel("2026-11-06", "2026-11-06")).toBe("hôm nay");
    expect(dueLabel("2026-11-07", "2026-11-06")).toBe("ngày mai");
    expect(dueLabel("2026-11-05", "2026-11-06")).toBe("đã đến hạn");
    expect(dueLabel("2026-11-20", "2026-11-06")).toBe("20/11");
  });
});

describe("inbound domain", () => {
  it("is real only off .local", () => {
    expect(hasRealInboundDomain("u@inbox.mentor.local")).toBe(false);
    expect(hasRealInboundDomain("u@inbox.mentor.vn")).toBe(true);
    expect(hasRealInboundDomain(null)).toBe(false);
  });
});

describe("tool wording", () => {
  it("hides paths and failures", () => {
    expect(plainStep("Đã đọc me/now.md")).toBe("Đã đọc tệp");
    expect(isToolFailure("Lỗi: Dịch vụ tìm web đang lỗi (502)")).toBe(true);
    expect(isToolFailure("Đã đọc tệp")).toBe(false);
  });
  it("headlines", () => {
    expect(toolHeadline([{ tool: "web_search", status: "running" }])).toBe("Mentor đang tra cứu…");
    expect(toolHeadline([{ tool: "run_script", status: "running" }])).toBe("Mentor đang kiểm tra…");
    expect(toolHeadline([{ tool: "read_file", status: "done" }])).toBe("Mentor đã tra cứu xong");
  });
});

describe("weekPlan", () => {
  const md =
    "# Kế hoạch tuần\n<!-- c -->\n\n## Việc của người học\n- [x] T2 5 bài\n- T3 4 bài (chat 30/10)\n- [ ] T6 ôn (learning/math/review/x.md)\n\n## Mentor sẽ làm\n- Xử lý ảnh\n\n## Điều chỉnh\n- 2/11: dời (chat 30/10)\n";
  it("keeps only the learner tasks", () => {
    const w = weekPlan(md);
    expect(w.hasLearnerSection).toBe(true);
    expect(w.text).not.toMatch(/Mentor|Xử lý|dời|chat|learning/);
    expect(w.plain).toEqual(["T3 4 bài"]);
  });
  it("drops the removed sections of a headingless plan", () => {
    const w = weekPlan("# Kế hoạch\n\n| Ngày | Việc |\n|---|---|\n| T2 | A |\n\n## Điều chỉnh\n- x\n");
    expect(w.hasLearnerSection).toBe(false);
    expect(w.text).toContain("| T2 | A |");
    expect(w.text).not.toContain("x");
  });
});

describe("stripRefs: file names the learner knows", () => {
  it("names mistakes/review files in plain words and drops refs", () => {
    expect(stripRefs("ghi lại 3 lỗi vào mistakes.md (chat 1/11)")).toBe("ghi lại 3 lỗi vào sổ lỗi");
    expect(stripRefs("xem `learning/math/review-queue.md` trước")).toBe("xem lịch ôn trước");
    expect(stripRefs("Toán cuối kỳ — hạn 2026-12-14 (nguồn: chat 10/10)")).toBe("Toán cuối kỳ — hạn 2026-12-14");
  });
});