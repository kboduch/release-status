from __future__ import annotations

import pytest
import responses

from release_status.config import (
    GitHubApiProvider,
    GitLabApiProvider,
    RepositoryConfig,
)
from release_status.models import ProviderError
from release_status.providers import GitHubApiCommitProvider, GitLabApiCommitProvider


def _github_repo(url: str = "https://github.com/org/repo.git", branch: str = "main") -> RepositoryConfig:
    return RepositoryConfig(
        url=url,
        branch=branch,
        provider=GitHubApiProvider(type="github-api", token_env="TEST_TOKEN"),
    )


def _gitlab_repo(url: str = "https://gitlab.com/org/repo.git", branch: str = "main") -> RepositoryConfig:
    return RepositoryConfig(
        url=url,
        branch=branch,
        provider=GitLabApiProvider(type="gitlab-api", token_env="TEST_TOKEN"),
    )


def test_repo_path() -> None:
    repo = _github_repo("https://github.com/org/repo.git")
    assert repo.repo_path == "org/repo"


def test_repo_path_with_git_suffix() -> None:
    repo = _github_repo("https://github.com/org/repo.git")
    assert repo.repo_path == "org/repo"


def test_repo_path_gitlab_subgroup() -> None:
    repo = _gitlab_repo("https://gitlab.com/group/subgroup/repo.git")
    assert repo.repo_path == "group/subgroup/repo"
    assert repo.repo_path_encoded == "group%2Fsubgroup%2Frepo"


def test_base_url_normalized() -> None:
    repo = _github_repo()
    assert repo.base_url == "https://github.com/org/repo"


@responses.activate
def test_github_api_fetches_commits() -> None:
    commits_data = [
        {
            "sha": "abc1234567890abcdef1234567890abcdef123456",
            "commit": {
                "message": "Fix bug",
                "author": {
                    "name": "Jan",
                    "date": "2026-04-07T10:00:00Z",
                },
            },
        },
        {
            "sha": "def4567890abcdef1234567890abcdef456789ab",
            "commit": {
                "message": "Add feature\n\nMore details",
                "author": {
                    "name": "Anna",
                    "date": "2026-04-06T09:00:00Z",
                },
            },
        },
    ]
    responses.add(
        responses.GET,
        "https://api.github.com/repos/org/repo/commits",
        json=commits_data,
    )

    provider = GitHubApiCommitProvider(token="test-token")
    commits = provider.fetch_commits(_github_repo(), 30)

    assert len(commits) == 2
    assert commits[0].sha == "abc1234567890abcdef1234567890abcdef123456"
    assert commits[0].short_sha == "abc1234"
    assert commits[0].message == "Fix bug"
    assert commits[0].author == "Jan"
    assert commits[1].message == "Add feature"  # First line only


@responses.activate
def test_github_api_handles_401() -> None:
    responses.add(
        responses.GET,
        "https://api.github.com/repos/org/repo/commits",
        status=401,
        json={"message": "Bad credentials"},
    )

    provider = GitHubApiCommitProvider(token="bad-token")
    with pytest.raises(ProviderError, match="github-api"):
        provider.fetch_commits(_github_repo(), 30)


@responses.activate
def test_gitlab_api_fetches_commits() -> None:
    commits_data = [
        {
            "id": "abc1234567890abcdef1234567890abcdef123456",
            "message": "Fix bug",
            "author_name": "Jan",
            "authored_date": "2026-04-07T10:00:00.000+00:00",
        },
    ]
    responses.add(
        responses.GET,
        "https://gitlab.com/api/v4/projects/org%2Frepo/repository/commits",
        json=commits_data,
    )

    provider = GitLabApiCommitProvider(token="test-token")
    commits = provider.fetch_commits(_gitlab_repo(), 30)

    assert len(commits) == 1
    assert commits[0].short_sha == "abc1234"
    assert commits[0].author == "Jan"


@responses.activate
def test_github_api_pagination() -> None:
    page1 = [
        {
            "sha": f"{'a' * 40}",
            "commit": {
                "message": "commit 1",
                "author": {"name": "Dev", "date": "2026-04-07T10:00:00Z"},
            },
        }
    ]
    page2 = [
        {
            "sha": f"{'b' * 40}",
            "commit": {
                "message": "commit 2",
                "author": {"name": "Dev", "date": "2026-04-06T10:00:00Z"},
            },
        }
    ]

    responses.add(
        responses.GET,
        "https://api.github.com/repos/org/repo/commits",
        json=page1,
        headers={"Link": '<https://api.github.com/repos/org/repo/commits?page=2>; rel="next"'},
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/org/repo/commits",
        json=page2,
    )

    provider = GitHubApiCommitProvider(token="test-token")
    commits = provider.fetch_commits(_github_repo(), 30)
    assert len(commits) == 2
