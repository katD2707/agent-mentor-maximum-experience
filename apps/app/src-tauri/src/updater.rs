//! App updates (desktop). Uses the official `tauri-plugin-updater`: it fetches the channel's `latest.json` over
//! HTTPS and checks the minisign signature of the bundle against the public key in `tauri.conf.json`. On top of that
//! this module (patterns from hermes-agent: pinned digest, validated manifest, explicit states) refuses a manifest
//! that has no SHA-256 pin, a download URL that is not HTTPS or carries credentials, and a bundle whose digest does
//! not match. The page drives it in three steps (check, download in the background, install when idle).
//!
//! Channels: the configured endpoint is the `stable` feed (`<base>/stable/latest.json`); the page passes
//! `"beta"` when the learner chose early versions in settings, and the same feed is read from `<base>/beta/`.
//! While downloading, `update-progress {downloaded, total}` events go to the page (total is null when unknown).
//!
//! Plain `http` to a loopback host is accepted only in a build made with `--features insecure-dev-feed`
//! (the local update test); release builds are HTTPS only.

use std::sync::Mutex;

use semver::Version;
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter, State, Url};
use tauri_plugin_updater::{Update, UpdaterExt};

#[derive(Default)]
pub struct Pending {
    update: Option<Update>,
    bytes: Option<Vec<u8>>,
}
pub type UpdateState = Mutex<Pending>;

#[derive(Serialize)]
pub struct UpdateInfo {
    version: String,
    notes: Option<String>,
}

const SECRET_QUERY_KEYS: [&str; 8] = ["token", "access_token", "key", "apikey", "api_key", "secret", "password", "auth"];

#[derive(Serialize, Clone)]
struct Progress {
    downloaded: u64,
    total: Option<u64>,
}

/// `<base>/stable/latest.json` -> `<base>/<channel>/latest.json`. `None` for an unknown channel or an endpoint that
/// does not end in `/<channel>/<file>`.
fn channel_endpoint(endpoint: &str, channel: &str) -> Option<Url> {
    const CHANNELS: [&str; 2] = ["stable", "beta"];
    if !CHANNELS.contains(&channel) {
        return None;
    }
    let mut url = Url::parse(endpoint).ok()?;
    let mut parts: Vec<String> = url.path_segments()?.map(str::to_string).collect();
    let at = parts.len().checked_sub(2)?;
    if !CHANNELS.contains(&parts[at].as_str()) {
        return None;
    }
    parts[at] = channel.to_string();
    url.set_path(&parts.join("/"));
    Some(url)
}

fn configured_endpoint(app: &AppHandle) -> Option<String> {
    let cfg = app.config().plugins.0.get("updater")?;
    cfg.get("endpoints")?.as_array()?.first()?.as_str().map(str::to_string)
}

fn is_loopback(url: &Url) -> bool {
    matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"))
}

/// Checks the manifest the plugin received and returns the pinned SHA-256 (lowercase hex) of this platform's bundle.
fn validate_manifest(raw: &Value, download_url: &Url, current: &str, allow_loopback_http: bool) -> Result<String, String> {
    let version = raw.get("version").and_then(Value::as_str).ok_or("manifest has no version")?;
    let version = Version::parse(version.trim_start_matches('v')).map_err(|_| "manifest version is not semver")?;
    let current = Version::parse(current).map_err(|_| "app version is not semver")?;
    if version <= current {
        return Err("manifest version is not newer".into());
    }
    let secure = download_url.scheme() == "https" || (allow_loopback_http && download_url.scheme() == "http" && is_loopback(download_url));
    if !secure {
        return Err("download url must be https".into());
    }
    let leaks = !download_url.username().is_empty()
        || download_url.password().is_some()
        || download_url.query_pairs().any(|(k, _)| SECRET_QUERY_KEYS.contains(&k.to_ascii_lowercase().as_str()));
    if leaks {
        return Err("download url must not carry credentials".into());
    }
    let entry = raw
        .get("platforms")
        .and_then(Value::as_object)
        .and_then(|p| p.values().find(|e| e.get("url").and_then(Value::as_str) == Some(download_url.as_str())))
        .ok_or("manifest has no entry for this bundle")?;
    if entry.get("signature").and_then(Value::as_str).is_none_or(str::is_empty) {
        return Err("manifest entry has no signature".into());
    }
    let sha = entry.get("sha256").and_then(Value::as_str).ok_or("manifest entry has no sha256 pin")?.to_ascii_lowercase();
    if sha.len() != 64 || !sha.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("manifest sha256 is not 64 hex characters".into());
    }
    Ok(sha)
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes).iter().map(|b| format!("{b:02x}")).collect()
}

fn validate(update: &Update) -> Result<String, String> {
    validate_manifest(&update.raw_json, &update.download_url, &update.current_version, cfg!(feature = "insecure-dev-feed"))
}

#[tauri::command]
pub async fn update_check(app: AppHandle, state: State<'_, UpdateState>, channel: Option<String>) -> Result<Option<UpdateInfo>, String> {
    let channel = channel.unwrap_or_else(|| "stable".into());
    let endpoint = configured_endpoint(&app).ok_or("no update endpoint configured")?;
    let url = channel_endpoint(&endpoint, &channel).ok_or("unknown update channel")?;
    let updater = app.updater_builder().endpoints(vec![url]).map_err(|e| e.to_string())?.build().map_err(|e| e.to_string())?;
    let found = updater.check().await.map_err(|e| e.to_string())?;
    let Some(update) = found else {
        *state.lock().unwrap() = Pending::default();
        return Ok(None);
    };
    validate(&update)?;
    let info = UpdateInfo { version: update.version.clone(), notes: update.body.clone() };
    *state.lock().unwrap() = Pending { update: Some(update), bytes: None };
    Ok(Some(info))
}

/// Downloads the bundle (the plugin verifies the minisign signature) and checks it against the manifest's pin.
#[tauri::command]
pub async fn update_download(app: AppHandle, state: State<'_, UpdateState>) -> Result<(), String> {
    let update = state.lock().unwrap().update.clone().ok_or("no update checked")?;
    let pin = validate(&update)?;
    let mut downloaded: u64 = 0;
    let mut last_pct: i64 = -1;
    let on_chunk = |chunk: usize, total: Option<u64>| {
        downloaded += chunk as u64;
        // about one event per percent (or per 256 KiB when the size is unknown)
        let pct = total.filter(|t| *t > 0).map_or((downloaded / (256 * 1024)) as i64, |t| (downloaded * 100 / t) as i64);
        if pct != last_pct {
            last_pct = pct;
            let _ = app.emit("update-progress", Progress { downloaded, total });
        }
    };
    let bytes = update.download(on_chunk, || {}).await.map_err(|e| e.to_string())?;
    if sha256_hex(&bytes) != pin {
        return Err("sha256 mismatch".into());
    }
    state.lock().unwrap().bytes = Some(bytes);
    Ok(())
}

/// Installs the downloaded bundle. Windows: the installer takes over and the app exits; elsewhere the app restarts.
#[tauri::command]
pub fn update_install(app: AppHandle, state: State<'_, UpdateState>) -> Result<(), String> {
    let (update, bytes) = {
        let mut p = state.lock().unwrap();
        (p.update.clone().ok_or("no update checked")?, p.bytes.take().ok_or("update not downloaded")?)
    };
    update.install(bytes).map_err(|e| e.to_string())?;
    app.restart()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const SHA: &str = "ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12ab12";

    fn manifest(url: &str) -> Value {
        json!({ "version": "0.2.0", "platforms": { "windows-x86_64": { "url": url, "signature": "sig", "sha256": SHA } } })
    }
    fn check(url: &str, loopback: bool) -> Result<String, String> {
        validate_manifest(&manifest(url), &Url::parse(url).unwrap(), "0.1.0", loopback)
    }

    #[test]
    fn accepts_a_pinned_https_manifest() {
        assert_eq!(check("https://updates.example.org/mentor_0.2.0_x64-setup.exe", false).unwrap(), SHA);
    }

    #[test]
    fn rejects_plain_http_unless_dev_loopback() {
        assert!(check("http://updates.example.org/a.exe", false).is_err());
        assert!(check("http://updates.example.org/a.exe", true).is_err());
        assert!(check("http://127.0.0.1:8099/a.exe", false).is_err());
        assert!(check("http://127.0.0.1:8099/a.exe", true).is_ok());
    }

    #[test]
    fn rejects_credentials_in_the_url() {
        assert!(check("https://user:pw@updates.example.org/a.exe", false).is_err());
        assert!(check("https://updates.example.org/a.exe?token=abc", false).is_err());
        assert!(check("https://updates.example.org/a.exe?v=2", false).is_ok());
    }

    #[test]
    fn rejects_missing_or_malformed_pin_signature_and_stale_version() {
        let url = Url::parse("https://updates.example.org/a.exe").unwrap();
        let mut m = manifest(url.as_str());
        m["platforms"]["windows-x86_64"]["sha256"] = json!("nothex");
        assert!(validate_manifest(&m, &url, "0.1.0", false).is_err());
        m["platforms"]["windows-x86_64"].as_object_mut().unwrap().remove("sha256");
        assert!(validate_manifest(&m, &url, "0.1.0", false).is_err());
        let mut m = manifest(url.as_str());
        m["platforms"]["windows-x86_64"]["signature"] = json!("");
        assert!(validate_manifest(&m, &url, "0.1.0", false).is_err());
        assert!(validate_manifest(&manifest(url.as_str()), &url, "0.2.0", false).is_err());
    }

    #[test]
    fn switches_the_channel_segment_of_the_feed() {
        let got = |e: &str, c: &str| channel_endpoint(e, c).map(|u| u.to_string());
        assert_eq!(got("https://updates.mentor.vn/app/stable/latest.json", "beta").unwrap(), "https://updates.mentor.vn/app/beta/latest.json");
        assert_eq!(got("http://127.0.0.1:8099/app/beta/latest.json", "stable").unwrap(), "http://127.0.0.1:8099/app/stable/latest.json");
        assert!(got("https://updates.mentor.vn/app/stable/latest.json", "nightly").is_none());
        assert!(got("https://updates.mentor.vn/app/latest.json", "beta").is_none());
    }

    #[test]
    fn digest_is_lowercase_hex() {
        assert_eq!(sha256_hex(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    }
}
