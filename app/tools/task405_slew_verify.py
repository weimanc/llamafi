#!/usr/bin/env python3
"""DUT verification for TASK-405 (M-WEBRADIO-POSBAR-SLEW): the posbar's
delta-threshold gate was replaced with a slew-rate limiter, and a new
`wrPosbarSimDrain` debug hook was added (VE-2) to make OQ2 (does a real
depleting trend still show up in time through the gated/slewed path)
deterministically testable. Live-eyeball follow-up added a hysteresis
dead-band near the ceiling (WR_POSBAR_FREEZE_ENTER_PCT=90/EXIT_PCT=80) to
kill steady-state ceiling jitter -- host-only evaluated against real
captured traces + synthetic scenarios (see M-WEBRADIO-POSBAR-SLEW.md's
addendum) before landing here; this script re-verifies the mechanism on
real DUT/playback state.

Mechanism-level verification only -- NOT a substitute for the live human
eyeball on the physical LCD the design doc's own Exit Criteria require
(>=3 trials against SLAM! specifically) for the actual "does it look
smooth" call. Ad hoc script, not added to run_serialdbg_tests.py, same
convention as task399_402_dut_verify.py / task402_posbar_trace.py.

Usage: python3 task405_slew_verify.py [--port /dev/ttyUSB0]
"""
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_serialdbg_tests import (  # noqa: E402
    Dut, _ensure_webradio, _webradio_enter_with_stations, _wait_wr_state,
)

WR_STATE_PLAYING = 2
MAX_STEP = 2  # WR_POSBAR_MAX_STEP_PER_TICK

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))
    return cond


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    args = ap.parse_args()

    dut = Dut(args.port, log_file=str(Path(__file__).resolve().parent
                                       / "rnd_logs" / "task405_slew_verify_raw.log"))

    entered = _ensure_webradio(dut, "setup")
    station_count = _webradio_enter_with_stations(dut, "setup", fetch_timeout=180.0) if entered else 0
    check("setup: entered WebRadio with stations loaded",
          entered and station_count >= 1, f"entered={entered} stations={station_count}")
    if not (entered and station_count >= 1):
        dut.close()
        sys.exit(1)

    is_playing = _wait_wr_state(dut, WR_STATE_PLAYING, timeout=25.0)
    if not is_playing:
        dut.cmd("set wrPlay 0")
        is_playing = _wait_wr_state(dut, WR_STATE_PLAYING, timeout=25.0)
    check("setup: reached PLAYING", is_playing)
    if not is_playing:
        dut.close()
        sys.exit(1)

    print("\n=== wrBufPct bypass still works (unchanged behavior) ===")
    r_force = dut.cmd("set wrBufPct 37")
    check("set wrBufPct ok", r_force.get("ok") is True, str(r_force))
    rp0 = dut.cmd("get wrPosbar", timeout=1.0)
    # Only bufPctDrawn (the actually-visible, gate-controlled value) is asserted --
    # bufPctSmoothed is recomputed unconditionally from real buffer data on every
    # tick regardless of this debug hook (same race pre-dates TASK-405), so with a
    # real station concurrently playing it can have already drifted from 37 by the
    # time this read lands. Not a regression -- see raw log if this needs re-checking.
    check("forced value reflected immediately in bufPctDrawn (gate bypass)",
          rp0.get("bufPctDrawn") == 37, str(rp0))

    print("\n=== wrPosbarSimDrain: deterministic decline through the gated/slewed path ===")
    # Seed below wherever wrBufPct just left drawn (37) isn't guaranteed -- read current
    # state first rather than assume, then seed comfortably above it so the trace is a
    # clean decline, not an initial climb-then-decline.
    r_drain = dut.cmd("set wrPosbarSimDrain 80,4")
    check("set wrPosbarSimDrain ok", r_drain.get("ok") is True, str(r_drain))

    samples = []
    deadline = time.monotonic() + 15.0
    zero_streak = 0
    while time.monotonic() < deadline:
        r = dut.cmd("get wrPosbar", timeout=2.0)
        if r.get("ok"):
            samples.append(r)
            zero_streak = zero_streak + 1 if r.get("bufPctDrawn") == 0 else 0
        if zero_streak >= 3:  # sat at 0 for a few consecutive polls -- no auto-disable
            break             # bounce-back to worry about, safe to stop early
        # No fixed sleep -- back-to-back polling (~20-90ms/sample, per
        # task402_posbar_trace.py's precedent) stays well under the real
        # WR_POSBAR_MIN_REDRAW_MS=200ms step cadence, so no internal slew
        # step is missed between samples (a missed step would alias as a
        # single observed jump larger than WR_POSBAR_MAX_STEP_PER_TICK,
        # even though each real step was still individually bounded).

    drawn = [s.get("bufPctDrawn") for s in samples]
    check("drawn value reached 0 and stayed there (no auto-disable bounce-back)",
          len(drawn) >= 3 and drawn[-1] == 0 and drawn[-2] == 0,
          f"last5={drawn[-5:] if len(drawn) >= 5 else drawn}")
    check("decline was gradual, not instant (passed through a real midpoint -- OQ2)",
          len(set(drawn)) >= 10, f"n_unique={len(set(drawn))} n_samples={len(drawn)}")

    # The core slew-bound claim: no single redraw step exceeds MAX_STEP. Compare
    # consecutive *distinct* drawn values (skip repeats from oversampling relative
    # to the real MIN_REDRAW_MS cadence).
    distinct = []
    for d in drawn:
        if not distinct or distinct[-1] != d:
            distinct.append(d)
    steps = [abs(distinct[i] - distinct[i - 1]) for i in range(1, len(distinct))]
    check("every observed redraw step is <= WR_POSBAR_MAX_STEP_PER_TICK",
          len(steps) > 3 and all(s <= MAX_STEP for s in steps),
          f"steps={steps[:20]} max={max(steps) if steps else None}")

    reasons = {s.get("lastSkipReason") for s in samples}
    check("lastSkipReason takes only recognized (post-rename) values",
          reasons.issubset({"none", "converged", "interval", "frozen"}) and len(reasons) > 0,
          f"reasons_seen={reasons}")
    check("no stale 'delta' value leaking from the pre-rename enum",
          "delta" not in reasons, f"reasons_seen={reasons}")

    print("\n=== dead-band: freeze near ceiling, hold through decline to EXIT, "
          "then resume tracking (live-eyeball follow-up) ===")
    # The previous section ended with bufPctDrawn=0 (fully declined). Seeding
    # wrPosbarSimDrain 95,1 directly from there would make drawn *climb* from
    # 0 (capped at 2pts/200ms-tick) while raw is *simultaneously declining*
    # from 95 at 1pt/200ms-tick -- the climb can't out-pace the decline plus
    # close a 95-point gap before the target itself drops under the ENTER
    # threshold, so it would never freeze at all (this was tried first, and
    # is exactly what happened). Force drawn to 95 immediately first (wrBufPct
    # bypasses both gates), THEN start the slow sim-drain from there, so the
    # freeze test starts already at the ceiling like the host-eval scenarios did.
    dut.cmd("set wrBufPct 95")
    r_drain2 = dut.cmd("set wrPosbarSimDrain 95,1")
    check("set wrPosbarSimDrain 95,1 ok", r_drain2.get("ok") is True, str(r_drain2))

    samples2 = []
    deadline = time.monotonic() + 25.0
    zero_streak = 0
    while time.monotonic() < deadline:
        r = dut.cmd("get wrPosbar", timeout=2.0)
        if r.get("ok"):
            samples2.append(r)
            zero_streak = zero_streak + 1 if r.get("bufPctDrawn") == 0 else 0
        if zero_streak >= 3:
            break

    saw_frozen = any(s.get("frozen") is True for s in samples2)
    check("froze at some point while declining through the ceiling band",
          saw_frozen, f"n_samples={len(samples2)}")

    if saw_frozen:
        first_frozen_idx = next(i for i, s in enumerate(samples2) if s.get("frozen") is True)
        # While frozen, bufPctDrawn must not move even as raw/smoothed keep
        # declining underneath it (the whole point of the dead-band).
        frozen_run = []
        for s in samples2[first_frozen_idx:]:
            if s.get("frozen") is True:
                frozen_run.append(s)
            else:
                break
        drawn_during_freeze = {s.get("bufPctDrawn") for s in frozen_run}
        raw_during_freeze = [s.get("bufPctRaw") for s in frozen_run]
        check("bufPctDrawn held constant throughout a frozen run",
              len(drawn_during_freeze) == 1, f"values_seen={drawn_during_freeze}")
        check("bufPctRaw kept changing underneath the freeze (sim-drain still "
              "decrementing, not itself stuck)",
              len(set(raw_during_freeze)) > 1 or len(raw_during_freeze) < 3,
              f"raw_during_freeze={raw_during_freeze[:10]}")
        check("held value was actually near the ceiling (>= EXIT_PCT), not "
              "an unrelated freeze",
              next(iter(drawn_during_freeze)) >= 80, f"held={drawn_during_freeze}")

        # After the frozen run ends, confirm it wasn't a fluke -- unfrozen state
        # resumes normal declining behavior and reasons stay well-formed.
        post_unfreeze = samples2[first_frozen_idx + len(frozen_run):]
        reasons2 = {s.get("lastSkipReason") for s in post_unfreeze}
        check("post-unfreeze skip reasons still well-formed",
              reasons2.issubset({"none", "converged", "interval", "frozen"}),
              f"reasons_after_unfreeze={reasons2}")

    drawn2 = [s.get("bufPctDrawn") for s in samples2]
    check("dead-band run still reaches 0 eventually (freeze doesn't get "
          "permanently stuck)",
          len(drawn2) >= 3 and drawn2[-1] == 0 and drawn2[-2] == 0,
          f"last5={drawn2[-5:] if len(drawn2) >= 5 else drawn2}")

    print("\n=== disable sim-drain, confirm real buffer readings resume ===")
    r_off = dut.cmd("set wrPosbarSimDrain 0")
    check("set wrPosbarSimDrain 0 (disable) ok", r_off.get("ok") is True, str(r_off))
    # Don't assert bufPctRaw > 0 here -- the traced stations in this same session
    # showed real buffers legitimately sitting at/near 0 for extended stretches even
    # while genuinely PLAYING (network-delivery-paced, not a bug). The real signal
    # that the sim-drain override released control is *variability* resuming (the
    # override held raw frozen at exactly 0 for 3+ consecutive polls above), not a
    # specific non-zero value.
    post_raw = []
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        r = dut.cmd("get wrPosbar", timeout=2.0)
        if r.get("ok"):
            post_raw.append(r.get("bufPctRaw"))
    check("wrPosbar still reachable post-disable", len(post_raw) > 0, f"n={len(post_raw)}")
    check("raw value is no longer frozen (sim-drain override released, real "
          "per-tick computation resumed)",
          len(set(post_raw)) > 1, f"values_seen={sorted(set(post_raw))}")

    print()
    n_pass = sum(1 for _, s, _ in RESULTS if s == "PASS")
    n_fail = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    print(f"=== {n_pass} passed, {n_fail} failed (of {len(RESULTS)}) ===")
    dut.close()
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
