#!/usr/bin/env python3
"""probe/test_rig_uart.py — device-free suite for probe/rig_uart.py
(TASK-677/678 H-1). Every cell's parsing/decision function is pure, so this
never touches tmux or a device.

DEVICE-FREE IS NOT THE SAME AS TIME-FREE (TASK-684). Three of these cases drive
the real `run_echo_cell`/`wait_console_idle` against a stub, and those functions
poll with `time.sleep` — so the suite cost 28.9 s of pure sleeping, 112 calls,
which is 40 % of `run/check`'s whole host-gate budget for a suite that talks to
nothing. They now run under `lib.replay`'s virtual clock, which TASK-628 built
for exactly this ("the suite's ~250 fixed sleeps cost nothing"). `dilation=1.0`
is deliberate: sleeps advance the clock by exactly what was asked, so every
deadline loop terminates on the same condition and after the same number of
iterations it always did — the clock is faithful, it just does not wait. The
cases below assert that directly, so a future change that turns a poll loop into
a no-op cannot hide behind the fast clock.

    python3 app/tools/probe/test_rig_uart.py [-v]
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.replay import VirtualClock, virtual_time
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


class TestBurstTimeoutScalesWithPayload(unittest.TestCase):
    """EXP-029 (TASK-677) found the old fixed 60s wait too short for
    lines=20000 pad=64/200: the DUT log shows 20000x64 actually finished
    cleanly at elapsedMs=139663, and 20000x200 at elapsedMs=375765, well
    past the old 60s constant — the driver gave up early both times and the
    next cell's command landed on a still-busy console. burst_timeout_s
    (formula: lines*(pad+16)/11520*1.5 + 15) must cover both measured
    times."""

    def test_formula_matches_spec(self):
        lines, pad = 2000, 8
        expected = lines * (pad + 16) / 11520 * 1.5 + 15
        self.assertAlmostEqual(ru.burst_timeout_s(lines, pad), expected)

    def test_20000_pad64_exceeds_the_old_fixed_60s(self):
        self.assertGreater(ru.burst_timeout_s(20000, 64), 60.0)

    def test_20000_pad64_covers_the_measured_139663ms(self):
        self.assertGreaterEqual(ru.burst_timeout_s(20000, 64), 139.663)

    def test_20000_pad200_covers_the_measured_375765ms(self):
        self.assertGreaterEqual(ru.burst_timeout_s(20000, 200), 375.765)

    def test_larger_pad_needs_more_time(self):
        self.assertGreater(ru.burst_timeout_s(20000, 200),
                           ru.burst_timeout_s(20000, 64))


class TestEchoWindows(unittest.TestCase):
    """echo_windows is a pure splitter — no device touched."""

    def test_splits_into_fixed_size_chunks(self):
        sent = [f"l{i}" for i in range(10)]
        w = ru.echo_windows(sent, 4)
        self.assertEqual(w, [["l0", "l1", "l2", "l3"],
                              ["l4", "l5", "l6", "l7"],
                              ["l8", "l9"]])

    def test_window_le_zero_is_one_giant_window(self):
        sent = ["a", "b", "c"]
        self.assertEqual(ru.echo_windows(sent, 0), [["a", "b", "c"]])

    def test_empty_sent_is_no_windows(self):
        self.assertEqual(ru.echo_windows([], 8), [])

    def test_exact_multiple_has_no_short_trailing_window(self):
        sent = [f"l{i}" for i in range(8)]
        w = ru.echo_windows(sent, 4)
        self.assertEqual(len(w), 2)
        self.assertEqual(len(w[-1]), 4)


class TestCountEchoed(unittest.TestCase):
    def test_counts_only_e_hash_lines(self):
        text = "E#a\nsome log chatter\nE#b\nE#c\n"
        self.assertEqual(ru.count_echoed(text), 3)

    def test_zero_on_no_replies_yet(self):
        self.assertEqual(ru.count_echoed('{"probe":"echo","phase":"begin"}'), 0)


class _FakeEchoLog:
    """Simulates the DUT's tmux log for run_echo_cell: send_literal() feeds
    lines through drop_lines/corrupt_lines and appends their E#-prefixed
    echo immediately (fast synchronous DUT), so windowing can be exercised
    without a device or a sleep-driven poll loop."""

    def __init__(self, drop_lines=frozenset(), corrupt_lines=frozenset()):
        self.buf = ""
        self.sent_seen = 0
        self.drop_lines = drop_lines
        self.corrupt_lines = corrupt_lines

    def size(self):
        return len(self.buf)

    def send(self, cmd):
        self.buf += cmd + "\n"

    def send_literal(self, text):
        for line in text.splitlines():
            idx = self.sent_seen
            self.sent_seen += 1
            if idx in self.drop_lines:
                continue
            echoed = "XXCORRUPT" if idx in self.corrupt_lines else line
            self.buf += f"E#{echoed}\n"

    def read_from(self, offset):
        return self.buf[offset:]


class TestRunEchoCellWindowed(unittest.TestCase):
    """run_echo_cell against a fake, instantly-responsive log — checks the
    windowing loop terminates promptly and reports the same shape
    serialecho_diff would from a real transcript."""

    def _run(self, n_lines, window, fake):
        """-> (result, clock). The clock is returned, not swallowed: what the
        polling loops did with time is an assertable property here, not an
        invisible side effect (TASK-684).

        `wait_console_idle` is stubbed out so the clock measures the WINDOWING
        LOOP and nothing else. It has its own case below, and leaving it in
        added two IDLE_QUIET_S waits to every reading — which is exactly what
        made the first draft of these assertions read 5.1 s for all three cases
        and conclude, wrongly, that no window ever reached its deadline.
        """
        orig_mt = ru.mt
        orig_stamp = ru.rigwatch.stamp
        orig_idle = ru.wait_console_idle
        ru.mt = fake
        ru.rigwatch.stamp = lambda *a, **k: None
        ru.wait_console_idle = lambda *a, **k: True
        clock = VirtualClock()
        try:
            with virtual_time(clock):
                return ru.run_echo_cell(n_lines, window=window), clock
        finally:
            ru.mt = orig_mt
            ru.rigwatch.stamp = orig_stamp
            ru.wait_console_idle = orig_idle

    #: What `run_echo_cell` sleeps unconditionally, outside any poll loop: the
    #: settle after `serialecho` and the drain before the final read. Every
    #: reading below is this plus whatever the windowing loop chose to wait,
    #: so the assertions are stated as deadlines burned, never as wall clock.
    FIXED_SLEEP_S = 0.5 + 1.0

    def _windows_burned(self, clock) -> float:
        """How many window deadlines the loop ran out. Derived from the probe's
        own constant, so re-tuning ECHO_WINDOW_WAIT_S cannot silently change
        what these cases assert. A float quotient by construction — callers
        compare it with assertAlmostEqual, not assertEqual."""
        return (clock.slept_s - self.FIXED_SLEEP_S) / ru.ECHO_WINDOW_WAIT_S

    def test_all_lines_echoed_clean(self):
        r, clock = self._run(20, 4, _FakeEchoLog())
        self.assertTrue(r["ok"])
        self.assertEqual(r["sent"], 20)
        self.assertEqual(r["echoed"], 20)
        self.assertEqual(r["lost"], 0)
        # The fake answers immediately, so every window breaks on its first
        # look and none reaches its deadline. This is the "windowing loop
        # terminates promptly" claim in the class docstring, which until now
        # was asserted only by the suite finishing at all.
        self.assertAlmostEqual(self._windows_burned(clock), 0)

    def test_dropped_line_reported_lost(self):
        r, clock = self._run(10, 3, _FakeEchoLog(drop_lines={5}))
        self.assertFalse(r["ok"])
        self.assertEqual(r["lost"], 1)
        # `cumulative` is a running total, so once a line is missing NO later
        # window can reach it either: with 10 lines in windows of 3, the drop at
        # line 5 falls in window 2 and windows 2, 3 and 4 all poll to their
        # deadline. Three, not one — the loop does not re-baseline after a loss,
        # and that is worth pinning: it is the difference between a lost line
        # costing 5 s and costing the rest of the cell.
        self.assertAlmostEqual(self._windows_burned(clock), 3)

    def test_corrupted_line_reported_mismatch(self):
        r, clock = self._run(10, 3, _FakeEchoLog(corrupt_lines={2}))
        self.assertFalse(r["ok"])
        self.assertEqual(r["mismatches"], 1)
        # A corrupted line still ARRIVES and still carries its E# prefix, so
        # `count_echoed` is satisfied and no window waits: corruption is caught
        # by the diff afterwards, never by a timeout. The contrast with the
        # dropped-line case above is the point of having both.
        self.assertAlmostEqual(self._windows_burned(clock), 0)


class TestWaitConsoleIdle(unittest.TestCase):
    """wait_console_idle must observe a quiet log without ever touching the
    device (mt.size() stubbed to a fixed value simulates an already-idle
    console)."""

    def test_returns_true_when_already_idle(self):
        import types
        fake_mt = types.SimpleNamespace(size=lambda: 42)
        orig = ru.mt
        ru.mt = fake_mt
        clock = VirtualClock()
        try:
            with virtual_time(clock):
                self.assertTrue(ru.wait_console_idle(quiet_s=0.05,
                                                     max_wait_s=2.0))
        finally:
            ru.mt = orig
        # It observed quiet by WAITING for it, not by returning early: the poll
        # step is 0.3 s, so reaching a 0.05 s quiet window costs at least one
        # sleep. Without this, a `wait_console_idle` that never polled at all
        # would still pass this case.
        self.assertGreaterEqual(clock.sleeps, 1)
        self.assertLess(clock.slept_s, 2.0, "must not reach max_wait_s")


if __name__ == "__main__":
    unittest.main()
