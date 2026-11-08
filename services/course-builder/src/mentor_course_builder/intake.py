"""Stage 1-2 of the course-builder pipeline: receive teacher files, split into pages, check and extract text.

    result = intake(["book.pdf", "IMG_1.heic", "lesson.mp4"], out_dir, client=ModelClient.from_env())
    result.materials   # list[Material]: pages with text / transcript / image_path
    result.checks      # list[PageCheck]: one per page (ok, reasons, message_vi/en, text)
    result.retake      # checks to show the teacher as "retake page X"
"""

import json
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mentor_schemas import ModelAlias
from PIL import Image, ImageOps

from mentor_course_builder import documents, media
from mentor_course_builder.llm import ModelClient, ModelError, audio_part
from mentor_course_builder.models import (
    GATED_KINDS,
    KIND_AUDIO,
    KIND_DOCX,
    KIND_IMAGE,
    KIND_PDF_TEXT,
    KIND_SCANNED_PDF,
    KIND_SLIDE,
    KIND_VIDEO_AUDIO,
    KIND_VIDEO_FRAME,
    Material,
    Page,
    PageCheck,
)
from mentor_course_builder.quality import build_messages, check_page

log = logging.getLogger("mentor_course_builder")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MAX_IMAGE_SIDE = 3200


@dataclass
class IntakeOptions:
    keyframe_every_s: float = 30.0
    scene_threshold: float = 0.3
    max_frames: int = 60
    audio_chunk_s: int = 600
    render_dpi: int = 150
    scanned_min_chars: int = 30  # PDF page with fewer text-layer characters is treated as a scan
    ocr: bool = True  # vision OCR + judgement on image pages
    ocr_video_frames: bool = True
    workers: int = 3  # parallel model calls (the gateway rate-limits; keep small)


@dataclass
class IntakeResult:
    materials: list[Material] = field(default_factory=list)
    checks: list[PageCheck] = field(default_factory=list)

    @property
    def retake(self) -> list[PageCheck]:
        return [c for c in self.checks if not c.ok]

    def summary(self) -> str:
        pages = sum(len(m.pages) for m in self.materials)
        lines = [f"Đã đọc {len(self.materials)} tệp, {pages} trang/đoạn; {len(self.retake)} cần chụp lại."]
        lines += [f"- {c.message_vi}" for c in self.retake]
        for m in self.materials:
            lines += [f"! {m.source_file}: {n}" for n in m.notes]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {"materials": [m.to_dict() for m in self.materials], "checks": [c.to_dict() for c in self.checks]}


def _register_heif() -> None:
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:  # pragma: no cover
        pass


def normalise_image(src: Path, dest: Path) -> Path:
    """Decode (HEIC included), apply EXIF rotation, cap the size, save as JPEG (PNG stays lossless)."""
    _register_heif()
    img = ImageOps.exif_transpose(Image.open(src))
    if max(img.size) > MAX_IMAGE_SIDE:
        s = MAX_IMAGE_SIDE / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    if src.suffix.lower() == ".png":
        dest = dest.with_suffix(".png")
        img.save(dest, "PNG")
        return dest
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        img = bg
    dest = dest.with_suffix(".jpg")
    img.convert("RGB").save(dest, "JPEG", quality=92)
    return dest


TRANSCRIBE_PROMPT = (
    "Transcribe this audio exactly as spoken, in the original language (Vietnamese or English). Plain text only, "
    "no timestamps, no commentary. Mathematical expressions spoken aloud may be written as LaTeX between $...$. "
    "If there is no intelligible speech, reply with exactly: [NO_SPEECH]"
)


def transcribe(path: Path, client: ModelClient) -> str:
    fmt = "wav" if path.suffix.lower() == ".wav" else "mp3"
    content = [{"type": "text", "text": TRANSCRIBE_PROMPT}, audio_part(path.read_bytes(), fmt)]
    text = client.complete(ModelAlias.AUDIO, [{"role": "user", "content": content}], max_tokens=16000).strip()
    return "" if text.strip("[] ").upper() == "NO_SPEECH" else text


class _Ctx:
    def __init__(self, out_dir: Path, client: ModelClient | None, opts: IntakeOptions) -> None:
        self.out, self.client, self.opts = out_dir, client, opts
        self.images = out_dir / "images"
        self.images.mkdir(parents=True, exist_ok=True)
        self.image_counter = 0  # uploaded photos are numbered across files: "Ảnh 3"
        self.failed: dict[tuple[str, int, str], PageCheck] = {}  # (source, index, kind) -> check decided at intake


def _stem(path: Path, n: int) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in path.stem)[:40]
    return f"{n:02d}_{safe}"


def _failed(page: Page, reason: str) -> PageCheck:
    c = PageCheck(page=page.index, source_file=page.source_file, kind=page.kind, ok=False, reasons=[reason])
    c.message_vi, c.message_en = build_messages(page, c.reasons)
    return c


def _intake_image(src: Path, ctx: _Ctx, n: int) -> Material:
    ctx.image_counter += 1
    m = Material(str(src), "image")
    page = Page(str(src), ctx.image_counter, KIND_IMAGE)
    try:
        page.image_path = str(normalise_image(src, ctx.images / _stem(src, n)))
    except Exception as exc:
        m.notes.append(f"cannot open image ({exc.__class__.__name__})")
        ctx.failed[(page.source_file, page.index, page.kind)] = _failed(page, "unreadable_file")
    m.pages.append(page)
    return m


def _intake_pdf(src: Path, ctx: _Ctx, n: int) -> Material:
    m = Material(str(src), "pdf")
    chars = documents.pdf_text_chars(src)
    scanned = [i + 1 for i, c in enumerate(chars) if c < ctx.opts.scanned_min_chars]
    text_pages = [i + 1 for i in range(len(chars)) if i + 1 not in scanned]
    md: dict[int, str] = {}
    if text_pages:
        try:
            md = documents.docling_pages(src)
        except Exception as exc:
            m.notes.append(f"Docling failed ({exc.__class__.__name__}); plain text layer used")
            md = documents.plain_pdf_text(src, text_pages)
    imgs = documents.render_pdf_pages(src, ctx.images, scanned, ctx.opts.render_dpi, prefix=_stem(src, n)) if scanned else {}
    for p in range(1, len(chars) + 1):
        if p in imgs:
            m.pages.append(Page(str(src), p, KIND_SCANNED_PDF, image_path=str(imgs[p])))
        else:
            m.pages.append(Page(str(src), p, KIND_PDF_TEXT, text=md.get(p, "").strip() or None))
    return m


def _intake_docx(src: Path, ctx: _Ctx, n: int) -> Material:
    m = Material(str(src), "docx")
    md = documents.docling_pages(src)
    for i, chunk in enumerate(documents.split_markdown("\n\n".join(md.values())), 1):
        m.pages.append(Page(str(src), i, KIND_DOCX, text=chunk))
    return m


def _intake_pptx(src: Path, ctx: _Ctx, n: int) -> Material:
    m = Material(str(src), "pptx")
    md = documents.docling_pages(src)
    imgs = documents.render_slides(src, ctx.images / _stem(src, n))
    if not imgs:
        m.notes.append("slide images not rendered (LibreOffice not found); text only")
    for i, (_, text) in enumerate(sorted(md.items()), 1):
        img = imgs.get(i)
        m.pages.append(Page(str(src), i, KIND_SLIDE, text=text.strip() or None, image_path=str(img) if img else None))
    return m


def _safe_transcribe(client: ModelClient, path: Path) -> str:
    try:
        return transcribe(path, client)
    except ModelError as exc:
        log.warning("transcription failed: %s", exc)
        return ""


def _intake_speech(src: Path, kind: str, ctx: _Ctx, n: int, m: Material) -> None:
    if ctx.client is None:
        m.notes.append("no model client: audio not transcribed")
        return
    chunks = media.extract_audio_chunks(src, ctx.out / "audio" / _stem(src, n), ctx.opts.audio_chunk_s)
    if not chunks:
        m.notes.append("no audio track")
        return
    with ThreadPoolExecutor(ctx.opts.workers) as pool:
        texts = list(pool.map(lambda c: _safe_transcribe(ctx.client, c[0]), chunks))  # type: ignore[arg-type]
    for i, ((_, start), text) in enumerate(zip(chunks, texts), 1):
        page = Page(str(src), i, kind, transcript=text or None, timestamp_s=start)
        m.pages.append(page)
        if not text:
            ctx.failed[(page.source_file, page.index, page.kind)] = _failed(page, "no_speech")


def _intake_audio(src: Path, ctx: _Ctx, n: int) -> Material:
    m = Material(str(src), "audio")
    _intake_speech(src, KIND_AUDIO, ctx, n, m)
    return m


def _intake_video(src: Path, ctx: _Ctx, n: int) -> Material:
    m = Material(str(src), "video")
    _intake_speech(src, KIND_VIDEO_AUDIO, ctx, n, m)
    frames = media.extract_keyframes(
        src, ctx.images / _stem(src, n), ctx.opts.keyframe_every_s, ctx.opts.scene_threshold, ctx.opts.max_frames
    )
    for i, (path, t) in enumerate(frames, 1):
        m.pages.append(Page(str(src), i, KIND_VIDEO_FRAME, image_path=str(path), timestamp_s=t))
    return m


Route = Callable[[Path, _Ctx, int], Material]
_ROUTES: dict[str, Route] = {
    **{e: _intake_image for e in IMAGE_EXT},
    ".pdf": _intake_pdf,
    ".docx": _intake_docx,
    ".pptx": _intake_pptx,
    **{e: _intake_audio for e in AUDIO_EXT},
    **{e: _intake_video for e in VIDEO_EXT},
}


def intake(
    files: Sequence[str | Path],
    out_dir: str | Path,
    *,
    client: ModelClient | None = None,
    options: IntakeOptions | None = None,
) -> IntakeResult:
    """Run stages 1-2 over `files`. Writes images/audio under `out_dir`; returns materials + per-page checks."""
    opts = options or IntakeOptions()
    ctx = _Ctx(Path(out_dir), client, opts)
    result = IntakeResult()
    for n, f in enumerate(files, 1):
        src = Path(f)
        ext = src.suffix.lower()
        route = _ROUTES.get(ext)
        if route is None:
            result.materials.append(Material(str(src), "unknown", notes=[f"unsupported file type {ext or '(none)'}"]))
            continue
        try:
            result.materials.append(route(src, ctx, n))
        except Exception as exc:  # one bad file must not stop the batch
            log.warning("intake failed for %s: %s", src.name, exc.__class__.__name__)
            result.materials.append(Material(str(src), ext.lstrip("."), notes=[f"{exc.__class__.__name__}: {exc}"[:300]]))

    # Image-bearing pages get quality check + OCR (parallel); text/transcript pages are ok by construction.
    todo = [
        p
        for m in result.materials
        for p in m.pages
        if p.image_path and p.kind in (KIND_IMAGE, KIND_SCANNED_PDF, KIND_VIDEO_FRAME)
    ]

    def run(p: Page) -> PageCheck:
        if p.kind == KIND_VIDEO_FRAME:  # the teacher cannot retake a video frame: extract text, never fail
            return check_page(p, client, gate=False, ocr=opts.ocr and opts.ocr_video_frames)
        return check_page(p, client, ocr=opts.ocr)

    with ThreadPoolExecutor(opts.workers) as pool:
        checked = {id(p): c for p, c in zip(todo, pool.map(run, todo))}
    for m in result.materials:
        for p in m.pages:
            c = checked.get(id(p)) or ctx.failed.get((p.source_file, p.index, p.kind))
            if c is None:
                c = PageCheck(page=p.index, source_file=p.source_file, kind=p.kind, ok=True, text=p.text or p.transcript)
            if p.kind in GATED_KINDS | {KIND_VIDEO_FRAME} and c.text:
                p.text = c.text
            result.checks.append(c)
    return result


def write_outputs(result: IntakeResult, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = result.to_dict()
    (out / "pages.json").write_text(json.dumps(data["materials"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "checks.json").write_text(json.dumps(data["checks"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "summary.txt").write_text(result.summary() + "\n", encoding="utf-8")
