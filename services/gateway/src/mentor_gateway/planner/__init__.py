"""Study planner (REQUIREMENTS-PLAN 3.6, 3.7): behaviour events, study profile, LLM planner, validator, fallback, reminders."""

from mentor_gateway.planner import tables as _tables  # noqa: F401  (registers the tables before create_all)
from mentor_gateway.planner.service import PlannerService

__all__ = ["PlannerService"]
