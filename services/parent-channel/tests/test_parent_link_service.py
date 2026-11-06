import pytest
from mentor_parent_channel import ParentLinkError, ParentLinkService, find_leaks, is_consent_reply, messages
from mentor_schemas.reports import AI_DISCLAIMER
from zalo_fakes import Clock, FakeZalo, InMemoryStore, text_update

STUDENT = "stu-1"


def link_and_consent(service: ParentLinkService, chat_id: str = "chat-1") -> None:
    code = service.start_link(STUDENT).link_code
    service.handle_update(text_update(code, chat_id))
    service.handle_update(text_update("Đồng ý", chat_id))


def test_full_link_consent_verified_flow(service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo) -> None:
    link = service.start_link(STUDENT)
    assert len(link.link_code) == 6 and link.link_code.isdigit() and link.status == "pending"

    service.handle_update(text_update("xin chào"))
    assert zalo.sent()[-1][1] == messages.help_unlinked("Mentor Bot")

    service.handle_update(text_update(f"Mã liên kết: {link.link_code}"))
    saved = store.get_by_student(STUDENT)
    assert saved.status == "awaiting_consent" and saved.zalo_chat_id == "chat-1"
    consent = zalo.sent()[-1][1]
    assert "hệ thống tự động" in consent and "AI" in consent and "2 tuần" in consent and "dữ liệu" in consent

    service.handle_update(text_update("chưa chắc"))
    assert zalo.sent()[-1][1] == messages.help_awaiting_consent()
    assert store.get_by_student(STUDENT).status == "awaiting_consent"

    service.handle_update(text_update("ĐỒNG Ý"))
    saved = store.get_by_student(STUDENT)
    assert saved.status == "verified" and saved.verified_at is not None
    assert zalo.sent()[-1] == ("chat-1", messages.confirmation("Mentor Bot"))
    assert [(s, k) for s, k, _ in store.audit] == [(STUDENT, "consent")]


@pytest.mark.parametrize("reply", ["ĐỒNG Ý", "dong y", "đồng ý", "Đồng ý!", " dong  Y. "])
def test_consent_variants(reply: str) -> None:
    assert is_consent_reply(reply)


@pytest.mark.parametrize("reply", ["không đồng ý", "ok", "đồng"])
def test_not_consent(reply: str) -> None:
    assert not is_consent_reply(reply)


def test_start_link_replaces_pending_and_refuses_verified(service: ParentLinkService, store: InMemoryStore) -> None:
    first = service.start_link(STUDENT)
    second = service.start_link(STUDENT)
    assert store.get_by_student(STUDENT).link_code == second.link_code
    assert first.link_code == second.link_code or store.get_by_code(first.link_code) is None
    link_and_consent(service)
    with pytest.raises(ParentLinkError):
        service.start_link(STUDENT)


def test_expired_code(service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo, clock: Clock) -> None:
    code = service.start_link(STUDENT).link_code
    clock.advance(hours=24, seconds=1)
    service.handle_update(text_update(code))
    assert zalo.sent()[-1][1] == messages.expired_code()
    assert store.get_by_student(STUDENT).status == "pending"


def test_consent_after_expiry_is_refused(
    service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo, clock: Clock
) -> None:
    code = service.start_link(STUDENT).link_code
    service.handle_update(text_update(code))
    clock.advance(hours=25)
    service.handle_update(text_update("đồng ý"))
    assert store.get_by_student(STUDENT).status == "awaiting_consent"
    assert zalo.sent()[-1][1] == messages.expired_code()
    assert store.audit == []


def test_invalid_code_and_bruteforce_guard(
    service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo, clock: Clock
) -> None:
    code = service.start_link(STUDENT).link_code
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    for _ in range(5):
        service.handle_update(text_update(wrong))
    assert zalo.sent()[-1][1] == messages.invalid_code()
    service.handle_update(text_update(code))  # even the right code is refused while blocked
    assert zalo.sent()[-1][1] == messages.too_many_attempts()
    assert store.get_by_student(STUDENT).status == "pending"
    clock.advance(hours=1, seconds=1)
    service.handle_update(text_update(code))
    assert store.get_by_student(STUDENT).status == "awaiting_consent"


def test_code_cannot_be_claimed_by_second_chat(
    service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo
) -> None:
    code = service.start_link(STUDENT).link_code
    service.handle_update(text_update(code, "chat-1"))
    service.handle_update(text_update(code, "chat-2"))
    assert zalo.sent()[-1] == ("chat-2", messages.invalid_code())
    assert store.get_by_student(STUDENT).zalo_chat_id == "chat-1"


def test_duplicate_update_ignored(service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo) -> None:
    code = service.start_link(STUDENT).link_code
    service.handle_update(text_update(code, message_id="dup-1"))
    service.handle_update(text_update("đồng ý", message_id="dup-2"))
    n_sent = len(zalo.sent())
    service.handle_update(text_update("đồng ý", message_id="dup-2"))
    service.handle_update(text_update(code, message_id="dup-1"))
    assert len(zalo.sent()) == n_sent
    assert len(store.audit) == 1


def test_group_and_unsupported_events_ignored(service: ParentLinkService, zalo: FakeZalo) -> None:
    code = service.start_link(STUDENT).link_code
    group = text_update(code)
    group["message"]["chat"]["chat_type"] = "GROUP"
    service.handle_update(group)
    unsupported = text_update(code)
    unsupported["event_name"] = "message.unsupported.received"
    service.handle_update(unsupported)
    service.handle_update({"event_name": "bot.something"})
    assert zalo.sent() == []


def test_report_sent_with_label_and_disclaimer(service: ParentLinkService, zalo: FakeZalo) -> None:
    link_and_consent(service)
    report = (
        "---\nperiod_start: 2026-10-24\nperiod_end: 2026-11-06\nincludes_wellbeing_nudge: false\n---\n"
        "## Tiến độ mục tiêu\n- **Toán**: hoàn thành 3/4 mục tiêu tuần.\n\n" + AI_DISCLAIMER + "\n"
    )
    assert service.send_report(STUDENT, report) is True
    chat_id, text = zalo.sent()[-1]
    assert chat_id == "chat-1"
    assert text.startswith(messages.AI_LABEL)
    assert text.endswith(AI_DISCLAIMER) and text.count(AI_DISCLAIMER) == 1
    assert "**" not in text and "period_start" not in text


def test_report_disclaimer_present_is_not_repeated(service: ParentLinkService, zalo: FakeZalo) -> None:
    link_and_consent(service)
    report = f"## Tuần này\nCon học đều.\n\n*{AI_DISCLAIMER}*\n\n## Gợi ý\nDành thời gian trò chuyện với con."
    assert service.send_report(STUDENT, report) is True
    text = zalo.sent()[-1][1]
    assert text.count(AI_DISCLAIMER) == 1
    assert text.endswith("Dành thời gian trò chuyện với con.")  # kept where the report put it, nothing appended


def test_report_disclaimer_missing_is_appended(service: ParentLinkService, zalo: FakeZalo) -> None:
    link_and_consent(service)
    assert service.send_report(STUDENT, "## Tuần này\nCon học đều.") is True
    text = zalo.sent()[-1][1]
    assert text.count(AI_DISCLAIMER) == 1 and text.endswith(f"Con học đều.\n\n{AI_DISCLAIMER}")


@pytest.mark.parametrize(
    "bad",
    ["Bài kiểm tra 15 phút: 6/10.", "Điểm số 8 môn Toán.", "Con viết “mệt quá”.", "Con kể là bị bạn trêu.",
     "Liên hệ an.nguyen@gmail.com.", "Gọi 0912 345 678 nhé.", "Xem chi tiết ở me/now.md.",
     "Theo sessions/2026-10-28/s-1.md.", "File .mentor/wellbeing.jsonl."],
)
def test_report_blocked_when_forbidden_pattern_present(service: ParentLinkService, zalo: FakeZalo, bad: str) -> None:
    link_and_consent(service)
    n_sent = len(zalo.sent())
    assert service.send_report(STUDENT, f"## Tuần này\n{bad}\n") is False
    assert len(zalo.sent()) == n_sent


def test_report_requires_verified_link(service: ParentLinkService, zalo: FakeZalo) -> None:
    code = service.start_link(STUDENT).link_code
    service.handle_update(text_update(code))
    n_sent = len(zalo.sent())
    assert service.send_report(STUDENT, "Tiến bộ tốt.") is False
    assert service.send_report("nobody", "Tiến bộ tốt.") is False
    assert len(zalo.sent()) == n_sent


def test_long_report_split(service: ParentLinkService, zalo: FakeZalo) -> None:
    link_and_consent(service)
    n_sent = len(zalo.sent())
    sections = [f"## Chủ đề {i}\n" + "Con học đều và tiến bộ rõ ở phần này. " * 30 for i in range(6)]
    assert service.send_report(STUDENT, "\n\n".join(sections)) is True
    parts = [t for _, t in zalo.sent()[n_sent:]]
    assert len(parts) >= 3
    assert all(len(p) <= 2000 for p in parts)
    assert parts[0].startswith(messages.AI_LABEL) and parts[-1].endswith(AI_DISCLAIMER)


def test_crisis_alert_audited_without_details(service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo) -> None:
    link_and_consent(service)
    assert service.send_crisis_alert(STUDENT, "self_harm") is True
    assert zalo.sent()[-1] == ("chat-1", messages.CRISIS_ALERT)
    assert messages.CRISIS_ALERT == (
        "Hệ thống ghi nhận con cần được hỗ trợ. Phụ huynh vui lòng liên hệ với con, hoặc gọi Tổng đài 111."
    )
    assert store.audit[-1] == (STUDENT, "crisis_alert", "category=self_harm; delivered=true")


def test_crisis_alert_failure_and_unlinked_are_audited(
    service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo
) -> None:
    assert service.send_crisis_alert(STUDENT, "abuse") is False
    assert store.audit[-1][1:] == ("crisis_alert", "category=abuse; delivered=false; reason=no_verified_link")
    link_and_consent(service)
    zalo.fail_with = {"ok": False, "error_code": 429, "description": "Quota exceeded"}
    assert service.send_crisis_alert(STUDENT, "run_away") is False
    assert store.audit[-1][2] == "category=run_away; delivered=false; reason=ZaloQuotaExceededError"


def test_reply_failure_does_not_break_state(service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo) -> None:
    code = service.start_link(STUDENT).link_code
    zalo.fail_with = {"ok": False, "error_code": 403, "description": "Internal server error"}
    service.handle_update(text_update(code))
    assert store.get_by_student(STUDENT).status == "awaiting_consent"


def test_find_leaks_names_checks_without_content() -> None:
    report = "---\nperiod_start: 2026-10-14\nperiod_end: 2026-10-27\n---\nCon học đều đặn 9/14 ngày.\n"
    assert find_leaks(report) == []  # frontmatter dates and "9/14 ngày" are fine
    leaky = report + "Email a@b.vn, số +84 912 345 678, xem inbox/email/x.md, được 5/10.\n"
    assert find_leaks(leaky) == ["forbidden:0", "email", "phone", "workspace_path"]
