# Mentor desktop pop-up (Tauri 2)

A floating green bubble near the bottom-right corner, above the taskbar: the Mentor mascot (the
brand tile with a face). Click it (or press **Ctrl+Alt+M**) to open a small chat panel next to it;
**Esc** or a click elsewhere collapses it. When the mentor has something to say (a check-in, a
deadline, a review), it speaks up in a speech balloon beside the bubble, or as a Windows toast.

- **Bubble**: the mascot `<mentor-mascot>` from `packages/mentor-mascot` (the green brand tile with a
  face; one tight bottom corner is a speech tail that points at the screen edge it is docked to). It
  waves once at startup, shows `thinking` while a chat turn runs, `sleepy` in quiet hours or with the
  sandbox asleep, `calm` for serious topics (all reported by the panel page), and `happy` (or the
  nudge's own hint) while a speech balloon is up. If `src/mascot.js` is missing it falls back to the
  white "M" tile. While the panel is open it shows a close mark on the
  panel's surface color. Always on top, no taskbar entry. Drag it anywhere; on release it snaps to the
  nearest screen edge and remembers the spot (`%APPDATA%\vn.mentor.desktop\bubble.json`; Linux:
  `~/.config/vn.mentor.desktop/bubble.json`). Right-click
  for a small menu. A red badge counts what the mentor sent while the panel was closed (proactive
  `notification`s, approval requests, and finished replies).
- **Panel**: 380x560, frameless, rounded (Windows 11), opens beside the bubble and flips left/right
  and up/down to stay on screen. It shows the web app's `/popup` route: chat, attach/paste/drop
  images, the "open full page" button (opens the system browser).
- **Tray icon**: left-click toggles the panel; menu has open web app, show/hide bubble, when the
  bubble shows (see below), how nudges show (see below), start with Windows, quit. A second launch just opens the running app's
  panel.
- **When the bubble shows**: tray menu, two radio-style items:
  - **Bong bóng: luôn hiện** (default): the bubble shows from launch, signed in or not, so you can see
    the app is running. While signed out it is an outline tile (accent ring, no fill, no badge) with
    the tooltip "Mentor: chưa đăng nhập — bấm để đăng nhập"; click it or press Ctrl+Alt+M to open the
    panel on the login page.
  - **Bong bóng: chỉ khi đã đăng nhập**: the bubble appears only after signing in (the old behavior).

  "Hiện bong bóng" still wins: a bubble hidden by the user stays hidden in either mode. The choice
  is saved as `"bubble_mode": "always" | "signed_in"` in `bubble.json`. Older files without the field,
  or with an unknown value, get `"always"`.
- **Nudges (speech balloon)**: the panel page forwards proactive messages with `desktop_nudge`. A
  small balloon slides out of the bubble on the side away from the screen edge, with the title, the
  text, up to 3 buttons and a close ×. Clicking the text opens the chat panel; a button sends that
  answer (snooze, done, start focus...); × or **Esc** closes it. It goes away after 12 s unless the
  pointer is on it or it has keyboard focus. It never takes the focus from the app you are in (it
  is never activated by the app; only your click focuses it, and focus goes back to your app when
  it closes). Several nudges queue and show one at a time; repeats collapse. With Windows' "Show
  animations" off it fades instead of sliding.
- **When nudges show**: tray menu, three radio-style items, saved as `"nudge_mode"` in `bubble.json`
  (older files get `"balloon"`):
  - **Nhắc nhở: bong bóng** (default): the balloon; a silent Windows toast instead when the balloon
    could not be seen: the bubble is hidden, the session is locked, a full-screen app or
    presentation is running, or a screen reader is on (toasts are announced, a background window is
    not). While the chat panel is open, nothing extra shows (the chat has it).
  - **Nhắc nhở: thông báo Windows**: always a toast. Toasts are silent and carry the same buttons;
    clicking the toast opens the chat. Toast clicks only work while the toast is on screen, not
    from the Action Center.
  - **Nhắc nhở: tắt**: only the chat and the bubble's badge.

  Quiet hours and the proactivity level are applied by the server before a nudge reaches the app.
- **Sign-in**: when signed out, the panel shows the login page (it opens by itself on first launch
  and when the session ends). Sign in with the **6-digit code** from the login email (the link in
  the email would sign in the browser, not this window). THPT accounts waiting for parent
  verification see the onboarding step.

## Run (Windows PowerShell)

Needs Rust (MSVC toolchain), the Visual Studio C++ Build Tools, Node 20+ and pnpm. WebView2 ships
with Windows 11.

```powershell
# 1. gateway + web app as usual (repo README), e.g. in two terminals:
$env:MENTOR_ENV="dev"; $env:MENTOR_DATA_DIR="var"; $env:SANDBOX_BACKEND="local"; $env:MENTOR_MODEL_MODE="scripted"; uv run uvicorn mentor_gateway.app:app --port 8000
cd apps/web; $env:NEXT_PUBLIC_API_BASE="http://localhost:8000/api"; pnpm dev

# 2. the pop-up (third terminal)
cd apps/desktop
pnpm install
pnpm tauri dev
```

`pnpm tauri dev` and `pnpm tauri build` first run `scripts/sync-mascot.mjs` (Tauri's
`beforeDevCommand` / `beforeBuildCommand`), which copies `packages/mentor-mascot/mascot.js` to
`src/mascot.js` when it changed. After editing the mascot while `tauri dev` runs, run
`pnpm sync-mascot` and reload the bubble (or restart). A plain `cargo build` uses the copy already in
`src/`.

**Test nudges (debug builds only)**: tray menu **Thử nhắc nhở** shows a sample nudge (three
samples in turn; click it a few times to see the queue), even before signing in. Or start with
`$env:MENTOR_TEST_NUDGE="3"` to get three queued samples 3 s after launch. The sample buttons emit
`mentor://nudge-action` like real ones; the page ignores ids it does not know.

`WEB_ORIGIN` (default `http://localhost:3000`) is where the panel loads the web app from:

- **debug builds** (`pnpm tauri dev`): `WEB_ORIGIN` at run time, else the value baked in at build time;
- **release builds**: the value baked in at build time wins; only a release built without one reads
  `WEB_ORIGIN` at run time. Plain `http://` is refused unless the host is `localhost`, `127.0.0.1` or
  `[::1]` (the build fails, and at run time the app falls back to `http://localhost:3000`).

```powershell
$env:WEB_ORIGIN="https://mentor.example.vn"; pnpm tauri dev      # run time (dev)
Remove-Item Env:WEB_ORIGIN                                        # back to localhost:3000
```

The panel uses the same origin as the browser web app, so the gateway needs no extra
`CORS_ORIGINS`. In dev the login page also shows the code (`dev_code`) with a "Điền mã" button.

### Release installer (for end users)

```powershell
cd apps/desktop
.\build-release.ps1 -WebOrigin https://mentor.example.vn -Version 0.1.0
# -> <repo>\dist\Mentor-Setup-0.1.0.exe (+ .sha256), size and SHA-256 printed
```

The script checks the origin (https; http only for localhost test builds, which get a `-localhost`
suffix), sets the version in `tauri.conf.json`, `Cargo.toml` and `package.json` (writes only what
changes), puts `~\.cargo\bin` on `PATH` if needed, regenerates the icons if they are missing or older
than `icon.svg`, runs `pnpm install` and `pnpm tauri build --bundles nsis` with `WEB_ORIGIN` baked in,
then checks the origin is in the binary and copies the installer to `dist\`. It builds into
`apps\desktop\target-release` (`-TargetDir` to change), outside `src-tauri`, so it neither fights a
running `pnpm tauri dev` over `target\debug\mentor-desktop.exe` nor triggers its file watcher. A version
change does edit files under `src-tauri`, so a running `tauri dev` rebuilds once.

The installer is per-user (`installMode: currentUser`, installs to `%LOCALAPPDATA%\Mentor`, no admin
prompt) and downloads the WebView2 runtime silently if it is missing (`downloadBootstrapper`).
Uninstalling removes the autostart entry.

Code signing: there is no certificate yet. `-SignCommand 'signtool sign /fd sha256 /tr
http://timestamp.digicert.com /td sha256 /a %1'` (or any command with `%1` for the file) is passed to
Tauri's `bundle.windows.signCommand`, which signs the app exe, the uninstaller and the installer.
Unsigned installers trigger SmartScreen ("More info" -> "Run anyway"; see `docs/huong-dan-su-dung.md`).

Quick builds without the script:

```powershell
pnpm tauri build --debug    # src-tauri\target\debug\mentor-desktop.exe
```

### Linux packages (.deb and AppImage)

Built in Docker (`infra/desktop-linux.Dockerfile`: Ubuntu 22.04, Rust 1.99.1, Node 20, pnpm 9.15.9,
the Tauri 2 Linux prerequisites), so they install on Ubuntu 22.04 and newer (24.04, Mint 21+,
Debian 12): the binary needs the glibc and webkit2gtk-4.1 of the build host or newer.

On the Linux VM (or any machine with Docker, Git Bash on Windows included):

```bash
apps/desktop/build-linux.sh --web-origin https://mentor.example.vn --version 0.1.0
# -> dist/Mentor_0.1.0_amd64.deb and dist/Mentor-0.1.0-x86_64.AppImage (+ .sha256)
```

It builds the image `mentor-desktop-linux` the first time (`--rebuild-image` after editing the
Dockerfile) and runs itself in it. From Windows PowerShell, at the repo root:

```powershell
docker build -t mentor-desktop-linux -f infra/desktop-linux.Dockerfile infra
docker run --rm -v "${PWD}:/src:ro" -v "${PWD}\dist:/out" -v mentor-desktop-linux-cargo:/usr/local/cargo/registry -v mentor-desktop-linux-cache:/cache mentor-desktop-linux --web-origin https://mentor.example.vn --version 0.1.0
```

Same rules as `build-release.ps1`: https only (http for localhost test builds, whose files get a
`-localhost` suffix), version `x.y.z` (default: `tauri.conf.json`), no `devtools` feature, the
origin must be in the binary. Differences: the repo is mounted read-only and never written to; the
build runs on a copy in the `mentor-desktop-linux-cache` volume (with the cargo target dir, the
copy's `node_modules`, the pnpm store and Tauri's AppImage tools), so the version is set in the copy
only and a running `pnpm tauri dev` is not disturbed. The cargo registry is the
`mentor-desktop-linux-cargo` volume; the XDG cache in the cache volume keeps the linuxdeploy tools
Tauri downloads from GitHub for the AppImage (a dropped download is retried once). The first build
took ~15 min here (the release profile is fat LTO with one codegen unit), ~15 min more with
`--test` (the unit tests build every dependency again in the debug profile); a rebuild after a Rust
change ~9 min (the LTO link), with no change ~1 min plus the AppImage step. The icons are the committed PNGs
(regenerate them on Windows with `pnpm icons`). `--test` runs `cargo test` (the Linux build of the
unit tests) before building. `--smoke-test` starts the AppImage on a virtual display (Xvfb + a D-Bus
session) for 10 s and fails if it exits early.
`--no-docker` builds on the machine itself (Tauri Linux prerequisites, Rust, Node 20+, pnpm; cache
in `apps/desktop/target-linux`).

The .deb installs `/usr/bin/mentor-desktop`, a menu entry (category Education) and the icons, and
depends on `libwebkit2gtk-4.1-0`, `libgtk-3-0` and `libayatana-appindicator3-1` (tray). The AppImage
bundles WebKitGTK and GTK; it needs FUSE 2 on the user's machine (`libfuse2` on 22.04,
`libfuse2t64` on 24.04) or `--appimage-extract-and-run`. End-user steps: `docs/huong-dan-su-dung.md`
("Cài trên Linux"). Publish the link as `DESKTOP_DOWNLOAD_URL_LINUX` (infra/README.md).

**What differs on Linux** (`#[cfg(target_os = "linux")]` in `main.rs`; Windows behavior unchanged):

- **Window placement**: GTK applies moves asynchronously, so a position read right after a move is
  the old one. The startup re-snap (needed on Windows for DPI changes) is skipped, the end of a
  drag snaps from where the bubble was sent, and when the bubble reports its move the panel, the
  empty balloon and the bubble's side follow it (`linux_follow_bubble`). The bubble and the balloon
  stay `resizable` (`SIZED_BY_CODE_RESIZABLE`): GTK otherwise gives a non-resizable window its
  content's natural size, which grew the bubble to 200x200 and kept the balloon at least 200 px tall.
  Checked under Xvfb with and without a window manager (openbox): bubble 72x72 at the bottom-right,
  balloon beside it, drag-and-snap and the saved position. Not checked on a real GNOME desktop.

- **Wayland**: a Wayland client cannot place its windows or keep them on top, which the bubble, the
  panel, the balloon and drag-to-snap all need. On a Wayland session with XWayland (Ubuntu's
  default) the app runs on XWayland (`gdk::set_allowed_backends("x11")`, not the `GDK_BACKEND`
  variable, so the browser it opens is not pushed onto XWayland too). Users can opt out with
  `GDK_BACKEND=wayland`; the app then works but its windows go where the compositor puts them. With
  fractional scaling (125%, 150%) XWayland windows can look slightly blurry.
- **NVIDIA proprietary driver**: `WEBKIT_DISABLE_DMABUF_RENDERER=1` is set when
  `/proc/driver/nvidia/version` exists and the user has not set it (blank or black windows and
  "Error 71" crashes otherwise; tauri-apps/tauri#9394).
- **Tray**: AppIndicator reports no clicks; every click opens the menu, whose first item opens or
  collapses the chat. No tooltip either: the unread count is the icon's label. On stock GNOME
  (Debian, Fedora) the tray needs the "AppIndicator and KStatusNotifierItem Support" extension;
  Ubuntu ships it enabled. Without a tray the bubble still opens the chat and has the right-click menu.
- **Ctrl+Alt+M**: an X11 key grab. Works on X11 sessions; on Wayland GNOME only passes it on while
  one of our windows has the focus. Registration failures are only logged.
- **Notifications** ("Nhắc nhở: thông báo hệ thống"): freedesktop notifications over D-Bus
  (tauri-plugin-notification 2.8). GNOME and KDE show the buttons and report clicks on the
  notification (`open`) and on the buttons, as on Windows; servers without actions show the text only.
  Not detected on Linux: the locked screen, full-screen apps and screen readers (`presence()` is
  always "present", so the balloon is used where Windows would pick a notification).
- **Autostart** ("Khởi động khi đăng nhập"): `~/.config/autostart/Mentor.desktop`. For an AppImage
  it points at the AppImage file, quoted when the path has spaces (e.g. `~/Tải về`).
- **Focus**: a click outside collapses the panel unless the focus went to one of the app's own GTK
  windows (the bubble, the balloon, or the "attach image" file chooser). GNOME's focus-stealing
  prevention may keep the panel from taking the focus when opened from the tray; it then stays
  open until toggled.
- Transparent bubble and balloon: GNOME, KDE and other compositing desktops; on a window manager
  without a compositor they show a dark square behind the tile.
- The panel has no native shadow or rounded corners (Windows 11 only).

Regenerate the icons after editing `icon.svg`: `pnpm icons` (the release script does it when needed;
if the CLI cannot read the SVG it falls back to `apps\desktop\icon.png`, 1024x1024, or the existing
`src-tauri\icons\icon.png`).

Debugging the panel page: `$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=9333"`
exposes both webviews at `http://localhost:9333` (open from Edge via `edge://inspect`), and
`$env:MENTOR_PANEL_PIN="1"` stops the panel collapsing when it loses focus.

Rust unit tests (edge snapping, panel and balloon placement on virtual multi-monitor / mixed-DPI
layouts including 1366x768 at 125%, small work areas, the nudge queue and its de-duplication,
nudge validation and routing, toast click payloads, loading `bubble.json` and the bubble visibility
rule): `cd src-tauri; cargo test`.

Testing next to a running copy (single instance would just focus it): build with another identifier
into another target dir, e.g. `$env:TAURI_CONFIG='{"identifier":"vn.mentor.desktop.test","productName":"MentorTest"}';
$env:CARGO_TARGET_DIR="$env:TEMP\mentor-test-target"; cargo build`. It keeps its own settings, login
and autostart entry; Ctrl+Alt+M stays with whichever copy started first.


## How it fits together

- `src/bubble.*`: the bubble page (plain HTML/JS, colors copied from the web app's tokens). The
  shell pushes `{unread, open, side, signedIn, mascot}` to it with `window.mentorSetState`
  (`mascot`: the mascot state to show) and one-shot moves with `window.mentorMascotOnce("wave" |
  "celebrate")`; the page also reads the same state from `bubble_state` on load.
- `src/balloon.*`: the speech balloon page. The shell calls `mentorBalloon.render(nudge)`, the page
  answers with its height (`balloon_ready`), the shell places the window beside the bubble (same
  work-area and DPI code as the panel) and calls `mentorBalloon.reveal({side, anchorY})`. The
  window is created visible, empty and click-through, owned by the bubble (no Alt+Tab entry), and is
  only ever moved and made clickable, so Windows never activates it.
- `src-tauri/src/nudge.rs`: nudge validation, the queue, routing (balloon / toast / panel / off),
  balloon placement and the mascot priority, all pure and unit tested.
- Panel bridge for nudges (CONTRACTS.md section 9): `desktop_nudge {id, kind, title, body,
  actions: [{id, label}], mascot}` returns `"balloon" | "queued" | "duplicate" | "toast" | "panel" |
  "off"`; clicks come back to the panel page as the event `mentor://nudge-action {id, action}`
  (`open` also shows the panel; a click on a toast itself is `open`). `desktop_mascot {state}` sets
  the bubble's mascot. `signedIn` is false only once the panel page has
  reported a signed-out session (still loading counts as signed in, so the look does not flash).
- `src-tauri/src/main.rs`: windows, snapping, panel placement, tray, shortcut, autostart, commands.
- The panel webview stays alive while hidden, so the web page keeps its chat WebSocket open and the
  badge works with the panel collapsed. The page tells the shell about new messages and the session
  state through `desktop_*` commands (`apps/web/src/lib/desktop.ts`, `components/DesktopBridge.tsx`).
- Permissions: the bubble page may call only the `bubble_*` commands (`capabilities/bubble.json`).
  The balloon page may call only `balloon_ready`, `balloon_action` and `balloon_close`
  (`capabilities/balloon.json`). The remote panel page gets a runtime capability for
  `$WEB_ORIGIN/*` with only the six `desktop_*` commands plus `core:event:allow-listen`/`unlisten`
  (to receive `mentor://nudge-action`); no plugin APIs are exposed to any page (toasts are shown
  from Rust with `tauri-plugin-notification`; its injected `window.Notification` shim in the panel
  has no permission behind it, so the page should not use `Notification`). The panel cannot navigate away
  from `$WEB_ORIGIN`; other links, and `window.open` / `target=_blank`, open in the system browser
  (no WebView2 popup windows). Release builds have no devtools (the tauri `devtools` feature is off;
  the release script refuses to build if `Cargo.toml` mentions it). The local bubble page's CSP is
  `'self'` only; the remote page's CSP comes from the web server.
- Autostart: the autostart plugin writes the HKCU `Run` value unquoted (`C:\path\mentor-desktop.exe `),
  which breaks when the install path has a space (a user name with a space). The shell rewrites the
  value with quotes right after enabling it and at startup (repairing entries from older builds); it
  only touches the value when it is the unquoted path of the running exe.
- Browser preview of the panel layout: open `http://localhost:3000/popup?desktop=1`.
