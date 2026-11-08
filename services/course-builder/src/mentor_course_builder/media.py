"""ffmpeg helpers: audio track extraction and keyframes. ffmpeg is a runtime requirement for audio/video only.

Located at runtime (first hit wins): env FFMPEG_BIN, `ffmpeg` on PATH, the `imageio-ffmpeg` wheel if installed,
a winget/Chocolatey install on Windows. Any portable static build works (GPL/LGPL, used as an external process).
"""

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path


class MediaError(Exception):
    pass


def find_ffmpeg() -> str | None:
    cand = os.environ.get("FFMPEG_BIN")
    if cand and Path(cand).is_file():
        return cand
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    local = os.environ.get("LOCALAPPDATA", "")
    for pattern in (
        f"{local}/Microsoft/WinGet/Packages/*FFmpeg*/**/bin/ffmpeg.exe",
        "C:/ProgramData/chocolatey/bin/ffmpeg.exe",
    ):
        hits = glob.glob(pattern, recursive=True)
        if hits:
            return hits[0]
    return None


def _run(args: list[str], timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def require_ffmpeg() -> str:
    exe = find_ffmpeg()
    if not exe:
        raise MediaError("ffmpeg not found: set FFMPEG_BIN or put ffmpeg on PATH (needed for audio/video)")
    return exe


def extract_audio_chunks(src: Path, out_dir: Path, chunk_s: int = 600) -> list[tuple[Path, float]]:
    """Audio track -> mono 16 kHz mp3 chunks of `chunk_s`. Returns [(path, start_seconds)]; [] if no audio stream."""
    ffmpeg = require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "audio_%03d.mp3"
    r = _run([ffmpeg, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
              "-f", "segment", "-segment_time", str(chunk_s), "-reset_timestamps", "1", str(pattern)])
    files = sorted(out_dir.glob("audio_*.mp3"))
    if r.returncode != 0 and not files:
        if "does not contain any stream" in r.stderr or "matches no streams" in r.stderr:
            return []
        raise MediaError(f"ffmpeg audio extraction failed: {r.stderr.strip()[-200:]}")
    return [(f, i * float(chunk_s)) for i, f in enumerate(files)]


def extract_keyframes(
    src: Path, out_dir: Path, every_s: float = 30.0, scene: float = 0.3, max_frames: int = 60
) -> list[tuple[Path, float]]:
    """A frame at every scene change (> `scene`) and at least every `every_s` seconds. Returns [(path, t_seconds)]."""
    ffmpeg = require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    sel = f"isnan(prev_selected_t)+gt(scene,{scene})+gte(t-prev_selected_t,{every_s})"
    r = _run([ffmpeg, "-y", "-i", str(src), "-an", "-vf", f"select='{sel}',showinfo", "-fps_mode", "vfr",
              "-q:v", "3", str(out_dir / "frame_%04d.jpg")])
    files = sorted(out_dir.glob("frame_*.jpg"))
    if not files:
        if r.returncode != 0:
            raise MediaError(f"ffmpeg keyframe extraction failed: {r.stderr.strip()[-200:]}")
        return []
    times = [float(t) for t in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    times = (times + [0.0] * len(files))[: len(files)]
    pairs = list(zip(files, times))
    if len(pairs) > max_frames:  # thin out evenly, keep first and last
        step = (len(pairs) - 1) / (max_frames - 1)
        keep = {round(i * step) for i in range(max_frames)}
        for i, (f, _) in enumerate(pairs):
            if i not in keep:
                f.unlink(missing_ok=True)
        pairs = [p for i, p in enumerate(pairs) if i in keep]
    return pairs
