"""Scenario evals (REQUIREMENTS-PLAN 3.7 "Kiểm thử"): four synthetic personas, 3-4 weeks of generated events each, the
plan scored on hard constraints and on how well the planned windows match the persona's real habit.

Offline: the rule-based planner and a deliberately sloppy mocked model (its plan goes through the validator).
Run with `-s` to see the table.
"""

from datetime import date, datetime, timedelta

import pytest
from planner_fixtures import NOW, TZ, local_dt, make_courses, make_ctx, simulate

from mentor_gateway.planner import goals as goals_mod
from mentor_gateway.planner.bands import band_for, to_min
from mentor_gateway.planner.fallback import plan_fallback, weekly_cap
from mentor_gateway.planner.tables import StudyGoal
from mentor_gateway.planner.validator import validate

TODAY = NOW.astimezone(TZ).date()
PERSONAS = {
    "late_night": {"band": "uni", "habit": "22:30", "weekdays": {0, 1, 2, 3, 4, 5}, "weeks": 4, "minutes": 30},
    "skips_wednesday": {"band": "g10_12", "habit": "19:30", "weekdays": {0, 1, 3, 4, 5, 6}, "weeks": 4, "minutes": 20},
    "exam_in_3_weeks": {"band": "g10_12", "habit": "20:00", "weekdays": {0, 2, 4}, "weeks": 3, "minutes": 20},
    "grade1_child": {"band": "g1_5", "habit": "18:00", "weekdays": {0, 1, 2, 3, 4}, "weeks": 4, "minutes": 10},
}
RESULTS: list[tuple] = []


def build(name: str, now=NOW, **over):
    p = {**PERSONAS[name], **over}
    events = [e for e in simulate(NOW, p["habit"], p["weekdays"], p["weeks"], p["minutes"], seed=7) if e["ts"] < now]
    lessons, minutes = (16, 25) if name == "exam_in_3_weeks" else (8, 15)
    course = make_courses(lessons, minutes, done=2, partial=2)
    row = StudyGoal(id="g-me", user_id="u", kind="student" if name == "exam_in_3_weeks" else "inferred",
                    title="Thi giữa kỳ Vật lí" if name == "exam_in_3_weeks" else f"Học xong {course.title}",
                    deadline=(now.astimezone(TZ).date() + timedelta(days=21)) if name == "exam_in_3_weeks" else None,
                    course_ids=[course.id], dismissed=False, created_at=now - timedelta(days=30), updated_at=now)
    ctx = make_ctx(events, p["band"], courses=[course], goals=[], now=now)
    ctx.goals = goals_mod.build_infos([row], [course], ctx.profile, ctx.band, now)
    return p, ctx


def habit_match(plan: dict, habit: str, tol: int = 30) -> float:
    items = [i for i in plan["items"] if i["kind"] != "break"]
    return sum(abs(to_min(i["start"]) - to_min(habit)) <= tol for i in items) / len(items) if items else 0.0


def hard_checks(plan: dict, ctx):
    band = ctx.band
    items = [i for i in plan["items"] if i["kind"] != "break"]
    assert items, "plan has sessions"
    assert all(band.min_minutes <= i["minutes"] <= band.max_minutes for i in items)
    assert all(to_min(i["start"]) < band.bedtime_min and to_min(i["start"]) >= 6 * 60 + 30 for i in items)
    assert len({i["date"] for i in items}) <= 6
    assert sum(i["minutes"] for i in items) <= weekly_cap(ctx)
    per_day: dict[str, int] = {}
    for r in plan["reminders"]:
        at = datetime.fromisoformat(r["at"]).astimezone(TZ)
        assert at.hour * 60 + at.minute < band.bedtime_min, "reminder after bedtime"
        per_day[at.date().isoformat()] = per_day.get(at.date().isoformat(), 0) + 1
        assert at > ctx.now
    assert all(n <= 2 for n in per_day.values())
    ok, _, notes = validate(plan, ctx)
    assert ok and not notes, notes


@pytest.mark.parametrize("name", list(PERSONAS))
def test_persona_replayed_daily_over_the_generated_weeks(name):
    """Re-plan every day for the last 10 days of the generated history; every plan must be clean."""
    p = PERSONAS[name]
    matches = []
    for back in range(9, -1, -1):
        now = local_dt(TODAY - timedelta(days=back), "06:45")
        _, ctx = build(name, now=now)
        plan = plan_fallback(ctx)
        hard_checks(plan, ctx)
        matches.append(habit_match(plan, p["habit"]))
    avg = sum(matches) / len(matches)
    RESULTS.append((name, "10 daily replans", f"habit_match={avg:.2f}", "violations=0"))
    assert avg >= 0.8, matches


def test_late_night_learner_windows_and_reminders():
    p, ctx = build("late_night")
    assert ctx.profile["windows"][0]["start"] in ("22:00", "22:30")
    plan = plan_fallback(ctx)
    hard_checks(plan, ctx)
    assert habit_match(plan, p["habit"]) >= 0.8
    assert all(i["start"] >= "22:00" for i in plan["items"])  # not pushed back to an age-default 20:00
    assert band_for("uni").bedtime_min == to_min("23:30")
    RESULTS.append(("late_night", "plan", f"habit_match={habit_match(plan, p['habit']):.2f}", f"sessions={len(plan['items'])}"))


def test_wednesday_skipper_gets_no_wednesday():
    _, ctx = build("skips_wednesday")
    assert ctx.profile["skip_weekdays"] == [2]
    plan = plan_fallback(ctx)
    hard_checks(plan, ctx)
    assert all(date.fromisoformat(i["date"]).weekday() != 2 for i in plan["items"])
    assert all(datetime.fromisoformat(r["at"]).weekday() != 2 for r in plan["reminders"])
    assert len({i["date"] for i in plan["items"]}) >= 4
    RESULTS.append(("skips_wednesday", "plan", "wednesday=empty", f"sessions={len(plan['items'])}"))


def test_exam_in_three_weeks_is_flagged_and_planned_within_real_pace():
    _p, ctx = build("exam_in_3_weeks")
    goal = ctx.goals[0]
    assert goal.status in ("slightly_behind", "behind") and goal.required_min_per_day
    assert goal.required_min_per_day > ctx.profile["actual_minutes_per_day_14d"]
    plan = plan_fallback(ctx)
    hard_checks(plan, ctx)
    assert len({i["date"] for i in plan["items"]}) >= round(ctx.profile["cadence_days_per_week"]) + 1  # one extra session
    assert plan["goals"][0]["status"] == goal.status and "Mentor" in plan["goals"][0]["line_vi"]
    assert any(i["code"] == "BEHIND_GOAL" or i["code"] == "UNFINISHED_LESSON" for i in plan["items"])
    RESULTS.append(("exam_in_3_weeks", "plan", f"goal={goal.status}", f"required={goal.required_min_per_day}/day"))


def test_grade1_child_short_early_and_gentle():
    _p, ctx = build("grade1_child")
    plan = plan_fallback(ctx)
    hard_checks(plan, ctx)
    assert {i["minutes"] for i in plan["items"]} <= {5, 10, 15}
    assert all(i["start"] <= "20:00" for i in plan["items"]) and habit_match(plan, "18:00") >= 0.8
    assert all(datetime.fromisoformat(r["at"]).astimezone(TZ).hour < 21 for r in plan["reminders"])
    assert not any("yếu" in i["reason_vi"] or "lười" in i["reason_vi"] for i in plan["items"])
    RESULTS.append(("grade1_child", "plan", f"minutes={sorted({i['minutes'] for i in plan['items']})}", "bedtime ok"))


@pytest.mark.parametrize("name", list(PERSONAS))
def test_sloppy_model_is_repaired_by_the_validator(name):
    """A mocked model that ignores every rule: 90-minute sessions at 5:00 and midnight, 4 reminders a day."""
    p, ctx = build(name)
    base = TODAY
    items = [{"date": (base + timedelta(days=d)).isoformat(), "start": s, "minutes": 90, "kind": "lesson",
              "course_id": "c1", "lesson_id": f"l{d + 3}", "reason_vi": "Hãy học thật chăm chỉ nhé!!!", "reason_en": "x"}
             for d, s in ((1, "05:00"), (2, "23:59"), (3, p["habit"]), (4, p["habit"]))]
    rems = [{"at": local_dt(base + timedelta(days=3), h).astimezone(TZ).isoformat(), "kind": "study",
             "text_vi": "Học đi", "text_en": "Study", "deep_link": "/khoa-hoc/c1"} for h in ("06:00", p["habit"], "23:59", "12:00")]
    ok, fixed, notes = validate({"items": items, "reminders": rems}, ctx)
    assert ok and notes
    hard_checks(fixed, ctx)
    RESULTS.append((name, "sloppy model", f"fixes={len(notes)}", "repaired"))


def test_zz_print_table(capsys):
    with capsys.disabled():
        print("\n\npersona | scenario | result | constraints")
        for r in RESULTS:
            print(" | ".join(str(x) for x in r))
