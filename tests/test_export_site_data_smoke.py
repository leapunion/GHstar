from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATE_SCRIPT = ROOT / "scripts" / "generate_report.py"
EXPORT_SCRIPT = ROOT / "scripts" / "export_site_data.py"
FIXTURE = ROOT / "fixtures" / "github_repositories.json"
DATE_EARLY = "2026-05-28"
DATE_LATE = "2026-06-03"
EXPECTED_DATES = [DATE_EARLY, DATE_LATE]  # ascending, as the exporter emits them


class ExportSiteDataSmokeTest(unittest.TestCase):
    """Assert export_site_data.py emits the frozen site-data-contract (v1) shapes.

    Builds a real two-date SQLite history from the offline fixture (no network),
    then runs the exporter and checks index / corpus / snapshots against
    docs/site-data-contract.md.
    """

    def test_exporter_emits_site_data_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ghstar-export-smoke-") as tmp:
            tmp_root = Path(tmp)
            tmp_scripts = tmp_root / "scripts"
            tmp_scripts.mkdir()
            tmp_generate = tmp_scripts / "generate_report.py"
            shutil.copy2(GENERATE_SCRIPT, tmp_generate)
            # The facade imports the carved ghstar package — copy it alongside.
            shutil.copytree(GENERATE_SCRIPT.parent / "ghstar", tmp_scripts / "ghstar",
                            ignore=shutil.ignore_patterns("__pycache__"))

            db_path = tmp_root / "data" / "ghstar.sqlite"

            # Two dates, same 2 fixture repos each → a 2-point per-repo history
            # series (exercises the sparkline / "new since" path in the contract).
            for report_date in EXPECTED_DATES:
                subprocess.run(
                    [
                        sys.executable, str(tmp_generate),
                        "--fixture", str(FIXTURE),
                        "--date", report_date,
                        "--limit", "2",
                        "--db", str(db_path),
                    ],
                    cwd=tmp_root, check=True, capture_output=True, text=True,
                )

            self.assertTrue(db_path.exists(), "generate_report did not create the SQLite DB")

            out_dir = tmp_root / "site"
            result = subprocess.run(
                [
                    sys.executable, str(EXPORT_SCRIPT),
                    "--db", str(db_path),
                    "--out", str(out_dir),
                ],
                cwd=tmp_root, check=True, capture_output=True, text=True,
            )

            summary = json.loads(result.stdout)
            self.assertEqual(summary["repos"], 2)
            self.assertEqual(summary["dates"], 2)
            self.assertEqual(summary["files_written"], 4)  # index + corpus + 2 snapshots

            index_path = out_dir / "index.json"
            corpus_path = out_dir / "corpus.json"
            self.assertTrue(index_path.exists())
            self.assertTrue(corpus_path.exists())

            # ── index.json ────────────────────────────────────────────────
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["schema"], 1)
            self.assertEqual(index["dates"], EXPECTED_DATES)
            self.assertEqual(index["repo_count"], 2)
            self.assertIn("build", index)
            for facet_key in ("category", "subcategory", "language", "action_level"):
                self.assertIn(facet_key, index["facets"])
            self.assertTrue(index["facets"]["category"], "category facet is empty")
            # every repo carries a category, so the facet must cover all of them
            self.assertEqual(sum(index["facets"]["category"].values()), index["repo_count"])

            # ── corpus.json (repo-centric, carries history) ───────────────
            corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
            self.assertIsInstance(corpus, list)
            self.assertEqual(len(corpus), 2)
            by_name = {entry["full_name"]: entry for entry in corpus}
            self.assertIn("leapunion-labs/agent-commerce-kit", by_name)
            for entry in corpus:
                for field in ("full_name", "category", "stars", "history"):
                    self.assertIn(field, entry, f"corpus entry missing {field}")
                self.assertEqual(entry["first_seen_date"], DATE_EARLY)
                self.assertEqual(entry["last_seen_date"], DATE_LATE)
                history = entry["history"]
                self.assertEqual(len(history), 2, "expected a 2-point history series")
                self.assertEqual([h["date"] for h in history], EXPECTED_DATES)  # ascending
                for point in history:
                    for hk in ("date", "stars", "momentum_score"):
                        self.assertIn(hk, point)

            # ── snapshots/<date>.json (day-centric, no history) ───────────
            for date_str in EXPECTED_DATES:
                snap_path = out_dir / "snapshots" / f"{date_str}.json"
                self.assertTrue(snap_path.exists(), f"missing snapshot file for {date_str}")
                snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
                self.assertIsInstance(snapshot, list)
                self.assertEqual(len(snapshot), 2)
                for entry in snapshot:
                    for field in ("full_name", "category", "stars"):
                        self.assertIn(field, entry)
                    self.assertNotIn("history", entry, "snapshot entries must omit history")


if __name__ == "__main__":
    unittest.main()
