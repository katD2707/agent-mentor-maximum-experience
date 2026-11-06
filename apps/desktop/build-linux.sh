#!/usr/bin/env bash
# Builds the Linux packages of the Mentor desktop pop-up (.deb and AppImage, x86_64) with the web
# origin baked in, the Linux counterpart of build-release.ps1.
#
#   apps/desktop/build-linux.sh --web-origin https://mentor.example.vn --version 0.1.0
#   -> <repo>/dist/Mentor_0.1.0_amd64.deb and <repo>/dist/Mentor-0.1.0-x86_64.AppImage (+ .sha256)
#
# Run anywhere with Docker (the Linux VM, Git Bash on Windows): the script builds the builder image
# (infra/desktop-linux.Dockerfile, Ubuntu 22.04) and runs itself inside it with the repo mounted
# read-only at /src and <repo>/dist at /out. The cargo registry and a cache volume (cargo target dir,
# the build copy of the sources with its node_modules, the pnpm store, Tauri's AppImage tools) are
# named volumes, so a rebuild only compiles what changed. From PowerShell see apps/desktop/README.md
# ("Linux packages"). With --no-docker it builds on this machine (needs the Tauri Linux
# prerequisites, Rust, Node 20+ and pnpm; see the Dockerfile).
#
# Same rules as build-release.ps1:
#  1. the origin must be https, or plain http for localhost only (a test build: the files get a
#     -<host> suffix so they are never mistaken for a release);
#  2. the version (x.y.z, default: the one in tauri.conf.json) is set in tauri.conf.json, Cargo.toml
#     and package.json, but of the build copy only: the repo is never written to, so a running
#     `pnpm tauri dev` on the same checkout is not disturbed;
#  3. Cargo.toml must not enable the tauri `devtools` feature;
#  4. `pnpm tauri build --bundles deb,appimage` with WEB_ORIGIN set (build.rs refuses plain http for
#     other hosts too), then the origin must be found in the binary;
#  5. the packages are copied to dist/ with a .sha256 file each (`<hash>  <name>`).
#
# End users never set an environment variable: release builds use the baked origin and ignore
# WEB_ORIGIN at run time (see web_origin() in src-tauri/src/main.rs).
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: build-linux.sh --web-origin <url> [--version x.y.z] [options]

  --web-origin URL   where the panel loads the web app from, e.g. https://mentor.example.vn
                     (path dropped; http only for localhost / 127.0.0.1 / [::1] test builds)
  --version X.Y.Z    default: the version in src-tauri/tauri.conf.json
  --test             run the Rust unit tests (`cargo test`, Linux build of the tests) before building
  --smoke-test       after building, start the AppImage on a virtual display (Xvfb): fail unless it
                     finishes its setup and keeps running 12 s; screenshot in the cache volume
  --no-docker        build on this machine instead of in the builder image
  --rebuild-image    rebuild the builder image even if it exists (e.g. after editing the Dockerfile)
  -h, --help         this text

Environment (Docker mode): MENTOR_LINUX_IMAGE (default mentor-desktop-linux),
MENTOR_LINUX_VOLUME_PREFIX (default mentor-desktop-linux).
EOF
}

step() { printf '\033[36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m    %s\033[0m\n' "$*"; }
fail() { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

WEB_ORIGIN_ARG=""
VERSION=""
SMOKE=0
RUN_TESTS=0
NO_DOCKER=0
REBUILD_IMAGE=0
ARGS=("$@")
while [ $# -gt 0 ]; do
    case "$1" in
        --web-origin) WEB_ORIGIN_ARG="${2:-}"; shift 2 ;;
        --web-origin=*) WEB_ORIGIN_ARG="${1#*=}"; shift ;;
        --version) VERSION="${2:-}"; shift 2 ;;
        --version=*) VERSION="${1#*=}"; shift ;;
        --smoke-test) SMOKE=1; shift ;;
        --test) RUN_TESTS=1; shift ;;
        --no-docker) NO_DOCKER=1; shift ;;
        --rebuild-image) REBUILD_IMAGE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; fail "unknown argument: $1" ;;
    esac
done
[ -n "$WEB_ORIGIN_ARG" ] || { usage >&2; fail "--web-origin is required"; }

DESKTOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/../.." && pwd)"

# ------------------------------------------------------------------ 0. hand over to the builder image
if [ "${MENTOR_LINUX_BUILDER:-}" != "1" ] && [ "$NO_DOCKER" = 0 ]; then
    command -v docker >/dev/null || fail "docker not found (or use --no-docker on a machine with the Tauri prerequisites)"
    IMAGE="${MENTOR_LINUX_IMAGE:-mentor-desktop-linux}"
    PREFIX="${MENTOR_LINUX_VOLUME_PREFIX:-mentor-desktop-linux}"
    REPO_HOST="$REPO_ROOT"
    case "$(uname -s)" in
        # Git Bash on Windows: give docker a Windows path and stop MSYS rewriting the /src... args.
        MINGW*|MSYS*|CYGWIN*) REPO_HOST="$(cd "$REPO_ROOT" && pwd -W)"; export MSYS_NO_PATHCONV=1 ;;
    esac
    if [ "$REBUILD_IMAGE" = 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        step "Building the builder image $IMAGE"
        docker build -t "$IMAGE" -f "$REPO_HOST/infra/desktop-linux.Dockerfile" "$REPO_HOST/infra"
    fi
    mkdir -p "$REPO_ROOT/dist"
    TTY=()
    [ -t 1 ] && TTY=(-t)
    step "Running the build in $IMAGE"
    # HOST_UID/GID: the files written to dist/ get the caller's owner, not root.
    exec docker run --rm "${TTY[@]}" \
        -v "$REPO_HOST:/src:ro" \
        -v "$REPO_HOST/dist:/out" \
        -v "$PREFIX-cargo:/usr/local/cargo/registry" \
        -v "$PREFIX-cache:/cache" \
        -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
        "$IMAGE" "${ARGS[@]}"
fi

# From here on: inside the builder (or --no-docker).
for tool in node pnpm cargo rsync; do
    command -v "$tool" >/dev/null || fail "$tool not found"
done

# ------------------------------------------------------------------ 1. origin
# Parsed like build-release.ps1 ([Uri] there, WHATWG URL here; main.rs uses the same origin form).
ORIGIN_INFO="$(node -e '
const raw = process.argv[1].trim();
let u;
try { u = new URL(raw); } catch { process.exit(2); }
if (!["http:", "https:"].includes(u.protocol) || !u.hostname) process.exit(2);
const host = u.hostname.toLowerCase();
const local = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(host);
if (u.protocol === "http:" && !local) process.exit(3);
console.log(u.origin + " " + (u.protocol === "https:" ? "release" : "test") + " " + host.replace(/[^a-z0-9.-]/g, ""));
' "$WEB_ORIGIN_ARG")" || case $? in
    3) fail "--web-origin must use https (plain http is only allowed for localhost test builds)" ;;
    *) fail "--web-origin '$WEB_ORIGIN_ARG' is not an http(s) URL, e.g. https://mentor.example.vn" ;;
esac
read -r ORIGIN KIND ORIGIN_HOST <<<"$ORIGIN_INFO"
SUFFIX=""
if [ "$KIND" = test ]; then SUFFIX="-$ORIGIN_HOST"; fi

# ------------------------------------------------------------------ 2. work copy and version
if [ "${MENTOR_LINUX_BUILDER:-}" = "1" ]; then
    CACHE=/cache
    OUT=/out
else
    CACHE="$DESKTOP_DIR/target-linux"
    OUT="$REPO_ROOT/dist"
fi
WORK="$CACHE/work"
export CARGO_TARGET_DIR="$CACHE/target"
export npm_config_store_dir="${npm_config_store_dir:-$CACHE/pnpm-store}"
# no "is there a newer pnpm" request to the registry on every run
export npm_config_update_notifier=false
mkdir -p "$WORK/apps/desktop" "$WORK/packages" "$CARGO_TARGET_DIR" "$OUT"

step "Copying the sources to $WORK"
# -a keeps mtimes, so cargo and pnpm see unchanged files as unchanged. Build outputs and
# node_modules (Windows binaries in a Windows checkout) are not copied; the work copy keeps its own.
rsync -a --delete \
    --exclude node_modules --exclude /target-release --exclude /target-linux \
    --exclude /src-tauri/target --exclude /src-tauri/gen \
    "$DESKTOP_DIR/" "$WORK/apps/desktop/"
if [ -d "$REPO_ROOT/packages/mentor-mascot" ]; then
    rsync -a --delete --exclude node_modules "$REPO_ROOT/packages/mentor-mascot/" "$WORK/packages/mentor-mascot/"
fi
W="$WORK/apps/desktop"

CONF="$W/src-tauri/tauri.conf.json"
if [ -z "$VERSION" ]; then
    VERSION="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1], "utf8")).version)' "$CONF")"
fi
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "--version '$VERSION' must look like 0.1.0"
step "Version $VERSION"
set_version() { # file, sed pattern of the first version field (GNU sed: 0,/re/ = first match only)
    grep -Eq "$2" "$1" || fail "no version field found in $1"
    local new
    new="$(sed -E "0,/$2/s//\\1$VERSION\\2/" "$1")"
    # Only write when it changes: a new mtime alone makes cargo rebuild (and re-LTO) the app.
    if [ "$new" != "$(cat "$1")" ]; then
        printf '%s\n' "$new" >"$1"
        echo "    set version $VERSION in ${1#"$WORK"/}"
    fi
}
set_version "$CONF" '^(\s*"version"\s*:\s*")[^"]*(")'
set_version "$W/src-tauri/Cargo.toml" '^(version\s*=\s*")[^"]*(")'
set_version "$W/package.json" '^(\s*"version"\s*:\s*")[^"]*(")'

# Release builds must not ship devtools: the tauri `devtools` cargo feature must stay off.
if grep -q devtools "$W/src-tauri/Cargo.toml"; then
    fail "Cargo.toml enables 'devtools'; remove it for release builds"
fi

cd "$W"
step "pnpm install"
pnpm install --frozen-lockfile

# ------------------------------------------------------------------ 3. icons
# The Linux bundles use the PNGs; they are committed (build-release.ps1 regenerates them on Windows).
for icon in 32x32.png 128x128.png 128x128@2x.png; do
    if [ ! -f "src-tauri/icons/$icon" ]; then
        step "Generating icons from icon.svg ($icon missing)"
        pnpm tauri icon icon.svg
        break
    fi
done

if [ "$RUN_TESTS" = 1 ]; then
    step "cargo test"
    (cd src-tauri && cargo test)
fi

# ------------------------------------------------------------------ 4. build
export WEB_ORIGIN="$ORIGIN"
step "Building Mentor $VERSION for $ORIGIN (target dir $CARGO_TARGET_DIR)"
[ "$KIND" = test ] && warn "TEST BUILD (plain http): not for end users"
# NO_STRIP: linuxdeploy's bundled strip is older than the system's binutils and fails on some
# libraries; the app binary is already stripped by the release profile.
# One retry: the AppImage step downloads linuxdeploy and AppRun from GitHub on the first run (then
# they are cached), and a dropped connection should not cost a full rebuild; the retry only bundles.
if ! NO_STRIP=true pnpm tauri build --bundles deb,appimage; then
    warn "tauri build failed; retrying once (network downloads of the AppImage tools?)"
    NO_STRIP=true pnpm tauri build --bundles deb,appimage
fi

# ------------------------------------------------------------------ 5. collect
BIN="$CARGO_TARGET_DIR/release/mentor-desktop"
grep -qaF "$ORIGIN" "$BIN" || fail "$ORIGIN is not baked into $BIN (stale build? delete the cache volume and rerun)"
BUNDLE="$CARGO_TARGET_DIR/release/bundle"
DEB="$(ls -t "$BUNDLE"/deb/*_"${VERSION}"_amd64.deb 2>/dev/null | head -n1 || true)"
APPIMAGE="$(ls -t "$BUNDLE"/appimage/*_"${VERSION}"_amd64.AppImage 2>/dev/null | head -n1 || true)"
[ -n "$DEB" ] || fail "no .deb for $VERSION in $BUNDLE/deb"
[ -n "$APPIMAGE" ] || fail "no AppImage for $VERSION in $BUNDLE/appimage"

collect() { # source, name in dist/
    local out="$OUT/$2"
    cp -f "$1" "$out"
    chmod 0755 "$out"
    [ "${2##*.}" = deb ] && chmod 0644 "$out"
    local hash
    hash="$(sha256sum "$out" | cut -d' ' -f1)"
    printf '%s  %s\n' "$hash" "$2" >"$out.sha256"
    if [ -n "${HOST_UID:-}" ]; then chown "$HOST_UID:${HOST_GID:-$HOST_UID}" "$out" "$out.sha256" 2>/dev/null || true; fi
    printf '\033[32m%-9s: %s\033[0m\n' "${2##*.}" "$out"
    printf '%-9s: %s MB\n' "Size" "$(awk "BEGIN {printf \"%.2f\", $(stat -c %s "$out") / 1048576}")"
    printf '%-9s: %s\n' "SHA-256" "$hash"
}
echo
collect "$DEB" "Mentor_${VERSION}${SUFFIX}_amd64.deb"
collect "$APPIMAGE" "Mentor-${VERSION}${SUFFIX}-x86_64.AppImage"
echo "Origin   : $ORIGIN"
echo "Depends  : $(dpkg-deb -f "$DEB" Depends 2>/dev/null || echo '?')"
echo "(in Docker the paths above are under /out = <repo>/dist)"

# ------------------------------------------------------------------ 6. optional smoke test
if [ "$SMOKE" = 1 ]; then
    command -v xvfb-run >/dev/null && command -v dbus-run-session >/dev/null \
        || fail "--smoke-test needs xvfb-run and dbus-run-session (both are in the builder image)"
    step "Smoke test: starting the AppImage on a virtual display"
    SMOKE_DIR="$CACHE/smoke"
    rm -rf "$SMOKE_DIR" && mkdir -p "$SMOKE_DIR/home"
    cp -f "$OUT/Mentor-${VERSION}${SUFFIX}-x86_64.AppImage" "$SMOKE_DIR/Mentor.AppImage"
    # HOME in the cache: the app writes its prefs and WebKit data there, not in the image. Passes
    # when the app gets through its setup (it prints "panel loads ...": windows, tray, shortcut
    # done; unpacking the AppImage takes a few seconds first) and is still running 12 s later
    # (past the 8 s "show the panel when no session came" fallback). No web app runs here, so the
    # panel shows WebKit's connection error; the screenshot shows the bubble and that panel.
    set +e
    HOME="$SMOKE_DIR/home" APPIMAGE_EXTRACT_AND_RUN=1 \
        xvfb-run -a -s "-screen 0 1366x768x24" dbus-run-session -- bash -c '
            "$1/Mentor.AppImage" >"$1/app.log" 2>&1 &
            pid=$!
            for _ in $(seq 1 60); do
                kill -0 "$pid" 2>/dev/null || break
                grep -q "panel loads" "$1/app.log" && break
                sleep 0.5
            done
            grep -q "panel loads" "$1/app.log" || { echo "no startup line within 30 s" >>"$1/app.log"; kill "$pid" 2>/dev/null; exit 1; }
            sleep 12
            if kill -0 "$pid" 2>/dev/null; then
                command -v import >/dev/null && import -window root "$1/screen.png" 2>/dev/null
                kill "$pid"; wait "$pid" 2>/dev/null
                exit 0
            fi
            wait "$pid"; echo "exited early with code $?" >>"$1/app.log"; exit 1
        ' _ "$SMOKE_DIR"
    status=$?
    set -e
    sed 's/^/    | /' "$SMOKE_DIR/app.log" | tail -n 40
    [ "$status" = 0 ] || fail "the AppImage did not start or did not stay up (log above)"
    echo "Smoke test passed (screenshot: $SMOKE_DIR/screen.png in the cache volume)"
fi
