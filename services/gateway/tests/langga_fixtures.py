"""Shared bits of the Làng gà tests: a content dir with the placeholder papers, and the g1_5 kid course (8 quiz items)."""

import shutil
from pathlib import Path

from practice_fixtures import build_content
from test_gw_practice_courses import APPLE, KID, KID_META, PEAR, SAMPLES, kid_pack

from mentor_gateway.content import ContentStore

REPO = Path(__file__).resolve().parents[3]
FIXTURE_CONTENT = Path(__file__).parent / "fixtures" / "mentor-content"


def content_with_papers(base: Path) -> Path:
    target = build_content(FIXTURE_CONTENT, base / "mentor-content")
    shutil.copytree(REPO / "mentor-content" / "papers", target / "papers")
    return target


def kid_store(clock, root: Path) -> ContentStore:
    shutil.copytree(SAMPLES, root)
    s = ContentStore(root, clock)
    s.create_draft(KID_META)
    (s.course_dir(KID) / "cover.png").write_bytes(APPLE + b"cover")
    s.write_pack(KID, 1, kid_pack(1), {"a.png": APPLE, "p.png": PEAR})
    s.publish(KID, 1)
    return s
