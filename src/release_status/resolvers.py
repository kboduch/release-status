from __future__ import annotations

import json
import re

import requests
from jsonpath_ng import parse as jsonpath_parse  # type: ignore[import-untyped]

from release_status.config import EnvironmentConfig, JsonSource, RegexSource
from release_status.models import EnvironmentStatus


def resolve_environment(env_config: EnvironmentConfig) -> EnvironmentStatus:
    try:
        resp = requests.get(
            env_config.url,
            headers={"Cache-Control": "no-cache"},
            timeout=10,
        )
        resp.raise_for_status()
    except (requests.RequestException, ConnectionError, OSError) as e:
        return EnvironmentStatus.failure(
            name=env_config.name,
            url=env_config.url,
            error=f"HTTP request failed: {e}",
        )

    body = resp.text
    source = env_config.source

    match source:
        case JsonSource():
            return _resolve_json(env_config.name, env_config.url, source, body)
        case RegexSource():
            return _resolve_regex(env_config.name, env_config.url, source, body)
        case _:
            return EnvironmentStatus.failure(
                name=env_config.name,
                url=env_config.url,
                error=f"Unknown source type: {type(source).__name__}",
            )


def _resolve_json(
    name: str, url: str, source: JsonSource, body: str
) -> EnvironmentStatus:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return EnvironmentStatus.failure(
            name=name, url=url, error=f"Invalid JSON response: {e}"
        )

    extracted: dict[str, str] = {}
    for field_name, json_path in source.fields.items():
        expr = jsonpath_parse(json_path)
        matches = expr.find(data)
        if not matches:
            return EnvironmentStatus.failure(
                name=name,
                url=url,
                error=f"Field '{field_name}' not found via JSONPath '{json_path}'",
            )
        extracted[field_name] = str(matches[0].value)

    return EnvironmentStatus.success(name=name, url=url, fields=extracted)


def _resolve_regex(
    name: str, url: str, source: RegexSource, body: str
) -> EnvironmentStatus:
    match = re.search(source.pattern, body)
    if not match:
        return EnvironmentStatus.failure(
            name=name, url=url, error=f"Regex pattern did not match response body"
        )

    extracted: dict[str, str] = {}
    for field_name, group_name in source.fields.items():
        value = match.group(group_name)
        if value is None:
            return EnvironmentStatus.failure(
                name=name,
                url=url,
                error=f"Field '{field_name}': regex group '{group_name}' matched but is None",
            )
        extracted[field_name] = value

    return EnvironmentStatus.success(name=name, url=url, fields=extracted)
