"""PDF / DOCX / PPTX extraction. Docling (MIT) for structure -> Markdown; pypdfium2 for page rendering.

Docling is imported lazily (it pulls torch); its OCR is disabled because scanned pages are rendered to images and go
through the vision-model check instead (one OCR path, with quality judgement).
"""

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium

log = logging.getLogger("mentor_course_builder")


def _converter(do_ocr: bool = False):  # type: ignore[no-untyped-def]
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = do_ocr
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def docling_pages(path: Path) -> dict[int, str]:
    """{page_no: markdown} for a PDF/PPTX/DOCX; a format without pages comes back as {1: whole document}."""
    doc = _converter().convert(str(path)).document
    page_nos = sorted(doc.pages.keys()) if getattr(doc, "pages", None) else []
    if not page_nos:
        return {1: doc.export_to_markdown()}
    return {n: doc.export_to_markdown(page_no=n) for n in page_nos}


def pdf_text_chars(path: Path) -> list[int]:
    """Characters in the text layer of each page (0 = scanned/image-only page)."""
    pdf = pdfium.PdfDocument(str(path))
    try:
        counts = []
        for i in range(len(pdf)):
            tp = pdf[i].get_textpage()
            counts.append(len((tp.get_text_range() or "").strip()))
            tp.close()
        return counts
    finally:
        pdf.close()


def plain_pdf_text(path: Path, pages: list[int]) -> dict[int, str]:
    """Fallback when Docling is unavailable: raw text layer."""
    pdf = pdfium.PdfDocument(str(path))
    try:
        return {p: pdf[p - 1].get_textpage().get_text_range() for p in pages}
    finally:
        pdf.close()


def render_pdf_pages(path: Path, out_dir: Path, pages: list[int], dpi: int = 150, prefix: str = "page") -> dict[int, Path]:
    """Render 1-based `pages` to JPEG (pypdfium2 ships PDFium: no system libraries)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(path))
    out: dict[int, Path] = {}
    try:
        for n in pages:
            img = pdf[n - 1].render(scale=dpi / 72).to_pil().convert("RGB")
            p = out_dir / f"{prefix}_{n:04d}.jpg"
            img.save(p, "JPEG", quality=90)
            out[n] = p
    finally:
        pdf.close()
    return out


def split_markdown(md: str, max_chars: int = 6000) -> list[str]:
    """DOCX has no pages: split at level 1-2 headings, then at paragraph boundaries above `max_chars`."""
    parts = re.split(r"(?m)^(?=#{1,2} )", md)
    out: list[str] = []
    for part in (p for p in parts if p.strip()):
        while len(part) > max_chars:
            cut = part.rfind("\n\n", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            out.append(part[:cut].strip())
            part = part[cut:]
        if part.strip():
            out.append(part.strip())
    return out or [md.strip()]


def find_soffice() -> str | None:
    cand = os.environ.get("SOFFICE_BIN")
    if cand and Path(cand).is_file():
        return cand
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for p in ("C:/Program Files/LibreOffice/program/soffice.exe", "C:/Program Files (x86)/LibreOffice/program/soffice.exe"):
        if Path(p).is_file():
            return p
    return None


def render_slides(pptx: Path, out_dir: Path, dpi: int = 110) -> dict[int, Path]:
    """Optional slide images via LibreOffice -> PDF -> pypdfium2. {} when LibreOffice is not installed."""
    soffice = find_soffice()
    if not soffice:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(pptx)],
                           capture_output=True, timeout=300)
        pdf = Path(tmp) / (pptx.stem + ".pdf")
        if r.returncode != 0 or not pdf.is_file():
            log.warning("LibreOffice slide render failed for %s", pptx.name)
            return {}
        n = len(pdfium.PdfDocument(str(pdf)))
        return render_pdf_pages(pdf, out_dir, list(range(1, n + 1)), dpi=dpi, prefix="slide")
