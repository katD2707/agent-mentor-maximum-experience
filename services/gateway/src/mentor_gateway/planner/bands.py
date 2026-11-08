"""Age-band defaults and bounds (REQUIREMENTS-PLAN 3.7, layer 2 "Tuần đầu" and the hard-constraint layer)."""

from dataclasses import dataclass
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
EARLIEST_MIN = 6 * 60 + 30  # no study session or reminder before 06:30 local


@dataclass(frozen=True)
class Band:
    id: str
    start_min: int  # default session start, minutes after local midnight (cold start)
    minutes: int  # default session length (cold start)
    min_minutes: int  # session length bounds (hard constraint)
    max_minutes: int
    bedtime_min: int  # no reminder at or after this local time; no session starts after it
    break_after: int  # continuous minutes before a break reminder
    sessions_per_week: int  # cold-start cadence


def _hm(h: int, m: int = 0) -> int:
    return h * 60 + m


BANDS: dict[str, Band] = {
    "g1_5": Band("g1_5", _hm(18), 10, 5, 15, _hm(20, 30), 20, 4),
    "g6_9": Band("g6_9", _hm(19, 30), 20, 15, 30, _hm(21, 30), 40, 4),
    "g10_12": Band("g10_12", _hm(19, 30), 20, 15, 30, _hm(22, 30), 50, 4),
    "uni": Band("uni", _hm(20), 30, 20, 45, _hm(23, 30), 60, 4),
}


def band_for(age_band: str | None) -> Band:
    return BANDS.get(age_band or "", BANDS["g10_12"])


def hhmm(minutes: int) -> str:
    minutes = max(0, min(minutes, 24 * 60 - 1))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def to_min(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)
