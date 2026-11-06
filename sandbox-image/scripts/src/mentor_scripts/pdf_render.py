"""pdf_render: PNG images of a few pages of a workspace PDF, for PDFs without a text layer (scans).

Input: {path, pages?: [int] (default the first 3; at most 5 per call), width?: 1400 (px, 400..2000)}.
Output: {images: [{n, path}], page_count}. Each page is written next to the PDF as `<stem>-p<N>.png`
(overwritten if present), so the PDF must sit in an agent-writable folder (inbox/, research/, learning/...).
The model then reads the images with look_at_image. No OCR here. Renderer: pypdfium2 (bundled PDFium);
the PNG encoder is stdlib (zlib), so no Pillow / numpy is needed.
"""

import struct
import zlib
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from mentor_schemas import is_agent_writable

from mentor_scripts.common import ScriptError, resolve_in_workspace, run_cli

DEFAULT_PAGES = 3
MAX_PAGES = 5
DEFAULT_WIDTH = 1400
MIN_WIDTH, MAX_WIDTH = 400, 2000
MAX_SIDE = 2400  # tall pages: the long side is capped too


def encode_png(width: int, height: int, stride: int, channels: int, buf: bytes) -> bytes:
    """8-bit grayscale / RGB / RGBA PNG from raw rows (no filtering; scans compress well enough)."""
    color_type = {1: 0, 3: 2, 4: 6}[channels]
    row = width * channels
    raw = b"".join(b"\x00" + buf[y * stride : y * stride + row] for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def _pages(payload: dict[str, Any], page_count: int) -> list[int]:
    raw = payload.get("pages")
    if raw is None:
        return list(range(1, min(DEFAULT_PAGES, page_count) + 1))
    if not isinstance(raw, list) or not raw or not all(isinstance(n, int) and not isinstance(n, bool) for n in raw):
        raise ScriptError("pages must be a non-empty list of page numbers (from 1)")
    pages = list(dict.fromkeys(raw))
    if len(pages) > MAX_PAGES:
        raise ScriptError(f"at most {MAX_PAGES} pages per call")
    bad = [n for n in pages if not 1 <= n <= page_count]
    if bad:
        raise ScriptError(f"page {bad[0]} out of range (the PDF has {page_count} pages)")
    return pages


def pdf_render(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    rel = payload.get("path", "")
    path = resolve_in_workspace(root, rel)
    width = payload.get("width", DEFAULT_WIDTH)
    if not isinstance(width, int) or isinstance(width, bool) or not MIN_WIDTH <= width <= MAX_WIDTH:
        raise ScriptError(f"width must be an integer between {MIN_WIDTH} and {MAX_WIDTH}")
    if not path.is_file():
        raise ScriptError(f"file not found: {rel}")
    pdf_rel = path.relative_to(root).as_posix()
    if path.suffix.lower() != ".pdf":
        raise ScriptError("path must be a .pdf file")
    base = pdf_rel[:-4]  # images: <base>-p<N>.png
    if not is_agent_writable(f"{base}-p1.png"):
        raise ScriptError(f"images are written next to the PDF; {pdf_rel} is not in a writable folder")
    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as e:
        raise ScriptError(f"cannot read PDF: {e}") from e
    try:
        page_count = len(pdf)
        images = []
        for n in _pages(payload, page_count):
            page = pdf[n - 1]
            try:
                w_pt, h_pt = page.get_size()
                scale = min(width / max(w_pt, 1.0), MAX_SIDE / max(h_pt, 1.0))
                bitmap = page.render(scale=scale, rev_byteorder=True)  # opaque white fill -> RGB
                try:
                    png = encode_png(bitmap.width, bitmap.height, bitmap.stride, bitmap.n_channels,
                                     bytes(bitmap.buffer))
                finally:
                    bitmap.close()
            finally:
                page.close()
            out_rel = f"{base}-p{n}.png"
            (root / out_rel).write_bytes(png)
            images.append({"n": n, "path": out_rel})
    finally:
        pdf.close()
    return {"images": images, "page_count": page_count}


def main() -> None:
    run_cli(pdf_render)


if __name__ == "__main__":
    main()
