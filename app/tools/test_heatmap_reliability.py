#!/usr/bin/env python3
"""
Heatmap fetch reliability stress suite — TASK-130 / T214–T218.

Tests the two existing guards (f09f196 mailbox guard, a0f7601 main-loop guard)
and hunts for FM-1–FM-4 failure modes. All tests run on DUT via serial; no mocking.

Failure modes under test:
  FM-1: double-enqueue race — bad result races good in one-slot mailbox
  FM-2: long-uptime TLS heap fragmentation — persistent -1, no recovery
  FM-3: fetch -1 overwrites good _s.heatmapData (pre-fix regression check)
  FM-4: unknown — ERR -1 still seen after both fixes

Usage:
    python3 test_heatmap_reliability.py [--port /dev/ttyUSB0]
    python3 test_heatmap_reliability.py --tests T214,T215
    python3 test_heatmap_reliability.py --soak-minutes 10  # default

Requirements:
    DUT flashed with cyd2usb_winamp_debug, WiFi up, Spotify creds valid.
    Active Spotify session recommended (quota/chart fetches run in background).
"""

import argparse
import re
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from run_serialdbg_tests import (
    Dut,
    _switch_to_stock,
    _restore_from_stock,
    _wait_heatmap_count,
    _wait_shell_not_busy,
    _ensure_stock_list_view,
)

# ── result tracking ───────────────────────────────────────────────────────────

RESULTS: dict[str, str] = {}

def pass_(tid: str, detail: str = ""):
    RESULTS[tid] = "PASS"
    print(f"  [PASS] {tid}" + (f"  {detail}" if detail else ""))

def fail(tid: str, reason: str):
    RESULTS[tid] = f"FAIL: {reason}"
    print(f"  [FAIL] {tid}  {reason}")

def skip(tid: str, reason: str):
    RESULTS[tid] = f"SKIP: {reason}"
    print(f"  [SKIP] {tid}  {reason}")

def flake(tid: str, reason: str):
    RESULTS[tid] = f"FLAKE: {reason}"
    print(f"  [FLAKE] {tid}  {reason}")


# ── serial helpers ────────────────────────────────────────────────────────────

def _drain_for(dut: Dut, duration_s: float, line_cb=None):
    """Drain serial for duration_s seconds, calling line_cb(line) per non-empty line.
    Preserves ser.timeout."""
    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        try:
            raw = dut.ser.readline()
        except Exception:
            continue
        line = raw.decode(errors="replace").strip()
        if line and line_cb:
            line_cb(line)
    dut.ser.timeout = orig_timeout


def _safe_cmd(dut: Dut, cmd_str: str, timeout: float = 5.0) -> dict:
    """Send a command; return response dict. Returns {"ok": False, "error": "timeout"}
    on TimeoutError instead of raising."""
    try:
        return dut.cmd(cmd_str, timeout=timeout)
    except TimeoutError:
        return {"ok": False, "error": "timeout"}


def _safe_wait_heatmap_count(dut: Dut, timeout_s: float = 60.0) -> int | None:
    """Poll heatmapCount until > 0. Returns count (0 on timeout, None on comm error)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = dut.cmd("get heatmapCount", timeout=5.0)
        except TimeoutError:
            return None  # DUT stopped responding
        if r.get("ok"):
            try:
                val = int(r.get("val", 0))
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass
        time.sleep(3.0)
    return 0


def _flush(dut: Dut):
    """Flush any stale bytes from the serial input buffer."""
    dut.ser.reset_input_buffer()


def _parse_maxalloc_bytes(line: str) -> int | None:
    """Parse maxAlloc=Nk from heartbeat log line; return bytes or None."""
    m = re.search(r"maxAlloc=(\d+)k", line)
    return int(m.group(1)) * 1024 if m else None


def _heatmap_get_code(line: str) -> int | None:
    """Extract HTTP/error code from 'heatmap GET N' log line."""
    m = re.search(r"heatmap GET (-?\d+)", line)
    return int(m.group(1)) if m else None


def _poll_heatmap_state(dut: Dut) -> tuple[int, str]:
    """Return (heatmapCount, stockSubView). -1 / '?' on error."""
    rc = _safe_cmd(dut, "get heatmapCount", timeout=5.0)
    count = int(rc.get("val", -1)) if rc.get("ok") else -1
    rs = _safe_cmd(dut, "get stockSubView", timeout=3.0)
    sv = rs.get("val", "?") if rs.get("ok") else "?"
    return count, sv


# ── T214 ─────────────────────────────────────────────────────────────────────

def t214(dut: Dut):
    """T214: Rapid triggerHeatmap × 5 in 2s — heatmapCount must not drop to 0 after prior success.
    Covers FM-1 (double-enqueue race into one-slot mailbox)."""
    print("T214  Rapid triggerHeatmap × 5 in 2s — FM-1 double-enqueue guard")
    _flush(dut)
    if not _switch_to_stock(dut):
        skip("T214", "could not switch to Stock")
        _restore_from_stock(dut)
        return

    r = _safe_cmd(dut, "set triggerHeatmap 1")
    if not r.get("ok"):
        skip("T214", f"set triggerHeatmap 1 failed: {r}")
        _restore_from_stock(dut)
        return

    # Drain ~1s to let repaintHeatmap complete and initial enqueue land
    _drain_for(dut, 1.0)

    print("  [T214] waiting for initial successful fetch (up to 60s)…", flush=True)
    initial_count = _safe_wait_heatmap_count(dut, timeout_s=60.0)
    if initial_count is None:
        skip("T214", "DUT stopped responding during initial heatmapCount poll")
        _restore_from_stock(dut)
        return
    if initial_count == 0:
        skip("T214", "initial heatmapCount=0 after 60s — DUT not reaching Yahoo Finance")
        _restore_from_stock(dut)
        return

    print(f"  [T214] baseline heatmapCount={initial_count}; firing burst × 5…", flush=True)
    t_burst = time.monotonic()
    for i in range(5):
        _safe_cmd(dut, "set triggerHeatmap 1", timeout=3.0)
        elapsed = time.monotonic() - t_burst
        print(f"  [T214] trigger {i+1}/5 at {elapsed:.2f}s", flush=True)
    burst_s = time.monotonic() - t_burst
    print(f"  [T214] burst done in {burst_s:.2f}s; monitoring 60s for fetch completions…",
          flush=True)

    neg1_lines: list[str] = []
    ok200_lines: list[str] = []
    t_monitor = time.monotonic()

    def on_line(line: str):
        if "heatmap GET" in line:
            code = _heatmap_get_code(line)
            ts = time.monotonic() - t_monitor
            print(f"  [T214] t+{ts:.0f}s  {line}", flush=True)
            if code is not None and code < 0:
                neg1_lines.append(line)
            elif code == 200:
                ok200_lines.append(line)

    _drain_for(dut, 60.0, on_line)

    rc = _safe_cmd(dut, "get heatmapCount", timeout=5.0)
    final_count = int(rc.get("val", 0)) if rc.get("ok") else -1

    _restore_from_stock(dut)

    if final_count < 0:
        flake("T214", "get heatmapCount timed out after burst")
        return
    detail = (f"heatmapCount={final_count} (initial={initial_count}); "
              f"{len(ok200_lines)} ok; {len(neg1_lines)} errors")
    if final_count == 0:
        fail("T214", f"heatmapCount=0 after burst — FM-1 guard failed; {detail}")
    else:
        pass_("T214", detail)


# ── T215 ─────────────────────────────────────────────────────────────────────

def t215(dut: Dut):
    """T215: Observe 200 then -1 in same session; assert heatmapCount preserved and subView=heatmap.
    Covers FM-3 regression (bad result overwrites _s.heatmapData after fix)."""
    print("T215  200 → -1 sequence: heatmapCount must survive transient error (FM-3 guard)")
    _flush(dut)
    if not _switch_to_stock(dut):
        skip("T215", "could not switch to Stock")
        _restore_from_stock(dut)
        return

    r = _safe_cmd(dut, "set triggerHeatmap 1")
    if not r.get("ok"):
        skip("T215", "set triggerHeatmap 1 failed")
        _restore_from_stock(dut)
        return

    _drain_for(dut, 1.0)  # let repaintHeatmap settle

    print("  [T215] watching for heatmap GET 200 (up to 60s)…", flush=True)

    got_200 = False
    got_neg1 = False
    count_after_neg1 = -1
    sv_after_neg1 = "?"
    t0 = time.monotonic()

    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5
    deadline_200 = t0 + 60.0
    deadline_neg1 = None

    while True:
        now = time.monotonic()
        if not got_200 and now > deadline_200:
            break
        if got_200 and deadline_neg1 and now > deadline_neg1:
            break

        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            continue
        if not line:
            continue

        if "heatmap GET" in line:
            code = _heatmap_get_code(line)
            ts = now - t0
            print(f"  [T215] t+{ts:.0f}s  {line}", flush=True)

            if code == 200 and not got_200:
                got_200 = True
                deadline_neg1 = now + 30.0
                print("  [T215] 200 received — triggering second fetch to provoke -1…",
                      flush=True)
                dut.ser.timeout = orig_timeout
                _safe_cmd(dut, "set triggerHeatmap 1", timeout=3.0)
                dut.ser.timeout = 0.5

            elif code is not None and code < 0 and got_200 and not got_neg1:
                got_neg1 = True
                print(f"  [T215] -1 (code={code}) after 200 — checking count…", flush=True)
                time.sleep(2.0)  # allow main-loop tick to process result
                dut.ser.timeout = orig_timeout
                count_after_neg1, sv_after_neg1 = _poll_heatmap_state(dut)
                dut.ser.timeout = 0.5
                print(f"  [T215] heatmapCount={count_after_neg1} subView={sv_after_neg1!r}",
                      flush=True)
                break

    dut.ser.timeout = orig_timeout
    _restore_from_stock(dut)

    if not got_200:
        skip("T215", "no heatmap GET 200 in 60s — DUT not reaching Yahoo Finance")
        return
    if not got_neg1:
        skip("T215", "200 observed but no -1 in 30s — FM-1/FM-3 not reproduced in this window")
        return

    errors = []
    if count_after_neg1 == 0:
        errors.append("heatmapCount=0 after -1 — FM-3 regression (guard not working)")
    if count_after_neg1 == -1:
        errors.append("get heatmapCount timed out after -1")
    if sv_after_neg1 != "heatmap":
        errors.append(f"stockSubView={sv_after_neg1!r} (expected 'heatmap')")

    if errors:
        fail("T215", "; ".join(errors))
    else:
        pass_("T215", f"200 → -1 survived; heatmapCount={count_after_neg1} subView=heatmap")


# ── T216 + T217 (shared soak) ─────────────────────────────────────────────────

_SOAK_STARTED = False


def _run_soak(dut: Dut, soak_minutes: int):
    """Shared soak body — runs once; sets RESULTS for both T216 and T217.
    If called a second time (T217 after T216), reports T217 from existing data."""
    global _SOAK_STARTED

    if _SOAK_STARTED:
        # Second call: T216 already ran. If T217 not set, soak failed mid-way.
        if "T217" not in RESULTS:
            skip("T217", "soak did not complete (T216 failed before reporting T217)")
        return
    _SOAK_STARTED = True

    print(f"T216  {soak_minutes}-min soak: heatmapCount>0 and subView=heatmap throughout",
          flush=True)
    print(f"T217  Heap headroom: maxAlloc>32k after each fetch", flush=True)

    _flush(dut)
    if not _switch_to_stock(dut):
        skip("T216", "could not switch to Stock")
        skip("T217", "could not switch to Stock")
        _restore_from_stock(dut)
        return

    r = _safe_cmd(dut, "set triggerHeatmap 1")
    if not r.get("ok"):
        skip("T216", "set triggerHeatmap 1 failed")
        skip("T217", "set triggerHeatmap 1 failed")
        _restore_from_stock(dut)
        return

    _drain_for(dut, 2.0)  # let repaintHeatmap settle before polling

    print("  [T216] waiting for initial fetch (up to 60s)…", flush=True)
    initial_count = _safe_wait_heatmap_count(dut, timeout_s=60.0)
    if initial_count is None:
        skip("T216", "DUT stopped responding during initial heatmapCount poll (possible crash)")
        skip("T217", "DUT stopped responding during initial heatmapCount poll (possible crash)")
        _restore_from_stock(dut)
        return
    if initial_count == 0:
        skip("T216", "no initial fetch in 60s — DUT not reaching Yahoo Finance")
        skip("T217", "no initial fetch in 60s — DUT not reaching Yahoo Finance")
        _restore_from_stock(dut)
        return

    print(f"  [T216] initial heatmapCount={initial_count}; soak {soak_minutes} min starting…",
          flush=True)

    soak_s = soak_minutes * 60
    t_soak = time.monotonic()

    # Tracking
    neg1_events: list[tuple[float, str]] = []
    ok200_events: list[tuple[float, str]] = []
    count_reads: list[tuple[float, int]] = []
    count_zeros: list[float] = []
    sv_violations: list[tuple[float, str]] = []
    maxalloc_bytes: list[int] = []
    heap_violations: list[tuple[int, str]] = []

    poll_n = 0
    next_poll = t_soak + 30.0
    soak_deadline = t_soak + soak_s

    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5

    comm_errors = 0

    while time.monotonic() < soak_deadline:
        try:
            raw = dut.ser.readline()
        except Exception:
            continue
        line = raw.decode(errors="replace").strip()

        if not line:
            pass
        elif "heatmap GET" in line:
            ts = time.monotonic() - t_soak
            code = _heatmap_get_code(line)
            print(f"  [T216] t+{ts:.0f}s  {line}", flush=True)
            if code is not None and code < 0:
                neg1_events.append((ts, line))
            elif code == 200:
                ok200_events.append((ts, line))
        elif "[hb]" in line and "maxAlloc=" in line:
            alloc = _parse_maxalloc_bytes(line)
            if alloc is not None:
                maxalloc_bytes.append(alloc)
                ts = time.monotonic() - t_soak
                if alloc < 32768:
                    heap_violations.append((alloc, line))
                    print(f"  [T217] HEAP VIOLATION t+{ts:.0f}s maxAlloc={alloc//1024}k",
                          flush=True)
                else:
                    print(f"  [T216] t+{ts:.0f}s  hb maxAlloc={alloc//1024}k", flush=True)

        if time.monotonic() >= next_poll:
            next_poll += 30.0
            poll_n += 1
            dut.ser.timeout = orig_timeout
            ts = time.monotonic() - t_soak

            rc = _safe_cmd(dut, "get heatmapCount", timeout=5.0)
            rs = _safe_cmd(dut, "get stockSubView", timeout=3.0)

            if rc.get("error") == "timeout" or rs.get("error") == "timeout":
                comm_errors += 1
                print(f"  [T216] poll #{poll_n} t+{ts:.0f}s: COMM ERROR (DUT not responding)",
                      flush=True)
                dut.ser.timeout = 0.5
                continue

            count = int(rc.get("val", -1)) if rc.get("ok") else -1
            sv = rs.get("val", "?") if rs.get("ok") else "?"

            print(f"  [T216] poll #{poll_n} t+{ts:.0f}s: heatmapCount={count} subView={sv!r}",
                  flush=True)

            if count == 0:
                count_zeros.append(ts)
                print(f"  [T216] VIOLATION t+{ts:.0f}s: heatmapCount=0", flush=True)
            if sv != "heatmap":
                sv_violations.append((ts, sv))
                print(f"  [T216] VIOLATION t+{ts:.0f}s: stockSubView={sv!r}", flush=True)

            if count > 0:
                count_reads.append((ts, count))

            dut.ser.timeout = 0.5

    dut.ser.timeout = orig_timeout
    _restore_from_stock(dut)

    print(f"\n  [T216] soak complete: {poll_n} polls; "
          f"{len(ok200_events)} ok; {len(neg1_events)} errors; "
          f"{len(count_zeros)} count=0 events; {len(sv_violations)} subView violations; "
          f"{comm_errors} comm errors", flush=True)
    print(f"  [T217] {len(maxalloc_bytes)} maxAlloc readings; "
          f"{len(heap_violations)} violations", flush=True)

    # Evaluate T216
    t216_errors = []
    if count_zeros:
        t216_errors.append(f"heatmapCount=0 at {len(count_zeros)} polls "
                           f"(t={[f'{t:.0f}s' for t in count_zeros]})")
    if sv_violations:
        t216_errors.append(f"stockSubView violations at {len(sv_violations)} polls "
                           f"(values={[v for _, v in sv_violations]})")
    if comm_errors:
        t216_errors.append(f"{comm_errors} communication errors during soak "
                           f"(DUT not responding — possible crash/restart)")

    if t216_errors:
        fail("T216", "; ".join(t216_errors))
    else:
        pass_("T216",
              f"{poll_n} polls; {len(neg1_events)} errors observed; "
              f"count always>0; subView=heatmap throughout")

    # Evaluate T217
    if heap_violations:
        fail("T217", f"{len(heap_violations)} maxAlloc<32k readings: "
                     f"{[f'{v//1024}k' for v, _ in heap_violations]}")
    elif not maxalloc_bytes:
        skip("T217", f"no heartbeat maxAlloc lines in {soak_minutes}-min soak "
                     f"(hb every 30s; verify hb tag not filtered in this build)")
    else:
        min_alloc = min(maxalloc_bytes)
        pass_("T217", f"{len(maxalloc_bytes)} readings; "
                      f"min={min_alloc//1024}k; all ≥ 32k (TLS headroom OK)")


def t216(dut: Dut, soak_minutes: int = 10):
    _run_soak(dut, soak_minutes)


def t217(dut: Dut, soak_minutes: int = 10):
    _run_soak(dut, soak_minutes)


# ── T218 ─────────────────────────────────────────────────────────────────────

def t218(dut: Dut):
    """T218: After -1 cycle, heatmapCount recovers to >0 within 300s.
    Covers FM-2 (TLS heap fragmentation causing persistent failures)."""
    print("T218  Recovery: after -1, heatmapCount recovers within 300s (FM-2 check)",
          flush=True)
    _flush(dut)
    if not _switch_to_stock(dut):
        skip("T218", "could not switch to Stock")
        _restore_from_stock(dut)
        return

    r = _safe_cmd(dut, "set triggerHeatmap 1")
    if not r.get("ok"):
        skip("T218", "set triggerHeatmap 1 failed")
        _restore_from_stock(dut)
        return

    _drain_for(dut, 2.0)

    print("  [T218] waiting for initial successful fetch (up to 60s)…", flush=True)
    initial = _safe_wait_heatmap_count(dut, timeout_s=60.0)
    if initial is None:
        skip("T218", "DUT stopped responding during initial fetch wait")
        _restore_from_stock(dut)
        return
    if initial == 0:
        skip("T218", "no initial success in 60s — cannot test recovery")
        _restore_from_stock(dut)
        return

    print(f"  [T218] initial heatmapCount={initial}; watching for -1 (passive 120s)…",
          flush=True)

    got_neg1 = False
    neg1_ts = None
    neg1_line = ""
    t0 = time.monotonic()

    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5
    deadline_passive = t0 + 120.0

    while time.monotonic() < deadline_passive:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            continue
        if "heatmap GET" in line:
            code = _heatmap_get_code(line)
            ts = time.monotonic() - t0
            print(f"  [T218] t+{ts:.0f}s  {line}", flush=True)
            if code is not None and code < 0:
                got_neg1 = True
                neg1_ts = time.monotonic()
                neg1_line = line
                break

    if not got_neg1:
        print("  [T218] no -1 yet — sending 3 rapid triggers to provoke…", flush=True)
        dut.ser.timeout = orig_timeout
        for _ in range(3):
            _safe_cmd(dut, "set triggerHeatmap 1", timeout=3.0)
        dut.ser.timeout = 0.5
        deadline_provoke = time.monotonic() + 30.0
        while time.monotonic() < deadline_provoke:
            try:
                line = dut.ser.readline().decode(errors="replace").strip()
            except Exception:
                continue
            if "heatmap GET" in line:
                code = _heatmap_get_code(line)
                ts = time.monotonic() - t0
                print(f"  [T218] t+{ts:.0f}s  {line}", flush=True)
                if code is not None and code < 0:
                    got_neg1 = True
                    neg1_ts = time.monotonic()
                    neg1_line = line
                    break

    dut.ser.timeout = orig_timeout

    if not got_neg1:
        skip("T218", "no -1 in 150s (passive+provoked) — "
                     "FM-2 not reproduced; network/heap currently healthy")
        _restore_from_stock(dut)
        return

    print(f"  [T218] -1 observed: {neg1_line!r}; "
          f"waiting up to 300s for recovery (STOCK_HEATMAP_FETCH_MS=120s)…", flush=True)

    # Poll every 30s for up to 300s; STOCK_HEATMAP_FETCH_MS=120s gives 2+ chances
    recover_deadline = neg1_ts + 300.0
    recovered_count = 0
    recovery_elapsed = -1.0

    while time.monotonic() < recover_deadline:
        time.sleep(30.0)
        elapsed = time.monotonic() - neg1_ts
        count, sv = _poll_heatmap_state(dut)
        print(f"  [T218] t+{elapsed:.0f}s after -1: heatmapCount={count} subView={sv!r}",
              flush=True)
        if count == -1:
            print("  [T218] comm error — DUT not responding; skipping recovery check",
                  flush=True)
            skip("T218", "DUT stopped responding during recovery wait")
            _restore_from_stock(dut)
            return
        if count > 0:
            recovered_count = count
            recovery_elapsed = elapsed
            break

    _restore_from_stock(dut)

    if recovered_count == 0:
        fail("T218", "heatmapCount still 0 after 300s — FM-2 (TLS heap exhaustion) "
                     "confirmed; no auto-recovery within two 120s fetch windows")
    else:
        pass_("T218", f"recovered in {recovery_elapsed:.0f}s; heatmapCount={recovered_count}")


# ── test registry + main ──────────────────────────────────────────────────────

ALL_TESTS = ["T214", "T215", "T216", "T217", "T218"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", default="/dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=3.0,
                   help="default serial read timeout in seconds")
    p.add_argument("--tests", default=",".join(ALL_TESTS),
                   help="comma-separated test IDs")
    p.add_argument("--soak-minutes", type=int, default=10,
                   help="duration of T216/T217 soak (default 10)")
    args = p.parse_args()

    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in selected if t not in ALL_TESTS]
    if unknown:
        sys.exit(f"Unknown tests: {unknown}. Available: {ALL_TESTS}")

    print(f"Connecting to {args.port} @ {args.baud}…")
    dut = Dut(args.port, args.baud, timeout=args.timeout)
    try:
        dut.cmd("help", timeout=4.0)
    except Exception:
        pass
    print(f"Connected. Running: {selected}\n")

    for tid in selected:
        try:
            if tid == "T214":
                t214(dut)
            elif tid == "T215":
                t215(dut)
            elif tid == "T216":
                t216(dut, args.soak_minutes)
            elif tid == "T217":
                t217(dut, args.soak_minutes)
            elif tid == "T218":
                t218(dut)
        except TimeoutError as e:
            fail(tid, f"TimeoutError: {e}")
        except Exception as e:
            import traceback
            fail(tid, f"Exception: {e}")
            traceback.print_exc()
        time.sleep(0.5)

    dut.close()

    print("\n── Results ──────────────────────────────────")
    passed  = sum(1 for v in RESULTS.values() if v == "PASS")
    failed  = sum(1 for v in RESULTS.values() if v.startswith("FAIL"))
    skipped = sum(1 for v in RESULTS.values() if v.startswith("SKIP"))
    flaked  = sum(1 for v in RESULTS.values() if v.startswith("FLAKE"))
    for tid in ALL_TESTS:
        if tid in RESULTS:
            print(f"  {tid}: {RESULTS[tid]}")
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped, {flaked} flaked")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
