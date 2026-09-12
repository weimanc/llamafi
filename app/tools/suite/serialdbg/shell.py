"""Shell / taskbar / cross-app tests. Split from run_serialdbg_tests.py, TASK-480.

Catch-all family per M-TOOLING §3: everything driving the taskbar/app-switch
shell surface rather than one specific app -- posbar/transport hit-testing
(T077-T096), PLEDIT drag mechanics (T133-T160), touch-capture (T149-T154),
taskbar scroll + tap feedback (T162-T166/T242, T_TBFB_*), the small
single-screen apps that don't warrant their own family (Matrix/GameOfLife/
Weather/Crypto -- T_MA_*/T_GOL_*/T_WX_*/T_CX_*), a cross-feature dataTask
test (T_X07_01), settings-nav (T-SET-*), ADR-042 UART/bgPoll validation
(T-UART-01/T-BGPOLL-*), the shell-busy/cooldown gate (T-BUSY-*/T-CDWN-*),
and the app-error-signal red taskbar bar (T-ERR-*).

SCOPE DECLARATIONS (TASK-570, M-TESTARCH §13.3). This module has no module seed
— it is the catch-all — so its residue seeds to `shell` and the @meta(...)
declarations below override that where the seed is wrong. The rule they were
adjudicated by, applied per id rather than by category label, is §13.3's:

  * `Spotify` (27 ids, reason `winamp-view`) — the subject is a surface of the
    Winamp window itself: posbar/transport/volume hit-testing, the PLEDIT rows
    and their drag/scroll mechanics. Delete the Spotify app and the test has
    nothing left to point at.
  * `spotify-chrome` (11, reason `shell-poll`) — the subject is the SHELL's
    handling of Spotify: poll backoff/reconnect, bgPoll suspension, the 403
    activeError signal, the busy gate entered from the Spotify slot. These
    survive the app's deletion, which is exactly §13.3's test.
  * `Settings` (6, `settings-app`) and `taskbar` (7, `taskbar-surface`) — both
    are app/shell surfaces the catch-all would otherwise mis-attribute; §13.2
    measured the Settings ids as the clearest case.
  * Everything left stays `shell`: the busy/cooldown gates, dispatch routing and
    the UART/error-signal checks. They use whatever app is convenient as a
    VEHICLE (Stock, mostly) — the subject is shell machinery, so a Stock literal
    in the body is not an attribution. That is why the AST "app name in the body"
    signal is a cross-check and never the source (§13.2).
"""

import json
import pathlib
import time

from lib.dut import Dut, NoAnswer
from lib.results import pass_, fail, skip, unmet, flake
import coords as _c
from app_ids_gen import APP_SLOT
from suite.serialdbg._meta import meta
from suite.serialdbg._helpers import (
    _restore_spotify, _switch_to, _check_residue, _RESIDUE_DISPROOF,
    _wait_shell_not_busy,
    _diag_snapshot, _tap_and_wait_log, _do_drag, _get_scroll,
    _vs_drain_until_drag, _PLEDIT_X, _PLSTART_Y, _PLEND_Y,
    _tb_precondition, _TB_X, _TB_N, _tb_get_offset, _tb_set_offset,
    _bgpoll_suspended, _poll_shell_busy, _get_vis_mode,
    _switch_to_stock, _restore_from_stock, _stock_get, _stock_ok_count,
    _wait_chart_complete, _drain_data_pipeline, _CHART_PHASE_NAMES,
    _observe_progress_atom, _progress_atom_verdict,
    _dataq_fetch_edge, _FETCH_TYPE,
)
from suite.serialdbg.webradio import _switch_to_webradio_capture_heap


# ── T077 — dead zone between posbar and transport ─────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t077(dut: Dut):
    print("T077  Dead zone posbar/transport gap")
    dut.set_cooldown_zero()
    _pb_x0, _pb_x1, _pb_y0, _pb_y1 = _c.posbar_bounds()
    _gap_y = _pb_y1 + 1 + (int(_c.S["CB_PREV_Y"]) - _pb_y1 - 1) // 2
    r = dut.cmd(f"tap {_c.tap_posbar()[0]} {_gap_y}")
    hit = r.get("hit", "")
    action = r.get("action", "")
    if hit in ("TRANSPORT", "POSBAR", "VOLUME"):
        fail("T077", f"unexpected hit={hit} action={action}")
    else:
        pass_("T077", f"hit={hit} action={action}")


# ── T078 — zero-delta drag dispatches no ACT_VOLUME ──────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t078(dut: Dut):
    """T078: a zero-delta drag over the volume zone commits no ACT_VOLUME.

    TASK-603 (WP-D D-5). The body used to end with
    `print("NOTE: verify no 'dequeued action=VOLUME' in log manually")` and
    assert only that dragState returned to D_IDLE — which a committing drag also
    does. The marker it deferred to a human DOES exist and IS greppable:
    `LOG_D("touch", "enqueued ACT_VOLUME pct=%ld", ...)` at
    app/src/winamp/winampDisplay.cpp:496 and :510, already collected by T082 and
    T151 in this same module.

    THE POSITIVE CONTROL IS NOT OPTIONAL (WP-E E-6). This is a NEGATIVE log
    assertion, and four of them in the player family treat a `_wait_for_log`
    timeout as a pass on a SUPPRESSIBLE `LOG_D` channel — so "no commit" and "no
    logging" score identically. The control drag runs FIRST: if a real,
    non-zero-delta drag does not produce the marker either, the channel is not
    carrying it and the negative half proves nothing. That is `unmet()` (BP-074:
    an assertion whose precondition never occurred is inconclusive), never a
    pass.
    """
    print("T078  Zero-delta drag → no ACT_VOLUME (with a positive control)")
    dut.set_cooldown_zero()
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        skip("T078", f"dragState={rg.get('state')} not D_IDLE")
        return

    x1, x2 = _c.vol_drag_x()
    vy = _c.vol_drag_y()
    mid = (x1 + x2) // 2
    MARK = "enqueued ACT_VOLUME"

    # ── positive control: a real drag across the zone MUST emit the marker ──
    dut.set_cooldown_zero()
    ctl_lines, ctl_resp = _tc_drag_collect(dut, f"drag {x1} {vy} {x2} {vy} 10",
                                           [MARK], timeout=15.0)
    if ctl_resp is None:
        fail("T078", "no drag response to the positive control within 15 s")
        return
    if not ctl_lines:
        unmet("T078", f"positive control: a full-width volume drag "
                      f"({x1}->{x2} at y={vy}) emitted no {MARK!r} line, so this "
                      f"boot's LOG_D('touch') channel is not carrying the marker "
                      f"the negative half reads. A silent channel and a suppressed "
                      f"commit are the same observation (E-6) — inconclusive, not a "
                      f"pass. Raise the runtime log level and re-run.")
        return
    time.sleep(0.5)

    # ── the assertion: a zero-delta drag must NOT emit it ──────────────────
    dut.set_cooldown_zero()
    zero_lines, zero_resp = _tc_drag_collect(dut, f"drag {mid} {vy} {mid} {vy} 1",
                                             [MARK], timeout=15.0)
    if zero_resp is None:
        fail("T078", "no drag response to the zero-delta drag within 15 s")
        return
    if not zero_resp.get("ok"):
        fail("T078", f"zero-delta drag rejected: {zero_resp}")
        return
    if zero_lines:
        fail("T078", f"zero-delta drag at ({mid},{vy}) COMMITTED a volume change: "
                     f"{zero_lines!r} — the deadband is not holding")
        return

    time.sleep(0.5)
    rg2 = dut.cmd("get dragState")
    if rg2.get("state") != "D_IDLE":
        fail("T078", f"dragState={rg2.get('state')} after zero-delta drag")
        return
    pass_("T078", f"control drag emitted {len(ctl_lines)} {MARK!r} line(s); the "
                  f"zero-delta drag emitted none and returned to D_IDLE")


# ── T079 — cooldown gate blocks rapid sequential taps ────────────────────────

@meta(cls="CORE", cls_reason=
      "`Dut.set_cooldown_zero()` runs before nearly every injected tap in the "
      "corpus — it is how the suite guarantees its taps are admitted at all. This "
      "is the only id that asserts the gate in BOTH states: armed, a tap reports "
      "`skipped`; cleared, the same tap reports `hit=TRANSPORT`. If the gate stops "
      "honouring `set cooldown`, taps are silently dropped (or silently admitted) "
      "for the whole run, and every downstream tap assertion is scoring a machine "
      "the test did not arrange.")
def t079(dut: Dut):
    print("T079  Cooldown gate blocks rapid tap")
    # injectTouch (cmd tap) intentionally does NOT arm touchScreenCoolDownTime
    # — synthetic taps must not block real input. So `set cooldown <ms>` is
    # used to arm the gate, then we verify a follow-up `tap` reports skipped.
    # Use 10 s timeout: prior transport/seek actions fire Spotify HTTP calls
    # that can take > 2 s to complete; g_shellBusy must clear before arming.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    r_arm = dut.cmd("set cooldown 500")
    if not r_arm.get("ok"):
        fail("T079", f"set cooldown 500 failed: {r_arm}")
        return
    _px, _py = _c.tap_button("PLAY")
    r = dut.cmd(f"tap {_px} {_py}")   # PLAY — should be gated by cooldown
    skipped = r.get("skipped", False)
    hit = r.get("hit", "")
    if not skipped:
        fail("T079", f"tap not skipped while gate armed: {r}")
        dut.set_cooldown_zero()  # leave clean
        return
    # Clear gate; wait for any async work the (possibly-consumed) tap triggered,
    # then verify the follow-up tap fires.
    dut.set_cooldown_zero()
    _wait_shell_not_busy(dut, timeout_s=10.0)
    r2 = dut.cmd(f"tap {_px} {_py}")
    if r2.get("skipped") or r2.get("hit") != "TRANSPORT":
        fail("T079", f"post-reset tap unexpected: {r2}")
    else:
        pass_("T079", f"gate armed: skipped={skipped} hit={hit}; reset clears gate")


# ── T080 — `info` command shape ───────────────────────────────────────────────

@meta(cls="CORE", cls_reason=
      "The heap floor is the only assertion anywhere in the suite that the board "
      "has the RESOURCES to run the rest of it. Below it the allocation-heavy "
      "families — Stock's chart buffer, PlaneRadar's airport DB, WebRadio's decode "
      "arena — fail for want of memory, and each reports that as a defect in its "
      "own feature. Caveat recorded with the declaration: the 50 000 floor has no "
      "cited firmware constant or measurement behind it (WP-A A-11), so this gates "
      "on a number nobody derived; deriving it is owed.")
def t080(dut: Dut):
    print("T080  `info` command shape")
    r = dut.cmd("info", timeout=4.0)
    required = ["git", "elf", "build", "heap", "isPlaying",
                "progressMs", "durationMs", "volumePct", "consecutiveFailures"]
    missing = [k for k in required if k not in r]
    if missing:
        fail("T080", f"missing fields: {missing}")
        return
    heap = r.get("heap", 0)
    if heap < 50_000:
        fail("T080", f"heap={heap} < 50000")
        return
    pass_("T080", f"heap={heap} git={r.get('git')} elf={r.get('elf')}")


# ── T081 — serial tap reproduces transport suite ──────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t081(dut: Dut):
    print("T081  Serial tap → transport (shape check; Spotify effect manual)")
    buttons = [("PREV", "PREV"), ("PLAY", "PLAY"), ("PAUSE", "PAUSE"),
               ("STOP", "STOP"), ("NEXT", "NEXT")]
    errors = []
    for name, action in buttons:
        _poll_shell_busy(dut, False, timeout_ms=3000)   # wait for prior enqueued action to clear
        cx, cy = _c.tap_button(name)
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {cx} {cy}")
        if r.get("hit") != "TRANSPORT" or r.get("action") != action:
            errors.append(f"{name}: hit={r.get('hit')} action={r.get('action')}")
        time.sleep(0.3)
    if errors:
        fail("T081", "; ".join(errors))
    else:
        pass_("T081", "5/5 TRANSPORT hits correct (Spotify effects: verify manually)")


# ── T082 — serial drag reproduces volume drag ─────────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t082(dut: Dut):
    """T082: serial drag produces ACT_VOLUME enqueue events; debounce verified by count. [PARTIAL — requires Spotify playing for full verification]"""
    print("T082  Serial drag → ACT_VOLUME debounce (log count check)")
    dut.set_cooldown_zero()
    _vx0, _vx1 = _c.vol_drag_x()
    _vy = _c.vol_drag_y()
    dut.send(f"drag {_vx0} {_vy} {_vx1} {_vy} 60")
    # ACT_VOLUME enqueue is synchronous in injectTouch and emits
    # "enqueued ACT_VOLUME pct=N" via LOG_D("touch", ...). We count those
    # rather than the async "dequeued action=VOLUME" lines, which can lag
    # by many seconds behind a backlog of HTTPS calls on spotify.task.
    drag_resp = None
    enqueue_lines = []
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        if "enqueued ACT_VOLUME" in line:
            enqueue_lines.append(line)
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "drag":
                    drag_resp = obj
                    break
            except json.JSONDecodeError:
                pass
    if drag_resp is None:
        fail("T082", "no drag response within 20 s")
        return
    if len(enqueue_lines) < 2:
        fail("T082", f"only {len(enqueue_lines)} ACT_VOLUME enqueue(s); need ≥ 2 for debounce coverage")
    else:
        pass_("T082", f"drag ok; {len(enqueue_lines)} ACT_VOLUME enqueues (verify Spotify volume manually)")


# ── T083 — `help` is parseable single JSON line ───────────────────────────────

@meta(cls="CORE", cls_reason=
      "Every id in the corpus is a sequence of `get`/`set`/`tap`/`drag`/`info`/"
      "`reconnect`, and this is the only id that asserts those names are actually "
      "in the console registry. A command dropped from the registry answers with a "
      "well-formed error the callers do not check, so the failure surfaces in each "
      "test as its own feature misbehaving rather than as a missing command.")
def t083(dut: Dut):
    """T083: `help` command returns parseable JSON with required command names. [SMOKE — verifies command registry, not behavior]"""
    print("T083  `help` is parseable JSON")
    r = dut.cmd("help", timeout=3.0)
    cmds = r.get("commands", [])
    names = [c.get("name") for c in cmds]
    required_names = ["reconnect", "tap", "drag", "get", "set", "info", "help"]
    missing = [n for n in required_names if n not in names]
    if missing:
        fail("T083", f"missing commands: {missing}")
    else:
        pass_("T083", f"ok=True; {len(cmds)} commands listed")


# ── T084 — set/get backoff round-trip ─────────────────────────────────────────
# WAS "KNOWN INTERMITTENT" (first observed 2026-05-25): the Spotify poll task
# could increment consecutiveFailures between the set and the get, so the
# read-back disagreed with the write for a reason that had nothing to do with
# the mechanism under test. That was tolerated by calling flake() on all four
# failure paths. TASK-595 removes the race instead of reporting it: the whole
# round-trip now runs inside _bgpoll_suspended(), the same custody helper
# T-BUSY-05 uses, so nothing else is writing the counter while it is measured.
# With the race gone the failure paths can be honest — see the @meta below.

@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="CORE", cls_reason=
      "It is the only id that tests the `set X` → `get X` round trip ITSELF. Around "
      "thirty ids inject device state through that pair and then assert on a "
      "read-back (`set lastHttp`, `set fetchFailed`, `set bgPoll`, `set triggerFetch`, "
      "`set playerMode`…); if `set` silently no-ops or `get` answers a stale copy, "
      "every one of them asserts against a value it never wrote and passes or fails "
      "for a reason unrelated to its subject. WP-C is right that read-back of the "
      "same field is a tautology about the FEATURE — that is exactly why it is the "
      "right premise test for the MECHANISM. The debt this declaration recorded is "
      "DISCHARGED (TASK-595, 2026-09-12): its four failure paths called `flake()` "
      "while T084 was absent from `flaky.yaml`, so a real failure blocked the run "
      "with an UNDECLARED-flake message about bookkeeping rather than about the "
      "shell (WP-C C-7). It could not simply be declared — a CORE id carrying a "
      "`flaky.yaml` entry is an F1 finding, since a retry resolving FLAKY-PASS can "
      "never set the blocker CORE exists to set. So the race was removed at source "
      "instead, and the paths now `fail()`.")
def t084(dut: Dut):
    print("T084  set/get backoff round-trip")
    # The counter this id writes is also written by the Spotify poll task, so
    # the poll is suspended for the measurement (see the note above). `saved`
    # puts bgPoll back on every exit, including a raise.
    with _bgpoll_suspended(dut):
        # Typed throughout (TASK-596/R18): `set_val` raises BadField if the
        # device refuses the write, `get_int` raises BadField on a missing,
        # null or non-int field and NoAnswer if nothing answered at all.
        # lib/dispatch.py maps those to FAIL and UNMET respectively, so a
        # refused write is a real verdict about the shell and an unanswered
        # console is NOT laundered into one.
        dut.set_val("backoff", 5)
        cf = dut.get_int("backoff", field="consecutiveFailures")
        if cf != 5:
            fail("T084", f"`set backoff 5` then `get backoff` read "
                         f"consecutiveFailures={cf}, expected 5 — the set/get "
                         f"round-trip every injecting id depends on is broken")
            return
        dut.set_val("backoff", 0)
        cf = dut.get_int("backoff", field="consecutiveFailures")
        if cf != 0:
            fail("T084", f"`set backoff 0` then `get backoff` read "
                         f"consecutiveFailures={cf}, expected 0")
            return
    pass_("T084", "5→0 round-trip consistent")


# ── T085 — POSBAR tap → NONE when no track loaded ────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t085(dut: Dut):
    print("T085  POSBAR tap when no track (force songDuration=0)")
    # Force the `songDuration <= 0` precondition via the debug accessor
    # instead of waiting for Spotify to drop the player session (which can
    # take many minutes after the last client disconnects). The next
    # /me/player poll naturally restores songDuration, so the override is
    # transient — but tests run before that, so we restore explicitly.
    r_save = dut.cmd("get songDuration", timeout=3.0)
    saved_ms = r_save.get("ms", 180000)
    r_force = dut.cmd("set songDuration 0")
    if not r_force.get("ok"):
        fail("T085", f"set songDuration 0 failed: {r_force}")
        return
    dut.set_cooldown_zero()
    r = dut.cmd(f"tap {_c.tap_posbar()[0]} {_c.tap_posbar()[1]}")
    hit = r.get("hit", "")
    action = r.get("action", "")
    # Restore songDuration so T086 is not polluted.
    dut.cmd(f"set songDuration {saved_ms}")
    if hit == "POSBAR":
        fail("T085", f"got hit=POSBAR with songDuration=0 (action={action})")
    elif action == "SEEK":
        fail("T085", f"got action=SEEK with songDuration=0 (hit={hit})")
    else:
        pass_("T085", f"hit={hit} action={action} (no POSBAR / no SEEK at songDuration=0)")


# ── T096 — cmdDrag queue-drain completeness ───────────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t096(dut: Dut):
    print("T096  cmdDrag queue-drain completeness")
    dut.set_cooldown_zero()

    _vx0, _vx1 = _c.vol_drag_x()
    _vy = _c.vol_drag_y()

    def run_drag(steps: int) -> tuple[int, bool]:
        """Returns (sample_line_count, got_drag_response)."""
        dut.send(f"drag {_vx0} {_vy} {_vx1} {_vy} {steps}")
        sample_count = 0
        got_response = False
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            line = dut.ser.readline().decode(errors="replace").strip()
            if "inject sample" in line:
                sample_count += 1
            if line.startswith("{"):
                try:
                    obj = json.loads(line)
                    if obj.get("cmd") == "drag":
                        got_response = True
                        break
                except json.JSONDecodeError:
                    pass
        return sample_count, got_response

    # First drag: steps=60 → expect 61 move samples + release (trace doesn't log release)
    count1, ok1 = run_drag(60)
    if not ok1:
        fail("T096", "first drag: no drag-end response")
        return
    expected1 = 61  # steps+1 move samples (release sentinel not counted in LOG_D)
    if count1 != expected1:
        fail("T096", f"first drag: {count1} sample lines, expected {expected1}")
        return

    # Second drag: steps=62 → expect 63 move samples
    dut.set_cooldown_zero()
    count2, ok2 = run_drag(62)
    if not ok2:
        fail("T096", "second drag: no drag-end response")
        return
    expected2 = 63
    if count2 != expected2:
        fail("T096", f"second drag: {count2} sample lines, expected {expected2}")
        return

    pass_("T096", f"drag60={count1}/{expected1} drag62={count2}/{expected2} samples")



# ── T087 — serial tap: SHUFFLE / REPEAT / VIS / LOGO regions ─────────────────
# KNOWN INTERMITTENT: TLS reset log-line timing — the "hard reset / stopping
# client" log line is emitted after the current doPoll() completes; slow poll
# responses (high network latency, TLS renegotiation) can push it past the 8 s
# deadline — first observed 2026-05-25

@meta(scope="Spotify", scope_reason="winamp-view")
def t087(dut: Dut):
    print("T087  Serial tap: SHUFFLE / REPEAT / VIS / LOGO regions")
    errors = []

    dut.set_cooldown_zero()
    _shx, _shy = _c.tap_shuffle()
    r = dut.cmd(f"tap {_shx} {_shy}")
    if r.get("hit") != "SHUFFLE" or r.get("action") != "SHUFFLE":
        errors.append(f"SHUFFLE: hit={r.get('hit')} action={r.get('action')}")

    _poll_shell_busy(dut, False, timeout_ms=3000)   # SHUFFLE enqueues async; 0.3 s sleep insufficient
    dut.set_cooldown_zero()
    _rpx, _rpy = _c.tap_repeat()
    r = dut.cmd(f"tap {_rpx} {_rpy}")
    if r.get("hit") != "REPEAT" or r.get("action") != "REPEAT":
        errors.append(f"REPEAT: hit={r.get('hit')} action={r.get('action')}")

    _poll_shell_busy(dut, False, timeout_ms=3000)   # REPEAT enqueues async
    dut.set_cooldown_zero()
    _vsx, _vsy = _c.tap_vis()
    r = dut.cmd(f"tap {_vsx} {_vsy}")
    if r.get("hit") != "VIS" or r.get("action") != "VIS":
        errors.append(f"VIS: hit={r.get('hit')} action={r.get('action')} (expected VIS/VIS)")

    # LOGO: first tap → TLS_RESET. Second must be within LOGO_TAP_COOLDOWN_MS=2000 ms.
    _lgx, _lgy = _c.tap_logo()
    dut.set_cooldown_zero()
    r = dut.cmd(f"tap {_lgx} {_lgy}")
    if r.get("hit") != "LOGO" or r.get("action") != "TLS_RESET":
        errors.append(f"LOGO-1st: hit={r.get('hit')} action={r.get('action')}")

    # Second LOGO tap immediately (still within 2 s logoTapCooldownMs window).
    # set_cooldown_zero resets touchScreenCoolDownTime only, not logoTapCooldownMs.
    dut.set_cooldown_zero()
    r2 = dut.cmd(f"tap {_lgx} {_lgy}")
    if r2.get("hit") != "DEADZONE" or r2.get("action") != "FORCE_POLL":
        errors.append(f"LOGO-cooldown: hit={r2.get('hit')} action={r2.get('action')} "
                      f"(expected DEADZONE/FORCE_POLL while logoTapCooldownMs active)")

    # Now search for the TLS reset log line.  The Spotify task processes
    # s_resetTlsPending at the TOP of its loop, after the current doPoll()
    # completes.  Give up to 8 s to account for slow poll responses.
    tls_log_found = False
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "hard reset" in line or "stopping client" in line:
            tls_log_found = True
            break
    if not tls_log_found:
        errors.append("LOGO-1st: no TLS-reset log line within 8 s "
                      "(expected '[I][spotify.tls] hard reset — stopping client')")

    if errors:
        flake("T087", "; ".join(errors))
    else:
        pass_("T087", "SHUFFLE+REPEAT+VIS+LOGO correct; LOGO cooldown → DEADZONE")
    print("      NOTE: verify Spotify shuffle/repeat state flipped — manual observation")


# ── T088 — DEADZONE positive cases ───────────────────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t088(dut: Dut):
    print("T088  DEADZONE positive cases — canvas corners + dead-zone samples")
    # g_shellBusy may be True from a prior transport/seek/volume action — wait before tapping.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    _pbx0, _pbx1, _pby0, _pby1 = _c.posbar_bounds()
    _pbxm, _pbym = _c.tap_posbar()
    _gap_y = _pby1 + 1 + (int(_c.S["CB_PREV_Y"]) - _pby1 - 1) // 2
    _trans_bot = int(_c.S["CB_PREV_Y"]) + int(_c.S["CB_PREV_H"])
    _win_w = int(_c.S["WINDOW_W"])   # 275
    _win_h = int(_c.S["WINDOW_H"])   # 116

    # Coords with x < TASKBAR_X: expected DEADZONE / FORCE_POLL while Spotify active.
    # corner-TR/BR and 1px-right-chrome are now in the taskbar strip; tested below.
    deadzone_cases = [
        ("dead-posbar-left",           _pbx0 - 1,                  _pbym),
        ("dead-posbar-top",            _pbxm,                      _pby0 - 1),
        ("dead-gap-posbar-transport",  _pbxm,                      _gap_y),
        ("dead-below-transport",       _pbxm,                      _trans_bot + 1),
        ("corner-TL",                  0,                           0),
        ("corner-BL",                  0,                           _c.SCREEN_H - 1),
        ("1px-left-chrome",            _c.ORIGIN_X - 1,             _win_h // 2),
        ("1px-below-chrome",           _c.ORIGIN_X + _win_w // 2,   _win_h + 1),
    ]

    # Coords with x >= TASKBAR_X: expected TASKBAR (may call switchApp — restore after).
    taskbar_cases = [
        ("corner-TR",        _c.SCREEN_W - 1,            0),
        ("corner-BR",        _c.SCREEN_W - 1,            _c.SCREEN_H - 1),
        ("1px-right-chrome", _c.ORIGIN_X + _win_w + 1,   _win_h // 2),
    ]

    errors = []

    # DEADZONE checks (run first, while Spotify is guaranteed active at test start).
    # Each FORCE_POLL tap triggers a Spotify HTTP poll → g_shellBusy; wait between cases.
    for label, x, y in deadzone_cases:
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        hit = r.get("hit", "")
        action = r.get("action", "")
        if hit != "DEADZONE":
            errors.append(f"{label}({x},{y}): hit={hit} (expected DEADZONE)")
        elif action != "FORCE_POLL":
            errors.append(f"{label}({x},{y}): action={action} (expected FORCE_POLL)")

    # TASKBAR checks (x >= TASKBAR_X — these are correct; corner-TR/BR/right-chrome
    # are now valid taskbar slots, not dead zones).
    for label, x, y in taskbar_cases:
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        hit = r.get("hit", "")
        if hit != "TASKBAR":
            errors.append(f"{label}({x},{y}): hit={hit} (expected TASKBAR)")

    # Taskbar taps may have switched the active app (e.g. corner-BR → Life).
    # Restore to Spotify so subsequent tests start in a known state.
    _restore_spotify(dut)

    if errors:
        fail("T088", "; ".join(errors))
    else:
        pass_("T088", f"{len(deadzone_cases)} DEADZONE + {len(taskbar_cases)} TASKBAR correct")


# ── T090 — reconnect command emits JSON response ─────────────────────────────

def t090(dut: Dut):
    """T090: `reconnect` emits valid JSON response. [SMOKE — superseded by T091]"""
    print("T090  `reconnect` emits JSON {ok:true, cmd:'reconnect'}")
    r = dut.cmd("reconnect", timeout=4.0)
    if r.get("ok") is not True or r.get("cmd") != "reconnect":
        fail("T090", f"unexpected response: {r}")
    else:
        pass_("T090", f"ok=true cmd=reconnect")


# ── T091 — reconnect clears consecutiveFailures ───────────────────────────────
# KNOWN INTERMITTENT: reconnect race — an in-flight Spotify poll can
# re-increment consecutiveFailures between the reconnect and the get backoff
# commands, producing a non-zero value even after a successful reconnect —
# first observed 2026-05-25

@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. Two grounds. "
      "(1) The failure is LOCAL: nothing outside T092 and T-BGPOLL-02 — both also "
      "demoted — reads `consecutiveFailures` or depends on `reconnect` resetting "
      "it, and no FEATURE id does; a broken reconnect-clears-counter leaves every "
      "other id's premises intact. (2) WP-C C-6: every exit routes through "
      "`flake()` and the id is declared in `flaky.yaml`, so its best case is "
      "`FLAKY-PASS` — neither a PASS nor a FAIL — and `_gate.py:128` can never see "
      "it set the blocker. A class that cannot block is not the class it claims.")
def t091(dut: Dut):
    print("T091  `reconnect` clears consecutiveFailures")
    _wait_shell_not_busy(dut, timeout_s=10.0)
    r_set = dut.cmd("set backoff 3", timeout=3.0)
    if not r_set.get("ok"):
        flake("T091", f"set backoff 3 failed: {r_set}"); return
    r_get = dut.cmd("get backoff", timeout=3.0)
    if r_get.get("consecutiveFailures") != 3:
        flake("T091", f"consecutiveFailures={r_get.get('consecutiveFailures')} after set, expected 3"); return
    r_rc = dut.cmd("reconnect", timeout=3.0)
    if not r_rc.get("ok"):
        flake("T091", f"reconnect failed: {r_rc}"); return
    # reconnect triggers a TLS reset which floods serial for ~1-2 s; wait before querying.
    time.sleep(2.0)
    r_get2 = dut.cmd("get backoff", timeout=5.0)
    cf = r_get2.get("consecutiveFailures", -1)
    if cf != 0:
        flake("T091", f"consecutiveFailures={cf} after reconnect (expected 0)")
    else:
        pass_("T091", f"set→3, reconnect, consecutiveFailures=0 ✓")


# ── T092 — reconnect triggers immediate force poll ────────────────────────────
# KNOWN INTERMITTENT: TLS reset log-line timing — post-reconnect TLS
# renegotiation can delay the force-poll start, pushing the
# [spotify.poll] log line past the 2000 ms observation window —
# first observed 2026-05-25

@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. A latency bound "
      "on the Spotify force poll: a poll that arrives late says the Spotify chrome "
      "is slow and says nothing about the taskbar, Clock, Stock, Player or WebRadio "
      "families, which never read it. The oracle argues the same way — the whole "
      "assertion is one `LOG_D` line that `logSink.h:119`'s runtime level gate can "
      "suppress if an earlier test lowered the level, so its failure mode is as "
      "local as its subject.")
def t092(dut: Dut):
    print("T092  `reconnect` triggers force poll ≤2000ms")
    # Drain any pending serial data before starting the clock
    dut.ser.reset_input_buffer()
    t_send = time.monotonic()
    dut.send("reconnect")
    # Drain the JSON response (non-blocking; don't block the 2 s window)
    deadline_json = time.monotonic() + 1.0
    while time.monotonic() < deadline_json:
        line = dut.ser.readline().decode(errors="replace").strip()
        if line.startswith("{"):
            break
    # Wait for poll line within 2 s of reconnect send
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "[spotify.poll] GET" in line or "[spotify.poll] ok" in line or "[spotify.poll] 204" in line:
            latency_ms = (time.monotonic() - t_send) * 1000
            if latency_ms <= 2000:
                pass_("T092", f"force poll in {latency_ms:.0f}ms ≤ 2000ms")
            else:
                flake("T092", f"poll latency {latency_ms:.0f}ms > 2000ms")
            return
    flake("T092", "no poll line within 2s of reconnect")


# ── T093 — unhealthy titlebar overlay (interactive visual) ───────────────────

def t093(dut: Dut, interactive: bool):
    """T093: unhealthy titlebar overlay appears and clears after reconnect. [MANUAL — requires human operator]"""
    if not interactive:
        skip("T093", "visual test — re-run with --interactive")
        return
    print("T093  Unhealthy titlebar overlay appears + clears (INTERACTIVE)")
    r = dut.cmd("set backoff 5", timeout=3.0)
    if not r.get("ok"):
        fail("T093", f"set backoff 5 failed: {r}"); return
    print("  [visual] DUT: inactive (greyed) title bar should appear within one repaint.")
    try:
        ans = input("  Is the inactive titlebar visible? [y/n] ").strip().lower()
    except EOFError:
        fail("T093", "stdin closed"); return
    if ans != "y":
        fail("T093", "operator did not confirm inactive titlebar"); return
    dut.cmd("reconnect", timeout=4.0)
    time.sleep(3.0)
    print("  [visual] DUT: title bar should revert to active (coloured) on next poll.")
    try:
        ans2 = input("  Is the active titlebar back? [y/n] ").strip().lower()
    except EOFError:
        fail("T093", "stdin closed"); return
    if ans2 != "y":
        fail("T093", "active titlebar did not return after reconnect")
    else:
        pass_("T093", "inactive titlebar appeared; cleared after reconnect")


# ── T094 — Winamp logo tap → TLS reset (interactive physical) ────────────────

def t094(dut: Dut, interactive: bool):
    """T094: physical tap on Winamp logo triggers TLS reset; second tap within cooldown is no-op. [MANUAL — requires human operator]"""
    if not interactive:
        skip("T094", "physical-tap test — re-run with --interactive (T087 covers serial proxy)")
        return
    print("T094  Winamp logo tap → TLS reset (INTERACTIVE — physical tap required)")
    print("  Serial path verified by T087. This test confirms physical touch routes")
    print("  to the same dispatch path.\n")
    print("  Step 1: Physically tap the Winamp logo (bottom-right corner of chrome).")
    print("  Step 2: Watch serial for TLS reset + force poll.")
    try:
        input("  Tap the logo, then press Enter…")
    except EOFError:
        fail("T094", "stdin closed"); return
    found_reset = False
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if "hard reset" in line or "stopping client" in line:
            found_reset = True
            print(f"  [serial] TLS reset: {line}")
            break
    if not found_reset:
        fail("T094", "no TLS-reset log line within 4s of tap"); return
    # Second tap within 2s cooldown should be a no-op
    try:
        input("  Tap logo AGAIN quickly (within 2s of first tap), then Enter…")
    except EOFError:
        pass
    try:
        ans = input("  Was the second tap a no-op (no second TLS reset logged)? [y/n] ").strip().lower()
    except EOFError:
        ans = "n"
    if ans != "y":
        fail("T094", "second tap cooldown not confirmed")
    else:
        pass_("T094", "TLS reset logged; cooldown blocks second tap")


# ── T095 — injection-vs-physical calibration (interactive) ───────────────────

def t095(dut: Dut, interactive: bool):
    """T095: injection-vs-physical calibration — same region/action for serial and physical tap in each zone. [MANUAL — requires human operator]"""
    if not interactive:
        skip("T095", "requires --interactive flag (human operator at DUT). "
             "Re-run: python3 run_serialdbg_tests.py --interactive --tests T095")
        return

    print("T095  Injection-vs-physical calibration (INTERACTIVE)")
    print("      For each zone: harness sends serial tap, then prompts for physical tap.")
    print("      Pass = same region + action observed both ways.\n")

    _z_px, _z_py = _c.tap_button("PREV")
    _z_bx, _z_by = _c.tap_posbar()
    _z_vx        = (_c.vol_drag_x()[0] + _c.vol_drag_x()[1]) // 2
    _z_vy        = _c.vol_drag_y()
    # (zone_name, tap_x, tap_y, expected_hit, expected_action, dequeue_pattern)
    zones = [
        ("PREV",       _z_px, _z_py, "TRANSPORT", "PREV",   "dequeued action=PREV"),
        ("POSBAR-mid", _z_bx, _z_by, "POSBAR",    "SEEK",   "dequeued action=SEEK"),
        ("VOLUME-mid", _z_vx, _z_vy, "VOLUME",    "VOLUME", "dequeued action=VOLUME"),
    ]
    errors = []

    for zone_name, x, y, exp_hit, exp_action, dequeue_pat in zones:
        print(f"  --- Zone: {zone_name} tap({x},{y}) ---")

        # Step 1: serial injection
        dut.set_cooldown_zero()
        r = dut.cmd(f"tap {x} {y}")
        inj_hit = r.get("hit", "?")
        inj_action = r.get("action", "?")
        inj_ok = (inj_hit == exp_hit and inj_action == exp_action)
        status = "✓" if inj_ok else "✗"
        print(f"    [serial]   hit={inj_hit} action={inj_action} {status}")
        if not inj_ok:
            errors.append(f"{zone_name}: serial mismatch hit={inj_hit} action={inj_action} "
                          f"(want {exp_hit}/{exp_action})")

        # Drain the dequeued action log from the injection before the physical step.
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            line = dut.ser.readline().decode(errors="replace").strip()
            if dequeue_pat in line:
                break

        # Step 2: physical tap
        try:
            input(f"\n    >>> Physically tap screen at ~({x},{y}). Press Enter when done…")
        except EOFError:
            fail("T095", "stdin closed — run interactively")
            return

        # Capture dequeued action from physical tap (up to 5 s).
        phys_seen = False
        phys_line = ""
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            line = dut.ser.readline().decode(errors="replace").strip()
            if dequeue_pat in line:
                phys_seen = True
                phys_line = line
                break
        if phys_seen:
            print(f"    [physical] {phys_line} ✓")
        else:
            print(f"    [physical] '{dequeue_pat}' not seen within 5 s ✗")
            errors.append(f"{zone_name}: physical tap not detected in serial log")

        # Spotify visual/audio confirmation
        try:
            answer = input(f"    Spotify effect correct ({exp_action.lower()})? [y/n] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer != "y":
            errors.append(f"{zone_name}: Spotify effect not confirmed by operator")
        print()
        time.sleep(0.5)

    if errors:
        fail("T095", "; ".join(errors))
    else:
        pass_("T095", "all 3 zones: serial and physical produce matching region+action")


# ── T133 — CurrentlyPlaying zero-init guard ───────────────────────────────────

@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE, per WP-B B-2 and "
      "WP-C C-14. Part A is a host-side `grep` of `lib/SpotifyArduino/` — a "
      "checkout missing that directory FAILs before the DUT is touched, which is a "
      "fact about the CHECKOUT and not about the board; part B is a 90 s idle soak "
      "satisfied by any board with or without the guard. Neither half establishes "
      "anything another id relies on, and part A is the R36 reference case for "
      "\"a gating class may not depend on the host file layout\".")
def t133(dut: Dut):
    """Static grep + 90 s runtime soak. Works with production or debug build."""
    print("T133  CurrentlyPlaying zero-init guard (static + 90s stability)")

    # Part A: static source audit — zero-init must be present.
    src = pathlib.Path(__file__).parent.parent.parent.parent / "lib/SpotifyArduino/src/SpotifyArduino.cpp"
    if not src.exists():
        fail("T133", f"source not found: {src}")
        return
    if "CurrentlyPlaying current = {}" not in src.read_text():
        fail("T133", "zero-init guard missing — 'CurrentlyPlaying current = {}' not found")
        return
    print("  [T133] static: zero-init guard present", flush=True)

    # Part B: 90 s runtime soak — fail on any Guru Meditation.
    print("  [T133] monitoring DUT for 90 s (≥12 polls)…", flush=True)
    deadline = time.monotonic() + 90.0
    orig_timeout = dut.ser.timeout
    dut.ser.timeout = 0.5
    try:
        while time.monotonic() < deadline:
            line = dut.ser.readline().decode(errors="replace").strip()
            if "Guru Meditation Error" in line:
                fail("T133", "Guru Meditation Error detected — crash regression")
                return
    finally:
        dut.ser.timeout = orig_timeout
    pass_("T133", "static guard present; 90 s no crash")


# ── T134 — Zone 1 hit-test: tap in PLEDIT content area reports hit="PLEDIT" ────

@meta(scope="Spotify", scope_reason="winamp-view")
def t134(dut: Dut):
    print("T134  Zone 1 hit-test: tap in PLEDIT content area")
    if not _restore_spotify(dut):
        fail("T134", "precondition: could not restore Spotify app")
        return
    if not dut.wait_for_queue(min_count=1):
        skip("T134", "precondition: queue count=0 after 30s — Spotify not playing")
        return
    # Tap row 2 centre. With scrollOffset=0 and count>=3 this dispatches
    # ACT_PLAY_URI(2); with count<3 it may still report hit=PLEDIT but with a
    # clamped or no-op play index. Either way the zone hit is confirmed.
    dut.set_cooldown_zero()
    tx, ty = _c.pledit_tap(2)
    r = dut.cmd(f"tap {tx} {ty}", timeout=5.0)
    if not r.get("ok"):
        fail("T134", f"tap returned ok=false: {r}")
        return
    hit = r.get("hit", "")
    action = r.get("action", "")
    if hit != "PLEDIT":
        fail("T134", f"hit={hit!r} action={action!r} — expected PLEDIT. "
                     f"Tap coords ({tx},{ty}). originX may differ from 22 or "
                     f"PLEDIT hitzone constants are wrong (H4 confirmed).")
        return
    pass_("T134", f"hit=PLEDIT action={action!r} at ({tx},{ty})")


# ── T135 — Drag-end fires: drag response arrives and dragState returns D_IDLE ──

@meta(scope="Spotify", scope_reason="winamp-view")
def t135(dut: Dut):
    print("T135  Drag-end fires on synthetic swipe-up")
    # Pre-condition: dragState must be D_IDLE.
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T135", f"pre-condition: dragState={rg.get('state')} not D_IDLE — "
                     "prior test left state dirty; run set cooldown 0 and retry")
        return
    # Issue swipe-up through Zone 1 centre: dy = -30 px, 30 steps.
    x1, y1, x2, y2 = _c.pledit_swipe("up")
    dut.send(f"drag {x1} {y1} {x2} {y2} 30")
    # Drain non-JSON lines until drag response or timeout.
    drag_resp = None
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if not line:
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "drag":
                    drag_resp = obj
                    break
            except json.JSONDecodeError:
                pass
    if drag_resp is None:
        fail("T135", "no drag response within 15 s — injectRelease() never called "
                     "or drag queue stalled")
        return
    if not drag_resp.get("ok"):
        fail("T135", f"drag response ok=false: {drag_resp}")
        return
    # dragState must return to D_IDLE.
    rg2 = dut.cmd("get dragState", timeout=3.0)
    if rg2.get("state") != "D_IDLE":
        fail("T135", f"dragState={rg2.get('state')} after drag — D_PLEDIT_SCROLL "
                     "not cleared in injectRelease()")
        return
    pass_("T135", f"drag response ok; dragState=D_IDLE; swipe ({x1},{y1})→({x2},{y2})")
    # Restore scrollOffset to 0 so T136 and T137 see clean initial state.
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    _do_drag(dut, xd, yd, xd2, yd2)


# ── shared drag helper (T136–T140) ────────────────────────────────────────────





# ── T137 — swipe-up increments scrollOffset ────────────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t137(dut: Dut):
    print("T137  swipe-up increments scrollOffset")
    if not dut.wait_for_queue(min_count=2):
        skip("T137", "precondition: queue count<2 after 30s — Spotify not playing")
        return
    # Precondition: scrollOffset must be 0 before we swipe (absorbs T136 assertion).
    r_pre = dut.cmd("get scrollOffset", timeout=3.0)
    if not r_pre.get("ok") or r_pre.get("key") != "scrollOffset":
        fail("T137", f"precondition: get scrollOffset failed: {r_pre}")
        return
    pre = r_pre.get("val")
    if pre != 0:
        fail("T137", f"pre-condition: scrollOffset={pre} not 0; run swipe-downs or reflash")
        return
    x1, y1, x2, y2 = _c.pledit_swipe("up")
    resp = _do_drag(dut, x1, y1, x2, y2)
    if resp is None:
        fail("T137", "no drag response within 15 s")
        return
    if not resp.get("ok"):
        fail("T137", f"drag ok=false: {resp}")
        return
    post = _get_scroll(dut)
    if post != 1:
        fail("T137", f"scrollOffset={post} after swipe-up, expected 1")
        return
    pass_("T137", f"scrollOffset 0→1 after swipe-up ({x1},{y1})→({x2},{y2})")


# ── T138 — swipe-down decrements scrollOffset ─────────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t138(dut: Dut):
    print("T138  swipe-down decrements scrollOffset")
    pre = _get_scroll(dut)
    if pre != 1:
        # Try to bring it to 1 via one swipe-up.
        xu, yu, xu2, yu2 = _c.pledit_swipe("up")
        _do_drag(dut, xu, yu, xu2, yu2)
        pre = _get_scroll(dut)
        if pre != 1:
            skip("T138", f"pre-condition: scrollOffset={pre} not 1 — Spotify not playing?")
            return
    x1, y1, x2, y2 = _c.pledit_swipe("down")
    resp = _do_drag(dut, x1, y1, x2, y2)
    if resp is None:
        fail("T138", "no drag response within 15 s")
        return
    if not resp.get("ok"):
        fail("T138", f"drag ok=false: {resp}")
        return
    post = _get_scroll(dut)
    if post != 0:
        fail("T138", f"scrollOffset={post} after swipe-down, expected 0")
        return
    pass_("T138", f"scrollOffset 1→0 after swipe-down ({x1},{y1})→({x2},{y2})")


# ── T139 — scrollOffset clamps at 0 (no underflow) ────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t139(dut: Dut):
    print("T139  scrollOffset clamps at 0 (no underflow)")
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    # Reset to 0 with a swipe-down (no-op if already 0).
    _do_drag(dut, xd, yd, xd2, yd2)
    pre = _get_scroll(dut)
    if pre != 0:
        fail("T139", f"pre-condition: scrollOffset={pre} not 0")
        return
    # Swipe down again at min — must not go negative.
    resp = _do_drag(dut, xd, yd, xd2, yd2)
    if resp is None:
        fail("T139", "no drag response within 15 s")
        return
    post = _get_scroll(dut)
    if post != 0:
        fail("T139", f"scrollOffset={post} after swipe-down at 0 — underflow detected")
        return
    pass_("T139", "scrollOffset stays 0 on swipe-down at minimum (no underflow)")


# ── T140 — scrollOffset clamps at max ─────────────────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t140(dut: Dut):
    print("T140  scrollOffset clamps at max (count - PLEDIT_ROW_COUNT)")
    # Queue snapshot stores PLEDIT_ROW_COUNT (5) items; need >5 to have a non-zero max.
    # If snapshot is still 5 items, skip rather than fail — this is a snapshot-size
    # limitation (not an originX bug). A future task should expand snapshot capacity.
    if not dut.wait_for_queue(min_count=6):
        skip("T140", "queue snapshot ≤ PLEDIT_ROW_COUNT items — max scrollOffset=0; "
                     "snapshot expansion needed (see TASK-081 notes)")
        return
    # Reset to 0: fire 15 swipe-downs, ignore individual timeouts.
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    for _ in range(15):
        _do_drag(dut, xd, yd, xd2, yd2)
    if _get_scroll(dut) != 0:
        fail("T140", "reset to 0 failed after 15 swipe-downs; queue too deep or drag broken")
        return
    # Saturate upward: 20 swipe-ups (enough for any realistic queue).
    xu, yu, xu2, yu2 = _c.pledit_swipe("up")
    for _ in range(20):
        _do_drag(dut, xu, yu, xu2, yu2)
    val_sat = _get_scroll(dut)
    if val_sat is None or val_sat < 1:
        fail("T140", f"scrollOffset={val_sat} after 20 swipe-ups — "
                     "queue count <= PLEDIT_ROW_COUNT; precondition not met")
        return
    # One extra swipe-up must not increment (clamp).
    _do_drag(dut, xu, yu, xu2, yu2)
    val_after = _get_scroll(dut)
    if val_after != val_sat:
        fail("T140", f"scrollOffset changed {val_sat}→{val_after} on extra swipe — "
                     "clamp not working")
        return
    pass_("T140", f"scrollOffset saturates at {val_sat}; extra swipe did not increment")


@meta(scope="taskbar", scope_reason="taskbar-surface",
      cls="CORE", cls_reason=
      "`_restore_spotify` and `_switch_to` (`_helpers.py:286,321`) reach EVERY app "
      "by tapping a taskbar slot, and shell.py, stock.py, webradio.py and player.py "
      "all route through them. If a taskbar tap does not switch the app, every id "
      "after it runs against whatever app happened to be on screen and reports the "
      "mismatch as a defect in the app it thought it was testing.")
def t147(dut: Dut):
    """T147: taskbar tap (via injectTouch) switches active app; get appId confirms round-trip."""
    import time
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        skip("T147", f"precondition: need Spotify active, got {r.get('name')!r}")
        return
    # Tap the Clock slot in the taskbar.
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)  # repaintChrome ~60 ms; 300 ms headroom
    r2 = dut.cmd("get appId", timeout=3.0)
    if not r2.get("ok") or r2.get("name") != "Clock":
        fail("T147", f"did not switch to Clock: got appId={r2.get('name')!r}")
        # Attempt restore before failing.
        dut.set_cooldown_zero()
        dut.cmd(f"tap {_c.tap_taskbar_slot(APP_SLOT["Spotify"])[0]} {_c.tap_taskbar_slot(APP_SLOT["Spotify"])[1]}", timeout=3.0)
        time.sleep(0.3)
        return
    # Switch back to Spotify to leave DUT in known state for subsequent tests.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.3)
    r3 = dut.cmd("get appId", timeout=3.0)
    if not r3.get("ok") or r3.get("name") != "Spotify":
        fail("T147", f"failed to return to Spotify: got {r3.get('name')!r}")
        return
    pass_("T147", "Spotify→Clock→Spotify round-trip confirmed via get appId")


@meta(cls="CORE", cls_reason=
      "Every non-Spotify app's canvas test assumes a tap on the canvas reaches that "
      "app's own handler. If Winamp zone routing leaks back — the TASK-346 BUG-1 "
      "class this guards — those tests are scoring Winamp's hit-test, and a Clock, "
      "Stock or PlaneRadar tap test then passes or fails for a reason that has "
      "nothing to do with the app named in its id.")
def t148(dut: Dut):
    """T148: while Clock active, tap routes through Clock's own dedicated handler
    (TASK-346 M-CLOCK-TAP-CYCLE) — hit=CLOCKAPP, never a Winamp/Spotify zone name."""
    import time
    # Switch to Clock.
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)
    r_pre = dut.cmd("get appId", timeout=3.0)
    if not r_pre.get("ok") or r_pre.get("name") != "Clock":
        skip("T148", f"precondition: could not switch to Clock (appId={r_pre.get('name')!r})")
        return
    # Tap clock-face centre — coordinate (137, 120) sits on CLK_TAP_SPLIT_Y and
    # lands in the face-cycle zone (TASK-346); _cycleFace() always consumes.
    dut.set_cooldown_zero()
    tx, ty = _c.clock_canvas_tap()
    r = dut.cmd(f"tap {tx} {ty}", timeout=3.0)
    hit = r.get("hit", "")
    action = r.get("action", "")
    # Restore to Spotify before asserting (so subsequent tests start clean).
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.3)
    if hit != "CLOCKAPP":
        fail("T148", f"BUG-1 guard not firing: hit={hit!r} action={action!r} "
                     f"at ({tx},{ty}) with Clock active — expected dedicated CLOCKAPP "
                     f"routing (TASK-346), got a Winamp/Spotify zone name instead")
        return
    if action != "CONSUMED":
        fail("T148", f"unexpected action={action!r} (want CONSUMED) for Clock face-cycle "
                     f"tap at ({tx},{ty}) — _cycleFace() always returns true")
        return
    pass_("T148", f"Clock active: hit={hit!r} action={action!r} — routed through Clock's "
                 f"own handler, no Winamp zone leak")


# ── T_BI_01 — PLEDIT repaint on Spotify resume ───────────────────────────────

@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. `lastPlaylistDraw` "
      "is read by no other id in the corpus: a PLEDIT repaint that does not fire on "
      "resume is a defect confined to the Winamp view. It also skips on an empty "
      "Spotify queue, which under TASK-243's live 403 is the routine outcome, so as "
      "a gate it is near-permanently inconclusive (BP-074) as well as local.")
def t_bi_01(dut: Dut):
    """T_BI_01: lastPlaylistDraw advances after Spotify resume (invalidatePlaylist fires)."""
    # Precondition: queue populated
    if not dut.wait_for_queue(min_count=1, timeout=30.0):
        skip("T_BI_01", "queue empty after 30s — Spotify not playing?")
        return
    # Ensure Spotify active.
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        dut.set_cooldown_zero()
        sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
        dut.cmd(f"tap {sx} {sy}", timeout=3.0)
        time.sleep(0.4)
    # Switch to Clock; wait 2 s (ensures rate-limit window clears; seqno may change).
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(2.0)
    # Note t_before.
    r_before = dut.cmd("get lastPlaylistDraw", timeout=3.0)
    if not r_before.get("ok"):
        fail("T_BI_01", f"get lastPlaylistDraw failed: {r_before}")
        return
    t_before = r_before.get("ms", 0)
    # Switch back to Spotify — resume() calls invalidatePlaylist().
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    # Poll until lastPlaylistDraw advances (drawPlaylist fired in tick()), timeout 2 s.
    deadline = time.monotonic() + 2.0
    t_after = t_before
    while time.monotonic() < deadline:
        r_poll = dut.cmd("get lastPlaylistDraw", timeout=1.0)
        if r_poll.get("ok"):
            candidate = r_poll.get("ms", t_before)
            if candidate != t_before:
                t_after = candidate
                break
        time.sleep(0.05)
    if t_after == t_before:
        fail("T_BI_01", f"lastPlaylistDraw did not advance after Spotify resume "
                        f"(before={t_before} after={t_after}) — "
                        f"invalidatePlaylist() + tick() path did not fire")
        return
    pass_("T_BI_01", f"lastPlaylistDraw advanced {t_before}→{t_after} after Spotify resume")


# ── T_BI_02 — no Winamp render bleed onto Clock canvas ───────────────────────

@meta(cls="CORE", cls_reason=
      "The suite taps the taskbar immediately after a canvas action all through the "
      "run — `_restore_spotify` right after a transport tap is the routine case. If "
      "the shell does not consume a taskbar tap that arrives while an app action is "
      "still pending, those restores become non-deterministic and every id inherits "
      "an active app it did not choose. This is the only id that asserts the "
      "preemption directly (`hit=TASKBAR`, `action=APP_SWITCH`, then `appId`).")
def t_bi_02(dut: Dut):
    """T_BI_02: taskbar tap while PLAY pending → APP_SWITCH response; appId=Clock (no bleed)."""
    # Ensure Spotify active.
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        skip("T_BI_02", f"precondition: need Spotify active, got {r.get('name')!r}")
        return
    # Tap PLAY (Press+Release delivered synchronously; pendingReleaseAt set then cleared).
    px, py = _c.tap_button("PLAY")
    dut.set_cooldown_zero()
    dut.cmd(f"tap {px} {py}", timeout=3.0)
    # Immediately tap taskbar Clock slot — shell must handle it, not Winamp.
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    r_switch = dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.2)  # past the 80 ms pendingReleaseAt window
    r_app = dut.cmd("get appId", timeout=3.0)
    # Restore to Spotify before asserting.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.3)
    hit    = r_switch.get("hit", "")
    action = r_switch.get("action", "")
    if hit != "TASKBAR" or action != "APP_SWITCH":
        fail("T_BI_02", f"taskbar tap: hit={hit!r} action={action!r} "
                        f"(expected TASKBAR/APP_SWITCH) — shell did not consume event")
        return
    if not r_app.get("ok") or r_app.get("name") != "Clock":
        fail("T_BI_02", f"appId={r_app.get('name')!r} after taskbar tap — switch did not complete")
        return
    pass_("T_BI_02", f"hit={hit!r} action={action!r}; appId=Clock — shell consumed event, no Winamp bleed")


# ── T_BI_03 — suspend() clears drag state mid-switch ─────────────────────────

@meta(cls="CORE", cls_reason=
      "Drag state that survives an app switch contaminates every later gesture in "
      "the run — taskbar scroll, PLEDIT scroll, volume drag — with a drag a previous "
      "test began. `suspend()` clearing it is what makes gesture tests independent "
      "of their predecessors, and this is the only id that asserts it. Only the "
      "`dragState` half carries the class; the `scrollOffset >= 0` half is a vacuous "
      "bound (WP-C, S8) and proves nothing. Its precondition needs a live Spotify "
      "queue of >= 2, which under TASK-243's 403 it does not get — an R36/TASK-626 "
      "case, listed there, not a reason to demote the claim.")
def t_bi_03(dut: Dut):
    """T_BI_03: suspend() resets dragState; resume() re-enables PLEDIT after Spotify→Clock→Spotify."""
    # Precondition: Spotify active, queue ≥ 2 items for scroll tests.
    if not dut.wait_for_queue(min_count=2, timeout=30.0):
        skip("T_BI_03", "queue count<2 after 30s — Spotify not playing?")
        return
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        dut.set_cooldown_zero()
        sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
        dut.cmd(f"tap {sx} {sy}", timeout=3.0)
        time.sleep(0.4)
    # Reset scrollOffset to 0 first.
    x1, y1, x2, y2 = _c.pledit_swipe("down")
    for _ in range(3):
        dut.set_cooldown_zero()
        dut.send(f"drag {x1} {y1} {x2} {y2} 5")
        dut.read_json(timeout=5.0)
    # Swipe up once so dragState exercises D_PLEDIT_SCROLL path.
    x1u, y1u, x2u, y2u = _c.pledit_swipe("up")
    dut.set_cooldown_zero()
    dut.send(f"drag {x1u} {y1u} {x2u} {y2u} 5")
    dut.read_json(timeout=5.0)
    # Verify dragState is D_IDLE after drag completes.
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T_BI_03", f"pre-condition: dragState={rg.get('state')} not D_IDLE after drag")
        return
    # Switch to Clock — suspend() → resetDragState().
    dut.set_cooldown_zero()
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.3)
    r_clock = dut.cmd("get appId", timeout=3.0)
    if not r_clock.get("ok") or r_clock.get("name") != "Clock":
        fail("T_BI_03", f"failed to switch to Clock: appId={r_clock.get('name')!r}")
        return
    time.sleep(0.5)
    # Switch back to Spotify — resume() → invalidatePlaylist().
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.4)
    # Check dragState is D_IDLE (resetDragState was called by suspend()).
    rg2 = dut.cmd("get dragState", timeout=3.0)
    if rg2.get("state") != "D_IDLE":
        fail("T_BI_03", f"dragState={rg2.get('state')} after Clock switch — suspend() did not reset")
        return
    # Check scrollOffset is in range [0, ∞) — no negative underflow from stale drag.
    rs = dut.cmd("get scrollOffset", timeout=3.0)
    so = rs.get("val", -1)
    if not isinstance(so, int) or so < 0:
        fail("T_BI_03", f"scrollOffset={so!r} — negative or missing after suspend/resume")
        return
    pass_("T_BI_03", f"dragState=D_IDLE; scrollOffset={so} ≥ 0 after Clock switch — suspend/resume clean")


# ── T_BI_04 — Release delivery after finger lift ─────────────────────────────

@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE, per WP-C C-20. Its "
      "stated subject — that `cmdTap` delivers the Release phase — has no oracle: "
      "the reply is synthesised by `cmdTap` from the hit-test, so a firmware that "
      "never delivers Release still answers TRANSPORT/PLAY. What it does assert "
      "duplicates T081's, and the tap-injection premise it appears to carry is "
      "already declared CORE on T079. A duplicate of a premise is not a premise.")
def t_bi_04(dut: Dut):
    """T_BI_04: cmdTap delivers Release phase; response region=TRANSPORT action=PLAY|PAUSE. [PARTIAL — requires Spotify playing for full verification]"""
    r = dut.cmd("get appId", timeout=3.0)
    if not r.get("ok") or r.get("name") != "Spotify":
        skip("T_BI_04", f"precondition: need Spotify active, got {r.get('name')!r}")
        return
    px, py = _c.tap_button("PLAY")
    dut.set_cooldown_zero()
    r_tap = dut.cmd(f"tap {px} {py}", timeout=3.0)
    # 150 ms — past the 80 ms pendingReleaseAt window; release already delivered synchronously.
    time.sleep(0.15)
    hit    = r_tap.get("hit", "")
    action = r_tap.get("action", "")
    if hit != "TRANSPORT":
        fail("T_BI_04", f"hit={hit!r} (expected TRANSPORT) — tap missed transport zone")
        return
    if action not in ("PLAY", "PAUSE"):
        fail("T_BI_04", f"action={action!r} (expected PLAY or PAUSE) — wrong transport action")
        return
    pass_("T_BI_04", f"Release delivered: hit={hit!r} action={action!r} — DUT stable, correct region")


# ── multiapp helpers ─────────────────────────────────────────────────────────


# ── T_MA_01 — MatrixApp switch round-trip ────────────────────────────────────

def t_ma_01(dut: Dut):
    """T_MA_01: Spotify→Matrix→Spotify round-trip; appId correct at each step."""
    print("T_MA_01  MatrixApp switch round-trip")
    # Ensure Spotify active.
    if not _restore_spotify(dut):
        skip("T_MA_01", "precondition: could not restore Spotify")
        return
    # Switch to Matrix.
    if not _switch_to(dut, "Matrix"):
        fail("T_MA_01", "did not switch to Matrix")
        _restore_spotify(dut)
        return
    # Switch back.
    if not _restore_spotify(dut):
        fail("T_MA_01", "Matrix→Spotify switch-back failed")
        return
    pass_("T_MA_01", "Spotify→Matrix→Spotify round-trip confirmed via get appId")


# T_MA_02 / T_GOL_02 / T_WX_02 / T_CX_02 retired 2026-09-06 (TASK-598) — all four
# asserted `hit == "CLOCK"`, a fixed literal in cmdTap's terminal `else` on a branch
# selected by the app id `_switch_to` had verified on the line before. Replacement:
# `T_APPKEY_01`, blocked on TASK-637 (ADR-063 D3's per-app identity guard).
# See docs/verification/retired_test_ids.md.


# ── T_MA_03 — Matrix→Spotify canvas residue ──────────────────────────────────

def t_ma_03(dut: Dut):
    """T_MA_03: Spotify renders correctly (lastPlaylistDraw advances) after Matrix switch-back."""
    print("T_MA_03  Matrix→Spotify canvas residue")
    if not _switch_to(dut, "Matrix"):
        # TASK-584 / BP-074: the subject is what Spotify does on the way BACK
        # from Matrix. If we never got to Matrix, the switch-back never
        # happened and nothing about residue was observed. That is an
        # unestablished premise — UNMET, which blocks (ADR-066 D4) — not a
        # skip, which is green and says the configuration excluded the test.
        unmet("T_MA_03", "never entered Matrix, so the Matrix->Spotify "
                       "switch-back this id is about never occurred")
        _restore_spotify(dut)
        return
    time.sleep(0.15)  # allow one or two Matrix ticks
    # Switch back to Spotify.
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.1)
    # TASK-584: establish the residue assertion's OWN precondition before
    # spending a verdict on it — a taskbar tap that missed leaves the shell
    # somewhere else, where a stalled lastPlaylistDraw says nothing about
    # residue. Read it typed: a silent device raises NoAnswer -> UNMET at the
    # runner, a device that answers the wrong app is a real dispatch defect.
    landed = dut.get_str("appId", field="name", timeout=3.0)
    if landed != "Spotify":
        fail("T_MA_03", f"taskbar tap on the Spotify slot left the shell in "
                       f"{landed!r} — the Matrix->Spotify switch-back did not land")
        _restore_spotify(dut)
        return
    if not _check_residue(dut, "T_MA_03"):
        fail("T_MA_03", "lastPlaylistDraw did not advance in 3 s after returning "
                      "to Spotify from Matrix — " + _RESIDUE_DISPROOF)


# ── T_GOL_01 — LifeApp switch round-trip ─────────────────────────────────────

def t_gol_01(dut: Dut):
    """T_GOL_01: Spotify→GoL→Spotify round-trip; appId correct at each step."""
    print("T_GOL_01  LifeApp switch round-trip")
    if not _restore_spotify(dut):
        skip("T_GOL_01", "precondition: could not restore Spotify")
        return
    if not _switch_to(dut, "Life"):
        fail("T_GOL_01", "did not switch to Life")
        _restore_spotify(dut)
        return
    if not _restore_spotify(dut):
        fail("T_GOL_01", "GoL→Spotify switch-back failed")
        return
    pass_("T_GOL_01", "Spotify→GoL→Spotify round-trip confirmed via get appId")


# ── T_GOL_03 — GoL→Spotify canvas residue ────────────────────────────────────

def t_gol_03(dut: Dut):
    """T_GOL_03: Spotify renders correctly after GoL switch-back."""
    print("T_GOL_03  GoL→Spotify canvas residue")
    if not _switch_to(dut, "Life"):
        # TASK-584 / BP-074: the subject is what Spotify does on the way BACK
        # from GoL. If we never got to GoL, the switch-back never
        # happened and nothing about residue was observed. That is an
        # unestablished premise — UNMET, which blocks (ADR-066 D4) — not a
        # skip, which is green and says the configuration excluded the test.
        unmet("T_GOL_03", "never entered GoL, so the GoL->Spotify "
                       "switch-back this id is about never occurred")
        _restore_spotify(dut)
        return
    time.sleep(0.2)  # allow GoL to tick
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.1)
    # TASK-584: establish the residue assertion's OWN precondition before
    # spending a verdict on it — a taskbar tap that missed leaves the shell
    # somewhere else, where a stalled lastPlaylistDraw says nothing about
    # residue. Read it typed: a silent device raises NoAnswer -> UNMET at the
    # runner, a device that answers the wrong app is a real dispatch defect.
    landed = dut.get_str("appId", field="name", timeout=3.0)
    if landed != "Spotify":
        fail("T_GOL_03", f"taskbar tap on the Spotify slot left the shell in "
                       f"{landed!r} — the GoL->Spotify switch-back did not land")
        _restore_spotify(dut)
        return
    if not _check_residue(dut, "T_GOL_03"):
        fail("T_GOL_03", "lastPlaylistDraw did not advance in 3 s after returning "
                      "to Spotify from GoL — " + _RESIDUE_DISPROOF)


# ── T_GOL_04 — GoL alive count updated ───────────────────────────────────────

def t_gol_04(dut: Dut):
    """T_GOL_04: golAlive > 0 after GoL ticks — confirms cells are alive and stepGeneration ran."""
    print("T_GOL_04  GoL alive count > 0")
    if not _switch_to(dut, "Life"):
        skip("T_GOL_04", "could not switch to Life")
        _restore_spotify(dut)
        return
    time.sleep(0.35)  # wait for 3+ GoL ticks (100 ms each)
    r = dut.cmd("get golAlive", timeout=3.0)
    _restore_spotify(dut)
    if not r.get("ok"):
        fail("T_GOL_04", f"get golAlive failed: {r}")
        return
    count = r.get("count", -1)
    if count <= 0:
        fail("T_GOL_04", f"golAlive={count} — expected > 0; GoL may not have ticked or board is empty")
        return
    pass_("T_GOL_04", f"golAlive={count} > 0 — cells alive, stepGeneration confirmed")


# ── T_WX_01 — WeatherApp switch round-trip ───────────────────────────────────

def t_wx_01(dut: Dut):
    """T_WX_01: Spotify→Weather→Spotify round-trip; appId correct at each step."""
    print("T_WX_01  WeatherApp switch round-trip")
    if not _restore_spotify(dut):
        skip("T_WX_01", "precondition: could not restore Spotify")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        switched = _switch_to(dut, "Weather", timeout=15.0)
    if not switched:
        fail("T_WX_01", "did not switch to Weather")
        _restore_spotify(dut)
        return
    if not _restore_spotify(dut):
        fail("T_WX_01", "Weather→Spotify switch-back failed")
        return
    pass_("T_WX_01", "Spotify→Weather→Spotify round-trip confirmed via get appId")


# ── T_WX_03 — Weather→Spotify canvas residue ─────────────────────────────────

def t_wx_03(dut: Dut):
    """T_WX_03: Spotify renders correctly after Weather switch-back."""
    print("T_WX_03  Weather→Spotify canvas residue")
    if not _switch_to(dut, "Weather"):
        # TASK-584 / BP-074: the subject is what Spotify does on the way BACK
        # from Weather. If we never got to Weather, the switch-back never
        # happened and nothing about residue was observed. That is an
        # unestablished premise — UNMET, which blocks (ADR-066 D4) — not a
        # skip, which is green and says the configuration excluded the test.
        unmet("T_WX_03", "never entered Weather, so the Weather->Spotify "
                       "switch-back this id is about never occurred")
        _restore_spotify(dut)
        return
    time.sleep(0.15)
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.1)
    # TASK-584: establish the residue assertion's OWN precondition before
    # spending a verdict on it — a taskbar tap that missed leaves the shell
    # somewhere else, where a stalled lastPlaylistDraw says nothing about
    # residue. Read it typed: a silent device raises NoAnswer -> UNMET at the
    # runner, a device that answers the wrong app is a real dispatch defect.
    landed = dut.get_str("appId", field="name", timeout=3.0)
    if landed != "Spotify":
        fail("T_WX_03", f"taskbar tap on the Spotify slot left the shell in "
                       f"{landed!r} — the Weather->Spotify switch-back did not land")
        _restore_spotify(dut)
        return
    if not _check_residue(dut, "T_WX_03"):
        fail("T_WX_03", "lastPlaylistDraw did not advance in 3 s after returning "
                      "to Spotify from Weather — " + _RESIDUE_DISPROOF)


# ── T_WX_04 — Weather pre-fetch state ────────────────────────────────────────

def t_wx_04(dut: Dut):
    """T_WX_04: weatherReady=false immediately after first switch-in (before fetch completes)."""
    print("T_WX_04  Weather pre-fetch state")
    # Only valid if Weather has never shown in this DUT session.
    r_pre = dut.cmd("get weatherReady", timeout=3.0)
    if not r_pre.get("ok"):
        fail("T_WX_04", f"get weatherReady failed: {r_pre}")
        return
    if r_pre.get("ready") is True:
        skip("T_WX_04",
             "weatherReady already true — Weather fetched data earlier this session; "
             "pre-fetch state no longer observable")
        return
    # Switch to Weather; check immediately (before 60s fetch interval).
    _switch_to(dut, "Weather")
    r_imm = dut.cmd("get weatherReady", timeout=3.0)
    _restore_spotify(dut)
    if not r_imm.get("ok"):
        fail("T_WX_04", f"get weatherReady (immediate) failed: {r_imm}")
        return
    if r_imm.get("ready") is True:
        # Data arrived extremely fast (cached or very fast network) — not a failure.
        skip("T_WX_04", "weatherReady=true immediately — data arrived before check; network too fast?")
        return
    pass_("T_WX_04", "weatherReady=false on switch-in — pre-fetch state confirmed")


# ── T_WX_05 — Weather data arrives ───────────────────────────────────────────

def t_wx_05(dut: Dut):
    """T_WX_05: weatherReady becomes true within 30 s of switching to WeatherApp."""
    print("T_WX_05  Weather data arrives")
    if not _switch_to(dut, "Weather"):
        skip("T_WX_05", "could not switch to Weather")
        _restore_spotify(dut)
        return
    deadline = time.monotonic() + 30.0
    ready = False
    while time.monotonic() < deadline:
        r = dut.cmd("get weatherReady", timeout=3.0)
        if r.get("ok") and r.get("ready") is True:
            ready = True
            break
        time.sleep(2.0)
    if not ready:
        r_prog = dut.cmd("get weatherFetchPhase", timeout=3.0)
        phase = r_prog.get("val") if r_prog.get("ok") else "?"
        phase_name = _CHART_PHASE_NAMES.get(phase, "idle" if phase == -1 else "unknown")
        _restore_spotify(dut)
        fail("T_WX_05", f"weatherReady still false after 30 s — "
                        f"weatherFetchPhase={phase} ({phase_name})")
        return
    _restore_spotify(dut)
    pass_("T_WX_05", "weatherReady=true — WeatherApp received live data from dataTask")


# ── T_WX_07 — weatherFetchPhase atom is actually written ─────────────────────
#
# TASK-657 (oracle sweep A-6). M-DATATASK-PROGRESS Phase 2 delivered
# `weatherFetchPhase`; before this id the whole suite read it at exactly one
# site — T_WX_05's FAILURE branch above, to enrich a message — so a green run
# was precisely the run in which it was never checked. See
# `_helpers._observe_progress_atom` for what this asserts and why not more.
#
# NEVER RUN ON HARDWARE (2026-09-06): written host-side with no DUT available;
# owes its first hardware run, same shape as TASK-645's `get boardId`.

def t_wx_07(dut: Dut):
    """T_WX_07: weatherFetchPhase leaves its -1 sentinel across a weather fetch,
    stays inside 0..2, and returns to -1."""
    print("T_WX_07  weatherFetchPhase atom is written during a weather fetch")
    if not _switch_to(dut, "Weather"):
        unmet("T_WX_07", "could not switch to Weather — no fetch to observe")
        _restore_spotify(dut)
        return
    # ORACLE (phase-2 hardware session, 2026-09-07). This was
    # `lambda: _ready_flag(dut, "weatherReady")` and it produced a FAIL naming a
    # firmware gap that does not exist: `weatherReady` is LATCHED, so on any run
    # where Weather had already fetched once it was true at entry and the poll
    # loop took a single sample. `_dataq_fetch_edge` watches the dataTask queue's
    # own pendingMask/inFlight bit for DATA_FETCH_WEATHER instead — a real
    # per-fetch edge, and still not the atom under test.
    #
    # WINDOW. WeatherApp re-enqueues on its own cadence, WEATHER_FETCH_MS =
    # 60 000 ms (`app/src/apps/weatherApp.h:16`), so a worst case is a full
    # 60 s wait for the tick plus the fetch itself. 80 s is that bound with
    # room; anything shorter can only produce UNMETs on a healthy board.
    obs = _observe_progress_atom(
        dut, "weatherFetchPhase", _dataq_fetch_edge(dut, _FETCH_TYPE["weather"]),
        timeout_s=80.0, test_id="T_WX_07")
    _restore_spotify(dut)
    outcome, msg = _progress_atom_verdict("weatherFetchPhase", obs)
    if outcome == "unmet":
        unmet("T_WX_07", msg)
    elif outcome == "fail":
        fail("T_WX_07", msg)
    else:
        pass_("T_WX_07", msg)


# `_ready_flag` lived here — a `get weatherReady`/`get cryptoReady` wrapper used
# as T_WX_07/T_CX_07's completion oracle. Deleted 2026-09-07 (phase-2 hardware
# session) rather than left dead: both `*Ready` flags are LATCHED, so as a
# completion oracle it was always-true after the app's first successful fetch,
# which is what made both ids sample the atom once and FAIL. Do not reintroduce
# it for that purpose; `_helpers._dataq_fetch_edge` is the per-fetch edge.


# ── T_CX_01 — CryptoApp switch round-trip ────────────────────────────────────

def t_cx_01(dut: Dut):
    """T_CX_01: Spotify→Crypto→Spotify round-trip; appId correct at each step."""
    print("T_CX_01  CryptoApp switch round-trip")
    if not _restore_spotify(dut):
        skip("T_CX_01", "precondition: could not restore Spotify")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        switched = _switch_to(dut, "Crypto", timeout=15.0)
    if not switched:
        fail("T_CX_01", "did not switch to Crypto")
        _restore_spotify(dut)
        return
    if not _restore_spotify(dut):
        fail("T_CX_01", "Crypto→Spotify switch-back failed")
        return
    pass_("T_CX_01", "Spotify→Crypto→Spotify round-trip confirmed via get appId")


# ── T_CX_03 — Crypto→Spotify canvas residue ──────────────────────────────────

def t_cx_03(dut: Dut):
    """T_CX_03: Spotify renders correctly after Crypto switch-back."""
    print("T_CX_03  Crypto→Spotify canvas residue")
    if not _switch_to(dut, "Crypto"):
        # TASK-584 / BP-074: the subject is what Spotify does on the way BACK
        # from Crypto. If we never got to Crypto, the switch-back never
        # happened and nothing about residue was observed. That is an
        # unestablished premise — UNMET, which blocks (ADR-066 D4) — not a
        # skip, which is green and says the configuration excluded the test.
        unmet("T_CX_03", "never entered Crypto, so the Crypto->Spotify "
                       "switch-back this id is about never occurred")
        _restore_spotify(dut)
        return
    time.sleep(0.15)
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=3.0)
    time.sleep(0.1)
    # TASK-584: establish the residue assertion's OWN precondition before
    # spending a verdict on it — a taskbar tap that missed leaves the shell
    # somewhere else, where a stalled lastPlaylistDraw says nothing about
    # residue. Read it typed: a silent device raises NoAnswer -> UNMET at the
    # runner, a device that answers the wrong app is a real dispatch defect.
    landed = dut.get_str("appId", field="name", timeout=3.0)
    if landed != "Spotify":
        fail("T_CX_03", f"taskbar tap on the Spotify slot left the shell in "
                       f"{landed!r} — the Crypto->Spotify switch-back did not land")
        _restore_spotify(dut)
        return
    if not _check_residue(dut, "T_CX_03"):
        fail("T_CX_03", "lastPlaylistDraw did not advance in 3 s after returning "
                      "to Spotify from Crypto — " + _RESIDUE_DISPROOF)


# ── T_CX_04 — Crypto pre-fetch state ─────────────────────────────────────────

def t_cx_04(dut: Dut):
    """T_CX_04: cryptoReady=false immediately after first switch-in (before fetch completes)."""
    print("T_CX_04  Crypto pre-fetch state")
    r_pre = dut.cmd("get cryptoReady", timeout=3.0)
    if not r_pre.get("ok"):
        fail("T_CX_04", f"get cryptoReady failed: {r_pre}")
        return
    if r_pre.get("ready") is True:
        skip("T_CX_04",
             "cryptoReady already true — Crypto fetched data earlier this session; "
             "pre-fetch state no longer observable")
        return
    _switch_to(dut, "Crypto")
    r_imm = dut.cmd("get cryptoReady", timeout=3.0)
    _restore_spotify(dut)
    if not r_imm.get("ok"):
        fail("T_CX_04", f"get cryptoReady (immediate) failed: {r_imm}")
        return
    if r_imm.get("ready") is True:
        skip("T_CX_04", "cryptoReady=true immediately — data arrived before check")
        return
    pass_("T_CX_04", "cryptoReady=false on switch-in — pre-fetch state confirmed")


# ── T_CX_05 — Crypto data arrives ────────────────────────────────────────────

def t_cx_05(dut: Dut):
    """T_CX_05: cryptoReady becomes true within 30 s of switching to CryptoApp."""
    print("T_CX_05  Crypto data arrives")
    if not _switch_to(dut, "Crypto"):
        skip("T_CX_05", "could not switch to Crypto")
        _restore_spotify(dut)
        return
    deadline = time.monotonic() + 30.0
    ready = False
    while time.monotonic() < deadline:
        r = dut.cmd("get cryptoReady", timeout=3.0)
        if r.get("ok") and r.get("ready") is True:
            ready = True
            break
        time.sleep(2.0)
    if not ready:
        r_code = dut.cmd("get cryptoHttpCode", timeout=3.0)
        http_code = r_code.get("val", "?") if r_code.get("ok") else "?"
        r_prog = dut.cmd("get cryptoFetchPhase", timeout=3.0)
        phase = r_prog.get("val") if r_prog.get("ok") else "?"
        phase_name = _CHART_PHASE_NAMES.get(phase, "idle" if phase == -1 else "unknown")
        _restore_spotify(dut)
        fail("T_CX_05", f"cryptoReady still false after 30 s — "
                        f"cryptoFetchPhase={phase} ({phase_name}), HTTP code: {http_code}")
        return
    _restore_spotify(dut)
    pass_("T_CX_05", "cryptoReady=true — CryptoApp received live data from dataTask")


# ── T_CX_07 — cryptoFetchPhase atom is actually written ──────────────────────
#
# TASK-657 (oracle sweep A-6). `cryptoFetchPhase` was read at ZERO sites in the
# suite before this id — a grep of the whole tree found none. It is the atom
# M-DATATASK-PROGRESS Phase 2 exists to add, and nothing ever looked at it.
#
# NEVER RUN ON HARDWARE (2026-09-06): written host-side with no DUT available;
# owes its first hardware run, same shape as TASK-645's `get boardId`.

def t_cx_07(dut: Dut):
    """T_CX_07: cryptoFetchPhase leaves its -1 sentinel across a crypto fetch,
    stays inside 0..2, and returns to -1."""
    print("T_CX_07  cryptoFetchPhase atom is written during a crypto fetch")
    if not _switch_to(dut, "Crypto"):
        unmet("T_CX_07", "could not switch to Crypto — no fetch to observe")
        _restore_spotify(dut)
        return
    # ORACLE / WINDOW: see the note in t_wx_07 above — `cryptoReady` is latched
    # the same way (`CryptoApp::_dataReady`), and CRYPTO_FETCH_MS is likewise
    # 60 000 ms (`app/src/apps/cryptoApp.h:13`).
    obs = _observe_progress_atom(
        dut, "cryptoFetchPhase", _dataq_fetch_edge(dut, _FETCH_TYPE["crypto"]),
        timeout_s=80.0, test_id="T_CX_07")
    _restore_spotify(dut)
    outcome, msg = _progress_atom_verdict("cryptoFetchPhase", obs)
    if outcome == "unmet":
        unmet("T_CX_07", msg)
    elif outcome == "fail":
        fail("T_CX_07", msg)
    else:
        pass_("T_CX_07", msg)


# ── T_X07_01 — dataTask cross-feature: rapid Weather↔Crypto switching ────────

@meta(cls="FEATURE", cls_reason=
      "TASK-626, approved 2026-09-06. DEMOTED from the CORE declared by TASK-591, "
      "which did not know what this gate later measured: the id's premise IS two "
      "activation fetches. Its subject is rapid Weather<->Crypto switching under "
      "dataTask contention, and the contention is supplied by Weather's and Crypto's "
      "fetch-on-activation — so unlike the other seven R36 cases there is no version "
      "of it that holds offline. Injecting the precondition would delete the subject, "
      "and no exception exists for a gating class that needs the network, so the "
      "class goes rather than the id. Its failure is LOCAL on the evidence it "
      "actually has: `get dataq` is never read (WP-C), so the docstring's 'no dataTask "
      "queue corruption' has no oracle, and what remains is five `appId` comparisons "
      "plus a liveness `info` — the single-switch half of which T147 already asserts "
      "and declares CORE. The churn claim keeps running as a FEATURE id; it simply no "
      "longer NOT-RUNs 167 ids when the weather or crypto endpoint is unreachable.")
def t_x07_01(dut: Dut):
    """T_X07_01 (X007): rapid Weather→Crypto→Weather→Crypto→Spotify; DUT stable throughout."""
    print("T_X07_01  dataTask cross-feature: rapid Weather↔Crypto switching")
    if not _restore_spotify(dut):
        skip("T_X07_01", "precondition: could not restore Spotify")
        return
    sequence = [
        ("Weather", APP_SLOT["Weather"]),
        ("Crypto",  APP_SLOT["Crypto"]),
        ("Weather", APP_SLOT["Weather"]),
        ("Crypto",  APP_SLOT["Crypto"]),
        ("Spotify", APP_SLOT["Spotify"]),
    ]
    for app_name, slot in sequence:
        dut.set_cooldown_zero()
        x, y = _c.tap_taskbar_slot(slot)
        dut.cmd(f"tap {x} {y}", timeout=3.0)
        time.sleep(0.2)
        r = dut.cmd("get appId", timeout=3.0)
        if not r.get("ok") or r.get("name") != app_name:
            # Ensure we're back to Spotify before failing.
            _restore_spotify(dut)
            fail("T_X07_01",
                 f"expected appId={app_name!r}, got {r.get('name')!r} — "
                 f"DUT unstable during rapid dataTask switching")
            return
    # Final sanity: DUT still responds to info.
    r_info = dut.cmd("info", timeout=4.0)
    if not r_info.get("ok"):
        fail("T_X07_01", "DUT unresponsive after rapid switching — info command failed")
        return
    pass_("T_X07_01",
          "Weather→Crypto×2→Spotify round-trip clean; DUT stable; "
          "no dataTask queue corruption detected")


# ── M-TOUCH-UX suite (TASK-118) ───────────────────────────────────────────────
# Verifies: busy indicator (shellBusy), cooldown gate, g_shellBusy cmdTap gate.
# Firmware prerequisites: get shellBusy, get visMode, cmdTap g_shellBusy check.
# All tests require cyd2usb_winamp_debug build.

_SPOTIFY_APP_ID = APP_SLOT["Spotify"]
_CLOCK_APP_ID   = APP_SLOT["Clock"]



def _poll_chart_len_positive(dut: Dut, timeout_s: float = 45.0) -> bool:
    """Poll get chartLen until > 0 (fetch complete)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = _stock_get(dut, "chartLen")
        try:
            if r.get("ok") and int(r.get("val", 0)) > 0:
                return True
        except (ValueError, TypeError):
            pass
        time.sleep(1.0)
    # TASK-386: same treatment as _wait_chart_complete — automatic for every caller.
    _diag_snapshot(dut, "_poll_chart_len_positive-timeout")
    return False


def _get_shell_busy(dut: Dut) -> bool | None:
    """Return current shellBusy bool, or None on error."""
    r = dut.cmd("get shellBusy", timeout=2.0)
    if r.get("ok"):
        return r.get("busy")
    return None


def _busy05_verdict(results: list) -> tuple:
    """T-BUSY-05's post-switch adjudication, split out so it can be pinned by a
    host test independent of the DUT (TASK-582, WP-C C-1).

    Lives here, beside its only caller, and NOT in `_helpers.py`: that module's
    own docstring reserves itself for helpers shared by 2+ families and sends a
    single-family helper back to its family's module (M-TOOLING §3). Being
    host-testable is not a reason to promote it — the test imports it from
    here.

    `results` is the list of `_get_shell_busy()` readings taken after
    `switchApp`; each entry is `True`, `False` or `None` (a failed `get
    shellBusy` read). -> (outcome, message) where outcome is
    'pass' | 'fail' | 'unmet'.

    A `None` in the list means the read itself failed — the test's premise
    (that shellBusy could be observed) never held, so that is `unmet`, not a
    verdict on the firmware (TASK-596/R18: a failed read must never silently
    stand in for a real reading, and per lib/results.py an unreadable value is
    closer to UNMET than to FAIL). Only once every reading is a real bool does
    this adjudicate the firmware: all-False is the amber clearing (pass),
    anything else — including all-True, the total regression this function
    exists to catch — is fail.
    """
    if any(b is None for b in results):
        return ("unmet", f"get shellBusy failed during post-switch poll: {results}")
    if any(b is not False for b in results):
        return ("fail", f"shellBusy not false after switchApp: {results}")
    return ("pass", f"shellBusy=false in all 3 polls after switchApp (results={results})")


# ── T-BUSY-01 — StockApp row tap triggers busy; clears on fetch complete ──────

@meta(cls="FEATURE", cls_reason=
      "TASK-626, approved 2026-09-06. DEMOTED from a SEEDED CORE (the seed came from "
      "shell.py's catch-all scope, not from an argument anyone made). Its failure is "
      "LOCAL: what it observes is StockApp's own chart fetch completing and the amber "
      "clearing behind it, so a failure costs the Stock chart assertions and nothing "
      "else. The `shellBusy` premise the whole suite leans on — the flag rises when "
      "work is enqueued and clears when it finishes — is asserted on BOTH edges, with "
      "a hard `fail()` on each, by T-BUSY-02, which is declared CORE and needs no "
      "network. This id cannot carry that premise anyway: `shell.py`'s busy-rose half "
      "is downgraded to a printed note, leaving `busy == False` at rest, which cannot "
      "distinguish auto-clear from never-rose. And its pass/fail is a network outcome "
      "— `_poll_chart_len_positive` is 45 s of live HTTPS to Yahoo and a timeout is a "
      "hard `fail()` — so under the class order it would NOT-RUN the FEATURE suite on "
      "an outage (R36).")
def t_busy_01(dut: Dut):
    """T-BUSY-01: switchApp(Stock) → tap AAPL row → shellBusy true → chartLen>0 → shellBusy false."""
    print("T-BUSY-01  StockApp row tap → amber → clears on fetch complete")
    # TASK-386: entry baseline. This is a single self-contained fetch (no self-induced
    # stress like T204) — structurally identical to T193's case, so its "chartLen never
    # exceeded 0" failure is most plausibly suite-accumulated-state-dependent, not
    # something an isolated run/test-targeted repro could validate on its own.
    entry_diag = _diag_snapshot(dut, "T-BUSY-01-entry")
    if not _switch_to_stock(dut):
        skip("T-BUSY-01", "could not switch to StockApp")
        return
    # Ensure list view (tap back to list if needed)
    dut.cmd("tap 10 7", timeout=2.0)  # back tap — no-op if already in list
    time.sleep(0.3)
    pre_diag = _diag_snapshot(dut, "T-BUSY-01-pre-trigger")
    # Tap AAPL row (137, 36) to drill to chart and trigger async fetch
    dut.cmd("tap 137 36", timeout=2.0)
    # Poll for busy (may be brief; miss → test gap, not firmware defect)
    busy_seen = _poll_shell_busy(dut, True, timeout_ms=500)
    if not busy_seen:
        # Not necessarily a defect — busy window may be shorter than poll granularity
        print("  [T-BUSY-01] shellBusy=true not observed within 500 ms (test gap; continuing)")
    else:
        print("  [T-BUSY-01] shellBusy=true observed")
    # Wait for chart fetch to complete (chartLen > 0)
    print("  [T-BUSY-01] waiting for chartLen > 0…", flush=True)
    if not _poll_chart_len_positive(dut, timeout_s=45.0):
        timeout_diag = _diag_snapshot(dut, "T-BUSY-01-timeout")
        _restore_from_stock(dut)
        fail("T-BUSY-01", "chartLen did not exceed 0 after 45 s — fetch did not complete | "
                           f"entry={entry_diag} | pre-trigger={pre_diag} | timeout={timeout_diag}")
        return
    # After fetch, shellBusy must be false
    time.sleep(0.1)
    busy_after = _get_shell_busy(dut)
    _restore_from_stock(dut)
    if busy_after is None:
        fail("T-BUSY-01", "get shellBusy failed after chart fetch")
        return
    if busy_after:
        fail("T-BUSY-01", "shellBusy still true after chartLen > 0 — auto-clear did not fire")
        return
    pass_("T-BUSY-01", f"shellBusy cleared after chart fetch complete (busy_seen={busy_seen})")


# ── T-BUSY-01b — StockApp tab-range tap also triggers busy ────────────────────

@meta(cls="FEATURE", cls_reason=
      "TASK-626, approved 2026-09-06. DEMOTED from a SEEDED CORE, same family and same "
      "argument as T-BUSY-01, and this is the weaker of the two. Its failure is LOCAL: "
      "it observes StockApp's 5D range tab re-issuing a chart fetch, so a failure costs "
      "the Stock range-tab assertion alone. It cannot carry the `shellBusy` premise for "
      "anyone: its negative outcome is a `skip()` (`warm fetch too fast`), so a genuine "
      "regression in which the tap raises nothing is indistinguishable from a fast "
      "fetch and the id reports green — the raise half it exists to supply is "
      "unfalsifiable in practice, and three `skip()` exits stand in front of it. "
      "T-BUSY-02 holds the premise with a hard `fail()` on both edges. Two live chart "
      "fetches make its precondition unsatisfiable offline besides (R36).")
def t_busy_01b(dut: Dut):
    """T-BUSY-01b: drill to chart, tap 5D tab → shellBusy true."""
    print("T-BUSY-01b  StockApp tab-range tap → amber")
    if not _switch_to_stock(dut):
        skip("T-BUSY-01b", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("tap 10 7", timeout=2.0)
        time.sleep(0.3)
        # tap-to-list triggers a quote refresh; wait for it to settle.
        _wait_shell_not_busy(dut, timeout_s=10.0)
        # Force stale cache BEFORE drill-in so the drill always triggers a fresh fetch.
        dut.cmd("set triggerFetch 1", timeout=2.0)
        drill_before = _stock_ok_count(dut)
        dut.cmd("tap 137 36", timeout=10.0)
        time.sleep(0.3)
        if not _wait_chart_complete(dut, drill_before, timeout_s=45.0):
            _restore_from_stock(dut)
            skip("T-BUSY-01b", "initial chart fetch did not complete — cannot test tab-range path")
            return
        time.sleep(0.1)
        before5d = _stock_ok_count(dut)
        dut.cmd("tap 184 7", timeout=2.0)
        busy_seen = _poll_shell_busy(dut, True, timeout_ms=5000, cmd_timeout=1.0)
        _wait_chart_complete(dut, before5d, timeout_s=45.0)
    _restore_from_stock(dut)
    if not busy_seen:
        skip("T-BUSY-01b", "shellBusy=true not observed within 5 s after 5D tap — warm fetch too fast")
        return
    pass_("T-BUSY-01b", "shellBusy=true observed after 5D range tab tap")


# ── T-BUSY-02 — Spotify PLAY tap triggers busy; clears ────────────────────────

@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="CORE", cls_reason=
      "`shellBusy` is the suite's universal synchronisation primitive: "
      "`_wait_shell_not_busy` and `_poll_shell_busy` gate taps in every family, and "
      "`Dut.cmd` leans on the same state. If the flag does not rise when an action "
      "is enqueued, tests tap while the previous action is still in flight; if it "
      "does not clear when the action finishes, their preconditions time out into "
      "skips and the run goes green having tested nothing. This is the only id that "
      "asserts BOTH edges and hard-fails on each (WP-C: the best of the busy "
      "family).")
def t_busy_02(dut: Dut):
    """T-BUSY-02: Spotify PLAY tap → shellBusy true → clears within 3 s."""
    print("T-BUSY-02  Spotify PLAY → amber → clears")
    if not _restore_spotify(dut):
        skip("T-BUSY-02", "could not restore Spotify app")
        return
    vx, vy = _c.tap_button("PLAY")
    dut.cmd(f"tap {vx} {vy}", timeout=2.0)
    busy_seen = _poll_shell_busy(dut, True, timeout_ms=500)
    if not busy_seen:
        fail("T-BUSY-02", "shellBusy=true not observed within 500 ms after PLAY tap")
        return
    print("  [T-BUSY-02] shellBusy=true; waiting for clear (max 3.5 s)…", flush=True)
    cleared = _poll_shell_busy(dut, False, timeout_ms=3500)
    if not cleared:
        fail("T-BUSY-02", "shellBusy still true after 3.5 s — auto-clear or queue drain did not fire")
        return
    pass_("T-BUSY-02", "shellBusy true→false observed after PLAY tap")


# ── T-BUSY-03 — Passive apps: no amber on canvas tap ─────────────────────────

@meta(cls="CORE", cls_reason=
      "The negative half of T-BUSY-02's premise, and it fails in the direction that "
      "hurts most. If an ordinary canvas tap in a passive app raises `shellBusy`, "
      "`_wait_shell_not_busy` never returns for the Clock, Matrix, Life and Aquarium "
      "families, their preconditions all expire into skips, and the run reports "
      "green having exercised none of them. Four apps asserted in one pass, all "
      "device-observed, one hard `fail()`. R36 (TASK-626, approved 2026-09-06): the "
      "two fetch-on-activation apps this id used to include, Weather and Crypto, were "
      "REMOVED from the list rather than the class being demoted — see the note in "
      "the body for why that costs no coverage.")
def t_busy_03(dut: Dut):
    """T-BUSY-03: Clock/Matrix/Life/Aquarium canvas taps → shellBusy false."""
    print("T-BUSY-03  Passive apps — no amber on canvas tap")
    # Use switchApp <id> for all — avoids taskbar scroll issues.
    #
    # TASK-626 / R36 (approved 2026-09-06): Weather and Crypto were dropped from this
    # list. They fetch on activation, which made a CORE id's precondition depend on
    # two live HTTP endpoints — under the class order an outage there would NOT-RUN
    # every FEATURE id below. Dropping them costs NO coverage, and that is a fact
    # about `cmdTap`, not a judgement: `debug/serialConsole/cmdTouch.cpp` dispatches
    # an injected canvas tap by `currentAppId`, and Weather, Crypto, Matrix, Life and
    # Aquarium all fall through the same terminal `else` (`hit=CLOCK`) — one branch,
    # no app handler, no `hasPendingAsync()` check, hence no `setBusy` call reachable.
    # Clock is the one with a branch of its own (`CLOCKAPP`), and it too makes no
    # `setBusy` call ("no async, so no setBusy propagation"). So the four retained
    # apps drive every code path the six drove; Weather and Crypto were duplicates of
    # the Matrix/Life/Aquarium path plus a network dependency. The claim the cls_reason
    # states — `_wait_shell_not_busy` must keep returning for the passive families —
    # names exactly Clock, Matrix, Life and Aquarium.
    PASSIVE_APPS = [
        (name, APP_SLOT[name])
        for name in ["Clock", "Matrix", "Life", "Aquarium"]
        if name in APP_SLOT
    ]
    errors = []
    for app_name, app_id in PASSIVE_APPS:
        _wait_shell_not_busy(dut, timeout_s=10.0)
        with _bgpoll_suspended(dut):
            r = dut.cmd(f"switchApp {app_id}", timeout=3.0)
            if not r.get("ok"):
                errors.append(f"{app_name}: switchApp failed: {r}")
                continue
            time.sleep(0.5)
            r_tap = dut.cmd("tap 137 120", timeout=5.0)
            if not r_tap.get("ok"):
                errors.append(f"{app_name}: tap failed: {r_tap}")
                continue
            time.sleep(0.1)
            busy = _get_shell_busy(dut)
        if busy is None:
            errors.append(f"{app_name}: get shellBusy failed")
        elif busy:
            errors.append(f"{app_name}: shellBusy=true after canvas tap (unexpected)")
        else:
            print(f"  [T-BUSY-03] {app_name}: shellBusy=false ✓")
    _restore_spotify(dut)
    if errors:
        fail("T-BUSY-03", "; ".join(errors))
    else:
        pass_("T-BUSY-03", f"all {len(PASSIVE_APPS)} passive apps: shellBusy=false after canvas tap")


# ── T-BUSY-05 — App switch while busy clears amber ────────────────────────────

@meta(cls="FEATURE", cls_reason=
      "TASK-626, approved 2026-09-06; C-1 corrected by TASK-582 on 2026-09-12, class "
      "UNCHANGED. The demotion was argued on the ground that the id could not report a "
      "failure at all: WP-C `C-1`, the end-of-body guard was inverted (`if any(b is "
      "not True ...)` is False exactly when all three post-switch reads are `True`, "
      "i.e. when the amber did NOT clear), so control fell through to `pass_()` "
      "precisely on the regression. That guard is GONE — `_busy05_verdict` now fails "
      "the all-True case and returns `unmet` on an unreadable one, pinned host-side by "
      "`suite/test_busy05_guard.py`. The class stays FEATURE anyway, for the reason "
      "the demotion gave second and TASK-582 did not touch: this id has NEVER been "
      "observed exercising its corrected path, so there is no evidence either way "
      "about the firmware behaviour underneath, and three `skip()` exits upstream "
      "mean the assertion is reached only when all three preconditions hold. "
      "Re-promotion needs a hardware run, not a corrected predicate. Its precondition "
      "(`set triggerFetch 1` + a Stock activation fetch) is not satisfiable offline "
      "either (R36).")
def t_busy_05(dut: Dut):
    """T-BUSY-05: Stock row tap (busy) → switchApp(Spotify) → shellBusy false × 3."""
    print("T-BUSY-05  App switch while busy → amber clears")
    if not _switch_to_stock(dut):
        skip("T-BUSY-05", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("tap 10 7", timeout=2.0)
        time.sleep(0.3)
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.cmd("set triggerFetch 1", timeout=2.0)
        r_d = dut.cmd("tap 137 36", timeout=5.0)
        drilled = (not r_d.get("skipped")) and (
            dut.cmd("get stockSubView", timeout=3.0).get("val") == "chart"
        )
        if not drilled:
            _restore_from_stock(dut)
            skip("T-BUSY-05", "could not drill to chart (tap skipped or wrong subView)")
            return
        busy_seen = _poll_shell_busy(dut, True, timeout_ms=5000, cmd_timeout=1.0)
        if not busy_seen:
            _restore_from_stock(dut)
            skip("T-BUSY-05", "shellBusy=true not observed within 5 s — warm connection completed fetch too fast")
            return
        dut.cmd(f"switchApp {_SPOTIFY_APP_ID}", timeout=3.0)
        time.sleep(0.05)
        results = []
        for _ in range(3):
            results.append(_get_shell_busy(dut))
            time.sleep(0.02)
        _poll_shell_busy(dut, False, timeout_ms=5000)
    outcome, msg = _busy05_verdict(results)
    if outcome == "unmet":
        unmet("T-BUSY-05", msg)
    elif outcome == "fail":
        fail("T-BUSY-05", msg)
    else:
        pass_("T-BUSY-05", msg)


# ── T-CDWN-01 — VIS Phase-2 cooldown gate (touchScreenCoolDownTime) ───────────

@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. Its subject is "
      "SpotifyApp's VIS 300 ms cooldown — a canvas feature. The gate the suite's own "
      "tap primitive drains before every tap is the shell's `s_cooldownMs`, a "
      "different variable (see T_TBFB_04's docstring), so VIS cycling misbehaving "
      "costs exactly the VIS assertions and nothing else. WP-C rates the body the "
      "most carefully built in the CORE set; that is an argument about its quality, "
      "not about its reach.")
def t_cdwn_01(dut: Dut):
    """T-CDWN-01: VIS cycling — tap 1 cycles; tap 2 inside the VIS 300 ms window
    suppressed; tap 3 after `get cooldown` polls to 0 cycles.

    TASK-297 (2026-07-10 rework): the historical flake was never the VIS 300 ms
    edge — it was the SHELL cooldown (main.cpp s_cooldownMs: every release arms
    +200 ms and an armed Press is silently dropped). Dut.cmd now drains it
    before every tap, so tap 2 naturally lands at ~200-280 ms post-tap-1 —
    inside [shell-clear, VIS-expiry]. The VIS gate reading taken right after
    tap 2 proves the window was actually hit; a missed window (gate already 0)
    retries the whole sequence instead of failing."""
    print("T-CDWN-01  VIS Phase-2 cooldown gate")
    if not _restore_spotify(dut):
        skip("T-CDWN-01", "could not restore Spotify app")
        return
    dut.cmd("set cooldown 0", timeout=2.0)
    vx, vy = _c.tap_vis()

    for attempt in range(3):
        # g_shellBusy is the OTHER silent Press-dropper on main.cpp's input
        # gate (T079 precedent) — on a fresh boot the Spotify app's pending
        # async (403-latched poll) holds it armed right when tap 1 fires.
        if not _wait_shell_not_busy(dut, timeout_s=10.0):
            skip("T-CDWN-01", "g_shellBusy never cleared — cannot tap")
            return
        m0 = _get_vis_mode(dut)
        if m0 is None:
            fail("T-CDWN-01", "get visMode failed at baseline")
            return
        # Tap 1 — cycles to M1 (cmd() drains the shell cooldown first)
        dut.cmd(f"tap {vx} {vy}", timeout=2.0)
        m1 = _get_vis_mode(dut)
        if m1 is None:
            fail("T-CDWN-01", "get visMode failed after tap 1")
            return
        if m1 == m0:
            busy = dut.cmd("get shellBusy", timeout=2.0).get("busy")
            sc = dut.cmd("get shellCooldown", timeout=2.0).get("remainingMs")
            fail("T-CDWN-01", f"tap 1 did not cycle visMode (stuck at {m0}) — "
                              f"post-tap gates: shellBusy={busy} shellCooldown={sc}ms")
            return
        # Tap 2 — cmd()'s shell drain holds it until ~200 ms post-release, then
        # it must land while the VIS gate (300 ms from tap 1) is still live.
        dut.cmd(f"tap {vx} {vy}", timeout=2.0)
        r_gate = dut.cmd("get cooldown", timeout=2.0)
        gate_rem = int(r_gate.get("remainingMs", -1))
        m_after2 = _get_vis_mode(dut)
        if m_after2 is None:
            fail("T-CDWN-01", "get visMode failed after tap 2")
            return
        if m_after2 != m1:
            # VIS gate expired before tap 2 arrived — window missed, not a
            # product failure. Retry the sequence from the new baseline.
            print(f"  [T-CDWN-01] attempt {attempt + 1}: tap 2 landed past the "
                  f"VIS window (visMode {m1}→{m_after2}, gate={gate_rem} ms) — retrying")
            continue
        print(f"  [T-CDWN-01] tap 1: visMode {m0}→{m1}; tap 2 suppressed "
              f"(VIS gate {gate_rem} ms live at check)")
        # Tap 3 — poll the VIS gate to 0 (shell drain happens inside cmd()).
        deadline = time.monotonic() + 2.0
        rem = gate_rem
        while rem > 0 and time.monotonic() < deadline:
            time.sleep(min(rem / 1000.0, 0.1))
            rem = int(dut.cmd("get cooldown", timeout=2.0).get("remainingMs", 0))
        if rem > 0:
            fail("T-CDWN-01", f"VIS cooldown never reached 0 within 2 s after tap 2 (last={rem} ms)")
            return
        # Tap 1's consumed Press arms g_shellBusy when the app has pending
        # async (main.cpp ~1985) — in suite context the Spotify poll makes
        # that routine, and an armed busy silently drops tap 3. No window
        # constraint here, so wait it out.
        if not _wait_shell_not_busy(dut, timeout_s=10.0):
            skip("T-CDWN-01", "g_shellBusy never cleared before tap 3")
            return
        dut.cmd(f"tap {vx} {vy}", timeout=2.0)
        m2 = _get_vis_mode(dut)
        if m2 is None:
            fail("T-CDWN-01", "get visMode failed after tap 3")
            return
        if m2 == m1:
            busy = dut.cmd("get shellBusy", timeout=2.0).get("busy")
            sc = dut.cmd("get shellCooldown", timeout=2.0).get("remainingMs")
            fail("T-CDWN-01", f"tap 3 did not cycle visMode (stuck at {m1}) with "
                              f"VIS gate 0 — post-tap gates: shellBusy={busy} "
                              f"shellCooldown={sc}ms")
            return
        print(f"  [T-CDWN-01] tap 3: visMode {m1}→{m2}")
        pass_("T-CDWN-01", f"Phase-2 gate confirmed: tap2 suppressed, tap3 cycled "
                           f"({m0}→{m1}→{m1}→{m2}); attempt {attempt + 1}")
        return
    fail("T-CDWN-01", "VIS suppression window missed on 3 consecutive attempts — "
                      "shell drain (~200 ms) + serial RTT may exceed the VIS 300 ms gate")


# ── T-CDWN-02 / T-CDWN-04 — the cmdTap g_shellBusy gate, split ───────────────
#
# TASK-626 / R36, approved 2026-09-06. One body used to carry two assertions of
# very different kinds:
#
#   PRIMARY   — a canvas tap issued while the shell is busy comes back
#               `skipped:true`. The oracle is the SHELL's tap gate; it resolves
#               the instant the reply arrives, and it is what earns the CORE
#               class, because the whole corpus reads `skipped` to know whether
#               its tap landed.
#   SECONDARY — the refused tap did not ALSO enqueue a fetch: exactly one chart
#               fetch resolves. Its oracle is Yahoo Finance answering an ESP32
#               over TLS within 60 s.
#
# Bundled, the second made the first's id network-dependent, and under TASK-566's
# class order a Yahoo outage would NOT-RUN the 167 FEATURE ids below it. They are
# now two ids: `T-CDWN-02` keeps the primary and the class, `T-CDWN-04` carries
# the secondary as a FEATURE id that may take as long as it likes and fail on a
# network it cannot reach without stopping anything.
#
# WHY A SECOND ID AND NOT A NON-BLOCKING ASSERTION IN ONE BODY. Both were
# offered. An in-body "assertion that cannot block" leaves the 60 s live fetch
# and the `fetchOkCount` reads inside a CORE id's call closure, so the id still
# spends a minute of every gated run waiting on an external service and R36's
# checker — correctly — still reads it as network-dependent. Splitting removes
# the wait and the reads from the gating body outright. It also forces the thing
# that was actually missing: with the fetch-count half gone, `T-CDWN-02` had no
# reachable `fail()` left at all (R34), which is the plain statement of what
# skip-adjudication row 101 recorded — the PRIMARY assertion's own negative
# outcome was a `skip()`. Fixed here, with the `shellBusy` reading that row named
# as the precondition of converting it.


def _cdwn_stale_chart_list(dut: Dut) -> None:
    """In StockApp: return to the list view and force the chart cache stale, so
    the next drill tap enqueues a real chart fetch and `shellBusy` rises.

    Shared by `T-CDWN-02` and `T-CDWN-04` at ONE lexical site on purpose. The
    `set triggerFetch 1` here cannot go through `Dut.injected()`: the firmware
    accepts only the literal `1` (`app/src/stock/stockApp.cpp:222`, `strcmp(val,
    "1") == 0`), so the clear-to write a restore manager performs on exit would
    be refused and raise — and there is nothing to clear anyway, the command
    zeroes cache timestamps rather than arming a latch. R17's ratchet counts
    write SITES, so sharing this one keeps the split count-neutral.
    """
    dut.cmd("tap 10 7", timeout=5.0)
    time.sleep(0.3)
    # tap-to-list triggers a quote refresh; wait for it before issuing more commands.
    _wait_shell_not_busy(dut, timeout_s=10.0)
    dut.cmd("set triggerFetch 1", timeout=2.0)


@meta(scope="Stock", scope_reason="drives-stock-only",
      cls="CORE", cls_reason=
      "The `cmdTap` `g_shellBusy` gate is what makes an injected tap issued during "
      "an in-flight async action come back `skipped:true` instead of being "
      "delivered. The suite reads that field to know whether its tap landed — T079, "
      "T-BUSY-05 and every `r.get('skipped')` check in the corpus. If the gate stops "
      "dropping, taps double up and `skipped` stops meaning anything, everywhere. "
      "Scope is declared `Stock` per WP-B B-1 (it drives StockApp exclusively and a "
      "Stock change must select it); the class is declared CORE anyway because the "
      "ORACLE is the shell's tap gate, not the chart. TASK-626: the 60 s live-Yahoo "
      "assertion that made this id network-dependent is now T-CDWN-04 (FEATURE), and "
      "the gate assertion it left behind is a real `fail()` guarded by a `shellBusy` "
      "reading, not the `skip()` WP-C C-7 objected to. The residue R36 still reports "
      "is the ARMING — `set triggerFetch 1` plus a Stock activation — which is a "
      "local write and a local enqueue; see the ledger row.")
def t_cdwn_02(dut: Dut):
    """T-CDWN-02: a canvas tap issued while shellBusy is true is refused by cmdTap's
    g_shellBusy gate — the reply carries skipped:true.

    One assertion, and it is the gating one. The verdict resolves on the shell's
    own reply; nothing here waits on a fetch to COMPLETE, only on one to be
    enqueued. The "exactly one fetch resolved" half is T-CDWN-04.
    """
    print("T-CDWN-02  cmdTap g_shellBusy gate blocks second tap")
    if not _switch_to_stock(dut):
        skip("T-CDWN-02", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        _cdwn_stale_chart_list(dut)
        r_d = dut.cmd("tap 137 36", timeout=5.0)
        if r_d.get("skipped"):
            _restore_from_stock(dut)
            skip("T-CDWN-02", "drill tap skipped — shell still busy after precondition wait")
            return
        # BP-074 / skip-adjudication row 101. The negative outcome below used to be
        # a skip() for one stated reason: nothing established that the gate was ARMED
        # when tap2 arrived, so "tap2 was delivered" had a second, innocent
        # explanation (the fetch had already resolved). Read the gate's own input
        # first, typed — a silent device raises NoAnswer -> UNMET at the runner, a
        # device that answers `false` means the premise did not occur, and only with
        # `true` in hand is a delivered tap2 a defect. That converts the assertion.
        armed = dut.get_bool("shellBusy", field="busy", timeout=2.0)
        if not armed:
            _restore_from_stock(dut)
            unmet("T-CDWN-02", "shellBusy was false between the drill tap and tap2 — "
                               "the busy gate this id is about was never armed, so "
                               "whatever tap2 returns says nothing about it")
            return
        # Gate armed → tap2 MUST come back skipped.
        tap2_r = dut.cmd("tap 137 36", timeout=8.0)
        print(f"  [T-CDWN-02] tap2 response: {tap2_r}", flush=True)
        _restore_from_stock(dut)
    # R18: `skipped` is the field this id exists to read. A reply without it is a
    # changed reply shape, which is a defect to report, not a False to assume.
    if not isinstance(tap2_r, dict) or "skipped" not in tap2_r:
        fail("T-CDWN-02", f"the tap2 reply carries no `skipped` field ({tap2_r!r}) — "
                          f"cmdTap's reply shape changed under the corpus that reads it")
        return
    if not tap2_r["skipped"]:
        fail("T-CDWN-02", f"shellBusy was true when tap2 was issued and cmdTap "
                          f"delivered it anyway (reply={tap2_r}) — the g_shellBusy "
                          f"gate did not drop the tap, so `skipped` no longer means "
                          f"what T079, T-BUSY-05 and every other `r.get('skipped')` "
                          f"check in the corpus read it as")
        return
    pass_("T-CDWN-02", "shellBusy=true at tap2; cmdTap returned skipped:true — gate active")


# ── T-CDWN-04 — the refused tap did not also enqueue a fetch ─────────────────

@meta(scope="Stock", scope_reason="drives-stock-only",
      cls="FEATURE", cls_reason=
      "TASK-626, approved 2026-09-06. This is T-CDWN-02's former SECOND assertion, "
      "split off as its own id so it is not gating. Its failure is LOCAL: it says a "
      "tap the shell refused nonetheless reached StockApp and started a duplicate "
      "chart fetch — a StockApp double-fetch, costing the Stock assertions and some "
      "bandwidth, with the shell's gate itself already proven intact by T-CDWN-02 "
      "before this id runs. It may not gate for a second reason: its oracle is Yahoo "
      "Finance answering an ESP32 over TLS inside 60 s, and R36 forbids a class that "
      "can stop the run resting on an external service.")
def t_cdwn_04(dut: Dut):
    """T-CDWN-04: after a drill tap plus a second tap the gate refused, exactly one
    chart fetch resolves — the refused tap did not enqueue a fetch of its own.

    Cold ESP32 TLS to Yahoo Finance can take 30-40 s; we wait up to 60 s for
    resolution. A fetch that never resolves is UNMET, not a pass and not a flake:
    the count this id compares against 1 was never produced.
    """
    print("T-CDWN-04  refused tap enqueued no second fetch")
    if not _switch_to_stock(dut):
        skip("T-CDWN-04", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        _cdwn_stale_chart_list(dut)
        dut.cmd("set fetchErrCount 0", timeout=2.0)
        n = _stock_ok_count(dut)
        r_d = dut.cmd("tap 137 36", timeout=5.0)
        if r_d.get("skipped"):
            _restore_from_stock(dut)
            skip("T-CDWN-04", "drill tap skipped — shell still busy after precondition wait")
            return
        # tap1 processed → send tap2 IMMEDIATELY (no subView check adds no delay).
        tap2_r = dut.cmd("tap 137 36", timeout=8.0)
        if not isinstance(tap2_r, dict) or "skipped" not in tap2_r:
            _restore_from_stock(dut)
            fail("T-CDWN-04", f"the tap2 reply carries no `skipped` field ({tap2_r!r}) "
                              f"— cmdTap's reply shape changed")
            return
        if not tap2_r["skipped"]:
            # No refused tap → nothing to say about what a refused tap enqueued.
            # T-CDWN-02 owns the gate itself and fails there if the gate is broken.
            _restore_from_stock(dut)
            unmet("T-CDWN-04", "tap2 was delivered rather than refused, so this id's "
                               "subject — what a REFUSED tap enqueues — did not occur "
                               "(T-CDWN-02 owns the gate assertion)")
            return
        print("  [T-CDWN-04] gate confirmed (skipped:true); waiting up to 60 s "
              "for the fetch to resolve…", flush=True)
        deadline = time.monotonic() + 60.0
        fetch_ok = n
        fetch_err = 0
        while time.monotonic() < deadline:
            try:
                cur_ok = _stock_ok_count(dut)
                cur_err = dut.get_int("fetchErrCount", timeout=5.0)
                if cur_ok > n or cur_err > 0:
                    fetch_ok  = cur_ok
                    fetch_err = cur_err
                    break
            except TimeoutError:
                pass  # DUT busy with TLS fetch — retry
            time.sleep(1.0)
        _restore_from_stock(dut)
    total = (fetch_ok - n) + fetch_err
    if total == 0:
        unmet("T-CDWN-04", "no fetch resolved within 60 s, so there is no count to "
                           "compare against 1 — the network, not the firmware, is "
                           "what this observed")
        return
    if total >= 2:
        fail("T-CDWN-04", f"{total} fetches resolved after one drill tap and one "
                          f"REFUSED tap — the refused tap reached StockApp and "
                          f"enqueued a fetch despite skipped:true")
        return
    pass_("T-CDWN-04", f"exactly 1 fetch resolved after the refused tap "
                       f"(ok={fetch_ok - n} err={fetch_err})")


# ── T-CDWN-03 — Taskbar tap bypasses g_shellBusy gate ────────────────────────

@meta(cls="FEATURE", cls_reason=
      "TASK-626, approved 2026-09-06. DEMOTED from a SEEDED CORE. Its failure is LOCAL "
      "because the claim it is supposed to hold — a taskbar tap is never dropped by "
      "the busy gate, so the suite can always leave an app — is never actually "
      "exercised: nothing between the row tap and the taskbar tap checks that "
      "`shellBusy` was true when the taskbar tap arrived, and `set triggerFetch 1` "
      "makes that likely, not certain. On a warm or failed fetch the body passes "
      "without the bypass ever being on the path. BP-074: an assertion whose "
      "precondition never occurred is inconclusive, not a pass, and an inconclusive "
      "verdict cannot gate 167 ids. What remains falsifiable — the taskbar tap lands "
      "on Clock — is the same claim T_BI_02 and T147 already assert without a fetch. "
      "Precondition not satisfiable offline (R36); TASK-634 owes the measurement of "
      "how often `shellBusy` is genuinely true here.")
def t_cdwn_03(dut: Dut):
    """T-CDWN-03: tap row (busy) → taskbar Clock tap (x≥275) → appId=Clock, shellBusy=false."""
    print("T-CDWN-03  Taskbar tap passes g_shellBusy gate → app switches")
    if not _switch_to_stock(dut):
        skip("T-CDWN-03", "could not switch to StockApp")
        return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("tap 10 7", timeout=2.0)
        time.sleep(0.3)
        # tap-to-list triggers a quote refresh; wait for it before issuing more commands.
        _wait_shell_not_busy(dut, timeout_s=10.0)
        dut.cmd("set triggerFetch 1", timeout=2.0)
        dut.cmd("tap 137 36", timeout=5.0)
        # Taskbar Clock tap arrives while fetch is in-flight (shellBusy=true).
        tx, ty = _c.tap_taskbar_slot(_CLOCK_APP_ID)
        dut.cmd(f"tap {tx} {ty}", timeout=2.0)
        time.sleep(0.3)
        r_app = dut.cmd("get appId", timeout=3.0)
        app_name = r_app.get("name") if r_app.get("ok") else None
        busy_after = _get_shell_busy(dut)
        dut.cmd(f"switchApp {_SPOTIFY_APP_ID}", timeout=3.0)
        time.sleep(0.3)
    if app_name != "Clock":
        fail("T-CDWN-03", f"appId={app_name!r} after taskbar tap — expected 'Clock'")
        return
    if busy_after is not False:
        fail("T-CDWN-03", f"shellBusy={busy_after} after switchApp to Clock — expected false")
        return
    pass_("T-CDWN-03", "taskbar Clock tap while busy: appId=Clock, shellBusy=false")


# ── main ──────────────────────────────────────────────────────────────────────

# ── velocity-scroll-001 suite (TASK-104) ──────────────────────────────────────
# Firmware constraint: `drag x1 y1 x2 y2 steps` always ends with a release
# sentinel; there is no standalone `release` command.  T157-T159 exploit the
# fact that handleSerialCommands() and drainInjectionQueue() each run ONCE per
# loop() iteration, so commands sent before the drag queue drains are processed
# mid-drag:
#   iter N:   drain pops step N-1 (updates _dragCurrentY)
#   iter N:   handleSerialCommands processes queued command → tick fires here
#   iter N+1: drain pops next step (or Release → drag JSON emitted)
# With steps=1 the queue is: Press@y1, Move@y2, Release.
#   iter 2: Press — cmd_A = get dragState  (dragState = D_PLEDIT_SCROLL)
#   iter 3: Move@y2 (_dragCurrentY=y2) — cmd_B = tick 50 20 (fires at full dy)
#   iter 4: Release → drag JSON
# As-built: SCROLL_DEAD_ZONE_PX=1, SCROLL_SPEED_K_DEFAULT=0.1667,
#           dy=-13 → effective=12 → velocity=12×0.1667=2.0004 rows/s


def _vs_precondition(dut: Dut, tid: str) -> bool:
    """Shared precondition: Spotify active, queue ≥ 10, scrollOffset=0, D_IDLE."""
    if not _restore_spotify(dut):
        skip(tid, "precondition: could not restore Spotify")
        return False
    if not dut.wait_for_queue(min_count=10, timeout=30.0):
        skip(tid, "precondition: queue count < 10 after 30 s — need ≥ 10 items loaded")
        return False
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    for _ in range(5):
        _do_drag(dut, xd, yd, xd2, yd2)
    so = _get_scroll(dut)
    if so != 0:
        skip(tid, f"precondition: scrollOffset={so} could not be reset to 0")
        return False
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        skip(tid, f"precondition: dragState={rg.get('state')!r} not D_IDLE")
        return False
    dut.set_cooldown_zero()
    return True



# ── touch-capture-001 (T149–T154) ────────────────────────────────────────────

def _tc_drag_collect(dut: Dut, cmd: str, markers: list[str],
                     timeout: float = 15.0) -> tuple[list[str], dict | None]:
    """Send a drag command, collect log lines containing any marker string,
    and return (matched_lines, drag_response_or_None)."""
    dut.send(cmd)
    matched: list[str] = []
    drag_resp = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if not line:
            continue
        if markers and any(m in line for m in markers):
            matched.append(line)
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "drag":
                    drag_resp = obj
                    break
            except json.JSONDecodeError:
                pass
    return matched, drag_resp


@meta(scope="Spotify", scope_reason="winamp-view")
def t149(dut: Dut):
    print("T149  POSBAR drag: ACT_SEEK committed at correct position")
    dut.cmd("set songDuration 120000")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T149", f"precondition: dragState={rg.get('state')} not D_IDLE"); return
    dut.set_cooldown_zero()

    pbx0, _pbx1, _pby0, _pby1 = _c.posbar_bounds()
    pby = _c.tap_posbar()[1]
    x_start = pbx0 + 24   # left quarter, well inside hitbox
    x_end   = pbx0 + 184  # right half → posbarFromX ≈ 89032 ms of 120000

    _, drag_resp = _tc_drag_collect(dut, f"drag {x_start} {pby} {x_end} {pby} 10",
                                    ["ACT_SEEK", "seek commit"])
    if drag_resp is None:
        fail("T149", "no drag response within 15 s"); return
    if not drag_resp.get("ok"):
        fail("T149", f"drag ok=false: {drag_resp}"); return

    rp = dut.cmd("get posbarDragMs")
    committed_ms = rp.get("ms", -1)
    if not (50000 <= committed_ms <= 120000):
        fail("T149", f"posbarDragMs={committed_ms} not in [50000, 120000]"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T149", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    pass_("T149", f"posbarDragMs={committed_ms} ms; dragState=D_IDLE")


@meta(scope="Spotify", scope_reason="winamp-view")
def t150(dut: Dut):
    print("T150  POSBAR capture: Move above groove still updates posbarDragMs")
    dut.cmd("set songDuration 120000")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T150", f"precondition: dragState={rg.get('state')} not D_IDLE"); return
    dut.set_cooldown_zero()

    pbx0, _pbx1, pby0, _pby1 = _c.posbar_bounds()
    pby = _c.tap_posbar()[1]
    x_start = pbx0 + 24   # same x profile as T149
    x_end   = pbx0 + 184  # same endpoint → same expected committed_ms
    y_end   = pby0 - 22   # above POSBAR hitbox (pby0=72 → y_end=50)

    _, drag_resp = _tc_drag_collect(dut, f"drag {x_start} {pby} {x_end} {y_end} 10", [])
    if drag_resp is None:
        fail("T150", "no drag response within 15 s"); return
    if not drag_resp.get("ok"):
        fail("T150", f"drag ok=false: {drag_resp}"); return

    rp = dut.cmd("get posbarDragMs")
    committed_ms = rp.get("ms", -1)
    if not (50000 <= committed_ms <= 120000):
        fail("T150", f"posbarDragMs={committed_ms} not in [50000, 120000] "
                     f"(~0 = capture broken; Move samples dropped after y left groove)"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T150", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    pass_("T150", f"posbarDragMs={committed_ms} ms despite y-drift above groove; dragState=D_IDLE")


@meta(scope="Spotify", scope_reason="winamp-view")
def t151(dut: Dut):
    print("T151  VOLUME capture: Move below groove still emits ACT_VOLUME")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T151", f"precondition: dragState={rg.get('state')} not D_IDLE"); return
    dut.set_cooldown_zero()

    vx0, _vx1, _vy0, vy1 = _c.vol_bounds()
    vy = _c.vol_drag_y()
    x_start = vx0 + 3   # well inside VOLUME x-range
    x_end   = vx0 + 60  # moves right but stays inside x-range
    y_end   = vy1 + 11  # drifts below VOLUME hitbox bottom edge

    lines, drag_resp = _tc_drag_collect(
        dut, f"drag {x_start} {vy} {x_end} {y_end} 10",
        ["enqueued ACT_VOLUME", "drag-end commit"])
    if drag_resp is None:
        fail("T151", "no drag response within 15 s"); return
    if not drag_resp.get("ok"):
        fail("T151", f"drag ok=false: {drag_resp}"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T151", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    if not lines:
        fail("T151", "no ACT_VOLUME event seen — volume not updated across y-drift; "
                     "capture likely broken"); return

    pass_("T151", f"dragState=D_IDLE; {len(lines)} ACT_VOLUME event(s) during y-drift below groove")


@meta(scope="Spotify", scope_reason="winamp-view")
def t152(dut: Dut):
    print("T152  PLEDIT scrollbar capture: Move into content area continues scrolling")
    if not _restore_spotify(dut):
        fail("T152", "precondition: could not restore Spotify app"); return
    if not dut.wait_for_queue(min_count=6):
        skip("T152", "queue < 6 items — scrollOffset max=0; need more queued tracks"); return

    # Reset scrollOffset to 0
    xd, yd, xd2, yd2 = _c.pledit_swipe("down")
    for _ in range(10):
        _do_drag(dut, xd, yd, xd2, yd2)
    pre = _get_scroll(dut)
    if pre != 0:
        fail("T152", f"precondition: scrollOffset={pre} could not be reset to 0"); return

    # Scrollbar strip: x ∈ [PLEDIT_CONTENT_X+PLEDIT_CONTENT_W, PLEDIT_W-1] = [256, 274].
    # Start drag in centre of strip (x=265), drift left into content area (x=52).
    # y sweeps top-of-rows→lower to advance scrollOffset via updateScrollDirect().
    pledit_rows_y = int(_c.S["PLEDIT_ROWS_Y"])          # 136
    sb_x      = int(_c.S["PLEDIT_CONTENT_X"]) + int(_c.S["PLEDIT_CONTENT_W"]) + 9  # 265
    content_x = int(_c.S["PLEDIT_CONTENT_X"]) + 40      # 52
    y_start   = pledit_rows_y + 4                        # 140
    y_end     = pledit_rows_y + 44                       # 180

    resp = _do_drag(dut, sb_x, y_start, content_x, y_end, steps=10)
    if resp is None:
        fail("T152", "no drag response within 15 s"); return
    if not resp.get("ok"):
        fail("T152", f"drag ok=false: {resp}"); return

    post = _get_scroll(dut)
    if post is None:
        fail("T152", "could not read scrollOffset after drag"); return
    if post <= 0:
        fail("T152", f"scrollOffset={post} after drag (expected > 0) — "
                     "capture broken; drift into content area lost D_PLEDIT_SCROLL_DIRECT"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T152", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    pass_("T152", f"scrollOffset 0→{post} during scrollbar→content drift; dragState=D_IDLE")


@meta(scope="Spotify", scope_reason="winamp-view")
def t153(dut: Dut):
    print("T153  Capture exclusivity: VOLUME drift into POSBAR row does not start seek")
    dut.cmd("set songDuration 120000")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T153", f"precondition: dragState={rg.get('state')} not D_IDLE"); return

    # Snapshot posbarDragMs before the drag — may be non-zero from earlier tests.
    # The key assertion is that it does NOT change during a VOLUME drag (capture exclusivity).
    rp_pre = dut.cmd("get posbarDragMs")
    baseline_ms = rp_pre.get("ms", -1)

    dut.set_cooldown_zero()

    vx0, _vx1, _vy0, _vy1 = _c.vol_bounds()
    vy  = _c.vol_drag_y()   # y inside VOLUME
    pby = _c.tap_posbar()[1]  # y inside POSBAR — drift target
    x_start = vx0 + 3    # inside VOLUME x-range
    x_end   = vx0 + 60   # still inside VOLUME x-range at release

    lines, drag_resp = _tc_drag_collect(
        dut, f"drag {x_start} {vy} {x_end} {pby} 10",
        ["ACT_SEEK", "seek commit", "D_POSBAR"])
    if drag_resp is None:
        fail("T153", "no drag response within 15 s"); return
    if not drag_resp.get("ok"):
        fail("T153", f"drag ok=false: {drag_resp}"); return

    rs = dut.cmd("get dragState")
    if rs.get("state") != "D_IDLE":
        fail("T153", f"dragState={rs.get('state')} after drag (expected D_IDLE)"); return

    rp_post = dut.cmd("get posbarDragMs")
    post_ms = rp_post.get("ms", -1)
    if post_ms != baseline_ms:
        fail("T153", f"posbarDragMs changed {baseline_ms}→{post_ms} during VOLUME drag "
                     f"(Phase 2 POSBAR hit-test fired — capture exclusivity broken)"); return

    if lines:
        fail("T153", f"ACT_SEEK log line seen during VOLUME drag: {lines[0]!r}"); return

    pass_("T153", f"posbarDragMs unchanged at {post_ms} ms; no seek initiated; dragState=D_IDLE")


@meta(scope="Spotify", scope_reason="winamp-view")
def t154(dut: Dut):
    print("T154  POSBAR tap: Press + Release seeks to pressed x position")
    dut.cmd("set songDuration 60000")
    rg = dut.cmd("get dragState")
    if rg.get("state") != "D_IDLE":
        fail("T154", f"precondition: dragState={rg.get('state')} not D_IDLE"); return
    dut.set_cooldown_zero()

    pbx0, _pbx1, _pby0, _pby1 = _c.posbar_bounds()
    pby  = _c.tap_posbar()[1]
    # tap_x = pbx0+164 → posbarFromX = 164*60000/248 ≈ 39677 ms — in [35000, 45000]
    tap_x = pbx0 + 164

    _poll_shell_busy(dut, False, timeout_ms=2000)
    r = dut.cmd(f"tap {tap_x} {pby}")
    if r.get("skipped"):
        fail("T154", f"tap skipped (cooldown still active?): {r}"); return
    if r.get("hit") != "POSBAR":
        fail("T154", f"hit={r.get('hit')!r} (expected POSBAR) — x={tap_x} y={pby}"); return

    rp = dut.cmd("get posbarDragMs")
    seeked_ms = rp.get("ms", -1)
    if not (35000 <= seeked_ms <= 45000):
        fail("T154", f"posbarDragMs={seeked_ms} not in [35000, 45000] "
                     f"(0 = Press-entry init broken; D_POSBAR_DRAG not entered on tap)"); return

    pass_("T154", f"seeked_ms={seeked_ms} ms (expected ≈39677); tap→seek committed correctly")


# ── velocity-scroll-001 ────────────────────────────────────────────────────────

@meta(scope="Spotify", scope_reason="winamp-view")
def t155(dut: Dut):
    """T155: 0-dy tap in dead zone fires PLEDIT hit (tap path, not scroll-end)."""
    print("T155  Tap within dead zone fires PLEDIT hit (0-dy)")
    if not _vs_precondition(dut, "T155"):
        return
    baseline = _get_scroll(dut)
    # cmdTap does Press + Release at same point → dy = 0 < DEAD_ZONE(1) → tap path.
    r = dut.cmd(f"tap {_PLEDIT_X} {_PLEND_Y}", timeout=5.0)
    if not r.get("ok"):
        fail("T155", f"tap returned ok=false: {r}")
        return
    if r.get("hit") != "PLEDIT":
        fail("T155", f"hit={r.get('hit')!r} — expected PLEDIT; tap missed content zone")
        return
    post = _get_scroll(dut)
    if post != baseline:
        fail("T155", f"scrollOffset changed {baseline}→{post} — scroll-end fired instead of tap")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T155", f"dragState={rg.get('state')!r} — Release cleanup failed")
        return
    pass_("T155",
          f"hit=PLEDIT scrollOffset={post} (unchanged) dragState=D_IDLE — tap path confirmed")


@meta(scope="Spotify", scope_reason="winamp-view")
def t156(dut: Dut):
    """T156: dy=13 px drag outside dead zone → scroll-end (no tap, no PLAY_URI)."""
    print("T156  Release outside dead zone suppresses tap (dy=13 px)")
    if not _vs_precondition(dut, "T156"):
        return
    # y 150→163: dy = +13 > DEAD_ZONE(1) → scroll-end; cooldown set to 150 ms (not 300 ms tap).
    dut.send(f"drag {_PLEDIT_X} {_PLEND_Y} {_PLEDIT_X} {_PLSTART_Y} 1")
    _, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T156", "no drag response within 10 s")
        return
    if not drag_resp.get("ok"):
        fail("T156", f"drag response ok=false: {drag_resp}")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T156", f"dragState={rg.get('state')!r} — Release did not complete")
        return
    # Distinguish scroll-end (cooldown≈150 ms) from tap (cooldown≈300 ms).
    # After ~15 ms of processing, scroll-end cooldown is ~135 ms; tap would be ~285 ms.
    rc = dut.cmd("get cooldown", timeout=3.0)
    cooldown_ms = rc.get("remainingMs", 9999)
    if cooldown_ms > 220:
        fail("T156", f"cooldown={cooldown_ms} ms > 220 — tap branch fired (expected scroll-end ≤220 ms)")
        return
    pass_("T156",
          f"dragState=D_IDLE cooldown={cooldown_ms} ms ≤ 220 — scroll-end confirmed, tap suppressed")


@meta(scope="Spotify", scope_reason="winamp-view")
def t157(dut: Dut):
    """T157: velocity ≈ 2.0 rows/s at dy=-13 px (effective=12 px, K=0.1667).
    Verified indirectly: tick 50×20ms at the final drag position produces
    scrollOffset ∈ [1, 3].  Direct scrollVelocity read is not viable because
    the drag command always releases before the harness regains control; tick is
    interleaved mid-drag via serial-buffer queueing (see module header note)."""
    print("T157  Velocity scaling: tick 50×20ms at dy=-13 → scrollOffset ∈ [1,3]")
    if not _vs_precondition(dut, "T157"):
        return
    # steps=1: Press@163(iter2), Move@150(iter3, _dragCurrentY=150), Release(iter4).
    # cmd_A(iter2): get dragState  — confirms D_PLEDIT_SCROLL while gesture active.
    # cmd_B(iter3): tick 50 20    — fires at _dragCurrentY=150; dy=-13; vel≈2.0;
    #                               50×0.04≈2.0 rows → scrollOffset=2.
    dut.send(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 1")
    dut.send("get dragState")
    dut.send("tick 50 20")
    pre, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T157", "no drag response within 10 s")
        return
    if len(pre) < 2:
        fail("T157", f"expected dragState + tick responses before drag JSON; got {len(pre)}: {pre}")
        return
    r_state, r_tick = pre[0], pre[1]
    if r_state.get("state") != "D_PLEDIT_SCROLL":
        fail("T157", f"dragState={r_state.get('state')!r} — gesture did not enter D_PLEDIT_SCROLL")
        return
    if r_tick.get("cmd") != "tick":
        fail("T157", f"expected tick response, got: {r_tick}")
        return
    so = r_tick.get("scrollOffset", -1)
    if not (1 <= so <= 3):
        fail("T157", f"scrollOffset={so} after tick 50×20ms at dy=-13 — "
                     f"expected [1,3] (velocity≈2.0 rows/s); actual velocity≈{so:.1f} rows/s")
        return
    pass_("T157", f"D_PLEDIT_SCROLL confirmed; scrollOffset={so} ∈ [1,3] → velocity≈2.0 rows/s")


@meta(scope="Spotify", scope_reason="winamp-view")
def t158(dut: Dut):
    """T158: tick 50×20ms (1 s equivalent) at dy=-13 advances scrollOffset ≥ 1."""
    print("T158  Tick integration: 1 s at dy=-13 → scrollOffset ≥ 1")
    if not _vs_precondition(dut, "T158"):
        return
    dut.send(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 1")
    dut.send("get dragState")
    dut.send("tick 50 20")
    pre, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T158", "no drag response within 10 s")
        return
    r_tick = next((r for r in pre if r.get("cmd") == "tick"), None)
    if r_tick is None:
        fail("T158", f"no tick response in pre-drag JSONs: {pre}")
        return
    so = r_tick.get("scrollOffset", -1)
    if so < 1:
        fail("T158", f"scrollOffset={so} after tick 50×20ms at dy=-13 — "
                     f"expected ≥ 1; accumulator integration or tickScroll guard broken")
        return
    pass_("T158", f"scrollOffset={so} ≥ 1 after tick 50×20ms at dy=-13 — integration confirmed")


@meta(scope="Spotify", scope_reason="winamp-view")
def t159(dut: Dut):
    """T159: scrollAccum is non-zero during drag, reset to 0.0000 on Release.
    Uses steps=3 so tick fires mid-drag (at Move@159, dy=-4, vel≈0.50) giving
    accum≈0.10.  scrollAccum is read in the next iteration (Move@155), still
    pre-Release, confirming non-zero.  After drag JSON, accum must be 0."""
    print("T159  Accumulator resets to 0.0000 on Release")
    if not _vs_precondition(dut, "T159"):
        return
    # steps=3 queue: Press@163(i2), Move@159(i3), Move@155(i4), Move@150(i5), Release(i6).
    # cmd_A(i2): get dragState  → D_PLEDIT_SCROLL
    # cmd_B(i3): tick 10 20    → _dragCurrentY=159, dy=-4, vel≈0.50, accum≈0.10
    # cmd_C(i4): get scrollAccum → reads accum≈0.10 (non-zero, < 1 row, no advance)
    dut.send(f"drag {_PLEDIT_X} {_PLSTART_Y} {_PLEDIT_X} {_PLEND_Y} 3")
    dut.send("get dragState")
    dut.send("tick 10 20")
    dut.send("get scrollAccum")
    pre, drag_resp = _vs_drain_until_drag(dut, timeout=10.0)
    if drag_resp is None:
        fail("T159", "no drag response within 10 s")
        return
    if len(pre) < 3:
        fail("T159", f"expected 3 pre-drag JSONs (dragState, tick, scrollAccum); got {len(pre)}: {pre}")
        return
    r_state = pre[0]
    r_accum_pre = next((r for r in pre if r.get("var") == "scrollAccum"), None)
    if r_state.get("state") != "D_PLEDIT_SCROLL":
        fail("T159", f"dragState={r_state.get('state')!r} — gesture not active mid-drag")
        return
    if r_accum_pre is None:
        fail("T159", f"no scrollAccum response in pre-drag JSONs: {pre}")
        return
    accum_pre = r_accum_pre.get("val", 0.0)
    if accum_pre == 0.0:
        fail("T159", f"scrollAccum={accum_pre} mid-drag — expected non-zero; "
                     f"tick may have fired before _dragCurrentY was set (tick response: "
                     f"{next((r for r in pre if r.get('cmd')=='tick'), 'missing')})")
        return
    r_accum_post = dut.cmd("get scrollAccum", timeout=3.0)
    accum_post = r_accum_post.get("val", -1.0)
    if accum_post != 0.0:
        fail("T159", f"scrollAccum={accum_post} after Release — expected 0.0000; "
                     f"Release cleanup (_scrollAccum=0) not firing")
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T159", f"dragState={rg.get('state')!r} after Release — expected D_IDLE")
        return
    pass_("T159",
          f"scrollAccum={accum_pre:.4f} mid-drag (non-zero) → 0.0000 after Release; dragState=D_IDLE")


@meta(scope="Spotify", scope_reason="winamp-view")
def t160(dut: Dut):
    """T160: tickScroll is a no-op when dragState is D_IDLE."""
    print("T160  tickScroll no-op when D_IDLE")
    if not _vs_precondition(dut, "T160"):
        return
    rg = dut.cmd("get dragState", timeout=3.0)
    if rg.get("state") != "D_IDLE":
        fail("T160", f"precondition: dragState={rg.get('state')!r} not D_IDLE")
        return
    baseline = _get_scroll(dut)
    if baseline is None:
        fail("T160", "get scrollOffset failed")
        return
    r_tick = dut.cmd("tick 50 20", timeout=5.0)
    if not r_tick.get("ok"):
        fail("T160", f"tick command failed: {r_tick}")
        return
    post = _get_scroll(dut)
    if post != baseline:
        fail("T160", f"scrollOffset changed {baseline}→{post} during D_IDLE tick — "
                     f"tickScroll guard clause not firing")
        return
    r_vel = dut.cmd("get scrollVelocity", timeout=3.0)
    vel = r_vel.get("val", None)
    if vel != 0.0:
        fail("T160", f"scrollVelocity={vel} after D_IDLE tick — expected 0.0000")
        return
    pass_("T160",
          f"scrollOffset={post} (unchanged) scrollVelocity=0.0000 — tickScroll D_IDLE guard confirmed")


# ── taskbar-scroll-001 suite (TASK-105/TASK-106) ─────────────────────────────
# Tests T162–T166 for the taskbar scroll gesture (tbScrollOffset mechanics).
#
# Serial commands used:
#   get tbScrollOffset, get appId
#   drag <x1> <y1> <x2> <y2> <steps>
#   tap <x> <y>
#   set cooldown 0
#
# Taskbar geometry (shell_layout.h):
#   TASKBAR_X=275, TASKBAR_W=45, TASKBAR_SLOT_H=40
#   x centre = 297;  slot n y-centre = n*40+20
#   N_APPS = 9  (AppId::COUNT)
#
# Drag parameters for reliable 1-slot step:
#   50 px / 10 steps → LP-smoothed ≈ 42.5 px > TASKBAR_SLOT_H(40) → exactly 1 slot
#   (LP α=0.4; TB_SCROLL_DEAD_ZONE_PX=3 exceeded after the first 5 px step)
#
# T167 is retired — duplicate of revised T165.
# T168 is MANUAL — active-indicator rendering cannot be verified via serial.



@meta(scope="taskbar", scope_reason="taskbar-surface",
      cls="CORE", cls_reason=
      "`_switch_to`/`_restore_spotify` reach an app by driving the offset to 0 and "
      "tapping its slot. If a slot tap were taken for a scroll, every app entry in "
      "the suite would land on the wrong app — and SILENTLY, because a consistent "
      "one-slot shift still yields a valid app name for `get appId` to report. This "
      "is the only id that asserts the tap/scroll discrimination itself: appId "
      "changed AND the offset did not.")
def t162(dut: Dut):
    """T162: Tap taskbar slot 1 (|rawDy|=0 < TB_SCROLL_DEAD_ZONE_PX=3) → switchApp fires, tbScrollOffset unchanged."""
    print("T162  Tap taskbar slot 1 — switchApp fires, tbScrollOffset unchanged")
    if not _tb_precondition(dut, "T162"):
        return
    baseline = _tb_get_offset(dut)
    cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])   # Clock slot
    dut.cmd(f"tap {cx} {cy}", timeout=3.0)
    time.sleep(0.2)
    r_app = dut.cmd("get appId", timeout=3.0)
    post = _tb_get_offset(dut)
    _restore_spotify(dut)
    if r_app.get("name") != "Clock":
        fail("T162", f"appId={r_app.get('name')!r} after tap slot 1 — expected Clock; switchApp not fired")
        return
    if post != baseline:
        fail("T162", f"tbScrollOffset changed {baseline}→{post} after tap — scroll triggered instead of tap")
        return
    pass_("T162", f"appId=Clock; tbScrollOffset={post} (unchanged at {baseline}) — tap/switchApp path confirmed")


@meta(scope="taskbar", scope_reason="taskbar-surface",
      cls="CORE", cls_reason=
      "`_tb_set_offset` (`_helpers.py:409`) reaches a target offset by composing "
      "this exact transition — one 50 px up-drag per slot step — and "
      "`_tb_precondition` calls it before all eleven taskbar ids, as does every "
      "`_switch_to`. If an up-drag does not step the offset by one, the helper's "
      "path arithmetic stops arriving — and `_switch_to` (`_helpers.py:325`) "
      "DISCARDS its return, so it taps a slot position that now denotes a different "
      "app and reports whatever it lands on.")
def t163(dut: Dut):
    """T163: Drag-up ≥50 px / 10 steps → tbScrollOffset increments by 1 (mod N)."""
    print("T163  Drag-up 50 px → tbScrollOffset + 1")
    if not _tb_precondition(dut, "T163"):
        return
    baseline = _tb_get_offset(dut)
    dut.cmd(f"drag {_TB_X} 110 {_TB_X} 60 10", timeout=5.0)   # 50 px up
    post = _tb_get_offset(dut)
    expected = (baseline + 1) % _TB_N
    _tb_set_offset(dut, 0)
    if post != expected:
        fail("T163", f"tbScrollOffset={post} after drag-up; expected {expected} (baseline={baseline})")
        return
    pass_("T163", f"tbScrollOffset {baseline}→{post} (+1 mod {_TB_N}) confirmed")


@meta(scope="taskbar", scope_reason="taskbar-surface",
      cls="CORE", cls_reason=
      "The other direction of T163's premise, and it is not redundant: "
      "`_tb_set_offset` chooses the SHORTER path, so roughly half of all offset "
      "targets in the suite are reached by down-drags only. A down-step that does "
      "not decrement leaves those calls short of the target with the same silent "
      "consequence in `_switch_to`.")
def t164(dut: Dut):
    """T164: Drag-down ≥50 px / 10 steps → tbScrollOffset decrements by 1 (mod N).
    Starts at offset=1 to exercise non-wrap decrement (wrap is T165)."""
    print("T164  Drag-down 50 px → tbScrollOffset - 1")
    if not _tb_precondition(dut, "T164"):
        return
    if not _tb_set_offset(dut, 1):
        skip("T164", f"could not set tbScrollOffset=1; actual={_tb_get_offset(dut)}")
        return
    dut.set_cooldown_zero()
    baseline = _tb_get_offset(dut)   # should be 1
    dut.cmd(f"drag {_TB_X} 60 {_TB_X} 110 10", timeout=5.0)   # 50 px down
    post = _tb_get_offset(dut)
    expected = (baseline - 1 + _TB_N) % _TB_N
    _tb_set_offset(dut, 0)
    if post != expected:
        fail("T164", f"tbScrollOffset={post} after drag-down; expected {expected} (baseline={baseline})")
        return
    pass_("T164", f"tbScrollOffset {baseline}→{post} (-1 mod {_TB_N}) confirmed")


@meta(scope="taskbar", scope_reason="taskbar-surface",
      cls="CORE", cls_reason=
      "`_tb_set_offset`'s shortest-path choice routes THROUGH the wrap whenever the "
      "target is nearer that way (`steps_down = (current - target) % n`), so the "
      "down-wrap is on the path for every target in the far half of the ring. A "
      "wrap that lands anywhere but N-1 misaddresses those slots for every caller, "
      "including `_restore_spotify`. WP-C C-19 also corrects the TASK-566 "
      "adjudication here: `_tb_precondition` DRIVES the offset to 0, so this id's "
      "`skip()` is unreachable in registry order and it is not order-sensitive.")
def t165(dut: Dut):
    """T165: Wrap-around down — offset=0, drag-down → offset=N-1=7."""
    print("T165  Wrap-around down: offset=0, drag-down → offset=7")
    if not _tb_precondition(dut, "T165"):
        return
    baseline = _tb_get_offset(dut)
    if baseline != 0:
        skip("T165", f"precondition offset={baseline}, expected 0")
        return
    dut.cmd(f"drag {_TB_X} 60 {_TB_X} 110 10", timeout=5.0)   # 50 px down from 0 → wrap to N-1
    post = _tb_get_offset(dut)
    _tb_set_offset(dut, 0)
    if post != _TB_N - 1:
        fail("T165", f"tbScrollOffset={post} after wrap-down from 0; expected {_TB_N - 1}")
        return
    pass_("T165", f"tbScrollOffset 0→{post} (wrap-around down confirmed)")


@meta(scope="taskbar", scope_reason="taskbar-surface",
      cls="CORE", cls_reason=
      "The fourth and last transition `_tb_set_offset` can emit — the up-wrap, taken "
      "returning to offset 0 from the far half of the ring, which is what "
      "`_tb_precondition` does before eleven ids and `_switch_to` does before "
      "hundreds of app entries. The four transitions are one premise tested in the "
      "four directions the helper actually uses; leaving any one at FEATURE would "
      "leave a quarter of the navigation primitive ungated.")
def t166(dut: Dut):
    """T166: Wrap-around up — offset=N-1=7, drag-up → offset=0."""
    print("T166  Wrap-around up: offset=7, drag-up → offset=0")
    if not _tb_precondition(dut, "T166"):
        return
    if not _tb_set_offset(dut, _TB_N - 1):
        skip("T166", f"could not set tbScrollOffset={_TB_N - 1}; actual={_tb_get_offset(dut)}")
        return
    dut.set_cooldown_zero()
    baseline = _tb_get_offset(dut)   # should be 7
    dut.cmd(f"drag {_TB_X} 110 {_TB_X} 60 10", timeout=5.0)   # 50 px up from N-1 → wrap to 0
    post = _tb_get_offset(dut)
    _tb_set_offset(dut, 0)
    if post != 0:
        fail("T166", f"tbScrollOffset={post} after wrap-up from {_TB_N - 1}; expected 0")
        return
    pass_("T166", f"tbScrollOffset {baseline}→{post} (wrap-around up confirmed)")


@meta(scope="taskbar", scope_reason="taskbar-surface",
      cls="CORE", cls_reason=
      "A taskbar render crash REBOOTS the board, and the suite scrolls the taskbar "
      "in every family that calls `_tb_set_offset`. This is the only id that walks a "
      "full cycle plus the wrap and checks the board is still answering at each "
      "offset; if it fails, every id after it is running on an unplanned fresh boot "
      "with none of the state its predecessors established. The class rests on that "
      "liveness half. The leak half is weak and does not carry it: it samples 2 of "
      "11 offsets and asserts only `!= WebRadio`, so a slot resolving to the wrong "
      "non-WebRadio app passes (WP-C C-15).")
def t242(dut: Dut):
    """T242 (TASK-242/LL-085): WebRadio must NOT be reachable via the taskbar — it
    is eject-entered only. Regression for the latent crash where WebRadio leaked
    into the taskbar (totalApps=AppId::COUNT) and its un-baked icon rendered
    pushImage(nullptr). Scroll a FULL cycle (the user path the old tests bypassed)
    and assert (a) no crash — DUT stays responsive, (b) no taskbar slot ever
    selects WebRadio."""
    print("T242  Taskbar excludes WebRadio (full scroll cycle, no crash)")
    if not _tb_precondition(dut, "T242"):
        return
    # Full scroll cycle: a crash on the WebRadio slot reboots the DUT, so
    # get appId stops responding at the offending offset.
    for off in range(_TB_N + 1):              # +1 exercises the wrap
        target = off % _TB_N
        if not _tb_set_offset(dut, target):
            fail("T242", f"could not reach scrollOffset={target} (DUT crash/reboot?)")
            return
        if not dut.cmd("get appId", timeout=3.0).get("name"):
            fail("T242", f"DUT unresponsive at scrollOffset={target} — taskbar render crash")
            return
    # Tap the top slot at a few offsets; the selected app must never be WebRadio.
    # TASK-413: offset 0 IS the player slot (appIdx == AppId::Spotify) — tapping it
    # while the player is already active now deliberately cycles Spotify -> WebRadio
    # -> Player (ADR-059 D6, resolvePlayerTap), which is a different mechanism from
    # "WebRadio leaked into the ordinary scroll rotation" this test guards against.
    # That cycle behaviour is T_PLR_01's job; skip offset 0 here so this test keeps
    # checking only the genuine leak class — a taskbar slot that ISN'T the player
    # slot must never resolve to WebRadio/LocalPlayer.
    for target in (_TB_N // 2, _TB_N - 1):
        _tb_set_offset(dut, target)
        dut.set_cooldown_zero()
        x, y = _c.tap_taskbar_slot(0)         # top visible slot → appIdx=target
        dut.cmd(f"tap {x} {y}", timeout=5.0)
        if dut.cmd("get appId", timeout=3.0).get("name") == "WebRadio":
            fail("T242", f"taskbar tap at offset {target} selected WebRadio — must be eject-only")
            return
    _restore_spotify(dut)
    pass_("T242", f"full scroll cycle ({_TB_N} offsets) — no crash; WebRadio never a taskbar slot")


# ── T_TBFB_01–04 — M-TASKBAR-FEEDBACK tap feedback (TASK-279) ─────────────────
# Asserts the stable-prefix lines per the design's VE dbg-surface sign-off
# (2026-07-07): [shell] tb-press slot=N / tb-press-cancel / tb-commit slot=N,
# ordered against [shell] entered M. Presence + relative order only — the
# [shell] switch phase numbers are recorded by e0_baseline.py, never
# threshold-asserted here (VE-3-2 single-shot flakiness rule).

def _tbfb_drag_capture(dut: Dut, x1: int, y1: int, x2: int, y2: int,
                       steps: int, timeout: float = 10.0) -> list[str]:
    """Send a drag and capture all raw lines through the drag-JSON terminator."""
    dut.ser.reset_input_buffer()
    dut.send(f"drag {x1} {y1} {x2} {y2} {steps}")
    lines: list[str] = []
    old_timeout = dut.ser.timeout
    dut.ser.timeout = 0.3
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if not line:
            continue
        lines.append(line)
        if line.startswith("{") and '"cmd":"drag"' in line.replace(" ", ""):
            break
    dut.ser.timeout = old_timeout
    return lines


def _tbfb_idx(lines: list[str], needle: str) -> int:
    """Index of first line containing needle, or -1."""
    for i, ln in enumerate(lines):
        if needle in ln:
            return i
    return -1


@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE (seeded only because "
      "its scope is `taskbar`). M-TASKBAR-FEEDBACK/TASK-279 asserts the ORDER of "
      "three log markers behind an amber press paint. The switch LANDING — the part "
      "the rest of the run depends on — is declared CORE on T147 and T162; if the "
      "markers were emitted out of order the switch would still land and every "
      "downstream id would be unaffected.")
def t_tbfb_01(dut: Dut):
    """T_TBFB_01: taskbar drag-tap → tb-press in the Press iteration, tb-commit
    strictly before [shell] entered (VE-3-3), switch lands on the tapped app."""
    print("T_TBFB_01  tb-press + tb-commit ordering on a taskbar tap")
    if not _tb_precondition(dut, "T_TBFB_01"):
        return
    _, y = _c.tap_taskbar_slot(APP_SLOT["Clock"])   # slot 1 centre, y=60
    lines = _tbfb_drag_capture(dut, _TB_X, y, _TB_X, y + 1, 2)
    i_press  = _tbfb_idx(lines, "[shell] tb-press slot=1")
    i_commit = _tbfb_idx(lines, "[shell] tb-commit slot=1")
    i_enter  = _tbfb_idx(lines, "[shell] entered 1 ")   # trailing space: not 10/11
    r_app = dut.cmd("get appId", timeout=3.0)
    _restore_spotify(dut)
    if i_press < 0:
        fail("T_TBFB_01", f"no '[shell] tb-press slot=1' in drain window: {lines[:6]}")
        return
    if i_commit < 0 or i_enter < 0:
        fail("T_TBFB_01", f"missing tb-commit ({i_commit}) or entered ({i_enter}) line")
        return
    if not (i_press < i_commit < i_enter):
        fail("T_TBFB_01", f"order wrong: press@{i_press} commit@{i_commit} entered@{i_enter}")
        return
    if r_app.get("name") != "Clock":
        fail("T_TBFB_01", f"appId={r_app.get('name')!r} after tap — switch did not land")
        return
    pass_("T_TBFB_01", f"press@{i_press} < commit@{i_commit} < entered@{i_enter}; appId=Clock")


@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. Same feature: "
      "`tb-press-cancel` on a scroll, with no commit and no switch. The strongest "
      "body in its family — it asserts the negative as well as the positive — and "
      "still local: the tap/scroll discrimination it overlaps is the premise, and "
      "that is declared CORE on T162.")
def t_tbfb_02(dut: Dut):
    """T_TBFB_02: scroll drag → tb-press then tb-press-cancel at dead-zone exceed
    (VE-3-4); no tb-commit, no switch; offset steps by 1 (discrimination unchanged)."""
    print("T_TBFB_02  tb-press-cancel on scroll-start; no commit")
    if not _tb_precondition(dut, "T_TBFB_02"):
        return
    lines = _tbfb_drag_capture(dut, _TB_X, 110, _TB_X, 60, 10)   # 50 px up = +1 slot
    post = _tb_get_offset(dut)
    i_press  = _tbfb_idx(lines, "[shell] tb-press slot=2")       # 110//40 = 2
    i_cancel = _tbfb_idx(lines, "[shell] tb-press-cancel")
    i_commit = _tbfb_idx(lines, "[shell] tb-commit")
    i_enter  = _tbfb_idx(lines, "[shell] entered")
    _tb_set_offset(dut, 0)
    if i_press < 0:
        fail("T_TBFB_02", f"no '[shell] tb-press slot=2' in drain window: {lines[:6]}")
        return
    if i_cancel < 0 or i_cancel < i_press:
        fail("T_TBFB_02", f"tb-press-cancel missing/misordered: press@{i_press} cancel@{i_cancel}")
        return
    if i_commit >= 0 or i_enter >= 0:
        fail("T_TBFB_02", f"scroll produced commit@{i_commit}/entered@{i_enter} — must not switch")
        return
    if post != 1:
        fail("T_TBFB_02", f"tbScrollOffset={post} after 50 px drag; expected 1 — scroll regressed")
        return
    pass_("T_TBFB_02", f"press@{i_press} → cancel@{i_cancel}; no commit; offset 0→1")


@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. A feature test of "
      "the WebRadio player-mode slot redirect; nothing else resolves a player slot. "
      "The class also cut the wrong way for it: WP-C C-12 shows its `finally` writes "
      "`set playerMode {r_pm.get('val', 0)}`, so a lost entry reply silently "
      "REWRITES persisted SPIFFS state to Spotify — an id that can corrupt persisted "
      "state on a dropped line is the last one that should run first, which is what "
      "CORE would have made it under the class-order switch.")
def t_tbfb_03(dut: Dut):
    """T_TBFB_03: WebRadio-player-mode case (QM-3-1) — player-slot tap with persisted
    mode WebRadio: amber paints the TAPPED slot (tb-commit slot=0), switch resolves
    to WebRadio via resolvePlayerSlot; no reverse app→slot lookup crash (LL-085)."""
    print("T_TBFB_03  commit amber on press-anchored slot; WebRadio player-mode redirect")
    if not _tb_precondition(dut, "T_TBFB_03"):
        return
    r_pm = dut.cmd("get playerMode", timeout=3.0)
    if not _switch_to(dut, "Clock"):
        skip("T_TBFB_03", "could not switch to Clock for the redirect tap")
        return
    dut.cmd("set playerMode 1", timeout=3.0)
    dut.set_cooldown_zero()
    try:
        lines = _tbfb_drag_capture(dut, _TB_X, 20, _TB_X, 21, 2)   # slot 0 = player slot
        i_commit = _tbfb_idx(lines, "[shell] tb-commit slot=0")
        i_enter  = _tbfb_idx(lines, f"[shell] entered {APP_SLOT['WebRadio']}")
        r_app = dut.cmd("get appId", timeout=5.0)
    finally:
        dut.cmd(f"set playerMode {r_pm.get('val', 0)}", timeout=3.0)
        _restore_spotify(dut)
    if i_commit < 0:
        fail("T_TBFB_03", f"no '[shell] tb-commit slot=0' — press-anchored amber missing: {lines[:6]}")
        return
    if i_enter < 0 or i_enter < i_commit:
        fail("T_TBFB_03", f"entered-WebRadio missing/misordered: commit@{i_commit} entered@{i_enter}")
        return
    if r_app.get("name") != "WebRadio":
        fail("T_TBFB_03", f"appId={r_app.get('name')!r} — resolvePlayerSlot redirect did not land")
        return
    pass_("T_TBFB_03", f"commit slot=0 @{i_commit} < entered WebRadio @{i_enter}; redirect OK")


@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. It draws a boundary "
      "between two cooldown variables — a taskbar gesture must not arm SpotifyApp's "
      "canvas cooldown, a canvas gesture still must. Both directions are asserted "
      "and both are local: the suite drives the canvas cooldown to zero before every "
      "tap anyway, so no other id would be misled if it stopped arming.")
def t_tbfb_04(dut: Dut):
    """T_TBFB_04: app-canvas cooldown behaviour unchanged. `get cooldown` reads
    SpotifyApp's touchScreenCoolDownTime (TASK-052 dead-zone-tap force-poll cooldown)
    — a taskbar gesture never touches it; a consumed canvas gesture still arms it.
    Note this is a DIFFERENT variable from the shell-level s_cooldownMs post-gesture
    cooldown TASK-280 fixed (main.cpp drainInjectionQueue's release branch now sets
    it, matching production's appHandleInput) — that one is covered by T_TBFB_05
    via `get shellCooldown` (TASK-294)."""
    print("T_TBFB_04  canvas cooldown unaffected by taskbar gesture; still armed by canvas gesture")
    if not _tb_precondition(dut, "T_TBFB_04"):
        return
    _, y = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    _tbfb_drag_capture(dut, _TB_X, y, _TB_X, y + 1, 2)            # taskbar tap → Clock
    r_cd_tb = dut.cmd("get cooldown", timeout=3.0)
    if not _restore_spotify(dut):
        skip("T_TBFB_04", "could not restore Spotify for the canvas half")
        return
    dut.set_cooldown_zero()
    # VIS window arms +300 ms at Press, data-independent (a PLEDIT tap needs playlist
    # rows, which TASK-243's Spotify 403 leaves empty — first run failed on that).
    # Side effect: visMode cycles once; left as-is per T-CDWN-01 precedent.
    px, py = _c.tap_vis()
    _tbfb_drag_capture(dut, px, py, px, py + 1, 2)
    r_cd_cv = dut.cmd("get cooldown", timeout=3.0)
    rem_tb = int(r_cd_tb.get("remainingMs", -1))
    rem_cv = int(r_cd_cv.get("remainingMs", -1))
    if rem_tb != 0:
        fail("T_TBFB_04", f"canvas cooldown {rem_tb}ms armed by a TASKBAR gesture — must stay 0")
        return
    if rem_cv <= 0:
        fail("T_TBFB_04", f"canvas cooldown not armed by VIS tap (remainingMs={rem_cv})")
        return
    pass_("T_TBFB_04", f"taskbar gesture: remainingMs=0; canvas VIS tap: remainingMs={rem_cv}")


@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE, and it is the "
      "closest call of the five. `Dut.cmd` does issue `get shellCooldown` before "
      "every tap and drag — but this id asserts the cooldown DOES arm on a release, "
      "and the load-bearing direction is the opposite one: if it stopped arming, "
      "`Dut.cmd`'s drain would simply become a no-op and downstream taps would be "
      "unaffected. A failure here invalidates nothing after it.")
def t_tbfb_05(dut: Dut):
    """T_TBFB_05 (TASK-294): shell-level post-gesture cooldown. `get shellCooldown`
    reads main.cpp's s_cooldownMs — the variable TASK-280's drainInjectionQueue fix
    arms on an injected taskbar release, matching production appHandleInput. Asserts
    it reads 0 once decayed and ~300 ms immediately after an injected taskbar
    release. NOT the same variable as T_TBFB_04's `get cooldown` (SpotifyApp's
    TASK-052 touchScreenCoolDownTime)."""
    print("T_TBFB_05  shellCooldown unarmed after decay; armed ~300ms by injected taskbar release")
    if not _tb_precondition(dut, "T_TBFB_05"):
        return
    # The precondition's own drags arm the same 300 ms shell cooldown — let it
    # decay so the "unarmed" half reads a settled 0, not a stale remnant.
    time.sleep(0.5)
    r_before = dut.cmd("get shellCooldown", timeout=3.0)
    _, y = _c.tap_taskbar_slot(APP_SLOT["Clock"])
    # The drag JSON terminator is emitted in the same loop iteration that arms
    # s_cooldownMs (drainInjectionQueue release branch), so the read that follows
    # lands well inside the 300 ms window.
    lines = _tbfb_drag_capture(dut, _TB_X, y, _TB_X, y + 1, 2)   # taskbar tap → Clock
    r_after = dut.cmd("get shellCooldown", timeout=3.0)
    _restore_spotify(dut)
    rem_before = int(r_before.get("remainingMs", -1))
    rem_after = int(r_after.get("remainingMs", -1))
    if rem_before != 0:
        fail("T_TBFB_05", f"shellCooldown={rem_before}ms before the gesture — expected 0 after decay")
        return
    if _tbfb_idx(lines, "[shell] tb-commit slot=1") < 0:
        fail("T_TBFB_05", f"tap did not reach the taskbar release branch (no tb-commit): {lines[:6]}")
        return
    if not (0 < rem_after <= 300):
        fail("T_TBFB_05", f"shellCooldown={rem_after}ms right after injected taskbar release — expected (0, 300]")
        return
    pass_("T_TBFB_05", f"decayed: 0ms; armed by injected release: {rem_after}ms (≤300)")


# ── Settings nav stub — T-SET-01..08 (TASK-142) ─────────────────────────────

_SETTINGS_APP_ID = APP_SLOT["Settings"]
_CRYPTO_APP_ID   = APP_SLOT["Crypto"]


def _switch_to_settings(dut: Dut, timeout: float = 3.0) -> bool:
    r = dut.cmd(f"switchApp {_SETTINGS_APP_ID}", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.2)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("ok", False) and r2.get("name") == "Settings"


def _settings_section(dut: Dut, timeout: float = 3.0):
    r = dut.cmd("get settingsSection", timeout=timeout)
    return r.get("section") if r.get("ok") else None


def _settings_submenu(dut: Dut, timeout: float = 3.0):
    r = dut.cmd("get settingsAppSubmenu", timeout=timeout)
    return r.get("submenu") if r.get("ok") else None


# ---- Settings-list geometry (mirrored from firmware — keep in sync; same
# row_y()/APP_LIST_ROW_H pattern as the prloc_*_smoke.py tools, e929792) ----
_S_CONTENT_Y = 28    # app/src/settings/settingsSection.h S_CONTENT_Y
_S_ROW_H     = 26    # app/src/settings/settingsSection.h S_ROW_H
_S_CONTENT_H = 212   # app/src/settings/settingsSection.h S_CONTENT_H (240 - header 28)
_CONFIGURABLE_APP_COUNT = 10   # app/gen/configurable_apps.h
# appsSection.h _appListRowH(): the Applications list compresses its row
# height once CONFIGURABLE_APP_COUNT * S_ROW_H no longer fits S_CONTENT_H —
# 21px today (TASK-330: was still using the uncompressed 26px formula here).
_APP_LIST_ROW_H = min(_S_ROW_H, _S_CONTENT_H // _CONFIGURABLE_APP_COUNT)


def _settings_tap_row(dut: Dut, row: int, timeout: float = 3.0):
    """Tap the midpoint of a top-level settings CATEGORY row (category list,
    e.g. General/Display/.../Applications — always S_ROW_H=26px). Do NOT use
    this for rows inside the Applications app list — that list compresses to
    a smaller row height once CONFIGURABLE_APP_COUNT apps no longer fit
    S_CONTENT_H at 26px (currently 21px); use _settings_tap_app_row() there.
    """
    y = _S_CONTENT_Y + row * _S_ROW_H + _S_ROW_H // 2
    dut.cmd(f"tap 137 {y}", timeout=timeout)
    time.sleep(0.1)


def _settings_tap_app_row(dut: Dut, row: int, timeout: float = 3.0):
    """Tap the midpoint of row `row` inside the Applications app list
    (settingsSection==5, submenu==-1) — uses the compressed _appListRowH()
    (min(S_ROW_H, S_CONTENT_H // CONFIGURABLE_APP_COUNT) == 21px today), NOT
    the 26px category-row height. See TASK-330.
    """
    y = _S_CONTENT_Y + row * _APP_LIST_ROW_H + _APP_LIST_ROW_H // 2
    dut.cmd(f"tap 137 {y}", timeout=timeout)
    time.sleep(0.1)


def _settings_tap_back(dut: Dut, timeout: float = 3.0):
    dut.cmd("tap 30 14", timeout=timeout)
    time.sleep(0.1)


@meta(scope="Settings", scope_reason="settings-app")
def t_set_01(dut: Dut):
    """T-SET-01: switchApp(Settings) → settingsSection==-1 (category list)."""
    print("T-SET-01  Settings opens at category list (section==-1)")
    if not _switch_to_settings(dut):
        skip("T-SET-01", "could not switch to Settings")
        _restore_spotify(dut)
        return
    sec = _settings_section(dut)
    _restore_spotify(dut)
    if sec != -1:
        fail("T-SET-01", f"settingsSection={sec!r} after switchApp — expected -1 (category list)")
        return
    pass_("T-SET-01", "settingsSection==-1 after switchApp(Settings) — category list confirmed")


@meta(scope="Settings", scope_reason="settings-app")
def t_set_02(dut: Dut):
    """T-SET-02: tap each stub row 0..4 → section==idx; back → section==-1 (× 5)."""
    print("T-SET-02  Section navigation: tap row→section; back→-1 (× 5)")
    if not _switch_to_settings(dut):
        skip("T-SET-02", "could not switch to Settings")
        _restore_spotify(dut)
        return
    for idx in range(5):
        _settings_tap_row(dut, idx)
        sec = _settings_section(dut)
        if sec != idx:
            _restore_spotify(dut)
            fail("T-SET-02", f"row {idx}: settingsSection={sec!r}, expected {idx}")
            return
        _settings_tap_back(dut)
        sec = _settings_section(dut)
        if sec != -1:
            _restore_spotify(dut)
            fail("T-SET-02", f"row {idx}: after back, settingsSection={sec!r}, expected -1")
            return
    _restore_spotify(dut)
    pass_("T-SET-02", "all 5 stub sections: tap→correct index, back→-1")


@meta(scope="Settings", scope_reason="settings-app")
def t_set_03(dut: Dut):
    """T-SET-03: Applications drill (row 5 → row 0) → submenu==0; back×2 unwinds fully."""
    print("T-SET-03  Applications drill: section 5, submenu 0, back×2")
    if not _switch_to_settings(dut):
        skip("T-SET-03", "could not switch to Settings")
        _restore_spotify(dut)
        return
    _settings_tap_row(dut, 5)
    sec = _settings_section(dut)
    sub = _settings_submenu(dut)
    if sec != 5:
        _restore_spotify(dut)
        fail("T-SET-03", f"section={sec!r} after tap row 5, expected 5")
        return
    if sub != -1:
        _restore_spotify(dut)
        fail("T-SET-03", f"submenu={sub!r} at Applications level 1, expected -1")
        return
    _settings_tap_app_row(dut, 0)  # Spotify — kConfigurableApps[0] (app-list row, TASK-330)
    sub = _settings_submenu(dut)
    if sub != 0:
        _restore_spotify(dut)
        fail("T-SET-03", f"submenu={sub!r} after tap Stock, expected 0")
        return
    _settings_tap_back(dut)    # back to app list
    sub = _settings_submenu(dut)
    if sub != -1:
        _restore_spotify(dut)
        fail("T-SET-03", f"submenu={sub!r} after first back, expected -1")
        return
    _settings_tap_back(dut)    # back to category list
    sec = _settings_section(dut)
    _restore_spotify(dut)
    if sec != -1:
        fail("T-SET-03", f"section={sec!r} after second back, expected -1")
        return
    pass_("T-SET-03", "Applications drill: section 5, submenu 0 confirmed; back×2 unwinds to -1/-1")


@meta(scope="Settings", scope_reason="settings-app")
def t_set_06(dut: Dut):
    """T-SET-06: suspend reset — switch away mid-submenu, return → section==-1, submenu==-1."""
    print("T-SET-06  suspend() reset: re-enter Settings → always category list")
    if not _switch_to_settings(dut):
        skip("T-SET-06", "could not switch to Settings")
        _restore_spotify(dut)
        return
    _settings_tap_row(dut, 5)   # Applications
    _settings_tap_app_row(dut, 0)   # Spotify submenu — kConfigurableApps[0] (app-list row, TASK-330)
    sub = _settings_submenu(dut)
    if sub != 0:
        _restore_spotify(dut)
        skip("T-SET-06", f"could not reach submenu 0, got {sub!r}")
        return
    if not _restore_spotify(dut):
        fail("T-SET-06", "switchApp(Spotify) failed mid-test")
        return
    if not _switch_to_settings(dut):
        fail("T-SET-06", "could not re-enter Settings after suspend")
        return
    sec = _settings_section(dut)
    sub = _settings_submenu(dut)
    _restore_spotify(dut)
    if sec != -1 or sub != -1:
        fail("T-SET-06", f"after suspend+resume: section={sec!r} submenu={sub!r}, expected -1/-1")
        return
    pass_("T-SET-06", "suspend() reset confirmed: section==-1 submenu==-1 on re-entry")


@meta(scope="Settings", scope_reason="settings-app")
def t_set_07(dut: Dut):
    """T-SET-07: back from Applications L2 (Crypto, app-list row 2) traverses all three levels correctly."""
    print("T-SET-07  Double-back from Applications L2 (Crypto, row 2) → fully unwound")
    if not _switch_to_settings(dut):
        skip("T-SET-07", "could not switch to Settings")
        _restore_spotify(dut)
        return
    _settings_tap_row(dut, 5)   # Applications
    _settings_tap_app_row(dut, 2)   # Crypto — kConfigurableApps[2] (app-list row, TASK-330 fix; tests assert indices, not app identity)
    sec = _settings_section(dut)
    sub = _settings_submenu(dut)
    if sec != 5 or sub != 2:
        _restore_spotify(dut)
        fail("T-SET-07", f"section={sec!r} submenu={sub!r} after drill to app-list row 2 (Crypto), expected 5/2")
        return
    _settings_tap_back(dut)     # back to app list
    sub = _settings_submenu(dut)
    if sub != -1:
        _restore_spotify(dut)
        fail("T-SET-07", f"submenu={sub!r} after first back, expected -1")
        return
    _settings_tap_back(dut)     # back to category list
    sec = _settings_section(dut)
    _restore_spotify(dut)
    if sec != -1:
        fail("T-SET-07", f"section={sec!r} after second back, expected -1")
        return
    pass_("T-SET-07", "back×2 from app-list row 2 (Crypto) submenu: submenu→-1, section→-1 confirmed")


@meta(scope="Settings", scope_reason="settings-app")
def t_set_08(dut: Dut):
    """T-SET-08: back from category list returns to g_previousAppId (Crypto)."""
    print("T-SET-08  goBack() from category list → g_previousAppId (Crypto)")
    r = dut.cmd(f"switchApp {_CRYPTO_APP_ID}", timeout=3.0)
    if not r.get("ok"):
        skip("T-SET-08", "could not switch to Crypto")
        _restore_spotify(dut)
        return
    time.sleep(0.2)
    r2 = dut.cmd("get appId", timeout=3.0)
    if r2.get("name") != "Crypto":
        skip("T-SET-08", f"appId={r2.get('name')!r} — could not confirm Crypto")
        _restore_spotify(dut)
        return
    if not _switch_to_settings(dut):
        skip("T-SET-08", "could not switch to Settings from Crypto")
        _restore_spotify(dut)
        return
    sec = _settings_section(dut)
    if sec != -1:
        _restore_spotify(dut)
        fail("T-SET-08", f"settingsSection={sec!r} on entry, expected -1")
        return
    _settings_tap_back(dut)    # back from category list → should go to Crypto
    time.sleep(0.2)
    r3 = dut.cmd("get appId", timeout=3.0)
    app_name = r3.get("name")
    if app_name != "Crypto":
        _restore_spotify(dut)
        fail("T-SET-08", f"appId={app_name!r} after back from category list, expected Crypto")
        return
    _restore_spotify(dut)
    pass_("T-SET-08", "goBack() from category list → Crypto confirmed (g_previousAppId tracking works)")


# ── ADR-042 validation tests ──────────────────────────────────────────────────

@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE, per WP-C C-2: the "
      "body is BROKEN in a way that makes the class meaningless. Its subject is JSON "
      "garbling under Core-0 load; its only detector is a `JSONDecodeError`, and "
      "`app/tools/lib/dut.py:1086` swallows that and returns the next well-formed "
      "line, so `errors` can fill only on a total timeout — never on the interleave "
      "it exists to catch. An id that cannot fail on its subject must not hold a "
      "veto over 167 others. Re-promotion is arguable once C-2 is fixed and it has "
      "actually been run; not before.")
def t_uart_01(dut: Dut):
    """T-UART-01: No JSON garbling during concurrent Core 0 HTTPClient activity.
    Switches to Stock (triggers chart fetch on Core 0), then fires 20 rapid
    get heap commands. All must parse cleanly — validates ADR-042 E1 log suppression.
    """
    print("T-UART-01  JSON integrity under Core 0 HTTPClient load (ADR-042 E1)")
    if not _switch_to_stock(dut):
        skip("T-UART-01", "could not switch to StockApp")
        return
    dut.set_cooldown_zero()
    # Tap AAPL row to trigger chart fetch (Core 0 HTTPClient activity)
    dut.cmd("tap 137 36", timeout=2.0)
    # Immediately hammer 20 get heap commands while Core 0 is busy
    errors = []
    for i in range(20):
        try:
            r = dut.cmd("get heap", timeout=3.0)
            if not r.get("ok"):
                errors.append(f"cmd {i}: ok=false {r}")
        except (TimeoutError, ValueError) as e:
            errors.append(f"cmd {i}: {type(e).__name__}: {e}")
        time.sleep(0.05)
    _restore_from_stock(dut)
    if errors:
        fail("T-UART-01", f"{len(errors)}/20 responses garbled: {errors[:3]}")
    else:
        pass_("T-UART-01", "20/20 get heap responses clean during chart fetch — no Core 0 interleave")


@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="CORE", cls_reason=
      "`_bgpoll_suspended()` (`_helpers.py:444`) is the context manager the "
      "injection-based ids use to stop a background Spotify poll overwriting the "
      "state they just wrote — T-ERR-01/02/04/05, T-BUSY-01b/03/05, T-CDWN-02/03 and "
      "T-BGPOLL-03 all run their assertions inside it. If `set bgPoll 0` does not "
      "actually suspend the poll, those injections are clobbered at a cadence "
      "nobody controls, and the resulting failures read as feature defects rather "
      "than as a lost `set`. Recorded: the behavioural half samples `shellBusy` "
      "every 500 ms as a PROXY for a poll firing, so a poll that starts and finishes "
      "between samples is invisible (WP-C, S8) — the `enabled == 0` half is what "
      "the class actually rests on.")
def t_bgpoll_01(dut: Dut):
    """T-BGPOLL-01: set bgPoll 0 suspends self-polls; get bgPoll returns enabled:0."""
    print("T-BGPOLL-01  bgPoll suspend — self-polls halt (ADR-042 E2)")
    # Ensure we start in a clean state
    dut.cmd("set bgPoll 1", timeout=2.0)
    r = dut.cmd("set bgPoll 0", timeout=2.0)
    if not r.get("ok"):
        fail("T-BGPOLL-01", f"set bgPoll 0 failed: {r}")
        return
    r2 = dut.cmd("get bgPoll", timeout=2.0)
    if not r2.get("ok") or r2.get("enabled") != 0:
        dut.cmd("set bgPoll 1", timeout=2.0)
        fail("T-BGPOLL-01", f"get bgPoll expected enabled:0, got {r2}")
        return
    print("  [T-BGPOLL-01] bgPoll suspended; monitoring shellBusy for 5 s…", flush=True)
    # Monitor for 5 s — no self-initiated polls should fire
    busy_fires = 0
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        sb = _get_shell_busy(dut)
        if sb:
            busy_fires += 1
        time.sleep(0.5)
    dut.cmd("set bgPoll 1", timeout=2.0)
    if busy_fires > 0:
        fail("T-BGPOLL-01", f"shellBusy fired {busy_fires} times during bgPoll suspend — self-poll not gated")
    else:
        pass_("T-BGPOLL-01", "shellBusy=false throughout 5 s bgPoll suspend — self-polls halted")


@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. `reconnect` "
      "resetting `bgPoll` to 1 is a recovery invariant of the Spotify poll; nothing "
      "downstream requires it. WP-B B-6 cuts the same way from the other side: with "
      "no `finally`, a failure here leaves `bgPoll 0` for every id that follows, so "
      "the id most able to poison its successors was the one licensed to stop them.")
def t_bgpoll_02(dut: Dut):
    """T-BGPOLL-02: reconnect resets bgPoll to enabled:1 (recovery invariant)."""
    print("T-BGPOLL-02  reconnect resets bgPoll to 1 (ADR-042 E2 invariant)")
    dut.cmd("set bgPoll 0", timeout=2.0)
    r = dut.cmd("get bgPoll", timeout=2.0)
    if r.get("enabled") != 0:
        fail("T-BGPOLL-02", f"pre-condition failed: bgPoll not suspended (got {r})")
        return
    # reconnect should reset s_bgPollEnabled = 1
    dut.cmd("reconnect", timeout=3.0)
    time.sleep(1.0)  # allow TLS reset + reconnect to process
    r2 = dut.cmd("get bgPoll", timeout=2.0)
    if not r2.get("ok") or r2.get("enabled") != 1:
        fail("T-BGPOLL-02", f"reconnect did not reset bgPoll: got {r2}")
    else:
        pass_("T-BGPOLL-02", "reconnect reset bgPoll to enabled:1 — recovery invariant holds")


@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE, per WP-C C-11. The "
      "only thing it asserts is that a flag the test itself wrote is still 0 — which "
      "would hold if the tap were never sent. `_wait_shell_not_busy`'s return is "
      "discarded and the tap's own `hit`/`action` reply is never inspected, so the "
      "\"force-poll completed\" half of the claim has no oracle at all. A vacuous "
      "pass cannot invalidate anything, which is the definition of local.")
def t_bgpoll_03(dut: Dut):
    """T-BGPOLL-03: ACT_FORCE_POLL tap completes fetch while bgPoll suspended; flag stays 0."""
    print("T-BGPOLL-03  ACT_FORCE_POLL bypasses bgPoll suspend (ADR-042 E2)")
    # Ensure Spotify app
    r = dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=3.0)
    if not r.get("ok"):
        skip("T-BGPOLL-03", "could not switch to Spotify app")
        return
    time.sleep(0.3)
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        # Confirm suspended
        r2 = dut.cmd("get bgPoll", timeout=2.0)
        if r2.get("enabled") != 0:
            fail("T-BGPOLL-03", f"bgPoll not suspended: {r2}")
            return
        dut.set_cooldown_zero()
        # Tap DEADZONE gap (posbar bottom ↔ transport top midpoint) — dispatches
        # ACT_FORCE_POLL in WinampDisplay
        _dx, _dy = _c.tap_deadzone_gap()
        dut.cmd(f"tap {_dx} {_dy}", timeout=2.0)
        print("  [T-BGPOLL-03] force-poll tap sent; waiting for shellBusy cycle…", flush=True)
        # Wait for the force-poll fetch to complete
        _wait_shell_not_busy(dut, timeout_s=15.0)
        # bgPoll flag must still be 0 (not self-resumed by force-poll path)
        r3 = dut.cmd("get bgPoll", timeout=2.0)
        if r3.get("enabled") != 0:
            fail("T-BGPOLL-03", f"bgPoll self-resumed during force-poll: {r3}")
            return
    pass_("T-BGPOLL-03", "ACT_FORCE_POLL fetch completed with bgPoll suspended; flag unchanged at 0")


# ── app-error-signal-001 (TASK-245 / ADR-046) ────────────────────────────────
# Red taskbar active-bar on a sustained app error. The bar colour itself is not
# serial-observable (no pixel readback) — that's the manual T-ERR-03 sign-off.
# These automate the state machine behind it via the `get activeError` getter
# and deterministic injection: `set lastHttp 403` + `set backoff 2` synthesises
# spotifyTask::authError() without depending on a real account 403; bgPoll is
# suspended so a real cadence poll can't overwrite the injected status mid-test.

def _get_active_error(dut: Dut):
    """Returns the `get activeError` dict: {active, spotifyAuthError}."""
    return dut.cmd("get activeError", timeout=3.0)

@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. An ADR-046 feature "
      "test of the `activeError` state machine behind one taskbar indicator. WP-C "
      "rates the body SOUND and it is the good version of the injection pattern "
      "(write key `lastHttp`, read key `activeError`) — but no other id's verdict "
      "depends on the error latch, so a regression here costs the six T-ERR cells "
      "and nothing beyond them.")
def t_err_01(dut: Dut):
    """T-ERR-01 (X020): a 403 poll → activeError true; recovered (200) poll → clears to false."""
    print("T-ERR-01  Spotify authError detection + self-clear")
    if not _restore_spotify(dut):
        skip("T-ERR-01", "could not restore Spotify"); return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        # Baseline: healthy poll → no error.
        dut.cmd("set lastHttp 200")
        base = _get_active_error(dut)
        # A 403 poll → authError true (one 403 is enough; not coupled to backoff).
        dut.cmd("set lastHttp 403")
        err = _get_active_error(dut)
        # A recovered (200) poll → self-clears.
        dut.cmd("set lastHttp 200")
        cleared = _get_active_error(dut)
    ok = (base.get("active") is False and base.get("spotifyAuthError") is False
          and err.get("active") is True and err.get("spotifyAuthError") is True
          and cleared.get("active") is False and cleared.get("spotifyAuthError") is False)
    if ok:
        pass_("T-ERR-01", "base=clean, 403→active+auth true, backoff-reset→clear")
    else:
        fail("T-ERR-01", f"base={base} err={err} cleared={cleared}")

@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. A per-app ownership "
      "rule for one indicator: the error is hidden while another app is active and "
      "restored on return. Local by construction — it is a statement about which app "
      "owns a bar. WP-C C-16 also applies: hardcoded `switchApp 1`/`switchApp 0` "
      "with no `ok` check, so a failed switch reads the previous app's state.")
def t_err_02(dut: Dut):
    """T-ERR-02 (X018+X019): error owned by app — hidden while another app is active
    (active-only limitation), restored on return to the errored app."""
    print("T-ERR-02  authError active-only (X018) + survives switch away/back (X019)")
    if not _restore_spotify(dut):
        skip("T-ERR-02", "could not restore Spotify"); return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("set lastHttp 403")            # 403 poll → Spotify error
        before = _get_active_error(dut)        # Spotify active → active true
        dut.cmd("switchApp 1")                 # Clock (offline, hasError()==false)
        time.sleep(0.4)
        away = _get_active_error(dut)          # active false, but spotifyAuthError still true
        dut.cmd("switchApp 0")                 # back to Spotify
        time.sleep(0.4)
        back = _get_active_error(dut)          # active true again (state survived)
        dut.cmd("set lastHttp 200")            # restore
    _restore_spotify(dut)
    ok = (before.get("active") is True
          and away.get("active") is False and away.get("spotifyAuthError") is True
          and back.get("active") is True)
    if ok:
        pass_("T-ERR-02", "Spotify red while active; hidden on Clock (auth still set); red on return")
    else:
        fail("T-ERR-02", f"before={before} away={away} back={back}")

@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE, and the order "
      "hazard is part of the argument. It tests the boot-amber `connecting` latch — "
      "one indicator's state, read by nothing else. WP-B B-7: it writes `lastOkMs`, "
      "`backoff` and `lastHttp` and restores NONE of them, so under the class-order "
      "switch it would have moved from index ~206 to ~39, in front of 170 ids. That "
      "is an argument against running it early, not for it.")
def t_err_04(dut: Dut):
    """T-ERR-04 (boot amber): connecting true before the first poll resolves, false
    after the first success — independent of error state."""
    print("T-ERR-04  connecting (boot amber) latches false on first success")
    if not _restore_spotify(dut):
        skip("T-ERR-04", "could not restore Spotify"); return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        # No error, no successful poll yet → boot/connecting.
        dut.cmd("set lastHttp 200"); dut.cmd("set backoff 0"); dut.cmd("set lastOkMs 0")
        boot = _get_active_error(dut)
        # Simulate the first successful poll → connected.
        dut.cmd("set lastOkMs 1")
        conn = _get_active_error(dut)
    ok = (boot.get("connecting") is True and boot.get("spotifyAuthError") is False
          and conn.get("connecting") is False)
    if ok:
        pass_("T-ERR-04", "connecting true at boot (amber), false after first success (green)")
    else:
        fail("T-ERR-04", f"boot={boot} connected={conn}")

@meta(scope="spotify-chrome", scope_reason="shell-poll",
      cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. A precise "
      "regression guard for one past defect — a touch must not clear a 403, because "
      "`authError` keys on the last HTTP status and not on `s_consecutiveFailures`. "
      "Valuable, and entirely confined to the Spotify error indicator: no other id "
      "reads `spotifyAuthError`.")
def t_err_05(dut: Dut):
    """T-ERR-05 (regression): a touch must not clear the 403 error. authError is keyed on the
    last HTTP status, not s_consecutiveFailures, so resetBackoff() (called on every touch via
    appHandleInput) must NOT knock the red bar back to amber."""
    print("T-ERR-05  authError survives backoff reset (touch decoupling)")
    if not _restore_spotify(dut):
        skip("T-ERR-05", "could not restore Spotify"); return
    _wait_shell_not_busy(dut, timeout_s=10.0)
    with _bgpoll_suspended(dut):
        dut.cmd("set lastHttp 403")
        err = _get_active_error(dut)
        # `set backoff 0` is exactly what a touch does (resetBackoff()).
        dut.cmd("set backoff 0")
        after_reset = _get_active_error(dut)
        dut.cmd("set lastHttp 200")   # restore
    ok = (err.get("spotifyAuthError") is True
          and after_reset.get("spotifyAuthError") is True)
    if ok:
        pass_("T-ERR-05", "403 error held across backoff reset (touch-immune)")
    else:
        fail("T-ERR-05", f"err={err} after_reset={after_reset}")

@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE. It asserts offline "
      "apps never report `connecting`, which is a weak negative — `connecting` "
      "defaults false, so it asserts a default was not overwritten — and a local "
      "one. Hardcoded `conn(1)`/`conn(4)` with no `ok` check on the switch means a "
      "failed switch reads the previous app's state (WP-C C-16).")
def t_err_06(dut: Dut):
    """T-ERR-06: offline apps never report connecting. Network apps (Weather/Crypto/Stock/
    Teletext) wire isConnecting() to their first-fetch; offline apps (Clock/Matrix) keep the
    default false — guards the 'offline apps stay default-false' invariant."""
    print("T-ERR-06  offline apps report connecting=false")
    def conn(app_id):
        dut.cmd(f"switchApp {app_id}"); time.sleep(0.5)
        return dut.cmd("get activeError").get("connecting")
    clock  = conn(1)   # Clock — offline
    matrix = conn(4)   # Matrix — offline
    _restore_spotify(dut)
    ok = (clock is False and matrix is False)
    if ok:
        pass_("T-ERR-06", "Clock + Matrix connecting=false (offline default held)")
    else:
        fail("T-ERR-06", f"clock={clock} matrix={matrix} (expected both False)")

@meta(cls="FEATURE", cls_reason=
      "TASK-591, approved 2026-09-04. DEMOTED from a SEEDED CORE, WP-B B-1's seventh "
      "Stock id. It drives StockApp's `hasError() = _s.fetchFailed` latch through "
      "`set fetchFailed`; nothing else in the corpus reads the Stock error latch, so "
      "the failure is confined to one app's indicator. It was seeded CORE only "
      "because its module is `shell.py` and its scope fell to the catch-all. OWED "
      "(B-1's other half, deliberately not done here because it changes `--scope` "
      "selection, not gating): its scope should be `Stock`.")
def t_err_07(dut: Dut):
    """T-ERR-07 (TASK-246): a network app's failed fetch → red. Stock hasError() = _s.fetchFailed,
    driven via the existing `set fetchFailed` injector; clears on success. Representative of the
    Weather/Crypto/Teletext error latches (same set-on-fail / clear-on-success pattern)."""
    print("T-ERR-07  network-app hasError → red (Stock fetchFailed)")
    dut.cmd(f"switchApp {APP_SLOT['Stock']}"); time.sleep(0.5)   # Stock
    dut.cmd("set fetchFailed 1"); time.sleep(0.2)
    err = dut.cmd("get activeError")
    dut.cmd("set fetchFailed 0"); time.sleep(0.2)
    cleared = dut.cmd("get activeError")
    _restore_spotify(dut)
    ok = (err.get("active") is True and cleared.get("active") is False)
    if ok:
        pass_("T-ERR-07", "Stock active(red)=true on fetchFailed, false on clear")
    else:
        fail("T-ERR-07", f"err={err} cleared={cleared}")



TESTS = {
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
    "T_MA_03": t_ma_03,
    # gol-001
    "T_GOL_01": t_gol_01,
    "T_GOL_03": t_gol_03,
    "T_GOL_04": t_gol_04,
    # weather-001
    "T_WX_01": t_wx_01,
    "T_WX_03": t_wx_03,
    "T_WX_04": t_wx_04,
    "T_WX_05": t_wx_05,
    "T_WX_07": t_wx_07,
    # crypto-001
    "T_CX_01": t_cx_01,
    "T_CX_03": t_cx_03,
    "T_CX_04": t_cx_04,
    "T_CX_05": t_cx_05,
    "T_CX_07": t_cx_07,
    # cross-feature X007
    "T_X07_01": t_x07_01,
    # M-TOUCH-UX (TASK-118)
    "T-BUSY-01":  t_busy_01,
    "T-BUSY-01b": t_busy_01b,
    "T-BUSY-02":  t_busy_02,
    "T-BUSY-03":  t_busy_03,
    "T-BUSY-05":  t_busy_05,
    "T-CDWN-01":  t_cdwn_01,
    "T-CDWN-02":  t_cdwn_02,
    "T-CDWN-03":  t_cdwn_03,
    "T-CDWN-04":  t_cdwn_04,
    # velocity-scroll-001 (TASK-104)
    "T155": t155,
    "T156": t156,
    "T157": t157,
    "T158": t158,
    "T159": t159,
    "T160": t160,
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
    # app-error-signal-001 — red taskbar active-bar (TASK-245 / ADR-046)
    "T-ERR-01": t_err_01,
    "T-ERR-02": t_err_02,
    "T-ERR-04": t_err_04,
    "T-ERR-05": t_err_05,
    "T-ERR-06": t_err_06,
    "T-ERR-07": t_err_07,
}


# TASK-570. Three registry entries are NOT functions — T093/T094/T095 map to
# None here and are dispatched by name in runner.py because they take a second
# `interactive` argument. A decorator cannot attach to None, so their record is
# declared here instead. (M-TESTARCH §13.3 asserted "nothing in TESTS is a
# non-function value today"; these three are the counter-example.)
#
# scope=rig: they calibrate the touchscreen against a human finger. They are a
# property of the rig, not of any app — and under §13.3's rule they would still
# exist were every app deleted.
#: TASK-591 / R35. These three take their declaration here rather than through a
#: decorator because their registry entries are `(dut, interactive)` bodies the
#: runner dispatches specially; the reason still lives WITH the declaration, which
#: is the rule the gate enforces.
#:
#: All three carry WP-C **C-3** on their face: no `run/` script passes
#: `--interactive`, so the RIG class has ZERO executable coverage from any shipped
#: entry point and each body takes its `skip()` branch. The class is nonetheless
#: correct for what these ids assert — a rig premise, not a firmware one — and the
#: reasons below are written for what they establish WHEN they are run. C-3's fix
#: is an entry point (`run/calibrate`), not a demotion: demoting them would say the
#: injection calibration is a feature of the firmware, which it is not.
META_OVERRIDES = {
    "T093": {
        "cls": "RIG", "scope": "rig", "scope_reason": "calibration",
        "cls_reason":
            "The greyed titlebar is the operator's only out-of-band signal that the "
            "board is in backoff. If it does not appear, a human watching the rig "
            "cannot tell a wedged board from a working one, and the ~40 ids that "
            "tolerate a degraded Spotify session will be read as passing on a board "
            "nobody could see was unhealthy. WP-C rates the body HOLLOW (both "
            "oracles are `input()` prompts) — that is a body defect to fix, not a "
            "reason to move the claim out of RIG.",
    },
    "T094": {
        "cls": "RIG", "scope": "rig", "scope_reason": "calibration",
        "cls_reason":
            "A physical tap on the logo must produce the same TLS reset an injected "
            "tap does. If physical and injected input diverge here, the rig is not "
            "the machine the suite thinks it is driving, and no injected-tap verdict "
            "in the corpus generalises to the product.",
    },
    "T095": {
        "cls": "RIG", "scope": "rig", "scope_reason": "calibration",
        "cls_reason":
            "This is the injection-vs-physical calibration that LICENSES every "
            "injected `tap` in the other 210 ids: three zones, serial and finger, "
            "same region and same action. If it fails, every tap-driven verdict in "
            "the suite is a statement about `cmdTap`'s hit-test and about nothing a "
            "user can do. Nothing else in the corpus establishes this, and per C-3 "
            "it has never been runnable from a shipped script.",
    },
}
