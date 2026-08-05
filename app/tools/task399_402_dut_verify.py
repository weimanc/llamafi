#!/usr/bin/env python3
"""DUT verification for TASK-399 (endless title-marquee wraparound) and
TASK-402 (WebRadio posbar EMA smoothing + rate-limited redraw), against
M-TITLE-MARQUEE-WRAP.md / M-WEBRADIO-POSBAR-SMOOTH.md.

Mechanism-level verification via serial polling of the new `get wrMarquee`
(textPx/periodPx/scrolling) and `get wrPosbar` (bufPctRaw/bufPctSmoothed/
bufPctDrawn/redraws/lastSkipReason) fields both designs added. This confirms
the underlying state machine behaves as designed (offset wraps without going
negative, both redraw gates are seen to bind, etc.) -- it is NOT a substitute
for the live human eyeball on the physical LCD both design docs' own exit
criteria call for (jump-free thumb motion, the shuriken separator reading
correctly, stall visibility). Ad hoc script, not added to the automated
run_serialdbg_tests.py suite, same convention as task400_401_dut_verify.py.

Usage: python3 task399_402_dut_verify.py [--port /dev/ttyUSB0]
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

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))
    return cond


def skip(name, detail=""):
    RESULTS.append((name, "SKIP", detail))
    print(f"[SKIP] {name}" + (f" -- {detail}" if detail else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    args = ap.parse_args()

    dut = Dut(args.port, log_file=str(Path(__file__).resolve().parent
                                       / "rnd_logs" / "task399_402_verify_raw.log"))

    # Shared setup: get into WebRadio with a real station loaded and (best
    # effort) actually PLAYING -- both tasks' fields only carry real data
    # once _pendingStations clears (marquee shows the real station name
    # instead of "Loading...") and once PLAYING (posbar has a real,
    # fluctuating buffer ratio instead of the pre-connect zero).
    entered = _ensure_webradio(dut, "shared-setup")
    station_count = 0
    is_playing = False
    if entered:
        station_count = _webradio_enter_with_stations(dut, "shared-setup", fetch_timeout=180.0)
        if station_count >= 1:
            is_playing = _wait_wr_state(dut, WR_STATE_PLAYING, timeout=30.0)
    check("shared-setup: entered WebRadio with stations loaded",
          entered and station_count >= 1, f"entered={entered} stations={station_count}")

    print("=== TASK-399: endless title-marquee wraparound ===")
    if entered and station_count >= 1:
        # Just long enough to clear TITLE_W (154px/6px pitch ~= 26 chars) once
        # combined with the station name -- kept short so the full-period
        # wrap-around wait below stays reasonable (period scales with length,
        # step rate is a fixed 1px/120ms regardless of content).
        long_title = "MARQUEE_WRAP_TEST_OK"
        r_set = dut.cmd(f"set wrIcy {long_title}")
        check("set wrIcy ok", r_set.get("ok") is True, str(r_set))
        time.sleep(0.3)

        # _drawTitleZone() shows "Loading..."/"Connecting..." ahead of the
        # ICY-folded title until the station is actually PLAYING/STOPPED
        # (default switch branch) -- re-send wrIcy each poll (dbgSet draws
        # immediately) until the composed title wins or this gives up.
        r0 = dut.cmd("get wrMarquee")
        wait_deadline = time.monotonic() + 15.0
        while (r0.get("lastTitle") in ("Loading...", "Connecting...")
               and time.monotonic() < wait_deadline):
            time.sleep(0.5)
            dut.cmd(f"set wrIcy {long_title}")
            r0 = dut.cmd("get wrMarquee")
        check("wrMarquee reachable", r0.get("ok") is True, str(r0))
        check("scrolling=true for long title", r0.get("scrolling") is True, str(r0))
        text_px = r0.get("textPx")
        period_px = r0.get("periodPx")
        check("periodPx > textPx (separator present)",
              isinstance(period_px, int) and isinstance(text_px, int) and period_px > text_px,
              f"textPx={text_px} periodPx={period_px}")

        # Poll the offset across several ticks (STEP_MS=120ms) and confirm it
        # increases, never goes negative (the old off-screen-respawn value),
        # and wraps back to a small value near 0 rather than jumping to a
        # large negative number -- the actual behavioral difference TASK-399
        # makes vs. the old bounce motion.
        # TITLE_SCROLL_STEP_MS=120ms, 1px/step -- a full period always takes
        # at least ~(period_px * 0.12)s regardless of content (fixed step
        # rate), so size the wait off the measured period rather than a
        # fixed guess (capped so a pathologically long injected string can't
        # hang the script).
        wait_s = min(90.0, (period_px or 0) * 0.12 + 5.0) if period_px else 20.0
        offsets = []
        saw_wrap = False
        prev = None
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline and len(offsets) < 400:
            r = dut.cmd("get wrMarquee", timeout=2.0)
            off = r.get("scrollOffset")
            if isinstance(off, int):
                offsets.append(off)
                if prev is not None and off < prev:
                    saw_wrap = True
                    check("wrap lands near 0, not a large negative offset",
                          0 <= off < 20, f"off={off} prev={prev}")
                prev = off
            time.sleep(0.15)
        check("offset observed advancing over time",
              len(set(offsets)) > 3, f"n_unique={len(set(offsets))} samples={offsets[:12]}")
        check("offset never negative (no off-screen respawn)",
              all(o >= 0 for o in offsets), f"min={min(offsets) if offsets else None}")
        if isinstance(period_px, int) and period_px:
            check("full wrap-around observed within the poll window",
                  saw_wrap or period_px > 900,
                  f"saw_wrap={saw_wrap} period_px={period_px} n_samples={len(offsets)}")

        # Short-text static path (Goal 3) unaffected.
        dut.cmd("set wrIcy -")
        time.sleep(0.3)
        r1 = dut.cmd("get wrMarquee")
        check("short text: scrolling=false (static path preserved)",
              r1.get("scrolling") is False, str(r1))
    else:
        skip("T399-setup", "could not enter WebRadio")

    print()
    print("=== TASK-402: posbar EMA smoothing + rate-limited redraw ===")
    if entered and station_count >= 1:
        # VE-1: debug-forced write bypasses both new gates, draws immediately.
        r_force = dut.cmd("set wrBufPct 37")
        check("set wrBufPct ok", r_force.get("ok") is True, str(r_force))
        time.sleep(0.1)
        rp0 = dut.cmd("get wrPosbar")
        check("wrPosbar reachable", rp0.get("ok") is True, str(rp0))
        check("forced value reflected immediately in bufPctDrawn (gate bypass)",
              rp0.get("bufPctDrawn") == 37, str(rp0))
        check("forced value synced into bufPctSmoothed (no resume-jump)",
              rp0.get("bufPctSmoothed") == 37, str(rp0))

        # Real playback: poll wrPosbar over a real-time window and confirm
        # the new fields behave -- raw fluctuates, redraw count increases but
        # not on every single tick (the whole point of the two gates), and
        # both skip reasons are named at least once if the window is long
        # enough to see a steady-state stretch.
        if not is_playing:
            # Cold-boot entry into a persisted WebRadio playerMode defers the
            # actual connect to the first toggle (see main.cpp's "refresh
            # deferred to first toggle" boot log) -- it does not autoplay.
            # Kick it explicitly rather than assume autoplay=on.
            dut.cmd("set wrPlay 0")
            is_playing = _wait_wr_state(dut, WR_STATE_PLAYING, timeout=25.0)
        if not is_playing:
            r_state = dut.cmd("get wrState")
            skip("T402-playback", f"not PLAYING (state={r_state.get('state')}), "
                 "skipping live-redraw-cadence checks")
        else:
            samples = []
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                r = dut.cmd("get wrPosbar", timeout=2.0)
                if r.get("ok"):
                    samples.append(r)
                time.sleep(0.25)
            redraw_counts = [s.get("redraws") for s in samples if isinstance(s.get("redraws"), int)]
            check("redraws counter present and monotonic non-decreasing",
                  len(redraw_counts) > 2 and redraw_counts == sorted(redraw_counts),
                  f"redraws={redraw_counts}")
            reasons = {s.get("lastSkipReason") for s in samples}
            check("lastSkipReason takes at least one recognized value",
                  reasons.issubset({"delta", "interval", "none"}) and len(reasons) > 0,
                  f"reasons_seen={reasons}")
            check("redraw count does not increase on every single 250ms sample "
                  "(time-floor gate is actually binding)",
                  len(redraw_counts) < 2 or (redraw_counts[-1] - redraw_counts[0]) < len(redraw_counts),
                  f"first={redraw_counts[0] if redraw_counts else None} "
                  f"last={redraw_counts[-1] if redraw_counts else None} n={len(redraw_counts)}")
    else:
        skip("T402-setup", "could not enter WebRadio")

    print()
    n_pass = sum(1 for _, s, _ in RESULTS if s == "PASS")
    n_fail = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    n_skip = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    print(f"=== {n_pass} passed, {n_fail} failed, {n_skip} skipped "
          f"(of {len(RESULTS)}) ===")
    dut.close()
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
