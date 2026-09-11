#!/usr/bin/env python3
"""probe/test_rig_ladder.py — device-free suite for probe/rig_ladder.py
(TASK-677 H-1). Proves the F-4-not-landed refusal actually refuses, and that
--dry-run never does (fixture/tempdir only, no tmux, no device, no pio).

    python3 app/tools/probe/test_rig_ladder.py [-v]
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

from probe import rig_ladder as rl


class TestF4Landed(unittest.TestCase):
    def test_false_when_marker_absent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(rl.f4_landed(os.path.join(d, "bodWatch.h")))

    def test_true_when_marker_present(self):
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "bodWatch.h")
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write("// stub\n")
            self.assertTrue(rl.f4_landed(marker))


class TestCliRefusal(unittest.TestCase):
    def test_refuses_when_f4_not_landed(self):
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run(
                [sys.executable, "probe/rig_ladder.py",
                "--bare-rig-dir", d, "--levels", "7", "--rungs", "1", "--reps", "1"],
                cwd=TOOLS, capture_output=True, text=True, timeout=20)
            self.assertEqual(p.returncode, 3)
            self.assertIn("REFUSED", p.stderr)
            self.assertIn("F-4", p.stderr)

    def test_dry_run_never_refuses_and_touches_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run(
                [sys.executable, "probe/rig_ladder.py", "--dry-run",
                "--bare-rig-dir", d, "--levels", "7", "--rungs", "1", "--reps", "1"],
                cwd=TOOLS, capture_output=True, text=True, timeout=20)
            self.assertEqual(p.returncode, 0)
            self.assertIn("[dry-run]", p.stdout)

    def test_still_refuses_even_with_marker_present(self):
        """F-4 landing only lifts the refusal-message half; the flash/monitor
        loop itself is not implemented (module docstring) — this pins that
        so a future edit cannot silently promise more than exists."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "src"))
            with open(os.path.join(d, "src", "bodWatch.h"), "w", encoding="utf-8") as fh:
                fh.write("// stub\n")
            p = subprocess.run(
                [sys.executable, "probe/rig_ladder.py",
                "--bare-rig-dir", d, "--levels", "7", "--rungs", "1", "--reps", "1"],
                cwd=TOOLS, capture_output=True, text=True, timeout=20)
            self.assertEqual(p.returncode, 3)
            self.assertNotIn("REFUSED", p.stderr)  # different message this time
            self.assertIn("not yet implemented", p.stderr)


if __name__ == "__main__":
    unittest.main()
