"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { usePageShortcuts, type Shortcut } from "@/lib/shortcuts";
import { formatClock, minutesLeft, segmentStates, spokenClock, submitCounts, submitMessage } from "@/lib/practice/logic";
import { Icon } from "../Icon";
import { ErrorBox, Loading } from "../ui";
import { PracticeDialog, ReportItemDialog } from "./Dialogs";
import { FeedbackPanel } from "./Feedback";
import { QuestionView } from "./QuestionView";
import { RichText } from "./RichText";
import { usePlayer } from "./usePlayer";

const PLAYER_SHORTCUTS: Shortcut[] = [
  { keys: "1-4 hoặc A-D", description: "Chọn đáp án (câu Đúng/Sai: đổi Đúng/Sai cho ý 1-4)" },
  { keys: "Enter", description: "Kiểm tra, rồi sang câu tiếp (thi thử: câu sau)" },
  { keys: "H", description: "Gợi ý, trước khi kiểm tra (luyện tập)" },
  { keys: "E", description: "Xem lời giải, sau khi kiểm tra" },
  { keys: "S", description: "Bỏ qua câu (luyện tập)" },
  { keys: "F", description: "Đánh dấu xem lại (thi thử)" },
  { keys: "G", description: "Mở bảng câu hỏi (thi thử)" },
  { keys: "← →", description: "Câu trước, câu sau (thi thử, xem lại)" },
  { keys: "L", description: "Báo lỗi câu hỏi, sau khi đã xem đáp án" },
  { keys: "Esc", description: "Tạm dừng bài làm" },
];

export function Player({ sessionId }: { sessionId: string }) {
  const p = usePlayer(sessionId);
  const router = useRouter();
  const stemRef = useRef<HTMLDivElement>(null);
  usePageShortcuts("practice-player", "Làm bài luyện tập", PLAYER_SHORTCUTS);

  // A new item: bring the question into view and let screen readers start from it.
  useEffect(() => {
    stemRef.current?.focus({ preventScroll: true });
    window.scrollTo?.({ top: 0 });
  }, [p.position, p.session?.id]);

  if (p.error) {
    return (
      <div className="page">
        <ErrorBox error={p.error} onRetry={() => router.refresh()} />
      </div>
    );
  }
  if (!p.session || !p.item) return <Loading full label="Đang mở bài làm…" />;

  const { session, item, mode, timer } = p;
  const total = p.items.length;
  const isMock = mode === "mock";
  const isPractice = mode === "practice";
  const answerShown = isPractice && !!p.result;
  const segs = segmentStates(p.items, session.answers, mode).map((s, i) => {
    // Local state wins over the last server snapshot.
    if (isMock) return p.flags[i] ? "flagged" : p.answers[i] ? "answered" : "empty";
    const r = p.results[i];
    if (r) return r.correct ? "correct" : "wrong";
    return s;
  });
  const counts = submitCounts(
    p.items,
    Object.fromEntries(p.items.map((it) => [String(it.position), { answer: p.answers[it.position] ?? null, flagged: !!p.flags[it.position] }])),
  );
  const answeredCount = p.items.filter((it) => !!p.answers[it.position] || !!p.results[it.position]).length;
  const lastItem = p.position === total - 1;
  const readyToSubmit = lastItem || counts.unanswered === 0;

  const primaryLabel = isMock
    ? lastItem
      ? "Nộp bài"
      : "Câu sau"
    : answerShown
      ? lastItem
        ? "Xem kết quả"
        : "Tiếp tục"
      : mode === "diagnostic"
        ? lastItem
          ? "Xong"
          : "Tiếp"
        : "Kiểm tra";
  const primaryDisabled = isPractice && !answerShown ? !p.canCheck || p.busy : p.finishing;
  const need =
    item.type === "SINGLE_CHOICE" ? "Chọn 1 đáp án (phím 1-4 hoặc A-D)" : item.type === "TRUE_FALSE_GROUP" ? "Chọn Đúng hoặc Sai cho từng ý (phím 1-4)" : "Nhập đáp số rồi bấm Enter";

  const fb = p.result;

  return (
    <div className="player" data-mode={mode}>
      <header className="player-top">
        <button type="button" className="btn btn-ghost btn-icon" aria-label="Tạm dừng bài làm (Esc)" onClick={() => p.setDialog("exit")}>
          <Icon name="close" />
        </button>
        <div className="player-title">
          <div className="player-line">
            <strong className="player-label">{session.label ?? "Bài làm"}</strong>
            <span className="muted">
              Câu {p.position + 1}/{total}
            </span>
            {isPractice && p.streak >= 2 && (
              <span className="pill-streak" role="status">
                Chuỗi đúng ×{p.streak}
              </span>
            )}
          </div>
          <ol className="segs" aria-label={`Tiến độ: đã làm ${answeredCount} trên ${total} câu`}>
            {segs.map((s, i) => (
              <li key={i} className="seg" data-state={s} data-current={i === p.position} aria-hidden="true" />
            ))}
          </ol>
        </div>
        <div className="player-right">
          {isMock && timer.warn && (
            <span className="badge badge-warn" role="status">
              Còn {minutesLeft(timer.shown)} phút
            </span>
          )}
          <div className="timer" data-urgent={timer.urgent} role="timer" aria-label={spokenClock(timer.shown, timer.counting)}>
            <span className="timer-num">{formatClock(timer.shown)}</span>
            <span className="faint timer-cap">{timer.counting === "down" ? "còn lại" : "đã trôi qua"}</span>
          </div>
          {isMock && (
            <>
              <button type="button" className="btn btn-sm" onClick={() => p.setDialog("grid")}>
                Bảng câu <kbd className="keycap keycap-inline">G</kbd>
              </button>
              <button type="button" className={readyToSubmit ? "btn btn-sm btn-primary" : "btn btn-sm"} onClick={() => p.setDialog("finish")}>
                Nộp bài
              </button>
            </>
          )}
        </div>
      </header>

      <div className="player-main">
        <div ref={stemRef} tabIndex={-1} className="player-focus" key={`${session.id}-${p.position}`} data-enter>
          <QuestionView
            item={item}
            part={p.part}
            flagged={!!p.flags[p.position]}
            answer={p.answer}
            onAnswer={p.setAnswer}
            readOnly={answerShown || p.finishing}
            outcome={fb}
            shakeKey={p.effect.shake}
          />
          {isPractice && p.hint && !answerShown && (
            <aside className="hintbox" aria-label="Gợi ý">
              <strong>Gợi ý</strong>
              <RichText text={p.hint} assets={item.assets} />
              <p className="faint">Dùng gợi ý vẫn được ghi nhận; câu này chỉ ảnh hưởng nhẹ hơn tới ước lượng mức nắm vững.</p>
            </aside>
          )}
          {fb && (
            <div data-bounce={fb.correct ? p.effect.bounce : undefined} className="fb-wrap">
              <FeedbackPanel
                item={item}
                data={fb}
                reveal={p.reveal}
                showSolution={p.showSolution}
                onToggleSolution={p.toggleSolution}
                onReport={() => p.setDialog("report")}
              />
            </div>
          )}
        </div>
      </div>

      <footer className="player-bottom">
        <div className="row">
          {isPractice && !answerShown && (
            <>
              {item.has_hint !== false && (
                <button type="button" className="btn btn-ghost" onClick={() => void p.requestHint()} disabled={!!p.hint}>
                  Gợi ý <kbd className="keycap keycap-inline">H</kbd>
                </button>
              )}
              <button type="button" className="btn btn-ghost" onClick={() => void p.skip()}>
                Bỏ qua câu <kbd className="keycap keycap-inline">S</kbd>
              </button>
            </>
          )}
          {isMock && (
            <>
              <button type="button" className="btn" onClick={() => void p.goTo(p.position - 1)} disabled={p.position === 0}>
                Trước
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => void p.toggleFlag()} aria-pressed={!!p.flags[p.position]}>
                {p.flags[p.position] ? "Bỏ đánh dấu" : "Đánh dấu xem lại"} <kbd className="keycap keycap-inline">F</kbd>
              </button>
            </>
          )}
          {mode === "diagnostic" && <span className="faint">Đánh giá nhanh · đáp án hiện ở cuối bài</span>}
        </div>
        <div className="row">
          {primaryDisabled && isPractice && !answerShown && <span className="faint">{need}</span>}
          <button type="button" className="btn btn-primary btn-lg" onClick={p.primary} disabled={primaryDisabled}>
            {primaryLabel} <kbd className="keycap keycap-inline">Enter</kbd>
          </button>
        </div>
      </footer>

      <PracticeDialog
        open={p.dialog === "exit"}
        title="Tạm dừng bài làm?"
        onClose={() => p.setDialog("none")}
        actions={[
          { label: "Làm tiếp", onClick: () => p.setDialog("none"), autoFocus: true },
          ...(isPractice && answeredCount > 0 ? [{ label: "Kết thúc và xem kết quả", onClick: () => void p.finish() }] : []),
          { label: "Lưu và thoát", kind: "primary" as const, onClick: () => router.push(`/practice?subject=${encodeURIComponent(session.subject)}`) },
        ]}
      >
        <p>
          Tiến độ đã được lưu. Bạn có thể quay lại làm tiếp bất cứ lúc nào.
          {isMock && " Bài thi thử đang được bấm giờ: hãy quay lại trước khi hết giờ, nếu không bài sẽ được nộp tự động."}
        </p>
      </PracticeDialog>

      <PracticeDialog
        open={p.dialog === "finish"}
        title="Nộp bài?"
        onClose={() => p.setDialog("none")}
        actions={[
          { label: "Kiểm tra lại", onClick: () => p.setDialog("none"), autoFocus: true },
          { label: "Nộp bài", kind: "primary", onClick: () => void p.finish() },
        ]}
      >
        <p>{submitMessage(counts)}</p>
        <p className="muted">Đúng/sai và lời giải hiện sau khi nộp bài.</p>
      </PracticeDialog>

      <PracticeDialog open={p.dialog === "grid"} title="Bảng câu hỏi" onClose={() => p.setDialog("none")} wide actions={[{ label: "Đóng", onClick: () => p.setDialog("none"), autoFocus: true }]}>
        <p className="muted">Chọn một câu để chuyển tới. Câu đánh dấu có viền vàng.</p>
        {(session.parts?.length ? session.parts.map((pt) => ({ label: pt.label, positions: pt.positions })) : [{ label: "", positions: p.items.map((i) => i.position) }]).map((g) => (
          <div key={g.label || "all"} className="grid-group">
            {g.label && <h3>{g.label}</h3>}
            <div className="qgrid">
              {g.positions.map((i) => (
                <button
                  key={i}
                  type="button"
                  className="qcell"
                  data-answered={!!p.answers[i]}
                  data-flagged={!!p.flags[i]}
                  data-current={i === p.position}
                  aria-label={`Câu ${i + 1}${p.answers[i] ? ", đã trả lời" : ", chưa trả lời"}${p.flags[i] ? ", đã đánh dấu" : ""}`}
                  onClick={() => void p.goTo(i)}
                >
                  {i + 1}
                </button>
              ))}
            </div>
          </div>
        ))}
        <p className="muted">
          Đã trả lời {answeredCount}/{total}
        </p>
      </PracticeDialog>

      <ReportItemDialog open={p.dialog === "report" && (answerShown || false)} onClose={() => p.setDialog("none")} itemId={item.id} sessionId={session.id} />
    </div>
  );
}
