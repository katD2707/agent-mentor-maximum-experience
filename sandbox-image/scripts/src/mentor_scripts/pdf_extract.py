"""pdf_extract: text of a workspace PDF, page by page.

Input: {path, max_chars?: 200000, start_page?: 1, end_page?: last}. Output: {pages: [{n, text}], page_count,
truncated}. Pages are numbered from 1; `start_page`/`end_page` (inclusive) read only part of a long PDF.
Extraction stops once max_chars characters have been collected; the last page is cut and `truncated` is true
(also when the range was not read to its end). Scanned PDFs yield empty text (no OCR here; pdf_render makes
page images for look_at_image).
"""

from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from mentor_scripts.common import ScriptError, resolve_in_workspace, run_cli

DEFAULT_MAX_CHARS = 200_000
HARD_MAX_CHARS = 1_000_000


def pdf_extract(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    path = resolve_in_workspace(root, payload.get("path", ""))
    max_chars = payload.get("max_chars", DEFAULT_MAX_CHARS)
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or not 1 <= max_chars <= HARD_MAX_CHARS:
        raise ScriptError(f"max_chars must be an integer between 1 and {HARD_MAX_CHARS}")
    start, end = payload.get("start_page"), payload.get("end_page")
    for name, value in (("start_page", start), ("end_page", end)):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 1):
            raise ScriptError(f"{name} must be a page number (from 1)")
    start = 1 if start is None else start
    if not path.is_file():
        raise ScriptError(f"file not found: {payload.get('path')}")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ScriptError("PDF is password-protected")
        page_count = len(reader.pages)
        last = min(end or page_count, page_count)
        if page_count and start > page_count:
            raise ScriptError(f"start_page {start} is past the last page ({page_count})")
        pages: list[dict[str, Any]] = []
        total = 0
        truncated = False
        for i in range(start, last + 1):
            page = reader.pages[i - 1]
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 - one broken page should not lose the rest
                text = ""
            room = max_chars - total
            if len(text) > room:
                text, truncated = text[:room], True
            pages.append({"n": i, "text": text})
            total += len(text)
            if truncated:
                break
    except (PdfReadError, ValueError, OSError) as e:
        raise ScriptError(f"cannot read PDF: {e}") from e
    wanted = max(last - start + 1, 0)
    return {"pages": pages, "page_count": page_count, "truncated": truncated or len(pages) < wanted}


def main() -> None:
    run_cli(pdf_extract)


if __name__ == "__main__":
    main()
