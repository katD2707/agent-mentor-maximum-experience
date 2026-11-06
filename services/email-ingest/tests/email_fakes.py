from datetime import UTC, datetime
from email.message import EmailMessage
from email.policy import SMTP

from mentor_schemas.sandbox_api import JobRequest

DOMAIN = "inbox.mentor.local"
FIXED_NOW = datetime(2026, 10, 28, 18, 30, tzinfo=UTC)  # 2026-10-29 01:30 in Asia/Ho_Chi_Minh


class FakeUsers:
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping
        self.lookups: list[str] = []

    def user_id_for_inbound_address(self, address: str) -> str | None:
        self.lookups.append(address)
        return self.mapping.get(address)


class MemoryWriter:
    """WorkspaceWriter that refuses to overwrite, like the gateway should."""

    def __init__(self) -> None:
        self.files: dict[tuple[str, str], bytes] = {}

    def write_inbox_file(self, user_id: str, relative_name: str, data: bytes) -> str:
        key = (user_id, relative_name)
        if key in self.files:
            raise FileExistsError(relative_name)
        self.files[key] = data
        return f"inbox/{relative_name}"

    def text(self, user_id: str, relative_name: str) -> str:
        return self.files[(user_id, relative_name)].decode("utf-8")


class ListQueue:
    def __init__(self) -> None:
        self.jobs: list[JobRequest] = []

    def enqueue(self, job: JobRequest) -> None:
        self.jobs.append(job)


def vietnamese_html_email(to: str = f"abc123@{DOMAIN}") -> bytes:
    msg = EmailMessage()
    msg["From"] = "Thầy Nam <nam@hust.edu.vn>"
    msg["To"] = to
    msg["Subject"] = "Fwd: Lịch bảo vệ luận văn tháng 11"
    msg["Date"] = "Tue, 27 Oct 2026 09:15:00 +0700"
    msg["Message-ID"] = "<abc@hust.edu.vn>"
    msg.set_content(
        "<html><head><style>p{color:red}</style><script>alert(1)</script></head><body>"
        "<p>Chào em,</p><p>Lịch bảo vệ: <b>ngày 15/11</b>,\n phòng 301.</p>"
        "<ul><li>Nộp bản nháp</li><li>Xem <a href='https://hust.edu.vn/lich'>chi tiết</a></li></ul>"
        "<p>&quot;Thân&quot; &amp; chúc em thành công</p></body></html>",
        subtype="html",
    )
    msg.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="Đề cương luận văn.pdf")
    return msg.as_bytes(policy=SMTP)
