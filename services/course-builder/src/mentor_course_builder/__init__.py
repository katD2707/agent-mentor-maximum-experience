"""Course-builder agent: stages 1-2 (intake, page quality) and the content stage (outline, lessons, quiz, humanize, verify, assemble)."""

from mentor_course_builder.intake import IntakeOptions, IntakeResult, intake
from mentor_course_builder.llm import ModelClient, ModelError
from mentor_course_builder.models import Material, Page, PageCheck
from mentor_course_builder.outline import CourseOutline, apply_outline_edits, build_outline, revise_outline
from mentor_course_builder.pipeline import build_course
from mentor_course_builder.quality import check_page, deterministic_check, vision_check

__all__ = [
    "CourseOutline",
    "apply_outline_edits",
    "build_course",
    "build_outline",
    "revise_outline",
    "IntakeOptions",
    "IntakeResult",
    "Material",
    "ModelClient",
    "ModelError",
    "Page",
    "PageCheck",
    "check_page",
    "deterministic_check",
    "intake",
    "vision_check",
]
