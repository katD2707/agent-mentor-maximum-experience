import httpx
import pytest
from mentor_parent_channel import (
    MAX_MESSAGE_CHARS,
    ZaloApiError,
    ZaloBotClient,
    ZaloNetworkError,
    ZaloQuotaExceededError,
    ZaloUnauthorizedError,
    markdown_to_plain,
    split_text,
)
from mentor_parent_channel.text import utf16_len
from zalo_fakes import BASE, TOKEN, FakeZalo


def test_get_me_and_url_shape(client: ZaloBotClient, zalo: FakeZalo) -> None:
    info = client.get_me()
    assert info.id == "1459"
    assert zalo.calls == [("getMe", {})]


def test_set_webhook_validates_secret_length(client: ZaloBotClient, zalo: FakeZalo) -> None:
    with pytest.raises(ValueError):
        client.set_webhook("https://example.vn/webhooks/zalo", "short")
    result = client.set_webhook("https://example.vn/webhooks/zalo", "s" * 32)
    assert result["verification"]["ok"] is True
    assert zalo.calls[-1] == ("setWebhook", {"url": "https://example.vn/webhooks/zalo", "secret_token": "s" * 32})


@pytest.mark.parametrize(
    ("code", "exc"),
    [(401, ZaloUnauthorizedError), (429, ZaloQuotaExceededError), (403, ZaloApiError)],
)
def test_typed_errors(client: ZaloBotClient, zalo: FakeZalo, code: int, exc: type) -> None:
    zalo.fail_with = {"ok": False, "error_code": code, "description": "nope"}
    with pytest.raises(exc) as info:
        client.send_message("c", "hi")
    assert info.value.error_code == code
    assert TOKEN not in str(info.value)


def test_network_error_hides_token() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = ZaloBotClient(TOKEN, base_url=BASE, transport=httpx.MockTransport(boom))
    with pytest.raises(ZaloNetworkError) as info:
        client.get_me()
    assert TOKEN not in str(info.value) and info.value.__cause__ is None
    assert TOKEN not in repr(client)


def test_non_json_response_is_network_error() -> None:
    client = ZaloBotClient(TOKEN, base_url=BASE, transport=httpx.MockTransport(lambda r: httpx.Response(502, text="x")))
    with pytest.raises(ZaloNetworkError):
        client.get_me()


def test_send_message_splits_long_text(client: ZaloBotClient, zalo: FakeZalo) -> None:
    paragraph = "Con học đều đặn trong tuần này và tiến bộ ở chủ đề hàm số. " * 12  # ~720 chars
    text = "\n\n".join([paragraph.strip()] * 5)
    ids = client.send_message("chat-9", text)
    sent = zalo.sent()
    assert len(ids) == len(sent) >= 2
    assert all(len(t) <= MAX_MESSAGE_CHARS for _, t in sent)
    assert all(t.endswith(".") for _, t in sent)  # cut at paragraph boundaries, not mid-sentence
    assert "\n\n".join(t for _, t in sent) == text


def test_split_prefers_lines_then_words_then_hard_cut() -> None:
    lines = "\n".join(f"Dòng {i}: " + "x" * 50 for i in range(100))
    chunks = split_text(lines, 500)
    assert all(utf16_len(c) <= 500 for c in chunks)
    assert all(c.startswith("Dòng") for c in chunks)
    assert split_text("a" * 1200, 500) == ["a" * 500, "a" * 500, "a" * 200]
    assert split_text("   ") == []


def test_split_counts_utf16_units() -> None:
    chunks = split_text("😀" * 1500)
    assert [len(c) for c in chunks] == [1000, 500]


def test_markdown_to_plain() -> None:
    md = (
        "# Báo cáo\n\n## Mục tiêu\n- **Toán**: tiến bộ ở _hàm số_\n* Xem [chi tiết](https://m.vn/r)\n\n"
        "| Chủ đề | Xu hướng |\n|---|---|\n| Đạo hàm | tăng |\n\n---\n> ghi chú `x`\n"
    )
    assert markdown_to_plain(md) == (
        "Báo cáo\n\nMục tiêu\n• Toán: tiến bộ ở hàm số\n• Xem chi tiết (https://m.vn/r)\n\n"
        "Chủ đề | Xu hướng\n\nĐạo hàm | tăng\n\nghi chú x"
    )
