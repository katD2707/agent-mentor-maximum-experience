"""Explainable next-step rules (port of agent-mentor `Recommender.kt`, learner-model.md section 6).

Deterministic, at most 3 recommendations, most important first. Wording is supportive: never "yếu", always "cần củng
cố". Each one has a Vietnamese `title`, a `reason` that starts with "Vì sao:" and an `action` the web app can open
(`kind` practice | mock | diagnostic | break | progress, with `params` shaped like the matching start request).
"""

from dataclasses import dataclass
from typing import Any

from mentor_gateway.practice.mastery import TopicMastery

BREAK_AFTER_MINUTES = 120
STALE_DIAGNOSTIC_SESSIONS = 6
MOCK_AFTER_PRACTICE_SESSIONS = 3


@dataclass
class TopicInput:
    id: str
    short: str
    weight: float
    mastery: TopicMastery


@dataclass
class History:
    diagnostic_done: bool  # a diagnostic was finished or skipped
    sessions_since_diagnostic: int
    completed_practice_sessions: int
    minutes_today: int  # practice + mock, all subjects


def _rec(code: str, subj: str, title: str, reason: str, kind: str, /, **params: Any) -> dict[str, Any]:
    return {"code": code, "subject": subj, "title": title, "reason": f"Vì sao: {reason}",
            "action": {"kind": kind, "params": params}}


def recommend(subject: str, topics: list[TopicInput], history: History, mock_profile: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if history.minutes_today >= BREAK_AFTER_MINUTES:
        out.append(_rec("TAKE_A_BREAK", subject, "Nghỉ ngơi một chút nhé",
                        f"bạn đã luyện hơn {BREAK_AFTER_MINUTES // 60} giờ hôm nay; nghỉ ngắn giúp ghi nhớ tốt hơn.", "break"))
    if not history.diagnostic_done and not any(t.mastery.has_evidence for t in topics):
        out.append(_rec("TAKE_DIAGNOSTIC", subject, "Làm bài đánh giá nhanh",
                        "chưa có dữ liệu nào; khoảng 12 câu giúp hiểu điểm mạnh của bạn và gợi ý đúng bài.",
                        "diagnostic", subject=subject))
    by_status: dict[str, list[TopicInput]] = {}
    for t in topics:
        by_status.setdefault(t.mastery.status, []).append(t)
    weak = sorted(by_status.get("WEAK", []), key=lambda t: t.mastery.estimate)
    developing = sorted(by_status.get("DEVELOPING", []), key=lambda t: t.mastery.estimate)
    unknown = sorted(by_status.get("UNKNOWN", []) + by_status.get("NEEDS_DATA", []), key=lambda t: (-t.weight, t.id))
    strong = sorted(by_status.get("STRONG", []), key=lambda t: -t.mastery.estimate)

    consolidate = (weak + developing)[:2]
    if consolidate:
        out.append(_rec("PRACTICE_WEAK", subject, "Củng cố " + " & ".join(t.short for t in consolidate),
                        ("các chủ đề này đang cần củng cố" if weak else "các chủ đề này đang tiến bộ nhưng chưa vững")
                        + "; luyện ở mức vừa sức để tiến bộ chắc chắn.",
                        "practice", subject=subject, minutes=20, goal="weak", topics=[t.id for t in consolidate]))
    if unknown and history.diagnostic_done:
        pick = unknown[:2]
        out.append(_rec("PROBE_UNKNOWN", subject, "Khám phá " + " & ".join(t.short for t in pick),
                        "hệ thống cần thêm vài câu để đánh giá chính xác các chủ đề này.",
                        "practice", subject=subject, minutes=20, goal="balanced", topics=[t.id for t in pick]))
    if strong:
        pick = strong[:2]
        out.append(_rec("CHALLENGE_STRONG", subject, "Thử thách " + " & ".join(t.short for t in pick),
                        "bạn đang làm tốt các chủ đề này; thử các câu vận dụng cao.",
                        "practice", subject=subject, minutes=20, goal="challenge", topics=[t.id for t in pick]))
    ok = sum(1 for t in topics if t.mastery.status in ("STRONG", "DEVELOPING"))
    if (history.completed_practice_sessions >= MOCK_AFTER_PRACTICE_SESSIONS and ok >= len(topics) / 2 and mock_profile):
        out.append(_rec("TAKE_MOCK", subject, "Thử sức với đề thi thử",
                        "bạn đã luyện đều; bấm giờ như thi thật để kiểm tra độ bền và phân bổ thời gian.",
                        "mock", subject=subject, profile_id=mock_profile))
    if history.diagnostic_done and history.sessions_since_diagnostic >= STALE_DIAGNOSTIC_SESSIONS:
        out.append(_rec("REDIAGNOSE", subject, "Đánh giá lại trình độ",
                        f"đã {STALE_DIAGNOSTIC_SESSIONS} buổi kể từ lần đánh giá trước; cập nhật lại bức tranh tổng thể.",
                        "diagnostic", subject=subject))
    return out[:3]
