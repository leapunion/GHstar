#!/usr/bin/env python3
"""Generate daily GitHub Top Star reports for AI, agents, commerce, and enterprise OS."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PUBLIC = ROOT / "public"
DATA_DIR = PUBLIC / "data"
DEFAULT_DB = Path(os.environ.get("GHSTAR_DB", ROOT / "data" / "ghstar.sqlite"))

FOCUS_AREAS = {
    "AI Agent Framework": [
        "agent",
        "multi-agent",
        "autonomous agent",
        "tool calling",
        "workflow",
        "llm app",
    ],
    "Agentic Enterprise": [
        "enterprise",
        "workflow automation",
        "rag",
        "knowledge base",
        "copilot",
        "orchestration",
    ],
    "AI Commerce": [
        "commerce",
        "ecommerce",
        "shopping",
        "retail",
        "recommendation",
        "product search",
    ],
    "AI Infrastructure": [
        "inference",
        "vector database",
        "embedding",
        "observability",
        "evaluation",
        "deployment",
    ],
}

SEARCH_QUERIES = [
    'agent language:Python',
    'multi-agent',
    'llm agent',
    'autonomous agent',
    'ai workflow',
    'rag agent',
    'agentic enterprise',
    'ai ecommerce',
    'ai commerce',
    'retail ai',
    'recommendation system ai',
    'product search ai',
    'copilot enterprise',
    'tool calling llm',
    'ai evaluation',
]


@dataclass
class Repo:
    name: str
    full_name: str
    owner: str
    url: str
    description: str
    language: str
    stars: int
    forks: int
    topics: list[str]
    created_at: str
    updated_at: str
    pushed_at: str
    category: str
    relevance: int
    modules: list[str]
    scenarios: list[str]
    commerce_score: int
    enterprise_score: int
    strategic_score: int
    action_level: str
    leap_commerce: str
    leap_enterprise: str


def github_get(path: str, token: str | None) -> dict[str, Any]:
    url = f"https://api.github.com{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "leapunion-ghstar",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def search_repos(query: str, since: date, token: str | None, per_page: int, mode: str) -> list[dict[str, Any]]:
    if mode == "created":
        q = f"{query} created:>={since.isoformat()}"
    elif mode == "active":
        q = f"{query} pushed:>={since.isoformat()} stars:>50"
    else:
        q = query
    params = urllib.parse.urlencode(
        {
            "q": q,
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
        }
    )
    try:
        data = github_get(f"/search/repositories?{params}", token)
    except urllib.error.HTTPError as exc:
        print(f"warn: GitHub query failed: {q}: {exc}", file=sys.stderr)
        return []
    return data.get("items", [])


def words(repo: dict[str, Any]) -> str:
    bits = [
        repo.get("name") or "",
        repo.get("full_name") or "",
        repo.get("description") or "",
        " ".join(repo.get("topics") or []),
        repo.get("language") or "",
    ]
    return " ".join(bits).lower()


def repo_owner(repo: dict[str, Any]) -> str:
    owner = repo.get("owner")
    if isinstance(owner, dict):
        return owner.get("login") or ""
    return str(owner or "")


def repo_url(repo: dict[str, Any]) -> str:
    return repo.get("html_url") or repo.get("url") or ""


def repo_stars(repo: dict[str, Any]) -> int:
    return int(repo.get("stargazers_count") or repo.get("stars") or 0)


def repo_forks(repo: dict[str, Any]) -> int:
    return int(repo.get("forks_count") or repo.get("forks") or 0)


def classify(repo: dict[str, Any]) -> tuple[str, int]:
    text = words(repo)
    scores: dict[str, int] = {}
    for category, keywords in FOCUS_AREAS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        scores[category] = score
    category = max(scores, key=scores.get)
    base = scores[category]
    topic_bonus = min(len(repo.get("topics") or []), 6)
    star_bonus = min(repo_stars(repo) // 100, 10)
    freshness_bonus = 3 if repo.get("pushed_at", "")[:10] >= (date.today() - timedelta(days=7)).isoformat() else 0
    return category, base * 10 + topic_bonus + star_bonus + freshness_bonus


def infer_modules(repo: dict[str, Any], category: str) -> list[str]:
    text = words(repo)
    modules = []
    if any(k in text for k in ["agent", "workflow", "orchestration"]):
        modules.extend(["Agent runtime", "Workflow orchestration", "Tool integration"])
    if any(k in text for k in ["rag", "knowledge", "vector", "embedding"]):
        modules.extend(["Knowledge retrieval", "Vector search", "Grounding layer"])
    if any(k in text for k in ["eval", "benchmark", "observability"]):
        modules.extend(["Evaluation harness", "Telemetry", "Quality gates"])
    if any(k in text for k in ["commerce", "retail", "shopping", "recommendation", "product"]):
        modules.extend(["Product intelligence", "Recommendation engine", "Commerce workflow"])
    if not modules:
        modules = [category, "Core library", "Integration surface"]
    return list(dict.fromkeys(modules))[:5]


def infer_scenarios(repo: dict[str, Any], category: str) -> list[str]:
    text = words(repo)
    scenarios = []
    if "agent" in text:
        scenarios.append("Build task-oriented AI agents with tool use and planning.")
    if any(k in text for k in ["commerce", "retail", "shopping", "product"]):
        scenarios.append("Improve AI shopping discovery, product comparison, and conversion assistance.")
    if any(k in text for k in ["enterprise", "workflow", "copilot"]):
        scenarios.append("Automate enterprise workflows and internal knowledge operations.")
    if any(k in text for k in ["rag", "knowledge", "vector"]):
        scenarios.append("Ground agent answers with private knowledge and searchable evidence.")
    if not scenarios:
        scenarios.append(f"Track as a {category.lower()} reference for platform capability planning.")
    return scenarios[:4]


def leap_notes(repo: dict[str, Any], category: str, modules: list[str]) -> tuple[str, str]:
    module_text = ", ".join(modules[:3]).lower()
    commerce = (
        "Useful for Leap Agent Commerce OS as a reference for product discovery, shopping copilots, "
        "merchant automation, or conversion-oriented agent workflows."
        if "commerce" in category.lower() or any(k in module_text for k in ["product", "recommendation", "commerce"])
        else "Review for reusable agent runtime, retrieval, or evaluation patterns that can strengthen commerce agents."
    )
    enterprise = (
        "Useful for Leap Agentic Enterprise OS as a pattern for workflow orchestration, enterprise copilots, "
        "knowledge automation, permissions, and operational governance."
        if "enterprise" in category.lower() or any(k in module_text for k in ["workflow", "knowledge", "tool"])
        else "Review for infrastructure and quality-gate ideas that can improve enterprise agent reliability."
    )
    return commerce, enterprise


def rubric_scores(repo: dict[str, Any], category: str, modules: list[str], relevance: int) -> tuple[int, int, int, str]:
    text = words(repo)
    module_text = " ".join(modules).lower()
    commerce_hits = [
        any(k in text for k in ["shopping", "shopper", "checkout", "comparison", "recommendation"]),
        any(k in text for k in ["merchant", "catalog", "merchandising", "retail", "support"]),
        any(k in text for k in ["product", "price", "pricing", "inventory", "review"]),
        any(k in module_text for k in ["agent runtime", "workflow", "tool integration", "commerce workflow"]),
        any(k in module_text for k in ["evaluation", "telemetry", "quality", "grounding"]),
    ]
    enterprise_hits = [
        any(k in text for k in ["workflow", "orchestration", "handoff", "automation"]),
        any(k in text for k in ["knowledge", "rag", "document", "retrieval", "vector"]),
        any(k in text for k in ["connector", "integration", "api", "sdk", "tool"]),
        any(k in text for k in ["permission", "audit", "policy", "governance", "approval"]),
        any(k in module_text for k in ["evaluation", "telemetry", "quality", "deployment"]),
    ]
    commerce_score = sum(3 if hit else 0 for hit in commerce_hits)
    enterprise_score = sum(3 if hit else 0 for hit in enterprise_hits)
    if category == "AI Commerce":
        commerce_score = min(15, commerce_score + 3)
    if category == "Agentic Enterprise":
        enterprise_score = min(15, enterprise_score + 3)
    maturity = min(repo_stars(repo) // 250, 8)
    freshness = 4 if repo.get("pushed_at", "")[:10] >= (date.today() - timedelta(days=14)).isoformat() else 0
    strategic_score = min(100, relevance + commerce_score * 2 + enterprise_score * 2 + maturity + freshness)
    if strategic_score >= 80:
        action = "strategic watch"
    elif strategic_score >= 65:
        action = "prototype pattern"
    elif strategic_score >= 50:
        action = "clone and test"
    elif strategic_score >= 35:
        action = "read docs"
    elif strategic_score >= 20:
        action = "monitor"
    else:
        action = "ignore"
    return commerce_score, enterprise_score, strategic_score, action


def normalize_repo(item: dict[str, Any]) -> Repo:
    category, relevance = classify(item)
    modules = infer_modules(item, category)
    scenarios = infer_scenarios(item, category)
    commerce, enterprise = leap_notes(item, category, modules)
    commerce_score, enterprise_score, strategic_score, action_level = rubric_scores(item, category, modules, relevance)
    return Repo(
        name=item.get("name") or "",
        full_name=item.get("full_name") or "",
        owner=repo_owner(item),
        url=repo_url(item),
        description=item.get("description") or "No description provided.",
        language=item.get("language") or "Unknown",
        stars=repo_stars(item),
        forks=repo_forks(item),
        topics=list(item.get("topics") or []),
        created_at=item.get("created_at") or "",
        updated_at=item.get("updated_at") or "",
        pushed_at=item.get("pushed_at") or "",
        category=category,
        relevance=relevance,
        modules=modules,
        scenarios=scenarios,
        commerce_score=commerce_score,
        enterprise_score=enterprise_score,
        strategic_score=strategic_score,
        action_level=action_level,
        leap_commerce=commerce,
        leap_enterprise=enterprise,
    )


def collect(days: int, limit: int, token: str | None) -> list[Repo]:
    since = date.today() - timedelta(days=days)
    seen: dict[str, dict[str, Any]] = {}
    for query in SEARCH_QUERIES:
        for mode in ("created", "active"):
            for item in search_repos(query, since, token, per_page=limit, mode=mode):
                full_name = item.get("full_name")
                if not full_name:
                    continue
                current = seen.get(full_name)
                if current is None or item.get("stargazers_count", 0) > current.get("stargazers_count", 0):
                    item["_radar_mode"] = mode
                    seen[full_name] = item
    repos = [normalize_repo(item) for item in seen.values()]
    repos.sort(key=lambda repo: (repo.relevance, repo.stars), reverse=True)
    return repos[:limit]


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        PRAGMA journal_mode = DELETE;

        CREATE TABLE IF NOT EXISTS repositories (
          full_name TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          owner TEXT NOT NULL,
          url TEXT NOT NULL,
          description TEXT NOT NULL,
          language TEXT NOT NULL,
          topics_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          pushed_at TEXT NOT NULL,
          first_seen_date TEXT NOT NULL,
          last_seen_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS repo_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          full_name TEXT NOT NULL,
          snapshot_date TEXT NOT NULL,
          stars INTEGER NOT NULL,
          forks INTEGER NOT NULL,
          category TEXT NOT NULL,
          relevance INTEGER NOT NULL,
          commerce_score INTEGER NOT NULL,
          enterprise_score INTEGER NOT NULL,
          strategic_score INTEGER NOT NULL,
          action_level TEXT NOT NULL,
          modules_json TEXT NOT NULL,
          scenarios_json TEXT NOT NULL,
          leap_commerce TEXT NOT NULL,
          leap_enterprise TEXT NOT NULL,
          UNIQUE(full_name, snapshot_date),
          FOREIGN KEY(full_name) REFERENCES repositories(full_name)
        );

        CREATE TABLE IF NOT EXISTS daily_reports (
          report_date TEXT PRIMARY KEY,
          repo_count INTEGER NOT NULL,
          markdown_path TEXT NOT NULL,
          html_path TEXT NOT NULL,
          json_path TEXT NOT NULL,
          generated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS leap_notes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          full_name TEXT NOT NULL,
          note_date TEXT NOT NULL,
          commerce_learning TEXT NOT NULL,
          enterprise_learning TEXT NOT NULL,
          follow_up_status TEXT NOT NULL DEFAULT 'new',
          human_notes TEXT NOT NULL DEFAULT '',
          UNIQUE(full_name, note_date),
          FOREIGN KEY(full_name) REFERENCES repositories(full_name)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_date_score
          ON repo_snapshots(snapshot_date, strategic_score DESC, stars DESC);
        CREATE INDEX IF NOT EXISTS idx_snapshots_repo_date
          ON repo_snapshots(full_name, snapshot_date);
        """
    )
    return conn


def save_to_db(conn: sqlite3.Connection, repos: list[Repo], report_date: date) -> None:
    today = report_date.isoformat()
    for repo in repos:
        conn.execute(
            """
            INSERT INTO repositories (
              full_name, name, owner, url, description, language, topics_json,
              created_at, updated_at, pushed_at, first_seen_date, last_seen_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name) DO UPDATE SET
              name = excluded.name,
              owner = excluded.owner,
              url = excluded.url,
              description = excluded.description,
              language = excluded.language,
              topics_json = excluded.topics_json,
              updated_at = excluded.updated_at,
              pushed_at = excluded.pushed_at,
              last_seen_date = excluded.last_seen_date
            """,
            (
                repo.full_name,
                repo.name,
                repo.owner,
                repo.url,
                repo.description,
                repo.language,
                json.dumps(repo.topics, ensure_ascii=False),
                repo.created_at,
                repo.updated_at,
                repo.pushed_at,
                today,
                today,
            ),
        )
        conn.execute(
            """
            INSERT INTO repo_snapshots (
              full_name, snapshot_date, stars, forks, category, relevance,
              commerce_score, enterprise_score, strategic_score, action_level,
              modules_json, scenarios_json, leap_commerce, leap_enterprise
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name, snapshot_date) DO UPDATE SET
              stars = excluded.stars,
              forks = excluded.forks,
              category = excluded.category,
              relevance = excluded.relevance,
              commerce_score = excluded.commerce_score,
              enterprise_score = excluded.enterprise_score,
              strategic_score = excluded.strategic_score,
              action_level = excluded.action_level,
              modules_json = excluded.modules_json,
              scenarios_json = excluded.scenarios_json,
              leap_commerce = excluded.leap_commerce,
              leap_enterprise = excluded.leap_enterprise
            """,
            (
                repo.full_name,
                today,
                repo.stars,
                repo.forks,
                repo.category,
                repo.relevance,
                repo.commerce_score,
                repo.enterprise_score,
                repo.strategic_score,
                repo.action_level,
                json.dumps(repo.modules, ensure_ascii=False),
                json.dumps(repo.scenarios, ensure_ascii=False),
                repo.leap_commerce,
                repo.leap_enterprise,
            ),
        )
        conn.execute(
            """
            INSERT INTO leap_notes (
              full_name, note_date, commerce_learning, enterprise_learning, follow_up_status
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(full_name, note_date) DO UPDATE SET
              commerce_learning = excluded.commerce_learning,
              enterprise_learning = excluded.enterprise_learning
            """,
            (repo.full_name, today, repo.leap_commerce, repo.leap_enterprise, repo.action_level),
        )
    conn.commit()


def load_report_repos(conn: sqlite3.Connection, report_date: date, limit: int) -> list[Repo]:
    rows = conn.execute(
        """
        SELECT
          r.name, r.full_name, r.owner, r.url, r.description, r.language,
          r.topics_json, r.created_at, r.updated_at, r.pushed_at,
          s.stars, s.forks, s.category, s.relevance, s.commerce_score,
          s.enterprise_score, s.strategic_score, s.action_level,
          s.modules_json, s.scenarios_json, s.leap_commerce, s.leap_enterprise
        FROM repo_snapshots s
        JOIN repositories r ON r.full_name = s.full_name
        WHERE s.snapshot_date = ?
        ORDER BY s.strategic_score DESC, s.relevance DESC, s.stars DESC
        LIMIT ?
        """,
        (report_date.isoformat(), limit),
    ).fetchall()
    return [
        Repo(
            name=row["name"],
            full_name=row["full_name"],
            owner=row["owner"],
            url=row["url"],
            description=row["description"],
            language=row["language"],
            stars=row["stars"],
            forks=row["forks"],
            topics=json.loads(row["topics_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            pushed_at=row["pushed_at"],
            category=row["category"],
            relevance=row["relevance"],
            modules=json.loads(row["modules_json"]),
            scenarios=json.loads(row["scenarios_json"]),
            commerce_score=row["commerce_score"],
            enterprise_score=row["enterprise_score"],
            strategic_score=row["strategic_score"],
            action_level=row["action_level"],
            leap_commerce=row["leap_commerce"],
            leap_enterprise=row["leap_enterprise"],
        )
        for row in rows
    ]


def save_daily_report_record(conn: sqlite3.Connection, report_date: date, repo_count: int) -> None:
    conn.execute(
        """
        INSERT INTO daily_reports (
          report_date, repo_count, markdown_path, html_path, json_path, generated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(report_date) DO UPDATE SET
          repo_count = excluded.repo_count,
          markdown_path = excluded.markdown_path,
          html_path = excluded.html_path,
          json_path = excluded.json_path,
          generated_at = excluded.generated_at
        """,
        (
            report_date.isoformat(),
            repo_count,
            f"reports/{report_date.isoformat()}.md",
            "public/index.html",
            "public/data/latest.json",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def history_summary(conn: sqlite3.Connection, limit: int = 30) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT report_date, repo_count, markdown_path, html_path, json_path, generated_at
        FROM daily_reports
        ORDER BY report_date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(repos: list[Repo], report_date: date) -> str:
    lines = [
        f"# GitHub Top Star AI & Agent Report - {report_date.isoformat()}",
        "",
        "Focus: AI agents, Agentic Enterprise, AI commerce, AI infrastructure, and ideas relevant to Leap Agent Commerce OS / Leap Agentic Enterprise OS.",
        "",
        "## Executive Summary",
        "",
        f"- Repositories reviewed: {len(repos)}",
        f"- Top category: {repos[0].category if repos else 'N/A'}",
        "- Method: GitHub Search API, recently created and recently active repositories, sorted by stars and Leap relevance.",
        "",
        "## Repository Table",
        "",
        "| Repository | Author | Stars | Category | Strategic | Action | URL |",
        "| --- | --- | ---: | --- | ---: | --- | --- |",
    ]
    for repo in repos:
        lines.append(
            f"| {md_escape(repo.name)} | {md_escape(repo.owner)} | {repo.stars} | {repo.category} | {repo.strategic_score} | {repo.action_level} | {repo.url} |"
        )
    lines.extend(["", "## Detailed Notes", ""])
    for index, repo in enumerate(repos, 1):
        lines.extend(
            [
                f"### {index}. {repo.full_name}",
                "",
                f"- URL: {repo.url}",
                f"- Author: {repo.owner}",
                f"- Language: {repo.language}",
                f"- Stars: {repo.stars}",
                f"- Forks: {repo.forks}",
                f"- Function category: {repo.category}",
                f"- Relevance score: {repo.relevance}",
                f"- Commerce score: {repo.commerce_score}/15",
                f"- Enterprise score: {repo.enterprise_score}/15",
                f"- Strategic score: {repo.strategic_score}/100",
                f"- Recommended action: {repo.action_level}",
                f"- Description: {repo.description}",
                f"- Topics: {', '.join(repo.topics) if repo.topics else 'N/A'}",
                "",
                "#### Modules",
                "",
                *[f"- {module}" for module in repo.modules],
                "",
                "#### Application Scenarios",
                "",
                *[f"- {scenario}" for scenario in repo.scenarios],
                "",
                "#### Leap Agent Commerce OS Learning",
                "",
                repo.leap_commerce,
                "",
                "#### Leap Agentic Enterprise OS Learning",
                "",
                repo.leap_enterprise,
                "",
            ]
        )
    return "\n".join(lines)


def category_counts(repos: list[Repo]) -> dict[str, int]:
    counts = {category: 0 for category in FOCUS_AREAS}
    for repo in repos:
        counts[repo.category] = counts.get(repo.category, 0) + 1
    return counts


def slug(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "repo"


def render_html(repos: list[Repo], report_date: date) -> str:
    counts = category_counts(repos)
    max_count = max(counts.values() or [1])
    top = repos[:8]
    data_json = html.escape(json.dumps([repo.__dict__ for repo in repos], ensure_ascii=False))
    category_cards = "\n".join(
        f"""
        <article class="metric">
          <span>{html.escape(category)}</span>
          <strong>{count}</strong>
          <div class="bar"><i style="width:{(count / max_count * 100) if max_count else 0:.1f}%"></i></div>
        </article>
        """
        for category, count in counts.items()
    )
    repo_cards = "\n".join(render_repo_card(repo, index) for index, repo in enumerate(top, 1))
    max_strategic = max([repo.strategic_score for repo in repos] or [1])
    score_rows = "\n".join(
        f"""
        <div class="score-row">
          <span>{html.escape(repo.full_name)}</span>
          <b>{repo.strategic_score}</b>
          <i style="width:{repo.strategic_score / max_strategic * 100:.1f}%"></i>
        </div>
        """
        for repo in top
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GHstar AI & Agent Report - {report_date.isoformat()}</title>
    <link rel="stylesheet" href="./assets/styles.css">
  </head>
  <body>
    <header class="hero">
      <div>
        <p class="eyebrow">LeapUnion Daily GitHub Intelligence</p>
        <h1>AI, Agent, Commerce, and Enterprise Top Star Radar</h1>
        <p class="sub">Daily repository digest with platform learning for Leap Agent Commerce OS and Leap Agentic Enterprise OS.</p>
      </div>
      <time>{report_date.isoformat()}</time>
    </header>

    <main>
      <section class="metrics">
        <article class="metric primary">
          <span>Repositories Reviewed</span>
          <strong>{len(repos)}</strong>
          <div class="bar"><i style="width:100%"></i></div>
        </article>
        {category_cards}
      </section>

      <section class="panel">
        <div class="section-head">
          <h2>Capability Map</h2>
          <p>How today's repositories map into Leap platform building blocks.</p>
        </div>
        <div class="architecture">
          <div>GitHub Top Star Sources</div>
          <span></span>
          <div>AI / Agent Classification</div>
          <span></span>
          <div>Module Extraction</div>
          <span></span>
          <div>Leap OS Learning</div>
        </div>
      </section>

      <section class="panel">
        <div class="section-head">
          <h2>Strategic Relevance</h2>
          <p>Weighted by relevance, Leap OS fit, maturity, and freshness.</p>
        </div>
        <div class="score-chart">
          {score_rows}
        </div>
      </section>

      <section class="panel">
        <div class="section-head">
          <h2>Daily Workflow</h2>
          <p>Automated collection, analysis, publication, and Vercel deployment path.</p>
        </div>
        <div class="flow">
          <div><b>1</b><span>Search GitHub</span></div>
          <div><b>2</b><span>Rank by stars and relevance</span></div>
          <div><b>3</b><span>Generate Markdown and HTML</span></div>
          <div><b>4</b><span>Commit to GHstar</span></div>
          <div><b>5</b><span>Deploy on Vercel</span></div>
        </div>
      </section>

      <section class="panel">
        <div class="section-head">
          <h2>Top Repositories</h2>
          <p>Highest priority repositories for review and learning.</p>
        </div>
        <div class="repo-grid">
          {repo_cards}
        </div>
      </section>

      <section class="panel">
        <div class="section-head">
          <h2>Raw Data</h2>
          <p>Machine-readable payload for downstream agents and dashboards.</p>
        </div>
        <pre id="raw-data">{data_json}</pre>
      </section>
    </main>
  </body>
</html>
"""


def render_repo_card(repo: Repo, index: int) -> str:
    module_items = "".join(f"<li>{html.escape(module)}</li>" for module in repo.modules)
    scenario_items = "".join(f"<li>{html.escape(item)}</li>" for item in repo.scenarios)
    topic_items = "".join(f"<span>{html.escape(topic)}</span>" for topic in repo.topics[:6])
    return f"""
    <article class="repo-card" id="{slug(repo.full_name)}">
      <div class="repo-top">
        <span class="rank">#{index}</span>
        <span class="category">{html.escape(repo.category)}</span>
      </div>
      <h3><a href="{html.escape(repo.url)}">{html.escape(repo.full_name)}</a></h3>
      <p>{html.escape(repo.description)}</p>
      <div class="stats">
        <span>{repo.stars} stars</span>
        <span>{html.escape(repo.language)}</span>
        <span>{repo.forks} forks</span>
        <span>{repo.strategic_score} strategic</span>
        <span>{html.escape(repo.action_level)}</span>
      </div>
      <div class="mini-diagram">
        <div>Input</div><i></i><div>{html.escape(repo.category)}</div><i></i><div>Leap Pattern</div>
      </div>
      <h4>Modules</h4>
      <ul>{module_items}</ul>
      <h4>Application Scenarios</h4>
      <ul>{scenario_items}</ul>
      <h4>Leap Commerce OS</h4>
      <p>{html.escape(repo.leap_commerce)}</p>
      <h4>Leap Enterprise OS</h4>
      <p>{html.escape(repo.leap_enterprise)}</p>
      <div class="topics">{topic_items}</div>
    </article>
    """


def write_outputs(repos: list[Repo], report_date: date, history: list[dict[str, Any]] | None = None) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    md = render_markdown(repos, report_date)
    html_doc = render_html(repos, report_date)
    data = [repo.__dict__ for repo in repos]

    (REPORTS / f"{report_date.isoformat()}.md").write_text(md, encoding="utf-8")
    (PUBLIC / "index.html").write_text(html_doc, encoding="utf-8")
    (PUBLIC / "latest.md").write_text(md, encoding="utf-8")
    (DATA_DIR / "latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if history is not None:
        (DATA_DIR / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate LeapUnion GHstar daily report.")
    parser.add_argument("--days", type=int, default=7, help="Lookback window for newly created repositories.")
    parser.add_argument("--limit", type=int, default=24, help="Maximum repositories to include.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Report date YYYY-MM-DD.")
    parser.add_argument("--fixture", help="Use local JSON fixture instead of GitHub API.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path.")
    parser.add_argument("--no-db", action="store_true", help="Generate files without writing SQLite history.")
    parser.add_argument("--from-db", action="store_true", help="Render outputs from existing SQLite snapshots.")
    args = parser.parse_args()

    report_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    if args.from_db:
        if args.no_db:
            raise SystemExit("--from-db cannot be combined with --no-db")
        with init_db(Path(args.db)) as conn:
            repos = load_report_repos(conn, report_date, args.limit)
            save_daily_report_record(conn, report_date, len(repos))
            write_outputs(repos, report_date, history_summary(conn))
        print(json.dumps({"date": report_date.isoformat(), "repos": len(repos)}, indent=2))
        return 0
    if args.fixture:
        fixture_data = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        repos = [normalize_repo(item) for item in fixture_data][: args.limit]
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        repos = collect(args.days, args.limit, token)
    if args.no_db:
        write_outputs(repos, report_date)
    else:
        with init_db(Path(args.db)) as conn:
            save_to_db(conn, repos, report_date)
            repos = load_report_repos(conn, report_date, args.limit)
            save_daily_report_record(conn, report_date, len(repos))
            write_outputs(repos, report_date, history_summary(conn))
    print(json.dumps({"date": report_date.isoformat(), "repos": len(repos)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
