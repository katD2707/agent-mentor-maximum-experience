"""PlannerService: ties layers 1-3 together (REQUIREMENTS-PLAN 3.7) and serves the API.

generate(): context (profile by code) -> LLM plan -> hard validator -> store; on any LLM failure, invalid JSON, or an
unfixable plan the rule-based fallback is used and the reason is kept in `study_plans.note`.
tick(): called by the scheduler; nightly pass, weekly review (Monday), and event-driven replans (new enrollment,
missed session, big practice change, goal change), plus server-side delivery of due reminders to web-push users.
"""

import asyncio
import logging
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from mentor_gateway.content.service import ContentService
from mentor_gateway.db import Database, User
from mentor_gateway.notifications import PLANNER_SOURCE, NotificationHub, Nudge
from mentor_gateway.planner import events as ev
from mentor_gateway.planner import fsrs_items, goals, research_plan
from mentor_gateway.planner.bands import TZ, band_for, hhmm, to_min
from mentor_gateway.planner.fallback import deep_link, explain_moves, plan_fallback
from mentor_gateway.planner.llm import PlannerLLM, PlannerLLMError, llm_plan
from mentor_gateway.planner.profile import compute_profile, local, sessions
from mentor_gateway.planner.tables import PlanRecord, Reminder, StudyGoal
from mentor_gateway.planner.text import clean
from mentor_gateway.planner.types import WEEKDAYS_EN, WEEKDAYS_VI, CourseInfo, LessonInfo, PlanContext
from mentor_gateway.planner.validator import validate
from mentor_gateway.settings import Clock
from mentor_gateway.users import UserService

log = logging.getLogger(__name__)

NIGHTLY_HOUR = 3  # local hour from which the nightly pass may run
CHECK_EVERY = timedelta(minutes=5)  # per-user trigger evaluation in tick()
MIN_REPLAN = timedelta(minutes=20)  # event-driven replans are rate limited
MISSED_GRACE = timedelta(minutes=30)


def _begin(it: dict) -> datetime:
    return datetime.fromisoformat(f"{it['date']}T{it['start']}:00").replace(tzinfo=TZ)


def _attended(starts: list[datetime], it: dict) -> bool:
    """A study session began in (or within the grace of) the planned slot."""
    begin = _begin(it)
    return any(begin - MISSED_GRACE <= t <= begin + timedelta(minutes=it["minutes"]) + MISSED_GRACE for t in starts)
PRACTICE_SHIFT = 0.2  # change of accuracy over the last answers that counts as "big"
PUSH_WINDOW = timedelta(minutes=15)
MAX_MOVES = 30


def short_title(title: str) -> str:
    return title.split(":", 1)[1].strip() if ":" in title else title


def part_of_day(minute: int) -> tuple[str, str]:
    if minute < 11 * 60:
        return "Sáng nay", "This morning"
    if minute < 17 * 60:
        return "Chiều nay", "This afternoon"
    return "Tối nay", "Tonight"


class PlannerService:
    def __init__(self, db: Database, users: UserService, hub: NotificationHub, push: Any, clock: Clock,
                 practice: Any = None, llm: PlannerLLM | None = None) -> None:
        self.db = db
        self.users = users
        self.hub = hub
        self.push = push
        self.clock = clock
        self.practice = practice
        self.llm = llm
        self.content: ContentService | None = None  # set by app.py (it owns the ContentService)
        self._locks: dict[str, asyncio.Lock] = {}
        self._checked: dict[str, datetime] = {}

    # ---- inputs --------------------------------------------------------------------------------

    def courses(self, user_id: str) -> tuple[list[CourseInfo], dict[str, tuple[str, str]]]:
        """Enrolled courses with their lesson tree, and item_id -> (course_id, lesson_id) for FSRS."""
        if self.content is None:
            return [], {}
        out, item_map = [], {}
        for e in self.content.list_enrollments(user_id):
            course = e.get("course") or {}
            try:
                pack = self.content.store.load_pack(e["course_id"], e["version"])
            except Exception:  # noqa: BLE001 - a pack that cannot be read is not plannable
                log.warning("planner: pack of %s v%s unreadable", e["course_id"], e["version"])
                continue
            done_ids = set(e["completed_block_ids"])
            lessons = []
            for ch in pack.chapters:
                for ls in ch.lessons:
                    ids = {b.id for b in ls.blocks}
                    lessons.append(LessonInfo(id=ls.id, title=ls.title, minutes=ls.est_minutes,
                                              done=ids <= done_ids, started=bool(ids & done_ids) or ls.id == e["last_lesson_id"]))
                    for b in ls.blocks:
                        if b.kind == "quiz":
                            for q in b.items:
                                item_map[q.id] = (e["course_id"], ls.id)
            out.append(CourseInfo(id=e["course_id"], title=course.get("title") or pack.title, subject=course.get("subject") or "",
                                  lessons=lessons, progress_pct=float(e["progress_pct"]), last_lesson_id=e["last_lesson_id"],
                                  enrolled_at=datetime.fromisoformat(e["enrolled_at"]),
                                  updated_at=datetime.fromisoformat(e["updated_at"])))
        return out, item_map

    def _goal_rows(self, user_id: str) -> list[StudyGoal]:
        with self.db.session() as s:
            rows = list(s.scalars(select(StudyGoal).where(StudyGoal.user_id == user_id)))
            s.expunge_all()
            return rows

    def _missed(self, rec: PlanRecord | None, study_days: set[date], today: date) -> int:
        if rec is None:
            return 0
        past = {i["date"] for i in rec.plan.get("items", []) if i["kind"] != "break" and i["date"] < today.isoformat()
                and i["date"] >= (today - timedelta(days=7)).isoformat()}
        return sum(1 for d in past if date.fromisoformat(d) not in study_days)

    def context(self, user: User, trigger: str, now: datetime | None = None) -> PlanContext:
        now = now or self.clock()
        band = band_for(user.age_band)
        language = user.language or "vi"
        courses, item_map = self.courses(user.id)
        evs = ev.load(self.db, user.id, now)
        due = fsrs_items.due_items(evs, now)
        for d in due:
            m = item_map.get(d["item"])
            if m:
                d["course_id"], d["lesson_id"] = m
            elif d.get("course_id") not in {c.id for c in courses}:
                d["course_id"] = None  # a practice item or a course the student left
        profile = compute_profile(evs, now, band, due)
        if user.age_band == "uni":  # Nghiên cứu (15.8): deadlines, meetings, action items, reading block
            profile["research"] = research_plan.research_block(self.db, user.id, now)
            profile["research"]["_log"] = research_plan.reminder_log(self.db, user.id)
        goals.sync_inferred(self.db, user.id, courses, language, now)
        infos = goals.build_infos(self._goal_rows(user.id), courses, profile, band, now)
        rec = self._record(user.id)
        study_days = {local(s["start"]).date() for s in sessions(evs)}
        profile["missed_recent"] = self._missed(rec, study_days, local(now).date())
        with self.db.session() as s:
            last_nudge = s.scalars(select(Reminder.created_at).where(Reminder.user_id == user.id, Reminder.kind == "nudge")
                                   .order_by(Reminder.created_at.desc())).first()
        return PlanContext(now=now, band=band, courses=courses, goals=infos, profile=profile, due_items=due,
                           quiet_until=user.quiet_until, moves=list(rec.moves) if rec else [],
                           old_items=list(rec.plan.get("items", [])) if rec else [], trigger=trigger,
                           missed_recent=profile["missed_recent"], last_nudge_at=last_nudge, language=language)

    def _record(self, user_id: str) -> PlanRecord | None:
        with self.db.session() as s:
            rec = s.get(PlanRecord, user_id)
            if rec is not None:
                s.expunge(rec)
            return rec

    # ---- generation ----------------------------------------------------------------------------

    def _decide(self, ctx: PlanContext, llm_result: dict | None, llm_error: str | None) -> tuple[dict, str, str | None]:
        """-> (plan, source, note). The validator has the last word on whatever the model said."""
        note = llm_error
        if llm_result is not None:
            ok, fixed, notes = validate(llm_result, ctx)
            if ok:
                return research_plan.overlay(fixed, ctx), "llm", "; ".join(notes[:6]) or None
            note = "; ".join(notes[-3:])
        plan = plan_fallback(ctx)
        ok, fixed, notes = validate(plan, ctx)
        return research_plan.overlay(fixed if ok else plan, ctx), "fallback", note

    async def generate(self, user: User, trigger: str, use_llm: bool = True) -> dict:
        lock = self._locks.setdefault(user.id, asyncio.Lock())
        async with lock:
            ctx = await asyncio.to_thread(self.context, user, trigger)
            result = err = None
            if use_llm and self.llm is not None and ctx.courses:
                try:
                    result = await llm_plan(self.llm, ctx)
                except PlannerLLMError as e:
                    err = f"llm: {e}"
                except Exception as e:
                    log.exception("planner llm")
                    err = f"llm: {e}"
            elif use_llm and self.llm is not None:
                err = "no courses"
            plan, source, note = self._decide(ctx, result, err)
            await asyncio.to_thread(self._store, user, ctx, plan, source, trigger, note)
            return plan

    def generate_now(self, user: User, trigger: str = "on_demand") -> dict:
        """Synchronous, rule-based only (first request of a new learner, tests)."""
        ctx = self.context(user, trigger)
        plan, source, note = self._decide(ctx, None, None)
        self._store(user, ctx, plan, source, trigger, note)
        return plan

    @staticmethod
    def _past_items(now: datetime, items: list[dict], new_items: list[dict]) -> list[dict]:
        """Planned sessions of this week that have begun and are not in the new plan: GET /plan/week still shows them."""
        loc = now.astimezone(TZ)
        monday = (loc.date() - timedelta(days=loc.weekday())).isoformat()
        nowkey = (loc.date().isoformat(), hhmm(loc.hour * 60 + loc.minute))
        current = {(i["date"], i["start"]) for i in new_items}
        kept = {(i["date"], i["start"]): i for i in items
                if (i["date"], i["start"]) < nowkey and i["date"] >= monday and (i["date"], i["start"]) not in current}
        return sorted(kept.values(), key=lambda i: (i["date"], i["start"]))

    def _snapshot(self, ctx: PlanContext, old: PlanRecord | None, user_id: str, plan_items: list[dict]) -> dict:
        snap = dict(old.snapshot) if old else {}
        snap["course_ids"] = sorted(ctx.course_ids)
        snap["practice_sig"] = self._practice_sig(user_id, ctx.now)
        snap["handled_missed"] = [k for k in snap.get("handled_missed", []) if k.split("|")[0] >= (ctx.now.astimezone(TZ).date() - timedelta(days=2)).isoformat()]
        snap["past_items"] = self._past_items(ctx.now, [*snap.get("past_items", []), *(old.plan.get("items", []) if old else [])],
                                              plan_items)
        if ctx.trigger == "weekly_review":
            snap["last_weekly"] = ctx.now.astimezone(TZ).date().isoformat()
        return snap

    def _store(self, user: User, ctx: PlanContext, plan: dict, source: str, trigger: str, note: str | None) -> None:
        now = ctx.now
        old = self._record(user.id)
        moves = list(old.moves) if old else []
        for m in explain_moves(ctx.old_items, plan["items"], trigger):
            moves.append({**m, "at": now.isoformat(), "trigger": trigger})
        moves = moves[-MAX_MOVES:]
        with self.db.session() as s:
            rec = s.get(PlanRecord, user.id)
            if rec is None:
                rec = PlanRecord(user_id=user.id)
                s.add(rec)
            rec.generated_at, rec.source, rec.trigger, rec.plan = now, source, trigger, plan
            rec.moves, rec.snapshot, rec.dirty, rec.note = moves, self._snapshot(ctx, old, user.id, plan["items"]), None, (note or None)
            for r in s.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.status == "scheduled",
                                                      Reminder.at > now)):
                r.status, r.updated_at = "cancelled", now
            for r in plan["reminders"]:
                s.add(Reminder(id="r-" + secrets.token_hex(8), user_id=user.id, at=datetime.fromisoformat(r["at"]),
                               kind=r["kind"], text_vi=r["text_vi"], text_en=r["text_en"], deep_link=r["deep_link"],
                               status="scheduled", created_at=now, updated_at=now))

    def mark_dirty(self, user_id: str, trigger: str) -> None:
        with self.db.session() as s:
            rec = s.get(PlanRecord, user_id)
            if rec is not None:
                rec.dirty = trigger

    def _practice_sig(self, user_id: str, now: datetime) -> dict:
        evs = [e for e in ev.derived(self.db, user_id, now - timedelta(days=30), True, set()) if e["kind"] == "quiz_answer"]
        last = evs[-20:]
        if len(last) < 5:
            return {"n": len(last), "acc": None}
        return {"n": len(evs), "acc": round(sum(1 for e in last if e["data"]["correct"]) / len(last), 2)}

    # ---- scheduler -----------------------------------------------------------------------------

    def _trigger(self, user: User, rec: PlanRecord | None, now: datetime) -> str | None:
        loc = now.astimezone(TZ)
        if rec is None:
            return "first"
        if rec.dirty:
            return rec.dirty
        if loc.hour >= NIGHTLY_HOUR and rec.generated_at.astimezone(TZ).date() < loc.date():
            weekly = loc.weekday() == 0 and rec.snapshot.get("last_weekly") != loc.date().isoformat()
            return "weekly_review" if weekly else "nightly"
        if now - rec.generated_at < MIN_REPLAN:
            return None
        courses, _ = self.courses(user.id)
        if {c.id for c in courses} != set(rec.snapshot.get("course_ids", [])):
            return "new_enrollment"
        handled = set(rec.snapshot.get("handled_missed", []))
        evs = ev.load(self.db, user.id, now, days=2)
        starts = [s["start"] for s in sessions(evs)]
        for it in rec.plan.get("items", []):
            if it["kind"] == "break" or it["date"] != loc.date().isoformat():
                continue
            key = f"{it['date']}|{it['start']}"
            if key in handled or now < _begin(it) + timedelta(minutes=it["minutes"]) + MISSED_GRACE:
                continue
            if not _attended(starts, it):
                with self.db.session() as s:
                    r = s.get(PlanRecord, user.id)
                    r.snapshot = {**r.snapshot, "handled_missed": [*handled, key]}
                return "missed_session"
        old, new = rec.snapshot.get("practice_sig") or {}, self._practice_sig(user.id, now)
        if old.get("acc") is not None and new.get("acc") is not None and abs(new["acc"] - old["acc"]) >= PRACTICE_SHIFT:
            return "practice_change"
        return None

    async def tick(self, now: datetime | None = None, force: bool = False) -> list[tuple[str, str]]:
        """-> [(user_id, trigger)] of the plans regenerated."""
        now = now or self.clock()
        ran = []
        for user in await asyncio.to_thread(self.users.all_provisioned):
            if not self.users.is_active(user):
                continue
            if not force and now - self._checked.get(user.id, datetime.min.replace(tzinfo=UTC)) < CHECK_EVERY:
                continue
            self._checked[user.id] = now
            try:
                rec = await asyncio.to_thread(self._record, user.id)
                trigger = await asyncio.to_thread(self._trigger, user, rec, now)
                if trigger:
                    await self.generate(user, trigger)
                    ran.append((user.id, trigger))
                await self.deliver_due(user, now)
            except Exception:
                log.exception("planner tick for %s", user.id)
        return ran

    async def deliver_due(self, user: User, now: datetime) -> int:
        """Web push: reminders whose time has come go out through the hub (a device that schedules locally needs
        no push). In quiet mode they are dropped, not queued."""
        if not self.push.count(user.id):
            return 0
        with self.db.session() as s:
            due = list(s.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.status == "scheduled",
                                                        Reminder.at <= now, Reminder.at > now - PUSH_WINDOW)))
            s.expunge_all()
        sent = 0
        for r in due:
            status = "skipped_quiet" if self.users.quiet_active(user.id, now) else "pushed"
            if status == "pushed":
                text = r.text_en if user.language == "en" else r.text_vi
                await self.hub.notify(user.id, text, nudge=Nudge(
                    text=text, kind="nudge", title="Mentor", source=PLANNER_SOURCE + r.id, expires_at=r.at + PUSH_WINDOW,
                    prefill=None))
                sent += 1
            with self.db.session() as s:
                row = s.get(Reminder, r.id)
                row.status, row.updated_at = status, now
        return sent

    # ---- views ---------------------------------------------------------------------------------

    def ensure_plan(self, user: User) -> PlanRecord:
        rec = self._record(user.id)
        if rec is None:
            self.generate_now(user, "first")
            rec = self._record(user.id)
        return rec  # type: ignore[return-value]

    def _label(self, it: dict, courses: dict[str, CourseInfo]) -> tuple[str, str, str]:
        c = courses.get(it.get("course_id") or "")
        short = short_title(c.title) if c else ""
        lesson = c.lesson(it.get("lesson_id")) if c else None
        m = it["minutes"]
        if it["kind"] == "practice":
            return "Luyện tập", "Practice", f"Luyện tập {m}′" if not short else f"Luyện {short} {m}′"
        if it["kind"] == "break":
            return "Nghỉ", "Break", f"Nghỉ {m}′"
        if it["kind"] == "research":
            return it.get("title_vi") or "Nghiên cứu", it.get("title_en") or "Research", f"{it.get('title_vi') or 'Nghiên cứu'} {m}′"
        verb_vi, _verb_en = ("Ôn", "Review") if it["kind"] == "review" else ("", "")
        label = f"{verb_vi} {short} {m}′".strip()
        return (lesson.title if lesson else short), (lesson.title if lesson else short), label if label else f"{m}′"

    def week_view(self, user: User) -> dict:
        rec = self.ensure_plan(user)
        courses = {c.id: c for c in self.courses(user.id)[0]}
        now = self.clock()
        today = local(now).date()
        starts = [s["start"] for s in sessions(ev.load(self.db, user.id, now, days=8))]
        items = []
        for it in sorted([*rec.snapshot.get("past_items", []), *rec.plan.get("items", [])], key=lambda i: (i["date"], i["start"])):
            t_vi, t_en, label = self._label(it, courses)
            c = courses.get(it.get("course_id") or "")
            wd = date.fromisoformat(it["date"]).weekday()
            items.append({**it, "weekday": wd, "weekday_vi": WEEKDAYS_VI[wd], "weekday_en": WEEKDAYS_EN[wd],
                          "course_title": c.title if c else None, "label": label, "title_vi": t_vi, "title_en": t_en,
                          "deep_link": it.get("deep_link") or "/nghien-cuu" if it["kind"] == "research"
                          else deep_link(it.get("course_id"), it.get("lesson_id"), it["kind"]),
                          "done": it["kind"] != "break" and _attended(starts, it)})
        monday = today - timedelta(days=today.weekday())
        return {"generated_at": rec.generated_at.isoformat(), "source": rec.source, "trigger": rec.trigger,
                "today": today.isoformat(), "days": [(monday + timedelta(days=i)).isoformat() for i in range((today - monday).days + 7)],
                "items": items, "goals": rec.plan.get("goals", []), "note_vi": rec.plan.get("week_note_vi", ""),
                "note_en": rec.plan.get("week_note_en", ""), "moves": rec.moves[-5:]}

    def today_view(self, user: User) -> dict:
        now = self.clock()
        loc = local(now)
        rec = self.ensure_plan(user)
        courses = {c.id: c for c in self.courses(user.id)[0]}
        items = sorted(rec.plan.get("items", []), key=lambda i: (i["date"], i["start"]))
        nowkey = (loc.date().isoformat(), hhmm(loc.hour * 60 + loc.minute - 30))  # a session stays "now" 30 min into it
        upcoming = [i for i in items if i["kind"] != "break" and (i["date"], i["start"]) >= nowkey]
        block = None
        if upcoming:
            it = upcoming[0]
            _t_vi, _t_en, _label = self._label(it, courses)
            is_today = it["date"] == loc.date().isoformat()
            wd = date.fromisoformat(it["date"]).weekday()
            pv, pe = part_of_day(to_min(it["start"])) if is_today else (WEEKDAYS_VI[wd], WEEKDAYS_EN[wd])
            c = courses.get(it.get("course_id") or "")
            what_vi = f"Ôn {short_title(c.title)}" if it["kind"] == "review" and c else "Luyện tập" if it["kind"] == "practice" else short_title(c.title) if c else ""
            what_en = f"Review {short_title(c.title)}" if it["kind"] == "review" and c else "Practice" if it["kind"] == "practice" else short_title(c.title) if c else ""
            if it["kind"] == "research":
                what_vi, what_en = it.get("title_vi") or "nghiên cứu", it.get("title_en") or "research"
            block = {"title_vi": clean(f"{pv}: {it['minutes']} phút {what_vi}".strip(), 80),
                     "title_en": clean(f"{pe}: {it['minutes']} min {what_en}".strip(), 80),
                     "date": it["date"], "start": it["start"], "is_today": is_today, "minutes": it["minutes"],
                     "kind": it["kind"], "course_id": it.get("course_id"), "lesson_id": it.get("lesson_id"),
                     "reason_vi": it["reason_vi"], "reason_en": it["reason_en"],
                     "deep_link": (it.get("deep_link") or "/nghien-cuu") if it["kind"] == "research"
                     else deep_link(it.get("course_id"), it.get("lesson_id"), it["kind"])}
        evs = ev.load(self.db, user.id, now, days=14)
        study_days = {local(s["start"]).date() for s in sessions(evs)}
        week_start = loc.date() - timedelta(days=loc.weekday())
        done = sum(1 for d in study_days if week_start <= d <= loc.date())
        rest = [i for i in items if i["kind"] != "break" and loc.date().isoformat() <= i["date"] <= (week_start + timedelta(days=6)).isoformat()
                and not (i["date"] == loc.date().isoformat() and loc.date() in study_days)]
        planned = done + len(rest)
        due_n = len(fsrs_items.due_items(evs, now))
        gs = self.goal_views(user)
        hub = {
            "courses": {"line_vi": block["title_vi"] if block else "Chưa có buổi nào trong lịch",
                        "line_en": block["title_en"] if block else "Nothing planned yet"},
            "practice": ({"line_vi": f"{due_n} câu đến hạn ôn", "line_en": f"{due_n} questions due for review"} if due_n
                         else {"line_vi": "10 câu, khoảng 12 phút", "line_en": "10 questions, about 12 minutes"}),
            "ask": {"line_vi": "Chụp ảnh, gõ hoặc nói", "line_en": "Snap, type or speak"},
            "progress": {"line_vi": f"{len(gs)} mục tiêu, tuần này {done}/{planned} buổi" if gs else "Chưa có mục tiêu",
                         "line_en": f"{len(gs)} goals, {done}/{planned} sessions this week" if gs else "No goals yet"},
        }
        if user.age_band == "uni":  # present only for the uni band (omitted, not null, for others)
            from mentor_gateway.research.status import status_line

            hub["research"] = status_line(self.db, user.id, now)
        return {"date": loc.date().isoformat(), "now": now.isoformat(), "today": block, "hub": hub,
                "week": {"done": done, "planned": planned}, "due_review_count": due_n,
                "quiet_until": user.quiet_until.isoformat() if user.quiet_until else None, "plan_source": rec.source}

    def reminders_view(self, user: User, since: datetime | None) -> dict:
        now = self.clock()
        self.ensure_plan(user)
        since = since or now - timedelta(days=1)
        with self.db.session() as s:
            rows = list(s.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.updated_at >= since)
                                  .order_by(Reminder.at)))
            fresh = s.get(User, user.id)
            quiet = fresh.quiet_until if fresh else None
        return {"now": now.isoformat(), "quiet_until": quiet.isoformat() if quiet else None,
                "break_after_minutes": band_for(user.age_band).break_after,
                "reminders": [{"id": r.id, "at": r.at.astimezone(TZ).isoformat(), "kind": r.kind, "text_vi": r.text_vi,
                               "text_en": r.text_en, "deep_link": r.deep_link, "status": r.status, "outcome": r.outcome}
                              for r in rows]}

    def record_outcome(self, user: User, reminder_id: str, outcome: str) -> bool:
        now = self.clock()
        with self.db.session() as s:
            r = s.get(Reminder, reminder_id)
            if r is None or r.user_id != user.id:
                return False
            r.outcome, r.outcome_at, r.updated_at = outcome, now, now
            at = r.at
        ev.record(self.db, user.id, f"ro-{reminder_id}-{outcome}", "reminder_outcome", now,
                  {"reminder_id": reminder_id, "outcome": outcome, "at": at.astimezone(TZ).isoformat()})
        return True

    # ---- goals ---------------------------------------------------------------------------------

    def goal_views(self, user: User) -> list[dict]:
        now = self.clock()
        courses, _ = self.courses(user.id)
        goals.sync_inferred(self.db, user.id, courses, user.language or "vi", now)
        evs = ev.load(self.db, user.id, now)
        profile = compute_profile(evs, now, band_for(user.age_band), None)
        rows = self._goal_rows(user.id)
        infos = goals.build_infos(rows, courses, profile, band_for(user.age_band), now)
        by_id = {c.id: c for c in courses}
        research = next((r for r in rows if r.source == "research" and not r.dismissed), None)

        def thesis_milestones() -> list[dict]:  # Goal.milestones of the research goal: the "Mốc luận văn", by date
            from mentor_gateway.research import milestones as ms

            planned = ms.planned_counts(self.db, user.id)
            today = local(now).date()
            return [ms.view(m, today, planned) for m in research.milestones or [] if m.get("thesis")]

        return [{"id": g.id, "title": g.title, "kind": g.kind, "deadline": g.deadline.isoformat() if g.deadline else None,
                 "source": "research" if research is not None and g.id == "res-thesis" else "learning",
                 "milestones": thesis_milestones() if research is not None and g.id == "res-thesis" else [],
                 "progress_pct": g.progress_pct, "status": g.status, "line_vi": clean(g.line_vi, 160),
                 "line_en": clean(g.line_en, 160), "course_ids": g.course_ids,
                 "courses": [{"id": cid, "title": by_id[cid].title, "subject": by_id[cid].subject} for cid in g.course_ids if cid in by_id],
                 "required_min_per_day": g.required_min_per_day,
                 "created_at": g.created_at.isoformat() if g.created_at else None} for g in infos]

    def goal_view(self, user: User, goal_id: str) -> dict | None:
        return next((g for g in self.goal_views(user) if g["id"] == goal_id), None)

    def create_goal(self, user: User, title: str, deadline: date | None, course_ids: list[str]) -> dict:
        now = self.clock()
        gid = goals.new_goal_id()
        with self.db.session() as s:
            s.add(StudyGoal(id=gid, user_id=user.id, kind="student", title=title.strip()[:200], deadline=deadline,
                            course_ids=course_ids, dismissed=False, created_at=now, updated_at=now))
        self.mark_dirty(user.id, "goal_change")
        return self.goal_view(user, gid) or {}

    def update_goal(self, user: User, goal_id: str, fields: dict) -> dict | None:
        if goal_id == "res-thesis":  # title, deadline and progress follow the thesis milestones: nothing to change here
            return self.goal_view(user, goal_id)
        with self.db.session() as s:
            g = s.get(StudyGoal, goal_id)
            if g is None or g.user_id != user.id or g.dismissed:
                return None
            if "title" in fields and g.kind == "student":
                g.title = fields["title"].strip()[:200]
            if "deadline" in fields:
                g.deadline = fields["deadline"]
            if "course_ids" in fields and g.kind == "student":
                g.course_ids = fields["course_ids"]
            g.updated_at = self.clock()
        self.mark_dirty(user.id, "goal_change")
        return self.goal_view(user, goal_id)

    def delete_goal(self, user: User, goal_id: str) -> bool:
        if goal_id == "res-thesis":  # leaves Tiến độ: the milestones stay as plain deadlines (thesis flag off)
            from mentor_gateway.research import milestones as ms

            row, items = ms.load(self.db, user.id)
            if row is None or row.dismissed:
                return False
            ms.save(self.db, user.id, [{**m, "thesis": False} for m in items], row.title, self.clock())
            self.mark_dirty(user.id, "goal_change")
            return True
        with self.db.session() as s:
            g = s.get(StudyGoal, goal_id)
            if g is None or g.user_id != user.id or g.dismissed:
                return False
            if g.kind == "inferred":  # stays as a tombstone so the next sync does not bring it back
                g.dismissed = True
            else:
                s.delete(g)
        self.mark_dirty(user.id, "goal_change")
        return True
