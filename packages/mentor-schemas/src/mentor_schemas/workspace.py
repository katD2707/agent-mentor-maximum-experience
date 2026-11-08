"""Workspace layout and write permissions (plan section 6.1).

The workspace is a git repo, one per learner. Paths here are POSIX-style and
relative to the workspace root.
"""

from enum import Enum
from fnmatch import fnmatch
from pathlib import PurePosixPath


class Profile(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"


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

    LEARNING_DIR = "learning"  # learning/<subject>/{skills,mistakes,review-queue}.md
    EVIDENCE_DIR = "learning/evidence"
    INBOX_DIR = "inbox"  # uploads and forwarded email land here
    SESSIONS_DIR = "sessions"  # sessions/YYYY-MM-DD/<session_id>.md, raw transcripts (no automatic deletion yet; account deletion removes them)

    ROUTINES = "routines.yaml"
    EVENTS = "events.jsonl"  # append-only, written only by the record_event script

    MENTOR_DIR = ".mentor"
    SKILLS_DIR = ".mentor/skills"  # <group>/<skill-name>/SKILL.md
    CURRICULA_DIR = ".mentor/curricula"
    ACTIVITY = ".mentor/activity.jsonl"  # written only by the harness


# Globs the agent's file tools may write. Everything else is read-only to the agent.
AGENT_WRITABLE_GLOBS: tuple[str, ...] = (
    "me/*.md",
    "me/journal/*.md",
    "goals/*.md",
    "goals/plans/*.md",
    "learning/**",
    "inbox/**",
    "routines.yaml",
)

# Read-only to the agent's file tools. events.jsonl changes only
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
    if any(_match(norm, g) for g in AGENT_READONLY_GLOBS):
        return False
    return any(_match(norm, g) for g in AGENT_WRITABLE_GLOBS)
