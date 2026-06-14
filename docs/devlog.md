# GHstar Development Log

Reverse-chronological engineering log. One entry per working session: what
shipped, why, what was verified, and what's next. Forward-looking plan lives at
the bottom of the latest entry.

---

## 2026-06-13 — Tame git growth: SQLite history off `main` (release asset)

Roadmap **P1#5**. `data/ghstar.sqlite` (a 1.3 MB binary) was re-committed by the daily
Action every run — ~31 MB of binary churn already in `main`'s history and climbing.

### Shipped (PR — branch `tame-git-growth-sqlite-off-main`)

- **Untracked the DB on `main`.** `git rm --cached data/ghstar.sqlite` + gitignore. The
  path stays configurable (`GHSTAR_DB` / `--db`), so no Python logic changed; Docker
  (host volume mount) and local dev (on-disk file) are unaffected; tests already use
  throwaway temp DBs.
- **Durable off-`main` store = the `data-latest` Release asset.** Seeded it with the
  current DB (17 accumulated snapshot dates, 117 repos / 824 snapshots) — byte-identical
  download round-trip verified — so no history is lost in the cutover.
- **Daily workflow is now restore → append → upload.** New *Restore SQLite history*
  step (`gh release download data-latest`) before generate; new *Persist SQLite history*
  step (`gh release upload --clobber`, create-if-missing) after generate. Dropped the DB
  from the commit `git add` line. The empty-result guard (P0-2) still gates generate, so
  an empty scan never clobbers good history.

### Why a release asset (not cache / LFS / orphan branch)

The run is **incremental** (history accumulates inside the DB), so the prior DB must
persist across runs. A release asset is durable (unlike Actions cache, which evicts after
~7 idle days), bounded (clobbered, not versioned — unlike LFS), uses in-repo infra (`gh`
+ the existing `contents: write` token), and is the simplest to script reliably.

### Not done (flagged)

- **History rewrite.** The ~31 MB already in `main`'s past commits is *not* reclaimed —
  that needs `git filter-repo` + force-push to `main` (rewrites shared history, breaks
  existing clones). Left as an explicit, opt-in destructive follow-up.
- `public/data/site/**` JSON still commits to `main` — it's *served* via Vercel, so it
  can't simply move off-`main` like the (un-served) DB did.

---

## 2026-06-03 (session 2) — P0 safety net: empty-result guard, exporter test, monolith carve

Worked the P0 block from the roadmap (items 1–3). The architectural half of P0-1
(unify ingest) was deferred by decision — see **Deferred**.

### Shipped (in working tree; verified, not yet committed)

- **P0-2 — empty-result guard.** New importable `enforce_min_repos(repos, minimum,
  source)` in `ghstar/collect.py`, raising `SystemExit` *before* any persist / render
  / commit / deploy when a **live** scan returns fewer than the floor (a 0-repo result
  almost always means token expiry or a Search-API change, not a quiet day). Wired into
  `generate_report.main` (live branch only — `--fixture` / `--from-db` exempt) and
  `ghstar_agent.run_agent` (before any SQLite/PG/Timescale write). New `--min-repos`
  flag on both (default 1); the daily workflow now passes `--min-repos 10`.
- **P0-3 — exporter smoke test + suite wiring.** `tests/test_export_site_data_smoke.py`
  builds a real two-date SQLite history from the fixture, runs `export_site_data.py`,
  and asserts the frozen `site-data-contract` (index schema/dates/facets, corpus
  `history` series ascending, day-snapshots omit `history`).
  `tests/test_empty_result_guard.py` unit-tests the guard. `run_smoke_test.py` now
  **discovers** the whole `tests/` suite (added `tests/__init__.py`), so new test
  modules auto-guard in CI. Also added `.github/workflows/tests.yml` — runs the
  suite on every PR + push to `main` (no path filter), closing a gap where the
  smoke suite previously ran *only* inside the schedule-only daily job and so never
  gated PRs.
- **P0-1 (carve only) — split the monolith.** The ~1500-line `generate_report.py` is
  now a 67-line CLI facade over a new `scripts/ghstar/` package, carved in dependency
  order `model ← enrich ← {collect, store, render}`. The facade re-exports the full
  surface, so `generate_report.collect`, `.Repo`, `.save_to_db`, … still resolve
  (back-compat for `ghstar_agent.py` + the tests). The two tempdir tests now copy the
  package alongside the script.

### Verified

- Full smoke suite: **8/8 OK**, including the byte-stable 2026-05-28 generator test.
- **Byte-diff old (git HEAD) vs new facade** on the fixture: every deterministic text
  output (`reports/*.md`, `report.html`, `latest.md`, `latest/history/backlog/trends.json`)
  **identical** — only the `generated_at` wall-clock field differs (non-deterministic
  in the original too). Function bodies were sliced verbatim; behavior is unchanged.
- `ghstar_agent` still imports the facade; `repo_payload` / `asdict(Repo)` work.

### Deferred (by decision)

- **Unify ingest** (the other half of roadmap P0-1) is *not* done. The "double scan"
  turned out to span two runtimes — CI `generate_report` (SQLite + render) vs the
  docker-compose `ghstar_agent` (PG/Timescale) — so unifying is entangled with **P2#6
  "PG/Timescale's role,"** a product decision rather than a refactor. Chose to land the
  safe carve now and defer the architectural unify until that role is decided.

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
