"""Tests for GitLab API data collection."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from gitlab_repo_audit.index import classify_repo_type, enrich_project
from gitlab_repo_audit.models import MergeRequestData, RepoData


def _mock_project():
    project = MagicMock()
    project.id = 42
    project.name = "test-project"
    project.path_with_namespace = "group/test-project"
    project.web_url = "https://gitlab.com/group/test-project"
    project.description = "A test project"
    project.visibility = "public"
    project.archived = False
    project.default_branch = "main"
    project.last_activity_at = "2025-01-15T10:00:00+00:00"
    project.star_count = 5
    project.forks_count = 2
    project.statistics = {"repository_size": 2048}
    project.topics = ["python", "ci"]

    branch = MagicMock()
    branch.commit = {"committed_date": "2025-01-14T09:00:00+00:00"}
    project.branches.get.return_value = branch

    mr1 = MagicMock()
    mr1.iid = 10
    mr1.title = "Fix thing"
    mr1.author = {"username": "dev1"}
    mr1.state = "merged"
    mr1.created_at = "2025-01-10T10:00:00+00:00"
    mr1.merged_at = "2025-01-12T10:00:00+00:00"
    mr1.web_url = "https://gitlab.com/group/test-project/-/merge_requests/10"

    open_mr_iter = MagicMock()
    open_mr_iter.total = 3

    def _mr_list_side_effect(**kwargs):
        if kwargs.get("state") == "opened":
            return open_mr_iter
        return [mr1]

    project.mergerequests.list.side_effect = _mr_list_side_effect

    file_obj = MagicMock()
    project.files.get.return_value = file_obj

    project.languages.return_value = {"Python": 85.0, "Shell": 15.0}

    commit1 = MagicMock()
    commit1.author_email = "dev1@example.com"
    commit2 = MagicMock()
    commit2.author_email = "dev2@example.com"
    project.commits.list.return_value = [commit1, commit2]

    pkg_iter = MagicMock()
    pkg_iter.total = 0
    project.packages.list.return_value = pkg_iter

    return project


@patch("gitlab_repo_audit.index._get_project")
def test_index_project(mock_get_project):
    project = _mock_project()
    mock_get_project.return_value = project

    gl = MagicMock()
    stub = MagicMock()
    stub.id = 42

    repo, mrs = enrich_project(gl, stub, "group")

    assert isinstance(repo, RepoData)
    assert repo.project_id == 42
    assert repo.name == "test-project"
    assert repo.visibility == "public"
    assert repo.open_mr_count == 3
    assert repo.ci_config_present is True
    assert repo.contributors_last_90d == 2
    assert repo.languages == {"Python": 85.0, "Shell": 15.0}
    assert repo.repo_size_kb == 2048
    assert repo.topics == ["python", "ci"]
    assert repo.is_package_index is False

    assert len(mrs) == 1
    assert mrs[0].mr_iid == 10
    assert mrs[0].author == "dev1"
    assert mrs[0].state == "merged"


@patch("gitlab_repo_audit.index._get_project")
def test_index_project_package_index(mock_get_project):
    project = _mock_project()

    orig_side_effect = project.packages.list.side_effect
    pkg_iter = MagicMock()
    pkg_iter.total = 50
    project.packages.list.side_effect = None
    project.packages.list.return_value = pkg_iter

    project.repository_tree.return_value = [
        {"name": "README.md", "type": "blob"},
    ]

    mock_get_project.return_value = project

    gl = MagicMock()
    stub = MagicMock()
    stub.id = 42

    repo, mrs = enrich_project(gl, stub, "group")
    assert repo.is_package_index is True
    assert repo.package_count == 50


def test_classify_repo_type_code():
    assert classify_repo_type("redhat/rhel-ai/core/some-tool", False) == "code"


def test_classify_repo_type_archived():
    assert classify_repo_type("redhat/rhel-ai/core/some-tool", True) == "archived"


def test_classify_repo_type_pypi_index():
    assert classify_repo_type("redhat/rhel-ai/rhai/indexes/vllm-2.20/cuda-ubi9-x86_64", False) == "pypi_index"


def test_classify_repo_type_wheel_cache():
    assert classify_repo_type("redhat/rhel-ai/core/wheels/torch-2.11/cuda-ubi9-x86_64", False) == "wheel_cache"


def test_classify_repo_type_mirror():
    assert classify_repo_type("redhat/rhel-ai/core/mirrors/github/pytorch/pytorch", False) == "mirror"


def test_classify_repo_type_archived_overrides_path():
    assert classify_repo_type("redhat/rhel-ai/rhai/indexes/old-thing", True) == "archived"
