"""Per-page quality check: deterministic image metrics first, then a vision model judge + full-page OCR.

Why two layers (P0): models only judge what is visible, so they miss a half-missing page; code catches blur, darkness
and cut-off areas, the model catches content problems and returns the OCR text in the same call.
"""

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from mentor_schemas import ModelAlias
from PIL import Image

from mentor_course_builder.jsonparse import parse_model_json
from mentor_course_builder.llm import ModelClient, ModelError, image_part
from mentor_course_builder.models import GATED_KINDS, Page, PageCheck

log = logging.getLogger("mentor_course_builder")

# --- thresholds (tuned on synthetic + rendered pages, see tests/test_quality.py and the P3-A report) -------------------
ANALYSIS_WIDTH = 1000  # every image is resized to this width before measuring, so metrics do not depend on megapixels
MIN_SIDE_PX = 600  # shorter side below this: too small to read body text
MIN_LONG_SIDE_PX = 900
BLUR_VAR_MIN = 60.0  # variance of Laplacian at ANALYSIS_WIDTH; clean text pages are >> 300, blurred < 40
MIN_INK_FRACTION = 0.004  # blur is only judged when the page has some content (a blank sheet is not "blurry")
DARK_P95_MAX = 110  # 95th percentile of gray below this: even the brightest areas are dim
LOW_RANGE_MAX = 45  # p99 - p1 below this: washed out / no contrast
BLACK_PIXEL = 35  # gray level counted as "black"
BLACK_AREA_MAX = 0.20  # fraction of the page that is near-black (on a page that is otherwise bright)
BRIGHT_BLOCKS_MIN = 0.15  # cut-off black only counts on a page that also has bright (paper) areas
BLACK_BLOCK_STD = 10  # a block counts as cut-off black when its mean is dark and flat
SKEW_MAX_DEG = 20.0  # text lines rotated more than this are flagged
MODEL_MIN_FRACTION = 0.7  # readable_fraction below this fails the page

REASON_TEXT: dict[str, tuple[str, str]] = {
    "blurry": ("ảnh bị mờ, không đọc được chữ", "the image is blurry and the text cannot be read"),
    "too_dark": ("ảnh quá tối, thiếu sáng", "the image is too dark"),
    "low_contrast": ("ảnh bị mờ nhạt hoặc cháy sáng, thiếu độ tương phản", "the image is washed out or overexposed"),
    "missing_area": ("mất một phần trang (vùng đen hoặc bị cắt)", "part of the page is missing (black or cut-off area)"),
    "low_resolution": ("ảnh có độ phân giải quá thấp", "the image resolution is too low"),
    "skewed": ("ảnh bị nghiêng nhiều", "the page is strongly rotated"),
    "model_unreadable": ("nội dung không đọc được rõ", "the content could not be read clearly"),
    "blank_page": ("trang trống, không thấy nội dung", "the page looks blank, no content visible"),
    "no_speech": ("không nghe được lời nói", "no speech could be heard"),
    "unreadable_file": ("không mở được tệp", "the file could not be opened"),
}
KIND_LABEL = {
    "image": ("Ảnh", "Image"),
    "scanned_pdf": ("Trang", "Page"),
    "slide": ("Slide", "Slide"),
    "audio": ("Đoạn ghi âm", "Audio part"),
    "video_audio": ("Đoạn tiếng video", "Video audio part"),
    "video_frame": ("Khung hình", "Frame"),
}


@dataclass
class Deterministic:
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def load_gray(img: Image.Image | str | Path) -> tuple[np.ndarray, tuple[int, int]]:
    """Return (gray array resized to ANALYSIS_WIDTH, original (w, h))."""
    if not isinstance(img, Image.Image):
        img = Image.open(img)
    w, h = img.size
    rgb = img.convert("RGB")
    if w != ANALYSIS_WIDTH:
        rgb = rgb.resize((ANALYSIS_WIDTH, max(1, round(h * ANALYSIS_WIDTH / w))), Image.LANCZOS)
    return cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2GRAY), (w, h)


def _profile_score(canvas: np.ndarray, angle: float) -> float:
    side = canvas.shape[0]
    m = cv2.getRotationMatrix2D((side / 2, side / 2), angle, 1.0)
    prof = cv2.warpAffine(canvas, m, (side, side), flags=cv2.INTER_NEAREST).sum(axis=1).astype(np.float64)
    return float(np.var(np.diff(prof)))


def _skew_angle(gray: np.ndarray) -> float | None:
    """Text-line angle in degrees via projection-profile search; None when there is too little text."""
    small = cv2.resize(gray, (320, max(1, round(gray.shape[0] * 320 / gray.shape[1]))), interpolation=cv2.INTER_AREA)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    frac = bw.mean() / 255
    if frac < 0.01 or frac > 0.5:
        return None
    h, w = bw.shape
    side = int(np.hypot(h, w)) + 2
    canvas = np.zeros((side, side), np.uint8)
    y0, x0 = (side - h) // 2, (side - w) // 2
    canvas[y0 : y0 + h, x0 : x0 + w] = bw
    best, best_a = -1.0, 0.0
    for a in np.arange(-45, 45.1, 3.0):
        s = _profile_score(canvas, float(a))
        if s > best:
            best, best_a = s, float(a)
    for a in np.arange(best_a - 2.5, best_a + 2.6, 0.5):
        s = _profile_score(canvas, float(a))
        if s > best:
            best, best_a = s, float(a)
    return -best_a


def deterministic_check(img: Image.Image | str | Path) -> Deterministic:
    gray, (w, h) = load_gray(img)
    res = Deterministic()
    m = res.metrics
    m["width"], m["height"] = float(w), float(h)
    m["laplacian_var"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    p1, p95, p99 = (float(np.percentile(gray, q)) for q in (1, 95, 99))
    m["mean_brightness"], m["p95_brightness"], m["dynamic_range"] = float(gray.mean()), p95, p99 - p1
    # 16 x 16 block map: a block is "cut-off black" when it is dark and flat
    bh, bw_ = gray.shape[0] // 16, gray.shape[1] // 16
    blocks = gray[: bh * 16, : bw_ * 16].reshape(16, bh, 16, bw_).swapaxes(1, 2).reshape(16, 16, -1)
    dark_blocks = (blocks.mean(axis=2) < BLACK_PIXEL + 10) & (blocks.std(axis=2) < BLACK_BLOCK_STD)
    m["black_area"] = float(dark_blocks.mean())
    bright_blocks = float((blocks.mean(axis=2) > 150).mean())
    # ink: dark pixels relative to the local paper level; only used to decide whether blur can be judged
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    m["ink_fraction"] = float((ink > 0).mean())

    if min(w, h) < MIN_SIDE_PX or max(w, h) < MIN_LONG_SIDE_PX:
        res.reasons.append("low_resolution")
    if p95 < DARK_P95_MAX:
        res.reasons.append("too_dark")
    elif p99 - p1 < LOW_RANGE_MAX:
        res.reasons.append("blank_page" if m["ink_fraction"] < MIN_INK_FRACTION else "low_contrast")
    if bright_blocks >= BRIGHT_BLOCKS_MIN and m["black_area"] > BLACK_AREA_MAX:
        res.reasons.append("missing_area")
    exposure_ok = not {"too_dark", "low_contrast", "blank_page"} & set(res.reasons)
    if exposure_ok and m["black_area"] <= BLACK_AREA_MAX:
        if m["ink_fraction"] >= MIN_INK_FRACTION and m["laplacian_var"] < BLUR_VAR_MIN:
            res.reasons.append("blurry")
    if exposure_ok:
        a = _skew_angle(gray)
        m["skew_deg"] = a if a is not None else 0.0
        if a is not None and abs(a) > SKEW_MAX_DEG:
            res.reasons.append("skewed")
    return res


# --- vision layer -----------------------------------------------------------------------------------------------------

VISION_PROMPT = r"""You inspect one page photographed or scanned by a teacher, to be turned into a course.
Look ONLY at what is visible. Return ONE JSON object and nothing else, with exactly these keys:
{"readable": bool, "readable_fraction": number 0..1, "reason_vi": string, "reason_en": string, "text": string}
- readable: true if a student could read all the text on this page; false if text is blurry, cut off, covered, too dark
  or the page looks incomplete (for example half of the page is black, missing, or cropped mid-sentence).
- readable_fraction: share of the page's content (as you would expect a full page) that is clearly legible.
- reason_vi / reason_en: one short sentence for the teacher saying what is wrong; empty string if readable.
- text: the full text of the page, transcribed completely and in reading order, as Markdown. Write formulas as LaTeX
  ($...$ inline, $$...$$ for display). Keep tables as Markdown tables. Describe a figure as [Figure: short description].
  Do not summarise, do not translate, do not invent text you cannot see.
Inside the JSON strings escape every backslash (write \\frac, not \frac) and write newlines as \n."""


def _to_jpeg(img: Image.Image | str | Path, max_side: int = 2200) -> bytes:
    if not isinstance(img, Image.Image):
        img = Image.open(img)
    img = img.convert("RGB")
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


@dataclass
class VisionResult:
    readable: bool
    readable_fraction: float
    reason_vi: str
    reason_en: str
    text: str


def vision_check(img: Image.Image | str | Path, client: ModelClient) -> VisionResult:
    messages = [{"role": "user", "content": [{"type": "text", "text": VISION_PROMPT}, image_part(_to_jpeg(img))]}]
    last: Exception | None = None
    for _ in range(2):  # one re-ask if the reply is not parseable JSON
        raw = client.complete(ModelAlias.VISION, messages, max_tokens=12000)
        try:
            d = parse_model_json(raw)
        except ValueError as exc:
            last = exc
            continue
        return _vision_result(d)
    raise ModelError(f"vision reply was not valid JSON: {last}")


def _vision_result(d: dict[str, Any]) -> VisionResult:
    frac = d.get("readable_fraction")
    readable = d.get("readable")
    if isinstance(readable, str):
        readable = readable.strip().lower() == "true"
    try:
        frac = float(frac)
        frac = min(1.0, max(0.0, frac if frac <= 1 else frac / 100))
    except (TypeError, ValueError):
        frac = 1.0 if readable else 0.0
    return VisionResult(
        readable=bool(readable) if readable is not None else frac >= MODEL_MIN_FRACTION,
        readable_fraction=frac,
        reason_vi=str(d.get("reason_vi") or ""),
        reason_en=str(d.get("reason_en") or ""),
        text=str(d.get("text") or ""),
    )


# --- combine ----------------------------------------------------------------------------------------------------------


def page_label(page: Page, lang: str = "vi") -> str:
    vi, en = KIND_LABEL.get(page.kind, ("Trang", "Page"))
    base = vi if lang == "vi" else en
    if page.kind == "video_frame" and page.timestamp_s is not None:
        t = int(page.timestamp_s)
        return f"{base} {t // 60}:{t % 60:02d}"
    if page.kind == "image":
        return f"{base} {page.index} ({Path(page.source_file).name})"
    return f"{base} {page.index}"


def build_messages(page: Page, reasons: list[str], model_vi: str = "", model_en: str = "") -> tuple[str, str]:
    if not reasons:
        return "", ""
    code_reasons = [r for r in reasons if r != "model_unreadable"]
    vi = [REASON_TEXT[r][0] for r in code_reasons]
    en = [REASON_TEXT[r][1] for r in code_reasons]
    if "model_unreadable" in reasons and not code_reasons:  # the model's own words only when code found nothing
        vi.append(model_vi.strip().rstrip(".") or REASON_TEXT["model_unreadable"][0])
        en.append(model_en.strip().rstrip(".") or REASON_TEXT["model_unreadable"][1])
    return f"{page_label(page, 'vi')}: {'; '.join(vi)}", f"{page_label(page, 'en')}: {'; '.join(en)}"


def check_page(page: Page, client: ModelClient | None, *, gate: bool | None = None, ocr: bool = True) -> PageCheck:
    """Quality check + OCR for an image page. `gate=False` extracts text but never fails the page (video frames)."""
    gate = page.kind in GATED_KINDS if gate is None else gate
    check = PageCheck(page=page.index, source_file=page.source_file, kind=page.kind, ok=True)
    try:
        det = deterministic_check(page.image_path)  # type: ignore[arg-type]
    except Exception as exc:  # corrupt image file
        log.warning("cannot open image %s: %s", page.image_path, exc.__class__.__name__)
        check.ok, check.reasons = False, ["unreadable_file"]
        check.message_vi, check.message_en = build_messages(page, check.reasons)
        return check
    check.metrics = det.metrics
    reasons = list(det.reasons) if gate else []
    model_vi = model_en = ""
    if client is not None and ocr:
        # Pages flagged by code still go to the model: its OCR is kept if it manages, and its fraction is recorded.
        try:
            v = vision_check(page.image_path, client)  # type: ignore[arg-type]
        except ModelError as exc:
            log.warning("vision check failed for %s p%s: %s", page.source_file, page.index, exc)
            check.metrics["model_error"] = 1.0
        else:
            check.text, check.readable_fraction = v.text or None, v.readable_fraction
            model_vi, model_en = v.reason_vi, v.reason_en
            if gate and (not v.readable or v.readable_fraction < MODEL_MIN_FRACTION):
                reasons.append("model_unreadable")
    check.reasons = reasons
    check.ok = not reasons
    check.message_vi, check.message_en = build_messages(page, reasons, model_vi, model_en)
    return check
