"""Deadlines and thesis milestones (CONTRACTS 15.8). Stored in the research goal's `milestones` (research/milestones.py)."""

from __future__ import annotations

import re
import threading
from datetime import date

from mentor_schemas.research import Milestone, MilestoneInput, MilestonePatch

from mentor_gateway.db import User
from mentor_gateway.planner.bands import TZ
from mentor_gateway.research import dates, milestones, prompts
from mentor_gateway.research.base import ModelUnavailable, ResearchBase, fail, iso

_SUBMIT = re.compile(r"\b(nộp|nop|submit|submission|camera[- ]ready|paper due|full paper|abstract due|hạn nộp)\b", re.IGNORECASE)
_LOCK = threading.Lock()  # read-modify-write of the milestone list


class DeadlinesMixin(ResearchBase):
    def _title(self, user_id: str) -> str:
        return self.topic(user_id)[0] or "Luận văn"

    def list_deadlines(self, user_id: str, include_done: bool = False) -> list[Milestone]:
        today = self.clock().astimezone(TZ).date()
        planned = milestones.planned_counts(self.db, user_id)
        items = [m for m in milestones.load(self.db, user_id)[1] if include_done or not m.get("done")]
        items.sort(key=lambda m: (m["due_date"], m.get("due_time") or "99:99", m["id"]))
        return [Milestone(**milestones.view(m, today, planned)) for m in items]

    def thesis_milestones(self, user_id: str) -> list[Milestone]:
        return [m for m in self.list_deadlines(user_id, include_done=True) if m.thesis]

    def _one(self, user_id: str, mid: str) -> Milestone:
        got = next((m for m in self.list_deadlines(user_id, include_done=True) if m.id == mid), None)
        if got is None:
            raise fail(404, "deadline_not_found")
        return got

    async def _read_text(self, text: str, today: date) -> tuple[dates.Local, str, str, bool]:
        """-> (Vietnam date/time, title, kind, certain) from the learner's words. Dates, times and zones are read by code
        (research/dates.py); the model only names the deadline and says whether it is a submission, and may read a date
        the code could not."""
        w = dates.parse_when(text, today)
        title, kind = dates.strip_when(text)[:200], ("submission" if _SUBMIT.search(text) else "other")
        try:
            d = await self.llm_json(prompts.fill(prompts.DEADLINE, today=today.isoformat()), text, timeout=30)
            if isinstance(d.get("title"), str) and d["title"].strip():
                title = " ".join(d["title"].split())[:200]
            if d.get("kind") in ("submission", "other"):
                kind = d["kind"]
            if w.day is None and isinstance(d.get("date"), str):
                try:
                    w.day = date.fromisoformat(d["date"])
                    w.certain = bool(d.get("certain", True))
                    if isinstance(d.get("time"), str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", d["time"]):
                        w.clock = (int(d["time"][:2]), int(d["time"][3:]))
                    if isinstance(d.get("tz"), str):
                        w.tz_hours, w.tz_label = dates._tz(d["tz"])
                except ValueError:
                    pass
        except ModelUnavailable:
            pass
        local = dates.to_vietnam(w)
        if local is None:
            raise fail(422, "deadline_unparsed")
        return local, title or "Hạn", kind, w.certain

    async def create_deadline(self, user: User, inp: MilestoneInput) -> Milestone:
        now = self.clock()
        today = now.astimezone(TZ).date()
        if inp.text is not None:
            local, title, kind, certain = await self._read_text(inp.text.strip(), today)
            due_date, due_time, original = local.day.isoformat(), local.time, local.original
            confirmed = local.time is not None and certain
        else:
            hours = dates.zone_hours(inp.tz)
            if hours is None:
                raise fail(422, "deadline_unparsed")
            title, kind = " ".join((inp.title or "").split())[:200], inp.kind or ("submission" if _SUBMIT.search(inp.title or "") else "other")
            d0 = date.fromisoformat(inp.due_date)  # type: ignore[arg-type]
            clock = (int(inp.due_time[:2]), int(inp.due_time[3:])) if inp.due_time else None
            local = dates.to_vietnam(dates.When(day=d0, clock=clock, tz_hours=hours if hours != 7.0 else None,
                                                tz_label=(inp.tz or "").upper() or None)) or dates.Local(d0, None, None, False)
            due_date, due_time, original = local.day.isoformat(), local.time, local.original
            confirmed = local.time is not None
        kind = inp.kind or kind
        thesis = inp.thesis if inp.thesis is not None else kind == "submission"
        with _LOCK:
            _row, items = milestones.load(self.db, user.id)
            m = {"id": milestones.next_id(items), "title": title, "due_date": due_date, "due_time": due_time,
                 "original_text": original, "confirmed": confirmed, "kind": kind, "thesis": thesis, "done": False,
                 "created_at": iso(now)}
            milestones.save(self.db, user.id, [*items, m], self._title(user.id), now)
        self.replan(user.id, "research_deadline_changed")
        return self._one(user.id, m["id"])

    def patch_deadline(self, user: User, mid: str, patch: MilestonePatch) -> Milestone:
        ch = patch.model_dump(exclude_unset=True)
        now = self.clock()
        with _LOCK:
            _row, items = milestones.load(self.db, user.id)
            m = next((x for x in items if x["id"] == mid), None)
            if m is None:
                raise fail(404, "deadline_not_found")
            if ch.get("title"):
                m["title"] = " ".join(ch["title"].split())[:200]
            if ch.get("due_date"):
                m["due_date"] = ch["due_date"]
                m["original_text"] = None  # the converted time no longer matches what the learner typed
            if "due_time" in ch:
                m["due_time"] = ch["due_time"]
                m["original_text"] = None
                if ch["due_time"] and "confirmed" not in ch:
                    m["confirmed"] = True  # the learner gave the time themselves
            for k in ("kind", "thesis", "confirmed", "done"):
                if ch.get(k) is not None:
                    m[k] = ch[k]
            if not m.get("due_time"):
                m["confirmed"] = False  # no time, no confirmation: "Chưa xác nhận"
            milestones.save(self.db, user.id, items, self._title(user.id), now)
        self.replan(user.id, "research_deadline_changed")
        return self._one(user.id, mid)

    def delete_deadline(self, user: User, mid: str) -> None:
        with _LOCK:
            _row, items = milestones.load(self.db, user.id)
            if not any(x["id"] == mid for x in items):
                raise fail(404, "deadline_not_found")
            milestones.save(self.db, user.id, [x for x in items if x["id"] != mid], self._title(user.id), self.clock())
        self.replan(user.id, "research_deadline_changed")

