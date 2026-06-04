from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_report  # noqa: E402  (scripts/ added to path above)


class EmptyResultGuardTest(unittest.TestCase):
    """Unit-test enforce_min_repos — the P0 empty-result guard shared by
    generate_report.py (live scan) and ghstar_agent.py (agent live scan)."""

    def test_zero_repos_raises(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            generate_report.enforce_min_repos([], 1)
        self.assertIn("empty-result guard", str(ctx.exception))

    def test_below_floor_raises(self) -> None:
        with self.assertRaises(SystemExit):
            generate_report.enforce_min_repos([object(), object()], 5)

    def test_custom_source_in_message(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            generate_report.enforce_min_repos([], 1, source="agent live scan")
        self.assertIn("agent live scan", str(ctx.exception))

    def test_meeting_floor_passes(self) -> None:
        # At or above the floor must not raise.
        generate_report.enforce_min_repos([object()], 1)
        generate_report.enforce_min_repos([object(), object(), object()], 2)

    def test_zero_minimum_disables_guard(self) -> None:
        # A minimum of 0 must never trip, even on an empty scan.
        generate_report.enforce_min_repos([], 0)


if __name__ == "__main__":
    unittest.main()
