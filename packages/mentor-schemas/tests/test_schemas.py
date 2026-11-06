import re
from datetime import date

from mentor_schemas import (
    REPORT_FORBIDDEN_PATTERNS,
    ParentReport,
    RoutinesFile,
    is_agent_writable,
)


def test_agent_write_permissions():
    assert is_agent_writable("me/now.md")
    assert is_agent_writable("me/journal/2026-10-28.md")
    assert is_agent_writable("research/papers/attention.md")
    assert not is_agent_writable("reports/2026-11-07.md")  # only the gateway writes sent reports
    assert is_agent_writable(".mentor/report-drafts/2026-11-07.md")
    assert not is_agent_writable(".mentor/report-drafts/sub/2026-11-07.md")
    assert not is_agent_writable(".mentor/report-drafts/x.txt")
    assert not is_agent_writable(".mentor/report-drafts/../wellbeing.jsonl")
    assert not is_agent_writable("AGENTS.md")
    assert not is_agent_writable("events.jsonl")
    assert not is_agent_writable(".mentor/wellbeing.jsonl")
    assert not is_agent_writable(".mentor/skills/core/memory-keeper/SKILL.md")
    assert not is_agent_writable("sessions/2026-10-28/abc.md")
    assert not is_agent_writable("../other-user/me/now.md")
    assert not is_agent_writable("/etc/passwd")
    assert not is_agent_writable("me/sub/deep.md")


def test_routines_roundtrip():
    text = "proactivity: high\nroutines:\n  - id: nightly_reflection\n    cron: '30 23 * * *'\n    job_kind: nightly_reflection\n    user_editable: false\n"
    rf = RoutinesFile.parse_yaml(text)
    assert rf.routines[0].cron == "30 23 * * *"
    assert RoutinesFile.parse_yaml(rf.to_yaml()) == rf


def test_report_roundtrip_and_forbidden_patterns():
    r = ParentReport(period_start=date(2026, 10, 24), period_end=date(2026, 11, 6), body_markdown="Con học đều 9/14 ngày.")
    assert ParentReport.parse(r.render()) == r
    assert any(re.search(p, "Bài 15 phút được 5/10", re.IGNORECASE) for p in REPORT_FORBIDDEN_PATTERNS)
    assert not any(re.search(p, r.body_markdown, re.IGNORECASE) for p in REPORT_FORBIDDEN_PATTERNS)
