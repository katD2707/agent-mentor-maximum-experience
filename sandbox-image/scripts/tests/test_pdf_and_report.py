from pathlib import Path

import pytest
from mentor_schemas.reports import AI_DISCLAIMER
from mentor_scripts.check_report import MAX_BODY_CHARS, check_report, check_text
from mentor_scripts.common import ScriptError
from mentor_scripts.pdf_extract import pdf_extract
from mentor_scripts.pdf_render import pdf_render


def make_pdf(pages: list[str]) -> bytes:
    """Minimal valid PDF with one line of Helvetica text per page (ASCII only)."""
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def pdf_path(workspace: Path) -> str:
    (workspace / "inbox").mkdir()
    (workspace / "inbox/paper.pdf").write_bytes(make_pdf(["Hello page one", "Second page text", "Third"]))
    return "inbox/paper.pdf"


def test_pdf_extract_pages(workspace: Path, pdf_path: str) -> None:
    out = pdf_extract({"path": pdf_path}, workspace)
    assert out["page_count"] == 3 and out["truncated"] is False
    assert [p["n"] for p in out["pages"]] == [1, 2, 3]
    assert "Hello page one" in out["pages"][0]["text"]
    assert "Second page text" in out["pages"][1]["text"]


def test_pdf_extract_caps_chars(workspace: Path, pdf_path: str) -> None:
    out = pdf_extract({"path": pdf_path, "max_chars": 20}, workspace)
    assert out["truncated"] is True
    assert sum(len(p["text"]) for p in out["pages"]) == 20
    assert len(out["pages"]) == 2


def test_pdf_extract_rejects_bad_paths(workspace: Path, pdf_path: str) -> None:
    for bad in ("../secret.pdf", "/etc/passwd", "C:/Windows/win.ini", "inbox/missing.pdf", ""):
        with pytest.raises(ScriptError):
            pdf_extract({"path": bad}, workspace)
    (workspace / "inbox/not.pdf").write_text("plain text", encoding="utf-8")
    with pytest.raises(ScriptError):
        pdf_extract({"path": "inbox/not.pdf"}, workspace)


def test_pdf_extract_page_range(workspace: Path, pdf_path: str) -> None:
    out = pdf_extract({"path": pdf_path, "start_page": 2, "end_page": 3}, workspace)
    assert [p["n"] for p in out["pages"]] == [2, 3] and out["page_count"] == 3 and out["truncated"] is False
    assert "Second page text" in out["pages"][0]["text"]
    assert [p["n"] for p in pdf_extract({"path": pdf_path, "start_page": 3, "end_page": 99}, workspace)["pages"]] == [3]
    for bad in ({"start_page": 4}, {"start_page": 0}, {"end_page": "2"}):
        with pytest.raises(ScriptError):
            pdf_extract({"path": pdf_path, **bad}, workspace)


def _blank_pdf(workspace: Path, rel: str, pages: int) -> str:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(612, 792)
    (workspace / rel).parent.mkdir(parents=True, exist_ok=True)
    with open(workspace / rel, "wb") as f:
        writer.write(f)
    return rel


def test_pdf_render_pages_next_to_the_pdf(workspace: Path) -> None:
    import struct
    import zlib

    rel = _blank_pdf(workspace, "inbox/web/scan.pdf", 4)
    out = pdf_render({"path": rel}, workspace)
    assert out == {"page_count": 4, "images": [{"n": n, "path": f"inbox/web/scan-p{n}.png"} for n in (1, 2, 3)]}
    png = (workspace / "inbox/web/scan-p1.png").read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (1400, 1812)
    idat_len = struct.unpack(">I", png[33:37])[0]
    assert len(zlib.decompress(png[41:41 + idat_len])) == height * (1 + width * 3)  # well-formed RGB rows
    assert pdf_render({"path": rel, "pages": [4], "width": 400}, workspace)["images"] == [
        {"n": 4, "path": "inbox/web/scan-p4.png"}]


@pytest.mark.parametrize(("payload", "needle"), [
    ({"pages": [5]}, "out of range"),
    ({"pages": [1, 2, 3, 4, 5, 6]}, "at most 5"),
    ({"pages": []}, "non-empty"),
    ({"width": 5000}, "width"),
    ({"path": ".mentor/x.pdf"}, "writable"),
    ({"path": "inbox/missing.pdf"}, "not found"),
    ({"path": "../x.pdf"}, "relative"),
])
def test_pdf_render_rejects(workspace: Path, payload: dict, needle: str) -> None:
    _blank_pdf(workspace, "inbox/a.pdf", 2)
    _blank_pdf(workspace, ".mentor/x.pdf", 1)
    with pytest.raises(ScriptError, match=needle):
        pdf_render({"path": "inbox/a.pdf", **payload}, workspace)


def test_cli_pdf_extract(run_cli, pdf_path: str) -> None:
    code, out = run_cli("pdf_extract", {"path": pdf_path})
    assert code == 0 and len(out["pages"]) == 3
    code, out = run_cli("pdf_extract", {"path": "../x.pdf"})
    assert code == 1 and "error" in out


GOOD_BODY = f"""## Tiến độ mục tiêu
Con đã hoàn thành 4 trong 5 buổi ôn tập theo kế hoạch hai tuần qua.

## Xu hướng theo chủ đề
- Phương trình bậc hai: tiến bộ rõ, làm độc lập ổn định hơn.
- Hình học: cần thêm thời gian luyện tập.

{AI_DISCLAIMER}
"""


def report(body: str = GOOD_BODY, start: str = "2026-10-24", end: str = "2026-11-06") -> str:
    return f"---\nperiod_start: {start}\nperiod_end: {end}\nincludes_wellbeing_nudge: false\n---\n{body}"


def test_clean_report_passes() -> None:
    assert check_text(report()) == []


def test_italic_disclaimer_is_accepted() -> None:
    assert check_text(report(GOOD_BODY.replace(AI_DISCLAIMER, f"*{AI_DISCLAIMER}*"))) == []


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        (GOOD_BODY + "\nBài kiểm tra 15 phút được 5/10.", "điểm số của từng bài"),
        (GOOD_BODY + "\nBài kiểm tra được 7,5 / 10.", "điểm số của từng bài"),
        (GOOD_BODY + "\nCon nói: “con mệt lắm”.", "ngoặc kép"),
        (GOOD_BODY + '\nCon bảo "không thích học".', "ngoặc kép"),
        (GOOD_BODY + "\nĐiểm: 6 môn Toán.", "điểm số cụ thể"),
        (GOOD_BODY + "\nEm tâm sự rằng gần đây khó ngủ.", "lời học sinh"),
        (GOOD_BODY.replace(AI_DISCLAIMER, ""), "Thiếu dòng miễn trừ"),
        (GOOD_BODY + "\nLiên hệ cô giáo: co.lan@truong.edu.vn", "email"),
        (GOOD_BODY + "\nGọi 0912 345 678 nếu cần.", "số điện thoại"),
        (GOOD_BODY + "\nXem thêm me/journal/2026-10-28.md", "riêng tư"),
        (GOOD_BODY + "x" * MAX_BODY_CHARS, "quá dài"),
    ],
)
def test_report_violations(body: str, needle: str) -> None:
    violations = check_text(report(body))
    assert violations, body
    assert any(needle.lower() in v.lower() for v in violations), violations


def test_report_period_order_and_frontmatter() -> None:
    assert any("period_end" in v for v in check_text(report(start="2026-11-06", end="2026-10-24")))
    assert check_text(GOOD_BODY)[0].startswith("Thiếu hoặc sai phần frontmatter")
    assert check_text("---\nperiod_start: hôm qua\n---\nabc")[0].startswith("Thiếu hoặc sai")


def test_check_report_file_and_cli(workspace: Path, run_cli) -> None:
    (workspace / "reports").mkdir()
    (workspace / "reports/2026-11-07.md").write_text(report(GOOD_BODY + "\nĐược 5/10."), encoding="utf-8")
    out = check_report({"path": "reports/2026-11-07.md"}, workspace)
    assert out["ok"] is False and len(out["violations"]) == 1

    code, out = run_cli("check_report", {"path": "reports/2026-11-07.md"})
    assert code == 0 and out["ok"] is False and "5/10" in out["violations"][0]
    code, out = run_cli("check_report", {"path": "reports/missing.md"})
    assert code == 1
