#!/usr/bin/env python3
"""probe/test_rig_ladder.py — device-free suite for probe/rig_ladder.py (PROP-011
X-P2). Refusals refuse; --dry-run touches nothing; the boot parser and the
stopping rule decide correctly on recorded boot text. No tmux, no device, no pio.
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

BOOT_TRIP = """[bootphase] 0 reset
[bootreason] 1 POWERON
[bod] armed thres=3 regBefore=0x43ffc000 regAfter=0x7bffc000 ena=1 rstEna=0 intEnaBefore=1 intEna=1 isr=1
[wifi] IP 192.168.1.181
[bod] TRIP tag=wifi-end t=1533ms thres=3 trips=1 det=0 us=1533000 dur=0 min=3 ctx=03
[bootphase] 6 ready
"""
BOOT_QUIET = BOOT_TRIP.replace(
    "[bod] TRIP tag=wifi-end t=1533ms thres=3 trips=1 det=0 us=1533000 dur=0 min=3 ctx=03\n", "")


def _cli(*args):
    return subprocess.run([sys.executable, "probe/rig_ladder.py", *args],
                          cwd=TOOLS, capture_output=True, text=True, timeout=20)


class TestParseAndRule(unittest.TestCase):
    def test_trip_boot(self):
        b = rl.parse_boot(BOOT_TRIP)
        self.assertEqual((b["tripped"], b["ready"], b["bootreason"], b["armed_thres"], b["wifi_ip"]),
                         (True, True, 1, 3, True))

    def test_quiet_boot(self):
        self.assertFalse(rl.parse_boot(BOOT_QUIET)["tripped"])

    def test_run_tag_trip_is_not_a_boot_trip(self):
        self.assertFalse(rl.parse_boot(BOOT_QUIET + "[bod] TRIP tag=run t=9000ms thres=3\n")["tripped"])

    def test_usb_drop_is_recorded_not_raised(self):
        b = rl.parse_boot("[bootphase] 0 reset\n[bootreason] 1 POWERON\n"
                          "[rig] usb-drop at +0.61s: device reports readiness to read but returned no data\n")
        self.assertTrue(b["usb_drop"])
        self.assertFalse(b["ready"])
        self.assertFalse(rl.parse_boot(BOOT_TRIP)["usb_drop"])

    def test_b_boot_is_lowest_tripping_level(self):
        self.assertEqual(rl.b_boot({7: 3, 5: 3, 3: 1, 2: 0}), 3)
        self.assertIsNone(rl.b_boot({7: 0}))

    def test_stop_rule(self):
        self.assertTrue(rl.keep_descending(1))
        self.assertFalse(rl.keep_descending(0))

    def test_rung_flags(self):
        self.assertEqual(rl.build_flags(1, 7), "-DBARE_BOD_THRES=7")
        self.assertEqual(rl.build_flags(4, 0), "-DBARE_WIFI -DBARE_TFT -DBARE_SD -DBARE_BOD_THRES=0")


class TestCliGuards(unittest.TestCase):
    def test_refuses_when_f4_not_landed(self):
        with tempfile.TemporaryDirectory() as d:
            p = _cli("--bare-rig-dir", d, "--i-know-this-resets-the-board")
            self.assertEqual(p.returncode, 3)
            self.assertIn("F-4", p.stderr)

    def test_refuses_without_the_reset_flag_even_with_f4(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "src", "debug"))
            open(os.path.join(d, "src", "debug", "bodWatch.h"), "w").close()
            p = _cli("--bare-rig-dir", d)
            self.assertEqual(p.returncode, 3)
            self.assertIn("--i-know-this-resets-the-board", p.stderr)

    def test_dry_run_touches_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p = _cli("--dry-run", "--bare-rig-dir", d, "--levels", "7", "--rungs", "1")
            self.assertEqual(p.returncode, 0)
            self.assertIn("[dry-run]", p.stdout)


if __name__ == "__main__":
    unittest.main()
