"""Keep system FFmpeg from loading PyInstaller-bundled shared libraries."""

import os
import sys


def restore_linux_library_path() -> None:
    """Restore the pre-PyInstaller loader path for subprocesses on Linux.

    The bootloader points LD_LIBRARY_PATH at _internal so the frozen Python
    process can load its libraries. An external /usr/bin/ffmpeg or ffprobe
    inherits it and can mix incompatible libavcodec/libavutil versions.
    Child PyInstaller executables set their own path when they start.
    """
    if sys.platform != "linux" or not getattr(sys, "frozen", False):
        return
    original = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is None:
        os.environ.pop("LD_LIBRARY_PATH", None)
    else:
        os.environ["LD_LIBRARY_PATH"] = original
