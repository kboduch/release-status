from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal
from datetime import timedelta
from urllib.parse import quote_plus, urlparse

from pydantic import BaseModel, Field, model_validator

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "release-status" / "config.json"
CONFIG_ENV_VAR = "RELEASE_STATUS_CONFIG"


# --- Provider types ---


class _GitHubProvider(BaseModel):
    def commit_url(self, repo_base_url: str, sha: str) -> str:
        return f"{repo_base_url}/commit/{sha}"


class _GitLabProvider(BaseModel):
    def commit_url(self, repo_base_url: str, sha: str) -> str:
        return f"{repo_base_url}/-/commit/{sha}"


class GitHubCliProvider(_GitHubProvider):
    type: Literal["github-cli"]
    cli_tool: str = "gh"


class GitLabCliProvider(_GitLabProvider):
    type: Literal["gitlab-cli"]
    cli_tool: str = "glab"


class GitHubApiProvider(_GitHubProvider):
    type: Literal["github-api"]
    token_env: str


class GitLabApiProvider(_GitLabProvider):
    type: Literal["gitlab-api"]
    token_env: str


Provider = Annotated[
    GitHubCliProvider | GitLabCliProvider | GitHubApiProvider | GitLabApiProvider,
    Field(discriminator="type"),
]


# --- Source types ---


class JsonSource(BaseModel):
    type: Literal["json"]
    fields: dict[str, str]

    @model_validator(mode="after")
    def validate_fields(self) -> JsonSource:
        if "version" not in self.fields:
            raise ValueError("'fields' must contain a 'version' key")
        return self


class RegexSource(BaseModel):
    type: Literal["regex"]
    pattern: str
    fields: dict[str, str]

    @model_validator(mode="after")
    def validate_pattern_and_fields(self) -> RegexSource:
        if "version" not in self.fields:
            raise ValueError("'fields' must contain a 'version' key")
        try:
            compiled = re.compile(self.pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e
        group_names = set(compiled.groupindex.keys())
        for field_name, group_name in self.fields.items():
            if group_name not in group_names:
                raise ValueError(
                    f"Field '{field_name}' references regex group '{group_name}' "
                    f"which does not exist. Available groups: {sorted(group_names)}"
                )
        return self


Source = Annotated[
    JsonSource | RegexSource,
    Field(discriminator="type"),
]


# --- Environment ---


class EnvironmentConfig(BaseModel):
    name: str
    url: str
    source: Source


# --- Repository ---


class RepositoryConfig(BaseModel):
    url: str
    branch: str
    provider: Provider

    @property
    def base_url(self) -> str:
        """Normalized URL without trailing slash or .git suffix."""
        return self.url.rstrip("/").removesuffix(".git")

    @property
    def repo_path(self) -> str:
        """Extracted owner/repo path for API calls."""
        parsed = urlparse(self.url)
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return path

    @property
    def repo_path_encoded(self) -> str:
        """URL-encoded repo path for GitLab API."""
        return quote_plus(self.repo_path)



# --- Project ---


class ProjectConfig(BaseModel):
    name: str
    repository: RepositoryConfig
    environments: list[EnvironmentConfig]


# --- Root config ---


def parse_duration(value: str) -> timedelta:
    """Parse duration string like '30s', '5m', '1h' into timedelta."""
    match = re.match(r"^(\d+)(s|m|h)$", value)
    if not match:
        raise ValueError(f"Invalid duration: '{value}'. Use format like '30s', '5m', '1h'")
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return timedelta(seconds=amount)
    elif unit == "m":
        return timedelta(minutes=amount)
    else:
        return timedelta(hours=amount)


class AppConfig(BaseModel):
    cache_dir: Path
    git_cache_ttl: str
    env_cache_ttl: str
    since_days: int
    projects: list[ProjectConfig]

    @model_validator(mode="after")
    def validate_ttls(self) -> AppConfig:
        parse_duration(self.git_cache_ttl)
        parse_duration(self.env_cache_ttl)
        return self


# --- Loading ---


def resolve_config_path(cli_override: Path | None = None) -> Path:
    if cli_override:
        return cli_override
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_CONFIG_PATH


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = json.loads(path.read_text())
    return AppConfig.model_validate(raw)


def generate_schema() -> dict[str, object]:
    return AppConfig.model_json_schema()
