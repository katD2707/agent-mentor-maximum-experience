"""Synthetic bank, profiles and curriculum for the practice tests (agent-mentor bank format + `skill_ids`)."""

import json
import shutil
from pathlib import Path

import yaml

TOPICS = ("math.function", "math.exp-log", "math.integral")
LEVELS = (1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 2, 3)  # 12 single-choice items per topic
ESTIMATE = {1: 0.18, 2: 0.40, 3: 0.65, 4: 0.86}


def _base(qid: str, topic: str, qtype: str, level: int, skills: list[str], seconds: int) -> dict:
    return {
        "id": qid, "revision": 1, "subject_id": "math", "type": qtype, "topic_ids": [topic], "language": "vi",
        "stem": f"Câu {qid}: $x^2 = {level}$", "hint": f"Gợi ý {qid}", "explanation": f"Lời giải {qid}", "tip": f"Mẹo {qid}",
        "option_feedback": {}, "difficulty": {"level": level, "estimate": ESTIMATE[level], "confidence": "PROVISIONAL"},
        "estimated_seconds": seconds, "assets": [], "quality_status": "APPROVED", "skill_ids": skills,
        "source": {"license": "PROJECT_AUTHORED"},
    }


def build_bank() -> dict[str, list[dict]]:
    files: dict[str, list[dict]] = {}
    for topic in TOPICS:
        qs = []
        for i, level in enumerate(LEVELS):
            q = _base(f"{topic}.{i + 1:03d}", topic, "SINGLE_CHOICE", level, [f"{topic}.s{i % 2 + 1}"], 45 + 15 * level)
            key = "ABCD"[i % 4]
            q["options"] = [{"id": o, "text": f"${n}$"} for n, o in enumerate("ABCD")]
            q["answer_key"] = {"correct_option_id": key}
            q["option_feedback"] = {o: f"Sai vì {o}" for o in "ABCD" if o != key}
            if i == 0:
                q["assets"] = [{"id": "tab1", "type": "table", "alt_text": "bảng",
                                "table": {"headers": ["$x$"], "rows": [["$1$"]]}}]
            qs.append(q)
        tf = _base(f"{topic}.101", topic, "TRUE_FALSE_GROUP", 3, [f"{topic}.s1"], 200)
        tf["statements"] = [{"id": c, "text": f"Ý {c}", "truth": t, "explanation": f"Giải ý {c}", "level": 2}
                            for c, t in zip("abcd", (True, True, False, False), strict=True)]
        sa = _base(f"{topic}.201", topic, "SHORT_ANSWER", 2, [f"{topic}.s2"], 120)
        sa["short_answer"] = {"answer": "-0,5", "decimals": 1, "unit": "m", "max_chars": 4}
        qs += [tf, sa]
        files[topic] = qs
    return files


PROFILES = {"schema_version": 1, "profiles": [
    {"id": "math.mcq.t", "type": "MCQ_PRACTICE_MOCK", "subject_id": "math", "label": "Thi thử trắc nghiệm", "question_types": ["SINGLE_CHOICE"],
     "time_limit_sec": 600, "item_count": 9, "topic_matrix": {t: 3 for t in TOPICS}, "level_mix": [0.4, 0.3, 0.2, 0.1],
     "scoring_policy_version": "mcq-v1", "max_score": 10.0, "official_format": False, "disclaimer": "Không phải đề chính thức."},
    {"id": "math.parts.t", "type": "OFFICIAL_FORMAT_MOCK", "subject_id": "math", "label": "Thi thử 3 phần",
     "question_types": ["SINGLE_CHOICE", "TRUE_FALSE_GROUP", "SHORT_ANSWER"], "time_limit_sec": 1200, "item_count": 12,
     "level_mix": [0.4, 0.3, 0.2, 0.1], "scoring_policy_version": "scoring-v2", "max_score": 10.0, "official_format": False,
     "disclaimer": "Đề 3 phần luyện tập.",
     "parts": [{"part": 1, "label": "Phần I", "type": "SINGLE_CHOICE", "item_count": 6, "points_per_item": 0.25},
               {"part": 2, "label": "Phần II", "type": "TRUE_FALSE_GROUP", "item_count": 3, "points_per_item": 1.0,
                "level_mix": [0.0, 0.25, 0.5, 0.25]},
               {"part": 3, "label": "Phần III", "type": "SHORT_ANSWER", "item_count": 3, "points_per_item": 0.5}]},
    {"id": "math.too-big.t", "type": "OFFICIAL_FORMAT_MOCK", "subject_id": "math", "label": "Quá lớn",
     "question_types": ["TRUE_FALSE_GROUP"], "time_limit_sec": 600, "item_count": 4, "level_mix": [0.4, 0.3, 0.2, 0.1],
     "scoring_policy_version": "scoring-v2", "max_score": 10.0, "disclaimer": "",
     "parts": [{"part": 1, "label": "Phần II", "type": "TRUE_FALSE_GROUP", "item_count": 4, "points_per_item": 1.0}]},
]}


def curriculum() -> str:
    skills = []
    for t in TOPICS:
        for n in (1, 2):
            skills.append({"id": f"{t}.s{n}", "title": f"Kĩ năng {t} {n}", "grade": 12, "prerequisites": [], "topic": t})
    return yaml.safe_dump({"subject": "math", "skills": skills}, allow_unicode=True)


def build_content(base: Path, target: Path) -> Path:
    shutil.copytree(base, target)
    (target / "bank" / "math").mkdir(parents=True)
    for topic, qs in build_bank().items():
        (target / "bank" / "math" / f"{topic.split('.')[1]}.json").write_text(
            json.dumps({"schema_version": 1, "questions": qs}, ensure_ascii=False), encoding="utf-8")
    (target / "exam-profiles.json").write_text(json.dumps(PROFILES, ensure_ascii=False), encoding="utf-8")
    (target / "curricula" / "math.yaml").write_text(curriculum(), encoding="utf-8")
    return target
