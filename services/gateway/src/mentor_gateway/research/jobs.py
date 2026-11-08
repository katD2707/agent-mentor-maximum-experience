"""Quick review and weekly discovery (CONTRACTS 15.4): polled jobs with a 1-hour TTL, plus the scheduler hook.

The job rows are in memory (a review table is not stored; a discovery result is its suggestions). Review = `literature_pass`
(arXiv) then ONE model call that fills the matrix from the abstracts. Discovery = `discover_frontier` (arXiv, read-only),
drop what the learner already has, dismissed or was suggested, then one model call for a one-line reason per paper.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from mentor_schemas.research import (
    REVIEW_MAX_FOLLOWUPS,
    REVIEW_MAX_PAPERS,
    SUGGESTIONS_FEATURED,
    SUGGESTIONS_PER_WEEK,
    DiscoveryResult,
    JobProgress,
    JobStarted,
    ResearchJob,
    ReviewRequest,
    ReviewResult,
    ReviewRow,
    SearchRun,
)
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from mentor_gateway.db import JobRow, User
from mentor_gateway.planner.bands import TZ
from mentor_gateway.planner.text import clean, unaccent
from mentor_gateway.research import prompts
from mentor_gateway.research.profile_keys import title_keywords
from mentor_gateway.research.base import JOB_TTL, ModelUnavailable, ResearchBase, fail, iso, new_id
from mentor_gateway.research.tables import PaperRow, ReadingEntryRow, ResearchProfileRow, SuggestionRow

log = logging.getLogger(__name__)

_NOT_STATED = {"", "null", "none", "n/a", "không nêu", "abstract không nêu", "not stated", "not stated in the abstract"}


def cell(v: Any) -> str | None:
    """A matrix cell: None when the model said the abstract does not state it."""
    if not isinstance(v, str):
        return None
    t = " ".join(v.split())
    return None if t.lower().strip(" .") in _NOT_STATED else t[:300]


class JobsMixin(ResearchBase):
    # ---- job store ----------------------------------------------------------------------------------------------------
    def _new_job(self, user_id: str, kind: str) -> dict[str, Any]:
        now = self.clock()
        for jid in [j for j, row in self.jobs.items() if now - row["created_at"] > JOB_TTL]:
            del self.jobs[jid]
        job = {"id": new_id("rj-"), "user_id": user_id, "kind": kind, "status": "queued", "progress": None, "result": None,
               "error": None, "created_at": now, "finished_at": None}
        self.jobs[job["id"]] = job
        return job

    def _running(self, user_id: str, kind: str) -> dict[str, Any] | None:
        return next((j for j in self.jobs.values() if j["user_id"] == user_id and j["kind"] == kind
                     and j["status"] in ("queued", "running")), None)

    def _finish(self, job: dict[str, Any], *, result: Any = None, error: str | None = None) -> None:
        job.update(status="failed" if error else "done", result=None if error else result, error=error,
                   finished_at=self.clock())

    def job_view(self, user_id: str, job_id: str) -> ResearchJob:
        job = self.jobs.get(job_id)
        if job is None or job["user_id"] != user_id or self.clock() - job["created_at"] > JOB_TTL:
            raise fail(404, "job_not_found")
        return ResearchJob(id=job["id"], kind=job["kind"], status=job["status"], progress=job["progress"], result=job["result"],
                           error=job["error"], created_at=iso(job["created_at"]), finished_at=iso(job["finished_at"]))

    # ---- review -------------------------------------------------------------------------------------------------------
    def start_review(self, user: User, req: ReviewRequest) -> JobStarted:
        running = self._running(user.id, "review")
        if running is not None:
            raise fail(409, "job_running", job_id=running["id"])
        self.limiter.require(user.id, "review", 10, timedelta(hours=1))
        query = " ".join(req.query.split())
        if not query:
            raise fail(422, "empty_query")
        job = self._new_job(user.id, "review")
        self.bg(self._run_review(job, user.id, user.language or "vi", query, req.year_min,
                                 [f for f in (" ".join(x.split()) for x in req.followups) if f][:REVIEW_MAX_FOLLOWUPS]))
        return JobStarted(job_id=job["id"], status="queued")

    async def _run_review(self, job: dict[str, Any], user_id: str, lang: str, query: str, year_min: int | None,
                          followups: list[str]) -> None:
        job["status"], job["progress"] = "running", JobProgress(stage="searching")
        try:
            lit = await self.literature(query, followups, client=self.lit_client)
        except Exception as exc:  # noqa: BLE001 - ResearchError, HTTP errors, anything: the search did not work
            log.info("review search failed: %s", exc.__class__.__name__)
            return self._finish(job, error="search_failed")
        found = [p for p in lit.papers if year_min is None or p.year is None or p.year >= year_min][:REVIEW_MAX_PAPERS]
        cards = [self.card_of_arxiv(p) for p in found]
        job["progress"] = JobProgress(stage="reading", total=len(found), done=0)
        _t, _q, kws = self.topic(user_id)
        try:
            rows, chips = await self._review_rows(found, lang, query, kws)
        except ModelUnavailable:
            return self._finish(job, error="model_unavailable")
        job["progress"] = JobProgress(stage="reading", total=len(found), done=len(found))
        self._finish(job, result=ReviewResult(
            query=query, papers=cards, matrix=rows, followups=chips, searches=[SearchRun(query=s.query, count=s.count) for s in lit.searches],
            coverage=lit.coverage))

    async def _review_rows(self, found: list[Any], lang: str, query: str, kws: list[str]) -> tuple[list[ReviewRow], list[str]]:
        if not found:
            return [], self._fallback_followups(query, kws)
        keys = {self.fields_of_arxiv(p)["key"]: p for p in found}
        payload = "\n\n".join(f"key: {k}\ntitle: {p.title}\nabstract: {p.abstract[:1800]}" for k, p in keys.items())
        data = await self.llm_json(prompts.fill(prompts.REVIEW_ROWS, lang=prompts.lang_name(lang)),
                                   f"Review query: {query}\n\n{payload}", max_tokens=2600)
        by_key = {r.get("key"): r for r in data.get("rows") or [] if isinstance(r, dict)}
        rows = []
        for k in keys:  # one row per paper, in card order; a paper the model skipped gets nulls, never invented cells
            r = by_key.get(k) or {}
            rows.append(ReviewRow(key=k, problem=cell(r.get("problem")), method=cell(r.get("method")), data=cell(r.get("data")),
                                  result=cell(r.get("result"))))
        chips = []
        for f in data.get("followups") or []:
            if isinstance(f, str) and len(f.split()) >= 2 and unaccent(f) != unaccent(query) and f.strip() not in chips:
                chips.append(" ".join(f.split())[:120])
        return rows, (chips or self._fallback_followups(query, kws))[:REVIEW_MAX_FOLLOWUPS]

    @staticmethod
    def _fallback_followups(query: str, kws: list[str]) -> list[str]:
        have = unaccent(query)
        return [k for k in kws if len(k.split()) >= 2 and unaccent(k) not in have][:REVIEW_MAX_FOLLOWUPS]

    # ---- discovery ----------------------------------------------------------------------------------------------------
    def start_discovery(self, user: User, *, manual: bool) -> JobStarted | None:
        """Manual (POST /research/discovery): 409 while running, 422 without a topic, 429 beyond 1 per 6 hours. Automatic
        (profile set, Monday): returns None when one is running or there is no topic."""
        title, _q, _k = self.topic(user.id)
        running = self._running(user.id, "discovery")
        if manual:
            if not title:
                raise fail(422, "empty_title")
            if running is not None:
                raise fail(409, "job_running", job_id=running["id"])
            self.limiter.require(user.id, "discovery", 1, timedelta(hours=6))
        elif running is not None or not title:
            return None
        job = self._new_job(user.id, "discovery")
        self.bg(self._run_discovery(job, user.id, user.language or "vi"))
        return JobStarted(job_id=job["id"], status="queued")

    def _taken_keys(self, user_id: str) -> set[str]:
        """Papers not to suggest: in the list now, accepted or dismissed before."""
        with self.db.session() as s:
            listed = set(s.scalars(select(PaperRow.key).join(ReadingEntryRow, ReadingEntryRow.paper_id == PaperRow.id)
                                   .where(PaperRow.user_id == user_id, ReadingEntryRow.removed_at.is_(None))))
            decided = set(s.scalars(select(PaperRow.key).join(SuggestionRow, SuggestionRow.paper_id == PaperRow.id)
                                    .where(SuggestionRow.user_id == user_id, SuggestionRow.status.in_(("accepted", "dismissed")))))
        return listed | decided

    def _set_discovery_status(self, user_id: str, status: str) -> None:
        with self.db.session() as s:
            row = s.get(ResearchProfileRow, user_id)
            if row is not None:
                row.discovery_last_run_at, row.discovery_last_status = self.clock(), status

    @staticmethod
    def _usable_keywords(title: str, kws: list[str]) -> list[str]:
        """No model: keywords the user typed or edited always count; the ones taken from the title words count only in English."""
        if kws != title_keywords(title):
            return kws
        return [k for k in kws if k.isascii()]

    def discovery_waiting(self, user_id: str) -> bool:
        row = self.profile_row(user_id)
        return bool(row and row.discovery_last_status == "waiting_model")

    async def _run_discovery(self, job: dict[str, Any], user_id: str, lang: str) -> None:
        job["status"] = "running"
        title, _question, kws = self.topic(user_id)
        if self.llm is None:  # no model: only English keywords make a usable arXiv query
            kws = self._usable_keywords(title, kws)
            title = title if title.isascii() else " ".join(kws)
            if not kws:
                self._set_discovery_status(user_id, "waiting_model")
                return self._finish(job, result=DiscoveryResult(status="papers_not_found", queries=[], new_suggestions=0))
        try:
            fr = await self.frontier(title, "", SUGGESTIONS_PER_WEEK, 3, keywords=kws, llm=self.llm, searcher=self.arxiv_searcher)
        except Exception as exc:  # noqa: BLE001
            log.info("discovery search failed: %s", exc.__class__.__name__)
            self._set_discovery_status(user_id, "failed")
            return self._finish(job, error="search_failed")
        taken = self._taken_keys(user_id)
        fresh = []
        for p in fr.papers:
            f = self.fields_of_arxiv(p)
            if f["key"] not in taken and f["key"] not in {x[0]["key"] for x in fresh}:
                fresh.append((f, p.source_query or ""))
            if len(fresh) >= SUGGESTIONS_PER_WEEK:
                break
        if not fresh:
            self._set_discovery_status(user_id, "papers_not_found")
            return self._finish(job, result=DiscoveryResult(status="papers_not_found", queries=fr.queries[:3], new_suggestions=0))
        reasons = await self._reasons(user_id, lang, title, kws, [f for f, _ in fresh])
        now = self.clock()
        week_of = (now.astimezone(TZ).date() - timedelta(days=now.astimezone(TZ).weekday())).isoformat()
        ids = [self.upsert_paper(user_id, f) for f, _ in fresh]
        with self.db.session() as s:
            s.execute(delete(SuggestionRow).where(SuggestionRow.user_id == user_id, SuggestionRow.status == "pending"))
            for i, ((f, query), pid) in enumerate(zip(fresh, ids, strict=True)):
                s.add(SuggestionRow(id=new_id("sg-"), user_id=user_id, paper_id=pid, week_of=week_of,
                                    reason=reasons.get(f["key"]) or self.fallback_reason(f, kws, lang, query), query=query[:300],
                                    featured=i < SUGGESTIONS_FEATURED, status="pending",
                                    created_at=now + timedelta(microseconds=i)))  # keeps the discovery order
        self._set_discovery_status(user_id, "papers_found")
        self._finish(job, result=DiscoveryResult(status="papers_found", queries=fr.queries[:3], new_suggestions=len(fresh)))

    async def _reasons(self, user_id: str, lang: str, title: str, kws: list[str], fields: list[dict[str, Any]]) -> dict[str, str]:
        with self.db.session() as s:
            read = list(s.scalars(select(PaperRow.title).join(ReadingEntryRow, ReadingEntryRow.paper_id == PaperRow.id)
                                  .where(PaperRow.user_id == user_id, ReadingEntryRow.status == "read",
                                         ReadingEntryRow.removed_at.is_(None)).order_by(ReadingEntryRow.read_at.desc()).limit(8)))
        body = "\n\n".join(f"key: {f['key']}\ntitle: {f['title']}\nabstract: {(f.get('abstract') or '')[:700]}" for f in fields)
        try:
            data = await self.llm_json(
                prompts.fill(prompts.DISCOVERY_REASONS, lang=prompts.lang_name(lang)),
                f"Thesis title: {title}\nKeywords: {', '.join(kws)}\nPapers the student read: {'; '.join(read) or '(none yet)'}\n\n"
                f"NEW papers:\n{body}", max_tokens=2000)
        except ModelUnavailable:
            return {}
        out = {}
        for r in data.get("reasons") or []:
            if isinstance(r, dict) and isinstance(r.get("key"), str) and isinstance(r.get("reason"), str) and r["reason"].strip():
                out[r["key"]] = clean(r["reason"], 200)
        return out

    # ---- scheduler ----------------------------------------------------------------------------------------------------
    async def tick(self, now: datetime | None = None, *, force: bool = False) -> list[str]:
        """Scheduler hook: Monday 06:00 discovery and the agenda draft 2 days before a meeting, for `uni` learners.
        -> what ran, as "discovery:<user>" / "agenda:<meeting>"."""
        import asyncio

        now = now or self.clock()
        ran: list[str] = []
        for user in await asyncio.to_thread(self.users.all_provisioned):
            if not self.users.is_active(user) or user.age_band != "uni":
                continue
            last = self._checked.get(user.id)
            if not force and last is not None and now - last < timedelta(minutes=5):
                continue
            self._checked[user.id] = now
            try:
                ran += await self._tick_user(user, now)
            except Exception:
                log.exception("research tick for %s", user.id)
        return ran

    async def _tick_user(self, user: User, now: datetime) -> list[str]:
        import asyncio

        ran: list[str] = []
        loc = now.astimezone(TZ)
        title, _q, _k = self.topic(user.id)
        if title and self.llm is not None and self.discovery_waiting(user.id) and self.start_discovery(user, manual=False) is not None:
            ran.append(f"discovery:{user.id}")  # a model is back: the run that was waiting for it
        if title and loc.weekday() == 0 and loc.hour >= 6:  # Monday 06:00 local, once per Monday
            jid = f"lw-{user.id}-{loc.date().isoformat()}"
            try:
                with self.db.session() as s:
                    s.add(JobRow(id=jid, user_id=user.id, kind="literature_watch", prompt=None, payload={}, source="research",
                                 scheduled_for=now, status="ok", created_at=now, started_at=now, finished_at=now,
                                 summary="weekly discovery"))
                if self.start_discovery(user, manual=False) is not None:
                    ran.append(f"discovery:{user.id}")
            except IntegrityError:
                pass  # already started today
        for mid in await asyncio.to_thread(self.meetings_needing_agenda, user.id, now):
            try:
                await self.draft_agenda(user, mid, require_model=False)
                ran.append(f"agenda:{mid}")
            except Exception:
                log.exception("agenda draft of %s", mid)
        return ran
