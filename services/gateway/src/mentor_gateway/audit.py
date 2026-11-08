"""Content-free audit rows (`audit_log`): which notification action was applied, never what it was about."""

from mentor_gateway.db import AuditRow, Database
from mentor_gateway.settings import Clock


class AuditLog:
    def __init__(self, db: Database, clock: Clock) -> None:
        self.db = db
        self.clock = clock

    def record(self, user_id: str, kind: str, detail: str = "") -> None:
        with self.db.session() as s:
            s.add(AuditRow(student_user_id=user_id, kind=kind, detail=detail, created_at=self.clock()))
