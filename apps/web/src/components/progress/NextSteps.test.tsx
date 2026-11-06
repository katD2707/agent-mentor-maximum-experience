import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Recommendation } from "@/lib/practice/progressTypes";
import { RecommendationList } from "./NextSteps";

const r = (code: string, kind: Recommendation["action"]["kind"], title: string, subject = "math"): Recommendation => ({
  code,
  subject,
  title,
  reason: "đã luyện ít",
  action: { kind, params: { subject } },
});

describe("<RecommendationList>", () => {
  it("shows up to 3 steps with 'Vì sao' and exactly one primary button", () => {
    const html = renderToStaticMarkup(
      <RecommendationList
        recs={[r("PRACTICE_WEAK", "practice", "Luyện 20 phút"), r("TAKE_MOCK", "mock", "Thi thử"), r("PROBE_UNKNOWN", "practice", "Thử bài mới"), r("CHALLENGE_STRONG", "practice", "Thử thách")]}
      />,
    );
    expect(html).toContain("Bước tiếp theo");
    expect(html).toContain("Vì sao: đã luyện ít");
    expect((html.match(/btn btn-primary/g) ?? []).length).toBe(1);
    expect((html.match(/<li/g) ?? []).length).toBe(3);
    expect(html).not.toContain("Thử thách");
    expect(html).toContain('href="/practice?subject=math"');
  });

  it("renders TAKE_A_BREAK as a gentle card without a button", () => {
    const html = renderToStaticMarkup(<RecommendationList recs={[r("TAKE_A_BREAK", "break", "Nghỉ một chút nhé")]} />);
    expect(html).toContain("break-card");
    expect(html).toContain("Nghỉ một chút nhé");
    expect(html).not.toContain("<a ");
  });

  it("renders nothing when empty", () => {
    expect(renderToStaticMarkup(<RecommendationList recs={[]} />)).toBe("");
  });
});
