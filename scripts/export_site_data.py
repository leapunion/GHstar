#!/usr/bin/env python3
"""Export static site data API from GHstar SQLite DB.

Reads full history from data/ghstar.sqlite and writes:
  public/data/site/index.json
  public/data/site/corpus.json
  public/data/site/snapshots/<YYYY-MM-DD>.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get("GHSTAR_DB", "") or ROOT / "data" / "ghstar.sqlite")
DEFAULT_OUT = ROOT / "public" / "data" / "site"


def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def parse_json_col(value: str | None, fallback: list) -> list:
    if not value:
        return fallback
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def build_repo_dict(r_row: sqlite3.Row, s_row: sqlite3.Row) -> dict:
    """Build a per-repo dict from a repositories row and a repo_snapshots row."""
    topics = parse_json_col(r_row["topics_json"], [])
    modules = parse_json_col(s_row["modules_json"], [])
    scenarios = parse_json_col(s_row["scenarios_json"], [])
    risk_flags = parse_json_col(s_row["risk_flags_json"], [])

    return {
        "full_name": r_row["full_name"],
        "name": r_row["name"],
        "owner": r_row["owner"],
        "url": r_row["url"],
        "description": r_row["description"],
        "language": r_row["language"],
        "stars": s_row["stars"],
        "forks": s_row["forks"],
        "topics": topics,
        "created_at": r_row["created_at"],
        "pushed_at": r_row["pushed_at"],
        "category": s_row["category"],
        "subcategory": s_row["subcategory"],
        "relevance": s_row["relevance"],
        "modules": modules,
        "scenarios": scenarios,
        "risk_flags": risk_flags,
        "commerce_score": s_row["commerce_score"],
        "enterprise_score": s_row["enterprise_score"],
        "strategic_score": s_row["strategic_score"],
        "action_level": s_row["action_level"],
        "stars_per_day": s_row["stars_per_day"],
        "momentum_score": s_row["momentum_score"],
        "maturity_level": s_row["maturity_level"],
        "repository_review": s_row["repository_review"],
        "first_seen_date": r_row["first_seen_date"],
        "last_seen_date": r_row["last_seen_date"],
    }


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def export(db_path: Path, out_dir: Path) -> dict:
    conn = open_db(db_path)

    # ── 1. Fetch all distinct snapshot dates (ascending) ────────────────────
    dates_rows = conn.execute(
        "SELECT DISTINCT snapshot_date FROM repo_snapshots ORDER BY snapshot_date ASC"
    ).fetchall()
    dates: list[str] = [row["snapshot_date"] for row in dates_rows]

    # ── 2. Fetch latest snapshot for each repo ───────────────────────────────
    # Join repositories + latest snapshot per full_name
    latest_snapshots = conn.execute(
        """
        SELECT
          r.full_name, r.name, r.owner, r.url, r.description, r.language,
          r.topics_json, r.created_at, r.updated_at, r.pushed_at,
          r.first_seen_date, r.last_seen_date,
          s.snapshot_date, s.stars, s.forks, s.category, s.subcategory,
          s.relevance, s.commerce_score, s.enterprise_score, s.strategic_score,
          s.action_level, s.age_days, s.days_since_push, s.stars_per_day,
          s.fork_ratio, s.momentum_score, s.maturity_level, s.repository_review,
          s.modules_json, s.scenarios_json, s.risk_flags_json,
          s.follow_up_next_action, s.leap_commerce, s.leap_enterprise
        FROM repositories r
        JOIN repo_snapshots s ON s.full_name = r.full_name
        WHERE s.snapshot_date = (
          SELECT MAX(s2.snapshot_date)
          FROM repo_snapshots s2
          WHERE s2.full_name = r.full_name
        )
        ORDER BY s.strategic_score DESC, s.stars DESC
        """
    ).fetchall()

    # ── 3. Fetch full history for every repo ─────────────────────────────────
    history_rows = conn.execute(
        """
        SELECT full_name, snapshot_date, stars, momentum_score
        FROM repo_snapshots
        ORDER BY full_name, snapshot_date ASC
        """
    ).fetchall()

    # Build history map: full_name → [{date, stars, momentum_score}, ...]
    history_map: dict[str, list[dict]] = {}
    for hr in history_rows:
        fn = hr["full_name"]
        if fn not in history_map:
            history_map[fn] = []
        history_map[fn].append({
            "date": hr["snapshot_date"],
            "stars": hr["stars"],
            "momentum_score": hr["momentum_score"],
        })

    # ── 4. Build corpus.json ─────────────────────────────────────────────────
    corpus: list[dict] = []
    for row in latest_snapshots:
        entry = build_repo_dict(row, row)  # same row has both r.* and s.* columns
        entry["history"] = history_map.get(row["full_name"], [])
        corpus.append(entry)

    # ── 5. Compute facets from the latest snapshot of each repo ──────────────
    facets: dict[str, dict[str, int]] = {
        "category": {},
        "subcategory": {},
        "language": {},
        "action_level": {},
    }
    for entry in corpus:
        for facet_key in ("category", "subcategory", "language", "action_level"):
            val = entry.get(facet_key) or ""
            if val:
                facets[facet_key][val] = facets[facet_key].get(val, 0) + 1

    # Sort each facet by count desc, then name asc
    for facet_key in facets:
        facets[facet_key] = dict(
            sorted(facets[facet_key].items(), key=lambda kv: (-kv[1], kv[0]))
        )

    # ── 6. Build index.json ──────────────────────────────────────────────────
    build_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index = {
        "schema": 1,
        "build": build_time,
        "dates": dates,
        "repo_count": len(corpus),
        "facets": facets,
    }

    # ── 7. Build snapshots/<date>.json ───────────────────────────────────────
    # For each snapshot date, gather all repos seen that date (no history field)
    # We need all snapshot rows grouped by date
    all_snapshot_rows = conn.execute(
        """
        SELECT
          r.full_name, r.name, r.owner, r.url, r.description, r.language,
          r.topics_json, r.created_at, r.updated_at, r.pushed_at,
          r.first_seen_date, r.last_seen_date,
          s.snapshot_date, s.stars, s.forks, s.category, s.subcategory,
          s.relevance, s.commerce_score, s.enterprise_score, s.strategic_score,
          s.action_level, s.age_days, s.days_since_push, s.stars_per_day,
          s.fork_ratio, s.momentum_score, s.maturity_level, s.repository_review,
          s.modules_json, s.scenarios_json, s.risk_flags_json,
          s.follow_up_next_action, s.leap_commerce, s.leap_enterprise
        FROM repo_snapshots s
        JOIN repositories r ON r.full_name = s.full_name
        ORDER BY s.snapshot_date ASC, s.strategic_score DESC, s.stars DESC
        """
    ).fetchall()

    # Group by snapshot_date
    snapshots_by_date: dict[str, list[dict]] = {}
    for row in all_snapshot_rows:
        d = row["snapshot_date"]
        if d not in snapshots_by_date:
            snapshots_by_date[d] = []
        entry = build_repo_dict(row, row)
        snapshots_by_date[d].append(entry)

    conn.close()

    # ── 8. Write all files ───────────────────────────────────────────────────
    files_written = 0

    write_json(out_dir / "index.json", index)
    files_written += 1

    write_json(out_dir / "corpus.json", corpus)
    files_written += 1

    snapshots_dir = out_dir / "snapshots"
    for date_str, repos_for_date in snapshots_by_date.items():
        write_json(snapshots_dir / f"{date_str}.json", repos_for_date)
        files_written += 1

    return {
        "repos": len(corpus),
        "dates": len(dates),
        "files_written": files_written,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export GHstar SQLite history to static site data API."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to ghstar.sqlite (default: $GHSTAR_DB or data/ghstar.sqlite)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory (default: public/data/site)",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"error: database not found: {args.db}", flush=True)
        return 1

    summary = export(args.db, args.out)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
