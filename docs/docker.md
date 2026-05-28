# GHstar Docker Runtime

GHstar can run locally in Docker with a stable Python runtime and a mounted SQLite database.

## Services

| Service | Purpose |
| --- | --- |
| `ghstar` | Runs `scripts/generate_report.py` and writes reports plus SQLite history. |
| `ghstar-smoke` | Runs deterministic smoke tests in the same Python image. |
| `ghstar-web` | Serves the generated `public/` site with Nginx at `http://localhost:8080`. |

## Database

The SQLite database is mounted at:

```text
./data/ghstar.sqlite -> /app/data/ghstar.sqlite
```

The container uses:

```text
GHSTAR_DB=/app/data/ghstar.sqlite
```

This keeps the database visible to git, local tools, GitHub Actions, and future migration scripts.

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
