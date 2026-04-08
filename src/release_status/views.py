from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.text import Text

from release_status.config import AppConfig, ProjectConfig
from release_status.models import SHORT_SHA_LENGTH, Commit, EnvironmentStatus

# Colors cycle by environment position index, consistent across both views
ENV_COLORS = ["green", "yellow", "blue", "magenta", "cyan", "red"]


def _sha_text(
    short_sha: str, full_sha: str, project: ProjectConfig, fetched: bool = False
) -> Text:
    url = project.repository.provider.commit_url(project.repository.base_url, full_sha)
    text = Text()
    text.append(short_sha, style=f"link {url}")
    if fetched:
        text.append("*", style="yellow")
    return text


def _find_commit(commits: list[Commit], version: str) -> Commit | None:
    for commit in commits:
        if commit.sha_matches(version):
            return commit
    return None


def _render_status_line(
    since_days: int,
    cache_ttl_minutes: int,
    branch: str,
    has_fetched: bool,
    console: Console,
) -> None:
    cache_info = f"{cache_ttl_minutes}m" if cache_ttl_minutes > 0 else "disabled"
    console.print(
        f"  📅 Since: {since_days} days ago | ⏳ Cache TTL: {cache_info} | 🌿 Branch: {branch}",
        style="dim",
    )
    if has_fetched:
        console.print(
            f"  * fetched individually (older than {since_days} days or on a different branch)",
            style="dim yellow",
        )
    console.print()


def render_commits(
    project: ProjectConfig,
    commits: list[Commit],
    environments: list[EnvironmentStatus],
    since_days: int,
    cache_ttl_minutes: int,
    console: Console | None = None,
) -> None:
    console = console or Console()
    console.print()
    table = Table(title=f"Commits: {project.name}", show_lines=False)
    table.add_column("SHA", style="dim", no_wrap=True)
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Author", style="white", no_wrap=True)
    table.add_column("Message", style="white")
    table.add_column("Deployed", justify="left")

    # Build SHA → env names mapping
    sha_envs: dict[str, list[tuple[str, str, str]]] = {}
    for i, env in enumerate(environments):
        color = ENV_COLORS[i % len(ENV_COLORS)]
        if env.version:
            for commit in commits:
                if commit.sha_matches(env.version):
                    sha_envs.setdefault(commit.sha, []).append((env.name, color, env.url))
                    break

    for commit in commits:
        sha_text = _sha_text(commit.short_sha, commit.sha, project, commit.fetched)
        envs = sha_envs.get(commit.sha, [])
        env_text = Text()
        for j, (ename, ecolor, eurl) in enumerate(envs):
            if j > 0:
                env_text.append(" ")
            env_text.append(f" {ename} ", style=f"bold white on {ecolor} link {eurl}")

        table.add_row(
            sha_text,
            commit.date.strftime("%Y-%m-%d"),
            commit.author,
            commit.message[:60],
            env_text,
        )

    console.print(table)

    for env in environments:
        if env.error:
            console.print(
                f"  [red]ERROR[/red] {env.name}: {env.error} (url: {env.url})"
            )

    _render_status_line(since_days, cache_ttl_minutes, project.repository.branch, any(c.fetched for c in commits), console)


def render_environments(
    project: ProjectConfig,
    commits: list[Commit],
    environments: list[EnvironmentStatus],
    since_days: int,
    cache_ttl_minutes: int,
    console: Console | None = None,
) -> None:
    console = console or Console()
    console.print()
    table = Table(title=f"Environments: {project.name}")
    table.add_column("Environment", style="bold")
    table.add_column("SHA", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Commit Info", style="dim", ratio=1)

    for i, env in enumerate(environments):
        color = ENV_COLORS[i % len(ENV_COLORS)]
        env_name = Text()
        env_name.append(f" {env.name} ", style=f"bold white on {color} link {env.url}")
        if env.error:
            error_text = Text(env.error, style="not dim red")
            table.add_row(env_name, "---", Text("ERROR", style="bold red"), error_text)
        elif env.version:
            matching = _find_commit(commits, env.version)
            fetched = matching.fetched if matching else False
            sha_display = _sha_text(
                env.version[:SHORT_SHA_LENGTH], env.version, project, fetched
            )
            commit_info = ""
            if matching:
                commit_info = (
                    f"{matching.date.strftime('%Y-%m-%d')} {matching.message}"
                )
            table.add_row(env_name, sha_display, Text("OK", style="bold green"), commit_info)

    console.print(table)

    _render_status_line(since_days, cache_ttl_minutes, project.repository.branch, any(c.fetched for c in commits), console)


def render_projects(config: AppConfig, console: Console | None = None) -> None:
    console = console or Console()
    console.print()
    table = Table(title="Configured Projects")
    table.add_column("Project", style="bold")
    table.add_column("Provider", style="cyan")
    table.add_column("Branch", style="green")
    table.add_column("Environments", style="yellow")

    for p in config.projects:
        env_names = ", ".join(e.name for e in p.environments)
        table.add_row(
            p.name,
            p.repository.provider.type,
            p.repository.branch,
            env_names,
        )
    console.print(table)
    console.print()
