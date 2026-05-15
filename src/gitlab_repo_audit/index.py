"""GitLab API data collection for repository indexing."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import gitlab
from tqdm import tqdm

from .models import MergeRequestData, RepoData
from .retry import retry_on_error

logger = logging.getLogger(__name__)


@retry_on_error()
def _get_project(gl: gitlab.Gitlab, project_id: int) -> gitlab.v4.objects.Project:
    return gl.projects.get(project_id, statistics=True)


@retry_on_error()
def _get_open_mr_count(project: gitlab.v4.objects.Project) -> int:
    mrs = project.mergerequests.list(state="opened", per_page=1, iterator=True)
    return mrs.total or 0  # type: ignore[union-attr]


@retry_on_error()
def _get_recent_mrs(project: gitlab.v4.objects.Project, limit: int = 100) -> list[MergeRequestData]:
    mrs = project.mergerequests.list(
        order_by="created_at", sort="desc", per_page=limit, get_all=False
    )
    return [
        MergeRequestData(
            project_id=project.id,
            mr_iid=mr.iid,
            title=mr.title,
            author=mr.author["username"] if mr.author else None,
            state=mr.state,
            created_at=datetime.fromisoformat(mr.created_at) if mr.created_at else None,
            merged_at=datetime.fromisoformat(mr.merged_at) if mr.merged_at else None,
            web_url=mr.web_url,
        )
        for mr in mrs
    ]


@retry_on_error()
def _get_last_commit_date(project: gitlab.v4.objects.Project) -> datetime | None:
    if not project.default_branch:
        return None
    try:
        branch = project.branches.get(project.default_branch)
        committed = branch.commit["committed_date"]
        return datetime.fromisoformat(committed)
    except gitlab.exceptions.GitlabGetError:
        return None


@retry_on_error()
def _has_ci_config(project: gitlab.v4.objects.Project) -> bool:
    try:
        project.files.get(file_path=".gitlab-ci.yml", ref=project.default_branch)
        return True
    except gitlab.exceptions.GitlabGetError:
        return False


@retry_on_error()
def _get_languages(project: gitlab.v4.objects.Project) -> dict[str, float]:
    try:
        return project.languages()  # type: ignore[return-value]
    except gitlab.exceptions.GitlabGetError:
        return {}


@retry_on_error()
def _get_recent_contributors(project: gitlab.v4.objects.Project, days: int = 90) -> int:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        commits = project.commits.list(since=since, per_page=100, get_all=True)
        authors = {c.author_email for c in commits if c.author_email}
        return len(authors)
    except gitlab.exceptions.GitlabGetError:
        return 0


@retry_on_error()
def _get_package_count(project: gitlab.v4.objects.Project) -> int:
    try:
        packages = project.packages.list(per_page=1, iterator=True)
        return packages.total or 0  # type: ignore[union-attr]
    except (gitlab.exceptions.GitlabGetError, gitlab.exceptions.GitlabListError):
        return 0


@retry_on_error()
def _check_is_package_index(project: gitlab.v4.objects.Project) -> bool:
    """A package index repo has no real source code — empty tree or only README."""
    try:
        tree = project.repository_tree(ref=project.default_branch, per_page=20, get_all=False)
    except gitlab.exceptions.GitlabGetError:
        return False
    if not tree:
        return True
    filenames = {item["name"].lower() for item in tree}
    source_files = filenames - {"readme.md", "readme", "readme.txt", ".gitignore", "license", "license.md"}
    return len(source_files) == 0


def index_project(
    gl: gitlab.Gitlab, project_stub: gitlab.v4.objects.GroupProject, group_path: str
) -> tuple[RepoData, list[MergeRequestData]]:
    """Collect all metadata for a single project."""
    project = _get_project(gl, project_stub.id)
    stats = getattr(project, "statistics", None) or {}

    last_activity = None
    if project.last_activity_at:
        last_activity = datetime.fromisoformat(project.last_activity_at)

    last_commit = _get_last_commit_date(project)
    open_mrs = _get_open_mr_count(project)
    recent_mrs = _get_recent_mrs(project)
    ci_present = _has_ci_config(project) if project.default_branch else False
    languages = _get_languages(project)
    contributors = _get_recent_contributors(project)
    pkg_count = _get_package_count(project)
    is_pkg_index = _check_is_package_index(project) if pkg_count > 0 else False

    repo = RepoData(
        project_id=project.id,
        name=project.name,
        path=project.path_with_namespace,
        web_url=project.web_url,
        description=project.description,
        visibility=project.visibility,
        archived=project.archived,
        default_branch=project.default_branch,
        last_activity_at=last_activity,
        last_commit_date=last_commit,
        open_mr_count=open_mrs,
        ci_config_present=ci_present,
        topics=getattr(project, "topics", []) or [],
        star_count=project.star_count,
        forks_count=project.forks_count,
        repo_size_kb=stats.get("repository_size"),
        languages=languages,
        contributors_last_90d=contributors,
        is_package_index=is_pkg_index,
        package_count=pkg_count,
        group_path=group_path,
        indexed_at=datetime.now(timezone.utc),
    )
    return repo, recent_mrs


def index_group(
    gl: gitlab.Gitlab,
    group_path: str,
    max_workers: int = 5,
    quiet: bool = False,
) -> list[tuple[RepoData, list[MergeRequestData]]]:
    """Index all projects in a GitLab group recursively."""
    group = gl.groups.get(group_path)
    all_stubs = group.projects.list(get_all=True, include_subgroups=True)
    project_stubs = [s for s in all_stubs if "deletion_scheduled" not in s.name]
    skipped = len(all_stubs) - len(project_stubs)

    if not quiet:
        logger.info("Found %d projects in %s", len(project_stubs), group_path)
        if skipped:
            logger.info("Skipped %d project(s) pending deletion", skipped)

    results: list[tuple[RepoData, list[MergeRequestData]]] = []
    errors: list[tuple[str, Exception]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(index_project, gl, stub, group_path): stub
            for stub in project_stubs
        }
        with tqdm(
            total=len(futures), desc="Indexing", file=None if quiet else __import__("sys").stderr, disable=quiet
        ) as progress:
            for future in as_completed(futures):
                stub = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    name = getattr(stub, "path_with_namespace", str(stub.id))
                    logger.warning("Failed to index %s: %s", name, e)
                    errors.append((name, e))
                progress.update(1)

    if errors and not quiet:
        logger.warning("Failed to index %d project(s)", len(errors))

    return results
