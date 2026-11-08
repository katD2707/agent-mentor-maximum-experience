"""Plain data the planner works on (built by service.py from the DB; tests build it by hand)."""

from dataclasses import dataclass, field
from datetime import date, datetime

from mentor_gateway.planner.bands import Band

KINDS = ("lesson", "review", "practice", "break", "research")
REMINDER_KINDS = ("study", "break", "nudge", "research")
STATUSES = ("on_track", "slightly_behind", "behind", "new")
WEEKDAYS_VI = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
WEEKDAYS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass
class LessonInfo:
    id: str
    title: str
    minutes: int
    done: bool = False
    started: bool = False  # some blocks done or it is the last-opened lesson


@dataclass
class CourseInfo:
    id: str
    title: str
    subject: str = ""
    lessons: list[LessonInfo] = field(default_factory=list)
    progress_pct: float = 0.0
    last_lesson_id: str | None = None
    enrolled_at: datetime | None = None
    updated_at: datetime | None = None

    def remaining_minutes(self) -> int:
        return sum(ls.minutes for ls in self.lessons if not ls.done)

    def lesson(self, lesson_id: str | None) -> LessonInfo | None:
        return next((ls for ls in self.lessons if ls.id == lesson_id), None)


@dataclass
class GoalInfo:
    id: str
    title: str
    kind: str  # student | inferred
    deadline: date | None
    course_ids: list[str]
    progress_pct: float = 0.0
    remaining_minutes: int = 0
    required_min_per_day: float | None = None
    status: str = "new"
    line_vi: str = ""
    line_en: str = ""
    created_at: datetime | None = None


@dataclass
class PlanContext:
    now: datetime
    band: Band
    courses: list[CourseInfo]
    goals: list[GoalInfo]
    profile: dict
    due_items: list[dict]  # FSRS: [{item, course_id, lesson_id?, overdue_days, ...}]
    quiet_until: datetime | None = None
    moves: list[dict] = field(default_factory=list)
    old_items: list[dict] = field(default_factory=list)  # previous plan, to explain moves
    trigger: str = "nightly"
    missed_recent: int = 0
    last_nudge_at: datetime | None = None
    language: str = "vi"

    @property
    def course_ids(self) -> set[str]:
        return {c.id for c in self.courses}

    def course(self, course_id: str | None) -> CourseInfo | None:
        return next((c for c in self.courses if c.id == course_id), None)
