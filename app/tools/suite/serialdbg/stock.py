"""Stock app tests -- stock-001 (TASK-110) + stock-002 (TASK-120) suites.
Split from run_serialdbg_tests.py, TASK-480.

All tests use `switchApp <Stock>` (debug command) to reach StockApp directly rather
than scrolling the taskbar — taskbar scrolling is covered by T162-T168.
T182 is the one exception: it uses the taskbar path to exercise the real UI.

Firmware prerequisites (main.cpp):
  get stockSubView, get stockChartTicker, get stockChartRange,
  get lastQuoteFetch, get lastChartFetch,
  set fetchFailed, set fetchErrorCode, set triggerFetch,
  switchApp <id>

Geometry (from main.cpp constants):
  List rows: y_centre = 36 + 26*i   (AAPL=36, AMD=62, AMZN=88, ARM=114,
                                      GOOG=140, META=166, MSFT=192, NVDA=218)
  Chart header: y 0..17
  Back tap: (10, 7)   Chart tabs (x,7): 1D=148, 5D=184, 1M=220, YTD=256
  Plot area: y 18..213   Footer: y=214

stock-002 (heatmap sub-view):
  ST_LIST_RULE_Y = 22 -> tile canvas y=22..239, header y=0..21
  HEAT button:   tap 220 10   (x=220 > 190, y=10 < 22)
  Tile drill:    tap 10 30    (top-left corner -- always in the largest/first tile)
  Chart back:    tap 10 7
  Chart 5D tab:  tap 184 9
"""

import time

from lib.dut import Dut, DeviceReadError, NoAnswer
from lib.results import pass_, fail, skip, unmet  # noqa: F401 — skip used below
import coords as _c
from app_ids_gen import APP_SLOT
from suite.serialdbg._meta import meta
from suite.serialdbg._helpers import (
    _restore_spotify, _check_residue, _RESIDUE_DISPROOF,
    _diag_snapshot, _wait_shell_not_busy,
    _switch_to_stock, _restore_from_stock, _stock_get, _stock_ok_count,
    _wait_chart_complete, _drain_data_pipeline,
    _observe_progress_atom, _progress_atom_verdict, _bgpoll_suspended,
)


def _diag_val(dut: Dut, var: str, timeout: float = 3.0):
    """A device value for a FAILURE MESSAGE ONLY. Never an oracle term.

    TASK-585: the typed read raises, and the sites that read state to DESCRIBE a
    failure already have their verdict. Letting a NoAnswer out of one of those
    would convert a decided FAIL into an UNMET at the dispatch loop — the read
    that could not be made was the diagnostic, not the assertion. So the one
    place a default is still legitimate is named, is a string that no comparison
    in this file consumes, and is the only such place.
    """
    try:
        return dut.get_val(var, timeout=timeout)
    except DeviceReadError:
        return "?"


def _wait_quote_fetch(dut: Dut, baseline: int, timeout_s: float = 65.0) -> bool:
    """Wait until lastQuoteFetch advances past baseline (fetch completed).

    TASK-585: THIS IS THE SECOND INSTANCE OF `G-2`, which the WP-G audit did not
    name. The old body was `if r.get("ok") and int(r.get("val", 0)) != baseline`
    — a reply that arrived without a `val` defaulted to `0`, and `baseline` here
    is non-zero by construction (`T173` skips out when it reads 0; `T185`, the other such caller, was retired 2026-09-05 under TASK-603), so
    `0 != baseline` was TRUE and the wait returned success on a read it never
    made. Identical shape to `_stock_ok_count`'s `-1`, different literal. The
    typed read makes both unrepresentable.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if dut.get_int("lastQuoteFetch") != baseline:
                return True
        except NoAnswer:
            pass   # bounded poll loop; the deadline is the verdict, not this read
        time.sleep(2.0)
    # TASK-386: diagnostic snapshot on timeout, for every caller, automatically.
    # Return type/signature unchanged — zero risk to existing call sites — but the
    # get heap/backoff/dataq round trips still land on the wire and get captured by
    # any LOG_FILE= in effect, same rationale as _wait_chart_complete below.
    _diag_snapshot(dut, "_wait_quote_fetch-timeout")
    return False


def _stock_quote_ok_count(dut: Dut) -> int:
    """Current quoteOkCount. Raises rather than returning `-1` (TASK-585, `G-2`).

    `T170`'s entire oracle is `current > before` against this counter; with
    `before = -1` the next poll read the real, already-non-zero count and passed
    with no fetch in the window at all.
    """
    return dut.get_int("quoteOkCount")


# _drain_data_pipeline — moved to suite/serialdbg/_helpers.py (TASK-480):
# also used by webradio.py's T_WR_TLS_01, not stock-only as first assumed.


# ── T169 — Stock app switch round-trip ───────────────────────────────────────

def t169(dut: Dut):
    """T169 (L1): switchApp→Stock activates StockApp; switchApp→Spotify restores."""
    print("T169  Stock app switch round-trip")
    if not _restore_spotify(dut):
        skip("T169", "precondition: could not restore Spotify")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    from suite.serialdbg._helpers import _bgpoll_suspended
    with _bgpoll_suspended(dut):
        switched = _switch_to_stock(dut)
    if not switched:
        fail("T169", "switchApp did not switch to Stock")
        _restore_from_stock(dut)
        return
    r = _stock_get(dut, "stockSubView")
    if not r.get("ok"):
        fail("T169", f"get stockSubView failed: {r}")
        _restore_from_stock(dut)
        return
    if r.get("val") != "list":
        fail("T169", f"expected stockSubView=list on first launch, got {r.get('val')!r}")
        _restore_from_stock(dut)
        return
    if not _restore_from_stock(dut):
        fail("T169", "Stock→Spotify switch-back failed")
        return
    pass_("T169", "Stock round-trip OK; stockSubView=list on launch")


# ── T170 — Pre-fetch placeholders ─────────────────────────────────────────────

# `_DEFAULT_TICKERS` lived here and was used only to name a symbol from
# `stockQuoteProgress` in T170's two failure messages. The atom is a busy flag,
# not an index, so those names were fabricated; both messages and the list were
# removed by TASK-660.


# TASK-705: declares stock_quote_fetch. Its whole oracle IS a quote fetch
# completing (quoteOkCount advancing) within 65s — exactly the op's
# definition, TRUE for the body as written; no other op in OPS applies (it
# does not hold Spotify idle, so it is not the idle-control variant T_SQI_01
# adds).
@meta(ops=("stock_quote_fetch",))
def t170(dut: Dut):
    """T170 (L2): quote fetch completes after Stock switch-in; quoteOkCount advances within 65 s."""
    print("T170  Quote fetch completes after switch-in")
    if not _switch_to_stock(dut):
        skip("T170", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # TASK-585: the baseline is the whole oracle, so a baseline that could not be
    # read must end the id, not become `-1`. Restore first — the raise leaves the
    # device in Stock otherwise, and a leaked app is how one unreadable counter
    # becomes the next six ids' problem.
    try:
        before = _stock_quote_ok_count(dut)
    except DeviceReadError:
        _restore_from_stock(dut)
        raise
    print(f"  [T170] switched to Stock (quoteOkCount={before}); waiting for quote fetch…", flush=True)
    deadline = time.monotonic() + 65.0
    advanced = False
    last_progress = None
    last_progress_time = time.monotonic()
    while time.monotonic() < deadline:
        try:
            current = _stock_quote_ok_count(dut)
            if current > before:
                advanced = True
                break
            prog = dut.get_int("stockQuoteProgress", timeout=3.0)
        except NoAnswer:
            time.sleep(2.0)
            continue
        if prog != last_progress:
            last_progress = prog
            last_progress_time = time.monotonic()
        elif prog is not None and prog != -1 and time.monotonic() - last_progress_time > 20.0:
            # stockQuoteProgress is a busy flag ({0, -1}), not a ticker index —
            # a non-idle value says a quote fetch is in flight, and nothing
            # about which symbol (TASK-659/660). Do not name one.
            _restore_from_stock(dut)
            fail("T170", f"stockQuoteProgress stuck at {prog} for >20 s — a quote "
                         f"fetch was in flight and never cleared")
            return
        time.sleep(2.0)
    if not advanced:
        prog = _diag_val(dut, "stockQuoteProgress")
        # Busy flag, not a ticker index (TASK-659/660): 0 means a quote fetch
        # was in flight and never completed; -1 means none was ever in flight
        # in the window. Neither tells us which symbol — say only what is known.
        state = ("a quote fetch was in flight and did not clear" if prog == 0 else
                 "no quote fetch was ever in flight" if prog == -1 else
                 f"stockQuoteProgress={prog!r}, outside its {{0, -1}} domain")
        _restore_from_stock(dut)
        fail("T170", f"quoteOkCount did not advance within 65 s — {state}, "
                     f"fetchFailed={_diag_val(dut, 'fetchFailed')!r} "
                     f"fetchErrorCode={_diag_val(dut, 'fetchErrorCode')!r}")
        return
    _restore_from_stock(dut)
    pass_("T170", f"quoteOkCount advanced past {before} — quote fetch completed")



# ── T_DTP_01 / T_DTP_02 — M-DATATASK-PROGRESS atoms are actually written ──────
#
# TASK-657 (oracle sweep A-6). See `_helpers._observe_progress_atom` for what
# these assert and why that and not more. The two weather/crypto siblings are
# T_WX_07 / T_CX_07 in shell.py, beside the fetches they observe.
#
# NEITHER ID HAS EVER RUN ON HARDWARE (2026-09-06). They were written host-side
# with no DUT available and owe their first hardware run — recorded in the same
# shape TASK-645 used for `get boardId`. Until that run they are written, not
# passing, and must not be cited as evidence of anything.

# TASK-705: declares stock_quote_fetch. Its completion oracle
# (_quote_count_advanced) is deliberately the SAME "a quote fetch completed"
# claim T170 makes — the id's own comment says the atom is observed
# alongside, not instead of, that completion — so the op is TRUE for this
# body too, even though the atom-domain assertion itself is not in OPS.
@meta(ops=("stock_quote_fetch",))
def t_dtp_01(dut: Dut):
    """T_DTP_01: stockQuoteProgress leaves its -1 sentinel across a quote fetch,
    stays inside its {0, -1} busy-flag domain, and returns to -1.
    M-DATATASK-PROGRESS Phase 1."""
    print("T_DTP_01  stockQuoteProgress atom is written during a quote fetch")
    if not _switch_to_stock(dut):
        unmet("T_DTP_01", "could not switch to Stock — no quote fetch to observe")
        _restore_from_stock(dut)
        return
    try:
        before = _stock_quote_ok_count(dut)
    except DeviceReadError:
        _restore_from_stock(dut)
        raise
    obs = _observe_progress_atom(
        dut, "stockQuoteProgress",
        lambda: _quote_count_advanced(dut, before),
        timeout_s=65.0, test_id="T_DTP_01")
    _restore_from_stock(dut)
    outcome, msg = _progress_atom_verdict("stockQuoteProgress", obs)
    if outcome == "unmet":
        unmet("T_DTP_01", msg)
    elif outcome == "fail":
        # DOMAIN NOTE (TASK-660, ruled 2026-09-06 by TASK-659). The domain is
        # {0, -1}: `s_stockQuoteProgress` is written 0 once at the top of the
        # spark fetch and -1 once at the bottom (dataTaskStorage.cpp:471, :523).
        # It is a busy flag; there has been no per-ticker loop since TASK-249
        # collapsed the eight per-ticker GETs into one multi-symbol request.
        #
        # This id asserted the old documented [0,7] bound until TASK-660. That
        # was not the more rigorous choice — it was the vacuous one: {0} is
        # inside [0,7], so the clause passed on every build and could not fail
        # on any. The bound is now (0, 0) in `_PROGRESS_ATOM_DOMAIN`, which is
        # what would catch a firmware change reintroducing per-symbol indices.
        # Do not widen it back to match a stale comment.
        fail("T_DTP_01", msg)
    else:
        pass_("T_DTP_01", msg)


def _quote_count_advanced(dut: Dut, before: int) -> bool:
    """Completion oracle for T_DTP_01 — deliberately NOT the atom under test."""
    try:
        return _stock_quote_ok_count(dut) > before
    except (TimeoutError, NoAnswer):
        return False


def t_dtp_02(dut: Dut):
    """T_DTP_02: stockChartProgress leaves its -1 sentinel across a chart fetch,
    stays inside 0..2, and returns to -1. M-DATATASK-PROGRESS Phase 2."""
    print("T_DTP_02  stockChartProgress atom is written during a chart fetch")
    if not _switch_to_stock(dut):
        unmet("T_DTP_02", "could not switch to Stock — no chart fetch to observe")
        _restore_from_stock(dut)
        return
    # Same contention reasoning as T176: a chart fetch that serializes behind an
    # in-flight Spotify poll spends the whole window at -1 for reasons that have
    # nothing to do with the atom. Quiet the pipeline so the observation is of
    # the atom and not of the queue.
    #
    # R17/TASK-602: `_bgpoll_suspended` (which delegates to `Dut.saved`), NOT the
    # `set bgPoll 0` / try-finally / `set bgPoll 1` pair T176 still uses. A
    # try/finally is not a restore mechanism — it writes a literal `1` on the way
    # out, which is a silent WRITE for any caller that did not find it at 1.
    try:
        with _bgpoll_suspended(dut):
            if not _drain_data_pipeline(dut, tag="T_DTP_02"):
                unmet("T_DTP_02", "fetch pipeline never drained within 200 s — no chart "
                                  "fetch could be driven, so nothing was observed")
                return
            before = _stock_ok_count(dut)
            dut.set_cooldown_zero()
            dut.cmd("tap 137 36", timeout=3.0)   # drill into AAPL -> chart fetch
            time.sleep(0.3)
            if _stock_get(dut, "stockSubView").get("val") != "chart":
                unmet("T_DTP_02", "could not enter chart view — no chart fetch to observe")
                return
            obs = _observe_progress_atom(
                dut, "stockChartProgress",
                lambda: _chart_count_advanced(dut, before),
                timeout_s=45.0, test_id="T_DTP_02")
    finally:
        _restore_from_stock(dut)
    outcome, msg = _progress_atom_verdict("stockChartProgress", obs)
    if outcome == "unmet":
        unmet("T_DTP_02", msg)
    elif outcome == "fail":
        fail("T_DTP_02", msg)
    else:
        pass_("T_DTP_02", msg)


def _chart_count_advanced(dut: Dut, before: int) -> bool:
    """Completion oracle for T_DTP_02 — deliberately NOT the atom under test."""
    try:
        return _stock_ok_count(dut) > before
    except (TimeoutError, NoAnswer):
        return False


# ── T172 — App switch residue ─────────────────────────────────────────────────

def t172(dut: Dut):
    """T172 (L4): Spotify→Stock→Spotify; Winamp chrome repaints cleanly."""
    print("T172  App switch residue")
    if not _restore_spotify(dut):
        # TASK-584 / BP-074: the id measures Spotify's repaint on return. If we
        # could not start on Spotify there is no baseline and no return — the
        # premise did not hold. UNMET blocks (ADR-066 D4); the old skip() was
        # green.
        unmet("T172", "could not start the round trip on Spotify, so no "
                      "Spotify->Stock->Spotify transit was observed")
        return
    if not _switch_to_stock(dut):
        fail("T172", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    time.sleep(0.15)
    # TASK-685: the baseline MUST be read BEFORE the switch-back. The clock
    # stamps ONCE on resume and then stands still (measured: 3861 -> 127744
    # within 180 ms, then one value for 6 s), so a baseline read afterwards
    # sees the post-stamp value and the window observes a correctly idle
    # clock. Read here, while still away from Spotify, and the assertion
    # becomes "did the return repaint?" — which is the subject.
    _t_before = dut.get_int("lastPlaylistDraw", field="ms", timeout=3.0)
    if not _restore_from_stock(dut):
        fail("T172", "Stock→Spotify switch-back failed")
        return
    # `_restore_from_stock` already asserted `get appId == "Spotify"`
    # (`_helpers.py:_restore_from_stock` -> `_appid_is`), so the residue
    # assertion's precondition — "we are back on Spotify" — is established
    # above and a stalled clock here is attributable to the subject.
    if not _check_residue(dut, "T172", _t_before):
        fail("T172", "lastPlaylistDraw did not advance in 3 s after "
                     "Stock->Spotify switch-back — " + _RESIDUE_DISPROOF)


# ── T173 — Resume cache ───────────────────────────────────────────────────────

def t173(dut: Dut):
    """T173 (L5): switch away from Stock and back within 60 s; prices come from cache."""
    print("T173  Resume cache")
    if not _switch_to_stock(dut):
        skip("T173", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    try:
        baseline = dut.get_int("lastQuoteFetch")
    except DeviceReadError:
        _restore_from_stock(dut)
        raise
    if baseline == 0:
        skip("T173", "no quote fetch recorded yet — cannot verify resume cache")
        _restore_from_stock(dut)
        return
    # Switch away and quickly back.
    dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
    time.sleep(2.0)
    if not _switch_to_stock(dut):
        fail("T173", "could not switch back to Stock")
        _restore_from_stock(dut)
        return
    # TASK-585: this used to default to `-1` on a bad read, which then satisfied
    # `post_val != baseline` and reported a re-fetch the test never observed —
    # G-2's shape inverted (a false FAIL rather than a false PASS, but the same
    # unreadable-as-a-value defect).
    try:
        post_val = dut.get_int("lastQuoteFetch")
    finally:
        _restore_from_stock(dut)
    if post_val != baseline:
        fail("T173", f"lastQuoteFetch changed {baseline}→{post_val} — unexpected re-fetch on resume")
        return
    pass_("T173", f"lastQuoteFetch unchanged ({baseline}) — resume served from cache")


# ── T174 — Row drill-in ───────────────────────────────────────────────────────

def t174(dut: Dut):
    """T174 (L6): tap NVDA row (row 7, y=218); verify stockSubView=chart, stockChartTicker=NVDA."""
    print("T174  Row drill-in (NVDA)")
    if not _switch_to_stock(dut):
        skip("T174", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    r_sv = _stock_get(dut, "stockSubView")
    if r_sv.get("val") != "list":
        skip("T174", f"stockSubView={r_sv.get('val')!r} — expected list; prior test may have left chart view")
        _restore_from_stock(dut)
        return
    r_ff = _stock_get(dut, "stockSubView")
    # Also check fetchFailed via a set-then-get round-trip isn't practical here;
    # just proceed — if fetchFailed the tap will be ignored and subView stays list.
    dut.set_cooldown_zero()
    dut.cmd("tap 137 218", timeout=3.0)  # NVDA row centre: y = 25 + 7*26 + 11 = 218
    time.sleep(0.3)
    r_sv2 = _stock_get(dut, "stockSubView")
    r_tk  = _stock_get(dut, "stockChartTicker")
    r_rng = _stock_get(dut, "stockChartRange")
    _restore_from_stock(dut)
    if r_sv2.get("val") != "chart":
        fail("T174", f"stockSubView={r_sv2.get('val')!r} after tap — drill-in did not fire")
        return
    if r_tk.get("val") != "NVDA":
        fail("T174", f"stockChartTicker={r_tk.get('val')!r} — expected NVDA")
        return
    if r_rng.get("val") != "D1":
        fail("T174", f"stockChartRange={r_rng.get('val')!r} — expected D1 default on drill-in")
        return
    pass_("T174", "drill-in NVDA: subView=chart, ticker=NVDA, range=D1")


# ── T175 — Back navigation ────────────────────────────────────────────────────

def t175(dut: Dut):
    """T175 (C1): from chart view, tap back zone (10,7); stockSubView returns to list."""
    print("T175  Back navigation from chart")
    if not _switch_to_stock(dut):
        skip("T175", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Drill into any row (AAPL, row 0, y=36).
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)
    time.sleep(0.3)
    r_sv = _stock_get(dut, "stockSubView")
    if r_sv.get("val") != "chart":
        skip("T175", "drill-in did not fire (fetchFailed?) — cannot test back navigation")
        _restore_from_stock(dut)
        return
    # Tap back button: x=10 < ST_CHART_BACK_W(30), y=7 < ST_CHART_HEADER_H(18).
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)
    time.sleep(0.2)
    r_sv2 = _stock_get(dut, "stockSubView")
    _restore_from_stock(dut)
    if r_sv2.get("val") != "list":
        fail("T175", f"stockSubView={r_sv2.get('val')!r} after back tap — expected list")
        return
    pass_("T175", "back tap (10,7) returned stockSubView=list")


# ── T176 — Plot bounds (automated proxy only) ─────────────────────────────────

def t176(dut: Dut):
    """T176 (C2): chart fetch completes; fetchOkCount advances confirms data received."""
    print("T176  Plot bounds (automated: fetchOkCount advance; pixel check manual)")
    if not _switch_to_stock(dut):
        skip("T176", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # TASK-300: in full-suite order the drill-in's chart fetch serializes behind
    # an in-flight Spotify poll (tlsYield has no ack path inside doPoll; the
    # 403-latch keeps bgPoll on a 60 s cadence) and/or queued dataTask requests,
    # blowing the 45 s window with stockChartProgress still -1. This test
    # measures fetch COMPLETION, not latency under contention (TASK-244
    # accepted poll-bounded yield latency) — quiet the pipeline first, same
    # rationale as T_WR_TLS_01.
    dut.cmd("set bgPoll 0", timeout=2.0)
    try:
        if not _drain_data_pipeline(dut, tag="T176"):
            skip("T176", "fetch pipeline never drained within 200 s — "
                         "dataTask/spotifyTask wedged (investigate via get dataq)")
            _restore_from_stock(dut)
            return
        before = _stock_ok_count(dut)
        dut.set_cooldown_zero()
        dut.cmd("tap 137 36", timeout=3.0)  # drill into AAPL
        time.sleep(0.3)
        r_sv = _stock_get(dut, "stockSubView")
        if r_sv.get("val") != "chart":
            skip("T176", "could not enter chart view")
            _restore_from_stock(dut)
            return
        print(f"  [T176] drill-in complete (fetchOkCount={before}); waiting for fetch…", flush=True)
        fetched = _wait_chart_complete(dut, before, timeout_s=45.0, test_id="T176")
    finally:
        dut.cmd("set bgPoll 1", timeout=2.0)
    _restore_from_stock(dut)
    if not fetched:
        fail("T176", "fetchOkCount did not advance after 45 s with a drained pipeline "
                     "and bgPoll off — drill-in → enqueue path suspect (see dataq above)")
        return
    pass_("T176", "fetchOkCount advanced — chart data received; pixel bounds check is manual (y:18..213)")


# ── T177 — Range tab switch ───────────────────────────────────────────────────

def t177(dut: Dut):
    """T177 (C3): tap 5D tab (184,7); stockChartRange=D5 and lastChartFetch resets."""
    print("T177  Range tab — 5D")
    if not _switch_to_stock(dut):
        skip("T177", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)  # drill into AAPL
    time.sleep(0.3)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T177", "could not enter chart view")
        _restore_from_stock(dut)
        return
    # Tap 5D tab: x=184 (tab 1 centre), y=7 (header centre).
    dut.set_cooldown_zero()
    dut.cmd("tap 184 7", timeout=3.0)
    time.sleep(0.2)
    r_rng = _stock_get(dut, "stockChartRange")
    # lastChartFetch resets to 0 on tab change, then advances when enqueue fires.
    deadline = time.monotonic() + 5.0
    fetched = False
    while time.monotonic() < deadline:
        try:
            if dut.get_int("lastChartFetch") > 0:
                fetched = True
                break
        except NoAnswer:
            pass   # bounded poll; the 5 s deadline is the verdict
        time.sleep(0.3)
    _restore_from_stock(dut)
    if r_rng.get("val") != "D5":
        fail("T177", f"stockChartRange={r_rng.get('val')!r} after 5D tap — expected D5")
        return
    if not fetched:
        fail("T177", "lastChartFetch did not advance after tab change — enqueue not fired")
        return
    pass_("T177", "5D tab: stockChartRange=D5, lastChartFetch advanced")






# ── T180 — Drill-in default range ────────────────────────────────────────────

def t180(dut: Dut):
    """T180 (C6): every drill-in sets stockChartRange=D1."""
    print("T180  Drill-in default range always D1")
    if not _switch_to_stock(dut):
        skip("T180", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Normalize to list view — prior tests may leave Stock in chart view (T178, the usual culprit, was retired 2026-09-05 under TASK-603).
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=3.0)
        time.sleep(0.2)
    # Drill, change range, go back, re-drill — verify range resets.
    dut.set_cooldown_zero()
    r_drill1 = dut.cmd("tap 137 36", timeout=3.0)   # AAPL
    time.sleep(0.3)
    sv1 = _stock_get(dut, "stockSubView").get("val")
    if sv1 != "chart":
        skip("T180", "first drill-in failed")
        _restore_from_stock(dut)
        return
    # Wait for D1 fetch before changing tab (g_shellBusy must clear).
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 184 7", timeout=3.0)    # change to 5D
    # Wait for D5 fetch before navigating back.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)    # back to list
    time.sleep(0.2)
    # Wait for any quote refresh triggered by returning to list view.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)   # re-drill AAPL
    time.sleep(0.3)
    r_rng = _stock_get(dut, "stockChartRange")
    _restore_from_stock(dut)
    if r_rng.get("val") != "D1":
        fail("T180", f"stockChartRange={r_rng.get('val')!r} on re-drill — expected D1 reset")
        return
    pass_("T180", "re-drill after range change: stockChartRange reset to D1")


# ── T181 — Back then re-drill ─────────────────────────────────────────────────

def t181(dut: Dut):
    """T181 (C7): back→list→tap NVDA again; chart redraws with correct ticker."""
    print("T181  Back then re-drill")
    if not _switch_to_stock(dut):
        skip("T181", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Drill AAPL, go back, drill NVDA.
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)   # AAPL
    time.sleep(0.3)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T181", "first drill-in failed")
        _restore_from_stock(dut)
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)     # back
    time.sleep(0.2)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 218", timeout=3.0)  # NVDA row
    time.sleep(0.3)
    r_sv  = _stock_get(dut, "stockSubView")
    r_tk  = _stock_get(dut, "stockChartTicker")
    _restore_from_stock(dut)
    if r_sv.get("val") != "chart":
        fail("T181", "re-drill did not enter chart view")
        return
    if r_tk.get("val") != "NVDA":
        fail("T181", f"stockChartTicker={r_tk.get('val')!r} — expected NVDA")
        return
    pass_("T181", "back→re-drill NVDA: subView=chart, ticker=NVDA")


# ── T182 — Canvas isolation (taskbar-driven path) ─────────────────────────────

@meta(scope="taskbar", scope_reason="cross-feature",
      cls="FEATURE", cls_reason=
      "TASK-604, 2026-09-13. Re-scoping this id to `taskbar` (G-13/E-5) moves its "
      "seed from FEATURE to a SEEDED CORE, since taskbar is a gating scope by "
      "default — but the body cannot actually gate anything: both fail() calls "
      "are unreachable (WP-G G-13's BROKEN verdict), every real detection path "
      "exits as skip(). A test whose failure paths never fire cannot make the "
      "claim CORE requires about the rest of the run.")
def t182(dut: Dut):
    """T182 (cross): Stock→chart view→switchApp away→taskbar back→list; no residue."""
    print("T182  Stock canvas isolation (taskbar-driven switch)")
    if not _restore_spotify(dut):
        # TASK-584 / BP-074: unestablished premise, not a configuration
        # exclusion. UNMET blocks (ADR-066 D4); the old skip() was green.
        unmet("T182", "could not start on Spotify, so the return leg this id "
                      "measures had no origin")
        return
    # Enter chart view via serial switchApp (fastest setup).
    if not _switch_to_stock(dut):
        fail("T182", "could not switch to Stock")
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)
    time.sleep(0.3)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        # Setup, not the subject: the claim is about the TASKBAR-driven return
        # out of a non-default sub-view. Without the sub-view there is nothing
        # to isolate — premise unestablished, and it blocks.
        unmet("T182", "could not enter Stock chart view, so the non-default "
                      "sub-view this id switches away from never existed")
        _restore_from_stock(dut)
        return
    # Switch away via switchApp.
    dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
    time.sleep(0.3)
    # Switch back via taskbar scroll + slot tap (real UI path).
    dut.set_cooldown_zero()
    dut.cmd("drag 297 200 297 100 10", timeout=3.0)  # scroll up 2 slots → offset=2
    time.sleep(0.3)
    r_off = dut.cmd("get tbScrollOffset", timeout=3.0)
    if r_off.get("val") != 2:
        # TASK-584 / D-2: this IS the subject. T182 is the family's only
        # taskbar cross-feature test; "the taskbar scroll did not take" is the
        # cross-feature regression, not a reason to stand down.
        fail("T182", f"taskbar drag did not scroll: tbScrollOffset="
                     f"{r_off.get('val')!r}, expected 2")
        dut.cmd("drag 297 100 297 200 10", timeout=3.0)  # reset scroll
        _restore_spotify(dut)
        return
    dut.set_cooldown_zero()
    # Physical slot at scrollOffset=2 → AppId (offset+slot)%TASKBAR_APP_COUNT == Stock.
    # NOTE: this test intentionally uses physical-slot arithmetic, not APP_SLOT.
    # It breaks if the app order changes — update the drag offset and slot together.
    # Mod base is APP_SLOT["WebRadio"] (= firmware TASKBAR_APP_COUNT, the taskbar
    # cycle length excluding eject-only WebRadio — TASK-242), NOT APP_COUNT (TASK-347:
    # Settings moved directly before WebRadio, shifting Stock's physical slot 5→4).
    _stock_physical_slot = (APP_SLOT["Stock"] - 2) % APP_SLOT["WebRadio"]
    sx, sy = _c.tap_taskbar_slot(_stock_physical_slot)
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.4)
    # TASK-584/596: typed. A silent device raises NoAnswer -> UNMET at the
    # runner; a device that answers the wrong app is the defect below. The old
    # `dut.cmd(...).get("name")` could not tell those two apart, and skipped on
    # both.
    landed = dut.get_str("appId", field="name", timeout=3.0)
    if landed != "Stock":
        # TASK-584 / D-2: also the subject. Physical-slot arithmetic at
        # scrollOffset=2 resolving to the wrong app is exactly the taskbar
        # cross-feature regression this id is the only place in the family to
        # cover.
        fail("T182", f"taskbar slot tap at scrollOffset=2 landed in {landed!r}, "
                     f"expected Stock — physical-slot mapping is wrong")
        dut.cmd("drag 297 100 297 200 10", timeout=3.0)
        _restore_spotify(dut)
        return
    # resume() should restore to last subView (chart) then list if we tapped back...
    # Actually resume() calls repaintChart() if subView==ChartDetail.
    # The test is: no display crash, subView is still whatever it was.
    r_sv = _stock_get(dut, "stockSubView")
    # Reset taskbar scroll.
    dut.cmd("drag 297 100 297 200 10", timeout=3.0)
    # TASK-584: this was `if not r_app.get("ok")` on a reply whose `name` had
    # already been read successfully two lines above — an unreachable `fail()`
    # standing in for the reachable one. `_restore_from_stock` asserts
    # `get appId == "Spotify"` (`_appid_is`), so it is the real establishment of
    # the residue assertion's precondition and a real failure of the return leg.
    # TASK-685: the baseline MUST be read BEFORE the switch-back. The clock
    # stamps ONCE on resume and then stands still (measured: 3861 -> 127744
    # within 180 ms, then one value for 6 s), so a baseline read afterwards
    # sees the post-stamp value and the window observes a correctly idle
    # clock. Read here, while still away from Spotify, and the assertion
    # becomes "did the return repaint?" — which is the subject.
    _t_before = dut.get_int("lastPlaylistDraw", field="ms", timeout=3.0)
    if not _restore_from_stock(dut):
        fail("T182", "Stock->Spotify return leg did not land on Spotify after "
                     "the taskbar-driven switch")
        return
    if not _check_residue(dut, "T182", _t_before):
        fail("T182", "lastPlaylistDraw did not advance in 3 s after the "
                     "taskbar-driven return to Spotify — " + _RESIDUE_DISPROOF)
        return


# ── T183 — Inject fetch error ────────────────────────────────────────────────

def t183(dut: Dut):
    """T183 (error): set fetchFailed=1, fetchErrorCode=-1; tap ignored; error screen shown."""
    print("T183  Inject fetch error")
    if not _switch_to_stock(dut):
        skip("T183", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Ensure list view — prior test may have left us in chart view.
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=3.0)  # back to list
        time.sleep(0.2)
    dut.cmd("set fetchFailed 1", timeout=3.0)
    dut.cmd("set fetchErrorCode -1", timeout=3.0)
    time.sleep(0.15)  # wait one tick for repaint
    # Tap a list row — should be ignored when fetchFailed.
    dut.set_cooldown_zero()
    dut.cmd("tap 137 120", timeout=3.0)
    time.sleep(0.1)
    r_sv = _stock_get(dut, "stockSubView")
    # Clear error state before returning.
    dut.cmd("set fetchFailed 0", timeout=3.0)
    dut.cmd("set fetchErrorCode 0", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv.get("val") != "list":
        fail("T183", f"stockSubView={r_sv.get('val')!r} after tap while fetchFailed — expected no drill-in")
        return
    pass_("T183", "tap ignored while fetchFailed=1; stockSubView stayed list; error screen shown (manual verify)")


# ── T184 — Error in chart view ────────────────────────────────────────────────

def t184(dut: Dut):
    """T184 (error/chart): inject error while in chart; back button still works."""
    print("T184  Error injection in chart view")
    if not _switch_to_stock(dut):
        skip("T184", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=3.0)
    time.sleep(0.3)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T184", "could not enter chart view")
        _restore_from_stock(dut)
        return
    dut.cmd("set fetchFailed 1", timeout=3.0)
    time.sleep(0.15)
    # Back button must still work even when fetchFailed.
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)
    time.sleep(0.2)
    r_sv = _stock_get(dut, "stockSubView")
    dut.cmd("set fetchFailed 0", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv.get("val") != "list":
        fail("T184", f"stockSubView={r_sv.get('val')!r} after back tap while fetchFailed — expected list")
        return
    pass_("T184", "back tap works while fetchFailed=1 in chart view; returned to list")


# ── T231 — Settings → Stock "mode" launch view (TASK-231) ─────────────────────

def _enter_stock_no_force(dut: Dut, timeout: float = 5.0) -> bool:
    """switchApp → Stock WITHOUT forcing stockMode (unlike _switch_to_stock, which
    pins mode 0). Lets resume()/_applyLaunchView() honour the mode set just prior."""
    r = dut.cmd(f"switchApp {APP_SLOT['Stock']}", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.4)  # let resume() → _applyLaunchView() run + first paint
    try:
        return dut.get_str("appId", field="name", timeout=timeout) == "Stock"
    except DeviceReadError:
        return False


def t231(dut: Dut):
    """T231: Settings → Stock "mode" (List/Chart/Heatmap) is honoured at launch.

    Regression for the wired-up _applyLaunchView() (was: init() hardcoded List, so
    the Settings toggle did nothing). Drives stockMode 1/2/0 then re-enters Stock
    and asserts the launch sub-view. Also asserts the launch-into-Chart symbol is
    non-empty (the original concern: Chart launched with an empty ticker) and that
    List is the back-navigation base for both detail views. No Spotify/network
    needed — switchApp + in-RAM stockMode only. TASK-231 / BP-034.
    """
    tid = "T231"
    print(f"{tid}  Settings → Stock mode launch view (List/Chart/Heatmap)")

    # Clean List baseline (this also init()s the app and sets _appliedMode=List).
    if not _switch_to_stock(dut):
        skip(tid, "could not switch to Stock for baseline")
        _restore_from_stock(dut)
        return

    # ── Chart launch ──────────────────────────────────────────────────────────
    _restore_from_stock(dut)                     # leave on List → go to Spotify
    dut.cmd("set stockMode 1", timeout=3.0)      # Chart
    if not _enter_stock_no_force(dut):
        fail(tid, "switchApp Stock failed (Chart case)")
        return
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "chart":
        fail(tid, f"stockMode=Chart but launched stockSubView={sv!r} (expected chart)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    tk = dut.get_str("stockChartTicker")
    if not tk:
        fail(tid, "Chart launched with EMPTY ticker — drillToChart(0) precondition not met")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] Chart launch ✓ (ticker={tk!r})")
    # back-nav base must be List
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)             # chart back zone
    time.sleep(0.25)
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "list":
        fail(tid, f"Chart back-nav base = {sv!r} (expected list)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] Chart → back → list ✓")

    # ── Heatmap launch ────────────────────────────────────────────────────────
    _restore_from_stock(dut)                     # leave on List
    dut.cmd("set stockMode 2", timeout=3.0)      # Heatmap
    if not _enter_stock_no_force(dut):
        fail(tid, "switchApp Stock failed (Heatmap case)")
        return
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "heatmap":
        fail(tid, f"stockMode=Heatmap but launched stockSubView={sv!r} (expected heatmap)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] Heatmap launch ✓")
    dut.set_cooldown_zero()
    dut.cmd("tap 260 7", timeout=3.0)            # heatmap back zone (x>190, y<ST_LIST_RULE_Y=22)
    time.sleep(0.25)
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "list":
        fail(tid, f"Heatmap back-nav base = {sv!r} (expected list)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] Heatmap → back → list ✓")

    # ── List launch (explicit, no-op default) ─────────────────────────────────
    _restore_from_stock(dut)
    dut.cmd("set stockMode 0", timeout=3.0)      # List
    if not _enter_stock_no_force(dut):
        fail(tid, "switchApp Stock failed (List case)")
        return
    sv = _stock_get(dut, "stockSubView").get("val")
    if sv != "list":
        fail(tid, f"stockMode=List but launched stockSubView={sv!r} (expected list)")
        _restore_from_stock(dut); dut.cmd("set stockMode 0", timeout=3.0)
        return
    print(f"  [T231] List launch ✓")

    # Restore default + leave Stock.
    dut.cmd("set stockMode 0", timeout=3.0)
    _restore_from_stock(dut)
    pass_(tid, "stockMode honoured at launch: Chart(ticker set)/Heatmap/List; List is back-nav base")




# ── T186–T188 — M-DATATASK-STREAM-PARSE regression suite ─────────────────────
#
# T186: MSFT (tickerIdx=6) chart fetch succeeds after tickerIdx >= 8 guard fix.
# T187: NVDA (tickerIdx=7) same.
# T188: Cycling all four range tabs fetches without -99 NET ERR (getStream fix).
#
# Row centres (x=137): AAPL=36, AMD=62, AMZN=88, ARM=114,
#                       GOOG=140, META=166, MSFT=192, NVDA=218
# Tab centres (x): D1=148, D5=184, Mo1=220, Ytd=256  (all y=9)
_TAB_XY    = [(148, 9), (184, 9), (220, 9), (256, 9)]
_TAB_NAMES = ["D1", "D5", "Mo1", "Ytd"]


def _t18x_guard(dut: Dut, tid: str, ticker: str, row_y: int):
    """Shared body for T186/T187: verify tickerIdx guard fix allows ticker to fetch."""
    if not _switch_to_stock(dut):
        skip(tid, "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=5.0)   # back to list
        time.sleep(0.3)
    dut.cmd("set fetchFailed 0", timeout=3.0)
    dut.cmd("set fetchErrorCode 0", timeout=3.0)
    # Drill into ticker row — triggers enqueue via drillToChart().
    dut.set_cooldown_zero()
    dut.cmd(f"tap 137 {row_y}", timeout=5.0)
    time.sleep(0.5)
    r_sv = _stock_get(dut, "stockSubView")
    if r_sv.get("val") != "chart":
        skip(tid, f"drill-in did not enter chart view (subView={r_sv.get('val')!r})")
        _restore_from_stock(dut)
        return
    r_tk = _stock_get(dut, "stockChartTicker")
    if r_tk.get("val") != ticker:
        fail(tid, f"stockChartTicker={r_tk.get('val')!r} — expected {ticker}")
        _restore_from_stock(dut)
        return
    # Snapshot ok count, trigger fetch, wait for proven completion (LL-041).
    before = _stock_ok_count(dut)
    dut.cmd("set triggerFetch 1", timeout=3.0)
    print(f"  [{tid}] fetch triggered (fetchOkCount={before}); waiting for completion…", flush=True)
    if not _wait_chart_complete(dut, before, timeout_s=45.0):
        _restore_from_stock(dut)
        fail(tid, f"fetchOkCount did not advance after 45 s for {ticker} — guard fix may not have landed")
        return
    r_ff   = _stock_get(dut, "fetchFailed")
    r_code = _stock_get(dut, "fetchErrorCode")
    _restore_from_stock(dut)
    if r_ff.get("val") == "1" or r_ff.get("val") is True:
        fail(tid, f"fetchFailed=1 errorCode={r_code.get('val')} for {ticker}")
        return
    pass_(tid, f"{ticker} chart fetch completed; fetchOkCount advanced")


def t186(dut: Dut):
    """T186: MSFT (tickerIdx=6) chart fetch succeeds after tickerIdx >= 8 guard fix."""
    print("T186  MSFT guard fix — tickerIdx=6 chart fetch")
    _t18x_guard(dut, "T186", "MSFT", 192)


def t187(dut: Dut):
    """T187: NVDA (tickerIdx=7) chart fetch succeeds after tickerIdx >= 8 guard fix."""
    print("T187  NVDA guard fix — tickerIdx=7 chart fetch")
    _t18x_guard(dut, "T187", "NVDA", 218)


def t188(dut: Dut):
    """T188: cycling all four range tabs fetches without -99 (getStream() fix, ADR-034)."""
    print("T188  Range-cycle no-99 regression (ADR-034 getStream fix)", flush=True)
    if not _switch_to_stock(dut):
        skip("T188", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Clear any leftover error state from prior tests.
    dut.cmd("set fetchFailed 0", timeout=3.0)
    dut.cmd("set fetchErrorCode 0", timeout=3.0)
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=5.0)
        time.sleep(0.5)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=5.0)   # drill AAPL
    time.sleep(1.0)                       # allow chart render before checking
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T188", "could not drill into chart view")
        _restore_from_stock(dut)
        return

    # Use tab taps (not triggerFetch) — tab taps only enqueue DATA_FETCH_STOCK_CHART.
    # triggerFetch also resets lastQuoteFetch, triggering an 8-ticker quote fetch
    # in parallel that can take 60 s+, causing serial timeouts mid-test.
    #
    # Pattern (LL-041): snapshot fetchOkCount before tap → tap → wait for count to
    # advance → proven completion, not a blind sleep. Queue depth is irrelevant
    # because we observe the counter, not the number of taps fired.

    for tab_idx, (tx, ty) in enumerate(_TAB_XY):
        tab_name = _TAB_NAMES[tab_idx]
        before = _stock_ok_count(dut)
        dut.set_cooldown_zero()
        dut.cmd(f"tap {tx} {ty}", timeout=5.0)
        print(f"  [T188] {tab_name} tapped (fetchOkCount={before}); waiting for completion…", flush=True)
        if not _wait_chart_complete(dut, before, timeout_s=45.0):
            r_ff   = _stock_get(dut, "fetchFailed",    timeout=3.0)
            r_code = _stock_get(dut, "fetchErrorCode", timeout=3.0)
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T188", f"fetchOkCount did not advance on {tab_name} — "
                         f"fetchFailed={r_ff.get('val')!r} fetchErrorCode={r_code.get('val')!r}")
            return
        r_ff   = _stock_get(dut, "fetchFailed", timeout=8.0)
        r_code = _stock_get(dut, "fetchErrorCode", timeout=8.0)
        if r_ff.get("val") == "1" or r_ff.get("val") is True:
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T188", f"fetchFailed=1 errorCode={r_code.get('val')} on range {tab_name}")
            return
        print(f"  [T188] {tab_name} ok", flush=True)

    _restore_from_stock(dut)
    pass_("T188", "all 4 ranges (D1/D5/Mo1/Ytd) fetched without -99 — getStream() fix confirmed")


# ── T204 — M-STOCK-VE-STRESS: D1↔Ytd rapid alternating stress ────────────────
# Step 2 of M-STOCK-VE-STRESS. T188 verified each range sequentially; T204 drives
# D1↔Ytd alternation (3 cycles = 6 fetches) to exercise back-to-back
# DynamicJsonDocument(16384) alloc/free under heap pressure (ADR-034).
# Counter observation between taps proves queue drains — no blind sleeps.

def t204(dut: Dut):
    """T204: D1↔Ytd rapid alternating stress — back-to-back alloc/free under heap pressure."""
    print("T204  D1↔Ytd rapid alternating stress (M-STOCK-VE-STRESS)", flush=True)
    # TASK-386: entry baseline. Unlike T193, T204 self-induces heap pressure via its own
    # 6 rapid back-to-back fetches — but its *starting* fragmentation still depends on
    # whatever ~150 prior tests in a full-suite run left behind, so this baseline still
    # matters for comparing an isolated run/test-targeted repro against a real suite run.
    entry_diag = _diag_snapshot(dut, "T204-entry")
    if not _switch_to_stock(dut):
        skip("T204", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    dut.cmd("set fetchFailed 0", timeout=3.0)
    dut.cmd("set fetchErrorCode 0", timeout=3.0)
    if _stock_get(dut, "stockSubView").get("val") == "chart":
        dut.set_cooldown_zero()
        dut.cmd("tap 10 7", timeout=5.0)   # back to list
        time.sleep(0.5)
    dut.set_cooldown_zero()
    dut.cmd("tap 137 36", timeout=5.0)     # drill AAPL
    time.sleep(1.0)
    if _stock_get(dut, "stockSubView").get("val") != "chart":
        skip("T204", "could not drill into chart view")
        _restore_from_stock(dut)
        return

    stress_tabs = [(_TAB_XY[3], "Ytd"), (_TAB_XY[0], "D1")] * 3  # 3 cycles, 6 taps

    for i, ((tx, ty), tab_name) in enumerate(stress_tabs, start=1):
        before = _stock_ok_count(dut)
        # TASK-386: snapshot before every tap, not just on failure — the heap-pressure
        # hypothesis is specifically about a *trend* across the 6-fetch cycle (freeInt/
        # lfbInt shrinking cycle over cycle), which a single failure-point snapshot can't
        # show. Cheap (3 `get`s) relative to the ~2.9s fetch itself.
        pre_diag = _diag_snapshot(dut, f"T204-pre-{i}-{tab_name}")
        dut.set_cooldown_zero()
        dut.cmd(f"tap {tx} {ty}", timeout=5.0)
        print(f"  [T204] {tab_name} tapped (fetchOkCount={before}); waiting…", flush=True)
        if not _wait_chart_complete(dut, before, timeout_s=45.0, test_id="T204"):
            timeout_diag = _diag_snapshot(dut, f"T204-timeout-{i}-{tab_name}")
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T204", f"fetchOkCount did not advance on {tab_name} (cycle {i}/6) — heap "
                          f"pressure failure? | entry={entry_diag} | pre-tap={pre_diag} | "
                          f"timeout={timeout_diag}")
            return
        r_ff   = _stock_get(dut, "fetchFailed", timeout=8.0)
        r_code = _stock_get(dut, "fetchErrorCode", timeout=8.0)
        if r_ff.get("val") == "1" or r_ff.get("val") is True:
            post_diag = _diag_snapshot(dut, f"T204-fail-{i}-{tab_name}")
            dut.cmd("set fetchFailed 0", timeout=3.0)
            dut.cmd("set fetchErrorCode 0", timeout=3.0)
            _restore_from_stock(dut)
            fail("T204", f"fetchFailed=1 errorCode={r_code.get('val')} on {tab_name} (cycle "
                          f"{i}/6) — alloc/free stress failure | entry={entry_diag} | "
                          f"pre-tap={pre_diag} | post={post_diag}")
            return
        print(f"  [T204] {tab_name} ok", flush=True)

    _restore_from_stock(dut)
    pass_("T204", "D1↔Ytd × 3 cycles — no fetchFailed; getStream() alloc/free stable under stress")


# ── stock-002 (TASK-120): heatmap sub-view, navigation, fetch-gate, chartSymbol guard ──

def _wait_heatmap_count(dut: Dut, timeout_s: float = 60.0) -> int:
    """Poll get heatmapCount until > 0. Returns count (0 on timeout).

    TASK-596: `0` is still the timeout return, and that is DELIBERATE and safe
    here in a way `_stock_ok_count`'s `-1` was not — every caller treats 0 as
    "no heatmap", i.e. the failing direction, so a conflated sentinel cannot
    manufacture a pass. What changed is the read: an unanswered poll no longer
    reads as `val=0` mid-loop, and a renamed key now raises instead of spending
    60 s pretending to poll.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            val = dut.get_int("heatmapCount", timeout=3.0)
            if val > 0:
                return val
        except NoAnswer:
            pass
        time.sleep(3.0)
    # TASK-386: same treatment as _wait_chart_complete — automatic for every caller.
    _diag_snapshot(dut, "_wait_heatmap_count-timeout")
    return 0


def _ensure_stock_list_view(dut: Dut) -> bool:
    """After switchApp to Stock, normalize to ListDetail sub-view.
    Handles leftover state from previous tests (heatmap or chart sub-view).
    Returns True if ListDetail confirmed."""
    for _ in range(3):
        try:
            sv = dut.get_str("stockSubView", timeout=3.0)
        except NoAnswer:
            time.sleep(0.3)
            continue
        if sv == "list":
            return True
        if sv == "chart":
            # Chart may have pending fetch; wait for shellBusy to clear first
            _wait_shell_not_busy(dut, timeout_s=45.0)
            time.sleep(0.1)
            dut.set_cooldown_zero()
            dut.cmd("tap 10 7", timeout=3.0)  # chart back button
        elif sv == "heatmap":
            dut.set_cooldown_zero()
            dut.cmd("tap 220 10", timeout=3.0)  # HEAT toggle → list
        time.sleep(0.3)
    return dut.cmd("get stockSubView", timeout=3.0).get("val") == "list"


# ── T196 — Heatmap fetch completes; triggerHeatmap sets sub-view ──────────────

def t196(dut: Dut):
    """T196: triggerHeatmap → subView=heatmap; heatmapCount > 0 within 60 s."""
    print("T196  Heatmap data present after fetch")
    if not _switch_to_stock(dut):
        skip("T196", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
    if not r.get("ok"):
        fail("T196", "set triggerHeatmap 1 returned error")
        _restore_from_stock(dut)
        return
    time.sleep(0.3)
    r_sv = dut.cmd("get stockSubView", timeout=3.0)
    if r_sv.get("val") != "heatmap":
        fail("T196", f"stockSubView={r_sv.get('val')!r} after triggerHeatmap — expected 'heatmap'")
        _restore_from_stock(dut)
        return
    count = _wait_heatmap_count(dut, timeout_s=60.0)
    _restore_from_stock(dut)
    if count == 0:
        fail("T196", "heatmapCount still 0 after 60 s — screener fetch did not complete")
        return
    pass_("T196", f"heatmapCount={count}; subView=heatmap confirmed; fetch complete")


# ── T200 — List→Heatmap toggle via HEAT tap ───────────────────────────────────

def t200(dut: Dut):
    """T200: HEAT tap (x>190, y<22) in list view → subView switches to heatmap."""
    print("T200  List→Heatmap toggle via HEAT tap")
    if not _switch_to_stock(dut):
        skip("T200", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T200", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 220 10", timeout=3.0)
    time.sleep(0.3)
    r_sv2 = dut.cmd("get stockSubView", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv2.get("val") != "heatmap":
        fail("T200", f"stockSubView={r_sv2.get('val')!r} after HEAT tap — expected 'heatmap'")
        return
    pass_("T200", "HEAT tap in list → subView=heatmap confirmed")


# ── T201 — Heatmap→List back toggle via HEAT tap ──────────────────────────────

def t201(dut: Dut):
    """T201: HEAT tap (x>190, y<22) in heatmap view → subView returns to list."""
    print("T201  Heatmap→List back toggle via HEAT tap")
    if not _switch_to_stock(dut):
        skip("T201", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    # Normalize to list first so prevSubView is correctly set to List
    if not _ensure_stock_list_view(dut):
        skip("T201", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
    if not r.get("ok"):
        skip("T201", "set triggerHeatmap 1 failed")
        _restore_from_stock(dut)
        return
    time.sleep(0.5)  # allow repaintHeatmap to finish before querying
    r_sv_pre = dut.cmd("get stockSubView", timeout=5.0)
    if r_sv_pre.get("val") != "heatmap":
        skip("T201", f"stockSubView={r_sv_pre.get('val')!r} after triggerHeatmap — expected 'heatmap'")
        _restore_from_stock(dut)
        return
    dut.set_cooldown_zero()
    dut.cmd("tap 220 10", timeout=3.0)
    time.sleep(0.3)
    r_sv = dut.cmd("get stockSubView", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv.get("val") != "list":
        fail("T201", f"stockSubView={r_sv.get('val')!r} after HEAT tap in heatmap — expected 'list'")
        return
    pass_("T201", "HEAT tap in heatmap → subView=list (back) confirmed")


# ── T202 — Heatmap tile tap drills to ChartDetail ─────────────────────────────

def t202(dut: Dut):
    """T202: Tap canvas centre in heatmap (tile area) → drills to ChartDetail."""
    print("T202  Heatmap tile tap drills to chart")
    if not _switch_to_stock(dut):
        skip("T202", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T202", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap when cache is present — avoids re-fetching and re-fetch failures
    if _wait_heatmap_count(dut, timeout_s=10.0) == 0:
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T202", "set triggerHeatmap 1 failed (no cached heatmap)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T202", "heatmapCount still 0 after 60 s — no tiles to tap")
            _restore_from_stock(dut)
            return
        time.sleep(2.0)  # let heatmap render after first fetch
    else:
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT tap → heatmap (no new fetch)
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T202", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    time.sleep(0.3)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of canvas — always in largest tile
    time.sleep(0.5)
    r_sv = dut.cmd("get stockSubView", timeout=3.0)
    if r_sv.get("val") != "chart":
        _restore_from_stock(dut)
        fail("T202", f"stockSubView={r_sv.get('val')!r} after tile tap — expected 'chart'")
        return
    drilled = dut.get_str("stockChartTicker")
    _restore_from_stock(dut)
    pass_("T202", f"tile tap → ChartDetail; drilled symbol={drilled!r}")


# ── T203 — Chart back from heatmap drill restores HeatmapDetail ───────────────

def t203(dut: Dut):
    """T203: Back tap from chart (entered via heatmap drill) → restores HeatmapDetail, not List."""
    print("T203  Chart back from heatmap drill restores HeatmapDetail")
    if not _switch_to_stock(dut):
        skip("T203", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T203", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap when cache is present — avoids re-fetching and re-fetch failures
    if _wait_heatmap_count(dut, timeout_s=10.0) == 0:
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T203", "set triggerHeatmap 1 failed (no cached heatmap)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T203", "heatmapCount still 0 after 60 s — no tiles")
            _restore_from_stock(dut)
            return
        time.sleep(2.0)
    else:
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT tap → heatmap (no new fetch)
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T203", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    time.sleep(0.3)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of canvas — always in largest tile
    time.sleep(0.5)
    if dut.cmd("get stockSubView", timeout=3.0).get("val") != "chart":
        skip("T203", "could not drill to chart from heatmap tile tap")
        _restore_from_stock(dut)
        return
    # Wait for chart fetch to complete (g_shellBusy clears) before back tap
    if not _wait_shell_not_busy(dut, timeout_s=45.0):
        skip("T203", "shellBusy did not clear after tile drill — chart fetch stuck?")
        _restore_from_stock(dut)
        return
    time.sleep(0.1)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 7", timeout=3.0)
    time.sleep(0.3)
    r_sv = dut.cmd("get stockSubView", timeout=3.0)
    _restore_from_stock(dut)
    if r_sv.get("val") != "heatmap":
        fail("T203", f"stockSubView={r_sv.get('val')!r} after chart back — expected 'heatmap'")
        return
    pass_("T203", "chart back → subView=heatmap (prevSubView preserved correctly)")


# ── T192 — Tab-switch after heatmap drill uses drilled symbol ─────────────────

def t192(dut: Dut):
    """T192: After heatmap drill, range tab-switch fetches the drilled symbol (TASK-121 fix)."""
    print("T192  Tab-switch after heatmap drill uses drilled symbol")
    if not _switch_to_stock(dut):
        skip("T192", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T192", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap when cache is available to avoid queueing a new screener fetch
    if _wait_heatmap_count(dut, timeout_s=3.0) == 0:
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T192", "set triggerHeatmap 1 failed (no cached heatmap data)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T192", "heatmapCount still 0 after 60 s")
            _restore_from_stock(dut)
            return
        time.sleep(2.0)
    else:
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT tap → heatmap (no new fetch)
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T192", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    # Wait for any in-progress heatmap layout recompute/repaint (cache-expiry re-fetch) to settle
    time.sleep(0.5)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of heatmap canvas — always in the largest tile
    time.sleep(0.5)
    if dut.cmd("get stockSubView", timeout=3.0).get("val") != "chart":
        skip("T192", "could not drill to chart from heatmap")
        _restore_from_stock(dut)
        return
    # TASK-596: `"?"` on BOTH sides of the later `after_sym != drilled` comparison
    # made two failed reads compare EQUAL — the same defaulted-to-pass shape as
    # `G-2`, in the term the audit graded as merely tautological.
    drilled = dut.get_str("stockChartTicker")
    # Wait for D1 chart fetch to complete before tab-switching (clears g_shellBusy)
    if not _wait_shell_not_busy(dut, timeout_s=45.0):
        skip("T192", "shellBusy did not clear after tile drill — chart fetch stuck?")
        _restore_from_stock(dut)
        return
    before_ok = _stock_ok_count(dut)
    time.sleep(0.1)
    dut.set_cooldown_zero()
    dut.cmd("tap 184 9", timeout=3.0)  # 5D tab
    time.sleep(0.3)
    r_range = dut.cmd("get stockChartRange", timeout=3.0)
    if r_range.get("val") != "D5":
        skip("T192", f"stockChartRange={r_range.get('val')!r} after 5D tap — tab not registered")
        _restore_from_stock(dut)
        return
    if not _wait_chart_complete(dut, before_ok, timeout_s=45.0):
        fail("T192", "fetchOkCount did not advance after tab-switch — TASK-121 fix may be missing")
        _restore_from_stock(dut)
        return
    after_sym = dut.get_str("stockChartTicker")
    _restore_from_stock(dut)
    if after_sym != drilled:
        fail("T192", f"chart ticker changed: {drilled!r} → {after_sym!r} after tab-switch")
        return
    pass_("T192", f"drilled={drilled!r}; 5D tab-switch fired fetch; ticker unchanged")


# ── T193 — Auto-refresh path uses drilled symbol ──────────────────────────────

def t193(dut: Dut):
    """T193: stockTickChart() auto-refresh uses chartSymbol after heatmap drill (TASK-121b fix)."""
    print("T193  Auto-refresh path uses drilled symbol")
    # TASK-385: baseline snapshot at test entry. In a full `run/test` pass this runs after
    # ~150 prior tests with no reboot in between; in an isolated `run/test-targeted T193`
    # rerun it runs 2-3 min post-boot. Comparing this line's heap/dataq/backoff numbers
    # across the two contexts is the whole point — see _diag_snapshot's docstring.
    entry_diag = _diag_snapshot(dut, "T193-entry")
    if not _switch_to_stock(dut):
        skip("T193", "could not switch to Stock")
        _restore_from_stock(dut)
        return
    if not _ensure_stock_list_view(dut):
        skip("T193", "could not normalize to list view")
        _restore_from_stock(dut)
        return
    # Use HEAT tap (not triggerHeatmap) to enter heatmap — enterHeatmap() only fetches if
    # lastHeatmapFetch==0, so re-using cached data avoids queuing a new screener fetch that
    # would block the dataTask queue and starve the subsequent chart fetch (LL-T193-001).
    # Use 10 s deadline so a transient serial flood (stockTickQuotes HTTP) doesn't drop us
    # into the triggerHeatmap branch on the very first check attempt.
    if _wait_heatmap_count(dut, timeout_s=10.0) == 0:
        # No cached data yet — fall back to triggerHeatmap and wait for fetch
        r = dut.cmd("set triggerHeatmap 1", timeout=3.0)
        if not r.get("ok"):
            skip("T193", "set triggerHeatmap 1 failed (no cached heatmap data)")
            _restore_from_stock(dut)
            return
        if _wait_heatmap_count(dut, timeout_s=60.0) == 0:
            skip("T193", "heatmapCount still 0 after 60 s")
            _restore_from_stock(dut)
            return
        # Flush the heatmap result from the dataTask queue before drilling to chart
        time.sleep(2.0)  # allow pollHeatmapQuote to run in stockTickHeatmap tick
    else:
        # Cached data present — HEAT tap enters heatmap without queuing a screener fetch
        dut.set_cooldown_zero()
        dut.cmd("tap 220 10", timeout=3.0)  # HEAT button in list header
        time.sleep(0.3)
        if dut.cmd("get stockSubView", timeout=3.0).get("val") != "heatmap":
            skip("T193", "HEAT tap did not enter heatmap")
            _restore_from_stock(dut)
            return
    time.sleep(0.5)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.set_cooldown_zero()
    dut.cmd("tap 10 30", timeout=3.0)  # top-left of canvas — always in largest tile
    time.sleep(0.5)
    if dut.cmd("get stockSubView", timeout=3.0).get("val") != "chart":
        skip("T193", "could not drill to chart from heatmap")
        _restore_from_stock(dut)
        return
    # TASK-596: `"?"` on BOTH sides of the later `after_sym != drilled` comparison
    # made two failed reads compare EQUAL — the same defaulted-to-pass shape as
    # `G-2`, in the term the audit graded as merely tautological.
    drilled = dut.get_str("stockChartTicker")
    # Wait for initial D1 fetch to complete (clears shellBusy), then force re-fetch
    if not _wait_shell_not_busy(dut, timeout_s=45.0):
        skip("T193", "shellBusy did not clear after tile drill")
        _restore_from_stock(dut)
        return
    before_ok = _stock_ok_count(dut)
    # TASK-385: snapshot immediately before the risky trigger — this is the state the
    # forced re-fetch actually has to run against (post-heatmap-drill, post-tile-drill).
    pre_diag = _diag_snapshot(dut, "T193-pre-trigger")
    dut.cmd("set triggerFetch 1", timeout=3.0)  # reset lastChartFetch → force next tick re-fetch
    if not _wait_chart_complete(dut, before_ok, timeout_s=45.0, test_id="T193"):
        # TASK-385: on timeout, one more snapshot at the point of failure. Embedded
        # directly in the fail() reason (not just printed) so it survives even without
        # LOG_FILE= capture — the original 2026-08-01 filing had neither.
        timeout_diag = _diag_snapshot(dut, "T193-timeout")
        fail("T193", "fetchOkCount did not advance after triggerFetch — auto-refresh did not "
                      f"fire | entry={entry_diag} | pre-trigger={pre_diag} | timeout={timeout_diag}")
        _restore_from_stock(dut)
        return
    after_sym = dut.get_str("stockChartTicker")
    chart_len = dut.get_int("chartLen")
    _restore_from_stock(dut)
    if after_sym != drilled:
        fail("T193", f"chart ticker changed after auto-refresh: {drilled!r} → {after_sym!r}")
        return
    if chart_len <= 0:
        skip("T193", f"chartLen={chart_len} after auto-refresh — Yahoo returned empty data (external API flakiness)")
        return
    pass_("T193", f"drilled={drilled!r}; auto-refresh fetched same symbol; chartLen={chart_len}")


# ── T_SQI_01 — Stock quote fetch completes with Spotify provably idle ───────
# TASK-705 primitive: stock_quote_fetch (O8's idle half). T170 already proves
# the fetch completes; this id additionally holds Spotify idle for the WHOLE
# wait via `_bgpoll_suspended` (bgPoll=0, the same custody helper T084/T169
# use) so the completion is observed with Spotify's own background poll
# provably out of the picture — TASK-697's reading is that Spotify BUSY, not
# idle, is what starves this path, so this id is the idle control.

@meta(ops=("stock_quote_fetch",))
def t_sqi_01(dut: Dut):
    """T_SQI_01: Stock quoteOkCount advances within 65s with Spotify's
    background poll held off the whole time. TASK-705 primitive:
    stock_quote_fetch."""
    print("T_SQI_01  Quote fetch completes, Spotify provably idle")
    with _bgpoll_suspended(dut):
        if not _switch_to_stock(dut):
            unmet("T_SQI_01", "could not switch to Stock")
            _restore_from_stock(dut)
            return
        try:
            before = _stock_quote_ok_count(dut)
        except DeviceReadError:
            _restore_from_stock(dut)
            raise
        deadline = time.monotonic() + 65.0
        advanced = False
        while time.monotonic() < deadline:
            if _stock_quote_ok_count(dut) > before:
                advanced = True
                break
            time.sleep(2.0)
        _restore_from_stock(dut)
    if not advanced:
        fail("T_SQI_01", f"quoteOkCount did not advance past {before} within "
                         "65s with Spotify bgPoll held off the whole time")
        return
    pass_("T_SQI_01", f"quoteOkCount advanced past {before} — quote fetch "
                      "completed with Spotify provably idle")


TESTS = {
    "T169": t169,
    "T170": t170,
    "T172": t172,
    "T173": t173,
    "T174": t174,
    "T175": t175,
    "T176": t176,
    "T177": t177,
    "T180": t180,
    "T181": t181,
    "T182": t182,
    "T183": t183,
    "T184": t184,
    "T231": t231,
    "T186": t186,
    "T187": t187,
    "T188": t188,
    "T204": t204,
    "T196": t196,
    "T200": t200,
    "T201": t201,
    "T202": t202,
    "T203": t203,
    "T192": t192,
    "T193": t193,
    "T_DTP_01": t_dtp_01,
    "T_DTP_02": t_dtp_02,
    "T_SQI_01": t_sqi_01,
}
