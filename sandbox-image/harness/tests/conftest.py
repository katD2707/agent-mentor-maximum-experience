"""Fixtures: a small provisioned workspace in tmp_path, a fake script runner, harness builders."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from harness_helpers import FILES, FakeScripts, git
from mentor_harness.agent import Harness
from mentor_harness.config import Settings
from mentor_harness.model import ScriptedModel
from mentor_harness.workspace import Workspace
from mentor_schemas import Profile


@pytest.fixture
def ws_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    for rel, content in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "-c", "user.name=system", "-c", "user.email=system@local", "commit", "-q", "-m", "provision")
    return root


@pytest.fixture
def ws(ws_root: Path) -> Workspace:
    return Workspace(ws_root)


@pytest.fixture
def scripts() -> FakeScripts:
    return FakeScripts()


@pytest.fixture
def make_harness(ws_root: Path, scripts: FakeScripts) -> Callable[..., Harness]:
    def build(model: ScriptedModel, profile: Profile | None = None, **overrides: Any) -> Harness:
        settings = Settings(workspace_root=ws_root, profile=profile, **overrides)
        return Harness(settings, model, script_runner=scripts)

    return build
