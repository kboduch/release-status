from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Protocol
from urllib.parse import urlparse

import requests

from release_status.config import (
    GitHubApiProvider,
    GitHubCliProvider,
    GitLabApiProvider,
    GitLabCliProvider,
    Provider,
    RepositoryConfig,
)
from release_status.models import Commit, ProviderError, ToolNotFoundError


class CommitProvider(Protocol):
    def fetch_commits(self, repo: RepositoryConfig, since_days: int) -> list[Commit]:
        ...

    def fetch_commit(self, repo: RepositoryConfig, sha: str) -> Commit:
        ...


def _since_iso(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_date(date_str: str) -> datetime:
    date_str = date_str.replace("Z", "+00:00")
    return datetime.fromisoformat(date_str)


# --- GitHub CLI ---


class GitHubCliCommitProvider:
    def fetch_commits(self, repo: RepositoryConfig, since_days: int) -> list[Commit]:
        since = _since_iso(since_days)
        cmd = [
            "gh", "api",
            f"repos/{repo.repo_path}/commits?sha={repo.branch}&since={since}&per_page=100",
            "--paginate",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=30
            )
        except subprocess.CalledProcessError as e:
            raise ProviderError(
                f"gh api failed (exit {e.returncode}): {e.stderr.strip()}",
                "github-cli",
            ) from e
        except subprocess.TimeoutExpired as e:
            raise ProviderError("gh api timed out", "github-cli") from e

        data = json.loads(result.stdout)
        return [
            Commit.from_raw(
                sha=item["sha"],
                message=item["commit"]["message"],
                author=item["commit"]["author"]["name"],
                date=_parse_iso_date(item["commit"]["author"]["date"]),
            )
            for item in data
        ]


    def fetch_commit(self, repo: RepositoryConfig, sha: str) -> Commit:
        cmd = ["gh", "api", f"repos/{repo.repo_path}/commits/{sha}"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=30
            )
        except subprocess.CalledProcessError as e:
            raise ProviderError(
                f"gh api failed (exit {e.returncode}): {e.stderr.strip()}",
                "github-cli",
            ) from e
        except subprocess.TimeoutExpired as e:
            raise ProviderError("gh api timed out", "github-cli") from e

        item = json.loads(result.stdout)
        return Commit.from_raw(
            sha=item["sha"],
            message=item["commit"]["message"],
            author=item["commit"]["author"]["name"],
            date=_parse_iso_date(item["commit"]["author"]["date"]),
        )


# --- GitLab CLI ---


class GitLabCliCommitProvider:
    def fetch_commits(self, repo: RepositoryConfig, since_days: int) -> list[Commit]:
        since = _since_iso(since_days)
        commits: list[Commit] = []
        page = 1

        while True:
            cmd = [
                "glab", "api",
                f"projects/{repo.repo_path_encoded}/repository/commits"
                f"?ref_name={repo.branch}&since={since}&per_page=100&page={page}",
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, check=True, timeout=30
                )
            except subprocess.CalledProcessError as e:
                raise ProviderError(
                    f"glab api failed (exit {e.returncode}): {e.stderr.strip()}",
                    "gitlab-cli",
                ) from e
            except subprocess.TimeoutExpired as e:
                raise ProviderError("glab api timed out", "gitlab-cli") from e

            data = json.loads(result.stdout)
            if not data:
                break

            for item in data:
                commits.append(
                    Commit.from_raw(
                        sha=item["id"],
                        message=item["message"],
                        author=item["author_name"],
                        date=_parse_iso_date(item["authored_date"]),
                    )
                )

            if len(data) < 100:
                break
            page += 1

        return commits

    def fetch_commit(self, repo: RepositoryConfig, sha: str) -> Commit:
        cmd = [
            "glab", "api",
            f"projects/{repo.repo_path_encoded}/repository/commits/{sha}",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=30
            )
        except subprocess.CalledProcessError as e:
            raise ProviderError(
                f"glab api failed (exit {e.returncode}): {e.stderr.strip()}",
                "gitlab-cli",
            ) from e
        except subprocess.TimeoutExpired as e:
            raise ProviderError("glab api timed out", "gitlab-cli") from e

        item = json.loads(result.stdout)
        return Commit.from_raw(
            sha=item["id"],
            message=item["message"],
            author=item["author_name"],
            date=_parse_iso_date(item["authored_date"]),
        )


# --- GitHub API ---


class GitHubApiCommitProvider:
    def __init__(self, token: str) -> None:
        self.token = token

    def fetch_commits(self, repo: RepositoryConfig, since_days: int) -> list[Commit]:
        since = _since_iso(since_days)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }
        commits: list[Commit] = []
        url: str | None = f"https://api.github.com/repos/{repo.repo_path}/commits"
        params: dict[str, str] = {
            "sha": repo.branch,
            "since": since,
            "per_page": "100",
        }

        while url:
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                raise ProviderError(str(e), "github-api") from e

            for item in resp.json():
                commits.append(
                    Commit.from_raw(
                        sha=item["sha"],
                        message=item["commit"]["message"],
                        author=item["commit"]["author"]["name"],
                        date=_parse_iso_date(item["commit"]["author"]["date"]),
                    )
                )

            # Follow pagination via Link header
            url = None
            params = {}
            link = resp.headers.get("Link", "")
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")

        return commits

    def fetch_commit(self, repo: RepositoryConfig, sha: str) -> Commit:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{repo.repo_path}/commits/{sha}",
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise ProviderError(str(e), "github-api") from e

        item = resp.json()
        return Commit.from_raw(
            sha=item["sha"],
            message=item["commit"]["message"],
            author=item["commit"]["author"]["name"],
            date=_parse_iso_date(item["commit"]["author"]["date"]),
        )


# --- GitLab API ---


class GitLabApiCommitProvider:
    def __init__(self, token: str) -> None:
        self.token = token

    def fetch_commits(self, repo: RepositoryConfig, since_days: int) -> list[Commit]:
        since = _since_iso(since_days)
        headers = {"PRIVATE-TOKEN": self.token}
        parsed = urlparse(repo.url)
        api_base = f"{parsed.scheme}://{parsed.hostname}/api/v4"
        commits: list[Commit] = []
        page = 1

        while True:
            url = f"{api_base}/projects/{repo.repo_path_encoded}/repository/commits"
            params = {
                "ref_name": repo.branch,
                "since": since,
                "per_page": "100",
                "page": str(page),
            }
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                raise ProviderError(str(e), "gitlab-api") from e

            data = resp.json()
            if not data:
                break

            for item in data:
                commits.append(
                    Commit.from_raw(
                        sha=item["id"],
                        message=item["message"],
                        author=item["author_name"],
                        date=_parse_iso_date(item["authored_date"]),
                    )
                )

            if len(data) < 100:
                break
            page += 1

        return commits

    def fetch_commit(self, repo: RepositoryConfig, sha: str) -> Commit:
        headers = {"PRIVATE-TOKEN": self.token}
        parsed = urlparse(repo.url)
        api_base = f"{parsed.scheme}://{parsed.hostname}/api/v4"
        try:
            resp = requests.get(
                f"{api_base}/projects/{repo.repo_path_encoded}/repository/commits/{sha}",
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise ProviderError(str(e), "gitlab-api") from e

        item = resp.json()
        return Commit.from_raw(
            sha=item["id"],
            message=item["message"],
            author=item["author_name"],
            date=_parse_iso_date(item["authored_date"]),
        )


# --- Factory ---


_CLI_PROVIDERS: dict[type[GitHubCliProvider | GitLabCliProvider], type[GitHubCliCommitProvider | GitLabCliCommitProvider]] = {
    GitHubCliProvider: GitHubCliCommitProvider,
    GitLabCliProvider: GitLabCliCommitProvider,
}


def _resolve_token(token_env: str, provider_type: str) -> str:
    token = os.environ.get(token_env, "")
    if not token:
        raise ProviderError(
            f"Environment variable '{token_env}' is not set",
            provider_type,
        )
    return token


def get_provider(provider_config: Provider) -> CommitProvider:
    if isinstance(provider_config, (GitHubCliProvider, GitLabCliProvider)):
        if not shutil.which(provider_config.cli_tool):
            raise ToolNotFoundError(provider_config.cli_tool)
        return _CLI_PROVIDERS[type(provider_config)]()

    if isinstance(provider_config, GitHubApiProvider):
        token = _resolve_token(provider_config.token_env, provider_config.type)
        return GitHubApiCommitProvider(token=token)

    if isinstance(provider_config, GitLabApiProvider):
        token = _resolve_token(provider_config.token_env, provider_config.type)
        return GitLabApiCommitProvider(token=token)

    raise ProviderError(f"Unknown provider type: {type(provider_config)}", "unknown")


def check_cli_tools(provider_config: Provider) -> str | None:
    if isinstance(provider_config, (GitHubCliProvider, GitLabCliProvider)):
        if not shutil.which(provider_config.cli_tool):
            return f"CLI tool '{provider_config.cli_tool}' is required but not found in PATH."
        return None

    if isinstance(provider_config, (GitHubApiProvider, GitLabApiProvider)):
        if not os.environ.get(provider_config.token_env):
            return f"Environment variable '{provider_config.token_env}' is not set."
        return None

    return None
