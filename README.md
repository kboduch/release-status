# release-status

CLI tool that shows which commit is deployed to which environment across multiple projects.

Fetches commit history from GitHub/GitLab and checks public build endpoints to display two views:
- **Commits view** -- recent commits annotated with environment names where they're deployed
- **Environments view** -- each environment with its current deployed SHA and commit info

SHAs in the output are clickable links to the commit in the repository (in terminals that support OSC 8 hyperlinks).

## Installation

Requires Python 3.13+.

```bash
# Install globally via uv
uv tool install git+https://github.com/<user>/project_release_status

# Uninstall
uv tool uninstall release-status

# Or run from the cloned repo (development)
uv sync
uv run release-status --help
```

## Usage

```bash
# Create a starter config file (default: ~/.config/release-status/config.json)
release-status init

# Or specify a custom path
release-status --config ./my-config.json init

# List configured projects
release-status projects

# Validate config and check CLI tools / env vars
release-status check

# Show commits with environment deployment markers
release-status commits MyProject

# Project names with spaces need quotes
release-status commits "My App"

# Show environment status
release-status envs MyProject

# Print JSON Schema for config validation
release-status schema

# Clear cached data
release-status clear-cache
```

### Global flags

Place these **before** the subcommand:

```bash
release-status --config path/to/config.json commits MyProject
release-status --no-cache envs MyProject
release-status --since 60 commits MyProject   # look back 60 days instead of default 30
```

| Flag | Description |
|------|-------------|
| `--config`, `-c` | Path to config file |
| `--no-cache` | Bypass cache for this run |
| `--since` | Override days to look back for commits (default from config) |

### Views

**`commits`** — recent commits with deployment markers:

| Column | Description |
|--------|-------------|
| SHA | Commit hash, clickable link to the commit in the repository |
| Date | Commit date |
| Author | Commit author |
| Message | First line of commit message |
| Deployed | Colored environment badges showing which environments have this commit deployed. Each badge is a clickable link to the environment's build URL |

If an environment has a fetch error, it's shown below the table.

**`envs`** — environment deployment status:

| Column | Description |
|--------|-------------|
| Environment | Colored badge with environment name, clickable link to the build URL |
| SHA | Deployed commit hash, clickable link to the commit in the repository |
| Status | `OK` if version was extracted successfully, `ERROR` if the fetch or extraction failed |
| Commit Info | Commit date and message when status is `OK`. Error details in red when status is `ERROR` |

If a deployed commit is not in the commit history (older than `since_days` or on a different branch), it's fetched individually. These commits are marked with `*` next to the SHA in both views, with a legend shown below the table.

Both views show a status line below the table with the `since_days` value and cache TTL.

### Shell completion

Tab completion works for commands, options, and project names from your config.

```bash
# Print the completion script (zsh/bash/fish)
release-status --show-completion

# Or install it directly into your shell profile
release-status --install-completion
```

With `--show-completion` you can place the script wherever you prefer.
`--install-completion` auto-detects the right location (e.g. `~/.zfunc/` for zsh). Restart the terminal after installing.

## Configuration

Default location: `~/.config/release-status/config.json`

Override with `--config <path>` or `RELEASE_STATUS_CONFIG` environment variable.

Repository URL should be the HTTPS clone URL (e.g. `https://github.com/org/repo.git`), not SSH.

### Example

```json
{
  "cache_dir": "~/.cache/release-status",
  "cache_ttl_minutes": 5,
  "since_days": 180,
  "projects": [
    {
      "name": "MyApp",
      "repository": {
        "url": "https://github.com/org/myapp.git",
        "branch": "main",
        "provider": { "type": "github-cli" }
      },
      "environments": [
        {
          "name": "dev",
          "url": "https://dev.myapp.com/build.json",
          "source": {
            "type": "json",
            "fields": { "version": "$.version" }
          }
        },
        {
          "name": "prod",
          "url": "https://prod.myapp.com/build.json",
          "source": {
            "type": "json",
            "fields": { "version": "$.version" }
          }
        }
      ]
    }
  ]
}
```

### Repository providers

#### CLI providers

| Type | CLI tool | Auth |
|------|----------|------|
| `github-cli` | [`gh`](https://cli.github.com/) | Uses `gh`'s own auth session (`gh auth login`) |
| `gitlab-cli` | [`glab`](https://gitlab.com/gitlab-org/cli) | Uses `glab`'s own auth session (`glab auth login`) |

CLI providers call `gh api` / `glab api` under the hood to fetch commit history. Authentication is handled by the CLI tool itself — no tokens needed in config. Make sure you're logged in (`gh auth login` / `glab auth login`) and have access to the repository. Verify with `gh auth status` / `glab auth status`.

#### API providers

| Type | Token scope | How to create |
|------|-------------|---------------|
| `github-api` | `repo` | https://github.com/settings/tokens → Generate new token (classic) |
| `gitlab-api` | `read_api` | https://gitlab.com/-/user_settings/personal_access_tokens → Add new token |

API providers reference an environment variable name (not the token itself):

```json
{
  "type": "gitlab-api",
  "token_env": "MY_GITLAB_TOKEN"
}
```

Set the token in your shell profile:

```bash
export MY_GITLAB_TOKEN="glpat-xxxxxxxxxxxx"
```

Note: avoid using `GITLAB_TOKEN` as the env var name — `glab` CLI reads it and it will override `glab`'s own auth session.

### Environment sources

Each environment has a public URL that returns the deployed commit SHA. Two extraction methods:

**JSON** -- extract via JSONPath.

Example response from `https://dev.example.com/build.json`:
```json
{"version": "abc1234", "build": 42}
```

Source config:
```json
{
  "type": "json",
  "fields": { "version": "$.version" }
}
```

**Regex** -- extract via named groups from HTML/text.

Example response from `https://dev.example.com/build.html`:
```
some_data	2026-04-07T10:00:00Z
abc1234	2026-04-07T10:05:00Z
```

Source config:
```json
{
  "type": "regex",
  "pattern": "(.*)\\t(?P<commit_time>.*)\\n(?P<version>.*)\\t(?P<pipeline_time>.*)",
  "fields": {
    "version": "version",
    "pipeline_time": "pipeline_time"
  }
}
```

The `fields` map is `{ our_field_name: extraction_path }`:
- For JSON sources: values are JSONPath expressions (e.g. `$.version`)
- For regex sources: values are regex named group names (e.g. `version`)

At minimum, `fields` must contain `"version"` (the commit SHA). You can add extra fields like `pipeline_time` -- every field you configure must be found in the response, otherwise the tool will show an extraction error for that environment.

### Caching

Responses are cached for 5 minutes by default. Use `--no-cache` to bypass or `release-status clear-cache` to wipe.

Both cache directory and TTL are configurable:

```json
{
  "cache_dir": "/tmp/my-release-cache",
  "cache_ttl_minutes": 5,
  "since_days": 180,
  "projects": [...]
}
```

## Development

```bash
uv sync
uv run pytest -v
uv run mypy src/
uv run release-status --config config.example.json check
```

After making changes, reinstall the global tool with a fresh build:

```bash
uv tool install . --force --reinstall
```

`--force` alone may use a cached wheel. `--reinstall` forces a rebuild.
