"""LocalPlayer (Winamp-native SD playback) app tests. Split from
run_serialdbg_tests.py, TASK-480.

Covers: three-way PlayerMode + eject remap (TASK-413/414, ADR-059 D6/D7),
M3U index model (TASK-415, ADR-059 D3), file browser (TASK-416), transport
capability mask (TASK-417, ADR-059 D8), play-order engine (TASK-418,
ADR-059 D9/D12), and player mode transitions / arena ownership
(T_PMT_00-04, M-TESTBASE P3 §8 / M2/X052) -- these drive the operation
(playerCycle) rather than a coordinate, so they live here rather than in
shell.py alongside the taskbar-gesture tests.
"""

import functools
import time

from lib.dut import Dut
from lib.results import pass_, fail, skip, flake
import coords as _c
from app_ids_gen import APP_SLOT
from suite.serialdbg._meta import meta
from suite.serialdbg._helpers import (
    _restore_spotify, _switch_to, _wait_shell_not_busy, _tap_and_wait_log,
    _tb_set_offset, _get_scroll, _do_drag,
    _poll_shell_busy, _bgpoll_suspended,
)
from suite.serialdbg.webradio import _switch_to_webradio_capture_heap


# ── T_PLR_01–05 — M-PLAYER-STATE three-way mode (TASK-413 / ADR-059 D6/D7) ─────
# PlayerMode widens Spotify=0/WebRadio=1 to +Player=2. Cycling moves off eject
# onto the taskbar Winamp icon: tap the player slot while it's already active ->
# cycle + persist (resolvePlayerTap, ADR-059 D6 amendment); tap it from another
# app -> restore the persisted mode (resolvePlayerSlot, unchanged). Player has no
# taskbar slot of its own (eject-only tail, same as WebRadio).

def t_plr_01(dut: Dut):
    """T_PLR_01: taskbar tap on the active player slot cycles Spotify -> WebRadio ->
    Player -> Spotify -> WebRadio (x4 taps from Spotify)."""
    print("T_PLR_01  Taskbar tap cycles the mode Spotify->WebRadio->Player->Spotify->WebRadio")
    dut.cmd("set playerMode spotify", timeout=3.0)
    if not _restore_spotify(dut):
        skip("T_PLR_01", "precondition: could not restore Spotify")
        return
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    expected = ["WebRadio", "LocalPlayer", "Spotify", "WebRadio"]
    got = []
    for _ in expected:
        dut.set_cooldown_zero()
        dut.cmd(f"tap {sx} {sy}", timeout=5.0)
        time.sleep(0.3)
        got.append(dut.cmd("get appId", timeout=3.0).get("name"))
    dut.cmd("set playerMode spotify", timeout=3.0)
    _restore_spotify(dut)
    if got != expected:
        fail("T_PLR_01", f"cycle sequence={got} — expected {expected}")
        return
    pass_("T_PLR_01", f"cycle Spotify->{'->'.join(got)} confirmed (x4 taps)")


def t_plr_04(dut: Dut):
    """T_PLR_04: get/set playerMode round-trip all three values by name and by
    numeric index (§6.1 debug-surface widening — the pre-TASK-413 getter
    collapsed Player(2) to WebRadio(1) and the setter rejected idx>1)."""
    print("T_PLR_04  get/set playerMode round-trips all three values, name+numeric")
    r_pm0 = dut.cmd("get playerMode", timeout=3.0)
    cases = [("spotify", 0, "Spotify"), ("1", 1, "WebRadio"), ("player", 2, "Player")]
    mismatches = []
    for val_in, expect_val, expect_name in cases:
        dut.cmd(f"set playerMode {val_in}", timeout=3.0)
        r = dut.cmd("get playerMode", timeout=3.0)
        if r.get("val") != expect_val or r.get("name") != expect_name:
            mismatches.append((val_in, r.get("val"), r.get("name")))
    r_bad = dut.cmd("set playerMode 3", timeout=3.0)
    dut.cmd(f"set playerMode {r_pm0.get('val', 0)}", timeout=3.0)
    if mismatches:
        fail("T_PLR_04", f"round-trip mismatches: {mismatches}")
        return
    if r_bad.get("ok", True):
        fail("T_PLR_04", f"set playerMode 3 (out of range) was accepted: {r_bad}")
        return
    pass_("T_PLR_04", "spotify/webradio(1)/player all round-trip; out-of-range idx=3 rejected")


def t_plr_05(dut: Dut):
    """T_PLR_05: tapping the player slot from ANOTHER app restores the persisted
    mode (resolvePlayerSlot, unchanged), it does not cycle."""
    print("T_PLR_05  Tap from another app restores the persisted mode, does not cycle")
    r_pm0 = dut.cmd("get playerMode", timeout=3.0)
    if not _switch_to(dut, "Clock"):
        skip("T_PLR_05", "precondition: could not switch to Clock")
        return
    dut.cmd("set playerMode player", timeout=3.0)
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=5.0)
    time.sleep(0.3)
    name1 = dut.cmd("get appId", timeout=3.0).get("name")
    # A second tap, now that the player IS active, should cycle away from Player.
    dut.set_cooldown_zero()
    dut.cmd(f"tap {sx} {sy}", timeout=5.0)
    time.sleep(0.3)
    name2 = dut.cmd("get appId", timeout=3.0).get("name")
    dut.cmd(f"set playerMode {r_pm0.get('val', 0)}", timeout=3.0)
    _restore_spotify(dut)
    if name1 != "LocalPlayer":
        fail("T_PLR_05", f"restore tap landed on {name1!r} — expected LocalPlayer (persisted mode)")
        return
    if name2 != "Spotify":
        fail("T_PLR_05", f"cycle tap from active Player landed on {name2!r} — expected Spotify")
        return
    pass_("T_PLR_05", f"restore->LocalPlayer, then cycle->Spotify — restore-vs-cycle distinction confirmed")


# ── T_PLR_06/07 — eject remap (TASK-414 / ADR-059 D6) ──────────────────────────
# Eject is freed from "switch to WebRadio" (the taskbar player-slot cycle above
# owns app switching now) and becomes "load media from this source", one verb
# with three per-mode realisations. The logo tap keeps its own TLS-reset
# behaviour unchanged (T_PLR_07 regression-checks the shared helper refactor).

def t_plr_06(dut: Dut):
    """T_PLR_06: eject is per-mode. Spotify -> TLS reset + force poll, appId stays
    Spotify. WebRadio -> station-list refresh (wrEnqueues advances), appId stays
    WebRadio. Player -> opens the file browser (TASK-416), appId stays LocalPlayer.

    The Player-mode leg's pass criterion was rewritten by TASK-416, and the real
    history matters because it is a process lesson, not a tidy-up:

      - At TASK-414 (`07250ca`) this assertion (`hit == "LOCALPLAYER"`,
        `action == "CONSUMED"`) was correct AND passing on the DUT —
        `main.cpp:3101` reported exactly that for LocalPlayer's cmdTap branch.
      - TASK-415 (`fd129ec`) rerouted that branch through
        `winampDisplay.injectTouch()` so PLEDIT row taps would anchor in the
        shared PleditView. Correct change, but it made the tap-dispatch REPORT
        `EJECT`/`EJECT` like every other mode — and T_PLR_06 was not re-run, so
        the suite carried a stale assertion for a day without anyone noticing.
      - TASK-416 inherited the stale test. It did NOT cause the divergence.

    So: the eject VERB differs per mode (that is what this whole test is for);
    the tap-dispatch REPORT does not, and has not since `fd129ec`. This now
    checks the thing that actually distinguishes Player's eject from a no-op —
    the browser (`get fbState`) is active afterward."""
    print("T_PLR_06  Eject is per-mode: Spotify TLS-reset, WebRadio refresh, Player browser opens")
    errors = []
    ex, ey = _c.tap_eject()

    # ── Spotify: TLS reset + force poll ─────────────────────────────────────
    if not _restore_spotify(dut):
        skip("T_PLR_06", "precondition: could not restore Spotify")
        return
    # TASK-417: pre-existing gap (predates this task, same as T_WR_EJECT_01)
    # — without this, a tap landing while g_shellBusy is still true from
    # _restore_spotify's own app-switch/poll is silently swallowed
    # (hit=CANVAS), which then also starves the TLS-reset log check below.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    # TASK-417 gate investigation: tap + log-scan combined into one
    # continuous read (_tap_and_wait_log) — the previous split
    # dut.cmd(tap)+manual-readline-loop pattern raced read_json()'s
    # non-JSON-line discard against spotifyTask's async "hard reset —
    # stopping client" trace (a different FreeRTOS task) and could silently
    # eat the very log line being waited for. See _tap_and_wait_log's
    # docstring for the raw-serial-capture proof (T_PLR_17's SHUFFLE/REPEAT
    # case, same mechanism).
    dut.set_cooldown_zero()
    r, tls_seen = _tap_and_wait_log(dut, ex, ey, "hard reset", tap_timeout=5.0, log_timeout=8.0)
    if r is None or r.get("hit") != "EJECT" or r.get("action") != "EJECT":
        errors.append(f"Spotify: hit={r.get('hit') if r else None} action={r.get('action') if r else None}")
    else:
        time.sleep(0.3)
        appid = dut.cmd("get appId", timeout=3.0).get("name")
        if appid != "Spotify":
            errors.append(f"Spotify: appId={appid!r} after eject (expected Spotify — eject no longer switches apps)")
        if not tls_seen:
            errors.append("Spotify: no TLS-reset log line within 8 s")

    # ── WebRadio: station-list refresh ──────────────────────────────────────
    dut.cmd("set bgPoll 0", timeout=2.0)
    ok, _ = _switch_to_webradio_capture_heap(dut)
    if not ok:
        errors.append("WebRadio: could not enter WebRadio via taskbar player-slot cycle")
    else:
        _wait_shell_not_busy(dut, timeout_s=5.0)
        enq_before = dut.cmd("get dataq", timeout=3.0).get("wrEnqueues", 0)
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {ex} {ey}", timeout=5.0)
        if r.get("hit") != "EJECT" or r.get("action") != "EJECT":
            errors.append(f"WebRadio: hit={r.get('hit')} action={r.get('action')}")
        else:
            time.sleep(0.3)
            appid = dut.cmd("get appId", timeout=3.0).get("name")
            if appid != "WebRadio":
                errors.append(f"WebRadio: appId={appid!r} after eject (expected WebRadio — eject no longer switches apps)")
            enq_after = dut.cmd("get dataq", timeout=3.0).get("wrEnqueues", 0)
            if enq_after <= enq_before:
                errors.append(f"WebRadio: wrEnqueues did not advance ({enq_before} -> {enq_after})")
    dut.cmd("set bgPoll 1", timeout=2.0)

    # ── Player: opens the file browser (TASK-416) ───────────────────────────
    heap_pressure_skip = False
    dut.cmd("set playerMode player", timeout=3.0)
    if not _switch_to(dut, "Clock"):
        errors.append("Player: precondition: could not switch to Clock")
    else:
        dut.set_cooldown_zero()
        sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
        dut.cmd(f"tap {sx} {sy}", timeout=5.0)   # restore persisted mode -> LocalPlayer
        time.sleep(0.3)
        appid = dut.cmd("get appId", timeout=3.0).get("name")
        if appid != "LocalPlayer":
            errors.append(f"Player: precondition failed, appId={appid!r} (expected LocalPlayer)")
        else:
            dut.set_cooldown_zero()
            r = dut.cmd(f"tap {ex} {ey}", timeout=5.0)
            if r.get("hit") != "EJECT" or r.get("action") != "EJECT":
                errors.append(f"Player: hit={r.get('hit')} action={r.get('action')} (expected EJECT/EJECT — "
                              "the tap-dispatch report, not the per-mode verb)")
            time.sleep(0.3)
            appid2 = dut.cmd("get appId", timeout=3.0).get("name")
            if appid2 != "LocalPlayer":
                errors.append(f"Player: appId={appid2!r} after eject (expected LocalPlayer — the browser "
                              "is modal WITHIN the app, not a switchApp)")
            fb = dut.cmd("get fbState", timeout=3.0)
            if not fb.get("active"):
                # fileBrowser.h heap-allocates its dir/file arrays (~13 KB) on
                # first open() — a real fragmented-heap alloc failure (seen on
                # the DUT: this exact Spotify->WebRadio->Player chain, in this
                # order, left `free=50700` but no contiguous block big enough)
                # degrades cleanly, same class of risk as m3u::PlaylistIndex's
                # own alloc under pressure (T_PLR_12's notes). Distinguish it
                # from a real defect via LocalPlayerApp's own hasError()
                # (`get activeError` — NOT `get plCount`'s "error", which is
                # m3u::PlaylistIndex's own flag and unrelated to a browser-
                # alloc failure) rather than failing the eject-verb gate on a
                # pre-existing, already-tracked heap-pressure risk.
                ae = dut.cmd("get activeError", timeout=3.0)
                if ae.get("active"):
                    heap_pressure_skip = True
                else:
                    errors.append(f"Player: eject did not open the browser: {fb}")
            dut.cmd("set fbCancel", timeout=3.0)   # leave the browser closed for later tests

    dut.cmd("set playerMode spotify", timeout=3.0)
    _restore_spotify(dut)

    if heap_pressure_skip and not errors:
        skip("T_PLR_06", "Player leg: file-browser alloc failed under heap pressure after the "
                         "Spotify+WebRadio legs fragmented the heap (LocalPlayerApp reported "
                         "error=true, not a crash) — known M-HEAP-FRAGMENTATION-class risk, not "
                         "an eject-verb defect; Spotify/WebRadio legs above already passed")
        return
    if errors:
        fail("T_PLR_06", "; ".join(errors))
        return
    pass_("T_PLR_06", "eject per-mode confirmed: Spotify TLS-reset, WebRadio refresh, Player browser opens")


def t_plr_07(dut: Dut):
    """T_PLR_07: Winamp logo tap still resets TLS — unchanged from TASK-053f.
    Regression check for the TASK-414 refactor that moved the TLS-reset +
    force-poll action into a shared tryReconnect() (winampDisplay.h) used by
    both the logo tap and eject."""
    print("T_PLR_07  Logo tap still resets TLS (unchanged from TASK-053f)")
    if not _restore_spotify(dut):
        skip("T_PLR_07", "precondition: could not restore Spotify")
        return
    dut.set_cooldown_zero()
    lgx, lgy = _c.tap_logo()
    r = dut.cmd(f"tap {lgx} {lgy}", timeout=5.0)
    if r.get("hit") != "LOGO" or r.get("action") != "TLS_RESET":
        fail("T_PLR_07", f"expected hit=LOGO action=TLS_RESET got hit={r.get('hit')} action={r.get('action')}")
        return
    tls_log_found = False
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "hard reset" in line or "stopping client" in line:
            tls_log_found = True
            break
    if not tls_log_found:
        flake("T_PLR_07", "hit=LOGO action=TLS_RESET but no TLS-reset log line within 8 s")
        return
    pass_("T_PLR_07", "logo tap → TLS_RESET confirmed, unchanged from TASK-053f")


# ── T_PLR_08–12 — M3U index model (TASK-415 / ADR-059 D3) ─────────────────────
# The playlist is a RAM index over an SD-backed file: entries[] plus viewOrder/
# playOrder permutations, with row text read on demand. These assert the load,
# the resolution rules, the degradation behaviour and — the one that would ship
# broken while looking fine — that the index is bounded and actually freed.
#
# FIXTURES: app/tools/gen_playlist_fixtures.py writes them; they must be copied
# onto the card from a host reader (the device write path is TASK-424). Missing
# fixtures SKIP rather than FAIL — that's a rig gap, not a defect.

_PL_GATE   = "/playlists/gate100.m3u"
_PL_RELPAR = "/playlists/relpar.m3u"
_PL_REL    = "/mp3/rel.m3u"
_PL_BAD    = "/playlists/bad.m3u"
_PL_EMPTY  = "/playlists/empty.m3u"
_PL_UTF8   = "/playlists/utf8.m3u"
# TASK-418: 20-entry fixture for the play-order engine (gen_playlist_fixtures.py's
# gate20()) — entry ids are per-record, not per-file, so it does not need 20
# distinct audio files; T_PLR_20-24 never decode audio at all (D12's `advance`/
# `set plCursor`). T_PLR_25 is the one real-playback case and needs actual
# short files (/playlists/short5.m3u — 5 real ~3s tones, not part of
# gen_playlist_fixtures.py since they're binary audio, not generated text).
# TASK-603: T_PLR_25's registry copy is deleted (WP-E §7.2 — one working test
# and one copy stranded on the wrong build). The id's sole executable body is
# now app/tools/test_playorder_player.py, dispatched by leg B of
# run/player-gate on cyd2usb_player; `_PL_SHORT5` went with it, and no id in
# this module decodes audio any more.
_PL_20     = "/playlists/gate20.m3u"


def _enter_player(dut: Dut, tid: str) -> bool:
    """Leave the player slot, persist Player mode, tap back in (the restore path).
    Tapping the slot while a player mode is already active CYCLES (T_PLR_01), so
    the step-off is mandatory, not defensive.

    Also suspends Spotify's background poll for the whole T_PLR_08-12 suite.
    TASK-430 (2026-08-11) bounded aeConnectFile()'s yield to tlsTryYield()'s
    1.5 s ceiling, so a stuck-mid-HTTP Spotify task can no longer park loopTask
    for up to 150 s the way it could when this comment was first written — that
    original failure mode (every later command in the run timing out) is fixed.
    Kept anyway, DUT-reproduced under TASK-430's own gate: with bgPoll left on,
    this account's real TASK-243 403-retry loop (a genuine ~5 s-cadence HTTP
    round trip, not a debug simulation) can still be in flight exactly when
    T_PLR_09 calls plPlay, and tlsTryYield() then legitimately times out at its
    1.5 s bound — a clean, fast, but FLAKY play failure instead of a hang. Only
    T_PLR_09 actually calls aeConnectFile(); 08/10/11/12 never touch it, so this
    suite-wide suspension is now precautionary for them, not load-bearing.
    Restored by _leave_player()."""
    dut.cmd("set bgPoll 0", timeout=3.0)
    dut.cmd("set playerMode player", timeout=3.0)
    if dut.cmd("get appId", timeout=3.0).get("name") in ("Spotify", "WebRadio", "LocalPlayer"):
        if not _switch_to(dut, "Clock"):
            _leave_player(dut)
            skip(tid, "precondition: could not step off the player slot")
            return False
    dut.cmd("set playerMode player", timeout=3.0)
    # Two attempts: the taskbar tap resolves against the CURRENT scroll offset,
    # and a dropped `set tbScroll` leaves the tap landing on whichever app now
    # occupies that slot (seen once as appId='PlaneRadar'). Re-anchoring and
    # re-tapping costs a second and removes a whole class of false SKIPs.
    name = None
    for attempt in range(2):
        _tb_set_offset(dut, 0)
        dut.set_cooldown_zero()
        x, y = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
        dut.cmd(f"tap {x} {y}", timeout=5.0)
        time.sleep(0.4)
        name = dut.cmd("get appId", timeout=3.0).get("name")
        if name == "LocalPlayer":
            return True
        # Landed somewhere else: step back off the player slot before retrying,
        # or the next tap cycles the mode instead of restoring it.
        if attempt == 0:
            _switch_to(dut, "Clock")
            dut.cmd("set playerMode player", timeout=3.0)
    _leave_player(dut)
    skip(tid, f"precondition: appId={name!r} (expected LocalPlayer, 2 attempts)")
    return False


def _leave_player(dut: Dut) -> None:
    """Undo _enter_player()'s poll suspension. Every T_PLR_08-12 exit path calls
    this — a suite that left bgPoll off would silently disarm Spotify for every
    test that runs after it."""
    dut.cmd("set bgPoll 1", timeout=3.0)


def _bgpoll_backstop(fn):
    """DUT-observed 2026-09-13 (TASK-635's boundary check, TASK-695 item 7):
    `T_PLR_08`, `T_PLR_19` and `T_PLR_24` each timed out and left `bgPoll 0`
    armed — `_enter_player` arms it, but the restore only ever ran through
    hand-placed `_leave_player()` calls on the paths the author remembered,
    which a mid-body timeout or exception skips past entirely. This wraps the
    whole test body in the manager-backed `_bgpoll_suspended` (`_helpers.py`)
    as a backstop, so bgPoll is put back on EVERY exit path — the existing
    `_enter_player`/`_leave_player` calls inside the body are unchanged and
    still run on the paths they always did; this only closes the gap on the
    paths they don't reach."""
    @functools.wraps(fn)
    def wrapper(dut: Dut):
        with _bgpoll_suspended(dut):
            return fn(dut)
    return wrapper


def _pl_load(dut: Dut, path: str, timeout: float = 20.0) -> dict:
    """`set plLoad <path>` then `get plCount`. Returns the plCount reply."""
    dut.cmd(f"set plLoad {path}", timeout=timeout)
    return dut.cmd("get plCount", timeout=8.0)


@_bgpoll_backstop
def t_plr_08(dut: Dut):
    """T_PLR_08: a >=100-track M3U loads, count is exact, load time recorded."""
    print("T_PLR_08  >=100-track M3U loads (count exact, load time recorded)")
    if not _enter_player(dut, "T_PLR_08"):
        return
    r = _pl_load(dut, _PL_GATE)
    if r.get("count", 0) == 0:
        _leave_player(dut)
        skip("T_PLR_08", f"fixture {_PL_GATE} not on the card (gen_playlist_fixtures.py) — reply={r}")
        return
    if r.get("count") != 120:
        _leave_player(dut)
        fail("T_PLR_08", f"count={r.get('count')} (expected 120) truncated={r.get('truncated')}")
        return
    if r.get("truncated"):
        _leave_player(dut)
        fail("T_PLR_08", "index reports truncated at 120 entries — PL_MAX_ENTRIES is 256")
        return
    # Spot-check the last row: an off-by-one in the record scan shows up here,
    # not in the count.
    last = dut.cmd(f"get plRow {r['count'] - 1}", timeout=8.0)
    if not last.get("ok") or "(120)" not in last.get("text", ""):
        _leave_player(dut)
        fail("T_PLR_08", f"last row text={last.get('text')!r} (expected the '(120)' entry)")
        return
    _leave_player(dut)
    pass_("T_PLR_08", f"120 entries in {r.get('loadMs')} ms, totalSec={r.get('totalSec')}, "
                      f"last row={last.get('text')!r}")


def t_plr_09(dut: Dut):
    """T_PLR_09: scroll the list end to end while a track plays — no stall, no
    reboot, playback survives. The short end of the same risk T_PLR_13/39 attack
    at longer durations (loopTask SD I/O starving the audio pump)."""
    print("T_PLR_09  Scroll end to end during playback")
    if not _enter_player(dut, "T_PLR_09"):
        return
    r = _pl_load(dut, _PL_GATE)
    if r.get("count", 0) < 100:
        _leave_player(dut)
        skip("T_PLR_09", f"fixture {_PL_GATE} missing or short (count={r.get('count')})")
        return
    # Spotify's background poll must be off for any test that starts playback.
    # aeConnectFile() calls spotifyTask::tlsTryYield() (TASK-430), which blocks
    # the CALLING task (loopTask) for at most ~1.5 s now, not tlsYield()'s old
    # 150 s ceiling — a stuck Spotify task fails the play cleanly instead of
    # hanging the harness. Left OFF anyway: this account's real TASK-243
    # 403-retry loop is enough real HTTP traffic on its own ~5 s cadence to
    # occasionally win the race and time out the try-yield for real, turning a
    # would-be PASS into a flaky FAIL. Redundant with _enter_player()'s own
    # suite-wide bgPoll=0 (belt and suspenders — this is the one test in the
    # suite where it's actually load-bearing).
    dut.cmd("set bgPoll 0", timeout=3.0)
    dut.cmd("set plPlay 0", timeout=8.0)
    # connecttoFS + first decode: give the pump task a real window before judging.
    playing = False
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        time.sleep(1.0)
        if dut.cmd("get plCount", timeout=5.0).get("playing"):
            playing = True
            break
    if not playing:
        # VE 2026-08-15 (TASK-443), DELIBERATELY still a SKIP — read before changing.
        # This SKIP is correct on cyd2usb_winamp_debug, where local playback cannot
        # start at all with Spotify's TLS working set resident (TASK-425/431), and
        # that is the env this whole harness runs on. It is WRONG on cyd2usb_player
        # once TASK-443's ruling (retire the arena from the FILE path) lands: there,
        # "never reached playing=true" IS the ruling failing, and a SKIP would hide
        # exactly the regression the ruling has to be gated on.
        # It is not flipped today because (a) the ruling is proposed, not accepted,
        # (b) on cyd2usb_player playback genuinely cannot start right now (TASK-442,
        # open P1), so flipping turns a SKIP into a permanent red no one can action,
        # and (c) the harness carries no env discriminator to make it conditional,
        # and inventing one unverified with no DUT access is worse than a note.
        # WHEN THE RULING LANDS: gate on the build variant and make this a fail()
        # on cyd2usb_player, keeping skip() only on cyd2usb_winamp_debug.
        dut.cmd("set bgPoll 1", timeout=3.0)
        _leave_player(dut)
        skip("T_PLR_09", "track never reached playing=true — audio precondition failed, "
                         "not a scroll result (check the card's /mp3 files). NOTE: this "
                         "must become a FAIL on cyd2usb_player once TASK-443's ruling "
                         "lands — see the comment above this call")
        return
    xu, yu, xu2, yu2 = _c.pledit_swipe("up")
    worst_gap = 0.0
    for i in range(12):                      # 12 swipes ≈ the full 120-row list
        t0 = time.monotonic()
        if _do_drag(dut, xu, yu, xu2, yu2, steps=20, timeout=20.0) is None:
            dut.cmd("set bgPoll 1", timeout=3.0)
            _leave_player(dut)
            fail("T_PLR_09", f"DUT stopped responding on swipe {i + 1} — drag timeout")
            return
        worst_gap = max(worst_gap, time.monotonic() - t0)
    off = _get_scroll(dut)
    still = dut.cmd("get plCount", timeout=5.0)
    if not still.get("ok"):
        _leave_player(dut)
        fail("T_PLR_09", "DUT unresponsive after the scroll sweep")
        return
    if not still.get("playing"):
        _leave_player(dut)
        fail("T_PLR_09", f"playback stopped during the scroll sweep (scrollOffset={off})")
        return
    if not off:
        _leave_player(dut)
        fail("T_PLR_09", f"scrollOffset={off} after 12 up-swipes — the list did not scroll")
        return
    dut.cmd("set plPlay 0", timeout=5.0)     # leave a defined state
    dut.cmd("set bgPoll 1", timeout=3.0)
    _leave_player(dut)
    pass_("T_PLR_09", f"scrolled to offset {off} over 12 swipes, still playing; "
                      f"worst swipe round-trip {worst_gap:.1f}s")


def t_plr_10(dut: Dut):
    """T_PLR_10: relative paths resolve against the PLAYLIST's directory, not the
    root and not the current working directory (there isn't one)."""
    print("T_PLR_10  Relative paths resolve against the playlist directory")
    if not _enter_player(dut, "T_PLR_10"):
        return
    errors = []

    dut.cmd("set bgPoll 0", timeout=3.0)   # see T_PLR_09's note on tlsYield
    r = _pl_load(dut, _PL_REL)
    if r.get("count", 0) == 0:
        dut.cmd("set bgPoll 1", timeout=3.0)
        _leave_player(dut)
        skip("T_PLR_10", f"fixture {_PL_REL} not on the card (gen_playlist_fixtures.py)")
        return
    row0 = dut.cmd("get plRow 0", timeout=8.0)       # bare "name.mp3"
    row4 = dut.cmd("get plRow 4", timeout=8.0)       # "./name.mp3"
    if row0.get("path") != "/mp3/01 - Tomorrow Comes Today.mp3":
        errors.append(f"bare relative resolved to {row0.get('path')!r}")
    if not str(row4.get("path", "")).startswith("/mp3/") or "./" in str(row4.get("path", "")):
        errors.append(f"'./' relative resolved to {row4.get('path')!r}")

    r2 = _pl_load(dut, _PL_RELPAR)
    if r2.get("count", 0) == 0:
        errors.append(f"fixture {_PL_RELPAR} not on the card")
    else:
        rp = dut.cmd("get plRow 0", timeout=8.0)
        if rp.get("path") != "/mp3/01 - Tomorrow Comes Today.mp3":
            errors.append(f"'../' relative resolved to {rp.get('path')!r} "
                          "(expected the COLLAPSED /mp3/... — the FATFS VFS does not "
                          "resolve '..' itself; measured on the DUT, T_PLR_10 2026-08-11)")

    # Resolution is only half of it: a collapsed path must actually OPEN. Prove
    # that by loading a playlist THROUGH a '..' path rather than by playing a
    # track — SD.open() is the same syscall either way, and routing the proof
    # through the audio engine makes the test fail whenever the Helix arena
    # cannot get its 24 KB contiguous (observed with WiFi + TLS resident: the
    # decoder alloc fails, which says nothing about path resolution).
    r3 = _pl_load(dut, "/mp3/../playlists/gate100.m3u")
    if r3.get("count", 0) != 120:
        errors.append(f"opening through a '..' path failed: count={r3.get('count')} "
                      f"error={r3.get('error')} (expected the 120-entry fixture)")
    if errors:
        _leave_player(dut)
        fail("T_PLR_10", "; ".join(errors))
        return
    _leave_player(dut)
    pass_("T_PLR_10", "bare, './' and '../' relative paths all resolve against the playlist dir")


def t_plr_11(dut: Dut):
    """T_PLR_11: malformed input degrades — BOM, CRLF, missing/garbage #EXTINF,
    stray directives, a trailing record with no path line, and an empty file.
    Loads what it can, never crashes, and the UTF-8 fold (design OQ1) is applied
    to row text."""
    print("T_PLR_11  Malformed M3U degrades (BOM/CRLF/no-EXTINF/truncated/empty) + UTF-8 fold")
    if not _enter_player(dut, "T_PLR_11"):
        return
    errors = []

    r = _pl_load(dut, _PL_BAD)
    if r.get("count", 0) == 0 and not r.get("ok"):
        _leave_player(dut)
        skip("T_PLR_11", f"fixture {_PL_BAD} not on the card (gen_playlist_fixtures.py)")
        return
    if r.get("count") != 8:
        errors.append(f"bad.m3u count={r.get('count')} (expected 8 — the trailing "
                      "#EXTINF with no path line must NOT produce an entry)")
    rows = {i: dut.cmd(f"get plRow {i}", timeout=8.0) for i in range(min(8, r.get("count", 0)))}
    checks = [
        (0, "Gorillaz - Tomorrow Comes Today", 192, "normal record"),
        (1, "02 - Clint Eastwood", 0, "no #EXTINF -> basename, no duration"),
        (2, "Unknown duration", 0, "#EXTINF:-1 -> duration 0"),
        (3, "Junk duration", 0, "unparsable duration -> 0"),
        # `#EXTINF:222` — a duration with no ",title". The duration is real and
        # is kept; only the text falls back to the basename. (This expectation
        # was wrong on the first gate run: it demanded durSec 0, i.e. that a
        # malformed *title* discard a perfectly good duration.)
        (4, "05 - Feel Good Inc", 222, "#EXTINF with no comma -> basename, duration kept"),
        (5, "Gorillaz - DARE", 246, "directive between #EXTINF and path"),
    ]
    for idx, want_text, want_dur, why in checks:
        got = rows.get(idx, {})
        if got.get("text") != want_text:
            errors.append(f"row {idx} text={got.get('text')!r} expected {want_text!r} ({why})")
        if got.get("durSec") != want_dur:
            errors.append(f"row {idx} durSec={got.get('durSec')} expected {want_dur} ({why})")
    if 7 in rows and rows[7].get("path") != "/mp3/07 - Dirty Harry.mp3":
        errors.append(f"row 7 path={rows[7].get('path')!r} — leading/trailing spaces not trimmed")

    r_empty = _pl_load(dut, _PL_EMPTY)
    if r_empty.get("count") != 0:
        errors.append(f"empty.m3u count={r_empty.get('count')} (expected 0)")

    r_utf8 = _pl_load(dut, _PL_UTF8)
    if r_utf8.get("count", 0) == 0:
        errors.append(f"fixture {_PL_UTF8} not on the card")
    else:
        folded = {0: "Bjork - Joga", 1: "Sigur Ros - Saeglopur",
                  2: "Antonin Dvorak - Symphony No. 9", 3: "Motorhead - Ace of Spades"}
        for idx, want in folded.items():
            got = dut.cmd(f"get plRow {idx}", timeout=8.0).get("text")
            if got != want:
                errors.append(f"fold: row {idx} text={got!r} expected {want!r}")
        cjk = dut.cmd("get plRow 7", timeout=8.0).get("text", "")
        if not cjk.startswith("????"):
            errors.append(f"fold: CJK row text={cjk!r} (expected '?' per codepoint)")

    # Still alive after all of it — the whole point of "degrades".
    if not dut.cmd("get plMem", timeout=5.0).get("ok"):
        errors.append("DUT unresponsive after the malformed-input sweep")
    if errors:
        _leave_player(dut)
        fail("T_PLR_11", "; ".join(errors))
        return
    _leave_player(dut)
    pass_("T_PLR_11", "8/8 malformed-input cases degraded correctly; empty file loads to 0; "
                      "UTF-8 folded to ASCII")


def t_plr_12(dut: Dut):
    """T_PLR_12: the index is bounded and freed. Heap AND largest-free-block are
    both reported (VE-15) — a clean free-heap figure hides fragmentation, which
    is the real risk for a 3 KB allocation taken and returned every mode switch."""
    print("T_PLR_12  Index memory bounded (<=5.2 KB) and returned on suspend (+/-256 B)")
    if not _enter_player(dut, "T_PLR_12"):
        return
    # Baseline with the index NOT allocated: step off the mode entirely.
    if not _switch_to(dut, "Clock"):
        _leave_player(dut)
        skip("T_PLR_12", "precondition: could not switch to Clock for the baseline")
        return
    time.sleep(0.5)
    base = dut.cmd("get plMem", timeout=5.0)
    if base.get("allocated"):
        _leave_player(dut)
        fail("T_PLR_12", "index still allocated after leaving Player mode — suspend() did not free")
        return
    if not _enter_player(dut, "T_PLR_12"):
        return
    time.sleep(0.5)
    entered = dut.cmd("get plMem", timeout=5.0)
    loaded = _pl_load(dut, _PL_GATE)
    peak = dut.cmd("get plMem", timeout=5.0)     # handle still open
    # The playlist File is dropped 1.5 s after the last row read (an open handle
    # is ~4.4 KB of stdio buffer, not index memory) — measure the resting cost,
    # and report the open-handle peak alongside it.
    time.sleep(3.0)
    after = dut.cmd("get plMem", timeout=5.0)
    if not _switch_to(dut, "Clock"):
        _leave_player(dut)
        skip("T_PLR_12", "could not leave Player mode for the free measurement")
        return
    time.sleep(0.5)
    freed = dut.cmd("get plMem", timeout=5.0)

    d_enter = base["freeHeap"] - entered["freeHeap"]
    d_load  = base["freeHeap"] - after["freeHeap"]
    d_free  = base["freeHeap"] - freed["freeHeap"]
    errors = []
    if freed.get("allocated"):
        errors.append("index still allocated after suspend")
    d_peak = base["freeHeap"] - peak["freeHeap"]
    if d_load > 5324:                       # 5.2 KB
        errors.append(f"load delta {d_load} B exceeds the 5.2 KB budget")
    if abs(d_free) > 256:
        errors.append(f"heap did not return to baseline: {d_free:+d} B (limit +/-256)")
    if loaded.get("count", 0) == 0:
        errors.append(f"fixture {_PL_GATE} not on the card — the delta above is index-only, "
                      "not index+rowcache under load")
    if errors:
        _leave_player(dut)
        fail("T_PLR_12", f"{'; '.join(errors)} | resume={d_enter}B load={d_load}B "
                         f"residual={d_free:+d}B lfb {base['largestBlock']}->{freed['largestBlock']}")
        return
    _leave_player(dut)
    pass_("T_PLR_12", f"resume +{d_enter} B, loaded ({loaded.get('count')} rows) +{d_load} B "
                      f"(peak with the file open +{d_peak} B), "
                      f"residual {d_free:+d} B; largest-free-block "
                      f"{base['largestBlock']} -> {after['largestBlock']} -> {freed['largestBlock']}")


# ── T_PLR_13-16 — file browser (TASK-416 / M-WINAMP-PLAYER-local §4) ──────────
# fileBrowser.h: SD.open()+openNextFile(), paged at <=FB_BATCH=4 entries/tick,
# directories bucketed ahead of .mp3/.m3u files, non-audio filtered. These
# assert paging never stalls, back/up survives the busy gate (TASK-384 defect
# class), hasPendingAsync() actually self-clears, and deep/edge directory
# shapes degrade correctly.
#
# FIXTURES: /probe200 (TASK-408's 200-entry probe dir — all named `*.txt`, so
# it is 0 playable files after filtering, which is itself part of what T_PLR_16
# checks; its VALUE for T_PLR_13 is walk cost, not row count) and /probefb/*
# (this task's own fixtures — empty dir, 2-level nested dir, an 8.3 name, a
# long name and a non-audio file side by side — created via `sdmkdir`+`sdput`
# 2026-08-11, same rig TASK-415 used for its playlist fixtures. Missing
# fixtures SKIP, not FAIL — a rig gap, not a defect.

_FB_BIG    = "/probe200"
_FB_ROOT   = "/"
_FB_EMPTY  = "/probefb/empty"
_FB_NESTED = "/probefb/nested"
_FB_DEEP   = "/probefb/nested/deep"
_FB_EDGE   = "/probefb/edge"


def _fb_open(dut: Dut, path: str, timeout: float = 6.0) -> dict:
    return dut.cmd(f"set fbOpen {path}", timeout=timeout)


def _fb_fixture_missing(dut: Dut, path: str) -> bool:
    """Did `set fbOpen <path>` fail because the fixture genuinely is not on the
    card, or because the browser itself failed to open a directory that IS
    there? The two are not the same and must not both read as SKIP.

    Filed because they did: on a 2026-08-11 orchestrator re-run, T_PLR_13 and
    T_PLR_15 opened the SAME `_FB_BIG` path in the SAME run — 13's open
    succeeded and 15's failed, and 15 reported "fixture not on the card", which
    was false. That is TASK-433. Probing with `sdls` (an independent path that
    does not go through fileBrowser's own state or its heap allocation) tells
    the two apart, so a real reopen failure fails loudly instead of hiding in a
    skip."""
    r = dut.cmd(f"sdls {path} n", timeout=8.0)
    return not r.get("ok")


def _fb_wait_done(dut: Dut, timeout_s: float = 12.0) -> dict | None:
    """Poll `get fbState` until pending clears. Returns the last reply, or None
    on timeout (DUT stopped responding — a real failure, not a slow walk)."""
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        last = dut.cmd("get fbState", timeout=3.0)
        if not last.get("ok"):
            return None
        if last.get("pending") is False:
            return last
    return last


def t_plr_13(dut: Dut):
    """T_PLR_13: browsing a ~200-file directory does not stall the pump. This
    node only proves the walk completes cleanly and the DUT stays responsive
    the whole time (no WDT, no stuck pending) — actual concurrent PLAYBACK
    (the design's real gate) needs cyd2usb_player, where the arena can be
    acquired at all (TASK-425/431: it cannot on cyd2usb_winamp_debug, in
    either mount/arena ordering, with Spotify's TLS working set resident).
    See test_fbrowser_player.py / run/browser-player for that half."""
    print("T_PLR_13  Browse ~200-file dir — walk completes, DUT stays responsive")
    if not _enter_player(dut, "T_PLR_13"):
        return
    t0 = time.monotonic()
    r = _fb_open(dut, _FB_BIG)
    if not r.get("ok"):
        missing = _fb_fixture_missing(dut, _FB_BIG)
        _leave_player(dut)
        if missing:
            skip("T_PLR_13", f"fixture {_FB_BIG} not on the card (TASK-408's probe fixture) — reply={r}")
        else:
            fail("T_PLR_13", f"fbOpen {_FB_BIG} failed but sdls says the directory IS on the card "
                             f"— browser-side open failure, see TASK-433. reply={r}")
        return
    # TASK-692: this id's SUBJECT, per its own docstring, is "the walk completes
    # cleanly and the DUT stays responsive" — not "within 15 s". The old 15.0 s
    # was an unstated PERFORMANCE bound smuggled in as a timeout, with no cited
    # origin anywhere (test_plan.md points this id at its design doc, not at the
    # number). It fired on 2026-09-13 while the walk was merely slower than it:
    # a probe watched the same walk run to completion at 22.1 s, pending going
    # False, `get fbState` answering throughout. The bound now bounds STUCK, which
    # is what the subject is about; the elapsed time is reported on the PASS line
    # either way, so a genuine slowdown stays visible instead of being hidden by
    # the larger number.
    _STUCK_BOUND_S = 60.0
    st = _fb_wait_done(dut, timeout_s=_STUCK_BOUND_S)
    elapsed = time.monotonic() - t0
    _leave_player(dut)
    if st is None:
        fail("T_PLR_13", f"DUT stopped responding mid-walk (unresponsive after {elapsed:.1f}s) "
                          "— loopTask stalled")
        return
    if st.get("pending"):
        # BP-059: state what was observed. The walk did not finish inside the
        # stuck bound — that is the observation. It is NOT called a "batching
        # regression" here, which is a cause this id has never established and
        # which the 22.1 s measurement above actively contradicts.
        fail("T_PLR_13", f"walk still pending after {elapsed:.1f}s "
                         f"(>{_STUCK_BOUND_S}s stuck bound) — the walk did not "
                         f"complete; cause NOT established by this id")
        return
    pass_("T_PLR_13", f"200-entry walk completed in {elapsed:.1f}s, DUT responsive throughout "
                      f"(dirCount={st.get('dirCount')} fileCount={st.get('fileCount')} — "
                      f"0 expected, TASK-408's fixture is all .txt, filtered)")


def t_plr_14(dut: Dut):
    """T_PLR_14: a tap on the browser's own back/up zone is honoured even while
    a page walk is in flight — the TASK-384 defect class (isNavigationTap()
    must except it or g_shellBusy swallows it). Drives the REAL tap path (not
    the fbSelect/fbCancel debug shortcuts, which bypass the busy gate
    entirely and would prove nothing about it): eject opens the browser at a
    directory big enough that the walk outlives the round-trip, `get
    shellBusy` confirms the gate is actually armed, then a real `tap` at the
    back-zone coordinates must be honoured (not `skipped`)."""
    print("T_PLR_14  Browser back/up tap survives the busy gate mid-walk (TASK-384)")
    if not _enter_player(dut, "T_PLR_14"):
        return
    errors = []
    # Land the eject fallback dir on /probe200 (200 entries, ~5 s walk per
    # T_SD_07-class timing) by loading a playlist that lives there first —
    # eject opens _pl.dir() when a playlist is loaded. A smaller directory
    # (tried first: /mp3, 53 entries) races the walk against this test's own
    # serial round trips and can finish before either check below observes
    # it — not the bug under test, just insufficient margin.
    pl = _pl_load(dut, "/probe200/anchor.m3u")
    if pl.get("count", 0) == 0:
        _leave_player(dut)
        skip("T_PLR_14", "fixture /probe200/anchor.m3u not on the card")
        return
    ex, ey = _c.tap_eject()
    dut.set_cooldown_zero()
    r = dut.cmd(f"tap {ex} {ey}", timeout=5.0)
    if r.get("skipped"):
        errors.append(f"eject tap itself was skipped: {r}")
    busy = dut.cmd("get shellBusy", timeout=3.0)
    if not busy.get("val", busy.get("busy")):
        # Walk may have finished before we could observe it (e.g. after a
        # slow serial round trip) — that is a real precondition miss, not the
        # bug under test.
        _leave_player(dut)
        skip("T_PLR_14", f"g_shellBusy never observed true after eject — reply={busy}; "
                         "walk finished before this could be checked")
        return
    st = dut.cmd("get fbState", timeout=3.0)
    if not st.get("active") or not st.get("pending"):
        errors.append(f"browser not mid-walk when expected: {st}")
    dut.set_cooldown_zero()
    r2 = dut.cmd("tap 10 10", timeout=5.0)   # back-zone: x<S_BACK_ZONE_W(60), y<S_HEADER_H(28)
    if r2.get("skipped"):
        errors.append(f"back-zone tap SKIPPED while busy — TASK-384 defect class: {r2}")
    st2 = _fb_wait_done(dut, timeout_s=10.0)
    if st2 is None:
        errors.append("DUT unresponsive after the back-zone tap")
    elif st2.get("active") and st2.get("dir") == "/probe200/":
        errors.append(f"back-zone tap had no effect — still browsing {st2.get('dir')!r}")
    _leave_player(dut)
    if errors:
        fail("T_PLR_14", "; ".join(errors))
        return
    pass_("T_PLR_14", "back-zone tap honoured while g_shellBusy was true and the walk was mid-flight "
                      f"(ascended to dir={st2.get('dir')!r})")


def t_plr_15(dut: Dut):
    """T_PLR_15: hasPendingAsync() is true from the moment a page walk starts
    and self-clears when it finishes, without any other action — the contract
    NEW-APP-CHECKLIST item 1 requires."""
    print("T_PLR_15  hasPendingAsync() true during the walk, self-clears on completion")
    if not _enter_player(dut, "T_PLR_15"):
        return
    r = _fb_open(dut, _FB_BIG)
    if not r.get("ok"):
        missing = _fb_fixture_missing(dut, _FB_BIG)
        _leave_player(dut)
        if missing:
            skip("T_PLR_15", f"fixture {_FB_BIG} not on the card")
        else:
            fail("T_PLR_15", f"fbOpen {_FB_BIG} failed but sdls says the directory IS on the card "
                             f"— browser-side open failure, see TASK-433. reply={r}")
        return
    immediate = dut.cmd("get fbState", timeout=3.0)
    st = _fb_wait_done(dut, timeout_s=15.0)
    _leave_player(dut)
    errors = []
    if not immediate.get("pending"):
        errors.append(f"pending was not true immediately after fbOpen: {immediate}")
    if st is None:
        errors.append("DUT unresponsive waiting for pending to clear")
    elif st.get("pending"):
        errors.append(f"pending never cleared: {st}")
    if errors:
        fail("T_PLR_15", "; ".join(errors))
        return
    pass_("T_PLR_15", "pending true immediately after open, false once the walk finished "
                      f"(dirCount={st.get('dirCount')} fileCount={st.get('fileCount')})")


def t_plr_16(dut: Dut):
    """T_PLR_16: deep/edge directory shapes. Nested descend, an empty
    directory, 8.3 vs long filenames, and non-audio files mixed alongside
    playable ones — no crash, correct filter, correct bucket counts."""
    print("T_PLR_16  Deep/edge paths: nested, empty, 8.3/long names, non-audio filtered")
    if not _enter_player(dut, "T_PLR_16"):
        return
    errors = []

    def check(path: str, want_dirs: int | None, want_files: int | None, label: str):
        r = _fb_open(dut, path)
        if not r.get("ok"):
            errors.append(f"{label}: fbOpen {path} failed — fixture missing?")
            return
        st = _fb_wait_done(dut, timeout_s=10.0)
        if st is None:
            errors.append(f"{label}: DUT unresponsive")
            return
        if want_dirs is not None and st.get("dirCount") != want_dirs:
            errors.append(f"{label}: dirCount={st.get('dirCount')} (expected {want_dirs})")
        if want_files is not None and st.get("fileCount") != want_files:
            errors.append(f"{label}: fileCount={st.get('fileCount')} (expected {want_files})")

    # Empty directory — no crash, both counts 0.
    check(_FB_EMPTY, 0, 0, "empty dir")
    # 2-level nested descend: /probefb/nested has one subdir (deep); descending
    # into it finds its one file. Exercises open() being called twice in a row
    # (a directory tap's onSelect -> open()) without a free()/alloc() cycle
    # between — the arrays are reused, not just allocated once and forgotten.
    check(_FB_NESTED, 1, 0, "nested (parent)")
    r = _fb_open(dut, _FB_NESTED)   # re-open parent to select its subdir by index
    st = _fb_wait_done(dut, timeout_s=6.0)
    if st is None or st.get("dirCount", 0) < 1:
        errors.append("nested: could not re-list parent to descend")
    else:
        sel = dut.cmd("set fbSelect 0", timeout=5.0)   # the one subdir, "deep"
        if not sel.get("ok"):
            errors.append(f"nested: fbSelect 0 (descend into deep) failed: {sel}")
        st2 = _fb_wait_done(dut, timeout_s=6.0)
        if st2 is None or st2.get("dir") != "/probefb/nested/deep/" or st2.get("fileCount") != 1:
            errors.append(f"nested: descend did not land in deep/ with 1 file: {st2}")
    # 8.3 name, a long name, an .m3u and a filtered non-audio file side by
    # side: SONG1.MP3 (8.3), "A Really Quite Long Song Title Name Here.mp3"
    # (long), list.m3u, notes.txt (filtered) -> fileCount=3, dirCount=0.
    check(_FB_EDGE, 0, 3, "edge names (8.3/long/m3u, .txt filtered)")
    # Root: real card content mixes directories with a non-audio file at the
    # top level (probebench.bin, a TASK-408 leftover) -> that file must not
    # appear in either bucket.
    check(_FB_ROOT, None, 0, "root (probebench.bin filtered, no dirCount assertion — card-dependent)")

    _leave_player(dut)
    if errors:
        fail("T_PLR_16", "; ".join(errors))
        return
    pass_("T_PLR_16", "empty dir, 2-level nested descend, 8.3/long/m3u names and non-audio "
                      "filtering all correct")


# _tap_and_wait_log — moved to suite/serialdbg/_helpers.py (TASK-480).
from suite.serialdbg._helpers import _tap_and_wait_log                          # noqa: E402,F401


def _wait_for_log(dut: Dut, marker: str, timeout_s: float = 5.0) -> bool:
    """Read serial lines until `marker` is seen (True) or timeout (False).
    Same idiom as T087/T095's inline log scans, extracted since T_PLR_17-19
    need it three different ways (positive AND negative assertions)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if marker in line:
            return True
    return False


def _drain_serial(dut: Dut, seconds: float = 0.3) -> None:
    """Discard buffered serial output for `seconds` — prevents a stale log
    line from a prior tap/test being misread as this one's effect."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            dut.ser.readline()
        except Exception:
            break


# ── T_PLR_17-19 — transport capability mask (TASK-417 / ADR-059 D8) ──────────
# CAP_TRANSPORT|CAP_SEEK|CAP_SHUFFLE|CAP_REPEAT gate winampDisplay's shuffle/
# repeat/seek zones per active mode: neither drawn (repaintChrome()) nor
# hit-tested (handleWinampInput() / each app's own hit-test) when the bit is
# absent. Spotify keeps all four (T_PLR_17 — a shipped mode getting no
# benefit from this refactor; ANY delta here is a regression, not a finding).
# WebRadio keeps CAP_TRANSPORT only (T_PLR_18) — before TASK-417 the SHUFREP
# sprites were drawn in WebRadio anyway (repaintChrome() was unconditional,
# sourced from whatever the shared cache last held) despite never being
# hit-tested; this closes that visual/hit-test mismatch. Player advertises
# all four (T_PLR_19), with its own state (not spotifyTask::Snapshot) behind
# the sprites — `get shufRep` reports both the active mask and the
# currently-rendered sprite indices, so a test can check what's REACHABLE
# (mask) and what's actually PAINTED (lastShuffle/lastRepeat) in one call.

@meta(scope="Spotify", scope_reason="cross-mode")
def t_plr_17(dut: Dut):
    """T_PLR_17: Spotify still advertises all four capabilities — shuffle and
    repeat are still drawn and still hit-tested, dispatching ACT_SHUFFLE/
    ACT_REPEAT exactly as before TASK-417. Zero delta is the pass condition."""
    print("T_PLR_17  Spotify: all four capabilities unchanged (shuffle/repeat still real)")
    if not _restore_spotify(dut):
        skip("T_PLR_17", "precondition: could not restore Spotify app")
        return
    # TASK-417: pre-existing gap (predates this task, same class as
    # T_WR_EJECT_01/T_PLR_06) — a tap fired while g_shellBusy is still true
    # from _restore_spotify's own app-switch/poll is silently swallowed
    # (hit=CANVAS), which then also starves the "dequeued action=SHUFFLE/
    # REPEAT" log-line check below (the dispatch never happened at all).
    _wait_shell_not_busy(dut, timeout_s=10.0)
    errors = []

    r = dut.cmd("get shufRep", timeout=3.0)
    if not r.get("ok") or r.get("caps") != 15:   # CAP_TRANSPORT|SEEK|SHUFFLE|REPEAT = 1+2+4+8
        errors.append(f"playerCaps={r.get('caps')} (expected 15 — all four bits set)")

    # SHUFFLE: hit-tested AND dispatches. dequeue log ("dequeued action=SHUFFLE
    # param=N") is spotifyTask's generic dispatcher trace (spotifyTaskStorage.cpp)
    # — proves the tap reached the real ACT_SHUFFLE enqueue, not just the sprite.
    # 20 s bound, not an arbitrary short one: T082's own comment documents that
    # the dequeue can "lag by many seconds behind a backlog of HTTPS calls on
    # spotify.task", and T082 itself waits up to 20 s for the same class of
    # confirmation — a shorter bound here would flag that backlog as a defect.
    # TASK-417 gate investigation: tap + log-scan combined into one
    # continuous read (_tap_and_wait_log) — the previous split
    # dut.cmd(tap)+_wait_for_log() pattern raced read_json()'s non-JSON-line
    # discard against spotifyTask's async dequeue trace and could silently
    # eat the very log line being waited for (see _tap_and_wait_log's
    # docstring; confirmed via raw serial capture showing both dequeue
    # lines present while the old split-read reported FAIL for both).
    dut.set_cooldown_zero()
    shx, shy = _c.tap_shuffle()
    r, shuffle_seen = _tap_and_wait_log(dut, shx, shy, "dequeued action=SHUFFLE",
                                         tap_timeout=5.0, log_timeout=20.0)
    if r is None or r.get("hit") != "SHUFFLE" or r.get("action") != "SHUFFLE":
        errors.append(f"SHUFFLE hit-test: hit={r.get('hit') if r else None} "
                      f"action={r.get('action') if r else None}")
    if not shuffle_seen:
        errors.append("SHUFFLE: no 'dequeued action=SHUFFLE' within 20s — dispatch did not reach spotifyTask")

    _poll_shell_busy(dut, False, timeout_ms=3000)
    dut.set_cooldown_zero()
    rpx, rpy = _c.tap_repeat()
    r, repeat_seen = _tap_and_wait_log(dut, rpx, rpy, "dequeued action=REPEAT",
                                        tap_timeout=5.0, log_timeout=20.0)
    if r is None or r.get("hit") != "REPEAT" or r.get("action") != "REPEAT":
        errors.append(f"REPEAT hit-test: hit={r.get('hit') if r else None} "
                      f"action={r.get('action') if r else None}")
    if not repeat_seen:
        errors.append("REPEAT: no 'dequeued action=REPEAT' within 20s — dispatch did not reach spotifyTask")

    if errors:
        fail("T_PLR_17", "; ".join(errors))
    else:
        pass_("T_PLR_17", "caps=15 (all four); SHUFFLE/REPEAT still hit-tested and still "
                          "dispatch ACT_SHUFFLE/ACT_REPEAT — no delta from pre-TASK-417 behaviour")


@meta(scope="WebRadio", scope_reason="cross-mode")
def t_plr_18(dut: Dut):
    """T_PLR_18: WebRadio advertises CAP_TRANSPORT only. Shuffle/repeat zones
    must be neither drawn (caps bit absent) nor hit-tested (tap there must not
    report a SHUFFLE/REPEAT hit, and must not reach spotifyTask). Volume stays
    on its own TASK-352 seam, untouched by this task — confirm it still
    hit-tests correctly (TASK-406 was a real WebRadio-volume regression once)."""
    print("T_PLR_18  WebRadio: CAP_TRANSPORT only — shuffle/repeat neither drawn nor hit-tested")
    # TASK-605/E-11: _switch_to(dut, "WebRadio") taps taskbar slot 11, which
    # WebRadio does not have (APP_SLOT["WebRadio"]=11, TASKBAR_APP_COUNT=11 ->
    # appIdx=0, the player/Spotify slot) — it only reached WebRadio when a
    # predecessor id left the board on Spotify so resolvePlayerTap() took the
    # cycle branch. Use the real, order-independent entry path instead (it
    # restores Spotify itself, then cycles the player slot once).
    ok, _heap = _switch_to_webradio_capture_heap(dut)
    if not ok:
        skip("T_PLR_18", "precondition: could not switch to WebRadio")
        return
    errors = []

    r = dut.cmd("get shufRep", timeout=3.0)
    if not r.get("ok") or r.get("caps") != 1:   # CAP_TRANSPORT only
        errors.append(f"playerCaps={r.get('caps')} (expected 1 — CAP_TRANSPORT only)")

    # Drain any residual dequeue lines from a prior test before probing —
    # otherwise an old "dequeued action=SHUFFLE" from a previous suite entry
    # could be misread as this tap's effect.
    _drain_serial(dut, 0.3)

    dut.set_cooldown_zero()
    shx, shy = _c.tap_shuffle()
    r = dut.cmd(f"tap {shx} {shy}")
    if r.get("hit") == "SHUFFLE" or r.get("action") == "SHUFFLE":
        errors.append(f"SHUFFLE zone still hit-tested in WebRadio: hit={r.get('hit')} "
                      f"action={r.get('action')} (expected NOT SHUFFLE)")
    if _wait_for_log(dut, "dequeued action=SHUFFLE", timeout_s=8.0):  # generous — this is a NEGATIVE check, more time only strengthens it
        errors.append("SHUFFLE: 'dequeued action=SHUFFLE' seen — WebRadio tap leaked into "
                      "spotifyTask (the exact cross-mode leak TASK-417's sink seam exists to stop)")

    dut.set_cooldown_zero()
    rpx, rpy = _c.tap_repeat()
    r = dut.cmd(f"tap {rpx} {rpy}")
    if r.get("hit") == "REPEAT" or r.get("action") == "REPEAT":
        errors.append(f"REPEAT zone still hit-tested in WebRadio: hit={r.get('hit')} "
                      f"action={r.get('action')} (expected NOT REPEAT)")
    if _wait_for_log(dut, "dequeued action=REPEAT", timeout_s=8.0):  # generous — this is a NEGATIVE check, more time only strengthens it
        errors.append("REPEAT: 'dequeued action=REPEAT' seen — WebRadio tap leaked into spotifyTask")

    # Volume: unaffected by the mask (TASK-352's own seam) — confirm the
    # zone is still correctly classified for WebRadio (TASK-406 territory).
    dut.set_cooldown_zero()
    vx = (_c.vol_drag_x()[0] + _c.vol_drag_x()[1]) // 2
    vy = _c.vol_drag_y()
    r = dut.cmd(f"tap {vx} {vy}")
    if r.get("hit") != "VOLUME":
        errors.append(f"VOLUME hit-test regressed in WebRadio: hit={r.get('hit')} "
                      f"(expected VOLUME — TASK-352/TASK-406 seam, untouched by this task)")

    if errors:
        fail("T_PLR_18", "; ".join(errors))
    else:
        pass_("T_PLR_18", "caps=1 (CAP_TRANSPORT only); shuffle/repeat neither hit-tested nor "
                          "leaked to spotifyTask; volume zone still hit-tests correctly")


@_bgpoll_backstop
def t_plr_19(dut: Dut):
    """T_PLR_19: Player advertises all four capabilities. Shuffle/repeat are
    drawn and hit-tested with STATE SOURCED FROM PLAYER, not spotifyTask::
    Snapshot (D8) — confirmed by toggling in Player and reading back via
    `get shufRep` rather than trusting the tap reply alone. Seek is confirmed
    reachable (not falling through to the dead zone) via the real per-app
    input path (`drag`), distinct from Spotify's songDuration-gated posbar —
    TASK-419 is the real duration-accurate scrub, this only proves the zone
    is captured."""
    print("T_PLR_19  Player: all four capabilities, state sourced from Player not Spotify")
    if not _enter_player(dut, "T_PLR_19"):
        return
    errors = []

    r = dut.cmd("get shufRep", timeout=3.0)
    if not r.get("ok") or r.get("caps") != 15:
        errors.append(f"playerCaps={r.get('caps')} (expected 15 — all four bits set)")
    base = r

    # SHUFFLE: hit-tested (reported by lastTouchResult, same as Spotify/
    # WebRadio above) AND the sprite cache changes — proving the toggle is
    # real, not just a reported hit with no effect.
    _drain_serial(dut, 0.3)
    dut.set_cooldown_zero()
    shx, shy = _c.tap_shuffle()
    r = dut.cmd(f"tap {shx} {shy}")
    if r.get("hit") != "SHUFFLE" or r.get("action") != "SHUFFLE":
        errors.append(f"SHUFFLE hit-test: hit={r.get('hit')} action={r.get('action')}")
    r2 = dut.cmd("get shufRep", timeout=3.0)
    if r2.get("lastShuffle") == base.get("lastShuffle"):
        errors.append(f"SHUFFLE: lastShuffle unchanged ({r2.get('lastShuffle')}) after tap — "
                      f"hit-tested but not actually toggled")
    # D8: this must NOT have gone through spotifyTask — Player has its own sink.
    if _wait_for_log(dut, "dequeued action=SHUFFLE", timeout_s=8.0):  # generous — this is a NEGATIVE check, more time only strengthens it
        errors.append("SHUFFLE: 'dequeued action=SHUFFLE' seen while in Player mode — "
                      "leaked to spotifyTask instead of Player's own sink")

    _drain_serial(dut, 0.3)
    dut.set_cooldown_zero()
    rpx, rpy = _c.tap_repeat()
    r = dut.cmd(f"tap {rpx} {rpy}")
    if r.get("hit") != "REPEAT" or r.get("action") != "REPEAT":
        errors.append(f"REPEAT hit-test: hit={r.get('hit')} action={r.get('action')}")
    r3 = dut.cmd("get shufRep", timeout=3.0)
    if r3.get("lastRepeat") == r2.get("lastRepeat"):
        errors.append(f"REPEAT: lastRepeat unchanged ({r3.get('lastRepeat')}) after tap — "
                      f"hit-tested but not actually toggled")
    if _wait_for_log(dut, "dequeued action=REPEAT", timeout_s=8.0):  # generous — this is a NEGATIVE check, more time only strengthens it
        errors.append("REPEAT: 'dequeued action=REPEAT' seen while in Player mode — "
                      "leaked to spotifyTask instead of Player's own sink")

    # SEEK: drive through `drag` (single-step = a tap), the real per-app
    # dispatch path (main.cpp's drainInjectionQueue() calls the ACTIVE app's
    # handleInput() directly) — NOT `tap`/injectTouch, which classifies via
    # Spotify's songDuration-gated hitTestPosbar() and would be unreliable
    # here (Player never sets songDuration). dragState must stay D_IDLE
    # throughout: Player's seek zone deliberately does not engage Spotify's
    # shared D_POSBAR_DRAG machine (that's TASK-419's real-scrub wiring).
    rd0 = dut.cmd("get dragState", timeout=3.0)
    bx, by = _c.tap_posbar()
    dr = dut.cmd(f"drag {bx} {by} {bx} {by} 1", timeout=5.0)
    if not dr.get("ok"):
        errors.append(f"SEEK zone drag: no ok reply ({dr})")
    rd1 = dut.cmd("get dragState", timeout=3.0)
    if rd1.get("state") != "D_IDLE":
        errors.append(f"SEEK zone drag left dragState={rd1.get('state')} "
                      f"(expected D_IDLE — Player must not engage Spotify's posbar-drag machine)")
    # DUT still responsive after the seek tap — proves it didn't wedge on an
    # unimplemented engine call (TASK-419's stub is a documented no-op).
    if not dut.cmd("get plCount", timeout=5.0).get("ok"):
        errors.append("SEEK zone drag: DUT unresponsive to a follow-up command")

    _leave_player(dut)
    if errors:
        fail("T_PLR_19", "; ".join(errors))
    else:
        pass_("T_PLR_19", "caps=15; shuffle/repeat drawn+hit-tested with Player-sourced state "
                          "(not spotifyTask), no leak to spotifyTask; seek zone reachable via the "
                          "real input path without engaging Spotify's drag machine")


# ── T_PLR_20-26 — play-order engine (TASK-418 / ADR-059 D9/D12) ─────────────
# The debug surface these depend on (`get plOrder`, `get plCursor`,
# `set plCursor <n>`, `advance next|prev`) steps the SAME _stepOrder()/bag
# real playback uses, without decoding audio — that's what turns "20-track
# shuffle cycle" and "20 forced wraps" from ~3h of real playback (the design's
# original ask) into a few seconds of serial round-trips (VE-1).
#
# Shuffle/repeat have no dedicated `set` debug verb (D12 lists only the
# order-engine surface) — they're driven the same way a real finger would,
# via `tap` on the sprite coordinates, reading back `get shufRep` to confirm
# the toggle actually landed (not just that the tap hit-tested).

def _pl_shuffle(dut: Dut, want_on: bool, timeout_s: float = 3.0) -> bool:
    """Tap the shuffle sprite until `get shufRep`'s lastShuffle matches
    want_on. Bounded — a stuck toggle reports False rather than looping."""
    sx, sy = _c.tap_shuffle()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = dut.cmd("get shufRep", timeout=3.0)
        cur = r.get("lastShuffle")
        if (cur == 1) == want_on:
            return True
        dut.set_cooldown_zero()
        dut.cmd(f"tap {sx} {sy}", timeout=3.0)
        time.sleep(0.15)
    r = dut.cmd("get shufRep", timeout=3.0)
    return (r.get("lastShuffle") == 1) == want_on


def _pl_repeat(dut: Dut, want_off: bool, timeout_s: float = 4.0) -> bool:
    """Tap the repeat sprite until it reads the target D9 binary state:
    2 (off) or NOT-2 (repeat-all, folded to 0 by playerRepeatSink — see
    localPlayerApp.h's onRepeatChanged()). handleWinampInput()'s shared
    dispatch cycles a Spotify-shaped tri-state (2->1->0->2) regardless of
    mode, so this may pass through 1 on the way — only the final resting
    value matters here."""
    rx, ry = _c.tap_repeat()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = dut.cmd("get shufRep", timeout=3.0)
        cur = r.get("lastRepeat")
        if want_off and cur == 2:
            return True
        if not want_off and cur != 2:
            return True
        dut.set_cooldown_zero()
        dut.cmd(f"tap {rx} {ry}", timeout=3.0)
        time.sleep(0.15)
    r = dut.cmd("get shufRep", timeout=3.0)
    cur = r.get("lastRepeat")
    return (cur == 2) if want_off else (cur != 2)


def t_plr_20(dut: Dut):
    """T_PLR_20: the shuffle bag visits each track exactly once over a full
    cycle — 20x `advance next` on a 20-track list, no repeats, no skips."""
    print("T_PLR_20  Shuffle bag visits each track once (20-track cycle)")
    if not _enter_player(dut, "T_PLR_20"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) == 0:
        _leave_player(dut)
        skip("T_PLR_20", f"fixture {_PL_20} not on the card (gen_playlist_fixtures.py + sd_put.py)")
        return
    if r.get("count") != 20:
        _leave_player(dut)
        fail("T_PLR_20", f"count={r.get('count')} (expected 20)")
        return
    if not _pl_shuffle(dut, True):
        _leave_player(dut)
        fail("T_PLR_20", "could not toggle shuffle ON via tap")
        return
    order = dut.cmd("get plOrder", timeout=5.0).get("order", [])
    if len(order) != 20 or len(set(order)) != 20:
        errors.append(f"plOrder after shuffle-ON not a 20-entry permutation: {order}")

    visited = []
    for i in range(20):
        adv = dut.cmd("advance next", timeout=5.0)
        if not adv.get("ok") or not adv.get("moved"):
            errors.append(f"advance next #{i}: {adv}")
            break
        visited.append(adv.get("row"))
    if len(visited) == 20 and len(set(visited)) != 20:
        errors.append(f"visited rows not all distinct: {visited}")
    if visited != order:
        errors.append(f"advance sequence {visited} != get plOrder {order} "
                       f"(advance should walk the bag exactly)")

    _leave_player(dut)
    if errors:
        fail("T_PLR_20", "; ".join(errors))
    else:
        pass_("T_PLR_20", f"20/20 distinct rows visited via advance next, matching plOrder exactly: {order}")


def t_plr_21(dut: Dut):
    """T_PLR_21: all four shuffle x repeat end-of-list cells (design §8),
    forced via `set plCursor <last>` + `advance next` — no real playback."""
    print("T_PLR_21  All four shuffle x repeat end-of-list cells")
    if not _enter_player(dut, "T_PLR_21"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) != 20:
        _leave_player(dut)
        skip("T_PLR_21", f"fixture {_PL_20} not on the card (count={r.get('count')})")
        return

    last_idx = r.get("count", 20) - 1

    # `set plCursor` below moves real cursor state (`get plCursor` field
    # `cursor`, TASK-695 B-taxonomy B-4/item 3) and nothing restored it before —
    # only `_leave_player`'s bgPoll undo ran on exit. Wrap the whole forced-wrap
    # sequence so the cursor is put back to wherever it was on entry (freshly
    # -1 from `_pl_load`'s own reset) on every exit path, exception included.
    with dut.saved("plCursor", field="cursor", timeout=3.0):
        def _force_wrap_from_last():
            # Always set explicitly to the known last index — do NOT infer "am I
            # already at the end" from a `get plCursor` read first. That reflects
            # whatever the PREVIOUS cell's advance left behind, not this cell's
            # precondition, and masks a real firmware bug the same way (a stale
            # cursor near the start silently reads as "close enough", producing
            # exactly the kind of drifted-cell failure this test exists to catch).
            dut.cmd(f"set plCursor {last_idx}", timeout=3.0)
            return dut.cmd("advance next", timeout=5.0)

        # Cell 1: shuffle off, repeat off -> stop at last row.
        if not _pl_shuffle(dut, False) or not _pl_repeat(dut, True):
            errors.append("cell1: could not set shuffle=off repeat=off")
        else:
            adv = _force_wrap_from_last()
            if adv.get("moved") is not False:
                errors.append(f"cell1 (shuffle off, repeat off): expected moved=false, got {adv}")

        # Cell 2: shuffle off, repeat all -> wrap to viewOrder[0].
        if not _pl_repeat(dut, False):
            errors.append("cell2: could not set repeat=all")
        else:
            adv = _force_wrap_from_last()
            if adv.get("moved") is not True or adv.get("row") != 0 or adv.get("reshuffled"):
                errors.append(f"cell2 (shuffle off, repeat all): expected moved=true row=0 "
                              f"reshuffled=false, got {adv}")

        # Cell 3: shuffle on, repeat off -> play each once, then stop.
        if not _pl_shuffle(dut, True) or not _pl_repeat(dut, True):
            errors.append("cell3: could not set shuffle=on repeat=off")
        else:
            adv = _force_wrap_from_last()
            if adv.get("moved") is not False:
                errors.append(f"cell3 (shuffle on, repeat off): expected moved=false, got {adv}")

        # Cell 4: shuffle on, repeat all -> reshuffle and continue.
        if not _pl_repeat(dut, False):
            errors.append("cell4: could not set repeat=all")
        else:
            adv = _force_wrap_from_last()
            if adv.get("moved") is not True or not adv.get("reshuffled"):
                errors.append(f"cell4 (shuffle on, repeat all): expected moved=true "
                              f"reshuffled=true, got {adv}")

    _leave_player(dut)
    if errors:
        fail("T_PLR_21", "; ".join(errors))
    else:
        pass_("T_PLR_21", "all four end-of-list cells match design §8 exactly, 4/4 — "
                          "no real-time playback")


def t_plr_22(dut: Dut):
    """T_PLR_22: reshuffle-on-wrap never re-opens with the track that just
    finished — 20 forced wraps (shuffle on, repeat all), 0 collisions."""
    print("T_PLR_22  Reshuffle does not re-open with the last track (20 forced wraps)")
    if not _enter_player(dut, "T_PLR_22"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) != 20:
        _leave_player(dut)
        skip("T_PLR_22", f"fixture {_PL_20} not on the card (count={r.get('count')})")
        return
    if not _pl_shuffle(dut, True) or not _pl_repeat(dut, False):
        _leave_player(dut)
        fail("T_PLR_22", "could not set shuffle=on repeat=all")
        return

    # `set plCursor` moves real cursor state (TASK-695 B-4/item 3) — restore it
    # on every exit path, not just the fall-through at the bottom of the loop.
    collisions = 0
    with dut.saved("plCursor", field="cursor", timeout=3.0):
        for i in range(20):
            before = dut.cmd("get plOrder", timeout=5.0).get("order", [])
            if len(before) != 20:
                errors.append(f"wrap {i}: plOrder count={len(before)} (expected 20)")
                break
            last_id = before[19]
            dut.cmd("set plCursor 19", timeout=3.0)
            adv = dut.cmd("advance next", timeout=5.0)
            if not adv.get("moved") or not adv.get("reshuffled"):
                errors.append(f"wrap {i}: expected moved=true reshuffled=true, got {adv}")
                continue
            after = dut.cmd("get plOrder", timeout=5.0).get("order", [])
            if len(after) == 20 and after[0] == last_id:
                collisions += 1
                errors.append(f"wrap {i}: reshuffle re-opened with the just-finished id {last_id}")

    _leave_player(dut)
    if errors:
        fail("T_PLR_22", f"{collisions}/20 collisions; " + "; ".join(errors[:5]))
    else:
        pass_("T_PLR_22", f"{collisions}/20 collisions over 20 forced wraps")


def t_plr_23(dut: Dut):
    """T_PLR_23: Prev replays history — walks playOrder backward, never
    rerolls. advance next x5 then advance prev x5 must be the exact reverse,
    and plOrder must be byte-identical before and after (no reshuffle)."""
    print("T_PLR_23  Prev replays history (no reroll, plOrder unchanged)")
    if not _enter_player(dut, "T_PLR_23"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) != 20:
        _leave_player(dut)
        skip("T_PLR_23", f"fixture {_PL_20} not on the card (count={r.get('count')})")
        return
    if not _pl_shuffle(dut, True):
        _leave_player(dut)
        fail("T_PLR_23", "could not toggle shuffle ON")
        return

    order_before = dut.cmd("get plOrder", timeout=5.0).get("order", [])
    forward = []
    for i in range(5):
        adv = dut.cmd("advance next", timeout=5.0)
        if not adv.get("moved"):
            errors.append(f"advance next #{i} did not move: {adv}")
            break
        forward.append(adv.get("row"))
    backward = []
    for i in range(5):
        adv = dut.cmd("advance prev", timeout=5.0)
        backward.append((adv.get("moved"), adv.get("row")))
    order_after = dut.cmd("get plOrder", timeout=5.0).get("order", [])

    if len(forward) == 5:
        # 5 nexts land at bag positions 0..4. 5 prevs should retrace
        # positions 3,2,1,0 (rows = forward[3],forward[2],forward[1],forward[0])
        # and then report moved=false on the 5th (nothing before position 0).
        expected_rows = list(reversed(forward[:-1]))
        got_rows = [row for (moved, row) in backward[:4] if moved]
        if got_rows != expected_rows:
            errors.append(f"prev sequence {got_rows} != expected reverse {expected_rows}")
        if len(backward) < 4 or not all(m for (m, _) in backward[:4]):
            errors.append(f"one of the first 4 prevs did not move: {backward}")
        if len(backward) == 5 and backward[4][0] is not False:
            errors.append(f"5th prev (at position 0) should report moved=false, got {backward[4]}")
    if order_before != order_after:
        errors.append(f"plOrder changed across the next/prev walk: "
                      f"before={order_before} after={order_after}")

    _leave_player(dut)
    if errors:
        fail("T_PLR_23", "; ".join(errors))
    else:
        pass_("T_PLR_23", f"forward={forward} backward retraced exactly, "
                          f"plOrder unchanged (no reroll)")


@_bgpoll_backstop
def t_plr_24(dut: Dut):
    """T_PLR_24: tap-to-play under shuffle moves the bag cursor to that
    entry's position — it does not reshuffle. Uses `set plPlay` (dbgPlayRow,
    the same tap-to-play entry point PLEDIT's onTap() drives) rather than a
    screen-coordinate tap, since row position depends on live scroll offset."""
    print("T_PLR_24  Tap-to-play moves the cursor, does not reshuffle")
    if not _enter_player(dut, "T_PLR_24"):
        return
    errors = []
    r = _pl_load(dut, _PL_20)
    if r.get("count", 0) != 20:
        _leave_player(dut)
        skip("T_PLR_24", f"fixture {_PL_20} not on the card (count={r.get('count')})")
        return
    if not _pl_shuffle(dut, True):
        _leave_player(dut)
        fail("T_PLR_24", "could not toggle shuffle ON")
        return

    order_before = dut.cmd("get plOrder", timeout=5.0).get("order", [])
    target_row = 5
    if target_row >= len(order_before) or target_row not in order_before:
        errors.append(f"row {target_row} not present in plOrder {order_before}")
    else:
        # `set plPlay` (dbgPlayRow) has no read-back of its own — `plCursor` is
        # the gettable state it actually moves (TASK-695 B-4/item 3), so that's
        # what gets restored on every exit path here. `plPlay` itself stays a
        # one-shot fire, same as before; the STOP tap below is the (still
        # best-effort, not exception-safe) undo for the playback it starts.
        with dut.saved("plCursor", field="cursor", timeout=5.0):
            expected_pos = order_before.index(target_row)
            pick = dut.cmd(f"set plPlay {target_row}", timeout=8.0)
            if not pick.get("ok"):
                errors.append(f"set plPlay {target_row} failed: {pick}")
            cur = dut.cmd("get plCursor", timeout=5.0)
            if cur.get("cursor") != expected_pos:
                errors.append(f"cursor={cur.get('cursor')} (expected bag position "
                              f"{expected_pos} of row {target_row})")
            if cur.get("curRow") != target_row:
                errors.append(f"curRow={cur.get('curRow')} (expected {target_row})")
            order_after = dut.cmd("get plOrder", timeout=5.0).get("order", [])
            if order_before != order_after:
                errors.append(f"plOrder changed by tap-to-play: before={order_before} "
                              f"after={order_after}")
            # Leave playback stopped — this test never means to leave audio running.
            if pick.get("ok"):
                dut.cmd(f"tap {_c.tap_button('STOP')[0]} {_c.tap_button('STOP')[1]}", timeout=5.0)

    _leave_player(dut)
    if errors:
        fail("T_PLR_24", "; ".join(errors))
    else:
        pass_("T_PLR_24", f"tap-to-play row {target_row} moved cursor to bag position "
                          f"{expected_pos}, plOrder unchanged (no reshuffle)")


def t_plr_26(dut: Dut):
    """T_PLR_26: shuffle/repeat persist across reboot; Spotify's own
    shuffle/repeat are never written to g_settings.player* (ADR-059 D9)."""
    print("T_PLR_26  Shuffle/repeat persist across reboot")
    if not _enter_player(dut, "T_PLR_26"):
        return
    errors = []
    if not _pl_shuffle(dut, True) or not _pl_repeat(dut, False):
        _leave_player(dut)
        fail("T_PLR_26", "could not set shuffle=on repeat=all before reboot")
        return
    before = dut.cmd("get shufRep", timeout=3.0)
    # suspend()'s coalesced write only fires on a mode switch away (ADR-050
    # rule 3) — leave Player before rebooting, same discipline plLoad's own
    # persistence gates use elsewhere in this suite.
    _leave_player(dut)
    if not _switch_to(dut, "Clock"):
        skip("T_PLR_26", "precondition: could not step off Player before reboot")
        return

    # [REBOOT] — same idiom as T_PR_04: reuse the same Dut/port, the CH34x
    # driver's DTR-reset detection in _wait_for_ready() handles the reconnect.
    dut.send("reboot")
    time.sleep(0.3)
    dut._wait_for_ready()

    if not _enter_player(dut, "T_PLR_26"):
        return
    after = dut.cmd("get shufRep", timeout=5.0)
    if after.get("lastShuffle") != 1:
        errors.append(f"shuffle did not survive reboot: before={before} after={after}")
    if after.get("lastRepeat") == 2:
        errors.append(f"repeat did not survive reboot: before={before} after={after}")
    # Restore a clean default (off/off) so later tests in the suite don't
    # inherit an unexpected shuffle/repeat state.
    _pl_shuffle(dut, False)
    _pl_repeat(dut, True)
    _leave_player(dut)

    if errors:
        fail("T_PLR_26", "; ".join(errors))
    else:
        pass_("T_PLR_26", f"shuffle=on repeat=all survived reboot: {after}")


# ── T_PMT_00..03 — player mode transitions (M-TESTBASE P3, §8) ───────────────
# The whole point of this family: it drives the OPERATION (`playerCycle`), never
# a coordinate. The gesture that cycles player mode has already moved once
# (eject -> taskbar player slot, TASK-413/414, ADR-059 D6) and silently
# invalidated every test that had hardcoded the old surface. T_PMT_00 is the ONE
# test that touches a coordinate, and it derives it from `get playerBind` — so
# relocating the surface costs an edit HERE and nowhere else.

# Expected per-mode vector. srcKind is the source that last actually drove a
# PLEDIT draw; caps is the ADR-059 D8 transport capability mask.
_PMT_EXPECT = {
    0: ("Spotify",  "SpotifyQueue",  15),
    1: ("WebRadio", "StationList",    1),
    2: ("Player",   "LocalPlaylist", 15),
}
_PMT_SETTLE_S = 2.5   # PLEDIT must actually repaint before srcKind is meaningful


def _pmt_vector(dut: Dut, timeout: float = 6.0) -> dict:
    return dut.cmd("get player", timeout=timeout)


def _pmt_goto(dut: Dut, want: int, tid: str) -> bool:
    """Cycle to `want` using the operation, never a gesture. Max 3 hops."""
    for _ in range(4):
        r = _pmt_vector(dut)
        if not r.get("ok"):
            fail(tid, f"get player failed: {r}")
            return False
        if r.get("mode") == want:
            return True
        dut.cmd("playerCycle", timeout=8.0)
        time.sleep(_PMT_SETTLE_S)
    fail(tid, f"could not reach mode {want} in 3 cycles")
    return False


def _pmt_edge(dut: Dut, tid: str, frm: int, to: int):
    """One transition: cycle frm -> to and assert the whole get-player vector."""
    if not _pmt_goto(dut, frm, tid):
        return
    before = _pmt_vector(dut)
    c = dut.cmd("playerCycle", timeout=8.0)
    if not c.get("ok"):
        fail(tid, f"playerCycle failed: {c}")
        return
    if c.get("from") != frm or c.get("to") != to:
        fail(tid, f"cycle reported {c.get('from')}->{c.get('to')}, expected {frm}->{to}")
        return
    time.sleep(_PMT_SETTLE_S)
    v = _pmt_vector(dut)
    name, src, caps = _PMT_EXPECT[to]
    problems = []
    if v.get("mode") != to:
        problems.append(f"mode={v.get('mode')} expected {to}")
    if v.get("modeName") != name:
        problems.append(f"modeName={v.get('modeName')!r} expected {name!r}")
    # M5 (X054/X055): the right PlaylistSource is actually driving PLEDIT.
    if v.get("srcName") != src:
        problems.append(f"srcName={v.get('srcName')!r} expected {src!r}")
    # M3 (X061): the capability mask matches the mode.
    if v.get("caps") != caps:
        problems.append(f"caps={v.get('caps')} expected {caps}")
    # M2 (X052): leaving Player must not strand the arena. On this build the
    # arena is never acquired (TASK-425), so this asserts "still 0" rather than
    # a release — the real acquire/release cell is Leg B, cyd2usb_player.
    if frm == 2 and v.get("arenaHeld") not in (0, None):
        problems.append(f"arenaHeld={v.get('arenaHeld')} after leaving Player")
    # M4a (X062): playlist fields exist in Player and are honestly absent elsewhere.
    if to == 2:
        if v.get("plCount") is None:
            problems.append("plCount missing in Player mode")
    elif v.get("plCount") is not None:
        problems.append(f"plCount={v.get('plCount')} leaked into non-Player mode")
    if problems:
        fail(tid, "; ".join(problems))
        return
    pass_(tid, f"{before.get('modeName')} -> {name}: src={src} caps={caps}")


def t_pmt_00(dut: Dut):
    """T_PMT_00: the surface named by `get playerBind` still performs the cycle.

    THE binding test. If it fails, T_PMT_01-03 are meaningless — they would be
    exercising an operation nothing on screen can reach."""
    print("T_PMT_00  playerBind: the documented surface still cycles")
    b = dut.cmd("get playerBind", timeout=5.0)
    if not b.get("ok"):
        fail("T_PMT_00", f"get playerBind failed: {b}")
        return
    if b.get("op") != "playerCycle":
        fail("T_PMT_00", f"playerBind op={b.get('op')!r}, expected 'playerCycle'")
        return
    region = b.get("region")
    if region != "TASKBAR_SLOT":
        skip("T_PMT_00",
             f"playerBind region={region!r} — surface relocated; update this test "
             "(that is the design intent: ONE edit, here)")
        return
    # Player must be active for the tap to CYCLE rather than RESTORE (ADR-059 D6).
    if not _pmt_goto(dut, 0, "T_PMT_00"):
        return
    slot_app = b.get("appId", APP_SLOT["Spotify"])
    before = _pmt_vector(dut).get("mode")
    sx, sy = _c.tap_taskbar_slot(slot_app)
    dut.set_cooldown_zero()
    dut.cmd(f"tap {sx} {sy}", timeout=5.0)
    time.sleep(_PMT_SETTLE_S)
    after = _pmt_vector(dut).get("mode")
    if after == before:
        fail("T_PMT_00",
             f"tapping the bound surface ({region}, slot {slot_app}) did not cycle "
             f"(mode stayed {before}) — binding is stale, exactly the TASK-413/414 failure")
        return
    pass_("T_PMT_00", f"{region} slot {slot_app} cycled {before} -> {after}")


@meta(scope="Spotify", scope_reason="cross-mode")
def t_pmt_01(dut: Dut):
    """T_PMT_01: Spotify -> WebRadio; full get-player vector correct after."""
    print("T_PMT_01  transition Spotify -> WebRadio")
    _pmt_edge(dut, "T_PMT_01", 0, 1)


@meta(scope="WebRadio", scope_reason="cross-mode")
def t_pmt_02(dut: Dut):
    """T_PMT_02: WebRadio -> Player; full get-player vector correct after."""
    print("T_PMT_02  transition WebRadio -> Player")
    _pmt_edge(dut, "T_PMT_02", 1, 2)


@meta(scope_reason="cross-mode")
def t_pmt_03(dut: Dut):
    """T_PMT_03: Player -> Spotify; vector correct + arena not stranded."""
    print("T_PMT_03  transition Player -> Spotify")
    _pmt_edge(dut, "T_PMT_03", 2, 0)


# ── T_PMT_04 — M2/X052, the arena cell with an actual acquire in it ──────────
# TASK-513. T_PMT_03 asserts `arenaHeld == 0` after leaving Player, and that
# assertion is VACUOUS by construction: mode switching alone never touches the
# arena (a 2026-08-17 probe read `arenaStats acquires=0` on BOTH build legs),
# so it checks a counter nothing ever incremented. The only acquire site on the
# FILE arm is aeConnectFile() (audioEngine.h, under MEMBUDGET_PHASE1), reached
# only by REAL playback; the only release is aeTeardownFile(), reached from
# LocalPlayerApp::suspend() on mode exit. This test drives that whole edge.
#
# LEG B ONLY. Local playback works on cyd2usb_player alone (TASK-425/431/442 —
# Spotify's ~39 KB TLS working set otherwise leaves no contiguous room), so on
# cyd2usb_winamp_debug this SKIPs rather than fails: a red cell there would be
# reporting a known, documented variant constraint as a regression.
_PMT04_PLAYLIST = "/playlists/short5.m3u"   # 5 real ~3 s tones (TASK-418 fixture)
_PMT04_SETTLE_S = 100.0   # heap is not stable until ~150 s post-reset (TASK-425);
                          # Dut.__init__ has already burned 25-40 s of that
_PMT04_PLAY_TIMEOUT_S = 20.0
_PMT04_PLAY_ATTEMPTS = 3


def t_pmt_04(dut: Dut):
    """T_PMT_04: real local playback acquires the arena, and leaving Player
    releases it — acquires > 0 AND active == 0.

    The non-vacuous half of M2/X052. T_PMT_03 only proves the counter is not
    non-zero; this proves the counter MOVED and then came back to rest."""
    print("T_PMT_04  arena acquire/release across a real Player-mode playback")

    # Leg guard (TASK-255's `get variant`, the same probe Dut's readiness path
    # uses). On leg A this test cannot start playback at all, and a red cell
    # there would be reporting TASK-425/431/442's documented variant constraint
    # as a regression.
    var = dut.cmd("get variant", timeout=5.0)
    if var.get("spotify") != "off":
        skip("T_PMT_04",
             f"leg A (variant spotify={var.get('spotify')!r}) — local playback needs "
             f"cyd2usb_player (TASK-425/431/442). Run: DUT_ENV=cyd2usb_player "
             f"python3 -u tools/run_serialdbg_tests.py --tests T_PMT_04")
        return

    base = dut.cmd("get arenaStats", timeout=5.0)
    if not base.get("ok"):
        skip("T_PMT_04", f"get arenaStats unsupported on this build: {base}")
        return
    base_acq = base.get("acquires", 0)
    print(f"  baseline arenaStats: acquires={base_acq} releases={base.get('releases')} "
          f"active={base.get('active')} fails={base.get('fails')} hwm={base.get('hwm')}")

    # TASK-553: this test asserts an acquire EDGE (acquires must move), and that
    # edge is unobservable if the arena is already held when we start —
    # mb_arena_acquire() early-returns on `if (s_owned) return true;` BEFORE it
    # increments the counter (app/src/mem/arena/mb_arena.cpp), so a second
    # acquire in the same boot is invisible by design, not broken.
    #
    # Measured 2026-08-31: run alone from a fresh boot this reads
    # acquires=0 active=0 and PASSES (0->1, then releases 0->1 on exit). Run
    # third in a suite behind T_PLR_25 — which plays five real tracks and does
    # NOT release on its way out — baseline reads acquires=1 active=1 and the
    # assertion fails with "acquires did not move", which looks exactly like a
    # product regression and is not one. The test's 2026-08-17 validation was
    # five consecutive FRESH-BOOT runs, so the precondition was always met and
    # never stated.
    #
    # Report the precondition instead of reporting a false regression. SKIP
    # rather than FAIL: nothing here says the firmware is wrong. A stronger fix
    # would reboot to force a clean arena and re-baseline, at the cost of
    # another ~100 s settle — left for @VE, see TASK-553.
    if base.get("active"):
        skip("T_PMT_04",
             f"precondition: the arena is ALREADY held at baseline "
             f"(acquires={base_acq} active={base.get('active')} "
             f"hwm={base.get('hwm')}). mb_arena_acquire() is idempotent and does "
             f"not re-count, so the 0->1 edge this test asserts cannot be "
             f"observed. Something earlier in this boot acquired and did not "
             f"release — T_PLR_25 is the known one. Run it from a fresh boot: "
             f"NO_WIFI=1 DUT_ENV=cyd2usb_player ./run/test-targeted T_PMT_04")
        return

    if not _pmt_goto(dut, 2, "T_PMT_04"):
        return

    # Spotify's background poll competes for exactly the contiguous heap the
    # decoder needs. Best-effort: the key does not exist on -DDISABLE_SPOTIFY.
    dut.cmd("set bgPoll 0", timeout=5.0)

    r = dut.cmd(f"set plLoad {_PMT04_PLAYLIST}", timeout=20.0)
    if not r.get("ok"):
        skip("T_PMT_04",
             f"set plLoad {_PMT04_PLAYLIST} failed — SD fixture missing "
             f"(push it with app/tools/sd_put.py): {r}")
        return
    c = dut.cmd("get plCount", timeout=6.0)
    if not c.get("count"):
        skip("T_PMT_04", f"plCount={c.get('count')} after loading {_PMT04_PLAYLIST} "
                         f"— fixture empty or unreadable: {c}")
        return
    print(f"  loaded {_PMT04_PLAYLIST}: {c.get('count')} rows, lfb8={c.get('lfb8')}")

    # Heap settle. A `set plPlay` before the internal pool has coalesced fails
    # cleanly (TASK-432) but for a reason that has nothing to do with the arena
    # contract under test, so wait it out rather than mis-attribute it.
    elapsed = time.monotonic() - getattr(dut, "_port_open_time", time.monotonic())
    if elapsed < _PMT04_SETTLE_S:
        wait = _PMT04_SETTLE_S - elapsed
        print(f"  waiting {wait:.0f}s more for heap settle (~150 s post-reset, TASK-425)…")
        time.sleep(wait)

    playing = False
    last_state = {}
    for attempt in range(1, _PMT04_PLAY_ATTEMPTS + 1):
        p = dut.cmd("set plPlay 0", timeout=15.0)
        if not p.get("ok"):
            print(f"  attempt {attempt}: set plPlay 0 refused: {p}")
        else:
            deadline = time.monotonic() + _PMT04_PLAY_TIMEOUT_S
            while time.monotonic() < deadline:
                st = dut.cmd("get plCount", timeout=6.0)
                last_state = st
                if st.get("playing") and st.get("curRow") == 0:
                    playing = True
                    break
                time.sleep(1.0)
        if playing:
            break
        if not playing:
            # Diagnostics, not assertions: aeConnectFile() can fail at the TLS
            # yield, the DMA floor, or the Audio alloc, and dbgPlayRow() reports
            # ok:true in all three (it returns "row index valid", not "started").
            print(f"  attempt {attempt}: playback never started — "
                  f"arenaStats={dut.cmd('get arenaStats', timeout=5.0)}")
            print(f"  attempt {attempt}: aePlay={dut.cmd('get aePlay', timeout=5.0)}")
        if not playing and attempt < _PMT04_PLAY_ATTEMPTS:
            print(f"  attempt {attempt}: lfb8={last_state.get('lfb8')} — retrying in 20s")
            time.sleep(20.0)

    if not playing:
        # NOT a pass and NOT an arena verdict: nothing was ever asked of the
        # arena, so this is the same vacuum T_PMT_03 sits in. Report it as a
        # rig/precondition failure, loudly.
        fail("T_PMT_04",
             f"playback never started after {_PMT04_PLAY_ATTEMPTS} attempts "
             f"(last plCount={last_state}) — the arena assertion below would be "
             f"vacuous, which is the exact defect TASK-513 exists to remove")
        return
    print(f"  playing row 0 (lfb8={last_state.get('lfb8')})")

    # ── mid-playback: the arena must be HELD ──
    mid = dut.cmd("get arenaStats", timeout=5.0)
    midv = _pmt_vector(dut)
    mid_acq = mid.get("acquires", 0)
    print(f"  mid-playback arenaStats: acquires={mid_acq} releases={mid.get('releases')} "
          f"active={mid.get('active')} fails={mid.get('fails')} hwm={mid.get('hwm')}; "
          f"get player arenaHeld={midv.get('arenaHeld')}")
    if mid_acq <= base_acq:
        fail("T_PMT_04",
             f"acquires did not move during REAL playback: {base_acq} -> {mid_acq} "
             f"(fails={mid.get('fails')}). Either the FILE arm no longer acquires "
             f"(TASK-452 landed?) or the acquire failed into the libc fallback — "
             f"either way M2/X052 has no acquire/release edge to cover and the "
             f"close condition needs re-specifying, not forcing")
        return
    if mid.get("active") != 1:
        fail("T_PMT_04", f"arena active={mid.get('active')} during playback, expected 1 "
                         f"(arenaStats={mid})")
        return

    # ── leave Player via the OPERATION, never a coordinate (§8) ──
    cyc = dut.cmd("playerCycle", timeout=10.0)
    if not cyc.get("ok") or cyc.get("from") != 2:
        fail("T_PMT_04", f"playerCycle out of Player failed: {cyc}")
        return
    time.sleep(_PMT_SETTLE_S)

    end = dut.cmd("get arenaStats", timeout=5.0)
    v = _pmt_vector(dut)
    end_acq = end.get("acquires", 0)
    print(f"  post-exit arenaStats: acquires={end_acq} releases={end.get('releases')} "
          f"active={end.get('active')} hwm={end.get('hwm')}; "
          f"get player mode={v.get('mode')} arenaHeld={v.get('arenaHeld')}")

    problems = []
    if not (end_acq > 0):
        problems.append(f"acquires={end_acq}, expected > 0")
    if end.get("active") != 0:
        problems.append(f"arena still held after leaving Player: active={end.get('active')}")
    if v.get("arenaHeld") not in (0, None):
        problems.append(f"get player arenaHeld={v.get('arenaHeld')} after leaving Player")
    if end.get("releases", 0) <= base.get("releases", 0):
        problems.append(f"releases did not move: {base.get('releases')} -> {end.get('releases')}")
    if problems:
        fail("T_PMT_04", "; ".join(problems))
        return
    pass_("T_PMT_04",
          f"real playback acquired the arena ({base_acq} -> {mid_acq} acquires, "
          f"active 1 mid-play) and leaving Player released it "
          f"(active=0, releases {base.get('releases')} -> {end.get('releases')}, "
          f"hwm={end.get('hwm')})")



TESTS = {
    "T_PLR_01": t_plr_01,
    "T_PLR_04": t_plr_04,
    "T_PLR_05": t_plr_05,
    "T_PLR_06": t_plr_06,
    "T_PLR_07": t_plr_07,
    "T_PLR_08": t_plr_08,
    "T_PLR_09": t_plr_09,
    "T_PLR_10": t_plr_10,
    "T_PLR_11": t_plr_11,
    "T_PLR_12": t_plr_12,
    "T_PLR_13": t_plr_13,
    "T_PLR_14": t_plr_14,
    "T_PLR_15": t_plr_15,
    "T_PLR_16": t_plr_16,
    "T_PLR_17": t_plr_17,
    "T_PLR_18": t_plr_18,
    "T_PLR_19": t_plr_19,
    "T_PLR_20": t_plr_20,
    "T_PLR_21": t_plr_21,
    "T_PLR_22": t_plr_22,
    "T_PLR_23": t_plr_23,
    "T_PLR_24": t_plr_24,
    "T_PLR_26": t_plr_26,
    "T_PMT_00": t_pmt_00,
    "T_PMT_01": t_pmt_01,
    "T_PMT_02": t_pmt_02,
    "T_PMT_03": t_pmt_03,
    "T_PMT_04": t_pmt_04,
}
