"""The learner's grade and which bank topics are "in grade".

The learner's derived `age_band` (CONTRACTS section 4) sets the range: g1_5 -> up to grade 5, g6_9 -> up to grade 9, uni -> no
filter, g10_12 (and unset) -> the exact grade 10-12 from the mentor-maintained `me/profile.md`. `parse_grade` reads it
defensively: an explicit line (`Lớp: 11`, `- Khối: 11`, `Grade: 11`) wins, then a statement about the learner's own class
(`học lớp 11A2`, `học sinh lớp 11`, `lớp 11A2`). A bare "lớp 10" elsewhere (review notes such as "ôn kiến thức lớp 10") is
never taken as the grade. HTML comments are ignored. Unknown (None) means "do not filter".
"""

import re

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_EXPLICIT = re.compile(r"^[\s>*\-+#]*(?:lớp|khối|grade)\s*[:=]\s*(?:lớp\s*)?(\d{1,2})\b", re.IGNORECASE | re.MULTILINE)
_OWN = re.compile(r"(?:học\s+sinh\s+lớp|(?:đang\s+)?học\s+lớp|(?:đang\s+)?học\s+ở\s+lớp|lớp)\s*(\d{1,2})[A-Za-zĐđ]\w{0,2}\b"
                  r"|(?:học\s+sinh\s+lớp|(?:đang\s+)?học\s+lớp|(?:đang\s+)?là\s+học\s+sinh\s+lớp)\s*(\d{1,2})\b", re.IGNORECASE)
GRADES = (10, 11, 12)


def parse_grade(profile_md: str | None) -> int | None:
    if not profile_md:
        return None
    text = _COMMENT.sub("", profile_md)
    m = _EXPLICIT.search(text)
    if m and int(m.group(1)) in GRADES:
        return int(m.group(1))
    for m in _OWN.finditer(text):
        g = int(m.group(1) or m.group(2))
        if g in GRADES:
            return g
    return None


# age_band -> (lowest, highest) grade; None = no grade filter
AGE_BAND_GRADES: dict[str, tuple[int, int] | None] = {"g1_5": (1, 5), "g6_9": (6, 9), "g10_12": (10, 12), "uni": None}


def grade_for(age_band: str | None, profile_md: str | None) -> int | None:
    """The grade whose topics count as "in grade": topics starting above it are above-grade. None = no filter."""
    if age_band in ("g1_5", "g6_9"):
        return AGE_BAND_GRADES[age_band][1]
    if age_band == "uni":
        return None
    return parse_grade(profile_md)  # g10_12 or not set: unchanged behaviour
