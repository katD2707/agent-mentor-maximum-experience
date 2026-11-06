"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { getApi, isApiError } from "@/lib/api";
import { blockedFrom, gradeDetail, LEVEL_NAMES } from "@/lib/practice/logic";
import { GOALS, levelShares, MINUTES, previewSummary } from "@/lib/practice/setup";
import type { PracticeGoal, PracticePreview, PracticeSubject, Session } from "@/lib/practice/types";
import { Icon } from "../Icon";
import { useToast } from "../toast";
import { errorText } from "../ui";

export const sessionRoute = (id: string) => `/practice/session/${encodeURIComponent(id)}`;

/** "Bạn đang làm dở..." with one button back into the session. */
export function ResumeBanner({ session }: { session: Session }) {
  const answered = Object.values(session.answers).filter((a) => a.answer || a.draft || a.checked).length;
  return (
    <section className="resume card" aria-label="Bài làm dở">
      <div>
        <strong>Bạn đang làm dở một bài {session.kind === "mock" ? "thi thử" : session.kind === "diagnostic" ? "đánh giá nhanh" : "luyện tập"}</strong>
        <p className="muted">
          Đã trả lời {answered}/{session.items.length} câu · tiến độ được lưu tự động
          {typeof session.remaining_sec === "number" && ` · còn khoảng ${Math.ceil(session.remaining_sec / 60)} phút`}
        </p>
      </div>
      <Link href={sessionRoute(session.id)} className="btn btn-primary">
        Tiếp tục
      </Link>
    </section>
  );
}

/** 409 `active_session`: offer to resume instead of starting another. */
export function BlockedNotice({ blocked }: { blocked: { id: string; kind: string } }) {
  const what = blocked.kind === "mock" ? "bài thi thử" : blocked.kind === "diagnostic" ? "bài đánh giá nhanh" : "bài luyện tập";
  return (
    <div className="alert alert-warn" role="alert">
      <div className="row">
        <span className="spacer">Bạn đang có một {what} chưa xong ở môn này. Hãy làm tiếp hoặc nộp bài trước khi bắt đầu bài mới.</span>
        <Link href={sessionRoute(blocked.id)} className="btn btn-sm btn-primary">
          Làm tiếp
        </Link>
      </div>
    </div>
  );
}

function Chip({ on, onClick, children, label, disabled = false }: { on: boolean; onClick: () => void; children: React.ReactNode; label?: string; disabled?: boolean }) {
  return (
    <button type="button" className="pchip" aria-pressed={on} aria-label={label} onClick={onClick} disabled={disabled} style={disabled ? { opacity: 0.55 } : undefined}>
      {on && <Icon name="check" size={14} />}
      {children}
    </button>
  );
}

/** PracticeSetup: duration, goal, topics and a live preview from `/preview`; Enter starts. */
export function PracticeSetup({
  subject,
  initial,
  active,
  droppedTopics = 0,
}: {
  subject: PracticeSubject;
  initial: { minutes: number; goal: PracticeGoal; topics: string[] };
  active?: Session | null;
  droppedTopics?: number;
}) {
  const router = useRouter();
  const toast = useToast();
  const [minutes, setMinutes] = useState(initial.minutes);
  const [goal, setGoal] = useState<PracticeGoal>(initial.goal);
  const [topics, setTopics] = useState<string[]>(initial.topics);
  const [aboveOk, setAboveOk] = useState(() => initial.topics.some((id) => subject.topics.find((t) => t.id === id)?.above_grade));
  const hasAbove = subject.topics.some((t) => t.above_grade);
  const [preview, setPreview] = useState<PracticePreview | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [blocked, setBlocked] = useState<{ id: string; kind: string } | null>(null);
  const startRef = useRef<() => void>(() => {});
  const topicsKey = topics.join(",");

  useEffect(() => {
    let alive = true;
    const t = setTimeout(() => {
      setPreview(null);
      setProblem(null);
      getApi()
        .practice.preview({ subject: subject.id, minutes, goal, topics: topics.length ? topics : undefined, ...(aboveOk ? { include_above_grade: true } : {}) })
        .then(
          (p) => alive && setPreview(p),
          (e: unknown) => {
            if (!alive) return;
            const insufficient = isApiError(e) && JSON.stringify(e.body ?? "").includes("insufficient_content");
            setProblem(gradeDetail(e) ?? (insufficient ? "Chưa đủ câu hỏi cho lựa chọn này. Hãy chọn thêm chủ đề hoặc giảm thời lượng." : errorText(e)));
          },
        );
    }, 120);
    return () => {
      alive = false;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subject.id, minutes, goal, topicsKey, aboveOk]);

  async function start() {
    if (!preview || starting) return;
    setStarting(true);
    try {
      const s = await getApi().practice.start({ kind: "practice", subject: subject.id, minutes, goal, topics: topics.length ? topics : undefined, seed: preview.seed, ...(aboveOk ? { include_above_grade: true } : {}) });
      router.push(sessionRoute(s.id));
    } catch (e) {
      setStarting(false);
      const b = blockedFrom(e);
      if (b) setBlocked(b);
      else toast(gradeDetail(e) ?? errorText(e), "error");
    }
  }
  useEffect(() => {
    startRef.current = () => void start();
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Enter" || e.defaultPrevented || e.isComposing) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag && tag !== "BODY" && tag !== "MAIN" && tag !== "DIV") return; // a focused control keeps its own Enter
      if (document.querySelector("dialog[open]")) return;
      startRef.current();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const shares = useMemo(() => (preview ? levelShares(preview.level_mix) : []), [preview]);

  return (
    <section aria-labelledby="setup-h">
      <h2 id="setup-h">Buổi luyện tập · {subject.label}</h2>
      {droppedTopics > 0 && (
        <p className="alert alert-info" role="status">
          Một số chủ đề trong gợi ý không còn trong ngân hàng câu hỏi, nên mình để bạn chọn lại bên dưới.
        </p>
      )}
      <fieldset>
        <legend>Thời lượng</legend>
        <div className="pchips" role="group" aria-label="Thời lượng">
          {MINUTES.map((m) => (
            <Chip key={m} on={minutes === m} onClick={() => setMinutes(m)}>
              {m} phút
            </Chip>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Mục tiêu</legend>
        <div className="pchips" role="group" aria-label="Mục tiêu">
          {GOALS.map((g) => (
            <Chip key={g.id} on={goal === g.id} onClick={() => setGoal(g.id)}>
              {g.label}
            </Chip>
          ))}
        </div>
        <p className="hint">{GOALS.find((g) => g.id === goal)?.hint}</p>
      </fieldset>
      <fieldset>
        <legend>Chủ đề</legend>
        <div className="pchips" role="group" aria-label="Chủ đề">
          <Chip on={topics.length === 0} onClick={() => setTopics([])}>
            Tất cả
          </Chip>
          {subject.topics.map((t) => {
            const locked = !!t.above_grade && !aboveOk;
            return (
              <Chip
                key={t.id}
                on={topics.includes(t.id)}
                disabled={locked}
                onClick={() => setTopics((cur) => (cur.includes(t.id) ? cur.filter((x) => x !== t.id) : [...cur, t.id]))}
                label={`${t.title}, ${t.item_count} câu${t.above_grade ? `, lớp ${t.grade}` : ""}`}
              >
                {t.title}
                {t.above_grade && t.grade != null && <span className="badge">lớp {t.grade}</span>}
              </Chip>
            );
          })}
        </div>
        {hasAbove && (
          <label className="switch" style={{ marginTop: 8 }}>
            <input
              type="checkbox"
              role="switch"
              checked={aboveOk}
              onChange={(e) => {
                setAboveOk(e.target.checked);
                if (!e.target.checked) setTopics((cur) => cur.filter((id) => !subject.topics.find((t) => t.id === id)?.above_grade));
              }}
            />
            <span>Thử cả chủ đề lớp trên</span>
          </label>
        )}
      </fieldset>

      <div className="card preview" aria-live="polite" aria-busy={!preview && !problem}>
        {problem ? (
          <p className="alert alert-warn">{problem}</p>
        ) : !preview ? (
          <p className="muted">Đang sắp đề…</p>
        ) : (
          <>
            <p className="preview-big">{previewSummary(preview)}</p>
            <p className="faint">Độ khó</p>
            <div className="lvbar" role="img" aria-label={shares.map((s) => `${LEVEL_NAMES[s.level - 1]} ${s.n}`).join(", ")}>
              {shares.map((s) => (
                <span key={s.level} data-level={s.level} style={{ flexGrow: s.n }} />
              ))}
            </div>
            <ul className="lvlegend">
              {shares.map((s) => (
                <li key={s.level}>
                  <span className="lvdot" data-level={s.level} aria-hidden="true" /> {LEVEL_NAMES[s.level - 1]} {s.n}
                </li>
              ))}
            </ul>
            <p className="muted">{preview.per_topic.map((t) => `${t.title} ${t.count}`).join(" · ")}</p>
          </>
        )}
      </div>

      {active && active.kind === "practice" && (
        <p className="hint">Bài luyện tập đang làm dở của môn này sẽ được kết thúc và lưu kết quả khi bạn bắt đầu buổi mới.</p>
      )}
      {blocked && <BlockedNotice blocked={blocked} />}
      <div className="row" style={{ marginTop: 16 }}>
        <button type="button" className="btn btn-primary btn-lg" onClick={() => void start()} disabled={!preview || starting}>
          {starting ? "Đang mở…" : "Bắt đầu"} <kbd className="keycap keycap-inline">Enter</kbd>
        </button>
        <Link href="/practice" className="btn btn-ghost">
          Đổi môn
        </Link>
      </div>
    </section>
  );
}
