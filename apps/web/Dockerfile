# syntax=docker/dockerfile:1
# Web app, production build (Next.js standalone server). Build context = apps/web:
#   docker build -t mentor-web:prod --build-arg NEXT_PUBLIC_API_BASE=https://<domain>/api apps/web
# NEXT_PUBLIC_* values are inlined into the client bundle at build time, so a new domain needs a rebuild.
# The mock client is never compiled in: NEXT_PUBLIC_API_MOCK is forced empty below.
# Standalone output comes from NEXT_PRIVATE_STANDALONE (Next reads it as the default for `output`), so
# next.config.ts stays untouched for `pnpm dev`; the build fails if .next/standalone is missing.

FROM node:22-bookworm-slim AS deps
WORKDIR /app
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:22-bookworm-slim AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE
# optional: installer link shown in the setup guide ("Cài app máy tính"); the step is hidden when empty
ARG NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL=
# optional: Linux package link (.deb or AppImage), shown instead to Linux desktop browsers
ARG NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL_LINUX=
RUN test -n "$NEXT_PUBLIC_API_BASE" || (echo "build arg NEXT_PUBLIC_API_BASE is required" >&2; exit 1)
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL=$NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL \
    NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL_LINUX=$NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL_LINUX \
    NEXT_PUBLIC_API_MOCK= \
    NEXT_PRIVATE_STANDALONE=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN rm -f .env .env.* \
    && pnpm build \
    && test -f .next/standalone/server.js \
    && mkdir -p public

FROM node:22-bookworm-slim AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD node -e "fetch('http://127.0.0.1:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
