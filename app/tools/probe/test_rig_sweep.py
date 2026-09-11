#!/usr/bin/env python3
"""probe/test_rig_sweep.py — device-free suite for probe/rig_sweep.py
(TASK-677 H-1). Also proves the driver REFUSES to run without
--i-know-this-resets-the-board (this driver is the one that resets the
board every rep — PROP-011-runbook.md §0.1 rule 2).

    python3 app/tools/probe/test_rig_sweep.py [-v]
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

from probe import rig_sweep as rs


_BOOT_SLICE_TRIPPED = """\
[bootphase] 0 reset
[bootphase] 1 fs
[bootphase] 2 display
[bootphase] 3 wifi
[bod] TRIP tag=wifi-end t=1500ms thres=7 trips=1 det=0 us=797017 dur=0 min=7 ctx=03
[bootphase] 4 time
[bootphase] 5 services
[bootphase] 6 ready
"""

_BOOT_SLICE_NO_TRIP = """\
[bootphase] 0 reset
[bootphase] 1 fs
[bootphase] 2 display
[bootphase] 3 wifi
[bootphase] 4 time
[bootphase] 5 services
[bootphase] 6 ready
"""


class TestParseBootSlice(unittest.TestCase):
    def test_finds_the_wifi_end_trip(self):
        r = rs.parse_boot_slice(_BOOT_SLICE_TRIPPED)
        self.assertTrue(r["tripped"])
        self.assertEqual(r["min"], 7)
        self.assertEqual(r["dur"], 0)

    def test_no_trip_when_absent(self):
        r = rs.parse_boot_slice(_BOOT_SLICE_NO_TRIP)
        self.assertFalse(r["tripped"])
        self.assertIsNone(r["min"])

    def test_other_tags_are_not_confused_for_wifi_end(self):
        text = "[bod] TRIP tag=run t=1ms thres=7 trips=1 det=0 us=1 dur=5 min=3 ctx=00\n"
        r = rs.parse_boot_slice(text)
        self.assertFalse(r["tripped"])

    def test_alt_field_order_still_parses(self):
        # F-1's real ordering is dur= before min=; make sure a hypothetical
        # reorder is still caught by the ALT pattern.
        text = ("[bod] TRIP tag=wifi-end t=1ms thres=7 trips=1 det=0 "
               "us=1 min=2 dur=9 ctx=00\n")
        r = rs.parse_boot_slice(text)
        self.assertTrue(r["tripped"])
        self.assertEqual(r["min"], 2)
        self.assertEqual(r["dur"], 9)


class TestReachedBootphase6(unittest.TestCase):
    def test_true_when_present(self):
        self.assertTrue(rs.reached_bootphase6(_BOOT_SLICE_TRIPPED))

    def test_false_when_boot_stalled_earlier(self):
        self.assertFalse(rs.reached_bootphase6("[bootphase] 3 wifi\n"))


class TestRefusal(unittest.TestCase):
    def test_refuses_without_the_confirm_flag(self):
        p = subprocess.run(
            [sys.executable, "probe/rig_sweep.py", "--levels", "7", "--reps", "1"],
            cwd=TOOLS, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 3)
        self.assertIn("REFUSED", p.stderr)

    def test_dry_run_never_refuses_and_touches_nothing(self):
        p = subprocess.run(
            [sys.executable, "probe/rig_sweep.py", "--dry-run",
            "--levels", "7", "--reps", "1"],
            cwd=TOOLS, capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 0)
        self.assertIn("[dry-run]", p.stdout)


if __name__ == "__main__":
    unittest.main()
