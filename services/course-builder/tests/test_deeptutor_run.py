"""DeepTutor._run: a timeout kills the whole process tree and returns, instead of hanging on inherited pipes."""
import subprocess
import sys

import pytest

from mentor_course_builder import deeptutor
from mentor_course_builder.deeptutor import DeepTutor, DeepTutorError


def _dt(tmp_path, uvx, timeout_s):
    dt = DeepTutor(tmp_path, "https://x/v1", "secret-key", uvx, timeout_s=timeout_s)
    dt._with = lambda: []  # type: ignore[method-assign]
    return dt


def test_timeout_kills_tree_and_returns(tmp_path, monkeypatch):
    script = tmp_path / "fake_uvx.py"
    # the "uvx" starts a grandchild that keeps stdout open and sleeps: the old pipe-based code hung here
    script.write_text("import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\ntime.sleep(60)\n")
    wrapper = tmp_path / ("uvx.cmd" if sys.platform == "win32" else "uvx")
    wrapper.write_text(f'@"{sys.executable}" "{script}"\r\n' if sys.platform == "win32" else f'#!/bin/sh\nexec "{sys.executable}" "{script}"\n')
    wrapper.chmod(0o755)
    dt = _dt(tmp_path, str(wrapper), 3.0)
    with pytest.raises(DeepTutorError, match="timed out"):
        dt._run(["run", "x"])


def test_failure_masks_key(tmp_path, monkeypatch):
    class P:
        pid = 1
        def __init__(self, cmd, stdout=None, stderr=None, **kw):
            stdout.write(b"out secret-key"); stderr.write(b"boom")
        def wait(self, timeout=None):
            return 3
    monkeypatch.setattr(deeptutor.subprocess, "Popen", P)
    with pytest.raises(DeepTutorError) as e:
        _dt(tmp_path, "uvx", 5)._run(["run", "x"])
    assert "secret-key" not in str(e.value) and "failed (3)" in str(e.value)
