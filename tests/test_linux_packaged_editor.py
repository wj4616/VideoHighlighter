import asyncio
import sys

from sidecar import server


def test_packaged_linux_editor_launches_bundled_viewer(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.touch()
    sidecar = tmp_path / "vh-sidecar" / "vh-sidecar"
    sidecar.parent.mkdir()
    viewer = tmp_path / "vh-viewer" / "vh-viewer"
    viewer.parent.mkdir()
    viewer.touch()
    launches = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(sidecar))
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("subprocess.Popen", lambda cmd, **kw: launches.append((cmd, kw)))

    result = asyncio.run(server.open_editor(server.EditorRequest(video_path=str(video))))

    assert result == {"ok": True}
    assert launches[0][0] == [str(viewer), str(video)]
    assert launches[0][1]["cwd"] == server._ROOT


def test_packaged_linux_editor_reports_missing_viewer(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.touch()
    sidecar = tmp_path / "vh-sidecar" / "vh-sidecar"
    sidecar.parent.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(sidecar))
    monkeypatch.setattr(sys, "platform", "linux")

    result = asyncio.run(server.open_editor(server.EditorRequest(video_path=str(video))))

    assert result == {"ok": False, "error": "Bundled Qt Timeline Viewer not found"}
