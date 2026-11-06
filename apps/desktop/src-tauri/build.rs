/// Host part of an `http://` URL (`[::1]` keeps its brackets), lowercased; `None` for other schemes.
fn http_host(url: &str) -> Option<String> {
    let url = url.trim();
    let scheme_end = url.find("://")?;
    if !url[..scheme_end].eq_ignore_ascii_case("http") {
        return None;
    }
    let rest = &url[scheme_end + 3..];
    let authority = rest.split(['/', '?', '#']).next().unwrap_or_default();
    let host_port = authority.rsplit('@').next().unwrap_or_default();
    let host = if host_port.starts_with('[') {
        host_port.split_inclusive(']').next().unwrap_or_default()
    } else {
        host_port.split(':').next().unwrap_or_default()
    };
    Some(host.to_ascii_lowercase())
}

fn main() {
    // `WEB_ORIGIN` is baked into the binary (option_env! in main.rs). A release build must not
    // point the panel, which gets IPC access, at a plain-http server on the network; main.rs
    // refuses that at run time too, but failing the build is clearer than a panel on localhost.
    println!("cargo:rerun-if-env-changed=WEB_ORIGIN");
    if std::env::var("PROFILE").as_deref() == Ok("release") {
        if let Ok(origin) = std::env::var("WEB_ORIGIN") {
            if let Some(host) = http_host(&origin) {
                if !matches!(host.as_str(), "localhost" | "127.0.0.1" | "[::1]") {
                    panic!(
                        "WEB_ORIGIN={origin:?}: release builds need https (plain http only for localhost)"
                    );
                }
            }
        }
    }

    // Declaring the app commands makes each one need an explicit permission (`allow-<command>`), so
    // the bubble and the remote panel page can each call only their own commands (see capabilities/
    // and the runtime capability in main.rs).
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "bubble_state",
            "bubble_click",
            "bubble_menu",
            "bubble_drag_start",
            "bubble_drag_move",
            "bubble_drag_end",
            "desktop_session",
            "desktop_unread",
            "desktop_hide_panel",
            "desktop_open_url",
            "desktop_nudge",
            "desktop_mascot",
            "balloon_ready",
            "balloon_action",
            "balloon_close",
        ]),
    ))
    .expect("failed to run tauri-build");
}
