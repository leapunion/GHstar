from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_report.py"
AGENT_SCRIPT = ROOT / "scripts" / "ghstar_agent.py"
FIXTURE = ROOT / "fixtures" / "github_repositories.json"
REPORT_DATE = "2026-05-28"


class GenerateReportSmokeTest(unittest.TestCase):
    def test_agent_script_compiles(self) -> None:
        subprocess.run([sys.executable, "-m", "py_compile", str(AGENT_SCRIPT)], cwd=ROOT, check=True)

    def test_fixture_run_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ghstar-smoke-") as tmp:
            tmp_root = Path(tmp)
            tmp_script_dir = tmp_root / "scripts"
            tmp_script_dir.mkdir()
            tmp_script = tmp_script_dir / "generate_report.py"
            shutil.copy2(SCRIPT, tmp_script)

            result = subprocess.run(
                [
                    sys.executable,
                    str(tmp_script),
                    "--fixture",
                    str(FIXTURE),
                    "--date",
                    REPORT_DATE,
                    "--limit",
                    "2",
                ],
                cwd=tmp_root,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(json.loads(result.stdout), {"date": REPORT_DATE, "repos": 2})

            markdown_path = tmp_root / "reports" / f"{REPORT_DATE}.md"
            html_path = tmp_root / "public" / "index.html"
            latest_md_path = tmp_root / "public" / "latest.md"
            data_path = tmp_root / "public" / "data" / "latest.json"
            history_path = tmp_root / "public" / "data" / "history.json"
            backlog_path = tmp_root / "public" / "data" / "backlog.json"
            trends_path = tmp_root / "public" / "data" / "trends.json"
            db_path = tmp_root / "data" / "ghstar.sqlite"

            for output_path in [markdown_path, html_path, latest_md_path, data_path, history_path, backlog_path, trends_path, db_path]:
                self.assertTrue(output_path.exists(), f"missing output: {output_path}")

            markdown = markdown_path.read_text(encoding="utf-8")
            latest_markdown = latest_md_path.read_text(encoding="utf-8")
            html = html_path.read_text(encoding="utf-8")
            data = json.loads(data_path.read_text(encoding="utf-8"))
            history = json.loads(history_path.read_text(encoding="utf-8"))
            backlog = json.loads(backlog_path.read_text(encoding="utf-8"))
            trends = json.loads(trends_path.read_text(encoding="utf-8"))

            self.assertEqual(latest_markdown, markdown)
            self.assertIn(f"# GitHub Top Star AI & Agent 90-Day Radar - {REPORT_DATE}", markdown)
            self.assertIn("90-Day Trend Signals", markdown)
            self.assertIn("Follow-Up Backlog", markdown)
            self.assertIn("Watchlist Flags", markdown)
            self.assertIn("Repository review", markdown)
            self.assertIn("leapunion-labs/agent-commerce-kit", markdown)
            self.assertIn("acme-ai/enterprise-rag-copilot", markdown)
            self.assertIn("Leap Agent Commerce OS Learning", markdown)
            self.assertIn("Leap Agentic Enterprise OS Learning", markdown)

            self.assertIn(f"<title>GHstar AI & Agent 90-Day Radar - {REPORT_DATE}</title>", html)
            self.assertIn("AI, Agent, Commerce, and Enterprise Top Star Radar", html)
            self.assertIn("90-Day Trend Signals", html)
            self.assertIn("Follow-Up Backlog", html)
            self.assertIn("category-filter", html)
            self.assertIn("Repository Review", html)
            self.assertIn("leapunion-labs/agent-commerce-kit", html)
            self.assertIn("Repositories Reviewed", html)

            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["full_name"], "leapunion-labs/agent-commerce-kit")
            self.assertEqual(data[0]["owner"], "leapunion-labs")
            self.assertEqual(data[0]["stars"], 1280)
            self.assertEqual(data[0]["category"], "AI Commerce")
            self.assertEqual(data[0]["subcategory"], "Commerce Agent")
            self.assertIn("Product intelligence", data[0]["modules"])
            self.assertIn("risk_flags", data[0])
            self.assertIn("follow_up_next_action", data[0])
            self.assertEqual(data[0]["age_days"], 27)
            self.assertGreater(data[0]["stars_per_day"], 0)
            self.assertGreaterEqual(data[0]["momentum_score"], 0)
            self.assertIn(data[0]["maturity_level"], {"emerging", "scaling", "established", "ecosystem leader"})
            self.assertIn("stars/day", data[0]["repository_review"])
            self.assertEqual(data[1]["full_name"], "acme-ai/enterprise-rag-copilot")
            self.assertEqual(data[1]["language"], "TypeScript")
            self.assertIn(data[1]["category"], {"Agentic Enterprise", "AI Infrastructure"})
            self.assertEqual(history[0]["report_date"], REPORT_DATE)
            self.assertEqual(history[0]["repo_count"], 2)
            self.assertGreaterEqual(len(backlog), 1)
            self.assertIn("next_action", backlog[0])
            self.assertEqual(trends["report_date"], REPORT_DATE)
            self.assertIn("subcategory_distribution", trends)
            self.assertIn("watchlist_flags", trends)


if __name__ == "__main__":
    unittest.main()
