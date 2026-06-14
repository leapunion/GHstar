"""Collection: GitHub Search API access (github_get/search_repos), the collect() scan+dedupe, balanced_selection, and the enforce_min_repos empty-result guard."""
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


def enforce_min_repos(repos: list[Repo], minimum: int, source: str = "live scan") -> None:
    """Guard against a degraded scan silently producing an empty report.

    Applied to live GitHub scans only (not --fixture / --from-db), before any
    persistence, rendering, commit, or deploy. A 0-repo result almost always
    means an expired token or a GitHub API/search change rather than a real
    "nothing new today" — so failing loudly is safer than committing an empty
    report and deploying it.
    """
    if minimum > 0 and len(repos) < minimum:
        raise SystemExit(
            f"empty-result guard: {source} returned {len(repos)} repos "
            f"(minimum {minimum}); refusing to persist/render. "
            "Check the GH token and GitHub API status."
        )
