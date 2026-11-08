"""Layer 2 (3.7): the study profile, computed by code from behaviour events. No model involved.

| metric | how |
|---|---|
| windows | study starts per 30-minute slot x weekday, weight halves every 14 days |
| session_minutes | where accuracy or speed first drops within a session (median over sessions); else observed length; else age default |
| cadence | days studied per week, median of the last 3 weeks |
| reminder_response | share of reminders opened per slot; slots ignored 3 times in a row are `avoid_slots` |
| ask | questions asked in Hỏi đáp and course cards opened from an answer, last 14 days (no text, no practice answers: those are PracticeAnswer rows) |
| due items | FSRS (fsrs_items.py), added by the service |
| cold start | age-band defaults (bands.py) until there are 3 sessions |
"""

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from mentor_gateway.planner.bands import TZ, Band, hhmm

HALF_LIFE_DAYS = 14.0
GAP = timedelta(minutes=30)  # activity further apart than this starts a new session
ACTIVITY = ("session_start", "focus_tick", "lesson_progress", "video_watch", "quiz_answer",
            "paper_opened", "paper_read", "summary_written", "experiment_logged")  # the last four: Nghiên cứu (15.9)
MIN_SESSIONS = 3  # below this the profile is "cold" and age defaults rule
AVOID_AFTER_IGNORED = 3
MIN_ANSWERS_FOR_DROP = 6


def local(ts: datetime) -> datetime:
    return ts.astimezone(TZ)


def slot_of(ts: datetime) -> str:
    t = local(ts)
    return hhmm((t.hour * 60 + t.minute) // 30 * 30)


def sessions(events: list[dict]) -> list[dict]:
    """Cluster activity events (gap > 30 min = new session). [{start, end, active_s, answers: [(ts, correct, sec)]}]"""
    acts = sorted((e for e in events if e["kind"] in ACTIVITY), key=lambda e: e["ts"])
    out: list[dict] = []
    for e in acts:
        if not out or e["ts"] - out[-1]["end"] > GAP:
            out.append({"start": e["ts"], "end": e["ts"], "active_s": 0, "answers": []})
        s = out[-1]
        s["end"] = max(s["end"], e["ts"])
        if e["kind"] == "focus_tick":
            s["active_s"] += int(e["data"].get("seconds") or 0)
        elif e["kind"] == "quiz_answer":
            s["answers"].append((e["ts"], bool(e["data"].get("correct")), float(e["data"].get("seconds") or 0)))
    for s in out:  # no focus ticks: the span of the activity is the best estimate we have
        if not s["active_s"]:
            s["active_s"] = int((s["end"] - s["start"]).total_seconds())
    return out


def drop_minute(sess: dict) -> float | None:
    """Minutes into the session where a 3-answer window first loses >= 1/3 of the opening accuracy or answers
    >= 1.6x slower than the opening median. None when the session is too short or never drops."""
    a = sess["answers"]
    if len(a) < MIN_ANSWERS_FOR_DROP:
        return None
    acc0 = sum(1 for _, c, _ in a[:3] if c) / 3
    sec0 = statistics.median(x for _, _, x in a[:3]) or 1.0
    for i in range(3, len(a)):
        win = a[i - 2:i + 1]
        acc = sum(1 for _, c, _ in win if c) / 3
        sec = statistics.median(x for _, _, x in win)
        if acc <= acc0 - 0.33 or (sec0 >= 2 and sec >= 1.6 * sec0):
            return (a[i][0] - sess["start"]).total_seconds() / 60
    return None


def effective_minutes(sess_list: list[dict]) -> float | None:
    drops = [d for s in sess_list if (d := drop_minute(s)) is not None]
    if len(drops) >= 2:
        return statistics.median(drops)
    full = [s["active_s"] / 60 for s in sess_list if len(s["answers"]) >= MIN_ANSWERS_FOR_DROP and s["active_s"] > 0]
    if len(full) >= 3 and not drops:  # never dropped: they hold up for at least as long as they usually study
        return statistics.median(full)
    return None


def weekly_cadence(study_days: set[date], today: date, first: date | None) -> float | None:
    if first is None:
        return None
    counts = []
    for k in range(3):
        end = today - timedelta(days=7 * k)
        start = end - timedelta(days=6)
        if end < first:
            break
        counts.append(sum(1 for d in study_days if start <= d <= end))
    return float(statistics.median(counts)) if counts else None


def reminder_stats(events: list[dict]) -> tuple[dict, list[str]]:
    by_slot: dict[str, list[str]] = defaultdict(list)
    for e in events:
        if e["kind"] == "reminder_outcome" and e["data"].get("at"):
            try:
                at = datetime.fromisoformat(e["data"]["at"])
            except ValueError:
                continue
            by_slot[slot_of(at)].append(e["data"]["outcome"])
    resp, avoid = {}, []
    for slot, outs in sorted(by_slot.items()):
        n = len(outs)
        streak = 0
        for o in reversed(outs):
            if o != "ignored":
                break
            streak += 1
        resp[slot] = {"sent": n, "opened": outs.count("opened"), "ignored": outs.count("ignored"),
                      "snoozed": outs.count("snoozed"), "open_rate": round(outs.count("opened") / n, 2),
                      "ignored_streak": streak}
        if streak >= AVOID_AFTER_IGNORED:
            avoid.append(slot)
    return resp, avoid


def compute_profile(events: list[dict], now: datetime, band: Band, due: list[dict] | None = None) -> dict:
    today = local(now).date()
    sess = sessions(events)
    first = local(min(e["ts"] for e in events)).date() if events else None

    # windows: slot x weekday histogram with a 14-day half-life
    cells: dict[tuple[int, str], float] = defaultdict(float)
    slots: dict[str, float] = defaultdict(float)
    for s in sess:
        age = max(0.0, (now - s["start"]).total_seconds() / 86400)
        w = 0.5 ** (age / HALF_LIFE_DAYS)
        cells[(local(s["start"]).weekday(), slot_of(s["start"]))] += w
        slots[slot_of(s["start"])] += w
    windows = [{"weekday": d, "start": sl, "weight": round(w, 3)}
               for (d, sl), w in sorted(cells.items(), key=lambda kv: -kv[1])[:8]]
    overall = [{"start": sl, "weight": round(w, 3)} for sl, w in sorted(slots.items(), key=lambda kv: -kv[1])[:3]]

    # weekday activity over the last 28 days
    study_days = {local(s["start"]).date() for s in sess}
    span_days = 28 if first is None else min(28, (today - first).days + 1)
    rate: dict[int, float] = {}
    for wd in range(7):
        occ = [today - timedelta(days=i) for i in range(span_days) if (today - timedelta(days=i)).weekday() == wd]
        rate[wd] = round(sum(1 for d in occ if d in study_days) / len(occ), 2) if occ else 0.0
    skip = []
    if span_days >= 21 and len(sess) >= 6:
        usual = statistics.median(rate.values())
        skip = [wd for wd, r in rate.items() if r <= 0.25 and usual >= 0.5]

    eff = effective_minutes(sess)
    cold = len(sess) < MIN_SESSIONS
    default_min = band.minutes
    session_minutes = default_min if (cold or eff is None) else eff
    session_minutes = int(max(band.min_minutes, min(band.max_minutes, round(session_minutes / 5) * 5)))

    cadence = weekly_cadence(study_days, today, first)
    resp, avoid = reminder_stats(events)

    # slots where the student starts on their own: >= 3 recent starts there and no reminder was ever opened there
    cutoff = now - timedelta(days=21)
    recent_starts: dict[str, int] = defaultdict(int)
    for s in sess:
        if s["start"] >= cutoff:
            recent_starts[slot_of(s["start"])] += 1
    self_start = [sl for sl, n in recent_starts.items() if n >= 3 and resp.get(sl, {}).get("opened", 0) == 0]

    cut14 = now - timedelta(days=14)
    active_min_14 = sum(s["active_s"] for s in sess if s["start"] >= cut14) / 60
    last = max(study_days) if study_days else None
    asked = [e["data"]["intent"] for e in events if e["kind"] == "ask_question" and e["ts"] >= cut14]
    return {
        "cold_start": cold,
        "sessions_seen": len(sess),
        "windows": windows,
        "overall_slots": overall,
        "weekday_activity": rate,
        "skip_weekdays": skip,
        "effective_session_minutes": None if eff is None else round(eff),
        "session_minutes": session_minutes,
        "cadence_days_per_week": cadence,
        "reminder_response": resp,
        "avoid_slots": avoid,
        "self_start_slots": self_start,
        "actual_minutes_per_day_14d": round(active_min_14 / 14, 1),
        "last_study_date": last.isoformat() if last else None,
        "days_since_study": (today - last).days if last else None,
        "today_starts": [hhmm(local(s["start"]).hour * 60 + local(s["start"]).minute)
                         for s in sess if local(s["start"]).date() == today],
        "ask_14d": {"learn": asked.count("learn"), "solve": asked.count("solve"), "other": asked.count("other"),
                    "courses_opened": sum(1 for e in events if e["kind"] == "ask_course_open" and e["ts"] >= cut14)},
        "due_items_count": len(due or []),
        "age_defaults": {"start": hhmm(band.start_min), "minutes": band.minutes, "bounds": [band.min_minutes, band.max_minutes],
                         "bedtime": hhmm(band.bedtime_min), "break_after": band.break_after,
                         "sessions_per_week": band.sessions_per_week},
    }
