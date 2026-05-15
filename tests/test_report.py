"""Tests for report generation."""

import io
from datetime import datetime, timezone

from gitlab_repo_audit.models import RepoRecord
from gitlab_repo_audit.report import generate_csv, generate_html


def _make_record(**kwargs):
    defaults = dict(
        project_id=1,
        name="test-repo",
        path="group/test-repo",
        web_url="https://gitlab.com/group/test-repo",
        visibility="public",
        group_path="group",
        indexed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        last_activity_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        open_mr_count=3,
        ci_config_present=True,
        languages={"Python": 80.0},
        repo_size_kb=1024,
        contributors_last_90d=5,
    )
    defaults.update(kwargs)
    return RepoRecord(**defaults)


def test_csv_output():
    repos = [
        _make_record(project_id=1, name="repo-a"),
        _make_record(project_id=2, name="repo-b", archived=True),
    ]
    buf = io.StringIO()
    generate_csv(repos, buf)
    csv_text = buf.getvalue()

    assert "repo-a" in csv_text
    assert "repo-b" in csv_text
    assert "disposition" in csv_text
    lines = csv_text.strip().split("\n")
    assert len(lines) == 3  # header + 2 rows


def test_csv_columns():
    repos = [_make_record()]
    buf = io.StringIO()
    generate_csv(repos, buf)
    header = buf.getvalue().split("\n")[0]
    assert "name" in header
    assert "web_url" in header
    assert "disposition" in header
    assert "destination_org" in header
    assert "notes" in header


def test_html_contains_charts():
    repos = [
        _make_record(project_id=1, name="active-repo"),
        _make_record(project_id=2, name="stale-repo",
                     last_activity_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
                     last_commit_date=datetime(2023, 1, 1, tzinfo=timezone.utc)),
        _make_record(project_id=3, name="archived-repo", archived=True),
    ]
    html = generate_html(repos)

    assert "<!DOCTYPE html>" in html
    assert "plotly" in html.lower()
    assert "Last Activity Distribution" in html
    assert "Repository Types" in html
    assert "Activity Timeline" in html
    assert "active-repo" in html
    assert "stale-repo" in html


def test_html_summary_stats():
    repos = [
        _make_record(project_id=1, name="a"),
        _make_record(project_id=2, name="b", archived=True),
    ]
    html = generate_html(repos)
    assert "Total repos" in html
    assert "Archived" in html


def test_html_sortable_table():
    repos = [_make_record()]
    html = generate_html(repos)
    assert "sortTable" in html
    assert "<th" in html
