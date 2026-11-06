from email.message import EmailMessage
from email.policy import SMTP

from email_fakes import DOMAIN, vietnamese_html_email
from mentor_email_ingest import decode_bytes, html_to_text, parse_message


def test_parse_vietnamese_subject_html_body_and_attachment() -> None:
    raw = vietnamese_html_email()
    assert b"=?utf-8?" in raw  # the subject really is RFC 2047 encoded on the wire
    parsed = parse_message(raw)
    assert parsed.subject == "Fwd: Lịch bảo vệ luận văn tháng 11"
    assert parsed.from_addr == "nam@hust.edu.vn" and parsed.from_name == "Thầy Nam"
    assert parsed.to_addrs == [f"abc123@{DOMAIN}"]
    assert parsed.date is not None and parsed.date.isoformat() == "2026-10-27T09:15:00+07:00"
    assert parsed.message_id == "<abc@hust.edu.vn>"
    assert parsed.text == (
        "Chào em,\n\nLịch bảo vệ: ngày 15/11, phòng 301.\n\n- Nộp bản nháp\n"
        '- Xem chi tiết (https://hust.edu.vn/lich)\n\n"Thân" & chúc em thành công'
    )
    assert parsed.attachments == [("Đề cương luận văn.pdf", "application/pdf", b"%PDF-1.4 fake")]


def test_plain_preferred_over_html_in_alternative() -> None:
    msg = EmailMessage()
    msg["From"] = "a@b.vn"
    msg["To"] = f"x@{DOMAIN}"
    msg["Subject"] = "Hi"
    msg.set_content("Bản văn thuần")
    msg.add_alternative("<p>Bản HTML</p>", subtype="html")
    assert parse_message(msg.as_bytes(policy=SMTP)).text == "Bản văn thuần"


def test_windows_1258_and_mislabelled_charsets() -> None:
    body = "Thầy giáo".encode("cp1258")
    raw = (
        b"From: a@b.vn\r\nTo: x@inbox.mentor.local\r\nSubject: =?windows-1258?Q?Th=E2=CCy?=\r\n"
        b"MIME-Version: 1.0\r\nContent-Type: text/plain; charset=windows-1258\r\n"
        b"Content-Transfer-Encoding: 8bit\r\n\r\n" + body
    )
    parsed = parse_message(raw)
    assert parsed.text == "Thầy giáo"  # combining tone mark composed (NFC)
    assert parsed.subject == "Thầy"
    assert decode_bytes("Lịch học".encode(), "us-ascii") == "Lịch học"  # utf-8 labelled as ascii
    assert decode_bytes("Lịch học".encode(), "x-unknown-charset") == "Lịch học"


def test_forwarded_message_attachment_is_inlined() -> None:
    inner = EmailMessage()
    inner["From"] = "Phòng Đào tạo <pdt@hust.edu.vn>"
    inner["To"] = "sv@gmail.com"
    inner["Subject"] = "Hạn nộp hồ sơ"
    inner.set_content("Hạn nộp: 30/11.")
    inner.add_attachment(b"a,b\n1,2\n", maintype="text", subtype="csv", filename="danh-sach.csv")
    outer = EmailMessage()
    outer["From"] = "sv@gmail.com"
    outer["To"] = f"abc123@{DOMAIN}"
    outer["Subject"] = "Fwd: Hạn nộp hồ sơ"
    outer.set_content("Xem thư dưới.")
    outer.add_attachment(inner)
    parsed = parse_message(outer.as_bytes(policy=SMTP))
    assert parsed.text.startswith("Xem thư dưới.")
    assert "Từ / From: Phòng Đào tạo <pdt@hust.edu.vn>" in parsed.text and "Hạn nộp: 30/11." in parsed.text
    assert [(n, m) for n, m, _ in parsed.attachments] == [("danh-sach.csv", "text/csv")]


def test_html_to_text_skips_scripts_and_keeps_breaks() -> None:
    assert html_to_text("<div>a<br>b<script>x()</script></div><table><tr><td>1</td><td>2</td></tr></table>") == (
        "a\nb\n\n1 2"
    )
