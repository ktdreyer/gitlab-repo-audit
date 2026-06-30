"""Tests for report generation."""

import io
from datetime import UTC, datetime

from gitlab_repo_audit.models import RepoData
from gitlab_repo_audit.report import extract_subgroup, generate_csv, generate_html


def _make_repo(**kwargs):
    defaults = {
        "project_id": 1,
        "name": "test-repo",
        "path": "group/test-repo",
        "web_url": "https://gitlab.com/group/test-repo",
        "visibility": "public",
        "group_path": "group",
        "indexed_at": datetime(2025, 1, 1, tzinfo=UTC),
        "last_activity_at": datetime(2025, 1, 1, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return RepoData(**defaults)


def test_csv_output():
    repos = [
        _make_repo(project_id=1, name="repo-a"),
        _make_repo(project_id=2, name="repo-b", archived=True),
    ]
    buf = io.StringIO()
    generate_csv(repos, buf)
    csv_text = buf.getvalue()

    assert "repo-a" in csv_text
    assert "repo-b" in csv_text
    lines = csv_text.strip().split("\n")
    assert len(lines) == 3


def test_csv_columns():
    repos = [_make_repo()]
    buf = io.StringIO()
    generate_csv(repos, buf)
    header = buf.getvalue().split("\n")[0]
    assert "name" in header
    assert "web_url" in header
    assert "repo_type" in header
    assert "group_path" in header


def test_html_contains_charts():
    repos = [
        _make_repo(project_id=1, name="active-repo"),
        _make_repo(project_id=2, name="stale-repo",
                   last_activity_at=datetime(2023, 1, 1, tzinfo=UTC)),
        _make_repo(project_id=3, name="archived-repo", archived=True,
                   repo_type="archived"),
    ]
    html = generate_html(repos)

    assert "<!DOCTYPE html>" in html
    assert "plotly" in html.lower()
    assert "Last Activity Distribution" in html
    assert "Repository Types" in html
    assert "active-repo" in html
    assert "stale-repo" in html


def test_html_summary_stats():
    repos = [
        _make_repo(project_id=1, name="a"),
        _make_repo(project_id=2, name="b", archived=True, repo_type="archived"),
    ]
    html = generate_html(repos)
    assert "Total repos" in html
    assert "Archived" in html


def test_html_sortable_table():
    repos = [_make_repo()]
    html = generate_html(repos)
    assert "sortTable" in html
    assert "<th" in html


def test_html_sunburst():
    repos = [_make_repo()]
    html = generate_html(repos)
    assert "sunburst-chart" in html
    assert "plotly_sunburstclick" in html


def test_html_filter_attributes():
    repos = [_make_repo(repo_type="code")]
    html = generate_html(repos)
    assert 'data-repo-type="code"' in html
    assert "data-subgroup=" in html


def test_extract_subgroup_pypi_index():
    assert extract_subgroup(
        "redhat/rhel-ai/rhai/indexes/vllm-2.20/cuda", "pypi_index", "redhat/rhel-ai"
    ) == "vllm-2.20"


def test_extract_subgroup_wheel_cache():
    assert extract_subgroup(
        "redhat/rhel-ai/core/wheels/torch-2.11/cuda", "wheel_cache", "redhat/rhel-ai"
    ) == "torch-2.11"


def test_extract_subgroup_mirror():
    assert extract_subgroup(
        "redhat/rhel-ai/core/mirrors/github/pytorch", "mirror", "redhat/rhel-ai"
    ) == "github"


def test_extract_subgroup_mirror_without_mirrors_segment():
    assert extract_subgroup(
        "redhat/rhel-ai/core/wheels/upstream-mirror", "mirror", "redhat/rhel-ai"
    ) == "core"


def test_extract_subgroup_code():
    assert extract_subgroup(
        "redhat/rhel-ai/core/some-tool", "code", "redhat/rhel-ai"
    ) == "core"
