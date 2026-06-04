#!/usr/bin/env python3
"""
tlsYield reliability suite — TASK-138 / T219–T221.

Tests:
  T219: Stock quote tlsYield — all 8 tickers 200 + mechanism fires + maxBlk≥50k.
  T220: Crypto tlsYield — GET 200, NoMemory absent, mechanism fires + maxBlk≥50k.
  T221: Weather TCP-close regression — GET 200 + heap recovery ≤5k drop (HTTP/1.0
        close frees TLS; 'tcp keep open for reuse' absent).

        NOTE: Arduino HTTPClient log_d lines ('tcp is closed', 'tcp keep open for
        reuse') ARE visible with CORE_DEBUG_LEVEL=4 in the debug build. The suppression
        in logSink::setup() targets the ESP_LOG_xxx system tags; log_d uses the Arduino
        ARDUHAL tag which is separate. T221 checks both the heap criterion and the tcp log.

Implementation notes:
  All three tests use dut.send() (non-blocking) so the monitoring loop starts before
  any intermediate cmd() calls consume log lines. switchApp triggers App::init() which
  enqueues fetches immediately; the tlsYield fires within the next Spotify poll cycle
  (typically <5s). Starting the monitor before reading the switchApp ack is critical to
  capturing the yield log.

Usage:
    python3 test_tls_yield_reliability.py [--port /dev/ttyUSB0]
    python3 test_tls_yield_reliability.py --tests T219,T220,T221

Requirements:
    DUT flashed with cyd2usb_winamp_debug, WiFi up, Spotify creds valid.
    Active Spotify session required — tlsYield blocks until Spotify task yields its
    TLS client (T219, T220).
"""

import json
import re
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from run_serialdbg_tests import Dut
from ve_suite_base import (
    RESULTS, pass_, fail, skip, flake,
    make_arg_parser, run_suite, print_results,
)


# ── shared helpers ────────────────────────────────────────────────────────────

_WEATHER_APP_ID = 2   # AppId::Weather
_CRYPTO_APP_ID  = 3   # AppId::Crypto
_STOCK_APP_ID   = 7   # AppId::Stock

_STOCK_TICKERS = ["AAPL", "AMD", "AMZN", "ARM", "GOOG", "META", "MSFT", "NVDA"]


def _parse_maxblk_kb(line: str) -> int | None:
    """Extract maxBlk value in KB from a LOG_HEAP line, or None."""
    m = re.search(r"maxBlk=(\d+)k", line)
    return int(m.group(1)) if m else None


def _restore_to_spotify(dut: Dut, timeout: float = 5.0) -> bool:
    r = dut.cmd("switchApp 0", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.3)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("ok", False) and r2.get("name") == "Spotify"


def _parse_switchapp_ack(line: str, app_id: int) -> bool:
    """Return True if line is a JSON switchApp ack for the given app_id."""
    if not line.startswith("{"):
        return False
    try:
        obj = json.loads(line)
        return obj.get("cmd") == "switchApp" and obj.get("ok") is True
    except (json.JSONDecodeError, ValueError):
        return False


# ── T219 — Stock quote tlsYield ──────────────────────────────────────────────

def t219(dut: Dut):
    """T219: all 8 stock tickers 200; tlsYield fires before loop; maxBlk≥50k after yield.

    Implementation: uses dut.send() (non-blocking) for BOTH switchApp and set triggerFetch
    so the monitoring loop starts before any serial reads consume yield log lines.
    switchApp triggers StockApp.init() which enqueues a quote fetch; tlsYield fires within
    the next Spotify poll cycle (≤5s). The additional set triggerFetch ensures a second
    cycle runs even if init() was already called (app revisited).
    """
    print("T219  Stock quote tlsYield — 8 tickers 200 + mechanism + maxBlk≥50k")

    # Clear stale data, then start monitoring before switchApp ack is consumed.
    dut.ser.reset_input_buffer()
    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5
    t0 = time.monotonic()
    deadline = time.monotonic() + 100.0  # 100s: covers switchApp + two full cycles

    dut.send(f"switchApp {_STOCK_APP_ID}")
    print("  [T219] monitoring serial for stock quote fetch (up to 95s)…", flush=True)
    print("  [T219] tlsYield fires after current Spotify poll; will also send triggerFetch.", flush=True)

    switched             = False
    triggered            = False
    yield_stopped        = False
    yield_resumed        = False
    tickers_200: set[str]   = set()
    tickers_fail: list[str] = []
    heap_before_quotes: list[int] = []  # pre-loop LOG_HEAP entries (before first ticker)
    heap_after_loop:  list[int]   = []  # post-loop LOG_HEAP entries (after last ticker)
    quotes_in_progress   = False        # True while we're in a quote loop

    # Track quote progress per cycle to identify pre/post LOG_HEAP
    last_quote_count_at_heap = 0  # how many tickers were seen when last LOG_HEAP appeared

    while time.monotonic() < deadline:
        try:
            raw = dut.ser.readline()
        except Exception:
            continue
        line = raw.decode(errors="replace").strip()
        if not line:
            continue

        ts = time.monotonic() - t0

        # switchApp ack: send triggerFetch immediately after app switches
        if not switched and _parse_switchapp_ack(line, _STOCK_APP_ID):
            switched = True
            if not triggered:
                triggered = True
                dut.send("set triggerFetch 1")
            continue

        if "tls yield" in line and "client stopped" in line:
            yield_stopped = True
            print(f"  [T219] t+{ts:.0f}s  {line}", flush=True)

        elif "tls yield" in line and "resumed" in line:
            yield_resumed = True
            print(f"  [T219] t+{ts:.0f}s  {line}", flush=True)

        elif "dataTask.stock" in line and "quote GET" in line:
            for sym in _STOCK_TICKERS:
                if f"quote GET {sym} " in line:
                    m = re.search(rf"quote GET {sym} (-?\d+)", line)
                    if m:
                        code = int(m.group(1))
                        if code == 200:
                            tickers_200.add(sym)
                        else:
                            tickers_fail.append(f"{sym}:{code}")
            print(f"  [T219] t+{ts:.0f}s  {line}", flush=True)

        elif "dataTask.stock" in line and "maxBlk=" in line:
            mb = _parse_maxblk_kb(line)
            if mb is not None:
                print(f"  [T219] t+{ts:.0f}s  {line}", flush=True)
                # A LOG_HEAP before any tickers = pre-loop; after all 8 = post-loop
                n = len(tickers_200)
                if n == 0:
                    heap_before_quotes.append(mb)
                elif n == 8:
                    heap_after_loop.append(mb)

        # Stop when we have all 8 tickers AND a complete yield cycle
        if len(tickers_200) == 8 and yield_resumed:
            break
        # Also stop if we have all 8 tickers and yield evidence (even without "resumed")
        if len(tickers_200) == 8 and yield_stopped and heap_before_quotes:
            break

    dut.ser.timeout = orig_timeout

    if not switched:
        skip("T219", "switchApp 7 ack not seen — DUT not responding?")
        _restore_to_spotify(dut)
        return

    _restore_to_spotify(dut)

    if not tickers_200 and not yield_stopped:
        skip("T219", "no stock quote fetch observed in 95s — DUT not reaching Yahoo Finance?")
        return

    errors = []
    missing = [s for s in _STOCK_TICKERS if s not in tickers_200]
    if missing:
        errors.append(f"tickers missing 200: {missing}")
    if tickers_fail:
        errors.append(f"tickers non-200: {tickers_fail}")
    if not yield_stopped:
        # "resumed" alone proves the yield spin exited; it can only do so after "client stopped"
        if not yield_resumed:
            errors.append("tls yield mechanism not observed (neither client-stopped nor resumed)")
        # else: "resumed" seen means mechanism fired; "client stopped" was missed due to timing
    if not yield_resumed and not yield_stopped:
        errors.append("tls yield — resumed: not seen")
    # Heap check: any pre-loop LOG_HEAP (before first ticker) should be ≥50k
    if heap_before_quotes:
        min_pre = min(heap_before_quotes)
        if min_pre < 50:
            errors.append(f"pre-loop maxBlk={min_pre}k < 50k — TLS not freed before quote loop")
    elif heap_after_loop or len(tickers_200) == 8:
        # Fallback: check post-loop heap if pre-loop wasn't captured
        if heap_after_loop:
            min_post = min(heap_after_loop)
            if min_post < 50:
                errors.append(f"post-loop maxBlk={min_post}k < 50k")
        else:
            errors.append("no LOG_HEAP lines seen — verify SERIAL_DEBUG build")

    if errors:
        fail("T219", "; ".join(errors))
    else:
        pre_s  = f"pre_maxBlk_min={min(heap_before_quotes)}k" if heap_before_quotes else "pre_heap=N/A"
        yld_s  = f"yield={'stopped+resumed' if (yield_stopped and yield_resumed) else 'resumed-only' if yield_resumed else 'partial'}"
        pass_("T219", f"8/8 tickers 200; {yld_s}; {pre_s}≥50k")


# ── T220 — Crypto tlsYield ────────────────────────────────────────────────────

def t220(dut: Dut):
    """T220: crypto GET 200; NoMemory absent; tlsYield fires; maxBlk≥50k after yield.

    Uses dut.send() (non-blocking) so monitoring starts before the switchApp ack is
    consumed, capturing the yield log that fires within ms of CryptoApp.init().
    """
    print("T220  Crypto tlsYield — GET 200 + NoMemory absent + mechanism + maxBlk≥50k")

    dut.ser.reset_input_buffer()
    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5
    t0 = time.monotonic()
    deadline = time.monotonic() + 100.0

    dut.send(f"switchApp {_CRYPTO_APP_ID}")
    print("  [T220] monitoring serial for crypto fetch (up to 95s)…", flush=True)

    switched           = False
    yield_stopped      = False
    yield_resumed      = False
    got_200            = False
    no_memory_seen     = False
    heap_after_yield: list[int] = []

    while time.monotonic() < deadline:
        try:
            raw = dut.ser.readline()
        except Exception:
            continue
        line = raw.decode(errors="replace").strip()
        if not line:
            continue

        ts = time.monotonic() - t0

        if not switched and _parse_switchapp_ack(line, _CRYPTO_APP_ID):
            switched = True
            continue

        if "tls yield" in line and "client stopped" in line:
            yield_stopped = True
            print(f"  [T220] t+{ts:.0f}s  {line}", flush=True)

        elif "tls yield" in line and "resumed" in line:
            yield_resumed = True
            print(f"  [T220] t+{ts:.0f}s  {line}", flush=True)

        elif "dataTask.crypto" in line and "GET" in line:
            print(f"  [T220] t+{ts:.0f}s  {line}", flush=True)
            m = re.search(r"GET (-?\d+)", line)
            if m and int(m.group(1)) == 200:
                got_200 = True

        elif "dataTask.crypto" in line and "NoMemory" in line:
            no_memory_seen = True
            print(f"  [T220] NOMEMORY t+{ts:.0f}s  {line}", flush=True)

        elif "dataTask.crypto" in line and "maxBlk=" in line:
            mb = _parse_maxblk_kb(line)
            if mb is not None:
                print(f"  [T220] t+{ts:.0f}s  {line}", flush=True)
                heap_after_yield.append(mb)

        if got_200 and yield_resumed:
            break

    dut.ser.timeout = orig_timeout

    if not switched:
        skip("T220", "switchApp 3 ack not seen — DUT not responding?")
        _restore_to_spotify(dut)
        return

    _restore_to_spotify(dut)

    if not got_200 and not yield_stopped and not yield_resumed:
        skip("T220", "no crypto fetch observed in 95s — DUT not reaching CoinGecko?")
        return

    errors = []
    if not got_200:
        errors.append("dataTask.crypto GET 200 not seen")
    if no_memory_seen:
        errors.append("JSON parse error: NoMemory detected — tlsYield guard insufficient")
    if not yield_stopped:
        # "resumed" can only log after the yield spin exits; it proves the mechanism fired
        # even when "client stopped" races ahead of the monitoring window (LL-051 timing).
        if not yield_resumed:
            errors.append("tls yield mechanism not observed (neither client-stopped nor resumed)")
    if not yield_resumed and not yield_stopped:
        errors.append("tls yield — resumed: not seen")
    if heap_after_yield:
        min_mb = min(heap_after_yield)
        if min_mb < 50:
            errors.append(f"maxBlk after yield: min={min_mb}k < 50k — TLS headroom insufficient")
    else:
        errors.append("no dataTask.crypto LOG_HEAP line seen")

    if errors:
        fail("T220", "; ".join(errors))
    else:
        min_mb = min(heap_after_yield) if heap_after_yield else -1
        pass_("T220",
              f"GET 200; NoMemory absent; yield fired; maxBlk_min={min_mb}k≥50k")


# ── T221 — Weather TCP-close regression ──────────────────────────────────────

def t221(dut: Dut):
    """T221: weather GET 200; heap recovers ≤5k (HTTP/1.0 close frees TLS via http.end()).

    Uses dut.send() (non-blocking). The switchApp ack is identified in the monitoring loop
    by checking JSON lines; subsequent JSON from other commands (get appId, etc.) are
    filtered out. tcp log lines from HTTPClient ARE visible with CORE_DEBUG_LEVEL=4
    (ARDUHAL tag is not suppressed by logSink::setup()).
    """
    print("T221  Weather TCP-close regression — GET 200 + heap recovery ≤5k drop")

    # Allow DUT to settle after T220's Spotify reconnect activity.
    time.sleep(2.0)

    dut.ser.reset_input_buffer()
    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5
    t0 = time.monotonic()
    deadline = time.monotonic() + 100.0

    dut.send(f"switchApp {_WEATHER_APP_ID}")
    print("  [T221] monitoring serial for weather fetch (up to 95s)…", flush=True)

    switched                = False
    pre_maxblk:  int | None = None
    post_maxblk: int | None = None
    got_200                 = False
    tcp_keep_open_seen      = False
    tcp_closed_seen         = False
    heap_phase              = "pre"   # "pre" → before GET; "post" → after GET

    while time.monotonic() < deadline:
        try:
            raw = dut.ser.readline()
        except Exception:
            continue
        line = raw.decode(errors="replace").strip()
        if not line:
            continue

        ts = time.monotonic() - t0

        if not switched and _parse_switchapp_ack(line, _WEATHER_APP_ID):
            switched = True
            continue

        if "dataTask.weather" in line and "maxBlk=" in line:
            mb = _parse_maxblk_kb(line)
            if mb is not None:
                print(f"  [T221] t+{ts:.0f}s  {line}", flush=True)
                if heap_phase == "pre" and pre_maxblk is None:
                    pre_maxblk = mb
                elif heap_phase == "post" and post_maxblk is None:
                    post_maxblk = mb

        elif "dataTask.weather" in line and "GET" in line:
            print(f"  [T221] t+{ts:.0f}s  {line}", flush=True)
            m = re.search(r"GET (-?\d+)", line)
            if m and int(m.group(1)) == 200:
                got_200 = True
                heap_phase = "post"

        elif "tcp keep open for reuse" in line:
            tcp_keep_open_seen = True
            print(f"  [T221] TCP-KEEP t+{ts:.0f}s  {line}", flush=True)

        elif "tcp is closed" in line:
            tcp_closed_seen = True
            print(f"  [T221] t+{ts:.0f}s  {line}", flush=True)

        if got_200 and post_maxblk is not None:
            break

    dut.ser.timeout = orig_timeout

    # Ack detection is best-effort — data task may emit LOG_HEAP before the serial
    # command handler emits the JSON ack (different FreeRTOS tasks). Skip only if
    # no weather data arrived at all.
    _restore_to_spotify(dut)

    if not got_200 and pre_maxblk is None:
        skip("T221", "no weather data in 95s — DUT not reaching open-meteo.com?")
        return

    errors = []
    if tcp_keep_open_seen:
        errors.append("'tcp keep open for reuse' seen — HTTP/1.1 keep-alive regression")
    if pre_maxblk is None:
        errors.append("pre-fetch LOG_HEAP not seen")
    if post_maxblk is None:
        errors.append("post-fetch LOG_HEAP not seen — http.end() did not free TLS promptly?")
    if pre_maxblk is not None and post_maxblk is not None:
        drop = pre_maxblk - post_maxblk
        if drop > 5:
            errors.append(
                f"maxBlk dropped {drop}k (pre={pre_maxblk}k post={post_maxblk}k) > 5k — TLS leaked"
            )

    if errors:
        fail("T221", "; ".join(errors))
    else:
        drop = (pre_maxblk - post_maxblk) if (pre_maxblk is not None and post_maxblk is not None) else -1
        tcp_note = (f"tcp_closed confirmed" if tcp_closed_seen else "tcp_closed not observed")
        pass_("T221",
              f"GET 200; pre_maxBlk={pre_maxblk}k post_maxBlk={post_maxblk}k drop={drop}k≤5k; {tcp_note}")


# ── test registry + main ──────────────────────────────────────────────────────

ALL_TESTS = ["T219", "T220", "T221"]


def main():
    p = make_arg_parser(ALL_TESTS, description=__doc__)
    args = p.parse_args()
    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in selected if t not in ALL_TESTS]
    if unknown:
        sys.exit(f"Unknown tests: {unknown}. Available: {ALL_TESTS}")
    print(f"Connecting to {args.port} @ {args.baud}…")
    dut = Dut(args.port, args.baud, timeout=args.timeout)
    print(f"Connected. Running: {selected}\n")
    test_fns = {"T219": t219, "T220": t220, "T221": t221}
    run_suite(ALL_TESTS, test_fns, dut, selected, inter_test_sleep=1.0)
    dut.close()
    print_results(ALL_TESTS)


if __name__ == "__main__":
    main()
