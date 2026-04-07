from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from release_status.cli import app

runner = CliRunner()


def test_init_creates_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.json"
    result = runner.invoke(app, ["--config", str(config_path), "init"])
    assert result.exit_code == 0
    assert "Created config" in result.output
    assert config_path.exists()

    config = json.loads(config_path.read_text())
    assert "projects" in config
    assert config["projects"][0]["name"] == "my-project"


def test_init_refuses_if_exists(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")
    result = runner.invoke(app, ["--config", str(config_path), "init"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_init_creates_parent_dirs(tmp_path: Path) -> None:
    config_path = tmp_path / "deep" / "nested" / "config.json"
    result = runner.invoke(app, ["--config", str(config_path), "init"])
    assert result.exit_code == 0
    assert config_path.exists()


def test_check_with_valid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    runner.invoke(app, ["--config", str(config_path), "init"])
    result = runner.invoke(app, ["--config", str(config_path), "check"])
    assert result.exit_code == 0
    assert "Config is valid" in result.output


def test_check_missing_config(tmp_path: Path) -> None:
    config_path = tmp_path / "nonexistent.json"
    result = runner.invoke(app, ["--config", str(config_path), "check"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_projects_lists_projects(sample_config_path: Path) -> None:
    result = runner.invoke(app, ["--config", str(sample_config_path), "projects"])
    assert result.exit_code == 0
    assert "TestProject" in result.output
