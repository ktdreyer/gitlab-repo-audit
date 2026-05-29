"""Tests for GitLab API data collection."""

from unittest.mock import MagicMock

from gitlab_repo_audit.index import _stub_to_repo, classify_repo_type


def _mock_stub(**kwargs):
    stub = MagicMock()
    stub.id = kwargs.get("id", 42)
    stub.name = kwargs.get("name", "test-project")
    stub.path_with_namespace = kwargs.get("path", "group/test-project")
    stub.web_url = kwargs.get("web_url", "https://gitlab.com/group/test-project")
    stub.description = kwargs.get("description", "A test project")
    stub.visibility = kwargs.get("visibility", "public")
    stub.archived = kwargs.get("archived", False)
    stub.default_branch = kwargs.get("default_branch", "main")
    stub.last_activity_at = kwargs.get("last_activity_at", "2025-01-15T10:00:00+00:00")
    stub.star_count = kwargs.get("star_count", 5)
    stub.forks_count = kwargs.get("forks_count", 2)
    stub.topics = kwargs.get("topics", ["python", "ci"])
    return stub


def test_stub_to_repo():
    stub = _mock_stub()
    repo = _stub_to_repo(stub, "group")

    assert repo.project_id == 42
    assert repo.name == "test-project"
    assert repo.visibility == "public"
    assert repo.repo_type == "code"
    assert repo.group_path == "group"
    assert repo.topics == ["python", "ci"]


def test_stub_to_repo_index():
    stub = _mock_stub(
        path="redhat/rhel-ai/rhai/indexes/vllm-2.20/cuda",
    )
    repo = _stub_to_repo(stub, "redhat/rhel-ai")
    assert repo.repo_type == "pypi_index"


def test_classify_repo_type_code():
    assert classify_repo_type("redhat/rhel-ai/core/some-tool", False) == "code"


def test_classify_repo_type_archived():
    assert classify_repo_type("redhat/rhel-ai/core/some-tool", True) == "archived"


def test_classify_repo_type_pypi_index():
    path = "redhat/rhel-ai/rhai/indexes/vllm-2.20/cuda-ubi9-x86_64"
    assert classify_repo_type(path, False) == "pypi_index"


def test_classify_repo_type_wheel_cache():
    path = "redhat/rhel-ai/core/wheels/torch-2.11/cuda-ubi9-x86_64"
    assert classify_repo_type(path, False) == "wheel_cache"


def test_classify_repo_type_mirror():
    path = "redhat/rhel-ai/core/mirrors/github/pytorch/pytorch"
    assert classify_repo_type(path, False) == "mirror"


def test_classify_repo_type_archived_overrides_path():
    assert classify_repo_type("redhat/rhel-ai/rhai/indexes/old-thing", True) == "archived"


def test_classify_repo_type_wheels_builder_is_code():
    assert classify_repo_type("redhat/rhel-ai/wheels/builder", False) == "code"


def test_classify_repo_type_wheels_pipeline_is_code():
    assert classify_repo_type("redhat/rhel-ai/core/wheels/pipeline", False) == "code"


def test_classify_repo_type_wheels_build_repo_is_code():
    assert classify_repo_type("redhat/rhel-ai/wheels/tpu-wheel-build", False) == "code"


def test_classify_repo_type_wheels_mirror_is_mirror():
    assert classify_repo_type("redhat/rhel-ai/wheels/gaudi-mirror", False) == "mirror"


def test_classify_repo_type_wheels_mirrored_is_mirror():
    assert classify_repo_type("redhat/rhel-ai/wheels/tpu-mirrored-wheels", False) == "mirror"


def test_classify_repo_type_wheels_upstream_sdists():
    assert classify_repo_type("redhat/rhel-ai/core/wheels/upstream-sdists", False) == "wheel_cache"


def test_classify_repo_type_wheels_prefetch():
    assert classify_repo_type("redhat/rhel-ai/wheels/prefetch", False) == "wheel_cache"
