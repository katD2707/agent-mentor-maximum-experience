"""DeepTutor (Apache-2.0) as an isolated sidecar: knowledge base, quiz generation, learning path.

DeepTutor is NOT a dependency of our venv. Each call runs `uvx --from deeptutor==1.7.2 deeptutor ...` as a subprocess
with its own home directory (short path under <repo>/var-dev/dt: Windows MAX_PATH broke long paths) and PYTHONUTF8=1.
Never install the `deeptutor_parsing` extra (PyMuPDF is AGPL). DeepTutor's settings file stores the API key in plaintext:
the home must stay under a gitignored directory and the key is never printed or logged here.

Everything is best-effort: every method raises `DeepTutorError` when the sidecar is missing or fails, and callers
(quiz.py) fall back to our own prompts.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mentor_course_builder.llm import _find_env_file, _read_env_file

log = logging.getLogger("mentor_course_builder")

VERSION = "1.7.2"
LLM_MODEL = "fai/Alibaba:DeepSeek-V4.1-Flash"  # real model names only: a made-up fai/ name locks the gateway ~2 min
MODULES = ("deeptutor-knowledge", "deeptutor-questions", "deeptutor-mastery")
OVERRIDDEN = ("pymupdf", "pymupdf4llm", "pymupdf-layout")
EMBED_MODEL = "azure-ai/Cohere-Embed-V5-Fast"


class DeepTutorError(Exception):
    """Sidecar missing, misconfigured, timed out or returned something unusable."""


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and everything it started (uvx -> deeptutor -> python), then reap it."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        else:
            proc.kill()
    except Exception:  # noqa: BLE001 - best effort
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


@dataclass
class RawQuestion:
    """One multiple-choice question as DeepTutor produced it, before mapping to course.QuizItem."""

    stem: str
    options: dict[str, str]  # "A" -> text
    correct: str  # option letter
    explanation: str = ""
    difficulty: str = ""
    concentration: str = ""


@dataclass
class DeepTutor:
    home: Path
    api_base: str = ""
    api_key: str = field(default="", repr=False)
    uvx: str = ""
    timeout_s: float = 420.0
    fails: int = 0  # consecutive failed quiz calls; at `max_fails` the sidecar is skipped for the rest of the build
    max_fails: int = 2

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_env(cls, home: Path | None = None) -> "DeepTutor":
        """Reads FPT_API_BASE / FPT_API_KEY from env or .env.dev.local (same sources as ModelClient direct mode)."""
        base, key = os.environ.get("FPT_API_BASE", ""), os.environ.get("FPT_API_KEY", "")
        f = _find_env_file()
        if not (base and key) and f and f.is_file():
            vals = _read_env_file(f, {"FPT_API_BASE", "FPT_API_KEY"})
            base, key = base or vals.get("FPT_API_BASE", ""), key or vals.get("FPT_API_KEY", "")
        if home is None:
            env = os.environ.get("DEEPTUTOR_HOME")
            home = Path(env) if env else (f.parent if f else Path.cwd()) / "var-dev" / "dt"
        return cls(Path(home), base, key, shutil.which("uvx") or "")

    def available(self) -> bool:
        return bool(self.uvx and self.api_base and self.api_key)

    # ------------------------------------------------------------------ subprocess
    def _with(self) -> list[str]:
        """Base wheel + only the modules we use. `[full]` would add deeptutor-parsing -> PyMuPDF (AGPL), so the
        pymupdf* requirements are overridden away (impossible marker); we only feed markdown, never PDFs."""
        ov = self.home / "overrides.txt"
        ov.parent.mkdir(parents=True, exist_ok=True)
        ov.write_text("".join(f'{p} ; sys_platform == "never"\n' for p in OVERRIDDEN), encoding="utf-8")
        mods = [a for m in MODULES for a in ("--with", f"{m}=={VERSION}")]
        return [*mods, "--overrides", ov.name]  # relative: uv splits absolute paths with spaces; cwd is the home

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        # NLTK_DATA: llama_index's bundled stopwords sit in uv's cache as hardlinks, and nltk>=3.9 refuses
        # multiply-linked files (pathsec, CWE-59); a private copy under the home avoids that on every OS
        env.update(PYTHONUTF8="1", DEEPTUTOR_HOME=str(self.home), FPT_API_KEY=self.api_key, NO_COLOR="1",
                   NLTK_DATA=str(self.home / "nltk_data"))
        return env

    def _run(self, args: list[str], timeout: float | None = None) -> str:
        if not self.available():
            raise DeepTutorError("uvx or FPT_API_BASE/FPT_API_KEY missing")
        cmd = [self.uvx, "--from", f"deeptutor=={VERSION}", *self._with(), "deeptutor", *args]
        # Output goes to temp files, not pipes: uvx starts grandchildren that keep a pipe open after the parent is killed,
        # and subprocess.run(timeout=...) then waits for EOF forever (a build once hung for 30 min on a 7-min timeout).
        with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
            try:
                proc = subprocess.Popen(cmd, env=self._env(), stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, cwd=str(self.home))
            except OSError as exc:
                raise DeepTutorError(f"cannot start deeptutor: {exc}") from exc
            try:
                rc = proc.wait(timeout=timeout or self.timeout_s)
            except subprocess.TimeoutExpired as exc:
                _kill_tree(proc)
                raise DeepTutorError(f"deeptutor {args[0]} timed out") from exc
            fo.seek(0)
            fe.seek(0)
            out, err_raw = fo.read().decode("utf-8", "replace"), fe.read().decode("utf-8", "replace")
        if rc != 0:
            err = (err_raw + out)[-400:].replace(self.api_key, "***")
            raise DeepTutorError(f"deeptutor {args[0]} failed ({rc}): {err}")
        return out

    # ------------------------------------------------------------------ setup
    def setup(self) -> None:
        """Idempotent: `init --cli --non-interactive` then `config apply` (key by env var name, not by value)."""
        self.home.mkdir(parents=True, exist_ok=True)
        if (self.home / ".mcb-configured").is_file():
            return
        self._run(["init", "--cli", "--non-interactive"], timeout=300)
        base = self.api_base.rstrip("/")
        emb = base if base.endswith("/embeddings") else base + "/embeddings"
        cfg = {
            "llm": {"provider": "custom", "api_format": "openai_chat", "base_url": base,
                    "api_key_env": "FPT_API_KEY", "model": LLM_MODEL},
            "embedding": {"provider": "custom", "base_url": emb, "api_key_env": "FPT_API_KEY", "model": EMBED_MODEL},
        }
        f = self.home / "setup.json"
        f.write_text(json.dumps(cfg), encoding="utf-8")  # holds no secret (env var name only)
        self._run(["config", "apply", str(f)], timeout=120)
        (self.home / ".mcb-configured").write_text("ok", encoding="utf-8")

    # ------------------------------------------------------------------ knowledge base
    def create_kb(self, name: str, md_files: list[Path]) -> float:
        """Builds a knowledge base from markdown files. Returns seconds taken."""
        self.setup()
        t = time.time()
        self._run(["kb", "create", name, *[a for f in md_files for a in ("-d", str(f))]], timeout=600)
        return time.time() - t

    # ------------------------------------------------------------------ run helpers
    @staticmethod
    def _events(out: str) -> list[dict[str, Any]]:
        ev = []
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    ev.append(json.loads(line))
                except ValueError:
                    pass
        return ev

    # ------------------------------------------------------------------ quiz
    def quiz(self, topic: str, kb: str, n: int = 3, language: str = "vi") -> list[RawQuestion]:
        """`deep_question` in custom mode, choice questions, RAG over `kb`. Parses only the final result event."""
        if self.fails >= self.max_fails:  # every uvx start costs 20-60 s: do not pay it again and again for a dead sidecar
            raise DeepTutorError("deeptutor skipped: it failed repeatedly in this build")
        self.setup()
        topic = clean_topic(topic)
        cfg = {"mode": "custom", "topic": topic, "num_questions": n, "question_types": ["choice"]}
        args = ["run", "deep_question", topic, "--kb", kb, "-t", "rag", "-l", language,
                "--config-json", json.dumps(cfg, ensure_ascii=False), "-f", "json"]
        last: DeepTutorError | None = None
        for attempt in range(3):  # the FPT gateway drops streams now and then ("incomplete chunked read"); DeepTutor does not retry
            try:
                events = self._events(self._run(args))
            except DeepTutorError:  # the process itself failed or timed out: retrying would only repeat the wait
                self.fails += 1
                raise
            try:
                got = parse_quiz_events(events)
                self.fails = 0
                return got
            except DeepTutorError as exc:
                err = next((e.get("content") for e in events if e.get("type") == "error" and e.get("content")), "")
                last = DeepTutorError(f"{exc}: {str(err)[:150]}")
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        self.fails += 1
        raise last or DeepTutorError("deep_question failed")

    # ------------------------------------------------------------------ learning path
    def mastery_path(self, kb: str, goal: str, language: str = "vi") -> dict[str, Any]:
        """`mastery_path`: returns the arguments of the mastery_build tool call (lessons + knowledge points)."""
        self.setup()
        out = self._run(["run", "mastery_path", goal, "--kb", kb, "-t", "rag", "-l", language, "-f", "json"])
        return parse_mastery_events(self._events(out))


def clean_topic(topic: str) -> str:
    """Plain topic words (no punctuation, at most 8 words): keeps the CLI argument and the retrieval query simple."""
    t = "".join(" " if c in "?!:;\"'`$\\" else c for c in topic)
    return " ".join(t.split()[:8])


def parse_quiz_events(events: list[dict[str, Any]]) -> list[RawQuestion]:
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if result is None:
        raise DeepTutorError("deep_question returned no result event")
    meta = result.get("metadata") or result
    summary = meta.get("summary") or result.get("summary") or {}
    out: list[RawQuestion] = []
    for it in summary.get("results") or []:
        qa = it.get("qa_pair") or it
        opts = qa.get("options") or {}
        if isinstance(opts, list):
            opts = {chr(65 + i): str(o) for i, o in enumerate(opts)}
        stem = (qa.get("question") or "").strip()
        ans = str(qa.get("correct_answer") or "").strip()[:1].upper()
        opts = {str(k).strip().upper()[:1]: str(v) for k, v in opts.items()}
        if stem and len(opts) >= 2 and ans in opts:
            out.append(RawQuestion(stem, opts, ans, (qa.get("explanation") or "").strip(),
                                   str(qa.get("difficulty") or ""), str(qa.get("concentration") or "")))
    return out


def parse_mastery_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Arguments of the last `mastery_build` tool call: {"path_name", "modules": [{"name", "objective",
    "knowledge_points": [{"client_ref", "name", "type", "prerequisite_refs"?}]}]}."""
    for e in reversed(events):
        if e.get("type") == "tool_call" and e.get("content") == "mastery_build":
            args = (e.get("metadata") or {}).get("args")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    continue
            if isinstance(args, dict) and args.get("modules"):
                return args
    raise DeepTutorError("no mastery_build call found")
