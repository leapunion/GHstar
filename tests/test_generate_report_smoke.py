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
FIXTURE = ROOT / "fixtures" / "github_repositories.json"
REPORT_DATE = "2026-05-28"


class GenerateReportSmokeTest(unittest.TestCase):
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

            for output_path in [markdown_path, html_path, latest_md_path, data_path]:
                self.assertTrue(output_path.exists(), f"missing output: {output_path}")

            markdown = markdown_path.read_text(encoding="utf-8")
            latest_markdown = latest_md_path.read_text(encoding="utf-8")
            html = html_path.read_text(encoding="utf-8")
            data = json.loads(data_path.read_text(encoding="utf-8"))

            self.assertEqual(latest_markdown, markdown)
            self.assertIn(f"# GitHub Top Star AI & Agent Report - {REPORT_DATE}", markdown)
            self.assertIn("leapunion-labs/agent-commerce-kit", markdown)
            self.assertIn("acme-ai/enterprise-rag-copilot", markdown)
            self.assertIn("Leap Agent Commerce OS Learning", markdown)
            self.assertIn("Leap Agentic Enterprise OS Learning", markdown)

            self.assertIn(f"<title>GHstar AI & Agent Report - {REPORT_DATE}</title>", html)
            self.assertIn("AI, Agent, Commerce, and Enterprise Top Star Radar", html)
            self.assertIn("leapunion-labs/agent-commerce-kit", html)
            self.assertIn("Repositories Reviewed", html)

            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["full_name"], "leapunion-labs/agent-commerce-kit")
            self.assertEqual(data[0]["owner"], "leapunion-labs")
            self.assertEqual(data[0]["stars"], 1280)
            self.assertEqual(data[0]["category"], "AI Commerce")
            self.assertIn("Product intelligence", data[0]["modules"])
            self.assertEqual(data[1]["full_name"], "acme-ai/enterprise-rag-copilot")
            self.assertEqual(data[1]["language"], "TypeScript")
            self.assertIn(data[1]["category"], {"Agentic Enterprise", "AI Infrastructure"})


if __name__ == "__main__":
    unittest.main()
