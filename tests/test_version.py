from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import responses

from release_status import version
from release_status.version import (
    _parse_version,
    check_for_update,
    check_for_update_strict,
    clear_update_cache,
    get_current_version,
)


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(version, "CACHE_PATH", tmp_path / "version-check.json")


def _cache_path() -> Path:
    return version.CACHE_PATH


def _write_cache(latest_version: str | None, age: timedelta = timedelta()) -> None:
    checked_at = datetime.now(timezone.utc) - age
    data = {"checked_at": checked_at.isoformat(), "latest_version": latest_version}
    _cache_path().parent.mkdir(parents=True, exist_ok=True)
    _cache_path().write_text(json.dumps(data))


# --- get_current_version ---


def test_get_current_version_returns_string() -> None:
    result = get_current_version()
    assert isinstance(result, str)
    assert len(result) > 0


# --- _parse_version ---


def test_parse_version_simple() -> None:
    assert _parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_strips_v_prefix() -> None:
    assert _parse_version("v1.2.3") == (1, 2, 3)


def test_parse_version_two_parts() -> None:
    assert _parse_version("1.0") == (1, 0)


# --- check_for_update ---


@responses.activate
def test_update_available() -> None:
    responses.add(
        responses.GET,
        version.PYPI_URL,
        json={"info": {"version": "2.0.0"}},
        status=200,
    )
    assert check_for_update("1.0.0") == "2.0.0"


@responses.activate
def test_already_up_to_date() -> None:
    responses.add(
        responses.GET,
        version.PYPI_URL,
        json={"info": {"version": "1.0.0"}},
        status=200,
    )
    assert check_for_update("1.0.0") is None


@responses.activate
def test_current_is_newer() -> None:
    responses.add(
        responses.GET,
        version.PYPI_URL,
        json={"info": {"version": "0.9.0"}},
        status=200,
    )
    assert check_for_update("1.0.0") is None


@responses.activate
def test_pypi_error_returns_none() -> None:
    responses.add(responses.GET, version.PYPI_URL, status=500)
    assert check_for_update("1.0.0") is None


@responses.activate
def test_network_error_returns_none() -> None:
    responses.add(
        responses.GET,
        version.PYPI_URL,
        body=ConnectionError("network down"),
    )
    assert check_for_update("1.0.0") is None


# --- cache behavior ---


@responses.activate
def test_cache_hit_skips_http() -> None:
    _write_cache("2.0.0")
    assert check_for_update("1.0.0") == "2.0.0"
    assert len(responses.calls) == 0


@responses.activate
def test_stale_cache_refetches() -> None:
    _write_cache("2.0.0", age=timedelta(hours=25))
    responses.add(
        responses.GET,
        version.PYPI_URL,
        json={"info": {"version": "3.0.0"}},
        status=200,
    )
    assert check_for_update("1.0.0") == "3.0.0"
    assert len(responses.calls) == 1


@responses.activate
def test_cache_written_on_success() -> None:
    responses.add(
        responses.GET,
        version.PYPI_URL,
        json={"info": {"version": "2.0.0"}},
        status=200,
    )
    check_for_update("1.0.0")
    assert _cache_path().exists()
    data = json.loads(_cache_path().read_text())
    assert data["latest_version"] == "2.0.0"
    assert "checked_at" in data


@responses.activate
def test_cached_null_version_returns_none() -> None:
    _write_cache(None)
    assert check_for_update("1.0.0") is None
    assert len(responses.calls) == 0


# --- check_for_update_strict ---


@responses.activate
def test_strict_update_available() -> None:
    responses.add(
        responses.GET,
        version.PYPI_URL,
        json={"info": {"version": "2.0.0"}},
        status=200,
    )
    ver, ok = check_for_update_strict("1.0.0")
    assert ver == "2.0.0"
    assert ok is True


@responses.activate
def test_strict_up_to_date() -> None:
    responses.add(
        responses.GET,
        version.PYPI_URL,
        json={"info": {"version": "1.0.0"}},
        status=200,
    )
    ver, ok = check_for_update_strict("1.0.0")
    assert ver is None
    assert ok is True


@responses.activate
def test_strict_network_error() -> None:
    responses.add(
        responses.GET,
        version.PYPI_URL,
        body=ConnectionError("network down"),
    )
    ver, ok = check_for_update_strict("1.0.0")
    assert ver is None
    assert ok is False


# --- server error caching ---


@responses.activate
def test_server_error_not_cached() -> None:
    responses.add(responses.GET, version.PYPI_URL, status=500)
    check_for_update("1.0.0")
    assert not _cache_path().exists()


@responses.activate
def test_404_is_cached() -> None:
    responses.add(responses.GET, version.PYPI_URL, status=404)
    check_for_update("1.0.0")
    assert _cache_path().exists()
    data = json.loads(_cache_path().read_text())
    assert data["latest_version"] is None


# --- clear_update_cache ---


def test_clear_update_cache_deletes_file() -> None:
    _write_cache("2.0.0")
    assert _cache_path().exists()
    clear_update_cache()
    assert not _cache_path().exists()


def test_clear_update_cache_no_error_if_missing() -> None:
    assert not _cache_path().exists()
    clear_update_cache()  # should not raise
