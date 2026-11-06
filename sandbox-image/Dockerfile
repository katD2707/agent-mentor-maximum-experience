# syntax=docker/dockerfile:1
# Sandbox image: one container per learner, workspace mounted at /workspace (CONTRACTS.md section 2).
# Build from the repo root:  docker build -f sandbox-image/Dockerfile -t mentor-sandbox:dev .
# No secrets are baked in; MODEL_ROUTER_URL / MODEL_ROUTER_KEY / MENTOR_PROFILE / MENTOR_USER_ID /
# MENTOR_HARNESS_TOKEN / MENTOR_GATEWAY_TOKEN come at run time.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# matplotlib for learner code (run_python saves plots into the workspace). Headless: Agg backend, no GUI
# toolkit installed. The font cache is pre-built into /opt/mpl-cache (read-only image layer). The gateway runs
# the container with --read-only and an empty tmpfs on /tmp, so the CMD below copies that cache to
# $MPLCONFIGDIR=/tmp/.cache/matplotlib at start: the same dir matplotlib derives from HOME=/tmp
# ($HOME/.cache/matplotlib), so run_python (env allowlist: HOME, PATH, ... plus MPLBACKEND=Agg) shares it.
# Installed before the mentor packages so code changes do not rebuild this layer.
ENV MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/.cache/matplotlib
RUN pip install "matplotlib>=3.8,<4" \
    && MPLCONFIGDIR=/opt/mpl-cache python -c "import matplotlib.pyplot as plt; plt.figure(); plt.plot([0, 1]); plt.close('all')" \
    && chmod -R a+rX /opt/mpl-cache

WORKDIR /opt/mentor
# mentor-scripts pulls pypdf (pdf_extract) and pypdfium2==5.14.0 (pdf_render: page images of scanned PDFs that
# web_fetch downloads; manylinux wheel with PDFium bundled, ~8 MB, no apt packages). Versions: scripts/pyproject.toml.
COPY packages/mentor-schemas packages/mentor-schemas
COPY sandbox-image/scripts sandbox-image/scripts
COPY sandbox-image/harness sandbox-image/harness
RUN pip install ./packages/mentor-schemas ./sandbox-image/scripts ./sandbox-image/harness \
    && rm -rf /opt/mentor

# Non-root: uid/gid 4242 (not 1000, which is usually a real user on Linux hosts). The gateway passes
# --user <its own uid:gid> (the compose gateway image also runs as 4242) and never root.
RUN groupadd --gid 4242 mentor \
    && useradd --uid 4242 --gid 4242 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin mentor \
    && mkdir -p /workspace \
    && chown mentor:mentor /workspace

USER 4242:4242
WORKDIR /workspace
# The container is the isolation boundary, so learner utility code (run_python) is allowed here.
# Hardened run (DockerBackend): --read-only, --tmpfs /tmp, --cap-drop ALL, --security-opt no-new-privileges,
# own internal network per sandbox. HOME=/tmp keeps any tool that touches $HOME on the writable tmpfs, and git
# trusts every repo via env (no ~/.gitconfig write needed). The harness sets the same safe.directory at startup.
# Every endpoint but /v1/health needs `Authorization: Bearer $MENTOR_HARNESS_TOKEN` (set by the gateway).
ENV WORKSPACE_ROOT=/workspace \
    MENTOR_SANDBOX_ISOLATED=1 \
    HOME=/tmp \
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=safe.directory \
    GIT_CONFIG_VALUE_0=*
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/v1/health', timeout=2)"

CMD ["sh", "-c", "mkdir -p /tmp/.cache && { [ -d \"$MPLCONFIGDIR\" ] || cp -R /opt/mpl-cache \"$MPLCONFIGDIR\"; }; exec uvicorn mentor_harness.server:app --host 0.0.0.0 --port 8080"]
