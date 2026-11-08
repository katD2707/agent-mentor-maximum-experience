"""Generate (or remove) the placeholder courses that make the catalog feel full.

    python mentor-content/tools/make_placeholders.py            # write ph-* courses + covers, regenerate catalog.json
    python mentor-content/tools/make_placeholders.py remove     # delete every ph-* course, regenerate catalog.json
    python mentor-content/tools/make_placeholders.py --svg-dir out/   # also write each cover as SVG

Placeholders are CourseMeta with status "coming_soon" under <courses>/ph-<slug>/ (course.json + cover.webp, never a
pack.json). Overviews come from placeholder_courses.txt; covers are drawn by placeholder_covers.py. Output is
deterministic, so running it twice changes nothing. Real courses are never touched.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from mentor_schemas.course import AgeBand, CourseMeta, OutlineChapter, OutlineLesson  # noqa: E402

import placeholder_covers as covers  # noqa: E402

PREFIX = "ph-"
DEFAULT_ROOT = HERE.parent / "courses"
MEDIA_SETS = {
    "g1_5": [["video", "reading", "quiz", "interactive"], ["video", "audio", "quiz"], ["reading", "audio", "quiz"]],
    "g6_9": [["video", "reading", "quiz"], ["reading", "quiz"], ["video", "quiz"]],
    "g10_12": [["video", "reading", "quiz"], ["reading", "quiz"], ["video", "reading", "quiz"]],
    "uni": [["reading", "quiz"], ["video", "reading", "quiz"], ["video", "reading"]],
}
MINUTES = {"g1_5": (6, 12), "g6_9": (9, 18), "g10_12": (10, 22), "uni": (18, 45)}


def fold(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return re.sub(r"[^a-z0-9]+", "-", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip("-")


def parse(path: Path) -> list[dict]:
    courses: list[dict] = []
    cur: dict | None = None
    for raw in path.read_text("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") and not line.startswith("##"):
            continue
        if line.startswith("## "):
            band, subject, motif, lang, teacher, title = (x.strip() for x in line[3:].split("|", 5))
            cur = {"band": band, "subject": subject, "motif": motif, "lang": lang, "teacher": teacher, "title": title,
                   "desc": "", "level": None, "outcomes": [], "chapters": []}
            courses.append(cur)
        elif cur is None:
            raise ValueError(f"text before the first course: {line}")
        elif line.startswith("v:"):
            cur["level"] = line[2:].strip()
        elif line.startswith("d:"):
            cur["desc"] = line[2:].strip()
        elif line.startswith("o:"):
            cur["outcomes"].append(line[2:].strip())
        elif line.startswith("c:"):
            title, lessons = line[2:].split(":", 1)
            cur["chapters"].append((title.strip(), [x.strip() for x in lessons.split(";") if x.strip()]))
        else:
            raise ValueError(f"unknown line in {cur['title']}: {line}")
    return courses


def build(spec: dict, used: set[str]) -> CourseMeta:
    slug = fold(spec["title"])[:44].strip("-")
    cid = PREFIX + slug
    n = 2
    while cid in used:
        cid = f"{PREFIX}{slug}-{n}"
        n += 1
    used.add(cid)
    band: AgeBand = spec["band"]
    lo, hi = MINUTES[band]
    outline = []
    for ci, (ctitle, lessons) in enumerate(spec["chapters"], 1):
        outline.append(OutlineChapter(id=f"ch{ci}", title=ctitle, lessons=[
            OutlineLesson(id=f"ch{ci}-l{li}", title=lt,
                          est_minutes=lo + zlib.crc32(f"{cid}/{ci}/{li}".encode()) % (hi - lo + 1))
            for li, lt in enumerate(lessons, 1)]))
    sets = MEDIA_SETS[band]
    meta = CourseMeta(
        id=cid, title=spec["title"], subject=spec["subject"], age_band=band, language=spec["lang"],
        teacher_id="ph-teacher", teacher_name=spec["teacher"], description_short=spec["desc"], outcomes=spec["outcomes"],
        cover="cover.webp", media=sets[zlib.crc32(cid.encode()) % len(sets)],
        lessons_count=sum(len(c.lessons) for c in outline), est_minutes=sum(ls.est_minutes for c in outline for ls in c.lessons),
        status="coming_soon", outline=outline, level=spec["level"])
    if spec["level"] not in ("basic", "intermediate", "advanced"):
        raise ValueError(f"{spec['title']}: needs `v: basic|intermediate|advanced`")
    if len(spec["outcomes"]) < 3 or not spec["desc"]:
        raise ValueError(f"{spec['title']}: needs a description and at least 3 outcomes")
    return meta


def existing_placeholders(root: Path) -> list[Path]:
    out = []
    for d in sorted(root.glob(PREFIX + "*")):
        f = d / "course.json"
        if f.is_file() and '"status": "coming_soon"' in f.read_text("utf-8"):
            out.append(d)
    return out


def regenerate_catalog(root: Path) -> int:
    from mentor_gateway.content.store import ContentStore

    return len(ContentStore(root).regenerate_catalog().courses)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", nargs="?", choices=["generate", "remove"], default="generate")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="the courses directory")
    ap.add_argument("--svg-dir", type=Path, help="also write each cover as SVG here")
    args = ap.parse_args()
    root: Path = args.root

    for d in existing_placeholders(root):  # always start from a clean set: removed rows disappear too
        shutil.rmtree(d)
    if args.action == "remove":
        print(f"removed placeholders; catalog now has {regenerate_catalog(root)} courses")
        return

    used: set[str] = set()
    metas = [(spec, build(spec, used)) for spec in parse(HERE / "placeholder_courses.txt")]
    if args.svg_dir:
        args.svg_dir.mkdir(parents=True, exist_ok=True)
    for spec, meta in metas:
        d = root / meta.id
        d.mkdir(parents=True, exist_ok=True)
        seed = zlib.crc32(meta.id.encode())
        webp = covers.cover_webp(spec["motif"], seed)
        (d / "cover.webp").write_bytes(webp)
        (d / "course.json").write_text(meta.model_dump_json(indent=2) + "\n", "utf-8")
        if args.svg_dir:
            (args.svg_dir / f"{meta.id}.svg").write_text(covers.cover_scene(spec["motif"], seed).svg(), "utf-8")
    total = regenerate_catalog(root)
    from collections import Counter

    print(f"{len(metas)} placeholders written; catalog has {total} courses")
    print("by age band:", dict(Counter(m.age_band for _, m in metas)))
    print("by language:", dict(Counter(m.language for _, m in metas)))


if __name__ == "__main__":
    main()
