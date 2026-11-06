#!/usr/bin/env python3
"""Import the agent-mentor seed question bank into mentor-content (CONTRACTS section 10.1).

    uv run python infra/import-agent-mentor-bank.py --src <path to the agent-mentor repo> [--dry-run]

Reads `<src>/content/bank/<subject>/<topic>.json` (agent-mentor format, kept unchanged) and writes
`mentor-content/bank/<subject>/<topic>.json` with one added field per question, `skill_ids`, taken from
`mentor-content/bank/skill-map.yaml` (per-question entry, else the topic default) and checked against
`mentor-content/curricula/<subject>.yaml`. Also copies `<src>/content/exam-profiles.json`.

Only questions with `source.license == "PROJECT_AUTHORED"` and `quality_status == "APPROVED"` are imported;
everything else is refused and reported. Nothing outside `content/bank/<subject>/*.json` is read, so the
bank-v2 / 2048.vn material (licensing unclear) can never be imported by this script. Idempotent: output is
deterministic and files are only rewritten when their content changes.

Exit code: 0 on success (refusals are reported, not errors); 1 if a question has no valid skill ids or the
source is missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "mentor-content"
BANK_OUT = CONTENT / "bank"
SKILL_MAP = BANK_OUT / "skill-map.yaml"
CURRICULA = CONTENT / "curricula"
SUBJECTS = ("math", "physics", "english")
ALLOWED_LICENSES = {"PROJECT_AUTHORED"}
ALLOWED_STATUS = {"APPROVED"}


def render(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def write_if_changed(path: Path, text: str, dry_run: bool) -> bool:
    old = path.read_bytes().decode("utf-8") if path.exists() else None
    if old == text:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return True


def load_curriculum_ids(subject: str) -> set[str]:
    data = yaml.safe_load((CURRICULA / f"{subject}.yaml").read_text(encoding="utf-8"))
    return {s["id"] for s in data["skills"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", required=True, help="agent-mentor repository root")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args(argv)

    src = Path(args.src) / "content"
    if not (src / "bank").is_dir():
        print(f"error: {src / 'bank'} not found", file=sys.stderr)
        return 1
    skill_map = yaml.safe_load(SKILL_MAP.read_text(encoding="utf-8"))
    per_topic = skill_map.get("topics") or {}
    per_question = skill_map.get("questions") or {}
    curricula = {s: load_curriculum_ids(s) for s in SUBJECTS}

    imported: Counter[tuple[str, str]] = Counter()
    refused: list[str] = []
    errors: list[str] = []
    changed: list[str] = []
    used_map_keys: set[str] = set()
    seen_ids: set[str] = set()

    for subject in SUBJECTS:
        sdir = src / "bank" / subject
        if not sdir.is_dir():
            errors.append(f"missing source folder {sdir}")
            continue
        for path in sorted(sdir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            out_questions = []
            for q in data["questions"]:
                qid = q["id"]
                lic = (q.get("source") or {}).get("license")
                status = q.get("quality_status")
                if lic not in ALLOWED_LICENSES or status not in ALLOWED_STATUS:
                    refused.append(f"{qid}: license={lic!r} quality_status={status!r}")
                    continue
                if q.get("subject_id") != subject or qid in seen_ids:
                    errors.append(f"{qid}: wrong subject or duplicate id")
                    continue
                seen_ids.add(qid)
                if qid in per_question:
                    ids = per_question[qid]
                    used_map_keys.add(qid)
                else:
                    ids = per_topic.get(q["topic_ids"][0])
                    if ids:
                        used_map_keys.add(q["topic_ids"][0])
                if not ids:
                    errors.append(f"{qid}: no skill ids in skill-map.yaml")
                    continue
                unknown = [i for i in ids if i not in curricula[subject]]
                if unknown:
                    errors.append(f"{qid}: unknown skill ids {unknown} (not in curricula/{subject}.yaml)")
                    continue
                item = dict(q)
                item.pop("skill_ids", None)
                item["skill_ids"] = list(ids)
                out_questions.append(item)
                imported[(subject, q["type"])] += 1
            if not out_questions:
                continue
            out = {k: v for k, v in data.items() if k != "questions"}
            out["questions"] = out_questions
            target = BANK_OUT / subject / path.name
            if write_if_changed(target, render(out), args.dry_run):
                changed.append(str(target.relative_to(ROOT)))

    profiles_src = src / "exam-profiles.json"
    if profiles_src.is_file():
        text = profiles_src.read_bytes().decode("utf-8")  # copied verbatim
        if write_if_changed(CONTENT / "exam-profiles.json", text, args.dry_run):
            changed.append("mentor-content/exam-profiles.json")
    else:
        errors.append(f"missing {profiles_src}")

    unused = sorted(set(per_question) - used_map_keys)
    print(("DRY RUN: " if args.dry_run else "") + f"imported {sum(imported.values())} questions")
    for (subject, qtype), n in sorted(imported.items()):
        print(f"  {subject:8} {qtype:17} {n}")
    print(f"files {'that would change' if args.dry_run else 'written'}: {len(changed)}")
    for c in changed:
        print(f"  {c}")
    print(f"refused (licence/status not allowed): {len(refused)}")
    for r in refused:
        print(f"  {r}")
    if unused:
        print(f"skill-map entries not used (stale): {unused}")
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
