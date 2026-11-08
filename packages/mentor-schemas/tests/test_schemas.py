from mentor_schemas import (
    RoutinesFile,
    is_agent_writable,
)


def test_agent_write_permissions():
    assert is_agent_writable("me/now.md")
    assert is_agent_writable("me/journal/2026-10-28.md")
    assert not is_agent_writable("research/papers/attention.md")
    assert not is_agent_writable("AGENTS.md")
    assert not is_agent_writable("events.jsonl")
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


def test_catalog_entry_live_needs_pack_but_coming_soon_does_not():
    import pytest
    from pydantic import ValidationError

    from mentor_schemas.course import CatalogEntry

    base = dict(id="ph-x", title="t", subject="s", age_band="uni", language="vi", teacher_name="n", description_short="d",
                cover_sha256="0" * 64, lessons_count=2, est_minutes=20)
    assert CatalogEntry(**base, status="coming_soon").version == 0
    with pytest.raises(ValidationError):
        CatalogEntry(**base)  # live by default: needs version, pack_sha256, published_at
