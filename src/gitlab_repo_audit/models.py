"""Pydantic models for repository data."""

from datetime import datetime

from pydantic import BaseModel, Field


class RepoData(BaseModel):
    """Data collected from the GitLab group listing API for a single project."""

    project_id: int
    name: str
    path: str
    web_url: str
    description: str | None = None
    visibility: str
    archived: bool = False
    default_branch: str | None = None
    last_activity_at: datetime | None = None
    topics: list[str] = Field(default_factory=list)
    star_count: int = 0
    forks_count: int = 0
    repo_type: str = "code"
    group_path: str = ""
    indexed_at: datetime = Field(default_factory=datetime.utcnow)
