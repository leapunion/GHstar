# GHstar Docker Runtime

GHstar can run locally in Docker with a stable Python runtime and a mounted SQLite database.

## Services

| Service | Purpose |
| --- | --- |
| `ghstar` | Runs `scripts/generate_report.py` and writes reports plus SQLite history. |
| `ghstar-agent` | Runs `scripts/ghstar_agent.py` for 30-day Top 50 scanning and ETL into SQLite, PostgreSQL, and TimescaleDB. |
| `ghstar-pg` | PostgreSQL storage service with container/database name `GHstar_PG`. |
| `ghstar-timescaledb` | TimescaleDB storage service with container/database name `GHstar_TimescaleDB`. |
| `ghstar-smoke` | Runs deterministic smoke tests in the same Python image. |
| `ghstar-web` | Serves the generated `public/` site with Nginx at `http://localhost:8080`. |

Docker image references use lower-case names because Docker image references cannot contain uppercase letters. Project-visible container, volume, and database names use the `GHstar_*` naming convention.

| Runtime | Image | Container / database |
| --- | --- | --- |
| Agent | `ghstar-agent:local` | `GHstar_Agent` |
| PostgreSQL | `ghstar-pg:local` | `GHstar_PG` |
| TimescaleDB | `ghstar-timescaledb:local` | `GHstar_TimescaleDB` |

## Databases

The SQLite database is mounted at:

```text
./data/ghstar.sqlite -> /app/data/ghstar.sqlite
```

The container uses:

```text
GHSTAR_DB=/app/data/ghstar.sqlite
```

This keeps the database visible to git, local tools, GitHub Actions, and future migration scripts.

The Agent ETL runtime also starts:

| Database | Container | Database name | Host port | Internal DSN |
| --- | --- | --- | ---: | --- |
| PostgreSQL | `GHstar_PG` | `GHstar_PG` | `54321` | `postgresql://GHstar:GHstar@ghstar-pg:5432/GHstar_PG` |
| TimescaleDB | `GHstar_TimescaleDB` | `GHstar_TimescaleDB` | `54322` | `postgresql://GHstar:GHstar@ghstar-timescaledb:5432/GHstar_TimescaleDB` |

The ETL writes three logical layers:

- `raw.github_repositories`: run-scoped JSON payloads.
- `curated.repositories` and `curated.repo_snapshots`: normalized repository dimensions and daily metrics.
- `mart.follow_up_backlog`: prioritized review queue for product and engineering.
- TimescaleDB only: `curated.repo_metrics_timeseries` hypertable for time-series metrics.

## Commands

Build and run smoke tests:

```bash
docker compose run --rm ghstar-smoke
```

Run fixture validation without changing project outputs:

```bash
docker compose run --rm ghstar-smoke
```

The smoke test copies the generator into a temporary workspace, so sample repositories do not pollute the real history database or generated report files.

Generate a live report:

```bash
GH_TOKEN="$GHSTAR_GITHUB_TOKEN" docker compose run --rm ghstar
```

Start the automatic 30-day Top 50 Agent ETL loop:

```bash
docker compose up -d ghstar-pg ghstar-timescaledb ghstar-agent
```

`GHstar_Agent` runs immediately and then sleeps for `GHSTAR_AGENT_INTERVAL_SECONDS`, defaulting to `86400` seconds.

Run a one-off Agent ETL without changing the long-running service:

```bash
docker compose run --rm ghstar-agent \
  python scripts/ghstar_agent.py --days 30 --limit 50 --targets sqlite,postgres,timescale
```

Query PostgreSQL from the container:

```bash
docker compose exec ghstar-pg psql -U GHstar -d GHstar_PG \
  -c "select count(*) from curated.repo_snapshots;"
```

Query TimescaleDB from the container:

```bash
docker compose exec ghstar-timescaledb psql -U GHstar -d GHstar_TimescaleDB \
  -c "select count(*) from curated.repo_metrics_timeseries;"
```

Rebuild static outputs from the existing SQLite database:

```bash
docker compose run --rm ghstar \
  python scripts/generate_report.py \
  --from-db \
  --date 2026-05-28 \
  --limit 24 \
  --db /app/data/ghstar.sqlite
```

Serve the static report:

```bash
docker compose up ghstar-web
```

Open:

```text
http://localhost:8080
```

## Postgres Upgrade Path

SQLite is the right first step because the system still publishes static files and runs in GitHub Actions. Move to Postgres when GHstar needs:

- multi-user review and tagging;
- dashboard queries over long history;
- API access for downstream agents;
- cross-project joins with Leap data;
- row-level permissions or hosted backups.

The current schema in `docs/database.md` is portable to Postgres.
