#!/usr/bin/env python3
"""probe/test_burst_check.py — negative suite for probe/burst_check.py
(TASK-557/677). Device-free: every fixture is generated in-process to match
`cmdSerialBurst`'s exact wire format (app/src/debug/serialConsole/
cmdMisc.cpp:278), then deliberately corrupted per test to prove the checker
actually notices (BP-068).

    python3 app/tools/probe/test_burst_check.py [-v]
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probe import burst_check as bc


def _checksum(seq: int, pad_chars: str) -> int:
    total = seq & 0xFFFFFFFF
    for ch in pad_chars:
        total += ord(ch) & 0xFF
    return total & 0xFFFFFFFF


def _gen(n: int, pad: int, bod_trips: int = 0, first_trip_seq: int = -1):
    """A clean burst transcript, matching cmdSerialBurst's format exactly."""
    lines = [f'{{"probe":"burst","phase":"begin","lines":{n},"pad":{pad},'
            f'"thres":7,"t":0}}']
    pad_chars = "A" * pad
    for i in range(n):
        lines.append(f"#{i} {pad_chars} {_checksum(i, pad_chars):08x}")
    lines.append(f'{{"probe":"burst","phase":"end","lines":{n},'
                f'"elapsedMs":123,"bodTrips":{bod_trips},'
                f'"firstTripSeq":{first_trip_seq},"thres":7}}')
    return lines


class TestCleanBurst(unittest.TestCase):
    def test_clean_burst_passes(self):
        r = bc.check(_gen(50, 16))
        self.assertTrue(r.began)
        self.assertTrue(r.ended)
        self.assertEqual(r.lost(), [])
        self.assertEqual(r.corrupt, [])
        self.assertEqual(r.duplicate_count(), 0)
        self.assertTrue(r.ok())

    def test_bod_trips_and_first_seq_carried_through(self):
        r = bc.check(_gen(10, 8, bod_trips=2, first_trip_seq=4))
        self.assertEqual(r.bod_trips, 2)
        self.assertEqual(r.first_trip_seq, 4)

    def test_interleaved_chatter_tolerated(self):
        """A gap only counts if the sequence number is truly missing — a
        stray log line cut into the stream must not register as loss."""
        lines = _gen(20, 8)
        # splice unrelated chatter into the middle, as another task's printf
        # landing between two burst lines would.
        lines.insert(10, "[I][hb] uptime=00:00:30 disc=0 heap=100000")
        lines.insert(5, '{"var":"heap","ok":true,"val":123456}')
        r = bc.check(lines)
        self.assertTrue(r.ok())
        self.assertEqual(len(r.seen), 20)


class TestLossDetection(unittest.TestCase):
    def test_missing_line_detected_as_lost(self):
        lines = _gen(20, 8)
        # Remove the data line for seq 7 (index 8: begin + 7 data lines before it)
        del lines[8]
        r = bc.check(lines)
        self.assertFalse(r.ok())
        self.assertEqual(r.lost(), [7])

    def test_multiple_gaps_all_reported(self):
        lines = _gen(30, 8)
        for seq in (25, 10, 3):  # delete from the end first to keep indices valid
            del lines[1 + seq]
        r = bc.check(lines)
        self.assertEqual(r.lost(), [3, 10, 25])
        self.assertFalse(r.ok())


class TestCorruption(unittest.TestCase):
    def test_bit_flip_in_checksum_detected(self):
        lines = _gen(10, 8)
        # corrupt the checksum on seq 3's line (index 1+3)
        bad = lines[4].replace(_checksum(3, "A" * 8).__format__("08x"), "ffffffff")
        self.assertNotEqual(bad, lines[4])
        lines[4] = bad
        r = bc.check(lines)
        self.assertFalse(r.ok())
        self.assertEqual(len(r.corrupt), 1)
        self.assertEqual(r.corrupt[0][0], 3)

    def test_pad_byte_flip_detected(self):
        """Corrupting a PAD BYTE (not the printed checksum) must also be
        caught — this is the case that actually matters: silent bit rot in
        the payload, not the hex digits."""
        lines = _gen(5, 8)
        parts = lines[3].split(" ")   # "#2 AAAAAAAA <sum>"
        parts[1] = "B" + parts[1][1:]  # flip one pad byte
        lines[3] = " ".join(parts)
        r = bc.check(lines)
        self.assertFalse(r.ok())
        self.assertEqual(len(r.corrupt), 1)


class TestDuplicates(unittest.TestCase):
    def test_duplicated_line_flagged(self):
        lines = _gen(10, 8)
        lines.insert(3, lines[3])   # repeat one data line verbatim
        r = bc.check(lines)
        self.assertEqual(r.duplicate_count(), 1)
        self.assertFalse(r.ok())


class TestTruncatedStream(unittest.TestCase):
    def test_no_end_line_fails(self):
        lines = _gen(10, 8)[:-1]   # drop the end JSON
        r = bc.check(lines)
        self.assertTrue(r.began)
        self.assertFalse(r.ended)
        self.assertFalse(r.ok())

    def test_no_begin_line_fails(self):
        lines = _gen(10, 8)[1:]
        r = bc.check(lines)
        self.assertFalse(r.began)
        self.assertFalse(r.ok())

    def test_empty_stream_fails_cleanly(self):
        r = bc.check([])
        self.assertFalse(r.began)
        self.assertFalse(r.ended)
        self.assertFalse(r.ok())
        # must not raise formatting a report over a totally empty result
        bc.format_report(r)


class TestFormatReport(unittest.TestCase):
    def test_report_mentions_pass_on_clean_burst(self):
        out = bc.format_report(bc.check(_gen(5, 8)))
        self.assertIn("PASS", out)

    def test_report_mentions_fail_and_lost_seq_on_gap(self):
        lines = _gen(5, 8)
        del lines[3]
        out = bc.format_report(bc.check(lines))
        self.assertIn("FAIL", out)
        self.assertIn("lost", out)


if __name__ == "__main__":
    unittest.main()
