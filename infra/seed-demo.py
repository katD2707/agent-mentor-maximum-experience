"""Seed two lived-in DEMO learner accounts into the DEV stack, through the gateway API only.

    uv run python infra/seed-demo.py [--base http://127.0.0.1:8000] [--reset] [--no-chat] [--only thpt|ncs]
    uv run python infra/seed-demo.py --login demo.thpt@example.com      # print a fresh dev login link + code
    uv run python infra/seed-demo.py --delete                           # delete both demo accounts

Accounts (all people, schools and events are made up; emails are @example.com):
- demo.thpt@example.com  "Nguyễn Minh Anh", lớp 11, profile THPT, parent dev-verified
- demo.ncs@example.com   "Trần Thu Lan", NCS năm 2 (NLP), profile NCS

Dev only: refuses unless `POST /auth/request-link` answers with a `dev_link` (MENTOR_ENV=dev). Everything goes
through the same endpoints the web app uses (dev magic link, /onboarding, /dev/parent-link/verify, PUT
/workspace/file, POST /uploads) plus the inbound email endpoint the mail transport uses
(/internal/email/inbound, open in dev with the local sandbox backend, or pass --internal-token). Nothing is
written into the data dir directly, so the mirror, git history and encryption stay consistent.

Dates are relative to today (Asia/Ho_Chi_Minh), so the data always looks like the last 3-4 weeks.

Known limits (no API for them): events.jsonl cannot be written, so learning/math/skills.md and review-queue.md
are rendered here with the real bkt_update code from synthetic events, but the next bkt_update run in the sandbox
recomputes them from the real (empty) event log; seeded files show author "user" and today's commit time in
the history; chat history only exists for the real chat turns this script runs.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parents[1]
VN = ZoneInfo("Asia/Ho_Chi_Minh")
WEB_ORIGIN_DEFAULT = "http://localhost:3000"
THPT_EMAIL = "demo.thpt@example.com"
NCS_EMAIL = "demo.ncs@example.com"
# Optional photo of a graded quiz for the THPT demo; skipped when absent (pass --quiz PATH to use your own).
QUIZ_PNG_DEFAULT = ROOT / "infra" / "demo-quiz.png"

THPT_CHAT = [
    "Mai em kiểm tra 15 phút Toán, ôn gì bây giờ ạ?",
    "Mentor ơi, bố mẹ em hỏi tình hình học của em. Mentor soạn và gửi báo cáo định kỳ 2 tuần cho bố mẹ em luôn nhé.",
]
NCS_CHAT = ["Tuần này mình nên ưu tiên gì?"]

# ---- dates ---------------------------------------------------------------------------------------

TODAY = datetime.now(VN).date()
WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]
WD_SHORT = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def d(k: int) -> date:
    return TODAY + timedelta(days=k)


def iso(k: int) -> str:
    return d(k).isoformat()


def dm(k: int) -> str:
    x = d(k)
    return f"{x.day}/{x.month}"


def wd(k: int) -> str:
    return WEEKDAYS[d(k).weekday()]


def wds(k: int) -> str:
    return WD_SHORT[d(k).weekday()]


def next_weekday(weekday: int, min_days: int) -> int:
    """Offset of the first `weekday` (0 = Monday) at least `min_days` from today."""
    k = min_days
    while d(k).weekday() != weekday:
        k += 1
    return k


def en_date(k: int) -> str:
    x = d(k)
    return x.strftime("%B ") + str(x.day) + x.strftime(", %Y")


MONDAY = -TODAY.weekday()  # offset of this week's Monday


# ---- HTTP helpers --------------------------------------------------------------------------------


class SeedError(RuntimeError):
    pass


def check(r: httpx.Response, what: str) -> httpx.Response:
    if r.status_code >= 400:
        raise SeedError(f"{what}: HTTP {r.status_code} {r.text[:300]}")
    return r


def rebase(link: str, base: str) -> str:
    """The dev link points at PUBLIC_BASE_URL; call the gateway at --base instead."""
    lk, b = urlsplit(link), urlsplit(base)
    return urlunsplit((b.scheme, b.netloc, lk.path, lk.query, ""))


def request_link(c: httpx.Client, email: str) -> dict:
    r = c.post("/auth/request-link", json={"email": email})
    if r.status_code == 429:
        raise SeedError(f"request-link {email}: rate limited (5 per hour per email). Try again later.")
    data = check(r, f"request-link {email}").json()
    if not data.get("dev_link"):
        raise SeedError("The gateway did not return dev_link: it is not in dev mode (MENTOR_ENV=dev). Refusing to seed.")
    return data


def login(base: str, web_origin: str, email: str) -> httpx.Client:
    c = httpx.Client(base_url=base.rstrip("/") + "/api", headers={"Origin": web_origin}, timeout=120)
    link = request_link(c, email)["dev_link"]
    r = c.get(rebase(link, base), follow_redirects=False)
    if r.status_code != 302 or "mentor_session" not in c.cookies:
        raise SeedError(f"verify {email}: HTTP {r.status_code} {r.text[:200]}")
    return c


class Workspace:
    def __init__(self, c: httpx.Client) -> None:
        self.c = c
        self.written: list[str] = []

    def put(self, path: str, content: str) -> None:
        r = self.c.get("/workspace/file", params={"path": path})
        base_sha = r.json().get("sha") if r.status_code == 200 else None
        if r.status_code not in (200, 404):
            check(r, f"read {path}")
        check(self.c.put("/workspace/file", json={"path": path, "content": content, "base_sha": base_sha}),
              f"write {path}")
        self.written.append(path)

    def upload(self, name: str, data: bytes, mime: str) -> str:
        r = check(self.c.post("/uploads", files={"file": (name, data, mime)}), f"upload {name}")
        return r.json()["path"]


# ---- learning/math from synthetic events, rendered by the real bkt_update code ---------------------

EVIDENCE_K = -14  # earlier graded 15-minute test (dấu tam thức), private evidence file
EVIDENCE_PATH = f"learning/evidence/{iso(EVIDENCE_K)}-kiem-tra-15p.md"

# (day offset, skill_id, correct, mode, hint_count)
THPT_EVENTS = [
    (-22, "algebra.radicals.basic", True, "independent", 0),
    (-21, "algebra.quadratic.formula", True, "independent", 0),
    (-20, "functions.quadratic.vertex", True, "independent", 0),
    (-19, "algebra.quadratic.formula", False, "independent", 0),
    (-18, "algebra.quadratic.vieta", True, "independent", 0),
    (-14, "algebra.quadratic.formula", True, "classroom_graded", 0),
    (-14, "algebra.quadratic.trinomial_sign", True, "classroom_graded", 0),
    (-14, "algebra.quadratic.trinomial_sign", False, "classroom_graded", 0),
    (-14, "algebra.quadratic.inequality", False, "classroom_graded", 0),
    (-13, "functions.quadratic.vertex", True, "independent", 0),
    (-12, "algebra.quadratic.formula", True, "independent", 0),
    (-11, "algebra.quadratic.vieta", True, "independent", 0),
    (-10, "algebra.quadratic.trinomial_sign", True, "independent", 0),
    (-9, "algebra.quadratic.inequality", False, "independent", 0),
    (-8, "functions.quadratic.vertex", True, "independent", 0),
    (-8, "algebra.radicals.basic", True, "independent", 0),
    (-7, "algebra.quadratic.formula", False, "independent", 0),
    (-6, "algebra.quadratic.trinomial_sign", True, "independent", 0),
    (-6, "algebra.quadratic.inequality", True, "guided", 2),
    (-5, "algebra.quadratic.formula", True, "independent", 0),
    (-4, "algebra.quadratic.vieta", True, "independent", 0),
    (-3, "algebra.quadratic.formula", True, "guided", 1),
    (-2, "algebra.quadratic.inequality", True, "independent", 0),
]


def render_math_files() -> tuple[str, str] | None:
    """skills.md and review-queue.md exactly as bkt_update would write them for THPT_EVENTS."""
    try:
        import yaml
        from mentor_schemas import LearningEvent
        from mentor_scripts.bkt_update import (
            CurriculumSkill,
            _params,
            compute_states,
            render_review_md,
            render_skills_md,
        )
    except ImportError as exc:
        print(f"  ! bkt_update not importable ({exc}); learning/math/skills.md left as the template")
        return None
    data = yaml.safe_load((ROOT / "mentor-content" / "curricula" / "math.yaml").read_text(encoding="utf-8"))
    curriculum = {
        str(s["id"]): CurriculumSkill(id=str(s["id"]), title=str(s.get("title") or ""),
                                      prerequisites=[str(p) for p in s.get("prerequisites") or []],
                                      params=_params(s.get("bkt")))
        for s in data.get("skills") or [] if isinstance(s, dict) and s.get("id")
    }
    events = []
    for i, (k, sid, correct, mode, hints) in enumerate(THPT_EVENTS):
        ts = datetime.combine(d(k), datetime.min.time(), VN).replace(hour=20, minute=10 + i % 40)
        events.append(LearningEvent(
            event_id=f"demo-{i:03d}", ts=ts, type="graded_work_ingested" if mode == "classroom_graded" else "problem_attempt",
            subject="math", skill_ids=[sid], correct=correct, mode=mode, hint_count=hints,
            source_ref=EVIDENCE_PATH if mode == "classroom_graded" else f"sessions/{iso(k)}",
            grader="teacher" if mode == "classroom_graded" else "sympy",
        ))
    states = compute_states(events, curriculum)
    review, _ = render_review_md("math", TODAY, states, curriculum)
    return render_skills_md("math", TODAY, states, curriculum), review


# ---- THPT content --------------------------------------------------------------------------------

MEMO = "<!-- Mỗi dòng: một ý ngắn + (nguồn ngày), ví dụ: - Học lớp 10A1. (chat 28/10). Điều mentor tự đoán bắt đầu bằng [suy luận]. Người học xem và sửa được file này trên web. -->"


def thpt_files() -> dict[str, str]:
    k_exam = next_weekday(0, 40)  # Monday of the end-of-term exam week, ~6 weeks out
    files: dict[str, str] = {}
    files["me/profile.md"] = f"""# Hồ sơ — cập nhật {iso(-3)}
{MEMO}
- Profile: thpt

## Cơ bản
- Tên gọi Minh Anh (Nguyễn Minh Anh), học lớp 11A2. (chat {dm(-26)})
- Học theo tổ hợp Toán, Lý, Hóa. (chat {dm(-26)})

## Môn học
- Mạnh: Hóa và Tiếng Anh. (chat {dm(-25)})
- Cần cố gắng: Toán, nhất là phương trình và bất phương trình bậc hai, phần lớp 11 dùng lại nhiều trong lượng giác. (chat {dm(-25)})
- Đang học cùng mentor: Toán (lượng giác lớp 11, củng cố đại số bậc hai lớp 10). (chat {dm(-24)})

## Mục tiêu dài hạn
- Muốn thi khối A00, nhắm ngành Kỹ thuật hóa học. (chat {dm(-25)})
- [suy luận] Toán là môn kéo điểm khối A00 xuống nên là ưu tiên năm nay. (chat {dm(-25)}, độ chắc: vừa)

## Hoàn cảnh học tập
- Học thêm Toán ở trung tâm tối thứ Hai và thứ Năm. (chat {dm(-24)})
- Học bằng laptop ở nhà, chụp bài làm bằng điện thoại. (chat {dm(-20)})
"""
    files["me/now.md"] = f"""# Tình hình hiện tại — cập nhật {iso(-1)}
{MEMO}
<!-- Chỉ giữ việc đang diễn ra. Việc đã qua: xóa hoặc để nightly-reflection chuyển sang journal. -->

## Tuần này
- Kiểm tra 15 phút Toán {wd(1)} {dm(1)}: phương trình lượng giác quy về bậc hai. (chat {dm(-1)})
- Cô Hạnh vừa trả bài kiểm tra 15 phút ôn kiến thức lớp 10 (phương trình bậc hai); em định chụp gửi mentor xem. (chat {dm(-1)})
- Tập văn nghệ cho lớp chuẩn bị 20/11, tối thứ Ba và thứ Năm về muộn. (chat {dm(-4)})

## Áp lực và năng lượng
- Tuần này có 3 bài kiểm tra: Toán, Hóa, Anh. (chat {dm(-2)})
- [suy luận] Hơi lo về Toán sau bài 15 phút vừa trả; nên mở đầu buổi ôn bằng bài dễ. (chat {dm(-1)}, độ chắc: vừa)

## Đã xong gần đây
- Ôn xong công thức nghiệm và định lí Vi-ét theo kế hoạch. (events {dm(-4)})
"""
    files["me/preferences.md"] = f"""# Sở thích và cách làm việc — cập nhật {iso(-15)}
{MEMO}

## Ngôn ngữ và xưng hô
- Ngôn ngữ: tiếng Việt
- Mentor xưng: mình
- Gọi người học: em

## Cách giải thích hiệu quả
- Thích ví dụ số cụ thể trước rồi mới tới công thức tổng quát. (chat {dm(-22)})
- Muốn câu trả lời ngắn, chia bước có đánh số. (chat {dm(-20)})

## Giờ học và nhịp sinh hoạt
- Học tối 20:00-22:00; tối thứ Hai và thứ Năm đi học thêm đến 19:30. (chat {dm(-24)})
- Cuối tuần học buổi sáng tốt hơn buổi tối. (chat {dm(-17)})

## Giọng điệu
- Thích được chỉ thẳng chỗ sai, không cần khen nhiều. (chat {dm(-15)})
"""
    files["me/people.md"] = f"""# Những người liên quan — cập nhật {iso(-17)}
{MEMO}
<!-- Chỉ ghi tối thiểu: tên gọi + vai trò + điều liên quan đến việc học. Không ghi chuyện riêng, sức khỏe hay nhận xét cá nhân về người khác. -->

## Trong việc học
- Cô Hạnh: dạy Toán lớp 11A2, hay kiểm tra 15 phút đầu giờ. (chat {dm(-24)})
- Thầy Quang: giáo viên chủ nhiệm, dạy Hóa. (chat {dm(-24)})
- Khánh: bạn cùng lớp, học nhóm Toán sáng thứ Bảy. (chat {dm(-17)})
- Mẹ: nhận báo cáo học tập 2 tuần một lần qua Zalo. (chat {dm(-26)})
"""
    files["me/what-works.md"] = f"""# Cách hỗ trợ hiệu quả — cập nhật {iso(-6)}
{MEMO}

## Hiệu quả
- Bắt đầu bằng 1 bài dễ giúp vào nhịp nhanh hơn. (chat {dm(-21)})
- Viết riêng -b ra nháp trước khi thay vào công thức nghiệm giúp bớt nhầm dấu. (chat {dm(-12)})
- Học 25 phút rồi nghỉ 5 phút giữ được tập trung cả buổi. (chat {dm(-9)})

## Không hiệu quả
- Xem lời giải mẫu ngay khi bí làm em chép lại mà không hiểu; nên gợi ý từng bước. (chat {dm(-18)})
- [suy luận] Sau 21:30 hay sai bài dễ; nên dồn bài khó trước 21:00. (chat {dm(-6)}, độ chắc: vừa)
"""
    journals = {
        -24: ("Buổi đầu với mentor: kể về lớp 11A2, mục tiêu khối A00. (chat {a})",
              "Tự làm đúng 1 bài căn thức không cần gợi ý. (events {b})",
              "Chưa có thói quen học Toán đều mỗi tối. (chat {a})",
              "[suy luận] Cần mục tiêu nhỏ, đo được theo tuần. (chat {a}, độ chắc: vừa)"),
        -19: ("Ôn công thức nghiệm phương trình bậc hai 40 phút, làm 6 bài. (chat {a})",
              "Tìm đỉnh parabol đúng cả 3 bài. (events {b})",
              "Nhầm dấu -b ở 2 bài khi b dương. (events {a})",
              "Nhắc viết -b ra nháp trước khi thay số. (chat {a})"),
        -14: ("Cô Hạnh trả bài kiểm tra 15 phút dấu tam thức bậc hai; em gửi ảnh cho mentor xem. (ảnh bài kiểm tra {a})",
              "Câu xét dấu tam thức có a > 0 làm đúng. (ảnh bài kiểm tra {a})",
              "Bất phương trình bậc hai lấy nhầm khoảng nghiệm. (ảnh bài kiểm tra {a})",
              "Tuần sau ưu tiên bất phương trình bậc hai. (chat {a})"),
        -9: ("Ôn bất phương trình bậc hai 30 phút. (chat {a})",
             "Xét dấu tam thức đúng 2 bài liên tiếp, kể cả khi a < 0. (events {b})",
             "Vẫn lấy nhầm khoảng nghiệm ở 1 bài. (events {a})",
             "[suy luận] Vẽ trục số trước khi kết luận có thể giúp. (chat {a}, độ chắc: thấp)"),
        -6: ("Ôn Vi-ét và tam thức 45 phút, nghỉ giữa giờ 5 phút. (chat {a})",
             "Bất phương trình bậc hai làm đúng sau 2 gợi ý về trục số. (events {a})",
             "Làm sai 1 bài dễ lúc gần 22:00. (chat {a})",
             "[suy luận] Buổi muộn dễ mất tập trung. (chat {a}, độ chắc: vừa)"),
        -2: ("Bắt đầu phương trình lượng giác quy về bậc hai (đặt t = sin x). (chat {a})",
             "Tự giải đúng bất phương trình bậc hai, không cần gợi ý. (events {a})",
             "Quên điều kiện -1 ≤ t ≤ 1 khi đặt t = sin x. (chat {a})",
             "Mai nhắc lại điều kiện của t trước khi làm bài. (chat {a})"),
    }
    for k, (what, good, hard, note) in journals.items():
        a, b = dm(k), dm(k)
        files[f"me/journal/{iso(k)}.md"] = (
            f"# Nhật ký {iso(k)}\n## Chuyện gì đã xảy ra\n- {what.format(a=a, b=b)}\n"
            f"## Tiến bộ\n- {good.format(a=a, b=b)}\n## Khó khăn\n- {hard.format(a=a, b=b)}\n"
            f"## Ghi chú cho mentor\n- {note.format(a=a, b=b)}\n"
        )
    files["goals/goals.md"] = f"""# Mục tiêu — cập nhật {iso(-2)}
<!-- Người học làm chủ mục tiêu; mentor đề xuất. Mỗi mục tiêu có hạn, lý do và 2-5 mốc có ngày (skill goal-planning). -->

## Đang theo đuổi
### Toán cuối học kỳ I đạt từ 8 điểm — hạn {iso(k_exam)} (nguồn: chat {dm(-24)})
- Vì sao: Toán là môn chính của khối A00, em muốn kéo điểm Toán lên ngang Hóa.
- Mốc:
  - [x] {iso(-12)} — Ôn xong công thức nghiệm và Vi-ét
  - [ ] {iso(4)} — Không nhầm dấu -b trong 10 bài liên tiếp
  - [ ] {iso(15)} — Làm xong 2 đề bất phương trình bậc hai
  - [ ] {iso(28)} — Phương trình lượng giác quy về bậc hai
  - [ ] {iso(k_exam - 6)} — Làm 3 đề thi thử cuối kỳ

### Học Toán đều 5 buổi mỗi tuần — hạn {iso(k_exam)} (nguồn: chat {dm(-21)})
- Vì sao: học dồn trước kiểm tra làm em mệt và hay quên.
- Mốc:
  - [x] {iso(-14)} — Đủ 5 buổi tuần đầu
  - [ ] {iso(MONDAY + 6)} — Đủ 5 buổi tuần này

## Đã đạt
- Thuộc công thức nghiệm và Vi-ét, làm đúng không cần xem lại công thức. (events {dm(-12)})

## Đã dừng
"""
    files["goals/plans/this-week.md"] = f"""# Kế hoạch tuần (từ {iso(MONDAY)})
<!-- Việc cụ thể, có ngày và thời lượng. Mentor sửa kế hoạch khi bị chậm, không lập lại từ đầu (skill goal-planning). -->

## Việc của người học
- [x] {wds(MONDAY)} 20:00 — 30 phút: 5 bài phương trình bậc hai, viết -b ra nháp (mốc {dm(4)})
- [ ] {wds(MONDAY + 1)} 20:00 — 25 phút: 4 bài phương trình lượng giác đặt t = sin x, nhớ điều kiện của t
- [ ] {wds(MONDAY + 2)} 20:00 — 20 phút: xem lại bài kiểm tra 15 phút vừa trả, gửi ảnh cho mentor
- [ ] {wds(MONDAY + 3)} 21:00 — 20 phút: ôn lại 3 lỗi trong learning/math/mistakes.md
- [ ] {wds(MONDAY + 5)} 09:00 — 45 phút: học nhóm với Khánh, 1 đề bất phương trình bậc hai

## Mentor sẽ làm
- Chuẩn bị 5 bài ôn nhanh dấu tam thức cho tối {wds(MONDAY + 3)}.
- Nhắc kiểm tra 15 phút Toán {wds(1)} {dm(1)} vào tối hôm trước.

## Điều chỉnh
- {dm(MONDAY)}: dời buổi học tối T3 và T5 sang 21:00 vì tập văn nghệ. (chat {dm(-4)})
"""
    files["goals/plans/term.md"] = f"""# Kế hoạch dài hạn — cập nhật {iso(-24)}
<!-- Mốc lớn của học kỳ hoặc năm. Mỗi tuần chỉ kéo 1-2 mốc vào this-week.md. -->

## Mốc lớn
- [x] {iso(-12)} — Củng cố đại số bậc hai lớp 10 (công thức nghiệm, Vi-ét)
- [ ] {iso(15)} — Bất phương trình bậc hai, dấu tam thức
- [ ] {iso(28)} — Phương trình lượng giác cơ bản và quy về bậc hai
- [ ] {iso(k_exam)} — Thi cuối học kỳ I

## Ghi chú
- Lớp 11 đang học lượng giác; phần nào cần đại số lớp 10 thì ôn lại trước. (chat {dm(-24)})
"""
    files["learning/math/mistakes.md"] = f"""# Lỗi hay gặp — Toán
<!-- Một dòng một loại lỗi: - [kiến thức] hoặc [cẩu thả] mô tả. skill_id. (nguồn dd/mm) ×số lần
Ví dụ: - [cẩu thả] Nhầm dấu khi tính -b/2a. functions.quadratic.vertex. (ảnh bài kiểm tra 25/10) ×2
Ghi về lỗi, không nhận xét về con người. -->

## Đang gặp
- [cẩu thả] Quên đổi dấu b khi tính (-b ± √Δ)/2a, nhất là khi b dương. algebra.quadratic.formula. (chat {dm(-7)}) ×2
- [cẩu thả] Bất phương trình bậc hai lấy nhầm khoảng trong thành khoảng ngoài hai nghiệm. algebra.quadratic.inequality. (ảnh bài kiểm tra {dm(EVIDENCE_K)}) ×2
- [kiến thức] Đặt t = sin x nhưng quên điều kiện -1 ≤ t ≤ 1. chưa gắn kỹ năng. (chat {dm(-2)}) ×1

## Đã khắc phục
- [kiến thức] Xét dấu tam thức khi a < 0 bị ngược dấu. algebra.quadratic.trinomial_sign. (ảnh bài kiểm tra {dm(EVIDENCE_K)}) ×1, làm đúng 2 lần sau đó (events {dm(-6)})
"""
    files[EVIDENCE_PATH] = f"""# Kiểm tra 15 phút Toán — {iso(EVIDENCE_K)}
- Ảnh gốc: (ảnh gửi trong chat {dm(EVIDENCE_K)}, dữ liệu demo)
- Kết quả chung: 6/10

## Câu 1
- Đề: Giải phương trình x^2 - 7x + 10 = 0
- Kỹ năng: algebra.quadratic.formula
- Giáo viên chấm: đúng
## Câu 2
- Đề: Xét dấu f(x) = x^2 - 5x + 6
- Kỹ năng: algebra.quadratic.trinomial_sign
- Giáo viên chấm: đúng
## Câu 3
- Đề: Xét dấu f(x) = -x^2 + 2x + 3
- Kỹ năng: algebra.quadratic.trinomial_sign
- Giáo viên chấm: sai
- Lỗi: [kiến thức] a < 0 nhưng vẫn ghi dấu như a > 0
## Câu 4
- Đề: Giải bất phương trình x^2 - 3x - 4 ≤ 0
- Kỹ năng: algebra.quadratic.inequality
- Giáo viên chấm: sai
- Lỗi: [cẩu thả] lấy khoảng ngoài hai nghiệm thay vì đoạn [-1; 4]
- Lời phê: Xem lại bảng xét dấu!
"""
    math = render_math_files()
    if math:
        files["learning/math/skills.md"], files["learning/math/review-queue.md"] = math
    return files


# ---- NCS content ---------------------------------------------------------------------------------

K_MEET = next_weekday(3, 7)   # next supervisor meeting: a Thursday at least a week out
K_PREV_MEET = K_MEET - 14      # previous one, two weeks earlier (in the past)
K_ABSTRACT = 30                # VietNLP 2027 (fictional workshop) abstract deadline, AoE
K_FULL = 37                    # full paper deadline, AoE


def aoe_to_vn(k: int) -> str:
    """23:59 AoE (UTC-12) on day k = 18:59 Vietnam time (UTC+7) on day k+1."""
    return f"{iso(k + 1)} 18:59 (giờ VN, = 23:59 AoE ngày {dm(k)})"


def ncs_files() -> dict[str, str]:
    files: dict[str, str] = {}
    files["me/profile.md"] = f"""# Hồ sơ — cập nhật {iso(-20)}
{MEMO}
- Profile: ncs

## Cơ bản
- Tên gọi Lan (Trần Thu Lan), nghiên cứu sinh tiến sĩ năm 2 ngành Khoa học máy tính. (chat {dm(-27)})
- Làm ở lab Xử lý ngôn ngữ tự nhiên của khoa. (chat {dm(-27)})

## Hướng nghiên cứu
- Retrieval-augmented generation (RAG) cho hỏi đáp văn bản pháp luật tiếng Việt; chi tiết ở research/thesis.md. (chat {dm(-27)})

## Mục tiêu dài hạn
- Bảo vệ luận án cấp cơ sở năm 2028, trước đó cần 2 bài hội nghị hoặc hội thảo. (chat {dm(-26)})

## Hoàn cảnh
- Trợ giảng môn NLP nhập môn chiều thứ Tư. (chat {dm(-26)})
- GPU dùng chung với lab, đặt lịch theo tuần vào sáng thứ Hai. (chat {dm(-20)})
"""
    files["me/now.md"] = f"""# Tình hình hiện tại — cập nhật {iso(-1)}
{MEMO}
<!-- Chỉ giữ việc đang diễn ra. Việc đã qua: xóa hoặc để nightly-reflection chuyển sang journal. -->

## Tuần này
- Họp GVHD {wd(K_MEET)} {dm(K_MEET)} 14:00; cần gửi nháp mục 3.1-3.2 trước đó 2 ngày. (chat {dm(-5)})
- Đang chạy fine-tune PhoBERT-DPR trên tập dev, dự kiến xong {dm(1)}. (chat {dm(-3)})
- Đang cân nhắc nộp workshop VietNLP 2027, hạn full paper {dm(K_FULL)} (AoE). (chat {dm(-12)})

## Áp lực và năng lượng
- Tuần này vừa trợ giảng vừa viết chương 3 nên ít thời gian chạy thí nghiệm. (chat {dm(-2)})
- [suy luận] Đang ngại viết phần phương pháp hơn là chạy thí nghiệm; nên chia viết thành khối nhỏ. (chat {dm(-8)}, độ chắc: vừa)

## Đã xong gần đây
- Gửi GVHD bản nháp chương 2 (tổng quan). (chat {dm(-9)})
"""
    files["me/preferences.md"] = f"""# Sở thích và cách làm việc — cập nhật {iso(-18)}
{MEMO}

## Ngôn ngữ và xưng hô
- Ngôn ngữ: tiếng Việt
- Mentor xưng: mình
- Gọi người học: bạn

## Cách giải thích hiệu quả
- Thích gạch đầu dòng ngắn, giữ nguyên thuật ngữ tiếng Anh. (chat {dm(-25)})
- Muốn có link nguồn cho mọi thông tin về paper và deadline. (chat {dm(-18)})

## Giờ học và nhịp sinh hoạt
- Viết vào buổi sáng 8:00-11:00, chiều chạy và xem thí nghiệm. (chat {dm(-25)})
- Chiều thứ Tư đi trợ giảng, không xếp việc nghiên cứu. (chat {dm(-26)})

## Giọng điệu
- Thẳng thắn, góp ý cụ thể, không cần động viên chung chung. (chat {dm(-22)})
"""
    files["me/people.md"] = f"""# Những người liên quan — cập nhật {iso(-12)}
{MEMO}
<!-- Chỉ ghi tối thiểu: tên gọi + vai trò + điều liên quan đến việc học. Không ghi chuyện riêng, sức khỏe hay nhận xét cá nhân về người khác. -->

## Trong việc học
- Thầy Hùng (PGS. Lê Văn Hùng): GVHD chính, họp 2 tuần một lần chiều thứ Năm, muốn nhận bản nháp trước 2 ngày. (chat {dm(-27)})
- Cô Như (TS. Phạm Quỳnh Như): đồng hướng dẫn, góp ý phần đánh giá. (chat {dm(-27)})
- Đức: bạn cùng lab làm ASR, dùng chung lịch GPU. (chat {dm(-20)})
- Anh Tùng: postdoc của lab, hay góp ý cách viết paper. (chat {dm(-12)})
"""
    files["me/what-works.md"] = f"""# Cách hỗ trợ hiệu quả — cập nhật {iso(-8)}
{MEMO}

## Hiệu quả
- Chia phần viết thành khối 45 phút, mỗi khối một đoạn. (chat {dm(-19)})
- Checklist trước khi chạy thí nghiệm (seed, commit, cấu hình) giúp không phải chạy lại. (chat {dm(-10)})
- Chuẩn bị agenda họp 2 ngày trước giúp buổi họp gọn. (chat {dm(-5)})

## Không hiệu quả
- Đọc paper liền mạch từ đầu đến cuối dễ bỏ dở; nên đọc 3 lượt. (chat {dm(-16)})
- [suy luận] Kế hoạch tuần quá 6 việc thì cuối tuần bỏ gần hết; nên giữ 4-5 việc. (chat {dm(-8)}, độ chắc: vừa)
"""
    journals = {
        -20: ["Buổi đầu: kể về đề tài RAG pháp luật tiếng Việt và lịch họp GVHD. (chat {a})",
              "Liệt kê được 3 câu hỏi nghiên cứu bằng lời của mình. (chat {a})",
              "Chưa có baseline nào chạy ổn định. (chat {a})",
              "[suy luận] Cần mốc nhỏ theo tuần cho phần thí nghiệm. (chat {a}, độ chắc: vừa)"],
        -13: ["Đọc xong DPR (Karpukhin và cộng sự, 2020), viết tóm tắt 4 câu. (chat {a})",
              "Chạy xong baseline BM25 và mDPR trên tập dev. (file research/experiments/log.md {a})",
              "Kết quả mDPR thấp hơn BM25 trên văn bản dài. (chat {a})",
              "Lần sau hỏi về cách chia đoạn (chunking) văn bản luật. (chat {a})"],
        -8: ["Thử thí nghiệm vị trí đoạn trích, bị lỗi hết bộ nhớ GPU. (chat {a})",
             "Ghi đủ thí nghiệm thất bại vào log, có cấu hình và seed. (chat {a})",
             "Viết phần phương pháp chậm, mới được nửa mục 3.1. (chat {a})",
             "[suy luận] Ngại viết hơn ngại chạy thí nghiệm. (chat {a}, độ chắc: vừa)"],
        K_PREV_MEET: ["Họp GVHD: thầy Hùng góp ý chương 2, giao 3 việc. (chat {a})",
                      "Agenda chuẩn bị trước nên buổi họp 40 phút là xong. (chat {a})",
                      "Chưa quyết có nộp workshop VietNLP 2027 không. (chat {a})",
                      "Việc sau họp đã ghi ở research/meetings. (chat {a})"],
        -1: ["Bắt đầu fine-tune PhoBERT-DPR, đọc tiếp Lost in the Middle. (chat {a})",
             "Viết xong khung mục 3.2. (chat {a})",
             "Lịch GPU kín đến giữa tuần. (chat {a})",
             "Nhắc gửi nháp cho thầy Hùng trước buổi họp {meet}. (chat {a})"],
    }
    for k, (what, good, hard, note) in sorted(journals.items()):
        a = dm(k)
        fmt = {"a": a, "meet": dm(K_MEET)}
        files[f"me/journal/{iso(k)}.md"] = (
            f"# Nhật ký {iso(k)}\n## Chuyện gì đã xảy ra\n- {what.format(**fmt)}\n"
            f"## Tiến bộ\n- {good.format(**fmt)}\n## Khó khăn\n- {hard.format(**fmt)}\n"
            f"## Ghi chú cho mentor\n- {note.format(**fmt)}\n"
        )
    files["research/thesis.md"] = f"""# Luận văn / luận án — cập nhật {iso(-5)}
<!-- Nguồn sự thật về hướng nghiên cứu. Người học viết nội dung; mentor chỉ ghi lại và nhắc mốc. -->

**Câu hỏi nghiên cứu:** Làm sao để hệ hỏi đáp RAG tiếng Việt trả lời đúng và có trích dẫn trên văn bản pháp luật dài, khi chỉ có ít dữ liệu gán nhãn?

## Tên đề tài (tạm)
Retrieval-augmented generation cho hỏi đáp văn bản pháp luật tiếng Việt với tài nguyên hạn chế

## Câu hỏi nghiên cứu
- RQ1: Bộ truy xuất dense huấn luyện riêng cho tiếng Việt (PhoBERT-DPR) hơn bộ truy xuất đa ngôn ngữ và BM25 đến đâu trên văn bản luật dài?
- RQ2: Vị trí của đoạn liên quan trong ngữ cảnh ảnh hưởng thế nào đến câu trả lời tiếng Việt của LLM?
- RQ3: Có giảm được câu trả lời không có căn cứ bằng bước tự kiểm tra (self-reflection) với chi phí thấp không?

## Từ khóa theo dõi
- retrieval-augmented generation
- dense passage retrieval
- Vietnamese question answering
- long-context language models
- hallucination detection

## Cấu trúc
- Chương 1. Mở đầu — nháp
- Chương 2. Tổng quan — đã gửi GVHD ({dm(-9)})
- Chương 3. Phương pháp truy xuất — đang viết (3.1 nửa, 3.2 khung)
- Chương 4. Thực nghiệm — chưa viết
- Chương 5. Kết luận — chưa viết

## Mốc tiến độ
- [x] {iso(-150)} — Bảo vệ đề cương
- [x] {iso(-9)} — Gửi GVHD bản nháp chương 2
- [ ] {iso(K_MEET - 2)} — Gửi GVHD nháp mục 3.1-3.2
- [ ] {iso(K_FULL)} — Nộp bài workshop VietNLP 2027 (nếu đủ kết quả)
- [ ] {iso(120)} — Bảo vệ chuyên đề tiến sĩ 2
"""
    files["research/reading-queue.md"] = f"""# Danh sách đọc
<!-- Skill literature-watch thêm paper vào Chưa đọc, kèm lý do liên quan. Ghi chú đọc ở research/papers/<slug>.md. -->

## Chưa đọc
- [ ] Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection — Asai và cộng sự (2023). https://arxiv.org/abs/2310.11511
  Lý do: đề xuất bước tự đánh giá khi sinh câu trả lời, liên quan trực tiếp RQ3. (literature-watch {dm(-15)})
- [ ] Retrieval-Augmented Generation for Large Language Models: A Survey — Gao và cộng sự (2023). https://arxiv.org/abs/2312.10997
  Lý do: tổng quan các kiểu RAG, dùng cho chương 2. (literature-watch {dm(-15)})
- [ ] ColBERTv2: Effective and Efficient Retrieval via Lightweight Late Interaction — Santhanam và cộng sự (2021). https://arxiv.org/abs/2112.01488
  Lý do: một kiểu truy xuất khác dense dual-encoder, có thể làm baseline cho RQ1. (literature-watch {dm(-1)})
- [ ] QLoRA: Efficient Finetuning of Quantized LLMs — Dettmers và cộng sự (2023). https://arxiv.org/abs/2305.14314
  Lý do: fine-tune LLM sinh câu trả lời trên GPU dùng chung của lab. (chat {dm(-10)})

## Đang đọc
- [ ] Lost in the Middle: How Language Models Use Long Contexts — Liu và cộng sự (2023). https://arxiv.org/abs/2307.03172
  Ghi chú: research/papers/liu2023-lost-middle.md (chat {dm(-3)})

## Đã đọc
- [x] Dense Passage Retrieval for Open-Domain Question Answering — Karpukhin và cộng sự (2020). https://arxiv.org/abs/2004.04906
  Ghi chú: research/papers/karpukhin2020-dpr.md (chat {dm(-13)})
- [x] Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks — Lewis và cộng sự (2020). https://arxiv.org/abs/2005.11401 (chat {dm(-24)})
- [x] PhoBERT: Pre-trained language models for Vietnamese — Nguyen và Nguyen (2020). https://arxiv.org/abs/2003.00744 (chat {dm(-24)})
"""
    files["research/papers/karpukhin2020-dpr.md"] = f"""# Dense Passage Retrieval for Open-Domain Question Answering
- Tác giả, năm, nơi đăng: Vladimir Karpukhin, Barlas Oğuz, Sewon Min, Patrick Lewis, Ledell Wu, Sergey Edunov, Danqi Chen, Wen-tau Yih; 2020; EMNLP 2020
- Link / file: https://arxiv.org/abs/2004.04906
- Trạng thái: đã đọc

## Abstract (chép từ paper)
Open-domain question answering relies on efficient passage retrieval to select candidate contexts, where traditional sparse vector space models, such as TF-IDF or BM25, are the de facto method. In this work, we show that retrieval can be practically implemented using dense representations alone, where embeddings are learned from a small number of questions and passages by a simple dual-encoder framework. When evaluated on a wide range of open-domain QA datasets, our dense retriever outperforms a strong Lucene-BM25 system largely by 9%-19% absolute in terms of top-20 passage retrieval accuracy, and helps our end-to-end QA system establish new state-of-the-art on multiple open-domain QA benchmarks.

## Tóm tắt của người học
- Vấn đề: truy xuất đoạn văn cho QA miền mở, BM25 bỏ sót khi câu hỏi và đoạn văn dùng từ khác nhau.
- Cách làm: hai encoder BERT riêng cho câu hỏi và đoạn văn, huấn luyện với in-batch negatives và hard negative từ BM25.
- Kết quả: top-20 accuracy cao hơn BM25 rõ rệt trên nhiều bộ QA tiếng Anh.
- Liên quan: baseline chính cho RQ1; cần thử với PhoBERT làm encoder.
(chat {dm(-13)})

## Phê bình của người học
- Văn bản luật dài hơn đoạn Wikipedia nhiều; chưa rõ cách chia đoạn ảnh hưởng ra sao. (chat {dm(-13)})

## Góp ý của mentor
- Tóm tắt đúng ý chính về in-batch negatives và hard negative từ BM25.
- Câu hỏi đào sâu: paper so sánh mấy loại negative, và loại nào hợp với dữ liệu ít nhãn của bạn?

## Liên quan đến luận văn
"""
    files["research/papers/liu2023-lost-middle.md"] = f"""# Lost in the Middle: How Language Models Use Long Contexts
- Tác giả, năm, nơi đăng: Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua, Fabio Petroni, Percy Liang; 2023; TACL 2024
- Link / file: https://arxiv.org/abs/2307.03172
- Trạng thái: đang đọc

## Abstract (chép từ paper)
While recent language models have the ability to take long contexts as input, relatively little is known about how well they use longer context. We analyze the performance of language models on two tasks that require identifying relevant information in their input contexts: multi-document question answering and key-value retrieval. We find that performance can degrade significantly when changing the position of relevant information, indicating that current language models do not robustly make use of information in long input contexts. In particular, we observe that performance is often highest when relevant information occurs at the beginning or end of the input context, and significantly degrades when models must access relevant information in the middle of long contexts, even for explicitly long-context models. Our analysis provides a better understanding of how language models use their input context and provides new evaluation protocols for future long-context language models.

## Tóm tắt của người học
- Vấn đề: LLM có dùng tốt thông tin nằm giữa ngữ cảnh dài không. (chat {dm(-3)})

## Phê bình của người học

## Góp ý của mentor

## Liên quan đến luận văn
"""
    files["research/experiments/log.md"] = f"""# Nhật ký thí nghiệm
<!-- Skill experiment-journal. Mục mới nhất ở trên cùng, ngay dưới dòng này. Ghi cả thí nghiệm thất bại. -->

## EXP-{iso(-3)}-a — Fine-tune PhoBERT-DPR
- Trạng thái: đang chạy
- Mục đích / giả thuyết: encoder tiếng Việt truy xuất tốt hơn mDPR trên văn bản luật (RQ1).
- Thiết lập: code commit a41f2c9, tập train 3.2k cặp câu hỏi-đoạn, batch 32, lr 2e-5, seed 13
- Kết quả: (chưa có)
- Nhận xét của người học:
- Bước tiếp theo: so sánh Recall@20 với BM25 và mDPR trên cùng tập dev.
- Nguồn: chat {dm(-3)}

## EXP-{iso(-8)}-a — Vị trí đoạn liên quan trong ngữ cảnh
- Trạng thái: thất bại
- Mục đích / giả thuyết: kiểm tra hiện tượng lost-in-the-middle với câu hỏi tiếng Việt (RQ2).
- Thiết lập: 20 đoạn mỗi câu hỏi, LLM 7B, ngữ cảnh 8k token, seed 7
- Kết quả: hết bộ nhớ GPU khi ngữ cảnh 8k; chưa có số liệu.
- Nhận xét của người học: thử lại với 10 đoạn hoặc lượng tử hóa 4-bit.
- Bước tiếp theo: đọc QLoRA trước khi chạy lại.
- Nguồn: chat {dm(-8)}

## EXP-{iso(-13)}-a — Baseline BM25 và mDPR
- Trạng thái: xong
- Mục đích / giả thuyết: có mốc so sánh cho RQ1.
- Thiết lập: tập dev 400 câu hỏi (tự gán nhãn), đoạn 200 từ, BM25 mặc định; mDPR checkpoint công khai
- Kết quả: Recall@20 BM25 0.61, mDPR 0.58.
- Nhận xét của người học: mDPR kém trên điều luật dài, có thể do chia đoạn.
- Bước tiếp theo: fine-tune encoder tiếng Việt.
- Nguồn: chat {dm(-13)}
"""
    files[f"research/meetings/{iso(K_PREV_MEET)}-gvhd.md"] = f"""# Họp GVHD — {iso(K_PREV_MEET)}
## Việc đã hứa lần trước
- [x] Chạy baseline BM25 và mDPR (log {dm(-13)})
- [x] Gửi bản nháp chương 2 (chat {dm(-9)})
## Kết quả mới
- BM25 vẫn hơn mDPR trên tập dev; nghi do chia đoạn.
## Câu hỏi mở
- Có nên tự gán nhãn thêm 500 câu hỏi không?
## Cần GVHD quyết định
- Có nộp workshop VietNLP 2027 không.
## Ghi chú trong buổi họp
- Thầy Hùng: chương 2 cần thêm phần so sánh các cách chia đoạn. (chat {dm(K_PREV_MEET)})
- Chưa cần gán nhãn thêm; ưu tiên fine-tune encoder tiếng Việt trước. (chat {dm(K_PREV_MEET)})
## Việc cần làm sau họp
- [ ] Fine-tune PhoBERT-DPR, báo Recall@20 — hạn {iso(K_MEET)}
- [ ] Viết nháp mục 3.1-3.2 — hạn {iso(K_MEET - 2)}
- [ ] Đọc Lost in the Middle, nghĩ thiết kế thí nghiệm RQ2 — hạn {iso(K_MEET)}
"""
    files["goals/goals.md"] = f"""# Mục tiêu — cập nhật {iso(-5)}
<!-- Người học làm chủ mục tiêu; mentor đề xuất. Mỗi mục tiêu có hạn, lý do và 2-5 mốc có ngày (skill goal-planning). -->

## Đang theo đuổi
### Nộp bài workshop VietNLP 2027 — hạn {iso(K_FULL + 1)} (nguồn: chat {dm(-12)})
- Vì sao: cần bài hội thảo đầu tiên từ kết quả RQ1.
- Mốc:
  - [x] {iso(-13)} — Có baseline BM25 và mDPR
  - [ ] {iso(2)} — Có kết quả PhoBERT-DPR trên tập dev
  - [ ] {iso(K_ABSTRACT - 3)} — Bản nháp 4 trang gửi thầy Hùng và cô Như
  - [ ] {iso(K_ABSTRACT)} — Đăng ký abstract
  - [ ] {iso(K_FULL - 2)} — Bản cuối, kiểm tra trích dẫn và định dạng

### Xong nháp chương 3 — hạn {iso(45)} (nguồn: chat {dm(-20)})
- Vì sao: chương 3 là nền cho bài workshop và chuyên đề tiến sĩ 2.
- Mốc:
  - [ ] {iso(K_MEET - 2)} — Nháp mục 3.1-3.2 gửi GVHD
  - [ ] {iso(30)} — Nháp mục 3.3 (thiết kế đánh giá)

## Deadline
- {iso(K_MEET - 2)} (chưa rõ giờ) — Gửi thầy Hùng nháp mục 3.1-3.2 — nguồn: chat {dm(K_PREV_MEET)}
- {iso(K_MEET)} 14:00 (giờ VN) — Họp GVHD — nguồn: chat {dm(K_PREV_MEET)}
- {aoe_to_vn(K_ABSTRACT)} — Đăng ký abstract workshop VietNLP 2027 — nguồn: chat {dm(-12)} (chưa xác nhận)
- {aoe_to_vn(K_FULL)} — Nộp full paper workshop VietNLP 2027 — nguồn: chat {dm(-12)} (chưa xác nhận)

## Đã qua
- {iso(-9)} — Gửi GVHD nháp chương 2: xong.

## Đã đạt

## Đã dừng
"""
    files["goals/plans/this-week.md"] = f"""# Kế hoạch tuần (từ {iso(MONDAY)})
<!-- Việc cụ thể, có ngày và thời lượng. Mentor sửa kế hoạch khi bị chậm, không lập lại từ đầu (skill goal-planning). -->

## Việc của người học
- [x] {wds(MONDAY)} 08:00 — 2 giờ: viết nửa sau mục 3.1
- [ ] {wds(MONDAY + 1)} 08:00 — 90 phút: khung mục 3.2, liệt kê các cách chia đoạn
- [ ] {wds(MONDAY + 3)} 09:00 — 1 giờ: đọc phần thí nghiệm của Lost in the Middle
- [ ] {wds(MONDAY + 4)} 14:00 — 1 giờ: xem kết quả PhoBERT-DPR, ghi vào log
- [ ] {wds(MONDAY + 5)} 09:00 — 45 phút: quyết định có nộp VietNLP 2027 không

## Mentor sẽ làm
- Chuẩn bị khung agenda họp GVHD {dm(K_MEET)} trước 2 ngày.
- Theo dõi hạn abstract và full paper VietNLP 2027, nhắc trước 7 ngày.

## Điều chỉnh
- {dm(MONDAY)}: bỏ việc chạy lại thí nghiệm vị trí đoạn sang tuần sau vì lịch GPU kín. (chat {dm(-2)})
"""
    files["goals/plans/term.md"] = f"""# Kế hoạch dài hạn — cập nhật {iso(-20)}
<!-- Mốc lớn của học kỳ hoặc năm. Mỗi tuần chỉ kéo 1-2 mốc vào this-week.md. -->

## Mốc lớn
- [ ] {iso(K_FULL)} — Nộp workshop VietNLP 2027
- [ ] {iso(45)} — Nháp chương 3
- [ ] {iso(120)} — Bảo vệ chuyên đề tiến sĩ 2

## Ghi chú
- Giữ 4-5 việc mỗi tuần. (chat {dm(-8)})
"""
    return files


# ---- inbox: PDF and emails -----------------------------------------------------------------------


def make_pdf(pages: list[list[str]]) -> bytes:
    """A minimal, valid, text-based PDF (Helvetica, ASCII text) with a correct xref table."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    page_ids = [4 + 2 * i for i in range(len(pages))]
    objs: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(pages)} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    }
    for pid, lines in zip(page_ids, pages, strict=True):
        ops = ["BT", "/F1 15 Tf", "18 TL", "56 780 Td", f"({esc(lines[0])}) Tj", "T*", "/F1 10.5 Tf", "14 TL", "T*"]
        for line in lines[1:]:
            ops += [f"({esc(line)}) Tj", "T*"]
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objs[pid] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                     f"/Resources << /Font << /F1 3 0 R >> >> /Contents {pid + 1} 0 R >>").encode()
        objs[pid + 1] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for n in sorted(objs):
        offsets[n] = len(out)
        out += b"%d 0 obj\n" % n + objs[n] + b"\nendobj\n"
    xref = len(out)
    count = max(objs) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % count
    for n in range(1, count):
        out += b"%010d 00000 n \n" % offsets[n]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (count, xref)
    return bytes(out)


def ncs_pdf() -> bytes:
    return make_pdf([
        [
            "Lab Tech Note: Retrieval Baselines for Vietnamese Legal QA (draft)",
            "Tran Thu Lan  -  NLP Lab  -  internal note, demo data (fictional)",
            f"Version of {en_date(-6)}",
            "",
            "1. Goal",
            "We compare sparse and dense retrievers on a small, self-annotated dev set of",
            "400 questions over Vietnamese legal documents. The note is a working draft for",
            "the supervisor meeting and is not a publication.",
            "",
            "2. Setup",
            "- Corpus: 1,250 legal documents split into passages of about 200 words.",
            "- Retrievers: BM25 (default parameters), multilingual DPR (public checkpoint),",
            "  PhoBERT-DPR (fine-tuning in progress).",
            "- Metric: Recall@20 and MRR@10 on the dev set.",
            "",
            "3. Preliminary results",
            "- BM25: Recall@20 = 0.61, MRR@10 = 0.42",
            "- mDPR:  Recall@20 = 0.58, MRR@10 = 0.39",
            "- PhoBERT-DPR: pending (run started this week).",
            "",
            "4. Observations",
            "- Dense retrieval underperforms on long articles with many cross-references.",
            "- Passage length (chunking) seems to matter more than the encoder for now.",
        ],
        [
            "5. Next steps",
            "- Finish PhoBERT-DPR fine-tuning and report Recall@20 on the same dev set.",
            "- Try three chunking strategies: fixed 200 words, per article, per clause.",
            "- Design the position experiment for RQ2 with 10 passages per question.",
            "",
            "6. Open questions for the meeting",
            "- Is the dev set (400 questions) large enough for a workshop paper?",
            "- Should we report results per document type (law, decree, circular)?",
            "",
            "References",
            "[1] Karpukhin et al. Dense Passage Retrieval for Open-Domain Question Answering.",
            "    EMNLP 2020. arXiv:2004.04906",
            "[2] Nguyen and Nguyen. PhoBERT: Pre-trained language models for Vietnamese.",
            "    Findings of EMNLP 2020. arXiv:2003.00744",
            "[3] Liu et al. Lost in the Middle: How Language Models Use Long Contexts.",
            "    TACL 2024. arXiv:2307.03172",
        ],
    ])


def ncs_emails(inbound: str) -> list[bytes]:
    sup = EmailMessage()
    sup["From"] = "PGS.TS. Lê Văn Hùng <hung.le@university.example.com>"
    sup["To"] = f"Trần Thu Lan <lan.tran@university.example.com>, {inbound}"
    sup["Subject"] = f"Họp nhóm {wd(K_MEET)} {dm(K_MEET)} và bản nháp chương 3"
    sup["Date"] = format_datetime(datetime.combine(d(-1), datetime.min.time(), VN).replace(hour=21, minute=14))
    sup["Message-ID"] = f"<{uuid.uuid4().hex}@university.example.com>"
    sup.set_content(f"""Chào Lan,

Thầy xác nhận buổi họp {wd(K_MEET).lower()} {dm(K_MEET)}/{d(K_MEET).year} lúc 14:00 ở phòng 702 nhà B1 (nếu em bận \
việc trợ giảng thì họp online, thầy gửi link sau).

Em gửi thầy bản nháp mục 3.1-3.2 trước {wd(K_MEET - 2).lower()} {dm(K_MEET - 2)} để thầy kịp đọc. Buổi họp em mang theo:
- bảng so sánh BM25 / mDPR / PhoBERT-DPR trên cùng tập dev (Recall@20, MRR@10);
- thiết kế thí nghiệm vị trí đoạn trích (RQ2), chỉ cần 1 trang.

Về workshop VietNLP 2027: nếu PhoBERT-DPR có kết quả trước buổi họp thì mình bàn chuyện nộp bài luôn.

Thầy Hùng

--
Dữ liệu demo: người gửi và nội dung là giả lập.
""")
    cfp = EmailMessage()
    cfp["From"] = "VietNLP 2027 Workshop <cfp@vietnlp-workshop.example.com>"
    cfp["To"] = inbound
    cfp["Subject"] = "[CFP] VietNLP 2027 Workshop - Second Call for Papers"
    cfp["Date"] = format_datetime(datetime.combine(d(-4), datetime.min.time(), ZoneInfo("UTC")).replace(hour=9, minute=30))
    cfp["Message-ID"] = f"<{uuid.uuid4().hex}@vietnlp-workshop.example.com>"
    cfp.set_content(f"""SECOND CALL FOR PAPERS
VietNLP 2027: Workshop on Natural Language Processing for Vietnamese (fictional demo event)

We invite submissions on all aspects of NLP for Vietnamese and related low-resource languages, including:
- retrieval-augmented generation and question answering
- evaluation of large language models in Vietnamese
- resources, benchmarks and annotation
- legal, medical and educational applications

IMPORTANT DATES (all deadlines are 23:59 AoE, UTC-12)
- Abstract registration: {en_date(K_ABSTRACT)}
- Full paper submission: {en_date(K_FULL)}
- Notification of acceptance: {en_date(K_FULL + 35)}
- Camera-ready: {en_date(K_FULL + 50)}

SUBMISSION
Long papers up to 8 pages, short papers up to 4 pages, plus unlimited references, in the ACL template.
Submission site: https://openreview.example.com/group?id=VietNLP/2027/Workshop
Workshop website: https://vietnlp-workshop.example.com/2027

Organizing committee, VietNLP 2027

--
Demo data: this workshop and its dates are fictional.
""")
    return [sup.as_bytes(), cfp.as_bytes()]


# ---- chat ----------------------------------------------------------------------------------------


async def chat_turn(base: str, web_origin: str, cookie: str, text: str, n: int) -> str:
    import websockets

    ws_url = base.rstrip("/").replace("http", "ws", 1) + "/api/ws/chat"
    t0, reply, tools = time.time(), [], []
    async with websockets.connect(ws_url, additional_headers={"Cookie": cookie, "Origin": web_origin},
                                  open_timeout=30, max_size=None) as ws:
        await ws.send(json.dumps({"type": "user_message", "client_msg_id": f"seed-{n}-{uuid.uuid4().hex[:6]}",
                                  "text": text, "attachments": []}))
        while True:
            ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=420))
            kind = ev.get("type")
            if kind == "text_delta":
                reply.append(ev.get("text", ""))
            elif kind == "tool_started":
                tools.append(ev.get("summary") or ev.get("tool"))
            elif kind == "approval_request":  # never approve external actions from a seed script
                appr = ev.get("approval") or {}
                await ws.send(json.dumps({"type": "approval_decision", "approval_id": appr.get("approval_id"),
                                          "decision": "deny", "scope": "once"}))
            elif kind == "error":
                raise SeedError(f"chat error: {ev.get('error')}")
            elif kind == "turn_done":
                break
    out = "".join(reply).strip()
    print(f"    turn {n}: {time.time() - t0:.0f}s, {len(tools)} tools; reply: {out[:240]!r}{'...' if len(out) > 240 else ''}")
    return out


def run_chat(c: httpx.Client, base: str, web_origin: str, messages: list[str]) -> None:
    cookie = "; ".join(f"{k}={v}" for k, v in c.cookies.items())
    try:
        c.post("/sandbox/warm")
    except httpx.HTTPError:
        pass
    for i, m in enumerate(messages, 1):
        print(f"  chat: {m}")
        asyncio.run(chat_turn(base, web_origin, cookie, m, i))


# ---- accounts ------------------------------------------------------------------------------------


def delete_account(base: str, web_origin: str, email: str) -> None:
    c = login(base, web_origin, email)
    check(c.delete("/account"), f"delete {email}")
    print(f"  deleted {email}")


def seed_thpt(base: str, web_origin: str, quiz: Path, chat: bool) -> httpx.Client:
    print(f"\n== THPT: {THPT_EMAIL}")
    c = login(base, web_origin, THPT_EMAIL)
    me = check(c.get("/me"), "me").json()
    if me["onboarding_state"] == "active":
        print("  already set up; use --reset to recreate it")
        return c
    check(c.post("/onboarding", json={"role": "thpt", "display_name": "Nguyễn Minh Anh", "language": "vi"}), "onboarding")
    check(c.post("/parent-link"), "parent-link")
    check(c.post("/dev/parent-link/verify"), "dev parent verify")
    me = check(c.get("/me"), "me").json()
    if me["onboarding_state"] != "active":
        raise SeedError(f"THPT account not active after parent verify: {me}")
    ws = Workspace(c)
    for path, content in thpt_files().items():
        ws.put(path, content)
    print(f"  wrote {len(ws.written)} files")
    if quiz.is_file():
        print(f"  uploaded {ws.upload('kiem-tra-15p-toan.png', quiz.read_bytes(), 'image/png')}")
    else:
        print(f"  ! quiz image not found at {quiz}; pass --quiz PATH")
    if chat:
        run_chat(c, base, web_origin, THPT_CHAT)
        for _ in range(20):  # the gateway delivers the report from the outbox after the turn
            reports = c.get("/reports").json()
            if reports:
                print(f"  parent report sent: {reports[0]['path']}")
                break
            time.sleep(3)
        else:
            print("  ! no parent report in /reports (the model did not draft/send one this time)")
    return c


def seed_ncs(base: str, web_origin: str, chat: bool, internal_token: str | None) -> httpx.Client:
    print(f"\n== NCS: {NCS_EMAIL}")
    c = login(base, web_origin, NCS_EMAIL)
    me = check(c.get("/me"), "me").json()
    if me["onboarding_state"] == "active":
        print("  already set up; use --reset to recreate it")
        return c
    me = check(c.post("/onboarding", json={"role": "ncs", "display_name": "Trần Thu Lan", "language": "vi"}),
               "onboarding").json()
    ws = Workspace(c)
    for path, content in ncs_files().items():
        ws.put(path, content)
    print(f"  wrote {len(ws.written)} files")
    print(f"  uploaded {ws.upload('lab-technote-retrieval.pdf', ncs_pdf(), 'application/pdf')}")
    inbound = me.get("inbound_email_address")
    if not inbound:
        print("  ! no inbound_email_address in /me; emails skipped")
    else:
        headers = {"Content-Type": "message/rfc822"}
        if internal_token:
            headers["X-Internal-Token"] = internal_token
        for raw in ncs_emails(inbound):
            r = c.post(base.rstrip("/") + "/internal/email/inbound", params={"rcpt": inbound}, content=raw,
                       headers=headers)
            if r.status_code == 403:
                print("  ! /internal/email/inbound refused (403): set --internal-token / GATEWAY_INTERNAL_TOKEN")
                break
            res = check(r, "inbound email").json()
            print(f"  email stored: {res.get('path')} (an intake job reads it in the background)")
    if chat:
        run_chat(c, base, web_origin, NCS_CHAT)
    return c


def verify(c: httpx.Client, email: str) -> None:
    """/me, memory and workspace files through the API, with the session the dev link gave us."""
    me = check(c.get("/me"), "me").json()
    tree = check(c.get("/workspace/tree"), "tree").json()
    files = [e["path"] for e in tree if e["type"] == "file"]
    now = check(c.get("/workspace/file", params={"path": "me/now.md"}), "now.md").json()["content"]
    hist = c.get("/chat/history").json()
    print(f"  {email}: state={me['onboarding_state']} role={me['role']} files={len(files)} "
          f"inbox={len([f for f in files if f.startswith('inbox/')])} chat_msgs_today={len(hist)}")
    print("    me/now.md: " + " | ".join(line for line in now.splitlines() if line.startswith("- "))[:300])


def print_instructions(base: str, gcal: str) -> None:
    print(f"""
================ DEMO ACCOUNTS (dev only, synthetic data) ================
Đăng nhập (web http://localhost:3000):
  1. Lấy link đăng nhập mới:
       uv run python infra/seed-demo.py --login {THPT_EMAIL}
       uv run python infra/seed-demo.py --login {NCS_EMAIL}
     (hoặc gõ email ở trang đăng nhập; gateway dev trả dev_link / dev_code, xem log hoặc
      POST {base}/api/auth/request-link)
  2. Mở dev_link trong trình duyệt (dùng localhost, không dùng 127.0.0.1, để cookie khớp với web),
     hoặc nhập mã 6 số ở trang đăng nhập. Tối đa 5 link mỗi giờ cho mỗi email.

THPT — Nguyễn Minh Anh, lớp 11 ({THPT_EMAIL}), phụ huynh đã xác nhận (dev):
  - Đính kèm ảnh bài kiểm tra (file inbox/...-kiem-tra-15p-toan.png đã có trong Workspace; hoặc tải lại
    ảnh và đính kèm): "Mentor xem giúp em bài kiểm tra này"
  - "Mentor nhớ gì về em?"  /  mục "Mentor biết gì về tôi" (có dòng [suy luận])
  - Báo cáo phụ huynh: mục "Báo cáo phụ huynh" (nếu đã gửi), hoặc nhờ mentor soạn và gửi báo cáo
  - "Quên chuyện tập văn nghệ đi"
  - Cài đặt → Mức độ chủ động (Tắt / Vừa / Nhiều), giờ yên lặng
  - Học tập: mastery Toán, lịch ôn, lỗi hay gặp; Mục tiêu & kế hoạch: hạn thi cuối kỳ

NCS — Trần Thu Lan, NCS năm 2 NLP ({NCS_EMAIL}):
  - "Tìm giúp mình paper mới về Vietnamese legal question answering"
  - Đọc trang web: "Đọc giúp mình https://arxiv.org/abs/2307.03172" ; PDF: "Tóm tắt file
    inbox/...-lab-technote-retrieval.pdf" (pdf_extract)
  - "Hạn nộp full paper VietNLP 2027 là mấy giờ theo giờ Việt Nam?" (deadline AoE)
  - "Thầy Hùng vừa gửi email gì?" (2 email vào inbox/email/; job intake đọc trong ~1 phút, ghi deadline vào
    goals/goals.md, me/now.md, rồi xóa file email và ghi vào inbox/processed.md, đúng skill intake-document)
  - "Chuẩn bị agenda họp với thầy Hùng" ; Nghiên cứu: câu hỏi nghiên cứu, mốc, hàng đợi đọc
  - Google Calendar: {gcal}
==========================================================================""")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="gateway base URL (no /api)")
    ap.add_argument("--web-origin", default=WEB_ORIGIN_DEFAULT)
    ap.add_argument("--reset", action="store_true", help="delete the demo accounts first, then recreate them")
    ap.add_argument("--delete", action="store_true", help="only delete the demo accounts")
    ap.add_argument("--login", metavar="EMAIL", help="print a fresh dev login link and code for EMAIL, then exit")
    ap.add_argument("--only", choices=["thpt", "ncs"])
    ap.add_argument("--no-chat", action="store_true", help="skip the real-model chat turns (3 by default)")
    ap.add_argument("--quiz", type=Path, default=QUIZ_PNG_DEFAULT, help="graded quiz image to upload for THPT")
    ap.add_argument("--internal-token", default=None,
                    help="GATEWAY_INTERNAL_TOKEN, only if the dev gateway sets one (for /internal/email/inbound)")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    token = args.internal_token or os.environ.get("GATEWAY_INTERNAL_TOKEN")
    try:
        if args.login:
            c = httpx.Client(base_url=base + "/api", headers={"Origin": args.web_origin}, timeout=30)
            data = request_link(c, args.login)
            print(f"dev_link: {data['dev_link']}\ndev_code: {data.get('dev_code')}")
            return 0
        which = [args.only] if args.only else ["thpt", "ncs"]
        emails = {"thpt": THPT_EMAIL, "ncs": NCS_EMAIL}
        if args.reset or args.delete:
            print("== deleting demo accounts")
            for w in which:
                delete_account(base, args.web_origin, emails[w])
            if args.delete:
                return 0
        clients: dict[str, httpx.Client] = {}
        if "thpt" in which:
            clients[THPT_EMAIL] = seed_thpt(base, args.web_origin, args.quiz, chat=not args.no_chat)
        if "ncs" in which:
            clients[NCS_EMAIL] = seed_ncs(base, args.web_origin, chat=not args.no_chat, internal_token=token)
        print("\n== check")
        gcal = "chưa kiểm tra"
        if NCS_EMAIL in clients:
            g = clients[NCS_EMAIL].get("/integrations/google-calendar")
            gcal = ("Cài đặt → Google Calendar → Kết nối Google Calendar"
                    if g.status_code == 200 and g.json().get("available")
                    else "máy chủ dev chưa cấu hình GOOGLE_OAUTH_CLIENT_ID/SECRET nên chưa thử được")
        for email, c in clients.items():
            verify(c, email)
        print_instructions(base, gcal)
    except (SeedError, httpx.HTTPError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
