#!/usr/bin/env python3
"""probe/test_rig_resetgap.py — fixture suite for rig_resetgap.py (X-P6). Device-free."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rig_resetgap as R

SYNC_OUT = "esptool.py v4.5.1\nConnecting...\nChip is ESP32-D0WD-V3 (revision v3.1)\nMAC: 00:00\n"
NOSYNC_OUT = ("esptool.py v4.5.1\nConnecting...\nA fatal error occurred: Failed to connect to "
              "ESP32: No serial data received.\n")


class TestClassify(unittest.TestCase):
    def test_sync_is_wedged(self):
        self.assertTrue(R.classify_probe(0, SYNC_OUT))

    def test_no_sync_is_ok(self):
        self.assertFalse(R.classify_probe(2, NOSYNC_OUT))

    def test_rc0_without_chip_line_is_not_wedged(self):
        self.assertFalse(R.classify_probe(0, "Connecting...\n"))

    def test_timeout_is_not_wedged(self):
        self.assertFalse(R.classify_probe(124, "timed out"))


class TestArgvAndSummary(unittest.TestCase):
    def test_probe_never_resets(self):
        a = R.esptool_argv("/dev/x", probe=True)
        self.assertIn("no_reset", a)
        self.assertNotIn("default_reset", a)
        self.assertNotIn("hard_reset", a)
        self.assertEqual(a[a.index("--connect-attempts") + 1], "1")

    def test_reset_argv_boots_the_app(self):
        a = R.esptool_argv("/dev/x", probe=False)
        self.assertEqual(a[a.index("--after") + 1], "hard_reset")

    def test_summarize_counts(self):
        rows = [{"gap": 1.0, "wedged": False, "rc1": 0, "rc2": 0, "reenum": 2},
                {"gap": 1.0, "wedged": True, "rc1": 0, "rc2": 2, "reenum": 3},
                {"gap": 12.0, "wedged": False, "rc1": 0, "rc2": 0, "reenum": 2}]
        s = R.summarize(rows)
        self.assertEqual(s["1.0"], {"trials": 2, "wedged": 1, "reset_fail": 1, "reenum": 5})
        self.assertEqual(s["12.0"]["wedged"], 0)


class TestGuards(unittest.TestCase):
    def test_refuses_without_flag(self):
        self.assertEqual(R.main(["--gaps", "1", "--trials", "1"]), 3)

    def test_dry_run_touches_nothing(self):
        self.assertEqual(R.main(["--dry-run", "--gaps", "1", "--trials", "1"]), 0)


if __name__ == "__main__":
    unittest.main()
