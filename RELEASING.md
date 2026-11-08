# Releasing the app (not courses)

Two separate pipelines. Neither needs the other.

| | App release | Course publish |
|---|---|---|
| What | Mentor itself: desktop installer, web build | A course or a new version of one (`pack.json` + assets) |
| Tool | `apps/app/scripts/release.mjs` | course-builder / gateway (`/api/catalog`, `/api/courses/{id}/versions/{v}/pack`) |
| Reaches users via | Desktop: `tauri-plugin-updater` feed. Web: service worker, next launch | The app syncs the catalog and downloads the pack (sha256 checked) |
| Needs a new app? | Yes, that is the point | **Never.** The one exception is below |

The exception: `pack.json` has `min_app_version`. An app older than that refuses the pack with a plain notice ("update the app")
instead of rendering blocks it does not know. So a course that uses a new block type sets `min_app_version` to the app version
that first shipped the block; everything else stays at the default `0.1.0`.

## Desktop

Signed with minisign. The public key is `plugins.updater.pubkey` in `apps/app/src-tauri/tauri.conf.json`; the private key and its
password stay out of git (dev pair: `var-dev/updater/`, which is gitignored). The checked-in pubkey is the **dev** key. Before the
first real release, generate a production pair (`pnpm -C apps/app tauri signer generate -w <path>`), keep the private key in your
secret store, and put its public half in `tauri.conf.json`.

```
export TAURI_SIGNING_PRIVATE_KEY=/secure/mentor.key
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=...        # from the secret store, never on the command line
pnpm -C apps/app release --bump patch --channel stable --base-url https://updates.example.org/app --notes "What changed"
```

The script bumps the version in `package.json`, `tauri.conf.json` and `Cargo.toml`, runs `tauri build` (which also builds the web bundle),
and writes under `release-out/` (gitignored):

- `<channel>/<version>/<installer>`: the signed bundle (upload next to the manifest)
- `<channel>/latest.json`: the channel manifest, with the minisign signature and a `sha256` pin per platform. The script
  validates it before writing (semver, https URLs with no credentials, signature, sha256)
- `web/`: the static web build for any static host

Run it on each OS (Windows, macOS, Linux) with the same version and `--out`; each run adds its platform to the same `latest.json`.
Upload `release-out/<channel>` to `<base-url>/<channel>/`. Channels are `stable` and `beta`: a build checks the feed it was built
with (`--channel beta` builds point at `<base-url>/beta/latest.json`).

What the app enforces: HTTPS feed (the plugin), minisign signature (the plugin), plus `src-tauri/src/updater.rs`: the manifest must
carry a `sha256` pin, the bundle URL must be https without credentials, and the downloaded bytes must match the pin. The update
downloads in the background and installs only when the learner is not in a lesson or practice run and has been idle for a minute
(or the window is hidden in the tray).

### Testing an update locally

`--dev-feed` (with an `http://127.0.0.1:<port>` base URL) builds with `--features insecure-dev-feed`, which allows plain http to a
loopback host. Never use it for a release; the script refuses an http base URL without it.

1. `release --version 0.1.0 --dev-feed ...`, keep the installer, install it.
2. `release --version 0.1.1 --dev-feed ...` into the same `--out`, serve that folder (`python -m http.server 8099`).
3. Start the installed 0.1.0; it finds 0.1.1, downloads, and restarts on 0.1.1 once idle.

## Web

`vite build` stamps `sw.js` with a build id. A browser that already has the app sees new `sw.js` bytes, installs the new build in the
background, and switches to it the next time the app is opened (no tab is swapped mid-lesson). The service worker also keeps the shell
offline. Deploy `web/` anywhere static; keep `sw.js` and `manifest.webmanifest` uncached (`Cache-Control: no-cache`).

## Not done

Android and iOS (stores, or an APK version check) are postponed.
