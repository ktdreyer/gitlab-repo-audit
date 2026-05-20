"""Command-line interface for gitlab-repo-audit."""

import logging
import os
import sys
import time
from pathlib import Path
from typing import TextIO

import click
import gitlab

from .db import RepoDB
from .index import index_group
from .report import generate_csv, generate_html
from .retry import retry_on_error

DEFAULT_DB_DIR = Path.home() / ".cache" / "gitlab-repo-audit"


def configure_logging(verbose: bool, quiet: bool) -> None:
    if verbose and quiet:
        raise click.ClickException("Cannot use both --verbose and --quiet")
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("urllib3").setLevel(logging.ERROR)


@retry_on_error()
def get_gitlab_client(token: str | None = None, url: str = "https://gitlab.com") -> gitlab.Gitlab:
    if token is None:
        token = os.environ.get("GITLAB_TOKEN")
    if not token:
        raise click.ClickException(
            "GitLab token not found. Set GITLAB_TOKEN or use --token."
        )
    gl = gitlab.Gitlab(url, private_token=token, retry_transient_errors=True)
    gl.auth()
    return gl


@click.group()
def cli() -> None:
    """Audit and inventory GitLab repositories."""


@cli.command()
@click.argument("group_path")
@click.option("--token", "-t", default=None, help="GitLab API token (defaults to GITLAB_TOKEN)")
@click.option("--url", "-u", default="https://gitlab.com", show_default=True, help="GitLab instance URL")
@click.option("--db", "db_path", default=None, help="SQLite database path (defaults to ~/.cache/gitlab-repo-audit/repos.db)")
@click.option("--workers", "-w", type=int, default=5, show_default=True, help="Parallel workers for API calls")
@click.option("--verbose", "-v", is_flag=True, help="Debug output")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode")
@click.option("--quick", is_flag=True, help="Fast stub-only index (skip per-project API calls)")
def index(
    group_path: str,
    token: str | None,
    url: str,
    db_path: str | None,
    workers: int,
    verbose: bool,
    quiet: bool,
    quick: bool,
) -> None:
    """Index all repositories in a GitLab group into SQLite.

    GROUP_PATH is the full path to a GitLab group (e.g. 'redhat/rhel-ai/ci-cd').
    Projects are discovered recursively across all subgroups.

    \b
    Examples:
        gitlab-repo-audit index redhat/rhel-ai/ci-cd
        gitlab-repo-audit index redhat/rhel-ai --workers 10
        gitlab-repo-audit index redhat/rhel-ai --quick
    """
    try:
        configure_logging(verbose, quiet)

        gl = get_gitlab_client(token, url)

        if db_path is None:
            db_path = str(DEFAULT_DB_DIR / "repos.db")

        db = RepoDB(db_path)
        start = time.monotonic()

        group_path = group_path.strip("/")
        results = index_group(gl, group_path, max_workers=workers, quiet=quiet, quick=quick)

        for repo, mrs in results:
            db.upsert(repo)
            db.upsert_mrs(mrs)

        db.close()
        elapsed = time.monotonic() - start
        minutes, seconds = divmod(int(elapsed), 60)

        if not quiet:
            total_mrs = sum(len(mrs) for _, mrs in results)
            click.echo(
                f"Indexed {len(results)} repos ({total_mrs} MRs) from {group_path} in {minutes}m {seconds}s. "
                f"Database: {db_path}",
                err=True,
            )

    except gitlab.exceptions.GitlabAuthenticationError as e:
        raise click.ClickException("Authentication failed. Check your GitLab token.") from e
    except gitlab.exceptions.GitlabGetError as e:
        raise click.ClickException(f"Could not find group: {group_path}\n{e}") from e
    except gitlab.exceptions.GitlabError as e:
        raise click.ClickException(f"GitLab API error: {e}") from e


@cli.command()
@click.option("--db", "db_path", default=None, help="SQLite database path")
@click.option("--group", "group_path", default=None, help="Filter by group path")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output file (HTML or CSV by extension, default: stdout HTML)")
@click.option("--verbose", "-v", is_flag=True, help="Debug output")
@click.option("--quiet", "-q", is_flag=True, help="Quiet mode")
def report(
    db_path: str | None,
    group_path: str | None,
    output: str | None,
    verbose: bool,
    quiet: bool,
) -> None:
    """Generate a report from indexed repository data.

    Output format is determined by file extension:
    .html → interactive HTML report with Plotly charts
    .csv  → CSV for spreadsheet workflows

    \b
    Examples:
        gitlab-repo-audit report -o repos.html
        gitlab-repo-audit report -o repos.csv --group redhat/rhel-ai/ci-cd
    """
    configure_logging(verbose, quiet)

    if db_path is None:
        db_path = str(DEFAULT_DB_DIR / "repos.db")

    if not Path(db_path).exists():
        raise click.ClickException(
            f"Database not found: {db_path}\nRun 'gitlab-repo-audit index' first."
        )

    db = RepoDB(db_path)
    repos = db.get_all(group_path=group_path)
    mrs_by_repo = {r.project_id: db.get_mrs(r.project_id) for r in repos}
    db.close()

    if not repos:
        raise click.ClickException("No repos found in database. Run 'gitlab-repo-audit index' first.")

    if output and output.endswith(".csv"):
        with open(output, "w", newline="") as f:
            generate_csv(repos, f, mrs_by_repo=mrs_by_repo)
        if not quiet:
            click.echo(f"CSV report written to {output} ({len(repos)} repos)", err=True)
    else:
        quick = all(r.ci_config_present is None for r in repos)
        html = generate_html(repos, mrs_by_repo=mrs_by_repo, quick=quick)
        if output:
            with open(output, "w") as f:
                f.write(html)
            if not quiet:
                click.echo(f"HTML report written to {output} ({len(repos)} repos)", err=True)
        else:
            click.echo(html)


if __name__ == "__main__":
    cli()
