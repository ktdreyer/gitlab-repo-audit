# gitlab-repo-audit specification

## Purpose

Classify all repositories under a GitLab group by type (code, PyPI index, wheel cache, mirror, archived) and generate a report. Uses only the group listing API — no per-project API calls — so it completes in minutes even for groups with thousands of repos.

## CLI

Entry point: `gitlab-repo-audit`

### `gitlab-repo-audit index <group-path>`

List all projects in a GitLab group and store metadata in SQLite.

**Arguments:**

| Argument | Description |
|---|---|
| `group_path` | Full path to a GitLab group (e.g. `redhat/rhel-ai`) |

**Options:**

| Option | Default | Description |
|---|---|---|
| `--token`, `-t` | `$GITLAB_TOKEN` | GitLab API personal access token |
| `--url`, `-u` | `https://gitlab.com` | GitLab instance URL |
| `--db` | `~/.cache/gitlab-repo-audit/repos.db` | SQLite database path |
| `--verbose`, `-v` | off | Debug logging to stderr |
| `--quiet`, `-q` | off | Suppress all non-error output |

**Behavior:**

1. Authenticate with the GitLab API using the token.
2. Call `group.projects.list(get_all=True, include_subgroups=True)` to get all project stubs in a single paginated request.
3. Skip projects with `deletion_scheduled` in their name.
4. Classify each project by path (see Classification).
5. Upsert each project into the `repos` table.
6. Print summary to stderr: repo count, elapsed time, database path.

**Error handling:**

- Network errors: retry up to 3 times with exponential backoff (1s, 2s, 4s, max 60s).
- HTTP 429/5xx: delegated to python-gitlab's built-in `retry_transient_errors`.

### `gitlab-repo-audit report`

Generate a report from the indexed data.

**Options:**

| Option | Default | Description |
|---|---|---|
| `--db` | `~/.cache/gitlab-repo-audit/repos.db` | SQLite database path |
| `--group` | all | Filter output to a single group path |
| `-o`, `--output` | stdout (HTML) | Output file; format detected by extension |
| `--verbose`, `-v` | off | Debug logging to stderr |
| `--quiet`, `-q` | off | Suppress all non-error output |

**Output formats:**

| Extension | Format |
|---|---|
| `.html` | Self-contained HTML with PatternFly v6 styling and Plotly charts |
| `.csv` | Flat CSV with all data columns |
| (stdout) | HTML |

## Classification

Each repo is classified by its path segments and archived status:

| Rule (evaluated in order) | `repo_type` |
|---|---|
| `archived == True` | `archived` |
| Path contains `/indexes/` | `pypi_index` |
| Path contains `/wheels/` | `wheel_cache` |
| Path contains `/mirrors/` | `mirror` |
| Everything else | `code` |

## Data model

### RepoData

All fields come from the group project listing (no per-project API calls).

| Field | Type | Source |
|---|---|---|
| `project_id` | int | GitLab project ID (primary key) |
| `name` | str | Project name |
| `path` | str | Full path (`group/subgroup/project`) |
| `web_url` | str | GitLab web URL |
| `description` | str? | Project description |
| `visibility` | str | `public`, `internal`, or `private` |
| `archived` | bool | Whether the project is archived |
| `default_branch` | str? | Default branch name |
| `last_activity_at` | datetime? | Last activity timestamp (from GitLab) |
| `topics` | list[str] | Project topics/tags |
| `star_count` | int | Number of stars |
| `forks_count` | int | Number of forks |
| `repo_type` | str | Classification (see above) |
| `group_path` | str | Which group path was indexed |
| `indexed_at` | datetime | Timestamp of when this record was last updated |

## Storage

SQLite database with WAL journal mode. One table:

- `repos` — one row per project, keyed by `project_id`.

**Upsert behavior:** Re-indexing overwrites all columns.

**Incremental updates:** Records from previous runs that are no longer in the group are kept (not deleted), allowing detection of moved or removed projects.

## HTML report

Rendered from a Jinja2 template (`templates/report.html`) using PatternFly v6 CSS (via CDN) and Plotly.js charts.

### Summary stats

Five cards showing: Total repos, Code repos, Active code (90d), Stale code (>1y), Archived.

Active and stale counts are scoped to code repos only, because GitLab's `last_activity_at` counts bot activity (package publishes, mirror syncs, CI pipelines) which inflates numbers for non-code repos.

### Charts

1. **Last Activity Distribution** — bar chart bucketing code repos by time since last activity: < 30 days, 30–90 days, 90 days – 1 year, > 1 year, Unknown. Includes annotation explaining why it is scoped to code repos.
2. **Repository Types** — Plotly Sunburst chart with two levels:
   - **Inner ring:** repo type (Code, PyPI index, Wheel cache, Mirror, Archived).
   - **Outer ring:** subgroup within each type. The subgroup is the path segment immediately after the classifying segment (e.g. `vllm-2.20` under `indexes/vllm-2.20/...`, `torch-2.11` under `wheels/torch-2.11/...`). For code and archived repos, the subgroup is the first path segment after `redhat/rhel-ai/` (e.g. `core`, `rhai`).
   - Clicking an inner segment zooms into its children (built-in Plotly Sunburst behavior).

### Interactive filtering

Clicking a segment in the Repository Types sunburst chart filters the repository table below to show only matching repos. Clicking the center of the sunburst (or a "Show all" button) resets the filter. Filtering is client-side JavaScript using Plotly's `plotly_click` event and `data-repo-type` / `data-subgroup` attributes on table rows.

### Repository table

Sortable HTML table with columns: Name (linked), Visibility, Last Activity, Type, Disposition, Dest Org.

Each `<tr>` carries `data-repo-type` and `data-subgroup` attributes for filtering.

Sorting is client-side JavaScript. Archived rows are dimmed. Stale rows (>1y) are highlighted in red.

## CSV report

Same data as the HTML table. One header row, one row per repo.

## Dependencies

| Package | Purpose |
|---|---|
| click | CLI framework |
| python-gitlab | GitLab API client |
| pydantic | Data models with validation and serialization |
| plotly | Interactive chart generation |
| jinja2 | HTML template rendering |

## Testing

Tests use pytest with mocked GitLab API responses. Key test areas:

- **db:** upsert, group_path filtering, boolean/JSON roundtrip.
- **index:** classification logic, stub-to-repo conversion.
- **report:** CSV column correctness, HTML chart presence, summary stats.
- **cli:** help text, missing token/database errors.
