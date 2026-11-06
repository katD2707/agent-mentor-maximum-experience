"""Content checks for the practice bank, curricula and exam profiles (CONTRACTS section 10.1).

Run from the repo root: `uv run pytest mentor-content/tests -q`.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

CONTENT = Path(__file__).resolve().parents[1]
BANK = CONTENT / "bank"
CURRICULA = CONTENT / "curricula"
SUBJECTS = ("math", "physics", "english")
ALLOWED_LICENSES = {"PROJECT_AUTHORED"}
TYPES = {"SINGLE_CHOICE", "TRUE_FALSE_GROUP", "SHORT_ANSWER"}
LABELS_BAD_WORDS = ("yếu",)

# Exam profiles that cannot be offered with the current seed bank (not enough APPROVED items of the needed
# type). The practice backend must hide these profiles; extend the bank, then shrink this set.
KNOWN_GAPS = {"physics.format-2025-mock.2026"}


def _curriculum(subject: str) -> list[dict]:
    data = yaml.safe_load((CURRICULA / f"{subject}.yaml").read_text(encoding="utf-8"))
    assert data["subject"] == subject
    return data["skills"]


def _questions() -> list[tuple[str, Path, dict]]:
    out = []
    for subject in SUBJECTS:
        for path in sorted((BANK / subject).glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["schema_version"] == 1, path
            out.extend((subject, path, q) for q in data["questions"])
    return out


QUESTIONS = _questions()


# ---------- curricula ----------

@pytest.mark.parametrize("subject", SUBJECTS)
def test_curriculum_valid(subject: str):
    skills = _curriculum(subject)
    ids = [s["id"] for s in skills]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for s in skills:
        assert re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)+", s["id"]), f"bad id {s['id']}"
        assert s["title"].strip()
        assert isinstance(s["grade"], int) and 8 <= s["grade"] <= 12
        for pre in s["prerequisites"]:
            assert pre in ids, f"{s['id']}: unknown prerequisite {pre}"
        assert set(s) <= {"id", "title", "grade", "prerequisites", "topic", "bkt"}, f"{s['id']}: keys {set(s)}"
    if subject != "math":
        assert all(s["id"].startswith(f"{subject}.") for s in skills)


@pytest.mark.parametrize("subject", SUBJECTS)
def test_curriculum_acyclic(subject: str):
    graph = {s["id"]: list(s["prerequisites"]) for s in _curriculum(subject)}
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        if state.get(node) == 2:
            return
        assert state.get(node) != 1, f"cycle: {' -> '.join(path + [node])}"
        state[node] = 1
        for pre in graph[node]:
            visit(pre, path + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])


def test_skill_ids_unique_across_subjects():
    ids = [s["id"] for subject in SUBJECTS for s in _curriculum(subject)]
    assert len(ids) == len(set(ids))


def test_math_curriculum_covers_grades_10_to_12():
    grades = Counter(s["grade"] for s in _curriculum("math"))
    assert grades[10] >= 18 and grades[11] >= 10 and grades[12] >= 15


@pytest.mark.parametrize("subject", SUBJECTS)
def test_skill_topics_are_bank_topics(subject: str):
    """`topic` on a skill must be a topic that exists in the bank or the taxonomy naming scheme."""
    bank_topics = {t for s, _, q in QUESTIONS if s == subject for t in q["topic_ids"]}
    used = {s["topic"] for s in _curriculum(subject) if "topic" in s}
    assert bank_topics <= used, f"bank topics without a skill carrying them: {bank_topics - used}"
    prefix = {"math": "math.", "physics": "phys.", "english": "eng."}[subject]
    assert all(t.startswith(prefix) for t in used)


# ---------- bank ----------

def test_bank_size():
    assert len(QUESTIONS) == 193
    by_subject = Counter(s for s, _, _ in QUESTIONS)
    assert by_subject == {"math": 70, "physics": 63, "english": 60}


def test_ids_unique_and_file_matches_topic():
    ids = [q["id"] for _, _, q in QUESTIONS]
    assert len(ids) == len(set(ids))
    for subject, path, q in QUESTIONS:
        assert q["subject_id"] == subject
        assert q["topic_ids"][0] == f"{q['id'].rsplit('.', 1)[0]}"
        assert re.fullmatch(r"[a-z-]+(\.[a-z-]+)+\.\d{3}", q["id"])
        assert path.stem == q["id"].rsplit(".", 1)[0].split(".", 1)[1], f"{q['id']} in {path.name}"


@pytest.mark.parametrize("subject,path,q", QUESTIONS, ids=[q["id"] for _, _, q in QUESTIONS])
def test_question_schema_sanity(subject: str, path: Path, q: dict):
    assert q["type"] in TYPES
    assert q["quality_status"] == "APPROVED"
    assert q["source"]["license"] in ALLOWED_LICENSES
    assert q["source"].get("usage_rights") in {"COMMERCIAL_OK", "NONCOMMERCIAL"}
    assert q["stem"].strip() and len(q["stem"]) <= 1200
    assert q["hint"].strip() and q["explanation"].strip()
    d = q["difficulty"]
    assert d["level"] in (1, 2, 3, 4) and 0 <= d["estimate"] <= 1
    assert 15 <= q["estimated_seconds"] <= 600
    assert q["language"] in ("vi", "en")
    assert q["reviews"], "APPROVED needs at least one review"
    if q["type"] == "SINGLE_CHOICE":
        assert [o["id"] for o in q["options"]] == ["A", "B", "C", "D"]
        assert q["answer_key"]["correct_option_id"] in {"A", "B", "C", "D"}
        assert len({o["text"] for o in q["options"]}) == 4
        assert not q.get("statements") and not q.get("short_answer")
    elif q["type"] == "TRUE_FALSE_GROUP":
        assert [s["id"] for s in q["statements"]] == ["a", "b", "c", "d"]
        assert all(isinstance(s["truth"], bool) for s in q["statements"])
        assert not q.get("options") and not q.get("answer_key")
    else:
        sa = q["short_answer"]
        assert sa["answer"].strip() and not q.get("options") and not q.get("answer_key")
    # asset ids referenced in the stem placement tokens must exist
    asset_ids = {a["id"] for a in q.get("assets") or []}
    for token in re.findall(r"\{\{(?:asset|fig):([^}]+)\}\}", q["stem"]):
        assert token in asset_ids


@pytest.mark.parametrize("subject,path,q", QUESTIONS, ids=[q["id"] for _, _, q in QUESTIONS])
def test_skill_ids_exist(subject: str, path: Path, q: dict):
    ids = q.get("skill_ids")
    assert isinstance(ids, list) and ids, f"{q['id']}: skill_ids missing"
    known = {s["id"] for s in _curriculum(subject)}
    assert len(ids) == len(set(ids))
    assert set(ids) <= known, f"{q['id']}: unknown skill ids {set(ids) - known}"


def test_skill_map_has_no_unknown_skills():
    sm = yaml.safe_load((BANK / "skill-map.yaml").read_text(encoding="utf-8"))
    known = {s["id"] for subject in SUBJECTS for s in _curriculum(subject)}
    for key, ids in {**sm["topics"], **sm["questions"]}.items():
        assert ids and set(ids) <= known, f"{key}: {set(ids) - known}"


def test_every_bank_topic_skill_is_exercised_or_listed():
    """Known gaps: skills with a topic but no bank question yet (mastery stays "Chưa có dữ liệu")."""
    used = {i for _, _, q in QUESTIONS for i in q["skill_ids"]}
    unused = sorted(
        s["id"] for subject in SUBJECTS for s in _curriculum(subject) if s.get("topic") and s["id"] not in used
    )
    # skills tagged with a topic that has no bank item at all (measurement) are expected
    assert set(unused) <= {
        "physics.measurement.units_error", "physics.mechanics.kinematics", "physics.mechanics.circular_motion",
        "physics.oscillation.harmonic", "english.phonetics.sounds", "english.phonetics.stress",
        # grade-11 prerequisites shown under "Hàm số" on the progress page; no question of their own yet
        "calculus.limits.basic", "calculus.derivative.rules",
    }, unused


# ---------- exam profiles ----------

def _profiles() -> list[dict]:
    data = json.loads((CONTENT / "exam-profiles.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    return data["profiles"]


def test_exam_profiles_shape():
    profiles = _profiles()
    assert len({p["id"] for p in profiles}) == len(profiles)
    for p in profiles:
        assert p["official_format"] is False
        assert p["disclaimer"].strip()
        assert p["subject_id"] in SUBJECTS
        assert p["type"] in {"MCQ_PRACTICE_MOCK", "OFFICIAL_FORMAT_MOCK"}


def _shortfalls() -> list[tuple[str, str, int, int]]:
    """(profile id, what, needed, available) for every demand the bank cannot satisfy."""
    have = Counter((q["topic_ids"][0], q["type"]) for _, _, q in QUESTIONS if q["quality_status"] == "APPROVED")
    short: list[tuple[str, str, int, int]] = []
    for p in _profiles():
        if p["type"] == "MCQ_PRACTICE_MOCK":
            demands = [(t, "SINGLE_CHOICE", n) for t, n in p["topic_matrix"].items()]
            assert sum(p["topic_matrix"].values()) == p["item_count"], p["id"]
        else:
            assert sum(part["item_count"] for part in p["parts"]) == p["item_count"], p["id"]
            demands = []
            subject_topics = {t for t, _ in have if t.startswith(p["subject_id"][:4] if p["subject_id"] != "english" else "eng")}
            for part in p["parts"]:
                if "topic_matrix" in part:
                    demands += [(t, part["type"], n) for t, n in part["topic_matrix"].items()]
                else:  # any topic of the subject
                    total = sum(n for (t, ty), n in have.items() if ty == part["type"] and t in subject_topics)
                    if total < part["item_count"]:
                        short.append((p["id"], f"part {part['part']} {part['type']}", part["item_count"], total))
        for topic, qtype, need in demands:
            if have[(topic, qtype)] < need:
                short.append((p["id"], f"{topic} {qtype}", need, have[(topic, qtype)]))
    return short


def test_exam_profile_topics_exist_in_bank():
    topics = {q["topic_ids"][0] for _, _, q in QUESTIONS}
    for p in _profiles():
        matrices = [p["topic_matrix"]] if "topic_matrix" in p else []
        matrices += [part["topic_matrix"] for part in p.get("parts", []) if "topic_matrix" in part]
        for m in matrices:
            assert set(m) <= topics, f"{p['id']}: topics without bank items {set(m) - topics}"


def test_exam_profile_known_gaps():
    """Shortfalls are reported, not hidden: the set of unservable profiles must equal KNOWN_GAPS."""
    short = _shortfalls()
    gaps = {pid for pid, *_ in short}
    assert gaps == KNOWN_GAPS, f"unservable exam profiles changed: {sorted(short)}"


def test_math_three_part_mock_is_servable():
    assert "math.format-2025-mock.2026" not in {pid for pid, *_ in _shortfalls()}


def test_no_banned_label_words_in_content_files():
    for name in ("english.yaml", "physics.yaml", "math.yaml"):
        text = (CURRICULA / name).read_text(encoding="utf-8").lower()
        for w in LABELS_BAD_WORDS:
            assert w not in text
