"""Real Qt/FFmpeg thumbnail regression tests on a tiny generated video folder."""
from __future__ import annotations

import subprocess
import shutil
import sys
import os
import time

import pytest


def _make_video(path, color, duration=2):
    from modules.system.app_paths import ffmpeg_exe
    executable = ffmpeg_exe()
    if not (os.path.isfile(executable) or shutil.which(executable)):
        pytest.skip("FFmpeg unavailable in the lightweight test environment")
    subprocess.run(
        [executable, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"color=c={color}:s=320x180:r=5:d={duration}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True, timeout=20, capture_output=True,
    )


def test_ffmpeg_extracts_real_thumbnail_and_skips_nonvideo(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QImage
    from modules.ui.video_thumbnails import thumbnail_bytes

    video = tmp_path / "short.MP4"
    _make_video(video, "red", duration=0.5)  # seek-at-one-second fallback
    image = QImage.fromData(thumbnail_bytes(str(video)))
    assert not image.isNull()
    assert image.width() <= 160 and image.height() <= 90
    color = image.pixelColor(image.width() // 2, image.height() // 2)
    assert color.red() > 150 and color.blue() < 70
    assert thumbnail_bytes(str(tmp_path / "notes.txt")) == b""


def test_qt_picker_shows_three_thumbnail_tiles_and_keeps_multiselect(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QListView
    from modules.ui.local_video_picker import create_video_dialog

    for color in ("red", "green", "blue"):
        _make_video(tmp_path / f"{color}.mp4", color)
    app = QApplication.instance() or QApplication([])
    dialog = create_video_dialog()
    dialog.setDirectory(str(tmp_path))
    try:
        dialog.show()
        controller = dialog.thumbnail_controller
        view = dialog.findChild(QListView, "listView")
        assert view.viewMode() == QListView.ViewMode.IconMode
        assert view.iconSize().width() >= 160
        deadline = time.monotonic() + 6
        while len(controller.cache) < 3 and time.monotonic() < deadline:
            QTest.qWait(50)
        assert len(controller.cache) == 3, (controller.active, controller.failed)

        root = view.rootIndex()
        model = view.model()
        assert model.rowCount(root) == 3
        colors = {}
        for row in range(3):
            index = model.index(row, 0, root)
            icon = model.data(index, Qt.ItemDataRole.DecorationRole)
            assert isinstance(icon, QIcon)
            image = icon.pixmap(160, 90).toImage()
            colors[model.data(index, Qt.ItemDataRole.DisplayRole)] = image.pixelColor(80, 45)
        assert colors["red.mp4"].red() > 150
        assert colors["blue.mp4"].blue() > 150
        assert colors["green.mp4"].green() > 60

        # The thumbnail grid is the real QFileDialog file view, not a separate
        # gallery that loses multi-selection or mounted-drive navigation.
        first = model.index(0, 0, root)
        second = model.index(1, 0, root)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         pos=view.visualRect(first).center())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ControlModifier,
                         pos=view.visualRect(second).center())
        assert len(dialog.selectedFiles()) == 2
    finally:
        dialog.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux process lifecycle")
def test_closing_picker_stops_in_flight_thumbnail_process(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QProcess
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from modules.ui import video_thumbnails
    from modules.ui.local_video_picker import create_video_dialog

    sleep = shutil.which("sleep")
    if not sleep:
        pytest.skip("sleep executable unavailable")
    (tmp_path / "slow.mp4").write_bytes(b"placeholder")
    app = QApplication.instance() or QApplication([])
    dialog = create_video_dialog()
    controller = dialog.thumbnail_controller
    controller.executable = sleep
    monkeypatch.setattr(video_thumbnails, "_arguments", lambda path, seek: ["5"])
    dialog.setDirectory(str(tmp_path))
    dialog.show()
    try:
        deadline = time.monotonic() + 3
        while not controller.processes and time.monotonic() < deadline:
            QTest.qWait(50)
        assert controller.processes
        process = next(iter(controller.processes.values()))
        assert process.state() == QProcess.ProcessState.Running
    finally:
        dialog.close()
    assert controller.closed
    assert not controller.processes
    QTest.qWait(100)
    assert process.state() == QProcess.ProcessState.NotRunning


def test_large_folder_queues_only_visible_videos(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QListView
    from modules.ui.local_video_picker import create_video_dialog

    for index in range(200):
        (tmp_path / f"clip-{index:03}.mp4").touch()
    app = QApplication.instance() or QApplication([])
    dialog = create_video_dialog()
    controller = dialog.thumbnail_controller
    view = dialog.findChild(QListView, "listView")
    monkeypatch.setattr(controller, "_start", lambda path, seek: None)
    dialog.setDirectory(str(tmp_path))
    try:
        dialog.show()
        deadline = time.monotonic() + 3
        while controller.model.rowCount(controller.model.index(str(tmp_path))) < 200 and time.monotonic() < deadline:
            QTest.qWait(50)
        controller._visible()
        assert len(controller.active) <= 2
        assert len(controller.pending) < 60
        assert len(controller.active) + len(controller.pending) < 200
        scrollbar = view.verticalScrollBar()
        assert scrollbar.maximum() > 0
        scrollbar.setValue(scrollbar.maximum())
        QTest.qWait(100)
        controller._visible()
        assert any(int(path.rsplit("-", 1)[1].split(".")[0]) > 100
                   for path in controller.pending)
    finally:
        dialog.close()
