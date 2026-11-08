"""Birth year -> age band (September school year), PATCH /me set-once, the admin CLI and the migration."""

from datetime import UTC, date, datetime

import pytest
from gateway_fakes import login
from sqlalchemy import text

from mentor_gateway import age
from mentor_gateway.age import band_for_birth_year, grade_for
from mentor_gateway.cli import main as cli_main
from mentor_gateway.db import Database, User


@pytest.mark.parametrize(("year", "on", "grade", "band"), [
    (2010, date(2026, 11, 7), 11, "g10_12"),   # the approved example
    (2010, date(2030, 11, 7), 15, "uni"),
    (2010, date(2030, 8, 31), 14, "uni"),
    (2010, date(2028, 8, 31), 12, "g10_12"),   # last day before 1 September: still grade 12
    (2010, date(2028, 9, 1), 13, "uni"),       # 1 September moves up a year
    (2018, date(2026, 8, 31), 2, "g1_5"),
    (2012, date(2026, 8, 31), 8, "g6_9"),
    (2012, date(2026, 9, 1), 9, "g6_9"),
    (2012, date(2027, 9, 1), 10, "g10_12"),
    (2015, date(2026, 9, 1), 6, "g6_9"),       # born 2015 starts grade 6 in September 2026
    (2015, date(2026, 8, 31), 5, "g1_5"),
    (2020, date(2026, 11, 7), 1, "g1_5"),
    (2020, date(2024, 11, 7), -1, "g1_5"),     # before grade 1 counts as primary
    (1980, date(2026, 11, 7), 41, "uni"),
])
def test_band_from_birth_year(year, on, grade, band):
    assert grade_for(year, on) == grade
    assert band_for_birth_year(year, on) == band


def test_no_birth_year_no_band():
    assert band_for_birth_year(None) is None


def _clear_birth_year(client):
    gw = client.app.state.gw
    gw.users.update(gw.users.by_username("hocsinh").id, birth_year=None)


def test_patch_me_sets_birth_year_once(client):
    login(client)
    _clear_birth_year(client)
    assert client.get("/api/me").json()["age_band"] is None
    r = client.patch("/api/me", json={"birth_year": 2015, "language": "vi"})
    assert r.status_code == 200 and r.json()["birth_year"] == 2015 and r.json()["age_band"] == "g6_9"
    r = client.patch("/api/me", json={"birth_year": 2005})
    assert r.status_code == 409 and r.json()["error"] == "birth_year_locked"
    assert client.get("/api/me").json()["birth_year"] == 2015
    assert client.patch("/api/me", json={"birth_year": None}).status_code in (409, 422)
    assert client.patch("/api/me", json={"theme": "dark"}).status_code == 200  # other fields still work


def test_patch_me_rejects_out_of_range_birth_year(client):
    login(client)
    _clear_birth_year(client)
    for bad in (1900, 2100, "abc"):
        assert client.patch("/api/me", json={"birth_year": bad}).status_code == 422


def test_band_follows_the_clock_on_every_request(client, clock, student):
    assert client.get("/api/me").json()["age_band"] == "g10_12"
    clock.now = datetime(2030, 11, 7, 3, 0, tzinfo=UTC)
    login(client)  # four years later the old session has expired
    assert client.get("/api/me").json()["age_band"] == "uni"
    assert client.app.state.gw.users.by_username("hocsinh").age_band == "uni"  # planner, practice, Ask, catalog


def test_cli_set_birth_year(settings, client, capsys):
    login(client)
    cli_main(["set-birth-year", "--username", "hocsinh", "--year", "2013"], settings)
    assert "birth year 2013" in capsys.readouterr().out
    assert client.get("/api/me").json()["birth_year"] == 2013
    for args in (["--username", "nobody", "--year", "2013"], ["--username", "giaovien", "--year", "2013"],
                 ["--username", "hocsinh", "--year", "1800"]):
        with pytest.raises(SystemExit):
            cli_main(["set-birth-year", *args], settings)


def test_migration_gives_band_only_rows_a_birth_year(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with db.engine.begin() as c:  # a database from before birth_year
        c.execute(text("CREATE TABLE users (id VARCHAR(64) PRIMARY KEY, role VARCHAR(16), username VARCHAR(64), "
                       "password_hash VARCHAR(300), display_name VARCHAR(200), age_band VARCHAR(8), language VARCHAR(8), "
                       "theme VARCHAR(8), quiet_until DATETIME, provisioned_at DATETIME, created_at DATETIME)"))
        for i, band in enumerate(("g1_5", "g6_9", "g10_12", "uni", None)):
            c.execute(text("INSERT INTO users (id, role, username, password_hash, age_band) VALUES (:i, 'student', :u, 'x', :b)"),
                      {"i": f"u{i}", "u": f"u{i}", "b": band})
    age.set_today_provider(lambda: datetime(2026, 11, 7, tzinfo=UTC))
    try:
        db.create_all()
        with db.session() as s:
            rows = {u.id: (u.birth_year, u.age_band) for u in s.query(User)}
        db.create_all()  # idempotent
    finally:
        age.set_today_provider(None)
    assert [rows[f"u{i}"][1] for i in range(5)] == ["g1_5", "g6_9", "g10_12", "uni", None]
    assert rows["u2"][0] == 2010 and rows["u4"][0] is None
