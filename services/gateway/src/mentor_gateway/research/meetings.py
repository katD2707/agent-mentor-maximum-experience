"""Advisor meetings (CONTRACTS 15.7): the time, the agenda drafted 2 days before, the notes split into action items.

Action items with a date become planner items (`kind: "research"`) on the planner's next pass (the overlay in
`planner/research_plan.py` reads them from this table). Items without a date stay items and feed the next agenda."""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from mentor_schemas.research import (
    ActionItem,
    ActionItemPatch,
    Agenda,
    AgendaInput,
    AgendaItem,
    Meeting,
    MeetingInput,
    MeetingPatch,
)
from sqlalchemy import select

from mentor_gateway.db import User
from mentor_gateway.planner.bands import TZ
from mentor_gateway.planner.text import clean, unaccent
from mentor_gateway.research import dates, milestones, prompts
from mentor_gateway.research.base import ModelUnavailable, ResearchBase, fail, iso, new_id
from mentor_gateway.research.tables import ExperimentRow, MeetingRow, PaperRow, ReadingEntryRow

log = logging.getLogger(__name__)

AGENDA_LEAD = timedelta(hours=48)
_BULLET = re.compile(r"^\s*(?:[-*•–]|\d{1,2}[.)]|\[[ xX]?\])\s*")
_TASK_CUE = re.compile(r"\b(cần|phải|làm|viết|chạy|gửi|nộp|sửa|thêm|đọc|chuẩn bị|kiểm tra|hoàn thành|todo|to do|need to|write|run|send|submit|fix|add|read|prepare|check|finish)\b",
                       re.IGNORECASE)


def split_actions(notes: str, today: date) -> list[dict[str, Any]]:
    """No model: bullet lines are the tasks; without bullets, sentences that sound like a task. A date in the line is its due date."""
    lines = [ln for ln in notes.splitlines() if ln.strip()]
    bullets = [_BULLET.sub("", ln).strip() for ln in lines if _BULLET.match(ln)]
    if bullets:
        texts = bullets
    else:
        texts = [s.strip() for ln in lines for s in re.split(r"(?<=[.;!?])\s+", ln) if _TASK_CUE.search(s)]
    out = []
    for t in texts:
        if not t:
            continue
        w = dates.parse_when(t, today)
        out.append({"text": t[:300], "due_date": w.day.isoformat() if w.day else None})
    return out[:20]


_ADVISOR = re.compile(r"\b(gvhd|thay huong dan|co huong dan|giang vien huong dan|advisor|adviser|supervisor)\b")
_NAME_STOP = {"luc", "vao", "thu", "ngay", "gio", "o", "tai", "de", "va", "sang", "chieu", "toi", "mai", "nay", "tuan", "at", "on",
              "to", "and", "for", "tomorrow", "today", "next", "this"}


def meeting_title(text: str) -> str:
    """No model: a short title from the typed text. 'Họp GVHD' only when it names the advisor or nothing else fits."""
    words = text.split()
    plain = [unaccent(w).strip(".,;:!?") for w in words]
    flat = " ".join(plain)
    if _ADVISOR.search(flat):
        return "Họp GVHD"
    for pat, title in (("hop nhom", "Họp nhóm"), ("hop lab", "Họp lab"), ("seminar", "Seminar"), ("lab meeting", "Lab meeting"),
                       ("group meeting", "Group meeting"), ("team meeting", "Team meeting")):
        if pat in flat:
            return title
    for i, w in enumerate(plain):
        who = None
        if w == "gap" and i + 1 < len(plain) and plain[i + 1] in ("thay", "co"):
            who, start, label = plain[i + 1], i + 2, f"Gặp {'thầy' if plain[i + 1] == 'thay' else 'cô'}"
        elif w in ("meet", "meeting") and i + 2 < len(plain) and plain[i + 1] == "with" and plain[i + 2] in ("prof", "professor", "dr", "dr."):
            who, start, label = "en", i + 3, f"Meeting with {words[i + 2].strip('.,;:!?').capitalize()}"
        if who:
            name = []
            for j in range(start, min(start + 2, len(words))):
                if plain[j] in _NAME_STOP or not words[j][:1].isalpha() or not words[j][:1].isupper():
                    break
                name.append(words[j].strip(".,;:!?"))
            return " ".join([label, *name])[:100]
    return "Họp GVHD"


class MeetingsMixin(ResearchBase):
    # ---- views --------------------------------------------------------------------------------------------------------
    @staticmethod
    def meeting_model(r: MeetingRow) -> Meeting:
        ag = r.agenda
        return Meeting(
            id=r.id, at=iso(r.at), title=r.title, status=r.status,
            agenda=Agenda(promised=[AgendaItem(**x) for x in ag.get("promised") or []], new_results=ag.get("new_results") or "",
                          open_questions=ag.get("open_questions") or "", drafted_at=ag.get("drafted_at"),
                          edited_at=ag.get("edited_at")) if ag else None,
            notes_md=r.notes_md, action_items=[ActionItem(**a) for a in r.action_items or []], created_at=iso(r.created_at))

    def _meeting(self, user_id: str, mid: str) -> MeetingRow:
        with self.db.session() as s:
            r = s.get(MeetingRow, mid)
            if r is None or r.user_id != user_id:
                raise fail(404, "meeting_not_found")
            s.expunge(r)
            return r

    def list_meetings(self, user_id: str, status: str = "scheduled") -> list[Meeting]:
        with self.db.session() as s:
            q = select(MeetingRow).where(MeetingRow.user_id == user_id)
            if status == "scheduled":
                q = q.where(MeetingRow.status == "scheduled").order_by(MeetingRow.at)
            elif status == "done":
                q = q.where(MeetingRow.status == "done").order_by(MeetingRow.at.desc())
            else:
                q = q.order_by(MeetingRow.at.desc())
            rows = list(s.scalars(q))
            s.expunge_all()
        return [self.meeting_model(r) for r in rows]

    def next_meeting(self, user_id: str) -> Meeting | None:
        with self.db.session() as s:
            r = s.scalars(select(MeetingRow).where(MeetingRow.user_id == user_id, MeetingRow.status == "scheduled",
                                                   MeetingRow.at > self.clock()).order_by(MeetingRow.at)).first()
            if r is not None:
                s.expunge(r)
        return self.meeting_model(r) if r else None

    # ---- create, move, delete -----------------------------------------------------------------------------------------
    async def _when(self, text: str, today: date) -> datetime:
        w = dates.parse_when(text, today)
        if w.day is None and self.llm is not None:
            try:
                d = await self.llm_json(prompts.fill(prompts.MEETING_WHEN, today=today.isoformat(),
                                                     weekday=today.strftime("%A")), text, timeout=20)
                if isinstance(d.get("date"), str):
                    w = dates.When(day=date.fromisoformat(d["date"]), clock=w.clock)
                    if isinstance(d.get("time"), str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", d["time"]):
                        w.clock = (int(d["time"][:2]), int(d["time"][3:]))
            except (ModelUnavailable, ValueError):
                pass
        if w.day is None:
            raise fail(422, "meeting_unparsed")
        if w.clock is None:
            w.clock = (9, 0)
        local = dates.to_vietnam(w)
        assert local is not None and local.time is not None
        return datetime.fromisoformat(f"{local.day.isoformat()}T{local.time}:00").replace(tzinfo=TZ)

    async def create_meeting(self, user: User, inp: MeetingInput) -> Meeting:
        now = self.clock()
        if inp.at is not None:
            at = datetime.fromisoformat(inp.at)
            at = (at if at.tzinfo else at.replace(tzinfo=TZ)).astimezone(TZ)
        else:
            at = await self._when(inp.text or "", now.astimezone(TZ).date())
        title = " ".join((inp.title or meeting_title(inp.text or "")).split())[:100] or "Họp GVHD"
        mid = new_id("mt-")
        with self.db.session() as s:
            s.add(MeetingRow(id=mid, user_id=user.id, at=at, title=title, status="scheduled", agenda=None, notes_md=None,
                             action_items=[], created_at=now))
        self.replan(user.id, "research_deadline_changed")
        return self.meeting_model(self._meeting(user.id, mid))

    def patch_meeting(self, user: User, mid: str, patch: MeetingPatch) -> Meeting:
        self._meeting(user.id, mid)
        ch = patch.model_dump(exclude_unset=True)
        with self.db.session() as s:
            r = s.get(MeetingRow, mid)
            if ch.get("at"):
                at = datetime.fromisoformat(ch["at"])
                at = (at if at.tzinfo else at.replace(tzinfo=TZ)).astimezone(UTC)
                if at != r.at:
                    r.at = at
                    if r.agenda and r.agenda.get("drafted_at"):  # the draft follows the meeting: redrafted 2 days before the new time
                        r.agenda = {**r.agenda, "drafted_at": None}
            if ch.get("title"):
                r.title = " ".join(ch["title"].split())[:100]
            if ch.get("status"):
                r.status = ch["status"]
        self.replan(user.id, "research_deadline_changed")
        return self.meeting_model(self._meeting(user.id, mid))

    def delete_meeting(self, user: User, mid: str) -> None:
        self._meeting(user.id, mid)
        with self.db.session() as s:
            s.delete(s.get(MeetingRow, mid))
        self.replan(user.id, "research_deadline_changed")

    # ---- agenda -------------------------------------------------------------------------------------------------------
    def put_agenda(self, user: User, mid: str, inp: AgendaInput) -> Meeting:
        self._meeting(user.id, mid)
        ch = inp.model_dump(exclude_unset=True)
        now = self.clock()
        with self.db.session() as s:
            r = s.get(MeetingRow, mid)
            ag = dict(r.agenda or {"promised": [], "new_results": "", "open_questions": "", "drafted_at": None, "edited_at": None})
            for k in ("new_results", "open_questions"):
                if ch.get(k) is not None:
                    ag[k] = ch[k]
            ag["edited_at"] = iso(now)
            r.agenda = ag
        return self.meeting_model(self._meeting(user.id, mid))

    def meetings_needing_agenda(self, user_id: str, now: datetime) -> list[str]:
        with self.db.session() as s:
            rows = list(s.scalars(select(MeetingRow).where(MeetingRow.user_id == user_id, MeetingRow.status == "scheduled",
                                                           MeetingRow.at > now, MeetingRow.at <= now + AGENDA_LEAD)))
            return [r.id for r in rows if not (r.agenda or {}).get("drafted_at")]

    def _agenda_facts(self, user_id: str, r: MeetingRow) -> tuple[list[dict[str, Any]], list[str]]:
        """-> (code lines [{text, done}], digest lines for the model). Facts only, each with its source."""
        today = r.at.astimezone(TZ).date()
        with self.db.session() as s:
            last = s.scalars(select(MeetingRow).where(MeetingRow.user_id == user_id, MeetingRow.status == "done",
                                                      MeetingRow.at < r.at).order_by(MeetingRow.at.desc())).first()
            since = last.at if last else self.clock() - timedelta(days=30)
            exps = list(s.scalars(select(ExperimentRow).where(ExperimentRow.user_id == user_id, ExperimentRow.created_at >= since)
                                  .order_by(ExperimentRow.created_at)))
            read = list(s.scalars(select(PaperRow.title).join(ReadingEntryRow, ReadingEntryRow.paper_id == PaperRow.id)
                                  .where(PaperRow.user_id == user_id, ReadingEntryRow.status == "read",
                                         ReadingEntryRow.read_at >= since).order_by(ReadingEntryRow.read_at)))
            actions = [dict(a) for a in (last.action_items if last else [])]
        lines: list[dict[str, Any]] = [{"text": a["text"], "done": bool(a.get("done"))} for a in actions]
        lines += [{"text": f"{e.id}: {e.title} ({e.status})", "done": True} for e in exps[-4:]]
        lines += [{"text": f"Đã đọc: {t[:100]}", "done": True} for t in read[-3:]]
        for m in milestones.load(self.db, user_id)[1]:
            due = date.fromisoformat(m["due_date"])
            if not m.get("done") and m.get("thesis") and today <= due <= today + timedelta(days=30):
                lines.append({"text": f"Mốc: {m['title']}, hạn {due.day}/{due.month}", "done": False})
        digest = [f"{'[done]' if x['done'] else '[open]'} {x['text']}" for x in lines]
        return lines[:8], digest

    async def draft_agenda(self, user: User, mid: str, *, require_model: bool) -> Meeting:
        """(Re)drafts `agenda.promised`, keeping the learner's two boxes. `require_model`: 503 without a model (the endpoint);
        the scheduler's draft falls back to the code's own lines so the agenda still exists 2 days before."""
        r = self._meeting(user.id, mid)
        lines, digest = self._agenda_facts(user.id, r)
        promised = lines
        if digest:
            try:
                data = await self.llm_json(prompts.fill(prompts.AGENDA, lang=prompts.lang_name(user.language or "vi")),
                                           "Facts:\n" + "\n".join(digest), max_tokens=900)
                items = [{"text": clean(x["text"], 160), "done": bool(x.get("done"))} for x in data.get("promised") or []
                         if isinstance(x, dict) and isinstance(x.get("text"), str) and x["text"].strip()]
                if items:
                    promised = items[:8]
            except ModelUnavailable:
                if require_model:
                    raise
        elif require_model and self.llm is None:
            raise ModelUnavailable("no model configured")
        now = self.clock()
        with self.db.session() as s:
            row = s.get(MeetingRow, mid)
            ag = dict(row.agenda or {"new_results": "", "open_questions": "", "edited_at": None})
            ag["promised"], ag["drafted_at"] = promised, iso(now)
            row.agenda = ag
        self.replan(user.id, "research_deadline_changed")  # the plan adds the "agenda ready" reminder
        return self.meeting_model(self._meeting(user.id, mid))

    # ---- notes and action items ---------------------------------------------------------------------------------------
    async def put_notes(self, user: User, mid: str, notes: str) -> Meeting:
        r = self._meeting(user.id, mid)
        today = self.clock().astimezone(TZ).date()
        notes = notes.strip()
        found: list[dict[str, Any]] | None = None
        try:
            data = await self.llm_json(prompts.fill(prompts.NOTES, today=today.isoformat(), weekday=today.strftime("%A")),
                                       notes, max_tokens=1200)
            found = []
            for a in data.get("actions") or []:
                if not (isinstance(a, dict) and isinstance(a.get("text"), str) and a["text"].strip()):
                    continue
                due = None
                if isinstance(a.get("due_date"), str):
                    try:
                        due = date.fromisoformat(a["due_date"]).isoformat()
                    except ValueError:
                        due = None
                if due is None and (w := dates.parse_when(a["text"], today)).day:
                    due = w.day.isoformat()
                found.append({"text": " ".join(a["text"].split())[:300], "due_date": due})
        except ModelUnavailable:
            found = None
        if found is None:
            found = split_actions(notes, today)
        old = {a["text"].lower(): a for a in r.action_items or []}
        items = []
        for n, a in enumerate(found[:20], 1):
            prev = old.get(a["text"].lower(), {})
            items.append({"id": f"a-{n}", "text": a["text"], "due_date": a["due_date"], "done": bool(prev.get("done")),
                          "in_plan": bool(a["due_date"])})
        with self.db.session() as s:
            row = s.get(MeetingRow, mid)
            row.status, row.notes_md, row.action_items = "done", notes, items
        self.replan(user.id, "research_meeting_notes")
        return self.meeting_model(self._meeting(user.id, mid))

    def patch_action(self, user: User, mid: str, aid: str, patch: ActionItemPatch) -> Meeting:
        r = self._meeting(user.id, mid)
        if not any(a["id"] == aid for a in r.action_items or []):
            raise fail(404, "action_not_found")
        ch = patch.model_dump(exclude_unset=True)
        with self.db.session() as s:
            row = s.get(MeetingRow, mid)
            items = [dict(a) for a in row.action_items]
            for a in items:
                if a["id"] != aid:
                    continue
                if ch.get("text"):
                    a["text"] = " ".join(ch["text"].split())[:300]
                if "due_date" in ch:
                    a["due_date"] = ch["due_date"]
                if ch.get("done") is not None:
                    a["done"] = ch["done"]
                a["in_plan"] = bool(a.get("due_date"))
            row.action_items = items
        self.replan(user.id, "research_meeting_notes")
        return self.meeting_model(self._meeting(user.id, mid))
