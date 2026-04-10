from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_ZERO = timedelta(0)


class Cache:
    def __init__(
        self,
        cache_dir: Path,
        git_ttl: timedelta,
        env_ttl: timedelta,
    ) -> None:
        self.cache_dir = cache_dir
        self.git_ttl = git_ttl
        self.env_ttl = env_ttl
        self.enabled = True

    def _key_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{h}.json"

    def _get(self, key: str, ttl: timedelta) -> Any | None:
        if not self.enabled or ttl == _ZERO:
            return None
        path = self._key_path(key)
        if not path.exists():
            return None
        entry = json.loads(path.read_text())
        cached_at = datetime.fromisoformat(entry["cached_at"])
        if datetime.now(timezone.utc) - cached_at > ttl:
            path.unlink()
            return None
        return entry["data"]

    def _set(self, key: str, data: Any, ttl: timedelta) -> None:
        if not self.enabled or ttl == _ZERO:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self._key_path(key).write_text(json.dumps(entry))

    def get_git(self, key: str) -> Any | None:
        return self._get(key, self.git_ttl)

    def get_env(self, key: str) -> Any | None:
        return self._get(key, self.env_ttl)

    def set_git(self, key: str, data: Any) -> None:
        self._set(key, data, self.git_ttl)

    def set_env(self, key: str, data: Any) -> None:
        self._set(key, data, self.env_ttl)

    def clear(self) -> int:
        if not self.cache_dir.exists():
            return 0
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count
