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
    html = require_file(PUBLIC / "index.html")
    markdown = require_file(PUBLIC / "latest.md")
    latest = json.loads(require_file(DATA / "latest.json"))
    history = json.loads(require_file(DATA / "history.json"))
    backlog = json.loads(require_file(DATA / "backlog.json"))
    trends = json.loads(require_file(DATA / "trends.json"))

    if "<title>GHstar AI & Agent 90-Day Radar" not in html:
        raise ValueError("index.html title is missing")
    if "Follow-Up Backlog" not in html or "90-Day Trend Signals" not in html:
        raise ValueError("index.html is missing expected dashboard sections")
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
        public_url = os.environ.get("GHSTAR_PUBLIC_URL", "").strip()
        if public_url:
            check_remote_outputs(public_url)
    except Exception as exc:
        return fail(str(exc))
    print(json.dumps({"local": "ok", "remote": bool(os.environ.get("GHSTAR_PUBLIC_URL"))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
