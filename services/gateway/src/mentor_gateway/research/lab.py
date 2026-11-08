"""Experiment log (CONTRACTS 15.6). Mentor restates the learner's note in fixed fields and never interprets it. Without a
model the note is stored as it is (`structured: false`), never a 503."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import re

from mentor_schemas import ModelAlias
from mentor_schemas.research import Experiment, ExperimentInput, ExperimentList, ExperimentPatch
from sqlalchemy import and_, func, or_, select

from mentor_gateway.ask.llm import image_part
from mentor_gateway.db import User
from mentor_gateway.mirror import normalize_path
from mentor_gateway.planner.bands import TZ
from mentor_gateway.research import prompts
from mentor_gateway.research.base import ModelUnavailable, ResearchBase, fail, iso
from mentor_gateway.research.tables import ExperimentRow

log = logging.getLogger(__name__)

STATUSES = ("running", "done", "failed", "cancelled")
_COMMIT = re.compile(r"\b(?:commit|branch)\s*[:=#]?\s*([0-9a-f]{7,40}|[A-Za-z][\w./-]{1,60})", re.IGNORECASE)
_SEED = re.compile(r"\bseeds?\s*[:=]?\s*(\d{1,10})", re.IGNORECASE)


def suffix(i: int) -> str:
    """a..z, then aa, ab, ... (CONTRACTS 15.6)."""
    if i < 26:
        return chr(97 + i)
    j = i - 26
    return chr(97 + (j // 26) % 26) + chr(97 + j % 26)


def _s(v: object, cap: int) -> str:
    return " ".join(v.split())[:cap] if isinstance(v, str) else ""


class LabMixin(ResearchBase):
    @staticmethod
    def exp_model(r: ExperimentRow) -> Experiment:
        return Experiment(id=r.id, date=r.date, title=r.title, status=r.status, aim=r.aim, setup=r.setup, result=r.result,
                          user_note=r.user_note, next=r.next, commit=r.commit, seed=r.seed,
                          missing=[f for f in ("commit", "seed") if not getattr(r, f)], photo_path=r.photo_path,
                          raw_text=r.raw_text, structured=r.structured, created_at=iso(r.created_at), updated_at=iso(r.updated_at))

    def _get_exp(self, user_id: str, eid: str) -> ExperimentRow:
        with self.db.session() as s:
            r = s.get(ExperimentRow, (eid, user_id))
            if r is None:
                raise fail(404, "experiment_not_found")
            s.expunge(r)
            return r

    def list_experiments(self, user_id: str, limit: int = 20, before: str | None = None) -> ExperimentList:
        limit = max(1, min(limit, 50))
        with self.db.session() as s:
            q = select(ExperimentRow).where(ExperimentRow.user_id == user_id)
            if before:
                ref = s.get(ExperimentRow, (before, user_id))
                if ref is not None:
                    older = or_(func.length(ExperimentRow.id) < len(ref.id),
                                and_(func.length(ExperimentRow.id) == len(ref.id), ExperimentRow.id < ref.id))
                    q = q.where(or_(ExperimentRow.created_at < ref.created_at,
                                    and_(ExperimentRow.created_at == ref.created_at, older)))
            # same instant: later ids first (a..z, then aa: a longer id is later)
            rows = list(s.scalars(q.order_by(ExperimentRow.created_at.desc(), func.length(ExperimentRow.id).desc(),
                                             ExperimentRow.id.desc()).limit(limit + 1)))
            s.expunge_all()
        more = len(rows) > limit
        rows = rows[:limit]
        return ExperimentList(items=[self.exp_model(r) for r in rows], next_before=rows[-1].id if more and rows else None)

    def get_experiment(self, user_id: str, eid: str) -> Experiment:
        return self.exp_model(self._get_exp(user_id, eid))

    async def create_experiment(self, user: User, inp: ExperimentInput) -> Experiment:
        photo = None
        if inp.photo_path:
            try:
                norm = normalize_path(inp.photo_path)
            except ValueError:
                raise fail(404, "upload_not_found") from None
            got = await asyncio.to_thread(self.mirror.read, user.id, norm)
            if got is None:
                raise fail(404, "upload_not_found")
            photo = (norm, got[0])
        text = inp.text.strip()
        table = ""
        if photo is not None and self.llm is not None:
            mime = mimetypes.guess_type(photo[0])[0] or "image/jpeg"
            try:
                table = (await asyncio.wait_for(self.llm.complete(
                    ModelAlias.VISION.value, [{"role": "user", "content": [{"type": "text", "text": prompts.TABLE_PHOTO},
                                                                          image_part(photo[1], mime)]}],
                    max_tokens=1200, temperature=0.0), self.llm_timeout)).strip()
            except Exception:
                log.info("experiment photo not read", exc_info=True)
        data: dict | None = None
        try:
            body = f"Student's text:\n{text}" + (f"\n\nTable copied from the student's photo:\n{table}" if table else "")
            data = await self.llm_json(prompts.EXPERIMENT, body, max_tokens=1200)
        except ModelUnavailable:
            data = None
        now = self.clock()
        day = now.astimezone(TZ).date().isoformat()
        fields = self._fields(text, data)
        with self.db.session() as s:
            have = set(s.scalars(select(ExperimentRow.id).where(ExperimentRow.user_id == user.id,
                                                                ExperimentRow.id.like(f"EXP-{day}-%"))))
            i = 0
            while f"EXP-{day}-{suffix(i)}" in have:
                i += 1
            eid = f"EXP-{day}-{suffix(i)}"
            s.add(ExperimentRow(id=eid, user_id=user.id, date=day, photo_path=photo[0] if photo else None, raw_text=text,
                                structured=data is not None, created_at=now, updated_at=now, **fields))
        self.event(user, "experiment_logged", eid, {"experiment_id": eid, "status": fields["status"]})
        return self.get_experiment(user.id, eid)

    @staticmethod
    def _fields(text: str, data: dict | None) -> dict:
        if data is None:  # no model: the note as it is
            cm, sd = _COMMIT.search(text), _SEED.search(text)  # still "taken from the text when present" (15.6)
            return {"title": text[:60], "status": "done", "aim": "", "setup": "", "result": "", "user_note": "", "next": "",
                    "commit": cm.group(1)[:64] if cm else None, "seed": sd.group(1) if sd else None}
        status = data.get("status") if data.get("status") in STATUSES else "done"
        commit = _s(data.get("commit"), 64) or None
        seed = _s(data.get("seed"), 32) or None
        if commit is None and (m := _COMMIT.search(text)):  # taken from the text when it is there
            commit = m.group(1)[:64]
        if seed is None and (m := _SEED.search(text)):
            seed = m.group(1)
        return {"title": _s(data.get("title"), 60) or text[:60], "status": status, "aim": _s(data.get("aim"), 1000),
                "setup": _s(data.get("setup"), 2000), "result": _s(data.get("result"), 2000),
                "user_note": _s(data.get("user_note"), 2000), "next": _s(data.get("next"), 1000), "commit": commit, "seed": seed}

    def patch_experiment(self, user: User, eid: str, patch: ExperimentPatch) -> Experiment:
        self._get_exp(user.id, eid)
        changes = patch.model_dump(exclude_unset=True)
        with self.db.session() as s:
            r = s.get(ExperimentRow, (eid, user.id))
            for k, v in changes.items():
                if v is None and k not in ("commit", "seed"):
                    continue
                setattr(r, k, (v.strip() or None) if k in ("commit", "seed") and isinstance(v, str) else v)
            r.updated_at = self.clock()
        return self.get_experiment(user.id, eid)
