"""Qt video picker: live volumes, filters, and removable-drive recovery."""
from pathlib import Path
import sys

import pytest


def test_mount_shortcuts_filter_system_and_missing_volumes(monkeypatch):
    pytest.importorskip("PySide6")
    from modules.ui import local_video_picker as picker

    class Volume:
        def __init__(self, path, ready=True):
            self.path, self.ready = path, ready

        def isValid(self):
            return True

        def isReady(self):
            return self.ready

        def rootPath(self):
            return self.path

    class Storage:
        @staticmethod
        def mountedVolumes():
            return [Volume("/tmp"), Volume("/run/media/test/USB disk"),
                    Volume("/mnt/internal"), Volume("/mnt/offline", ready=False),
                    Volume("/run/media/test/USB disk")]

    monkeypatch.setattr(picker, "QStorageInfo", Storage)
    monkeypatch.setattr(picker, "_accessible_directory",
                        lambda path: path in (str(Path.home()), "/", "/mnt",
                                              "/run/media/test/USB disk", "/mnt/internal"))
    locations = picker.mounted_locations()
    assert "/run/media/test/USB disk" in locations
    assert "/mnt/internal" in locations
    assert locations.count("/run/media/test/USB disk") == 1
    assert "/mnt/offline" not in locations
    assert "/tmp" not in locations


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux mount sidebar")
def test_qt_dialog_lists_live_volumes_and_recovers_unmounted_last_folder(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QFileDialog, QListView, QWidget
    from modules.ui import local_video_picker as picker

    app = QApplication.instance() or QApplication([])

    class Settings:
        def value(self, key, default, type=str):
            return "/previous/removed-drive"

    monkeypatch.setattr(picker, "QSettings", lambda *args: Settings())
    monkeypatch.setattr(picker, "mounted_locations",
                        lambda: [str(Path.home()), "/", "/run/media/test/USB disk"])
    host = QWidget()
    dialog = picker.create_video_dialog(host)
    try:
        host.show()
        dialog.show()
        assert dialog.fileMode() == QFileDialog.FileMode.ExistingFiles
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog)
        assert dialog.directory().absolutePath() == str(Path.home())
        assert "/run/media/test/USB disk" in [u.toLocalFile() for u in dialog.sidebarUrls()]
        assert dialog.findChild(QListView, "sidebar").minimumWidth() >= 220
        assert "*.webm" in dialog.nameFilters()[0]
        assert "*.MP4" in dialog.nameFilters()[0]
        assert "All files (*)" in dialog.nameFilters()
    finally:
        dialog.close()
        host.close()


def test_selection_deduplicates_and_remembers_only_readable_files(monkeypatch, tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QDialog
    from modules.ui import local_video_picker as picker

    video = tmp_path / "test.MP4"
    video.write_bytes(b"data")
    messages = []
    remembered = {}

    class Dialog:
        def exec(self):
            return QDialog.DialogCode.Accepted

        def selectedFiles(self):
            return [str(video), str(video), str(tmp_path / "unmounted.mp4")]

    class Settings:
        def setValue(self, key, value):
            remembered[key] = value

    monkeypatch.setattr(picker, "create_video_dialog", lambda parent: Dialog())
    monkeypatch.setattr(picker, "QSettings", lambda *args: Settings())
    monkeypatch.setattr(picker.QMessageBox, "warning",
                        lambda *args: messages.append(args))
    assert picker.pick_video_files() == [str(video)]
    assert remembered["last-video-directory"] == str(tmp_path)
    assert len(messages) == 1


def test_main_video_entry_uses_shared_picker():
    source = Path("main.py").read_text(encoding="utf-8")
    assert "file_paths = pick_video_files(self)" in source
