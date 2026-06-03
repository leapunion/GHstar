#!/usr/bin/env python3
"""Validate GHstar static outputs and optionally smoke-check the deployed site."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
DATA = PUBLIC / "data"


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def require_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"{path} is empty")
    return text


def check_local_outputs() -> None:
    html = require_file(PUBLIC / "report.html")
    markdown = require_file(PUBLIC / "latest.md")
    latest = json.loads(require_file(DATA / "latest.json"))
    history = json.loads(require_file(DATA / "history.json"))
    backlog = json.loads(require_file(DATA / "backlog.json"))
    trends = json.loads(require_file(DATA / "trends.json"))

    if "<title>GHstar AI & Agent 90-Day Radar" not in html:
        raise ValueError("report.html title is missing")
    if "Follow-Up Backlog" not in html or "90-Day Trend Signals" not in html:
        raise ValueError("report.html is missing expected dashboard sections")
    if "Follow-Up Backlog" not in markdown:
        raise ValueError("latest.md is missing backlog section")
    if not isinstance(latest, list) or not latest:
        raise ValueError("latest.json must contain at least one repository")
    for key in ["full_name", "subcategory", "risk_flags", "follow_up_next_action"]:
        if key not in latest[0]:
            raise ValueError(f"latest.json missing key: {key}")
    if not isinstance(history, list):
        raise ValueError("history.json must be a list")
    if not isinstance(backlog, list):
        raise ValueError("backlog.json must be a list")
    if "action_distribution" not in trends or "watchlist_flags" not in trends:
        raise ValueError("trends.json is missing trend summaries")


def check_site_outputs() -> None:
    """Validate SPA data outputs under public/data/site/."""
    site = PUBLIC / "data" / "site"

    # Validate index.json
    index_text = require_file(site / "index.json")
    index = json.loads(index_text)

    if not isinstance(index.get("schema"), int):
        raise ValueError("index.json missing or invalid schema (must be int)")

    dates = index.get("dates")
    if not isinstance(dates, list) or not dates:
        raise ValueError("index.json dates must be a non-empty list")

    facets = index.get("facets")
    if not isinstance(facets, dict):
        raise ValueError("index.json facets must be a dict")

    required_facet_keys = {"category", "subcategory", "language", "action_level"}
    if not required_facet_keys.issubset(facets.keys()):
        raise ValueError(
            f"index.json facets missing required keys: {required_facet_keys - set(facets.keys())}"
        )

    # Validate corpus.json
    corpus_text = require_file(site / "corpus.json")
    corpus = json.loads(corpus_text)

    if not isinstance(corpus, list) or not corpus:
        raise ValueError("corpus.json must be a non-empty array")

    for i, entry in enumerate(corpus):
        for key in ["full_name", "category", "stars", "history"]:
            if key not in entry:
                raise ValueError(f"corpus.json entry {i} missing key: {key}")
        if not isinstance(entry.get("history"), list):
            raise ValueError(f"corpus.json entry {i} history must be a list")

    # Validate snapshots for each date
    snapshots_dir = site / "snapshots"
    for date in dates:
        snapshot_file = snapshots_dir / f"{date}.json"
        snapshot_text = require_file(snapshot_file)
        snapshot = json.loads(snapshot_text)

        if not isinstance(snapshot, list) or not snapshot:
            raise ValueError(f"snapshots/{date}.json must be a non-empty array")


def check_remote_outputs(base_url: str) -> None:
    base = base_url.rstrip("/")
    for path in ["/", "/data/latest.json", "/data/backlog.json", "/data/trends.json"]:
        url = f"{base}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "leapunion-ghstar-smoke"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status >= 400:
                raise urllib.error.HTTPError(url, resp.status, "bad status", resp.headers, None)
            body = resp.read(512)
            if not body:
                raise ValueError(f"{url} returned an empty body")


def main() -> int:
    try:
        check_local_outputs()
        check_site_outputs()
        public_url = os.environ.get("GHSTAR_PUBLIC_URL", "").strip()
        if public_url:
            check_remote_outputs(public_url)
    except Exception as exc:
        return fail(str(exc))
    print(json.dumps({"local": "ok", "remote": bool(os.environ.get("GHSTAR_PUBLIC_URL"))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
