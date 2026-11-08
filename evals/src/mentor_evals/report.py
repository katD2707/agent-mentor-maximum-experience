"""Run outputs: `results.jsonl` (one line per scenario) and `summary.md` (short tables)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def summary_markdown(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    lines = [
        f"# Eval run {meta['run_id']}",
        "",
        (
            f"- model: `{meta['model']}` · judge: `{meta['judge']}` · scenarios: {len(rows)} · "
            f"passed: {sum(r['passed'] for r in rows)} · duration: {meta.get('duration_s', 0):.1f}s"
        ),
    ]
    if meta.get("note"):
        lines.append(f"- {meta['note']}")
    lines += ["", "## By suite", "", "| Suite | Scenarios | Passed | Failed checks (critical / soft) | Judge skipped |",
              "|---|---|---|---|---|"]  # fmt: skip
    by_suite: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_suite[r["suite"]].append(r)
    for suite in sorted(by_suite):
        rs = by_suite[suite]
        checks = [c for r in rs for c in r["checks"]]
        crit = sum(c["status"] in ("fail", "error") and c["severity"] == "critical" for c in checks)
        soft = sum(c["status"] in ("fail", "error") and c["severity"] == "soft" for c in checks)
        skipped = sum(c["status"] == "skip" and c["check"] == "judge" for c in checks)
        lines.append(f"| {suite} | {len(rs)} | {sum(r['passed'] for r in rs)} | {crit} / {soft} | {skipped} |")

    lines += [
        "",
        "## Scenarios",
        "",
        "| Scenario | Suite | Persona | Result | Failed checks |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        failed = [c for c in r["checks"] if c["status"] in ("fail", "error")]
        desc = "; ".join(f"{c['id']}{' (soft)' if c['severity'] == 'soft' else ''}" for c in failed) or "—"
        result = "PASS" if r["passed"] else ("ERROR" if r.get("error") else "FAIL")
        lines.append(f"| {r['scenario']} | {r['suite']} | {r['persona']} | {result} | {_cell(desc)} |")

    details = [(r, c) for r in rows for c in r["checks"] if c["status"] in ("fail", "error")]
    if details:
        lines += ["", "## Failure details", ""]
        for r, c in details[:60]:
            lines.append(f"- `{r['scenario']}` {c['id']} [{c['severity']}, {c['where']}]: {_cell(c['detail'])[:400]}")
    return "\n".join(lines) + "\n"
