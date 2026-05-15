*Warning: lightly read, heavily AI generated.*

# GitLab Repo Audit

A command-line tool to inventory and audit GitLab repositories for migration planning. Indexes repo metadata into SQLite and generates HTML reports with interactive Plotly charts.

## Features

- Recursively index all projects in a GitLab group
- Parallel data collection with configurable workers
- SQLite storage with incremental updates
- Interactive HTML reports with Plotly charts
- CSV export for spreadsheet workflows
- Detects package-index-only repos (no real source code)
- Preserves manual decision annotations across re-indexes

## Installation

```bash
uv pip install -e .
```

## Usage

Set your GitLab token:

```bash
export GITLAB_TOKEN=$(glab config get --host gitlab.com token)
```

### Index repos

```bash
gitlab-repo-audit index redhat/rhel-ai/ci-cd
```

### Generate report

```bash
# HTML with interactive charts
gitlab-repo-audit report -o repos.html

# CSV for spreadsheet work
gitlab-repo-audit report -o repos.csv
```

### Common options

- `--token` / `-t` — GitLab API token (defaults to `GITLAB_TOKEN` env var)
- `--url` / `-u` — GitLab instance URL (defaults to `https://gitlab.com`)
- `--db` — SQLite database path (defaults to `~/.cache/gitlab-repo-audit/repos.db`)
- `--verbose` / `-v` — Enable debug output
- `--quiet` / `-q` — Quiet mode

## Development

```bash
uv pip install -e ".[dev]"
hatch run test
hatch run lint
```

## License

MIT
