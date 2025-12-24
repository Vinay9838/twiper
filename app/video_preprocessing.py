import os
import subprocess
from shutil import which
from typing import Optional


def get_video_duration_seconds(path: str) -> Optional[float]:
    """Return duration in seconds using ffprobe or ffmpeg.
    Returns None if tools are unavailable or output cannot be parsed.
    """
    try:
        if which("ffprobe"):
            res = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            out = (res.stdout or "").strip()
            return float(out) if out else None
        elif which("ffmpeg"):
            res = subprocess.run(
                ["ffmpeg", "-i", path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            probe = res.stderr or res.stdout or ""
            for line in probe.splitlines():
                if "Duration:" in line:
                    try:
                        stamp = line.split("Duration:")[1].split(",")[0].strip()
                        h, m, s = stamp.split(":")
                        return int(h) * 3600 + int(m) * 60 + float(s)
                    except Exception:
                        break
        return None
    except Exception:
        return None


def maybe_trim_video(path: str, max_seconds: int = 140, logger=None) -> str:
    """If video exceeds max_seconds (default 2m20s), trim to 00:00:00-00:02:20 using cut_video.sh.

    Returns the path to the video to upload (trimmed or original).
    """
    dur = get_video_duration_seconds(path)
    if dur is None:
        if logger:
            logger.info("Cannot determine duration; proceeding without trim: %s", path)
        return path
    if dur <= max_seconds + 0.5:
        if logger:
            logger.info("Video within limit (%.1fs); no trim: %s", dur, path)
        return path

    script_path = os.path.join(os.path.dirname(__file__), "cut_video.sh")
    if not os.path.isfile(script_path):
        if logger:
            logger.warning("cut_video.sh not found; cannot trim. path=%s", path)
        return path
    if not which("ffmpeg"):
        if logger:
            logger.warning("ffmpeg not available; cannot trim. path=%s", path)
        return path

    if logger:
        logger.info("Trimming video to 2m20s: dur=%.1fs path=%s", dur, path)
    start, end = "00:00:00", "00:02:20"
    dirname = os.path.dirname(path)
    basename = os.path.basename(path)
    stem, ext = os.path.splitext(basename)
    trimmed_path = os.path.join(dirname, f"{stem}_trimmed{ext}")
    try:
        res = subprocess.run(
            ["bash", script_path, path, start, end],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            if logger:
                logger.warning("Trim script failed (code=%s). stderr=%s", res.returncode, (res.stderr or "").strip())
            return path
        if os.path.isfile(trimmed_path):
            if logger:
                logger.info("Trim successful: %s", trimmed_path)
            return trimmed_path
        for candidate in [
            os.path.join(dirname, f"{stem}_trimmed.mp4"),
            os.path.join(dirname, f"{stem}_trimmed.MP4"),
        ]:
            if os.path.isfile(candidate):
                if logger:
                    logger.info("Trim successful (found candidate): %s", candidate)
                return candidate
        if logger:
            logger.warning("Trim script completed but output not found; using original")
        return path
    except Exception:
        if logger:
            logger.warning("Exception while trimming; using original", exc_info=True)
        return path
