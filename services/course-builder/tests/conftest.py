"""Live tests call the real model gateway. They run only when asked for, wherever pytest is started from
(the package's `-m 'not live'` addopts is ignored when pytest runs from the repo root)."""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("MENTOR_LIVE_BUILDER") == "1" or "live" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="live model test: set MENTOR_LIVE_BUILDER=1 or run with -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_picture_network(monkeypatch, request):
    """Unit tests never reach an image API or the web: the picture chain is pinned to code-drawn unless a test sets it."""
    if "live" not in request.keywords:
        monkeypatch.setenv("IMAGE_SOURCES", "code")
