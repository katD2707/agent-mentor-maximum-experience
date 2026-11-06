//! Mentor desktop pop-up: a floating "M" bubble plus a compact chat panel.
//!
//! Windows:
//! - `bubble`: tiny transparent always-on-top window (local page `src/bubble.html`), draggable, snaps
//!   to the nearest edge of the monitor's work area, position saved in `bubble.json`.
//! - `panel`: frameless always-on-top window that loads `$WEB_ORIGIN/popup` from the web app. It is
//!   hidden, never closed, so its page keeps the chat WebSocket open and can report unread messages
//!   while collapsed. The page reaches the shell only through the `desktop_*` commands, granted by a
//!   runtime capability limited to `$WEB_ORIGIN`.
//! - `balloon`: transparent always-on-top speech balloon beside the bubble (local page
//!   `src/balloon.html`) for the nudges the panel page forwards with `desktop_nudge`; see `nudge.rs`.
//!   It is created visible but empty and click-through, and is only ever moved, filled and made
//!   clickable, so it never activates (steals focus from) the user's current app.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod nudge;

use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use nudge::{Nudge, NudgeAction, NudgeMode, NudgeQueue, Pushed, Route, RouteInput};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::ipc::CapabilityBuilder;
use tauri::menu::{CheckMenuItem, Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, RunEvent, Url, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder, Window, WindowEvent, Wry,
};
use tauri_plugin_autostart::ManagerExt as _;
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_opener::OpenerExt;

const BUBBLE: &str = "bubble";
const PANEL: &str = "panel";
const BALLOON: &str = "balloon";

/// Event sent to the panel page when the user clicks a nudge (balloon or toast): `{id, action}`.
const NUDGE_EVENT: &str = "mentor://nudge-action";
/// Pause between two queued balloons, so they read as two messages.
const NEXT_NUDGE_AFTER: Duration = Duration::from_millis(700);

/// Logical sizes (scaled by the monitor's DPI factor).
const BUBBLE_WIN: f64 = 72.0; // window; the circle sits in the middle (margin for shadow and badge)
const BUBBLE_CIRCLE: f64 = 56.0;
const EDGE_MARGIN: f64 = 12.0; // gap between the circle and the screen edge
const DEFAULT_BOTTOM_MARGIN: f64 = 24.0;
const PANEL_W: f64 = 380.0;
const PANEL_H: f64 = 560.0;
const PANEL_GAP: f64 = 8.0;
/// `resizable` of the bubble and the balloon, windows only the code sizes (no frame; the bubble's
/// min = max size pins it). Linux: GTK gives a non-resizable window the natural size of its content
/// instead of the size set (tao turns resizing off after the first configure), which under X11
/// made the 72x72 bubble grow to 200x200 a moment after it appeared and kept the balloon at least
/// 200 px tall; so there they stay resizable.
const SIZED_BY_CODE_RESIZABLE: bool = cfg!(target_os = "linux");

const DEFAULT_WEB_ORIGIN: &str = "http://localhost:3000";
/// If the page has not reported a session by then (web app down?), show the panel so the user sees why.
const STARTUP_SHOW_AFTER: Duration = Duration::from_secs(8);

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Session {
    Unknown,
    SignedOut,
    SignedIn,
}

/// When the bubble shows (`bubble_mode` in `bubble.json`). The user's hide/show toggle wins over both.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Default, Serialize)]
#[serde(rename_all = "snake_case")]
enum BubbleMode {
    /// Also while signed out (muted look; a click opens the login page), so the user sees the app runs.
    #[default]
    Always,
    /// Only while signed in (the original behavior).
    SignedIn,
}

impl<'de> Deserialize<'de> for BubbleMode {
    /// Lenient: a missing, null or unknown value means the default instead of discarding the whole file.
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        Ok(match Option::<String>::deserialize(d)?.as_deref() {
            Some("signed_in") => BubbleMode::SignedIn,
            _ => BubbleMode::Always,
        })
    }
}

/// Whether the bubble window should be visible.
fn bubble_should_show(session: Session, mode: BubbleMode, hidden_by_user: bool) -> bool {
    !hidden_by_user
        && match mode {
            BubbleMode::Always => true,
            BubbleMode::SignedIn => session == Session::SignedIn,
        }
}

struct Shared {
    web_origin: String,
    inner: Mutex<Inner>,
    tray_bubble_item: Mutex<Option<CheckMenuItem<Wry>>>,
    /// "Bong bóng: luôn hiện" / "Bong bóng: chỉ khi đã đăng nhập", kept mutually exclusive.
    tray_mode_items: Mutex<Option<(CheckMenuItem<Wry>, CheckMenuItem<Wry>)>>,
    tray_autostart_item: Mutex<Option<CheckMenuItem<Wry>>>,
    /// "Nhắc nhở: bong bóng / thông báo Windows / tắt", kept mutually exclusive.
    tray_nudge_items: Mutex<Option<[CheckMenuItem<Wry>; 3]>>,
}

struct Inner {
    session: Session,
    unread: u32,
    /// The user hid the bubble from the tray or its menu (it stays hidden until they show it again).
    bubble_hidden_by_user: bool,
    bubble_mode: BubbleMode,
    /// Cursor offset from the bubble's top-left while dragging (physical pixels).
    drag_offset: Option<(f64, f64)>,
    nudge_mode: NudgeMode,
    nudges: NudgeQueue,
    /// The balloon of the current nudge is on screen (placed, clickable).
    balloon_shown: bool,
    /// The app the user was in when the balloon appeared (HWND), to give focus back to it if they
    /// clicked into the balloon and it then goes away.
    balloon_prev_foreground: isize,
    /// Mascot state the panel page reported (`desktop_mascot`): idle, thinking, sleepy, calm...
    panel_mascot: &'static str,
    /// Notification ids for the toasts (the plugin wants an i32).
    toast_seq: i32,
}

/// `bubble.json`. Every field has a default, so older files (or ones missing a field) still load.
#[derive(Serialize, Deserialize, Default, Debug)]
#[serde(default)]
struct Prefs {
    /// Bubble window top-left in physical pixels.
    bubble_x: Option<i32>,
    bubble_y: Option<i32>,
    bubble_hidden: bool,
    bubble_mode: BubbleMode,
    /// `"balloon" | "toast" | "off"`; older files without it get `"balloon"`.
    nudge_mode: NudgeMode,
}

#[derive(Clone, Copy, Debug)]
struct Rect {
    x: i32,
    y: i32,
    w: i32,
    h: i32,
}

impl Rect {
    fn right(&self) -> i32 {
        self.x + self.w
    }
    fn bottom(&self) -> i32 {
        self.y + self.h
    }
    fn contains(&self, px: i32, py: i32) -> bool {
        px >= self.x && px < self.right() && py >= self.y && py < self.bottom()
    }
    fn distance2(&self, px: i32, py: i32) -> i64 {
        let dx = (self.x - px).max(0).max(px - self.right()) as i64;
        let dy = (self.y - py).max(0).max(py - self.bottom()) as i64;
        dx * dx + dy * dy
    }
}

// ------------------------------------------------------------------ config and prefs

/// Where the panel loads the web app from.
///
/// - Release builds: `WEB_ORIGIN` baked in at build time (`build-release.ps1 -WebOrigin`), so end
///   users never set anything and a stray environment variable cannot point the panel elsewhere.
///   Only a release built without one reads `WEB_ORIGIN` at run time.
/// - Debug builds: `WEB_ORIGIN` at run time, else at build time.
///
/// Falls back to the dev default when unset or refused by [`parse_web_origin`].
fn web_origin() -> String {
    let release = !cfg!(debug_assertions);
    let runtime = std::env::var("WEB_ORIGIN")
        .ok()
        .filter(|s| !s.trim().is_empty());
    let baked = option_env!("WEB_ORIGIN")
        .filter(|s| !s.trim().is_empty())
        .map(str::to_owned);
    let raw = if release {
        baked.or(runtime)
    } else {
        runtime.or(baked)
    };
    let Some(raw) = raw else {
        return DEFAULT_WEB_ORIGIN.to_owned();
    };
    match parse_web_origin(&raw, release) {
        Ok(origin) => origin,
        Err(e) => {
            eprintln!("WEB_ORIGIN {raw:?}: {e}; using {DEFAULT_WEB_ORIGIN}");
            DEFAULT_WEB_ORIGIN.to_owned()
        }
    }
}

/// `scheme://host[:port]` of an http(s) URL. With `release`, plain http is refused unless the host
/// is this machine (`localhost`, `127.0.0.1`, `[::1]`): the panel page gets IPC access, so it must
/// not be served over a network in clear text. `build.rs` applies the same rule to the baked value.
fn parse_web_origin(raw: &str, release: bool) -> Result<String, String> {
    let u = Url::parse(raw.trim()).map_err(|e| format!("not a URL ({e})"))?;
    if !matches!(u.scheme(), "http" | "https") || u.host().is_none() {
        return Err("not an http(s) origin".into());
    }
    if release && u.scheme() == "http" && !is_loopback_host(u.host_str().unwrap_or_default()) {
        return Err("plain http is only allowed for localhost in release builds; use https".into());
    }
    Ok(u.origin().ascii_serialization())
}

fn is_loopback_host(host: &str) -> bool {
    matches!(host, "localhost" | "127.0.0.1" | "[::1]")
}

// ------------------------------------------------------------------ autostart entry quoting

/// The autostart plugin writes the Run entry as `C:\path\mentor-desktop.exe ` without quotes; with a
/// space in the install path (a user name with a space, a custom folder) Windows may run the wrong
/// program or nothing at all. Returns the quoted command line when `current` is that unquoted form of
/// `exe` (optionally followed by arguments); `None` when it is already quoted or points elsewhere
/// (e.g. another copy of the app, which keeps its own entry).
#[cfg(any(windows, test))]
fn quoted_run_command(current: &str, exe: &str) -> Option<String> {
    let cur = current.trim();
    if cur.starts_with('"') || exe.is_empty() || cur.len() < exe.len() {
        return None;
    }
    let (head, rest) = cur.split_at_checked(exe.len())?;
    if !head.eq_ignore_ascii_case(exe) || !(rest.is_empty() || rest.starts_with(' ')) {
        return None;
    }
    Some(format!("\"{exe}\"{}", rest.trim_end()))
}

/// Rewrites our HKCU Run entry (named after the product, like the plugin and the NSIS uninstaller
/// do) with a quoted path. Called after enabling autostart and at startup, which also repairs
/// entries written by older builds.
#[cfg(windows)]
fn quote_autostart_entry(app: &AppHandle) {
    let Ok(exe) = std::env::current_exe() else {
        return;
    };
    let name = app.package_info().name.clone();
    if let Err(e) = win_run_key::requote(&name, &exe.display().to_string()) {
        eprintln!("autostart: could not quote the Run entry: {e}");
    }
}

/// Linux: the plugin (auto-launch) writes `~/.config/autostart/<productName>.desktop` with
/// `Exec=<path> ` unquoted. For the .deb that is `/usr/bin/mentor-desktop`, but an AppImage runs
/// from wherever the user saved it, and on a Vietnamese desktop the downloads folder is
/// `~/Tải về`: the session would then try to start `~/Tải` and nothing happens at login. Same
/// repair as on Windows: quote our own unquoted entry after enabling it and at startup.
#[cfg(target_os = "linux")]
fn quote_autostart_entry(app: &AppHandle) {
    // The plugin points the entry at $APPIMAGE (the file the user runs), not at the binary inside
    // the AppImage's temporary mount, which changes on every launch.
    let appimage = app.env().appimage.map(PathBuf::from);
    let Some(exe) = appimage.or_else(|| std::env::current_exe().ok()) else {
        return;
    };
    // auto-launch uses $HOME/.config/autostart, not $XDG_CONFIG_HOME.
    let Ok(home) = app.path().home_dir() else {
        return;
    };
    let name = &app.package_info().name;
    let path = home.join(".config").join("autostart").join(format!("{name}.desktop"));
    let Ok(text) = fs::read_to_string(&path) else {
        return;
    };
    if let Some(fixed) = quoted_desktop_exec(&text, &exe.display().to_string()) {
        if let Err(e) = fs::write(&path, fixed) {
            eprintln!("autostart: could not quote {}: {e}", path.display());
        }
    }
}

#[cfg(not(any(windows, target_os = "linux")))]
fn quote_autostart_entry(_app: &AppHandle) {}

/// The desktop entry `text` with its `Exec=` line quoted when it is the unquoted path of `exe`
/// (optionally followed by arguments); `None` when there is nothing to fix: already quoted,
/// another program, or a path that needs no quotes. Quoting follows the Desktop Entry spec
/// (`%` doubled as it is a field-code prefix); a path with `"`, `` ` ``, `$`, `\` or a line break
/// would need escapes the launchers disagree on, so it is left alone.
#[cfg(any(target_os = "linux", test))]
fn quoted_desktop_exec(text: &str, exe: &str) -> Option<String> {
    let plain = |c: char| c.is_ascii_alphanumeric() || "/._-+,:@".contains(c);
    if exe.is_empty() || exe.chars().all(plain) || exe.contains(['"', '`', '$', '\\', '\n', '\r']) {
        return None;
    }
    let mut changed = false;
    let lines: Vec<String> = text
        .lines()
        .map(|line| {
            let fixed = line
                .strip_prefix("Exec=")
                .and_then(|v| v.strip_prefix(exe))
                .filter(|rest| rest.is_empty() || rest.starts_with(' '))
                .map(|rest| format!("Exec=\"{}\"{}", exe.replace('%', "%%"), rest.trim_end()));
            changed |= fixed.is_some();
            fixed.unwrap_or_else(|| line.to_owned())
        })
        .collect();
    changed.then(|| lines.join("\n") + "\n")
}

#[cfg(windows)]
mod win_run_key {
    use windows_sys::Win32::Foundation::ERROR_SUCCESS;
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegOpenKeyExW, RegQueryValueExW, RegSetValueExW, HKEY, HKEY_CURRENT_USER,
        KEY_QUERY_VALUE, KEY_SET_VALUE, REG_SZ,
    };

    const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";

    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(Some(0)).collect()
    }

    /// Quote the value `name` under HKCU\...\Run if it is the unquoted path of `exe`.
    pub fn requote(name: &str, exe: &str) -> Result<(), String> {
        let path = wide(RUN_KEY);
        let value_name = wide(name);
        let mut key: HKEY = std::ptr::null_mut();
        // SAFETY: plain Win32 registry calls with valid, NUL-terminated UTF-16 buffers; the key
        // handle is closed on every path below.
        unsafe {
            if RegOpenKeyExW(
                HKEY_CURRENT_USER,
                path.as_ptr(),
                0,
                KEY_QUERY_VALUE | KEY_SET_VALUE,
                &mut key,
            ) != ERROR_SUCCESS
            {
                return Ok(()); // no Run key: nothing to fix
            }
            let mut kind = 0u32;
            let mut buf = vec![0u16; 4096];
            let mut len = (buf.len() * 2) as u32;
            let read = RegQueryValueExW(
                key,
                value_name.as_ptr(),
                std::ptr::null(),
                &mut kind,
                buf.as_mut_ptr().cast(),
                &mut len,
            );
            let mut result = Ok(());
            if read == ERROR_SUCCESS && kind == REG_SZ {
                let n = (len as usize / 2).min(buf.len());
                let current = String::from_utf16_lossy(&buf[..n]);
                let current = current.trim_end_matches('\0');
                if let Some(fixed) = super::quoted_run_command(current, exe) {
                    let data = wide(&fixed);
                    let set = RegSetValueExW(
                        key,
                        value_name.as_ptr(),
                        0,
                        REG_SZ,
                        data.as_ptr().cast(),
                        (data.len() * 2) as u32,
                    );
                    if set != ERROR_SUCCESS {
                        result = Err(format!("RegSetValueExW failed ({set})"));
                    }
                }
            }
            RegCloseKey(key);
            result
        }
    }
}

fn prefs_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_config_dir()
        .ok()
        .map(|d| d.join("bubble.json"))
}

fn load_prefs(app: &AppHandle) -> Prefs {
    prefs_path(app)
        .and_then(|p| fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_prefs(app: &AppHandle, f: impl FnOnce(&mut Prefs)) {
    let mut prefs = load_prefs(app);
    f(&mut prefs);
    if let Some(path) = prefs_path(app) {
        if let Some(dir) = path.parent() {
            let _ = fs::create_dir_all(dir);
        }
        if let Err(e) = fs::write(
            &path,
            serde_json::to_string_pretty(&prefs).unwrap_or_default(),
        ) {
            eprintln!("could not save {}: {e}", path.display());
        }
    }
}

// ------------------------------------------------------------------ geometry

/// One monitor in physical pixels (the virtual desktop may have negative coordinates).
#[derive(Clone, Copy, Debug)]
struct Screen {
    full: Rect,
    /// Screen minus the taskbar.
    work: Rect,
    scale: f64,
}

impl From<&tauri::Monitor> for Screen {
    fn from(m: &tauri::Monitor) -> Self {
        let wa = m.work_area();
        Screen {
            full: Rect {
                x: m.position().x,
                y: m.position().y,
                w: m.size().width as i32,
                h: m.size().height as i32,
            },
            work: Rect {
                x: wa.position.x,
                y: wa.position.y,
                w: wa.size.width as i32,
                h: wa.size.height as i32,
            },
            scale: m.scale_factor(),
        }
    }
}

fn screens(app: &AppHandle) -> Vec<Screen> {
    let mut all: Vec<Screen> = app
        .available_monitors()
        .unwrap_or_default()
        .iter()
        .map(Screen::from)
        .collect();
    if all.is_empty() {
        all.extend(
            app.primary_monitor()
                .ok()
                .flatten()
                .as_ref()
                .map(Screen::from),
        );
    }
    all
}

/// The monitor containing a physical point, else the nearest one.
fn screen_at(screens: &[Screen], px: i32, py: i32) -> Option<Screen> {
    screens
        .iter()
        .find(|s| s.full.contains(px, py))
        .or_else(|| screens.iter().min_by_key(|s| s.full.distance2(px, py)))
        .copied()
}

/// Work area (screen minus taskbar) and DPI scale of the monitor at a physical point; the nearest
/// monitor if the point is off-screen.
fn work_area_at(app: &AppHandle, px: i32, py: i32) -> Option<(Rect, f64)> {
    screen_at(&screens(app), px, py).map(|s| (s.work, s.scale))
}

fn px(v: f64, scale: f64) -> i32 {
    (v * scale).round() as i32
}

/// Start coordinate for a span of `len` inside `[lo, lo + area)`, `margin` from both ends when it
/// fits, else centered (never panics, unlike `clamp` with crossed bounds on a small work area).
fn fit(v: i32, len: i32, lo: i32, area: i32, margin: i32) -> i32 {
    if len + 2 * margin <= area {
        v.clamp(lo + margin, lo + area - margin - len)
    } else {
        lo + (area - len) / 2
    }
}

/// Offset of the circle inside the bubble window and its diameter (physical pixels). Computed from
/// the real window size: Windows may enforce a minimum window width larger than requested.
fn circle(scale: f64, win_w: i32, win_h: i32) -> (i32, i32, i32) {
    let size = px(BUBBLE_CIRCLE, scale);
    ((win_w - size) / 2, (win_h - size) / 2, size)
}

/// Bubble window top-left that puts the circle `EDGE_MARGIN` from the nearest work-area edge.
fn snapped(wa: Rect, scale: f64, win_x: i32, win_y: i32, win_w: i32, win_h: i32) -> (i32, i32) {
    let (pad_x, pad_y, size) = circle(scale, win_w, win_h);
    let m = px(EDGE_MARGIN, scale);
    let (mut bx, mut by) = (win_x + pad_x, win_y + pad_y);
    let (cx, cy) = (bx + size / 2, by + size / 2);
    let distances = [cx - wa.x, wa.right() - cx, cy - wa.y, wa.bottom() - cy];
    let nearest = (0..4).min_by_key(|&i| distances[i]).unwrap_or(1);
    match nearest {
        0 => bx = wa.x + m,
        1 => bx = wa.right() - m - size,
        2 => by = wa.y + m,
        _ => by = wa.bottom() - m - size,
    }
    bx = bx.clamp(wa.x + m, (wa.right() - m - size).max(wa.x + m));
    by = by.clamp(wa.y + m, (wa.bottom() - m - size).max(wa.y + m));
    (bx - pad_x, by - pad_y)
}

/// Bubble window size (physical) on a monitor with this DPI scale.
fn bubble_win_size(scale: f64) -> i32 {
    px(BUBBLE_WIN, scale)
}

/// Saved position if it is still inside a work area, else bottom-right of the primary work area just
/// above the taskbar; snapped either way. Sizes are computed for the target monitor's DPI, because
/// Windows rescales the bubble when it lands on a monitor with another scale.
fn initial_bubble_pos(
    screens: &[Screen],
    primary: Option<Screen>,
    saved: Option<(i32, i32)>,
) -> Option<(i32, i32)> {
    if let Some((x, y)) = saved {
        // The saved spot was recorded with the window size of the monitor it was on.
        let target = screens.iter().find(|s| {
            let half = bubble_win_size(s.scale) / 2;
            s.work.contains(x + half, y + half)
        });
        if let Some(s) = target {
            let win = bubble_win_size(s.scale);
            return Some(snapped(s.work, s.scale, x, y, win, win));
        }
    }
    let s = primary.or_else(|| screens.first().copied())?;
    let win = bubble_win_size(s.scale);
    let (pad_x, pad_y, size) = circle(s.scale, win, win);
    let bx = s.work.right() - px(EDGE_MARGIN, s.scale) - size;
    let by = s.work.bottom() - px(DEFAULT_BOTTOM_MARGIN, s.scale) - size;
    Some((bx - pad_x, by - pad_y))
}

fn get_win(app: &AppHandle, label: &str) -> Option<WebviewWindow> {
    app.get_webview_window(label)
}

/// Put the panel beside the bubble, on the side with room, opening up or down so it stays on screen.
fn place_panel(app: &AppHandle) {
    let (Some(bubble), Some(panel)) = (get_win(app, BUBBLE), get_win(app, PANEL)) else {
        return;
    };
    let Ok(pos) = bubble.outer_position() else {
        return;
    };
    let Ok(size) = bubble.outer_size() else {
        return;
    };
    let (cx, cy) = (
        pos.x + size.width as i32 / 2,
        pos.y + size.height as i32 / 2,
    );
    let Some((wa, scale)) = work_area_at(app, cx, cy) else {
        return;
    };
    let bubble_win = Rect {
        x: pos.x,
        y: pos.y,
        w: size.width as i32,
        h: size.height as i32,
    };
    let r = panel_rect(wa, scale, bubble_win);
    let _ = panel.set_position(PhysicalPosition::new(r.x, r.y));
    let _ = panel.set_size(PhysicalSize::new(r.w as u32, r.h as u32));
    // Moving onto a monitor with another DPI scale makes Windows resize (and may shift) the window
    // while it is being moved; put it back where it belongs at the size just set.
    let _ = panel.set_position(PhysicalPosition::new(r.x, r.y));
}

/// Panel rectangle (physical) beside the bubble window `bubble_win`, inside the work area `wa` of the
/// bubble's monitor whose DPI scale is `scale`.
fn panel_rect(wa: Rect, scale: f64, bubble_win: Rect) -> Rect {
    let (cx, cy) = (
        bubble_win.x + bubble_win.w / 2,
        bubble_win.y + bubble_win.h / 2,
    );
    let (pad_x, pad_y, bsize) = circle(scale, bubble_win.w, bubble_win.h);
    let (bx, by) = (bubble_win.x + pad_x, bubble_win.y + pad_y);
    let (pw, ph) = (px(PANEL_W, scale).min(wa.w), px(PANEL_H, scale).min(wa.h));
    let gap = px(PANEL_GAP, scale);
    let m = px(EDGE_MARGIN, scale);

    let on_right_half = cx > wa.x + wa.w / 2;
    let mut x = if on_right_half {
        bx - gap - pw
    } else {
        bx + bsize + gap
    };
    let on_lower_half = cy > wa.y + wa.h / 2;
    let mut y = if on_lower_half { by + bsize - ph } else { by };
    // Bubble snapped to the top or bottom edge: open above/below it instead of beside it.
    let near_top = by - wa.y <= m * 2;
    let near_bottom = wa.bottom() - (by + bsize) <= m * 2;
    if near_bottom && (bx - wa.x > m * 2 && wa.right() - (bx + bsize) > m * 2) {
        y = by - gap - ph;
        x = bx + bsize / 2 - pw / 2;
    } else if near_top && (bx - wa.x > m * 2 && wa.right() - (bx + bsize) > m * 2) {
        y = by + bsize + gap;
        x = bx + bsize / 2 - pw / 2;
    }
    x = fit(x, pw, wa.x, wa.w, m);
    y = fit(y, ph, wa.y, wa.h, m);
    Rect { x, y, w: pw, h: ph }
}

// ------------------------------------------------------------------ bubble and panel state

fn shared(app: &AppHandle) -> tauri::State<'_, Shared> {
    app.state::<Shared>()
}

/// Which half of its monitor the bubble sits on ("left" or "right"). The page points the bubble's
/// speech-tail corner at that screen edge.
fn bubble_side(app: &AppHandle) -> &'static str {
    let Some(b) = get_win(app, BUBBLE) else {
        return "right";
    };
    let (Ok(pos), Ok(size)) = (b.outer_position(), b.outer_size()) else {
        return "right";
    };
    let (cx, cy) = (
        pos.x + size.width as i32 / 2,
        pos.y + size.height as i32 / 2,
    );
    match work_area_at(app, cx, cy) {
        Some((wa, _)) if cx < wa.x + wa.w / 2 => "left",
        _ => "right",
    }
}

/// The bubble's look: only a known signed-out session gets the signed-out style, so a signed-in
/// user does not see it flash while the panel page is still loading.
fn looks_signed_in(session: Session) -> bool {
    session != Session::SignedOut
}

/// What the bubble's mascot shows now: the nudge on screen, else what the chat page reported
/// (`nudge::bubble_mascot`). Always one of `nudge::MASCOT_STATES`.
fn mascot_of(inner: &Inner) -> String {
    let hint = inner
        .nudges
        .current()
        .filter(|_| inner.balloon_shown)
        .map(|n| n.mascot.as_str());
    nudge::bubble_mascot(looks_signed_in(inner.session), inner.panel_mascot, hint).to_owned()
}

fn push_bubble_state(app: &AppHandle) {
    let (unread, session, mascot) = {
        let s = shared(app);
        let inner = s.inner.lock().unwrap();
        (inner.unread, inner.session, mascot_of(&inner))
    };
    let signed_in = looks_signed_in(session);
    let open = get_win(app, PANEL)
        .and_then(|p| p.is_visible().ok())
        .unwrap_or(false);
    let side = bubble_side(app);
    if let Some(b) = get_win(app, BUBBLE) {
        let _ = b.eval(format!(
            "window.mentorSetState && window.mentorSetState({{unread: {unread}, open: {open}, side: \"{side}\", signedIn: {signed_in}, mascot: \"{mascot}\"}})"
        ));
    }
    if let Some(tray) = app.tray_by_id("main") {
        let tip = if !signed_in {
            "Mentor (chưa đăng nhập)".to_owned()
        } else if unread > 0 {
            format!("Mentor ({unread} tin mới)")
        } else {
            "Mentor".to_owned()
        };
        let _ = tray.set_tooltip(Some(tip));
        // Linux: AppIndicator has no tooltip (the call above does nothing there); it shows a label
        // next to the icon instead, so the unread count goes there.
        #[cfg(target_os = "linux")]
        let _ = tray.set_title(Some(if signed_in && unread > 0 {
            unread.to_string()
        } else {
            String::new()
        }));
    }
}

/// Tray check marks follow the state (Windows flips a check item on click by itself).
fn sync_tray_checks(app: &AppHandle) {
    let (hidden, mode) = {
        let s = shared(app);
        let inner = s.inner.lock().unwrap();
        (inner.bubble_hidden_by_user, inner.bubble_mode)
    };
    let s = shared(app);
    if let Some(item) = s.tray_bubble_item.lock().unwrap().as_ref() {
        let _ = item.set_checked(!hidden);
    }
    if let Some((always, signed_in)) = s.tray_mode_items.lock().unwrap().as_ref() {
        let _ = always.set_checked(mode == BubbleMode::Always);
        let _ = signed_in.set_checked(mode == BubbleMode::SignedIn);
    };
    let nudge_mode = s.inner.lock().unwrap().nudge_mode;
    if let Some(items) = s.tray_nudge_items.lock().unwrap().as_ref() {
        for (item, m) in items
            .iter()
            .zip([NudgeMode::Balloon, NudgeMode::Toast, NudgeMode::Off])
        {
            let _ = item.set_checked(m == nudge_mode);
        }
    };
}

/// Bubble is visible unless the user hid it; in "signed_in" mode only while signed in.
fn sync_bubble_visibility(app: &AppHandle) {
    let (session, hidden, mode) = {
        let s = shared(app);
        let inner = s.inner.lock().unwrap();
        (inner.session, inner.bubble_hidden_by_user, inner.bubble_mode)
    };
    sync_tray_checks(app);
    let Some(b) = get_win(app, BUBBLE) else {
        return;
    };
    if bubble_should_show(session, mode, hidden) {
        if !b.is_visible().unwrap_or(false) {
            let _ = b.show();
            push_bubble_state(app);
        }
    } else {
        // No bubble to point at: drop the balloon (later nudges become toasts, see `nudge::route`).
        clear_nudges(app, true);
        let _ = b.hide();
    }
}

fn show_panel(app: &AppHandle) {
    let Some(panel) = get_win(app, PANEL) else {
        return;
    };
    // The chat has every nudge: the balloon and the ones waiting go away. The panel takes the
    // focus next, so it is not handed back to the previous app first.
    clear_nudges(app, false);
    place_panel(app);
    let _ = panel.show();
    let _ = panel.unminimize();
    let _ = panel.set_focus();
    shared(app).inner.lock().unwrap().unread = 0;
    push_bubble_state(app);
}

fn hide_panel(app: &AppHandle) {
    if let Some(panel) = get_win(app, PANEL) {
        let _ = panel.hide();
    }
    push_bubble_state(app);
}

fn toggle_panel(app: &AppHandle) {
    let visible = get_win(app, PANEL)
        .and_then(|p| p.is_visible().ok())
        .unwrap_or(false);
    if visible {
        hide_panel(app);
    } else {
        show_panel(app);
    }
}

/// Linux: GTK moves windows asynchronously, so code that moves the bubble and then places the
/// panel or the balloon beside it (startup, the end of a drag) reads the old spot. When the bubble
/// reports its move, the panel, the empty balloon and the bubble's side follow it. Not while
/// dragging (the balloon is hidden then and the panel follows at the end), and not a balloon on
/// screen (it was placed by `balloon_ready`, which runs after the move).
#[cfg(target_os = "linux")]
fn linux_follow_bubble(app: &AppHandle) {
    let (dragging, balloon_shown) = {
        let s = shared(app);
        let inner = s.inner.lock().unwrap();
        (inner.drag_offset.is_some(), inner.balloon_shown)
    };
    if dragging {
        return;
    }
    if panel_visible(app) {
        place_panel(app);
    }
    push_bubble_state(app);
    if !balloon_shown {
        move_balloon(app, nudge::BALLOON_MIN_H);
    }
}

fn set_bubble_hidden_by_user(app: &AppHandle, hidden: bool) {
    shared(app).inner.lock().unwrap().bubble_hidden_by_user = hidden;
    save_prefs(app, |p| p.bubble_hidden = hidden);
    sync_bubble_visibility(app);
}

fn set_bubble_mode(app: &AppHandle, mode: BubbleMode) {
    shared(app).inner.lock().unwrap().bubble_mode = mode;
    save_prefs(app, |p| p.bubble_mode = mode);
    sync_bubble_visibility(app);
}

fn set_nudge_mode(app: &AppHandle, mode: NudgeMode) {
    shared(app).inner.lock().unwrap().nudge_mode = mode;
    save_prefs(app, |p| p.nudge_mode = mode);
    if mode != NudgeMode::Balloon {
        clear_nudges(app, true);
    }
    sync_tray_checks(app);
}

fn open_web_app(app: &AppHandle) {
    let url = format!("{}/chat", shared(app).web_origin);
    if let Err(e) = app.opener().open_url(url, None::<&str>) {
        eprintln!("could not open the browser: {e}");
    }
}

// ------------------------------------------------------------------ nudges: balloon and toast

fn panel_visible(app: &AppHandle) -> bool {
    get_win(app, PANEL)
        .and_then(|p| p.is_visible().ok())
        .unwrap_or(false)
}

/// Where a nudge goes right now. `force_signed_in`: the debug test nudge, before signing in.
fn nudge_route(app: &AppHandle, force_signed_in: bool) -> Route {
    let (mode, session) = {
        let s = shared(app);
        let inner = s.inner.lock().unwrap();
        (inner.nudge_mode, inner.session)
    };
    nudge::route(&RouteInput {
        mode,
        signed_in: force_signed_in || looks_signed_in(session),
        panel_visible: panel_visible(app),
        bubble_visible: get_win(app, BUBBLE)
            .and_then(|b| b.is_visible().ok())
            .unwrap_or(false),
        presence: win_shell::presence(),
        screen_reader: win_shell::screen_reader(),
    })
}

/// Takes a validated nudge from the page (or the debug tray item). Returns what happened, for
/// the page: `balloon`, `queued`, `duplicate`, `toast`, `panel` (the open chat shows it), `off`.
fn submit_nudge(app: &AppHandle, n: Nudge, force_signed_in: bool) -> &'static str {
    match nudge_route(app, force_signed_in) {
        Route::Off => "off",
        Route::Panel => {
            shared(app).inner.lock().unwrap().nudges.remember(n.key());
            "panel"
        }
        Route::Toast => {
            {
                let s = shared(app);
                let mut inner = s.inner.lock().unwrap();
                if inner.nudges.was_shown(&n.key()) {
                    return "duplicate";
                }
                inner.nudges.remember(n.key());
            }
            show_toast(app, &n);
            "toast"
        }
        Route::Balloon => {
            let pushed = shared(app).inner.lock().unwrap().nudges.push(n);
            match pushed {
                Pushed::ShowNow | Pushed::Updated => {
                    render_balloon(app);
                    "balloon"
                }
                Pushed::Queued => "queued",
                Pushed::Duplicate => "duplicate",
            }
        }
    }
}

/// Hands the current nudge to the balloon page, which lays it out at the balloon's width and
/// answers with `balloon_ready` (its height); the shell then places the window and reveals it.
/// If the balloon cannot be seen any more (full-screen app, locked, bubble hidden), the nudges
/// waiting for it go out as toasts instead.
fn render_balloon(app: &AppHandle) {
    loop {
        let Some(n) = shared(app).inner.lock().unwrap().nudges.current().cloned() else {
            return;
        };
        match nudge_route(app, true) {
            Route::Balloon => {
                let payload = serde_json::json!({
                    "key": n.key(),
                    "kind": n.kind,
                    "title": n.title,
                    "body": n.body,
                    "actions": n.actions,
                });
                if let Some(w) = get_win(app, BALLOON) {
                    // JSON is a valid JS expression; every string in it is escaped.
                    let _ = w.eval(format!(
                        "window.mentorBalloon && window.mentorBalloon.render({payload})"
                    ));
                }
                return;
            }
            Route::Toast => {
                show_toast(app, &n);
                shared(app).inner.lock().unwrap().nudges.finish(&n.key());
            }
            Route::Panel | Route::Off => {
                clear_nudges(app, true);
                return;
            }
        }
    }
}

/// Physical rectangle, tail side and tail position of a balloon `height` logical px tall.
fn balloon_place_now(app: &AppHandle, height: f64) -> Option<nudge::BalloonPlace> {
    let b = get_win(app, BUBBLE)?;
    let (pos, size) = (b.outer_position().ok()?, b.outer_size().ok()?);
    let (w, h) = (size.width as i32, size.height as i32);
    let (wa, scale) = work_area_at(app, pos.x + w / 2, pos.y + h / 2)?;
    let bubble_win = Rect {
        x: pos.x,
        y: pos.y,
        w,
        h,
    };
    Some(nudge::balloon_place(wa, scale, bubble_win, height))
}

/// Moves the balloon window into place (also while empty, so it never sits on the bubble).
fn move_balloon(app: &AppHandle, height: f64) -> Option<nudge::BalloonPlace> {
    let place = balloon_place_now(app, height)?;
    let w = get_win(app, BALLOON)?;
    let r = place.rect;
    // Same dance as the panel: a move onto a monitor with another DPI makes Windows resize it.
    let _ = w.set_position(PhysicalPosition::new(r.x, r.y));
    let _ = w.set_size(PhysicalSize::new(r.w as u32, r.h as u32));
    let _ = w.set_position(PhysicalPosition::new(r.x, r.y));
    Some(place)
}

/// Hides the balloon's content and makes the window click-through again. If the user had clicked
/// into it and `give_focus_back`, focus goes back to the app they were in (not when our panel is
/// about to take it).
fn hide_balloon(app: &AppHandle, give_focus_back: bool) {
    let prev = {
        let s = shared(app);
        let mut inner = s.inner.lock().unwrap();
        inner.balloon_shown = false;
        std::mem::take(&mut inner.balloon_prev_foreground)
    };
    let Some(w) = get_win(app, BALLOON) else {
        return;
    };
    let _ = w.eval("window.mentorBalloon && window.mentorBalloon.hide()");
    let _ = w.set_ignore_cursor_events(true);
    if give_focus_back && w.is_focused().unwrap_or(false) {
        win_shell::restore_foreground(prev);
    }
}

/// Drops the balloon and every waiting nudge (the chat opened, the bubble went away...).
/// `give_focus_back`: see `hide_balloon`.
fn clear_nudges(app: &AppHandle, give_focus_back: bool) {
    let had_any = {
        let s = shared(app);
        let mut inner = s.inner.lock().unwrap();
        let had = inner.nudges.current().is_some() || inner.balloon_shown;
        inner.nudges.clear();
        had
    };
    if had_any {
        hide_balloon(app, give_focus_back);
        push_bubble_state(app);
    }
}

/// The nudge `key` is done (action, close, timeout): hide its balloon, show the next after a pause.
fn finish_nudge(app: &AppHandle, key: &str) {
    let has_next = {
        let s = shared(app);
        let mut inner = s.inner.lock().unwrap();
        if inner.nudges.current().map(Nudge::key).as_deref() != Some(key) {
            return; // stale (an older balloon's timer)
        }
        inner.nudges.finish(key).is_some()
    };
    hide_balloon(app, true);
    push_bubble_state(app);
    if has_next {
        let app = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(NEXT_NUDGE_AFTER);
            render_balloon(&app);
        });
    }
}

/// Tells the panel page what the user chose; it calls `POST /api/notifications/{id}/action`.
fn emit_nudge_action(app: &AppHandle, id: Value, action: &str) {
    let payload = serde_json::json!({ "id": id, "action": action });
    if let Err(e) = app.emit_to(PANEL, NUDGE_EVENT, payload) {
        eprintln!("{NUDGE_EVENT}: {e}");
    }
}

/// A silent Windows toast (no sound is set, so the plugin asks for `<audio silent="true"/>`).
/// Toasts can show on the lock screen, so they carry a generic text per kind, never the nudge's
/// own title or body, and no `answer:` buttons (`nudge::toast_text`, `nudge::toast_actions`).
/// A click on the toast itself means `open`.
fn show_toast(app: &AppHandle, n: &Nudge) {
    use tauri_plugin_notification::{Action, ActionType};
    let seq = {
        let s = shared(app);
        let mut inner = s.inner.lock().unwrap();
        inner.toast_seq = inner.toast_seq.wrapping_add(1).max(1);
        inner.toast_seq
    };
    let notifications = app.notification();
    let (title, body) = nudge::toast_text(&n.kind);
    let buttons = nudge::toast_actions(&n.actions);
    let mut toast = notifications
        .builder()
        .id(seq)
        .title(title)
        .body(body)
        .extra("nudgeId", &n.id);
    if !buttons.is_empty() {
        // One action type per distinct set of buttons (the plugin keeps them in a map).
        let type_id = format!(
            "mentor:{}",
            buttons
                .iter()
                .map(|a| format!("{}={}", a.id, a.label))
                .collect::<Vec<_>>()
                .join("|")
        );
        let actions = buttons
            .iter()
            .map(|a| Action::builder(&a.id, &a.label).build())
            .collect();
        let registered = notifications
            .register_action_types(vec![ActionType::builder(&type_id).actions(actions).build()]);
        if registered.is_ok() {
            toast = toast.action_type_id(type_id);
        }
    }
    if let Err(e) = toast.show() {
        eprintln!("toast: {e}");
    }
}

/// The nudge id a toast carries (`extra.nudgeId`), and the action clicked (`tap` = the toast).
fn toast_action(performed: &tauri_plugin_notification::ActionPerformed) -> Option<(Value, String)> {
    let id = performed.notification()?.extra().get("nudgeId")?.clone();
    let action = match performed.action_id() {
        "tap" => "open",
        a => a,
    };
    nudge::valid_action_id(action).then(|| (id, action.to_owned()))
}

#[cfg(debug_assertions)]
fn push_test_nudge(app: &AppHandle) {
    use std::sync::atomic::{AtomicU32, Ordering};
    static SEQ: AtomicU32 = AtomicU32::new(0);
    let i = SEQ.fetch_add(1, Ordering::Relaxed);
    let act = |id: &str, label: &str| NudgeAction {
        id: id.into(),
        label: label.into(),
    };
    let (kind, title, body, actions) = match i % 3 {
        0 => (
            "checkin",
            "Chào buổi sáng, Lan!",
            "Hôm nay mình làm 3 việc nào trước? Mình đã xếp sẵn bài Toán còn dở từ hôm qua.",
            vec![
                act("open", "Lên kế hoạch"),
                act("snooze_1h", "Để sau 1 giờ"),
                act("done", "Xong rồi"),
            ],
        ),
        1 => (
            "review",
            "Đến giờ ôn 5 thẻ từ vựng",
            "Chỉ mất khoảng 3 phút.",
            vec![act("start_focus", "Bắt đầu"), act("snooze_1h", "Để sau")],
        ),
        _ => (
            "deadline",
            "Bài nộp Hóa học còn 2 ngày",
            "Phần thí nghiệm 2 chưa có số liệu. Muốn mình chia nhỏ phần còn lại thành từng bước 20 phút không?",
            vec![act("open", "Chia nhỏ giúp mình")],
        ),
    };
    let n = Nudge::new(
        Value::String(format!("test-{i}")),
        Some(kind.into()),
        Some(title.into()),
        Some(body.into()),
        Some(actions),
        None,
    )
    .expect("valid test nudge");
    println!("test nudge test-{i}: {}", submit_nudge(app, n, true));
}

/// Windows' view of the user (away: locked; busy: full screen), the screen reader flag and the
/// foreground window.
#[cfg(windows)]
mod win_shell {
    use super::nudge::Presence;
    use windows_sys::Win32::UI::Shell::{
        SHQueryUserNotificationState, QUNS_BUSY, QUNS_NOT_PRESENT, QUNS_PRESENTATION_MODE,
        QUNS_RUNNING_D3D_FULL_SCREEN,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetForegroundWindow, GetWindowThreadProcessId, IsWindow, SetForegroundWindow,
        SystemParametersInfoW, SPI_GETSCREENREADER,
    };

    pub fn presence() -> Presence {
        let mut state = 0;
        // SAFETY: writes one value to a local.
        if unsafe { SHQueryUserNotificationState(&mut state) } != 0 {
            return Presence::Present;
        }
        match state {
            QUNS_NOT_PRESENT => Presence::Away,
            QUNS_BUSY | QUNS_RUNNING_D3D_FULL_SCREEN | QUNS_PRESENTATION_MODE => Presence::Busy,
            _ => Presence::Present,
        }
    }

    pub fn screen_reader() -> bool {
        let mut on: i32 = 0;
        // SAFETY: SPI_GETSCREENREADER writes a BOOL to the pointer.
        let ok = unsafe {
            SystemParametersInfoW(SPI_GETSCREENREADER, 0, (&mut on as *mut i32).cast(), 0)
        };
        ok != 0 && on != 0
    }

    /// The foreground window if it belongs to another app, else 0.
    pub fn foreground_other_app() -> isize {
        // SAFETY: plain queries on the current foreground window.
        unsafe {
            let fg = GetForegroundWindow();
            if fg.is_null() {
                return 0;
            }
            let mut pid = 0u32;
            GetWindowThreadProcessId(fg, &mut pid);
            if pid == std::process::id() {
                0
            } else {
                fg as isize
            }
        }
    }

    /// Gives the foreground back to `hwnd` (we are the foreground process, so Windows allows it).
    pub fn restore_foreground(hwnd: isize) {
        if hwnd == 0 {
            return;
        }
        let h = hwnd as windows_sys::Win32::Foundation::HWND;
        // SAFETY: IsWindow guards against a window that has gone away.
        unsafe {
            if IsWindow(h) != 0 {
                SetForegroundWindow(h);
            }
        }
    }
}

#[cfg(not(windows))]
mod win_shell {
    use super::nudge::Presence;
    pub fn presence() -> Presence {
        Presence::Present
    }
    pub fn screen_reader() -> bool {
        false
    }
    pub fn foreground_other_app() -> isize {
        0
    }
    pub fn restore_foreground(_hwnd: isize) {}
}

#[cfg(windows)]
fn left_button_down() -> bool {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON};
    // High bit: the (primary) button is down now.
    unsafe { (GetAsyncKeyState(VK_LBUTTON as i32) as u16 & 0x8000) != 0 }
}

#[cfg(not(windows))]
fn left_button_down() -> bool {
    false
}

/// The mouse is over our tray icon (or the overflow chevron while the icon sits in the overflow).
fn cursor_on_tray_icon(app: &AppHandle) -> bool {
    let (Some(tray), Ok(c)) = (app.tray_by_id("main"), app.cursor_position()) else {
        return false;
    };
    let Ok(Some(r)) = tray.rect() else {
        return false;
    };
    // Physical pixels on Windows (the scale is ignored for physical values).
    let (pos, size) = (
        r.position.to_physical::<f64>(1.0),
        r.size.to_physical::<f64>(1.0),
    );
    c.x >= pos.x && c.x < pos.x + size.width && c.y >= pos.y && c.y < pos.y + size.height
}

/// True if the foreground window belongs to this app: the bubble, the panel, or a dialog the panel
/// opened (file picker, screen-capture picker; WebView2 shows those from its own process, owned by
/// the panel). Clicking those must not collapse the panel.
#[cfg(windows)]
fn foreground_is_ours(panel: &WebviewWindow) -> bool {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetAncestor, GetForegroundWindow, GetWindow, GetWindowThreadProcessId, GA_ROOTOWNER,
        GW_OWNER,
    };
    let panel_hwnd = match panel.hwnd() {
        Ok(h) => h.0 as isize,
        Err(_) => return false,
    };
    unsafe {
        let fg = GetForegroundWindow();
        if fg.is_null() {
            return false;
        }
        let mut pid = 0u32;
        GetWindowThreadProcessId(fg, &mut pid);
        if pid == std::process::id() {
            return true;
        }
        if GetAncestor(fg, GA_ROOTOWNER) as isize == panel_hwnd {
            return true;
        }
        let mut owner = GetWindow(fg, GW_OWNER);
        for _ in 0..8 {
            if owner.is_null() {
                break;
            }
            if owner as isize == panel_hwnd {
                return true;
            }
            owner = GetWindow(owner, GW_OWNER);
        }
        false
    }
}

/// Linux: one of this process's GTK toplevels is the active (focused) window. That covers the
/// bubble and the balloon, and the file chooser the panel opens for "attach image": WebKitGTK shows
/// it in-process as a dialog of its own, so checking only our Tauri windows would collapse the panel
/// (and its dialog) the moment the picker opens. GTK may only be touched on the main thread; if
/// that does not answer within a second, keep the panel (a stray open panel is the lesser harm).
#[cfg(target_os = "linux")]
fn foreground_is_ours(panel: &WebviewWindow) -> bool {
    use gtk::prelude::*;
    let (tx, rx) = std::sync::mpsc::channel();
    let asked = panel.run_on_main_thread(move || {
        let active = gtk::Window::list_toplevels()
            .into_iter()
            .filter_map(|w| w.downcast::<gtk::Window>().ok())
            .any(|w| w.is_visible() && w.is_active());
        let _ = tx.send(active);
    });
    if asked.is_err() {
        return panel.is_focused().unwrap_or(false);
    }
    rx.recv_timeout(Duration::from_secs(1)).unwrap_or(true)
}

#[cfg(not(any(windows, target_os = "linux")))]
fn foreground_is_ours(panel: &WebviewWindow) -> bool {
    panel.is_focused().unwrap_or(false)
}

// ------------------------------------------------------------------ menus

/// Tray wording that names the platform. Linux: the tray icon (AppIndicator) never reports
/// clicks, every click opens this menu, so its first item is the way to the chat; the shortcut
/// hint is left out (a GTK menu shows the tab as a gap, and on a Wayland session Ctrl+Alt+M only
/// reaches us while one of our own windows has the focus, see `register_shortcut`).
#[cfg(not(target_os = "linux"))]
mod tray_text {
    pub const TOGGLE: &str = "Mở / thu gọn khung chat\tCtrl+Alt+M";
    pub const NUDGE_TOAST: &str = "Nhắc nhở: thông báo Windows";
    pub const AUTOSTART: &str = "Khởi động cùng Windows";
}

#[cfg(target_os = "linux")]
mod tray_text {
    pub const TOGGLE: &str = "Mở / thu gọn khung chat";
    pub const NUDGE_TOAST: &str = "Nhắc nhở: thông báo hệ thống";
    pub const AUTOSTART: &str = "Khởi động khi đăng nhập";
}

fn build_tray(app: &AppHandle, prefs: &Prefs) -> tauri::Result<()> {
    let toggle = MenuItem::with_id(app, "panel", tray_text::TOGGLE, true, None::<&str>)?;
    let bubble = CheckMenuItem::with_id(
        app,
        "bubble",
        "Hiện bong bóng",
        true,
        !prefs.bubble_hidden,
        None::<&str>,
    )?;
    // Radio-style pair (muda has no radio items; `sync_tray_checks` keeps exactly one checked).
    let mode_always = CheckMenuItem::with_id(
        app,
        "bubble-mode-always",
        "Bong bóng: luôn hiện",
        true,
        prefs.bubble_mode == BubbleMode::Always,
        None::<&str>,
    )?;
    let mode_signed_in = CheckMenuItem::with_id(
        app,
        "bubble-mode-signed-in",
        "Bong bóng: chỉ khi đã đăng nhập",
        true,
        prefs.bubble_mode == BubbleMode::SignedIn,
        None::<&str>,
    )?;
    // Radio-style triple, like the bubble modes.
    let nudge_items = [
        ("nudge-balloon", "Nhắc nhở: bong bóng", NudgeMode::Balloon),
        ("nudge-toast", tray_text::NUDGE_TOAST, NudgeMode::Toast),
        ("nudge-off", "Nhắc nhở: tắt", NudgeMode::Off),
    ]
    .map(|(id, label, mode)| {
        CheckMenuItem::with_id(app, id, label, true, prefs.nudge_mode == mode, None::<&str>)
    });
    let [nudge_balloon, nudge_toast, nudge_off] = nudge_items;
    let nudge_items = [nudge_balloon?, nudge_toast?, nudge_off?];
    let web = MenuItem::with_id(app, "web", "Mở ứng dụng web", true, None::<&str>)?;
    let autostart_on = app.autolaunch().is_enabled().unwrap_or(false);
    let autostart = CheckMenuItem::with_id(
        app,
        "autostart",
        tray_text::AUTOSTART,
        true,
        autostart_on,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(app, "quit", "Thoát Mentor", true, None::<&str>)?;
    let separator = || PredefinedMenuItem::separator(app);
    let (sep1, sep2, sep3, sep4) = (separator()?, separator()?, separator()?, separator()?);
    let mut items: Vec<&dyn tauri::menu::IsMenuItem<Wry>> = vec![
        &toggle,
        &web,
        &sep1,
        &bubble,
        &mode_always,
        &mode_signed_in,
        &sep2,
        &nudge_items[0],
        &nudge_items[1],
        &nudge_items[2],
    ];
    // Debug builds only: show a sample nudge (cycles through three), for testing the balloon.
    #[cfg(debug_assertions)]
    let test_nudge = MenuItem::with_id(app, "nudge-test", "Thử nhắc nhở", true, None::<&str>)?;
    #[cfg(debug_assertions)]
    items.push(&test_nudge);
    items.extend([
        &sep3 as &dyn tauri::menu::IsMenuItem<Wry>,
        &autostart,
        &sep4,
        &quit,
    ]);
    let menu = Menu::with_items(app, &items)?;
    let s = shared(app);
    *s.tray_bubble_item.lock().unwrap() = Some(bubble);
    *s.tray_mode_items.lock().unwrap() = Some((mode_always, mode_signed_in));
    *s.tray_autostart_item.lock().unwrap() = Some(autostart);
    *s.tray_nudge_items.lock().unwrap() = Some(nudge_items);

    let mut builder = TrayIconBuilder::with_id("main")
        .tooltip("Mentor")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            // Windows 11 reports the press and the release together on release, so the press
            // cannot be used to remember the state; see `cursor_on_tray_icon` for slow clicks.
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                toggle_panel(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder.build(app)?;
    Ok(())
}

fn on_menu_event(app: &AppHandle, event: MenuEvent) {
    match event.id().as_ref() {
        "panel" => toggle_panel(app),
        "bubble" => {
            let hidden = shared(app).inner.lock().unwrap().bubble_hidden_by_user;
            set_bubble_hidden_by_user(app, !hidden);
        }
        "bubble-hide" => set_bubble_hidden_by_user(app, true),
        "bubble-mode-always" => set_bubble_mode(app, BubbleMode::Always),
        "bubble-mode-signed-in" => set_bubble_mode(app, BubbleMode::SignedIn),
        "nudge-balloon" => set_nudge_mode(app, NudgeMode::Balloon),
        "nudge-toast" => set_nudge_mode(app, NudgeMode::Toast),
        "nudge-off" => set_nudge_mode(app, NudgeMode::Off),
        #[cfg(debug_assertions)]
        "nudge-test" => push_test_nudge(app),
        "web" => open_web_app(app),
        "autostart" => {
            let auto = app.autolaunch();
            let enable = !auto.is_enabled().unwrap_or(false);
            let result = if enable {
                auto.enable()
            } else {
                auto.disable()
            };
            if let Err(e) = result {
                eprintln!("autostart: {e}");
            }
            if enable {
                quote_autostart_entry(app);
            }
            let now = auto.is_enabled().unwrap_or(false);
            if let Some(item) = shared(app).tray_autostart_item.lock().unwrap().as_ref() {
                let _ = item.set_checked(now);
            }
        }
        "quit" => app.exit(0),
        _ => {}
    }
}

// ------------------------------------------------------------------ commands: bubble (local page)

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BubbleState {
    unread: u32,
    open: bool,
    side: &'static str,
    signed_in: bool,
    mascot: String,
}

#[tauri::command]
fn bubble_state(app: AppHandle) -> BubbleState {
    let (unread, session, mascot) = {
        let s = shared(&app);
        let inner = s.inner.lock().unwrap();
        (inner.unread, inner.session, mascot_of(&inner))
    };
    BubbleState {
        unread,
        open: get_win(&app, PANEL)
            .and_then(|p| p.is_visible().ok())
            .unwrap_or(false),
        side: bubble_side(&app),
        signed_in: looks_signed_in(session),
        mascot,
    }
}

#[tauri::command]
fn bubble_click(app: AppHandle) {
    toggle_panel(&app);
}

#[tauri::command]
fn bubble_menu(app: AppHandle, window: Window) -> Result<(), String> {
    let build = || -> tauri::Result<Menu<Wry>> {
        Menu::with_items(
            &app,
            &[
                &MenuItem::with_id(&app, "panel", "Mở / thu gọn khung chat", true, None::<&str>)?,
                &MenuItem::with_id(&app, "web", "Mở ứng dụng web", true, None::<&str>)?,
                &MenuItem::with_id(
                    &app,
                    "bubble-hide",
                    "Ẩn bong bóng (mở lại từ khay hệ thống)",
                    true,
                    None::<&str>,
                )?,
                &PredefinedMenuItem::separator(&app)?,
                &MenuItem::with_id(&app, "quit", "Thoát Mentor", true, None::<&str>)?,
            ],
        )
    };
    let menu = build().map_err(|e| e.to_string())?;
    window.popup_menu(&menu).map_err(|e| e.to_string())
}

#[tauri::command]
fn bubble_drag_start(app: AppHandle) {
    let (Some(b), Ok(cursor)) = (get_win(&app, BUBBLE), app.cursor_position()) else {
        return;
    };
    let Ok(pos) = b.outer_position() else { return };
    let balloon_shown = {
        let s = shared(&app);
        let mut inner = s.inner.lock().unwrap();
        inner.drag_offset = Some((cursor.x - pos.x as f64, cursor.y - pos.y as f64));
        inner.balloon_shown
    };
    // The balloon steps aside while the bubble moves and comes back beside its new spot.
    if balloon_shown {
        hide_balloon(&app, true);
        push_bubble_state(&app);
    }
}

#[tauri::command]
fn bubble_drag_move(app: AppHandle) {
    drag_bubble_to_cursor(&app);
}

/// Moves the bubble under the cursor (keeping the grab offset); returns where it was sent.
fn drag_bubble_to_cursor(app: &AppHandle) -> Option<PhysicalPosition<i32>> {
    let (ox, oy) = shared(app).inner.lock().unwrap().drag_offset?;
    let (Some(b), Ok(cursor)) = (get_win(app, BUBBLE), app.cursor_position()) else {
        return None;
    };
    let to = PhysicalPosition::new((cursor.x - ox).round() as i32, (cursor.y - oy).round() as i32);
    let _ = b.set_position(to);
    Some(to)
}

#[tauri::command]
fn bubble_drag_end(app: AppHandle) {
    let moved = drag_bubble_to_cursor(&app);
    shared(&app).inner.lock().unwrap().drag_offset = None;
    let Some(b) = get_win(&app, BUBBLE) else {
        return;
    };
    let (Ok(read_back), Ok(size)) = (b.outer_position(), b.outer_size()) else {
        return;
    };
    // Linux: GTK moves the window asynchronously, so what reads back is still an earlier spot of
    // the drag; snap from where the bubble was just sent. The panel and the balloon below may also
    // read the old spot; `linux_follow_bubble` puts them right once the move is reported.
    let pos = match moved {
        Some(to) if cfg!(target_os = "linux") => to,
        _ => read_back,
    };
    let (cx, cy) = (
        pos.x + size.width as i32 / 2,
        pos.y + size.height as i32 / 2,
    );
    if let Some((wa, scale)) = work_area_at(&app, cx, cy) {
        let (x, y) = snapped(
            wa,
            scale,
            pos.x,
            pos.y,
            size.width as i32,
            size.height as i32,
        );
        let _ = b.set_position(PhysicalPosition::new(x, y));
        save_prefs(&app, |p| {
            p.bubble_x = Some(x);
            p.bubble_y = Some(y);
        });
    }
    if get_win(&app, PANEL)
        .and_then(|p| p.is_visible().ok())
        .unwrap_or(false)
    {
        place_panel(&app);
    }
    push_bubble_state(&app); // the snapped side may have changed (tail corner)
    // Keep the (empty, click-through) balloon window off the bubble; show the current nudge again.
    move_balloon(&app, nudge::BALLOON_MIN_H);
    render_balloon(&app);
}

// ------------------------------------------------------------------ commands: panel (remote web page)

#[tauri::command]
fn desktop_session(app: AppHandle, state: String) {
    let next = match state.as_str() {
        "active" | "onboarding" => Session::SignedIn,
        "anon" | "error" => Session::SignedOut,
        _ => return, // "loading"
    };
    let prev = {
        let s = shared(&app);
        let mut inner = s.inner.lock().unwrap();
        if next == Session::SignedOut {
            inner.unread = 0; // nothing to read while signed out; no stale badge on the muted bubble
            inner.panel_mascot = "idle";
        }
        std::mem::replace(&mut inner.session, next)
    };
    if next == Session::SignedOut {
        clear_nudges(&app, true);
    }
    sync_bubble_visibility(&app);
    if prev != next {
        push_bubble_state(&app); // signed-in / signed-out look, tooltip
    }
    let panel_visible = get_win(&app, PANEL)
        .and_then(|p| p.is_visible().ok())
        .unwrap_or(false);
    if next == Session::SignedOut && prev != Session::SignedOut {
        // First launch or the session ended: the panel shows the login page.
        show_panel(&app);
    } else if next == Session::SignedIn && prev != Session::SignedIn && panel_visible {
        place_panel(&app); // just signed in: the bubble appeared, keep the panel next to it
    }
}

#[tauri::command]
fn desktop_unread(app: AppHandle, kind: String) {
    if !matches!(
        kind.as_str(),
        "notification" | "approval_request" | "turn_done"
    ) {
        return;
    }
    let panel_visible = get_win(&app, PANEL)
        .and_then(|p| p.is_visible().ok())
        .unwrap_or(false);
    if panel_visible {
        return;
    }
    {
        let s = shared(&app);
        let mut inner = s.inner.lock().unwrap();
        inner.unread = inner.unread.saturating_add(1);
    }
    push_bubble_state(&app);
}

#[tauri::command]
fn desktop_hide_panel(app: AppHandle) {
    hide_panel(&app);
}

/// A proactive message from the mentor (CONTRACTS.md section 9, "Desktop bridge"). Shows the
/// speech balloon, or a silent Windows toast when the balloon cannot be seen or the user chose
/// toasts. Clicks come back to the page as `mentor://nudge-action {id, action}`.
/// Returns `balloon | queued | duplicate | toast | panel | off` (see `submit_nudge`).
#[tauri::command]
fn desktop_nudge(
    app: AppHandle,
    id: Value,
    kind: Option<String>,
    title: Option<String>,
    body: Option<String>,
    actions: Option<Vec<NudgeAction>>,
    mascot: Option<String>,
) -> Result<&'static str, String> {
    let n = Nudge::new(id, kind, title, body, actions, mascot)?;
    Ok(submit_nudge(&app, n, false))
}

/// What the chat page is doing, for the bubble's mascot: `thinking` while a turn runs, `sleepy`
/// in quiet hours or with the sandbox asleep, `calm` for serious topics, `idle` otherwise. The
/// one-shot `wave` and `celebrate` play once (never while `calm`).
#[tauri::command]
fn desktop_mascot(app: AppHandle, state: String) -> Result<(), String> {
    let Some(&state) = nudge::MASCOT_STATES.iter().find(|s| **s == state) else {
        return Err(format!("unknown mascot state {state:?}"));
    };
    if matches!(state, "wave" | "celebrate") {
        let calm = shared(&app).inner.lock().unwrap().panel_mascot == "calm";
        if !calm {
            if let Some(b) = get_win(&app, BUBBLE) {
                let _ = b.eval(format!(
                    "window.mentorMascotOnce && window.mentorMascotOnce(\"{state}\")"
                ));
            }
        }
        return Ok(());
    }
    shared(&app).inner.lock().unwrap().panel_mascot = state;
    push_bubble_state(&app);
    Ok(())
}

// ------------------------------------------------------------------ commands: balloon (local page)

fn is_current_nudge(app: &AppHandle, key: &str) -> bool {
    shared(app)
        .inner
        .lock()
        .unwrap()
        .nudges
        .current()
        .is_some_and(|n| n.key() == key)
}

/// The page laid out nudge `key` and needs `height` logical px: place the window and reveal it.
#[tauri::command]
fn balloon_ready(app: AppHandle, key: String, height: f64) {
    if !height.is_finite() || !is_current_nudge(&app, &key) {
        return;
    }
    if shared(&app).inner.lock().unwrap().drag_offset.is_some() {
        return; // shown again at drag end
    }
    let Some(place) = move_balloon(&app, height) else {
        return;
    };
    let Some(w) = get_win(&app, BALLOON) else {
        return;
    };
    {
        let s = shared(&app);
        let mut inner = s.inner.lock().unwrap();
        if !inner.balloon_shown {
            inner.balloon_prev_foreground = win_shell::foreground_other_app();
        }
        inner.balloon_shown = true;
    }
    let _ = w.set_ignore_cursor_events(false);
    let reveal = serde_json::json!({
        "key": key,
        "side": place.side,
        "anchorY": (place.anchor_y * 10.0).round() / 10.0,
    });
    let _ = w.eval(format!(
        "window.mentorBalloon && window.mentorBalloon.reveal({reveal})"
    ));
    push_bubble_state(&app); // mascot: the nudge's state
}

/// A click in the balloon: `open` (the body or an `open` button) or one of the nudge's actions.
#[tauri::command]
fn balloon_action(app: AppHandle, key: String, action: String) {
    let id = {
        let s = shared(&app);
        let inner = s.inner.lock().unwrap();
        let Some(n) = inner.nudges.current().filter(|n| n.key() == key) else {
            return;
        };
        if action != "open" && !n.actions.iter().any(|a| a.id == action) {
            return;
        }
        n.id.clone()
    };
    emit_nudge_action(&app, id, &action);
    if action == "open" {
        show_panel(&app); // clears the balloon and the queue: the chat shows them
    } else {
        finish_nudge(&app, &key);
    }
}

/// The × or the 12 s timeout. Nothing is reported to the page: the nudge stays in the chat.
#[tauri::command]
fn balloon_close(app: AppHandle, key: String) {
    finish_nudge(&app, &key);
}

#[tauri::command]
fn desktop_open_url(app: AppHandle, url: String) -> Result<(), String> {
    let parsed = Url::parse(&url).map_err(|e| e.to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("only http(s) links can be opened".into());
    }
    app.opener()
        .open_url(parsed.as_str(), None::<&str>)
        .map_err(|e| e.to_string())
}

// ------------------------------------------------------------------ setup

fn create_windows(app: &AppHandle, prefs: &Prefs) -> tauri::Result<()> {
    let origin = shared(app).web_origin.clone();

    let bubble = WebviewWindowBuilder::new(app, BUBBLE, WebviewUrl::App("bubble.html".into()))
        .title("Mentor")
        .inner_size(BUBBLE_WIN, BUBBLE_WIN)
        // Without a min size Windows enforces its minimum window width (~130px) on this popup.
        .min_inner_size(BUBBLE_WIN, BUBBLE_WIN)
        .max_inner_size(BUBBLE_WIN, BUBBLE_WIN)
        .resizable(SIZED_BY_CODE_RESIZABLE)
        .maximizable(false)
        .minimizable(false)
        .decorations(false)
        .transparent(true)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .focused(false)
        // Shown at creation when it should show at all: Windows then shows it without activating
        // it (a later `show()` activates the window and would take the focus from the app the user
        // is in, e.g. right after logging in with autostart). The page is still empty (transparent)
        // while the position is set below.
        .visible(bubble_should_show(
            Session::Unknown,
            prefs.bubble_mode,
            prefs.bubble_hidden,
        ))
        // Release builds have no devtools anyway (the `devtools` cargo feature is off); be explicit.
        .devtools(cfg!(debug_assertions))
        .build()?;
    bubble.set_size(tauri::LogicalSize::new(BUBBLE_WIN, BUBBLE_WIN))?;
    let all = screens(app);
    let primary = app
        .primary_monitor()
        .ok()
        .flatten()
        .as_ref()
        .map(Screen::from);
    let saved = prefs.bubble_x.zip(prefs.bubble_y);
    if let Some((x, y)) = initial_bubble_pos(&all, primary, saved) {
        bubble.set_position(PhysicalPosition::new(x, y))?;
        // Landing on a monitor with another DPI resizes the bubble (and Windows may enforce a
        // minimum width): snap again with the real size. Not on Linux: GTK applies the move later,
        // so this would read back the window's spot before the move (0,0, size 0) and snap that to
        // the top-left corner; GDK's scale is the same on every monitor there anyway.
        let (pos, size) = (bubble.outer_position()?, bubble.outer_size()?);
        let (w, h) = (size.width as i32, size.height as i32);
        let resnap = cfg!(not(target_os = "linux"));
        if let Some(s) = screen_at(&all, pos.x + w / 2, pos.y + h / 2).filter(|_| resnap) {
            let (sx, sy) = snapped(s.work, s.scale, pos.x, pos.y, w, h);
            if (sx, sy) != (pos.x, pos.y) {
                bubble.set_position(PhysicalPosition::new(sx, sy))?;
            }
        }
    }

    // The speech balloon. Created visible (Windows shows it without activating it, since it is
    // not `focused`), empty and click-through; from then on it is only moved, filled and made
    // clickable, never shown again, so it cannot take the focus from the user's app. Owned by the
    // bubble: no Alt+Tab entry, always just above the bubble.
    let balloon = WebviewWindowBuilder::new(app, BALLOON, WebviewUrl::App("balloon.html".into()))
        .title("Mentor")
        .inner_size(nudge::BALLOON_W, nudge::BALLOON_MIN_H)
        .resizable(SIZED_BY_CODE_RESIZABLE)
        .maximizable(false)
        .minimizable(false)
        .decorations(false)
        .transparent(true)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .focused(false)
        .visible(true)
        .parent(&bubble)?
        .devtools(cfg!(debug_assertions))
        .build()?;
    balloon.set_ignore_cursor_events(true)?;
    // (Linux: the bubble has not moved yet, see above; `linux_follow_bubble` moves the balloon
    // again once it has.)
    move_balloon(app, nudge::BALLOON_MIN_H);

    let panel_url = Url::parse(&format!("{origin}/popup")).expect("valid origin");
    let nav_origin = origin.clone();
    let nav_app = app.clone();
    let popup_app = app.clone();
    WebviewWindowBuilder::new(app, PANEL, WebviewUrl::External(panel_url))
        .title("Mentor")
        .inner_size(PANEL_W, PANEL_H)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .decorations(false)
        .shadow(true) // Windows 11: native rounded corners and shadow on the frameless panel
        .always_on_top(true)
        .skip_taskbar(true)
        .visible(false)
        // Let the page handle file drops (drag a screenshot into the chat).
        .disable_drag_drop_handler()
        // The panel only ever shows the web app; anything else opens in the system browser.
        .on_navigation(move |url| {
            if url.origin().ascii_serialization() == nav_origin {
                return true;
            }
            if matches!(url.scheme(), "http" | "https") {
                let _ = nav_app.opener().open_url(url.as_str(), None::<&str>);
            }
            false
        })
        // window.open / target=_blank: no extra WebView2 popup window (it would escape the
        // navigation rule above); http(s) links open in the system browser instead.
        .on_new_window(move |url, _features| {
            if matches!(url.scheme(), "http" | "https") {
                let _ = popup_app.opener().open_url(url.as_str(), None::<&str>);
            }
            tauri::webview::NewWindowResponse::Deny
        })
        .devtools(cfg!(debug_assertions))
        .build()?;
    Ok(())
}

/// IPC for the remote panel page: only the `desktop_*` commands and listening to events (for
/// `mentor://nudge-action`), only from `$WEB_ORIGIN`, only in the panel window. No plugin API.
fn add_panel_capability(app: &AppHandle) -> tauri::Result<()> {
    let origin = shared(app).web_origin.clone();
    app.add_capability(
        CapabilityBuilder::new("panel-remote")
            .remote(format!("{origin}/*"))
            .window(PANEL)
            .permission("allow-desktop-session")
            .permission("allow-desktop-unread")
            .permission("allow-desktop-hide-panel")
            .permission("allow-desktop-open-url")
            .permission("allow-desktop-nudge")
            .permission("allow-desktop-mascot")
            .permission("core:event:allow-listen")
            .permission("core:event:allow-unlisten"),
    )
}

/// Ctrl+Alt+M. Never fatal: a failure is logged and the tray (and the bubble) still open the chat.
/// Linux: the plugin grabs the key on the X server, which also works on a Wayland session through
/// XWayland (see `linux_display`), but there the compositor only passes the key on while an X11
/// window, e.g. one of ours, has the focus; in practice the shortcut works on X11 sessions only.
fn register_shortcut(app: &AppHandle) {
    let toggle = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::ALT), Code::KeyM);
    let toggle_id = toggle.id();
    let plugin = tauri_plugin_global_shortcut::Builder::new()
        .with_handler(move |app, shortcut, event| {
            if shortcut.id() == toggle_id && event.state() == ShortcutState::Pressed {
                toggle_panel(app);
            }
        })
        .build();
    if let Err(e) = app.plugin(plugin) {
        eprintln!("global shortcut plugin: {e}");
        return;
    }
    if let Err(e) = app.global_shortcut().register(toggle) {
        eprintln!("Ctrl+Alt+M is taken by another app ({e}); use the tray icon instead");
    }
}

/// Linux display setup, run first thing in `main` (before GTK starts and before any thread exists).
///
/// - Wayland: a client cannot place its own windows or keep them above others there, and the whole
///   design is placed windows (the bubble at the screen edge, the panel and the balloon beside it,
///   drag-to-snap), so on a Wayland session with XWayland available GTK is told to use X11.
///   `gdk::set_allowed_backends` and not `GDK_BACKEND=x11`: the variable would be inherited by the
///   browser `xdg-open` starts for "open the web app" and push it onto XWayland too. A user who
///   sets `GDK_BACKEND` themselves (or a session without XWayland) keeps native Wayland: the app
///   still works, the windows just land where the compositor puts them.
/// - NVIDIA's proprietary driver: WebKitGTK's DMA-BUF renderer gives blank (or, for the bubble and
///   the balloon, black) windows or "Error 71" crashes with it (tauri-apps/tauri#9394, Tauri's
///   "Linux graphics issues" page). The fallback costs a faster path, so it is only set when the
///   NVIDIA kernel driver is loaded and the user has not set the variable either way.
#[cfg(target_os = "linux")]
mod linux_display {
    use std::env::var_os;

    pub fn prepare() {
        let set = |k: &str| var_os(k).is_some_and(|v| !v.is_empty());
        let session = std::env::var("XDG_SESSION_TYPE").unwrap_or_default();
        if super::use_xwayland(set("WAYLAND_DISPLAY"), &session, set("DISPLAY"), set("GDK_BACKEND")) {
            gtk::gdk::set_allowed_backends("x11");
        }
        if var_os("WEBKIT_DISABLE_DMABUF_RENDERER").is_none()
            && std::path::Path::new("/proc/driver/nvidia/version").exists()
        {
            // Rust 2021: no other thread exists yet (see `main`).
            std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
        }
    }
}

/// Run GTK on XWayland: a Wayland session (`WAYLAND_DISPLAY`, or `XDG_SESSION_TYPE=wayland`) with an
/// X server to fall back to (`DISPLAY`), and no backend chosen by the user (`GDK_BACKEND`).
#[cfg(any(target_os = "linux", test))]
fn use_xwayland(wayland_display: bool, session_type: &str, display: bool, gdk_backend: bool) -> bool {
    (wayland_display || session_type.eq_ignore_ascii_case("wayland")) && display && !gdk_backend
}

fn main() {
    #[cfg(target_os = "linux")]
    linux_display::prepare();

    let app = tauri::Builder::default()
        // Must be the first plugin: a second launch just opens the panel of the running one.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_panel(app)
        }))
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_opener::init())
        // Toasts are shown from Rust only; no page is granted the plugin's commands.
        .plugin(tauri_plugin_notification::init())
        .manage(Shared {
            web_origin: web_origin(),
            inner: Mutex::new(Inner {
                session: Session::Unknown,
                unread: 0,
                bubble_hidden_by_user: false,
                bubble_mode: BubbleMode::default(),
                drag_offset: None,
                nudge_mode: NudgeMode::default(),
                nudges: NudgeQueue::default(),
                balloon_shown: false,
                balloon_prev_foreground: 0,
                panel_mascot: "idle",
                toast_seq: 0,
            }),
            tray_bubble_item: Mutex::new(None),
            tray_mode_items: Mutex::new(None),
            tray_autostart_item: Mutex::new(None),
            tray_nudge_items: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            bubble_state,
            bubble_click,
            bubble_menu,
            bubble_drag_start,
            bubble_drag_move,
            bubble_drag_end,
            desktop_session,
            desktop_unread,
            desktop_hide_panel,
            desktop_open_url,
            desktop_nudge,
            desktop_mascot,
            balloon_ready,
            balloon_action,
            balloon_close,
        ])
        .on_menu_event(on_menu_event)
        .on_window_event(|window, event| match event {
            WindowEvent::CloseRequested { api, .. } => {
                // Alt+F4 collapses instead of quitting; quit is in the tray menu.
                api.prevent_close();
                if window.label() == PANEL {
                    hide_panel(window.app_handle());
                }
            }
            // MENTOR_PANEL_PIN=1 (dev): keep the panel open on blur, e.g. while using WebView2 devtools.
            WindowEvent::Focused(false)
                if window.label() == PANEL && std::env::var_os("MENTOR_PANEL_PIN").is_none() =>
            {
                // Click outside collapses the panel, unless focus went to our bubble or a picker the
                // panel opened. Check a moment later, once the new foreground window is settled.
                let app = window.app_handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_millis(150));
                    // Pressing our tray icon activates the taskbar, and Windows 11 reports the
                    // icon's press and release together on release, which then toggles the panel.
                    // Collapsing now would make a slow click reopen the panel, so wait for the
                    // release and let its click decide.
                    let pressed_at = Instant::now();
                    let mut waited = false;
                    while left_button_down()
                        && cursor_on_tray_icon(&app)
                        && pressed_at.elapsed() < Duration::from_secs(10)
                    {
                        waited = true;
                        std::thread::sleep(Duration::from_millis(30));
                    }
                    if waited {
                        std::thread::sleep(Duration::from_millis(150));
                    }
                    let Some(panel) = get_win(&app, PANEL) else {
                        return;
                    };
                    if !panel.is_visible().unwrap_or(false) || panel.is_focused().unwrap_or(false) {
                        return;
                    }
                    if !foreground_is_ours(&panel) {
                        hide_panel(&app);
                    }
                });
            }
            #[cfg(target_os = "linux")]
            WindowEvent::Moved(_) if window.label() == BUBBLE => {
                linux_follow_bubble(window.app_handle())
            }
            _ => {}
        })
        .setup(|app| {
            let handle = app.handle().clone();
            let prefs = load_prefs(&handle);
            {
                let s = shared(&handle);
                let mut inner = s.inner.lock().unwrap();
                inner.bubble_hidden_by_user = prefs.bubble_hidden;
                inner.bubble_mode = prefs.bubble_mode;
                inner.nudge_mode = prefs.nudge_mode;
            }
            // Toast clicks: the toast itself means `open`, its buttons are the nudge's actions.
            let toast_app = handle.clone();
            let _ = handle.notification().on_action(move |performed| {
                if let Some((id, action)) = toast_action(performed) {
                    emit_nudge_action(&toast_app, id, &action);
                    if action == "open" {
                        show_panel(&toast_app);
                    }
                }
            });
            add_panel_capability(&handle)?;
            create_windows(&handle, &prefs)?;
            build_tray(&handle, &prefs)?;
            if handle.autolaunch().is_enabled().unwrap_or(false) {
                quote_autostart_entry(&handle); // repairs entries written by older builds
            }
            register_shortcut(&handle);
            // "always" mode: show the bubble right away, before the panel page reports a session.
            sync_bubble_visibility(&handle);

            let later = handle.clone();
            std::thread::spawn(move || {
                std::thread::sleep(STARTUP_SHOW_AFTER);
                // (debug test nudges: keep the panel closed so the balloons can be seen)
                let testing = cfg!(debug_assertions) && std::env::var_os("MENTOR_TEST_NUDGE").is_some();
                if !testing && shared(&later).inner.lock().unwrap().session == Session::Unknown {
                    show_panel(&later);
                }
            });
            // Debug builds: MENTOR_TEST_NUDGE=<n> shows n sample nudges (queued) after 3 s.
            #[cfg(debug_assertions)]
            if let Some(n) = std::env::var("MENTOR_TEST_NUDGE")
                .ok()
                .and_then(|v| v.trim().parse::<u32>().ok())
            {
                let test_app = handle.clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(3));
                    for _ in 0..n.min(5) {
                        push_test_nudge(&test_app);
                    }
                });
            }
            println!(
                "Mentor desktop: panel loads {}/popup",
                shared(&handle).web_origin
            );
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Mentor desktop app");

    app.run(|_app, event| {
        if let RunEvent::ExitRequested { api, code, .. } = event {
            // Windows are only hidden, never closed; keep running until "Thoát" (exit code set).
            if code.is_none() {
                api.prevent_exit();
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    const WA: Rect = Rect {
        x: 0,
        y: 0,
        w: 1920,
        h: 1032,
    }; // 1080p minus a 48px taskbar

    #[test]
    fn snaps_to_nearest_edge_and_stays_inside() {
        // near the right edge, mid-height -> right edge, y unchanged
        let (x, y) = snapped(WA, 1.0, 1800, 500, 72, 72);
        assert_eq!(x, 1920 - 12 - 56 - 8);
        assert_eq!(y, 500);
        // near the bottom -> bottom edge, above the taskbar
        let (_, y) = snapped(WA, 1.0, 900, 1010, 72, 72);
        assert_eq!(y, 1032 - 12 - 56 - 8);
        // dragged off-screen to the left -> back on the left edge
        let (x, _) = snapped(WA, 1.0, -300, 400, 72, 72);
        assert_eq!(x, 12 - 8);
        // a wider window than asked for (Windows minimum width): the circle still sits 12px from the edge
        let (x, _) = snapped(WA, 1.0, 1700, 500, 130, 72);
        assert_eq!(x + (130 - 56) / 2 + 56, 1920 - 12);
    }

    #[test]
    fn snap_respects_dpi_scale() {
        let wa = Rect {
            x: 0,
            y: 0,
            w: 2880,
            h: 1728,
        };
        let (x, _) = snapped(wa, 1.5, 2700, 800, 108, 108);
        assert_eq!(x, 2880 - 18 - 84 - 12);
    }

    // Virtual layout: 1080p primary at 100% with a bottom taskbar, a 4K-ish monitor at 150% to its
    // left and a bit higher (negative coordinates), and a portrait 1200x1920 at 125% on the right
    // with its taskbar on top.
    fn layout() -> Vec<Screen> {
        vec![
            Screen {
                full: Rect {
                    x: 0,
                    y: 0,
                    w: 1920,
                    h: 1080,
                },
                work: Rect {
                    x: 0,
                    y: 0,
                    w: 1920,
                    h: 1032,
                },
                scale: 1.0,
            },
            Screen {
                full: Rect {
                    x: -2880,
                    y: -400,
                    w: 2880,
                    h: 1620,
                },
                work: Rect {
                    x: -2880,
                    y: -400,
                    w: 2880,
                    h: 1548,
                },
                scale: 1.5,
            },
            Screen {
                full: Rect {
                    x: 1920,
                    y: 200,
                    w: 1200,
                    h: 1920,
                },
                work: Rect {
                    x: 1920,
                    y: 260,
                    w: 1200,
                    h: 1860,
                },
                scale: 1.25,
            },
        ]
    }

    fn inside(r: Rect, wa: Rect) -> bool {
        r.x >= wa.x && r.y >= wa.y && r.right() <= wa.right() && r.bottom() <= wa.bottom()
    }

    #[test]
    fn picks_the_monitor_under_a_point_or_the_nearest() {
        let s = layout();
        assert_eq!(screen_at(&s, 100, 100).unwrap().scale, 1.0);
        assert_eq!(screen_at(&s, -10, -300).unwrap().scale, 1.5);
        assert_eq!(screen_at(&s, 2500, 2000).unwrap().scale, 1.25);
        // the gap above the primary, right of the left monitor's top: nearest is the left monitor
        assert_eq!(screen_at(&s, -5, -390).unwrap().scale, 1.5);
        // far below everything on the right: the portrait monitor
        assert_eq!(screen_at(&s, 3000, 5000).unwrap().scale, 1.25);
        assert!(screen_at(&[], 0, 0).is_none());
    }

    #[test]
    fn initial_spot_uses_the_saved_monitor_and_its_dpi() {
        let s = layout();
        // saved on the 150% monitor (window 108px there): snapped to its left edge
        let (x, y) = initial_bubble_pos(&s, Some(s[0]), Some((-2870, 300))).unwrap();
        assert_eq!(x, -2880 + 18 - (108 - 84) / 2);
        assert_eq!(y, 300);
        // saved on a monitor that is gone: default spot on the primary, above the taskbar
        let (x, y) = initial_bubble_pos(&s, Some(s[0]), Some((9000, 9000))).unwrap();
        assert_eq!((x + 8 + 56, y + 8 + 56), (1920 - 12, 1032 - 24));
        // no saved spot, primary at 125%: default spot with the 125% sizes
        let (x, y) = initial_bubble_pos(&s, Some(s[2]), None).unwrap();
        let (win, circle) = (px(72.0, 1.25), px(56.0, 1.25));
        assert_eq!(
            x + (win - circle) / 2 + circle,
            1920 + 1200 - px(12.0, 1.25)
        );
        assert_eq!(y + (win - circle) / 2 + circle, 260 + 1860 - px(24.0, 1.25));
        assert!(initial_bubble_pos(&[], None, None).is_none());
    }

    #[test]
    fn panel_stays_on_the_bubble_monitor_for_every_edge_spot() {
        for scr in layout() {
            let win = bubble_win_size(scr.scale);
            let (pw, ph) = (px(PANEL_W, scr.scale), px(PANEL_H, scr.scale));
            // walk the bubble along all four edges of this monitor
            for i in 0..=20 {
                let t = i as f64 / 20.0;
                let along_x = scr.work.x + ((scr.work.w - win) as f64 * t) as i32;
                let along_y = scr.work.y + ((scr.work.h - win) as f64 * t) as i32;
                for (x, y) in [
                    (scr.work.x, along_y),
                    (scr.work.right() - win, along_y),
                    (along_x, scr.work.y),
                    (along_x, scr.work.bottom() - win),
                ] {
                    let (bx, by) = snapped(scr.work, scr.scale, x, y, win, win);
                    let b = Rect {
                        x: bx,
                        y: by,
                        w: win,
                        h: win,
                    };
                    let r = panel_rect(scr.work, scr.scale, b);
                    assert_eq!((r.w, r.h), (pw, ph), "{scr:?}");
                    assert!(
                        inside(r, scr.work),
                        "panel {r:?} outside {scr:?} for bubble {b:?}"
                    );
                    // never covers the circle
                    let (pad, _, c) = circle(scr.scale, win, win);
                    let circ = Rect {
                        x: bx + pad,
                        y: by + pad,
                        w: c,
                        h: c,
                    };
                    let overlap = r.x < circ.right()
                        && circ.x < r.right()
                        && r.y < circ.bottom()
                        && circ.y < r.bottom();
                    assert!(!overlap, "panel {r:?} covers bubble {circ:?} on {scr:?}");
                }
            }
        }
    }

    #[test]
    fn small_work_area_does_not_panic() {
        // 1366x768 at 125% with a 60px taskbar: the 700px-tall panel leaves less than 2x15px of
        // margin. `clamp` with crossed bounds used to panic here.
        let wa = Rect {
            x: 0,
            y: 0,
            w: 1366,
            h: 708,
        };
        let b = Rect {
            x: 1366 - 15 - 70 - 10,
            y: 400,
            w: 90,
            h: 90,
        };
        let r = panel_rect(wa, 1.25, b);
        assert!(inside(r, wa), "{r:?}");
        assert_eq!(r.h, 700);
        // even smaller than the panel: shrinks to the work area
        let tiny = Rect {
            x: -500,
            y: 10,
            w: 400,
            h: 500,
        };
        let r = panel_rect(
            tiny,
            1.0,
            Rect {
                x: -110,
                y: 300,
                w: 72,
                h: 72,
            },
        );
        assert!(inside(r, tiny), "{r:?}");
        assert_eq!((r.w, r.h), (380, 500));
    }

    #[test]
    fn prefs_load_old_partial_and_new_files() {
        let parse = |s: &str| serde_json::from_str::<Prefs>(s).unwrap();
        // file written before `bubble_mode` existed: keeps the spot, gets the default mode
        let p = parse(r#"{"bubble_x": 10, "bubble_y": -20, "bubble_hidden": true}"#);
        assert_eq!((p.bubble_x, p.bubble_y, p.bubble_hidden), (Some(10), Some(-20), true));
        assert_eq!(p.bubble_mode, BubbleMode::Always);
        // a missing `bubble_hidden` no longer throws the whole file (and the saved spot) away
        let p = parse(r#"{"bubble_x": 5, "bubble_y": 6}"#);
        assert_eq!((p.bubble_x, p.bubble_hidden), (Some(5), false));
        assert_eq!(parse("{}").bubble_mode, BubbleMode::Always);
        assert_eq!(
            parse(r#"{"bubble_mode": "signed_in"}"#).bubble_mode,
            BubbleMode::SignedIn
        );
        assert_eq!(parse(r#"{"bubble_mode": "always"}"#).bubble_mode, BubbleMode::Always);
        // unknown or null values fall back to the default without losing the other fields
        let p = parse(r#"{"bubble_x": 1, "bubble_y": 2, "bubble_mode": "sometimes"}"#);
        assert_eq!((p.bubble_x, p.bubble_mode), (Some(1), BubbleMode::Always));
        assert_eq!(parse(r#"{"bubble_mode": null}"#).bubble_mode, BubbleMode::Always);
        // round trip
        let p = Prefs {
            bubble_x: Some(3),
            bubble_y: Some(4),
            bubble_hidden: false,
            bubble_mode: BubbleMode::SignedIn,
            nudge_mode: NudgeMode::Toast,
        };
        let json = serde_json::to_string(&p).unwrap();
        assert!(json.contains(r#""bubble_mode":"signed_in""#), "{json}");
        assert!(json.contains(r#""nudge_mode":"toast""#), "{json}");
        assert_eq!(parse(&json).bubble_mode, BubbleMode::SignedIn);
        assert_eq!(parse(&json).nudge_mode, NudgeMode::Toast);
        // files written before `nudge_mode` existed get balloons; unknown values too
        assert_eq!(parse(r#"{"bubble_x": 1, "bubble_y": 2}"#).nudge_mode, NudgeMode::Balloon);
        let p = parse(r#"{"bubble_x": 1, "bubble_y": 2, "nudge_mode": "sometimes"}"#);
        assert_eq!((p.bubble_x, p.nudge_mode), (Some(1), NudgeMode::Balloon));
        assert_eq!(parse(r#"{"nudge_mode": "off"}"#).nudge_mode, NudgeMode::Off);
    }

    #[test]
    fn toast_clicks_carry_the_nudge_id() {
        // The payload shape the notification plugin builds on Windows: the action and the
        // serialized notification data (with our `extra.nudgeId`).
        let performed = |action: &str, id: serde_json::Value| {
            serde_json::from_value::<tauri_plugin_notification::ActionPerformed>(serde_json::json!({
                "actionId": action,
                "notification": {
                    "id": 3, "channelId": null, "title": "Ôn bài", "body": "5 thẻ",
                    "schedule": null, "largeBody": null, "summary": null,
                    "actionTypeId": "mentor:open=Mở", "group": null, "groupSummary": false,
                    "sound": null, "inboxLines": [], "icon": null, "largeIcon": null,
                    "iconColor": null, "attachments": [], "extra": {"nudgeId": id},
                    "ongoing": false, "autoCancel": false, "silent": false
                }
            }))
            .unwrap()
        };
        let (id, action) = toast_action(&performed("tap", serde_json::json!("n-1"))).unwrap();
        assert_eq!((id, action.as_str()), (serde_json::json!("n-1"), "open"));
        let (id, action) = toast_action(&performed("snooze_1h", serde_json::json!(42))).unwrap();
        assert_eq!((id, action.as_str()), (serde_json::json!(42), "snooze_1h"));
        assert!(toast_action(&performed("Bad Action", serde_json::json!(1))).is_none());
        // a toast from elsewhere (no nudge id) is ignored
        let other = serde_json::from_value::<tauri_plugin_notification::ActionPerformed>(
            serde_json::json!({"actionId": "tap"}),
        )
        .unwrap();
        assert!(toast_action(&other).is_none());
    }

    #[test]
    fn bubble_visibility_rules() {
        let (always, only_in) = (BubbleMode::Always, BubbleMode::SignedIn);
        for s in [Session::Unknown, Session::SignedOut, Session::SignedIn] {
            assert!(bubble_should_show(s, always, false), "{s:?}");
            // hidden by the user always wins
            assert!(!bubble_should_show(s, always, true), "{s:?}");
            assert!(!bubble_should_show(s, only_in, true), "{s:?}");
        }
        assert!(bubble_should_show(Session::SignedIn, only_in, false));
        assert!(!bubble_should_show(Session::SignedOut, only_in, false));
        assert!(!bubble_should_show(Session::Unknown, only_in, false));
        // only a known signed-out session gets the signed-out look
        assert!(!looks_signed_in(Session::SignedOut));
        assert!(looks_signed_in(Session::Unknown) && looks_signed_in(Session::SignedIn));
    }

    #[test]
    fn web_origin_rules() {
        // normalized to scheme://host[:port], path and trailing slash dropped
        assert_eq!(
            parse_web_origin(" https://mentor.example.vn/popup ", true).unwrap(),
            "https://mentor.example.vn"
        );
        assert_eq!(
            parse_web_origin("https://mentor.example.vn:8443/", true).unwrap(),
            "https://mentor.example.vn:8443"
        );
        // plain http: only this machine in release, anything in dev
        for local in ["http://localhost:3000", "http://127.0.0.1:3000", "http://[::1]:3000"] {
            assert_eq!(parse_web_origin(local, true).unwrap(), local);
        }
        assert!(parse_web_origin("http://mentor.example.vn", true).is_err());
        assert!(parse_web_origin("http://192.168.1.10:3000", true).is_err());
        assert!(parse_web_origin("http://localhost.evil.vn", true).is_err());
        assert_eq!(
            parse_web_origin("http://192.168.1.10:3000", false).unwrap(),
            "http://192.168.1.10:3000"
        );
        // not a web origin at all
        for bad in ["", "mentor.example.vn", "file:///C:/x", "ftp://example.vn", "javascript:alert(1)"] {
            assert!(parse_web_origin(bad, false).is_err(), "{bad}");
        }
    }

    #[test]
    fn run_entry_gets_quoted() {
        let exe = r"C:\Users\Nguyen Van A\AppData\Local\Mentor\mentor-desktop.exe";
        // what the autostart plugin writes (path, a space, no arguments)
        assert_eq!(
            quoted_run_command(&format!("{exe} "), exe).unwrap(),
            format!("\"{exe}\"")
        );
        assert_eq!(
            quoted_run_command(&format!("{exe} --autostart"), exe).unwrap(),
            format!("\"{exe}\" --autostart")
        );
        // Windows paths are case-insensitive
        assert!(quoted_run_command(&exe.to_uppercase(), exe).is_some());
        // already quoted, another program, or a longer path sharing the prefix: left alone
        assert!(quoted_run_command(&format!("\"{exe}\""), exe).is_none());
        assert!(quoted_run_command(r"C:\Other\app.exe ", exe).is_none());
        assert!(quoted_run_command(&format!("{exe}x "), exe).is_none());
        assert!(quoted_run_command("", exe).is_none());
        // non-ASCII user folder (no panic on char boundaries)
        let vi = r"C:\Users\Nguyễn Ánh\AppData\Local\Mentor\mentor-desktop.exe";
        assert_eq!(quoted_run_command(vi, vi).unwrap(), format!("\"{vi}\""));
        assert!(quoted_run_command(r"C:\Users\Nguyễ", vi).is_none());
    }

    #[test]
    fn linux_autostart_exec_gets_quoted() {
        // what auto-launch writes for an AppImage in a Vietnamese desktop's downloads folder
        let exe = "/home/lan/Tải về/Mentor-0.1.0-x86_64.AppImage";
        let entry = |exec: &str| {
            format!("[Desktop Entry]\nType=Application\nVersion=1.0\nName=Mentor\nComment=Mentor startup script\nExec={exec}\nStartupNotify=false\nTerminal=false")
        };
        let fixed = quoted_desktop_exec(&entry(&format!("{exe} ")), exe).unwrap();
        assert!(fixed.contains(&format!("\nExec=\"{exe}\"\n")), "{fixed}");
        assert!(fixed.starts_with("[Desktop Entry]\n") && fixed.ends_with("Terminal=false\n"));
        assert!(quoted_desktop_exec(&entry(&format!("{exe} --minimized")), exe)
            .unwrap()
            .contains(&format!("Exec=\"{exe}\" --minimized\n")));
        // `%` starts a field code in Exec
        let pct = "/home/lan/100% ok/Mentor.AppImage";
        assert!(quoted_desktop_exec(&entry(pct), pct)
            .unwrap()
            .contains("Exec=\"/home/lan/100%% ok/Mentor.AppImage\"\n"));
        // nothing to do: a plain path (the .deb), already quoted, another program, a longer path
        assert!(quoted_desktop_exec(&entry("/usr/bin/mentor-desktop "), "/usr/bin/mentor-desktop").is_none());
        assert!(quoted_desktop_exec(&entry(&format!("\"{exe}\"")), exe).is_none());
        assert!(quoted_desktop_exec(&entry("/opt/other app/x "), exe).is_none());
        assert!(quoted_desktop_exec(&entry(&format!("{exe}x ")), exe).is_none());
        // paths whose escaping launchers disagree on are left alone
        let odd = "/home/lan/a \"b\"/Mentor.AppImage";
        assert!(quoted_desktop_exec(&entry(odd), odd).is_none());
    }

    #[test]
    fn xwayland_only_on_wayland_with_x_and_no_user_choice() {
        assert!(use_xwayland(true, "wayland", true, false));
        assert!(use_xwayland(false, "wayland", true, false)); // WAYLAND_DISPLAY not exported
        assert!(use_xwayland(true, "", true, false));
        assert!(!use_xwayland(false, "x11", true, false)); // X11 session: nothing to change
        assert!(!use_xwayland(true, "wayland", false, false)); // no XWayland: stay on Wayland
        assert!(!use_xwayland(true, "wayland", true, true)); // the user chose GDK_BACKEND
        assert!(!use_xwayland(false, "tty", false, false));
    }

    #[test]
    fn fit_keeps_margins_or_centers() {
        assert_eq!(fit(-50, 100, 0, 1000, 10), 10);
        assert_eq!(fit(990, 100, 0, 1000, 10), 890);
        assert_eq!(fit(400, 100, 0, 1000, 10), 400);
        assert_eq!(fit(0, 700, 0, 708, 15), 4); // no room for margins: centered
        assert_eq!(fit(0, 708, 0, 708, 15), 0);
    }
}
