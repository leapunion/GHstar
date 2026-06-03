# GHstar Development Log

Reverse-chronological engineering log. One entry per working session: what
shipped, why, what was verified, and what's next. Forward-looking plan lives at
the bottom of the latest entry.

---

## 2026-06-03 — Data-service layer + single-page SPA, verification harness, full pipeline run

### Shipped (merged to `main`)

- **PR #1** (`7ecc4b5`) — *data-service layer + single-page SPA*. Evolves the
  product from a daily-overwritten static snapshot into a data-driven pipeline:
  `SQLite full history → static data API → SPA`.
  - `scripts/export_site_data.py` — reads the full snapshot history from SQLite
    and emits `public/data/site/{index.json, corpus.json, snapshots/<date>.json}`
    per the frozen contract (`docs/site-data-contract.md`). Stdlib only.
  - `public/index.html` + `public/app.js` — one page, filters all content
    client-side by **date / category / subcategory / language / action-level /
    keyword**, with per-repo sparklines. Vanilla JS, no build step.
  - Generator's legacy daily page moved `index.html → report.html`, freeing
    `index.html` for the SPA shell (smoke test + `daily_reports` record updated).
- **PR #2** (`01f8906`) — *SPA behavior verifier + deploy guardrail*.
  - `scripts/verify_spa.mjs` — zero-dependency verifier. Self-serves `public/`,
    drives installed Chrome over the DevTools Protocol (Node built-in
    `WebSocket`/`fetch`), and asserts **behavior** (cards render, sparklines,
    filters narrow, reset restores, single-date snapshot view, no exceptions).
    Deliberately not Playwright — avoids a ~300MB download for a static page.
  - `.claude/skills/verifier-spa/SKILL.md` — replayable evidence-capture protocol.
  - `.github/workflows/verify-spa.yml` — runs the verifier on every PR touching
    the frontend/exporter; uploads the screenshot artifact.
  - `daily-report.yml` — Vercel `--prod` deploy (and deployed-output check) now
    gated on `github.ref == 'refs/heads/main'`. Also bumped `checkout@v5` /
    `setup-python@v6` (Node 24).

### Why

The old frontend was *generated*: today's 50 repos were hardcoded into ~900 lines
of HTML, so the page could only ever show "today," and the rich layered storage
(SQLite/PG/Timescale full history) never reached it. The two "truth sources"
(daily-overwritten `latest.json` vs durable SQLite) had drifted. The static
export closes that gap with **zero backend** (keeps free Vercel hosting; keyword
search runs in-browser).

### Process note (high/low model split, concurrent)

Built with Opus designing (froze the data contract + made the one shared-file
edit) and Sonnet/Haiku executing **four streams concurrently** against the frozen
contract with disjoint file ownership — zero conflicts. Verified the concurrency
model works in practice; the multiplier was contract-first + file partitioning,
not the tool count.

### Verified end-to-end (full pipeline run, all real data, 2026-06-03)

| Stage | Action | Evidence |
|---|---|---|
| Scan / ingest | live GitHub Search API, 15 queries × 2 modes (~100s) | 50 repos today |
| ETL / enrich | normalize → `Repo` (class, scores, momentum, risk, leap notes) | — |
| Storage · SQLite | `repositories/repo_snapshots/daily_reports/leap_notes` | 102 repos / 324 snapshots / 7 dates |
| Storage · PostgreSQL | container agent → `raw/curated/mart` schemas | raw 250 · curated.repos 65 · snapshots 50 · mart 50 |
| Storage · TimescaleDB | `curated.repo_metrics_timeseries` **hypertable** | registered (`event_time` dim, 1 chunk), 50 rows |
| Data service | `export_site_data.py` → static API | 82 repos / 7 dates / 9 files |
| Frontend | real headless Chrome behavior assertions | **PASS 7/7** (82 cards, 63 sparklines, filters 82→59→72, single-date→50) |

CI caught a genuine dev-vs-CI gap: the verifier passed locally but failed on the
runner (`exit 3`, Chrome couldn't start in the container's small `/dev/shm`);
fixed with `--disable-dev-shm-usage`. This is exactly why verification belongs in
CI, not just on a dev box.

### Known debt / observations

- **Double scan.** `generate_report.py` and `ghstar_agent.py` each run a
  *separate* live GitHub scan, so SQLite and PG/Timescale are independent writes
  with different dedup counts (50 vs 65 distinct this run). 2× API spend + drift.
- **PG/Timescale serve nothing.** The SPA reads the static export (SQLite-derived
  only); the layered warehouse is currently write-only.
- **No exporter/agent tests.** Only `generate_report` has a smoke test.
- **Unbounded git growth.** The daily Action commits `site/` JSON + the SQLite
  binary every day.
- **No empty-result guard.** A 0-repo scan (token expiry / API change) would
  silently commit an empty report and deploy it.

---

## Next steps (prioritized)

### P0 — correctness & safety (do next)

1. **Unify ingest: one scan feeds all stores.** Refactor so a single
   `collect()` result is persisted to SQLite + PG + Timescale, and render/export
   read from storage. Kills the double API spend and the SQLite-vs-PG divergence.
   (This is the deferred "split the 1500-line monolith" debt — do the carve now:
   `model / collect / enrich / store / render`.)
2. **Empty-result guard.** Fail the daily run (and the agent) if a scan yields
   fewer than N repos, before anything is committed or deployed.
3. **Exporter smoke test.** Fixture-/SQLite-based test asserting the
   `site-data-contract` shapes (index/corpus/snapshots, `history` present). Wire
   into `run_smoke_test.py` so CI guards the data service.

### P1 — robustness & coverage

4. **Run `verify-spa` on the daily pipeline too** (post-export, non-deploy job),
   so regressions in *real daily data* are caught, not just on PRs.
5. **Tame git growth.** Move `public/data/site/**` + `data/ghstar.sqlite` off the
   main branch (dedicated `data` branch or build artifact / release asset);
   serve the SQLite history from there.

### P2 — product & scale

6. **Decide PG/Timescale's role.** Either build a small read API over the
   hypertable for time-series the static export can't do (true momentum trends,
   per-repo star history charts), or document them as analytics-only and drop
   them from the default `--targets` to cut operational surface.
7. **SPA UX:** real virtualization (replace the 200-cap + "show more"),
   date-range mode, URL-deep-linkable filter state, mobile layout.
8. **Taxonomy quality:** the keyword-count classifier is coarse; revisit
   category/subcategory inference against the now-larger corpus (`docs/taxonomy.md`).
