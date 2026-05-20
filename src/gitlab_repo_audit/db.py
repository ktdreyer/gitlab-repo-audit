"""SQLite storage for repository data."""

import json
import sqlite3
from pathlib import Path

from .models import RepoData

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
    topics TEXT,
    star_count INTEGER DEFAULT 0,
    forks_count INTEGER DEFAULT 0,
    repo_type TEXT DEFAULT 'code',
    group_path TEXT NOT NULL,
    indexed_at TEXT NOT NULL
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
    "topics",
    "star_count",
    "forks_count",
    "repo_type",
    "group_path",
    "indexed_at",
]


def _repo_to_row(repo: RepoData) -> dict:
    """Serialize a RepoData model to a SQLite-compatible dict."""
    d = repo.model_dump(mode="json")
    d["archived"] = int(d["archived"])
    d["topics"] = json.dumps(d["topics"])
    return d


def _row_to_repo(row: sqlite3.Row) -> RepoData:
    """Deserialize a SQLite row into a RepoData model."""
    d = dict(row)
    d["topics"] = json.loads(d["topics"]) if d["topics"] else []
    return RepoData.model_validate(d)


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
        """Insert or update a repo record."""
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

    def get_all(self, group_path: str | None = None) -> list[RepoData]:
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

    def close(self) -> None:
        self._conn.close()
