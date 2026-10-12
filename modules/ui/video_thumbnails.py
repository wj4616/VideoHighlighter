"""Non-blocking video thumbnails for the Qt QFileDialog icon view.

Only visible video cells are queued; FFmpeg work never runs on the UI thread.
The cache is per dialog and in memory so footage previews are not persisted.
"""
from __future__ import annotations

from collections import OrderedDict, deque
import math
import os
import subprocess

from PySide6.QtCore import QEvent, QIdentityProxyModel, QObject, QProcess, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFileSystemModel, QListView

from modules.segments.simple_run import VIDEO_SUFFIXES
from modules.system.app_paths import ffmpeg_exe


THUMBNAIL_SIZE = QSize(160, 90)
CELL_SIZE = QSize(190, 130)
MAX_CACHE = 256
VIDEO_EXTENSIONS = {ext.lstrip(".") for ext in VIDEO_SUFFIXES}


def _arguments(path: str, seek: str) -> list[str]:
    return ["-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", seek, "-i", path, "-frames:v", "1",
            "-vf", "scale=160:90:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]


def thumbnail_bytes(path: str, executable: str | None = None) -> bytes:
    """Extract a small JPEG near the beginning, or return empty on failure."""
    if os.path.splitext(path)[1].lower() not in VIDEO_SUFFIXES:
        return b""
    executable = executable or ffmpeg_exe()
    for seek in ("1", "0"):
        try:
            result = subprocess.run(
                [executable, *_arguments(path, seek)],
                capture_output=True, timeout=6, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return b""
        if result.returncode == 0 and result.stdout:
            return result.stdout
    return b""


class _ThumbnailProxy(QIdentityProxyModel):
    """Override cached file icons without fighting QFileSystemModel's icon cache."""

    def __init__(self, controller: "ThumbnailController"):
        super().__init__(controller)
        self.controller = controller

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            path = self.controller.model.filePath(self.mapToSource(index))
            cached = self.controller.cache.get(path)
            if cached is not None:
                return cached
        return super().data(index, role)


class ThumbnailController(QObject):
    """Fill currently visible QFileSystemModel icons as background jobs finish."""

    def __init__(self, dialog, view: QListView, model: QFileSystemModel):
        super().__init__(dialog)
        self.view = view
        self.model = model
        self.cache: OrderedDict[str, QIcon] = OrderedDict()
        self.executable = ffmpeg_exe()  # resolve once, not in each worker thread
        self.failed: set[str] = set()
        self.active: set[str] = set()
        self.pending: deque[str] = deque()
        self.processes: dict[str, QProcess] = {}
        self.closed = False
        self.proxy = _ThumbnailProxy(self)
        dialog.setProxyModel(self.proxy)

        view.setViewMode(QListView.ViewMode.IconMode)
        view.setIconSize(THUMBNAIL_SIZE)
        view.setGridSize(CELL_SIZE)
        view.setResizeMode(QListView.ResizeMode.Adjust)
        view.setMovement(QListView.Movement.Static)
        view.setWordWrap(True)
        view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        view.viewport().installEventFilter(self)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._visible)
        model.directoryLoaded.connect(self.schedule)
        dialog.directoryEntered.connect(self.schedule)
        dialog.finished.connect(self.shutdown)
        view.verticalScrollBar().valueChanged.connect(self.schedule)
        self.schedule()

    def eventFilter(self, watched, event):
        try:
            viewport = self.view.viewport()
        except RuntimeError:
            return False  # Qt is tearing down the dialog.
        if watched is viewport and event.type() in (
            QEvent.Type.Show, QEvent.Type.Resize,
        ):
            self.schedule()
        return super().eventFilter(watched, event)

    def schedule(self, *_args):
        if not self.closed:
            self.timer.start(70)  # coalesce rapid scrolling and directory changes

    def _visible(self):
        root = self.view.rootIndex()
        if not root.isValid():
            return
        columns = max(1, self.view.viewport().width() // CELL_SIZE.width())
        first_row = self.view.verticalScrollBar().value() // CELL_SIZE.height()
        start = max(0, first_row * columns)
        count = (math.ceil(self.view.viewport().height() / CELL_SIZE.height()) + 2) * columns
        self.pending.clear()  # scrolling shouldn't decode the old view first
        for row in range(start, min(self.proxy.rowCount(root), start + count)):
            index = self.proxy.index(row, 0, root)
            info = self.model.fileInfo(self.proxy.mapToSource(index))
            path = info.absoluteFilePath()
            if (info.isFile() and info.suffix().lower() in VIDEO_EXTENSIONS
                    and path not in self.cache and path not in self.failed
                    and path not in self.active):
                self.pending.append(path)
        self._launch()

    def _launch(self):
        while self.pending and len(self.active) < 2:
            path = self.pending.popleft()
            if path in self.active or path in self.cache or path in self.failed:
                continue
            self.active.add(path)
            self._start(path, "1")

    def _start(self, path: str, seek: str):
        process = QProcess(self)
        output = bytearray()
        self.processes[path] = process
        process.setProgram(self.executable)
        process.setArguments(_arguments(path, seek))
        process.readyReadStandardOutput.connect(
            lambda: output.extend(bytes(process.readAllStandardOutput())))
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.timeout.connect(process.kill)
        timer.start(6000)

        def finished(*_args):
            if self.processes.get(path) is not process:
                return
            timer.stop()
            output.extend(bytes(process.readAllStandardOutput()))
            self.processes.pop(path, None)
            success = process.exitCode() == 0 and bool(output)
            process.deleteLater()
            if self.closed:
                return
            if success:
                self._ready(path, bytes(output))
            elif seek == "1":
                self._start(path, "0")
            else:
                self._ready(path, b"")

        process.finished.connect(finished)
        process.errorOccurred.connect(
            lambda error: finished() if error == QProcess.ProcessError.FailedToStart else None)
        process.start()

    def shutdown(self, *_args):
        self.closed = True
        self.timer.stop()
        self.pending.clear()
        for process in self.processes.values():
            process.blockSignals(True)
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
        self.processes.clear()
        self.active.clear()

    def _ready(self, path: str, data: bytes):
        self.active.discard(path)
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            self.cache[path] = QIcon(pixmap)
            if len(self.cache) > MAX_CACHE:
                self.cache.popitem(last=False)
            source_index = self.model.index(path)
            index = self.proxy.mapFromSource(source_index)
            if index.isValid():
                self.proxy.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])
        else:
            self.failed.add(path)
        self._launch()
