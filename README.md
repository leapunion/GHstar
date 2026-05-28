# GHstar

Daily GitHub Top Star reports for AI agents, Agentic Enterprise, AI commerce, and AI infrastructure.

## Automation

The daily workflow is defined in `.github/workflows/daily-report.yml`.

- Runs every day at 13:15 UTC and can also be started manually with `workflow_dispatch`.
- Executes `python scripts/generate_report.py`.
- Commits generated report files under `reports/` and `public/`.
- Deploys `public/` to Vercel when Vercel secrets are configured.

Generated outputs:

- `reports/YYYY-MM-DD.md`
- `public/index.html`
- `public/latest.md`
- `public/data/latest.json`
- `public/data/history.json`
- `data/ghstar.sqlite`

## Deployment

Vercel serves the static site from `public/`, configured in `vercel.json`.

Required GitHub repository secrets:

- `GHSTAR_GITHUB_TOKEN`: GitHub token used by the report generator for GitHub Search API requests. If omitted, the workflow falls back to the built-in `GITHUB_TOKEN`, but a dedicated token is recommended for rate limits.
- `VERCEL_TOKEN`: Vercel access token used by the workflow deployment step.
- `VERCEL_ORG_ID`: Vercel team or user ID for the project.
- `VERCEL_PROJECT_ID`: Vercel project ID for this site.

The workflow skips the Vercel deploy step unless all three Vercel secrets are present.

## Local Usage

Run deterministic smoke tests:

```bash
python3 scripts/run_smoke_test.py
```

Generate a local report from the fixture:

```bash
python3 scripts/generate_report.py --fixture fixtures/github_repositories.json --date 2026-05-28 --limit 2
```

Generate a live report from GitHub:

```bash
GH_TOKEN="$GHSTAR_GITHUB_TOKEN" python3 scripts/generate_report.py --days 7 --limit 24
```

The generator writes repository metadata, daily snapshots, report records, and Leap learning notes into `data/ghstar.sqlite` before rendering Markdown, HTML, and JSON outputs.

Database details are documented in `docs/database.md`.

## Docker

Run the deterministic smoke test in Docker:

```bash
docker compose run --rm ghstar-smoke
```

Generate a report in Docker:

```bash
docker compose run --rm ghstar
```

Serve the generated static site:

```bash
docker compose up ghstar-web
```

Docker runtime details are documented in `docs/docker.md`.

## Publishing Checklist

1. Authenticate GitHub CLI:

```bash
gh auth login -h github.com
```

2. Push this project to `leapunion/GHstar`:

```bash
git remote add origin https://github.com/leapunion/GHstar.git
git branch -M main
git push -u origin main
```

3. Add repository secrets in GitHub:

```text
GHSTAR_GITHUB_TOKEN
VERCEL_TOKEN
VERCEL_ORG_ID
VERCEL_PROJECT_ID
```

4. In Vercel, link the GitHub repository to the `leapunion/GHstar` project or keep using the GitHub Actions deploy step.
