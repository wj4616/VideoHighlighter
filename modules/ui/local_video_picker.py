"""Local video picker shared by Simple and Detailed Qt views.

Linux's platform dialog can omit drives mounted outside the home directory.
The Qt dialog exposes live mount shortcuts and still permits navigation from
the filesystem root (including mounts without a conventional media prefix).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QStorageInfo, QUrl, Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QFileSystemModel, QListView, QMessageBox

from modules.segments.simple_run import VIDEO_SUFFIXES
from modules.ui.video_thumbnails import ThumbnailController


def _accessible_directory(path: str) -> bool:
    return bool(path) and os.path.isdir(path) and os.access(path, os.R_OK | os.X_OK)


def mounted_locations() -> list[str]:
    """Fresh navigable locations, including hot-plugged and read-only volumes."""
    home = str(Path.home())
    candidates = [home, os.path.abspath(os.sep)]

    # QStorageInfo knows about mounts outside /media as well (custom fstab,
    # internal disks, network volumes, VeraCrypt, and USB automounts).
    for volume in QStorageInfo.mountedVolumes():
        if volume.isValid() and volume.isReady():
            path = volume.rootPath()
            # Many distros mount /var, /tmp and transient AppImages as separate
            # filesystems. They are not useful video drives and would bury the
            # USB/internal volumes at the bottom of the shortcuts list.
            system_path = path in ("/", "/home", "/run", "/tmp", "/var",
                                   "/var/tmp", "/run/user") or path.startswith(
                ("/proc/", "/sys/", "/dev/", "/var/", "/tmp/", "/run/systemd/",
                 "/run/credentials/", "/run/user/")
            )
            if not system_path:
                candidates.append(path)

    # Some FUSE mounts are absent from QStorageInfo. Discover mounted children
    # without cluttering the sidebar with duplicate /run/media parent folders.
    for root in (f"/run/media/{Path.home().name}", "/run/media", "/media", "/mnt"):
        if _accessible_directory(root):
            try:
                with os.scandir(root) as entries:
                    candidates.extend(entry.path for entry in entries
                                      if entry.is_dir() and os.path.ismount(entry.path))
            except OSError:
                pass  # An inaccessible or disconnected mount does not break browsing.

    locations = []
    seen = set()
    for path in candidates:
        normalized = os.path.normpath(path)
        if normalized not in seen and _accessible_directory(normalized):
            seen.add(normalized)
            locations.append(normalized)
    return locations


def create_video_dialog(parent=None) -> QFileDialog:
    """Build a new dialog so freshly mounted drives appear on every open."""
    dialog = QFileDialog(parent, "Select Video(s)")
    if sys.platform.startswith("linux"):
        # Portal/native dialogs can hide non-home mount points. This Qt dialog
        # honors our sidebar URLs and retains an editable path for any folder.
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
    patterns = " ".join(f"*{ext}" for ext in sorted(VIDEO_SUFFIXES))
    dialog.setNameFilters([
        f"Videos ({patterns} {patterns.upper()})",
        "All files (*)",
    ])
    settings = QSettings("VideoHighlighter", "file-picker")
    last_directory = settings.value("last-video-directory", "", type=str)
    dialog.setDirectory(last_directory if _accessible_directory(last_directory)
                        else str(Path.home()))
    if sys.platform.startswith("linux"):
        dialog.setSidebarUrls([QUrl.fromLocalFile(path) for path in mounted_locations()])
        # Qt can default to a ~70px sidebar, truncating drive names so much
        # that an internal disk and a USB stick are hard to distinguish.
        sidebar = dialog.findChild(QListView, "sidebar")
        if sidebar is not None:
            sidebar.setMinimumWidth(220)
            sidebar.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        dialog.resize(960, 640)
        view = dialog.findChild(QListView, "listView")
        model = dialog.findChild(QFileSystemModel, "qt_filesystem_model")
        if view is not None and model is not None:
            dialog.thumbnail_controller = ThumbnailController(dialog, view, model)
    return dialog


def pick_video_files(parent=None) -> list[str]:
    dialog = create_video_dialog(parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return []
    selected = dialog.selectedFiles()
    files = [path for path in selected if os.path.isfile(path) and os.access(path, os.R_OK)]
    if len(files) != len(selected):
        QMessageBox.warning(parent, "Video unavailable",
                            "Some selected files are no longer readable. Mount or unlock "
                            "the drive and try again.")
    if files:
        QSettings("VideoHighlighter", "file-picker").setValue(
            "last-video-directory", os.path.dirname(files[0]))
    return list(dict.fromkeys(files))
