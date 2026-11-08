"""Luyện tập from the student's own courses and the bank (P5-A): the default "10 câu" session, "Theo khóa học" practice, the
`/practice/home` payload, and the one-line takeaway of a result. Mixed into `PracticeService`. No LLM anywhere.

What is chosen (`mixed-v1`, deterministic per seed): the candidates are the quiz items of the lessons the student has
studied (pinned version of each enrollment) plus bank items on weak skills or due for review. Each candidate scores
points for: FSRS due (the planner's `fsrs_items.due_items` over `planner.events.load`, called, not changed), answered
wrongly last time, weak skill (BKT mastery < 0.5 with evidence), belonging to the lesson(s) being studied now, never
seen; minus a repeat penalty and a distance from the difficulty that suits the learner's mastery (target P(correct)
0.70, same axis as the bank's assembler). Greedy pick under a per-lesson cap (40 %) and, when courses supply items, a bank
cap (30 %). The count and minutes follow the age band: g1_5 5 items / 6 min (picture, tap and single-choice first),
g6_9 8 / 10, g10_12 and uni 10 / 12.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from mentor_gateway.db import User
from mentor_gateway.planner import events as planner_events
from mentor_gateway.planner import fsrs_items
from mentor_gateway.practice import assembler as asm
from mentor_gateway.practice import mastery as bkt
from mentor_gateway.practice.bank import LOCATION_PER_LEVEL, Item
from mentor_gateway.practice.sources import SEPARATOR, CourseBundle, load_bundles, slug
from mentor_gateway.practice.tables import PracticeSession
from mentor_gateway.practice.topics import SUBJECT_LABELS

VN = ZoneInfo("Asia/Ho_Chi_Minh")
VERSION = "mixed-v1"
MIN_ITEMS = 3
# band -> (items, minutes) of the default session
BAND_SESSION = {"g1_5": (5, 6), "g6_9": (8, 10)}
DEFAULT_SESSION = (10, 12)
KID_TYPES = ("PICTURE_CHOICE", "TAP_COUNT", "SINGLE_CHOICE")
TOPIC_CAP = 0.4
BANK_CAP = 0.3
WEEKDAY_VI = ("thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật")
WEEKDAY_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def session_size(age_band: str | None) -> tuple[int, int]:
    return BAND_SESSION.get(age_band or "", DEFAULT_SESSION)


def short_title(title: str) -> str:
    return title.split(":", 1)[1].strip() if ":" in title else title


def _event_key(data: dict) -> str:
    """Engine item id of a planner `quiz_answer` event: bank `p:<id>`, course `<course_id>:<item>`."""
    item = str(data.get("item") or "")
    if item.startswith("p:"):
        return item[2:]
    cid = data.get("course_id")
    return f"{cid}{SEPARATOR}{item}" if cid else item


@dataclass
class Signals:
    """What is known about the learner, from the planner's events and the BKT state."""

    due: dict[str, float] = field(default_factory=dict)  # item key -> overdue days
    wrong: set[str] = field(default_factory=set)  # last answer wrong
    known: set[str] = field(default_factory=set)  # answered at least once
    seen: dict[str, int] = field(default_factory=dict)  # item id -> sessions ago
    states: dict[str, dict] = field(default_factory=dict)  # subject -> skill -> SkillState

    def mastery(self, item: Item) -> tuple[float | None, int]:
        rows = [self.states.get(item.subject, {}).get(s) for s in item.skill_ids]
        rows = [r for r in rows if r is not None and r.mastery_attempts > 0]
        n = sum(r.mastery_attempts for r in rows)
        return (sum(r.mastery * r.mastery_attempts for r in rows) / n, n) if n else (None, 0)


@dataclass
class Scored:
    item: Item
    score: float
    reasons: list[str]
    is_bank: bool


def score_candidate(it: Item, sig: Signals, current: set[tuple[str, str]], seed: int) -> Scored:
    s, reasons = 0.0, []
    if it.id in sig.due:
        s += 3.0 + min(sig.due[it.id], 7.0) / 7.0
        reasons.append("DUE_REVIEW")
    if it.id in sig.wrong:
        s += 2.5
        reasons.append("PREVIOUSLY_WRONG")
    m, evidence = sig.mastery(it)
    if evidence and m is not None and m < 0.5:
        s += 2.0
        reasons.append("WEAK_SKILL")
    course = it.doc.get("course")
    if course and (course["course_id"], course["lesson_id"]) in current:
        s += 1.5
        reasons.append("CURRENT_LESSON")
    if it.id not in sig.known:
        s += 0.5
        reasons.append("NEW_ITEM")
    ago = sig.seen.get(it.id)
    if ago is not None:
        s -= 2.0 * asm.RECENT_PENALTY.get(ago, asm.OLDER_PENALTY)
    theta = bkt.TopicMastery("", m, evidence).theta
    s -= 0.5 * abs(it.location - asm.b_for(theta, asm.TARGET_P_CORE)) / LOCATION_PER_LEVEL
    s += 0.3 * asm.jitter(seed, it.id)
    return Scored(it, s, reasons, course is None)


def pick(scored: list[Scored], n: int, budget_sec: int, bank_cap: int | None) -> list[asm.Selected]:
    ordered = sorted(scored, key=lambda c: (-c.score, c.item.id))
    cap = max(2, math.ceil(TOPIC_CAP * n))
    chosen: list[Scored] = []
    per_topic: dict[str, int] = {}
    seconds = bank_n = 0
    for relax in (False, True):
        for c in ordered:
            if len(chosen) >= n:
                break
            if c in chosen:
                continue
            if not relax and per_topic.get(c.item.topic, 0) >= cap:
                continue
            if bank_cap is not None and c.is_bank and bank_n >= bank_cap:
                continue
            if seconds + c.item.seconds > budget_sec and len(chosen) >= MIN_ITEMS:
                continue
            chosen.append(c)
            per_topic[c.item.topic] = per_topic.get(c.item.topic, 0) + 1
            seconds += c.item.seconds
            bank_n += 1 if c.is_bank else 0
    return [asm.Selected(c.item, reasons=c.reasons) for c in chosen]


class MixedSessions:
    """Methods of `PracticeService` for sessions drawn from courses (`self.db`, `self.bank`, `self.clock`, `self.mirror`,
    `self.content` and `self.planner` come from the service)."""

    content: Any = None
    planner: Any = None

    # ---- inputs ----------------------------------------------------------------------------------------

    def _user(self, user_id: str) -> User | None:
        with self.db.session() as s:  # type: ignore[attr-defined]
            user = s.get(User, user_id)
            if user is not None:
                s.expunge(user)
            return user

    def bundles(self, user_id: str, only_course: str | None = None) -> list[CourseBundle]:
        return load_bundles(self.content, self.bank, user_id, only_course)  # type: ignore[attr-defined]

    def signals(self, user_id: str, subjects: set[str]) -> Signals:
        now = self.clock()  # type: ignore[attr-defined]
        events = planner_events.load(self.db, user_id, now)  # type: ignore[attr-defined]
        sig = Signals()
        last: dict[str, bool] = {}
        for e in events:
            if e["kind"] == "quiz_answer":
                key = _event_key(e["data"])
                last[key] = bool(e["data"].get("correct"))
                sig.known.add(key)
        sig.wrong = {k for k, ok in last.items() if not ok}
        for d in fsrs_items.due_items(events, now, limit=500):
            sig.due[_event_key({"item": d["item"], "course_id": d["course_id"]})] = d["overdue_days"]
        sig.seen = self._recent_any(user_id)
        text = self._events_text(user_id)  # type: ignore[attr-defined]
        for subject in subjects:
            sig.states[subject] = bkt.skill_states(text, subject, self._curriculum_text(user_id, subject))  # type: ignore[attr-defined]
        return sig

    def _recent_any(self, user_id: str) -> dict[str, int]:
        with self.db.session() as s:  # type: ignore[attr-defined]
            rows = s.scalars(select(PracticeSession).where(
                PracticeSession.user_id == user_id, PracticeSession.kind == "practice",
                PracticeSession.status.in_(("finished", "expired"))).order_by(PracticeSession.started_at.desc()).limit(10)).all()
            seen: dict[str, int] = {}
            for rank, sess in enumerate(rows, start=1):
                for rec in sess.items:
                    seen.setdefault(rec["doc"]["id"], rank)
            return seen

    def _bank_candidates(self, user_id: str, subjects: set[str] | None) -> list[Item]:
        """In-grade bank items of `subjects` (None = every subject)."""
        grade = self.learner_grade(user_id)  # type: ignore[attr-defined]
        out: list[Item] = []
        for subject in self.bank.subjects():  # type: ignore[attr-defined]
            if subjects is not None and subject not in subjects:
                continue
            above = self._above_topics(subject, grade)  # type: ignore[attr-defined]
            out += [i for i in self.bank.by_subject.get(subject, []) if i.topic not in above]  # type: ignore[attr-defined]
        return out

    def _matching_bank_subjects(self, bundles: list[CourseBundle]) -> set[str]:
        found = set()
        for b in bundles:
            for subject in self.bank.subjects():  # type: ignore[attr-defined]
                if slug(SUBJECT_LABELS.get(subject, subject)) == slug(b.subject):
                    found.add(subject)
            found |= {i.subject for i in b.items if i.subject in self.bank.by_subject}  # type: ignore[attr-defined]
        return found

    @staticmethod
    def _kid_filter(items: list[Item], band: str | None) -> list[Item]:
        if band != "g1_5":
            return items
        kid = [i for i in items if i.type in KID_TYPES]
        return kid if len(kid) >= MIN_ITEMS else items

    # ---- planning ----------------------------------------------------------------------------------------

    def _plan_mixed(self, user_id: str, source: str, seed: int, band: str | None, course_id: str | None = None):
        from mentor_gateway.practice.service import PracticeError

        bundles = self.bundles(user_id, course_id)
        if course_id and not bundles:
            raise PracticeError(404, "course_not_found", "Em chưa tham gia khóa học này.")
        n, minutes = session_size(band)
        course_items = [i for b in bundles for i in b.studied_items()]
        current = {(b.course_id, ls.id) for b in bundles for ls in b.lessons if ls.current}
        bank_items: list[Item] = []
        if not course_id:
            bank_items = self._bank_candidates(user_id, self._matching_bank_subjects(bundles) if bundles else None)
        subjects = {i.subject for i in course_items} | {i.subject for i in bank_items}
        sig = self.signals(user_id, subjects)
        course_items = self._kid_filter(course_items, band)
        if bundles and len(course_items) >= n * 0.7:
            # courses supply the session: the bank only adds items the learner is weak on or must review
            bank_items = [i for i in bank_items if i.id in sig.due or i.id in sig.wrong or self._weak(sig, i)]
            bank_cap: int | None = int(BANK_CAP * n)
        else:
            bank_cap = None
            if bundles:
                bank_items = [i for i in bank_items if i.id in sig.due or i.id in sig.wrong or self._weak(sig, i)]
        scored = [score_candidate(i, sig, current, seed) for i in course_items + bank_items]
        chosen = pick(scored, n, int(minutes * 60 * 1.3), bank_cap)
        if len(chosen) < MIN_ITEMS:
            what = "bài em đã học trong khóa này" if course_id else "các bài em đang học"
            raise PracticeError(422, "insufficient_content",
                                f"Chưa đủ câu hỏi từ {what}; học thêm vài bài rồi quay lại nhé.",
                                available=len(chosen), required=MIN_ITEMS)
        shown_minutes = max(1, round(minutes * len(chosen) / n))
        assembly = asm.Assembly(asm._order(chosen, seed), seed, sum(s.item.seconds for s in chosen), [], VERSION)
        params = {"minutes": shown_minutes, "goal": "balanced", "topics": [], "mixed": True, "source": source,
                  "course_id": course_id, "band": band}
        return MixedPlan(assembly, params, self._from_summary(assembly, bundles))

    @staticmethod
    def _weak(sig: Signals, item: Item) -> bool:
        m, n = sig.mastery(item)
        return bool(n) and m is not None and m < 0.5

    def _from_summary(self, assembly: asm.Assembly, bundles: list[CourseBundle]) -> list[dict]:
        titles = {b.course_id: b.title for b in bundles}
        counts: dict[tuple[str, str], int] = {}
        for sel in assembly.items:
            course = sel.item.doc.get("course")
            key = ("course_id", course["course_id"]) if course else ("subject", sel.item.subject)
            counts[key] = counts.get(key, 0) + 1
        out = []
        for (kind, ident), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            label = short_title(titles.get(ident, ident)) if kind == "course_id" else SUBJECT_LABELS.get(ident, ident)
            out.append({kind: ident, "label": label, "n": n})
        return out

    # ---- /practice/home ----------------------------------------------------------------------------------

    def home(self, user_id: str, seed: int | None = None) -> dict:
        user = self._user(user_id)
        band = user.age_band if user else None
        today = self.clock().astimezone(VN).date()  # type: ignore[attr-defined]
        seed = int(today.strftime("%Y%m%d")) if seed is None else seed
        quick: dict[str, Any] = {"count": 0, "minutes": 0, "from": [], "seed": seed}
        try:
            plan = self._plan_mixed(user_id, "quick", seed, band)
            quick.update(count=len(plan.assembly.items), minutes=plan.params["minutes"], **{"from": plan.sources})
        except Exception as exc:
            if getattr(exc, "code", None) != "insufficient_content":
                raise
            quick["reason"] = "insufficient_content"
        by_course = []
        for b in self.bundles(user_id):
            rng = b.lessons_range()
            items = len(b.studied_items())
            if rng is None or not items:
                continue
            label = f"Bài {rng[0]}" if rng[0] == rng[1] else f"Bài {rng[0]}–{rng[1]}"
            by_course.append({"course_id": b.course_id, "title": b.title, "cover_sha256": b.cover_sha256,
                              "lessons_range": label, "lessons_from": rng[0], "lessons_to": rng[1], "items": items})
        return {"quick": quick, "mocks": self._mock_cards(user_id), "by_course": by_course}

    def _mock_cards(self, user_id: str) -> list[dict]:
        grade = self.learner_grade(user_id)  # type: ignore[attr-defined]
        last: dict[str, float | None] = {}
        with self.db.session() as s:  # type: ignore[attr-defined]
            for sess in s.scalars(select(PracticeSession).where(
                    PracticeSession.user_id == user_id, PracticeSession.kind == "mock",
                    PracticeSession.status.in_(("finished", "expired"))).order_by(PracticeSession.started_at.desc())):
                last.setdefault(sess.profile_id or "", sess.score_10)
        out = []
        for p in self.bank.profiles.values():  # type: ignore[attr-defined]
            above = self._above_topics(p.subject, grade)  # type: ignore[attr-defined]
            if not self._profile_available(p) or self._profile_above(p, above):  # type: ignore[attr-defined]
                continue
            out.append({"profile_id": p.id, "title": p.label, "subject": p.subject, "minutes": round(p.time_limit_sec / 60),
                        "items": p.item_count, "last_score": last.get(p.id)})
        return out

    # ---- result lines ------------------------------------------------------------------------------------

    @staticmethod
    def takeaway(answered: list[tuple[bool, str]]) -> dict | None:
        """One line about the session from the answers `(correct, topic title)`; None when nothing was answered."""
        if not answered:
            return None
        wrong = [t for ok, t in answered if not ok]
        if not wrong:
            return {"line_vi": "Em làm đúng hết, giữ nhịp này nhé.", "line_en": "All right, keep that pace."}
        worst = max(dict.fromkeys(wrong), key=wrong.count)
        if len(wrong) * 10 <= len(answered) * 3:
            return {"line_vi": f"Tốt rồi. Chỉ còn cần xem lại: {worst}.", "line_en": f"Good. Only one thing to look at again: {worst}."}
        return {"line_vi": f"Phần {worst} còn chưa chắc; xem lại bài rồi làm lại nhé.",
                "line_en": f"{worst} is not solid yet; revisit the lesson and try again."}

    def redo_line(self, user_id: str, wrong: int) -> dict | None:
        """The planner's plan decides when: the next `review` item of the stored plan (never generated here)."""
        if not wrong or self.planner is None:
            return None
        rec = self.planner._record(user_id)
        if rec is None:
            return None
        from mentor_gateway.planner.bands import TZ

        now = self.clock().astimezone(TZ)  # type: ignore[attr-defined]
        key = (now.date().isoformat(), now.strftime("%H:%M"))
        nxt = sorted((i for i in rec.plan.get("items", []) if i.get("kind") == "review" and (i["date"], i["start"]) >= key),
                     key=lambda i: (i["date"], i["start"]))
        if not nxt:
            return None
        it = nxt[0]
        if it["date"] == key[0]:
            vi, en = ("tối nay", "tonight") if it["start"] >= "17:00" else ("hôm nay", "today")
        else:
            wd = datetime.fromisoformat(it["date"]).weekday()
            vi, en = WEEKDAY_VI[wd], WEEKDAY_EN[wd]
        return {"line_vi": f"Mentor sẽ cho em làm lại {wrong} câu sai vào {vi}, giờ em hay học.",
                "line_en": f"Mentor will have you redo {wrong} wrong question{'s' if wrong != 1 else ''} on {en}, your usual time."}


@dataclass
class MixedPlan:
    """Assembly + stored params + the `from` breakdown (same attributes as the service's `Plan`)."""

    assembly: asm.Assembly
    params: dict
    sources: list[dict]
