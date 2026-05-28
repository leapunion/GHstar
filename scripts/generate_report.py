#!/usr/bin/env python3
"""Generate daily GitHub Top Star reports for AI, agents, commerce, and enterprise OS."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
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


def classify(repo: dict[str, Any]) -> tuple[str, int]:
    text = words(repo)
    scores: dict[str, int] = {}
    for category, keywords in FOCUS_AREAS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        scores[category] = score
    category = max(scores, key=scores.get)
    base = scores[category]
    topic_bonus = min(len(repo.get("topics") or []), 6)
    star_bonus = min(int(repo.get("stargazers_count", 0)) // 100, 10)
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
    maturity = min(int(repo.get("stargazers_count", 0)) // 250, 8)
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
        owner=(item.get("owner") or {}).get("login") or "",
        url=item.get("html_url") or "",
        description=item.get("description") or "No description provided.",
        language=item.get("language") or "Unknown",
        stars=int(item.get("stargazers_count") or 0),
        forks=int(item.get("forks_count") or 0),
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


def write_outputs(repos: list[Repo], report_date: date) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate LeapUnion GHstar daily report.")
    parser.add_argument("--days", type=int, default=7, help="Lookback window for newly created repositories.")
    parser.add_argument("--limit", type=int, default=24, help="Maximum repositories to include.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Report date YYYY-MM-DD.")
    parser.add_argument("--fixture", help="Use local JSON fixture instead of GitHub API.")
    args = parser.parse_args()

    report_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    if args.fixture:
        fixture_data = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        repos = [normalize_repo(item) for item in fixture_data][: args.limit]
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        repos = collect(args.days, args.limit, token)
    write_outputs(repos, report_date)
    print(json.dumps({"date": report_date.isoformat(), "repos": len(repos)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
