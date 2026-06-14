#!/usr/bin/env python3
"""Run the deterministic local smoke suite for GHstar.

Discovers every ``tests/test_*.py`` (report generation, the empty-result guard,
and the site-data exporter contract) so newly added test modules are guarded by
CI without touching this runner.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", str(ROOT), "-v"],
        cwd=ROOT,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
