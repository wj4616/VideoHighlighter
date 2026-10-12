// Tauri v2 shell for Video Highlighter.
//
// On startup it launches the Python FastAPI sidecar (the highlight engine) and
// tears it down on exit. In a packaged build the sidecar is a PyInstaller binary
// bundled as a resource; in `tauri dev` we fall back to running the
// project venv's python against sidecar.server so you don't need to
// rebuild the binary on every change.

use std::sync::Mutex;
use tauri::{Manager, RunEvent, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const SIDECAR_PORT: &str = "8756";

#[derive(Default)]
struct SidecarProcess(Mutex<Option<CommandChild>>);

/// Debug builds run the engine straight from the project venv so you don't have
/// to rebuild the PyInstaller binary on every Python change. Release builds run
/// the bundled PyInstaller build (see below).
#[cfg(debug_assertions)]
fn sidecar_command(app: &tauri::AppHandle) -> tauri_plugin_shell::process::Command {
    // Do not depend on the directory the user launches tauri dev from.
    // Use absolute paths: a relative python path resolves against the spawned
    // process's CWD and breaks venv detection ("No pyvenv.cfg file").
    //
    // canonicalize() returns a \\?\-prefixed UNC path on Windows, which CPython
    // mishandles when locating pyvenv.cfg — strip the prefix.
    let raw_root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .canonicalize()
        .expect("failed to resolve project root");
    let project_root = std::path::PathBuf::from(
        raw_root.to_string_lossy().trim_start_matches(r"\\?\").to_string(),
    );
    let py = project_root.join(".venv").join(if cfg!(windows) {
        "Scripts/python.exe"
    } else {
        "bin/python"
    });
    println!("[vh] dev sidecar: {} (cwd {})", py.display(), project_root.display());
    app.shell()
        .command(py.to_string_lossy().to_string())
        .args(["-m", "sidecar.server", "--port", SIDECAR_PORT])
        .current_dir(project_root)
}

/// Release: run the PyInstaller onedir build shipped under `resources/`.
///
/// Not `externalBin`/`.sidecar()`, which take a single file: a onefile build of
/// this engine unpacks ~2GB of torch/openvino to a temp dir on *every* launch,
/// adding many seconds to startup. A onedir build is a folder, so it ships as a
/// bundled resource and we spawn the exe inside it.
#[cfg(not(debug_assertions))]
fn sidecar_command(app: &tauri::AppHandle) -> tauri_plugin_shell::process::Command {
    use tauri::path::BaseDirectory;
    use tauri::Manager as _;

    let exe = app
        .path()
        .resolve(
            if cfg!(windows) {
                "vh-sidecar/vh-sidecar.exe"
            } else {
                "vh-sidecar/vh-sidecar"
            },
            BaseDirectory::Resource,
        )
        .expect("bundled vh-sidecar missing from resources");
    let dir = exe.parent().expect("sidecar exe has no parent").to_path_buf();
    println!("[vh] sidecar: {}", exe.display());
    app.shell()
        .command(exe.to_string_lossy().to_string())
        .args(["--port", SIDECAR_PORT])
        // PyInstaller resolves its bundle relative to the exe, but the engine
        // also writes cache/ and config.yaml relative to the CWD — keep both
        // next to the binary rather than wherever the app was launched from.
        .current_dir(dir)
}

fn spawn_sidecar(app: &tauri::AppHandle) {
    let (mut rx, child) = match sidecar_command(app).spawn() {
        Ok(pair) => pair,
        Err(e) => {
            eprintln!("[vh] failed to spawn sidecar: {e}");
            return;
        }
    };

    // Drain sidecar stdout/stderr to the Tauri console for debugging.
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[sidecar] {}", String::from_utf8_lossy(&line))
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[sidecar] {}", String::from_utf8_lossy(&line))
                }
                _ => {}
            }
        }
    });

    let state: State<SidecarProcess> = app.state();
    *state.0.lock().unwrap() = Some(child);
}

#[cfg(target_os = "linux")]
fn configure_linux_webview() {
    // On NVIDIA + Wayland, WebKitGTK can abort the window with a GDK protocol
    // error or fail to allocate GBM buffers. XWayland plus the non-DMA-BUF
    // renderer works on that combination. Leave explicit user choices intact,
    // and never require XWayland on systems where DISPLAY is absent.
    if std::env::var_os("WAYLAND_DISPLAY").is_some()
        && std::env::var_os("DISPLAY").is_some()
        && std::path::Path::new("/proc/driver/nvidia/version").is_file()
    {
        if std::env::var_os("GDK_BACKEND").is_none() {
            std::env::set_var("GDK_BACKEND", "x11");
        }
        if std::env::var_os("WEBKIT_DISABLE_DMABUF_RENDERER").is_none() {
            std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(target_os = "linux")]
    configure_linux_webview();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(SidecarProcess::default())
        .setup(|app| {
            spawn_sidecar(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // Kill the sidecar so no orphaned Python server survives.
                // Bind the taken child first so the MutexGuard drops before use.
                let state: State<SidecarProcess> = app.state();
                let child = state.0.lock().unwrap().take();
                if let Some(child) = child {
                    let _ = child.kill();
                }
            }
        });
}
