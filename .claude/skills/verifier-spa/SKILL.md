---
name: verifier-spa
description: Evidence-capture protocol for the GHstar single-page app. Serves public/ and drives a real headless Chrome (via the DevTools Protocol, no Playwright install) to assert the date/category/keyword filters actually work, then screenshots. Use when verifying any change to public/index.html, public/app.js, the styles, or the site-data exporter.
---

# verifier-spa

The GHstar frontend is a static single page (`public/index.html` + `public/app.js`)
that loads the static data API under `public/data/site/` and filters client-side.
Its surface is **pixels + DOM behavior**, so verification means driving a real
browser, not running tests or import-and-calling functions.

This skill drives the page through `scripts/verify_spa.mjs` — a zero-dependency
verifier that starts a static server, launches whatever Chrome/Chromium is
installed over the DevTools Protocol (Node built-in `WebSocket`/`fetch`), and
asserts real behavior. It is deliberately *not* Playwright: for a static
client-filtered page, a headless Chrome already on the box (macOS dev / GitHub
runner) is enough and avoids a ~300MB browser download. Swap in Playwright only
if you need cross-browser coverage.

## Run it

```bash
# 1. Ensure the data API exists (reads the committed SQLite history; no network).
python3 scripts/export_site_data.py

# 2. Drive the page and assert behavior. Self-serves public/ on a random port.
node scripts/verify_spa.mjs --serve public --shot /tmp/ghstar-spa.png
```

Override the browser with `CHROME=/path/to/chrome node scripts/verify_spa.mjs ...`.
To point at an already-running server instead of self-serving:
`node scripts/verify_spa.mjs --url http://127.0.0.1:8000/`.

## What it asserts (exit 0 = all pass, 1 = a check failed, 3 = no browser/handle)

It prints a JSON report with one entry per check:

- **cards render** — `.repo-card` count > 0 after first paint (data fetched + rendered).
- **sparklines render** — inline SVG present in the corpus view (per-repo `history`).
- **category filter narrows** — selecting a category yields `0 < n ≤ initial`.
- **reset restores full list** — `#btn-reset` returns to the initial count.
- **keyword filter applies** — typing `agent` yields `0 < n ≤ initial`.
- **single-date snapshot view loads** — picking a date loads `snapshots/<date>.json` and renders.
- **no uncaught exceptions** — no `Runtime.exceptionThrown` during the run.

The screenshot (`--shot`) is the one frame a reviewer looks at. `console_errors`
in the report are soft signal (e.g. a missing favicon) and do not fail the run.

## Gotchas

- The **snapshot (single-date) view omits `history` by contract**, so it has no
  sparklines — assert sparklines on the default corpus view, before switching dates.
- In CI pass `--no-sandbox` is already set; the runner's `google-chrome-stable`
  is auto-detected. If the browser handle can't come up the verdict is exit 3
  (environment), which is distinct from a real behavioral FAIL (exit 1).
