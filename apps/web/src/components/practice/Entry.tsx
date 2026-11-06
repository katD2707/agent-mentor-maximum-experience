"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getApi } from "@/lib/api";
import { emitTourSignal } from "@/lib/tour";
import { useAsync } from "@/lib/hooks";
import { diagnosticRoute, mockRoute, practiceRoute, progressRoute } from "@/lib/practice/routes";
import { matchTopics, parseGoal, parseMinutes, splitParam } from "@/lib/practice/setup";
import type { PracticeSubject, Session } from "@/lib/practice/types";
import { usePageShortcuts, type Shortcut } from "@/lib/shortcuts";
import { PageHeader, ErrorBox, Loading } from "../ui";
import { useToast } from "../toast";
import { errorText } from "../ui";
import { PracticeDialog } from "./Dialogs";
import { blockedFrom, gradeDetail } from "@/lib/practice/logic";
import { BlockedNotice, PracticeSetup, ResumeBanner, sessionRoute } from "./Setup";

function useSubjects() {
  return useAsync(() => getApi().practice.subjects(), []);
}

function SubjectPicker({ subjects, active, mode }: { subjects: PracticeSubject[]; active: Session | null; mode: "practice" | "mock" }) {
  return (
    <>
      {active && <ResumeBanner session={active} />}
      <h2 className="section-label">Chọn môn</h2>
      <ul className="subject-grid">
        {subjects.map((s) => (
          <li key={s.id} className="card subject-card">
            <h3>{s.label}</h3>
            <p className="muted">{s.topics.reduce((n, t) => n + t.item_count, 0)} câu · {s.topics.length} chủ đề</p>
            <div className="row">
              <Link href={mode === "mock" ? mockRoute({ subject: s.id }) : practiceRoute({ subject: s.id })} className="btn btn-primary btn-sm">
                {mode === "mock" ? "Thi thử" : "Luyện tập"}
              </Link>
              <Link href={mode === "mock" ? practiceRoute({ subject: s.id }) : mockRoute({ subject: s.id })} className="btn btn-sm">
                {mode === "mock" ? "Luyện tập" : "Thi thử"}
              </Link>
              <Link href={progressRoute(s.id)} className="btn btn-ghost btn-sm">
                Tiến bộ
              </Link>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

const HEADER_NOTE = "Câu hỏi do dự án biên soạn và được AI kiểm định (thử nghiệm). Mức nắm vững là ước lượng để chọn bài vừa sức, không phải điểm thi.";

/** `/practice`: the subject picker, or the setup page when `?subject=` is given (prefilled from a link or chat card). */
export function PracticeHome() {
  const q = useSearchParams();
  const subjects = useSubjects();
  const active = useAsync(() => getApi().practice.active(q.get("subject") ?? undefined), [q.get("subject")]);
  if (subjects.error) return <div className="page"><ErrorBox error={subjects.error} onRetry={subjects.reload} /></div>;
  if (!subjects.data) return <Loading full label="Đang tải môn học…" />;
  const subject = subjects.data.find((s) => s.id === q.get("subject"));
  const resume = active.data ?? null;

  if (!subject) {
    return (
      <div className="page">
        <PageHeader title="Luyện tập" description={HEADER_NOTE} />
        <SubjectPicker subjects={subjects.data} active={resume} mode="practice" />
      </div>
    );
  }
  const m = matchTopics(splitParam(q.get("topics")), subject);
  return (
    <div className="page page-narrow">
      <PageHeader title="Luyện tập" description={HEADER_NOTE} />
      {resume && <ResumeBanner session={resume} />}
      {subject.diagnostic === "none" && (
        <section className="card diag-nudge" aria-label="Đánh giá nhanh">
          <div>
            <strong>Làm đánh giá nhanh trước?</strong>
            <p className="muted">Khoảng 12 câu giúp mình xếp đề vừa sức cho bạn. Bạn cũng có thể bỏ qua.</p>
          </div>
          <Link href={diagnosticRoute({ subject: subject.id })} className="btn">
            Xem chi tiết
          </Link>
        </section>
      )}
      <PracticeSetup
        key={`${subject.id}-${q.get("minutes")}-${q.get("goal")}-${q.get("topics")}`}
        subject={subject}
        initial={{ minutes: parseMinutes(q.get("minutes")), goal: parseGoal(q.get("goal")), topics: m.ids }}
        active={resume}
        droppedTopics={m.dropped}
      />
    </div>
  );
}

const MOCK_SHORTCUTS: Shortcut[] = [
  { keys: "Enter", description: "Bắt đầu thi thử (khi không có bài làm dở)" },
  { keys: "Esc", description: "Để sau" },
];

/** `/practice/mock`: the confirmation before a timed mock starts (profile, count, minutes, disclaimer). */
export function MockEntry() {
  const q = useSearchParams();
  const router = useRouter();
  const toast = useToast();
  usePageShortcuts("practice-mock", "Thi thử", MOCK_SHORTCUTS);
  const subjects = useSubjects();
  const subjectId = q.get("subject");
  const active = useAsync(() => getApi().practice.active(subjectId ?? undefined), [subjectId]);
  const [picked, setPicked] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const [aboveOk, setAboveOk] = useState(false);
  const started = useRef(false);
  const [blocked, setBlocked] = useState<{ id: string; kind: string } | null>(null);

  const subject = subjects.data?.find((s) => s.id === subjectId);
  const wanted = q.get("profile_id");
  const profiles = subject?.mock_profiles ?? [];
  const known = profiles.find((p) => p.id === wanted);
  const profile = profiles.find((p) => p.id === picked) ?? known ?? profiles[0];
  const unfinished = active.data ?? null;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Enter" || e.defaultPrevented || !open || unfinished) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "BUTTON" || tag === "INPUT" || tag === "A") return;
      e.preventDefault();
      document.querySelector<HTMLButtonElement>("dialog[open] .btn-primary")?.click();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, unfinished]);

  if (subjects.error) return <div className="page"><ErrorBox error={subjects.error} onRetry={subjects.reload} /></div>;
  if (!subjects.data) return <Loading full label="Đang tải…" />;
  if (!subject) {
    return (
      <div className="page">
        <PageHeader title="Thi thử" description="Bấm giờ như thi thật, xem đáp án sau khi nộp bài." />
        <SubjectPicker subjects={subjects.data} active={unfinished} mode="mock" />
      </div>
    );
  }
  if (!profile) {
    return (
      <div className="page">
        <PageHeader title={`Thi thử ${subject.label}`} />
        <p className="alert alert-info">Môn này chưa có đề thi thử. Bạn có thể <Link href={practiceRoute({ subject: subject.id })}>luyện tập theo chủ đề</Link>.</p>
      </div>
    );
  }

  async function start() {
    if (busy || started.current || !profile) return;
    started.current = true;
    setBusy(true);
    try {
      const s = await getApi().practice.start({ kind: "mock", subject: subject!.id, profile_id: profile.id, ...(profile.above_grade && aboveOk ? { include_above_grade: true } : {}) });
      router.push(sessionRoute(s.id));
    } catch (e) {
      started.current = false;
      setBusy(false);
      const b = blockedFrom(e);
      if (b) setBlocked(b);
      else toast(gradeDetail(e) ?? errorText(e), "error");
    }
  }
  const later = () => {
    setOpen(false);
    router.replace(practiceRoute({ subject: subject.id }));
  };

  return (
    <div className="page page-narrow">
      <PageHeader title={`Thi thử ${subject.label}`} description="Bấm giờ như thi thật, xem đáp án sau khi nộp bài." />
      {wanted && !known && <p className="alert alert-info" role="status">Đề {wanted} không còn nữa, mình chọn đề thi thử gần nhất.</p>}
      {!open && <button type="button" className="btn btn-primary" onClick={() => setOpen(true)}>Mở lại hộp xác nhận</button>}
      <PracticeDialog
        open={open}
        title={`Bắt đầu thi thử ${subject.label}?`}
        onClose={later}
        actions={[
          { label: "Để sau", onClick: later, autoFocus: !!unfinished, hint: unfinished ? "Enter" : "Esc" },
          { label: busy ? "Đang mở…" : "Bắt đầu thi thử", kind: "primary", onClick: () => void start(), autoFocus: !unfinished, disabled: busy || (!!profile.above_grade && !aboveOk), hint: unfinished ? undefined : "Enter" },
        ]}
      >
        {profiles.length > 1 && (
          <fieldset>
            <legend>Đề thi thử</legend>
            <div className="choice-grid">
              {profiles.map((p) => (
                <label key={p.id} className="choice">
                  <input type="radio" name="profile" checked={p.id === profile.id} onChange={() => setPicked(p.id)} />
                  <span className="choice-title">{p.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <p>
          <strong>{profile.item_count} câu</strong> trong <strong>{Math.round(profile.time_limit_sec / 60)} phút</strong>. Đồng hồ chạy ngay khi bắt đầu; đúng/sai và lời giải chỉ hiện sau khi nộp bài. Bạn được đánh dấu câu, đổi đáp án và chuyển câu tự do; hết giờ bài sẽ tự nộp.
        </p>
        <p className="disclaimer">{profile.disclaimer}</p>
        {profile.above_grade && (
          <div className="alert alert-warn">
            <p>{profile.note ?? "Đề này gồm chủ đề lớp trên mà bạn chưa học."}</p>
            <label className="switch">
              <input type="checkbox" role="switch" checked={aboveOk} onChange={(ev) => setAboveOk(ev.target.checked)} />
              <span>Thử cả chủ đề lớp trên</span>
            </label>
          </div>
        )}
        {blocked && <BlockedNotice blocked={blocked} />}
        {unfinished && (
          <p className="alert alert-warn">
            Bài đang làm dở của môn này ({unfinished.items.length} câu) sẽ được kết thúc và lưu kết quả. Vì vậy Enter đang là “Để sau”.
          </p>
        )}
      </PracticeDialog>
    </div>
  );
}

const DIAG_SHORTCUTS: Shortcut[] = [
  { keys: "Enter", description: "Bắt đầu đánh giá" },
  { keys: "S", description: "Bỏ qua, luyện theo chuẩn" },
];

/** `/practice/diagnostic`: start (≤ 12 questions, no feedback) or skip. */
export function DiagnosticEntry() {
  const q = useSearchParams();
  const router = useRouter();
  const toast = useToast();
  usePageShortcuts("practice-diagnostic", "Đánh giá nhanh", DIAG_SHORTCUTS);
  const subjects = useSubjects();
  const subject = subjects.data?.find((s) => s.id === q.get("subject"));
  const [busy, setBusy] = useState(false);
  const [diagBlocked, setDiagBlocked] = useState<{ id: string; kind: string } | null>(null);
  const act = useRef<{ start: () => void; skip: () => void }>({ start: () => {}, skip: () => {} });

  async function start() {
    if (!subject || busy) return;
    setBusy(true);
    try {
      const s = await getApi().practice.start({ kind: "diagnostic", subject: subject.id });
      router.replace(sessionRoute(s.id));
    } catch (e) {
      setBusy(false);
      const b = blockedFrom(e);
      if (b) setDiagBlocked(b);
      else toast(errorText(e), "error");
    }
  }
  async function skip() {
    if (!subject || busy) return;
    setBusy(true);
    try {
      await getApi().practice.skipDiagnostic(subject.id);
      emitTourSignal("diagnostic-skipped");
      router.replace(practiceRoute({ subject: subject.id }));
    } catch (e) {
      setBusy(false);
      toast(errorText(e), "error");
    }
  }
  useEffect(() => {
    act.current = { start: () => void start(), skip: () => void skip() };
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || document.querySelector("dialog[open]")) return;
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "BUTTON" || tag === "A" || tag === "INPUT") return;
      if (e.key === "Enter") act.current.start();
      else if (e.key.toLowerCase() === "s") act.current.skip();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (subjects.error) return <div className="page"><ErrorBox error={subjects.error} onRetry={subjects.reload} /></div>;
  if (!subjects.data) return <Loading full label="Đang tải…" />;
  if (!subject) {
    return (
      <div className="page">
        <PageHeader title="Đánh giá nhanh" description="Chọn môn bạn muốn đánh giá." />
        <ul className="subject-grid">
          {subjects.data.map((s) => (
            <li key={s.id} className="card subject-card">
              <h3>{s.label}</h3>
              <Link href={diagnosticRoute({ subject: s.id })} className="btn btn-primary btn-sm">Chọn</Link>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return (
    <div className="page page-narrow">
      <section className="card diag" aria-labelledby="diag-h">
        <span className="badge badge-ok">Đánh giá nhanh · {subject.label}</span>
        <h1 id="diag-h">Để mình hiểu bạn trước nhé</h1>
        <ul className="diag-list">
          <li><strong>Khoảng 12 câu, 10-15 phút.</strong> Câu trắc nghiệm, 2 câu mỗi chủ đề.</li>
          <li><strong>Không chấm điểm, không hiện đáp án</strong> trong lúc làm. Cứ làm thật lòng, chỗ nào chưa biết thì bỏ trống cũng được.</li>
          <li><strong>Kết quả giúp xếp đề:</strong> chủ đề cần luyện thêm có nhiều câu vừa sức hơn, chủ đề vững được thử thách hơn.</li>
        </ul>
        <div className="row">
          <button type="button" className="btn btn-primary btn-lg" onClick={() => void start()} disabled={busy}>
            Bắt đầu đánh giá <kbd className="keycap keycap-inline">Enter</kbd>
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => void skip()} disabled={busy}>
            Bỏ qua, luyện theo chuẩn <kbd className="keycap keycap-inline">S</kbd>
          </button>
        </div>
        {diagBlocked && <BlockedNotice blocked={diagBlocked} />}
        <p className="hint">Bỏ qua thì đề dùng tỉ lệ độ khó thông thường (nhiều câu nhận biết, ít câu vận dụng cao); bạn có thể đánh giá sau.</p>
      </section>
    </div>
  );
}
