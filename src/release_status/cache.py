from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

class Cache:
    def __init__(
        self,
        cache_dir: Path,
        ttl: timedelta,
    ) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.enabled = True

    def _key_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{h}.json"

    def get(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        path = self._key_path(key)
        if not path.exists():
            return None
        entry = json.loads(path.read_text())
        cached_at = datetime.fromisoformat(entry["cached_at"])
        if datetime.now(timezone.utc) - cached_at > self.ttl:
            path.unlink()
            return None
        return entry["data"]

    def set(self, key: str, data: Any) -> None:
        if not self.enabled:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        self._key_path(key).write_text(json.dumps(entry))

    def clear(self) -> int:
        if not self.cache_dir.exists():
            return 0
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count
