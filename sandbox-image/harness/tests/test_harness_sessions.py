"""Chat history persistence: sessions/<date>/<session_id>.jsonl and reload after a restart."""

import json
from pathlib import Path

import httpx
from harness_helpers import FakeScripts, collect, turn_request
from mentor_harness.config import Settings
from mentor_harness.model import ScriptedModel
from mentor_harness.server import create_app
from mentor_harness.workspace import Workspace, ensure_git_safe_directory
from mentor_schemas import Attachment, Profile, TurnRequest


async def post_turn(app, req: TurnRequest) -> str:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sandbox") as client:
        resp = await client.post("/v1/turn", json=req.model_dump(mode="json"))
    assert '"type":"done"' in resp.text
    return resp.text


def chat_records(root: Path, session_id: str = "s-20261028") -> list[dict]:
    files = list((root / "sessions").glob(f"*/{session_id}.jsonl"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


async def test_restart_reloads_history_from_jsonl(ws_root: Path) -> None:
    settings = Settings(workspace_root=ws_root)
    first = ScriptedModel(
        [
            "Chào An!",
            ScriptedModel.call("list_dir", path="me", _id="c1"),
            "Mình đã xem thư mục me/ rồi.",
        ]
    )
    app1 = create_app(settings, model=first, script_runner=FakeScripts())
    await post_turn(app1, turn_request("Em tên An", session_id="s-20261028"))
    await post_turn(app1, turn_request("Xem giúp em thư mục me", session_id="s-20261028"))

    records = chat_records(ws_root)
    assert [(r["role"], r["text"]) for r in records] == [
        ("user", "Em tên An"),
        ("mentor", "Chào An!"),
        ("user", "Xem giúp em thư mục me"),
        ("mentor", "Mình đã xem thư mục me/ rồi."),
    ]
    assert all(set(r) == {"ts", "role", "text", "attachments"} for r in records)
    raw = "".join((ws_root / "sessions").glob("*/s-20261028.jsonl").__next__().read_text(encoding="utf-8"))
    assert "list_dir" not in raw and "tool" not in raw and "Bạn là Mentor." not in raw  # no tools, no prompt

    # "Restart": a new app instance on the same workspace has an empty in-memory session table.
    second = ScriptedModel(["Em tên An mà."])
    app2 = create_app(settings, model=second, script_runner=FakeScripts())
    await post_turn(app2, turn_request("Em tên gì nhỉ?", session_id="s-20261028"))
    msgs = second.calls[0].messages
    assert msgs[0]["role"] == "system"  # context prefix stays first
    assert [(m["role"], m["content"]) for m in msgs[1:]] == [
        ("user", "Em tên An"),
        ("assistant", "Chào An!"),
        ("user", "Xem giúp em thư mục me"),
        ("assistant", "Mình đã xem thư mục me/ rồi."),
        ("user", "Em tên gì nhỉ?"),
    ]
    assert len(chat_records(ws_root)) == 6

    # A different session id starts fresh.
    third = ScriptedModel(["Chào em."])
    app3 = create_app(settings, model=third, script_runner=FakeScripts())
    await post_turn(app3, turn_request("Chào", session_id="s-20261029"))
    assert [m["role"] for m in third.calls[0].messages] == ["system", "user"]


async def test_attachments_recorded_and_restored(make_harness, ws_root: Path) -> None:
    req = TurnRequest(
        session_id="s-20261028",
        user_id="u1",
        profile=Profile.THPT,
        text="Bài kiểm tra của em",
        attachments=[Attachment(path="inbox/kt.jpg", mime_type="image/jpeg")],
    )
    await collect(make_harness(ScriptedModel(["Mình xem nhé."])), req)
    assert chat_records(ws_root)[0]["attachments"] == ["inbox/kt.jpg"]
    model = ScriptedModel(["Ok."])
    await collect(make_harness(model), turn_request("tiếp", session_id="s-20261028"))
    assert "inbox/kt.jpg" in model.calls[0].messages[1]["content"]


async def test_reload_caps_and_tolerates_bad_lines(make_harness, ws: Workspace) -> None:
    records = []
    for i in range(30):
        records.append({"ts": "2026-10-27T10:00:00+07:00", "role": "user", "text": f"u{i}", "attachments": []})
        records.append({"ts": "2026-10-27T10:00:01+07:00", "role": "mentor", "text": f"m{i}", "attachments": []})
    path = ws.root / ws.append_chat("s-x", records[:31])
    ws.append_chat("s-x", records[31:])
    with path.open("a", encoding="utf-8") as f:
        f.write('{"ts": "torn')  # crash mid-write
    model = ScriptedModel(["Ok."])
    await collect(make_harness(model), turn_request("mới", session_id="s-x"))
    history = model.calls[0].messages[1:-1]
    assert len(history) == 40 and history[0] == {"role": "user", "content": "u10"}
    assert history[-1] == {"role": "assistant", "content": "m29"}


def test_git_safe_directory_via_env(monkeypatch) -> None:
    for key in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0", "GIT_CONFIG_KEY_1"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.pager")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "cat")
    ensure_git_safe_directory()
    ensure_git_safe_directory()  # idempotent
    import os

    assert os.environ["GIT_CONFIG_COUNT"] == "2"
    assert os.environ["GIT_CONFIG_KEY_1"] == "safe.directory" and os.environ["GIT_CONFIG_VALUE_1"] == "*"
