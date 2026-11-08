"""routines.yaml (plan section 7.5)."""

from enum import Enum

import yaml
from pydantic import BaseModel, Field


class ProactivityLevel(str, Enum):
    OFF = "off"
    NORMAL = "normal"  # default: at most 1 notification/day
    HIGH = "high"


class Routine(BaseModel):
    id: str  # e.g. "nightly_reflection", "evening_review"
    enabled: bool = True
    cron: str = Field(description="5-field cron in the learner's timezone, e.g. '30 23 * * *'")
    job_kind: str  # a JobKind value
    prompt: str | None = None  # extra instruction for the job
    user_editable: bool = True  # nightly_reflection is not


class RoutinesFile(BaseModel):
    timezone: str = "Asia/Ho_Chi_Minh"
    proactivity: ProactivityLevel = ProactivityLevel.NORMAL
    quiet_hours: tuple[str, str] = ("22:00", "07:00")
    routines: list[Routine] = []

    @classmethod
    def parse_yaml(cls, text: str) -> "RoutinesFile":
        return cls.model_validate(yaml.safe_load(text) or {})

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
