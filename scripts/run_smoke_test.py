#!/usr/bin/env python3
"""Run deterministic local smoke tests for GHstar report generation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "tests" / "test_generate_report_smoke.py"


def main() -> int:
    completed = subprocess.run([sys.executable, str(TEST)], cwd=ROOT)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
