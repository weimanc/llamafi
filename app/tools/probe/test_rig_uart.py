#!/usr/bin/env python3
"""probe/test_rig_uart.py — device-free suite for probe/rig_uart.py
(TASK-677/678 H-1). Every cell's parsing/decision function is pure, so this
never touches tmux or a device.

    python3 app/tools/probe/test_rig_uart.py [-v]
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probe import rig_uart as ru


def _burst_lines(n, pad, drop=None):
    pad_chars = "A" * pad
    lines = [f'{{"probe":"burst","phase":"begin","lines":{n},"pad":{pad},"thres":7,"t":0}}']
    for i in range(n):
        if drop is not None and i == drop:
            continue
        total = i & 0xFFFFFFFF
        for ch in pad_chars:
            total += ord(ch) & 0xFF
        lines.append(f"#{i} {pad_chars} {total & 0xFFFFFFFF:08x}")
    lines.append(f'{{"probe":"burst","phase":"end","lines":{n},"elapsedMs":1,'
                f'"bodTrips":0,"firstTripSeq":-1,"thres":7}}')
    return lines


class TestSerialburstCell(unittest.TestCase):
    def test_clean_burst_is_ok_with_zero_loss(self):
        r = ru.serialburst_cell(_burst_lines(50, 16))
        self.assertTrue(r["ok"])
        self.assertEqual(r["lost"], 0)
        self.assertEqual(r["L_bytes_upper_bound"], 0)

    def test_one_lost_line_is_reflected_in_L(self):
        r = ru.serialburst_cell(_burst_lines(50, 16, drop=10))
        self.assertFalse(r["ok"])
        self.assertEqual(r["lost"], 1)
        self.assertGreater(r["L_bytes_upper_bound"], 0)


class TestSinkPayload(unittest.TestCase):
    def test_payload_is_exact_length(self):
        p = ru.sink_payload(1000)
        self.assertEqual(len(p), 1000)

    def test_payload_is_printable_ascii(self):
        p = ru.sink_payload(500)
        self.assertTrue(all(0x20 <= b < 0x7F for b in p))

    def test_sum8_is_deterministic(self):
        p = ru.sink_payload(200)
        self.assertEqual(ru.sink_sum8(p), ru.sink_sum8(p))


class TestSerialsinkCellResult(unittest.TestCase):
    def test_full_receipt_matches(self):
        payload = ru.sink_payload(100)
        s = ru.sink_sum8(payload)
        text = f'{{"probe":"sink","bytes":100,"got":100,"sum":"{s}","bodTrips":0}}\n'
        r = ru.serialsink_cell_result(text, 100, s)
        self.assertTrue(r["ok"])
        self.assertEqual(r["L_bytes"], 0)

    def test_short_receipt_reports_loss(self):
        payload = ru.sink_payload(100)
        s = ru.sink_sum8(payload)
        text = '{"probe":"sink","bytes":100,"got":40,"sum":"deadbeef","bodTrips":0}\n'
        r = ru.serialsink_cell_result(text, 100, s)
        self.assertFalse(r["ok"])
        self.assertEqual(r["L_bytes"], 60)

    def test_no_reply_is_total_loss(self):
        r = ru.serialsink_cell_result("nothing here\n", 100, "deadbeef")
        self.assertFalse(r["ok"])
        self.assertEqual(r["L_bytes"], 100)


class TestSerialechoDiff(unittest.TestCase):
    def test_exact_echo_is_ok(self):
        sent = ["a", "b", "c"]
        echoed = ["E#a\n", "E#b\n", "E#c\n"]
        r = ru.serialecho_diff(sent, echoed)
        self.assertTrue(r["ok"])
        self.assertEqual(r["lost"], 0)
        self.assertEqual(r["mismatches"], 0)

    def test_missing_lines_are_lost_not_mismatched(self):
        sent = ["a", "b", "c"]
        echoed = ["E#a\n", "E#b\n"]
        r = ru.serialecho_diff(sent, echoed)
        self.assertFalse(r["ok"])
        self.assertEqual(r["lost"], 1)
        self.assertEqual(r["mismatches"], 0)

    def test_corrupted_line_is_a_mismatch(self):
        sent = ["a", "b", "c"]
        echoed = ["E#a\n", "E#X\n", "E#c\n"]
        r = ru.serialecho_diff(sent, echoed)
        self.assertFalse(r["ok"])
        self.assertEqual(r["mismatches"], 1)

    def test_non_echo_lines_are_ignored(self):
        sent = ["a"]
        echoed = ["some other log chatter\n", "E#a\n"]
        r = ru.serialecho_diff(sent, echoed)
        self.assertTrue(r["ok"])


class TestOneMbInfeasibility(unittest.TestCase):
    def test_max_bytes_is_well_under_1mb(self):
        self.assertLess(ru.SERIALSINK_MAX_BYTES, 1024 * 1024)

    def test_cell_size_is_64kb(self):
        self.assertEqual(ru.SERIALSINK_CELL_BYTES, 64 * 1024)


if __name__ == "__main__":
    unittest.main()
