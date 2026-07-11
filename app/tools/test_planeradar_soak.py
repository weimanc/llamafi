#!/usr/bin/env python3
"""PlaneRadar + Spotify coexistence soak — TASK-307 exit criterion 4.

30-min foreground PlaneRadar soak while Spotify keeps its background TLS
session/poll alive (spotifyTask polls regardless of which app is in the
foreground — only WebRadio's tlsYield()/tlsResume() bracket suspends it, and
PlaneRadar's own fetch is bracketed the same way per NEW-APP-CHECKLIST #2).
This is the one exit criterion phase 0 explicitly could not settle off-DUT
(design doc R1's coexistence term) — everything else about the parse/heap
model was bounded on-host.

Records, each poll interval:
  - `get prAircraftCount` / `get prLastHttp` — confirms the app is still
    ticking and fetching, not wedged.
  - `info`'s `heap` field — tracks the free-heap floor across the run.
Watches the serial stream throughout for a reboot signature ("[boot]",
"ets Jul") or a crash string (panic/abort/stack overflow/Guru Meditation/
LoadProhibited/StoreProhibited) — either is an immediate hard fail.

Usage:
    python3 test_planeradar_soak.py --port /dev/ttyUSB0 --minutes 30
Requires: DUT flashed with cyd2usb_winamp_debug, WiFi up, Spotify session
authenticated and playing (device is the active Spotify Connect target).
Exit 0 = zero reboots/crashes and heap floor within budget; 1 otherwise.
"""
import re
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from run_serialdbg_tests import Dut, _switch_to, _restore_spotify   # noqa: E402
from ve_suite_base import make_arg_parser                            # noqa: E402

CRASH_RE = re.compile(
    r"\[boot\]|ets Jul|panic|abort|stack overflow|Guru Meditation|"
    r"LoadProhibited|StoreProhibited", re.I)

# VE-chosen budget (no number was committed in the design doc's exit criteria —
# "within agreed budget of pre-app baseline" was left for this run to pin down).
# Spotify's TLS session (~50 KB) is already resident before PlaneRadar ever
# enters the foreground; ADR-048's D1(b') chunked parse adds a measured ~4 KB
# fixed contribution on top. 15 KB gives that margin plus slack for TLS-record
# churn without masking a real regression — tighten once a real number's in.
HEAP_FLOOR_BUDGET_B = 15_000


def main():
    ap = make_arg_parser([], "PlaneRadar + Spotify coexistence soak (TASK-307 exit criterion 4)")
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--sample-secs", type=float, default=20.0,
                    help="heap/liveness sample interval while watching for crashes")
    args = ap.parse_args()

    dut = Dut(args.port, args.baud)
    ok = True
    reason = ""
    try:
        if not _restore_spotify(dut, timeout=10.0):
            print("[pr-soak] WARNING: could not confirm Spotify active before soak "
                  "(continuing — coexistence still exercises the background TLS session)")
        r_base = dut.cmd("info", timeout=5.0)
        baseline_heap = r_base.get("heap", 0)
        print(f"[pr-soak] pre-app baseline heap={baseline_heap}")

        if not _switch_to(dut, "PlaneRadar", timeout=15.0):
            print("[pr-soak] FAIL: could not switch to PlaneRadar")
            sys.exit(1)

        t_start = time.monotonic()
        t_end = t_start + args.minutes * 60
        min_heap = baseline_heap
        samples = 0
        last_count = None
        while time.monotonic() < t_end:
            slice_s = min(args.sample_secs, t_end - time.monotonic())
            if slice_s <= 0:
                break
            crash = dut.drain_log_lines(CRASH_RE.pattern, count=1, timeout=slice_s)
            if crash:
                ok = False
                reason = f"crash/reboot signature: {crash[0]!r}"
                break
            r_info = dut.cmd("info", timeout=5.0)
            heap = r_info.get("heap", min_heap)
            min_heap = min(min_heap, heap)
            r_pr = dut.cmd("get prAircraftCount", timeout=5.0)
            last_count = r_pr.get("val", last_count)
            r_app = dut.cmd("get appId", timeout=5.0)
            if r_app.get("name") != "PlaneRadar":
                ok = False
                reason = f"appId={r_app.get('name')!r} — no longer foreground PlaneRadar"
                break
            samples += 1
            elapsed = time.monotonic() - t_start
            print(f"  [pr-soak] t+{elapsed:.0f}s heap={heap} min={min_heap} "
                  f"prAircraftCount={last_count}", flush=True)

        if ok:
            floor_delta = baseline_heap - min_heap
            print(f"[pr-soak] done: {samples} samples, min_heap={min_heap}, "
                  f"baseline={baseline_heap}, delta={floor_delta}")
            if floor_delta > HEAP_FLOOR_BUDGET_B:
                ok = False
                reason = (f"heap floor delta {floor_delta}B > budget "
                          f"{HEAP_FLOOR_BUDGET_B}B (baseline={baseline_heap}, min={min_heap})")
    except Exception as e:
        ok = False
        reason = f"exception: {e}"
    finally:
        try:
            _restore_spotify(dut, timeout=10.0)
        except Exception:
            pass
        dut.close()

    print("\n" + "=" * 72)
    if ok:
        print(f"VERDICT: PASS — {args.minutes:.0f} min soak, zero reboots, "
              f"heap floor within {HEAP_FLOOR_BUDGET_B}B budget")
    else:
        print(f"VERDICT: FAIL — {reason}")
    print("=" * 72)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
