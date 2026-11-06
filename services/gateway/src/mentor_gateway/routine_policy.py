"""Limits on routines.yaml entries (CONTRACTS section 5 `PUT /settings`).

Learners (via the settings API) and the agent (it may write routines.yaml) can add routines, but:
- platform job kinds (`parent_report`, `nightly_reflection`) run only from the fixed platform routines that
  provisioning creates (`user_editable: false`, routine id == job kind); nobody may add more of them;
- no routine may run more than once per MIN_ROUTINE_INTERVAL.
The settings API rejects violations with 422; the scheduler skips violating routines found in routines.yaml.
"""

from datetime import datetime, timedelta

from croniter import croniter
from mentor_schemas import JobKind, Routine

PLATFORM_JOB_KINDS = frozenset({JobKind.PARENT_REPORT.value, JobKind.NIGHTLY_REFLECTION.value})
MIN_ROUTINE_INTERVAL = timedelta(hours=1)


def min_cron_gap(cron: str, samples: int = 200) -> timedelta:
    """Smallest gap between consecutive runs among the next `samples` runs (enough for minute/hour/day patterns)."""
    it = croniter(cron, datetime(2026, 1, 1))
    prev = it.get_next(datetime)
    gap = timedelta.max
    for _ in range(samples):
        nxt = it.get_next(datetime)
        gap = min(gap, nxt - prev)
        prev = nxt
    return gap


def platform_routine_ok(r: Routine) -> bool:
    """A platform job kind is allowed only in its own fixed routine (id == job kind, not user editable)."""
    return r.job_kind not in PLATFORM_JOB_KINDS or (r.id == r.job_kind and not r.user_editable)


def routine_violation(r: Routine, *, from_user: bool) -> str | None:
    """Vietnamese reason why the routine may not run, or None. `from_user`: added/changed through the settings API."""
    if r.job_kind in PLATFORM_JOB_KINDS and (from_user or not platform_routine_ok(r)):
        return f"Lịch '{r.id}': loại việc '{r.job_kind}' do hệ thống tự lên lịch, bạn không thể tự thêm."
    if croniter.is_valid(r.cron) and min_cron_gap(r.cron) < MIN_ROUTINE_INTERVAL:
        return (f"Lịch '{r.id}' chạy quá dày ('{r.cron}'): mỗi lịch chỉ được chạy tối đa 1 lần mỗi giờ.")
    return None
