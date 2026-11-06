"""Practice, mock exams and progress (CONTRACTS section 10). Import tables so `create_all` sees them."""

from mentor_gateway.practice import tables  # noqa: F401  (registers the ops.db tables)
from mentor_gateway.practice.bank import Bank
from mentor_gateway.practice.service import PracticeError, PracticeService

__all__ = ["Bank", "PracticeError", "PracticeService"]
