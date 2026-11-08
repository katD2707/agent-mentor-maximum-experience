"""Data shapes of the intake stage. Plain dataclasses, JSON-serialisable via `to_dict()`."""

from dataclasses import asdict, dataclass, field
from typing import Any

# Page kinds. Only `image` and `scanned_pdf` pages are quality-gated (the teacher can retake those).
KIND_IMAGE = "image"
KIND_SCANNED_PDF = "scanned_pdf"
KIND_PDF_TEXT = "pdf_text"
KIND_DOCX = "docx_section"
KIND_SLIDE = "slide"
KIND_AUDIO = "audio"
KIND_VIDEO_AUDIO = "video_audio"
KIND_VIDEO_FRAME = "video_frame"

GATED_KINDS = {KIND_IMAGE, KIND_SCANNED_PDF}


@dataclass
class Page:
    source_file: str
    index: int  # 1-based within the source file
    kind: str
    image_path: str | None = None
    text: str | None = None  # Markdown (+LaTeX) text of the page
    transcript: str | None = None  # speech to text (audio, video audio track)
    timestamp_s: float | None = None  # video frame time / audio chunk start

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageCheck:
    page: int
    source_file: str
    kind: str
    ok: bool
    reasons: list[str] = field(default_factory=list)
    message_vi: str = ""
    message_en: str = ""
    text: str | None = None
    readable_fraction: float | None = None
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Material:
    source_file: str
    kind: str  # image | pdf | docx | pptx | audio | video
    pages: list[Page] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # e.g. "ffmpeg missing: audio skipped"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
