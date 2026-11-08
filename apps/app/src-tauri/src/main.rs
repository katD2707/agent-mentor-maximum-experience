//! Mentor: one app for students and teachers. The UI is the Vite/React frontend in `../src`; this shell adds the
//! native pieces: toasts, opening links, one running instance, and the "keep running for reminders" behaviour.
//!
//! Reminders while the window is closed: closing the window only hides it (the webview and its timers keep running),
//! a tray icon brings it back or quits, and the app starts hidden at login (`--autostart`). The page schedules the
//! reminders the gateway planned and asks this side to show each toast (`show_reminder`). Tapping a toast shows the
//! window and sends `reminder-open {id, deepLink}` to the page, which opens the link and reports `opened`.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod updater;

use std::fs;
use std::sync::atomic::{AtomicI32, Ordering};

use serde_json::json;
use tauri::menu::{CheckMenuItem, Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, WindowEvent};
use tauri_plugin_autostart::ManagerExt as _;
use tauri_plugin_notification::NotificationExt;

const MAIN: &str = "main";
const AUTOSTART_ARG: &str = "--autostart";

fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window(MAIN) {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

// ------------------------------------------------------------------ autostart entry quoting

/// The autostart plugin writes the Run entry as `C:\path\mentor-app.exe --autostart` without quotes; with a space in
/// the install path (a user name with a space) Windows may run the wrong program or nothing at all. Returns the
/// quoted command line when `current` is that unquoted form of `exe` (optionally followed by arguments); `None` when
/// it is already quoted or points elsewhere.
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
        // SAFETY: plain Win32 registry calls with valid, NUL-terminated UTF-16 buffers; the key handle is closed on
        // every path below.
        unsafe {
            if RegOpenKeyExW(HKEY_CURRENT_USER, path.as_ptr(), 0, KEY_QUERY_VALUE | KEY_SET_VALUE, &mut key) != ERROR_SUCCESS {
                return Ok(()); // no Run key: nothing to fix
            }
            let mut kind = 0u32;
            let mut buf = vec![0u16; 4096];
            let mut len = (buf.len() * 2) as u32;
            let read = RegQueryValueExW(key, value_name.as_ptr(), std::ptr::null(), &mut kind, buf.as_mut_ptr().cast(), &mut len);
            let mut result = Ok(());
            if read == ERROR_SUCCESS && kind == REG_SZ {
                let n = (len as usize / 2).min(buf.len());
                let current = String::from_utf16_lossy(&buf[..n]);
                let current = current.trim_end_matches('\0');
                if let Some(fixed) = super::quoted_run_command(current, exe) {
                    let data = wide(&fixed);
                    let set = RegSetValueExW(key, value_name.as_ptr(), 0, REG_SZ, data.as_ptr().cast(), (data.len() * 2) as u32);
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

#[cfg(not(windows))]
fn quote_autostart_entry(_app: &AppHandle) {}

/// Autostart is switched on once, the first time the app runs (so reminders still arrive after a restart); the tray
/// menu turns it off. A marker file remembers that the choice was made, so it is never switched back on.
fn first_run_autostart(app: &AppHandle) {
    let Ok(dir) = app.path().app_config_dir() else {
        return;
    };
    let marker = dir.join("autostart-set");
    if marker.exists() {
        return;
    }
    if !cfg!(debug_assertions) {
        if let Err(e) = app.autolaunch().enable() {
            eprintln!("autostart: {e}");
        }
    }
    let _ = fs::create_dir_all(&dir);
    let _ = fs::write(marker, b"1");
}

// ------------------------------------------------------------------ reminders

static TOAST_SEQ: AtomicI32 = AtomicI32::new(1);

/// Shows one reminder as a system toast. Called by the page when a scheduled reminder is due (the page keeps running
/// while the window is hidden in the tray). The toast carries the reminder id and deep link for the tap.
#[tauri::command]
fn show_reminder(app: AppHandle, id: String, title: String, body: String, deep_link: String) {
    let clip = |s: &str, n: usize| s.chars().take(n).collect::<String>();
    let seq = TOAST_SEQ.fetch_add(1, Ordering::Relaxed);
    let r = app
        .notification()
        .builder()
        .id(seq)
        .title(clip(&title, 80))
        .body(clip(&body, 240))
        .extra("reminderId", clip(&id, 128))
        .extra("deepLink", clip(&deep_link, 256))
        .show();
    if let Err(e) = r {
        eprintln!("toast: {e}");
    }
}

fn on_toast_action(app: &AppHandle, performed: &tauri_plugin_notification::ActionPerformed) {
    let Some(n) = performed.notification() else {
        return;
    };
    let extra = n.extra();
    let id = extra.get("reminderId").cloned().unwrap_or(serde_json::Value::Null);
    let link = extra.get("deepLink").cloned().unwrap_or(serde_json::Value::Null);
    show_main(app);
    let _ = app.emit_to(MAIN, "reminder-open", json!({ "id": id, "deepLink": link }));
}

// ------------------------------------------------------------------ tray

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Mở Mentor", true, None::<&str>)?;
    let auto = CheckMenuItem::with_id(app, "autostart", "Mở khi bật máy (để nhắc học)", true, app.autolaunch().is_enabled().unwrap_or(false), None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Thoát Mentor", true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(app, &[&open, &auto, &sep, &quit])?;
    let mut b = TrayIconBuilder::with_id("main")
        .tooltip("Mentor")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        b = b.icon(icon.clone());
    }
    b.build(app)?;
    Ok(())
}

fn on_menu_event(app: &AppHandle, event: MenuEvent) {
    match event.id().as_ref() {
        "open" => show_main(app),
        "autostart" => {
            let a = app.autolaunch();
            let want = !a.is_enabled().unwrap_or(false);
            let r = if want { a.enable() } else { a.disable() };
            if let Err(e) = r {
                eprintln!("autostart: {e}");
            }
            if want {
                quote_autostart_entry(app);
            }
        }
        "quit" => app.exit(0),
        _ => {}
    }
}

fn main() {
    tauri::Builder::default()
        // Must be the first plugin: a second launch just brings the running window forward.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| show_main(app)))
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, Some(vec![AUTOSTART_ARG])))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(updater::UpdateState::default())
        .invoke_handler(tauri::generate_handler![show_reminder, updater::update_check, updater::update_download, updater::update_install])
        .on_menu_event(on_menu_event)
        .on_window_event(|window, event| {
            // Closing the window keeps the app (and its reminders) running in the tray; "Thoát Mentor" really quits.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == MAIN {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .setup(|app| {
            let handle = app.handle().clone();
            let toast_app = handle.clone();
            let _ = handle.notification().on_action(move |performed| on_toast_action(&toast_app, performed));
            build_tray(&handle)?;
            first_run_autostart(&handle);
            if handle.autolaunch().is_enabled().unwrap_or(false) {
                quote_autostart_entry(&handle);
            }
            // started by the login entry: stay in the tray, the reminders run in the hidden window
            if std::env::args().any(|a| a == AUTOSTART_ARG) {
                if let Some(w) = handle.get_webview_window(MAIN) {
                    let _ = w.hide();
                }
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Mentor");
}

#[cfg(test)]
mod tests {
    use super::quoted_run_command;

    #[test]
    fn quotes_the_unquoted_run_entry_and_keeps_arguments() {
        let exe = r"C:\Users\Ba Lan\AppData\Local\Mentor\mentor-app.exe";
        assert_eq!(quoted_run_command(&format!("{exe} --autostart"), exe).unwrap(), format!("\"{exe}\" --autostart"));
        assert_eq!(quoted_run_command(exe, exe).unwrap(), format!("\"{exe}\""));
        assert!(quoted_run_command(&format!("\"{exe}\" --autostart"), exe).is_none());
        assert!(quoted_run_command(r"C:\Other\mentor-app.exe", exe).is_none());
    }
}
