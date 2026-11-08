# syntax=docker/dockerfile:1
# Web build of apps/app (static files) served by Caddy. Build context = the repo root:
#   docker build -t mentor-web:prod -f infra/web.Dockerfile --build-arg VITE_API_BASE=https://<domain>/api .
# VITE_API_BASE is compiled into the bundle, so a new domain needs a rebuild. The mock client is never compiled in.

FROM node:22-bookworm-slim AS build
WORKDIR /repo
ARG VITE_API_BASE
RUN test -n "$VITE_API_BASE" || (echo "build arg VITE_API_BASE is required" >&2; exit 1)
ENV VITE_API_BASE=$VITE_API_BASE VITE_API_MOCK=
# pnpm straight from npm, the version apps/app pins (corepack run from the repo root fetches the newest pnpm,
# which then refuses the pinned packageManager)
RUN npm install -g pnpm@9.15.9
COPY apps/app/package.json apps/app/pnpm-lock.yaml apps/app/
RUN pnpm -C apps/app install --frozen-lockfile
COPY packages/mentor-mascot packages/mentor-mascot
COPY apps/app apps/app
RUN pnpm -C apps/app exec tsc -b && pnpm -C apps/app exec vite build

FROM caddy:2-alpine
COPY infra/web.Caddyfile /etc/caddy/Caddyfile
COPY --from=build /repo/apps/app/dist /srv
ENV XDG_CONFIG_HOME=/tmp XDG_DATA_HOME=/tmp
USER nobody
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1
