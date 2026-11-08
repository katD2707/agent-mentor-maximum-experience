"""Scheduler loop (plan 4.3, 7.5): routines.yaml crons in the learner's timezone plus `next_wake` jobs.

Each tick: (1) turn due routine occurrences into job rows, (2) run due jobs, (3) flush pending
notifications that quiet hours or the daily cap held back, (4) put idle sandboxes to sleep.
Quiet hours never delay jobs, only notifications.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from croniter import croniter
from mentor_schemas import JobKind
from sqlalchemy import select

from mentor_gateway.db import Database, JobRow, RoutineSchedule
from mentor_gateway.jobs import JobRunner
from mentor_gateway.notifications import NotificationHub
from mentor_gateway.routine_policy import routine_violation
from mentor_gateway.settings import Clock
from mentor_gateway.users import UserService

log = logging.getLogger(__name__)


def next_run(cron: str, tz: str, after: datetime) -> datetime:
    local = after.astimezone(ZoneInfo(tz))
    nxt = croniter(cron, local).get_next(datetime)
    return nxt.astimezone(UTC)


class Scheduler:
    def __init__(self, db: Database, users: UserService, runner: JobRunner, hub: NotificationHub,
                 clock: Clock, interval: float = 30.0) -> None:
        self.db = db
        self.users = users
        self.runner = runner
        self.hub = hub
        self.clock = clock
        self.interval = interval
        self.practice_sweep: Any = None  # PracticeService.sweep: auto-finishes mocks whose deadline passed (set by context)
        self.planner: Any = None  # PlannerService.tick: nightly/weekly/event-driven replans (set by context)
        self.research: Any = None  # ResearchService.tick: Monday discovery, agenda drafts (set by app)
        self.backups: Any = None  # backup.BackupService when the daily backup job is enabled (set by context)
        self._stopping = asyncio.Event()

    def materialize_routines(self, now: datetime) -> list[str]:
        """Create job rows for routine occurrences that are due. Returns the new job ids."""
        created = []
        for user in self.users.all_provisioned():
            if not self.users.is_active(user):
                continue
            try:
                rf = self.users.routines(user)
            except Exception:
                log.exception("reading routines of %s", user.id)
                continue
            wanted = {r.id: r for r in rf.routines if r.enabled}
            with self.db.session() as s:
                existing = {
                    row.routine_id: row
                    for row in s.scalars(select(RoutineSchedule).where(RoutineSchedule.user_id == user.id))
                }
                for rid, row in existing.items():
                    if rid not in wanted:
                        s.delete(row)
                for rid, routine in wanted.items():
                    try:
                        kind = JobKind(routine.job_kind)
                        if not croniter.is_valid(routine.cron):
                            raise ValueError(routine.cron)
                    except ValueError:
                        log.warning("routine %s of %s is invalid; skipped", rid, user.id)
                        continue
                    if routine_violation(routine, from_user=False):
                        # e.g. the agent wrote an every-minute or extra platform routine into routines.yaml
                        log.warning("routine %s of %s breaks the routine policy; skipped", rid, user.id)
                        continue
                    row = existing.get(rid)
                    if row is None or row.cron != routine.cron or row.timezone != rf.timezone:
                        if row is None:
                            row = RoutineSchedule(user_id=user.id, routine_id=rid)
                            s.add(row)
                        row.cron, row.timezone = routine.cron, rf.timezone
                        row.next_run_at = next_run(routine.cron, rf.timezone, now)
                        continue
                    if row.next_run_at > now:
                        continue
                    job_id = f"r-{user.id}-{rid}-{row.next_run_at.strftime('%Y%m%d%H%M')}"
                    if s.get(JobRow, job_id) is None:
                        s.add(JobRow(id=job_id, user_id=user.id, kind=kind.value, prompt=routine.prompt, payload={},
                                     source=f"routine:{rid}", scheduled_for=row.next_run_at, status="pending",
                                     created_at=now))
                        created.append(job_id)
                    row.next_run_at = next_run(routine.cron, rf.timezone, now)
        return created

    async def tick(self, now: datetime | None = None) -> list[str]:
        now = now or self.clock()
        await asyncio.to_thread(self.materialize_routines, now)
        started = self.runner.run_due(now)
        if self.practice_sweep is not None:
            await asyncio.to_thread(self.practice_sweep)
        await self.hub.flush_all()
        if self.planner is not None:
            await self.planner(now)
        if self.research is not None:
            await self.research(now)
        if self.backups is not None:
            await self.backups.maybe_run(now)  # starts the daily snapshot run in a thread; never blocks the tick
        return started

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopping.set()
