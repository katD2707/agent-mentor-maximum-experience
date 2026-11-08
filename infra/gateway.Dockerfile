# syntax=docker/dockerfile:1
# Gateway image. Build from the repo root:  docker build -f infra/gateway.Dockerfile -t mentor-gateway:dev .
# It contains the whole uv workspace (the gateway imports mentor_schemas and mentor_scripts; the agent harness is a
# library for the future job workers). Runs as the non-root user 4242. On Linux the host data dir must be writable
# by 4242 (or override `user:` with your own non-root uid:gid). See infra/README.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app
COPY . .
RUN uv sync --all-packages --no-dev

RUN groupadd --gid 4242 mentor \
    && useradd --uid 4242 --gid 4242 --create-home --home-dir /home/mentor --shell /usr/sbin/nologin mentor \
    && mkdir -p /data \
    && chown 4242:4242 /data
# HOME=/tmp: works for any `user:` override (git); the app never needs a real home.
ENV PATH=/opt/venv/bin:$PATH MENTOR_DATA_DIR=/data MENTOR_CONTENT_DIR=/app/mentor-content HOME=/tmp
USER 4242:4242

EXPOSE 8000
# no access log: keeps request URLs (upload tokens) out of the container logs
CMD ["uvicorn", "mentor_gateway.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
