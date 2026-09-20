"""Teletext app tests -- M-TELETEXT (TASK-191/197). Split from
run_serialdbg_tests.py, TASK-480."""

import time

import coords as _c
from lib.dut import TIMEOUT, Dut
from lib.results import pass_, fail, skip
from app_ids_gen import APP_SLOT
from suite.serialdbg._helpers import _restore_spotify, _switch_to, _wait_shell_not_busy


# ── T272 — TLS heap contention: fetchTeletext + spotifyTask concurrent ────────

def t272(dut: Dut):
    """T272: fetchTeletext completes without OOM while spotifyTask holds a TLS session.

    ADR-044 item 9 asserts teletext follows the weather pattern (no tlsYield). This
    test exercises both tasks concurrently to validate that assumption. Failure (timeout
    or DUT crash) indicates heap contention → apply tlsYield/tlsResume to fetchTeletext.
    TASK-191.
    """
    tid = "T272"
    print(f"{tid}  TLS heap contention — fetchTeletext concurrent with spotifyTask")

    # Baseline: confirm Spotify is rendering (spotifyTask has an active TLS session)
    r0 = dut.cmd("get lastPlaylistDraw", timeout=TIMEOUT)
    if not r0.get("ok"):
        skip(tid, "get lastPlaylistDraw failed — Spotify not active?")
        return
    draw0 = r0.get("ms", 0)

    # Switch to Teletext: triggers resume() which sets _lastFetch=0, forcing immediate enqueue
    r = dut.cmd(f"switchApp {APP_SLOT['Teletext']}", timeout=5.0)
    if not r.get("ok"):
        skip(tid, "switchApp Teletext failed — app not registered?")
        _restore_spotify(dut)
        return

    # Force a second enqueue in case the app was already ready from a prior run
    dut.cmd("set triggerTeletextFetch 1", timeout=TIMEOUT)

    # Poll teletextReady up to 30s — failure implies OOM/watchdog/network error
    deadline = time.monotonic() + 30.0
    ready = False
    while time.monotonic() < deadline:
        try:
            r = dut.cmd("get teletextReady", timeout=2.0)
            if r.get("ok") and r.get("ready") is True:
                ready = True
                break
        except TimeoutError:
            break  # DUT stopped responding — likely crash
        time.sleep(0.5)

    _restore_spotify(dut)
    time.sleep(0.3)

    if not ready:
        # Distinguish network failure from firmware crash
        try:
            r_http = dut.cmd("get teletextHttpCode", timeout=2.0)
            http_code = r_http.get("val", 0) if r_http.get("ok") else 0
        except TimeoutError:
            http_code = 0
        if http_code != 0 and http_code != 200:
            skip(tid, f"teletextReady false — HTTP {http_code} (network, not contention)")
        else:
            fail(tid, "teletextReady not true within 30s — OOM/watchdog/crash or persistent network error")
        return

    # Assert Spotify playback survived (lastPlaylistDraw must advance within 10s)
    deadline2 = time.monotonic() + 10.0
    draw_advanced = False
    while time.monotonic() < deadline2:
        try:
            r = dut.cmd("get lastPlaylistDraw", timeout=2.0)
            if r.get("ok") and r.get("ms", 0) > draw0:
                draw_advanced = True
                break
        except TimeoutError:
            break
        time.sleep(0.5)

    if not draw_advanced:
        fail(tid, f"lastPlaylistDraw did not advance after Teletext fetch (baseline={draw0}ms) — Spotify stalled")
        return

    pass_(tid, "teletextReady=true within 30s; lastPlaylistDraw advanced — no TLS contention")


# ── T270 — Synthetic subpage navigation (TASK-197) ────────────────────────────

def t270(dut: Dut):
    """T270-SYN: SUBDN tap enqueues subpage fetch when subpageNext is set.

    Sets subpageNext=617-2 via debug command. Taps SUBDN zone centre
    (coords.ttxt_subdn_centre(), derived from app/gen/teletext_layout.h —
    TASK-715, was a hand-computed y=182 literal);
    asserts teletextLastAction==STRIP_SUBDN and shellBusy fires (confirming
    _navigate(617,2) was called). No live network required. Replaces
    [NETWORK][Blocked: G1,G2] variant. TASK-197 / BP-034.
    """
    tid = "T270"
    print(f"{tid}  Subpage ▼ zone → STRIP_SUBDN + busy (synthetic)")

    if not _switch_to(dut, "Teletext"):
        skip(tid, "could not switch to TeletextApp")
        return

    # Wait for any pending fetch from resume() to settle
    _wait_shell_not_busy(dut, timeout_s=8.0)
    dut.cmd("set cooldown 0", timeout=2.0)

    # Set subpage navigation targets via debug injection. Both are write-only
    # (no per-var read-back — only the combined `get teletextSubpage` exists),
    # so they go through `injected()` rather than `saved()`. "0" clears
    # (teletextApp.cpp:239/248), which is the firmware fact `clear_to` states.
    with dut.injected("teletextSubpageNext", "617-2", clear_to="0", timeout=2.0), \
         dut.injected("teletextSubpagePrev", "617-1", clear_to="0", timeout=2.0):
        # Confirm fields propagated
        r_sp = dut.cmd("get teletextSubpage", timeout=2.0)
        if not r_sp.get("ok") or r_sp.get("next", 0) != 617 or r_sp.get("nextSub", 0) != 2:
            fail(tid, f"subpageNext not set as expected: {r_sp}")
            return
        print(f"  [T270] subpageNext={r_sp.get('next')}-{r_sp.get('nextSub')} ✓")

        # Wait past app-level 300 ms debounce (inject is not a tap — _lastTapMs unchanged,
        # but resume() set it to 0 and millis()>300 at this point so first tap is free)
        time.sleep(0.1)

        # Tap SUBDN zone centre — coords.ttxt_subdn_centre() (TASK-715)
        subdn_y = _c.ttxt_subdn_centre()
        dut.cmd(f"tap 257 {subdn_y}", timeout=TIMEOUT)
        time.sleep(0.1)  # let action propagate

        r_act = dut.cmd("get teletextLastAction", timeout=2.0)
        action = r_act.get("val", "") if r_act.get("ok") else "<error>"
        if action != "STRIP_SUBDN":
            fail(tid, f"expected STRIP_SUBDN, got '{action}'")
            return
        print(f"  [T270] lastAction=STRIP_SUBDN ✓")

        r_busy = dut.cmd("get shellBusy", timeout=2.0)
        if not r_busy.get("ok") or not r_busy.get("busy", False):
            fail(tid, "shellBusy not true after SUBDN tap — _navigate() not called?")
            return
        print(f"  [T270] shellBusy=true ✓ (fetch enqueued for 617-2)")

        _wait_shell_not_busy(dut, timeout_s=8.0)
        pass_(tid, "STRIP_SUBDN routed correctly; shellBusy=true confirmed (no network required)")


# ── T271 — Strip zone 1-px boundary (TASK-197) ───────────────────────────────

def t271(dut: Dut):
    """T271: Right-strip pixel-exact zone boundaries PAGE_NUM/BACK/PREV_PAGE.

    Tap order: TTXT_STRIP_BACK_Y0, TTXT_STRIP_BACK_Y1, TTXT_STRIP_PREV_Y0,
    TTXT_STRIP_PAGE_Y1 (PAGE last) — parsed from app/gen/teletext_layout.h
    via coords.py (TASK-715, was hand literals 67/99/100/66). All BACK/PREV taps fire
    with numpad OFF, so _draw()/_drawNumpad() is not called and no SPI phantom
    touch is generated. PAGE is tapped last: its phantom (re-hits PAGE zone,
    STRIP_PAGE) matches the expected value, so order doesn't matter.
    _wait_shell_not_busy between steps handles any _goBack()/_navigate() that
    fires when histDepth or prevPage is non-zero from a prior test.
    No content injection needed. TASK-197 / BP-034.
    """
    tid = "T271"
    print(f"{tid}  Strip zone 1-px boundary — PAGE_NUM/BACK/PREV_PAGE")

    if not _switch_to(dut, "Teletext"):
        skip(tid, "could not switch to TeletextApp")
        return

    # Steps where numpad is OFF: BACK and PREV zones. No _draw() call →
    # no SPI phantom. _goBack() / _navigate() may fire (no-op or network);
    # _wait_shell_not_busy drains any resulting fetch before the next tap.
    steps_nav = [
        (_c.TTXT_STRIP_BACK_Y0, "STRIP_BACK", f"y={_c.TTXT_STRIP_BACK_Y0} → BACK zone first px"),
        (_c.TTXT_STRIP_BACK_Y1, "STRIP_BACK", f"y={_c.TTXT_STRIP_BACK_Y1} → BACK zone last px"),
        (_c.TTXT_STRIP_PREV_Y0, "STRIP_PREV", f"y={_c.TTXT_STRIP_PREV_Y0} → PREV_PAGE zone first px"),
    ]
    # PAGE zone last: _drawNumpad() fires, causing a phantom that also hits
    # PAGE zone → both real action and phantom are STRIP_PAGE → harmless.
    step_page = (_c.TTXT_STRIP_PAGE_Y1, "STRIP_PAGE", f"y={_c.TTXT_STRIP_PAGE_Y1} → PAGE_NUM zone last px")

    for y, expected, desc in steps_nav:
        _wait_shell_not_busy(dut, timeout_s=8.0)
        time.sleep(0.35)  # past 300 ms per-app debounce
        dut.cmd("set cooldown 0", timeout=2.0)
        dut.cmd(f"tap 257 {y}", timeout=TIMEOUT)
        r_act = dut.cmd("get teletextLastAction", timeout=2.0)
        action = r_act.get("val", "") if r_act.get("ok") else "<error>"
        if action != expected:
            fail(tid, f"{desc}: expected '{expected}', got '{action}'")
            return
        print(f"  [T271] {desc}: '{action}' ✓")

    # PAGE zone — last step
    _wait_shell_not_busy(dut, timeout_s=8.0)
    time.sleep(0.35)
    dut.cmd("set cooldown 0", timeout=2.0)
    y, expected, desc = step_page
    dut.cmd(f"tap 257 {y}", timeout=TIMEOUT)
    r_act = dut.cmd("get teletextLastAction", timeout=2.0)
    action = r_act.get("val", "") if r_act.get("ok") else "<error>"
    if action != expected:
        fail(tid, f"{desc}: expected '{expected}', got '{action}'")
        return
    print(f"  [T271] {desc}: '{action}' ✓")

    pass_(tid, "all 4 boundary taps matched expected zone actions")



TESTS = {
    "T272": t272,
    "T270": t270,
    "T271": t271,
}
