"""Background jobs: a durable queue in the ops DB and a runner that posts JobRequests to sandboxes.

Every job source (routines.yaml, `next_wake`, inbound email, ...) inserts a `jobs` row; the scheduler
tick runs the due ones. One job or turn at a time per learner (the orchestrator's lock).
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from mentor_schemas import JobKind, JobRequest, JobResult
from mentor_schemas.interaction import CRISIS_REFUSED_KINDS
from sqlalchemy import select

from mentor_gateway.db import Database, JobRow
from mentor_gateway.outbox import OutboxDispatcher
from mentor_gateway.sandbox import Orchestrator, SandboxSpec
from mentor_gateway.security import new_id
from mentor_gateway.settings import Clock
from mentor_gateway.users import UserService

log = logging.getLogger(__name__)


class JobStore:
    """Implements mentor_schemas.JobQueue (sync, thread-safe: the email ingest may call it from another thread)."""

    def __init__(self, db: Database, clock: Clock) -> None:
        self.db = db
        self.clock = clock

    def enqueue(self, job: JobRequest, source: str = "queue") -> None:
        with self.db.session() as s:
            if s.get(JobRow, job.job_id) is not None:
                return  # idempotent on job_id
            s.add(
                JobRow(id=job.job_id or new_id("j"), user_id=job.user_id, kind=JobKind(job.kind).value,
                       prompt=job.prompt, payload=job.payload, source=source,
                       scheduled_for=job.scheduled_for or self.clock(), status="pending", created_at=self.clock())
            )

    def claim_due(self, now: datetime) -> list[JobRow]:
        with self.db.session() as s:
            rows = list(
                s.scalars(
                    select(JobRow)
                    .where(JobRow.status == "pending", JobRow.scheduled_for <= now)
                    .order_by(JobRow.scheduled_for)
                )
            )
            for r in rows:
                r.status = "running"
                r.started_at = now
            return rows

    def finish(self, job_id: str, status: str, summary: str | None = None, error: str | None = None) -> None:
        with self.db.session() as s:
            row = s.get(JobRow, job_id)
            if row is None:
                return
            row.status = status
            row.summary = summary
            row.error = error
            row.finished_at = self.clock()

    def get(self, job_id: str) -> JobRow | None:
        with self.db.session() as s:
            return s.get(JobRow, job_id)

    def for_user(self, user_id: str) -> list[JobRow]:
        with self.db.session() as s:
            return list(s.scalars(select(JobRow).where(JobRow.user_id == user_id).order_by(JobRow.created_at)))


class JobRunner:
    def __init__(self, store: JobStore, users: UserService, orchestrator: Orchestrator, dispatcher: OutboxDispatcher,
                 workspace_path, clock: Clock) -> None:
        self.store = store
        self.users = users
        self.orchestrator = orchestrator
        self.dispatcher = dispatcher
        self.workspace_path = workspace_path
        self.clock = clock
        self.nudges: Any = None  # nudges.NudgeService (proactive routine gating, gateway-only routines); set by context
        self._tasks: set[asyncio.Task] = set()

    def run_due(self, now: datetime) -> list[str]:
        started = []
        for row in self.store.claim_due(now):
            task = asyncio.create_task(self.run(row))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            started.append(row.id)
        return started

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def run(self, row: JobRow) -> JobResult | None:
        user = self.users.get(row.user_id)
        if user is None or self.users.onboarding_state(user) != "active":
            self.store.finish(row.id, "skipped", error="user missing or not active")
            return None
        if self.nudges is not None:
            handled = await self.nudges.before_job(user, row)
            if handled is not None:
                status, summary, error = handled
                self.store.finish(row.id, status, summary=summary, error=error)
                return None
        profile = self.users.profile(user)
        hub = self.dispatcher.hub
        req = JobRequest(job_id=row.id, user_id=user.id, profile=profile, kind=JobKind(row.kind), prompt=row.prompt,
                         payload=row.payload or {}, scheduled_for=row.scheduled_for,
                         crisis_hold=hub.hold_active(user.id))  # the harness then refuses celebration/weekly cards
        spec = SandboxSpec(user_id=user.id, profile=profile, workspace_dir=self.workspace_path(user.id))
        try:
            async with self.orchestrator.session(spec) as client:
                result = await client.job(req)
        except Exception as exc:
            log.exception("job %s failed", row.id)
            self.store.finish(row.id, "error", error=str(exc)[:1000])
            return None
        await self.dispatcher.dispatch(user.id, profile, result.outbox)
        # chat cards the job wrote into today's transcript (already in the mirror): show them in an open chat too,
        # except celebratory ones while a crisis hold is active (also set by this job's own crisis alert)
        held = hub.hold_active(user.id)
        for card in result.cards:
            if held and card.get("kind") in CRISIS_REFUSED_KINDS:
                continue
            await hub.send(user.id, {"type": "card", "card": card})
        self.store.finish(row.id, result.status, summary=result.summary, error=result.error)
        return result
