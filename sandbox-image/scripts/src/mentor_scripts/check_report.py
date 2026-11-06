"""check_report: leak and format check for a parent report (plan 7.6) before it is sent.

Input: {path}. Output: {ok, violations: [Vietnamese strings]}. Read-only.
Checks: frontmatter parses as ParentReport, period_end >= period_start, the AI disclaimer is
present, REPORT_FORBIDDEN_PATTERNS, no email addresses or phone numbers, no workspace paths
of private folders, body length <= MAX_BODY_CHARS.
"""

import re
from pathlib import Path
from typing import Any

from mentor_schemas import REPORT_FORBIDDEN_PATTERNS, ParentReport
from mentor_schemas.reports import (
    AI_DISCLAIMER,
    REPORT_EMAIL_PATTERN,
    REPORT_PHONE_PATTERN,
    REPORT_PRIVATE_PATH_PATTERN,
)

from mentor_scripts.common import ScriptError, resolve_in_workspace, run_cli

MAX_BODY_CHARS = 5000

# Same order as REPORT_FORBIDDEN_PATTERNS.
_PATTERN_MESSAGES = (
    "Có điểm số của từng bài kiểm tra",
    "Có nhắc đến điểm số cụ thể",
    "Có dấu ngoặc kép (không được trích dẫn lời học sinh)",
    "Có thuật lại lời học sinh nói hoặc tâm sự",
)
_EMAIL = re.compile(REPORT_EMAIL_PATTERN)
_PHONE = re.compile(REPORT_PHONE_PATTERN)
_PRIVATE_PATH = re.compile(REPORT_PRIVATE_PATH_PATTERN, re.IGNORECASE)


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 40 else text[:37] + "..."


def check_text(text: str) -> list[str]:
    """Violations for the full report file content; empty means it may be sent."""
    try:
        report = ParentReport.parse(text)
    except Exception:  # noqa: BLE001 - any parse failure is one violation
        return ["Thiếu hoặc sai phần frontmatter YAML (cần period_start, period_end dạng YYYY-MM-DD)."]

    violations: list[str] = []
    body = report.body_markdown
    if report.period_end < report.period_start:
        violations.append("period_end phải bằng hoặc sau period_start.")
    plain = re.sub(r"[*_]", "", body)
    if AI_DISCLAIMER not in plain:
        violations.append(f"Thiếu dòng miễn trừ: {AI_DISCLAIMER}")
    for i, pattern in enumerate(REPORT_FORBIDDEN_PATTERNS):
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            label = _PATTERN_MESSAGES[i] if i < len(_PATTERN_MESSAGES) else "Có nội dung bị cấm"
            violations.append(f"{label}: «{_snippet(m.group())}».")
    if m := _EMAIL.search(body):
        violations.append(f"Có địa chỉ email: «{_snippet(m.group())}».")
    if m := _PHONE.search(body):
        violations.append(f"Có số điện thoại: «{_snippet(m.group())}».")
    if m := _PRIVATE_PATH.search(body):
        violations.append(f"Có nhắc đến nội dung riêng tư của học sinh: «{_snippet(m.group())}».")
    if len(body) > MAX_BODY_CHARS:
        violations.append(f"Báo cáo quá dài ({len(body)} ký tự, tối đa {MAX_BODY_CHARS}).")
    return violations


def check_report(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    path = resolve_in_workspace(root, payload.get("path", ""))
    if not path.is_file():
        raise ScriptError(f"file not found: {payload.get('path')}")
    violations = check_text(path.read_text(encoding="utf-8"))
    return {"ok": not violations, "violations": violations}


def main() -> None:
    run_cli(check_report)


if __name__ == "__main__":
    main()
