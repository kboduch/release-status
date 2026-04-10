from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

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

    from release_status.config import load_config
    config = load_config(config_path)
    assert len(config.projects) == 4
    provider_types = [p.repository.provider.type for p in config.projects]
    assert provider_types == ["github-cli", "github-api", "gitlab-cli", "gitlab-api"]


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


# --- update command ---


def test_update_already_up_to_date() -> None:
    with patch("release_status.cli.check_for_update_strict", return_value=(None, True)):
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "Already up to date" in result.output


def test_update_check_failed() -> None:
    with patch("release_status.cli.check_for_update_strict", return_value=(None, False)):
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "Could not check for updates" in result.output


def test_update_uv_not_found() -> None:
    with (
        patch("release_status.cli.check_for_update_strict", return_value=("2.0.0", True)),
        patch("shutil.which", return_value=None),
    ):
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 1
    assert "uv not found" in result.output


def test_update_runs_uv_install() -> None:
    mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with (
        patch("release_status.cli.check_for_update_strict", return_value=("2.0.0", True)),
        patch("shutil.which", return_value="/usr/bin/uv"),
        patch("subprocess.run", return_value=mock_result) as mock_run,
        patch("release_status.cli.clear_update_cache"),
    ):
        result = runner.invoke(app, ["update"])
    assert result.exit_code == 0
    assert "Updated to v2.0.0" in result.output
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "uv"
    assert "release-status" in args
    assert "--no-cache" in args
