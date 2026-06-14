# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

GHstar is a daily "90-day GitHub Top Star Radar" generator. It scans GitHub for repos created or recently active in a lookback window, classifies them into four focus areas (AI Agent Framework, Agentic Enterprise, AI Commerce, AI Infrastructure), scores them, persists snapshots, and renders Markdown / HTML / JSON outputs that are deployed as a static Vercel site. There is no application server — the "product" is the generated `reports/` and `public/` files plus the SQLite history.

The runtime is pure-Python standard library (no third-party deps for report generation; `urllib` is used directly against the GitHub Search API). The only pip dependency, `psycopg`, is needed solely by the Agent ETL path (`scripts/ghstar_agent.py`) for Postgres/TimescaleDB.

## Commands

```bash
# Deterministic smoke test (the canonical test — discovers + runs the whole tests/ suite)
python3 scripts/run_smoke_test.py
python3 -m unittest discover -s tests -t .                  # equivalent direct invocation
python3 -m unittest tests.test_generate_report_smoke       # just the byte-stable generator test

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

`scripts/generate_report.py` is now a thin CLI facade (hosts `main()`) over the `scripts/ghstar/` package, which was carved out of the former ~1500-line monolith into five layers in dependency order **`model` ← `enrich` ← {`collect`, `store`, `render`}**. The facade re-exports the whole public surface, so `generate_report.collect`, `generate_report.Repo`, `generate_report.save_to_db`, etc. still resolve for back-compat (`ghstar_agent.py` and the tests import the module that way). The pipeline flows in one direction:

1. **Collect** (`collect`, `ghstar/collect.py`) — runs every query in `SEARCH_QUERIES` against the GitHub Search API in two modes (`created` and `active`), deduplicates by `full_name` keeping the higher star count, and normalizes each item. `enforce_min_repos` guards the live-scan result against an empty/degraded scan before anything is persisted.
2. **Normalize + enrich** (`normalize_repo`, `ghstar/enrich.py`) — turns a raw API dict into the `Repo` dataclass, computing all derived fields at once: `classify` (focus area + relevance), `infer_subcategory`/`infer_modules`/`infer_scenarios`/`infer_risk_flags`, `rubric_scores` (commerce/enterprise/strategic), `trend_metrics` (momentum, maturity, stars-per-day), and `leap_notes`. **The `Repo` dataclass is the single contract that flows through the entire system** — DB writers, renderers, and the ETL agent all consume it.
3. **Select** (`balanced_selection`, `ghstar/collect.py`) — guarantees a per-category floor before filling remaining slots by strategic score, so no single focus area dominates the report.
4. **Persist** (`init_db` / `save_to_db`, `ghstar/store.py`) — writes to SQLite tables `repositories`, `repo_snapshots`, `daily_reports`, `leap_notes`. `ensure_snapshot_columns` does lightweight additive schema migration on existing DBs.
5. **Render** (`render_markdown`, `render_html`, `trend_payload`, `backlog_items`, `ghstar/render.py`) — `write_outputs` fans the selected repos into `reports/YYYY-MM-DD.md`, `public/report.html`, `public/latest.md`, and `public/data/{latest,history,backlog,trends}.json`.

Key flag interactions in `main`: `--from-db` re-renders outputs from existing SQLite snapshots without hitting the network (incompatible with `--no-db`); `--fixture` reads a local JSON file instead of the API; `--no-db` renders without persisting. Classification keywords live in `FOCUS_AREAS` and search terms in `SEARCH_QUERIES` at the top of the file — editing these changes what the radar finds and how it buckets results.

`scripts/ghstar_agent.py` ("GHstar_Agent") is a separate ETL layer that reuses `generate_report.collect` for scanning (and `generate_report.enforce_min_repos` to guard the result) but writes to a multi-schema warehouse. It defines `raw.github_repositories`, `curated.repositories`, `curated.repo_snapshots`, `curated.repo_metrics_timeseries`, and `mart.follow_up_backlog`. When `--targets` includes `timescale`, `ensure_pg_schema(enable_timescale=True)` promotes the metrics table to a hypertable via `create_hypertable`. `connect_with_retry` polls the DB on startup because the agent runs against freshly-started compose containers.

## Conventions worth knowing

- **Determinism**: a `report_date` (not `date.today()`) is threaded through `classify`, `normalize_repo`, `collect`, and `trend_metrics` so fixture runs produce byte-stable output. Preserve this when adding date-dependent logic — the smoke test asserts exact output for date `2026-05-28`.
- **No network in tests**: `tests/test_generate_report_smoke.py` copies the facade script **and the `ghstar/` package** to a tempdir and runs it against the fixture, asserting the exact stdout `{"date": ..., "repos": 2}` and that every expected output file is created. The fixture (`fixtures/github_repositories.json`) is the contract for the GitHub Search API response shape. The suite also covers the empty-result guard (`test_empty_result_guard.py`) and the site-data exporter contract (`test_export_site_data_smoke.py`); `run_smoke_test.py` discovers all `tests/test_*.py`, so new test modules are guarded by CI automatically.
- **Token resolution order** is consistently `GH_TOKEN` → `GITHUB_TOKEN` → `GHSTAR_GITHUB_TOKEN` in both scripts.
- **Generated files are committed**: the daily GitHub Actions workflow (`.github/workflows/daily-report.yml`, 13:15 UTC) regenerates and commits `reports/` + `public/`, then optionally deploys to Vercel. Treat these as build artifacts — don't hand-edit them.
- **SQLite history lives off `main`**: `data/ghstar.sqlite` is gitignored and **not** committed. The daily workflow restores it from the `data-latest` GitHub Release asset, appends today's snapshot (the run is incremental — history accumulates in the DB), then re-uploads it with `gh release upload --clobber`. This bounds git growth (the 1.3 MB binary was previously re-committed every day). Local/Docker runs use the on-disk file at the same path; tests use throwaway temp DBs.
- **Docker naming**: container/DB names are project-scoped and capitalized (`GHstar_Agent`, `GHstar_PG`, `GHstar_TimescaleDB`); image tags are lowercase (`ghstar-agent:local`) because Docker forbids uppercase image names. Postgres is on host port `54321`, TimescaleDB on `54322`.

Reference docs live in `docs/` (`database.md`, `docker.md`, `report-architecture.md`, `taxonomy.md`, `90-day-radar.md`).
