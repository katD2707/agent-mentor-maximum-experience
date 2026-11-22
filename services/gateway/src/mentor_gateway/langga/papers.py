"""Arena papers: loader, validator, bosses and a small CLI for the crawl project's importer.

    python -m mentor_gateway.langga.papers validate <dir>            check every *.json of <dir>
    python -m mentor_gateway.langga.papers import <dir> [--content-dir <mentor-content>]   validate, then copy into papers/

Format: `mentor-content/papers/README.md`, model `mentor_schemas.paper.Paper`.
"""

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from mentor_schemas.paper import Paper
from pydantic import ValidationError

from mentor_gateway.langga import subjects

log = logging.getLogger(__name__)

# one boss per chicken family (names from the lg-05 mockup); other chickens reuse the closest one
BOSSES = {
    "toan": {"name_vi": "Quái Sai Số", "name_en": "The Slip-Up Monster", "art": "boss-toan"},
    "van": {"name_vi": "Bóng Lạc Đề", "name_en": "The Off-Topic Phantom", "art": "boss-van"},
    "anh": {"name_vi": "Quái Lỗi Ngữ Pháp", "name_en": "The Grammar-Slip Monster", "art": "boss-anh"},
}
BOSS_OF_CHICKEN = {"van": "van", "daicuong": "van", "anh": "anh", "nna": "anh"}
BEAT_SCORE = 5.0  # boss beaten at 5/10 or more


def boss_for(chicken: str) -> dict:
    return dict(BOSSES[BOSS_OF_CHICKEN.get(chicken, "toan")])


def check_paper(p: Paper) -> list[str]:
    """Problems of a paper beyond the schema (chicken vs band, item counts)."""
    errs = []
    if not subjects.valid_for_band(p.chicken, p.band):
        errs.append(f"chicken {p.chicken!r} is not a chicken of band {p.band}")
    if p.item_count < 3:
        errs.append("a paper needs at least 3 items")
    return errs


def validate_dir(path: Path) -> tuple[dict[str, Paper], list[str]]:
    """Papers of a directory by id, and every error found (file name first). Never raises on a bad file."""
    papers: dict[str, Paper] = {}
    errors: list[str] = []
    files = sorted(path.glob("*.json"))
    if not files:
        errors.append(f"{path}: no *.json files")
    for f in files:
        try:
            p = Paper.model_validate(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:  # includes JSONDecodeError and pydantic's ValidationError
            first = str(exc).splitlines()[0] if isinstance(exc, ValidationError) else str(exc)
            detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:3]) \
                if isinstance(exc, ValidationError) else first
            errors.append(f"{f.name}: {detail}")
            continue
        if f.stem != p.id:
            errors.append(f"{f.name}: file name must be the paper id ({p.id}.json)")
        if p.id in papers:
            errors.append(f"{f.name}: duplicate paper id {p.id}")
        errors += [f"{f.name}: {e}" for e in check_paper(p)]
        papers[p.id] = p
    return papers, errors


class PaperStore:
    """`<content dir>/papers/*.json`, loaded lazily and reloaded when a file changes. Bad files are logged and skipped."""

    def __init__(self, content_dir: Path) -> None:
        self.dir = Path(content_dir) / "papers"
        self._sig: tuple | None = None
        self._papers: dict[str, Paper] = {}

    def _signature(self) -> tuple:
        if not self.dir.is_dir():
            return ()
        return tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in sorted(self.dir.glob("*.json")))

    def all(self) -> dict[str, Paper]:
        sig = self._signature()
        if sig != self._sig:
            self._sig = sig
            papers: dict[str, Paper] = {}
            if sig:
                found, errors = validate_dir(self.dir)
                for e in errors:
                    log.warning("papers: %s", e)
                bad = {e.split(":", 1)[0] for e in errors}
                papers = {pid: p for pid, p in found.items() if f"{pid}.json" not in bad}
            self._papers = papers
        return self._papers

    def get(self, paper_id: str) -> Paper | None:
        return self.all().get(paper_id)


def import_dir(src: Path, content_dir: Path) -> tuple[list[str], list[str]]:
    """Validate `src` and copy the valid files to `<content_dir>/papers/` (an existing paper of the same id is replaced).
    Returns (imported ids, errors); nothing is copied when any file is invalid."""
    papers, errors = validate_dir(src)
    if errors:
        return [], errors
    dest = Path(content_dir) / "papers"
    dest.mkdir(parents=True, exist_ok=True)
    for pid in papers:
        shutil.copyfile(src / f"{pid}.json", dest / f"{pid}.json")
    return sorted(papers), []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mentor_gateway.langga.papers", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check every *.json of a directory")
    v.add_argument("dir", type=Path)
    i = sub.add_parser("import", help="validate, then copy into mentor-content/papers")
    i.add_argument("dir", type=Path)
    i.add_argument("--content-dir", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.cmd == "validate":
        papers, errors = validate_dir(args.dir)
        for e in errors:
            print(f"ERROR {e}", file=sys.stderr)
        print(f"{len(papers)} paper(s) read, {len(errors)} error(s)")
        for p in papers.values():
            print(f"  {p.id}: {p.kind} {p.band} {p.chicken} {p.item_count} items, {p.minutes} min"
                  f"{' (placeholder)' if p.placeholder else ''}")
        return 1 if errors else 0
    from mentor_gateway.settings import Settings

    content = args.content_dir or Settings.from_env().content_dir
    ids, errors = import_dir(args.dir, content)
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    if errors:
        print("nothing imported", file=sys.stderr)
        return 1
    print(f"imported {len(ids)} paper(s) into {Path(content) / 'papers'}: {', '.join(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
