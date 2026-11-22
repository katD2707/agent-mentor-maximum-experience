"""XP of the course player: `ContentService.progress_hook` (enrollment progress PUT), the rules of lg-09.

lesson_done +20 when the last block of a lesson is done; lesson_perfect +5 on top when every quiz item of that lesson was
answered right on the first try (at least one item, all answered). Blocks and single quiz answers pay nothing. The ledger
(UNIQUE source+ref) makes each award once only.
"""

from collections.abc import Callable
from typing import Any

from mentor_schemas.course import CoursePack

from mentor_gateway.db import Database, User
from mentor_gateway.langga import xp as xpm
from mentor_gateway.langga.resolve import ChickenResolver


def progress_awards(course_id: str, chicken: str, pack: CoursePack, before: set[str], after: set[str],
                    quiz: dict | None, quiz_state: dict) -> list[tuple[str, str, str, int]]:
    """Awards for the lessons this call touched (a block newly done, or the lesson of the quiz item answered) that are
    complete now. Progress made before the XP existed is not paid back."""
    awards: list[tuple[str, str, str, int]] = []
    for ch in pack.chapters:
        for ls in ch.lessons:
            ids = {b.id for b in ls.blocks}
            items = [q.id for b in ls.blocks if b.kind == "quiz" for q in b.items]
            touched = bool(ids & (after - before)) or bool(quiz and quiz["item_id"] in items)
            if not touched or not ids <= after:
                continue
            ref = f"{course_id}:{ls.id}"
            awards.append((chicken, "lesson_done", ref, xpm.AMOUNTS["lesson_done"]))
            if items and all((quiz_state.get(i) or {}).get("correct") and (quiz_state.get(i) or {}).get("attempts") == 1
                             for i in items):
                awards.append((chicken, "lesson_perfect", ref, xpm.AMOUNTS["lesson_perfect"]))
    return awards


def make_progress_hook(db: Database, xp: xpm.XpService, resolver: ChickenResolver) -> Callable[..., list[dict]]:
    def hook(user_id: str, course_id: str, pack: CoursePack, before: set[str], after: set[str], quiz: dict | None,
             quiz_state: Any) -> list[dict]:
        with db.session() as s:
            user = s.get(User, user_id)
            band = user.age_band if user else None
        chicken = resolver.of_course(course_id, band) or resolver.fallback(band)
        return xp.award_many(user_id, progress_awards(course_id, chicken, pack, before, after, quiz, quiz_state or {}))

    return hook
