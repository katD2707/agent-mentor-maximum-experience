"use client";

import Link from "next/link";
import { useRef, useState, type KeyboardEvent } from "react";
import { RoleGate } from "@/components/AuthGate";
import { NextSteps } from "@/components/progress/NextSteps";
import { SkillMeter, Sparkline } from "@/components/progress/SkillMeter";
import { EmptyState, ErrorBox, Loading, PageHeader } from "@/components/ui";
import { getApi } from "@/lib/api";
import { formatDate, localDateStamp } from "@/lib/format";
import { useAsync } from "@/lib/hooks";
import { dueLabel, parseDueSkills, parseMistakes } from "@/lib/learner";
import { groupByTopic, labelTone, SUBJECT_NAMES } from "@/lib/practice/progress";
import { diagnosticRoute, reviewRoute } from "@/lib/practice/routes";
import type { SessionSummary } from "@/lib/practice/progressTypes";

const SUBJECTS = ["math", "physics", "english"] as const;
const KIND_TEXT: Record<SessionSummary["kind"], string> = { practice: "Luyện tập", mock: "Thi thử", diagnostic: "Chẩn đoán" };

function initialSubject(): string {
  if (typeof window === "undefined") return SUBJECTS[0];
  const s = new URLSearchParams(window.location.search).get("subject");
  return s && (SUBJECTS as readonly string[]).includes(s) ? s : SUBJECTS[0];
}

function Skills({ subject }: { subject: string }) {
  const q = useAsync(() => getApi().getProgress(subject), [subject]);
  if (q.error != null) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data) return <Loading />;
  const topics = groupByTopic(q.data.skills);
  const titles = new Map((q.data.topics ?? []).map((t) => [t.topic, t.title]));
  const none = q.data.skills.every((s) => s.evidence === 0);
  return (
    <>
      {none && (
        <EmptyState card>
          <p>Chưa có dữ liệu cho môn này. Làm 5 câu đầu tiên để Mầm biết em đang ở đâu.</p>
          <Link href={diagnosticRoute({ subject })} className="btn btn-primary btn-sm" style={{ marginTop: 8 }}>
            Làm 5 câu đầu tiên
          </Link>
        </EmptyState>
      )}
      {topics.map((t) => (
        <details key={t.topic} className="card topic" open>
          <summary>
            <span className="topic-name">{titles.get(t.topic) ?? t.topic}</span>
            <span className="badge" data-tone={labelTone(t.label)}>
              {t.label}
            </span>
            <span className="faint">{t.evidence} bằng chứng</span>
          </summary>
          <ul className="skill-list">
            {t.skills.map((s) => (
              <li key={s.skill_id}>
                <div className="skill-title">{s.title}</div>
                <SkillMeter skill={s} />
                <div className="skill-trend">
                  <Sparkline trend={s.trend} label={s.title} />
                </div>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </>
  );
}

/** Optional workspace file: a missing one (404) or any failure just means "nothing to show". */
function useOptionalFile(path: string): string | null {
  const q = useAsync(() => getApi().getFile(path).then((f) => f.content, () => null), [path]);
  return q.data ?? null;
}

/** "Sắp ôn" (skills due) and "Lỗi hay gặp" (current mistakes), in plain words: no ids, no mastery numbers. */
function Upcoming({ subject }: { subject: string }) {
  const queue = useOptionalFile(`learning/${subject}/review-queue.md`);
  const mistakes = useOptionalFile(`learning/${subject}/mistakes.md`);
  const due = queue ? parseDueSkills(queue).slice(0, 5) : [];
  const wrong = mistakes ? parseMistakes(mistakes) : [];
  if (due.length === 0 && wrong.length === 0) return null;
  const today = localDateStamp();
  return (
    <div className="grid-2" style={{ marginTop: 16 }}>
      {due.length > 0 && (
        <section className="card" aria-labelledby="due-h">
          <h2 id="due-h">Sắp ôn</h2>
          <ul className="plain-list">
            {due.map((d) => (
              <li key={`${d.title}-${d.due}`}>
                <span>{d.title}</span>
                <span className="faint">{dueLabel(d.due, today)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {wrong.length > 0 && (
        <section className="card" aria-labelledby="miss-h">
          <h2 id="miss-h">Lỗi hay gặp</h2>
          <ul className="plain-list">
            {wrong.map((w) => (
              <li key={w}>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Sessions({ subject }: { subject: string }) {
  const q = useAsync(() => getApi().listPracticeSessions({ subject, limit: 30 }), [subject]);
  return (
    <section className="card" aria-labelledby="sess-h" style={{ marginTop: 16 }}>
      <h2 id="sess-h">30 buổi gần nhất</h2>
      {q.error != null && <ErrorBox error={q.error} onRetry={q.reload} />}
      {!q.data && q.error == null && <Loading />}
      {q.data && q.data.length === 0 && <p className="empty">Chưa có buổi luyện nào cho môn này.</p>}
      {q.data && q.data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Các buổi luyện tập và thi thử gần đây</caption>
            <thead>
              <tr>
                <th scope="col">Ngày</th>
                <th scope="col">Loại</th>
                <th scope="col">Điểm</th>
                <th scope="col">Đúng</th>
                <th scope="col">Phút</th>
                <th scope="col">
                  <span className="sr-only">Xem lại</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((s) => (
                <tr key={s.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{formatDate(s.started_at)}</td>
                  <td>{KIND_TEXT[s.kind]}</td>
                  <td>{s.score_10 != null ? `${String(s.score_10).replace(".", ",")}/10` : "—"}</td>
                  <td>
                    {s.correct}/{s.total}
                  </td>
                  <td>{s.minutes}</td>
                  <td>
                    <Link href={reviewRoute(s.id)} className="btn btn-sm">
                      Xem lại<span className="sr-only"> buổi {formatDate(s.started_at)}</span>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Progress() {
  const [subject, setSubject] = useState(initialSubject);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKey(e: KeyboardEvent, i: number) {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const n = (i + d + SUBJECTS.length) % SUBJECTS.length;
    setSubject(SUBJECTS[n]);
    tabs.current[n]?.focus();
  }

  return (
    <div className="page">
      <PageHeader
        title="Tiến bộ"
        description="Mỗi kỹ năng có một dải ước lượng: dải càng hẹp thì mình càng chắc. Làm thêm bài thì dải sẽ thu lại."
      />
      <div className="tabs" role="tablist" aria-label="Môn học">
        {SUBJECTS.map((s, i) => (
          <button
            key={s}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${s}`}
            aria-selected={s === subject}
            aria-controls="progress-panel"
            tabIndex={s === subject ? 0 : -1}
            onClick={() => setSubject(s)}
            onKeyDown={(e) => onKey(e, i)}
          >
            {SUBJECT_NAMES[s]}
          </button>
        ))}
      </div>
      <div id="progress-panel" role="tabpanel" aria-labelledby={`tab-${subject}`}>
        <NextSteps key={`n-${subject}`} subject={subject} />
        <Skills key={`s-${subject}`} subject={subject} />
        <Upcoming key={`u-${subject}`} subject={subject} />
        <p className="hint disclaimer">Mức thành thạo là ước lượng, không phải dự đoán điểm thi.</p>
        <Sessions key={`h-${subject}`} subject={subject} />
      </div>
    </div>
  );
}

export default function ProgressPage() {
  return (
    <RoleGate role="thpt" fallback="/research">
      <Progress />
    </RoleGate>
  );
}
