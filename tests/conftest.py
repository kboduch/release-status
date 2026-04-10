from __future__ import annotations

import json
from pathlib import Path

import pytest

from release_status.config import AppConfig


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_config_path(tmp_path: Path) -> Path:
    config = {
        "cache_dir": str(tmp_path / "cache"),
        "git_cache_ttl": "5m",
        "env_cache_ttl": "30s",
        "since_days": 180,
        "projects": [
            {
                "name": "TestProject",
                "repository": {
                    "url": "https://github.com/org/repo.git",
                    "branch": "main",
                    "provider": {"type": "github-cli"},
                },
                "environments": [
                    {
                        "name": "dev",
                        "url": "https://dev.example.com/build.json",
                        "source": {
                            "type": "json",
                            "fields": {"version": "$.version"},
                        },
                    },
                    {
                        "name": "prod",
                        "url": "https://prod.example.com/build.html",
                        "source": {
                            "type": "regex",
                            "pattern": r"(?P<version>[a-f0-9]{7,40})",
                            "fields": {"version": "version"},
                        },
                    },
                ],
            }
        ]
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path


@pytest.fixture
def sample_config(sample_config_path: Path) -> AppConfig:
    from release_status.config import load_config
    return load_config(sample_config_path)
