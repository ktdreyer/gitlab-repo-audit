"""SQLite storage for repository data."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import MergeRequestData, RepoData, RepoRecord

SCHEMA = """\
CREATE TABLE IF NOT EXISTS repos (
    project_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    web_url TEXT NOT NULL,
    description TEXT,
    visibility TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    default_branch TEXT,
    last_activity_at TEXT,
    last_commit_date TEXT,
    open_mr_count INTEGER,
    ci_config_present INTEGER,
    topics TEXT,
    star_count INTEGER DEFAULT 0,
    forks_count INTEGER DEFAULT 0,
    repo_size_kb INTEGER,
    languages TEXT,
    contributors_last_90d INTEGER,
    is_package_index INTEGER DEFAULT 0,
    package_count INTEGER DEFAULT 0,
    group_path TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    disposition TEXT,
    visibility_decision TEXT,
    destination_org TEXT,
    ci_runner_deps TEXT,
    content_sensitivity TEXT,
    dependencies TEXT,
    priority INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS merge_requests (
    project_id INTEGER NOT NULL,
    mr_iid INTEGER NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    state TEXT NOT NULL,
    created_at TEXT,
    merged_at TEXT,
    web_url TEXT NOT NULL,
    PRIMARY KEY (project_id, mr_iid),
    FOREIGN KEY (project_id) REFERENCES repos(project_id)
);
"""

API_COLUMNS = [
    "name",
    "path",
    "web_url",
    "description",
    "visibility",
    "archived",
    "default_branch",
    "last_activity_at",
    "last_commit_date",
    "open_mr_count",
    "ci_config_present",
    "topics",
    "star_count",
    "forks_count",
    "repo_size_kb",
    "languages",
    "contributors_last_90d",
    "is_package_index",
    "package_count",
    "group_path",
    "indexed_at",
]

MR_COLUMNS = ["project_id", "mr_iid", "title", "author", "state", "created_at", "merged_at", "web_url"]


def _repo_to_row(repo: RepoData) -> dict:
    """Serialize a RepoData model to a SQLite-compatible dict."""
    d = repo.model_dump(mode="json")
    d["archived"] = int(d["archived"])
    d["ci_config_present"] = int(d["ci_config_present"]) if d["ci_config_present"] is not None else None
    d["is_package_index"] = int(d["is_package_index"])
    d["topics"] = json.dumps(d["topics"])
    d["languages"] = json.dumps(d["languages"])
    return d


def _row_to_repo(row: sqlite3.Row) -> RepoRecord:
    """Deserialize a SQLite row into a RepoRecord model."""
    d = dict(row)
    d["topics"] = json.loads(d["topics"]) if d["topics"] else []
    d["languages"] = json.loads(d["languages"]) if d["languages"] else {}
    return RepoRecord.model_validate(d)


def _mr_to_row(mr: MergeRequestData) -> dict:
    """Serialize a MergeRequestData model to a SQLite-compatible dict."""
    return mr.model_dump(mode="json")


def _row_to_mr(row: sqlite3.Row) -> MergeRequestData:
    """Deserialize a SQLite row into a MergeRequestData model."""
    return MergeRequestData.model_validate(dict(row))


class RepoDB:
    """SQLite database for repository data."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def upsert(self, repo: RepoData) -> None:
        """Insert or update a repo record, preserving manual decision columns."""
        row = _repo_to_row(repo)
        set_clause = ", ".join(f"{col} = excluded.{col}" for col in API_COLUMNS)
        cols = ["project_id"] + API_COLUMNS
        placeholders = ", ".join(f":{col}" for col in cols)
        col_names = ", ".join(cols)
        sql = (
            f"INSERT INTO repos ({col_names}) VALUES ({placeholders}) "
            f"ON CONFLICT(project_id) DO UPDATE SET {set_clause}"
        )
        self._conn.execute(sql, row)
        self._conn.commit()

    def get_all(self, group_path: str | None = None) -> list[RepoRecord]:
        """Get all repo records, optionally filtered by group_path."""
        if group_path:
            cursor = self._conn.execute(
                "SELECT * FROM repos WHERE group_path = ? ORDER BY last_activity_at DESC",
                (group_path,),
            )
        else:
            cursor = self._conn.execute(
                "SELECT * FROM repos ORDER BY last_activity_at DESC"
            )
        return [_row_to_repo(row) for row in cursor.fetchall()]

    def upsert_mrs(self, mrs: list[MergeRequestData]) -> None:
        """Insert or update merge request records."""
        cols = ", ".join(MR_COLUMNS)
        placeholders = ", ".join(f":{col}" for col in MR_COLUMNS)
        update_cols = [c for c in MR_COLUMNS if c not in ("project_id", "mr_iid")]
        set_clause = ", ".join(f"{col}=excluded.{col}" for col in update_cols)
        sql = (
            f"INSERT INTO merge_requests ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(project_id, mr_iid) DO UPDATE SET {set_clause}"
        )
        for mr in mrs:
            self._conn.execute(sql, _mr_to_row(mr))
        self._conn.commit()

    def get_mrs(self, project_id: int) -> list[MergeRequestData]:
        """Get all stored merge requests for a project."""
        cursor = self._conn.execute(
            "SELECT * FROM merge_requests WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        )
        return [_row_to_mr(row) for row in cursor.fetchall()]

    def get_mr_count_since(self, project_id: int, since: datetime) -> int:
        """Count merge requests created after a given date."""
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM merge_requests WHERE project_id = ? AND created_at >= ?",
            (project_id, since.isoformat()),
        )
        return cursor.fetchone()[0]

    def close(self) -> None:
        self._conn.close()
