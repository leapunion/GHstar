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
    subcategory: str
    relevance: int
    modules: list[str]
    scenarios: list[str]
    risk_flags: list[str]
    follow_up_next_action: str
    commerce_score: int
    enterprise_score: int
    strategic_score: int
    action_level: str
    age_days: int
    days_since_push: int
    stars_per_day: float
    fork_ratio: float
    momentum_score: int
    maturity_level: str
    repository_review: str
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


def parse_github_date(value: str, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return fallback


def classify(repo: dict[str, Any], report_date: date | None = None) -> tuple[str, int]:
    as_of = report_date or date.today()
    text = words(repo)
    scores: dict[str, int] = {}
    for category, keywords in FOCUS_AREAS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        scores[category] = score
    category = max(scores, key=scores.get)
    base = scores[category]
    topic_bonus = min(len(repo.get("topics") or []), 6)
    star_bonus = min(repo_stars(repo) // 100, 10)
    freshness_bonus = 3 if repo.get("pushed_at", "")[:10] >= (as_of - timedelta(days=7)).isoformat() else 0
    return category, base * 10 + topic_bonus + star_bonus + freshness_bonus


def infer_subcategory(repo: dict[str, Any], category: str) -> str:
    text = words(repo)
    patterns = [
        ("Commerce Agent", ["commerce", "ecommerce", "shopping", "checkout", "merchant", "retail"]),
        ("Product Intelligence", ["product search", "recommendation", "catalog", "inventory", "pricing"]),
        ("Enterprise Workflow", ["workflow", "orchestration", "handoff", "automation"]),
        ("Knowledge / RAG", ["rag", "knowledge", "retrieval", "document", "vector", "embedding"]),
        ("Evaluation / Observability", ["evaluation", "eval", "benchmark", "observability", "telemetry"]),
        ("Agent Runtime", ["agent runtime", "multi-agent", "tool calling", "autonomous agent", "agentic"]),
        ("AI Application Platform", ["copilot", "llm app", "assistant", "platform"]),
        ("Infrastructure", ["inference", "deployment", "sdk", "api", "database"]),
    ]
    for label, keywords in patterns:
        if any(keyword in text for keyword in keywords):
            return label
    return category


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


def infer_risk_flags(repo: dict[str, Any], modules: list[str], days_since_push: int) -> list[str]:
    text = words(repo)
    module_text = " ".join(modules).lower()
    flags = []
    license_info = repo.get("license")
    if not license_info:
        flags.append("license unknown")
    if not any(k in text for k in ["doc", "example", "starter", "template", "quickstart"]):
        flags.append("docs need review")
    if days_since_push > 30:
        flags.append("maintenance freshness risk")
    if not any(k in text for k in ["permission", "audit", "policy", "governance", "approval", "security"]):
        flags.append("enterprise control gap")
    if "evaluation" not in module_text and not any(k in text for k in ["eval", "benchmark", "test", "observability"]):
        flags.append("quality gate unclear")
    return flags[:4]


def follow_up_next_action(repo: "Repo") -> str:
    if repo.action_level == "strategic watch":
        return "Assign owner to track releases, ecosystem adoption, license posture, and architecture fit weekly."
    if repo.action_level == "prototype pattern":
        return "Extract the reusable architecture pattern and create a small Leap OS prototype brief."
    if repo.action_level == "clone and test":
        return "Run locally, document setup friction, core modules, integration surface, and operational risks."
    if repo.action_level == "read docs":
        return "Review docs for API shape, deployment model, license, and reusable design ideas."
    if repo.action_level == "monitor":
        return "Keep on watchlist until adoption, docs, or implementation fit improves."
    return "No follow-up unless it reappears with stronger activity or strategic relevance."


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


def rubric_scores(
    repo: dict[str, Any],
    category: str,
    modules: list[str],
    relevance: int,
    report_date: date | None = None,
) -> tuple[int, int, int, str]:
    as_of = report_date or date.today()
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
    freshness = 4 if repo.get("pushed_at", "")[:10] >= (as_of - timedelta(days=14)).isoformat() else 0
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


def trend_metrics(
    item: dict[str, Any],
    report_date: date,
    relevance: int,
    strategic_score: int,
) -> tuple[int, int, float, float, int, str, str]:
    created_date = parse_github_date(item.get("created_at") or "", report_date)
    pushed_date = parse_github_date(item.get("pushed_at") or "", created_date)
    age_days = max(1, (report_date - created_date).days)
    days_since_push = max(0, (report_date - pushed_date).days)
    stars = repo_stars(item)
    forks = repo_forks(item)
    stars_per_day = stars / age_days
    fork_ratio = forks / stars if stars else 0.0
    freshness_score = max(0, 30 - min(days_since_push, 30))
    velocity_score = min(40, int(stars_per_day * 4))
    adoption_score = min(15, int(fork_ratio * 100))
    fit_score = min(15, int((relevance + strategic_score) / 10))
    momentum_score = min(100, velocity_score + freshness_score + adoption_score + fit_score)

    if stars >= 20000 or forks >= 3000:
        maturity_level = "ecosystem leader"
    elif stars >= 5000 or forks >= 800:
        maturity_level = "established"
    elif stars >= 1000 or stars_per_day >= 20:
        maturity_level = "scaling"
    else:
        maturity_level = "emerging"

    if days_since_push <= 7:
        activity = "actively maintained"
    elif days_since_push <= 30:
        activity = "recently active"
    else:
        activity = "needs maintenance review"
    repository_review = (
        f"{maturity_level.title()} project with {stars_per_day:.1f} stars/day, "
        f"{activity}, and {momentum_score}/100 momentum. "
        f"Review first for reusable modules if action is '{item.get('_action_level', 'monitor')}'."
    )
    return age_days, days_since_push, stars_per_day, fork_ratio, momentum_score, maturity_level, repository_review


def normalize_repo(item: dict[str, Any], report_date: date | None = None) -> Repo:
    as_of = report_date or date.today()
    category, relevance = classify(item, as_of)
    subcategory = infer_subcategory(item, category)
    modules = infer_modules(item, category)
    scenarios = infer_scenarios(item, category)
    commerce, enterprise = leap_notes(item, category, modules)
    commerce_score, enterprise_score, strategic_score, action_level = rubric_scores(item, category, modules, relevance, as_of)
    item["_action_level"] = action_level
    age_days, days_since_push, stars_per_day, fork_ratio, momentum_score, maturity_level, repository_review = trend_metrics(
        item, as_of, relevance, strategic_score
    )
    risk_flags = infer_risk_flags(item, modules, days_since_push)
    repo = Repo(
        name=item.get("name") or "",
        full_name=item.get("full_name") or "",
        owner=repo_owner(item),
        url=repo_url(item),
        description=(item.get("description") or "No description provided.").strip(),
        language=item.get("language") or "Unknown",
        stars=repo_stars(item),
        forks=repo_forks(item),
        topics=list(item.get("topics") or []),
        created_at=item.get("created_at") or "",
        updated_at=item.get("updated_at") or "",
        pushed_at=item.get("pushed_at") or "",
        category=category,
        subcategory=subcategory,
        relevance=relevance,
        modules=modules,
        scenarios=scenarios,
        risk_flags=risk_flags,
        follow_up_next_action="",
        commerce_score=commerce_score,
        enterprise_score=enterprise_score,
        strategic_score=strategic_score,
        action_level=action_level,
        age_days=age_days,
        days_since_push=days_since_push,
        stars_per_day=round(stars_per_day, 2),
        fork_ratio=round(fork_ratio, 4),
        momentum_score=momentum_score,
        maturity_level=maturity_level,
        repository_review=repository_review,
        leap_commerce=commerce,
        leap_enterprise=enterprise,
    )
    repo.follow_up_next_action = follow_up_next_action(repo)
    return repo


def collect(days: int, limit: int, token: str | None, report_date: date | None = None) -> list[Repo]:
    as_of = report_date or date.today()
    since = as_of - timedelta(days=days)
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
    repos = [normalize_repo(item, as_of) for item in seen.values()]
    repos.sort(key=lambda repo: (repo.momentum_score, repo.relevance, repo.stars), reverse=True)
    return balanced_selection(repos, limit)


def balanced_selection(repos: list[Repo], limit: int) -> list[Repo]:
    if limit <= 0:
        return []
    category_floor = max(1, min(5, limit // max(1, len(FOCUS_AREAS))))
    selected: list[Repo] = []
    selected_names: set[str] = set()
    for category in FOCUS_AREAS:
        category_repos = [repo for repo in repos if repo.category == category]
        for repo in category_repos[:category_floor]:
            if repo.full_name not in selected_names:
                selected.append(repo)
                selected_names.add(repo.full_name)
    for repo in repos:
        if len(selected) >= limit:
            break
        if repo.full_name not in selected_names:
            selected.append(repo)
            selected_names.add(repo.full_name)
    selected.sort(key=lambda repo: (repo.strategic_score, repo.momentum_score, repo.relevance, repo.stars), reverse=True)
    return selected[:limit]


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
          subcategory TEXT NOT NULL DEFAULT '',
          relevance INTEGER NOT NULL,
          commerce_score INTEGER NOT NULL,
          enterprise_score INTEGER NOT NULL,
          strategic_score INTEGER NOT NULL,
          action_level TEXT NOT NULL,
          age_days INTEGER NOT NULL DEFAULT 0,
          days_since_push INTEGER NOT NULL DEFAULT 0,
          stars_per_day REAL NOT NULL DEFAULT 0,
          fork_ratio REAL NOT NULL DEFAULT 0,
          momentum_score INTEGER NOT NULL DEFAULT 0,
          maturity_level TEXT NOT NULL DEFAULT '',
          repository_review TEXT NOT NULL DEFAULT '',
          modules_json TEXT NOT NULL,
          scenarios_json TEXT NOT NULL,
          risk_flags_json TEXT NOT NULL DEFAULT '[]',
          follow_up_next_action TEXT NOT NULL DEFAULT '',
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
    ensure_snapshot_columns(conn)
    return conn


def ensure_snapshot_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(repo_snapshots)").fetchall()}
    migrations = {
        "subcategory": "ALTER TABLE repo_snapshots ADD COLUMN subcategory TEXT NOT NULL DEFAULT ''",
        "age_days": "ALTER TABLE repo_snapshots ADD COLUMN age_days INTEGER NOT NULL DEFAULT 0",
        "days_since_push": "ALTER TABLE repo_snapshots ADD COLUMN days_since_push INTEGER NOT NULL DEFAULT 0",
        "stars_per_day": "ALTER TABLE repo_snapshots ADD COLUMN stars_per_day REAL NOT NULL DEFAULT 0",
        "fork_ratio": "ALTER TABLE repo_snapshots ADD COLUMN fork_ratio REAL NOT NULL DEFAULT 0",
        "momentum_score": "ALTER TABLE repo_snapshots ADD COLUMN momentum_score INTEGER NOT NULL DEFAULT 0",
        "maturity_level": "ALTER TABLE repo_snapshots ADD COLUMN maturity_level TEXT NOT NULL DEFAULT ''",
        "repository_review": "ALTER TABLE repo_snapshots ADD COLUMN repository_review TEXT NOT NULL DEFAULT ''",
        "risk_flags_json": "ALTER TABLE repo_snapshots ADD COLUMN risk_flags_json TEXT NOT NULL DEFAULT '[]'",
        "follow_up_next_action": "ALTER TABLE repo_snapshots ADD COLUMN follow_up_next_action TEXT NOT NULL DEFAULT ''",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)
    conn.commit()


def save_to_db(conn: sqlite3.Connection, repos: list[Repo], report_date: date) -> None:
    today = report_date.isoformat()
    conn.execute("DELETE FROM repo_snapshots WHERE snapshot_date = ?", (today,))
    conn.execute("DELETE FROM leap_notes WHERE note_date = ?", (today,))
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
              full_name, snapshot_date, stars, forks, category, subcategory, relevance,
              commerce_score, enterprise_score, strategic_score, action_level,
              age_days, days_since_push, stars_per_day, fork_ratio, momentum_score,
              maturity_level, repository_review, modules_json, scenarios_json,
              risk_flags_json, follow_up_next_action,
              leap_commerce, leap_enterprise
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(full_name, snapshot_date) DO UPDATE SET
              stars = excluded.stars,
              forks = excluded.forks,
              category = excluded.category,
              subcategory = excluded.subcategory,
              relevance = excluded.relevance,
              commerce_score = excluded.commerce_score,
              enterprise_score = excluded.enterprise_score,
              strategic_score = excluded.strategic_score,
              action_level = excluded.action_level,
              age_days = excluded.age_days,
              days_since_push = excluded.days_since_push,
              stars_per_day = excluded.stars_per_day,
              fork_ratio = excluded.fork_ratio,
              momentum_score = excluded.momentum_score,
              maturity_level = excluded.maturity_level,
              repository_review = excluded.repository_review,
              modules_json = excluded.modules_json,
              scenarios_json = excluded.scenarios_json,
              risk_flags_json = excluded.risk_flags_json,
              follow_up_next_action = excluded.follow_up_next_action,
              leap_commerce = excluded.leap_commerce,
              leap_enterprise = excluded.leap_enterprise
            """,
            (
                repo.full_name,
                today,
                repo.stars,
                repo.forks,
                repo.category,
                repo.subcategory,
                repo.relevance,
                repo.commerce_score,
                repo.enterprise_score,
                repo.strategic_score,
                repo.action_level,
                repo.age_days,
                repo.days_since_push,
                repo.stars_per_day,
                repo.fork_ratio,
                repo.momentum_score,
                repo.maturity_level,
                repo.repository_review,
                json.dumps(repo.modules, ensure_ascii=False),
                json.dumps(repo.scenarios, ensure_ascii=False),
                json.dumps(repo.risk_flags, ensure_ascii=False),
                repo.follow_up_next_action,
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
          s.stars, s.forks, s.category, s.subcategory, s.relevance, s.commerce_score,
          s.enterprise_score, s.strategic_score, s.action_level,
          s.age_days, s.days_since_push, s.stars_per_day, s.fork_ratio,
          s.momentum_score, s.maturity_level, s.repository_review,
          s.modules_json, s.scenarios_json, s.risk_flags_json, s.follow_up_next_action,
          s.leap_commerce, s.leap_enterprise
        FROM repo_snapshots s
        JOIN repositories r ON r.full_name = s.full_name
        WHERE s.snapshot_date = ?
        ORDER BY s.strategic_score DESC, s.relevance DESC, s.stars DESC
        LIMIT ?
        """,
        (report_date.isoformat(), limit),
    ).fetchall()
    repos = []
    for row in rows:
        topics = json.loads(row["topics_json"])
        row_item = {
            "name": row["name"],
            "full_name": row["full_name"],
            "description": row["description"],
            "topics": topics,
            "language": row["language"],
            "pushed_at": row["pushed_at"],
        }
        modules = json.loads(row["modules_json"])
        risk_flags = json.loads(row["risk_flags_json"] or "[]") or infer_risk_flags(
            row_item, modules, row["days_since_push"]
        )
        subcategory = row["subcategory"] or infer_subcategory(row_item, row["category"])
        repo = Repo(
            name=row["name"],
            full_name=row["full_name"],
            owner=row["owner"],
            url=row["url"],
            description=row["description"],
            language=row["language"],
            stars=row["stars"],
            forks=row["forks"],
            topics=topics,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            pushed_at=row["pushed_at"],
            category=row["category"],
            subcategory=subcategory,
            relevance=row["relevance"],
            modules=modules,
            scenarios=json.loads(row["scenarios_json"]),
            risk_flags=risk_flags,
            follow_up_next_action=row["follow_up_next_action"],
            commerce_score=row["commerce_score"],
            enterprise_score=row["enterprise_score"],
            strategic_score=row["strategic_score"],
            action_level=row["action_level"],
            age_days=row["age_days"],
            days_since_push=row["days_since_push"],
            stars_per_day=row["stars_per_day"],
            fork_ratio=row["fork_ratio"],
            momentum_score=row["momentum_score"],
            maturity_level=row["maturity_level"],
            repository_review=row["repository_review"],
            leap_commerce=row["leap_commerce"],
            leap_enterprise=row["leap_enterprise"],
        )
        if not repo.follow_up_next_action:
            repo.follow_up_next_action = follow_up_next_action(repo)
        repos.append(repo)
    return repos


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
    (PUBLIC / "index.html").write_text(html_doc, encoding="utf-8")
    (PUBLIC / "latest.md").write_text(md, encoding="utf-8")
    (DATA_DIR / "latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (DATA_DIR / "backlog.json").write_text(json.dumps(backlog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (DATA_DIR / "trends.json").write_text(json.dumps(trends, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if history is not None:
        (DATA_DIR / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate LeapUnion GHstar daily report.")
    parser.add_argument("--days", type=int, default=90, help="Lookback window for newly created and recently active repositories.")
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
            write_outputs(repos, report_date, history_summary(conn), args.days)
        print(json.dumps({"date": report_date.isoformat(), "repos": len(repos)}, indent=2))
        return 0
    if args.fixture:
        fixture_data = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        repos = [normalize_repo(item, report_date) for item in fixture_data][: args.limit]
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GHSTAR_GITHUB_TOKEN")
        repos = collect(args.days, args.limit, token, report_date)
    if args.no_db:
        write_outputs(repos, report_date, lookback_days=args.days)
    else:
        with init_db(Path(args.db)) as conn:
            save_to_db(conn, repos, report_date)
            repos = load_report_repos(conn, report_date, args.limit)
            save_daily_report_record(conn, report_date, len(repos))
            write_outputs(repos, report_date, history_summary(conn), args.days)
    print(json.dumps({"date": report_date.isoformat(), "repos": len(repos)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
