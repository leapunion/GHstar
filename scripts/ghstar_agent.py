#!/usr/bin/env python3
"""Run the GHstar GitHub scanning and ETL agent."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import generate_report


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_DB = ROOT / "data" / "ghstar.sqlite"
DEFAULT_PG_DSN = "postgresql://GHstar:GHstar@localhost:54321/GHstar_PG"
DEFAULT_TIMESCALE_DSN = "postgresql://GHstar:GHstar@localhost:54322/GHstar_TimescaleDB"


def import_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit(
            "psycopg is required for PostgreSQL/TimescaleDB targets. "
            "Install with `python3 -m pip install \"psycopg[binary]\"` or run through Docker."
        ) from exc
    return psycopg


def connect_with_retry(dsn: str, attempts: int = 30, delay: float = 2.0) -> Any:
    psycopg = import_psycopg()
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return psycopg.connect(dsn)
        except Exception as exc:  # pragma: no cover - exercised by Docker runtime
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"could not connect to database after {attempts} attempts: {dsn}") from last_error


def dsn_database_name(dsn: str) -> str:
    parsed = urlparse(dsn)
    return parsed.path.lstrip("/") or "unknown"


def repo_payload(repo: generate_report.Repo) -> dict[str, Any]:
    return asdict(repo)


def ensure_pg_schema(conn: Any, enable_timescale: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute("CREATE SCHEMA IF NOT EXISTS curated")
        cur.execute("CREATE SCHEMA IF NOT EXISTS mart")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.github_repositories (
              run_id TEXT NOT NULL,
              full_name TEXT NOT NULL,
              payload JSONB NOT NULL,
              ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (run_id, full_name)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS curated.repositories (
              full_name TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              owner_name TEXT NOT NULL,
              url TEXT NOT NULL,
              description TEXT NOT NULL,
              language TEXT NOT NULL,
              category TEXT NOT NULL,
              subcategory TEXT NOT NULL,
              topics JSONB NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              pushed_at TEXT NOT NULL,
              last_ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS curated.repo_snapshots (
              full_name TEXT NOT NULL REFERENCES curated.repositories(full_name),
              snapshot_date DATE NOT NULL,
              stars INTEGER NOT NULL,
              forks INTEGER NOT NULL,
              relevance INTEGER NOT NULL,
              commerce_score INTEGER NOT NULL,
              enterprise_score INTEGER NOT NULL,
              strategic_score INTEGER NOT NULL,
              action_level TEXT NOT NULL,
              age_days INTEGER NOT NULL,
              days_since_push INTEGER NOT NULL,
              stars_per_day DOUBLE PRECISION NOT NULL,
              fork_ratio DOUBLE PRECISION NOT NULL,
              momentum_score INTEGER NOT NULL,
              maturity_level TEXT NOT NULL,
              repository_review TEXT NOT NULL,
              modules JSONB NOT NULL,
              scenarios JSONB NOT NULL,
              risk_flags JSONB NOT NULL,
              follow_up_next_action TEXT NOT NULL,
              leap_commerce TEXT NOT NULL,
              leap_enterprise TEXT NOT NULL,
              ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (full_name, snapshot_date)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mart.follow_up_backlog (
              snapshot_date DATE NOT NULL,
              full_name TEXT NOT NULL,
              action_level TEXT NOT NULL,
              priority INTEGER NOT NULL,
              strategic_score INTEGER NOT NULL,
              momentum_score INTEGER NOT NULL,
              risk_flags JSONB NOT NULL,
              next_action TEXT NOT NULL,
              suggested_owner TEXT NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (snapshot_date, full_name)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_score ON curated.repo_snapshots (snapshot_date, strategic_score DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_backlog_priority ON mart.follow_up_backlog (snapshot_date, priority DESC)")
        if enable_timescale:
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS curated.repo_metrics_timeseries (
                  event_time TIMESTAMPTZ NOT NULL,
                  full_name TEXT NOT NULL,
                  snapshot_date DATE NOT NULL,
                  stars INTEGER NOT NULL,
                  forks INTEGER NOT NULL,
                  stars_per_day DOUBLE PRECISION NOT NULL,
                  momentum_score INTEGER NOT NULL,
                  strategic_score INTEGER NOT NULL,
                  category TEXT NOT NULL,
                  subcategory TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                SELECT create_hypertable(
                  'curated.repo_metrics_timeseries',
                  'event_time',
                  if_not_exists => TRUE
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_repo_metrics_timeseries_repo
                ON curated.repo_metrics_timeseries (full_name, event_time DESC)
                """
            )
    conn.commit()


def write_pg(conn: Any, repos: list[generate_report.Repo], run_id: str, snapshot_date: date, enable_timescale: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM mart.follow_up_backlog WHERE snapshot_date = %s", (snapshot_date,))
        cur.execute("DELETE FROM curated.repo_snapshots WHERE snapshot_date = %s", (snapshot_date,))
        if enable_timescale:
            cur.execute("DELETE FROM curated.repo_metrics_timeseries WHERE snapshot_date = %s", (snapshot_date,))
        for repo in repos:
            payload = repo_payload(repo)
            cur.execute(
                """
                INSERT INTO raw.github_repositories (run_id, full_name, payload)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (run_id, full_name) DO UPDATE SET
                  payload = excluded.payload,
                  ingested_at = now()
                """,
                (run_id, repo.full_name, json.dumps(payload, ensure_ascii=False)),
            )
            cur.execute(
                """
                INSERT INTO curated.repositories (
                  full_name, name, owner_name, url, description, language,
                  category, subcategory, topics, created_at, updated_at, pushed_at, last_ingested_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, now())
                ON CONFLICT (full_name) DO UPDATE SET
                  name = excluded.name,
                  owner_name = excluded.owner_name,
                  url = excluded.url,
                  description = excluded.description,
                  language = excluded.language,
                  category = excluded.category,
                  subcategory = excluded.subcategory,
                  topics = excluded.topics,
                  updated_at = excluded.updated_at,
                  pushed_at = excluded.pushed_at,
                  last_ingested_at = now()
                """,
                (
                    repo.full_name,
                    repo.name,
                    repo.owner,
                    repo.url,
                    repo.description,
                    repo.language,
                    repo.category,
                    repo.subcategory,
                    json.dumps(repo.topics, ensure_ascii=False),
                    repo.created_at,
                    repo.updated_at,
                    repo.pushed_at,
                ),
            )
            cur.execute(
                """
                INSERT INTO curated.repo_snapshots (
                  full_name, snapshot_date, stars, forks, relevance,
                  commerce_score, enterprise_score, strategic_score, action_level,
                  age_days, days_since_push, stars_per_day, fork_ratio,
                  momentum_score, maturity_level, repository_review,
                  modules, scenarios, risk_flags, follow_up_next_action,
                  leap_commerce, leap_enterprise, ingested_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, now()
                )
                ON CONFLICT (full_name, snapshot_date) DO UPDATE SET
                  stars = excluded.stars,
                  forks = excluded.forks,
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
                  modules = excluded.modules,
                  scenarios = excluded.scenarios,
                  risk_flags = excluded.risk_flags,
                  follow_up_next_action = excluded.follow_up_next_action,
                  leap_commerce = excluded.leap_commerce,
                  leap_enterprise = excluded.leap_enterprise,
                  ingested_at = now()
                """,
                (
                    repo.full_name,
                    snapshot_date,
                    repo.stars,
                    repo.forks,
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
            if enable_timescale:
                cur.execute(
                    """
                    INSERT INTO curated.repo_metrics_timeseries (
                      event_time, full_name, snapshot_date, stars, forks,
                      stars_per_day, momentum_score, strategic_score, category, subcategory
                    )
                    VALUES (now(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        repo.full_name,
                        snapshot_date,
                        repo.stars,
                        repo.forks,
                        repo.stars_per_day,
                        repo.momentum_score,
                        repo.strategic_score,
                        repo.category,
                        repo.subcategory,
                    ),
                )
        for item in generate_report.backlog_items(repos):
            cur.execute(
                """
                INSERT INTO mart.follow_up_backlog (
                  snapshot_date, full_name, action_level, priority, strategic_score,
                  momentum_score, risk_flags, next_action, suggested_owner, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, now())
                ON CONFLICT (snapshot_date, full_name) DO UPDATE SET
                  action_level = excluded.action_level,
                  priority = excluded.priority,
                  strategic_score = excluded.strategic_score,
                  momentum_score = excluded.momentum_score,
                  risk_flags = excluded.risk_flags,
                  next_action = excluded.next_action,
                  suggested_owner = excluded.suggested_owner,
                  updated_at = now()
                """,
                (
                    snapshot_date,
                    item["full_name"],
                    item["action_level"],
                    item["priority"],
                    item["strategic_score"],
                    item["momentum_score"],
                    json.dumps(item["risk_flags"], ensure_ascii=False),
                    item["next_action"],
                    item["suggested_owner"],
                ),
            )
    conn.commit()


def write_sqlite(db_path: Path, repos: list[generate_report.Repo], snapshot_date: date) -> None:
    with generate_report.init_db(db_path) as conn:
        generate_report.save_to_db(conn, repos, snapshot_date)
        generate_report.save_daily_report_record(conn, snapshot_date, len(repos))
        generate_report.write_outputs(repos, snapshot_date, generate_report.history_summary(conn), 30)


def run_agent(args: argparse.Namespace) -> dict[str, Any]:
    snapshot_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GHSTAR_GITHUB_TOKEN")
    run_id = f"GHstar-{snapshot_date.isoformat()}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    repos = generate_report.collect(args.days, args.limit, token, snapshot_date)
    targets = {target.strip().lower() for target in args.targets.split(",") if target.strip()}
    result: dict[str, Any] = {
        "agent": "GHstar_Agent",
        "run_id": run_id,
        "snapshot_date": snapshot_date.isoformat(),
        "lookback_days": args.days,
        "limit": args.limit,
        "repos": len(repos),
        "targets": sorted(targets),
    }
    if "sqlite" in targets:
        write_sqlite(Path(args.sqlite_db), repos, snapshot_date)
        result["sqlite"] = str(Path(args.sqlite_db))
    if "postgres" in targets:
        pg_dsn = args.pg_dsn or os.environ.get("GHSTAR_PG_DSN") or DEFAULT_PG_DSN
        with connect_with_retry(pg_dsn) as conn:
            ensure_pg_schema(conn, enable_timescale=False)
            write_pg(conn, repos, run_id, snapshot_date, enable_timescale=False)
        result["postgres"] = dsn_database_name(pg_dsn)
    if "timescale" in targets:
        ts_dsn = args.timescale_dsn or os.environ.get("GHSTAR_TIMESCALE_DSN") or DEFAULT_TIMESCALE_DSN
        with connect_with_retry(ts_dsn) as conn:
            ensure_pg_schema(conn, enable_timescale=True)
            write_pg(conn, repos, run_id, snapshot_date, enable_timescale=True)
        result["timescale"] = dsn_database_name(ts_dsn)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GHstar GitHub scanning and ETL agent.")
    parser.add_argument("--days", type=int, default=30, help="GitHub lookback window in days.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum repositories to ingest.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Snapshot date YYYY-MM-DD.")
    parser.add_argument("--targets", default="sqlite,postgres,timescale", help="Comma-separated targets: sqlite,postgres,timescale.")
    parser.add_argument("--sqlite-db", default=os.environ.get("GHSTAR_DB", str(DEFAULT_SQLITE_DB)))
    parser.add_argument("--pg-dsn", default=os.environ.get("GHSTAR_PG_DSN"))
    parser.add_argument("--timescale-dsn", default=os.environ.get("GHSTAR_TIMESCALE_DSN"))
    result = run_agent(parser.parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
