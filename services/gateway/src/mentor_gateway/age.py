"""Age band from the birth year (CONTRACTS section 4). Never stored as truth: it is worked out per request.

The Vietnamese school year starts in September; grade 1 is the school year in which a child turns 6, so
`grade = school_year_start - birth_year - 5`. Grade 5 and below is `g1_5` (before grade 1 counts too), 6-9
`g6_9`, 10-12 `g10_12`, above that `uni`. Age and grade are internal and never shown to the learner.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime

BIRTH_YEAR_MIN = 1950
BIRTH_YEAR_MAX = 2025

# Representative birth year for a stored band, used once to migrate rows that only had an age_band: the
# middle of the band, so the migrated learner stays in it for a few years (`grade = school_year - year - 5`).
_MIGRATE_GRADE = {"g1_5": 3, "g6_9": 8, "g10_12": 11, "uni": 14}

_today: Callable[[], date] = lambda: datetime.now(UTC).date()  # noqa: E731


def set_today_provider(clock: Callable[[], datetime] | None) -> None:
    """The gateway clock (tests freeze it). None restores the system date."""
    global _today
    _today = (lambda: clock().date()) if clock else (lambda: datetime.now(UTC).date())


def today() -> date:
    return _today()


def school_year_start(on: date) -> int:
    return on.year if on.month >= 9 else on.year - 1


def grade_for(birth_year: int, on: date | None = None) -> int:
    return school_year_start(on or today()) - birth_year - 5


def band_for_birth_year(birth_year: int | None, on: date | None = None) -> str | None:
    if birth_year is None:
        return None
    grade = grade_for(birth_year, on)
    return "g1_5" if grade <= 5 else "g6_9" if grade <= 9 else "g10_12" if grade <= 12 else "uni"


def birth_year_for_band(band: str, on: date | None = None) -> int | None:
    g = _MIGRATE_GRADE.get(band)
    return None if g is None else school_year_start(on or today()) - g - 5
