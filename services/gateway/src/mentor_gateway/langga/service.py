"""Village, market, chickens, XP week and the Arena list (CONTRACTS-LANGGA section 2). Plain `def` methods: the API runs them
in the thread pool (they read SQLite and course packs)."""

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from mentor_gateway.db import Database, User
from mentor_gateway.langga import subjects
from mentor_gateway.langga import xp as xpm
from mentor_gateway.langga.papers import PaperStore, boss_for
from mentor_gateway.langga.resolve import ChickenResolver
from mentor_gateway.langga.tables import LanggaState, UserChicken
from mentor_gateway.langga.xp import XpService
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)

SUGGESTED_MAX = 12
NEWS_MAX = 5


def _err(status: int, code: str) -> HTTPException:
    return HTTPException(status, {"error": code})


def short_title(title: str) -> str:
    return title.split(":", 1)[1].strip() if ":" in title else title


class LanggaService:
    def __init__(self, db: Database, clock: Clock, xp: XpService, content: Any, planner: Any, practice: Any,
                 resolver: ChickenResolver, papers: PaperStore) -> None:
        self.db, self.clock, self.xp = db, clock, xp
        self.content, self.planner, self.practice, self.resolver, self.papers = content, planner, practice, resolver, papers

    # ---- ownership ---------------------------------------------------------------------------------------

    def owned(self, user_id: str) -> dict[str, UserChicken]:
        with self.db.session() as s:
            rows = s.scalars(select(UserChicken).where(UserChicken.user_id == user_id, UserChicken.let_go_at.is_(None))
                             .order_by(UserChicken.taken_at, UserChicken.chicken)).all()
            return {r.chicken: r for r in rows}

    def _check_stage(self, user: User, chicken: str) -> None:
        if chicken not in subjects.CHICKENS or not subjects.valid_for_band(chicken, user.age_band):
            raise _err(400, "not_in_stage")

    def take(self, user: User, chicken: str) -> dict:
        self._check_stage(user, chicken)
        now = self.clock()
        with self.db.session() as s:
            row = s.get(UserChicken, (user.id, chicken))
            if row is not None and row.let_go_at is None:
                raise _err(409, "already_owned")
            if row is None:
                s.add(UserChicken(user_id=user.id, chicken=chicken, taken_at=now))
            else:  # taken again: the XP in the ledger is still there
                row.taken_at, row.let_go_at = now, None
        return self.chicken_view(user, chicken)

    def let_go(self, user: User, chicken: str) -> None:
        with self.db.session() as s:
            row = s.get(UserChicken, (user.id, chicken))
            if row is None or row.let_go_at is not None:
                raise _err(404, "not_owned")
            row.let_go_at = self.clock()

    def ensure_taken(self, user_id: str, chicken: str) -> None:
        """Used by the migration only: take a chicken without any checks (no-op when it is owned)."""
        now = self.clock()
        with self.db.session() as s:
            row = s.get(UserChicken, (user_id, chicken))
            if row is None:
                s.add(UserChicken(user_id=user_id, chicken=chicken, taken_at=now))

    def migrate(self, user: User) -> None:
        """First /village of a student who already has enrollments: one chicken for each enrolled course's chicken."""
        with self.db.session() as s:
            st = s.get(LanggaState, user.id)
            if st is not None and st.migrated_at is not None:
                return
        for e in self._enrollments(user):
            cid = e["_chicken"]
            if cid:
                self.ensure_taken(user.id, cid)
        with self.db.session() as s:
            st = s.get(LanggaState, user.id)
            if st is None:
                s.add(LanggaState(user_id=user.id, migrated_at=self.clock()))
            else:
                st.migrated_at = self.clock()

    # ---- building blocks ---------------------------------------------------------------------------------

    def _enrollments(self, user: User) -> list[dict]:
        """Enrollment views (newest activity first), each with `_chicken` (valid for the student's stage)."""
        out = []
        for e in self.content.list_enrollments(user.id):
            e["_chicken"] = self.resolver.of_course(e["course_id"], user.age_band)
            out.append(e)
        return out

    def _course_counts(self, band: str | None) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for e in self.content.store.load_catalog().courses:
            if e.age_band == subjects.band_or_default(band):
                counts[subjects.chicken_of_entry(e)] += 1
        return counts

    def _view(self, cid: str, info: dict, totals: dict[str, int], enrolls: list[dict], done_today: set[str],
              taken_at: Any) -> dict:
        c = subjects.CHICKENS[cid]
        mine = [e for e in enrolls if e["_chicken"] == cid]
        active = None
        if mine:
            e = mine[0]  # list_enrollments is newest first
            title = (e.get("course") or {}).get("title") or e["course_id"]
            active = {"id": e["course_id"], "title": title, "percent": e["progress_pct"]}
        return {"id": cid, "name_vi": c.name_vi, "name_en": c.name_en, "art": c.art, **xpm.level_info(totals.get(cid, 0)),
                "courses": len(mine), "active_course": active, "done_today": cid in done_today,
                "taken_at": taken_at.isoformat() if taken_at else None}

    def chicken_view(self, user: User, cid: str) -> dict:
        rows = self.owned(user.id)
        return self._view(cid, {}, self.xp.totals(user.id), self._enrollments(user),
                          self.xp.chickens_active_on(user.id, self.xp.today()),
                          rows[cid].taken_at if cid in rows else None)

    # ---- /village ----------------------------------------------------------------------------------------

    def village(self, user: User) -> dict:
        self.migrate(user)
        rows = self.owned(user.id)
        totals = self.xp.totals(user.id)
        enrolls = self._enrollments(user)
        today = self.xp.today()
        done_today = self.xp.chickens_active_on(user.id, today)
        chickens = [self._view(cid, {}, totals, enrolls, done_today, r.taken_at) for cid, r in rows.items()]
        plan: dict = {}
        try:
            plan = self.planner.today_view(user) if self.planner is not None and chickens else {}
        except Exception:
            log.warning("village: planner unavailable", exc_info=True)
        days = self.xp.active_days(user.id, today - timedelta(days=400))
        streak = plan.get("streak") or {"days": self._streak(days, today), "today_done": today in days}
        return {"chickens": chickens, "speaker": self._speaker(user, rows, chickens, plan), "news": self._news(user, rows, enrolls, plan),
                "streak": streak, "week": plan.get("week") or {"done": 0, "planned": 0}, "avatar": getattr(user, "avatar", None),
                "stage": subjects.band_or_default(user.age_band)}

    @staticmethod
    def _streak(days: set, today) -> int:
        day = today if today in days else today - timedelta(days=1)
        n = 0
        while day in days:
            n += 1
            day -= timedelta(days=1)
        return n

    def _speaker(self, user: User, rows: dict[str, UserChicken], chickens: list[dict], plan: dict) -> dict | None:
        if not chickens:
            return None
        block = plan.get("today")
        if block:
            cid = (self.resolver.of_course(block["course_id"], user.age_band) if block.get("course_id") else None)
            if cid in rows:
                c = subjects.CHICKENS[cid]
                kind = block.get("kind")
                return {"chicken": cid, "line_vi": block["title_vi"], "line_en": block["title_en"],
                        "action": {"kind": "lesson" if kind == "lesson" else "practice" if kind in ("practice", "review") else kind,
                                   "deep_link": self._plan_link(block), "minutes": block.get("minutes")},
                        "name_vi": c.name_vi}
        last = self.xp.last_active(user.id)
        cid = max((c for c in rows), key=lambda c: (last.get(c) or rows[c].taken_at, c))
        c = subjects.CHICKENS[cid]
        return {"chicken": cid, "line_vi": f"{c.name_vi} sẵn sàng rồi, mình luyện một chút nhé.",
                "line_en": f"{c.name_en} is ready, shall we practise a little?",
                "action": {"kind": "practice", "deep_link": "/luyen-tap", "minutes": 10}, "name_vi": c.name_vi}

    @staticmethod
    def _plan_link(block: dict) -> str:
        if block.get("kind") == "lesson" and block.get("course_id"):
            q = f"?lesson={block['lesson_id']}" if block.get("lesson_id") else ""
            return f"/khoa-hoc/{block['course_id']}/hoc{q}"
        if block.get("kind") in ("practice", "review"):
            return "/luyen-tap"
        return block.get("deep_link") or "/luyen-tap"

    def _news(self, user: User, rows: dict[str, UserChicken], enrolls: list[dict], plan: dict) -> list[dict]:
        news: list[dict] = []
        now = self.clock()
        # level-ups of the last 3 days: the level now against the level 3 days ago
        week = self.xp.week(user.id)
        totals = self.xp.totals(user.id)
        for cid in rows:
            recent = sum(week.get(cid, [0] * 7)[-3:])
            if recent and xpm.level_of(totals.get(cid, 0)) > xpm.level_of(totals.get(cid, 0) - recent):
                c = subjects.CHICKENS[cid]
                lv = xpm.level_of(totals[cid])
                news.append({"kind": "level_up", "chicken": cid, "text_vi": f"{c.name_vi} lên cấp {lv}.",
                             "text_en": f"{c.name_en} reached level {lv}.", "deep_link": "/tien-do"})
        due = int(plan.get("due_review_count") or 0)
        if due:
            news.append({"kind": "reminder", "chicken": None, "text_vi": f"{due} câu đến hạn ôn.",
                         "text_en": f"{due} questions are due for review.", "deep_link": "/luyen-tap"})
        enrolled = {e["course_id"] for e in enrolls}
        since = now - timedelta(days=14)
        for e in self.content.store.load_catalog().courses:
            if (e.status == "live" and e.age_band == subjects.band_or_default(user.age_band) and e.id not in enrolled
                    and e.published_at and e.published_at >= since and subjects.chicken_of_entry(e) in rows):
                news.append({"kind": "new_course", "chicken": subjects.chicken_of_entry(e),
                             "text_vi": f"Khóa mới: {e.title}.", "text_en": f"New course: {e.title}.",
                             "deep_link": f"/khoa-hoc/{e.id}"})
        return news[:NEWS_MAX]

    # ---- /market -----------------------------------------------------------------------------------------

    def market(self, user: User) -> dict:
        owned = self.owned(user.id)
        counts = self._course_counts(user.age_band)
        return {"stage": subjects.band_or_default(user.age_band),
                "chickens": [{**subjects.market_row(cid), "courses": counts.get(cid, 0), "owned": cid in owned}
                             for cid in subjects.chickens_of_band(user.age_band)]}

    # ---- /chickens/{id} ----------------------------------------------------------------------------------

    def chicken_page(self, user: User, cid: str) -> dict:
        if cid not in subjects.CHICKENS or not subjects.valid_for_band(cid, user.age_band):
            raise _err(404, "unknown_chicken")
        rows = self.owned(user.id)
        enrolls = self._enrollments(user)
        totals = self.xp.totals(user.id)
        view = self._view(cid, {}, totals, enrolls, self.xp.chickens_active_on(user.id, self.xp.today()),
                          rows[cid].taken_at if cid in rows else None)
        mine = [e for e in enrolls if e["_chicken"] == cid]
        courses = [self._course_row(e) for e in mine]
        enrolled = {e["course_id"] for e in enrolls}
        band = subjects.band_or_default(user.age_band)
        sugg = [e for e in self.content.store.load_catalog().courses
                if e.age_band == band and e.id not in enrolled and subjects.chicken_of_entry(e) == cid]
        sugg.sort(key=lambda e: e.status != "live")  # stable: real courses first
        return {"chicken": view, "courses": courses,
                "suggested": [e.model_dump(mode="json") | {"chicken": cid} for e in sugg[:SUGGESTED_MAX]],
                "week_xp": self.xp.week(user.id).get(cid, [0] * 7), "tests": self._tests(user, cid, mine)}

    def _course_row(self, e: dict) -> dict:
        last_title = None
        try:
            pack = self.content.store.load_pack(e["course_id"], e["version"])
            last_title = next((ls.title for ch in pack.chapters for ls in ch.lessons if ls.id == e["last_lesson_id"]), None)
        except Exception:  # noqa: BLE001 - a pack that cannot be read just has no lesson title
            pass
        course = e.get("course") or {}
        return {"course_id": e["course_id"], "title": course.get("title") or e["course_id"], "percent": e["progress_pct"],
                "version": e["version"], "update_available": e["update_available"], "last_lesson_id": e["last_lesson_id"],
                "last_lesson_title": last_title, "updated_at": e["updated_at"], "cover_sha256": course.get("cover_sha256"),
                "blocks_done": e["blocks_done"], "blocks_total": e["blocks_total"], "lessons_count": course.get("lessons_count")}

    def _tests(self, user: User, cid: str, mine: list[dict]) -> list[dict]:
        from mentor_gateway.langga.mocks import MIN_COURSE_MOCK_ITEMS, course_mock_size

        last = self.practice.last_scores(user.id)
        out = []
        bundles = {b.course_id: b for b in self.practice.bundles(user.id)} if mine else {}
        for e in mine:
            b = bundles.get(e["course_id"])
            if b is None or len(b.items) < MIN_COURSE_MOCK_ITEMS:
                continue
            n, minutes = course_mock_size(len(b.items))
            src = f"course-mock:{e['course_id']}"
            out.append({"course_id": e["course_id"], "profile_or_mock": src, "title": f"Kiểm tra: {short_title(b.title)}",
                        "minutes": minutes, "items": n, "last_score": last.get(src)})
        for m in self.practice._mock_cards(user.id):
            if subjects.chicken_of_bank_subject(m["subject"], user.age_band) == cid:
                out.append({"course_id": None, "profile_or_mock": f"mock:{m['profile_id']}", "title": m["title"],
                            "minutes": m["minutes"], "items": m["items"], "last_score": m["last_score"]})
        return out

    # ---- /xp/week ----------------------------------------------------------------------------------------

    def xp_week(self, user: User) -> dict:
        today = self.xp.today()
        first = today - timedelta(days=6)
        week = self.xp.week(user.id)
        by_source = self.xp.week_breakdown(user.id)
        totals = self.xp.totals(user.id)
        rows = self.owned(user.id)
        ids = list(dict.fromkeys([*rows, *week]))
        chickens = []
        for cid in ids:
            if cid not in subjects.CHICKENS:
                continue
            days = week.get(cid, [0] * 7)
            chickens.append({"chicken": cid, "owned": cid in rows, **xpm.level_info(totals.get(cid, 0)), "week": days,
                             "week_total": sum(days), "by_source": by_source.get(cid, {})})
        return {"days": [(first + timedelta(days=i)).isoformat() for i in range(7)], "chickens": chickens,
                "total": sum(c["week_total"] for c in chickens)}

    # ---- /arena/papers -----------------------------------------------------------------------------------

    def arena(self, user: User, chicken: str | None, year: int | None) -> list[dict]:
        band = subjects.band_or_default(user.age_band)
        results = self.practice.paper_results(user.id)
        out = []
        for p in self.papers.all().values():
            if p.band != band or (chicken and p.chicken != chicken) or (year and p.year != year):
                continue
            r = results.get(p.id) or {}
            out.append({"id": p.id, "kind": p.kind, "band": p.band, "title_vi": p.title_vi, "title_en": p.title_en or p.title_vi,
                        "year": p.year, "minutes": p.minutes, "items": p.item_count, "chicken": p.chicken,
                        "boss": boss_for(p.chicken), "best_score": r.get("best_score"), "beaten": bool(r.get("beaten")),
                        "placeholder": p.placeholder, "note_vi": p.note_vi, "note_en": p.note_en, "source": p.source.model_dump()})
        out.sort(key=lambda r: (-r["year"], r["kind"], r["id"]))
        return out
