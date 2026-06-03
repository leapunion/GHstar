# GHstar Site Data Contract (v1)

This is the **frozen contract** between the data-service layer (`scripts/export_site_data.py`)
and the single-page frontend (`public/index.html` + `public/app.js`). Both sides build against
this document independently. Do not change field names without bumping `schema`.

## Routing / file layout

The generator (`generate_report.py`) keeps producing the legacy daily snapshot page at
`public/report.html` (renamed from `index.html`). The SPA owns `public/index.html`.

The exporter reads the **full history** from `data/ghstar.sqlite` (tables `repositories`,
`repo_snapshots`, `daily_reports`) and writes everything under `public/data/site/`:

```
public/data/site/
  index.json                 # manifest + global facets + date list  (SPA first paint)
  corpus.json                # repo-centric, deduped (latest snapshot per repo + history)
  snapshots/YYYY-MM-DD.json  # one file per report date (day-centric view)
```

These are **append/overwrite by date** — `index.html`/`app.js` are committed once and never
regenerated daily; only `public/data/site/**` changes per run.

## `index.json`

```jsonc
{
  "schema": 1,
  "build": "2026-06-03T06:21:00Z",     // ISO8601 UTC, exporter run time
  "dates": ["2026-05-28", "2026-05-29", ...],   // ascending; drives the date picker
  "repo_count": 1842,                  // distinct repos in corpus.json
  "facets": {                          // value -> count, drives filter dropdowns
    "category":     {"AI Agent Framework": 35, "Agentic Enterprise": 5, ...},
    "subcategory":  {"Enterprise Workflow": 25, ...},
    "language":     {"Python": 24, "TypeScript": 14, ...},
    "action_level": {"strategic watch": 12, ...}
  }
}
```

## `corpus.json` (repo-centric, default view)

Array. One entry per distinct `full_name`, carrying the **latest** snapshot's fields plus a
compact `history` series for a sparkline. Fields mirror the `Repo` dataclass in
`generate_report.py` (do not rename):

```jsonc
[{
  "full_name": "ModelEngine-Group/nexent",
  "name": "nexent", "owner": "ModelEngine-Group", "url": "https://github.com/...",
  "description": "...", "language": "Python",
  "stars": 4848, "forks": 621,
  "topics": ["agent", "rag", ...],
  "created_at": "2025-04-28T10:44:33Z", "pushed_at": "2026-06-03T03:41:34Z",
  "category": "AI Agent Framework", "subcategory": "Enterprise Workflow",
  "relevance": 49,
  "modules": [...], "scenarios": [...], "risk_flags": [...],
  "commerce_score": 0, "enterprise_score": 0, "strategic_score": 91,
  "action_level": "strategic watch",
  "stars_per_day": 12.3, "momentum_score": 96, "maturity_level": "scaling",
  "repository_review": "...",
  "first_seen_date": "2026-05-28", "last_seen_date": "2026-06-03",
  "history": [                          // ascending by date; for sparkline + "new since"
    {"date": "2026-05-28", "stars": 4600, "momentum_score": 90},
    {"date": "2026-06-03", "stars": 4848, "momentum_score": 96}
  ]
}]
```

## `snapshots/YYYY-MM-DD.json` (day-centric view)

Array of repos as seen on that report date. Same per-repo fields as `corpus.json` **minus**
`history` (the date is implied by the filename). This is exactly today's `latest.json` shape,
but dated and never overwritten.

## Frontend filter semantics (informative)

- **date**: `all` (corpus) | a single `YYYY-MM-DD` (loads that snapshot file) | range (filter corpus by `last_seen_date`).
- **category / subcategory / language / action_level**: multi-select, value ∈ facet keys.
- **keyword**: case-insensitive substring over `name` + `description` + `topics` (client-side; no server).
- **sort**: one of `momentum_score | strategic_score | stars | stars_per_day` (desc).

## Validation (for `check_public_outputs.py`)

`index.json` parses and has `schema`, `dates` (non-empty), `facets`; `corpus.json` is a non-empty
array whose entries carry `full_name`, `category`, `stars`, `history`; every date in
`index.json.dates` has a matching `snapshots/<date>.json` that parses to a non-empty array.
