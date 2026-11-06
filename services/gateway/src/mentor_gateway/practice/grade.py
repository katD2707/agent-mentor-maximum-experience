"""The learner's grade (lớp 10-12) and which bank topics are "in grade".

The grade is not an onboarding field; it lives in the mentor-maintained `me/profile.md`. `learner_grade` reads it
defensively: an explicit line (`Lớp: 11`, `- Khối: 11`, `Grade: 11`) wins, then a statement about the learner's own class
(`học lớp 11A2`, `học sinh lớp 11`, `lớp 11A2`). A bare "lớp 10" elsewhere (review notes such as "ôn kiến thức lớp 10") is
never taken as the grade. HTML comments are ignored. Unknown (None) means "do not filter".
"""

import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_EXPLICIT = re.compile(r"^[\s>*\-+#]*(?:lớp|khối|grade)\s*[:=]\s*(?:lớp\s*)?(\d{1,2})\b", re.I | re.M)
_OWN = re.compile(r"(?:học\s+sinh\s+lớp|(?:đang\s+)?học\s+lớp|(?:đang\s+)?học\s+ở\s+lớp|lớp)\s*(\d{1,2})[A-Za-zĐđ]\w{0,2}\b"
                  r"|(?:học\s+sinh\s+lớp|(?:đang\s+)?học\s+lớp|(?:đang\s+)?là\s+học\s+sinh\s+lớp)\s*(\d{1,2})\b", re.I)
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
