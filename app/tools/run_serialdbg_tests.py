#!/usr/bin/env python3
"""
Serial debug test harness — serialdbg-001 suite.

Executes T076–T088, T095, T096, T_BI_01–T_BI_04,
T_MA_01–T_MA_03, T_GOL_01–T_GOL_04, T_WX_01–T_WX_05,
T_CX_01–T_CX_05, T_X07_01,
T-BUSY-01/01b/02/03/05, T-CDWN-01/02/03,
T149–T154 (touch-capture-001),
T162–T166 (taskbar-scroll-001),
T_WR_EJECT_01/02, T_WR_ERR_01–04, T_WR_COEX_01/02/04,
T_WR_HEAP_01–04, T_WR_VOL_03, T_WR_TLS_01, T_WR_SPOTIFY_RESUME_01 (M-WEBRADIO),
T_WR_VIS_01–03 (vu-002 / X043, M-WEBRADIO-REAL-VIS),
T_WR_VIS_04/05 (vu-003 / X044, TASK-387, M-WEBRADIO-REAL-VIS-SPECTRUM),
T_PR_01–06 (M-PLANERADAR, TASK-307),
T_PLR_01–07 (M-PLAYER-STATE, TASK-413/414),
T_PLR_08–12 (M3U index model, TASK-415 — needs the SD fixtures from
             app/tools/gen_playlist_fixtures.py copied onto the card)
against a DUT flashed with cyd2usb_winamp_debug (or another testable variant —
set DUT_ENV, e.g. DUT_ENV=cyd2usb_player, and run/lib.sh + the ELF guard follow it).
T089 (production ELF symbol check) is a host build check — not run here.
T095 (physical vs. synthetic calibration) requires --interactive (human at DUT).

Usage:
    python3 run_serialdbg_tests.py [--port /dev/ttyUSB0] [--tests T076,T080,T084]
    python3 run_serialdbg_tests.py --interactive --tests T095

Requirements:
    pip install pyserial
    DUT flashed with cyd2usb_winamp_debug, booted, WiFi up, Spotify creds valid.
    Active Spotify Connect device playing a track (required for most tests).
    T_WX_05, T_CX_05, T_X07_01 require network access to api.open-meteo.com /
    api.coingecko.com.

All tap/drag screen coordinates are derived at import time from
gen/skin_layout.h via tools/coords.py. originX shifts automatically when
M-MULTIAPP changes WINDOW_W (no literal edits required in this file).
"""

import argparse
from contextlib import contextmanager
import json
import collections
import os
import pathlib
import re
import sys
import threading
import time
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import coords as _c
from app_ids_gen import APP_SLOT

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")


# ── DUT session layer — extracted to lib/dut.py (M-TESTBASE P1 / TASK-478) ────
# Re-exported here so all 16 external importers keep working unchanged:
#     from run_serialdbg_tests import Dut, _switch_to, _restore_spotify, ...
# Migrate them to `from lib.dut import resolve_port, Dut` a few per commit; this shim is the
# reason that migration can be incremental instead of a flag day.
from lib.dut import (resolve_port,                                               # noqa: E402,F401
    Dut, SetupFailure, _TeeSerial,
    resolve_port, set_no_wifi, TIMEOUT, TIMEOUT_SLOW,
    _is_ip_line, _PORTAL_INDICATORS, SETUP_FAIL_EXIT,
    _DUT_RESET_GAP_FILE, _DUT_DRD_WINDOW_S,
    _DUT_WIFI_WAIT_S, _DUT_WIFI_WAIT_2_S, _DUT_ENV,
    _SETUP_FAIL_TAIL_LINES,
)


# ── test registry ─────────────────────────────────────────────────────────────

# Result recording — extracted to lib/results.py (TASK-520). This file and
# ve_suite_base.py each carried an identical private copy; the flaky policy
# (ADR-059 D13 / M-TESTARCH §7) has to be enforced in exactly one of them, so
# both now re-export the shared implementation. Same shim pattern as lib/dut.py
# above, and RESULTS is now genuinely one dict rather than two that happened to
# agree. flake() consults docs/verification/flaky.yaml; an undeclared or expired
# id is a FAIL, a declared one is retried once by the dispatch loop in main().
from lib.results import (RESULTS, pass_, fail, skip, flake,   # noqa: E402,F401
                         run_with_flake_retry, print_results)



# ── everything else — moved to suite/serialdbg/shell.py (TASK-480) ──────────
# Catch-all family per M-TOOLING §3: taskbar/app-switch, PLEDIT drag mechanics,
# touch-capture, the small single-screen apps without their own family
# (Matrix/GameOfLife/Weather/Crypto), settings-nav, ADR-042 UART/bgPoll
# validation, the shell-busy/cooldown gate, app-error-signal.
from suite.serialdbg.shell import (                                             # noqa: E402,F401
    t077, t078, t079, t080, t081, t082, t083, t084, t085, t087, t088,
    t090, t091, t092, t093, t094, t095, t096,
    t133, t134, t135, t136, t137, t138, t139, t140, t147, t148,
    t149, t150, t151, t152, t153, t154,
    t_bi_01, t_bi_02, t_bi_03, t_bi_04,
    t_ma_01, t_ma_02, t_ma_03,
    t_gol_01, t_gol_02, t_gol_03, t_gol_04,
    t_wx_01, t_wx_02, t_wx_03, t_wx_04, t_wx_05,
    t_cx_01, t_cx_02, t_cx_03, t_cx_04, t_cx_05,
    t_x07_01,
    t_busy_01, t_busy_01b, t_busy_02, t_busy_03, t_busy_05,
    t_cdwn_01, t_cdwn_02, t_cdwn_03,
    t155, t156, t157, t158, t159, t160,
    t162, t163, t164, t165, t166, t242,
    t_tbfb_01, t_tbfb_02, t_tbfb_03, t_tbfb_04, t_tbfb_05,
    t_set_01, t_set_02, t_set_03, t_set_06, t_set_07, t_set_08,
    t_uart_01, t_bgpoll_01, t_bgpoll_02, t_bgpoll_03,
    t_err_01, t_err_02, t_err_04, t_err_05, t_err_06, t_err_07,
)

# ── every other already-extracted family — re-imported here so ALL_TESTS below
# keeps working unchanged. Each family's own module is still the source of
# truth; this is only the monolith's registry-assembly step.
from suite.serialdbg.stock import (                                             # noqa: E402,F401
    t169, t170, t171, t172, t173, t174, t175, t176, t177, t178, t179, t180,
    t181, t182, t183, t184, t231, t185, t186, t187, t188, t204,
    t192, t193, t194, t196, t200, t201, t202, t203,
)
from suite.serialdbg.webradio import (                                          # noqa: E402,F401
    t_ple_wr_155, t_ple_wr_156, t_ple_wr_157, t_ple_wr_158, t_ple_wr_159, t_ple_wr_160,
    t_wr_eject_01, t_wr_eject_02,
    t_wr_err_01, t_wr_err_02, t_wr_err_03, t_wr_err_04,
    t_wr_coex_01, t_wr_coex_02, t_wr_coex_04,
    t_wr_heap_01, t_wr_heap_02, t_wr_heap_03, t_wr_heap_04,
    t_wr_vol_03, t_wr_vol_clamp, t237, t276,
    t_wr_tls_01, t_wr_spotify_resume_01,
    t_wr_vis_01, t_wr_vis_02, t_wr_vis_03, t_wr_vis_04, t_wr_vis_05,
)
from suite.serialdbg.player import (                                            # noqa: E402,F401
    t_plr_01, t_plr_02, t_plr_03, t_plr_04, t_plr_05, t_plr_06, t_plr_07,
    t_plr_08, t_plr_09, t_plr_10, t_plr_11, t_plr_12, t_plr_13, t_plr_14,
    t_plr_15, t_plr_16, t_plr_17, t_plr_18, t_plr_19, t_plr_20, t_plr_21,
    t_plr_22, t_plr_23, t_plr_24, t_plr_25, t_plr_26,
    t_pmt_00, t_pmt_01, t_pmt_02, t_pmt_03, t_pmt_04,
)
from suite.serialdbg.clock import (                                             # noqa: E402,F401
    t_clk_01, t_clk_02, t_clk_03, t_clk_04, t_clk_05, t_clk_06, t_clk_07,
    t_clk_08, t_clk_09, t_clk_10, t_clk_11, t_clk_12, t_clk_13, t_clk_14,
)
from suite.serialdbg.teletext import t272, t270, t271                           # noqa: E402,F401
from suite.serialdbg.planeradar import (                                        # noqa: E402,F401
    t_pr_01, t_pr_02, t_pr_03, t_pr_04, t_pr_05, t_pr_06,
    t_prm_01, t_prm_02, t_pri_01,
)

ALL_TESTS = {
    "T077": t077,
    "T078": t078,
    "T079": t079,
    "T080": t080,
    "T081": t081,
    "T082": t082,
    "T083": t083,
    "T084": t084,
    "T085": t085,
    "T087": t087,
    "T088": t088,
    # T090 excluded from default runs — T091 covers reconnect behavior (see docstring).
    "T091": t091,
    "T092": t092,
    "T093": None,   # interactive visual; handled specially in main()
    "T094": None,   # interactive physical; handled specially in main()
    "T095": None,   # interactive; handled specially in main()
    "T096": t096,
    "T133": t133,
    "T134": t134,
    "T135": t135,
    "T136": t136,
    "T137": t137,
    "T138": t138,
    "T139": t139,
    "T140": t140,
    "T147": t147,
    "T148": t148,
    # touch-capture-001 (TASK-102)
    "T149": t149,
    "T150": t150,
    "T151": t151,
    "T152": t152,
    "T153": t153,
    "T154": t154,
    "T_BI_01": t_bi_01,
    "T_BI_02": t_bi_02,
    "T_BI_03": t_bi_03,
    "T_BI_04": t_bi_04,
    # matrix-001
    "T_MA_01": t_ma_01,
    "T_MA_02": t_ma_02,
    "T_MA_03": t_ma_03,
    # gol-001
    "T_GOL_01": t_gol_01,
    "T_GOL_02": t_gol_02,
    "T_GOL_03": t_gol_03,
    "T_GOL_04": t_gol_04,
    # weather-001
    "T_WX_01": t_wx_01,
    "T_WX_02": t_wx_02,
    "T_WX_03": t_wx_03,
    "T_WX_04": t_wx_04,
    "T_WX_05": t_wx_05,
    # crypto-001
    "T_CX_01": t_cx_01,
    "T_CX_02": t_cx_02,
    "T_CX_03": t_cx_03,
    "T_CX_04": t_cx_04,
    "T_CX_05": t_cx_05,
    # cross-feature X007
    "T_X07_01": t_x07_01,
    # stock-001 (TASK-110)
    "T169": t169,
    "T170": t170,
    "T171": t171,
    "T172": t172,
    "T173": t173,
    "T174": t174,
    "T175": t175,
    "T176": t176,
    "T177": t177,
    "T178": t178,
    "T179": t179,
    "T180": t180,
    "T181": t181,
    "T182": t182,
    "T183": t183,
    "T184": t184,
    "T231": t231,   # TASK-231: Settings → Stock mode launch view
    "T185": t185,
    "T186": t186,
    "T187": t187,
    "T188": t188,
    # stock-002 (TASK-120)
    "T192": t192,
    "T193": t193,
    "T194": t194,
    "T196": t196,
    "T200": t200,
    "T201": t201,
    "T202": t202,
    "T203": t203,
    # M-STOCK-VE-STRESS (step 2)
    "T204": t204,
    # M-TOUCH-UX (TASK-118)
    "T-BUSY-01":  t_busy_01,
    "T-BUSY-01b": t_busy_01b,
    "T-BUSY-02":  t_busy_02,
    "T-BUSY-03":  t_busy_03,
    "T-BUSY-05":  t_busy_05,
    "T-CDWN-01":  t_cdwn_01,
    "T-CDWN-02":  t_cdwn_02,
    "T-CDWN-03":  t_cdwn_03,
    # velocity-scroll-001 (TASK-104)
    "T155": t155,
    "T156": t156,
    "T157": t157,
    "T158": t158,
    "T159": t159,
    "T160": t160,
    # M-PLAYER-STATE three-way mode (TASK-413 / ADR-059 D6/D7)
    "T_PLR_01": t_plr_01,
    "T_PLR_02": t_plr_02,
    "T_PLR_03": t_plr_03,
    "T_PLR_04": t_plr_04,
    "T_PLR_05": t_plr_05,
    "T_PLR_06": t_plr_06,
    "T_PLR_07": t_plr_07,
    # M3U index model (TASK-415 / ADR-059 D3)
    "T_PLR_08": t_plr_08,
    "T_PLR_09": t_plr_09,
    "T_PLR_10": t_plr_10,
    "T_PLR_11": t_plr_11,
    "T_PLR_12": t_plr_12,
    # file browser (TASK-416 / M-WINAMP-PLAYER-local §4)
    "T_PLR_13": t_plr_13,
    "T_PLR_14": t_plr_14,
    "T_PLR_15": t_plr_15,
    "T_PLR_16": t_plr_16,
    # transport capability mask (TASK-417 / ADR-059 D8)
    # player mode transitions (M-TESTBASE P3 / §8) — operation-driven, not gesture
    "T_PMT_00": t_pmt_00,
    "T_PMT_01": t_pmt_01,
    "T_PMT_02": t_pmt_02,
    "T_PMT_03": t_pmt_03,
    "T_PMT_04": t_pmt_04,
    "T_PLR_17": t_plr_17,
    "T_PLR_18": t_plr_18,
    "T_PLR_19": t_plr_19,
    # play-order engine (TASK-418 / ADR-059 D9/D12)
    "T_PLR_20": t_plr_20,
    "T_PLR_21": t_plr_21,
    "T_PLR_22": t_plr_22,
    "T_PLR_23": t_plr_23,
    "T_PLR_24": t_plr_24,
    "T_PLR_25": t_plr_25,
    "T_PLR_26": t_plr_26,
    # velocity-scroll-001 WebRadio variant (TASK-412 / T_PLE_08)
    "T_PLE_WR_155": t_ple_wr_155,
    "T_PLE_WR_156": t_ple_wr_156,
    "T_PLE_WR_157": t_ple_wr_157,
    "T_PLE_WR_158": t_ple_wr_158,
    "T_PLE_WR_159": t_ple_wr_159,
    "T_PLE_WR_160": t_ple_wr_160,
    # taskbar-scroll-001 (TASK-105/TASK-106)
    "T162": t162,
    "T163": t163,
    "T164": t164,
    "T165": t165,
    "T166": t166,
    "T242": t242,
    # T167 retired (duplicate of T165); T168 manual (rendering — no serial observable)
    # taskbar-feedback-001 (TASK-279 / M-TASKBAR-FEEDBACK)
    "T_TBFB_01": t_tbfb_01,
    "T_TBFB_02": t_tbfb_02,
    "T_TBFB_03": t_tbfb_03,
    "T_TBFB_04": t_tbfb_04,
    "T_TBFB_05": t_tbfb_05,
    # settings-nav-stub-001 (TASK-142)
    "T-SET-01": t_set_01,
    "T-SET-02": t_set_02,
    "T-SET-03": t_set_03,
    "T-SET-06": t_set_06,
    "T-SET-07": t_set_07,
    "T-SET-08": t_set_08,
    # T-SET-04 manual visual; T-SET-05 manual visual
    # ADR-042 validation (T-UART-01, T-BGPOLL-01/02/03)
    "T-UART-01":    t_uart_01,
    "T-BGPOLL-01":  t_bgpoll_01,
    "T-BGPOLL-02":  t_bgpoll_02,
    "T-BGPOLL-03":  t_bgpoll_03,
    # M-CLOCK-STYLES suite (TASK-193)
    "T_CLK_01": t_clk_01,
    "T_CLK_02": t_clk_02,
    "T_CLK_03": t_clk_03,
    "T_CLK_04": t_clk_04,
    "T_CLK_05": t_clk_05,
    "T_CLK_06": t_clk_06,
    "T_CLK_07": t_clk_07,
    "T_CLK_08": t_clk_08,
    "T_CLK_09": t_clk_09,
    "T_CLK_10": t_clk_10,
    "T_CLK_11": t_clk_11,
    "T_CLK_12": t_clk_12,
    "T_CLK_13": t_clk_13,
    "T_CLK_14": t_clk_14,
    # M-TELETEXT TLS contention (TASK-191)
    "T272": t272,
    # M-TELETEXT synthetic subpage + boundary (TASK-197)
    "T270": t270,
    "T271": t271,
    # M-WEBRADIO eject + error states (TASK-211/212)
    "T_WR_EJECT_01": t_wr_eject_01,
    "T_WR_EJECT_02": t_wr_eject_02,
    "T_WR_ERR_01":   t_wr_err_01,
    "T_WR_ERR_02":   t_wr_err_02,
    "T_WR_ERR_03":   t_wr_err_03,
    "T_WR_ERR_04":   t_wr_err_04,
    # M-WEBRADIO DUT coexistence + heap (TASK-207/208/209)
    "T_WR_COEX_01":  t_wr_coex_01,
    "T_WR_COEX_02":  t_wr_coex_02,
    "T_WR_COEX_04":  t_wr_coex_04,
    "T_WR_HEAP_01":  t_wr_heap_01,
    "T_WR_HEAP_02":  t_wr_heap_02,
    "T_WR_HEAP_03":  t_wr_heap_03,
    "T_WR_HEAP_04":  t_wr_heap_04,
    "T_WR_VOL_03":   t_wr_vol_03,
    "T_WR_VOL_CLAMP": t_wr_vol_clamp,
    "T237":          t237,   # TASK-237: auto-skip terminal bound (dead-URL hook)
    "T276":          t276,   # TASK-276/395: terminal-retry re-arm actually fires
    # M-WEBRADIO TLS path + Spotify coexistence (TASK-214)
    "T_WR_TLS_01":            t_wr_tls_01,
    "T_WR_SPOTIFY_RESUME_01": t_wr_spotify_resume_01,
    # vu-002 / X043 — WebRadio real-audio VIS envelope (M-WEBRADIO-REAL-VIS)
    "T_WR_VIS_01": t_wr_vis_01,
    "T_WR_VIS_02": t_wr_vis_02,
    "T_WR_VIS_03": t_wr_vis_03,
    # vu-003 / X044 — real per-band spectrum (TASK-387)
    "T_WR_VIS_04": t_wr_vis_04,
    "T_WR_VIS_05": t_wr_vis_05,
    # app-error-signal-001 — red taskbar active-bar (TASK-245 / ADR-046)
    "T-ERR-01": t_err_01,
    "T-ERR-02": t_err_02,
    "T-ERR-04": t_err_04,
    "T-ERR-05": t_err_05,
    "T-ERR-06": t_err_06,
    "T-ERR-07": t_err_07,
    # M-PLANERADAR DUT validation (TASK-307)
    "T_PR_01": t_pr_01,
    "T_PR_02": t_pr_02,
    "T_PR_03": t_pr_03,
    "T_PR_04": t_pr_04,
    "T_PR_05": t_pr_05,
    "T_PR_06": t_pr_06,
    # TASK-355 poll-interval setting (M-PR-MOTION Item A)
    "T_PRM_01": t_prm_01,
    "T_PRM_02": t_prm_02,
    # TASK-357 motion smoothing (EXP-014 graduation)
    "T_PRI_01": t_pri_01,
}

def _setup_fail(reason: str, message: str, tail=None):
    """Report a rig condition and exit with SETUP_FAIL_EXIT. Never returns.

    The `[SETUP-FAIL]` prefix is the machine-greppable half; the serial tail is
    the half a human needs, because "check serial output" (the old message)
    names a stream that is closed by the time anyone reads it — and that
    run/test* is about to overwrite by reflashing prod."""
    print("", flush=True)
    print(f"[SETUP-FAIL] {reason}", flush=True)
    print(message, flush=True)
    if tail:
        print(f"\n--- last {len(tail)} serial lines before the abort ---", flush=True)
        for line in tail:
            print(f"  | {line}", flush=True)
        print("--- end serial tail ---", flush=True)
    print("\nThis is a RIG condition, not a test result. No tests ran; "
          "nothing here says the firmware is broken.", flush=True)
    sys.exit(SETUP_FAIL_EXIT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=resolve_port())
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=3.0,
                   help="default serial read timeout in seconds")
    p.add_argument("--interactive", action="store_true",
                   help="enable interactive tests (T093/T094/T095 — requires human at DUT)")
    _interactive_tests = {"T093", "T094", "T095"}
    default_tests = ",".join(k for k in ALL_TESTS if k not in _interactive_tests)
    p.add_argument("--tests", default=default_tests,
                   help="comma-separated test IDs, e.g. T080,T083,T084")
    p.add_argument("--no-wifi", action="store_true",
                   help="proceed even if the DUT never gets an IP. Only for suites that "
                        "touch no network (e.g. the SD-backed T_PLR_08-12).")
    p.add_argument("--log-file", default=None,
                   help="append every raw serial line (JSON responses AND bare "
                        "LOG_D/LOG_W lines) to this file — for diagnosing "
                        "failures whose cause isn't visible in dbg command output")
    args = p.parse_args()

    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in selected if t not in ALL_TESTS]
    if unknown:
        sys.exit(f"Unknown tests: {unknown}. Available: {list(ALL_TESTS)}")

    print(f"Connecting to {args.port} @ {args.baud}…")
    if args.log_file:
        print(f"Raw serial log: {args.log_file}")
    if args.no_wifi:
        set_no_wifi(True)   # P1: crosses into lib.dut, see set_no_wifi()
    # TASK-434 item 1 (VE-endorsed): a rig condition must never be
    # summarisable as "the tests failed". Without this wrapper the
    # SetupFailure propagates as a bare traceback and Python exits 1 — the
    # SAME code a real test failure produces — and the last thing in the log is
    # run/test*'s prod-restore flash output. Three misreads in one session came
    # from exactly that (2026-08-11).
    #
    # SerialException is caught alongside it per VE answer 3: pyserial's
    # "multiple access on port?" is a different exception from a different call
    # site, but it is equally a rig condition and today reads identically to a
    # log reader. Detecting a busy port BEFORE the open is separate work.
    try:
        dut = Dut(args.port, args.baud, timeout=args.timeout, log_file=args.log_file)
    except SetupFailure as e:
        _setup_fail(e.reason, str(e), getattr(e, "tail", None))
    except serial.SerialException as e:
        _setup_fail("port-busy", f"{e}\n"
                    f"Another process holds {args.port} — the tmux monitor "
                    f"(run/monitor-stop) or a peer session.")
    # Warmup ping: flush any residual DUT serial output before first test.
    try:
        dut.cmd("help", timeout=4.0)
    except Exception:
        pass
    # TASK-407: playerMode was observed flipping Spotify->WebRadio between DUT
    # sessions with no traced mutation path. Neither boundary (post-boot vs.
    # pre-shutdown) had a snapshot before this, so a flip could only be caught
    # by manually diffing separate sessions' logs after the fact. Printing it
    # at both ends of every run closes that gap going forward.
    # Guard broadly, not just TimeoutError: read_json() swallows JSON decode
    # errors, but ser.readline() can still raise SerialException on a CH340
    # flap. This snapshot runs before the first test, so anything escaping here
    # aborts the whole suite instead of dropping one diagnostic line. Same
    # defensive style as the `help` probe directly above.
    try:
        pm = dut.cmd("get playerMode", timeout=3.0)
        print(f"[TASK-407] entry playerMode: {pm.get('name')} ({pm.get('val')})")
    except Exception as e:
        print(f"[TASK-407] entry playerMode: unavailable ({type(e).__name__})")
    print(f"Connected. Running: {selected}\n")
    print("NOTE: T089 (production ELF check) is a host build test — not here.")
    skip_notice = [t for t in selected if t in _interactive_tests and not args.interactive]
    if skip_notice:
        print(f"NOTE: {skip_notice} will SKIP — re-run with --interactive.\n")
    else:
        print()

    for tid in selected:
        # TASK-386: emit a serial-side marker before every test. `get __TEST_<id>__`
        # is intentionally an unrecognized var — the firmware's existing "unknown var"
        # fallback (main.cpp) echoes it straight back on serial, so it lands in any
        # LOG_FILE= capture with zero firmware changes and zero behavior risk. Without
        # this, reconstructing which raw serial lines belong to which test after the
        # fact requires manually pattern-matching tap/command sequences — expensive and
        # sometimes impossible when multiple tests share the same coordinates (T-BUSY-01
        # couldn't be isolated this way during TASK-385/386's 2026-08-02 investigation).
        try:
            dut.cmd(f"get __TEST_{tid}__", timeout=2.0)
        except TimeoutError:
            pass
        def _once(tid=tid):
            try:
                if tid == "T093":
                    t093(dut, args.interactive)
                elif tid == "T094":
                    t094(dut, args.interactive)
                elif tid == "T095":
                    t095(dut, args.interactive)
                else:
                    ALL_TESTS[tid](dut)
            except TimeoutError as e:
                fail(tid, f"TimeoutError: {e}")
            except Exception as e:
                fail(tid, f"Exception: {e}")
        # TASK-520: one mandated retry for a DECLARED flake, both outcomes kept.
        # Undeclared/expired ids never get here — flake() already failed them.
        run_with_flake_retry(tid, _once)
        time.sleep(0.5)

    # TASK-407: see entry snapshot above for rationale.
    try:
        pm = dut.cmd("get playerMode", timeout=3.0)
        print(f"[TASK-407] exit playerMode: {pm.get('name')} ({pm.get('val')})")
    except Exception as e:
        print(f"[TASK-407] exit playerMode: unavailable ({type(e).__name__})")

    dut.close()

    # TASK-520: shared summary — reports declared flakes in their own bucket
    # instead of folding them into the pass count. sys.exit()s.
    print_results()


if __name__ == "__main__":
    main()
