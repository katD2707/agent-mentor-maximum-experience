# syntax=docker/dockerfile:1
# Linux installers of the desktop app (apps/app + Tauri), built on Windows or anywhere Docker runs. Build context = repo root:
#   VITE_API_BASE=https://<domain>/api pnpm -C apps/app installers --linux
# (runs this build, then copies the files to the repo root next to the Windows and macOS ones). Out come
# Mentor_<version>_amd64.deb (double-click opens the software center on Ubuntu/Debian/Mint) and
# Mentor_<version>_amd64.AppImage (one file for any other distro). Ubuntu 22.04 is the base so the binaries run on glibc
# 2.35 and newer, which covers every desktop distro still supported.
# VITE_API_BASE is compiled into the app, like the web build. Updater artifacts are not signed here: release signing
# stays in scripts/release.mjs.

FROM ubuntu:22.04 AS build
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils file build-essential pkg-config patchelf \
      libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev libssl-dev libxdo-dev \
    && rm -rf /var/lib/apt/lists/*

ARG NODE_VERSION=22.12.0
RUN curl -fsSL https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz | tar -xJ -C /usr/local --strip-components=1
# pnpm straight from npm, the version apps/app pins (corepack in older Node 22 builds rejects npm's rotated signing key)
RUN npm install -g pnpm@9.15.9

ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo PATH=/usr/local/cargo/bin:$PATH
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable

WORKDIR /repo
ARG VITE_API_BASE
RUN test -n "$VITE_API_BASE" || (echo "build arg VITE_API_BASE is required" >&2; exit 1)
ENV VITE_API_BASE=$VITE_API_BASE VITE_API_MOCK= APPIMAGE_EXTRACT_AND_RUN=1 NO_STRIP=true

COPY apps/app/package.json apps/app/pnpm-lock.yaml apps/app/
RUN pnpm -C apps/app install --frozen-lockfile
COPY packages/mentor-mascot packages/mentor-mascot
COPY apps/app apps/app
# prebuild writes the guide map for the gateway; the gateway is not in this image, so give it somewhere to land
RUN mkdir -p services/gateway/src/mentor_gateway/ask
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/repo/apps/app/src-tauri/target \
    pnpm -C apps/app tauri build --bundles deb,appimage \
    && mkdir -p /out \
    && cp apps/app/src-tauri/target/release/bundle/deb/*.deb apps/app/src-tauri/target/release/bundle/appimage/*.AppImage /out/

FROM scratch
COPY --from=build /out /
