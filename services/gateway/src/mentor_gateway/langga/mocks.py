"""Làng gà additions to the practice engine, mixed into `PracticeService`:

- course mock exams (`source: "course-mock:<course_id>"`), timed sessions of kind `mock` built from the course's own quiz
  items, run by the same code as bank mocks (deadline, flag, auto-finish at 0, score out of 10);
- Arena papers (`source: "paper:<id>"`), the same runner over a `Paper`'s parts and points;
- the XP hooks of answer / fix / finish (CONTRACTS-LANGGA section 1). Awards run after the engine's own transaction.
"""

import dataclasses
import logging
import secrets
from datetime import timedelta
from typing import Any

from mentor_schemas.paper import Paper
from sqlalchemy import select

from mentor_gateway.content.store import ComingSoon, ContentError
from mentor_gateway.langga import subjects
from mentor_gateway.langga import xp as xpm
from mentor_gateway.langga.papers import BEAT_SCORE, boss_for
from mentor_gateway.langga.resolve import ChickenResolver
from mentor_gateway.practice import assembler as asm
from mentor_gateway.practice import scoring
from mentor_gateway.practice.sources import quiz_to_item
from mentor_gateway.practice.tables import PracticeSession

log = logging.getLogger(__name__)

COURSE_MOCK_PREFIX, PAPER_PREFIX = "course-mock:", "paper:"
MIN_COURSE_MOCK_ITEMS = 6
COURSE_MOCK_ITEMS = 22
MINUTES_PER_ITEM = 2
MOCK_MAX_MINUTES = 45
MOCK_LEVEL_MIX = [0.4, 0.3, 0.2, 0.1]


def course_mock_size(n_items: int) -> tuple[int, int]:
    """(items, minutes) of a course mock for a course that has `n_items` quiz items."""
    n = min(COURSE_MOCK_ITEMS, n_items)
    return n, min(MOCK_MAX_MINUTES, MINUTES_PER_ITEM * n)


def pick_spread(items: list, n: int, seed: int) -> list:
    """`n` items of mixed difficulty (40/30/20/10 over levels 1-4, filled from any level when one is short), deterministic."""
    by_level: dict[int, list] = {lv: [] for lv in (1, 2, 3, 4)}
    for it in sorted(items, key=lambda i: (asm.jitter(seed, i.id), i.id)):
        by_level[it.level].append(it)
    quota = {lv: 0 for lv in by_level}
    for lv in asm.level_sequence(n, MOCK_LEVEL_MIX):
        quota[lv] += 1
    chosen: list = []
    for lv in by_level:
        chosen += by_level[lv][: quota[lv]]
    if len(chosen) < n:
        left = [i for lv in by_level for i in by_level[lv][quota[lv]:]]
        chosen += sorted(left, key=lambda i: (asm.jitter(seed, i.id), i.id))[: n - len(chosen)]
    return chosen


class LanggaSessions:
    """Methods of `PracticeService` (`self.db`, `self.bank`, `self.clock`, `self.content` come from the service)."""

    papers: Any = None  # PaperStore, set by context.py
    xp: Any = None  # XpService, set by context.py
    resolver: ChickenResolver | None = None  # set by app.py once the ContentService exists

    # ---- starting ----------------------------------------------------------------------------------------

    def _open_timed(self, user_id: str, subject: str, records: list[dict], params: dict, parts: list[dict] | None,
                    minutes: int, seed: int) -> dict:
        from mentor_gateway.practice.service import PracticeError

        self._finish_due(user_id)  # type: ignore[attr-defined]
        with self.db.session() as s:  # type: ignore[attr-defined]
            blocking = next((x for x in self._active_rows(s, user_id, subject)  # type: ignore[attr-defined]
                             if x.kind != "practice"), None)
            if blocking is not None:
                raise PracticeError(409, "active_session", "Bạn đang có một bài làm dở trong môn này.",
                                    session_id=blocking.id, kind=blocking.kind)
        now = self.clock()  # type: ignore[attr-defined]
        types = {r["doc"]["type"] for r in records}
        params = {**params, "minutes": minutes, "goal": "balanced", "topics": [], "mixed": True, "mock": True,
                  "scoring": scoring.policy_for(types, None)}
        sid = f"p-{secrets.token_hex(6)}"
        with self.db.session() as s:  # type: ignore[attr-defined]
            s.add(PracticeSession(id=sid, user_id=user_id, kind="mock", subject=subject[:32], status="active",
                                  profile_id=None, seed=seed, params=params, items=records, parts=parts, position=0,
                                  started_at=now, deadline=now + timedelta(minutes=minutes), total=len(records)))
        return self.get(user_id, sid)  # type: ignore[attr-defined]

    def _start_course_mock(self, user_id: str, course_id: str, body: dict) -> dict:
        from mentor_gateway.practice.service import PracticeError

        if self.content is not None:  # type: ignore[attr-defined]
            try:
                self.content.ensure_available(course_id)  # type: ignore[attr-defined]
            except ComingSoon:
                raise PracticeError(409, "coming_soon", "Khóa học này sắp có.") from None
            except ContentError:
                pass
        bundles = self.bundles(user_id, course_id)  # type: ignore[attr-defined]
        if not bundles:
            raise PracticeError(404, "course_not_found", "Em chưa tham gia khóa học này.")
        bundle = bundles[0]
        if len(bundle.items) < MIN_COURSE_MOCK_ITEMS:
            raise PracticeError(422, "insufficient_content",
                                "Khóa học này chưa đủ câu hỏi để làm bài kiểm tra; mentor sẽ bổ sung dần.",
                                available=len(bundle.items), required=MIN_COURSE_MOCK_ITEMS)
        seed = body.get("seed")
        seed = secrets.randbelow(2**31) if seed is None else int(seed)
        n, minutes = course_mock_size(len(bundle.items))
        chosen = [asm.Selected(i) for i in pick_spread(bundle.items, n, seed)]
        ordered = asm._order(chosen, seed)
        records = [self._record(i, sel) for i, sel in enumerate(ordered)]  # type: ignore[attr-defined]
        params = {"source": f"{COURSE_MOCK_PREFIX}{course_id}", "course_id": course_id,
                  "course_title": bundle.title, "band": bundle.age_band}
        return self._open_timed(user_id, f"cm:{course_id}", records, params, None, minutes, seed)

    def _paper_records(self, paper: Paper) -> tuple[list[dict], list[dict]]:
        label = subjects.CHICKENS[paper.chicken].vi
        records: list[dict] = []
        parts: list[dict] = []
        for pi, part in enumerate(paper.parts, start=1):
            pts = paper.points_of(part)
            positions = []
            for q in part.items:
                item = quiz_to_item(q, course_id=f"paper-{paper.id}"[:60], version=1, course_title=paper.title_vi,
                                    subject_label=label, lesson_id=part.id, lesson_title=part.title_vi, lesson_index=pi,
                                    bank=self.bank)  # type: ignore[attr-defined]
                doc = {k: v for k, v in item.doc.items() if k != "course"}
                item = dataclasses.replace(item, doc=doc, topic=f"{paper.id}/{part.id}")
                pos = len(records)
                positions.append(pos)
                records.append({"position": pos, "doc": doc, "topic": item.topic, "level": item.level, "part": pi,
                                "points_each": pts, "seconds": item.seconds, "skill_ids": list(item.skill_ids),
                                "subject": item.subject, "topic_title": part.title_vi})
            parts.append({"part": pi, "label": part.title_vi, "type": part.type, "points_each": pts, "positions": positions})
        return records, parts

    def _start_paper(self, user_id: str, paper_id: str, body: dict) -> dict:
        from mentor_gateway.practice.service import PracticeError

        paper = self.papers.get(paper_id) if self.papers is not None else None
        if paper is None:
            raise PracticeError(404, "unknown_paper", "Không tìm thấy đề này.")
        user = self._user(user_id)  # type: ignore[attr-defined]
        if subjects.band_or_default(user.age_band if user else None) != paper.band:
            raise PracticeError(403, "band_mismatch", "Đề này không dành cho cấp học của em.")
        records, parts = self._paper_records(paper)
        seed = secrets.randbelow(2**31)
        params = {"source": f"{PAPER_PREFIX}{paper.id}", "paper": paper_meta(paper), "band": paper.band}
        return self._open_timed(user_id, f"pp:{paper.id}", records, params, parts, paper.minutes, seed)

    # ---- XP hooks ----------------------------------------------------------------------------------------

    def _band_of(self, user_id: str) -> str | None:
        user = self._user(user_id)  # type: ignore[attr-defined]
        return user.age_band if user else None

    def _item_chicken(self, user_id: str, params: dict, rec: dict) -> str:
        band = self._band_of(user_id)
        paper = params.get("paper")
        if paper:
            return paper["chicken"]
        source = str(params.get("source") or "")
        if source.startswith("notes:"):
            from mentor_gateway.ask.tables import NotesSet

            with self.db.session() as s:  # type: ignore[attr-defined]
                row = s.get(NotesSet, source[6:])
                label = row.subject if row is not None else ""
            return subjects.chicken_of(label, band) if label else (self.resolver.fallback(band) if self.resolver else "kn")
        if self.resolver is None:
            return "kn"
        return self.resolver.of_doc(rec["doc"], band)

    def _award(self, user_id: str, awards: list[tuple[str, str, str, int]]) -> list[dict]:
        if self.xp is None or not awards:
            return []
        try:
            return self.xp.award_many(user_id, awards)
        except Exception:
            log.exception("xp award failed")
            return []

    def _langga_answer(self, user_id: str, sid: str, position: int, res: dict) -> dict:
        """After a practice answer: +2 for a right one (`practice_right`, or `notes_review` in a notes session)."""
        if res.get("correct") is not True:
            return {**res, "xp": []} if "correct" in res else res
        with self.db.session() as s:  # type: ignore[attr-defined]
            sess = s.get(PracticeSession, sid)
            if sess is None or sess.kind != "practice":
                return res
            rec, params = sess.items[position], dict(sess.params or {})
        notes = str(params.get("source") or "").startswith("notes:")
        source = "notes_review" if notes else "practice_right"
        chicken = self._item_chicken(user_id, params, rec)
        return {**res, "xp": self._award(user_id, [(chicken, source, f"{sid}:{rec['doc']['id']}", xpm.AMOUNTS[source])])}

    def _langga_fix(self, user_id: str, sid: str, item_id: str, res: dict) -> dict:
        if res.get("correct") is not True:
            return {**res, "xp": []}
        with self.db.session() as s:  # type: ignore[attr-defined]
            sess = s.get(PracticeSession, sid)
            rec = next((r for r in sess.items if r["doc"]["id"] == item_id), None) if sess else None
            params = dict(sess.params or {}) if sess else {}
        if rec is None:
            return res
        chicken = self._item_chicken(user_id, params, rec)
        return {**res, "xp": self._award(user_id, [(chicken, "fix_right", f"{sid}:{item_id}", xpm.AMOUNTS["fix_right"])])}

    def _langga_finish(self, user_id: str, sid: str, report: dict) -> dict:
        """Called once, when a session is finished: mock/paper submit XP and the boss of an Arena paper."""
        with self.db.session() as s:  # type: ignore[attr-defined]
            sess = s.get(PracticeSession, sid)
            if sess is None or sess.kind != "mock":
                return report
            params, first = dict(sess.params or {}), (sess.items[0] if sess.items else None)
        answered = int(report.get("answered") or 0)
        score = report.get("score_10") or 0.0
        awards: list[tuple[str, str, str, int]] = []
        paper = params.get("paper")
        if paper:
            boss = dict(paper.get("boss") or boss_for(paper["chicken"]))
            report["boss"] = {"name": boss["name_vi"], **boss, "hp": int(report.get("total") or 0),
                              "damage": int(report.get("correct") or 0), "beaten": score >= BEAT_SCORE}
            if answered:
                awards.append((paper["chicken"], "paper_submit", sid, xpm.AMOUNTS["paper_submit"]))
                if score >= BEAT_SCORE:
                    awards.append((paper["chicken"], "boss_beaten", paper["id"], xpm.AMOUNTS["boss_beaten"]))
        elif answered and first is not None:
            awards.append((self._item_chicken(user_id, params, first), "mock_submit", sid, xpm.AMOUNTS["mock_submit"]))
        report["xp"] = self._award(user_id, awards)
        return report

    # ---- reads for the Arena and the chicken page ---------------------------------------------------------

    def paper_results(self, user_id: str) -> dict[str, dict]:
        """paper id -> {best_score, beaten, attempts} from the student's finished paper sessions."""
        out: dict[str, dict] = {}
        with self.db.session() as s:  # type: ignore[attr-defined]
            for sess in s.scalars(select(PracticeSession).where(
                    PracticeSession.user_id == user_id, PracticeSession.kind == "mock",
                    PracticeSession.status.in_(("finished", "expired")))):
                paper = (sess.params or {}).get("paper")
                if not paper:
                    continue
                row = out.setdefault(paper["id"], {"best_score": None, "beaten": False, "attempts": 0})
                row["attempts"] += 1
                sc = sess.score_10
                if sc is not None and (row["best_score"] is None or sc > row["best_score"]):
                    row["best_score"] = sc
                row["beaten"] = row["beaten"] or (sc is not None and sc >= BEAT_SCORE)
        return out

    def last_scores(self, user_id: str) -> dict[str, float | None]:
        """source (`course-mock:<id>` or `mock:<profile>`) -> score of the latest finished mock."""
        out: dict[str, float | None] = {}
        with self.db.session() as s:  # type: ignore[attr-defined]
            for sess in s.scalars(select(PracticeSession).where(
                    PracticeSession.user_id == user_id, PracticeSession.kind == "mock",
                    PracticeSession.status.in_(("finished", "expired"))).order_by(PracticeSession.started_at.desc())):
                src = (sess.params or {}).get("source") or (f"mock:{sess.profile_id}" if sess.profile_id else None)
                if src:
                    out.setdefault(src, sess.score_10)
        return out


def paper_meta(paper: Paper) -> dict:
    return {"id": paper.id, "kind": paper.kind, "chicken": paper.chicken, "title_vi": paper.title_vi,
            "title_en": paper.title_en, "placeholder": paper.placeholder, "boss": boss_for(paper.chicken)}
