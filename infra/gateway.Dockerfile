# syntax=docker/dockerfile:1
# Gateway image (dev). Build from the repo root:  docker build -f infra/gateway.Dockerfile -t mentor-gateway:dev .
# It contains the whole uv workspace, so SANDBOX_BACKEND=local can run the harness as a subprocess, and the
# docker CLI, so SANDBOX_BACKEND=docker can start mentor-sandbox:dev containers through the mounted socket.
# Runs as the non-root user 4242 (same uid as the sandbox image's default user). The docker backend starts
# sandboxes with --user <this uid:gid>, so the gateway and the sandbox both own the working copies and nothing
# runs as root. Docker socket access comes from the socket's group: add it with `group_add` (compose:
# DOCKER_GID, 0 on Docker Desktop, `stat -c %g /var/run/docker.sock` on Linux). On Linux the host data dir
# must be writable by 4242 (or override `user:` with your own non-root uid:gid). See infra/README.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
COPY . .
RUN uv sync --all-packages --no-dev

RUN groupadd --gid 4242 mentor \
    && useradd --uid 4242 --gid 4242 --create-home --home-dir /home/mentor --shell /usr/sbin/nologin mentor \
    && mkdir -p /data \
    && chown 4242:4242 /data
# HOME=/tmp: works for any `user:` override (docker CLI config, git); the app never needs a real home.
ENV PATH=/opt/venv/bin:$PATH MENTOR_DATA_DIR=/data MENTOR_CONTENT_DIR=/app/mentor-content HOME=/tmp
USER 4242:4242

EXPOSE 8000 2525
# no access log: magic-link tokens travel in the query string (Caddy logs requests with the token redacted)
CMD ["uvicorn", "mentor_gateway.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
