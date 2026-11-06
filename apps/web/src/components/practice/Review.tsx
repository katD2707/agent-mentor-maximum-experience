"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { getApi } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { keyAction, partOf, statementOutcome } from "@/lib/practice/logic";
import type { ReviewItem } from "@/lib/practice/types";
import { usePageShortcuts, type Shortcut } from "@/lib/shortcuts";
import { ReportItemDialog } from "./Dialogs";
import { FeedbackPanel } from "./Feedback";
import { QuestionView } from "./QuestionView";
import { ErrorBox, Loading } from "../ui";

const REVIEW_SHORTCUTS: Shortcut[] = [
  { keys: "← →", description: "Câu trước, câu sau" },
  { keys: "Enter", description: "Câu sau, hết bài thì đóng" },
  { keys: "L", description: "Báo lỗi câu hỏi" },
  { keys: "Esc", description: "Đóng" },
];

/** `/practice/review/[id]`: read-only replay of a finished session with answers, keys and solutions. */
export function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  usePageShortcuts("practice-review", "Xem lại bài", REVIEW_SHORTCUTS);
  const data = useAsync(() => getApi().practice.review(id), [id]);
  const [pos, setPos] = useState(0);
  const [report, setReport] = useState(false);
  const live = useRef({ pos, count: 0, report });
  const items: ReviewItem[] = useMemo(() => (Array.isArray(data.data) ? data.data : (data.data?.items ?? [])), [data.data]);
  const sessionParts = Array.isArray(data.data) ? null : (data.data?.session?.parts ?? null);
  useEffect(() => {
    live.current = { pos, count: items.length, report };
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const cur = items[live.current.pos];
      if (!cur) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if ((tag === "BUTTON" || tag === "A") && (e.key === "Enter" || e.key === " ")) return;
      const a = keyAction(e, { mode: "review", phase: "feedback", itemType: cur.type, optionCount: 0, hasHint: false, typing: false, modalOpen: live.current.report || !!document.querySelector("dialog[open]") });
      if (!a) return;
      e.preventDefault();
      const { pos: p, count } = live.current;
      if (a.type === "prev") setPos(Math.max(0, p - 1));
      else if (a.type === "next" || a.type === "primary") {
        if (p < count - 1) setPos(p + 1);
        else if (a.type === "primary") router.back();
      } else if (a.type === "pause") router.back();
      else if (a.type === "report") setReport(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, router]);

  if (data.error) return <div className="page"><ErrorBox error={data.error} onRetry={data.reload} /></div>;
  if (!data.data) return <Loading full label="Đang mở bài để xem lại…" />;
  const item = items[pos];
  if (!item) return <div className="page"><p className="muted">Bài này chưa có câu hỏi để xem lại.</p></div>;
  const unanswered = !item.answer;

  return (
    <div className="player" data-mode="review">
      <header className="player-top">
        <button type="button" className="btn btn-ghost" onClick={() => router.back()}>
          Đóng <kbd className="keycap keycap-inline">Esc</kbd>
        </button>
        <div className="player-title">
          <div className="player-line">
            <strong className="player-label">Xem lại bài</strong>
            <span className="muted">
              Câu {pos + 1}/{items.length}
            </span>
          </div>
          <ol className="segs" aria-hidden="true">
            {items.map((it, i) => (
              <li key={it.id} className="seg" data-state={it.correct === true ? "correct" : it.correct === false ? "wrong" : "empty"} data-current={i === pos} />
            ))}
          </ol>
        </div>
      </header>
      <div className="player-main">
        <div key={item.id} className="player-focus" data-enter>
          <QuestionView
            item={item}
            part={sessionParts ? partOf({ parts: sessionParts }, item.position) : null}
            answer={item.answer ?? null}
            onAnswer={() => {}}
            readOnly
            outcome={{ correctAnswer: item.correct_answer, correct: item.correct, statementResults: item.statement_results ? statementOutcome(item.statement_results) : undefined, optionFeedback: item.option_feedback }}
            extraAssets={item.solution_assets}
          />
          <FeedbackPanel
            item={item}
            data={{
              correct: item.correct === true,
              unanswered,
              points: item.points ?? undefined,
              maxPoints: item.max_points ?? (item.type === "TRUE_FALSE_GROUP" ? 1 : undefined),
              correctAnswer: item.correct_answer,
              statementResults: item.statement_results ? statementOutcome(item.statement_results) : undefined,
            }}
            showSolution
            alwaysOpen
            explanation={item.explanation}
            tip={item.tip}
            statementExplanations={item.statement_explanations ?? item.statements?.filter((s) => typeof s.truth === "boolean").map((s) => ({ id: s.id, truth: s.truth as boolean, explanation: s.explanation }))}
            solutionAssets={item.solution_assets}
            onReport={() => setReport(true)}
          />
        </div>
      </div>
      <footer className="player-bottom">
        <button type="button" className="btn" onClick={() => setPos(Math.max(0, pos - 1))} disabled={pos === 0}>
          Câu trước
        </button>
        <button type="button" className="btn btn-primary btn-lg" onClick={() => (pos < items.length - 1 ? setPos(pos + 1) : router.back())}>
          {pos < items.length - 1 ? "Câu sau" : "Đóng"} <kbd className="keycap keycap-inline">Enter</kbd>
        </button>
      </footer>
      <ReportItemDialog open={report} onClose={() => setReport(false)} itemId={item.id} sessionId={id} />
    </div>
  );
}
