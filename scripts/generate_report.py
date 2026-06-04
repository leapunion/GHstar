#!/usr/bin/env python3
"""Generate daily GitHub Top Star reports for AI, agents, commerce, and enterprise OS.

Thin CLI facade. The implementation is carved into the ``ghstar`` package
(model / enrich / collect / store / render); this module re-exports the full
public surface for backward compatibility (``import generate_report`` in
scripts/ghstar_agent.py and the tests) and hosts the ``main()`` entry point.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

from ghstar.model import *  # noqa: F401,F403
from ghstar.enrich import *  # noqa: F401,F403
from ghstar.collect import *  # noqa: F401,F403
from ghstar.store import *  # noqa: F401,F403
from ghstar.render import *  # noqa: F401,F403


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate LeapUnion GHstar daily report.")
    parser.add_argument("--days", type=int, default=90, help="Lookback window for newly created and recently active repositories.")
    parser.add_argument("--limit", type=int, default=24, help="Maximum repositories to include.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Report date YYYY-MM-DD.")
    parser.add_argument("--fixture", help="Use local JSON fixture instead of GitHub API.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path.")
    parser.add_argument("--no-db", action="store_true", help="Generate files without writing SQLite history.")
    parser.add_argument("--from-db", action="store_true", help="Render outputs from existing SQLite snapshots.")
    parser.add_argument("--min-repos", type=int, default=1, help="Fail a live scan that yields fewer than this many repos, before persisting/rendering (guards against token/API failures committing an empty report). Not applied to --fixture or --from-db.")
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
        enforce_min_repos(repos, args.min_repos)
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
