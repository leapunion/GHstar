# GHstar SQLite Data Model

GHstar stores daily repository intelligence in `data/ghstar.sqlite` before rendering Markdown, HTML, and JSON outputs.

## Tables

### `repositories`

One row per GitHub repository.

- `full_name`: primary key, such as `openai/openai-agents-python`.
- `name`, `owner`, `url`, `description`, `language`.
- `topics_json`: repository topics as JSON.
- `created_at`, `updated_at`, `pushed_at`.
- `first_seen_date`, `last_seen_date`.

### `repo_snapshots`

One row per repository per report date.

- `full_name`, `snapshot_date`.
- `stars`, `forks`.
- `category`, `relevance`, `commerce_score`, `enterprise_score`, `strategic_score`, `action_level`.
- `age_days`, `days_since_push`, `stars_per_day`, `fork_ratio`, `momentum_score`, `maturity_level`.
- `repository_review`: generated review/commentary for why the repository matters and how urgently to inspect it.
- `modules_json`, `scenarios_json`.
- `leap_commerce`, `leap_enterprise`.

### `daily_reports`

One row per generated report.

- `report_date`.
- `repo_count`.
- `markdown_path`, `html_path`, `json_path`.
- `generated_at`.

### `leap_notes`

One row per repository per report date for follow-up tracking.

- `full_name`, `note_date`.
- `commerce_learning`, `enterprise_learning`.
- `follow_up_status`.
- `human_notes`.

## Daily Flow

```text
GitHub API or fixture
  -> normalize repository metadata
  -> compute 90-day trend and repository review dimensions
  -> upsert repositories
  -> upsert repo_snapshots
  -> upsert leap_notes
  -> write daily_reports
  -> render reports/YYYY-MM-DD.md
  -> render public/index.html
  -> render public/data/latest.json and history.json
```

## Why SQLite First

- No external service required.
- Works in GitHub Actions.
- Keeps historical snapshots in the repository.
- Can be queried locally by humans or agents.

## Postgres Migration Path

The schema is intentionally portable. When GHstar needs multi-user editing, dashboards, API access, or cross-project agent queries, migrate these tables to Neon or Supabase Postgres and keep static report generation as the final rendering step.
