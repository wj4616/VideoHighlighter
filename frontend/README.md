# Video Highlighter — web UI

A Tauri v2 desktop app: React + shadcn/ui front end, with the existing Python
engine running behind it as a FastAPI sidecar.

```
frontend/           Vite + React + Tailwind v4 + shadcn/ui   (this directory)
frontend/src-tauri/ Tauri shell (WebKitGTK on Linux, WebView2 on Windows); spawns and reaps the sidecar
sidecar/server.py   FastAPI over the engine; streams log/progress on a WebSocket
sidecar/worker.py   Runs each job in a child process (see "Why a child process")
```

The engine itself is untouched: the sidecar calls the same
`pipeline.run_highlighter` the Qt app calls, with `log_fn` / `progress_fn` /
`cancel_flag` routed to a socket instead of Qt signals. Heavy compute stays in
Python, so nothing performance-sensitive crosses the webview boundary. The
native Qt timeline viewer is still used for the video-heavy surfaces — the
"Timeline Viewer" button launches it.

## What the web app adds over the Qt GUI

- **Folder-at-once input** — "Add Folder" scans a directory (recursively) for
  videos, so you can point it at a Downloads/GoPro folder instead of picking
  files one by one (`GET /scan-folder`).
- **Reel + music** — with more than one video, "Combine into one reel" stitches
  the produced highlights into a single video after the run. An optional music
  bed is applied once to the reel, in one of three modes: **replace** clip
  audio, **mix** under it, or **duck** it (music dips when the clip is loud).
  Runs as a `combine` job (`POST /combine`).
- **Rotation-correct output** — the engine reads each clip's orientation
  metadata (`GET /video-info` → `rotation`) and bakes rotated phone/GoPro
  footage upright when cutting and combining, so the reel isn't sideways.
- **Blur gate** — "Penalize blurry clips" scores candidates by
  variance-of-Laplacian sharpness and demotes soft ones (off by default).

These live in the engine (`modules/{video_probe,combine_videos,music_track,clip_quality}.py`),
so the Qt app can call them too; the web UI is just the first to surface them.

## Develop

```powershell
.\dev.ps1
```

Rust on Windows needs the MSVC toolchain on PATH and `LIB` set. The default
shell doesn't have it, so `dev.ps1` sources `vcvars64.bat` before running
`pnpm tauri dev` — without it you get `LNK1104: cannot open file 'msvcrt.lib'`.

In dev the shell runs the sidecar straight from the project venv
(`.venv/Scripts/python.exe -m sidecar.server`), so Python changes need only a
restart, not a rebuild. Release builds use the bundled PyInstaller output.

To run the sidecar on its own (useful when debugging the API):

```powershell
..\.venv\Scripts\python.exe -m sidecar.server --port 8756
# then http://127.0.0.1:8756/docs
```

## Build

The sidecar has to be built first — `tauri.conf.json` bundles
`dist-sidecar/vh-sidecar` as a resource.

```powershell
# from the project root
.\.venv\Scripts\python.exe -m PyInstaller packaging/vh-sidecar.spec --noconfirm `
  --distpath dist-sidecar --workpath build-sidecar

cd frontend
pnpm tauri build
```

CI does the same in the `build-web-windows` job of
`.github/workflows/build-release.yaml`.

### Why a resource, not `externalBin`

Tauri's `externalBin` takes a single file, which would mean a PyInstaller
*onefile* build — and that unpacks ~2GB of torch/openvino into a temp directory
on **every** launch. The spec builds *onedir* instead; the folder ships as a
bundled resource and the Rust shell resolves `vh-sidecar/vh-sidecar.exe` inside
it via the path resolver.

### Why a child process

torch's native runtime can hard-crash the interpreter (access violation
`0xc0000005` in `c10.dll`) when a run is cancelled mid-inference. In-process
that would kill the HTTP server and leave the UI staring at a dead socket, so
each job runs in a spawned child; if it dies, the parent reports
"The processing engine stopped unexpectedly" and stays up for the next run.
`main.py` works around the same class of problem by hard-exiting on close.

## Linux desktop (native picker)

The React interface can run inside a native Tauri window on Linux; browser preview mode
cannot expose absolute paths or a native picker. The debug shell starts the local Python
sidecar from the repository virtual environment and stops it on exit. Do not start a
separate server on port 8756 while using the shell.

From the repository root, after installing Rust/Cargo, the Tauri GTK/WebKit development
libraries, Node/Corepack, and the full Python requirements:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend
corepack pnpm install --frozen-lockfile
PATH="$HOME/.cargo/bin:$PATH" corepack pnpm tauri dev
```

On Linux, the automatically merged `tauri.linux.conf.json` removes the Windows-only
bundled sidecar resource during development and configures a local Vite server.
The native picker uses the Tauri dialog plugin. The Timeline Viewer remains a
separate Qt window started by the Python sidecar. On NVIDIA Wayland desktops
with XWayland available, the shell defaults to X11 and disables WebKitGTK's
DMA-BUF renderer before GTK starts; explicit GDK_BACKEND or
WEBKIT_DISABLE_DMABUF_RENDERER environment settings take precedence.

For a self-contained **release**, bundle both onedir Python executables before
building Tauri. The release config adds them as sibling resources; unlike the
source launch, a frozen sidecar cannot execute the viewer Python script:

```sh
cd /path/to/VideoHighlighter
.venv/bin/python -m pip install pyinstaller
.venv/bin/python -m PyInstaller packaging/vh-sidecar.spec --noconfirm --distpath dist-sidecar --workpath build-sidecar
.venv/bin/python -m PyInstaller packaging/vh-viewer.spec --noconfirm --distpath dist-viewer --workpath build-viewer
cd frontend
PATH="$HOME/.cargo/bin:$PATH" corepack pnpm tauri build --no-bundle --config src-tauri/tauri.linux-release.conf.json
cd ..
packaging/build-linux-folder.sh "$PWD/dist-linux-portable"
tar --numeric-owner -I "zstd -T4 -3" -cf dist-linux-portable/VideoHighlighter-Linux-x86_64.tar.zst -C dist-linux-portable usr
```
Archive the new folder **before launching it**: the running sidecar may update
runtime files, and tar must not capture those or a changing directory. The
portable folder and archive include the upstream AGPL-3.0 LICENSE and COPYRIGHT
notices; fork
source: https://github.com/wj4616/VideoHighlighter. The release is not covered by
the source-mode smoke test: verify the bundled sidecar, model assets, native
picker and Qt Timeline Viewer independently.

On Arch/CachyOS, a matching `usr/bin` + `usr/lib/Video Highlighter` folder can
run without installing system-wide, provided WebKitGTK 4.1 and GTK 3 are
installed. Keep the two directories together; the sidecar and viewer are looked
up relative to the desktop executable. After building the Tauri binary and
both Python bundles, `packaging/build-linux-folder.sh /new/output/path` from the
repository creates this layout without replacing any existing destination.
Run `/new/output/path/usr/bin/video-highlighter`. This is a local Linux folder,
not an AppImage or a universal cross-distribution package. The oversized
Tauri-generated `.deb` exceeded the `ar` member-size limit and was invalid;
bundling is deliberately disabled until that package can be made smaller.
