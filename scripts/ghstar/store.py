"""SQLite persistence: schema init/migration, save_to_db, load_report_repos, daily-report records, and history_summary."""
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
            "public/report.html",
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
