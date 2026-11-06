"""Parent report (plan section 7.6), with YAML frontmatter. Drafted at .mentor/report-drafts/YYYY-MM-DD.md
(hidden from the learner); the gateway moves it to reports/YYYY-MM-DD.md once it has been sent.

---
period_start: 2026-10-24
period_end: 2026-11-06
includes_wellbeing_nudge: false
---
<markdown body: goal progress, study regularity, per-topic trends, optional nudge, AI disclaimer>
"""

from datetime import date

import yaml
from pydantic import BaseModel

AI_DISCLAIMER = "Báo cáo được tạo tự động bởi AI mentor, chỉ mang tính tham khảo."

# Regexes a report body must not match. The score pattern also matches dd/10 dates, so reports
# write dates as "ngày 24 tháng 10". The leak checker (sandbox-image/scripts/check_report.py)
# extends these with heuristics; parent-channel refuses to send a report that fails the check.
REPORT_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    r"\b\d{1,2}([.,]\d{1,2})?\s*/\s*10\b",  # per-test scores like 5/10, 7,5/10
    r"\bđiểm\s*(số)?\s*[:=]?\s*\d",  # "điểm: 6", "điểm số 8"
    r"[\"“”]",  # quotations (no quoting the learner)
    r"\b(em|con)\s+(nói|kể|tâm sự|chia sẻ)\b",  # reporting what the learner said
)

# Personal data / private workspace content a report must not contain either. Checked by check_report (sandbox)
# and again by the gateway and parent-channel before anything is sent (they do not trust the sandbox).
REPORT_EMAIL_PATTERN = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
REPORT_PHONE_PATTERN = r"(?<![\w])(?:\+84|84|0)(?:[\s.\-]?\d){8,10}(?!\d)"  # Vietnamese numbers
REPORT_PRIVATE_PATH_PATTERN = r"(?<![\w/])(?:me|sessions|inbox|\.mentor)/[\w./-]*"  # private workspace folders


class ParentReport(BaseModel):
    period_start: date
    period_end: date
    includes_wellbeing_nudge: bool = False
    body_markdown: str

    @classmethod
    def parse(cls, text: str) -> "ParentReport":
        if not text.startswith("---"):
            raise ValueError("report must start with YAML frontmatter")
        _, fm, body = text.split("---", 2)
        return cls(**yaml.safe_load(fm), body_markdown=body.strip())

    def render(self) -> str:
        fm = yaml.safe_dump(self.model_dump(mode="json", exclude={"body_markdown"}), sort_keys=False)
        return f"---\n{fm}---\n{self.body_markdown.strip()}\n"
