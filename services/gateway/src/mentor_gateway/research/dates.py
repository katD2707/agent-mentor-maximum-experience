"""Dates, times and time zones in a learner's free text ("nộp full paper 15/11, 23:59 AoE", "họp thứ Tư 11/11 14:00").

Pure functions, no model: the rules of the old `deadline-watch` skill. Everything is converted to Vietnam time (UTC+7):
AoE (anywhere on earth) is UTC-12, so 23:59 AoE on 15/11 is 18:59 on 16/11 in Vietnam. A time that was converted is kept
as `original_text` ("23:59 AoE 15/11"). No time, or a date that is only a month, is not `certain`: the milestone is
shown as "Chưa xác nhận" and gets no time-based reminder.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from mentor_gateway.planner.text import unaccent

VN = timezone(timedelta(hours=7))
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11,
           "dec": 12}
_TZ = {"aoe": -12.0, "utc": 0.0, "gmt": 0.0, "pst": -8.0, "pdt": -7.0, "est": -5.0, "edt": -4.0, "cet": 1.0, "cest": 2.0,
       "ict": 7.0, "jst": 9.0, "kst": 9.0}
_WEEKDAYS = (("thu hai", "thu 2", "monday"), ("thu ba", "thu 3", "tuesday"), ("thu tu", "thu 4", "wednesday"),
             ("thu nam", "thu 5", "thursday"), ("thu sau", "thu 6", "friday"), ("thu bay", "thu 7", "saturday"),
             ("chu nhat", "sunday"))

_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_VI_DATE = re.compile(r"\b(?:ngay\s+)?(\d{1,2})\s+(?:thang|th)\s+(\d{1,2})(?:\s+nam\s+(\d{4}))?\b")
_DMY = re.compile(r"(?<![\d:])(\d{1,2})[/.](\d{1,2})(?:[/.](\d{4}|\d{2}))?(?![\d:])")
_EN_DM = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b(?:,?\s+(\d{4}))?")
_EN_MD = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?")
_MONTH_ONLY = re.compile(r"\bthang\s+(\d{1,2})(?:\s+nam\s+(\d{4}))?\b")
_TIME_COLON = re.compile(r"(?<![\d/.])(\d{1,2}):(\d{2})(?::\d{2})?\s*(am|pm)?\b")
_TIME_H = re.compile(r"\b(\d{1,2})\s*h\s*(\d{2})?\b")
_TIME_AMPM = re.compile(r"\b(\d{1,2})\s*(am|pm)\b")
_TZ_RE = re.compile(r"\b(aoe|anywhere on earth|utc\s*[+-]\s*\d{1,2}(?::?\d{2})?|utc|gmt|pst|pdt|est|edt|cet|cest|ict|jst|kst)\b")


@dataclass
class When:
    day: date | None = None
    clock: tuple[int, int] | None = None  # in the zone the text gave
    tz_hours: float | None = None  # None = Vietnam
    tz_label: str | None = None
    certain: bool = True  # False: only a month, or no way to know the year


@dataclass
class Local:
    day: date
    time: str | None  # "HH:MM", Vietnam time
    original: str | None  # "23:59 AoE 15/11" when a time was converted
    confirmed: bool


def _valid(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _year_for(m: int, d: int, today: date, explicit: str | None) -> date | None:
    if explicit:
        y = int(explicit)
        return _valid(y + 2000 if y < 100 else y, m, d)
    here = _valid(today.year, m, d)
    if here is None:
        return None
    return here if here >= today - timedelta(days=60) else _valid(today.year + 1, m, d)


def _tz(match: str) -> tuple[float | None, str | None]:
    low = match.lower().replace(" ", "")
    if low in ("aoe", "anywhereonearth"):
        return -12.0, "AoE"
    if low.startswith("utc") and len(low) > 3:
        m = re.match(r"utc([+-])(\d{1,2})(?::?(\d{2}))?$", low)
        if m:
            h = int(m.group(2)) + (int(m.group(3)) / 60 if m.group(3) else 0)
            return (h if m.group(1) == "+" else -h), match.upper().replace(" ", "")
    if low in _TZ:
        return _TZ[low], low.upper()
    return None, None


def parse_when(text: str, today: date) -> When:
    """Read a date, a time and a zone out of `text`. Whatever is not there stays None."""
    t = unaccent(text)
    w = When()
    if m := _ISO.search(t):
        w.day = _valid(int(m[1]), int(m[2]), int(m[3]))
    elif (m := _VI_DATE.search(t)) or (m := _DMY.search(t)):
        w.day = _year_for(int(m[2]), int(m[1]), today, m[3])
    elif m := _EN_DM.search(t):
        w.day = _year_for(_MONTHS[m[2]], int(m[1]), today, m[3])
    elif m := _EN_MD.search(t):
        w.day = _year_for(_MONTHS[m[1]], int(m[2]), today, m[3])
    elif re.search(r"\b(ngay mai|tomorrow)\b", t):
        w.day = today + timedelta(days=1)
    elif re.search(r"\b(hom nay|today)\b", t):
        w.day = today
    else:
        for i, names in enumerate(_WEEKDAYS):
            if any(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", t) for n in names):
                w.day = today + timedelta(days=(i - today.weekday()) % 7 or 7)
                break
        else:
            if m := _MONTH_ONLY.search(t):
                month = int(m[1])
                year = int(m[2]) if m[2] else today.year + (1 if month < today.month else 0)
                if 1 <= month <= 12:
                    w.day = date(year, month, calendar.monthrange(year, month)[1])
                    w.certain = False
    if m := _TIME_COLON.search(t):
        h, mi, ap = int(m[1]), int(m[2]), m[3]
    elif m := _TIME_AMPM.search(t):
        h, mi, ap = int(m[1]), 0, m[2]
    elif m := _TIME_H.search(t):
        h, mi, ap = int(m[1]), int(m[2] or 0), None
    else:
        h = mi = ap = None
    if h is not None:
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        if 0 <= h < 24 and 0 <= mi < 60:
            w.clock = (h, mi)
    if m := _TZ_RE.search(t):
        w.tz_hours, w.tz_label = _tz(m[1])
    elif re.search(r"\b(gio vn|vietnam|viet nam)\b", t):
        w.tz_hours, w.tz_label = 7.0, "VN"
    return w


def to_vietnam(w: When) -> Local | None:
    """Vietnam date and time of `w` (None without a date). Converts when the text named another zone."""
    if w.day is None:
        return None
    if w.clock is None:
        return Local(w.day, None, None, False)
    zone = timezone(timedelta(hours=w.tz_hours)) if w.tz_hours is not None else VN
    at = datetime(w.day.year, w.day.month, w.day.day, w.clock[0], w.clock[1], tzinfo=zone)
    vn = at.astimezone(VN)
    original = None
    if w.tz_hours is not None and w.tz_hours != 7.0:
        original = f"{w.clock[0]:02d}:{w.clock[1]:02d} {w.tz_label} {w.day.day:02d}/{w.day.month:02d}"
    return Local(vn.date(), vn.strftime("%H:%M"), original, w.certain)


def zone_hours(name: str | None) -> float | None:
    """`MilestoneInput.tz` ("AoE", "UTC", "Asia/Ho_Chi_Minh") -> hours from UTC; None when unknown."""
    if not name:
        return 7.0
    h, _ = _tz(name)
    if h is not None:
        return h
    if name.lower() in ("asia/ho_chi_minh", "asia/saigon", "vn", "vietnam"):
        return 7.0
    try:
        from zoneinfo import ZoneInfo

        off = datetime(2026, 1, 1, tzinfo=ZoneInfo(name)).utcoffset()
        return off.total_seconds() / 3600 if off is not None else None
    except Exception:  # noqa: BLE001 - unknown zone name
        return None


_CI = [re.compile(rx.pattern, re.IGNORECASE) for rx in (_ISO, _DMY, _EN_DM, _EN_MD, _TIME_COLON, _TIME_H, _TIME_AMPM, _TZ_RE)]
_VI_DATE_CI = re.compile(r"ng[àa]y\s+\d{1,2}\s+th[áa]ng\s+\d{1,2}(?:\s+n[ăa]m\s+\d{4})?", re.IGNORECASE)
_FILLER = re.compile(r"\b(ngày|hạn chót|hạn|trước|lúc|vào|deadline|due|by)\b", re.IGNORECASE)


def strip_when(text: str) -> str:
    """The text without its date, time and zone tokens: a fallback title for a deadline or a meeting."""
    out = _VI_DATE_CI.sub(" ", text)
    for rx in _CI:
        out = rx.sub(" ", out)
    out = _FILLER.sub(" ", out)
    return re.sub(r"\s+", " ", re.sub(r"[,;:()\-–—]+", " ", out)).strip()
