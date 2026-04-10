from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

import pytest

from release_status.cache import Cache


@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    return Cache(
        cache_dir=tmp_path / "cache",
        git_ttl=timedelta(minutes=5),
        env_ttl=timedelta(seconds=30),
    )


def test_get_git_empty_cache(cache: Cache) -> None:
    assert cache.get_git("missing-key") is None


def test_get_env_empty_cache(cache: Cache) -> None:
    assert cache.get_env("missing-key") is None


def test_set_and_get_git(cache: Cache) -> None:
    cache.set_git("key1", {"hello": "world"})
    assert cache.get_git("key1") == {"hello": "world"}


def test_set_and_get_env(cache: Cache) -> None:
    cache.set_env("key1", {"hello": "world"})
    assert cache.get_env("key1") == {"hello": "world"}


def test_git_expired_entry(cache: Cache) -> None:
    cache.set_git("key1", {"old": "data"})

    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    with patch("release_status.cache.datetime") as mock_dt:
        mock_dt.now.return_value = future
        mock_dt.fromisoformat = datetime.fromisoformat
        assert cache.get_git("key1") is None


def test_env_expired_entry(cache: Cache) -> None:
    cache.set_env("key1", {"data": True})

    future = datetime.now(timezone.utc) + timedelta(seconds=60)
    with patch("release_status.cache.datetime") as mock_dt:
        mock_dt.now.return_value = future
        mock_dt.fromisoformat = datetime.fromisoformat
        assert cache.get_env("key1") is None


def test_env_fresh_but_git_expired(cache: Cache) -> None:
    """3 minutes later: past env_ttl (30s) but within git_ttl (5m)."""
    cache.set_git("key1", {"data": True})
    cache.set_env("key2", {"data": True})

    future = datetime.now(timezone.utc) + timedelta(minutes=3)
    with patch("release_status.cache.datetime") as mock_dt:
        mock_dt.now.return_value = future
        mock_dt.fromisoformat = datetime.fromisoformat
        assert cache.get_git("key1") == {"data": True}
        assert cache.get_env("key2") is None


def test_clear(cache: Cache) -> None:
    cache.set_git("k1", {"a": 1})
    cache.set_git("k2", {"b": 2})
    count = cache.clear()
    assert count == 2
    assert cache.get_git("k1") is None
    assert cache.get_git("k2") is None


def test_clear_empty(cache: Cache) -> None:
    assert cache.clear() == 0


def test_disabled_cache(cache: Cache) -> None:
    cache.enabled = False
    cache.set_git("key1", {"data": True})
    cache.set_env("key2", {"data": True})
    assert cache.get_git("key1") is None
    assert cache.get_env("key2") is None


def test_stores_list(cache: Cache) -> None:
    cache.set_git("commits", [{"sha": "abc"}, {"sha": "def"}])
    result = cache.get_git("commits")
    assert result == [{"sha": "abc"}, {"sha": "def"}]


def test_zero_ttl_skips_io(tmp_path: Path) -> None:
    """TTL of 0 should not touch disk at all — preserves old behavior."""
    cache = Cache(
        cache_dir=tmp_path / "cache",
        git_ttl=timedelta(0),
        env_ttl=timedelta(0),
    )
    cache.set_git("key1", {"data": True})
    cache.set_env("key2", {"data": True})
    assert cache.get_git("key1") is None
    assert cache.get_env("key2") is None
    # Cache directory should not have been created
    assert not (tmp_path / "cache").exists()
