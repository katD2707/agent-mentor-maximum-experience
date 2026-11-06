"""Topic titles and curriculum weights for the subjects of the question bank.

The bank only carries topic ids (`math.function`); the names learners see come from agent-mentor's taxonomy. The ids
used by the imported bank are embedded here so the gateway needs no extra content file; an unknown id (a topic C adds
later) falls back to a readable form of the id, and `mentor-content/bank/topics.json` (`{id: {title, short, weight}}`)
may override or extend this table without a code change.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TopicInfo:
    id: str
    title: str
    short: str
    weight: float  # share of the national paper (curriculum weight), used for allocation and the diagnostic


SUBJECT_LABELS = {"math": "Toán", "physics": "Vật lí", "english": "Tiếng Anh"}

_BUILTIN: tuple[tuple[str, str, str, float], ...] = (
    ("math.function", "Ứng dụng đạo hàm & đồ thị hàm số", "Hàm số", 0.176),
    ("math.exp-log", "Hàm số mũ & logarit", "Mũ – Logarit", 0.096),
    ("math.integral", "Nguyên hàm & tích phân", "Tích phân", 0.144),
    ("math.oxyz", "Phương pháp tọa độ trong không gian Oxyz", "Oxyz", 0.16),
    ("math.statistics", "Thống kê mẫu số liệu ghép nhóm", "Thống kê", 0.096),
    ("math.probability", "Xác suất có điều kiện & công thức Bayes", "Xác suất", 0.128),
    ("phys.thermal", "Vật lí nhiệt", "Nhiệt học", 0.18),
    ("phys.gas", "Khí lí tưởng", "Khí lí tưởng", 0.18),
    ("phys.electromagnetism", "Điện từ học: từ trường & cảm ứng điện từ", "Điện từ", 0.225),
    ("phys.nuclear", "Vật lí hạt nhân & phóng xạ", "Hạt nhân", 0.18),
    ("phys.mechanics", "Cơ học: động học, động lực học, năng lượng & động lượng", "Cơ học", 0.09),
    ("phys.waves-optics", "Sóng & quang học nền tảng", "Sóng – Quang", 0.045),
    ("eng.grammar", "Ngữ pháp: thì, dạng động từ, cấu trúc câu", "Ngữ pháp", 0.176),
    ("eng.vocabulary", "Từ vựng & kết hợp từ (collocation)", "Từ vựng", 0.176),
    ("eng.word-formation", "Cấu tạo từ", "Cấu tạo từ", 0.088),
    ("eng.communication", "Thông báo, quảng cáo & tình huống giao tiếp", "Giao tiếp", 0.132),
    ("eng.reading", "Đọc hiểu", "Đọc hiểu", 0.22),
    ("eng.sentence-arrangement", "Sắp xếp câu/đoạn & viết lại câu", "Sắp xếp câu", 0.088),
)


class Topics:
    def __init__(self, content_dir: Path) -> None:
        self.by_id = {i: TopicInfo(i, t, s, w) for i, t, s, w in _BUILTIN}
        extra = content_dir / "bank" / "topics.json"
        if extra.exists():
            try:
                for tid, d in json.loads(extra.read_text(encoding="utf-8")).items():
                    title = str(d.get("title") or tid)
                    self.by_id[tid] = TopicInfo(tid, title, str(d.get("short") or title), float(d.get("weight") or 0.1))
            except (ValueError, AttributeError):
                pass  # a malformed optional file must not take practice down

    def get(self, topic_id: str) -> TopicInfo:
        info = self.by_id.get(topic_id)
        if info is None:
            human = re.sub(r"[-_.]+", " ", topic_id.split(".", 1)[-1]).strip().capitalize() or topic_id
            info = TopicInfo(topic_id, human, human, 0.1)
        return info
