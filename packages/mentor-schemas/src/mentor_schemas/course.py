"""Course content contracts (REQUIREMENTS-PLAN §5.3–§5.5).

A course is built by the course-builder agent from a teacher's materials and published as immutable versions.
On disk (dev: mentor-content/courses/, later object storage) and on the wire the same three files are used:

    catalog.json                         Catalog       every published course, latest version only
    <course_id>/course.json              CourseMeta    metadata + version history
    <course_id>/v<N>/pack.json           CoursePack    the whole course content for version N
    <course_id>/v<N>/assets/<path>       files         video, audio, images referenced by AssetRef.path
    <course_id>/v<N>/sources/...         server only   teacher materials, HyperFrames projects, SVG sources

Rules:
- A published version never changes. Editing a published course creates version N+1.
- Chapter, lesson, block and quiz-item ids are stable across versions, so progress and teacher comments survive
  edits. A new id means new content.
- Text is Markdown with KaTeX math ($...$, $$...$$). No raw HTML.
- Enrollments pin a version; learners stay on it until they finish (§3.3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 1

AgeBand = Literal["g1_5", "g6_9", "g10_12", "uni"]
Lang = Literal["vi", "en"]
Level = Literal["basic", "intermediate", "advanced"]  # course difficulty: the teacher confirms, the agent only suggests
Media = Literal["video", "reading", "quiz", "audio", "interactive"]
Id = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetRef(_Strict):
    """A file under <course_id>/v<N>/assets/."""

    path: Annotated[str, Field(pattern=r"^[A-Za-z0-9._/-]+$")]
    mime: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    bytes: int = Field(ge=0)


# ---------------------------------------------------------------- quiz items
QuizType = Literal["SINGLE_CHOICE", "TRUE_FALSE_GROUP", "SHORT_ANSWER", "PICTURE_CHOICE", "TAP_COUNT"]


class QuizOption(_Strict):
    id: Annotated[str, Field(pattern=r"^[A-Z]$")]
    text: str | None = None  # Markdown; may be empty for PICTURE_CHOICE
    image: AssetRef | None = None
    audio: AssetRef | None = None  # read-aloud for g1_5


class TrueFalseStatement(_Strict):
    id: Annotated[str, Field(pattern=r"^[a-d]$")]
    text: str


class TapTarget(_Strict):
    """TAP_COUNT: the player shows `total` copies of `image`; the learner taps until the count is right."""

    image: AssetRef
    total: int = Field(ge=1, le=20)


class QuizItem(_Strict):
    """Same answer semantics as the practice bank (mentor-content/bank), so practice can draw course items.

    answer_key by type:
      SINGLE_CHOICE / PICTURE_CHOICE  {"correct_option_id": "B"}
      TRUE_FALSE_GROUP                {"statements": {"a": true, "b": false, ...}}
      SHORT_ANSWER                    {"accepted": ["4e4", "40000"], "tolerance": 0.01}   (tolerance optional)
      TAP_COUNT                       {"count": 7}
    """

    id: Id
    type: QuizType
    stem: str  # Markdown
    stem_audio: AssetRef | None = None
    stem_image: AssetRef | None = None
    options: list[QuizOption] = []
    statements: list[TrueFalseStatement] = []
    tap: TapTarget | None = None
    answer_key: dict
    hint: str | None = None
    explanation: str  # one or two short sentences: why the right answer is right / the slip
    option_feedback: dict[str, str] = {}  # option id -> one sentence for that wrong choice
    skill_ids: list[str] = []
    difficulty: int = Field(default=2, ge=1, le=4)

    @model_validator(mode="after")
    def _shape(self) -> "QuizItem":
        t, k = self.type, self.answer_key
        if t in ("SINGLE_CHOICE", "PICTURE_CHOICE"):
            ids = {o.id for o in self.options}
            if len(self.options) < 2 or k.get("correct_option_id") not in ids:
                raise ValueError(f"{self.id}: needs >=2 options and correct_option_id among them")
            if t == "PICTURE_CHOICE" and not all(o.image for o in self.options):
                raise ValueError(f"{self.id}: PICTURE_CHOICE options need images")
        elif t == "TRUE_FALSE_GROUP":
            if not self.statements or set(k.get("statements", {})) != {s.id for s in self.statements}:
                raise ValueError(f"{self.id}: answer_key.statements must cover every statement")
        elif t == "SHORT_ANSWER":
            if not k.get("accepted"):
                raise ValueError(f"{self.id}: answer_key.accepted is required")
        elif t == "TAP_COUNT":
            if not self.tap or not isinstance(k.get("count"), int) or not 0 <= k["count"] <= self.tap.total:
                raise ValueError(f"{self.id}: TAP_COUNT needs tap and 0 <= count <= tap.total")
        return self


# ---------------------------------------------------------------- blocks
class _Block(_Strict):
    id: Id


class TextBlock(_Block):
    kind: Literal["text"] = "text"
    md: str
    audio: AssetRef | None = None  # read-aloud (always present for g1_5)


class CalloutBlock(_Block):
    """Boxed text: 'Bốn điều cần nhớ', a definition, a worked example, a tip or a common mistake."""

    kind: Literal["callout"] = "callout"
    variant: Literal["remember", "definition", "example", "tip", "mistake"]
    title: str | None = None
    md: str
    audio: AssetRef | None = None


class ImageBlock(_Block):
    kind: Literal["image"] = "image"
    image: AssetRef
    alt: str
    caption: str | None = None
    audio: AssetRef | None = None
    # credit for a picture taken from the web: {provider, title, author, license, license_url, source_url}; None = made by us
    attribution: dict[str, str | None] | None = None


class VideoBlock(_Block):
    kind: Literal["video"] = "video"
    video: AssetRef
    poster: AssetRef | None = None
    captions: AssetRef | None = None  # WebVTT
    duration_s: float = Field(gt=0)
    title: str | None = None


class AudioBlock(_Block):
    kind: Literal["audio"] = "audio"
    audio: AssetRef
    transcript: str


class QuizBlock(_Block):
    """Questions inside a lesson ('Kiểm tra'). Items also feed Luyện tập."""

    kind: Literal["quiz"] = "quiz"
    title: str | None = None
    items: list[QuizItem] = Field(min_length=1)


Block = Annotated[
    Union[TextBlock, CalloutBlock, ImageBlock, VideoBlock, AudioBlock, QuizBlock],
    Field(discriminator="kind"),
]

# first app release that renders each block kind / quiz type. A new kind or type must be added here with the app
# version that ships its renderer, so packs using it carry that min_app_version and older apps refuse them.
APP_VERSION_FOR: dict[str, str] = {
    **{k: "0.1.0" for k in ("text", "callout", "image", "video", "audio", "quiz")},
    **{t: "0.1.0" for t in QuizType.__args__},  # type: ignore[attr-defined]
}


# ---------------------------------------------------------------- course structure
class Lesson(_Strict):
    id: Id
    title: str
    est_minutes: int = Field(ge=1, le=240)
    summary: str | None = None  # one sentence, shown in the tree
    key_ideas: list[str] = []  # leaves of the course tree on the intro page
    blocks: list[Block] = Field(min_length=1)


class Chapter(_Strict):
    id: Id
    title: str
    lessons: list[Lesson] = Field(min_length=1)


class CoursePack(_Strict):
    """<course_id>/v<N>/pack.json — immutable once published."""

    schema_version: Literal[1] = SCHEMA_VERSION
    course_id: Id
    version: int = Field(ge=1)
    # the oldest app that can show every block in this pack; older apps refuse the pack instead of guessing
    min_app_version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+$")
    language: Lang
    age_band: AgeBand
    title: str
    chapters: list[Chapter] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "CoursePack":
        seen: set[str] = set()
        for ch in self.chapters:
            for i in [ch.id] + [ls.id for ls in ch.lessons]:
                if i in seen:
                    raise ValueError(f"duplicate id {i}")
                seen.add(i)
            for ls in ch.lessons:
                for b in ls.blocks:
                    ids = [b.id] + ([q.id for q in b.items] if isinstance(b, QuizBlock) else [])
                    for i in ids:
                        if i in seen:
                            raise ValueError(f"duplicate id {i}")
                        seen.add(i)
        return self

    def required_app_version(self) -> str:
        """The oldest app that renders every block kind and quiz type used here (see APP_VERSION_FOR)."""
        used = {b.kind for ch in self.chapters for ls in ch.lessons for b in ls.blocks}
        used |= {q.type for ch in self.chapters for ls in ch.lessons for b in ls.blocks
                 if isinstance(b, QuizBlock) for q in b.items}
        return max((APP_VERSION_FOR[k] for k in used), key=lambda v: tuple(map(int, v.split("."))), default="0.1.0")

    def assets(self) -> list[AssetRef]:
        """Every asset the pack references (for download, hashing and offline caching)."""
        out: list[AssetRef] = []

        def add(*refs: AssetRef | None) -> None:
            out.extend(r for r in refs if r is not None)

        for ch in self.chapters:
            for ls in ch.lessons:
                for b in ls.blocks:
                    if isinstance(b, (TextBlock, CalloutBlock)):
                        add(b.audio)
                    elif isinstance(b, ImageBlock):
                        add(b.image, b.audio)
                    elif isinstance(b, VideoBlock):
                        add(b.video, b.poster, b.captions)
                    elif isinstance(b, AudioBlock):
                        add(b.audio)
                    elif isinstance(b, QuizBlock):
                        for q in b.items:
                            add(q.stem_audio, q.stem_image, q.tap.image if q.tap else None)
                            for o in q.options:
                                add(o.image, o.audio)
        return out


class VersionInfo(_Strict):
    version: int = Field(ge=1)
    status: Literal["draft", "review", "published"]
    created_at: datetime
    published_at: datetime | None = None
    pack_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    pack_bytes: int | None = None  # pack.json + all assets
    note: str | None = None  # what changed, one line
    level_suggested: Level | None = None  # the builder's guess for this version; never shown to students
    level_confirmed: Level | None = None  # what the teacher picked; publishing needs it; becomes CourseMeta.level


CourseStatus = Literal["live", "coming_soon"]


class OutlineLesson(_Strict):
    id: Id
    title: str
    est_minutes: int = Field(ge=1, le=240)


class OutlineChapter(_Strict):
    id: Id
    title: str
    lessons: list[OutlineLesson] = Field(min_length=1)


class CourseMeta(_Strict):
    """<course_id>/course.json.

    `status: "coming_soon"` marks a placeholder (mentor-content/tools/make_placeholders.py): an overview with `outline`
    and no pack. It has no versions, cannot be enrolled in and never has a pack.json. Real courses are "live".
    """

    schema_version: Literal[1] = SCHEMA_VERSION
    id: Id
    title: str
    subject: str  # free text in the course language, e.g. "Vật lí"
    age_band: AgeBand
    language: Lang  # shown as the Tiếng Việt / English tag next to the description (§3.10)
    teacher_id: str
    teacher_name: str
    description_short: str = Field(max_length=400)  # two sentences; also the retrieval text (§3.5)
    outcomes: list[str] = []  # "Học xong em sẽ…"
    cover: str  # path relative to the course dir, e.g. "cover.webp"
    media: list[Media] = []
    lessons_count: int = 0
    est_minutes: int = 0
    latest_published: int | None = None
    versions: list[VersionInfo] = []
    level: Level | None = None  # difficulty the teacher confirmed for the latest published version
    status: CourseStatus = "live"
    outline: list[OutlineChapter] = []  # coming_soon only: the lesson tree shown on the course page


class CatalogEntry(_Strict):
    id: Id
    title: str
    subject: str
    age_band: AgeBand
    language: Lang
    teacher_name: str
    description_short: str
    outcomes: list[str] = []
    cover_sha256: str
    media: list[Media] = []
    lessons_count: int
    est_minutes: int
    version: int = 0
    pack_sha256: str = ""
    pack_bytes: int = 0
    published_at: datetime | None = None
    level: Level | None = None  # difficulty the teacher confirmed for the latest published version
    status: CourseStatus = "live"

    @model_validator(mode="after")
    def _live_has_pack(self) -> "CatalogEntry":
        if self.status == "live" and (self.version < 1 or not self.pack_sha256 or self.published_at is None):
            raise ValueError(f"{self.id}: a live course needs version, pack_sha256 and published_at")
        return self


class Catalog(_Strict):
    """catalog.json — published courses (latest version of each), then coming_soon placeholders."""

    schema_version: Literal[1] = SCHEMA_VERSION
    generated_at: datetime
    courses: list[CatalogEntry] = []
