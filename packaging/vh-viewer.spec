# Standalone native Timeline Viewer bundled beside the Tauri sidecar on Linux.
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(SPEC)), ".."))


def source(*parts):
    return os.path.join(ROOT, *parts)


a = Analysis(
    [source("signal_timeline_viewer.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (source("config.yaml"), "."),
        (source("yolo_objects_labels.json"), "."),
        (source("kinetics_700_labels.json"), "."),
        (source("modules"), "modules"),
        (source("video_ai_editor"), "video_ai_editor"),
        (source("assets"), "assets"),
    ],
    hiddenimports=[],
    hookspath=[source("packaging", "pyinstaller-hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["nncf", "PyQt5"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="vh-viewer",
    debug=False, strip=False, upx=False, console=True,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=False, name="vh-viewer",
)
