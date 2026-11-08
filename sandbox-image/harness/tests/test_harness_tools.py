"""Tool-level tests: permissions, traversal, edit uniqueness, validation hooks, caps, scripts, outbox."""

import json
import subprocess
from pathlib import Path

import pytest
from harness_helpers import FakeScripts, activity_lines
from mentor_harness import scripts as scripts_mod
from mentor_harness.config import Settings
from mentor_harness.model import ScriptedModel
from mentor_harness.scripts import ScriptError, run_mentor_script
from mentor_harness.tools import TOOLS, ToolContext, execute, tool_specs
from mentor_harness.workspace import Workspace
from mentor_schemas import ModelAlias, OutboxKind, Profile


def make_ctx(
    ws: Workspace,
    profile: Profile = Profile.STUDENT,
    model: ScriptedModel | None = None,
    runner=None,
    **settings,
) -> ToolContext:
    return ToolContext(
        ws=ws,
        profile=profile,
        model=model or ScriptedModel(),
        settings=Settings(workspace_root=ws.root, **settings),
        script_runner=runner or FakeScripts(),
        session_id="s1",
    )


@pytest.mark.parametrize(
    "path",
    ["AGENTS.md", ".mentor/activity.jsonl", "events.jsonl", "sessions/2026-10-28/s1.md", ".git/config",
     "../outside.md", "/etc/passwd", "C:/Windows/x.md", "me/../AGENTS.md", "random.md", "me/sub/deep.md"],
)  # fmt: skip
async def test_write_permission_denied(ws: Workspace, path: str) -> None:
    ctx = make_ctx(ws)
    before = (ws.root / "AGENTS.md").read_text(encoding="utf-8")
    res = await execute(ctx, "write_file", {"path": path, "content": "hacked"})
    assert res.is_error and res.content.startswith("LỖI")
    assert (ws.root / "AGENTS.md").read_text(encoding="utf-8") == before
    assert not (ws.root.parent / "outside.md").exists()
    for tool in ("edit_file", "delete_file"):
        res = await execute(ctx, tool, {"path": path, "old": "Mentor", "new": "x"})
        assert res.is_error
    assert activity_lines(ws.root) == []


async def test_read_rejects_traversal_and_git(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    (ws.root.parent / "secret.txt").write_text("secret", encoding="utf-8")
    for path in ("../secret.txt", ".git/config", "/etc/hosts"):
        res = await execute(ctx, "read_file", {"path": path})
        assert res.is_error, path
    listing = await execute(ctx, "list_dir", {"path": "."})
    assert ".git" not in listing.content and "me/" in listing.content


async def test_read_file_offset_limit_and_cap(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    (ws.root / "learning").mkdir()
    (ws.root / "learning/long.md").write_text("\n".join(f"line {i}" for i in range(1, 1001)), encoding="utf-8")
    res = await execute(ctx, "read_file", {"path": "learning/long.md", "offset": 10, "limit": 5})
    assert res.content.splitlines()[:5] == [f"line {i}" for i in range(10, 15)]
    assert "offset=15" in res.content
    (ws.root / "learning/huge.md").write_text("x" * 200_000, encoding="utf-8")
    res = await execute(ctx, "read_file", {"path": "learning/huge.md"})
    assert len(res.content) < 61_000 and "đã cắt" in res.content


async def test_grep_matches_and_caps(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    res = await execute(ctx, "grep", {"pattern": "Toán"})
    assert "me/now.md:3:" in res.content and "goals/goals.md:2:" in res.content
    (ws.root / "research").mkdir()
    (ws.root / "research/many.md").write_text("hit\n" * 1000, encoding="utf-8")
    res = await execute(ctx, "grep", {"pattern": "^hit$", "path": "research"})
    assert res.content.count("research/many.md:") == 200 and "bị cắt" in res.content
    bad = await execute(ctx, "grep", {"pattern": "("})
    assert bad.is_error


async def test_write_file_creates_and_logs(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    res = await execute(ctx, "write_file", {"path": "me/people.md", "content": "# people\n- Cô Lan dạy Toán.\n"})
    assert not res.is_error
    assert "Cô Lan" in (ws.root / "me/people.md").read_text(encoding="utf-8")
    entry = json.loads(activity_lines(ws.root)[-1])
    assert entry["action"] == "write_file" and entry["target"] == "me/people.md" and entry["actor"] == "mentor"
    assert "tạo" in entry["summary"]


async def test_edit_file_requires_unique_match(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    (ws.root / "me/what-works.md").write_text("- a\n- b\n- a\n", encoding="utf-8")
    missing = await execute(ctx, "edit_file", {"path": "me/what-works.md", "old": "- z", "new": "- y"})
    assert missing.is_error and "Không tìm thấy" in missing.content
    dup = await execute(ctx, "edit_file", {"path": "me/what-works.md", "old": "- a", "new": "- y"})
    assert dup.is_error and "2 lần" in dup.content
    ok = await execute(ctx, "edit_file", {"path": "me/what-works.md", "old": "- b", "new": "- c"})
    assert not ok.is_error
    assert (ws.root / "me/what-works.md").read_text(encoding="utf-8") == "- a\n- c\n- a\n"


async def test_edit_file_many_edits_in_one_call(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    path = "me/now.md"
    before = (ws.root / path).read_text(encoding="utf-8")
    res = await execute(
        ctx,
        "edit_file",
        {
            "path": path,
            "edits": [
                {"old": "# now.md", "new": "# now.md — cập nhật 2026-10-28"},
                {"old": "## Tuần này\n", "new": "## Tuần này\n- Học thêm Anh thứ Ba. (chat 28/10)\n"},
                {"old": "Học thêm Anh thứ Ba", "new": "Học thêm Anh thứ Ba, thứ Năm"},  # sees the earlier edit
            ],
        },
    )
    assert not res.is_error and "3 chỗ" in res.content
    text = (ws.root / path).read_text(encoding="utf-8")
    assert text.startswith("# now.md — cập nhật 2026-10-28\n## Tuần này\n- Học thêm Anh thứ Ba, thứ Năm. (chat 28/10)")
    assert "Thi giữa kỳ Toán" in text and text != before
    edits = [json.loads(line) for line in activity_lines(ws.root) if '"edit_file"' in line]
    assert len(edits) == 1  # one write, one activity entry


async def test_edit_file_many_edits_all_or_nothing(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    path = "me/now.md"
    before = (ws.root / path).read_text(encoding="utf-8")
    bad = await execute(
        ctx,
        "edit_file",
        {"path": path, "edits": [{"old": "# now.md", "new": "# NOW"}, {"old": "không có", "new": "x"}]},
    )
    assert bad.is_error and "edits[2]" in bad.content and "Chưa ghi gì" in bad.content
    assert (ws.root / path).read_text(encoding="utf-8") == before
    for args in (
        {"path": path, "edits": []},
        {"path": path, "edits": "old=new"},
        {"path": path, "edits": [{"old": "# now.md"}]},
        {"path": path, "edits": [{"old": "# now.md", "new": "x"}], "old": "# now.md", "new": "y"},
        {"path": path},
    ):
        res = await execute(ctx, "edit_file", args)
        assert res.is_error, args
    assert (ws.root / path).read_text(encoding="utf-8") == before
    denied = await execute(ctx, "edit_file", {"path": "AGENTS.md", "edits": [{"old": "Mentor", "new": "X"}]})
    assert denied.is_error and "Không có quyền" in denied.content


async def test_delete_file_logs_without_content(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    res = await execute(ctx, "delete_file", {"path": "me/journal/2026-10-24.md"})
    assert not res.is_error and not (ws.root / "me/journal/2026-10-24.md").exists()
    entry = json.loads(activity_lines(ws.root)[-1])
    assert entry["action"] == "delete_file" and "journal 24" not in entry["summary"]


async def test_routines_yaml_validated(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    bad = await execute(ctx, "write_file", {"path": "routines.yaml", "content": "routines:\n  - id: x\n"})
    assert bad.is_error and "RoutinesFile" in bad.content
    assert not (ws.root / "routines.yaml").exists()
    good = (
        "proactivity: normal\nroutines:\n  - id: nightly_reflection\n    cron: '30 23 * * *'\n"
        "    job_kind: nightly_reflection\n"
    )
    assert not (await execute(ctx, "write_file", {"path": "routines.yaml", "content": good})).is_error
    broken_edit = await execute(ctx, "edit_file", {"path": "routines.yaml", "old": "normal", "new": "loud"})
    assert broken_edit.is_error
    assert "normal" in (ws.root / "routines.yaml").read_text(encoding="utf-8")


async def test_run_script_uses_runner_and_allowlist(ws: Workspace) -> None:
    out = {"correct": True, "expected": "x=2", "detail": "", "verified": True}  # extra fields pass through
    runner = FakeScripts({"sympy_check": out})
    ctx = make_ctx(ws, runner=runner)
    payload = {"kind": "solve", "problem": "x-2=0", "answer": "2"}
    res = await execute(ctx, "run_script", {"name": "sympy_check", "input": payload})
    assert json.loads(res.content) == out
    assert runner.calls == [("sympy_check", payload, ws.root)]
    assert (await execute(ctx, "run_script", {"name": "os_system", "input": {}})).is_error
    runner.responses["bkt_update"] = ScriptError("curriculum missing")
    failed = await execute(ctx, "run_script", {"name": "bkt_update", "input": {"subject": "math"}})
    assert failed.is_error and "curriculum missing" in failed.content
    assert (await execute(ctx, "run_script", {"name": "record_wellbeing", "input": {}})).is_error  # removed script


async def test_default_runner_invokes_module_with_json_stdin(ws: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(cmd=cmd, **kw)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"event_id": "e1"}', stderr="")

    monkeypatch.setattr(scripts_mod.subprocess, "run", fake_run)
    out = await run_mentor_script("record_event", {"subject": "math"}, ws.root, 5)
    assert out == {"event_id": "e1"}
    assert seen["cmd"][1:] == ["-m", "mentor_scripts.record_event"]
    assert Path(seen["cwd"]) == ws.root and json.loads(seen["input"]) == {"subject": "math"}
    assert seen["env"]["WORKSPACE_ROOT"] == str(ws.root) and seen["timeout"] == 5

    def failing(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout='{"error": "invalid skill_id"}', stderr="")

    monkeypatch.setattr(scripts_mod.subprocess, "run", failing)
    with pytest.raises(ScriptError, match="invalid skill_id"):
        await run_mentor_script("record_event", {}, ws.root, 5)

    def hanging(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(scripts_mod.subprocess, "run", hanging)
    with pytest.raises(ScriptError, match="quá 30s"):
        await run_mentor_script("sympy_check", {}, ws.root, 30)
    with pytest.raises(ScriptError):
        await run_mentor_script("not_allowed", {}, ws.root, 5)
    assert Settings(workspace_root=ws.root).script_timeout_s == 30


async def test_look_at_image_sends_data_url_to_vision(ws: Workspace) -> None:
    (ws.root / "inbox").mkdir()
    (ws.root / "inbox/test.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    model = ScriptedModel(["Bài kiểm tra 15 phút, câu 2 sai dấu."])
    ctx = make_ctx(ws, model=model)
    res = await execute(ctx, "look_at_image", {"path": "inbox/test.png", "question": "Đây là gì?"})
    assert "câu 2" in res.content
    call = model.calls[0]
    assert call.alias == ModelAlias.VISION
    image_part = call.messages[0]["content"][1]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert ctx.usage[ModelAlias.VISION.value] == 10


async def test_notify_and_schedule_wake_add_outbox(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    await execute(ctx, "notify_user", {"text": "Mai thi Toán, nhớ ngủ sớm nhé."})
    wake = {"at": "2099-01-01T07:30:00+07:00", "job_kind": "routine", "prompt": "ôn bài"}
    res = await execute(ctx, "schedule_wake", wake)
    assert not res.is_error
    assert [o.kind for o in ctx.outbox] == [OutboxKind.NOTIFY_USER, OutboxKind.NEXT_WAKE]
    assert ctx.outbox[1].payload["job_kind"] == "routine" and ctx.outbox[1].payload["prompt"] == "ôn bài"
    assert (await execute(ctx, "schedule_wake", {"at": "2000-01-01T00:00:00", "job_kind": "routine"})).is_error
    assert (await execute(ctx, "schedule_wake", {"at": "2099-01-01T00:00:00", "job_kind": "party"})).is_error
    actions = [json.loads(line)["action"] for line in activity_lines(ws.root)]
    assert actions == ["notify_user", "schedule_wake"]


async def test_notify_user_rich_fields(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    args = {"text": "3 việc hôm nay: ôn hàm số, đọc 1 bài, nghỉ sớm.", "kind": "checkin", "title": "Chào buổi sáng",
            "actions": [{"id": "answer:ok", "label": "Chốt"}, {"id": "snooze_1h", "label": "Để sau"}],
            "mascot": "wave", "prefill": "Mình muốn đổi kế hoạch"}
    res = await execute(ctx, "notify_user", args)
    assert not res.is_error, res.content
    payload = ctx.outbox[-1].payload
    assert payload["kind"] == "checkin" and payload["title"] == "Chào buổi sáng" and payload["mascot"] == "wave"
    assert payload["actions"][0] == {"id": "answer:ok", "label": "Chốt"} and payload["text"].startswith("3 việc")
    bad = dict(args, actions=[{"id": "rm -rf", "label": "x"}])
    assert (await execute(ctx, "notify_user", bad)).is_error
    four = dict(args, actions=[{"id": f"answer:{i}", "label": str(i)} for i in range(4)])
    assert (await execute(ctx, "notify_user", four)).is_error


async def test_move_file_binary_safe_and_logged(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    data = bytes(range(256)) * 10
    (ws.root / "inbox").mkdir()
    (ws.root / "inbox/scan.jpg").write_bytes(data)
    res = await execute(ctx, "move_file", {"src": "inbox/scan.jpg", "dst": "learning/evidence/scans/2026-10-25.jpg"})
    assert not res.is_error, res.content
    assert (ws.root / "learning/evidence/scans/2026-10-25.jpg").read_bytes() == data
    assert not (ws.root / "inbox/scan.jpg").exists()
    entry = json.loads(activity_lines(ws.root)[-1])
    assert entry["action"] == "move_file" and entry["target"] == "learning/evidence/scans/2026-10-25.jpg"


async def test_move_file_permissions_and_conflicts(ws: Workspace) -> None:
    ctx = make_ctx(ws)
    (ws.root / "inbox").mkdir()
    (ws.root / "inbox/a.md").write_text("a", encoding="utf-8")
    for src, dst in (
        ("AGENTS.md", "me/agents.md"),  # read-only source
        ("inbox/a.md", ".mentor/skills/x.md"),  # read-only destination
        ("inbox/a.md", "../escape.md"),
        ("inbox/missing.md", "me/x.md"),
        ("inbox/a.md", "me/now.md"),  # destination exists
    ):
        res = await execute(ctx, "move_file", {"src": src, "dst": dst})
        assert res.is_error, (src, dst)
    assert (ws.root / "inbox/a.md").exists() and (ws.root / "AGENTS.md").exists()
    assert activity_lines(ws.root) == []


def test_tool_specs_match_contract() -> None:
    contract = {
        "read_file": {"path", "offset", "limit"},
        "list_dir": {"path"},
        "grep": {"pattern", "path"},
        "write_file": {"path", "content"},
        "edit_file": {"path", "old", "new", "edits"},
        "delete_file": {"path"},
        "move_file": {"src", "dst"},
        "run_script": {"name", "input"},
        "look_at_image": {"path", "question"},
        "notify_user": {"text", "kind", "title", "actions", "mascot", "prefill"},
        "schedule_wake": {"at", "job_kind", "prompt"},
        "request_approval": {"action", "summary", "details"},
        "suggest_replies": {"items"},
        "show_card": {"kind", "data"},
        "start_focus": {"task", "minutes"},
        "celebrate": {"title", "detail"},
    }
    specs = {s["function"]["name"]: s["function"] for profile in Profile for s in tool_specs(profile, is_turn=True)}
    assert set(specs) == set(contract)
    for name, args in contract.items():
        assert set(specs[name]["parameters"]["properties"]) == args, name
    assert set(TOOLS) >= set(contract)


def test_profile_tool_sets() -> None:
    for profile in Profile:
        names = {s["function"]["name"] for s in tool_specs(profile, is_turn=True)}
        assert not names & {"flag_crisis", "send_parent_report", "run_python", "web_search", "paper_search"}
    job_names = {s["function"]["name"] for s in tool_specs(Profile.STUDENT, is_turn=False)}
    assert "request_approval" not in job_names
