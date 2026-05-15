"""Report generation: HTML with Plotly charts and CSV export."""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TextIO

import jinja2
import plotly.graph_objects as go

from .models import MergeRequestData, RepoRecord

TEMPLATE_DIR = Path(__file__).parent / "templates"

CSV_COLUMNS = [
    "name",
    "web_url",
    "description",
    "visibility",
    "archived",
    "last_activity_at",
    "last_commit_date",
    "open_mr_count",
    "mrs_90d",
    "ci_config_present",
    "languages",
    "repo_size_kb",
    "topics",
    "star_count",
    "forks_count",
    "contributors_last_90d",
    "is_package_index",
    "package_count",
    "indexed_at",
    "disposition",
    "visibility_decision",
    "destination_org",
    "ci_runner_deps",
    "content_sensitivity",
    "dependencies",
    "priority",
    "notes",
]

COLUMNS = [
    {"label": "Name", "sortable": True},
    {"label": "Visibility", "sortable": True},
    {"label": "Last Activity", "sortable": True},
    {"label": "Last Commit", "sortable": True},
    {"label": "Open MRs", "sortable": True},
    {"label": "MRs (90d)", "sortable": True},
    {"label": "CI", "sortable": True},
    {"label": "Language", "sortable": True},
    {"label": "Size (KB)", "sortable": True},
    {"label": "Contributors (90d)", "sortable": True},
    {"label": "Type", "sortable": True},
    {"label": "Disposition", "sortable": False},
    {"label": "Dest Org", "sortable": False},
]


def _days_since(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def _staleness_bucket(days: int | None) -> str:
    if days is None:
        return "Unknown"
    if days < 30:
        return "< 30 days"
    if days < 90:
        return "30–90 days"
    if days < 365:
        return "90 days – 1 year"
    return "> 1 year"


def _top_language(repo: RepoRecord) -> str:
    if not repo.languages:
        return "None"
    return max(repo.languages, key=repo.languages.get)  # type: ignore[arg-type]


def _repo_type(repo: RepoRecord) -> str:
    if repo.archived:
        return "Archived"
    if repo.is_package_index:
        return "Package index"
    return "Active code"


def _mr_count_since(mrs: list[MergeRequestData], days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return sum(1 for mr in mrs if mr.created_at and mr.created_at >= cutoff)


def _build_charts(
    repos: list[RepoRecord],
    mrs_by_repo: dict[int, list[MergeRequestData]],
) -> list[dict]:
    """Build Plotly chart HTML fragments."""
    # Red Hat / PatternFly palette
    rh_blue = "#0066cc"
    rh_red = "#c9190b"
    rh_green = "#3e8635"
    rh_orange = "#f0ab00"
    rh_purple = "#6753ac"
    rh_gray = "#6a6e73"

    dark_layout = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#151515",
    )

    charts = []

    # Staleness distribution
    buckets = {"< 30 days": 0, "30–90 days": 0, "90 days – 1 year": 0, "> 1 year": 0, "Unknown": 0}
    for r in repos:
        buckets[_staleness_bucket(_days_since(r.last_activity_at))] += 1

    fig = go.Figure(data=[go.Bar(
        x=list(buckets.keys()), y=list(buckets.values()),
        marker_color=[rh_green, rh_orange, "#ec7a08", rh_red, rh_gray],
    )])
    fig.update_layout(
        title="Last Activity Distribution", xaxis_title="Time since last activity",
        yaxis_title="Number of repos", height=350, margin=dict(t=40, b=40, l=50, r=20), **dark_layout,
    )
    charts.append({"html": fig.to_html(full_html=False, include_plotlyjs=False), "full_width": False})

    # Repo type breakdown
    type_counts = {"Active code": 0, "Package index": 0, "Archived": 0}
    for r in repos:
        type_counts[_repo_type(r)] += 1

    fig = go.Figure(data=[go.Pie(
        labels=list(type_counts.keys()), values=list(type_counts.values()),
        marker_colors=[rh_blue, rh_purple, rh_gray], hole=0.4,
    )])
    fig.update_layout(title="Repository Types", height=350, margin=dict(t=40, b=20, l=20, r=20), **dark_layout)
    charts.append({"html": fig.to_html(full_html=False, include_plotlyjs=False), "full_width": False})

    # Activity timeline
    active_repos = [r for r in repos if r.last_commit_date and not r.archived]
    fig = go.Figure()
    vis_colors = [("public", rh_green), ("internal", rh_orange), ("private", rh_red)]
    for visibility, color in vis_colors:
        subset = [r for r in active_repos if r.visibility == visibility]
        if not subset:
            continue
        fig.add_trace(go.Scatter(
            x=[r.last_commit_date for r in subset],
            y=[r.open_mr_count or 0 for r in subset],
            mode="markers", name=visibility,
            marker=dict(color=color, size=[(r.repo_size_kb or 100) ** 0.3 * 3 for r in subset], sizemin=5),
            text=[f"{r.name}<br>{r.path}" for r in subset],
            hovertemplate="%{text}<br>Last commit: %{x}<br>Open MRs: %{y}<extra></extra>",
        ))
    fig.update_layout(
        title="Activity Timeline (non-archived repos)", xaxis_title="Last commit date",
        yaxis_title="Open merge requests", height=400, margin=dict(t=40, b=40, l=50, r=20), **dark_layout,
    )
    charts.append({"html": fig.to_html(full_html=False, include_plotlyjs=False), "full_width": True})

    # MR activity per repo
    non_archived = [r for r in repos if not r.archived]
    mr_repos = sorted(non_archived, key=lambda r: _mr_count_since(mrs_by_repo.get(r.project_id, []), 90), reverse=True)

    fig = go.Figure(data=[go.Bar(
        x=[_mr_count_since(mrs_by_repo.get(r.project_id, []), 90) for r in mr_repos],
        y=[r.name for r in mr_repos],
        orientation="h", marker_color=rh_blue,
    )])
    fig.update_layout(
        title="Merge Requests per Repo (last 90 days)", xaxis_title="MRs created",
        height=max(300, len(mr_repos) * 28 + 80), margin=dict(t=40, b=40, l=200, r=20),
        yaxis=dict(autorange="reversed"), **dark_layout,
    )
    charts.append({"html": fig.to_html(full_html=False, include_plotlyjs=False), "full_width": True})

    return charts


def _build_rows(
    repos: list[RepoRecord],
    mrs_by_repo: dict[int, list[MergeRequestData]],
) -> list[dict]:
    """Build table row data for the template."""
    rows = []
    for r in repos:
        days = _days_since(r.last_activity_at)
        css_class = ""
        if r.archived:
            css_class = "archived"
        elif days is not None and days >= 365:
            css_class = "stale"

        rows.append({
            "css_class": css_class,
            "name": r.name,
            "web_url": r.web_url,
            "visibility": r.visibility,
            "last_activity": r.last_activity_at.strftime("%Y-%m-%d") if r.last_activity_at else "—",
            "last_activity_sort": r.last_activity_at.isoformat() if r.last_activity_at else "",
            "last_commit": r.last_commit_date.strftime("%Y-%m-%d") if r.last_commit_date else "—",
            "last_commit_sort": r.last_commit_date.isoformat() if r.last_commit_date else "",
            "open_mr_count": r.open_mr_count or 0,
            "mrs_90d": _mr_count_since(mrs_by_repo.get(r.project_id, []), 90),
            "ci": "Yes" if r.ci_config_present else "No" if r.ci_config_present is not None else "—",
            "language": _top_language(r),
            "repo_size_kb": r.repo_size_kb or "—",
            "contributors_90d": r.contributors_last_90d or 0,
            "repo_type": _repo_type(r),
            "disposition": r.disposition or "",
            "destination_org": r.destination_org or "",
        })
    return rows


def generate_csv(
    repos: list[RepoRecord],
    output: TextIO,
    mrs_by_repo: dict[int, list[MergeRequestData]] | None = None,
) -> None:
    """Write repos as CSV."""
    if mrs_by_repo is None:
        mrs_by_repo = {}
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for repo in repos:
        row = repo.model_dump()
        row["languages"] = _top_language(repo)
        row["topics"] = ", ".join(repo.topics)
        row["mrs_90d"] = _mr_count_since(mrs_by_repo.get(repo.project_id, []), 90)
        writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})


def generate_html(
    repos: list[RepoRecord],
    mrs_by_repo: dict[int, list[MergeRequestData]] | None = None,
) -> str:
    """Generate a self-contained HTML report with Plotly charts."""
    if mrs_by_repo is None:
        mrs_by_repo = {}
    now = datetime.now(timezone.utc)

    stats = [
        {"value": len(repos), "label": "Total repos"},
        {"value": sum(1 for r in repos if _days_since(r.last_activity_at) is not None and _days_since(r.last_activity_at) < 90), "label": "Active (90d)"},  # type: ignore[operator]
        {"value": sum(1 for r in repos if _days_since(r.last_activity_at) is not None and _days_since(r.last_activity_at) >= 365), "label": "Stale (>1y)"},  # type: ignore[operator]
        {"value": sum(1 for r in repos if r.archived), "label": "Archived"},
        {"value": sum(1 for r in repos if r.is_package_index and not r.archived), "label": "Package indexes"},
        {"value": sum(_mr_count_since(mrs_by_repo.get(r.project_id, []), 90) for r in repos), "label": "MRs (90d)"},
    ]

    charts = _build_charts(repos, mrs_by_repo)
    rows = _build_rows(repos, mrs_by_repo)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("report.html")
    return template.render(
        stats=stats,
        charts=charts,
        columns=COLUMNS,
        rows=rows,
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
    )
