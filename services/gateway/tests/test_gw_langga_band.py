"""Band hygiene: suggestions, mocks, papers and goals only show content of the student's own band."""

import pytest
from gateway_fakes import set_band
from langga_fixtures import KID, content_with_papers, kid_store
from test_gw_practice_courses import enroll


@pytest.fixture(scope="session")
def lg_content(tmp_path_factory):
    return content_with_papers(tmp_path_factory.mktemp("lgb"))


@pytest.fixture
def settings(settings, lg_content):
    return settings.model_copy(update={"content_dir": lg_content})


@pytest.fixture
def store(client, tmp_path):
    s = kid_store(client.app.state.gw.clock, tmp_path / "courses")
    client.app.state.content.store = s
    client.app.state.chicken_resolver.clear()
    return s


def test_bank_mocks_are_for_the_upper_secondary_band_only(client, student, store):
    assert client.get("/api/practice/home").json()["mocks"], "g10_12 sees the bank's mock exams"
    for band in ("uni", "g6_9", "g1_5"):
        set_band(client, band)
        assert client.get("/api/practice/home").json()["mocks"] == [], band
        for c in client.get("/api/village").json()["chickens"]:
            tests = client.get(f"/api/chickens/{c['id']}").json()["tests"]
            assert not [t for t in tests if str(t["profile_or_mock"]).startswith("mock:")], band


def test_an_old_enrollment_from_another_band_is_not_a_goal(client, student, store):
    set_band(client, "g1_5")  # KID is a g1_5 course
    enroll(client, KID)
    assert any(g["course_ids"] == [KID] for g in client.get("/api/goals").json())
    set_band(client, "uni")
    assert not [g for g in client.get("/api/goals").json() if KID in g["course_ids"]]
    assert [e["course_id"] for e in client.get("/api/enrollments").json()] == [KID]  # still under "Khóa của em"
