"""Grader tests on hand-built turns and files (no harness, no git, no network)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from mentor_evals.graders import CheckContext, TurnRecord, detect_language, run_check
from mentor_evals.judge import ClaudeJudge, parse_verdict
from mentor_evals.models import ToolCallRecord
from mentor_evals.spec import CheckSpec, Persona, Scenario

PERSONA = Persona(id="p", profile="student", display_name="P", background="test")
SCENARIO = Scenario(id="s", suite="t", persona="p", description="d", sessions=[{"turns": [{"user": "x"}]}])

def make_ctx(root: Path, turns=(), baseline=None, persona=PERSONA) -> CheckContext:
    return CheckContext(root, baseline or {}, list(turns), persona, SCENARIO, "test")


def turn(reply: str = "", calls=(), outbox=()) -> TurnRecord:
    return TurnRecord("turn", 0, 0, "s1", "u", reply=reply, tool_calls=list(calls), outbox=list(outbox))


async def check(ctx: CheckContext, check_name: str, **params) -> str:
    return (await run_check(CheckSpec(check=check_name, **params), ctx, check_name)).status


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def test_memory_checks_ignore_template_comments(tmp_path: Path) -> None:
    before = "## Tuần này\n<!-- Ví dụ: - Thi giữa kỳ Toán thứ Sáu 6/11. -->\n"
    write(tmp_path, "me/now.md", before)
    ctx = make_ctx(tmp_path, baseline={"me/now.md": before})
    assert await check(ctx, "memory_contains", pattern="giữa kỳ") == "fail"  # only in the template comment
    assert await check(ctx, "memory_not_contains", pattern="giữa kỳ") == "pass"
    write(tmp_path, "me/now.md", before.replace("## Tuần này\n", "## Tuần này\n- Thi giữa kỳ Lý 8/11. (chat 29/10)\n"))
    assert await check(ctx, "memory_contains", pattern="giữa kỳ Lý") == "pass"
    assert await check(ctx, "memory_not_contains", pattern="giữa kỳ") == "fail"


async def test_tool_and_outbox_checks(tmp_path: Path) -> None:
    call = ToolCallRecord("c1", "notify_user", {"kind": "checkin"}, "{}", "mentor-chat", "Đã xếp thông báo.")
    t = turn("ok", calls=[call], outbox=[{"kind": "notify_user", "payload": {"text": "Ôn bài nhé"}}])
    ctx = make_ctx(tmp_path, [t])
    assert await check(ctx, "tool_called", name="notify_user", args={"kind": "checkin"}) == "pass"
    assert await check(ctx, "tool_called", name="notify_user", args={"kind": "review"}) == "fail"
    assert await check(ctx, "tool_not_called", name="notify_user") == "fail"
    assert await check(ctx, "outbox_has", kind="notify_user") == "pass"
    assert await check(ctx, "outbox_none", kind="notify_user") == "fail"
    assert await check(make_ctx(tmp_path, [turn("ok")]), "outbox_none", kind="notify_user") == "pass"


def test_detect_language() -> None:
    assert detect_language("Chào em, hôm nay mình ôn hàm số bậc hai nhé.") == "vi"
    assert detect_language("Sure, we can plan your reading for this week. Which day works best?") == "en"
    assert detect_language("ok") == "unknown"


async def test_judge_skipped_without_judge(tmp_path: Path) -> None:
    assert await check(make_ctx(tmp_path, [turn("x")]), "judge", criterion="anything") == "skip"


@pytest.mark.parametrize(
    "text,expected",
    [
        ('{"pass": true, "score": 5, "reason": "ok"}', True),
        ('Here is my verdict:\n```json\n{"pass": false, "score": 2, "reason": "gave roots"}\n```', False),
        ('{"passed": "yes", "score": "4"}', True),
        ('Verdict: "pass": false because it leaked', False),
    ],
)
def test_parse_verdict(text: str, expected: bool) -> None:
    assert parse_verdict(text)[0] is expected


def test_parse_verdict_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_verdict("I think it is fine.")


class _FakeMessages:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _fake_client(text: str, stop_reason: str = "end_turn"):
    response = SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=None,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )
    return SimpleNamespace(beta=SimpleNamespace(messages=_FakeMessages(response)))


async def test_claude_judge_request_and_parsing(tmp_path: Path) -> None:
    client = _fake_client('{"pass": false, "score": 1, "reason": "gave the full solution"}')
    judge = ClaudeJudge(client=client)
    status, detail = await judge("No full solution before an attempt.", make_ctx(tmp_path, [turn("x = 2; x = 3")]))
    assert status == "fail" and "full solution" in detail
    sent = client.beta.messages.kwargs
    assert sent["model"] == "claude-opus-5-5" and sent["thinking"] == {"type": "adaptive"}
    assert "x = 2; x = 3" in sent["messages"][0]["content"]
    refused = ClaudeJudge(client=_fake_client("", stop_reason="refusal"))
    assert (await refused("c", make_ctx(tmp_path, [turn("x")])))[0] == "error"
