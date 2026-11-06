"""Workspace layout and write permissions (plan section 6.1).

The workspace is a git repo, one per learner. Paths here are POSIX-style and
relative to the workspace root.
"""

from enum import Enum
from fnmatch import fnmatch
from pathlib import PurePosixPath


class Profile(str, Enum):
    THPT = "thpt"
    NCS = "ncs"


class WorkspacePaths:
    AGENTS_MD = "AGENTS.md"  # mentor identity + operating rules, platform-managed

    ME_DIR = "me"
    PROFILE = "me/profile.md"
    PEOPLE = "me/people.md"
    PREFERENCES = "me/preferences.md"
    NOW = "me/now.md"
    WHAT_WORKS = "me/what-works.md"
    JOURNAL_DIR = "me/journal"  # me/journal/YYYY-MM-DD.md

    GOALS = "goals/goals.md"
    PLAN_WEEK = "goals/plans/this-week.md"
    PLAN_TERM = "goals/plans/term.md"

    LEARNING_DIR = "learning"  # THPT: learning/<subject>/{skills,mistakes,review-queue}.md
    EVIDENCE_DIR = "learning/evidence"
    RESEARCH_DIR = "research"  # NCS: thesis.md, papers/, reading-queue.md, experiments/, meetings/
    REPORTS_DIR = "reports"  # THPT: reports/YYYY-MM-DD.md, reports already SENT to the parent (gateway writes)
    INBOX_DIR = "inbox"  # uploads and forwarded email land here
    SESSIONS_DIR = "sessions"  # sessions/YYYY-MM-DD/<session_id>.md, raw transcripts (no automatic deletion yet; account deletion removes them)

    ROUTINES = "routines.yaml"
    EVENTS = "events.jsonl"  # append-only, written only by the record_event script

    MENTOR_DIR = ".mentor"
    SKILLS_DIR = ".mentor/skills"  # <group>/<skill-name>/SKILL.md
    CURRICULA_DIR = ".mentor/curricula"
    WELLBEING = ".mentor/wellbeing.jsonl"  # THPT only, written only by the record_wellbeing script
    ACTIVITY = ".mentor/activity.jsonl"  # written only by the harness
    # THPT: the agent drafts parent reports here (hidden from the learner). After the gateway delivers one to
    # the parent it moves it to reports/<same name>; learners only ever see sent reports.
    REPORT_DRAFTS_DIR = ".mentor/report-drafts"


# Globs the agent's file tools may write. Everything else is read-only to the agent.
AGENT_WRITABLE_GLOBS: tuple[str, ...] = (
    "me/*.md",
    "me/journal/*.md",
    "goals/*.md",
    "goals/plans/*.md",
    "learning/**",
    "research/**",
    "inbox/**",
    "routines.yaml",
)

# Narrow exceptions inside otherwise read-only areas (checked before AGENT_READONLY_GLOBS).
# reports/ is not agent-writable: only the gateway writes there, when a draft has been sent.
AGENT_WRITABLE_EXCEPTIONS: tuple[str, ...] = (".mentor/report-drafts/*.md",)

# Read-only to the agent's file tools. events.jsonl and wellbeing.jsonl change only
# through scripts the agent may run; activity.jsonl and sessions/ only through the harness.
AGENT_READONLY_GLOBS: tuple[str, ...] = (
    "AGENTS.md",
    ".mentor/**",
    "events.jsonl",
    "sessions/**",
    ".git/**",
)


def _match(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch(path, pattern) and path.count("/") == pattern.count("/")


def is_agent_writable(path: str) -> bool:
    """True if the agent's write/edit/delete tools may touch this workspace-relative path."""
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts:
        return False
    norm = p.as_posix()
    if any(_match(norm, g) for g in AGENT_WRITABLE_EXCEPTIONS):
        return True
    if any(_match(norm, g) for g in AGENT_READONLY_GLOBS):
        return False
    return any(_match(norm, g) for g in AGENT_WRITABLE_GLOBS)
