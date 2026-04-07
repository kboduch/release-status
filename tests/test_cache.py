from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

import pytest

from release_status.cache import Cache


@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    return Cache(cache_dir=tmp_path / "cache", ttl=timedelta(minutes=5))


def test_get_empty_cache(cache: Cache) -> None:
    assert cache.get("missing-key") is None


def test_set_and_get(cache: Cache) -> None:
    cache.set("key1", {"hello": "world"})
    assert cache.get("key1") == {"hello": "world"}


def test_expired_entry(cache: Cache) -> None:
    cache.set("key1", {"old": "data"})

    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    with patch("release_status.cache.datetime") as mock_dt:
        mock_dt.now.return_value = future
        mock_dt.fromisoformat = datetime.fromisoformat
        assert cache.get("key1") is None


def test_clear(cache: Cache) -> None:
    cache.set("k1", {"a": 1})
    cache.set("k2", {"b": 2})
    count = cache.clear()
    assert count == 2
    assert cache.get("k1") is None
    assert cache.get("k2") is None


def test_clear_empty(cache: Cache) -> None:
    assert cache.clear() == 0


def test_disabled_cache(cache: Cache) -> None:
    cache.enabled = False
    cache.set("key1", {"data": True})
    assert cache.get("key1") is None


def test_stores_list(cache: Cache) -> None:
    cache.set("commits", [{"sha": "abc"}, {"sha": "def"}])
    result = cache.get("commits")
    assert result == [{"sha": "abc"}, {"sha": "def"}]
