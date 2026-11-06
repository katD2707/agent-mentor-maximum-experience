"""Practice, mock exams and diagnostics: sessions, answers, finishing, progress, recommendations, item reports.

Rules enforced here (server side, whatever the client does; CONTRACTS 10.2/10.3, agent-mentor `exam-modes-and-scoring.md`):
- practice shows correctness after every checked answer, allows one hint per item before the answer is checked, and
  unlocks the explanation (`reveal`) only for answered items; answers are idempotent per (session, position);
- mock and diagnostic keep answers as editable drafts, show nothing until finish, mock allows flags;
- a mock/diagnostic has a wall-clock `deadline`; the first request after it (or the scheduler sweep) finishes the session
  with the drafts it has; late answers are refused;
- finishing is idempotent: it scores, writes the evidence once (one mirror commit), stores the report and returns the
  same report on every later call. Evidence is written *before* the session is marked finished, so a failed commit
  leaves the session active and retryable (event ids are deterministic, so a retry never duplicates).
Positions are 0-based indexes into `Session.items`. Nothing here calls an LLM.
"""

import logging
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select

from mentor_gateway.db import Database
from mentor_gateway.mirror import Mirror
from mentor_gateway.practice import assembler as asm
from mentor_gateway.practice import evidence, recommender, scoring
from mentor_gateway.practice import mastery as bkt
from mentor_gateway.practice.grade import parse_grade
from mentor_gateway.practice.bank import SINGLE, TRUE_FALSE, Bank, Profile
from mentor_gateway.practice.tables import ItemReport, MasterySnapshot, PracticeAnswer, PracticeSession
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)

VN = ZoneInfo("Asia/Ho_Chi_Minh")
MINUTES = (10, 20, 30, 45)
DIAGNOSTIC_SECONDS = 15 * 60
DEADLINE_GRACE_SEC = 2  # autosave racing the last second still counts
REPORTS_PER_DAY = 10
REPORT_REASONS = ("wrong_key", "wrong_solution", "unclear", "typo", "other")
_NO_GRADE_CONTENT = ("Chưa có câu hỏi phù hợp với chương trình lớp {grade} của em; mentor sẽ bổ sung dần. "
                     "Em có thể thử cả chủ đề lớp trên.")
DONE = ("finished", "expired")
TREND_POINTS = 12


class PracticeError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _fmt_score(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


@dataclass
class Plan:
    assembly: asm.Assembly
    params: dict[str, Any]


class PracticeService:
    def __init__(self, db: Database, mirror: Mirror, bank: Bank, clock: Clock) -> None:
        self.db, self.mirror, self.bank, self.clock = db, mirror, bank, clock
        self._profile_ok: dict[str, bool] = {}

    # ---- state read from the workspace ---------------------------------------------------------------

    def _events_text(self, user_id: str) -> str:
        return self.mirror.read_text(user_id, "events.jsonl") or ""

    def _curriculum_text(self, user_id: str, subject: str) -> str | None:
        path = self.bank.curriculum_path(subject)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return self.mirror.read_text(user_id, f".mentor/curricula/{subject}.yaml")

    def mastery(self, user_id: str, subject: str) -> tuple[dict, dict[str, bkt.TopicMastery]]:
        states = bkt.skill_states(self._events_text(user_id), subject, self._curriculum_text(user_id, subject))
        return states, bkt.topic_mastery(self.bank, subject, states)

    # ---- grade filter ----------------------------------------------------------------------------------

    def learner_grade(self, user_id: str) -> int | None:
        """Grade 10-12 parsed from `me/profile.md`; None = unknown, nothing is filtered."""
        return parse_grade(self.mirror.read_text(user_id, "me/profile.md"))

    def _above_topics(self, subject: str, grade: int | None) -> set[str]:
        """Bank topics of the subject whose grade (minimum grade of their skills) is above the learner's."""
        if grade is None:
            return set()
        return {t for t in self.bank.topic_ids(subject)
                if (g := self.bank.topic_grade(subject, t)) is not None and g > grade}

    def _profile_topics(self, profile: Profile) -> set[str]:
        topics = set(profile.topic_matrix)
        for part in profile.parts:
            topics |= set(part.topic_matrix)
        return topics or set(self.bank.topic_ids(profile.subject))

    def _profile_above(self, profile: Profile, above: set[str]) -> list[str]:
        return sorted(self._profile_topics(profile) & above)

    def _above_note(self, subject: str, topics: list[str]) -> str:
        grades = sorted({g for t in topics if (g := self.bank.topic_grade(subject, t)) is not None})
        return f"Đề này gồm chủ đề lớp {grades[-1]} em chưa học" if grades else "Đề này gồm chủ đề em chưa học"

    # ---- catalogue -------------------------------------------------------------------------------------

    def _profile_available(self, profile: Profile) -> bool:
        ok = self._profile_ok.get(profile.id)
        if ok is None:
            try:
                asm.assemble_mock(self.bank, profile, asm.Constraints(time_budget_sec=profile.time_limit_sec), 0)
                ok = True
            except asm.InsufficientContent:
                ok = False
            self._profile_ok[profile.id] = ok
        return ok

    def subjects(self, user_id: str) -> list[dict]:
        from mentor_gateway.practice.topics import SUBJECT_LABELS

        out = []
        grade = self.learner_grade(user_id)
        for subject in self.bank.subjects():
            above = self._above_topics(subject, grade)
            diag = "none"
            with self.db.session() as s:
                last = s.scalars(select(PracticeSession).where(
                    PracticeSession.user_id == user_id, PracticeSession.subject == subject,
                    PracticeSession.kind == "diagnostic", PracticeSession.status.in_((*DONE, "skipped")))
                    .order_by(PracticeSession.started_at.desc())).first()
                if last is not None:
                    diag = "skipped" if last.status == "skipped" else "done"
            out.append({
                "id": subject, "label": SUBJECT_LABELS.get(subject, subject), "learner_grade": grade,
                "topics": [{"id": t, "title": self.bank.topics.get(t).title, "item_count": self.bank.item_count(subject, t),
                            "grade": self.bank.topic_grade(subject, t), "above_grade": t in above}
                           for t in self.bank.topic_ids(subject)],
                "diagnostic": diag,
                "mock_profiles": [
                    self._profile_entry(p, above)
                    for p in self.bank.profiles.values() if p.subject == subject and self._profile_available(p)],
            })
        return out

    def _profile_entry(self, p: Profile, above: set[str]) -> dict:
        entry = {"id": p.id, "label": p.label, "type": p.type, "item_count": p.item_count,
                 "time_limit_sec": p.time_limit_sec, "disclaimer": p.disclaimer, "above_grade": False, "note": None}
        over = self._profile_above(p, above)
        if over:
            entry["above_grade"], entry["note"] = True, self._above_note(p.subject, over)
        return entry

    # ---- planning --------------------------------------------------------------------------------------

    def _check_subject(self, subject: str) -> None:
        if subject not in self.bank.by_subject:
            raise PracticeError(404, "unknown_subject", "Môn học này chưa có câu hỏi.")

    def _recently_seen(self, user_id: str, subject: str) -> dict[str, int]:
        with self.db.session() as s:
            rows = s.scalars(select(PracticeSession).where(
                PracticeSession.user_id == user_id, PracticeSession.subject == subject,
                PracticeSession.status.in_(DONE)).order_by(PracticeSession.started_at.desc()).limit(10)).all()
            seen: dict[str, int] = {}
            for rank, sess in enumerate(rows, start=1):
                for rec in sess.items:
                    seen.setdefault(rec["doc"]["id"], rank)
            return seen

    def _active_rows(self, s, user_id: str, subject: str | None = None) -> list[PracticeSession]:
        q = select(PracticeSession).where(PracticeSession.user_id == user_id, PracticeSession.status == "active")
        if subject:
            q = q.where(PracticeSession.subject == subject)
        return list(s.scalars(q.order_by(PracticeSession.started_at.desc())))

    def _plan_practice(self, user_id: str, subject: str, minutes: int, goal: str, topics: list[str] | None,
                       seed: int, include_above_grade: bool = False) -> Plan:
        self._check_subject(subject)
        if minutes not in MINUTES:
            raise PracticeError(422, "bad_minutes", f"Thời lượng phải là một trong {', '.join(map(str, MINUTES))} phút.")
        if goal not in asm.GOALS:
            raise PracticeError(422, "bad_goal", "Mục tiêu phải là balanced, weak hoặc challenge.")
        known = set(self.bank.topic_ids(subject))
        if topics and not set(topics) <= known:
            raise PracticeError(422, "unknown_topic", "Chủ đề không có trong môn này.")
        grade = self.learner_grade(user_id)
        above = set() if include_above_grade else self._above_topics(subject, grade)
        topic_filter = set(topics) if topics else None
        if above:
            if topic_filter and topic_filter & above:
                raise PracticeError(422, "above_grade_topic",
                                    "Có chủ đề lớp trên em chưa học; bật \"Thử cả chủ đề lớp trên\" nếu muốn luyện.",
                                    topics=sorted(topic_filter & above))
            if not topic_filter:
                topic_filter = known - above
            if not topic_filter:
                raise PracticeError(422, "insufficient_content", _NO_GRADE_CONTENT.format(grade=grade),
                                    available=0, required=5)
        _, topic_m = self.mastery(user_id, subject)
        with self.db.session() as s:  # the items of the practice session this one replaces are left out
            exclude = {rec["doc"]["id"] for sess in self._active_rows(s, user_id, subject) if sess.kind == "practice"
                       for rec in sess.items}
        c = asm.Constraints(time_budget_sec=minutes * 60, goal=goal, topic_filter=topic_filter,
                            exclude_ids=exclude, recently_seen=self._recently_seen(user_id, subject))
        try:
            a = asm.assemble_practice(self.bank, subject, topic_m, c, seed)
        except asm.InsufficientContent as exc:
            msg = _NO_GRADE_CONTENT.format(grade=grade) if above else exc.message
            raise PracticeError(422, "insufficient_content", msg, available=exc.available,
                                required=exc.required) from exc
        return Plan(a, {"minutes": minutes, "goal": goal, "topics": sorted(topics or []),
                        "include_above_grade": include_above_grade})

    def preview(self, user_id: str, subject: str, minutes: int, goal: str, topics: list[str] | None,
                seed: int | None = None, include_above_grade: bool = False) -> dict:
        seed = secrets.randbelow(2**31) if seed is None else seed
        a = self._plan_practice(user_id, subject, minutes, goal, topics, seed, include_above_grade).assembly
        return {"seed": seed, "item_count": len(a.items), "minutes": minutes, "level_mix": a.level_mix(),
                "per_topic": [{"topic": t, "title": self.bank.topics.get(t).title, "count": n}
                              for t, n in a.per_topic().items()]}

    # ---- starting ----------------------------------------------------------------------------------------

    def start(self, user_id: str, body: dict[str, Any]) -> dict:
        kind, subject = body["kind"], body["subject"]
        self._check_subject(subject)
        self._finish_due(user_id)
        with self.db.session() as s:
            active = self._active_rows(s, user_id, subject)
            blocking = next((x for x in active if x.kind != "practice"), None)
            if blocking is not None:
                raise PracticeError(409, "active_session", "Bạn đang có một bài làm dở trong môn này.",
                                    session_id=blocking.id, kind=blocking.kind)
            old_practice = [x.id for x in active]
        seed = body.get("seed")
        seed = secrets.randbelow(2**31) if seed is None else int(seed)
        now = self.clock()
        deadline = None
        profile: Profile | None = None
        if kind == "practice":
            plan = self._plan_practice(user_id, subject, int(body.get("minutes") or 20), body.get("goal") or "balanced",
                                       body.get("topics"), seed, bool(body.get("include_above_grade")))
        elif kind == "mock":
            above = self._above_topics(subject, self.learner_grade(user_id))
            opt_in = bool(body.get("include_above_grade"))
            profile = self.bank.profiles.get(body.get("profile_id") or "") or next(
                (p for p in self.bank.profiles.values() if p.subject == subject and self._profile_available(p)
                 and (opt_in or not self._profile_above(p, above))), None)
            if profile is None or profile.subject != subject:
                raise PracticeError(404, "unknown_profile", "Không tìm thấy đề thi thử này.")
            over = self._profile_above(profile, above)
            if over and not opt_in:
                raise PracticeError(422, "above_grade", self._above_note(subject, over)
                                    + "; bật \"Thử cả chủ đề lớp trên\" nếu muốn làm đề này.", topics=over)
            c = asm.Constraints(time_budget_sec=profile.time_limit_sec, recently_seen=self._recently_seen(user_id, subject))
            try:
                plan = Plan(asm.assemble_mock(self.bank, profile, c, seed),
                            {"profile": profile.id, "include_above_grade": opt_in})
            except asm.InsufficientContent as exc:
                raise PracticeError(422, "insufficient_content", exc.message, available=exc.available,
                                    required=exc.required) from exc
            deadline = now + timedelta(seconds=profile.time_limit_sec)
        elif kind == "diagnostic":
            grade = self.learner_grade(user_id)
            above = self._above_topics(subject, grade)
            try:
                plan = Plan(asm.assemble_diagnostic(self.bank, subject, seed, exclude_topics=above), {})
            except asm.InsufficientContent as exc:
                msg = _NO_GRADE_CONTENT.format(grade=grade) if above else exc.message
                raise PracticeError(422, "insufficient_content", msg, available=exc.available,
                                    required=exc.required) from exc
            deadline = now + timedelta(seconds=DIAGNOSTIC_SECONDS)
        else:
            raise PracticeError(422, "bad_kind", "kind phải là practice, mock hoặc diagnostic.")
        for old in old_practice:  # assembled first, so the new set equals the preview; then the old one is scored
            self.finish(user_id, old)
        items = [self._record(i, sel) for i, sel in enumerate(plan.assembly.items)]
        policy = scoring.policy_for({sel.item.type for sel in plan.assembly.items}, profile.scoring if profile else None)
        params = {**plan.params, "assembler": plan.assembly.version, "scoring": policy}
        parts = None
        if profile and profile.parts:
            parts = [{"part": p.part, "label": p.label, "type": p.type, "points_each": p.points_per_item,
                      "positions": [r["position"] for r in items if r["part"] == p.part]} for p in profile.parts]
        sid = f"p-{secrets.token_hex(6)}"
        with self.db.session() as s:
            s.add(PracticeSession(id=sid, user_id=user_id, kind=kind, subject=subject, status="active",
                                  profile_id=profile.id if profile else None, seed=seed, params=params, items=items,
                                  parts=parts, position=0, started_at=now, deadline=deadline, total=len(items)))
        return self.get(user_id, sid)

    def _record(self, position: int, sel: asm.Selected) -> dict:
        it = sel.item
        return {"position": position, "doc": it.doc, "topic": it.topic, "level": it.level, "part": sel.part,
                "points_each": sel.points_each, "seconds": it.seconds, "skill_ids": list(it.skill_ids)}

    def skip_diagnostic(self, user_id: str, subject: str) -> None:
        self._check_subject(subject)
        now = self.clock()
        with self.db.session() as s:
            s.add(PracticeSession(id=f"p-{secrets.token_hex(6)}", user_id=user_id, kind="diagnostic", subject=subject,
                                  status="skipped", started_at=now, finished_at=now, items=[], params={}))

    # ---- views -------------------------------------------------------------------------------------------

    def _client_item(self, rec: dict) -> dict:
        doc = rec["doc"]
        out: dict[str, Any] = {
            "position": rec["position"], "id": doc["id"], "type": doc["type"], "stem": doc["stem"],
            "assets": doc.get("assets") or [], "topic": rec["topic"], "topic_title": self.bank.topics.get(rec["topic"]).title,
            "level": rec["level"], "estimated_seconds": rec["seconds"],
        }
        if doc["type"] == SINGLE:
            out["options"] = [{"id": o["id"], "text": o["text"]} for o in doc["options"]]
        elif doc["type"] == TRUE_FALSE:
            out["statements"] = [{"id": st["id"], "text": st["text"]} for st in doc["statements"]]
        else:
            sa = doc["short_answer"]
            out["short_answer"] = {"max_chars": int(sa.get("max_chars") or 6), "unit": sa.get("unit"),
                                   "decimals": sa.get("decimals")}
        return out

    def _result(self, rec: dict, row: PracticeAnswer) -> dict:
        doc = rec["doc"]
        res: dict[str, Any] = {"correct": row.correct, "points": row.points, "max_points": rec["points_each"],
                               "correct_answer": scoring.correct_answer_text(doc)}
        if doc["type"] == SINGLE and row.answer and row.correct is False:
            fb = (doc.get("option_feedback") or {}).get(row.answer.strip().upper())
            if fb:
                res["option_feedback"] = fb
        if row.statement_results is not None:
            res["statement_results"] = row.statement_results
        return res

    def _remaining(self, sess: PracticeSession) -> int | None:
        if sess.deadline is None or sess.status != "active":
            return None
        return max(0, int((sess.deadline - self.clock()).total_seconds()))

    def _view(self, sess: PracticeSession, rows: dict[int, PracticeAnswer]) -> dict:
        answers: dict[str, Any] = {}
        done = sess.status in DONE
        for pos, row in rows.items():
            rec = sess.items[pos]
            v: dict[str, Any] = {"flagged": row.flagged, "checked": row.checked, "hints_seen": row.hints_seen}
            if sess.kind == "practice":
                if row.checked:
                    v.update(answer=row.answer, correct=row.correct, result=self._result(rec, row), revealed=row.revealed)
                elif row.hints_seen:
                    v["hint"] = rec["doc"].get("hint") or ""
            else:
                if row.draft and not done:
                    v["draft"] = row.draft
                if done:
                    v.update(answer=row.answer, correct=row.correct)
            answers[str(pos)] = v
        position = sess.position
        if sess.kind == "practice" and sess.status == "active":  # reopen at the first unanswered item
            position = next((i for i in range(len(sess.items)) if not (i in rows and rows[i].checked)), len(sess.items) - 1)
        view: dict[str, Any] = {
            "id": sess.id, "kind": sess.kind, "subject": sess.subject, "profile_id": sess.profile_id, "status": sess.status,
            "started_at": _iso(sess.started_at), "finished_at": _iso(sess.finished_at), "deadline": _iso(sess.deadline),
            "remaining_sec": self._remaining(sess), "position": max(0, position),
            "items": [self._client_item(r) for r in sess.items], "answers": answers, "minutes": sess.params.get("minutes"),
            "goal": sess.params.get("goal"),
        }
        if sess.parts:
            view["parts"] = [{"label": p["label"], "positions": p["positions"], "points_each": p["points_each"]} for p in sess.parts]
        if sess.profile_id and sess.profile_id in self.bank.profiles:
            view["disclaimer"] = self.bank.profiles[sess.profile_id].disclaimer
        return view

    def _rows(self, s, sid: str) -> dict[int, PracticeAnswer]:
        return {r.position: r for r in s.scalars(select(PracticeAnswer).where(PracticeAnswer.session_id == sid))}

    def _summary(self, sess: PracticeSession) -> dict:
        return {"id": sess.id, "kind": sess.kind, "subject": sess.subject, "started_at": _iso(sess.started_at),
                "finished_at": _iso(sess.finished_at), "score_10": sess.score_10, "correct": sess.correct,
                "total": sess.total, "minutes": sess.minutes}

    def _load(self, s, user_id: str, sid: str) -> PracticeSession:
        sess = s.get(PracticeSession, sid)
        if sess is None or sess.user_id != user_id:
            raise PracticeError(404, "not_found", "Không tìm thấy bài làm này.")
        return sess

    def _due(self, sess: PracticeSession) -> bool:
        return (sess.status == "active" and sess.deadline is not None
                and self.clock() > sess.deadline + timedelta(seconds=DEADLINE_GRACE_SEC))

    def get(self, user_id: str, sid: str) -> dict:
        with self.db.session() as s:
            due = self._due(self._load(s, user_id, sid))
        if due:
            self.finish(user_id, sid, expired=True)
        with self.db.session() as s:
            sess = self._load(s, user_id, sid)
            return self._view(sess, self._rows(s, sid))

    def active(self, user_id: str, subject: str | None) -> dict | None:
        self._finish_due(user_id)
        with self.db.session() as s:
            rows = self._active_rows(s, user_id, subject)
            return self._view(rows[0], self._rows(s, rows[0].id)) if rows else None

    def _live(self, s, user_id: str, sid: str) -> PracticeSession:
        """Session for a write: 404/409 unless it is active and in time (a late request finishes it first)."""
        sess = self._load(s, user_id, sid)
        if self._due(sess):
            raise _Expired
        if sess.status != "active":
            raise PracticeError(409, "finished", "Bài làm này đã kết thúc.")
        return sess

    def _write(self, user_id: str, sid: str, fn):
        """Run `fn(session, sess)` in one transaction; finish the session first when its deadline has passed."""
        try:
            with self.db.session() as s:
                return fn(s, self._live(s, user_id, sid))
        except _Expired:
            self.finish(user_id, sid, expired=True)
            raise PracticeError(409, "expired", "Đã hết giờ; bài làm đã được nộp tự động.") from None

    def _row(self, s, sess: PracticeSession, position: int) -> PracticeAnswer:
        if not 0 <= position < len(sess.items):
            raise PracticeError(422, "bad_position", "Vị trí câu hỏi không hợp lệ.")
        row = s.get(PracticeAnswer, (sess.id, position))
        if row is None:
            row = _new_row(sess.id, position, sess.user_id)
            s.add(row)
        return row

    # ---- answering ---------------------------------------------------------------------------------------

    def answer(self, user_id: str, sid: str, position: int, answer: str | None, time_spent_sec: int) -> dict:
        def run(s, sess: PracticeSession) -> dict:
            row = self._row(s, sess, position)
            rec = sess.items[position]
            row.time_spent_sec = max(row.time_spent_sec, max(0, min(int(time_spent_sec), 6 * 3600)))
            if sess.kind != "practice":
                row.draft = (answer or "").strip() or None
                sess.position = position
                return {"saved": True}
            if row.checked:  # idempotent: a replayed or double-clicked submit is not scored twice
                return self._result(rec, row)
            sc = scoring.score_item(rec["doc"], answer)
            row.answer = (answer or "").strip() or None
            row.checked, row.correct, row.points, row.answered_at = True, sc.correct, sc.points, self.clock()
            if rec["doc"]["type"] == TRUE_FALSE:
                given = scoring.parse_truths(answer) or [None] * 4
                row.statement_results = [
                    {"id": st["id"], "given": given[i], "truth": bool(st["truth"]), "correct": given[i] == st["truth"],
                     **({"explanation": st["explanation"]} if st.get("explanation") else {})}
                    for i, st in enumerate(rec["doc"]["statements"])]
            sess.position = position
            return self._result(rec, row)

        return self._write(user_id, sid, run)

    def hint(self, user_id: str, sid: str, position: int) -> dict:
        def run(s, sess: PracticeSession) -> dict:
            if sess.kind != "practice":
                raise PracticeError(403, "hints_locked", "Không có gợi ý trong chế độ này.")
            row = self._row(s, sess, position)
            if row.checked:
                raise PracticeError(409, "already_answered", "Câu này đã được kiểm tra.")
            row.hints_seen = max(row.hints_seen, 1)  # one hint per item; counted in the evidence and the report
            return {"hint": sess.items[position]["doc"].get("hint") or ""}

        return self._write(user_id, sid, run)

    def reveal(self, user_id: str, sid: str, position: int) -> dict:
        with self.db.session() as s:
            sess = self._load(s, user_id, sid)
            if sess.kind != "practice":
                raise PracticeError(403, "reveal_locked", "Lời giải chỉ mở sau khi nộp bài.")
            row = self._row(s, sess, position)
            if not row.checked:
                raise PracticeError(409, "not_answered", "Hãy trả lời câu này trước khi xem lời giải.")
            row.revealed = True
            return self._explanation(sess.items[position]["doc"])

    @staticmethod
    def _explanation(doc: dict) -> dict:
        out: dict[str, Any] = {"explanation": doc.get("explanation") or ""}
        if doc.get("tip"):
            out["tip"] = doc["tip"]
        return out

    def flag(self, user_id: str, sid: str, position: int, flagged: bool) -> dict:
        def run(s, sess: PracticeSession) -> dict:
            if sess.kind != "mock":
                raise PracticeError(403, "flag_locked", "Chỉ đánh dấu câu trong thi thử.")
            self._row(s, sess, position).flagged = flagged
            return {"ok": True}

        return self._write(user_id, sid, run)

    def tick(self, user_id: str, sid: str, position: int, elapsed_sec: int) -> dict:
        """Autosave: `elapsed_sec` = seconds spent on item `position` so far; the server clock rules the deadline."""
        try:
            def run(s, sess: PracticeSession) -> dict:
                row = self._row(s, sess, position)
                if not row.checked:
                    row.time_spent_sec = max(row.time_spent_sec, max(0, min(int(elapsed_sec), 6 * 3600)))
                sess.position = position
                rem = self._remaining(sess)
                return {} if rem is None else {"remaining_sec": rem}

            return self._write(user_id, sid, run)
        except PracticeError as exc:
            if exc.code in ("expired", "finished"):  # the client's timer and ours disagree: tell it to go to the report
                return {"remaining_sec": 0, "expired": True}
            raise

    # ---- finishing ---------------------------------------------------------------------------------------

    def _finish_due(self, user_id: str | None = None) -> int:
        with self.db.session() as s:
            q = select(PracticeSession).where(PracticeSession.status == "active", PracticeSession.deadline.is_not(None))
            if user_id:
                q = q.where(PracticeSession.user_id == user_id)
            due = [(x.user_id, x.id) for x in s.scalars(q) if self._due(x)]
        n = 0
        for uid, sid in due:
            try:
                self.finish(uid, sid, expired=True)
                n += 1
            except Exception:
                log.exception("auto-finishing practice session %s", sid)
        return n

    def sweep(self) -> int:
        """Scheduler hook: finish every mock/diagnostic whose deadline has passed."""
        return self._finish_due()

    def finish(self, user_id: str, sid: str, expired: bool = False) -> dict:
        with self.mirror.locks.get(user_id):  # serialises double submits and the sandbox's own commits
            return self._finish_locked(user_id, sid, expired)

    def _finish_locked(self, user_id: str, sid: str, expired: bool) -> dict:
        with self.db.session() as s:
            sess = self._load(s, user_id, sid)
            if sess.status != "active":
                return self._stored_report(sess)
            rows = self._rows(s, sid)
            now = self.clock()
            scored = self._score_all(s, sess, rows)
            ev_rows = [{"position": p, "skill_ids": sess.items[p]["skill_ids"], "correct": r.correct, "hints": r.hints_seen}
                       for p, r in sorted(rows.items()) if r.correct is not None]
            if sess.kind == "practice" and not any(r.checked for r in rows.values()):
                sess.status, sess.finished_at, sess.evidence_done = "abandoned", now, True
                sess.report = self._report(sess, [], {}, {}, scored, now, rows)
                return sess.report
            line = self._log_line(sess, scored, rows, now)
            events = evidence.make_events(sess.id, sess.subject, ev_rows, now)
            try:
                before_states, after_states = evidence.commit_session_evidence(
                    self.mirror, user_id, sess.subject, sess.id, events, now.astimezone(VN).date(), line,
                    self.bank.curriculum_path(sess.subject))
            except Exception as exc:
                log.exception("practice evidence of %s failed", sid)
                raise PracticeError(503, "evidence_failed", "Chưa lưu được kết quả, hãy thử lại sau ít giây.") from exc
            before = bkt.topic_mastery(self.bank, sess.subject, before_states)
            after = bkt.topic_mastery(self.bank, sess.subject, after_states)
            touched = {sid_ for r in ev_rows for sid_ in r["skill_ids"]}
            for skill in sorted(touched):
                st = after_states.get(skill)
                if st is not None:
                    s.add(MasterySnapshot(user_id=user_id, subject=sess.subject, skill_id=skill, mastery=st.mastery,
                                          at=now, session_id=sess.id))
            sess.status = "expired" if expired else "finished"
            sess.finished_at, sess.evidence_done = now, True
            sess.correct, sess.total = scored["correct"], scored["total"]
            sess.score_10, sess.minutes = scored["score_10"], scored["minutes"]
            report = self._report(sess, ev_rows, before, after, scored, now, rows)
            sess.report = report
        report["recommendations"] = self._recs_for_report(user_id, sess.subject)
        with self.db.session() as s:
            s.get(PracticeSession, sid).report = report
        return report

    def _score_all(self, s, sess: PracticeSession, rows: dict[int, PracticeAnswer]) -> dict:
        """Score drafts (mock/diagnostic; practice rows are already scored) and summarise the session."""
        now = self.clock()
        total_points = max_points = 0.0
        correct = 0
        for rec in sess.items:
            pos = rec["position"]
            if sess.kind != "practice":
                row = rows.get(pos)
                if row is None:
                    row = _new_row(sess.id, pos, sess.user_id)
                    rows[pos] = row
                    s.add(row)
                sc = scoring.score_item(rec["doc"], row.draft, rec["points_each"])
                row.answer, row.correct, row.points = row.draft, sc.correct, sc.points
                if rec["doc"]["type"] == TRUE_FALSE:
                    row.statement_results = [
                        {"id": st["id"], "given": (scoring.parse_truths(row.draft) or [None] * 4)[i], "truth": bool(st["truth"]),
                         "correct": sc.statement_correct[i] if sc.statement_correct else False}
                        for i, st in enumerate(rec["doc"]["statements"])]
                row.answered_at = row.answered_at or (now if sc.correct is not None else None)
            row = rows.get(pos)
            if row is not None:
                total_points += row.points or 0.0
                correct += 1 if row.correct else 0
            max_points += rec["points_each"]
        answered = sum(1 for r in rows.values() if r.correct is not None)
        spent = sum(r.time_spent_sec for r in rows.values())
        if sess.kind == "mock":
            end = min(self.clock(), sess.deadline) if sess.deadline else self.clock()
            seconds = int((end - sess.started_at).total_seconds())
        else:
            seconds = spent or min(int((self.clock() - sess.started_at).total_seconds()), sum(r["seconds"] for r in sess.items))
        profile = self.bank.profiles.get(sess.profile_id or "")
        score_10 = scoring.scaled(total_points, max_points, profile.max_score if profile else 10.0) if sess.kind == "mock" else None
        total = len(sess.items) if sess.kind == "mock" else answered
        return {"correct": correct, "total": total, "answered": answered, "score_10": score_10, "points": total_points,
                "max_points": max_points, "minutes": max(1, math.ceil(seconds / 60)) if answered else 0,
                "hints": sum(r.hints_seen for r in rows.values())}

    def _log_line(self, sess: PracticeSession, scored: dict, rows: dict[int, PracticeAnswer], now: datetime) -> str:
        local = now.astimezone(VN)
        topics: list[str] = []
        for rec in sess.items:
            row = rows.get(rec["position"])
            if sess.kind == "mock" or (row is not None and row.correct is not None):
                short = self.bank.topics.get(rec["topic"]).short
                if short not in topics:
                    topics.append(short)
        head = f"- {local:%Y-%m-%d %H:%M} · "
        if sess.kind == "practice":
            body = (f"luyện tập {sess.params.get('minutes', scored['minutes'])} phút · {scored['correct']}/{scored['answered']} đúng"
                    f" · {scored['hints']} gợi ý")
        elif sess.kind == "mock":
            body = f"thi thử · {_fmt_score(scored['score_10'] or 0)}/10 · {scored['correct']}/{scored['total']} đúng"
        else:
            body = f"đánh giá nhanh · {scored['correct']}/{scored['answered']} đúng"
        return f"{head}{body} · chủ đề: {', '.join(topics) or '—'} · session {sess.id}"

    def _report(self, sess: PracticeSession, ev_rows: list[dict], before: dict, after: dict, scored: dict,
                now: datetime, answers: dict[int, PracticeAnswer]) -> dict:
        per: dict[str, dict] = {}
        rows = {r["position"]: r for r in ev_rows}
        for rec in sess.items:
            t = rec["topic"]
            e = rows.get(rec["position"])
            if e is None and sess.kind != "mock":
                continue
            d = per.setdefault(t, {"topic": t, "title": self.bank.topics.get(t).title, "right": 0, "total": 0})
            d["total"] += 1
            d["right"] += 1 if e and e["correct"] else 0
        for t, d in per.items():
            b, a = before.get(t), after.get(t)
            d["mastery_before"] = round(b.mastery, 3) if b and b.mastery is not None else None
            d["mastery_after"] = round(a.mastery, 3) if a and a.mastery is not None else None
            d["label"] = a.label if a else bkt.LABEL_UNKNOWN
        report: dict[str, Any] = {
            "session": self._summary(sess) | {"status": sess.status}, "correct": scored["correct"], "total": scored["total"],
            "answered": scored["answered"], "score_10": scored["score_10"], "minutes": scored["minutes"],
            "hints": scored["hints"], "per_topic": list(per.values()), "recommendations": [],
        }
        report["session"].update(correct=scored["correct"], total=scored["total"], score_10=scored["score_10"],
                                 minutes=scored["minutes"], finished_at=_iso(now))
        if sess.parts:
            report["per_part"] = self._per_part(sess, answers)
        if sess.profile_id and sess.profile_id in self.bank.profiles:
            report["disclaimer"] = self.bank.profiles[sess.profile_id].disclaimer
        return report

    @staticmethod
    def _per_part(sess: PracticeSession, rows: dict[int, PracticeAnswer]) -> list[dict]:
        out = []
        for p in sess.parts or []:
            rs = [rows.get(pos) for pos in p["positions"]]
            out.append({"part": p["part"], "label": p["label"], "total": len(rs),
                        "answered": sum(1 for r in rs if r and r.correct is not None),
                        "correct": sum(1 for r in rs if r and r.correct), "points": round(sum((r.points if r else 0) for r in rs), 4),
                        "max_points": round(p["points_each"] * len(rs), 4)})
        return out

    def _stored_report(self, sess: PracticeSession) -> dict:
        if sess.report is None:
            raise PracticeError(409, "no_report", "Bài làm này không có báo cáo.")
        return sess.report

    # ---- review ------------------------------------------------------------------------------------------

    def review(self, user_id: str, sid: str) -> list[dict]:
        with self.db.session() as s:
            sess = self._load(s, user_id, sid)
            if sess.status not in DONE:
                raise PracticeError(409, "not_finished", "Chỉ xem lại được bài đã kết thúc.")
            rows = self._rows(s, sid)
            out = []
            for rec in sess.items:
                doc, row = rec["doc"], rows.get(rec["position"])
                item = self._client_item(rec)
                if doc["type"] == TRUE_FALSE:
                    item["statements"] = [{"id": st["id"], "text": st["text"], "truth": bool(st["truth"]),
                                           "explanation": st.get("explanation")} for st in doc["statements"]]
                item.update(
                    answer=row.answer if row else None, correct=row.correct if row else None, points=row.points if row else 0.0,
                    max_points=rec["points_each"], hints_seen=row.hints_seen if row else 0, flagged=bool(row and row.flagged),
                    time_spent_sec=row.time_spent_sec if row else 0, correct_answer=scoring.correct_answer_text(doc),
                    hint=doc.get("hint"), option_feedback=doc.get("option_feedback") or {},
                    statement_results=row.statement_results if row else None, skills=rec["skill_ids"], **self._explanation(doc))
                out.append(item)
            return out

    def history(self, user_id: str, subject: str | None, limit: int) -> list[dict]:
        with self.db.session() as s:
            q = select(PracticeSession).where(PracticeSession.user_id == user_id, PracticeSession.status.in_(DONE))
            if subject:
                q = q.where(PracticeSession.subject == subject)
            return [self._summary(x) for x in s.scalars(q.order_by(PracticeSession.started_at.desc()).limit(limit))]

    # ---- progress and recommendations --------------------------------------------------------------------

    def progress(self, user_id: str, subject: str | None) -> dict:
        subjects = [subject] if subject else self.bank.subjects()
        skills_out, topics_out = [], []
        for sub in subjects:
            states, topic_m = self.mastery(user_id, sub)
            with self.db.session() as s:
                snaps = s.scalars(select(MasterySnapshot).where(MasterySnapshot.user_id == user_id, MasterySnapshot.subject == sub)
                                  .order_by(MasterySnapshot.at, MasterySnapshot.id)).all()
            trend: dict[str, list] = {}
            for sn in snaps:
                trend.setdefault(sn.skill_id, []).append({"at": _iso(sn.at), "mastery": round(sn.mastery, 3)})
            ids = set(states) | {sid for it in self.bank.by_subject.get(sub, []) for sid in it.skill_ids}
            for sid in sorted(ids):
                st = states.get(sid)
                topic = self.bank.skill_topic(sub, sid)
                ev = st.mastery_attempts if st else 0
                skills_out.append({
                    "skill_id": sid, "subject": sub, "title": self.bank.skill_title(sub, sid), "topic": topic,
                    "mastery": round(st.mastery, 3) if st and ev else None, "evidence": ev,
                    "guided": st.guided_attempts if st else 0, "confidence": bkt.confidence_for(ev),
                    "label": bkt.skill_label(st), "trend": trend.get(sid, [])[-TREND_POINTS:]})
            for t in self.bank.topic_ids(sub):
                m = topic_m.get(t) or bkt.TopicMastery(t, None, 0)
                topics_out.append({"topic": t, "subject": sub, "title": self.bank.topics.get(t).title,
                                   "mastery": round(m.mastery, 3) if m.mastery is not None else None, "evidence": m.evidence,
                                   "confidence": m.confidence, "label": m.label})
        return {"skills": skills_out, "topics": topics_out}

    def _history_for(self, user_id: str, subject: str) -> recommender.History:
        today = self.clock().astimezone(VN).date()
        with self.db.session() as s:
            mine = s.scalars(select(PracticeSession).where(PracticeSession.user_id == user_id)
                             .order_by(PracticeSession.started_at)).all()
            minutes_today = 0
            for x in mine:
                if x.kind == "diagnostic" and x.status == "skipped":
                    continue
                if x.status in DONE and x.finished_at and x.finished_at.astimezone(VN).date() == today:
                    minutes_today += x.minutes
                elif x.status == "active" and x.started_at.astimezone(VN).date() == today:
                    spent = s.scalar(select(func.coalesce(func.sum(PracticeAnswer.time_spent_sec), 0)).where(
                        PracticeAnswer.session_id == x.id)) or 0
                    minutes_today += int(spent) // 60
            sub = [x for x in mine if x.subject == subject]
            diag = [x for x in sub if x.kind == "diagnostic" and x.status in (*DONE, "skipped")]
            since = 0
            if diag:
                last = diag[-1].started_at
                since = sum(1 for x in sub if x.status in DONE and x.kind != "diagnostic" and x.started_at > last)
            practice_done = sum(1 for x in sub if x.kind == "practice" and x.status in DONE)
        return recommender.History(bool(diag), since, practice_done, minutes_today)

    def _recs_for_report(self, user_id: str, subject: str) -> list[dict]:
        return self.recommendations(user_id, subject)

    def recommendations(self, user_id: str, subject: str | None) -> list[dict]:
        per_subject: list[list[dict]] = []
        for sub in ([subject] if subject else self.bank.subjects()):
            self._check_subject(sub)
            _, topic_m = self.mastery(user_id, sub)
            above = self._above_topics(sub, self.learner_grade(user_id))
            topics = [recommender.TopicInput(t, self.bank.topics.get(t).short, self.bank.topics.get(t).weight,
                                             topic_m.get(t) or bkt.TopicMastery(t, None, 0))
                      for t in self.bank.topic_ids(sub) if t not in above]
            mock = next((p.id for p in self.bank.profiles.values() if p.subject == sub and self._profile_available(p)
                         and not self._profile_above(p, above)), None)
            per_subject.append(recommender.recommend(sub, topics, self._history_for(user_id, sub), mock))
        if len(per_subject) == 1:
            return per_subject[0]
        merged, seen_break = [], False  # one TAKE_A_BREAK at most, then round-robin across subjects
        for i in range(3):
            for recs in per_subject:
                if i < len(recs):
                    if recs[i]["code"] == "TAKE_A_BREAK":
                        if seen_break:
                            continue
                        seen_break = True
                    merged.append(recs[i])
        return merged[:3]

    # ---- item reports ------------------------------------------------------------------------------------

    def report_item(self, user_id: str, item_id: str, session_id: str, reason: str, note: str | None) -> dict:
        if reason not in REPORT_REASONS:
            raise PracticeError(422, "bad_reason", "Lý do không hợp lệ.")
        now = self.clock()
        with self.db.session() as s:
            sess = self._load(s, user_id, session_id)
            pos = next((r["position"] for r in sess.items if r["doc"]["id"] == item_id), None)
            if pos is None:
                raise PracticeError(404, "not_found", "Câu hỏi không thuộc bài làm này.")
            row = s.get(PracticeAnswer, (sess.id, pos))
            shown = sess.status in DONE or (sess.kind == "practice" and row is not None and row.checked)
            if not shown:
                raise PracticeError(409, "answer_not_shown", "Chỉ báo lỗi được sau khi đã xem đáp án của câu này.")
            dup = s.scalars(select(ItemReport).where(
                ItemReport.user_id == user_id, ItemReport.item_id == item_id, ItemReport.session_id == session_id,
                ItemReport.reason == reason)).first()
            if dup is not None:
                return {"id": dup.id, "status": dup.status}
            day = now.astimezone(VN).date()
            start = datetime(day.year, day.month, day.day, tzinfo=VN).astimezone(UTC)
            today = s.scalar(select(func.count()).select_from(ItemReport).where(
                ItemReport.user_id == user_id, ItemReport.created_at >= start)) or 0
            if today >= REPORTS_PER_DAY:
                raise PracticeError(429, "report_limit", f"Mỗi ngày chỉ báo lỗi được {REPORTS_PER_DAY} câu.")
            rep = ItemReport(user_id=user_id, item_id=item_id, session_id=session_id, reason=reason,
                             note=(note or "").strip()[:500], created_at=now)
            s.add(rep)
            s.flush()
            return {"id": rep.id, "status": rep.status}

    def list_reports(self, user_id: str) -> list[dict]:
        with self.db.session() as s:
            rows = s.scalars(select(ItemReport).where(ItemReport.user_id == user_id).order_by(ItemReport.id.desc())).all()
            return [{"id": r.id, "item_id": r.item_id, "session_id": r.session_id, "reason": r.reason, "note": r.note,
                     "status": r.status, "created_at": _iso(r.created_at)} for r in rows]

    # ---- account deletion ---------------------------------------------------------------------------------

    def forget(self, s, user_id: str) -> None:
        """Delete everything of a learner (called inside the account-deletion transaction)."""
        for model in (PracticeAnswer, MasterySnapshot, ItemReport, PracticeSession):
            s.execute(delete(model).where(model.user_id == user_id))


def _new_row(session_id: str, position: int, user_id: str) -> PracticeAnswer:
    """Column defaults only apply at flush; the engine reads the row before that."""
    return PracticeAnswer(session_id=session_id, position=position, user_id=user_id, flagged=False, checked=False,
                          hints_seen=0, revealed=False, time_spent_sec=0, points=0.0)


class _Expired(Exception):
    pass
