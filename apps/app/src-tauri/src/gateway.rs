//! Self-contained package: the gateway runs as a sidecar of the app, so nothing has to be started by hand.
//!
//! The package folder holds `Mentor.exe` and `gateway/mentor-gateway.exe` (the frozen gateway, see
//! `services/gateway/standalone`). When that file is found (next to the exe, or in Tauri's resource dir) the app is in
//! the standalone flavour: at start it picks a free localhost port, starts the gateway with its data folder, waits for
//! `/healthz`, and answers the page's `gateway_base` command with `http://127.0.0.1:<port>`. The page shows its splash
//! meanwhile. On exit the gateway is killed; if the app crashes instead, the gateway notices (`MENTOR_PARENT_PID`).
//! Without the sidecar file (the hosted-server installers, `pnpm tauri dev`) `gateway_base` answers `null` and the
//! page keeps `VITE_API_BASE`.
//!
//! Data folder: `FECO_APP_DATA_DIR` when the F-Eco launcher sets it (kept across updates), else the app-data folder
//! of the identifier (`%APPDATA%\vn.mentor.app`).

use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Condvar, Mutex};
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

const SIDECAR_DIR: &str = "gateway";
#[cfg(windows)]
const SIDECAR_EXE: &str = "mentor-gateway.exe";
#[cfg(not(windows))]
const SIDECAR_EXE: &str = "mentor-gateway";
const START_TIMEOUT: Duration = Duration::from_secs(90);

#[derive(Clone)]
enum Phase {
    /// Not the standalone flavour, or the start has not been attempted yet.
    Idle,
    Starting,
    Ready(String),
    Failed(String),
}

pub struct Gateway {
    phase: Mutex<Phase>,
    changed: Condvar,
    child: Mutex<Option<Child>>,
}

impl Default for Gateway {
    fn default() -> Self {
        Gateway { phase: Mutex::new(Phase::Idle), changed: Condvar::new(), child: Mutex::new(None) }
    }
}

impl Gateway {
    fn set(&self, p: Phase) {
        *self.phase.lock().unwrap() = p;
        self.changed.notify_all();
    }

    /// Blocks until the gateway is up (or has failed). `Ok(None)` = not the standalone flavour.
    fn wait(&self) -> Result<Option<String>, String> {
        let mut phase = self.phase.lock().unwrap();
        loop {
            match &*phase {
                Phase::Idle => return Ok(None),
                Phase::Ready(base) => return Ok(Some(base.clone())),
                Phase::Failed(e) => return Err(e.clone()),
                Phase::Starting => phase = self.changed.wait(phase).unwrap(),
            }
        }
    }

    /// Stops the sidecar (called when the app exits).
    pub fn stop(&self) {
        if let Some(mut c) = self.child.lock().unwrap().take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }
}

/// `<exe dir>/gateway/mentor-gateway.exe`, else `<resource dir>/gateway/mentor-gateway.exe`.
fn find_sidecar(app: &AppHandle) -> Option<PathBuf> {
    let mut dirs: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        dirs.extend(exe.parent().map(Path::to_path_buf));
    }
    if let Ok(res) = app.path().resource_dir() {
        dirs.push(res);
    }
    dirs.into_iter().map(|d| d.join(SIDECAR_DIR).join(SIDECAR_EXE)).find(|p| p.is_file())
}

pub fn is_standalone(app: &AppHandle) -> bool {
    find_sidecar(app).is_some()
}

fn data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    if let Some(d) = std::env::var_os("FECO_APP_DATA_DIR").filter(|d| !d.is_empty()) {
        return Ok(PathBuf::from(d));
    }
    app.path().app_data_dir().map_err(|e| format!("no data folder: {e}"))
}

fn free_port() -> Result<u16, String> {
    let l = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).map_err(|e| format!("no free port: {e}"))?;
    l.local_addr().map(|a| a.port()).map_err(|e| e.to_string())
}

/// One plain HTTP GET of `/healthz`; true on `200` with the gateway's `{"status":"ok"}`.
fn healthy(port: u16) -> bool {
    let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(500)) else {
        return false;
    };
    let _ = s.set_read_timeout(Some(Duration::from_secs(2)));
    if s.write_all(b"GET /healthz HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n").is_err() {
        return false;
    }
    let mut body = String::new();
    let _ = s.read_to_string(&mut body);
    body.starts_with("HTTP/1.1 200") && body.contains("\"ok\"")
}

fn spawn(sidecar: &Path, data: &Path, port: u16) -> Result<Child, String> {
    std::fs::create_dir_all(data).map_err(|e| format!("cannot create {}: {e}", data.display()))?;
    let mut cmd = Command::new(sidecar);
    cmd.current_dir(sidecar.parent().unwrap_or(Path::new(".")))
        .env("MENTOR_PORT", port.to_string())
        .env("MENTOR_DATA_DIR", data)
        .env("MENTOR_ENV", "standalone")
        .env("MENTOR_PARENT_PID", std::process::id().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.spawn().map_err(|e| format!("cannot start {}: {e}", sidecar.display()))
}

/// Starts the sidecar in the background (no-op when this is not the standalone flavour).
pub fn start(app: &AppHandle) {
    let gw = app.state::<Gateway>();
    let Some(sidecar) = find_sidecar(app) else {
        return;
    };
    gw.set(Phase::Starting);
    let handle = app.clone();
    std::thread::spawn(move || {
        let gw = handle.state::<Gateway>();
        let run = || -> Result<String, String> {
            let data = data_dir(&handle)?;
            let port = free_port()?;
            let child = spawn(&sidecar, &data, port)?;
            *gw.child.lock().unwrap() = Some(child);
            let began = Instant::now();
            while began.elapsed() < START_TIMEOUT {
                if healthy(port) {
                    return Ok(format!("http://127.0.0.1:{port}"));
                }
                if let Some(c) = gw.child.lock().unwrap().as_mut() {
                    if let Ok(Some(status)) = c.try_wait() {
                        return Err(format!("the gateway stopped at start ({status}); see {}", data.join("logs").join("gateway.log").display()));
                    }
                }
                std::thread::sleep(Duration::from_millis(150));
            }
            Err("the gateway did not answer in time".into())
        };
        match run() {
            Ok(base) => gw.set(Phase::Ready(base)),
            Err(e) => {
                eprintln!("gateway: {e}");
                gw.stop();
                gw.set(Phase::Failed(e));
            }
        }
    });
}

/// The page's first call: the gateway's address, or `null` when the app is not the standalone package.
#[tauri::command]
pub async fn gateway_base(app: AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || app.state::<Gateway>().wait())
        .await
        .map_err(|e| e.to_string())?
}
