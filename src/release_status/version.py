from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

import requests

PACKAGE_NAME = "release-status"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
CACHE_PATH = Path.home() / ".cache" / "release-status" / "version-check.json"
CACHE_TTL = timedelta(hours=24)
HTTP_TIMEOUT = 3


def get_current_version() -> str:
    return pkg_version(PACKAGE_NAME)


def _parse_version(version: str) -> tuple[int, ...]:
    cleaned = version.lstrip("v")
    return tuple(int(x) for x in cleaned.split("."))


def check_for_update(current_version: str) -> str | None:
    """Return latest version if newer than current, None otherwise.

    Fail-safe: any error silently returns None.
    """
    try:
        latest = _get_latest_version()
        if latest is None:
            return None
        if _parse_version(latest) > _parse_version(current_version):
            return latest
        return None
    except Exception:
        return None


def check_for_update_strict(current_version: str) -> tuple[str | None, bool]:
    """Like check_for_update but reports whether the check succeeded.

    Returns (latest_version_or_none, check_succeeded).
    """
    try:
        latest = _get_latest_version()
        if latest is None:
            return None, False
        if _parse_version(latest) > _parse_version(current_version):
            return latest, True
        return None, True
    except Exception:
        return None, False


def _get_latest_version() -> str | None:
    """Fetch latest version from cache or PyPI."""
    cached = _read_cache()
    if cached is not None:
        return cached.get("latest_version")

    resp = requests.get(PYPI_URL, timeout=HTTP_TIMEOUT)
    if resp.status_code == 200:
        latest: str = resp.json()["info"]["version"]
        _write_cache(latest)
        return latest

    # Don't cache server errors (5xx) — only cache explicit "no version" on 404
    if resp.status_code == 404:
        _write_cache(None)

    return None


def _read_cache() -> dict[str, str | None] | None:
    """Read cache file if it exists and is fresh. Returns None on miss."""
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text())
        checked_at = datetime.fromisoformat(data["checked_at"])
        if datetime.now(timezone.utc) - checked_at > CACHE_TTL:
            return None
        return data  # type: ignore[no-any-return]
    except Exception:
        return None


def _write_cache(latest_version: str | None) -> None:
    """Write version check result to cache file."""
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "latest_version": latest_version,
        }
        CACHE_PATH.write_text(json.dumps(data))
    except Exception:
        pass


def clear_update_cache() -> None:
    """Delete the version check cache file."""
    try:
        CACHE_PATH.unlink(missing_ok=True)
    except Exception:
        pass
