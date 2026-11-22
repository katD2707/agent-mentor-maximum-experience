"""Which chicken a course, a bank subject or a practice item belongs to (cached: the catalog is read from disk)."""

import time
from typing import Any

from mentor_gateway.langga import subjects

TTL_SECONDS = 30.0


class ChickenResolver:
    def __init__(self, content: Any) -> None:
        self.content = content  # ContentService (set late by app.py)
        self._cache: dict[str, tuple[float, str | None, str, str | None]] = {}  # course -> (at, chicken, subject, band)

    def clear(self) -> None:
        self._cache.clear()

    def _entry(self, course_id: str) -> tuple[str | None, str, str | None]:
        hit = self._cache.get(course_id)
        now = time.monotonic()
        if hit is not None and now - hit[0] < TTL_SECONDS:
            return hit[1], hit[2], hit[3]
        chicken: str | None = None
        subject, band = "", None
        try:
            e = self.content.entry(course_id) if self.content is not None else None
        except Exception:  # noqa: BLE001 - an unreadable catalog must never break an answer
            e = None
        if e is not None:
            subject, band, chicken = e.subject, e.age_band, subjects.chicken_of_entry(e)
        self._cache[course_id] = (now, chicken, subject, band)
        return chicken, subject, band

    def of_course(self, course_id: str, user_band: str | None = None) -> str | None:
        """The course's chicken; when `user_band` is given and the chicken is not on that stage's list (a g6_9 student doing
        a grade-11 Physics course) the chicken the subject has on the student's own stage."""
        chicken, subject, _band = self._entry(course_id)
        if chicken is None:
            return None
        if user_band and not subjects.valid_for_band(chicken, user_band):
            return subjects.chicken_of(subject, user_band)
        return chicken

    def fallback(self, band: str | None) -> str:
        return "daicuong" if band == "uni" else "kn"

    def of_doc(self, doc: dict[str, Any], band: str | None) -> str:
        """Chicken of an engine item `doc`: its course's chicken, else the bank subject's, else the fallback."""
        course = doc.get("course")
        if course:
            got = self.of_course(course["course_id"], band)
            if got:
                return got
        got = subjects.chicken_of_bank_subject(str(doc.get("subject_id") or ""), band)
        return got or self.fallback(band)
