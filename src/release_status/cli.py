from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer
from pydantic import ValidationError
from rich.console import Console

from release_status.cache import Cache
from release_status.config import (
    AppConfig,
    ProjectConfig,
    generate_schema,
    load_config,
    resolve_config_path,
)
from release_status.models import Commit, EnvironmentStatus, ProviderError, ToolNotFoundError
from release_status.providers import check_cli_tools, get_provider
from release_status.resolvers import resolve_environment
from release_status.views import render_commits, render_environments, render_projects

app = typer.Typer(
    name="release-status",
    help="Show release/deployment status across multiple projects.",
    no_args_is_help=True,
)
console = Console()


class _State:
    config_path: Path | None = None
    no_cache: bool = False
    since_days: int | None = None
    branch: str | None = None


_state = _State()


def _complete_project(incomplete: str) -> list[str]:
    try:
        path = resolve_config_path(_state.config_path)
        config = load_config(path)
        return [p.name for p in config.projects if p.name.lower().startswith(incomplete.lower())]
    except Exception:
        return []


@app.callback()
def main(
    config: Annotated[
        Optional[Path], typer.Option("--config", "-c", help="Path to config file")
    ] = None,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Disable cache")
    ] = False,
    since: Annotated[
        Optional[int], typer.Option("--since", help="Override days to look back for commits")
    ] = None,
    branch: Annotated[
        Optional[str], typer.Option("--branch", "-b", help="Override branch to fetch commits from")
    ] = None,
) -> None:
    """Release Status — deployment tracking across projects."""
    _state.config_path = config
    _state.no_cache = no_cache
    _state.since_days = since
    _state.branch = branch


@app.command()
def commits(
    project: Annotated[str, typer.Argument(help="Project name", autocompletion=_complete_project)],
) -> None:
    """Show recent commits with environment deployment markers."""
    cfg = _load_config()
    proj = _apply_branch_override(_find_project(cfg, project))
    cache = _make_cache(cfg)
    since = _since_days(cfg)
    cache_ttl = 0 if _state.no_cache else cfg.cache_ttl_minutes

    with console.status("Fetching commits..."):
        commit_list = _fetch_commits(proj, cache, since)

    with console.status("Checking environments..."):
        env_statuses = _fetch_environments(proj, cache)

    _fetch_missing_commits(commit_list, env_statuses, proj, cache)
    render_commits(proj, commit_list, env_statuses, since, cache_ttl, console)


@app.command()
def envs(
    project: Annotated[str, typer.Argument(help="Project name", autocompletion=_complete_project)],
) -> None:
    """Show environment deployment status."""
    cfg = _load_config()
    proj = _apply_branch_override(_find_project(cfg, project))
    cache = _make_cache(cfg)
    since = _since_days(cfg)
    cache_ttl = 0 if _state.no_cache else cfg.cache_ttl_minutes

    with console.status("Fetching data..."):
        commit_list = _fetch_commits(proj, cache, since)
        env_statuses = _fetch_environments(proj, cache)

    _fetch_missing_commits(commit_list, env_statuses, proj, cache)
    render_environments(proj, commit_list, env_statuses, since, cache_ttl, console)


@app.command()
def projects() -> None:
    """List all configured projects."""
    cfg = _load_config()
    render_projects(cfg, console)


@app.command()
def check() -> None:
    """Validate configuration and check CLI tool availability."""
    path = resolve_config_path(_state.config_path)
    cfg = _load_config()
    console.print(f"[green]Config is valid:[/green] {path}")
    console.print(f"  Projects: {len(cfg.projects)}")

    has_issues = False
    for proj in cfg.projects:
        issue = check_cli_tools(proj.repository.provider)
        if issue:
            console.print(f"  [red]WARN[/red] {proj.name}: {issue}")
            has_issues = True
        else:
            console.print(f"  [green]OK[/green] {proj.name}: {proj.repository.provider.type}")

    if not has_issues:
        console.print("[green]All checks passed.[/green]")


@app.command()
def schema() -> None:
    """Print JSON Schema for the config file."""
    console.print(json.dumps(generate_schema(), indent=2))


@app.command(name="clear-cache")
def clear_cache() -> None:
    """Clear all cached data."""
    cfg = _load_config()
    count = _make_cache(cfg).clear()
    console.print(f"Cleared {count} cache entries.")


@app.command()
def init() -> None:
    """Create a starter config file."""
    path = resolve_config_path(_state.config_path)
    if path.exists():
        console.print(f"Config already exists: {path}")
        raise typer.Exit(1)

    starter = {
        "cache_dir": str(Path.home() / ".cache" / "release-status"),
        "cache_ttl_minutes": 5,
        "since_days": 180,
        "projects": [
            {
                "name": "my-project",
                "repository": {
                    "url": "https://github.com/org/repo",
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
                    }
                ],
            }
        ]
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(starter, indent=2) + "\n")
    console.print(f"Created config: {path}")
    console.print("Edit it with your projects, then run: release-status check")


# --- Helpers ---


def _load_config() -> AppConfig:
    path = resolve_config_path(_state.config_path)
    try:
        return load_config(path)
    except FileNotFoundError:
        console.print(f"[red]Config file not found:[/red] {path}")
        console.print(
            f"Create one with: release-status init"
        )
        raise typer.Exit(1)
    except ValidationError as e:
        console.print(f"[red]Config validation error:[/red] {path}")
        for err in e.errors():
            loc = " → ".join(str(x) for x in err["loc"])
            console.print(f"  {loc}: {err['msg']}")
        raise typer.Exit(1)


def _find_project(config: AppConfig, name: str) -> ProjectConfig:
    for p in config.projects:
        if p.name.lower() == name.lower():
            return p
    available = ", ".join(p.name for p in config.projects)
    console.print(f"[red]Project '{name}' not found.[/red] Available: {available}")
    raise typer.Exit(1)


def _make_cache(config: AppConfig) -> Cache:
    cache = Cache(
        cache_dir=config.cache_dir,
        ttl=timedelta(minutes=config.cache_ttl_minutes),
    )
    cache.enabled = not _state.no_cache and config.cache_ttl_minutes > 0
    return cache


def _apply_branch_override(proj: ProjectConfig) -> ProjectConfig:
    if _state.branch:
        repo = proj.repository.model_copy(update={"branch": _state.branch})
        return proj.model_copy(update={"repository": repo})
    return proj


def _since_days(config: AppConfig) -> int:
    return _state.since_days if _state.since_days is not None else config.since_days


def _cache_key_commits(proj: ProjectConfig, since_days: int) -> str:
    return (
        f"commits:{proj.repository.provider.type}"
        f":{proj.repository.url}:{proj.repository.branch}"
        f":{since_days}"
    )


def _fetch_commits(proj: ProjectConfig, cache: Cache, since_days: int) -> list[Commit]:
    key = _cache_key_commits(proj, since_days)
    cached = cache.get(key)
    if cached is not None:
        return [
            Commit(
                sha=c["sha"],
                short_sha=c["short_sha"],
                message=c["message"],
                author=c["author"],
                date=datetime.fromisoformat(c["date"]),
            )
            for c in cached
        ]

    try:
        provider = get_provider(proj.repository.provider)
        commits = provider.fetch_commits(proj.repository, since_days)
    except (ProviderError, ToolNotFoundError) as e:
        console.print(f"[red]Error fetching commits:[/red] {e}")
        raise typer.Exit(1)

    cache.set(
        key,
        [
            {
                "sha": c.sha,
                "short_sha": c.short_sha,
                "message": c.message,
                "author": c.author,
                "date": c.date.isoformat(),
            }
            for c in commits
        ],
    )
    return commits


def _fetch_environments(
    proj: ProjectConfig, cache: Cache
) -> list[EnvironmentStatus]:
    results: list[EnvironmentStatus] = []
    for env_config in proj.environments:
        key = f"env:{env_config.url}"
        cached = cache.get(key)
        if cached is not None:
            results.append(
                EnvironmentStatus(
                    name=cached["name"],
                    fields=cached["fields"],
                    error=cached["error"],
                    url=cached["url"],
                )
            )
            continue

        status = resolve_environment(env_config)
        cache.set(
            key,
            {
                "name": status.name,
                "fields": status.fields,
                "error": status.error,
                "url": status.url,
            },
        )
        results.append(status)

    return results


def _fetch_missing_commits(
    commit_list: list[Commit],
    env_statuses: list[EnvironmentStatus],
    proj: ProjectConfig,
    cache: Cache,
) -> None:
    """Fetch individual commits for deployed SHAs not in the commit list."""
    for env in env_statuses:
        if not env.version or any(c.sha_matches(env.version) for c in commit_list):
            continue

        key = f"commit:{env.version}"
        cached = cache.get(key)
        if cached is not None:
            commit_list.append(
                Commit(
                    sha=cached["sha"],
                    short_sha=cached["short_sha"],
                    message=cached["message"],
                    author=cached["author"],
                    date=datetime.fromisoformat(cached["date"]),
                    fetched=True,
                )
            )
            continue

        try:
            provider = get_provider(proj.repository.provider)
            commit = provider.fetch_commit(proj.repository, env.version)
        except (ProviderError, ToolNotFoundError):
            continue

        cache.set(
            key,
            {
                "sha": commit.sha,
                "short_sha": commit.short_sha,
                "message": commit.message,
                "author": commit.author,
                "date": commit.date.isoformat(),
            },
        )
        commit_list.append(
            Commit.from_raw(
                sha=commit.sha,
                message=commit.message,
                author=commit.author,
                date=commit.date,
                fetched=True,
            )
        )
