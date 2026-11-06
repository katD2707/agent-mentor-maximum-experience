import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

CURRICULUM = """\
subject: math
skills:
  - id: algebra.linear.solve
    title: Giải phương trình bậc nhất
    grade: 9
    prerequisites: []
  - id: algebra.quadratic.formula
    title: Công thức nghiệm phương trình bậc hai
    grade: 10
    prerequisites: [algebra.linear.solve]
  - id: algebra.quadratic.vieta
    title: Định lý Vi-ét
    grade: 10
    prerequisites: [algebra.quadratic.formula]
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    curricula = tmp_path / ".mentor" / "curricula"
    curricula.mkdir(parents=True)
    (curricula / "math.yaml").write_text(CURRICULUM, encoding="utf-8")
    return tmp_path


RunCli = Callable[..., tuple[int, dict[str, Any]]]


@pytest.fixture
def run_cli(workspace: Path) -> RunCli:
    """Run `python -m mentor_scripts.<name>` for real, with the payload on stdin."""

    def _run(name: str, payload: Any, raw: bytes | None = None) -> tuple[int, dict[str, Any]]:
        env = {**os.environ, "WORKSPACE_ROOT": str(workspace)}
        stdin = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", f"mentor_scripts.{name}"],
            input=stdin,
            capture_output=True,
            cwd=workspace,
            env=env,
            timeout=120,
            check=False,  # exit code 1 is part of the protocol under test
        )
        return proc.returncode, json.loads(proc.stdout.decode("utf-8"))

    return _run
