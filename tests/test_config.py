from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from release_status.config import (
    AppConfig,
    generate_schema,
    load_config,
    resolve_config_path,
)


def test_load_valid_config(sample_config_path: Path) -> None:
    config = load_config(sample_config_path)
    assert len(config.projects) == 1
    assert config.projects[0].name == "TestProject"
    assert config.projects[0].repository.provider.type == "github-cli"
    assert len(config.projects[0].environments) == 2


def test_load_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config(Path("/nonexistent/config.json"))


def test_missing_version_field_in_json_source(tmp_path: Path) -> None:
    config = {
        "cache_dir": str(tmp_path / "cache"),
        "cache_ttl_minutes": 5,
        "projects": [
            {
                "name": "Bad",
                "repository": {
                    "url": "https://github.com/org/repo.git",
                    "provider": {"type": "github-cli"},
                },
                "environments": [
                    {
                        "name": "dev",
                        "url": "https://dev.example.com/build.json",
                        "source": {
                            "type": "json",
                            "fields": {"commit_time": "$.time"},
                        },
                    }
                ],
            }
        ]
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValidationError, match="version"):
        load_config(path)


def test_regex_invalid_group_reference(tmp_path: Path) -> None:
    config = {
        "cache_dir": str(tmp_path / "cache"),
        "cache_ttl_minutes": 5,
        "projects": [
            {
                "name": "Bad",
                "repository": {
                    "url": "https://github.com/org/repo.git",
                    "provider": {"type": "github-cli"},
                },
                "environments": [
                    {
                        "name": "dev",
                        "url": "https://dev.example.com/build.html",
                        "source": {
                            "type": "regex",
                            "pattern": r"(?P<version>\w+)",
                            "fields": {"version": "version", "time": "nonexistent"},
                        },
                    }
                ],
            }
        ]
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValidationError, match="nonexistent"):
        load_config(path)


def test_regex_invalid_pattern(tmp_path: Path) -> None:
    config = {
        "cache_dir": str(tmp_path / "cache"),
        "cache_ttl_minutes": 5,
        "projects": [
            {
                "name": "Bad",
                "repository": {
                    "url": "https://github.com/org/repo.git",
                    "provider": {"type": "github-cli"},
                },
                "environments": [
                    {
                        "name": "dev",
                        "url": "https://dev.example.com/build.html",
                        "source": {
                            "type": "regex",
                            "pattern": r"(?P<version>[",
                            "fields": {"version": "version"},
                        },
                    }
                ],
            }
        ]
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValidationError, match="Invalid regex"):
        load_config(path)


def test_generate_schema() -> None:
    schema = generate_schema()
    assert "properties" in schema
    assert "projects" in schema["properties"]


def test_resolve_config_path_cli_override(tmp_path: Path) -> None:
    path = tmp_path / "custom.json"
    assert resolve_config_path(path) == path


def test_resolve_config_path_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELEASE_STATUS_CONFIG", "/tmp/test.json")
    assert resolve_config_path() == Path("/tmp/test.json")


def test_resolve_config_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RELEASE_STATUS_CONFIG", raising=False)
    path = resolve_config_path()
    assert str(path).endswith(".config/release-status/config.json")


def test_discriminated_provider_types(tmp_path: Path) -> None:
    config = {
        "cache_dir": str(tmp_path / "cache"),
        "cache_ttl_minutes": 5,
        "projects": [
            {
                "name": "GitLabAPI",
                "repository": {
                    "url": "https://gitlab.com/org/repo.git",
                    "provider": {
                        "type": "gitlab-api",
                        "token_env": "MY_TOKEN",
                    },
                },
                "environments": [
                    {
                        "name": "dev",
                        "url": "https://dev.example.com/build.json",
                        "source": {
                            "type": "json",
                            "fields": {"version": "$.version"},
                        },
                    }
                ],
            }
        ]
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    cfg = load_config(path)
    assert cfg.projects[0].repository.provider.type == "gitlab-api"
    assert cfg.projects[0].repository.provider.token_env == "MY_TOKEN"
