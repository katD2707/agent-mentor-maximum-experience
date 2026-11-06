"use client";

import { feedbackHeadline, keyLabelOf } from "@/lib/practice/logic";
import type { ClientItem, PracticeAsset, RevealResult } from "@/lib/practice/types";
import { Icon } from "../Icon";
import { RichText } from "./RichText";
import type { Outcome } from "./QuestionView";

export interface FeedbackData extends Outcome {
  points?: number;
  maxPoints?: number;
  /** The learner left the item blank (review). */
  unanswered?: boolean;
  /** From `/answer`.statement_results: why each statement is true or false. */
  statementExplanations?: { id: string; truth: boolean; explanation?: string | null }[];
}

/** Immediate result under an answered item: headline in words, key, optional solution, tip, error report. */
export function FeedbackPanel({
  item,
  data,
  reveal,
  showSolution,
  onToggleSolution,
  onReport,
  solutionAssets,
  statementExplanations,
  tip,
  explanation,
  alwaysOpen = false,
}: {
  item: ClientItem;
  data: FeedbackData;
  reveal?: RevealResult | null;
  showSolution: boolean;
  onToggleSolution?: () => void;
  onReport?: () => void;
  solutionAssets?: PracticeAsset[];
  statementExplanations?: { id: string; truth: boolean; explanation?: string | null }[];
  tip?: string | null;
  explanation?: string;
  alwaysOpen?: boolean;
}) {
  const ok = !!data.correct;
  const right = (data.statementResults ?? []).filter((v) => v === true).length;
  const keyLabel = keyLabelOf(item.type, data.correctAnswer ?? "");
  const headline = data.unanswered
    ? `Câu này bạn chưa trả lời, đáp án đúng là ${keyLabel}`
    : feedbackHeadline(item.type, { correct: ok, points: data.points, max_points: data.maxPoints, right, keyLabel });
  const text = explanation ?? reveal?.explanation;
  const stmts = statementExplanations ?? data.statementExplanations ?? reveal?.statements;
  const theTip = tip ?? reveal?.tip;
  const open = alwaysOpen || showSolution;
  const tone = data.unanswered ? "warn" : ok ? "ok" : "wrong";
  return (
    <section className="fb" data-tone={tone} aria-label="Kết quả">
      <div className="fb-head">
        <p className="fb-title" role="status" aria-live="polite">
          <Icon name={ok ? "check" : "close"} size={18} /> {headline}
        </p>
        {!alwaysOpen && onToggleSolution && (
          <button type="button" className="btn btn-sm" onClick={onToggleSolution} aria-expanded={showSolution}>
            {showSolution ? "Ẩn lời giải" : "Xem lời giải"} <kbd className="keycap keycap-inline">E</kbd>
          </button>
        )}
      </div>
      {open && (
        <div className="fb-solution">
          <h3>Lời giải</h3>
          {text ? (
            text.split(/\n{2,}/).map((para, i) => <RichText key={i} text={para} assets={[...item.assets, ...(solutionAssets ?? reveal?.assets ?? [])]} />)
          ) : (
            <p className="muted">Đang tải lời giải…</p>
          )}
          {stmts
            ?.filter((s) => s.explanation)
            .map((s) => (
              <div key={s.id} className="fb-stmt">
                <RichText text={`${s.id}) ${s.truth ? "Đúng" : "Sai"}. ${s.explanation}`} />
              </div>
            ))}
          {theTip && (
            <div className="fb-tip">
              <strong>Mẹo</strong>
              <RichText text={theTip} />
            </div>
          )}
        </div>
      )}
      {onReport && (
        <button type="button" className="btn btn-ghost btn-sm fb-report" onClick={onReport}>
          Báo lỗi câu hỏi <kbd className="keycap keycap-inline">L</kbd>
        </button>
      )}
    </section>
  );
}
