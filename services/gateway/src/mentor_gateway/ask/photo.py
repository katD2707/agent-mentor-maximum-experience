"""Photo handling for Q&A: decode (EXIF rotation, HEIC when pillow-heif is installed), cap the size, and the deterministic
quality check (blur, darkness, cut-off areas, resolution, skew).

The check is copied from services/course-builder (mentor_course_builder.quality.deterministic_check): importing that package
pulls docling/torch, so only these small pure functions are duplicated here. numpy, opencv and pillow are imported lazily;
if they are missing the check is skipped (no reasons) and the vision model alone judges the photo.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

try:  # optional: see module docstring
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    HAVE_IMAGING = True
except ImportError:  # pragma: no cover - depends on the environment
    HAVE_IMAGING = False

MAX_SIDE = 2200

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
HOPELESS_BLUR_VAR = 8.0  # Laplacian variance: a clean page is > 300, mild blur 60 to 100, this is a smear
HOPELESS_DARK_P95 = 55
MODEL_MIN_FRACTION = 0.7  # readable_fraction below this fails the page


@dataclass
class Deterministic:
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def load_gray(img: Image.Image) -> tuple[np.ndarray, tuple[int, int]]:
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


def deterministic_check(img: Image.Image) -> Deterministic:
    gray, (w, h) = load_gray(img)
    res = Deterministic()
    m = res.metrics
    m["width"], m["height"] = float(w), float(h)
    m["laplacian_var"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    # p0.1 not p1: a page with one short problem has under 1% ink, p1 would still be paper and read as "no contrast"
    p1, p95, p99 = (float(np.percentile(gray, q)) for q in (0.1, 95, 99))
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
    if exposure_ok and m["black_area"] <= BLACK_AREA_MAX and m["ink_fraction"] >= MIN_INK_FRACTION and m["laplacian_var"] < BLUR_VAR_MIN:
        res.reasons.append("blurry")
    if exposure_ok:
        a = _skew_angle(gray)
        m["skew_deg"] = a if a is not None else 0.0
        if a is not None and abs(a) > SKEW_MAX_DEG:
            res.reasons.append("skewed")
    return res




REASON_TEXT = {
    "blurry": ("ảnh bị mờ", "the photo is blurry"),
    "too_dark": ("ảnh quá tối", "the photo is too dark"),
    "low_contrast": ("ảnh bị nhạt hoặc cháy sáng", "the photo is washed out or overexposed"),
    "missing_area": ("mất một phần trang (vùng đen hoặc bị cắt)", "part of the page is cut off or black"),
    "low_resolution": ("ảnh quá nhỏ", "the photo resolution is too low"),
    "skewed": ("ảnh bị nghiêng nhiều", "the page is strongly tilted"),
    "blank_page": ("không thấy nội dung trong ảnh", "no content is visible in the photo"),
}


def open_image(data: bytes) -> Image.Image:
    """Decode with EXIF rotation applied. Raises ValueError when the bytes are not an image."""
    try:
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except ImportError:
            pass
        img = Image.open(io.BytesIO(data))
        img.load()
        return ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise ValueError(f"not an image: {e}") from e


def to_jpeg(img: Image.Image, max_side: int = MAX_SIDE) -> bytes:
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def hopeless(det: Deterministic) -> bool:
    """Blur or darkness so strong that reading is pointless: skip the (slow) vision call and ask for a retake."""
    m = det.metrics
    blur = "blurry" in det.reasons and m.get("laplacian_var", 1e9) < HOPELESS_BLUR_VAR
    dark = "too_dark" in det.reasons and m.get("p95_brightness", 255) < HOPELESS_DARK_P95
    return blur or dark


def check_photo(img: Image.Image) -> Deterministic:
    return deterministic_check(img) if HAVE_IMAGING else Deterministic()
