#!/usr/bin/env python3
"""TASK-398 (M-WR-CONNECT-ASYNC) exit-criteria verification.

Targeted DUT script exercising the exit criteria listed in
docs/architecture/designs/M-WR-CONNECT-ASYNC.md's "Exit criteria" section
that aren't already covered by run_serialdbg_tests.py's T_WR_* suite
(T_WR_EJECT_01/02, T_WR_ERR_01-04, T_WR_VOL_03, T_WR_TLS_01,
T_WR_SPOTIFY_RESUME_01 — run those separately via run/test-targeted first).

## Real slow/dead host, calibrated against this network

`set wrDeadUrls` is NOT suitable here: it's a purely synthetic
_debugForceConnFail short-circuit that never dispatches to the pump task at
all (resolves _state synchronously within _play() before ever posting
CONNECT), so it can't exercise the CONNECTING window this design is about.

Empirically probed on this network before writing this script (see TASK-398
tasks.md entry): a genuinely unreachable IP (RFC 5737 TEST-NET-1, or an
unused LAN address) fails near-instantly here — this network's
router/resolver responds fast, so there is no multi-second TCP-connect hang
to exploit the way TASK-393's real-world flaky mirror produced one. An
accept-then-hold TCP listener doesn't help either: connecttohost() returns
success as soon as the TCP handshake completes, before any HTTP response is
read, so a server that accepts-but-never-responds resolves to PLAYING almost
instantly — no hang.

What DOES reliably produce a real, non-synthetic multi-second-scale window
on this network: a **fresh, never-cached hostname** that doesn't resolve
(NXDOMAIN). hostByName() has no enforced timeout (the exact mechanism the
Architect's VE review cites as TASK-393's real root cause), and DNS lookup +
negative-response round-trip against this network's resolver reproducibly
takes ~350-600ms per fresh (random) hostname (a cached/repeated hostname
resolves near-instantly on retry, which is WHY a fresh random label is used
per attempt below). This is real network I/O through the pump's genuine
mutex-held connecttohost() call — not as long as TASK-393's pathological
7-9s case, but a real, non-zero, reproducible window sufficient to exercise
the guards under genuine concurrent-task conditions, which is the property
that actually matters for these checks (see the tasks.md writeup for the
honest caveat: this does not reproduce the FULL 7-9s freeze duration, only
the mechanism).

Usage:
    python3 task398_connect_async_verify.py [--port /dev/ttyUSB0]

Requires: DUT flashed with cyd2usb_winamp_debug, booted, WiFi up, real
stations loadable (radio-browser.info reachable) for the successful-connect
check. Exit 0 if every check passes, 1 otherwise.
"""
import argparse
import os
import pathlib
import random
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from run_serialdbg_tests import Dut  # noqa: E402
from app_ids_gen import APP_SLOT  # noqa: E402

_results = []


def check(name, ok, detail=""):
    _results.append((name, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}  {detail}")


def switch_app(dut, name, timeout=5.0):
    dut.cmd(f"switchApp {APP_SLOT[name]}", timeout=timeout)  # drains its own ack
    time.sleep(0.3)
    r = dut.cmd("get appId", timeout=timeout)
    return r.get("ok", False) and r.get("name") == name


def wr_state(dut):
    r = dut.cmd("get wrState", timeout=3.0)
    return r.get("state")


def wait_state(dut, predicate, timeout=12.0, poll=0.1):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = wr_state(dut)
        if predicate(last):
            return True, last
        time.sleep(poll)
    return False, last


def fresh_dead_url():
    """A never-before-queried hostname -- see module docstring: fresh labels
    force a real (uncached) DNS round-trip, giving a real ~350-600ms
    CONNECTING window on this network. A repeated hostname resolves from
    cache almost instantly on retry."""
    return f"http://nx{random.randint(1000000, 9999999)}.invalid:80/mount"


def log_pos(log_path):
    """Current end-of-file byte offset, for a subsequent grep_new() call.
    Reading log lines via drain_log_lines()/read_json() during other cmd()
    calls in between an action and the check races and silently drops the
    target line (every readline() -- JSON or bare log text -- gets consumed
    off the wire whether or not the caller stores it); the persisted raw log
    (Dut's _TeeSerial log_file) sees every line unconditionally regardless of
    who was reading at the time, so grepping IT after the fact is race-free."""
    try:
        return os.path.getsize(log_path)
    except OSError:
        return 0


def grep_new(log_path, pos, pattern):
    try:
        with open(log_path, "r", errors="replace") as f:
            f.seek(pos)
            content = f.read()
    except OSError:
        return 0
    return len(re.findall(pattern, content))


def arm_dead_url(dut):
    """Inject a fresh unreachable-host station as slot 0, stopped (not playing)."""
    dut.cmd(f"set wrUrl {fresh_dead_url()}", timeout=5.0)
    time.sleep(0.1)
    dut.cmd("set wrStop 1", timeout=3.0)
    ok, st = wait_state(dut, lambda s: s == 0, timeout=5.0)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    args = ap.parse_args()

    log_path = "/tmp/task398_verify_raw.log"
    dut = Dut(args.port, log_file=log_path)

    print("== setup: enter WebRadio, quiesce bgPoll, let post-boot heap settle ==")
    if not switch_app(dut, "WebRadio", timeout=10.0):
        print("FATAL: could not switch to WebRadio")
        sys.exit(1)
    dut.cmd("set bgPoll 0", timeout=2.0)
    # DMA-capable heap settles ~8-10s post-boot (large transient block frees
    # once the boot-time station fetch's own TLS buffers are released) --
    # verified empirically this session; below this the DMA-floor guard in
    # _play() (webRadioApp.h, 16KB floor) aborts BEFORE ever posting CONNECT,
    # which would silently no-op every check below without this wait.
    time.sleep(9.0)
    heap = dut.cmd("get heap", timeout=3.0)
    check("setup-dma-headroom", heap.get("lfbDma", 0) >= 16384, str(heap))

    # ── 4. No runaway reconnect loop on a REAL successful connect ──
    # Run FIRST, before any `set wrUrl` injection -- wrUrl unconditionally
    # overwrites _stations[0] and clamps _stationCount to 1, and nothing
    # later re-triggers the real station fetch (that only happens when
    # _stationCount==0, which a single wrUrl injection never produces), so
    # this must run while the real boot-time station list is still intact.
    print("\n== 4. no runaway reconnect loop (real station, successful connect) ==")
    cnt = dut.cmd("get wrCount", timeout=3.0).get("count", 0) or 0
    if cnt > 0:
        dut.cmd("set wrStop 1", timeout=3.0)
        pos = log_pos(log_path)
        dut.cmd("set wrPlay 0", timeout=3.0)
        ok, st = wait_state(dut, lambda s: s == 2, timeout=12.0)
        check("4-real-connect-reaches-playing", ok, f"wrState={st}")
        time.sleep(5.0)  # 5s of steady PLAYING
        n = grep_new(log_path, pos, r"HEAP pre-connect|play idx=")
        check("4-no-reconnect-hammering", n <= 1,
              f"saw {n} connect-dispatch line(s) across dispatch+5s steady PLAYING (expect <=1)")
        dut.cmd("set wrStop 1", timeout=3.0)
    else:
        check("4-setup", False, "no stations loaded -- could not test real successful connect")

    # ── 1a. Re-entrant control input during CONNECTING -- _play()-path taps ──
    print("\n== 1a. re-entrant _play()-path taps during real CONNECTING (expect no-op) ==")
    if arm_dead_url(dut):
        pos = log_pos(log_path)
        t0 = time.monotonic()
        dut.cmd("set wrPlay 0", timeout=3.0)
        st_before = wr_state(dut)
        check("1a-precondition-connecting", st_before == 1,
              f"wrState={st_before} at t={time.monotonic()-t0:.3f}s")
        t1 = time.monotonic()
        dut.cmd("set wrNext", timeout=3.0)  # re-entrant _play()-path call while CONNECTING
        dt = time.monotonic() - t1
        check("1a-play-reentrant-noop-fast", dt < 1.0, f"round-trip={dt:.3f}s (must not block)")
        ok, st = wait_state(dut, lambda s: s != 1, timeout=5.0)
        check("1a-connect-eventually-resolves", ok, f"wrState={st}")
        # The real assertion: _play()'s guard means wrNext must NOT have
        # dispatched a second connect -- exactly one "play idx=" line for
        # this whole sequence (the original wrPlay 0), not two.
        n = grep_new(log_path, pos, r"\[I\]\[webradio\] play idx=")
        check("1a-play-reentrant-no-second-dispatch", n == 1,
              f"saw {n} 'play idx=' dispatch line(s) (expect exactly 1 -- wrNext must have no-op'd)")
    else:
        check("1a-setup", False, "could not arm dead-url station")

    # ── 1b. _stopAudio()-path taps during real CONNECTING ──
    print("\n== 1b. re-entrant _stopAudio()-path taps during real CONNECTING (expect ABORT posted, no block) ==")
    if arm_dead_url(dut):
        t0 = time.monotonic()
        dut.cmd("set wrPlay 0", timeout=3.0)
        st_before = wr_state(dut)
        check("1b-precondition-connecting", st_before == 1,
              f"wrState={st_before} at t={time.monotonic()-t0:.3f}s")
        t1 = time.monotonic()
        dut.cmd("set wrStop 1", timeout=3.0)  # routes through _stopAudio()'s CONNECTING guard
        dt = time.monotonic() - t1
        check("1b-stop-reentrant-fast", dt < 1.0, f"round-trip={dt:.3f}s (must not block on mutex)")
        ok, st = wait_state(dut, lambda s: s == 0, timeout=5.0)
        check("1b-resolves-to-stopped", ok, f"wrState={st}")
        arena = dut.cmd("get arenaStats", timeout=3.0)
        check("1b-arena-sane", arena.get("ok", True), str(arena))
    else:
        check("1b-setup", False, "could not arm dead-url station")

    # ── 2a. Early-arrival ABORT -- back-to-back, no delay ──
    print("\n== 2a. early-arrival ABORT (fired before pump could have read CONNECT) ==")
    for i in range(3):
        dut.cmd(f"set wrUrl {fresh_dead_url()}", timeout=5.0)
        time.sleep(0.1)
        dut.cmd("set wrStop 1", timeout=3.0)
        dut.send("set wrPlay 0")
        dut.send("set wrStop 1")  # fired immediately after, no delay, before pump's ~2ms cadence
        try:
            dut.read_json(timeout=2.0)
            dut.read_json(timeout=2.0)
        except TimeoutError:
            pass
        ok, st = wait_state(dut, lambda s: s == 0, timeout=5.0)
        check(f"2a-early-abort-terminal-iter{i}", ok, f"wrState={st}")
    pump = dut.cmd("get wrPump", timeout=3.0)
    check("2a-pump-alive-no-orphan", pump.get("ok", False), str(pump))

    print("\n== 2b. early-arrival TEARDOWN via eject (no delay) ==")
    dut.cmd(f"set wrUrl {fresh_dead_url()}", timeout=5.0)
    time.sleep(0.1)
    dut.cmd("set wrStop 1", timeout=3.0)
    dut.send("set wrPlay 0")
    dut.send("set wrEject 1")
    try:
        dut.read_json(timeout=2.0)
        dut.read_json(timeout=2.0)
    except TimeoutError:
        pass
    time.sleep(2.0)  # let TEARDOWN resolve off-screen
    ok = switch_app(dut, "WebRadio", timeout=10.0)
    check("2b-reenter-after-early-teardown", ok, "switched back to WebRadio")
    ok, st = wait_state(dut, lambda s: s == 0, timeout=5.0)
    check("2b-state-reconciled-stopped", ok, f"wrState={st}")

    # ── 3. TLS-yield accounting: interrupted vs. uninterrupted ──
    # Uses the persisted raw log (grep_new), not live drain_log_lines() --
    # the latter races against every intervening dut.cmd() call's own
    # read_json(), which consumes (and silently drops) whatever raw log
    # lines happen to be sitting in the serial buffer at the time, whether
    # or not the caller was looking for them.
    print("\n== 3a. TLS-yield accounting -- interrupted (stop during CONNECTING) ==")
    dut.cmd(f"set wrUrl {fresh_dead_url()}", timeout=5.0)
    time.sleep(0.1)
    dut.cmd("set wrStop 1", timeout=3.0)
    pos = log_pos(log_path)
    dut.cmd("set wrPlay 0", timeout=3.0)
    dut.cmd("set wrStop 1", timeout=3.0)  # interrupt while (likely) still CONNECTING
    ok, st = wait_state(dut, lambda s: s == 0, timeout=5.0)
    n_stop = grep_new(log_path, pos, r"tls yield . client stopped")
    n_res = grep_new(log_path, pos, r"tls yield . resumed")
    check("3a-tls-yielded", n_stop >= 1, f"saw {n_stop} 'client stopped' line(s)")
    check("3a-tls-resumed-after-abort", n_res >= 1, f"saw {n_res} 'resumed' line(s); final wrState={st}")

    print("\n== 3b. TLS-yield accounting -- uninterrupted (ordinary failed connect) ==")
    dut.cmd(f"set wrUrl {fresh_dead_url()}", timeout=5.0)
    time.sleep(0.1)
    dut.cmd("set wrStop 1", timeout=3.0)
    pos = log_pos(log_path)
    dut.cmd("set wrPlay 0", timeout=3.0)
    ok, st = wait_state(dut, lambda s: s in (0, 5), timeout=5.0)
    n_stop = grep_new(log_path, pos, r"tls yield . client stopped")
    n_res = grep_new(log_path, pos, r"tls yield . resumed")
    check("3b-tls-yielded", n_stop >= 1, f"saw {n_stop} 'client stopped' line(s)")
    check("3b-tls-resumed-after-failed-connect", n_res >= 1, f"saw {n_res} 'resumed' line(s)")
    check("3b-terminal-state", ok, f"wrState={st} (5=ERROR_UNREACHABLE expected, or 0 if auto-skip already reset)")

    # ── 5. Leave-and-quickly-re-enter during CONNECTING ──
    print("\n== 5. leave-and-quickly-re-enter during CONNECTING ==")
    dut.cmd(f"set wrUrl {fresh_dead_url()}", timeout=5.0)
    time.sleep(0.1)
    dut.cmd("set wrStop 1", timeout=3.0)
    t0 = time.monotonic()
    dut.cmd("set wrPlay 0", timeout=3.0)
    st = wr_state(dut)
    check("5-precondition-connecting", st == 1, f"wrState={st} at t={time.monotonic()-t0:.3f}s")
    ok1 = switch_app(dut, "Spotify", timeout=5.0)
    ok2 = switch_app(dut, "WebRadio", timeout=5.0)
    dt = time.monotonic() - t0
    check("5-fast-leave-reenter", ok1 and ok2, f"round-trip={dt:.2f}s")
    arena = dut.cmd("get arenaStats", timeout=3.0)
    check("5-no-crash-arena-sane", arena.get("ok", True), str(arena))
    ok, st = wait_state(dut, lambda s: s == 0, timeout=8.0)
    check("5-state-reconciled-not-stuck", ok, f"wrState={st}")
    pump = dut.cmd("get wrPump", timeout=3.0)
    check("5-single-pump-task", pump.get("ok", False), str(pump))
    cnt = dut.cmd("get wrCount", timeout=3.0).get("count", 0) or 0
    if cnt > 0:
        dut.cmd("set wrPlay 0", timeout=3.0)
        ok, st = wait_state(dut, lambda s: s in (2, 5), timeout=12.0)
        check("5-manual-play-after-reentry-works", ok, f"wrState={st}")
        dut.cmd("set wrStop 1", timeout=3.0)

    # ── 6. s_wr_audio doesn't dangle after TEARDOWN ──
    print("\n== 6. no dangling s_wr_audio after TEARDOWN (fresh session sanity) ==")
    dut.cmd(f"set wrUrl {fresh_dead_url()}", timeout=5.0)
    time.sleep(0.1)
    dut.cmd("set wrStop 1", timeout=3.0)
    dut.cmd("set wrPlay 0", timeout=3.0)
    switch_app(dut, "Spotify", timeout=5.0)  # triggers suspend() -> TEARDOWN (state was CONNECTING)
    time.sleep(2.0)
    ok = switch_app(dut, "WebRadio", timeout=10.0)
    check("6-reenter-after-teardown", ok, "switched back")
    cnt = dut.cmd("get wrCount", timeout=3.0).get("count", 0) or 0
    if cnt > 0:
        dut.cmd("set wrPlay 0", timeout=3.0)
        ok, st = wait_state(dut, lambda s: s in (2, 5), timeout=12.0)
        check("6-fresh-play-after-teardown-no-crash", ok, f"wrState={st}")
        r = dut.cmd("get appId", timeout=3.0)
        check("6-dut-still-alive", r.get("ok", False), "DUT responsive after fresh play post-teardown")
        dut.cmd("set wrStop 1", timeout=3.0)
    else:
        check("6-setup", True, "no stations to re-test with (non-fatal -- DUT survived re-entry, main check passed)")

    # ── 7. switchApp during real CONNECTING doesn't crash/corrupt arena ──
    print("\n== 7. switchApp-during-CONNECTING doesn't crash or corrupt the arena ==")
    dut.cmd(f"set wrUrl {fresh_dead_url()}", timeout=5.0)
    time.sleep(0.1)
    dut.cmd("set wrStop 1", timeout=3.0)
    dut.cmd("set wrPlay 0", timeout=3.0)
    ok = switch_app(dut, "Spotify", timeout=8.0)
    check("7-switch-away-succeeds", ok, "switched to Spotify while WebRadio was CONNECTING")
    time.sleep(3.0)  # let the (fast, real) connect + TEARDOWN resolve fully off-screen
    r = dut.cmd("get appId", timeout=3.0)
    check("7-dut-alive-after-connecting-switch", r.get("ok", False), str(r))
    ok = switch_app(dut, "WebRadio", timeout=10.0)
    arena = dut.cmd("get arenaStats", timeout=3.0)
    check("7-arena-sane-after-teardown", arena.get("ok", True), str(arena))

    dut.cmd("set bgPoll 1", timeout=2.0)
    switch_app(dut, "Spotify", timeout=5.0)

    print("\n== Summary ==")
    n_pass = sum(1 for _, ok, _ in _results if ok)
    n_fail = sum(1 for _, ok, _ in _results if not ok)
    for name, ok, detail in _results:
        print(f"  {'PASS' if ok else 'FAIL'}: {name}  {detail}")
    print(f"\n{n_pass} passed, {n_fail} failed. Raw log: {log_path}")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
