# Release Status CLI

CLI tool that shows which commit is deployed to which environment across multiple projects. Fetches commit history from GitHub/GitLab and checks public build endpoints to correlate deployed SHAs with commits.

## Architecture

```
cli.py          Entry point. Global flags, commands, caching orchestration.
config.py       Pydantic models for JSON config. Discriminated unions for providers/sources.
providers.py    Fetches commit history from GitHub/GitLab (CLI or API).
resolvers.py    Fetches build endpoints and extracts version via JSONPath or regex.
cache.py        File-based cache with TTL. SHA256-hashed keys.
views.py        Rich terminal tables for commits and environments views.
models.py       Frozen dataclasses (Commit, EnvironmentStatus) and exceptions.
version.py      Version check against PyPI. Independent 24h cache.
```

## Data Flow

1. User runs `release-status commits <project>` or `envs <project>`
2. `cli.py` loads config, resolves overrides (`--branch`, `--since`, `--no-cache`)
3. Fetches commit list from git provider (cached)
4. Fetches each environment's build URL, extracts version SHA (cached)
5. For any deployed SHA not in commit list: fetches that single commit individually (marked `fetched=True`)
6. Sorts all commits by date descending
7. Renders table with `views.py`

## Key Design Decisions

### Provider polymorphism via Pydantic models
Provider types (`_GitHubProvider`, `_GitLabProvider`) are Pydantic base classes with `commit_url()` method. Each knows how to build its own commit URL format. CLI providers also have `cli_tool` attribute for tool availability checks. No if/else chains on provider type strings.

### Branch override via model_copy
`--branch` flag doesn't thread through all layers. Instead, `cli.py` creates a modified `ProjectConfig` copy with overridden branch using Pydantic's `model_copy(update=...)`. All downstream code reads `repo.branch` and automatically gets the override. Zero changes needed in providers/cache/views.

### Fetched commits
When a deployed SHA is not in the commit list, it's fetched individually via `provider.fetch_commit(repo, sha)`. Two scenarios cause this:
- **Older than `since_days`**: the commit exists on the configured branch but is outside the time window
- **Different branch**: the environment deploys from a branch other than the configured one (e.g. `dev` deploys from `develop` but config has `branch: main`)

These commits have `fetched=True` and are displayed with `*` marker in both views. The legend below the table explains the marker.

### Cache TTL = 0 disables cache
Instead of a separate "cache enabled" config field, `cache_ttl_minutes: 0` disables caching. `cli.py:_make_cache()` sets `cache.enabled = False` when TTL is 0 or `--no-cache` flag is used. Views show "disabled" in status line when effective TTL is 0.

### Environment source fields map
Each environment has a `source` with a `fields` map: `{ field_name: extraction_path }`. For JSON sources, values are JSONPath expressions (`$.version`). For regex sources, values are named group names (`version`). The `version` field is always required. All configured fields must be found in the response — missing field = error.

### Resolvers never raise
`resolve_environment()` catches all exceptions and returns `EnvironmentStatus.failure()`. One broken environment doesn't block others.

### GitHub API URL
GitHub public API lives at `api.github.com` (different host from `github.com`). This is hardcoded in `GitHubApiCommitProvider`. GitLab API URL is derived from repo URL host: `{scheme}://{hostname}/api/v4`.

### Environment URLs are public
Build endpoints (`build.json`, `build.html`) are public. No auth needed. Requests include `Cache-Control: no-cache` header to bypass CDN caching.

## Config Structure

All fields are required (no hidden defaults):
- `cache_dir`: Path to cache directory
- `cache_ttl_minutes`: Cache TTL in minutes (0 = disabled)
- `since_days`: How many days of commit history to fetch
- `projects[]`: List of projects, each with `repository` and `environments`
- `repository.branch`: Required, no default — user must specify explicitly

Provider auth tokens are referenced by environment variable name (`token_env`), never stored directly. Avoid naming env vars `GITLAB_TOKEN` — `glab` CLI reads it and overrides its own auth.

`release-status init` generates a starter config showcasing every possible provider type and source type. When adding new providers or sources, update the starter config in `cli.py:init()` to include them.

## Conventions

- SHA display: 7 chars (`SHORT_SHA_LENGTH` constant)
- SHA matching: bidirectional — `full_sha.startswith(version)` or `version.startswith(short_sha)`
- Environment colors: cycle through `ENV_COLORS` list by position index
- Links: SHA links to commit in repo, environment badges link to build URL
- Regex sources: pattern must contain named group matching each field value in `fields` map
- Cache keys: `"commits:{provider_type}:{url}:{branch}:{since}"` and `"env:{url}"` and `"commit:{sha}"`

### Version check & self-update
`version.py` checks PyPI JSON API (`/pypi/release-status/json`) for newer versions. Results cached 24h at `~/.cache/release-status/version-check.json` (independent of project config). Fail-safe: any error silently returns None. Version displayed in status line of `commits` and `envs` commands. `release-status update` runs `uv tool install release-status --force --reinstall`.

### Releasing
Run `gh workflow run release.yml -f version=X.Y.Z`. The workflow validates version format, checks it's newer than current, bumps pyproject.toml, commits, tags, builds, publishes to PyPI, and creates a GitHub Release with auto-generated notes. Requires `PYPI_TOKEN` secret in repo settings.

## Development

```bash
uv sync
uv run pytest -v
uv run mypy src/          # strict mode
uv run release-status --config config.example.json check
```

After changes, reinstall global tool: `uv tool install . --force --reinstall`
