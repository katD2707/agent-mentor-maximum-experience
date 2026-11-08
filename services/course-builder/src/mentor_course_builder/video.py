"""Explainer videos via HyperFrames (Apache-2.0, https://github.com/heygen-com/hyperframes), pinned CLI version.

Flow (REQUIREMENTS-PLAN §4.4 step 8):
  scenes -> TTS per scene (sets scene length) -> REASONING model writes each scene (3 fenced parts that WE wrap in the
  strict HyperFrames template, so the contract - <template>, root ids, registered timeline, fonts - cannot be broken)
  -> `hyperframes check --json` loop (max 2 fix rounds) -> narration track -> `render` 1280x720 -> WebVTT -> poster.
The project dir is kept as the editable source; `timeline` (from `hyperframes timeline --json`) lets a teacher's
comment at second T be mapped to the scene file, which the model edits alone before a full re-render.

Authoring rules come from the `hyperframes` / `hyperframes-cli` skills (SKILL.md + references/format.md, v0.9.19).
HYPERFRAMES_NO_TELEMETRY=1 and DO_NOT_TRACK=1 are always set. Needs Node 22+, ffmpeg and Chrome.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mentor_schemas import ModelAlias

from mentor_course_builder.contracts import MediaFile, MediaRequest, MediaResult
from mentor_course_builder.llm import ModelClient, ModelError
from mentor_course_builder.media import MediaError, _run, find_ffmpeg, require_ffmpeg
from mentor_course_builder.tts import TtsService, audio_duration, default_cache_dir

log = logging.getLogger("mentor_course_builder")

HF_VERSION = "0.9.19"
W, H = 1280, 720
LEAD_S, TAIL_S, MIN_SCENE_S = 0.6, 0.9, 3.5

FONT_FACES = {  # fontsource lexend subsets (OFL-1.1) -> unicode-range
    "vietnamese": "U+0102-0103,U+0110-0111,U+0128-0129,U+0168-0169,U+01A0-01A1,U+01AF-01B0,U+0300-0301,U+0303-0304,"
                  "U+0308-0309,U+0323,U+0329,U+1EA0-1EF9,U+20AB",
    "latin-ext": "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,"
                 "U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF",
    "latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,"
             "U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
}
FONT_WEIGHTS = (400, 600)


# --------------------------------------------------------------------------------------------------- CLI + assets

def _node_cli_dir() -> Path:
    return default_cache_dir().parent / "hyperframes" / HF_VERSION


def hyperframes_cmd() -> list[str]:
    """Pinned CLI: $HYPERFRAMES_BIN, else a cached `npm install hyperframes@<ver>` run with node, else pinned npx."""
    explicit = os.environ.get("HYPERFRAMES_BIN")
    if explicit:
        return [explicit]
    node = shutil.which("node")
    if not node:
        raise MediaError("Node.js 22+ not found (needed for HyperFrames)")
    d = _node_cli_dir()
    entry = d / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    if not entry.is_file():
        npm = shutil.which("npm")
        if npm:
            d.mkdir(parents=True, exist_ok=True)
            (d / "package.json").write_text('{"name":"hf-cli","private":true}', encoding="utf-8")
            r = _run([npm, "install", f"hyperframes@{HF_VERSION}", "--no-audit", "--no-fund"], timeout=600) \
                if os.name != "nt" else subprocess.run(f'"{npm}" install hyperframes@{HF_VERSION} --no-audit --no-fund',
                                                       cwd=d, shell=True, capture_output=True, text=True, timeout=600)
            if r.returncode != 0 or not entry.is_file():
                log.warning("npm install of hyperframes failed, falling back to npx")
    if entry.is_file():
        return [node, str(entry)]
    npx = shutil.which("npx")
    if not npx:
        raise MediaError("npm/npx not found (needed to run HyperFrames)")
    return [npx, "-y", f"hyperframes@{HF_VERSION}"]


def hf_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update({"HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "PYTHONUTF8": "1"})
    ff = find_ffmpeg()
    if ff:
        env["PATH"] = str(Path(ff).parent) + os.pathsep + env.get("PATH", "")
    return env


def run_hf(args: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*hyperframes_cmd(), *args], cwd=cwd, env=hf_env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _find_fontsource() -> Path | None:
    for start in (Path.cwd(), Path(__file__).resolve()):
        for d in (start, *start.parents):
            for rel in ("apps/app/node_modules/@fontsource/lexend/files", "node_modules/@fontsource/lexend/files"):
                if (d / rel).is_dir():
                    return d / rel
    return None


def ensure_fonts(dest: Path) -> list[str]:
    """Copy (or download once into the cache) the Lexend woff2 subsets; returns the @font-face CSS."""
    dest.mkdir(parents=True, exist_ok=True)
    src_dir = _find_fontsource()
    cache = default_cache_dir() / "fonts"
    cache.mkdir(parents=True, exist_ok=True)
    css: list[str] = []
    for subset, rng in FONT_FACES.items():
        for wt in FONT_WEIGHTS:
            name = f"lexend-{subset}-{wt}-normal.woff2"
            target = dest / name
            if not target.is_file():
                cached = cache / name
                if not cached.is_file():
                    if src_dir and (src_dir / name).is_file():
                        shutil.copyfile(src_dir / name, cached)
                    else:
                        url = f"https://cdn.jsdelivr.net/npm/@fontsource/lexend@5.1.0/files/{name}"
                        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (fixed https URL)
                            cached.write_bytes(r.read())
                shutil.copyfile(cached, target)
            css.append(f"@font-face{{font-family:'Lexend';font-style:normal;font-weight:{wt};font-display:block;"
                       f"src:url('assets/fonts/{name}') format('woff2');unicode-range:{rng};}}")
    return css


def ensure_gsap(dest: Path) -> None:
    if dest.is_file():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = hyperframes_cmd()
    for cand in [Path(cmd[-1]).parent.parent / "dist/vendor/npm/gsap@3.15.0/dist/gsap.min.js"] + \
            list(_node_cli_dir().glob("node_modules/hyperframes/dist/vendor/npm/gsap@*/dist/gsap.min.js")):
        if cand.is_file():
            shutil.copyfile(cand, dest)
            return
    cached = default_cache_dir() / "gsap.min.js"
    if not cached.is_file():
        cached.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen("https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js", timeout=60) as r:  # noqa: S310
            cached.write_bytes(r.read())
    shutil.copyfile(cached, dest)


# --------------------------------------------------------------------------------------------------- scene authoring

SCENE_SYSTEM = f"""You are a motion designer writing ONE scene of an educational explainer video as HTML+CSS+GSAP for the
HyperFrames renderer. Canvas {W}x{H}. The audience is a school learner; the look is a warm notebook: paper background
(already provided), purple ink #5A4BC0, ink wash #E9E5F6, highlighter yellow #F0D76E, coral #E8806A, mint #9FD8BF, night
ink #2B283F text. Font: Lexend (provided; weights 400 and 600), Vietnamese diacritics must render, no italics.
You reply with exactly three fenced blocks, nothing else:
```html
(children of the scene root: the elements only)
```
```css
(extra rules; the root #root, the font and the paper background already exist)
```
```js
(statements that animate with the existing paused timeline `tl`; do NOT create or register a timeline)
```
HARD RULES (a checker enforces them):
- Prefix every id with the scene id (e.g. s2-title). Keep all content inside an 64px margin; text >= 34px (headline
  64px, 600 weight); max ~10 words per text; show the scene's caption as the headline; do not print the narration.
- EVERY visible element is written in the html with class="clip" plus data-start and data-duration in seconds, local to
  the scene (0 = scene start); each element is shown during [start, start+duration) and its duration ends at or before the
  scene length. Make the main elements last until the scene length. Never animate display/visibility; never put a CSS
  transform on an element that GSAP animates (use gsap.fromTo with x, y, scale, rotation, opacity instead).
- Animate with tl.fromTo("#s2-title", {{opacity:0,y:30}}, {{opacity:1,y:0,duration:0.5,ease:"power3.out"}}, 0.3);
  always fromTo (never from), absolute positions in seconds, no repeat:-1, no Date.now, no Math.random, no timers, no
  network, no external images/fonts. Draw with inline <svg> (shapes, paths, circles; plus/minus as two rects, no blobs)
  and divs. Elements appear in step with the narration: the narration starts at {LEAD_S}s and takes the stated time.
- Position with position:absolute and pixel left/top/width/height; avoid overlapping text and shapes; one idea per scene. Keep the scene simple (under ~25 elements) and do not deliberate at length.
"""


@dataclass
class SceneParts:
    html: str
    css: str
    js: str


def parse_scene_reply(raw: str) -> SceneParts:
    def blk(lang: str) -> str:
        m = re.search(rf"```{lang}\s*\n(.*?)```", raw, re.S | re.I)
        return m.group(1).strip() if m else ""

    p = SceneParts(blk("html"), blk("css"), blk("js"))
    if not p.html:
        raise MediaError("scene reply has no ```html block")
    if not p.js:
        raise MediaError("scene reply has no ```js block")
    return p


def _clean_js(js: str, sid: str) -> str:
    js = re.sub(r"(const|let|var)\s+tl\s*=\s*gsap\.timeline\([^;]*\);?", "", js)
    js = re.sub(r"window\.__timelines\s*\[[^\]]*\]\s*=\s*tl;?", "", js)
    return js.strip()


def scene_file(sid: str, parts: SceneParts, font_css: list[str]) -> str:
    return f"""<template>
  <style>
    {chr(10).join('    ' + c for c in font_css).strip()}
    #root {{ position: absolute; inset: 0; background: #F7F1E3; color: #2B283F; font-family: 'Lexend', sans-serif; overflow: hidden; }}
    #root * {{ box-sizing: border-box; }}
    {parts.css}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="{W}" data-height="{H}">
{parts.html}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{_clean_js(parts.js, sid)}
    window.__timelines["{sid}"] = tl;
  </script>
</template>
"""


def index_html(scenes: list[dict], total: float, title: str, lang: str) -> str:
    hosts = "\n".join(
        f'    <div id="{s["id"]}" class="clip" data-composition-id="{s["id"]}" data-composition-src="compositions/{s["id"]}.html" '
        f'data-start="{s["start"]:.2f}" data-duration="{s["duration"]:.2f}" data-track-index="1" data-track-kind="graphics" '
        f'data-width="{W}" data-height="{H}"></div>' for s in scenes)
    return f"""<!doctype html>
<html lang="{lang}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <title>{re.sub(r'[<>&]', '', title)}</title>
    <script src="assets/gsap.min.js"></script>
    <style>
      html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: #F7F1E3; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total:.2f}" data-width="{W}" data-height="{H}">
{hosts}
      <audio id="narration" src="assets/narration.mp3" data-start="0" data-duration="{total:.2f}" data-volume="1"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def write_scene(client: ModelClient, sc: dict, feedback: str = "", current: SceneParts | None = None) -> SceneParts:
    user = (f"Scene id: {sc['id']}   Scene length: {sc['duration']:.1f}s (narration plays {LEAD_S}s to "
            f"{LEAD_S + sc['narr_dur']:.1f}s).\nHeadline caption: {sc['caption']}\nNarration (for timing only, do not "
            f"print): {sc['narration']}\nWhat to draw and animate: {sc['visual']}")
    if current and feedback:
        user += (f"\n\nCurrent scene:\n```html\n{current.html}\n```\n```css\n{current.css}\n```\n```js\n{current.js}\n```\n"
                 f"Change it as follows (edit only what is needed, keep the rest): {feedback}")
    elif feedback:
        user += f"\n\nFix: {feedback}"
    last = ""
    for _ in range(3):
        try:  # the gateway sometimes drops a long reasoning stream (ModelClient already retried): try again
            raw = client.complete(ModelAlias.REASONING, [{"role": "system", "content": SCENE_SYSTEM},
                                                         {"role": "user", "content": user + last}],
                                  max_tokens=28000, temperature=0.3)
            return parse_scene_reply(raw)
        except MediaError as exc:
            last = f"\n\nYour last reply was unusable: {exc}. Reply with the three fenced blocks."
        except ModelError as exc:
            log.warning("scene %s: %s", sc["id"], exc)
    raise MediaError("model did not return a usable scene")


# --------------------------------------------------------------------------------------------------- check / timeline

def check_errors(proj: Path) -> list[dict]:
    """Errors from `hyperframes check --json` as [{file, code, message, fix}]."""
    r = run_hf(["check", "--json"], proj, timeout=300)
    try:
        data = json.loads(r.stdout[r.stdout.index("{"):])
    except (ValueError, json.JSONDecodeError):
        return [{"file": "", "code": "check_failed", "message": (r.stderr or r.stdout)[-300:], "fix": ""}]
    out: list[dict] = []
    for section in ("lint", "runtime", "layout", "contrast"):
        for f in (data.get(section) or {}).get("findings", []):
            if f.get("severity") == "error":
                out.append({"file": f.get("sourceFile") or f.get("file") or "", "code": f.get("code", ""),
                            "message": str(f.get("message", ""))[:240], "fix": str(f.get("fixHint") or f.get("fix") or "")[:200]})
    return out


def flatten_timeline(data: dict) -> list[dict]:
    """`hyperframes timeline --json` -> [{"start","end","file","element"}] (every clip incl. nested ones)."""
    out: list[dict] = []

    def visit(row: dict) -> None:
        out.append({"start": float(row.get("absStart", row.get("start", 0)) or 0),
                    "end": float(row.get("absEnd", row.get("end", 0)) or 0),
                    "file": row.get("file") or "index.html", "element": row.get("elementId") or row.get("id") or ""})
        for k in ("children", "inside"):
            for ch in row.get(k) or []:
                if isinstance(ch, dict) and ("absStart" in ch or "start" in ch):
                    visit(ch)

    for track in (data.get("timeline") or data).get("tracks", []):
        for row in track.get("rows", []):
            visit(row)
    return sorted(out, key=lambda e: (e["start"], e["end"]))


def read_timeline(proj: Path) -> list[dict]:
    r = run_hf(["timeline", "--json"], proj, timeout=180)
    try:
        return flatten_timeline(json.loads(r.stdout[r.stdout.index("{"):]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise MediaError(f"hyperframes timeline failed: {(r.stderr or r.stdout)[-200:]}") from exc


def find_element_at(timeline: list[dict], at_s: float) -> dict | None:
    """The most specific clip active at `at_s`: an element inside a scene file if any, else the scene host."""
    active = [e for e in timeline if e["start"] <= at_s < e["end"]]
    scene = [e for e in active if e["file"].startswith("compositions/")]
    pool = scene or [e for e in active if e["element"] != "narration"]
    if not pool:
        scenes = [e for e in timeline if e["file"].startswith("compositions/")]
        return min(scenes, key=lambda e: min(abs(at_s - e["start"]), abs(at_s - e["end"])), default=None)
    return min(pool, key=lambda e: (e["end"] - e["start"], -e["start"]))


# --------------------------------------------------------------------------------------------------- captions / audio

def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", " ".join(text.split())) if p.strip()]
    return parts or [text.strip()]


def build_vtt(scenes: list[dict]) -> str:
    """WebVTT: each scene's narration split into sentences, timed proportionally to length within its audio span."""
    lines = ["WEBVTT", ""]
    n = 0
    for sc in scenes:
        sents = split_sentences(sc["narration"])
        total = sum(len(s) for s in sents) or 1
        t = sc["start"] + sc["narr_start"]
        for s in sents:
            d = sc["narr_dur"] * len(s) / total
            n += 1
            lines += [str(n), f"{_ts(t)} --> {_ts(t + d)}", s, ""]
            t += d
    return "\n".join(lines)


def build_narration(clips: list[tuple[Path, float]], dest: Path) -> None:
    """clips: [(mp3, scene_duration)] -> one mp3 where clip i starts LEAD_S after its scene start."""
    ff = require_ffmpeg()
    args = [ff, "-y", "-v", "error"]
    for p, _ in clips:
        args += ["-i", str(p)]
    f = ";".join(f"[{i}:a]adelay={int(LEAD_S * 1000)}:all=1,apad=whole_dur={d:.3f}[a{i}]" for i, (_, d) in enumerate(clips))
    f += ";" + "".join(f"[a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=0:a=1[out]"
    r = _run(args + ["-filter_complex", f, "-map", "[out]", "-ac", "1", "-b:a", "64k", str(dest)], timeout=300)
    if r.returncode != 0 or not dest.is_file():
        raise MediaError(f"narration mux failed: {r.stderr.strip()[-200:]}")


# --------------------------------------------------------------------------------------------------- orchestration

def _save_state(proj: Path, state: dict) -> None:
    (proj / "scenes.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _write_project(proj: Path, state: dict, font_css: list[str]) -> None:
    (proj / "compositions").mkdir(parents=True, exist_ok=True)
    for sc in state["scenes"]:
        parts = SceneParts(sc["html"], sc["css"], sc["js"])
        (proj / "compositions" / f"{sc['id']}.html").write_text(scene_file(sc["id"], parts, font_css), encoding="utf-8")
    (proj / "index.html").write_text(index_html(state["scenes"], state["total"], state["title"], state["lang"]), encoding="utf-8")
    (proj / "hyperframes.json").write_text(json.dumps({"$schema": "https://hyperframes.heygen.com/schema/hyperframes.json"}), encoding="utf-8")
    _save_state(proj, state)


def _fix_loop(client: ModelClient, proj: Path, state: dict, font_css: list[str], notes: list[str], rounds: int = 2) -> None:
    for rnd in range(rounds + 1):
        errs = check_errors(proj)
        if not errs:
            notes.append(f"check: clean after {rnd} fix round(s)")
            return
        if rnd == rounds:
            notes.append("check: errors remain: " + "; ".join(f"{e['code']} ({e['file']})" for e in errs[:5]))
            return
        by_scene: dict[str, list[dict]] = {}
        for e in errs:
            m = re.search(r"compositions/([\w-]+)\.html", e["file"].replace("\\", "/"))
            by_scene.setdefault(m.group(1) if m else "*", []).append(e)
        targets = [s for s in state["scenes"] if s["id"] in by_scene or "*" in by_scene]
        for sc in targets:
            es = by_scene.get(sc["id"], []) + by_scene.get("*", [])
            fb = "; ".join(f"{e['code']}: {e['message']} {e['fix']}" for e in es)
            parts = write_scene(client, sc, "fix these checker errors: " + fb, SceneParts(sc["html"], sc["css"], sc["js"]))
            sc.update(html=parts.html, css=parts.css, js=parts.js)
        _write_project(proj, state, font_css)


def render_project(proj: Path, out_mp4: Path, notes: list[str]) -> None:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    r = run_hf(["render", "-o", str(out_mp4), "--fps", "30", "-q", "looks", "--crf", "24", "--quiet"], proj, timeout=1500)
    if r.returncode != 0 or not out_mp4.is_file() or out_mp4.stat().st_size < 10_000:
        raise MediaError(f"hyperframes render failed: {(r.stderr or r.stdout).strip()[-400:]}")


def make_poster(proj: Path, at_s: float, dest_webp: Path) -> None:
    from PIL import Image

    shots = proj / ".hyperframes-poster"
    shutil.rmtree(shots, ignore_errors=True)
    run_hf(["snapshot", "--at", f"{at_s:.2f}", "--no-end", "-o", str(shots)], proj, timeout=300)
    pngs = sorted(shots.rglob("*.png"))
    if not pngs:
        raise MediaError("hyperframes snapshot produced no poster")
    dest_webp.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(pngs[0]) as im:
        im.convert("RGB").save(dest_webp, "WEBP", quality=82)
    shutil.rmtree(shots, ignore_errors=True)


def _finish(req: MediaRequest, out_dir: Path, proj: Path, state: dict, notes: list[str]) -> MediaResult:
    mp4 = out_dir / "video" / f"{req.id}.mp4"
    t0 = time.monotonic()
    render_project(proj, mp4, notes)
    notes.append(f"render: {time.monotonic() - t0:.0f}s (hyperframes {HF_VERSION}, 1280x720 30fps)")
    vtt = out_dir / "video" / f"{req.id}.vtt"
    vtt.write_text(build_vtt(state["scenes"]), encoding="utf-8")
    poster = out_dir / "images" / f"{req.id}-poster.webp"
    first = state["scenes"][0]
    make_poster(proj, first["start"] + min(first["duration"] * 0.7, 3.0), poster)
    timeline = read_timeline(proj)
    shutil.rmtree(proj / ".hyperframes", ignore_errors=True)
    return MediaResult(
        id=req.id, kind="video", duration_s=round(audio_duration(mp4), 2), source_dir=proj, timeline=timeline, notes=notes,
        files=[MediaFile(role="main", path=f"video/{req.id}.mp4", mime="video/mp4", file=mp4),
               MediaFile(role="captions", path=f"video/{req.id}.vtt", mime="text/vtt", file=vtt),
               MediaFile(role="poster", path=f"images/{req.id}-poster.webp", mime="image/webp", file=poster)])


def make_video(req: MediaRequest, out_dir: Path, client: ModelClient, tts: TtsService) -> MediaResult:
    if req.revise:
        return revise_video(req, out_dir, client)
    spec = req.spec
    scenes_in = spec["scenes"]
    proj = out_dir / "sources" / req.id
    shutil.rmtree(proj, ignore_errors=True)
    (proj / "assets").mkdir(parents=True)
    notes: list[str] = []
    font_css = ensure_fonts(proj / "assets" / "fonts")
    ensure_gsap(proj / "assets" / "gsap.min.js")

    # 1. narration per scene fixes scene lengths
    scenes: list[dict] = []
    clips: list[tuple[Path, float]] = []
    t0 = 0.0
    with ThreadPoolExecutor(max_workers=min(3, len(scenes_in))) as ex:  # scene clips are independent
        scene_clips = list(ex.map(lambda a: tts.synthesize(a[1]["narration"], lang=req.language, age_band=req.age_band,
                                                           rate=spec.get("rate"), dest=proj / "assets" / f"narration-{a[0]}.mp3"),
                                  enumerate(scenes_in, 1)))
    for i, (s, clip) in enumerate(zip(scenes_in, scene_clips), 1):
        notes += clip.notes[-1:]
        dur = max(MIN_SCENE_S, clip.duration_s + LEAD_S + TAIL_S)
        scenes.append({"id": f"s{i}", "caption": s["caption"], "narration": s["narration"], "visual": s["visual"],
                       "start": round(t0, 3), "duration": round(dur, 3), "narr_start": LEAD_S,
                       "narr_dur": round(clip.duration_s, 3)})
        clips.append((clip.path, dur))
        t0 += dur
    build_narration(clips, proj / "assets" / "narration.mp3")
    for i in range(1, len(scenes) + 1):
        (proj / "assets" / f"narration-{i}.mp3").unlink(missing_ok=True)
    if spec.get("target_s") and abs(t0 - float(spec["target_s"])) > 0.5 * float(spec["target_s"]):
        notes.append(f"length {t0:.0f}s differs from target_s {spec['target_s']}: set by narration")

    # 2. scenes written by the model, in parallel
    with ThreadPoolExecutor(max_workers=3) as ex:
        parts = list(ex.map(lambda sc: write_scene(client, sc), scenes))
    for sc, p in zip(scenes, parts):
        sc.update(html=p.html, css=p.css, js=p.js)
    state = {"title": spec.get("title", req.id), "lang": req.language, "total": round(t0, 3), "scenes": scenes,
             "font_css": font_css}
    _write_project(proj, state, font_css)

    # 3. check loop, render
    _fix_loop(client, proj, state, font_css, notes)
    return _finish(req, out_dir, proj, state, notes)


def revise_video(req: MediaRequest, out_dir: Path, client: ModelClient) -> MediaResult:
    """{comment, at_s, source_dir}: edit only the scene active at `at_s`, then re-render the whole video."""
    rev = req.revise or {}
    if not rev.get("source_dir") or rev.get("at_s") is None:
        raise MediaError("video revise needs revise.source_dir (previous HyperFrames project) and revise.at_s")
    proj = out_dir / "sources" / req.id
    if Path(rev["source_dir"]).resolve() != proj.resolve():
        shutil.rmtree(proj, ignore_errors=True)
        shutil.copytree(rev["source_dir"], proj, ignore=shutil.ignore_patterns(".hyperframes"))
    state = json.loads((proj / "scenes.json").read_text(encoding="utf-8"))
    font_css = state["font_css"]
    timeline = read_timeline(proj)
    hit = find_element_at(timeline, float(rev["at_s"]))
    at = float(rev["at_s"])
    m = re.search(r"compositions/([\w-]+)\.html", (hit or {}).get("file", ""))
    ids = {s["id"] for s in state["scenes"]}
    sid = m.group(1) if m else ((hit or {}).get("element") if (hit or {}).get("element") in ids else None)
    if not sid:  # gap between elements: the scene whose slot contains the second
        sid = next((s["id"] for s in state["scenes"] if s["start"] <= at < s["start"] + s["duration"]), None)
    if not sid:
        raise MediaError(f"no scene found at {rev['at_s']}s")
    sc = next(s for s in state["scenes"] if s["id"] == sid)
    hit = hit or {"element": sid}
    notes = [f"revise: scene {sc['id']}, element #{hit['element']} at {rev['at_s']}s"]
    parts = write_scene(client, sc, f"Teacher comment at {float(rev['at_s']) - sc['start']:.1f}s into this scene "
                        f"(element #{hit['element']}): {rev.get('comment', '')}", SceneParts(sc["html"], sc["css"], sc["js"]))
    sc.update(html=parts.html, css=parts.css, js=parts.js)
    _write_project(proj, state, font_css)
    _fix_loop(client, proj, state, font_css, notes)
    return _finish(req, out_dir, proj, state, notes)
