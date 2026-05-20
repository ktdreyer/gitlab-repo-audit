"""GitLab API data collection for repository indexing."""

import logging
from datetime import UTC, datetime

import gitlab

from .models import RepoData

logger = logging.getLogger(__name__)


def classify_repo_type(path: str, archived: bool) -> str:
    """Classify a repo by its path and archived status."""
    if archived:
        return "archived"
    segments = path.split("/")
    if "indexes" in segments:
        return "pypi_index"
    if "wheels" in segments:
        return "wheel_cache"
    if "mirrors" in segments:
        return "mirror"
    return "code"


def _stub_to_repo(
    stub: gitlab.v4.objects.GroupProject, group_path: str
) -> RepoData:
    """Convert a group project stub to a RepoData without extra API calls."""
    last_activity = None
    if stub.last_activity_at:
        last_activity = datetime.fromisoformat(stub.last_activity_at)

    path = stub.path_with_namespace

    return RepoData(
        project_id=stub.id,
        name=stub.name,
        path=path,
        web_url=stub.web_url,
        description=stub.description,
        visibility=stub.visibility,
        archived=stub.archived,
        default_branch=getattr(stub, "default_branch", None),
        last_activity_at=last_activity,
        topics=getattr(stub, "topics", []) or [],
        star_count=getattr(stub, "star_count", 0),
        forks_count=getattr(stub, "forks_count", 0),
        repo_type=classify_repo_type(path, stub.archived),
        group_path=group_path,
        indexed_at=datetime.now(UTC),
    )


def index_group(gl: gitlab.Gitlab, group_path: str, quiet: bool = False) -> list[RepoData]:
    """Index all projects in a GitLab group using only the group listing API."""
    group = gl.groups.get(group_path)
    all_stubs = group.projects.list(get_all=True, include_subgroups=True)
    project_stubs = [s for s in all_stubs if "deletion_scheduled" not in s.name]
    skipped = len(all_stubs) - len(project_stubs)

    if not quiet:
        logger.info("Found %d projects in %s", len(project_stubs), group_path)
        if skipped:
            logger.info("Skipped %d project(s) pending deletion", skipped)

    return [_stub_to_repo(s, group_path) for s in project_stubs]
