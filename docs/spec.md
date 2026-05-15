# gitlab-repo-audit specification

## Purpose

Index GitLab repositories and generate reports for migration planning. Built to support the AIPCC GitLab-to-GitHub migration (AIPCC-15934), starting with the `redhat/rhel-ai/ci-cd` namespace and scaling to all ~2000 repos under `redhat/rhel-ai/*`.

## CLI

Entry point: `gitlab-repo-audit`

### `gitlab-repo-audit index <group-path>`

Recursively discover all projects in a GitLab group and store metadata in SQLite.

**Arguments:**

| Argument | Description |
|---|---|
| `group_path` | Full path to a GitLab group (e.g. `redhat/rhel-ai/ci-cd`) |

**Options:**

| Option | Default | Description |
|---|---|---|
| `--token`, `-t` | `$GITLAB_TOKEN` | GitLab API personal access token |
| `--url`, `-u` | `https://gitlab.com` | GitLab instance URL |
| `--db` | `~/.cache/gitlab-repo-audit/repos.db` | SQLite database path |
| `--workers`, `-w` | `5` | Number of parallel API workers |
| `--verbose`, `-v` | off | Debug logging to stderr |
| `--quiet`, `-q` | off | Suppress all non-error output |

**Behavior:**

1. Authenticate with the GitLab API using the token.
2. List all projects in the group, including subgroups.
3. Skip projects with `deletion_scheduled` in their name.
4. For each project, collect metadata in parallel (see Data Model).
5. Upsert each project into the `repos` table, preserving any manually-set decision columns.
6. Upsert the last 100 merge requests per project into the `merge_requests` table.
7. Print summary to stderr: repo count, MR count, elapsed time, database path.

**Error handling:**

- Network errors: retry up to 3 times with exponential backoff (1s, 2s, 4s, max 60s).
- HTTP 429/5xx: delegated to python-gitlab's built-in `retry_transient_errors`.
- Individual project failures: log a warning and continue indexing remaining projects.

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
| `.csv` | Flat CSV with all data columns plus blank decision columns |
| (stdout) | HTML |

## Data model

### RepoData (indexed from API)

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
| `last_commit_date` | datetime? | Last commit on the default branch |
| `open_mr_count` | int? | Number of currently open merge requests |
| `ci_config_present` | bool? | Whether `.gitlab-ci.yml` exists on the default branch |
| `topics` | list[str] | Project topics/tags |
| `star_count` | int | Number of stars |
| `forks_count` | int | Number of forks |
| `repo_size_kb` | int? | Repository size from project statistics |
| `languages` | dict[str, float] | Language breakdown (language → percentage) |
| `contributors_last_90d` | int? | Unique commit authors in the last 90 days |
| `is_package_index` | bool | Heuristic: repo tree is empty or only README, with packages in the registry |
| `package_count` | int | Number of packages in the GitLab package registry |
| `group_path` | str | Which group path was indexed (supports multiple index runs) |
| `indexed_at` | datetime | Timestamp of when this record was last updated |

### RepoRecord (extends RepoData with decision columns)

These columns are preserved across re-indexes. Only humans fill them in.

| Field | Type | Values |
|---|---|---|
| `disposition` | str? | `migrate`, `archive`, `merge`, `delete`, `transfer_ownership` |
| `visibility_decision` | str? | `public`, `private`, `internal` |
| `destination_org` | str? | `opendatahub-io`, `red-hat-data-services`, `aipcc-cicd` |
| `ci_runner_deps` | str? | Free text (GPU, cloud provider, architecture) |
| `content_sensitivity` | str? | Free text (secrets, internal tooling, customer data) |
| `dependencies` | str? | Free text (downstream consumers) |
| `priority` | int? | Migration order (1 = first) |
| `notes` | str? | Free text |

### MergeRequestData

| Field | Type | Source |
|---|---|---|
| `project_id` | int | Parent project ID |
| `mr_iid` | int | MR internal ID (unique per project) |
| `title` | str | MR title |
| `author` | str? | Author username |
| `state` | str | `opened`, `merged`, `closed` |
| `created_at` | datetime? | When the MR was created |
| `merged_at` | datetime? | When the MR was merged (null if not merged) |
| `web_url` | str | GitLab web URL |

## Storage

SQLite database with WAL journal mode. Two tables:

- `repos` — one row per project, keyed by `project_id`.
- `merge_requests` — one row per MR, keyed by `(project_id, mr_iid)`.

**Upsert behavior:** Re-indexing overwrites all API-sourced columns but preserves manual decision columns (`disposition`, `visibility_decision`, `destination_org`, `ci_runner_deps`, `content_sensitivity`, `dependencies`, `priority`, `notes`).

**Incremental updates:** Records from previous runs that are no longer in the group are kept (not deleted), allowing detection of moved or removed projects.

## Package index detection

A project is classified as a package index when:

1. Its GitLab package registry has at least one package, AND
2. Its repository tree is empty, or contains only files from the set: `README.md`, `README`, `README.txt`, `.gitignore`, `LICENSE`, `LICENSE.md`.

## HTML report

Rendered from a Jinja2 template (`templates/report.html`) using PatternFly v6 CSS (via CDN) and Plotly.js charts.

### Summary stats

Six cards showing: Total repos, Active (90d), Stale (>1y), Archived, Package indexes, MRs (90d).

### Charts

1. **Last Activity Distribution** — bar chart bucketing repos by time since last activity: < 30 days, 30–90 days, 90 days – 1 year, > 1 year, Unknown.
2. **Repository Types** — donut chart: Active code vs. Package index vs. Archived.
3. **Activity Timeline** — scatter plot of non-archived repos: x = last commit date, y = open MR count, color = visibility, size = repo size.
4. **Merge Requests per Repo (last 90 days)** — horizontal bar chart ranking repos by recent MR count.

### Repository table

Sortable HTML table with columns: Name (linked), Visibility, Last Activity, Last Commit, Open MRs, MRs (90d), CI, Language, Size (KB), Contributors (90d), Type, Disposition, Dest Org.

Sorting is client-side JavaScript. Archived rows are dimmed. Stale rows (>1y) are highlighted in red.

## CSV report

Same data as the HTML table, plus all decision columns. One header row, one row per repo.

## Dependencies

| Package | Purpose |
|---|---|
| click | CLI framework |
| python-gitlab | GitLab API client |
| pydantic | Data models with validation and serialization |
| plotly | Interactive chart generation |
| jinja2 | HTML template rendering |
| tqdm | Progress bars |

## Testing

Tests use pytest with mocked GitLab API responses. Key test areas:

- **db:** upsert, decision column preservation, group_path filtering, boolean/JSON roundtrip.
- **index:** project metadata collection, package index detection (both mocked).
- **report:** CSV column correctness, HTML chart presence, summary stats.
- **cli:** help text, missing token/database errors.
