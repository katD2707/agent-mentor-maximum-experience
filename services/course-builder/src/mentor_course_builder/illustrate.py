"""Covers, in-lesson illustrations, object pictures and computed diagrams (REQUIREMENTS-PLAN §13: SVG by DeepSeek).

Method adapted from the `anthropics/skills@canvas-design` skill (Apache-2.0): first state a short visual idea (its
"design philosophy" step, shrunk to 2-3 sentences), then express it as the artwork. Covers/illustrations/pictures are
SVG with NO text; diagrams are produced by a small model-written Python script that computes the geometry exactly and
prints SVG (run in a subprocess with a timeout, AST-restricted). Covers and illustrations are rasterised with headless
Chrome and saved as WebP, then get ONE vision self-critique round (mentor-vision) with a single regeneration.
"""

from __future__ import annotations

import ast
import atexit
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Callable

from mentor_schemas import ModelAlias

from mentor_course_builder.contracts import MediaFile, MediaRequest, MediaResult
from mentor_course_builder.jsonparse import parse_model_json
from mentor_course_builder.llm import ModelClient, ModelError, image_part
from mentor_course_builder.media import MediaError

log = logging.getLogger("mentor_course_builder")

PALETTE = """Palette (use ONLY these, flat fills, no gradients except the paper grain):
  paper cream #F7F1E3 (background), purple ink #5A4BC0 (main shapes and outlines), ink wash #E9E5F6,
  highlighter yellow #F0D76E, coral #E8806A, mint #9FD8BF, night ink #2B283F (thin details only).
  Add a soft paper grain over the whole picture: <filter id="grain"><feTurbulence type="fractalNoise"
  baseFrequency="0.8" numOctaves="2" seed="3"/><feColorMatrix values="0 0 0 0 0.35 0 0 0 0 0.3 0 0 0 0 0.5 0 0 0 0.10 0"/>
  </filter> applied to a full-size <rect filter="url(#grain)"/> as the last element. Rounded line caps and joins."""

SUBJECT_RECIPES = {
    "physics": "Show the concept with field-line arcs between charges: charges are circles (coral = positive, purple = "
               "negative) with a clean plus or minus glyph drawn from two <rect> bars (never text, never a blob); "
               "field lines are smooth cubic curves with small arrowheads; leave breathing space.",
    "maths": "Use COUNTABLE objects: 3-10 identical, clearly separated simple shapes (apples, stars, blocks) grouped in "
             "rows or a ten-frame, each fully visible and not overlapping, so a child could count them.",
    "statistics": "Show curves: a smooth bell curve or two overlapping distributions filled with translucent colour on a "
                  "faint grid, a few dots under the curve; no axis labels.",
    "default": "Draw one clear, simple, memorable scene or object that explains the idea at a glance.",
}


def subject_recipe(subject: str) -> str:
    s = subject.lower()
    if any(k in s for k in ("vật lí", "vật lý", "physic", "điện", "electric", "lực", "force")):
        return SUBJECT_RECIPES["physics"]
    if any(k in s for k in ("toán", "math", "số", "number", "count")):
        return SUBJECT_RECIPES["maths"]
    if any(k in s for k in ("thống kê", "xác suất", "statist", "probab", "bayes")):
        return SUBJECT_RECIPES["statistics"]
    return SUBJECT_RECIPES["default"]


SVG_SYSTEM = """You are a master illustrator who writes hand-crafted SVG. Work in two steps, like a designer who first
names the visual idea and then executes it with painstaking craft:
1. IDEA: two or three sentences naming the single visual idea, the composition and the colour roles.
2. Then ONE ```svg code block with the full artwork.
Rules: root <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"> without width/height; no <text>, <tspan>,
letters, digits or any typography in the artwork (the picture must work without words); no <script>, no <image>, no
external references, no <foreignObject>; at most ~120 elements; shapes must be balanced, with generous margins (keep
10% free at every edge) and one clear focal point; the style is a warm flat illustration, like a school notebook come
to life. {palette}"""

DIAGRAM_SYSTEM = """You write a small, self-contained Python 3 script that PRINTS one SVG document to stdout and computes
the geometry exactly (for example RK4 integration of field lines, exact parabola points, exact ticks). First write a
line starting with IDEA: (one or two sentences), then ONE ```python code block.
Script rules: standard library only, and only these imports: math, cmath, random (seeded), itertools, functools,
statistics, fractions, collections, colorsys. No file, network, process or environment access; no open(), exec(),
eval(), input(); finish in under 10 seconds. Output is the SVG text via print(). Canvas viewBox="0 0 {w} {h}" with no
width/height attributes. Use the palette below. Text IS allowed in diagrams, only for the given labels, in
font-family="Lexend, sans-serif" with font-size >= 26; every label must sit clear of all lines and shapes (offset the
anchor away from the geometry, and add a paper-coloured stroke halo: stroke="#F7F1E3" stroke-width="6"
paint-order="stroke"); labels must not overlap each other; plus/minus signs on charges are drawn as <rect> bars.
Keep the script short (under 80 lines, simple fixed-step RK4 or closed-form curves): do not deliberate at length.
{palette}"""

REVISE_SYSTEM = """You edit an existing SVG for a teacher's comment. Change only what the comment asks, around the given
point (coordinates in the viewBox), keep everything else byte-identical, keep the same rules (no <text> unless the
original had labels, no scripts, no external references). Reply with ONE ```svg code block containing the whole
updated SVG, and nothing else."""

CRITIQUE_PROMPT = """You review a children's-school illustration. List concrete DEFECTS only. Check: (1) any text, letters
or digits visible; (2) charge/plus/minus glyphs that are blobs instead of clean symbols; (3) clutter or overlapping
objects that cannot be told apart or counted; (4) elements cut off at the edges or lines crossing the focal point;
(5) the picture does not show the stated subject: "{subject}". Reply JSON only:
{{"ok": true|false, "defects": ["short fix instruction", ...]}}. ok=true if there is no defect that would embarrass a teacher."""


# --------------------------------------------------------------------------------------------------- SVG hygiene

_FORBIDDEN_TAGS = {"script", "foreignobject", "image", "iframe", "animate", "set", "style"}


def extract_block(raw: str, lang: str) -> tuple[str, str]:
    """(idea, code) from a reply with `IDEA: ...` and a fenced block. Falls back to a bare <svg> element."""
    m = re.search(rf"```(?:{lang})?\s*\n(.*?)(?:```|\Z)", raw, re.S | re.I)
    code = m.group(1).strip() if m else ""
    if not code and lang == "svg":
        m2 = re.search(r"<svg\b.*</svg>", raw, re.S)
        code = m2.group(0) if m2 else ""
    idea = raw[: m.start()] if m else raw
    idea = re.sub(r"^\s*(IDEA|VISUAL IDEA|1\.)\s*[:.]?\s*", "", idea.strip(), flags=re.I).strip()
    return idea[:600], code


def validate_svg(svg: str, *, allow_text: bool, max_bytes: int = 250_000) -> str | None:
    """None when OK, else a one-line problem for the model to fix."""
    if len(svg.encode()) > max_bytes:
        return "SVG too large; simplify (fewer elements)"
    if "<!DOCTYPE" in svg or "<!ENTITY" in svg:
        return "DOCTYPE/ENTITY is not allowed"
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        return f"invalid XML: {exc}"
    if not root.tag.endswith("}svg") and root.tag != "svg":
        return "root element must be <svg>"
    if not root.get("viewBox"):
        return "missing viewBox"
    count = 0
    for el in root.iter():
        tag = el.tag.split("}")[-1].lower()
        count += 1
        if tag in _FORBIDDEN_TAGS:
            return f"<{tag}> is not allowed"
        if tag in ("text", "tspan", "textpath") and not allow_text:
            return "the artwork must contain no <text>: draw everything with shapes"
        for k, v in el.attrib.items():
            kl = k.split("}")[-1].lower()
            if kl.startswith("on"):
                return f"event attribute {kl} is not allowed"
            if kl == "href" and not v.startswith("#"):
                return "external href is not allowed"
            if "url(" in v and "url(#" not in v:
                return "external url() is not allowed"
    if count < 4:
        return "SVG is nearly empty"
    return None


_ALLOWED_IMPORTS = {"math", "cmath", "random", "itertools", "functools", "statistics", "fractions", "collections",
                    "colorsys"}
_BANNED_NAMES = {"open", "exec", "eval", "compile", "input", "__import__", "globals", "locals", "getattr", "setattr",
                 "delattr", "vars", "breakpoint", "memoryview"}


def validate_script(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"Python syntax error: {exc}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _ALLOWED_IMPORTS:
                    return f"import {a.name} is not allowed"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _ALLOWED_IMPORTS or node.level:
                return f"import from {node.module} is not allowed"
        elif isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            return f"{node.id} is not allowed"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return "dunder attributes are not allowed"
    return None


def run_diagram_script(code: str, timeout_s: float = 20.0) -> str:
    """Run the model's script in a throwaway dir (isolated interpreter, scrubbed env, timeout); return stdout (the SVG)."""
    bad = validate_script(code)
    if bad:
        raise MediaError(bad)
    env = {k: v for k, v in os.environ.items() if k in ("SYSTEMROOT", "PATH", "TEMP", "TMP")}
    env["PYTHONUTF8"] = "1"
    with tempfile.TemporaryDirectory(prefix="mcb-diagram-") as d:
        script = Path(d) / "diagram.py"
        script.write_text(code, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-I", str(script)], cwd=d, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise MediaError("diagram script timed out") from None
    if r.returncode != 0:
        raise MediaError(f"diagram script failed: {r.stderr.strip()[-300:]}")
    out = r.stdout.strip()
    m = re.search(r"<svg\b.*</svg>", out, re.S)
    if not m:
        raise MediaError("diagram script printed no <svg>")
    return m.group(0)


# --------------------------------------------------------------------------------------------------- rasterising

def find_chrome() -> str | None:
    cand = os.environ.get("CHROME_BIN")
    if cand and Path(cand).is_file():
        return cand
    for p in ("C:/Program Files/Google/Chrome/Application/chrome.exe",
              "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
              "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if Path(p).is_file():
            return p
    return shutil.which("chrome") or shutil.which("chromium") or shutil.which("google-chrome")


class _ChromeSession:
    """One long-lived headless Chrome driven over CDP; every rasterisation opens a tab, screenshots, closes it."""

    def __init__(self, chrome: str) -> None:
        self._dir = tempfile.mkdtemp(prefix="mcb-chrome-")
        self._proc = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--remote-debugging-port=0",
             f"--user-data-dir={Path(self._dir) / 'profile'}", "--force-device-scale-factor=1", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self._dir) / "profile" / "DevToolsActivePort"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                break
            if port_file.is_file() and port_file.read_text().strip():
                self.port = int(port_file.read_text().split()[0])
                return
            time.sleep(0.1)
        self.close()
        raise MediaError("headless Chrome did not start a DevTools endpoint")

    def screenshot(self, url: str, width: int, height: int, timeout_s: float) -> bytes:
        import base64
        import json as _json
        import urllib.request

        from websockets.sync.client import connect

        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:
            tab = _json.loads(r.read())
        try:
            with connect(tab["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024, open_timeout=10) as ws:
                seq = [0]

                def call(method: str, params: dict | None = None) -> dict:
                    seq[0] += 1
                    ws.send(_json.dumps({"id": seq[0], "method": method, "params": params or {}}))
                    end = time.monotonic() + timeout_s
                    while True:
                        msg = _json.loads(ws.recv(timeout=max(0.1, end - time.monotonic())))
                        if msg.get("id") == seq[0]:
                            if "error" in msg:
                                raise MediaError(f"Chrome: {msg['error'].get('message')}")
                            return msg.get("result", {})

                call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
                call("Page.enable")
                call("Page.navigate", {"url": url})
                end = time.monotonic() + timeout_s
                while True:  # wait for the load event
                    msg = _json.loads(ws.recv(timeout=max(0.1, end - time.monotonic())))
                    if msg.get("method") == "Page.loadEventFired":
                        break
                call("Runtime.evaluate", {"expression": "Promise.all([...document.images].map(i=>i.decode().catch(()=>0)))",
                                          "awaitPromise": True})
                data = call("Page.captureScreenshot", {"format": "png", "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1}})
                return base64.b64decode(data["data"])
        finally:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/close/{tab['id']}", timeout=5).read()
            except Exception:  # noqa: BLE001
                pass

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        shutil.rmtree(self._dir, ignore_errors=True)


_session: _ChromeSession | None = None
_session_lock = threading.Lock()
_session_broken = False


def shutdown_chrome() -> None:
    """Stop the shared headless Chrome (also runs at interpreter exit)."""
    global _session
    with _session_lock:
        if _session is not None:
            _session.close()
            _session = None


atexit.register(shutdown_chrome)


def _shared_session(chrome: str) -> _ChromeSession | None:
    global _session, _session_broken
    with _session_lock:
        if _session_broken:
            return None
        if _session is not None and _session._proc.poll() is not None:
            _session.close()
            _session = None
        if _session is None:
            try:
                _session = _ChromeSession(chrome)
            except (OSError, MediaError) as exc:
                log.warning("shared Chrome unavailable (%s); using one process per image", exc)
                _session_broken = True
                return None
        return _session


def _rasterize_per_process(chrome: str, html_uri: str, d: str, width: int, height: int, timeout_s: float) -> Path:
    shot = Path(d) / "shot.png"
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           f"--user-data-dir={Path(d) / 'profile'}", f"--window-size={width},{height}",
           "--force-device-scale-factor=1", "--virtual-time-budget=2000", f"--screenshot={shot}", html_uri]
    for attempt in range(3):  # a loaded machine (many builds at once) makes headless Chrome miss the deadline
        try:
            subprocess.run(cmd, capture_output=True, timeout=timeout_s)
            break
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise MediaError("Chrome timed out rasterising the SVG") from None
    if not shot.is_file():
        raise MediaError("Chrome produced no screenshot")
    return shot


def rasterize_svg(svg_path: Path, png_path: Path, width: int, height: int, timeout_s: float = 60.0) -> None:
    """Rasterise through the shared Chrome session; falls back to one process per image if CDP is unavailable."""
    chrome = find_chrome()
    if not chrome:
        raise MediaError("Chrome not found: set CHROME_BIN (needed to rasterise SVG)")
    with tempfile.TemporaryDirectory(prefix="mcb-chrome-") as d:
        html = Path(d) / "p.html"
        html.write_text(
            f'<!doctype html><html><body style="margin:0;background:#F7F1E3"><img src="{svg_path.resolve().as_uri()}" '
            f'width="{width}" height="{height}" style="display:block"></body></html>', encoding="utf-8")
        sess = _shared_session(chrome)
        if sess is not None:
            for _ in range(2):
                try:
                    png = sess.screenshot(html.as_uri(), width, height, timeout_s)
                except Exception as exc:  # noqa: BLE001 - tab/ws trouble: retry once, then per-process fallback
                    log.warning("shared Chrome screenshot failed (%s)", exc)
                    continue
                png_path.parent.mkdir(parents=True, exist_ok=True)
                png_path.write_bytes(png)
                return
        shot = _rasterize_per_process(chrome, html.as_uri(), d, width, height, timeout_s)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(shot, png_path)


def png_to_webp(png: Path, webp: Path, quality: int = 82) -> None:
    from PIL import Image

    with Image.open(png) as im:
        im.convert("RGB").save(webp, "WEBP", quality=quality, method=6)


# --------------------------------------------------------------------------------------------------- generation

def _size(kind: str, spec: dict) -> tuple[int, int]:
    return {"cover": (1600, 1000), "illustration": (1200, 800), "picture": (400, 400), "diagram": (1000, 700)}[kind]


def _brief(req: MediaRequest) -> str:
    s = req.spec
    lang = "Vietnamese" if req.language == "vi" else "English"
    if req.kind == "cover":
        return (f"Course cover. Course: {s.get('title', '')}. Subject: {s.get('subject', '')}. Visual idea from the "
                f"author: {s.get('idea', '')}. The cover must show the concept itself, not a generic classroom. "
                f"Recipe for this subject: {subject_recipe(str(s.get('subject', '')) + ' ' + str(s.get('title', '')))}")
    if req.kind == "illustration":
        return (f"In-lesson illustration for learners ({req.age_band}, audience language {lang}, but no text in the "
                f"picture): {s.get('description', '')}")
    return (f"One small, simple picture of a SINGLE object, centred, big, friendly flat style, for a picture-choice "
            f"or counting exercise: {s.get('description', '')}")


def _ask(client: ModelClient, system: str, user: str, *, max_tokens: int = 28000, temperature: float = 0.4) -> str:
    return client.complete(ModelAlias.REASONING, [{"role": "system", "content": system},
                                                  {"role": "user", "content": user}],
                           max_tokens=max_tokens, temperature=temperature)


def _write_svg(client: ModelClient, brief: str, w: int, h: int, *, allow_text: bool, feedback: str = "",
               rounds: int = 3) -> tuple[str, str]:
    """(idea, svg) with validation feedback loop."""
    system = SVG_SYSTEM.format(w=w, h=h, palette=PALETTE)
    user = brief + (f"\nFix these defects from the previous attempt: {feedback}" if feedback else "")
    problem = ""
    for _ in range(rounds):
        raw = _ask(client, system, user + (f"\nYour last SVG was rejected: {problem}. Return a corrected one." if problem else ""))
        idea, svg = extract_block(raw, "svg")
        problem = validate_svg(svg, allow_text=allow_text) if svg else "no ```svg block found"
        if not problem:
            return idea, svg
    raise MediaError(f"model could not produce a valid SVG: {problem}")


def _critique(client: ModelClient, png: Path, subject: str) -> list[str]:
    """Defect list from the vision model (empty when fine or when the critic itself fails)."""
    from PIL import Image

    with Image.open(png) as im:
        buf = BytesIO()
        im.convert("RGB").resize((800, int(800 * im.height / im.width))).save(buf, "JPEG", quality=85)
    try:
        raw = client.complete(ModelAlias.VISION, [{"role": "user", "content": [
            {"type": "text", "text": CRITIQUE_PROMPT.format(subject=subject)}, image_part(buf.getvalue())]}],
            max_tokens=2000)
        data = parse_model_json(raw)
    except (ModelError, ValueError, KeyError) as exc:
        log.warning("illustration critique skipped: %s", exc)
        return []
    if data.get("ok") is True:
        return []
    return [str(d)[:200] for d in (data.get("defects") or [])][:6]


def _result(req: MediaRequest, out_dir: Path, svg: str, idea: str, *, raster: bool, w: int, h: int,
            script: str | None, notes: list[str]) -> MediaResult:
    src = out_dir / "sources" / req.id
    src.mkdir(parents=True, exist_ok=True)
    (src / "source.svg").write_text(svg, encoding="utf-8")
    (src / "idea.txt").write_text(idea, encoding="utf-8")
    if script:
        (src / "diagram.py").write_text(script, encoding="utf-8")
    files: list[MediaFile] = []
    if raster:
        png = src / "render.png"
        rasterize_svg(src / "source.svg", png, w, h)
        webp = out_dir / "images" / f"{req.id}.webp"
        webp.parent.mkdir(parents=True, exist_ok=True)
        png_to_webp(png, webp)
        files.append(MediaFile(role="main", path=f"images/{req.id}.webp", mime="image/webp", file=webp))
    else:
        dst = out_dir / "images" / f"{req.id}.svg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(svg, encoding="utf-8")
        files.append(MediaFile(role="main", path=f"images/{req.id}.svg", mime="image/svg+xml", file=dst))
    return MediaResult(id=req.id, kind=req.kind, files=files, source_dir=src, notes=notes)


def make_image(req: MediaRequest, out_dir: Path, client: ModelClient) -> MediaResult:
    """cover / illustration / picture: SVG (no text) -> WebP (cover, illustration) or SVG (picture) + one self-critique."""
    w, h = _size(req.kind, req.spec)
    notes: list[str] = []
    from mentor_course_builder import picture_chain

    if req.revise:
        return picture_chain.revise_picture(req, out_dir, client) or revise_svg(req, out_dir, client)
    # code-drawn stays first where accuracy matters; otherwise image API -> web image -> (below) code-drawn
    raster, chain_notes = picture_chain.try_raster_sources(req, out_dir, client)
    if raster:
        return raster
    notes.extend(chain_notes)
    idea, svg = _write_svg(client, _brief(req), w, h, allow_text=False)
    notes.append("illustration: deepseek svg")
    if req.kind in ("cover", "illustration"):
        subject = req.spec.get("idea") or req.spec.get("description") or req.spec.get("title", "")
        tmp = out_dir / "sources" / req.id
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "source.svg").write_text(svg, encoding="utf-8")
        rasterize_svg(tmp / "source.svg", tmp / "render.png", w, h)
        defects = _critique(client, tmp / "render.png", str(subject))
        if defects:
            notes.append("critique: " + "; ".join(defects))
            try:
                idea, svg = _write_svg(client, _brief(req), w, h, allow_text=False, feedback="; ".join(defects))
                notes.append("regenerated once after critique")
            except MediaError as exc:
                notes.append(f"regeneration failed, kept first version: {exc}")
        else:
            notes.append("critique: ok")
    return _result(req, out_dir, svg, idea, raster=req.kind != "picture", w=w, h=h, script=None, notes=notes)


def make_diagram(req: MediaRequest, out_dir: Path, client: ModelClient, *, fix_rounds: int = 2) -> MediaResult:
    if req.revise:
        return revise_svg(req, out_dir, client)
    w, h = _size("diagram", req.spec)
    s = req.spec
    user = (f"Diagram: {s.get('description', '')}\nLabels to place (exact strings): {s.get('labels') or []}\n"
            f"Exact math/data: {s.get('math') or 'none'}")
    system = DIAGRAM_SYSTEM.format(w=w, h=h, palette=PALETTE)
    problem = ""
    for _ in range(fix_rounds + 1):
        raw = _ask(client, system, user + (f"\nYour last script failed: {problem}. Return a corrected script." if problem else ""),
                   temperature=0.2)
        idea, code = extract_block(raw, "python")
        try:
            if not code:
                raise MediaError("no ```python block found")
            svg = run_diagram_script(code)
            bad = validate_svg(svg, allow_text=True)
            if bad:
                raise MediaError(bad)
            return _result(req, out_dir, svg, idea, raster=False, w=w, h=h, script=code,
                           notes=["diagram: computed by script (subprocess)"])
        except MediaError as exc:
            problem = str(exc)
    raise MediaError(f"diagram generation failed: {problem}")


def revise_svg(req: MediaRequest, out_dir: Path, client: ModelClient) -> MediaResult:
    """Teacher comment {comment, x, y} (+ source_dir of the previous result): edit the SVG around that point."""
    rev = req.revise or {}
    src_dir = Path(rev["source_dir"]) if rev.get("source_dir") else None
    svg_text = rev.get("svg") or ((src_dir / "source.svg").read_text(encoding="utf-8") if src_dir and (src_dir / "source.svg").is_file() else "")
    if not svg_text:
        raise MediaError("revise needs revise.source_dir (with source.svg) or revise.svg")
    w, h = _size(req.kind, req.spec)
    m = re.search(r'viewBox="\s*[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)', svg_text)
    if m:
        w, h = int(float(m.group(1))), int(float(m.group(2)))
    x, y = rev.get("x"), rev.get("y")
    where = ""
    if x is not None and y is not None:
        px, py = (x * w, y * h) if 0 <= x <= 1 and 0 <= y <= 1 else (x, y)
        where = f"\nPoint of the comment: x={px:.0f}, y={py:.0f} (viewBox {w}x{h})."
    allow_text = req.kind == "diagram" or "<text" in svg_text
    user = f"Teacher comment: {rev.get('comment', '')}{where}\n\nCurrent SVG:\n```svg\n{svg_text}\n```"
    problem = ""
    for _ in range(3):
        raw = _ask(client, REVISE_SYSTEM, user + (f"\nRejected: {problem}" if problem else ""), temperature=0.2)
        _, svg = extract_block(raw, "svg")
        problem = validate_svg(svg, allow_text=allow_text) if svg else "no ```svg block found"
        if not problem:
            return _result(req, out_dir, svg, f"revised: {rev.get('comment', '')}", raster=req.kind in ("cover", "illustration"),
                           w=w, h=h, script=None, notes=["revised svg around the commented point"])
    raise MediaError(f"revision failed: {problem}")
