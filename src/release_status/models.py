from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

SHORT_SHA_LENGTH = 7


@dataclass(frozen=True)
class Commit:
    sha: str
    short_sha: str
    message: str
    author: str
    date: datetime

    @classmethod
    def from_raw(cls, sha: str, message: str, author: str, date: datetime) -> Commit:
        return cls(
            sha=sha,
            short_sha=sha[:SHORT_SHA_LENGTH],
            message=message.split("\n", 1)[0],
            author=author,
            date=date,
        )

    def sha_matches(self, version: str) -> bool:
        return self.sha.startswith(version) or version.startswith(self.short_sha)


@dataclass(frozen=True)
class EnvironmentStatus:
    name: str
    fields: dict[str, str]
    error: str | None
    url: str

    @property
    def version(self) -> str | None:
        return self.fields.get("version")

    @classmethod
    def success(cls, name: str, url: str, fields: dict[str, str]) -> EnvironmentStatus:
        return cls(name=name, fields=fields, error=None, url=url)

    @classmethod
    def failure(cls, name: str, url: str, error: str) -> EnvironmentStatus:
        return cls(name=name, fields={}, error=error, url=url)


class ReleaseStatusError(Exception):
    pass


class ProviderError(ReleaseStatusError):
    def __init__(self, message: str, provider_type: str):
        self.provider_type = provider_type
        super().__init__(f"[{provider_type}] {message}")


class ToolNotFoundError(ReleaseStatusError):
    def __init__(self, tool: str):
        self.tool = tool
        super().__init__(f"CLI tool '{tool}' not found. Install it first.")
