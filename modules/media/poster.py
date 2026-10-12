"""Small FFmpeg JPEG poster for a local video, independent of Qt and WebKit."""

from __future__ import annotations

import os
import subprocess

from modules.system.app_paths import ffmpeg_exe


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mts", ".m2ts"}


def extract_poster(path: str) -> bytes:
    if os.path.splitext(path)[1].lower() not in VIDEO_EXTENSIONS:
        return b""
    for seek in ("1", "0"):
        try:
            result = subprocess.run(
                [ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-ss", seek, "-i", path, "-frames:v", "1",
                 "-vf", "scale=320:180:force_original_aspect_ratio=decrease",
                 "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                capture_output=True, timeout=6, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return b""
        if result.returncode == 0 and result.stdout.startswith(b"\xff\xd8"):
            return result.stdout
    return b""
