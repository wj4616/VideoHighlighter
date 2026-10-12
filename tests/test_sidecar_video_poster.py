"""Native WebKit must not decode input footage just to render its cards."""

from __future__ import annotations

import asyncio
import shutil
import subprocess

import pytest
from fastapi import HTTPException

from modules.media.poster import extract_poster
from sidecar.server import video_poster


def test_missing_video_is_404(tmp_path):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(video_poster(str(tmp_path / "missing.mp4")))
    assert exc.value.status_code == 404


def test_rejects_non_video_even_when_it_exists(tmp_path):
    file = tmp_path / "notes.txt"
    file.write_text("hello")
    assert extract_poster(str(file)) == b""
    with pytest.raises(HTTPException) as exc:
        asyncio.run(video_poster(str(file)))
    assert exc.value.status_code == 422


def test_short_video_has_ffmpeg_poster_and_metadata(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg unavailable")
    path = tmp_path / "red.mp4"
    subprocess.run(
        [ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         "color=c=red:s=320x180:r=5:d=0.5", "-c:v", "libx264", "-pix_fmt",
         "yuv420p", str(path)],
        check=True, capture_output=True, timeout=20,
    )
    response = asyncio.run(video_poster(str(path)))
    assert response.media_type == "image/jpeg"
    assert response.body.startswith(b"\xff\xd8")
    assert response.headers["cache-control"] == "no-store"
