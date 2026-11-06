# Builder for the Linux packages of the Mentor desktop pop-up (apps/desktop): a .deb and an AppImage.
# Nothing from the repo is baked in; the repo is mounted read-only at /src and build-linux.sh (the
# entrypoint) builds from a copy, so the same image serves every version and origin.
#
#   docker build -t mentor-desktop-linux -f infra/desktop-linux.Dockerfile infra
#   apps/desktop/build-linux.sh --web-origin https://mentor.example.vn --version 0.1.0   (Linux VM:
#     builds this image and runs itself in it; Windows: see apps/desktop/README.md "Linux")
#
# Ubuntu 22.04 on purpose: the binary links against the glibc / webkit2gtk-4.1 of the build host, so
# building on the oldest supported release gives packages that install on 22.04 and everything newer
# (24.04, Mint 21+, Debian 12...). Building on 24.04 would make the .deb refuse to install on 22.04.
#
# Versions are pinned (Rust, Node, pnpm, the Tauri CLI comes from apps/desktop/pnpm-lock.yaml);
# Ubuntu packages come from the 22.04 archive at build time.
FROM ubuntu:22.04

ARG RUST_VERSION=1.99.1
ARG NODE_VERSION=20.19.5
ARG PNPM_VERSION=9.15.9

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8

# Tauri 2 Linux prerequisites (https://v2.tauri.app/start/prerequisites/#linux) plus:
# - patchelf, file, xdg-utils: the AppImage step (linuxdeploy) rewrites rpaths, probes file types and
#   ships xdg-open so "open in browser" works inside the AppImage;
# - rsync: build-linux.sh copies the read-only source into the cache volume keeping mtimes, so cargo
#   only rebuilds what changed;
# - xvfb, xauth, dbus-x11, at-spi2-core, imagemagick: the optional smoke test (start the AppImage on a
#   virtual X display with a session bus, screenshot it); not needed for the build itself.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config curl wget ca-certificates file patchelf xdg-utils rsync xz-utils \
        libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev libxdo-dev libssl-dev \
        libgtk-3-dev libsoup-3.0-dev libjavascriptcoregtk-4.1-dev \
        xvfb xauth dbus-x11 at-spi2-core imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Rust, minimal profile, one pinned toolchain (no rustup self-update at build time).
ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo PATH=/usr/local/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --no-modify-path --profile minimal --default-toolchain ${RUST_VERSION} \
    && rustc --version && cargo --version

# Node from the official tarball, checked against nodejs.org's SHASUMS256.txt; pnpm pinned like the
# `packageManager` field of apps/desktop/package.json.
RUN cd /tmp \
    && curl -fsSLO https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz \
    && curl -fsSLO https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt \
    && grep " node-v${NODE_VERSION}-linux-x64.tar.xz\$" SHASUMS256.txt | sha256sum -c - \
    && tar -xJf node-v${NODE_VERSION}-linux-x64.tar.xz -C /usr/local --strip-components=1 \
        --exclude='*/CHANGELOG.md' --exclude='*/README.md' --exclude='*/LICENSE' \
    && rm -f node-v${NODE_VERSION}-linux-x64.tar.xz SHASUMS256.txt \
    && npm install -g pnpm@${PNPM_VERSION} \
    && node --version && pnpm --version

# linuxdeploy (the AppImage step) is itself an AppImage, and containers have no FUSE: let every
# AppImage extract itself instead of mounting. The cargo registry, the target dir (with the build
# copy of the source), the pnpm store and the XDG cache (where the Tauri CLI keeps the linuxdeploy
# and AppRun downloads) live in named volumes (see build-linux.sh).
ENV APPIMAGE_EXTRACT_AND_RUN=1 \
    CARGO_TARGET_DIR=/cache/target \
    npm_config_store_dir=/cache/pnpm-store \
    XDG_CACHE_HOME=/cache/xdg \
    MENTOR_LINUX_BUILDER=1

WORKDIR /src
ENTRYPOINT ["bash", "/src/apps/desktop/build-linux.sh"]
