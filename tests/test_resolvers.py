from __future__ import annotations

import json

import pytest
import responses

from release_status.config import EnvironmentConfig
from release_status.resolvers import resolve_environment


def _make_env_config(
    name: str = "dev",
    url: str = "https://dev.example.com/build.json",
    source: dict | None = None,
) -> EnvironmentConfig:
    if source is None:
        source = {"type": "json", "fields": {"version": "$.version"}}
    return EnvironmentConfig(name=name, url=url, source=source)


@responses.activate
def test_json_resolver_extracts_version() -> None:
    responses.add(
        responses.GET,
        "https://dev.example.com/build.json",
        json={"version": "abc1234", "build": 42},
    )
    env = _make_env_config()
    result = resolve_environment(env)
    assert result.version == "abc1234"
    assert result.error is None


@responses.activate
def test_json_resolver_multiple_fields() -> None:
    responses.add(
        responses.GET,
        "https://dev.example.com/build.json",
        json={"version": "abc1234", "time": "2026-04-07"},
    )
    env = _make_env_config(
        source={
            "type": "json",
            "fields": {"version": "$.version", "commit_time": "$.time"},
        }
    )
    result = resolve_environment(env)
    assert result.fields == {"version": "abc1234", "commit_time": "2026-04-07"}
    assert result.error is None


@responses.activate
def test_json_resolver_missing_field() -> None:
    responses.add(
        responses.GET,
        "https://dev.example.com/build.json",
        json={"build": 42},
    )
    env = _make_env_config()
    result = resolve_environment(env)
    assert result.error is not None
    assert "version" in result.error


@responses.activate
def test_json_resolver_invalid_json() -> None:
    responses.add(
        responses.GET,
        "https://dev.example.com/build.json",
        body="not json",
    )
    env = _make_env_config()
    result = resolve_environment(env)
    assert result.error is not None
    assert "Invalid JSON" in result.error


@responses.activate
def test_regex_resolver_extracts_version() -> None:
    responses.add(
        responses.GET,
        "https://dev.example.com/build.html",
        body="data\tcommit_time\nabc1234def\tpipeline_time",
    )
    env = _make_env_config(
        url="https://dev.example.com/build.html",
        source={
            "type": "regex",
            "pattern": r"(.*)\\t(?P<commit_time>.*)\\n(?P<version>.*)\\t(?P<pipeline_time>.*)",
            "fields": {"version": "version", "commit_time": "commit_time"},
        },
    )
    # Use a simpler pattern for the actual test since the response has literal chars
    env = _make_env_config(
        url="https://dev.example.com/build.html",
        source={
            "type": "regex",
            "pattern": r"(.*)\t(?P<commit_time>.*)\n(?P<version>.*)\t(?P<pipeline_time>.*)",
            "fields": {"version": "version", "commit_time": "commit_time"},
        },
    )
    result = resolve_environment(env)
    assert result.version == "abc1234def"
    assert result.fields["commit_time"] == "commit_time"


@responses.activate
def test_regex_resolver_no_match() -> None:
    responses.add(
        responses.GET,
        "https://dev.example.com/build.html",
        body="no matching content here",
    )
    env = _make_env_config(
        url="https://dev.example.com/build.html",
        source={
            "type": "regex",
            "pattern": r"(?P<version>[a-f0-9]{40})",
            "fields": {"version": "version"},
        },
    )
    result = resolve_environment(env)
    assert result.error is not None
    assert "did not match" in result.error


@responses.activate
def test_http_error() -> None:
    responses.add(
        responses.GET,
        "https://dev.example.com/build.json",
        status=500,
    )
    env = _make_env_config()
    result = resolve_environment(env)
    assert result.error is not None
    assert "HTTP" in result.error


@responses.activate
def test_connection_error() -> None:
    responses.add(
        responses.GET,
        "https://dev.example.com/build.json",
        body=ConnectionError("Connection refused"),
    )
    env = _make_env_config()
    result = resolve_environment(env)
    assert result.error is not None
