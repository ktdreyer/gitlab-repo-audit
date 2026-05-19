"""Pydantic models for repository data."""

from datetime import datetime

from pydantic import BaseModel, Field


class RepoData(BaseModel):
    """Data collected from the GitLab API for a single project."""

    project_id: int
    name: str
    path: str
    web_url: str
    description: str | None = None
    visibility: str
    archived: bool = False
    default_branch: str | None = None
    last_activity_at: datetime | None = None
    last_commit_date: datetime | None = None
    open_mr_count: int | None = None
    ci_config_present: bool | None = None
    topics: list[str] = Field(default_factory=list)
    star_count: int = 0
    forks_count: int = 0
    repo_size_kb: int | None = None
    languages: dict[str, float] = Field(default_factory=dict)
    contributors_last_90d: int | None = None
    is_package_index: bool = False
    package_count: int = 0
    repo_type: str = "code"
    group_path: str = ""
    indexed_at: datetime = Field(default_factory=datetime.utcnow)


class MergeRequestData(BaseModel):
    """Data collected from the GitLab API for a single merge request."""

    project_id: int
    mr_iid: int
    title: str
    author: str | None = None
    state: str
    created_at: datetime | None = None
    merged_at: datetime | None = None
    web_url: str


class RepoRecord(RepoData):
    """Full repo record including manual decision columns from the database."""

    disposition: str | None = None
    visibility_decision: str | None = None
    destination_org: str | None = None
    ci_runner_deps: str | None = None
    content_sensitivity: str | None = None
    dependencies: str | None = None
    priority: int | None = None
    notes: str | None = None
