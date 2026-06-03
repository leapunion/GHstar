# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GHstar is a daily "90-day GitHub Top Star Radar" generator. It scans GitHub for repos created or recently active in a lookback window, classifies them into four focus areas (AI Agent Framework, Agentic Enterprise, AI Commerce, AI Infrastructure), scores them, persists snapshots, and renders Markdown / HTML / JSON outputs that are deployed as a static Vercel site. There is no application server — the "product" is the generated `reports/` and `public/` files plus the SQLite history.

The runtime is pure-Python standard library (no third-party deps for report generation; `urllib` is used directly against the GitHub Search API). The only pip dependency, `psycopg`, is needed solely by the Agent ETL path (`scripts/ghstar_agent.py`) for Postgres/TimescaleDB.

## Commands

```bash
# Deterministic smoke test (the canonical test — runs the unittest suite via subprocess)
python3 scripts/run_smoke_test.py
python3 -m unittest tests.test_generate_report_smoke        # equivalent direct invocation

# Generate a report from the offline fixture (no network, used by CI smoke + local dev)
python3 scripts/generate_report.py --fixture fixtures/github_repositories.json --date 2026-05-28 --limit 2

# Generate a live report from GitHub (needs a token in GH_TOKEN / GITHUB_TOKEN / GHSTAR_GITHUB_TOKEN)
GH_TOKEN="$GHSTAR_GITHUB_TOKEN" python3 scripts/generate_report.py --days 90 --limit 50

# Validate the generated public/ outputs exist and parse (CI gate; also smoke-checks a deployed URL if GHSTAR_PUBLIC_URL is set)
python3 scripts/check_public_outputs.py

# Agent ETL: scan GitHub and fan out to SQLite + Postgres + TimescaleDB
python3 scripts/ghstar_agent.py --days 30 --limit 50 --targets sqlite,postgres,timescale
```

Docker equivalents (see `docs/docker.md`): `docker compose run --rm ghstar-smoke`, `docker compose run --rm ghstar`, `docker compose up ghstar-web` (nginx static serve), and `docker compose up -d ghstar-pg ghstar-timescaledb ghstar-agent` for the looping ETL stack.

## Architecture

`scripts/generate_report.py` (~1500 lines) is the core library and is imported by the other scripts. The pipeline flows in one direction:

1. **Collect** (`collect`) — runs every query in `SEARCH_QUERIES` against the GitHub Search API in two modes (`created` and `active`), deduplicates by `full_name` keeping the higher star count, and normalizes each item.
2. **Normalize + enrich** (`normalize_repo`) — turns a raw API dict into the `Repo` dataclass, computing all derived fields at once: `classify` (focus area + relevance), `infer_subcategory`/`infer_modules`/`infer_scenarios`/`infer_risk_flags`, `rubric_scores` (commerce/enterprise/strategic), `trend_metrics` (momentum, maturity, stars-per-day), and `leap_notes`. **The `Repo` dataclass is the single contract that flows through the entire system** — DB writers, renderers, and the ETL agent all consume it.
3. **Select** (`balanced_selection`) — guarantees a per-category floor before filling remaining slots by strategic score, so no single focus area dominates the report.
4. **Persist** (`init_db` / `save_to_db`) — writes to SQLite tables `repositories`, `repo_snapshots`, `daily_reports`, `leap_notes`. `ensure_snapshot_columns` does lightweight additive schema migration on existing DBs.
5. **Render** (`render_markdown`, `render_html`, `trend_payload`, `backlog_items`) — `write_outputs` fans the selected repos into `reports/YYYY-MM-DD.md`, `public/index.html`, `public/latest.md`, and `public/data/{latest,history,backlog,trends}.json`.

Key flag interactions in `main`: `--from-db` re-renders outputs from existing SQLite snapshots without hitting the network (incompatible with `--no-db`); `--fixture` reads a local JSON file instead of the API; `--no-db` renders without persisting. Classification keywords live in `FOCUS_AREAS` and search terms in `SEARCH_QUERIES` at the top of the file — editing these changes what the radar finds and how it buckets results.

`scripts/ghstar_agent.py` ("GHstar_Agent") is a separate ETL layer that reuses `generate_report.collect` for scanning but writes to a multi-schema warehouse. It defines `raw.github_repositories`, `curated.repositories`, `curated.repo_snapshots`, `curated.repo_metrics_timeseries`, and `mart.follow_up_backlog`. When `--targets` includes `timescale`, `ensure_pg_schema(enable_timescale=True)` promotes the metrics table to a hypertable via `create_hypertable`. `connect_with_retry` polls the DB on startup because the agent runs against freshly-started compose containers.

## Conventions worth knowing

- **Determinism**: a `report_date` (not `date.today()`) is threaded through `classify`, `normalize_repo`, `collect`, and `trend_metrics` so fixture runs produce byte-stable output. Preserve this when adding date-dependent logic — the smoke test asserts exact output for date `2026-05-28`.
- **No network in tests**: `tests/test_generate_report_smoke.py` copies the script to a tempdir and runs it against the fixture, asserting the exact stdout `{"date": ..., "repos": 2}` and that every expected output file is created. The fixture (`fixtures/github_repositories.json`) is the contract for the GitHub Search API response shape.
- **Token resolution order** is consistently `GH_TOKEN` → `GITHUB_TOKEN` → `GHSTAR_GITHUB_TOKEN` in both scripts.
- **Generated files are committed**: the daily GitHub Actions workflow (`.github/workflows/daily-report.yml`, 13:15 UTC) regenerates and commits `reports/` + `public/` + `data/ghstar.sqlite`, then optionally deploys to Vercel. Treat these as build artifacts — don't hand-edit them.
- **Docker naming**: container/DB names are project-scoped and capitalized (`GHstar_Agent`, `GHstar_PG`, `GHstar_TimescaleDB`); image tags are lowercase (`ghstar-agent:local`) because Docker forbids uppercase image names. Postgres is on host port `54321`, TimescaleDB on `54322`.

Reference docs live in `docs/` (`database.md`, `docker.md`, `report-architecture.md`, `taxonomy.md`, `90-day-radar.md`).
