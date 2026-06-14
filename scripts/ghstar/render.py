"""Rendering: Markdown/HTML report generation, JSON payloads (trends/backlog), and write_outputs that fans the selected repos to disk."""
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
from ghstar.model import *  # noqa: F401,F403
from ghstar.enrich import *  # noqa: F401,F403

def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def distribution(repos: list[Repo], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for repo in repos:
        key = str(getattr(repo, attr) or "Unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def top_languages(repos: list[Repo], limit: int = 6) -> dict[str, int]:
    return dict(list(distribution(repos, "language").items())[:limit])


def action_counts(repos: list[Repo]) -> dict[str, int]:
    return distribution(repos, "action_level")


def active_counts(repos: list[Repo]) -> tuple[int, int]:
    active_7 = sum(1 for repo in repos if repo.days_since_push <= 7)
    active_30 = sum(1 for repo in repos if repo.days_since_push <= 30)
    return active_7, active_30


def top_by(repos: list[Repo], key: str) -> Repo | None:
    if not repos:
        return None
    return max(repos, key=lambda repo: getattr(repo, key))


def watchlist_flags(repos: list[Repo]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for repo in repos:
        for flag in repo.risk_flags:
            counts[flag] = counts.get(flag, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def backlog_items(repos: list[Repo]) -> list[dict[str, Any]]:
    priority_order = {
        "strategic watch": 5,
        "prototype pattern": 4,
        "clone and test": 3,
        "read docs": 2,
        "monitor": 1,
        "ignore": 0,
    }
    items = []
    for repo in repos:
        if repo.action_level == "ignore":
            continue
        items.append(
            {
                "full_name": repo.full_name,
                "url": repo.url,
                "category": repo.category,
                "subcategory": repo.subcategory,
                "action_level": repo.action_level,
                "priority": priority_order.get(repo.action_level, 0),
                "strategic_score": repo.strategic_score,
                "momentum_score": repo.momentum_score,
                "risk_flags": repo.risk_flags,
                "next_action": repo.follow_up_next_action,
                "suggested_owner": "product+engineering review",
            }
        )
    items.sort(key=lambda item: (item["priority"], item["strategic_score"], item["momentum_score"]), reverse=True)
    return items


def trend_payload(repos: list[Repo], report_date: date, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    active_7, active_30 = active_counts(repos)
    return {
        "report_date": report_date.isoformat(),
        "repo_count": len(repos),
        "active_7_days": active_7,
        "active_30_days": active_30,
        "category_distribution": category_counts(repos),
        "subcategory_distribution": distribution(repos, "subcategory"),
        "language_distribution": top_languages(repos, limit=10),
        "maturity_distribution": distribution(repos, "maturity_level"),
        "action_distribution": action_counts(repos),
        "watchlist_flags": watchlist_flags(repos),
        "top_momentum": [
            {
                "full_name": repo.full_name,
                "momentum_score": repo.momentum_score,
                "stars_per_day": repo.stars_per_day,
                "days_since_push": repo.days_since_push,
                "action_level": repo.action_level,
            }
            for repo in sorted(repos, key=lambda repo: repo.momentum_score, reverse=True)[:10]
        ],
        "history": history or [],
    }


def render_count_list(counts: dict[str, int]) -> list[str]:
    return [f"- {key}: {value}" for key, value in counts.items()] or ["- N/A"]


def render_markdown(repos: list[Repo], report_date: date, lookback_days: int = 90) -> str:
    active_7, active_30 = active_counts(repos)
    top_momentum = sorted(repos, key=lambda repo: repo.momentum_score, reverse=True)[:5]
    notable = top_by(repos, "strategic_score")
    commerce_pick = top_by([repo for repo in repos if repo.commerce_score > 0], "commerce_score")
    enterprise_pick = top_by([repo for repo in repos if repo.enterprise_score > 0], "enterprise_score")
    flag_counts = watchlist_flags(repos)
    backlog = backlog_items(repos)[:10]
    lines = [
        f"# GitHub Top Star AI & Agent 90-Day Radar - {report_date.isoformat()}",
        "",
        "Focus: AI agents, Agentic Enterprise, AI commerce, AI infrastructure, and ideas relevant to Leap Agent Commerce OS / Leap Agentic Enterprise OS.",
        "",
        "## Executive Summary",
        "",
        f"- Repositories reviewed: {len(repos)}",
        f"- Lookback window: {lookback_days} days",
        f"- Top category: {repos[0].category if repos else 'N/A'}",
        f"- Notable repository of the day: {notable.full_name if notable else 'N/A'}",
        f"- Leap Commerce OS signal: {commerce_pick.full_name if commerce_pick else 'N/A'}",
        f"- Agentic Enterprise OS signal: {enterprise_pick.full_name if enterprise_pick else 'N/A'}",
        f"- Active in last 7 days: {active_7}",
        f"- Active in last 30 days: {active_30}",
        f"- Watchlist flags: {', '.join(f'{key} ({value})' for key, value in list(flag_counts.items())[:4]) if flag_counts else 'N/A'}",
        "- Method: GitHub Search API, recently created and recently active repositories, sorted by momentum, stars, and Leap relevance.",
        "",
        "## 90-Day Trend Signals",
        "",
        "### Category Distribution",
        "",
        *render_count_list(category_counts(repos)),
        "",
        "### Language Distribution",
        "",
        *render_count_list(top_languages(repos)),
        "",
        "### Maturity Distribution",
        "",
        *render_count_list(distribution(repos, "maturity_level")),
        "",
        "### Action Distribution",
        "",
        *render_count_list(action_counts(repos)),
        "",
        "### Subcategory Distribution",
        "",
        *render_count_list(distribution(repos, "subcategory")),
        "",
        "### Watchlist Flags",
        "",
        *render_count_list(flag_counts),
        "",
        "### Top Momentum Repositories",
        "",
        "| Repository | Momentum | Stars/day | Days Since Push | Review |",
        "| --- | ---: | ---: | ---: | --- |",
        *[
            f"| {md_escape(repo.full_name)} | {repo.momentum_score} | {repo.stars_per_day:.2f} | {repo.days_since_push} | {md_escape(repo.repository_review)} |"
            for repo in top_momentum
        ],
        "",
        "## Follow-Up Backlog",
        "",
        "| Repository | Action | Priority | Subcategory | Risks | Next Step |",
        "| --- | --- | ---: | --- | --- | --- |",
        *[
            f"| {md_escape(item['full_name'])} | {item['action_level']} | {item['priority']} | {md_escape(item['subcategory'])} | {md_escape(', '.join(item['risk_flags']) or 'N/A')} | {md_escape(item['next_action'])} |"
            for item in backlog
        ],
        "",
        "## Repository Table",
        "",
        "| Repository | Author | Stars | Stars/day | Momentum | Category | Subcategory | Strategic | Action | URL |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- | --- |",
    ]
    for repo in repos:
        lines.append(
            f"| {md_escape(repo.name)} | {md_escape(repo.owner)} | {repo.stars} | {repo.stars_per_day:.2f} | {repo.momentum_score} | {repo.category} | {repo.subcategory} | {repo.strategic_score} | {repo.action_level} | {repo.url} |"
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
                f"- Age days: {repo.age_days}",
                f"- Days since push: {repo.days_since_push}",
                f"- Stars/day: {repo.stars_per_day:.2f}",
                f"- Fork ratio: {repo.fork_ratio:.4f}",
                f"- Momentum score: {repo.momentum_score}/100",
                f"- Maturity level: {repo.maturity_level}",
                f"- Function category: {repo.category}",
                f"- Subcategory: {repo.subcategory}",
                f"- Relevance score: {repo.relevance}",
                f"- Commerce score: {repo.commerce_score}/15",
                f"- Enterprise score: {repo.enterprise_score}/15",
                f"- Strategic score: {repo.strategic_score}/100",
                f"- Recommended action: {repo.action_level}",
                f"- Next action: {repo.follow_up_next_action}",
                f"- Risk flags: {', '.join(repo.risk_flags) if repo.risk_flags else 'N/A'}",
                f"- Description: {repo.description}",
                f"- Repository review: {repo.repository_review}",
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


def render_html(repos: list[Repo], report_date: date, lookback_days: int = 90) -> str:
    counts = category_counts(repos)
    subcategory_counts = distribution(repos, "subcategory")
    maturity_counts = distribution(repos, "maturity_level")
    language_counts = top_languages(repos)
    flag_counts = watchlist_flags(repos)
    max_count = max(counts.values() or [1])
    max_subcategory = max(subcategory_counts.values() or [1])
    max_maturity = max(maturity_counts.values() or [1])
    max_language = max(language_counts.values() or [1])
    max_flags = max(flag_counts.values() or [1])
    active_7, active_30 = active_counts(repos)
    top = repos[:8]
    top_momentum = sorted(repos, key=lambda repo: repo.momentum_score, reverse=True)[:8]
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
    subcategory_cards = "\n".join(
        f"""
        <div class="score-row compact">
          <span>{html.escape(subcategory)}</span>
          <b>{count}</b>
          <i style="width:{count / max_subcategory * 100:.1f}%"></i>
        </div>
        """
        for subcategory, count in subcategory_counts.items()
    )
    flag_cards = "\n".join(
        f"""
        <div class="score-row compact risk">
          <span>{html.escape(flag)}</span>
          <b>{count}</b>
          <i style="width:{count / max_flags * 100:.1f}%"></i>
        </div>
        """
        for flag, count in flag_counts.items()
    )
    maturity_cards = "\n".join(
        f"""
        <article class="metric">
          <span>{html.escape(level.title())}</span>
          <strong>{count}</strong>
          <div class="bar"><i style="width:{(count / max_maturity * 100) if max_maturity else 0:.1f}%"></i></div>
        </article>
        """
        for level, count in maturity_counts.items()
    )
    language_cards = "\n".join(
        f"""
        <div class="score-row compact">
          <span>{html.escape(language)}</span>
          <b>{count}</b>
          <i style="width:{count / max_language * 100:.1f}%"></i>
        </div>
        """
        for language, count in language_counts.items()
    )
    repo_cards = "\n".join(render_repo_card(repo, index) for index, repo in enumerate(top, 1))
    backlog_rows = "\n".join(render_backlog_row(item) for item in backlog_items(repos)[:16])
    category_options = "\n".join(
        f'<option value="{html.escape(category)}">{html.escape(category)}</option>' for category in counts
    )
    action_options = "\n".join(
        f'<option value="{html.escape(action)}">{html.escape(action)}</option>' for action in action_counts(repos)
    )
    max_strategic = max(1, max([repo.strategic_score for repo in repos] or [1]))
    max_momentum = max(1, max([repo.momentum_score for repo in repos] or [1]))
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
    momentum_rows = "\n".join(
        f"""
        <div class="score-row">
          <span>{html.escape(repo.full_name)} <em>{repo.stars_per_day:.1f} stars/day · {repo.days_since_push}d since push</em></span>
          <b>{repo.momentum_score}</b>
          <i style="width:{repo.momentum_score / max_momentum * 100:.1f}%"></i>
        </div>
        """
        for repo in top_momentum
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GHstar AI & Agent 90-Day Radar - {report_date.isoformat()}</title>
    <link rel="stylesheet" href="./assets/styles.css">
  </head>
  <body>
    <header class="hero">
      <div>
        <p class="eyebrow">LeapUnion Daily GitHub Intelligence</p>
        <h1>AI, Agent, Commerce, and Enterprise Top Star Radar</h1>
        <p class="sub">{lookback_days}-day repository radar with trend signals, repository reviews, and platform learning for Leap Agent Commerce OS and Leap Agentic Enterprise OS.</p>
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
        <article class="metric">
          <span>Lookback Days</span>
          <strong>{lookback_days}</strong>
          <div class="bar"><i style="width:100%"></i></div>
        </article>
        <article class="metric">
          <span>Active in 7 Days</span>
          <strong>{active_7}</strong>
          <div class="bar"><i style="width:{(active_7 / len(repos) * 100) if repos else 0:.1f}%"></i></div>
        </article>
        <article class="metric">
          <span>Active in 30 Days</span>
          <strong>{active_30}</strong>
          <div class="bar"><i style="width:{(active_30 / len(repos) * 100) if repos else 0:.1f}%"></i></div>
        </article>
        {category_cards}
      </section>

      <section class="panel">
        <div class="section-head">
          <h2>90-Day Trend Signals</h2>
          <p>Momentum combines star velocity, recent pushes, fork ratio, and Leap strategic fit.</p>
        </div>
        <div class="trend-grid">
          <div>
            <h3>Momentum Leaders</h3>
            <div class="score-chart">{momentum_rows}</div>
          </div>
          <div>
            <h3>Language Mix</h3>
            <div class="score-chart">{language_cards}</div>
          </div>
          <div>
            <h3>Subcategory Mix</h3>
            <div class="score-chart">{subcategory_cards}</div>
          </div>
          <div>
            <h3>Watchlist Flags</h3>
            <div class="score-chart">{flag_cards}</div>
          </div>
        </div>
      </section>

      <section class="metrics">
        {maturity_cards}
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
          <h2>Follow-Up Backlog</h2>
          <p>Actionable queue generated from strategic score, momentum, and risk signals.</p>
        </div>
        <div class="backlog-table">
          <div class="backlog-head"><span>Repository</span><span>Action</span><span>Priority</span><span>Next Step</span></div>
          {backlog_rows}
        </div>
      </section>

      <section class="panel">
        <div class="section-head">
          <h2>Top Repositories</h2>
          <p>Highest priority repositories for review and learning.</p>
        </div>
        <div class="filters">
          <label>Category
            <select id="category-filter">
              <option value="">All</option>
              {category_options}
            </select>
          </label>
          <label>Action
            <select id="action-filter">
              <option value="">All</option>
              {action_options}
            </select>
          </label>
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
    <script>
      const categoryFilter = document.querySelector("#category-filter");
      const actionFilter = document.querySelector("#action-filter");
      const cards = Array.from(document.querySelectorAll(".repo-card"));
      function applyFilters() {{
        const category = categoryFilter.value;
        const action = actionFilter.value;
        cards.forEach((card) => {{
          const matchesCategory = !category || card.dataset.category === category;
          const matchesAction = !action || card.dataset.action === action;
          card.hidden = !(matchesCategory && matchesAction);
        }});
      }}
      categoryFilter.addEventListener("change", applyFilters);
      actionFilter.addEventListener("change", applyFilters);
    </script>
  </body>
</html>
"""


def render_repo_card(repo: Repo, index: int) -> str:
    module_items = "".join(f"<li>{html.escape(module)}</li>" for module in repo.modules)
    scenario_items = "".join(f"<li>{html.escape(item)}</li>" for item in repo.scenarios)
    topic_items = "".join(f"<span>{html.escape(topic)}</span>" for topic in repo.topics[:6])
    risk_items = "".join(f"<span>{html.escape(flag)}</span>" for flag in repo.risk_flags)
    return f"""
    <article class="repo-card" id="{slug(repo.full_name)}" data-category="{html.escape(repo.category)}" data-action="{html.escape(repo.action_level)}">
      <div class="repo-top">
        <span class="rank">#{index}</span>
        <span class="category">{html.escape(repo.category)}</span>
        <span class="category">{html.escape(repo.subcategory)}</span>
      </div>
      <h3><a href="{html.escape(repo.url)}">{html.escape(repo.full_name)}</a></h3>
      <p>{html.escape(repo.description)}</p>
      <div class="stats">
        <span>{repo.stars} stars</span>
        <span>{repo.stars_per_day:.1f} stars/day</span>
        <span>{repo.momentum_score} momentum</span>
        <span>{html.escape(repo.maturity_level)}</span>
        <span>{repo.days_since_push}d since push</span>
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
      <h4>Repository Review</h4>
      <p>{html.escape(repo.repository_review)}</p>
      <h4>Next Action</h4>
      <p>{html.escape(repo.follow_up_next_action)}</p>
      <h4>Risk Flags</h4>
      <div class="topics risks">{risk_items or '<span>N/A</span>'}</div>
      <h4>Leap Commerce OS</h4>
      <p>{html.escape(repo.leap_commerce)}</p>
      <h4>Leap Enterprise OS</h4>
      <p>{html.escape(repo.leap_enterprise)}</p>
      <div class="topics">{topic_items}</div>
    </article>
    """


def render_backlog_row(item: dict[str, Any]) -> str:
    risks = ", ".join(item["risk_flags"]) or "N/A"
    return f"""
    <div class="backlog-row">
      <span><a href="{html.escape(item['url'])}">{html.escape(item['full_name'])}</a><em>{html.escape(item['subcategory'])} · {html.escape(risks)}</em></span>
      <b>{html.escape(item['action_level'])}</b>
      <strong>{item['priority']}</strong>
      <span>{html.escape(item['next_action'])}</span>
    </div>
    """


def write_outputs(
    repos: list[Repo],
    report_date: date,
    history: list[dict[str, Any]] | None = None,
    lookback_days: int = 90,
) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    md = "\n".join(line.rstrip() for line in render_markdown(repos, report_date, lookback_days).splitlines()) + "\n"
    html_doc = "\n".join(line.rstrip() for line in render_html(repos, report_date, lookback_days).splitlines()) + "\n"
    data = [repo.__dict__ for repo in repos]
    history_payload = history or []
    backlog = backlog_items(repos)
    trends = trend_payload(repos, report_date, history_payload)

    (REPORTS / f"{report_date.isoformat()}.md").write_text(md, encoding="utf-8")
    (PUBLIC / "report.html").write_text(html_doc, encoding="utf-8")
    (PUBLIC / "latest.md").write_text(md, encoding="utf-8")
    (DATA_DIR / "latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (DATA_DIR / "backlog.json").write_text(json.dumps(backlog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (DATA_DIR / "trends.json").write_text(json.dumps(trends, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if history is not None:
        (DATA_DIR / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
