"""GHstar report-generation library, carved from the former generate_report.py monolith.

Layers (dependency order): model <- enrich <- {collect, store, render}.
``scripts/generate_report.py`` remains a thin CLI facade that re-exports this package.
"""
