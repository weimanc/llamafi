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


class TestBodmitProof(unittest.TestCase):
    """PROP-011 X-P2b-2: the `[bodmit] inwindow ... duty=` line is the
    applied-state proof that the REQUESTED mask actually took effect this
    boot. Reviewer fix #4 (2026-09-11): proof compares requested vs applied
    mask, not just the applied mask's own internal duty consistency — the
    original EXP-036 run's `bodmit=1` boots all read `mask=0` (the old value
    silently carried over) and the buggy proof called that `proved=True`."""

    def test_requested_matches_applied_bit0_off_with_duty_zero_is_proved(self):
        text = "[bodmit] inwindow mask=1 t=120ms duty=0 txdbm=8\n"
        r = rs.parse_bodmit_proof(text, requested=1)
        self.assertTrue(r["seen"])
        self.assertEqual((r["mask"], r["duty"]), (1, 0))
        self.assertTrue(r["proved"])

    def test_requested_bit0_but_duty_nonzero_is_not_proved(self):
        text = "[bodmit] inwindow mask=1 t=120ms duty=128 txdbm=8\n"
        r = rs.parse_bodmit_proof(text, requested=1)
        self.assertFalse(r["proved"])

    def test_requested_zero_matches_applied_zero_is_proved(self):
        text = "[bodmit] inwindow mask=0 t=120ms duty=255 txdbm=8\n"
        r = rs.parse_bodmit_proof(text, requested=0)
        self.assertTrue(r["proved"])

    def test_requested_one_but_applied_stayed_zero_is_not_proved(self):
        # The original EXP-036 driver bug: bodmit=1 was requested but the log
        # shows mask=0 (the mitigation never took). Old code called this
        # "proved" because it only checked duty-given-mask, never
        # requested-vs-mask. Must be False now.
        text = "[bodmit] inwindow mask=0 t=120ms duty=256 txdbm=8\n"
        r = rs.parse_bodmit_proof(text, requested=1)
        self.assertFalse(r["proved"])

    def test_requested_zero_but_applied_was_one_is_not_proved(self):
        # The mirror-image fault also seen in the original run (send #3):
        # requested 0, board applied 1 anyway.
        text = "[bodmit] inwindow mask=1 t=120ms duty=0 txdbm=8\n"
        r = rs.parse_bodmit_proof(text, requested=0)
        self.assertFalse(r["proved"])

    def test_absent_line_is_not_seen(self):
        r = rs.parse_bodmit_proof(_BOOT_SLICE_TRIPPED, requested=0)
        self.assertFalse(r["seen"])
        self.assertFalse(r["proved"])


class TestSliceSinceBootphase0(unittest.TestCase):
    """Reviewer fault #2: analyse only the NEW boot, not a leftover tail of
    the previous one that a too-fast read_from() offset can still contain."""

    def test_returns_text_from_first_bootphase0_onward(self):
        raw = ("[bod] TRIP tag=run t=9000ms thres=7\n"   # tail of the OLD boot
               "[bootphase] 0 reset\n[bootphase] 1 fs\n[bootphase] 6 ready\n")
        sliced = rs.slice_since_bootphase0(raw)
        self.assertIsNotNone(sliced)
        self.assertNotIn("tag=run", sliced)
        self.assertTrue(sliced.startswith("[bootphase] 0"))

    def test_none_when_no_bootphase0_yet(self):
        self.assertIsNone(rs.slice_since_bootphase0("still booting, nothing yet\n"))

    def test_old_boots_trip_line_never_leaks_into_the_slice(self):
        # Reproduces the original bug directly: the previous (level=7) boot's
        # trip line sits before the new boot's [bootphase] 0. Slicing must
        # drop it so parse_boot_slice sees only the new boot.
        raw = ("[bod] TRIP tag=wifi-end t=1ms thres=7 trips=9 det=0 us=1 dur=0 min=7 ctx=00\n"
               "[bootphase] 0 reset\n[bootphase] 3 wifi\n"
               "[bod] TRIP tag=wifi-end t=1ms thres=2 trips=10 det=0 us=1 dur=0 min=2 ctx=00\n"
               "[bootphase] 6 ready\n")
        sliced = rs.slice_since_bootphase0(raw)
        r = rs.parse_boot_slice(sliced)
        self.assertEqual(r["min"], 2)   # the NEW boot's trip, not the old min=7


class TestAcks(unittest.TestCase):
    def test_bod_query_ack_seen(self):
        self.assertTrue(rs.bod_query_ack_seen(
            '{"ok":true,"cmd":"bod","thresNow":7,"bootThres":2,"tripsSinceArm":0}\n'))

    def test_bod_query_ack_not_confused_with_set_ack(self):
        self.assertFalse(rs.bod_query_ack_seen(
            '{"ok":true,"cmd":"bod","bootThres":2,"note":"takes effect on next reboot"}\n'))

    def test_bod_set_ack_level_reads_requested_value(self):
        text = '{"ok":true,"cmd":"bod","bootThres":2,"note":"takes effect on next reboot"}\n'
        self.assertEqual(rs.bod_set_ack_level(text), 2)

    def test_bod_set_ack_level_none_when_only_query_seen(self):
        text = '{"ok":true,"cmd":"bod","thresNow":7,"bootThres":2,"tripsSinceArm":0}\n'
        self.assertIsNone(rs.bod_set_ack_level(text))

    def test_bod_set_ack_takes_the_latest_of_several(self):
        text = ('{"ok":true,"cmd":"bod","bootThres":5,"note":"x"}\n'
               '{"ok":true,"cmd":"bod","bootThres":2,"note":"x"}\n')
        self.assertEqual(rs.bod_set_ack_level(text), 2)

    def test_bodmit_ack_mask(self):
        text = '{"ok":true,"cmd":"bodmit","bootMit":1,"note":"takes effect on next reboot"}\n'
        self.assertEqual(rs.bodmit_ack_mask(text), 1)

    def test_bodmit_ack_mask_absent(self):
        self.assertIsNone(rs.bodmit_ack_mask("nothing here\n"))


class TestArmedLevelFrom(unittest.TestCase):
    def test_reads_the_armed_threshold(self):
        text = ("[bootphase] 0 reset\n"
                "[bod] armed thres=2 regBefore=0x43ffc000 regAfter=0x53ffc000 ena=1\n")
        self.assertEqual(rs.armed_level_from(text), 2)

    def test_none_when_absent(self):
        self.assertIsNone(rs.armed_level_from("[bootphase] 0 reset\n"))


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


class TestLowLevelFloor(unittest.TestCase):
    """EXP-035: an arm level <=1 dropped USB on every WiFi boot and left the board
    armed there with its console unreachable. The sweep must refuse it by default."""

    def _run(self, *args):
        tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run([sys.executable, "probe/rig_sweep.py", *args],
                              cwd=tools, capture_output=True, text=True, timeout=20)

    def test_refuses_level_1_even_when_confirmed(self):
        p = self._run("--levels", "7,1", "--i-know-this-resets-the-board")
        self.assertEqual(p.returncode, 3)
        self.assertIn("--allow-low-levels", p.stderr)

    def test_default_levels_stop_at_2(self):
        p = self._run("--dry-run")
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("bod 1", p.stdout)
        self.assertNotIn("bod 0", p.stdout)


class TestBodmitFlag(unittest.TestCase):
    def test_dry_run_shows_bodmit_send(self):
        p = self._run_dry("--dry-run", "--levels", "2", "--reps", "1", "--bodmit", "1")
        self.assertIn("bodmit 1", p.stdout)

    def test_bodmit_omitted_by_default(self):
        p = self._run_dry("--dry-run", "--levels", "2", "--reps", "1")
        self.assertNotIn("send: bodmit", p.stdout)

    def test_bodmit_out_of_range_rejected(self):
        p = self._run_dry("--dry-run", "--levels", "2", "--reps", "1", "--bodmit", "4")
        self.assertNotEqual(p.returncode, 0)

    def _run_dry(self, *args):
        return subprocess.run([sys.executable, "probe/rig_sweep.py", *args],
                              cwd=TOOLS, capture_output=True, text=True, timeout=20)


if __name__ == "__main__":
    unittest.main()
