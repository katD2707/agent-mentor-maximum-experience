"""Hand-off between the content stage (outline, lessons, quiz, humanize) and the media stage (TTS, video,
diagrams, illustrations, cover). REQUIREMENTS-PLAN §4.4 steps 4–8.

The content stage writes lesson blocks and, wherever a block needs a file, a MediaRequest whose `id` is the block id
(or "<block id>.<part>" for audio of a quiz option etc.). The media stage turns each request into a MediaResult; the
assembler then fills AssetRefs into the pack and writes the files through mentor_gateway.content.ContentStore.

Specs per kind (keys are required unless marked optional):
  tts           {"text": str, "rate": "slow"|"normal" (optional, default by age band)}
  video         {"title": str, "target_s": int, "scenes": [{"caption": str, "narration": str, "visual": str}]}
                 visual = plain description of what to draw/animate (the media stage writes the HyperFrames HTML)
  diagram       {"description": str, "labels": [str] (optional), "math": str (optional: formula/data to plot exactly)}
  illustration  {"description": str}   in-lesson picture, no text inside the image
  picture       {"description": str, "count": int (optional)}  small object pictures for PICTURE_CHOICE / TAP_COUNT
  cover         {"title": str, "subject": str, "idea": str}   course cover, no text inside the image
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mentor_schemas.course import AgeBand, Lang

MediaKind = Literal["tts", "video", "diagram", "illustration", "picture", "cover"]


class MediaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: MediaKind
    course_id: str
    lesson_id: str | None = None
    age_band: AgeBand
    language: Lang
    spec: dict
    # Teacher comment to apply when re-generating (review stage); the media stage edits the existing source
    # (e.g. the HyperFrames scene at `at_s`, or the SVG region at `x`,`y`) instead of starting over.
    # {"comment": str, "source_dir": str (MediaResult.source_dir of the version being fixed),
    #  "at_s": float | None (video), "x": float | None, "y": float | None (images; 0–1 fractions accepted)}
    revise: dict | None = None


class MediaFile(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    role: Literal["main", "poster", "captions", "audio"]
    path: str  # path under the version's assets/ dir, e.g. "video/l3-v1.mp4"
    mime: str
    file: Path  # local file produced by the media stage


class MediaResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    id: str
    kind: MediaKind
    files: list[MediaFile]
    duration_s: float | None = None  # video / audio
    source_dir: Path | None = None  # editable source kept under v<N>/sources/ (HyperFrames project, SVG, script)
    timeline: list[dict] | None = None  # video: [{"start": s, "end": s, "file": str, "element": str}] for comments
    notes: list[str] = []  # warnings, provider used (e.g. "tts: edge-tts vi-VN-HoaiMyNeural")
    # images: provenance for credit and revise, same content as sources/<id>/image.json:
    # {"kind": "generated"|"web", "provider", "model"?, "prompt"?, "query"?, "sha256", "bytes", "width", "height",
    #  "attribution": null | {"provider","title","author","license","license_url","source_url"}, "critique": {...}}
    meta: dict | None = None
