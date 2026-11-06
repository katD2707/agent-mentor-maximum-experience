"""wellbeing_window: share of negative days in the recent window (plan 7.6, tier 2 nudge).

Input: {days: 30, threshold: 0.4, today?: "YYYY-MM-DD"}.
Output: {days_recorded, negative_ratio, trigger_nudge, min_days_required, window_start, window_end}.

Rule: the window is the `days` calendar days ending today (inclusive). negative_ratio is
negative days / recorded days. trigger_nudge is true only when
  - at least ceil(days / 2) days were recorded (15 of 30 by default), so a handful of logged
    bad days cannot trigger a parent nudge on their own, and
  - negative_ratio is strictly greater than threshold ("vượt ngưỡng").
"""

import math
from datetime import timedelta
from pathlib import Path
from typing import Any

from mentor_schemas import WellbeingEntry, WellbeingLevel, WorkspacePaths

from mentor_scripts.common import ScriptError, parse_today, read_jsonl, run_cli, validate_or_none


def min_days_required(days: int) -> int:
    return math.ceil(days / 2)


def wellbeing_window(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    days = payload.get("days", 30)
    threshold = payload.get("threshold", 0.4)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 366:
        raise ScriptError("days must be an integer between 1 and 366")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0 <= threshold <= 1:
        raise ScriptError("threshold must be a number between 0 and 1")
    today = parse_today(payload)
    start = today - timedelta(days=days - 1)

    levels: dict[str, WellbeingLevel] = {}
    for obj in read_jsonl(root / WorkspacePaths.WELLBEING):
        e = validate_or_none(WellbeingEntry, obj)  # corrupt lines are ignored
        if e is not None and start <= e.date <= today:
            levels[e.date.isoformat()] = e.level  # last line wins if a date repeats

    recorded = len(levels)
    negative = sum(1 for lv in levels.values() if lv == WellbeingLevel.NEGATIVE)
    ratio = negative / recorded if recorded else 0.0
    need = min_days_required(days)
    return {
        "days_recorded": recorded,
        "negative_ratio": round(ratio, 4),
        "trigger_nudge": recorded >= need and ratio > threshold,
        "min_days_required": need,
        "window_start": start.isoformat(),
        "window_end": today.isoformat(),
    }


def main() -> None:
    run_cli(wellbeing_window)


if __name__ == "__main__":
    main()
