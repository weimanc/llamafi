#!/usr/bin/env python3
"""TASK-416 / T_PLR_13 (playback half) — browse a ~200-file directory while a
real track plays, on cyd2usb_player.

TASK-425/431: local playback (the Helix arena acquiring at all) only works on
cyd2usb_player, where Spotify's ~39 KB TLS working set is compiled out
entirely (-DDISABLE_SPOTIFY). On cyd2usb_winamp_debug the arena FAILS in every
mount/arena ordering whenever that working set is resident — proven, not
theoretical (TASK-425's measured table). run_serialdbg_tests.py's t_plr_13
covers the browsing-only half (walk completes, DUT stays responsive) on
cyd2usb_winamp_debug; THIS script is the half that needs real audio: start a
real track, browse a 200-entry directory while it plays, and confirm playback
never stops and the DUT never stalls.

TASK-432 tolerance. `aeConnectFile()`'s `new Audio(...)` can throw an
uncaught bad_alloc under transient heap pressure right after a flash (filed,
OPEN, not this task's to fix) — abort() -> reboot. TASK-427's own DUT
evidence hit this on its first play attempt and a retry at settled heap
succeeded cleanly; this script does the same: if a reboot signature appears
mid-command, it is NOT treated as this test's failure — it waits for the
device to re-settle and restarts the whole sequence from scratch (state does
not survive a reboot), up to MAX_ATTEMPTS times.

Usage: run/browser-player (flashes cyd2usb_player, runs this, restores prod)
       python3 test_fbrowser_player.py --port /dev/ttyUSB1
"""
import argparse
import json
import sys
import time

import serial

PL_PATH = "/mp3/rel.m3u"     # a real playlist (TASK-415 fixture) pointing at
                              # this card's actual mp3s, not a synthetic one
BROWSE_DIR = "/probe200"     # TASK-408's 200-entry probe fixture
MAX_ATTEMPTS = 3
REBOOT_SETTLE_S = 90.0

_REBOOT_MARKERS = ("ets Jul", "rst:0x", "abort() was called")


class RebootDetected(Exception):
    pass


class PlaybackNeverStarted(Exception):
    """Not a crash — pump-task creation / arena acquire can fail transiently
    under heap pressure that hasn't fully settled yet (seen on the DUT: a
    `[E][wrpump] xTaskCreatePinnedToCore failed rc=-1` at 60s post-boot,
    clean at a later attempt). Gets the same retry-from-scratch treatment as
    a reboot — this env has no Spotify TLS working set to wait out
    (TASK-425/431), but WiFi/HTTPS/dataTask startup can still transiently
    hold task-table/heap headroom this close to boot."""
    pass


def wait_boot(ser: serial.Serial, settle_s: float) -> None:
    print(f"waiting {settle_s:.0f}s for boot + WiFi settle...", flush=True)
    time.sleep(settle_s)
    ser.reset_input_buffer()


def cmd(ser: serial.Serial, line: str, timeout: float = 6.0) -> dict:
    """Send one command, return its JSON reply. Raises RebootDetected if a
    reboot signature (TASK-432 crash, or any other reset) appears first —
    the caller decides whether to tolerate it."""
    ser.write((line + "\n").encode())
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        raw = ser.readline().decode(errors="replace").strip()
        if not raw:
            continue
        print(raw)
        if any(m in raw for m in _REBOOT_MARKERS):
            raise RebootDetected(raw)
        if raw.startswith("{"):
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            last = d
            if d.get("last") or "cmd" in d:
                return d
    return last


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def run_sequence(ser: serial.Serial, walk_timeout_s: float) -> tuple:
    """The whole enter-player -> load -> play -> browse sequence, one shot.
    Returns (elapsed, st) on success. Raises RebootDetected on a crash-reboot
    (caller retries from scratch) or calls fail() (via a raised SystemExit)
    on a real, non-reboot defect."""
    print("=== enter Player mode, load a real playlist, start playback ===")
    r = cmd(ser, "set playerMode player")
    if not r.get("ok"):
        fail(f"set playerMode player failed: {r}")

    r = cmd(ser, f"set plLoad {PL_PATH}")
    if not r.get("ok"):
        fail(f"set plLoad {PL_PATH} failed (fixture missing?): {r}")

    r = cmd(ser, "set plPlay 0")
    if not r.get("ok"):
        fail(f"set plPlay 0 failed: {r}")

    print("=== waiting for playback to actually start (arena acquire + decode) ===")
    playing = False
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        st = cmd(ser, "get plCount", timeout=4.0)
        if st.get("playing"):
            playing = True
            break
        time.sleep(1.0)
    if not playing:
        # DUT-measured (2026-08-11): a `[E][wrpump] xTaskCreatePinnedToCore
        # failed rc=-1` transient right after boot. Retrying `plPlay` on the
        # SAME session reproduced the identical lfbBefore figure and the
        # identical failure 3x running — this does NOT self-clear that way.
        # A genuinely fresh flash + a full 90s settle (this script's own
        # --settle-s) succeeded on the first attempt in isolation. Re-running
        # run/browser-player (a real reflash, not a soft reconnect) is the
        # correct remedy, not an in-process retry loop here — a soft
        # DTR-toggle reconnect lands inside the ESP32 double-reset-detector
        # window and reproduces the SAME stuck state rather than a clean boot.
        raise PlaybackNeverStarted("plCount.playing stayed false for 15s after plPlay")
    print("playback confirmed — arena acquired, MP3 decoding")

    print(f"=== opening {BROWSE_DIR} (200 entries) while playback continues ===")
    t0 = time.monotonic()
    r = cmd(ser, f"set fbOpen {BROWSE_DIR}")
    if not r.get("ok"):
        fail(f"set fbOpen {BROWSE_DIR} failed (fixture missing?): {r}")

    min_playing_seen = True
    st = None
    deadline = time.monotonic() + walk_timeout_s
    while time.monotonic() < deadline:
        st = cmd(ser, "get fbState", timeout=4.0)
        if not st.get("ok"):
            fail(f"DUT stopped responding mid-walk: {st}")
        pl = cmd(ser, "get plCount", timeout=4.0)
        if not pl.get("playing"):
            min_playing_seen = False
        if st.get("pending") is False:
            break
    elapsed = time.monotonic() - t0

    if st is None or st.get("pending"):
        fail(f"walk did not finish within {walk_timeout_s:.0f}s (elapsed {elapsed:.1f}s) "
             "— pump-starving regression")
    if not min_playing_seen:
        fail(f"playback stopped during the browse (underrun/crash) — dir walk took {elapsed:.1f}s")

    pl_final = cmd(ser, "get plCount", timeout=4.0)
    if not pl_final.get("playing"):
        fail(f"playback not still active after the walk finished: {pl_final}")

    return elapsed, st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--settle-s", type=float, default=90.0)
    ap.add_argument("--walk-timeout-s", type=float, default=20.0)
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=1.0)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.3)
    wait_boot(ser, args.settle_s)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            elapsed, st = run_sequence(ser, args.walk_timeout_s)
        except RebootDetected as e:
            if attempt == MAX_ATTEMPTS:
                fail(f"device rebooted on attempt {attempt}/{MAX_ATTEMPTS} ({e}) — "
                     "TASK-432 (aeConnectFile's uncaught bad_alloc, filed OPEN) reproduced "
                     "and did not clear after retries; that task's fix, not this one's")
            print(f"\n=== reboot detected on attempt {attempt}/{MAX_ATTEMPTS} ({e}) — "
                  "TASK-432-class transient crash (filed, OPEN, not this task's scope). "
                  f"Waiting {REBOOT_SETTLE_S:.0f}s and retrying the whole sequence "
                  "(state does not survive a reboot) ===\n")
            wait_boot(ser, REBOOT_SETTLE_S)
            continue
        except PlaybackNeverStarted as e:
            # A soft reconnect lands inside the ESP32 double-reset-detector
            # window and reproduces the identical stuck state rather than a
            # clean boot (DUT-measured — see run_sequence()'s comment). Only
            # a real reflash gets a genuinely fresh boot, so this is not
            # retried in-process; fail with the exact remedy.
            fail(f"playback never started ({e}) — DUT-measured: this needs a genuinely fresh "
                 "boot (a real reflash), not an in-process retry, which lands inside the "
                 "double-reset-detector window and reproduces the identical stuck state. "
                 "Re-run run/browser-player.")
        else:
            print(f"\nPASS: 200-entry walk completed in {elapsed:.1f}s with playback continuous "
                  f"throughout (dirCount={st.get('dirCount')} fileCount={st.get('fileCount')}), "
                  f"env=cyd2usb_player, attempt={attempt}/{MAX_ATTEMPTS}")
            ser.close()
            return 0
    return 1  # unreachable


if __name__ == "__main__":
    sys.exit(main())
