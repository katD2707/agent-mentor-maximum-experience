import { band, CONFIDENCE_TEXT, labelTone, progressLabel, sparkPoints, trendSummary } from "@/lib/practice/progress";
import type { ProgressSkill } from "@/lib/practice/progressTypes";

export function Sparkline({ trend, label }: { trend: { mastery: number }[]; label: string }) {
  if (trend.length === 0) return <span className="faint" aria-hidden="true">—</span>;
  return (
    <svg className="spark" viewBox="0 0 80 22" width="80" height="22" role="img" aria-label={`Xu hướng ${label}: ${trendSummary(trend)}`}>
      <polyline points={sparkPoints(trend)} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Mastery bar with an uncertainty band (lo..hi) behind the marker. No pass/fail colours, no "yếu". */
export function SkillMeter({ skill }: { skill: ProgressSkill }) {
  const label = progressLabel(skill);
  const known = skill.evidence > 0;
  const { lo, hi } = band(skill);
  const pct = Math.round(skill.mastery * 100);
  return (
    <div className="skill-meter" data-tone={labelTone(label)}>
      <div
        className="mbar"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={known ? pct : undefined}
        aria-valuetext={known ? `${pct} phần trăm, ước lượng từ ${skill.evidence} bằng chứng, ${CONFIDENCE_TEXT[skill.confidence]}` : "Chưa có dữ liệu"}
        aria-label={`Mức thành thạo ${skill.title}`}
      >
        {known && <span className="mband" style={{ left: `${lo * 100}%`, width: `${(hi - lo) * 100}%` }} />}
        {known && <span className="mfill" style={{ width: `${pct}%` }} />}
      </div>
      <div className="mmeta">
        <span className="badge" data-tone={labelTone(label)}>
          {label}
        </span>
        {known && <span className="muted">≈ {pct}%</span>}
        <span className="faint">{skill.evidence} bằng chứng</span>
        {known && <span className="faint">· {CONFIDENCE_TEXT[skill.confidence]}</span>}
      </div>
    </div>
  );
}
