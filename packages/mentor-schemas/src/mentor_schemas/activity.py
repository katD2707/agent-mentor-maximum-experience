from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ActivityEntry(BaseModel):
    """One line of .mentor/activity.jsonl, written by the harness and shown to the learner.

    Crisis alerts are never written here; they are recorded only in the control
    plane's audit table (plan section 8.3).
    """

    ts: datetime
    actor: Literal["mentor", "user", "system"]
    action: str  # e.g. "write_file", "memory_forget", "job:nightly_reflection", "notify_user"
    target: str | None = None  # workspace path or job id
    summary: str  # one short Vietnamese sentence the learner can read
    session_id: str | None = None
    job_id: str | None = None
