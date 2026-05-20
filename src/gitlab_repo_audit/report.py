"""Report generation: HTML with Plotly charts and CSV export."""

import csv
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

import jinja2
import plotly.graph_objects as go

from .models import RepoData

TEMPLATE_DIR = Path(__file__).parent / "templates"

CSV_COLUMNS = [
    "name",
    "web_url",
    "description",
    "visibility",
    "archived",
    "last_activity_at",
    "topics",
    "star_count",
    "forks_count",
    "repo_type",
    "group_path",
    "indexed_at",
]

COLUMNS = [
    {"label": "Name", "sortable": True},
    {"label": "Visibility", "sortable": True},
    {"label": "Last Activity", "sortable": True},
    {"label": "Type", "sortable": True},
]

REPO_TYPE_LABELS = {
    "code": "Code",
    "pypi_index": "PyPI index",
    "wheel_cache": "Wheel cache",
    "mirror": "Mirror",
    "archived": "Archived",
}

REPO_TYPE_KEYS = {v: k for k, v in REPO_TYPE_LABELS.items()}


def _days_since(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
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


def _repo_type_label(repo: RepoData) -> str:
    return REPO_TYPE_LABELS.get(repo.repo_type, repo.repo_type)


def extract_subgroup(path: str, repo_type: str, group_path: str) -> str:
    """Extract the subgroup segment from a repo path for the sunburst chart."""
    segments = path.split("/")
    if repo_type == "pypi_index":
        idx = segments.index("indexes")
        return segments[idx + 1] if idx + 1 < len(segments) else "other"
    if repo_type == "wheel_cache":
        idx = segments.index("wheels")
        return segments[idx + 1] if idx + 1 < len(segments) else "other"
    if repo_type == "mirror":
        idx = segments.index("mirrors")
        return segments[idx + 1] if idx + 1 < len(segments) else "other"
    prefix_len = len(group_path.split("/"))
    return segments[prefix_len] if prefix_len < len(segments) else "other"


def _build_charts(repos: list[RepoData]) -> list[dict]:
    """Build Plotly chart HTML fragments."""
    rh_blue = "#0066cc"
    rh_red = "#c9190b"
    rh_green = "#3e8635"
    rh_orange = "#f0ab00"
    rh_purple = "#6753ac"
    rh_gray = "#6a6e73"

    dark_layout = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font_color": "#151515",
    }

    charts = []

    # Staleness distribution (code repos only)
    code_repos = [r for r in repos if r.repo_type == "code"]
    buckets = {"< 30 days": 0, "30–90 days": 0, "90 days – 1 year": 0, "> 1 year": 0, "Unknown": 0}
    for r in code_repos:
        buckets[_staleness_bucket(_days_since(r.last_activity_at))] += 1

    fig = go.Figure(data=[go.Bar(
        x=list(buckets.keys()), y=list(buckets.values()),
        marker_color=[rh_green, rh_orange, "#ec7a08", rh_red, rh_gray],
    )])
    fig.update_layout(
        title="Last Activity Distribution (code repos only)",
        xaxis_title="Time since last activity",
        yaxis_title="Number of repos", height=350,
        margin={"t": 40, "b": 40, "l": 50, "r": 20},
        **dark_layout,
    )
    fig.add_annotation(
        text="GitLab's last_activity_at counts any activity including bot pushes<br>"
             "to package registries, CI pipelines, and mirror syncs.<br>"
             "This chart is scoped to code repos to filter out that noise.",
        xref="paper", yref="paper", x=0.5, y=-0.25,
        showarrow=False, font={"size": 11, "color": rh_gray},
    )
    staleness_html = fig.to_html(full_html=False, include_plotlyjs=False)
    charts.append({"html": staleness_html, "full_width": False})

    # Sunburst: repo type → subgroup
    type_colors = {
        "Code": rh_blue,
        "PyPI index": rh_purple,
        "Wheel cache": rh_orange,
        "Mirror": rh_green,
        "Archived": rh_gray,
    }

    group_paths = {r.group_path for r in repos}
    group_path = next(iter(group_paths)) if len(group_paths) == 1 else ""

    type_subgroup_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in repos:
        label = _repo_type_label(r)
        subgroup = extract_subgroup(r.path, r.repo_type, group_path)
        type_subgroup_counts[label][subgroup] += 1

    ids = [""]
    labels = ["All"]
    parents = [""]
    values = [0]
    colors = ["rgba(0,0,0,0)"]
    custom_repo_type = [""]
    custom_subgroup = [""]

    for type_label in REPO_TYPE_LABELS.values():
        if type_label not in type_subgroup_counts:
            continue
        subgroups = type_subgroup_counts[type_label]
        type_total = sum(subgroups.values())
        type_id = type_label
        ids.append(type_id)
        labels.append(type_label)
        parents.append("")
        values.append(type_total)
        colors.append(type_colors.get(type_label, rh_gray))
        custom_repo_type.append(REPO_TYPE_KEYS.get(type_label, type_label))
        custom_subgroup.append("")

        for subgroup_name, count in sorted(subgroups.items(), key=lambda x: -x[1]):
            sub_id = f"{type_label}/{subgroup_name}"
            ids.append(sub_id)
            labels.append(subgroup_name)
            parents.append(type_id)
            values.append(count)
            colors.append(type_colors.get(type_label, rh_gray))
            custom_repo_type.append(REPO_TYPE_KEYS.get(type_label, type_label))
            custom_subgroup.append(subgroup_name)

    fig = go.Figure(data=[go.Sunburst(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        marker={"colors": colors},
        customdata=list(zip(custom_repo_type, custom_subgroup, strict=False)),
        hovertemplate="<b>%{label}</b><br>%{value} repos<extra></extra>",
    )])
    fig.update_layout(
        title="Repository Types", height=500,
        margin={"t": 40, "b": 20, "l": 20, "r": 20},
        **dark_layout,
    )
    sunburst_html = fig.to_html(full_html=False, include_plotlyjs=False, div_id="sunburst-chart")
    charts.append({"html": sunburst_html, "full_width": False})

    return charts


def _build_rows(repos: list[RepoData]) -> list[dict]:
    """Build table row data for the template."""
    group_paths = {r.group_path for r in repos}
    group_path = next(iter(group_paths)) if len(group_paths) == 1 else ""

    rows = []
    for r in repos:
        days = _days_since(r.last_activity_at)
        css_class = ""
        if r.archived:
            css_class = "archived"
        elif days is not None and days >= 365:
            css_class = "stale"

        subgroup = extract_subgroup(r.path, r.repo_type, group_path)

        rows.append({
            "css_class": css_class,
            "name": r.name,
            "web_url": r.web_url,
            "visibility": r.visibility,
            "last_activity": r.last_activity_at.strftime("%Y-%m-%d") if r.last_activity_at else "—",
            "last_activity_sort": r.last_activity_at.isoformat() if r.last_activity_at else "",
            "repo_type": _repo_type_label(r),
            "repo_type_key": r.repo_type,
            "subgroup": subgroup,
        })
    return rows


def generate_csv(repos: list[RepoData], output: TextIO) -> None:
    """Write repos as CSV."""
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for repo in repos:
        row = repo.model_dump()
        row["topics"] = ", ".join(repo.topics)
        writer.writerow({k: row.get(k, "") for k in CSV_COLUMNS})


def generate_html(repos: list[RepoData]) -> str:
    """Generate a self-contained HTML report with Plotly charts."""
    now = datetime.now(UTC)

    code_repos = [r for r in repos if r.repo_type == "code"]
    active = sum(
        1 for r in code_repos
        if _days_since(r.last_activity_at) is not None
        and _days_since(r.last_activity_at) < 90  # type: ignore[operator]
    )
    stale = sum(
        1 for r in code_repos
        if _days_since(r.last_activity_at) is not None
        and _days_since(r.last_activity_at) >= 365  # type: ignore[operator]
    )
    stats = [
        {"value": len(repos), "label": "Total repos"},
        {"value": len(code_repos), "label": "Code repos"},
        {"value": active, "label": "Active code (90d)"},
        {"value": stale, "label": "Stale code (>1y)"},
        {"value": sum(1 for r in repos if r.archived), "label": "Archived"},
    ]

    charts = _build_charts(repos)
    rows = _build_rows(repos)

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
