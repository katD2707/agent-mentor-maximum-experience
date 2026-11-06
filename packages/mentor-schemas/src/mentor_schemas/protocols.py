"""Interfaces that let services/parent-channel and services/email-ingest be built as
libraries while services/gateway owns the database and wires them in.
"""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

from mentor_schemas.sandbox_api import JobRequest


class ParentLink(BaseModel):
    student_user_id: str
    link_code: str  # 6 digits shown in the student's app; parent sends it to the Zalo bot
    code_expires_at: datetime
    zalo_chat_id: str | None = None
    status: Literal["pending", "awaiting_consent", "verified", "revoked"] = "pending"
    verified_at: datetime | None = None


class ParentLinkStore(Protocol):
    def get_by_code(self, link_code: str) -> ParentLink | None: ...
    def get_by_chat(self, zalo_chat_id: str) -> ParentLink | None: ...
    def get_by_student(self, student_user_id: str) -> ParentLink | None: ...
    def save(self, link: ParentLink) -> None: ...
    def record_audit(self, student_user_id: str, kind: str, detail: str) -> None:
        """Crisis alerts and consent events. Stored in the control plane only, never in the workspace."""
        ...


class UserDirectory(Protocol):
    def user_id_for_inbound_address(self, address: str) -> str | None:
        """Map <code>@inbox.<domain> to a user id."""
        ...


class WorkspaceWriter(Protocol):
    def write_inbox_file(self, user_id: str, relative_name: str, data: bytes) -> str:
        """Write into the user's inbox/ and return the workspace-relative path."""
        ...


class JobQueue(Protocol):
    def enqueue(self, job: JobRequest) -> None: ...
