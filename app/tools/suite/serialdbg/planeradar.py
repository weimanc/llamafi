"""PlaneRadar app tests -- M-PLANERADAR (TASK-307/355/357). Split from
run_serialdbg_tests.py, TASK-480."""

import functools
import time

from lib.dut import Dut
from lib.results import pass_, fail, skip, unmet
from app_ids_gen import APP_SLOT
from suite.serialdbg._meta import meta
from suite.serialdbg._helpers import (
    _restore_spotify, _ring_events, _switch_to, _wait_shell_not_busy, _bgpoll_suspended,
)


# ── M-PLANERADAR DUT validation (TASK-307, parent doc exit criteria 1-6) ─────
# T_PR_01: switch round-trip (sanity, mirrors T_WX_01/T_CX_01).
# T_PR_02: exit criterion 1 — live render within one poll of app entry.
# T_PR_03: exit criterion 2a — range tap cycles 5→10→15→25→5.
# T_PR_04: exit criterion 2b — range persists across reboot [REBOOT].
# T_PR_05: exit criterion 3 — fetch error → side-strip code, stays responsive, recovers [NETWORK][SLOW].
# T_PR_06: exit criterion 6 — synthetic injection render test, no network.
# Exit criterion 4 (30-min coexistence soak) is T_PR_SOAK (separate — [SLOW][MANUAL-length]).
# Exit criterion 5 (taskbar full-cycle scroll, new 12th slot) is covered by the
# EXISTING T162-T166/T242 suite unchanged — _TB_N derives from APP_SLOT["WebRadio"],
# which already grew by one now that PlaneRadar sits before WebRadio in APP_ORDER.

# Disc center — planeRadarApp.h PR_CX/PR_CY, frozen in phase0-preview-ui.md Results.
PR_CX, PR_CY = 120, 120

def t_pr_01(dut: Dut):
    """T_PR_01: Spotify→PlaneRadar→Spotify round-trip; appId correct at each step."""
    print("T_PR_01  PlaneRadarApp switch round-trip")
    if not _restore_spotify(dut):
        skip("T_PR_01", "precondition: could not restore Spotify")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        switched = _switch_to(dut, "PlaneRadar", timeout=15.0)
    if not switched:
        fail("T_PR_01", "did not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    if not _restore_spotify(dut):
        fail("T_PR_01", "PlaneRadar→Spotify switch-back failed")
        return
    pass_("T_PR_01", "Spotify→PlaneRadar→Spotify round-trip confirmed via get appId")


def t_pr_02(dut: Dut):
    """T_PR_02 (exit criterion 1): live aircraft render within one poll of app entry.
    resume() enqueues a fetch immediately; 'live render' is observed via
    `get activeError`'s `connecting` field (PlaneRadarApp::isConnecting() = !
    _everHadResult) going false — NOT prLastHttp==200. DUT diagnostic (2026-07-11)
    showed fetchPlaneRadar() only ever writes a non-zero errorCode on FAILURE;
    a successful fetch leaves PlaneRadarResult's default-constructed errorCode=0
    untouched (the raw HTTP 200 only appears in a LOG_D line, never in the
    result struct dbgGet reads) — so prLastHttp==0 is genuinely ambiguous
    between 'never fetched' and 'fetched fine', and waiting for it to equal
    200 can never pass. 90s budget (not PR_POLL_MS+margin): a 403-wedged
    Spotify holds tlsYield() in overdue-poll retries (same contention
    test_fetch_stress.py documents for weather/crypto/stock — TASK-244), so a
    'first poll' can legitimately take much longer than the 10s cadence alone
    would suggest."""
    print("T_PR_02  Live render within one poll of app entry")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_02", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    deadline = time.monotonic() + 90.0
    connecting = True
    while time.monotonic() < deadline:
        r = dut.cmd("get activeError", timeout=3.0)
        connecting = r.get("connecting", True)
        if not connecting:
            break
        time.sleep(1.0)
    http_r = dut.cmd("get prLastHttp", timeout=3.0)
    count_r = dut.cmd("get prAircraftCount", timeout=3.0)
    err_r = dut.cmd("get activeError", timeout=3.0)
    _restore_spotify(dut)
    if connecting:
        fail("T_PR_02", f"isConnecting() still true after 90s — first poll never "
                        f"resolved (prLastHttp={http_r.get('val')})")
        return
    if err_r.get("active"):
        fail("T_PR_02", f"first poll resolved but as an error (prLastHttp={http_r.get('val')})")
        return
    pass_("T_PR_02", f"first poll resolved ok (connecting->false), "
                     f"prAircraftCount={count_r.get('val')}, prLastHttp={http_r.get('val')}")


def t_pr_03(dut: Dut):
    """T_PR_03 (exit criterion 2a): tap disc 4x cycles 5→10→15→25→5 (wrap).
    Injects a synthetic aircraft first: handleInput()'s range-change branch only
    calls dataTask::enqueuePlaneRadar() when !_injected, so under real polling each
    tap re-arms hasPendingAsync() and (with tlsYield() stalled behind a 403 Spotify)
    the shell-busy gate can silently swallow the NEXT tap before the fetch resolves
    — exactly the failure mode observed on the first DUT run (range stuck at 10
    after tap #1). Injection makes the tap-cycle observation independent of network
    state, which is what this exit criterion is actually about."""
    print("T_PR_03  Range tap cycles 5->10->15->25->5")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_03", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    dut.cmd("set prInjectAircraft TEST01,A320,52.31,4.76,12.5,90,90,250,15000", timeout=3.0)
    dut.cmd("set prRange 5", timeout=3.0)
    dut.set_cooldown_zero()
    seen = []
    for _ in range(4):
        _wait_shell_not_busy(dut, timeout_s=5.0)
        dut.cmd(f"tap {PR_CX} {PR_CY}", timeout=3.0)
        time.sleep(0.2)
        r = dut.cmd("get prRange", timeout=3.0)
        seen.append(r.get("val"))
        dut.set_cooldown_zero()
    dut.cmd("set prClearInject 1", timeout=3.0)
    _restore_spotify(dut)
    if seen != [10, 15, 25, 5]:
        fail("T_PR_03", f"range sequence={seen}, expected [10, 15, 25, 5]")
        return
    pass_("T_PR_03", f"range sequence 5->{seen} confirmed")


# TASK-705: declares reboot_ready — this [REBOOT] id's own subject
# (prRange persistence) is not itself in _meta.OPS, so reboot_ready is the
# only op TRUE for this body; the harness's own Dut._wait_for_ready() is what
# actually satisfies the op's PRIMITIVE requirement (see
# gate/check_primitive_coverage.py's HARNESS_PRIMITIVES), this declaration is
# composite bookkeeping, not what clears P1 for the op.
@meta(ops=("reboot_ready",))
def t_pr_04(dut: Dut):
    """T_PR_04 (exit criterion 2b) [REBOOT]: range preset persists across reboot.
    Sets a distinctive non-default preset (25 km — default is 10 km per init()'s
    _presetIdx=1 fallback), reboots, and confirms PlaneRadar loads the same preset
    from settingsStorage instead of falling back to default."""
    print("T_PR_04  Range persists across reboot [REBOOT]")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_04", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    dut.cmd("set prRange 25", timeout=3.0)
    r_pre = dut.cmd("get prRange", timeout=3.0)
    if r_pre.get("val") != 25:
        skip("T_PR_04", f"could not set prRange=25 pre-reboot, got {r_pre.get('val')}")
        return
    dut.send("reboot")
    time.sleep(0.3)   # let the reset actually happen before we start reading for it
    dut.reboot_and_wait()
    if not _switch_to(dut, "PlaneRadar", timeout=15.0):
        fail("T_PR_04", "could not switch to PlaneRadar after reboot")
        _restore_spotify(dut)
        return
    r_post = dut.cmd("get prRange", timeout=3.0)
    _restore_spotify(dut)
    if r_post.get("val") != 25:
        fail("T_PR_04", f"prRange={r_post.get('val')} after reboot, expected 25 (not persisted)")
        return
    pass_("T_PR_04", "prRange=25 held across reboot — settingsStorage persistence confirmed")


def t_pr_05(dut: Dut):
    """T_PR_05 (exit criterion 3) [NETWORK][SLOW]: fetch error -> side-strip error code,
    app stays responsive, recovers on next poll. adsb.fi's public 1 req/s courtesy
    limit means hammering triggerPlaneRadarFetch back-to-back (phase-0 measured ~33%
    429 rate at that cadence) is expected to surface a real error within a bounded
    number of rapid-fire attempts, without needing a dedicated fault-injection hook.
    Uses `get activeError`'s `active` field (PlaneRadarApp::hasError() = _prErr) as
    the error signal, NOT prLastHttp==200 — DUT diagnostic (2026-07-11) showed a
    successful fetch leaves errorCode at its default-constructed 0, so 0 is
    ambiguous between 'never fetched' and 'fetched fine' and can't be used to
    detect a transition either way. `active` is exactly what drives the side-strip/
    taskbar error indicator this criterion is actually asking about (same pattern
    T-ERR-07 uses for Stock's fetchFailed)."""
    print("T_PR_05  Fetch error -> error code, stays responsive, recovers")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_05", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    # Baseline: the first poll must resolve cleanly (connecting->false, no error)
    # before we start hammering — otherwise we can't tell a fresh error apart from
    # the app never having had a chance to succeed at all.
    baseline_deadline = time.monotonic() + 90.0
    baseline_ok = False
    while time.monotonic() < baseline_deadline:
        r = dut.cmd("get activeError", timeout=3.0)
        if not r.get("connecting", True):
            baseline_ok = (r.get("active") is False)
            break
        time.sleep(1.0)
    if not baseline_ok:
        _restore_spotify(dut)
        skip("T_PR_05", "could not establish a clean baseline poll within 90s")
        return
    saw_error = False
    error_code = None
    for _ in range(20):
        dut.cmd("set triggerPlaneRadarFetch 1", timeout=3.0)
        deadline = time.monotonic() + 12.0
        got_error = False
        while time.monotonic() < deadline:
            time.sleep(0.5)
            err = dut.cmd("get activeError", timeout=3.0)
            if err.get("active"):
                got_error = True
                break
        if got_error:
            saw_error = True
            error_code = dut.cmd("get prLastHttp", timeout=3.0).get("val")
            break
        time.sleep(1.0)
    if not saw_error:
        _restore_spotify(dut)
        skip("T_PR_05", "no fetch error surfaced in 20 rapid-fire attempts — "
                        "adsb.fi rate limit not hit this run (network-dependent)")
        return
    # App must stay responsive with an error latched (hasError()->red taskbar).
    r_alive = dut.cmd("get appId", timeout=3.0)
    if not r_alive.get("ok") or r_alive.get("name") != "PlaneRadar":
        _restore_spotify(dut)
        fail("T_PR_05", f"app unresponsive/switched after error code={error_code}: {r_alive}")
        return
    # Recovers on next poll: wait for activeError.active to clear.
    recovered = False
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        err = dut.cmd("get activeError", timeout=3.0)
        if err.get("active") is False:
            recovered = True
            break
        time.sleep(2.0)
    _restore_spotify(dut)
    if not recovered:
        fail("T_PR_05", f"error code={error_code} latched but did not recover (activeError) within 30s")
        return
    pass_("T_PR_05", f"error code={error_code} -> activeError.active=true, responsive, "
                     f"recovered -> activeError.active=false")


def t_pr_06(dut: Dut):
    """T_PR_06 (exit criterion 6): synthetic-injection render test passes without network.
    prInjectAircraft isolates tick() from the real fetch/poll cycle (same pattern as
    TASK-276's injected-state lesson), so this must hold even with WiFi torn down —
    injects 3 aircraft, confirms prAircraftCount==3, prLastHttp stays whatever it was
    (no fetch attempted), then clears and confirms count returns to 0."""
    print("T_PR_06  Synthetic-injection render test (no network)")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PR_06", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    records = "TEST01,A320,52.31,4.76,12.5,90,90,250,15000;" \
              "TEST02,B738,52.28,4.80,8.0,270,270,180,8000;" \
              "TEST03,C172,52.30,4.75,3.0,0,0,90,2000"
    dut.cmd(f"set prInjectAircraft {records}", timeout=3.0)
    r_count = dut.cmd("get prAircraftCount", timeout=3.0)
    dut.cmd("set prClearInject 1", timeout=3.0)
    time.sleep(0.2)
    r_after = dut.cmd("get prAircraftCount", timeout=3.0)
    _restore_spotify(dut)
    if r_count.get("val") != 3:
        fail("T_PR_06", f"prAircraftCount={r_count.get('val')} after injecting 3, expected 3")
        return
    pass_("T_PR_06", f"injected 3 aircraft -> prAircraftCount=3; "
                     f"prClearInject -> count={r_after.get('val')} (real poll resumes)")


# ── TASK-355 / M-PR-MOTION Item A: poll-interval setting (prPollSec) ─────────
# T_PRM_01: dbg set/get round-trip (1/10/30) + out-of-range clamp + reboot
#           persistence [REBOOT].
# T_PRM_02: setting=1 → inter-fetch spacing settles at fetch-completion pace
#           (~4–5 s, TASK-313 edge pacing), no enqueue pile-up, no Spotify
#           heartbeat regression over a 5-min window [NETWORK][SLOW].

# dataTask.h FetchType — PlaneRadar's dispatch id as reported by `get dataq`
# inFlight (keep in sync with the enum; -1 = idle).
PR_FETCH_TYPE = 8

# TASK-705: declares reboot_ready — same reasoning as T_PR_04 above: its own
# subject (prPollSec round-trip/clamp/persistence) is not in _meta.OPS.
@meta(ops=("reboot_ready",))
def t_prm_01(dut: Dut):
    """T_PRM_01 (TASK-355) [REBOOT]: prPollSec slider value round-trips via dbg
    set/get at 1 / 10 / 30 (full slider range: min / default / max), clamps an
    out-of-range set (99 -> 30, mirroring load()'s corrupt-file guard), and
    persists across a reboot.

    No app switch needed: `set/get prPollSec` dispatch to the file-scope
    g_PlaneRadarApp instance (main.cpp planeRadarDbgGet/Set are called
    unconditionally) and the value is g_settings-backed, not app-instance
    state. Persistence expectation: dbgSet("prPollSec") calls
    SettingsStorage::save() itself (same idiom as _setPreset() for prRange /
    T_PR_04), so the value must survive a reboot with no further action; the
    on-screen slider's own Release path rides AppsSection::saveSettings()
    identically. Restores the default (10) at the end."""
    print("T_PRM_01  prPollSec set/get round-trip + clamp + persistence [REBOOT]")
    for v in (1, 10, 30):
        dut.cmd(f"set prPollSec {v}", timeout=3.0)
        r = dut.cmd("get prPollSec", timeout=3.0)
        if r.get("val") != v:
            fail("T_PRM_01", f"set {v} -> get returned {r.get('val')}")
            dut.cmd("set prPollSec 10", timeout=3.0)
            return
    # Out-of-range set clamps to the slider max (dbg mirror of the load guard).
    dut.cmd("set prPollSec 99", timeout=3.0)
    r = dut.cmd("get prPollSec", timeout=3.0)
    if r.get("val") != 30:
        fail("T_PRM_01", f"set 99 -> get returned {r.get('val')}, expected clamp to 30")
        dut.cmd("set prPollSec 10", timeout=3.0)
        return
    # Persistence leg (T_PR_04 idiom): 30 is distinctive vs the default 10.
    dut.send("reboot")
    time.sleep(0.3)   # let the reset actually happen before we start reading for it
    dut.reboot_and_wait()
    r_post = dut.cmd("get prPollSec", timeout=3.0)
    dut.cmd("set prPollSec 10", timeout=3.0)   # restore default
    if r_post.get("val") != 30:
        fail("T_PRM_01", f"prPollSec={r_post.get('val')} after reboot, expected 30 (not persisted)")
        return
    pass_("T_PRM_01", "1/10/30 round-trip OK, 99->30 clamp OK, 30 held across reboot; restored to 10")


def t_prm_02(dut: Dut):
    """T_PRM_02 (TASK-355) [NETWORK][SLOW]: at prPollSec=1 the poll loop is
    fetch-completion-paced, serialized, and does not starve Spotify — 5-min
    observation window.

    The design's honest-1s contract (M-PR-MOTION 'The 1 s setting, honestly'):
    _pendingFetch already serializes fetches and TASK-313 measured ~4.3 s wall
    per device GET (Cloudflare edge pacing), so setting=1 must settle at ~4–5 s
    effective spacing — NOT at 1 s, and NOT pile up requests.

    Observables (all via `get dataq`, sampled at ~0.5 s):
      - fetch identity: inFlightMs is the dispatch-start millis stamp, so each
        distinct value seen while inFlight==PR_FETCH_TYPE is one PR fetch —
        spacing is measured start-to-start from those stamps, immune to
        sampling aliasing between back-to-back fetches.
      - pile-up: queueWaiting stays small (<=2 tolerated: other apps' bg
        fetches legitimately queue behind an in-flight PR GET; PR itself can
        never stack a second request while _pendingFetch is true).
      - Spotify heartbeat: spActMs is spotifyTask's loop-position stamp; its
        age (dataq ms - spActMs) must never exceed 120 s. Uses task activity,
        not poll success — TASK-243 (Premium lapsed, 403s) makes success-based
        checks meaningless, but a starved/deadlocked task parks the stamp.
    Bounds: median spacing in [3.0, 9.0] s (fetch-completion pace, clearly
    faster than the 10 s default), min spacing >= 1.5 s (no double-fire),
    >= 20 fetches observed (~60-75 expected at ~4-5 s over 300 s).
    Restores prPollSec=10 and Spotify at the end."""
    print("T_PRM_02  prPollSec=1 -> fetch-completion pacing, no pile-up, Spotify alive [NETWORK][SLOW]")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PRM_02", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    dut.cmd("set prPollSec 1", timeout=3.0)
    # Baseline: first poll must resolve before the window starts (T_PR_02 idiom
    # incl. its 90 s budget rationale — tlsYield contention can stretch it).
    baseline_deadline = time.monotonic() + 90.0
    baseline_ok = False
    while time.monotonic() < baseline_deadline:
        r = dut.cmd("get activeError", timeout=3.0)
        if not r.get("connecting", True):
            baseline_ok = True
            break
        time.sleep(1.0)
    if not baseline_ok:
        dut.cmd("set prPollSec 10", timeout=3.0)
        _restore_spotify(dut)
        skip("T_PRM_02", "first poll never resolved within 90s — no baseline")
        return
    window_s = 300.0
    fetch_starts = set()      # distinct inFlightMs stamps while inFlight==PR
    max_queue = 0
    max_sp_age = 0
    deadline = time.monotonic() + window_s
    while time.monotonic() < deadline:
        q = dut.cmd("get dataq", timeout=3.0)
        if q.get("ok"):
            if q.get("inFlight") == PR_FETCH_TYPE and q.get("inFlightMs"):
                fetch_starts.add(q["inFlightMs"])
            max_queue = max(max_queue, q.get("queueWaiting", 0))
            if q.get("spActMs") and q.get("ms"):
                max_sp_age = max(max_sp_age, q["ms"] - q["spActMs"])
        time.sleep(0.5)
    # Restore before judging — the window is over either way.
    dut.cmd("set prPollSec 10", timeout=3.0)
    still_alive = dut.cmd("get appId", timeout=3.0)
    _restore_spotify(dut)
    starts = sorted(fetch_starts)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    if not still_alive.get("ok"):
        fail("T_PRM_02", f"DUT shell unresponsive after 5-min window: {still_alive}")
        return
    if len(starts) < 20:
        fail("T_PRM_02", f"only {len(starts)} PR fetch starts observed in 300s — "
                         f"expected >=20 at fetch-completion pace (gaps={gaps[:10]})")
        return
    gaps_sorted = sorted(gaps)
    median_gap = gaps_sorted[len(gaps_sorted) // 2]
    min_gap = gaps_sorted[0]
    if min_gap < 1500:
        fail("T_PRM_02", f"min inter-fetch gap {min_gap}ms < 1.5s — double-fire / "
                         f"_pendingFetch serialization broken")
        return
    if not (3000 <= median_gap <= 9000):
        fail("T_PRM_02", f"median inter-fetch gap {median_gap}ms outside [3s,9s] — "
                         f"not fetch-completion-paced ({len(starts)} fetches)")
        return
    if max_queue > 2:
        fail("T_PRM_02", f"queueWaiting peaked at {max_queue} (>2) — enqueue pile-up")
        return
    if max_sp_age > 120000:
        fail("T_PRM_02", f"spotifyTask activity stamp went {max_sp_age}ms stale (>120s) — "
                         f"heartbeat regression under continuous PR fetching")
        return
    pass_("T_PRM_02", f"{len(starts)} fetches in 300s, median gap {median_gap}ms "
                      f"(min {min_gap}ms), queueWaiting peak {max_queue}, "
                      f"max spotify activity age {max_sp_age}ms")


# ── TASK-357 / EXP-014 graduation: dr-damped(tau=2) motion smoothing ─────────
# T_PRI_01: injected continuity pair (same callsign, shifted fix) shows a
#           nonzero, un-snapped offset that decays toward 0 with tau=2s.

def _pr_inject_custody(fn):
    """Clear PlaneRadar's aircraft injector on EVERY exit path of the body.

    `set prInjectAircraft` sets `PlaneRadarApp::_injected`, which guards every
    real-fetch site and is cleared only by `set prClearInject 1` or `init()`,
    not by `resume()`. T_PRI_01 cleared it on entry but never on exit. TASK-635's
    boundary check FAILed it for that in 4 of 4 full runs (2026-09-13/14).
    The disarm is a different key from the arm, so the manager is armed with the
    clear itself: `prClearInject 1` on entry (what the body already did first)
    and again on exit.
    """
    @functools.wraps(fn)
    def wrapper(dut: Dut):
        with dut.injected("prClearInject", 1, clear_to=1):
            return fn(dut)
    return wrapper


# TASK-705: declares pr_inject. This id's whole subject IS the injected
# continuity pair's offset decay/settle behaviour — exactly `_meta.OPS`'s
# definition — and nothing else in the closed vocabulary (it does not touch
# prClearInject's re-arm-a-real-fetch behaviour; _pr_inject_custody's own
# clear-on-exit is restore bookkeeping, not an assertion).
@meta(ops=("pr_inject",))
@_pr_inject_custody
def t_pri_01(dut: Dut):
    """T_PRI_01 (TASK-357): dr-damped(tau=2) offset continuity + decay via the
    `get prInterp` observable (motion-slot 0: offsetPx, fixAgeMs, tracked).

    Forces prRange=25 (widest preset, smallest px/km) first — the offset is
    computed in *screen px*, so a fixed lat/lon delta's px magnitude scales
    with zoom; a tight preset can push a delta past PR_INTERP_SNAP_PX=40 and
    trigger the re-appearance snap instead of the continuity path this test
    means to exercise (found during initial DUT verification: the same
    injected pair read offsetPx=0 at whatever preset a prior test session had
    left persisted, vs ~13px at the test's intended preset — a leftover-state
    trap, not a code bug, but worth pinning the zoom explicitly here).

    Sequence: inject fix1 (first sighting -> offset must be 0, no continuity
    claim); inject fix2 for the SAME callsign, shifted ~0.01 deg lon (-> offset
    must jump to a nonzero, un-snapped value, continuity is exactly the
    OLD-predicted-vs-NEW-fix delta at that instant); poll prInterp at ~1 tau
    (2s) and ~2 tau (4s) intervals and assert it decays (not flat, not
    re-snapped) — bounds are generous (exp(-1)=~0.37, exp(-2)=~0.14 of the
    initial reading) to tolerate serial round-trip timing jitter, not an exact
    curve-fit. Restores prRange=10 (default) and Spotify at the end."""
    print("T_PRI_01  dr-damped(tau=2) offset continuity + decay")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        skip("T_PRI_01", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    dut.cmd("set prRange 25", timeout=3.0)
    dut.cmd("set prClearInject 1", timeout=3.0)

    r0 = dut.cmd("set prInjectAircraft AAA111,A320,51.5,0.0,10,90,90,450,35000", timeout=3.0)
    if not r0.get("ok"):
        fail("T_PRI_01", f"first injection failed: {r0}")
        dut.cmd("set prRange 10", timeout=3.0); _restore_spotify(dut)
        return
    r_first = dut.cmd("get prInterp", timeout=3.0)
    if r_first.get("offsetPx", -1) != 0.0:
        fail("T_PRI_01", f"first sighting offsetPx={r_first.get('offsetPx')}, expected exactly 0 (no continuity claim)")
        dut.cmd("set prRange 10", timeout=3.0); _restore_spotify(dut)
        return

    r1 = dut.cmd("set prInjectAircraft AAA111,A320,51.5,0.01,10,90,90,450,35000", timeout=3.0)
    if not r1.get("ok"):
        fail("T_PRI_01", f"second injection failed: {r1}")
        dut.cmd("set prRange 10", timeout=3.0); _restore_spotify(dut)
        return
    r_t0 = dut.cmd("get prInterp", timeout=3.0)
    off0 = r_t0.get("offsetPx", 0.0)
    if not (0.3 <= off0 <= 39.0):
        fail("T_PRI_01", f"t=0 offsetPx={off0} — expected a nonzero, un-snapped "
                         f"continuity offset in (0.3, 39.0)px")
        dut.cmd("set prRange 10", timeout=3.0); _restore_spotify(dut)
        return

    # NOTE: prRange restore is deliberately deferred until AFTER the decay
    # reads below — _setPreset() (any prRange write) calls _repaintDisc(),
    # which zeroes _motionCount as a side effect (new scale, no continuity
    # claim — see planeRadarApp.h). Restoring here first was an earlier
    # version of this test's own bug: it wiped motion state before the decay
    # checks ran, so both later reads read back the "nothing tracked" default
    # of exactly 0.0 — decaying-looking, but for the wrong reason. Caught by
    # DUT verification during TASK-357 (2026-07-19).
    time.sleep(2.0)
    r_t1 = dut.cmd("get prInterp", timeout=3.0)
    off1 = r_t1.get("offsetPx", off0)
    time.sleep(2.0)
    r_t2 = dut.cmd("get prInterp", timeout=3.0)
    off2 = r_t2.get("offsetPx", off1)
    dut.cmd("set prRange 10", timeout=3.0)
    _restore_spotify(dut)

    if not (off1 < off0 * 0.6):
        fail("T_PRI_01", f"offset not decaying: t=0 {off0}px -> t+2s {off1}px "
                         f"(expected < 60% of t=0, tau=2s theory ~37%)")
        return
    if not (off2 < off0 * 0.3):
        fail("T_PRI_01", f"offset not settling: t=0 {off0}px -> t+4s {off2}px "
                         f"(expected < 30% of t=0, tau=2s theory ~14%)")
        return
    pass_("T_PRI_01", f"offset {off0}px -> {off1}px (t+2s) -> {off2}px (t+4s), "
                      f"decaying toward 0 (tau=2s)")


# ── T_PR_07 — prClearInject re-arms a real PlaneRadar fetch ──────────────────
# TASK-705 primitive: pr_clear_rearms_fetch. `set prClearInject 1` backdates
# _lastFetch to _forceNow() = millis() - _pollMs() (planeRadarApp.h:353,
# planeRadarApp.cpp:230), which makes tick()'s own poll gate
# `now - _lastFetch >= _pollMs()` (planeRadarApp.cpp:33) TRUE on the very next
# tick() call — so a real enqueue (a RING_ENQUEUE event with
# arg=PlaneRadar's FetchType, 8) is expected within a couple of app ticks, not
# a whole poll interval. Bound: the CURRENT g_settings.prPollSec (`get
# prPollSec`) plus 3s scheduling slack — deliberately generous, since the
# code's own arithmetic says the enqueue should be near-immediate.

@meta(ops=("pr_clear_rearms_fetch",))
def t_pr_07(dut: Dut):
    """T_PR_07: `prClearInject 1` re-arms a REAL PlaneRadar fetch, not just a
    display clear. TASK-705 primitive: pr_clear_rearms_fetch."""
    print("T_PR_07  prClearInject re-arms a real fetch")
    if not _switch_to(dut, "PlaneRadar", timeout=10.0):
        unmet("T_PR_07", "could not switch to PlaneRadar")
        _restore_spotify(dut)
        return
    try:
        poll_sec = dut.get_int("prPollSec", timeout=3.0)
    except Exception:
        poll_sec = 30   # PR_POLL_MAX_SEC fallback if the read itself fails
    r0 = dut.cmd("get dataRing", timeout=3.0)
    if not r0.get("ok"):
        _restore_spotify(dut)
        unmet("T_PR_07", f"get dataRing refused: {r0!r} — firmware without "
                         "the TASK-697 event ring")
        return
    # `set prClearInject 1` IS the mutation under test — tracked via
    # dut.injected() (R17) even though its clear_to is the same value: the
    # injector's own disarm path, per _pr_inject_custody above, is re-issuing
    # the same command, and PlaneRadarApp::_injected is already false here
    # (T_PR_07 never armed prInjectAircraft), so the arm and clear are
    # identical no-ops on exit by construction.
    bound_s = poll_sec + 3.0
    seen = False
    with dut.injected("prClearInject", 1, clear_to=1):
        deadline = time.monotonic() + bound_s
        while time.monotonic() < deadline and not seen:
            for ev in _ring_events(dut):
                if ev.get("ev") == 0 and ev.get("arg") == PR_FETCH_TYPE:   # RING_ENQUEUE
                    seen = True
                    break
            if not seen:
                time.sleep(0.5)
    _restore_spotify(dut)
    if not seen:
        fail("T_PR_07", f"no RING_ENQUEUE(PlaneRadar, arg={PR_FETCH_TYPE}) "
                        f"observed within {bound_s:.0f}s of prClearInject 1 "
                        "— the clear did not re-arm a real fetch")
        return
    pass_("T_PR_07", f"RING_ENQUEUE(PlaneRadar) observed within {bound_s:.0f}s "
                     "of prClearInject 1")


TESTS = {
    "T_PR_01": t_pr_01,
    "T_PR_02": t_pr_02,
    "T_PR_03": t_pr_03,
    "T_PR_04": t_pr_04,
    "T_PR_05": t_pr_05,
    "T_PR_06": t_pr_06,
    "T_PRM_01": t_prm_01,
    "T_PRM_02": t_prm_02,
    "T_PRI_01": t_pri_01,
    "T_PR_07": t_pr_07,
}
