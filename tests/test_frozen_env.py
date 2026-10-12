import os
import sys

from modules.system.frozen_env import restore_linux_library_path


def test_packaged_linux_restores_original_loader_path(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundled/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/user/lib")

    restore_linux_library_path()

    assert os.environ["LD_LIBRARY_PATH"] == "/user/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in os.environ


def test_packaged_linux_removes_injected_path_when_none_existed(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundled/_internal")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    restore_linux_library_path()

    assert "LD_LIBRARY_PATH" not in os.environ


def test_source_run_keeps_environment(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/normal/lib")

    restore_linux_library_path()

    assert os.environ["LD_LIBRARY_PATH"] == "/normal/lib"
