"""Shared contracts for the AI mentor. See CONTRACTS.md at the repo root.

Every service imports from here; nobody redefines these shapes locally.
"""

from mentor_schemas.activity import ActivityEntry
from mentor_schemas.events import EvidenceMode, LearningEvent, WellbeingEntry, WellbeingLevel
from mentor_schemas.models import ModelAlias
from mentor_schemas.protocols import JobQueue, ParentLink, ParentLinkStore, UserDirectory, WorkspaceWriter
from mentor_schemas.reports import (
    AI_DISCLAIMER,
    REPORT_EMAIL_PATTERN,
    REPORT_FORBIDDEN_PATTERNS,
    REPORT_PHONE_PATTERN,
    REPORT_PRIVATE_PATH_PATTERN,
    ParentReport,
)
from mentor_schemas.routines import ProactivityLevel, Routine, RoutinesFile
from mentor_schemas.sandbox_api import (
    ApprovalDecision,
    ApprovalRequest,
    Attachment,
    CardAction,
    JobKind,
    JobRequest,
    JobResult,
    NotificationAction,
    NotifyPayload,
    OutboxItem,
    OutboxKind,
    SandboxEvent,
    TurnRequest,
)
from mentor_schemas.workspace import (
    AGENT_READONLY_GLOBS,
    AGENT_WRITABLE_GLOBS,
    Profile,
    WorkspacePaths,
    is_agent_writable,
)

__all__ = [
    "AGENT_READONLY_GLOBS",
    "AGENT_WRITABLE_GLOBS",
    "AI_DISCLAIMER",
    "REPORT_EMAIL_PATTERN",
    "REPORT_FORBIDDEN_PATTERNS",
    "REPORT_PHONE_PATTERN",
    "REPORT_PRIVATE_PATH_PATTERN",
    "ActivityEntry",
    "ApprovalDecision",
    "ApprovalRequest",
    "Attachment",
    "CardAction",
    "EvidenceMode",
    "JobKind",
    "JobQueue",
    "JobRequest",
    "JobResult",
    "LearningEvent",
    "ModelAlias",
    "NotificationAction",
    "NotifyPayload",
    "OutboxItem",
    "OutboxKind",
    "ParentLink",
    "ParentLinkStore",
    "ParentReport",
    "ProactivityLevel",
    "Profile",
    "Routine",
    "RoutinesFile",
    "SandboxEvent",
    "TurnRequest",
    "UserDirectory",
    "WellbeingEntry",
    "WellbeingLevel",
    "WorkspacePaths",
    "WorkspaceWriter",
    "is_agent_writable",
]
