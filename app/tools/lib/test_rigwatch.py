#!/usr/bin/env python3
"""lib/test_rigwatch.py — negative suite for lib/rigwatch.py (TASK-677).

Device-free throughout: every fixture below is a plain string or a file this
test writes itself under a tempdir. No serial port, no journalctl subprocess,
no network. Kernel-line fixtures are transcribed from real `journalctl -k`
output captured on this rig 2026-09-10 (see CLAUDE.md's rigwatch note), so a
regression in the parsing regexes is caught against real text, not a
synthetic stand-in that could quietly drift from what the kernel actually
prints.

    python3 app/tools/lib/test_rigwatch.py [-v]
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import rigwatch as rw


def _kjson(message: str, rt_us: int) -> str:
    return json.dumps({"MESSAGE": message, "__REALTIME_TIMESTAMP": str(rt_us),
                       "SYSLOG_IDENTIFIER": "kernel"})


class TestParseKernelLine(unittest.TestCase):
    """Real captured lines (CLAUDE.md's rigwatch note). The DUT is on sysfs
    port '1-1'; the fingerprint reader is on '1-4' and must never appear in a
    filtered stream — that is the whole reason port_filter exists."""

    def test_attach_on_dut_port_counted(self):
        line = _kjson("usb 1-1: new full-speed USB device number 108 using xhci_hcd",
                      1789064196909066)
        ev = rw.parse_kernel_line(line, "1-1")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["kind"], "attach")
        self.assertEqual(ev["devnum"], 108)
        self.assertAlmostEqual(ev["host_ts"], 1789064196.909066, places=3)

    def test_detach_on_dut_port(self):
        line = _kjson("usb 1-1: USB disconnect, device number 107", 1789064196000000)
        ev = rw.parse_kernel_line(line, "1-1")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["kind"], "detach")
        self.assertEqual(ev["devnum"], 107)

    def test_error_line(self):
        line = _kjson("usb 1-1: device not accepting address 67, error -71",
                      1789064197000000)
        ev = rw.parse_kernel_line(line, "1-1")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["kind"], "error")

    def test_ch341_tty_attach(self):
        line = _kjson("usb 1-1: ch341-uart converter now attached to ttyUSB0",
                      1789064197500000)
        ev = rw.parse_kernel_line(line, "1-1")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["kind"], "enum")
        self.assertEqual(ev["tty"], "ttyUSB0")

    def test_ch341_tty_detach_no_port_number_in_message(self):
        # The ch341-uart disconnect line does not repeat "usb 1-1:" at all —
        # it is driver-emitted, not core-usb-emitted. With an explicit port
        # filter this line is correctly DROPPED (nothing to match it against);
        # the daemon relies on the paired core-usb detach line instead, which
        # always does carry the port.
        line = _kjson("ch341-uart ttyUSB1: ch341-uart converter now disconnected "
                      "from ttyUSB1", 1789064198000000)
        ev = rw.parse_kernel_line(line, "1-1")
        self.assertIsNone(ev)

    def test_unrelated_port_dropped(self):
        """The decisive case: the fingerprint reader lives on 1-4. A rigwatch
        that does not filter by port would count its resets as DUT events —
        exactly the false-positive PROP-011 was written to stop."""
        line = _kjson("usb 1-4: reset full-speed USB device number 9 using xhci_hcd",
                      1789064199000000)
        ev = rw.parse_kernel_line(line, "1-1")
        self.assertIsNone(ev)

    def test_unrelated_port_similar_prefix_not_confused(self):
        """1-1 must not accidentally match 1-14 or 1-1.2 (a hub sub-port)."""
        line = _kjson("usb 1-14: new full-speed USB device number 3", 1789064199500000)
        ev = rw.parse_kernel_line(line, "1-1")
        self.assertIsNone(ev)

    def test_malformed_json_ignored(self):
        self.assertIsNone(rw.parse_kernel_line("not json at all", "1-1"))

    def test_no_port_filter_keeps_matching_lines(self):
        line = _kjson("usb 1-4: new full-speed USB device number 9", 1789064199000000)
        ev = rw.parse_kernel_line(line, None)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["kind"], "attach")


class _SummaryFixture(unittest.TestCase):
    """Base: builds a temp RIG_EVENTS + MONITOR_LOG.ts pair per test."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="rigwatch-test-")
        self._events = os.path.join(self._tmp, "rig-events.jsonl")
        self._monlog = os.path.join(self._tmp, "serial.log")
        self._sidecar = rw.ts_sidecar_path(self._monlog)
        self._dutlines = os.path.join(self._tmp, "dut-lines.jsonl")
        self._old_env = {
            "RIG_EVENTS": os.environ.get("RIG_EVENTS"),
            "MONITOR_LOG": os.environ.get("MONITOR_LOG"),
            "RIG_DUT_LINES": os.environ.get("RIG_DUT_LINES"),
            "RIGWATCH_NO_JOURNAL": os.environ.get("RIGWATCH_NO_JOURNAL"),
        }
        os.environ["RIG_EVENTS"] = self._events
        os.environ["MONITOR_LOG"] = self._monlog
        os.environ["RIG_DUT_LINES"] = self._dutlines
        # Hermetic: the real host journal must never leak into a fixture window.
        os.environ["RIGWATCH_NO_JOURNAL"] = "1"

    def tearDown(self):
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _dut(self, ts, line):
        rw.append_jsonl(self._sidecar, {"host_ts": ts, "line": line})

    def _harness(self, ts, kind, **kv):
        ev = {"host_ts": ts, "src": "harness", "kind": kind}
        ev.update(kv)
        rw.append_jsonl(self._events, ev)

    def _kernel(self, ts, kind, **kv):
        ev = {"host_ts": ts, "src": "kernel", "kind": kind}
        ev.update(kv)
        rw.append_jsonl(self._events, ev)


class TestEventSources(_SummaryFixture):
    """The two gaps found at review: history must come from the journal when
    the daemon did not cover the window, and the harness's own DUT lines must
    be read from the shared file, not only from MONITOR_LOG's sidecar."""

    def test_journal_fallback_merges_and_dedupes(self):
        raw = "usb 1-1: new full-speed USB device number 108 using xhci_hcd"
        self._kernel(5.0, "attach", devnum=108, tty=None, raw=raw)
        os.environ["RIGWATCH_NO_JOURNAL"] = "0"
        old_lines, old_port = rw._journal_lines_since, rw._cached_dut_port
        rw._journal_lines_since = lambda since: [
            _kjson(raw, 5_000_000),
            _kjson("usb 1-1: new full-speed USB device number 109 using xhci_hcd", 9_000_000),
            _kjson("usb 1-4: reset full-speed USB device number 2 using xhci_hcd", 7_000_000)]
        rw._cached_dut_port = lambda: "1-1"
        try:
            summ = rw.summarize(1.0)
        finally:
            rw._journal_lines_since, rw._cached_dut_port = old_lines, old_port
        # the daemon's copy and the journal's copy of t=5 are ONE event; the
        # fingerprint reader on 1-4 is none; t=9 is new -> R = 2, not 1, not 3
        self.assertEqual(summ["reenum"], 2)

    def test_journal_skipped_without_a_resolved_port(self):
        os.environ["RIGWATCH_NO_JOURNAL"] = "0"
        old_lines, old_port = rw._journal_lines_since, rw._cached_dut_port
        rw._journal_lines_since = lambda since: [
            _kjson("usb 1-1: ch341-uart converter now attached to ttyUSB0", 5_000_000)]
        rw._cached_dut_port = lambda: None
        try:
            summ = rw.summarize(1.0)
        finally:
            rw._journal_lines_since, rw._cached_dut_port = old_lines, old_port
        self.assertEqual(summ["reenum"], 0)

    def test_harness_dut_lines_read_from_shared_file(self):
        rw.append_jsonl(self._dutlines, {"host_ts": 10.0, "via": "harness",
                                         "line": "[bootphase] 0 reset"})
        summ = rw.summarize(1.0)
        self.assertEqual(summ["unexplained_boots"], 1)

    def test_same_line_in_sidecar_and_shared_file_counted_once(self):
        self._dut(10.0, "[bod] TRIP tag=run t=1 thres=7 trips=1 det=0")
        rw.append_jsonl(self._dutlines, {"host_ts": 10.0, "via": "monitor",
                                         "line": "[bod] TRIP tag=run t=1 thres=7 trips=1 det=0"})
        self.assertEqual(rw.summarize(1.0)["bod_trips"], 1)


class TestSummarize(_SummaryFixture):
    def test_reenum_counts_attach_kernel_events(self):
        self._kernel(100.0, "attach", devnum=1)
        self._kernel(101.0, "attach", devnum=2)
        self._kernel(102.0, "detach", devnum=2)  # not an attach — not counted
        summ = rw.summarize(since=0)
        self.assertEqual(summ["reenum"], 2)

    def test_bod_trips_counted_from_dut_lines(self):
        self._dut(100.0, "[bod] TRIP tag=wifi-end t=1518ms thres=7 trips=1 det=1")
        self._dut(101.0, "[bod] armed thres=7")  # not a TRIP — not counted
        self._dut(102.0, "[bod] TRIP tag=run t=9000ms thres=7 trips=2 det=2")
        summ = rw.summarize(since=0)
        self.assertEqual(summ["bod_trips"], 2)

    def test_wifi_disc_uses_heartbeat_delta_not_event_count(self):
        # Rate-limited [wifi-ev] lines would undercount; disc=N in the
        # heartbeat is the ground truth (PROP-011 §1.2's reading note).
        self._dut(100.0, "[wifi-ev] STA_DISCONNECTED reason=201 suppressed=0")
        self._dut(101.0, "[I][hb] uptime=00:01:00 disc=5 heap=123456")
        self._dut(200.0, "[I][hb] uptime=00:02:00 disc=23 heap=123000")
        summ = rw.summarize(since=0)
        self.assertEqual(summ["wifi_disc"], 18)

    def test_unstamped_boot_is_unexplained(self):
        self._dut(100.0, "[bootphase] 0 reset")
        summ = rw.summarize(since=0)
        self.assertEqual(summ["unexplained_boots"], 1)

    def test_boot_within_3s_of_flash_end_is_explained(self):
        self._harness(99.0, "flash-end")
        self._dut(100.5, "[bootphase] 0 reset")
        summ = rw.summarize(since=0)
        self.assertEqual(summ["unexplained_boots"], 0)

    def test_boot_within_3s_of_port_open_is_explained(self):
        self._harness(100.0, "port-open")
        self._dut(102.9, "[bootphase] 0 reset")
        summ = rw.summarize(since=0)
        self.assertEqual(summ["unexplained_boots"], 0)

    def test_boot_outside_window_still_unexplained(self):
        self._harness(90.0, "flash-end")   # 10s before — outside +/-3s
        self._dut(100.0, "[bootphase] 0 reset")
        summ = rw.summarize(since=0)
        self.assertEqual(summ["unexplained_boots"], 1)

    def test_since_filters_out_earlier_events(self):
        self._kernel(50.0, "attach", devnum=1)
        self._kernel(150.0, "attach", devnum=2)
        summ = rw.summarize(since=100.0)
        self.assertEqual(summ["reenum"], 1)

    def test_annotate_run_rig_none_when_clean(self):
        self._kernel(100.0, "detach", devnum=1)  # not attach; no unexplained boot
        summ = rw.summarize(since=0)
        self.assertIsNone(rw.annotate_run_rig(summ))

    def test_annotate_run_rig_fires_on_reenum(self):
        self._kernel(100.0, "attach", devnum=1)
        summ = rw.summarize(since=0)
        note = rw.annotate_run_rig(summ)
        self.assertIsNotNone(note)
        self.assertIn("[triage] rig:", note)
        self.assertIn("R=1", note)


class TestTimeline(_SummaryFixture):
    def test_events_render_in_chronological_order(self):
        self._kernel(100.0, "detach", devnum=1)
        self._harness(101.0, "flash-begin")
        self._dut(102.0, "[bootphase] 0 reset")
        summ = rw.summarize(since=0)
        out = rw.render_timeline(summ)
        lines = out.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("kernel", lines[0])
        self.assertIn("harness", lines[1])
        self.assertIn("dut", lines[2])
        # relative offsets increase monotonically
        self.assertIn("+  1.00s", lines[1])
        self.assertIn("+  2.00s", lines[2])

    def test_unexplained_boot_flagged_in_timeline(self):
        self._dut(100.0, "[bootphase] 0 reset")
        summ = rw.summarize(since=0)
        out = rw.render_timeline(summ)
        self.assertIn("UNEXPLAINED boot", out)

    def test_explained_boot_not_flagged(self):
        self._harness(99.5, "port-open")
        self._dut(100.0, "[bootphase] 0 reset")
        summ = rw.summarize(since=0)
        out = rw.render_timeline(summ)
        self.assertNotIn("UNEXPLAINED", out)

    def test_empty_window_renders_placeholder(self):
        summ = rw.summarize(since=0)
        self.assertEqual(rw.render_timeline(summ), "(no events in window)")


class TestDaemonIdempotency(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="rigwatch-pid-")
        self._pidfile = os.path.join(self._tmp, "rigwatch.pid")
        self._old = os.environ.get("RIGWATCH_PIDFILE")
        os.environ["RIGWATCH_PIDFILE"] = self._pidfile

    def tearDown(self):
        if self._old is None:
            os.environ.pop("RIGWATCH_PIDFILE", None)
        else:
            os.environ["RIGWATCH_PIDFILE"] = self._old

    def test_no_pidfile_means_not_running(self):
        self.assertIsNone(rw.daemon_already_running())

    def test_pidfile_with_own_pid_reports_running(self):
        # os.getpid() is always a live PID for the duration of this test —
        # the cheapest possible "definitely alive" process to probe with.
        with open(self._pidfile, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        self.assertEqual(rw.daemon_already_running(), os.getpid())

    def test_pidfile_with_dead_pid_reports_not_running(self):
        # PID 1 is real (rig host) but a huge made-up PID almost certainly is
        # not; guard against the vanishingly unlikely collision by picking a
        # PID far past any real process table.
        dead = 2**30 - 1
        with open(self._pidfile, "w", encoding="utf-8") as fh:
            fh.write(str(dead))
        self.assertIsNone(rw.daemon_already_running())

    def test_stop_daemon_removes_pidfile(self):
        with open(self._pidfile, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        # Don't actually SIGTERM this test process — patch os.kill locally by
        # stopping a dead pid instead; what's under test is pidfile cleanup.
        dead = 2**30 - 1
        with open(self._pidfile, "w", encoding="utf-8") as fh:
            fh.write(str(dead))
        rw.stop_daemon()
        self.assertFalse(os.path.exists(self._pidfile))


class TestParseSince(unittest.TestCase):
    def test_duration_forms(self):
        now = time.time()
        self.assertAlmostEqual(rw.parse_since("60s"), now - 60, delta=1)
        self.assertAlmostEqual(rw.parse_since("2m"), now - 120, delta=1)
        self.assertAlmostEqual(rw.parse_since("1h"), now - 3600, delta=1)
        self.assertAlmostEqual(rw.parse_since("1d"), now - 86400, delta=1)

    def test_bare_epoch(self):
        self.assertEqual(rw.parse_since("12345.5"), 12345.5)


class TestIsDutMarkerLine(unittest.TestCase):
    """Negative case: a line that carries none of the five markers must NOT be
    timestamped — the sidecar would otherwise grow unbounded on ordinary debug
    chatter, defeating the whole point of filtering to markers."""

    def test_marker_lines_recognized(self):
        for line in (
            "[bootreason] 1 POWERON",
            "[bootphase] 3 wifi",
            "[bod] TRIP tag=run t=1ms thres=7 trips=1 det=1",
            "[wifi-ev] STA_DISCONNECTED reason=201",
            "[I][hb] uptime=00:00:30 disc=0 heap=100000",
        ):
            self.assertTrue(rw.is_dut_marker_line(line), line)

    def test_non_marker_line_rejected(self):
        self.assertFalse(rw.is_dut_marker_line(
            "[spotify.poll] ok 200 track=foo"))


class TestSysfsPortNoSideEffectsWhenNodeMissing(unittest.TestCase):
    """dut_sysfs_port must not raise or hang when nothing is attached — a
    board-free host (CI, a laptop with the DUT unplugged) is a normal state,
    not an error."""

    def test_missing_node_returns_none(self):
        self.assertIsNone(rw.dut_sysfs_port("/dev/serial/by-id/nonexistent"))


if __name__ == "__main__":
    unittest.main()
