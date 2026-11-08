"""Which media a lesson really needs (decided from the outline, before the lesson is written).

Every video costs about 4-6 minutes (scene code by the model, HyperFrames render) and every drawn picture 1-3 minutes
(SVG, Chrome, vision critique); a read-aloud clip costs seconds. A picture or video helps when the idea is a
process, a motion or a shape; for a definition or a worked calculation it is filler. So:

- a video only for lessons whose content is dynamic (motion, wave, field, experiment, process...), at most one per
  lesson and at most VIDEO_RATIO[band] of the course (never for university unless the source is a lecture; grade 1-5 only
  when the material itself mentions a film, and then only the first lesson);
- pictures per lesson capped by band (children: 2, others: 1), a diagram when the lesson is about formulas, data or
  structure, an illustration when it is about concrete things, none for pure text lessons from grade 10 up;
- read-aloud (tts) is never limited: it is what lets a child who cannot read yet use the lesson.
`plan_media` is deterministic (keyword score), so a re-run gives the same plan.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from mentor_course_builder.outline import CourseOutline, OutlineLesson

VIDEO_RATIO = {"g1_5": 0.0, "g6_9": 0.5, "g10_12": 0.4, "uni": 0.0}
MAX_PICTURES = {"g1_5": 2, "g6_9": 1, "g10_12": 1, "uni": 1}

DYNAMIC = re.compile(r"chuyển động|quá trình|thí nghiệm|dao động|sóng|quay|lan truyền|biến đổi|vòng đời|chu trình|phản ứng|"
                     r"đường sức|từ trường|điện trường|dòng điện|va chạm|rơi|ném|motion|wave|oscillat|process|cycle|experiment|"
                     r"reaction|field|flow|collision|rotat|evolv|converge|simulation", re.I)
SHAPE = re.compile(r"hình|đồ thị|biểu đồ|sơ đồ|mạch|phân phối|phân bố|đường cong|hàm số|tọa độ|vectơ|vector|"
                   r"graph|plot|diagram|distribution|curve|function|circuit|geometry|triangle|angle|bayes|prior|posterior", re.I)
MATHY = re.compile(r"công thức|phương trình|định lý|xác suất|tích phân|đạo hàm|formula|equation|theorem|probability|"
                   r"integral|derivative|\$", re.I)
OBJECTS = re.compile(r"\bcon\b|\bquả\b|\bcây\b|\bsố\b|đếm|bằng nhau|nhiều hơn|ít hơn|count|animal|fruit|number", re.I)
FILM = re.compile(r"\bphim\b|\bvideo\b|\bfilm\b|\bmovie\b", re.I)


@dataclass(frozen=True)
class LessonMedia:
    video: int = 0  # 0 or 1
    pictures: int = 1  # most illustration + diagram blocks
    prefer: str = "illustration"  # "diagram" | "illustration" | "none"

    def prompt_line(self) -> str:
        v = ("NO video block in this lesson." if not self.video else
             "Exactly ONE short video block (the lesson is about something that moves or changes).")
        if self.pictures == 0:
            p = "NO illustration or diagram block: this lesson is best as text and a worked example."
        else:
            p = f"At most {self.pictures} picture block(s) in total (illustration or diagram), preferably a {self.prefer}."
        return f"MEDIA PLAN (follow it, extra media is dropped): {v} {p}"


def _text(ol: OutlineLesson) -> str:
    return " ".join([ol.title, ol.summary, *ol.key_ideas])


def plan_media(outline: CourseOutline, source_text: str = "") -> dict[str, LessonMedia]:
    lessons = outline.lessons()
    band = outline.age_band
    first_of_chapter = {ch.lessons[0].id for ch in outline.chapters if ch.lessons}
    scores = {ol.id: 2 * len(DYNAMIC.findall(_text(ol))) + (1 if ol.id in first_of_chapter and DYNAMIC.search(_text(ol)) else 0)
              for ol in lessons}
    film = bool(FILM.search(source_text or ""))
    budget = math.ceil(len(lessons) * VIDEO_RATIO[band]) if lessons else 0
    if band == "g1_5":
        budget = 1 if film and lessons else 0
    elif band == "uni" and not film:
        budget = 0
    ranked = sorted(lessons, key=lambda ol: (-scores[ol.id], lessons.index(ol)))
    videos = {ol.id for ol in ranked[:budget] if scores[ol.id] > 0}
    if band == "g1_5" and budget:  # the source names a film: it opens the course
        videos = {lessons[0].id}
    plan: dict[str, LessonMedia] = {}
    for ol in lessons:
        t = _text(ol)
        shape, mathy, objs, dyn = bool(SHAPE.search(t)), bool(MATHY.search(t)), bool(OBJECTS.search(t)), bool(DYNAMIC.search(t))
        if band in ("g10_12", "uni") and not (shape or mathy or dyn) and ol.id not in videos:
            plan[ol.id] = LessonMedia(video=0, pictures=0, prefer="none")
            continue
        prefer = "diagram" if (shape or mathy) and not objs and band != "g1_5" else "illustration"
        pics = 0 if (ol.id in videos and band in ("g10_12", "uni") and not shape and not mathy) else MAX_PICTURES[band]
        plan[ol.id] = LessonMedia(video=1 if ol.id in videos else 0, pictures=pics, prefer=prefer if pics else "none")
    return plan


__all__ = ["LessonMedia", "plan_media", "VIDEO_RATIO", "MAX_PICTURES"]
