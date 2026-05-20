"""Tests for SQLite database operations."""

from datetime import UTC, datetime

from gitlab_repo_audit.db import RepoDB
from gitlab_repo_audit.models import RepoData


def _make_repo(**kwargs):
    defaults = {
        "project_id": 1,
        "name": "test-repo",
        "path": "group/test-repo",
        "web_url": "https://gitlab.com/group/test-repo",
        "visibility": "public",
        "group_path": "group",
        "indexed_at": datetime(2025, 1, 1, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return RepoData(**defaults)


def test_upsert_and_get(tmp_path):
    db = RepoDB(tmp_path / "test.db")
    repo = _make_repo()
    db.upsert(repo)
    records = db.get_all()
    assert len(records) == 1
    assert records[0].name == "test-repo"
    assert records[0].project_id == 1
    db.close()


def test_upsert_overwrites(tmp_path):
    db = RepoDB(tmp_path / "test.db")
    db.upsert(_make_repo())
    db.upsert(_make_repo(name="test-repo-renamed", indexed_at=datetime(2025, 6, 1, tzinfo=UTC)))

    records = db.get_all()
    assert len(records) == 1
    assert records[0].name == "test-repo-renamed"
    db.close()


def test_filter_by_group_path(tmp_path):
    db = RepoDB(tmp_path / "test.db")
    db.upsert(_make_repo(project_id=1, group_path="group-a"))
    db.upsert(_make_repo(project_id=2, name="other", group_path="group-b"))

    assert len(db.get_all()) == 2
    assert len(db.get_all(group_path="group-a")) == 1
    assert len(db.get_all(group_path="group-b")) == 1
    db.close()


def test_creates_parent_dirs(tmp_path):
    db_path = tmp_path / "deep" / "nested" / "dir" / "test.db"
    db = RepoDB(db_path)
    db.upsert(_make_repo())
    assert db_path.exists()
    db.close()


def test_boolean_roundtrip(tmp_path):
    db = RepoDB(tmp_path / "test.db")
    repo = _make_repo(archived=True)
    db.upsert(repo)

    records = db.get_all()
    assert records[0].archived is True
    db.close()


def test_topics_roundtrip(tmp_path):
    db = RepoDB(tmp_path / "test.db")
    repo = _make_repo(topics=["python", "ci-cd"])
    db.upsert(repo)

    records = db.get_all()
    assert records[0].topics == ["python", "ci-cd"]
    db.close()
