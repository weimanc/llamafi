#!/usr/bin/env python3
"""TASK-409 / ADR-059 T_AE_04 — teardown ordering under eject-mid-CONNECTING.

The audio engine's pump task (TASK-278/TASK-398, moved verbatim into
audio/audioEngine.h by TASK-409) has a documented invariant: leaving WebRadio
while a connect is in flight must tear down pump-task -> Audio object -> arena
in that order, and must never block loopTask for the connect's remaining
duration (that's the whole point of TASK-398's async request/result protocol).

This injects a synthetic, unroutable station URL (`set wrUrl`) so `_play()`
enters CONNECTING and connecttohost() blocks the pump task for the full
connect timeout, then ejects mid-flight (`set wrEject`) and confirms:
  - loopTask is never blocked behind the in-flight connect (no `[perf] iter=`
    line over --max-block-ms during the whole eject/teardown window)
  - the pump task actually tears down (`get wrPump` alive -> false), via the
    post-connect TEARDOWN branch (`wrpump: torn down (post-connect)`)
  - the arena is released and this cycle's acquire/release delta balances
    (`get arenaStats`), with active back to 0
  - no crash/reboot signature

Runs ADR-059-D13-style, x10 (TASK-409's T_AE_04 exit criterion).

HARNESS NOTE (2026-08-10 rework — why the previous version could not render a
verdict).  Three defects, all in the harness, none in firmware:

 1. **Fixed 8 s teardown window vs a 10 s connect timeout.**  DEAD_URL is a raw
    IP, and `Audio::connecttohost()` (Audio.cpp:511-519, TASK-295's patch)
    force-sets `m_timeout_ms = 10000` for raw-IP hosts.  The pump is inside
    that blocking `_client->connect()` and only observes the posted TEARDOWN
    *after* it returns, so the pump legitimately stays alive up to ~10 s past
    the eject.  Asserting `alive == false` 8.0 s after eject is a bound the
    firmware is not supposed to meet.  Whether a cycle "passed" depended purely
    on how much of the 10 s had already burned before the eject command landed
    — which is exactly the alternating/parity pattern that was observed and
    misread as network jitter, then as accumulated state drift.  Fixed: poll
    for teardown with a deadline derived from the connect timeout
    (--teardown-deadline-s, default 16), and report the measured latency.

 2. **No precondition gate, so failures cascaded.**  When a cycle left a
    connect in flight, the next cycle started with `_state` stale-CONNECTING;
    `set wrStop` can't reconcile that off-screen (`_stopAudio()` returns early
    on CONNECTING), and `_play()`'s own CONNECTING guard then silently no-ops
    the `set wrUrl` injection — so every subsequent cycle ejected against
    nothing and failed identically.  That is the "worse and monotonic, not
    flaky" degradation from cycles 3-10: one late teardown poisoned the rest of
    the run.  Fixed: each cycle now *proves* STOPPED before injecting and
    *proves* CONNECTING + pump-alive after, and reports a failed precondition
    as SETUP (not as an invariant failure) so a harness problem can never again
    be mistaken for a firmware one.

 3. **`cmd()`'s `reset_input_buffer()` ate the evidence.**  Polling with `get
    wrPump` between reads discards whatever `[perf]`/`wrpump` lines arrived in
    the meantime — the loopTask-block bound and the ordering evidence are read
    from those same lines.  Fixed: `watch()` interleaves probe writes into one
    continuous raw read, never flushing.

 4. **No wait for the first-entry station fetch.**  On the first entry to
    WebRadio, `init()` has a station fetch in flight; while `_pendingStations`
    is set, `set wrUrl` defers instead of playing (TASK-289's fetch/playback
    heap-race guard).  Cycle 1 therefore never reached CONNECTING, and the
    deferred play firing later left the arena acquired, breaking cycle 2 as
    well.  Fixed: gate each cycle on `get wrCount` pending==0.

 The 180 ms loopTask bound (vs T_AE_04's literal 100 ms) stands from the
 previous session and is unrelated to the above: an isolation probe (WebRadio
 STOPPED -> Spotify, no CONNECTING, no pump/arena involvement) measured
 `[perf] iter=103ms (worst path shell.switch:76ms)` on this hardware — ordinary
 app-switch repaint cost, nothing the teardown path touches.

Self-contained serial wrapper (same reasoning as test_webradio_soak.py: this
targets cyd2usb_webradio, not the canonical cyd2usb_winamp_debug ELF, so it
does not reuse run_serialdbg_tests.Dut).

Usage:
    python3 test_ae04_teardown.py --port /dev/ttyUSB0 [--cycles 10]
Exit 0 = all cycles clean; 1 otherwise.
"""
import argparse
import json
import re
import sys
import time

import serial

WEBRADIO_APPID = 11  # appRegistry.h: Spotify..PlaneRadar, Settings, WebRadio (last)
SPOTIFY_APPID = 0
# Non-routed host: a real TCP-connect timeout, not an instant refusal. Raw IP on
# purpose — it makes the block deterministic (Audio.cpp forces 10 000 ms for
# raw-IP hosts) instead of DNS-dependent.
DEAD_URL = "http://10.255.255.1:1/blackhole"
WR_STATE_STOPPED = 0
WR_STATE_CONNECTING = 1

RE_PERF = re.compile(r"\[perf\] iter=(\d+)ms")
RE_CRASH = re.compile(r"rst:0x|Guru Meditation|Backtrace:|abort\(\) was called|panic|task_wdt")
RE_TORNDOWN = re.compile(r"wrpump.*torn down \((post-connect|early-arrival)\)")
RE_ACK_TIMEOUT = re.compile(r"teardown ack timeout")


class SerialDut:
    def __init__(self, port, baud=115200):
        self.ser = serial.Serial(port, baud, timeout=0.3)
        self.ser.dtr = False
        self.ser.rts = False

    def boot_wait(self, timeout=45):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if "IP address:" in l or "spotify=off" in l:
                break
        for _ in range(40):
            if self.cmd("get appId", 2.0).get("name"):
                return True
            time.sleep(1.0)
        return False

    def cmd(self, s, timeout=3.0):
        """Request/response with a flush — fine for setup steps, but it discards
        any pending log lines, so never use it inside a measurement window."""
        self.ser.reset_input_buffer()
        return self._write_and_read(s, timeout)

    def _write_and_read(self, s, timeout):
        self.ser.write((s + "\n").encode())
        self.ser.flush()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            l = self.ser.readline().decode(errors="replace").strip()
            if not l:
                continue
            r = _parse_json(l)
            if isinstance(r, dict) and r.get("last", True):
                return r
        return {}

    def poll_until(self, probe, accept, timeout, interval=0.3):
        """Repeatedly `probe` until `accept(reply)`; returns (ok, last_reply)."""
        end = time.monotonic() + timeout
        r = {}
        while True:
            r = self.cmd(probe, 2.0)
            if accept(r):
                return True, r
            if time.monotonic() >= end:
                return False, r
            time.sleep(interval)

    def watch(self, probe, accept, timeout, probe_every=0.5):
        """Continuous raw read for up to `timeout`, interleaving `probe` writes,
        without ever flushing the input buffer — so `[perf]`/`wrpump` lines seen
        between probes are still counted.

        Returns dict: matched, elapsed, worst_iter_ms, crashed, torn_down,
        ack_timeout, reply.
        """
        out = {"matched": False, "worst_iter_ms": 0, "crashed": False,
               "torn_down": None, "ack_timeout": False, "reply": {}}
        t0 = time.monotonic()
        end = t0 + timeout
        next_probe = 0.0
        while time.monotonic() < end:
            now = time.monotonic()
            if now >= next_probe:
                self.ser.write((probe + "\n").encode())
                self.ser.flush()
                next_probe = now + probe_every
            l = self.ser.readline().decode(errors="replace").strip()
            if not l:
                continue
            if RE_CRASH.search(l):
                out["crashed"] = True
            if RE_ACK_TIMEOUT.search(l):
                out["ack_timeout"] = True
            m = RE_TORNDOWN.search(l)
            if m and out["torn_down"] is None:
                out["torn_down"] = m.group(1)
            m = RE_PERF.search(l)
            if m:
                out["worst_iter_ms"] = max(out["worst_iter_ms"], int(m.group(1)))
            r = _parse_json(l)
            if isinstance(r, dict) and accept(r):
                out["reply"] = r
                out["matched"] = True
                break
        out["elapsed"] = time.monotonic() - t0
        return out


def _parse_json(line):
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class CycleResult:
    def __init__(self, ok, detail, setup=False):
        self.ok = ok
        self.detail = detail
        self.setup = setup  # harness/precondition problem, not an invariant failure


def run_cycle(d, n, args):
    # ── precondition 1: in WebRadio, STOPPED, nothing in flight ──────────────
    r = d.cmd(f"switchApp {WEBRADIO_APPID}")
    if r.get("name") != "WebRadio" and d.cmd("get appId").get("name") != "WebRadio":
        return CycleResult(False, "could not switch to WebRadio", setup=True)

    # First entry to WebRadio kicks off init()'s station fetch. While
    # `_pendingStations` is set, `set wrUrl` does NOT play — it defers
    # (`_deferredInject`, TASK-289's fetch/playback heap race guard) and tick()
    # starts it only once the fetch resolves. Injecting into that window gives a
    # vacuous cycle (still STOPPED), and the late-firing deferred play then
    # leaves the arena acquired, poisoning the next cycle too. Wait it out.
    ok, wc = d.poll_until("get wrCount", lambda r: _int(r.get("pending"), 1) == 0,
                          timeout=args.fetch_deadline_s, interval=0.5)
    if not ok:
        return CycleResult(
            False,
            f"precondition: station fetch still pending after {args.fetch_deadline_s}s "
            f"(count={wc.get('count')}) — `set wrUrl` would defer instead of playing",
            setup=True)

    # A prior cycle's TEARDOWN result is reconciled to STOPPED by tick(), which
    # only runs once WebRadio is the current app again — so poll first, and only
    # force a stop if it doesn't settle on its own. The deadline must exceed the
    # connect timeout: a still-in-flight connect cannot reconcile any sooner.
    ok, st = d.poll_until("get wrState",
                          lambda r: _int(r.get("state")) == WR_STATE_STOPPED,
                          timeout=2.0)
    if not ok:
        d.cmd("set wrStop 1")
        ok, st = d.poll_until("get wrState",
                              lambda r: _int(r.get("state")) == WR_STATE_STOPPED,
                              timeout=args.teardown_deadline_s)
    if not ok:
        return CycleResult(
            False,
            f"precondition: WebRadio never reached STOPPED (state={st.get('state')}) — "
            "a previous cycle left a connect in flight; injecting here would be a no-op "
            "(_play()'s CONNECTING guard) and every later cycle would fail identically",
            setup=True)

    base = d.cmd("get arenaStats")
    base_acq, base_rel = _int(base.get("acquires")), _int(base.get("releases"))
    base_fails, base_up = _int(base.get("fails")), _int(base.get("upMs"))
    if _int(base.get("active"), -1) != 0:
        return CycleResult(False,
                           f"precondition: arena active={base.get('active')} before injection "
                           "(expected 0 — previous cycle did not release)", setup=True)

    # ── inject a dead URL and prove we're really mid-CONNECTING ──────────────
    d.cmd("set wrDeadUrls 0")  # forced-fail shortcut off — we want the real CONNECTING path
    d.cmd(f"set wrUrl {DEAD_URL}")
    ok, st = d.poll_until("get wrState",
                          lambda r: _int(r.get("state")) == WR_STATE_CONNECTING,
                          timeout=3.0, interval=0.1)
    if not ok:
        return CycleResult(
            False,
            f"precondition: never entered CONNECTING after wrUrl inject (state={st.get('state')}) — "
            "cycle would be vacuous", setup=True)
    pump = d.cmd("get wrPump")
    if pump.get("alive") in (False, 0, "false", None):
        return CycleResult(False, "precondition: pump not alive while CONNECTING", setup=True)

    # ── eject mid-flight, watch loopTask + teardown ──────────────────────────
    d.cmd("set wrEject 1", timeout=2.0)
    w = d.watch("get wrPump",
                lambda r: r.get("var") == "wrPump" and r.get("alive") in (False, 0, "false"),
                timeout=args.teardown_deadline_s)

    if w["crashed"]:
        return CycleResult(False, f"crash/reboot signature during teardown ({w['elapsed']:.1f}s in)")
    if w["ack_timeout"]:
        return CycleResult(False, "wrpump teardown ack timeout tripwire fired")
    if not w["matched"]:
        return CycleResult(
            False,
            f"pump still alive {w['elapsed']:.1f}s after eject "
            f"(deadline {args.teardown_deadline_s}s > the {args.connect_timeout_s}s raw-IP "
            "connect timeout the pump is blocked in — this is a real teardown failure)")
    if w["worst_iter_ms"] > args.max_block_ms:
        return CycleResult(False,
                           f"loopTask blocked {w['worst_iter_ms']}ms > {args.max_block_ms}ms bound")
    # Ordering evidence: the TEARDOWN must have been serviced by the pump task
    # itself (post-connect branch), i.e. Audio deleted then arena released then
    # task self-deleted — not by loopTask synchronously.
    if w["torn_down"] is None:
        return CycleResult(False, "pump gone but no `wrpump: torn down (...)` line — "
                                  "teardown did not go through the pump's own TEARDOWN branch")

    # ── arena balance for THIS cycle (deltas — counters never reset) ─────────
    arena = d.cmd("get arenaStats")
    if _int(arena.get("upMs"), 0) < (base_up or 0):
        return CycleResult(False, "device rebooted mid-cycle (upMs went backwards)")
    d_acq = _int(arena.get("acquires"), 0) - (base_acq or 0)
    d_rel = _int(arena.get("releases"), 0) - (base_rel or 0)
    d_fail = _int(arena.get("fails"), 0) - (base_fails or 0)
    if _int(arena.get("active"), -1) != 0:
        return CycleResult(False, f"arena still active={arena.get('active')} after teardown")
    if d_acq != d_rel:
        return CycleResult(False, f"arena acquire/release imbalance this cycle {d_acq}/{d_rel}")
    if d_acq != 1:
        return CycleResult(False, f"expected exactly 1 acquire/release this cycle, saw {d_acq}")
    if d_fail:
        return CycleResult(False, f"{d_fail} arena acquire failure(s) this cycle")

    return CycleResult(True,
                       f"teardown={w['elapsed']:.1f}s ({w['torn_down']}) "
                       f"worst_iter={w['worst_iter_ms']}ms arena +{d_acq}/-{d_rel} hwm={arena.get('hwm')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--cycles", type=int, default=10)
    # See the module docstring's closing HARNESS NOTE para: 100 ms (T_AE_04's literal
    # exit criterion) false-positives on this app's ordinary app-switch repaint
    # cost, which the teardown path never touches. 180 ms = measured 103 ms
    # baseline + margin.
    ap.add_argument("--max-block-ms", type=int, default=180)
    # Audio.cpp:511-519 forces a 10 000 ms connect timeout for raw-IP hosts
    # (TASK-295). The pump cannot observe the posted TEARDOWN until
    # connecttohost() returns, so any teardown deadline below this is a bound
    # the firmware is not designed to meet.
    ap.add_argument("--connect-timeout-s", type=float, default=10.0,
                    help="raw-IP connect timeout the pump blocks in (documentation/bound derivation)")
    ap.add_argument("--teardown-deadline-s", type=float, default=16.0,
                    help="max wait for pump teardown after eject (connect timeout + margin)")
    ap.add_argument("--fetch-deadline-s", type=float, default=45.0,
                    help="max wait for the first-entry station fetch to settle before injecting")
    args = ap.parse_args()

    d = SerialDut(args.port)
    print(f"[T_AE_04] waiting for boot on {args.port}…", flush=True)
    if not d.boot_wait():
        print("[T_AE_04] FAIL: DUT did not come up", flush=True)
        return 1
    print(f"[T_AE_04] bounds: loopTask block <= {args.max_block_ms}ms, "
          f"teardown <= {args.teardown_deadline_s}s "
          f"(raw-IP connect timeout {args.connect_timeout_s}s + margin)", flush=True)

    ok_count = setup_fail = 0
    for i in range(1, args.cycles + 1):
        res = run_cycle(d, i, args)
        tag = "PASS" if res.ok else ("SETUP" if res.setup else "FAIL")
        print(f"[T_AE_04] cycle {i}/{args.cycles} {tag}: {res.detail}", flush=True)
        if res.ok:
            ok_count += 1
        elif res.setup:
            setup_fail += 1
        # Back to the Spotify slot so the next switchApp is a clean re-entry.
        d.cmd(f"switchApp {SPOTIFY_APPID}")
        time.sleep(0.5)

    failed = args.cycles - ok_count - setup_fail
    print(f"\n[T_AE_04] {ok_count}/{args.cycles} cycles clean "
          f"({failed} invariant failures, {setup_fail} setup/precondition)", flush=True)
    if setup_fail and not failed:
        print("[T_AE_04] VERDICT: INCONCLUSIVE — harness preconditions not met, "
              "no firmware verdict rendered", flush=True)
    else:
        print(f"[T_AE_04] VERDICT: {'PASS' if ok_count == args.cycles else 'FAIL'}", flush=True)
    return 0 if ok_count == args.cycles else 1


if __name__ == "__main__":
    sys.exit(main())
