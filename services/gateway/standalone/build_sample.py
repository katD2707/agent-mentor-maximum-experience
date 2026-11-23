"""Copy the small sample content bundled with the standalone package: base files plus a few courses.

    python build_sample.py <mentor-content dir> <out dir> [course ids...]

Stdlib only. The result is `<out>/{AGENTS.md, skills, curricula, ..., courses/catalog.json, courses/<id>/...}` and a
`.sample-version` stamp (a hash of what was copied) that tells an installed app when to refresh its base files.
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

BASE_ITEMS = ("AGENTS.md", "exam-profiles.json", "skills", "curricula", "workspace-templates", "bank", "papers")
# one small course per age band (the village shows only the courses of the learner's own band): g1_5, g6_9, g10_12, uni
DEFAULT_COURSES = ("dao-duc-3-trung-thuc-va-biet-on", "hoa-hoc-9-kim-loai-va-phi-kim", "ki-nang-hoc-tap-hieu-qua", "co-so-du-lieu-sql-tu-co-ban")


def build(content: Path, out: Path, courses: tuple[str, ...] = DEFAULT_COURSES) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in BASE_ITEMS:
        src = content / name
        if src.is_dir():
            shutil.copytree(src, out / name, ignore=shutil.ignore_patterns("__pycache__"))
        elif src.is_file():
            shutil.copy2(src, out / name)
    catalog = json.loads((content / "courses" / "catalog.json").read_text(encoding="utf-8"))
    keep = [c for c in catalog["courses"] if c["id"] in courses]
    missing = set(courses) - {c["id"] for c in keep}
    if missing:
        raise SystemExit(f"courses not in catalog.json: {sorted(missing)}")
    catalog["courses"] = keep
    (out / "courses").mkdir()
    (out / "courses" / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for cid in courses:
        shutil.copytree(content / "courses" / cid, out / "courses" / cid)
    h = hashlib.sha256()
    for f in sorted(p for p in out.rglob("*") if p.is_file() and "courses" not in p.relative_to(out).parts):
        h.update(f.relative_to(out).as_posix().encode())
        h.update(f.read_bytes())
    (out / ".sample-version").write_text(h.hexdigest()[:16] + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    build(Path(sys.argv[1]), Path(sys.argv[2]), tuple(sys.argv[3:]) or DEFAULT_COURSES)
