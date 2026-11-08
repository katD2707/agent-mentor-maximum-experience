"""Media stage entry point: MediaRequest -> MediaResult (see contracts.py for the spec of each kind).

    result = render_media(request, out_dir, client=ModelClient.from_env())

Files are written under `out_dir` at the `MediaFile.path` the result reports (audio/, video/, images/); editable
sources (HyperFrames project, SVG, diagram script) under out_dir/sources/<request id>/ (= result.source_dir).
Revise mode (request.revise): pass `source_dir` of the previous result inside `revise` alongside comment/at_s/x/y.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mentor_course_builder.contracts import MediaFile, MediaRequest, MediaResult
from mentor_course_builder.llm import ModelClient
from mentor_course_builder.media import MediaError
from mentor_course_builder.tts import TtsService

log = logging.getLogger("mentor_course_builder")

_REQUIRED = {
    "tts": ("text",),
    "video": ("title", "scenes"),
    "diagram": ("description",),
    "illustration": ("description",),
    "picture": ("description",),
    "cover": ("title", "subject", "idea"),
}


def validate_request(req: MediaRequest) -> None:
    missing = [k for k in _REQUIRED[req.kind] if not req.spec.get(k)]
    if missing:
        raise MediaError(f"{req.kind} spec is missing: {', '.join(missing)}")
    if req.kind == "video":
        for i, s in enumerate(req.spec["scenes"], 1):
            for k in ("caption", "narration", "visual"):
                if not str(s.get(k, "")).strip():
                    raise MediaError(f"video scene {i} is missing '{k}'")


def render_tts(req: MediaRequest, out_dir: Path, tts: TtsService) -> MediaResult:
    spec = req.spec
    rel = f"audio/{req.id}.mp3"
    clip = tts.synthesize(spec["text"], lang=req.language, age_band=req.age_band, rate=spec.get("rate"),
                          gender=spec.get("voice", "female"), dest=out_dir / rel)
    return MediaResult(id=req.id, kind="tts", duration_s=round(clip.duration_s, 2), notes=clip.notes[-2:],
                       files=[MediaFile(role="main", path=rel, mime="audio/mpeg", file=clip.path)])


def render_media(req: MediaRequest, out_dir: Path, *, client: ModelClient | None = None,
                 tts: TtsService | None = None) -> MediaResult:
    """Dispatch by kind. `client` is only needed for model-written kinds (not tts); `tts` defaults to Edge+Gemini."""
    validate_request(req)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if req.kind == "tts":
        return render_tts(req, out_dir, tts or TtsService())
    owned = client is None
    client = client or ModelClient.from_env()
    try:
        if req.kind == "video":
            from mentor_course_builder.video import make_video

            return make_video(req, out_dir, client, tts or TtsService())
        from mentor_course_builder.illustrate import make_diagram, make_image

        if req.kind == "diagram":
            return make_diagram(req, out_dir, client)
        return make_image(req, out_dir, client)
    finally:
        if owned:
            client.close()
