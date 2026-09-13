"""Helpers shared by 2+ serialdbg families (TASK-480).

Not a dumping ground (M-TOOLING §3): a helper used by exactly one family
lives in that family's own module instead. Populated as families are
extracted and their transitive shared dependencies surface -- started with
the teletext family, which needs the universal app-switch / taskbar-scroll
/ diagnostics primitives almost every other family also uses.
"""

import json
import time
from contextlib import contextmanager

from lib.dut import Dut, BadField, DeviceReadError, NoAnswer
from lib.results import skip, pass_
import coords as _c
from app_ids_gen import APP_SLOT


def dut_int(reply: dict, field: str) -> int:
    """An int field of an ALREADY-READ reply, raising instead of defaulting.

    TASK-596. `Dut.get_*` covers read-and-extract; this covers the case where one
    reply carries several fields the caller compares together (`get dataq`), so
    re-reading per field would sample four different instants of a moving queue.
    """
    if field not in reply:
        raise BadField(field, f"reply has no {field!r} field: {reply!r}")
    v = reply[field]
    if isinstance(v, bool) or not isinstance(v, int):
        raise BadField(field, f"{field}={v!r} is not an integer: {reply!r}")
    return v


def _appid_is(dut: Dut, app_name: str, timeout: float = 5.0) -> bool:
    """True iff `get appId` says the shell is in `app_name`.

    TASK-596: the four hand-rolled copies of this read used
    `r.get("ok", False) and r.get("name") == app_name`, where the `False` default
    made an unanswered read indistinguishable from "the switch did not happen" —
    and every caller turns that into a skip(). It still returns False on a failed
    read (the callers' contract is a bool), but the read itself is typed and the
    conflation now lives in exactly one place instead of four.
    """
    try:
        return dut.get_str("appId", field="name", timeout=timeout) == app_name
    except DeviceReadError:
        return False


def _tap_and_wait_log(dut: Dut, x: int, y: int, marker: str,
                       tap_timeout: float = 5.0, log_timeout: float = 8.0
                       ) -> tuple[dict | None, bool]:
    """Send a tap and scan for `marker` in ONE continuous serial read.

    TASK-417 gate investigation (2026-08-11): the split pattern used
    elsewhere — dut.cmd(f"tap {x} {y}") followed by a separate
    _wait_for_log() — has a real race. dut.cmd()'s read_json() silently
    discards every non-JSON line while hunting for the tap's own JSON
    reply. spotifyTask's async trace lines ("dequeued action=SHUFFLE",
    "hard reset — stopping client") are printed from a DIFFERENT FreeRTOS
    task and can land in that exact window — read_json() eats them before
    the caller's own _wait_for_log() ever starts reading, and the check
    then times out even though the firmware did exactly the right thing.
    Confirmed on the DUT: a raw serial capture (LOG_FILE) showed
    "dequeued action=SHUFFLE" and "dequeued action=REPEAT" both present,
    in order, within the same second — while T_PLR_17's old split-read
    reported FAIL for both ("dispatch did not reach spotifyTask"). The
    firmware was never at fault; the harness was reading around the line
    it needed. This helper keeps the tap-ack JSON parse and the log-marker
    scan in one unbroken readline() loop so nothing sent to the wire
    between them can be silently lost. Returns
    (json_response_or_None, marker_found)."""
    dut.wait_shell_cooldown_clear()
    dut.send(f"tap {x} {y}")
    resp: dict | None = None
    marker_found = False
    deadline = time.monotonic() + max(tap_timeout, log_timeout)
    while time.monotonic() < deadline and not (resp is not None and marker_found):
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            break
        if not line:
            continue
        if resp is None and line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "tap":
                    resp = obj
                    continue
            except json.JSONDecodeError:
                pass
        if marker in line:
            marker_found = True
    return resp, marker_found


def _drain_data_pipeline(dut: Dut, timeout_s: float = 200.0, tag: str = "") -> bool:
    """Wait until the dataTask/spotifyTask fetch pipeline is quiet: nothing in
    flight or queued, no unacked tlsYield, and spotifyTask not inside an API
    call (spAct=3 — doPoll incl. token refresh has no yield check). TASK-299/300:
    a fetch enqueued behind a busy pipeline serializes for up to minutes —
    firmware working as designed (TASK-244 accepted poll-bounded yield latency)
    — so tests that measure fetch completion rather than latency under
    contention must drain first. Returns True once quiet, False on timeout."""
    prefix = f"[{tag}] " if tag else ""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            # TASK-596: the three defaults here (`queueWaiting, 1` / `inFlight, 0`
            # / `yieldCount, 1`) were all in the SAFE direction — a missing field
            # kept draining rather than declaring quiet, which WP-G explicitly
            # credited. They are still removed: safe-by-choice is one edit away
            # from unsafe-by-choice, and `cmdGet.cpp`'s dataq reply prints all
            # four fields unconditionally, so an absent one is a shape change
            # this loop should surface rather than absorb for 200 s.
            q = dut.read_reply("get dataq", timeout=3.0)
            if (dut_int(q, "queueWaiting") == 0 and dut_int(q, "inFlight") == -1
                    and dut_int(q, "yieldCount") == 0 and q.get("spAct") != 3):
                return True
            print(f"  {prefix}draining: inFlight={q.get('inFlight')} "
                  f"queueWaiting={q.get('queueWaiting')} yieldCount={q.get('yieldCount')} "
                  f"spAct={q.get('spAct')}", flush=True)
        except (TimeoutError, NoAnswer):
            pass
        time.sleep(2.0)
    return False


def _poll_shell_busy(dut: Dut, expected: bool, timeout_ms: int = 500,
                     cmd_timeout: float = 5.0) -> bool:
    """Poll get shellBusy until busy==expected. Returns True if reached within timeout.
    cmd_timeout: per-command serial timeout; raised to 5 s by default to tolerate
    transient serial flooding from concurrent dataTask output (chart/quote fetches)."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            r = dut.cmd("get shellBusy", timeout=cmd_timeout)
            if r.get("ok") and r.get("busy") == expected:
                return True
        except TimeoutError:
            pass  # transient serial flood from dataTask; retry
        time.sleep(0.02)
    return False


def _get_vis_mode(dut: Dut) -> int | None:
    """Return current visMode integer (0–3), or None on error."""
    r = dut.cmd("get visMode", timeout=2.0)
    if r.get("ok"):
        try:
            return int(r["mode"])
        except (KeyError, ValueError, TypeError):
            pass
    return None


def _do_drag(dut: Dut, x1: int, y1: int, x2: int, y2: int,
             steps: int = 30, timeout: float = 15.0) -> dict | None:
    """Send a drag and return the drag JSON response, or None on timeout."""
    dut.send(f"drag {x1} {y1} {x2} {y2} {steps}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = dut.ser.readline().decode(errors="replace").strip()
        except Exception:
            return None
        if line.startswith("{"):
            try:
                obj = json.loads(line)
                if obj.get("cmd") == "drag":
                    return obj
            except json.JSONDecodeError:
                pass
    return None


def _get_scroll(dut: Dut, timeout: float = 3.0) -> int | None:
    """Return scrollOffset int, or None on error."""
    r = dut.cmd("get scrollOffset", timeout=timeout)
    if not r.get("ok") or r.get("key") != "scrollOffset":
        return None
    return r.get("val")


# PLEDIT (playlist-editor) drag geometry — shared by the velocity-scroll-001
# suite (Spotify queue, shell.py) and its WebRadio variant (webradio.py).
_PLEDIT_X  = 140   # x inside PLEDIT content area  (x ∈ [12..255])
_PLSTART_Y = 163   # drag start y (below anchor)
_PLEND_Y   = 150   # drag end y   (above anchor);  dy = 150-163 = -13 (finger up)


def _vs_drain_until_drag(dut: Dut, timeout: float = 10.0) -> tuple[list[dict], dict | None]:
    """Read JSON lines until the drag-completion response arrives.
    Returns (other_responses_in_order, drag_resp_or_None)."""
    pre: list[dict] = []
    drag_resp = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = dut.ser.readline().decode(errors="replace").strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("cmd") == "drag":
            drag_resp = obj
            break
        pre.append(obj)
    return pre, drag_resp


#: TASK-584 / D-2. The single explanation of why a False from `_check_residue`
#: is the regression and not an idle account, quoted into all six callers'
#: fail() strings so the failure carries its own disproof.
#:
#: The six call sites used to excuse this as "Spotify not rendering (not
#: playing?)". That excuse is false, and the firmware says so on two lines:
#:
#:   * `SpotifyApp::resume()` calls `winampDisplay.invalidatePlaylist()`
#:     UNCONDITIONALLY (`app/src/apps/spotifyApp.cpp:27`) — no queue, playback
#:     or Premium predicate guards it.
#:   * `PleditView::invalidate()` sets `_scrollDirty = true` and zeroes
#:     `_lastDrawMs` (`app/src/winamp/pleditView.h:175-179`), so the very next
#:     `draw()` clears both early-return gates (`:139-143`) and stamps
#:     `_lastDrawMs = now` BEFORE it reads `src.count()` (`:156`). An empty
#:     queue draws the frame and stamps the clock exactly like a full one.
#:   * `SpotifyApp::tick()` calls `drawPlaylist()` unconditionally
#:     (`app/src/apps/spotifyApp.cpp:67`).
#:
#: So on any boot where the shell is on Spotify and ticking, `lastPlaylistDraw`
#: advances within one tick of resume(). If it does not advance ACROSS the
#: switch-back, either resume() did not run or the Spotify tick is not running —
#: which is the TFT state residue these ids exist to catch.
#:
#: TASK-685 ADDS THE CLAUSE THIS ANALYSIS WAS MISSING, and it is the one that
#: matters to a caller: the advance is ONE-SHOT. After that first stamp,
#: `seqno` is latched and `_scrollDirty` is cleared, so `draw()` takes the
#: early return at `:139` on every subsequent tick and the clock stands still
#: until something new arrives — which, on an idle or 403 account, is never.
#: Measured on the device: 3861 -> 127744 within 180 ms of `switchApp`, then a
#: single distinct value for the following 6 s.
#:
#: Everything above is true and was never the defect. The defect was WHERE the
#: baseline was read: all six callers read it AFTER the switch-back, by which
#: time the one stamp had landed, and then watched a correctly idle clock for
#: 3 s and called it residue. Six ids reported FAIL across four runs and the
#: firmware was right every time. Read the baseline BEFORE the switch-back.
_RESIDUE_DISPROOF = (
    "SpotifyApp::resume() calls invalidatePlaylist() unconditionally "
    "(spotifyApp.cpp:27) and PleditView::draw() stamps _lastDrawMs before it "
    "reads the queue count (pleditView.h:139-156), so an idle/empty/403 "
    "Spotify still advances this clock ONCE on resume — the baseline for this "
    "assertion is read BEFORE the switch-back (TASK-685), so a clock that did "
    "not move across it is the residue regression, not an idle account"
)


def _check_residue(dut: Dut, tid: str, t_before: int = None) -> bool:
    """Verify lastPlaylistDraw advances ACROSS a switch back to Spotify.

    PASS `t_before`, read BEFORE the switch-back. TASK-685 measured why on the
    device: `lastPlaylistDraw` is a LAST-REPAINT stamp, not a heartbeat. On
    resume, `SpotifyApp::resume()` invalidates the pledit, the next
    `SpotifyApp::tick()` repaints, and the clock jumps ONCE — measured 3861 ->
    127744 within 180 ms of `switchApp`. It then stands still for as long as you
    care to watch (6 s, one distinct value), because `PleditView::draw()`
    early-returns when neither `seqno` nor `_scrollDirty` moved, and an idle or
    403 account never moves `seqno` again.

    Read after the switch-back — as every caller did until TASK-685 — the
    baseline is taken once that single stamp has already landed, and the 3 s
    window then observes a correctly idle clock and calls it a regression. Six
    ids reported that as FAIL across four runs. The firmware was right each
    time.

    Returns True if PASS was recorded. Returns False ONLY for the regression:
    the device answered, and the clock did not move.

    Raises `NoAnswer` if the device never answered inside the window — that is
    an unestablished premise (UNMET at the runner), never a fabricated
    regression. BP-074: an assertion whose precondition did not occur is
    inconclusive, not a result.

    Does not call fail() — the caller owns the id's verdict. TASK-584 requires
    every caller to spend that False on a `fail()`; see `_RESIDUE_DISPROOF`.
    """
    # TASK-596: `r.get("ms", t_before)` defaulted to the BASELINE, so a failed
    # read read as "no advance" — the safe direction here, but it also meant this
    # helper could not distinguish "Spotify did not repaint" from "the device did
    # not answer". TASK-584 closes that: the two outcomes are now a bool and an
    # exception, and they cannot be confused by a caller.
    if t_before is None:
        t_before = dut.get_int("lastPlaylistDraw", field="ms", timeout=3.0)
    answered = False
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            t_now = dut.get_int("lastPlaylistDraw", field="ms", timeout=1.0)
            answered = True
            if t_now != t_before:
                pass_(tid, f"lastPlaylistDraw advanced from {t_before} — no TFT state residue")
                return True
        except NoAnswer:
            pass
        time.sleep(0.05)
    if not answered:
        # Every poll in the 3 s window went unanswered. The baseline read
        # succeeded, so this is the line going quiet, not the clock standing
        # still: we have no reading of the subject at all.
        raise NoAnswer("lastPlaylistDraw",
                       "no reply to `get lastPlaylistDraw` for the whole 3 s "
                       "residue window (the baseline read answered), so the "
                       "clock was never observed — premise unestablished")
    return False


def _switch_to_stock(dut: Dut, timeout: float = 5.0) -> bool:
    """Switch to StockApp via the serial switchApp command.
    TASK-247: force List launch view first (in-RAM only, not persisted) so the
    list-centric suite is deterministic regardless of the device's saved stockMode
    (e.g. a user-configured Heatmap default), and so the heatmap/chart launch no
    longer pre-fetches the unused list quote."""
    dut.cmd("set stockMode 0", timeout=timeout)
    r = dut.cmd(f"switchApp {APP_SLOT['Stock']}", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.3)
    return _appid_is(dut, "Stock", timeout)


def _restore_from_stock(dut: Dut, timeout: float = 5.0) -> bool:
    """Switch back to Spotify from Stock."""
    r = dut.cmd(f"switchApp {APP_SLOT['Spotify']}", timeout=timeout)
    if not r.get("ok"):
        return False
    time.sleep(0.3)
    return _appid_is(dut, "Spotify", timeout)


def _stock_get(dut: Dut, var: str, timeout: float = 3.0):
    """Get a stock debug var; return the response dict.

    TASK-585/596: routed through `Dut.read_reply`, which CORRELATES the reply
    against the `var` it echoes. `dut.cmd` returned the first `{`-line on the
    wire, and every stock body is issued into `stockTickQuotes`' documented
    8-ticker fetch flood, so "the first JSON line" was routinely the answer to
    somebody else's question. That is WP-C's raced-reply hazard, and this is the
    one choke point all 30 stock ids already go through. A read that nothing
    answered now raises NoAnswer instead of returning `{}`-shaped nothing.
    """
    return dut.read_reply(f"get {var}", timeout=timeout)


def _stock_ok_count(dut: Dut) -> int:
    """Current fetchOkCount. Raises rather than returning a sentinel (TASK-585).

    IT USED TO RETURN `-1` ON A BAD READ, and `-1` is a number `_wait_chart_complete`
    can compare against: `current > before` with `before = -1` is satisfied by the
    very first poll, no fetch required. That made the family's central fetch
    oracle an unconditional pass across nine ids (WP-G `G-2`). A count that could
    not be read is not a count, so it is not representable as one any more.
    """
    return dut.get_int("fetchOkCount")


def _reject_sentinel_baseline(value) -> None:
    """Refuse a counter baseline that is not a reading (TASK-585).

    Deliberately a named function taking `value`, not an inline `if before < 0`
    in `_wait_chart_complete`. `_order.py`'s 0->1-edge scanner keys on the shape
    "a name like `before*` captured, then compared" — an inline guard makes all
    eight `_wait_chart_complete` callers read as delta-edge candidates needing
    adjudication, which they are not: this is argument validation, not an
    assertion about the device. Same rationale as the docstring stripping the
    scanner already does.
    """
    if value < 0:
        raise ValueError(
            f"a negative counter baseline ({value!r}) is not a reading — the "
            f"firmware counters are unsigned. This is `G-2`'s shape: a sentinel "
            f"standing in for a failed read, which `_wait_chart_complete` would "
            f"satisfy on its first poll. Snapshot with `_stock_ok_count()`, "
            f"which raises instead of returning one.")


_CHART_PHASE_NAMES = {0: "TLS/connect", 1: "GET/response", 2: "JSON-parse"}


# ── M-DATATASK-PROGRESS atoms: the observer the milestone never had ───────────
#
# TASK-657 (oracle sweep A-6). M-DATATASK-PROGRESS exists to add four volatile
# progress atoms; it closed citing T170/T_WX_05/T_CX_05, none of which asserts
# one. T170 reads `stockQuoteProgress` every poll and only ever USES it on the
# failure branches to enrich a message — so a T170 PASS is precisely the outcome
# in which the atom's value was never checked. This helper is the missing
# oracle, and it is deliberately cheap: no new firmware, no new `get` key.
#
# WHAT IT ASSERTS, and why that and not more. An atom's whole contract is:
# it sits at the sentinel -1 when idle, takes a value inside a documented
# domain while a fetch is in flight, and returns to -1. That is three
# observations, all available over the existing console. It does NOT assert
# that a particular phase is reached — phase 2 (parse) is sub-second on a small
# body and a Core-1 poller can legitimately miss it, so requiring it would ship
# a flake. "Left the sentinel at least once, never outside the domain, came
# back" is the strongest claim that is also stable.
#
# SAMPLING. Polls as fast as the console answers, with no sleep: the TLS and
# GET phases are seconds long, so a tight loop cannot plausibly miss BOTH. The
# poll count is returned so a zero-observation result can be told apart from a
# result that never got to look.

#: atom -> (lo, hi) inclusive, from `app/src/dataTask.h:339-344` and the
#: `httpFetchJsonBuffered` phase writes (`dataTaskStorage.cpp:313-336`).
#: -1 is the sentinel in every case and is NOT part of the domain.
_PROGRESS_ATOM_DOMAIN = {
    # stockQuoteProgress is a BUSY FLAG, not a ticker index: {0, -1}, so the
    # bound here is (0, 0). It read (0, 7) until 2026-09-06 (TASK-659/660),
    # copied from a `dataTask.h` comment that TASK-249 had already made false
    # when it collapsed the eight per-ticker GETs into one multi-symbol spark
    # request. A [0,7] bound cannot fail on any build — {0} is inside it — so
    # it asserted nothing; (0, 0) is the bound that would catch a firmware
    # change reintroducing per-symbol indices. Do not widen it back.
    "stockQuoteProgress": (0, 0),
    "weatherFetchPhase":  (0, 2),
    "cryptoFetchPhase":   (0, 2),
    "stockChartProgress": (0, 2),
}


def _observe_progress_atom(dut: Dut, var: str, done, *, timeout_s: float,
                           test_id: str = "") -> dict:
    """Poll a dataTask progress atom across one fetch. Never a verdict itself.

    `done()` is the caller's completion oracle (a counter advancing, a `*Ready`
    flag) — the atom is what is under test, so it must never also be the thing
    that says the fetch finished.

    Returns a dict: `polls`, `seen` (sorted distinct values, sentinel included),
    `nonsentinel` (sorted distinct values != -1), `bad` (values outside the
    documented domain and not the sentinel), `completed`, `returned_idle`.
    """
    lo, hi = _PROGRESS_ATOM_DOMAIN[var]
    prefix = f"[{test_id}] " if test_id else ""
    seen: set = set()
    polls = 0
    completed = False
    # ENTRY GUARD (TASK-657; added in the M-TESTQUAL phase-2 hardware session,
    # 2026-09-07, after T_WX_07/T_CX_07 both returned a FAIL that named a
    # firmware gap that is not there). The docstring above states half the
    # contract — done() must not also be the atom. The missing half is that
    # **done() must be FALSE when the loop starts**. Both weather ids handed in
    # a LATCHED `*Ready` flag ("data has arrived at least once", never reset),
    # already true at entry, so the loop below took exactly ONE sample, of an
    # atom that had long since returned to its sentinel, and the adjudicator
    # read that as "the atom is never written". A completion oracle that is
    # already satisfied cannot bracket a fetch; there is no observation to make
    # and the honest verdict is UNMET, not FAIL.
    try:
        preheld = bool(done())
    except (TimeoutError, NoAnswer):
        preheld = False
    if preheld:
        print(f"  {prefix}{var}: completion oracle already TRUE at entry — "
              f"no fetch edge to bracket; not observed", flush=True)
        return {"polls": 0, "seen": [], "nonsentinel": [], "bad": [],
                "completed": False, "returned_idle": False, "preheld": True}
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            seen.add(dut.get_int(var, timeout=3.0))
            polls += 1
        except (TimeoutError, NoAnswer):
            # An unanswered read inside a bounded loop is not a verdict; the
            # deadline is. BadField is deliberately NOT caught — a renamed or
            # wrong-typed atom is exactly the defect this id exists to catch.
            time.sleep(0.2)
            continue
        if done():
            completed = True
            break
    # The atom must come back to idle. Give it a bounded moment: `done()` can
    # fire on the counter the parse callback bumps, a few instructions before
    # `*phaseSlot = -1` on the same core.
    returned_idle = False
    idle_deadline = time.monotonic() + 5.0
    while completed and time.monotonic() < idle_deadline:
        try:
            if dut.get_int(var, timeout=3.0) == -1:
                returned_idle = True
                break
        except (TimeoutError, NoAnswer):
            pass
        time.sleep(0.3)
    nonsentinel = sorted(v for v in seen if v != -1)
    bad = sorted(v for v in nonsentinel if not (lo <= v <= hi))
    print(f"  {prefix}{var}: {polls} polls, saw {sorted(seen)}, "
          f"domain [{lo},{hi}], completed={completed}, idle_after={returned_idle}",
          flush=True)
    return {"polls": polls, "seen": sorted(seen), "nonsentinel": nonsentinel,
            "bad": bad, "completed": completed, "returned_idle": returned_idle,
            "preheld": False}


#: dataTask FetchType bit positions, from `app/src/dataTask.h:11-22`.
_FETCH_TYPE = {"weather": 0, "crypto": 1, "stockquote": 2, "stockchart": 3}


def _dataq_fetch_edge(dut: Dut, fetch_type: int):
    """Build a done()-shaped closure that is FALSE until a dataTask fetch of
    `fetch_type` has been seen ACTIVE and then seen FINISHED — a real per-fetch
    edge.

    Why this and not `weatherReady`/`cryptoReady`: those are latched flags
    (`WeatherApp::_dataReady` is set true on the first good parse and never
    cleared), so after an app's first success they answer true forever. Handing
    one to `_observe_progress_atom` as the completion oracle makes the loop exit
    on its first iteration — the defect the phase-2 hardware session diagnosed
    behind T_WX_07/T_CX_07's FAILs.

    `get dataq` is the queue's own bookkeeping: `pendingMask` is set in
    `enqueue()`/`enqueueWeather()` and cleared by the dispatch loop after the
    fetch function returns (`dataTaskStorage.cpp:1715`), and `inFlight` is the
    dispatch loop's own marker. Neither is written by the fetch body that writes
    the progress atom, so the oracle stays independent of its subject.
    """
    state = {"seen_active": False}

    def done() -> bool:
        try:
            q = dut.cmd("get dataq", timeout=3.0)
        except (TimeoutError, NoAnswer):
            return False
        if not q.get("ok"):
            return False
        # No `.get(key, <literal>)` here on purpose (R18 / check_defaulted_reads):
        # a defaulted read would hand a FAILED read the same type as a real one,
        # and a silent `inFlight = -1` would read as "the fetch finished".
        pm, inf = q.get("pendingMask"), q.get("inFlight")
        if pm is None or inf is None:
            return False
        try:
            pending = int(pm) & (1 << fetch_type)
            in_flight = int(inf)
        except (TypeError, ValueError):
            return False
        if pending or in_flight == fetch_type:
            state["seen_active"] = True
            return False
        return state["seen_active"]

    return done


def _progress_atom_verdict(var: str, obs: dict) -> tuple:
    """-> (outcome, message) where outcome is 'pass' | 'fail' | 'unmet'.

    Split out from the test bodies so all four ids adjudicate identically and
    the rule is readable in one place rather than four."""
    if obs.get("preheld"):
        return ("unmet", f"the completion oracle for {var} was already TRUE when the "
                         f"observation began, so no fetch could be bracketed and the "
                         f"atom was never sampled; the premise (an unstarted fetch to "
                         f"watch) did not hold, so this id has no verdict")
    if not obs["completed"]:
        return ("unmet", f"no fetch completed inside the window — {var} was polled "
                         f"{obs['polls']}x and saw {obs['seen']}; the premise (a fetch "
                         f"to observe) did not hold, so this id has no verdict")
    if obs["bad"]:
        return ("fail", f"{var} took {obs['bad']} — outside its documented domain "
                        f"{_PROGRESS_ATOM_DOMAIN[var]} and not the -1 sentinel")
    if not obs["nonsentinel"]:
        return ("fail", f"{var} never left the -1 sentinel across a completed fetch "
                        f"({obs['polls']} polls) — the atom M-DATATASK-PROGRESS "
                        f"exists to provide is not being written")
    if not obs["returned_idle"]:
        return ("fail", f"{var} reached {obs['nonsentinel']} but did not return to -1 "
                        f"within 5 s of completion — a stuck atom reports a fetch that "
                        f"is not running")
    return ("pass", f"{var} left the sentinel (saw {obs['nonsentinel']}), stayed inside "
                    f"{_PROGRESS_ATOM_DOMAIN[var]}, and returned to -1")


def _wait_chart_complete(dut: Dut, before: int, timeout_s: float = 45.0,
                         test_id: str = "") -> bool:
    """Wait until fetchOkCount advances past `before` — proves a chart fetch completed
    (HTTP + parse), not just that it was enqueued (LL-041). `before` must be snapshotted
    from fetchOkCount before the triggering tap/command. Returns True on success.
    On timeout prints stockChartProgress phase and the last dataq sample to aid
    diagnosis (TASK-300: distinguishes queued/parked-in-yield from never-enqueued
    — the fetch's tlsYield() fires BEFORE stockChartProgress is set, so
    progress=-1 alone can't tell the two apart).

    TASK-585: `before` is now guaranteed to be a real reading, because
    `_stock_ok_count` raises rather than handing back `-1`. That guarantee is
    the whole fix — `_wait_chart_complete(-1)` returned True on its first poll,
    which made this function an unconditional pass wherever its caller's
    baseline read had raced (`G-2`, nine ids). The assertion below is defensive
    and cheap: a negative baseline can no longer be produced by a read, so if one
    arrives it came from a caller inventing it, and inventing it is the defect."""
    _reject_sentinel_baseline(before)
    prefix = f"[{test_id}] " if test_id else ""
    deadline = time.monotonic() + timeout_s
    last_q = None
    ticks = 0
    while time.monotonic() < deadline:
        try:
            current = _stock_ok_count(dut)
        except (TimeoutError, NoAnswer):
            # A read nobody answered inside a bounded poll loop is not a verdict
            # — the loop's own deadline is. A BadField is NOT caught: a renamed
            # or wrong-typed fetchOkCount is a real defect and must reach the
            # dispatch loop as a FAIL rather than be polled away for 45 s.
            time.sleep(1.0)
            continue
        if current > before:
            return True
        ticks += 1
        if ticks % 3 == 0:  # sample the dispatch pipeline every ~3 s (TASK-300)
            try:
                q = dut.cmd("get dataq", timeout=3.0)
                if q.get("ok"):
                    q.pop("ok", None); q.pop("cmd", None); q.pop("last", None)
                    if q != last_q:
                        print(f"  {prefix}dataq: {q}", flush=True)
                    last_q = q
            except TimeoutError:
                pass
        time.sleep(1.0)
    try:
        phase = dut.get_int("stockChartProgress", timeout=3.0)
    except DeviceReadError:
        phase = "?"   # diagnostic text only — never an oracle term
    phase_name = _CHART_PHASE_NAMES.get(phase, "idle" if phase == -1 else "unknown")
    print(f"  {prefix}_wait_chart_complete timed out — stockChartProgress={phase} "
          f"({phase_name}) dataq={last_q}", flush=True)
    # TASK-386: heap/backoff snapshot on every timeout, for every caller, automatically
    # — dataq was already sampled above, this adds the two fields it doesn't cover.
    # Return type/signature unchanged (still bool) — zero risk to any of the 9 existing
    # call sites (T176/T188/T192/T193/T204/T-BUSY-01b/...; T185 and T194 retired 2026-09-05, TASK-603),
    # and any future
    # caller gets this for free without needing to know _diag_snapshot() exists.
    _diag_snapshot(dut, f"{prefix}_wait_chart_complete-timeout")
    return False


def _restore_spotify(dut: Dut, timeout: float = 3.0) -> bool:
    """Ensure currentAppId == Spotify; resets scroll then taps Spotify slot if needed.

    TASK-280: cmdTap's taskbar branch now routes through resolvePlayerSlot(), same as
    production — a tap on the player slot lands on WebRadio if that's the persisted
    mode. Force playerMode=spotify first so the tap is guaranteed to land on Spotify
    regardless of what a prior test left persisted (previously masked by the bug this
    task fixed: cmdTap used to always land on Spotify no matter the persisted mode).

    TASK-413: tapping the player slot while a player-mode app (Spotify/WebRadio/
    LocalPlayer) is ALREADY active now CYCLES instead of restoring (resolvePlayerTap,
    ADR-059 D6). So when currentAppId is WebRadio or LocalPlayer, setting
    playerMode=spotify and tapping no longer lands on Spotify — it cycles away from
    whatever `set playerMode spotify` just wrote. Step off to a non-player app
    (Clock) first so the follow-up tap takes the restore path, not the cycle path.
    """
    r = dut.cmd("get appId", timeout=timeout)
    if r.get("name") == "Spotify":
        return True
    if r.get("name") in ("WebRadio", "LocalPlayer"):
        _tb_set_offset(dut, 0)
        dut.set_cooldown_zero()
        cx, cy = _c.tap_taskbar_slot(APP_SLOT["Clock"])
        dut.cmd(f"tap {cx} {cy}", timeout=timeout)
        time.sleep(0.2)
    dut.cmd("set playerMode spotify", timeout=timeout)
    _tb_set_offset(dut, 0)
    dut.set_cooldown_zero()
    sx, sy = _c.tap_taskbar_slot(APP_SLOT["Spotify"])
    dut.cmd(f"tap {sx} {sy}", timeout=timeout)
    time.sleep(0.3)
    r2 = dut.cmd("get appId", timeout=timeout)
    return r2.get("name") == "Spotify"


def _switch_to(dut: Dut, app_name: str, timeout: float = 3.0) -> bool:
    """Reset scroll to 0, tap the app's taskbar slot, verify appId == app_name.

    TASK-605/E-11/F-6: eject-only apps (WebRadio, LocalPlayer — TASK-242/413,
    APP_SLOT index >= _TB_N == TASKBAR_APP_COUNT) have NO taskbar slot of their
    own. Tapping `tap_taskbar_slot(APP_SLOT[name])` for one of them wraps
    (`appIdx = slot % TASKBAR_APP_COUNT`) onto the player/Spotify slot instead,
    landing on the intended app only when a predecessor id happened to leave
    the board in the right player-mode/cycle state — silently, since the
    caller sees a bool, not why it worked or didn't. Refuse instead: use
    `_switch_to_webradio_capture_heap` (webradio.py) for WebRadio, or the
    player-mode cycle helpers for LocalPlayer.
    """
    if app_name not in APP_SLOT:
        return False
    if APP_SLOT[app_name] >= _TB_N:
        return False
    _tb_set_offset(dut, 0)
    dut.set_cooldown_zero()
    x, y = _c.tap_taskbar_slot(APP_SLOT[app_name])
    dut.cmd(f"tap {x} {y}", timeout=timeout)
    time.sleep(0.4)
    return _appid_is(dut, app_name, timeout)


def _diag_snapshot(dut: Dut, tag: str = "") -> str:
    """Best-effort one-line heap/backoff/dataq snapshot (TASK-385). `run/test-targeted`
    always starts from a fresh flash+boot, so an isolated re-run can only prove a test
    fails-or-doesn't from a *clean* state — it can't observe whatever heap fragmentation,
    dataTask queue backlog, or Spotify-poll/tlsYield contention ~150 prior tests may have
    left behind by the time T193 runs in a real `run/test` full-suite pass (T194, its
    twin here, was retired 2026-09-05 under TASK-603). Embedding
    this snapshot directly into the fail()/skip() reason (not just printing it) means the
    evidence survives even when the run has no `LOG_FILE=` capture — closing exactly the
    gap TASK-385 was originally blocked on ('no serial capture for this run'). Compare
    against the clean-boot baseline from the 2026-08-02 isolated 5/5-pass investigation:
    heap freeInt~74-118k/lfbInt~41-45k, dataq queueWaiting=0/inFlight=0 pre-trigger,
    spAct idle between POLL dequeues — a same-run T193 snapshot reading materially
    lower/busier than that is evidence for the suite-accumulation hypotheses; a snapshot
    that looks the same as a clean boot points back toward plain connect-level noise
    (TASK-383) instead."""
    parts = []
    try:
        h = dut.cmd("get heap", timeout=3.0)
        parts.append(f"heap(freeInt={h.get('freeInt')},lfbInt={h.get('lfbInt')},"
                      f"freeDma={h.get('freeDma')},lfbDma={h.get('lfbDma')})" if h.get("ok")
                      else "heap(no-ok)")
    except TimeoutError:
        parts.append("heap(timeout)")
    try:
        b = dut.cmd("get backoff", timeout=3.0)
        parts.append(f"backoff(cf={b.get('consecutiveFailures')})" if b.get("ok")
                      else "backoff(no-ok)")
    except TimeoutError:
        parts.append("backoff(timeout)")
    try:
        q = dut.cmd("get dataq", timeout=3.0)
        parts.append(
            f"dataq(ms={q.get('ms')},qw={q.get('queueWaiting')},inFlight={q.get('inFlight')},"
            f"inFlightMs={q.get('inFlightMs')},tlsStopped={q.get('tlsStopped')},"
            f"spAct={q.get('spAct')},spActMs={q.get('spActMs')},"
            f"yieldCount={q.get('yieldCount')})" if q.get("ok") else "dataq(no-ok)")
    except TimeoutError:
        parts.append("dataq(timeout)")
    snap = " ".join(parts)
    prefix = f"[{tag}] " if tag else ""
    print(f"  {prefix}diag: {snap}", flush=True)
    return snap


def _wait_shell_not_busy(dut: Dut, timeout_s: float = 45.0) -> bool:
    """Wait for g_shellBusy to clear (chart/heatmap fetch complete)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if not dut.get_bool("shellBusy", field="busy", timeout=5.0):
                return True
        except (TimeoutError, NoAnswer):
            pass
        time.sleep(1.0)
    # TASK-386: same treatment as _wait_chart_complete — automatic for every caller.
    # This helper gates on g_shellBusy directly, so a timeout here is exactly as
    # relevant to the dataTask/tlsYield hypotheses as a chart-fetch timeout is.
    _diag_snapshot(dut, "_wait_shell_not_busy-timeout")
    return False


# TASK-242: the taskbar cycles through apps BEFORE WebRadio — WebRadio is
# eject-entered only, no taskbar slot. Must match firmware TASKBAR_APP_COUNT
# (= (int)AppId::WebRadio), NOT APP_COUNT, or scroll-wrap tests mismatch.
_TB_X = _c.TASKBAR_X + _c.TASKBAR_W // 2   # 297
_TB_N = APP_SLOT["WebRadio"]                  # = 11 (Spotify..PlaneRadar) — TASK-307


def _tb_get_offset(dut: Dut) -> "int | None":
    r = dut.cmd("get tbScrollOffset", timeout=3.0)
    v = r.get("val")
    return int(v) if isinstance(v, (int, float)) else None


def _tb_set_offset(dut: Dut, target: int) -> bool:
    """Drive tbScrollOffset to target via drag gestures (one drag per slot step).
    Chooses the shorter path; each drag is 50 px / 10 steps (LP-safe).
    y span [60, 110] stays within screen bounds and clear of slot 0 edge."""
    current = _tb_get_offset(dut)
    if current is None:
        return False
    n = _TB_N
    steps_up   = (target - current) % n   # up = offset++
    steps_down = (current - target) % n   # down = offset--
    if steps_up <= steps_down:
        for _ in range(steps_up):
            dut.set_cooldown_zero()
            dut.cmd(f"drag {_TB_X} 110 {_TB_X} 60 10", timeout=5.0)  # 50 px up → +1
            time.sleep(0.1)
    else:
        for _ in range(steps_down):
            dut.set_cooldown_zero()
            dut.cmd(f"drag {_TB_X} 60 {_TB_X} 110 10", timeout=5.0)  # 50 px down → -1
            time.sleep(0.1)
    return _tb_get_offset(dut) == target


def _tb_precondition(dut: Dut, tid: str) -> bool:
    """Common precondition for T162–T166: Spotify active, tbScrollOffset=0."""
    if not _restore_spotify(dut):
        skip(tid, "precondition: could not restore Spotify")
        return False
    if not _tb_set_offset(dut, 0):
        skip(tid, f"precondition: tbScrollOffset={_tb_get_offset(dut)} could not be reset to 0")
        return False
    dut.set_cooldown_zero()
    return True


@contextmanager
def _bgpoll_suspended(dut: "Dut"):
    """Suspend background Spotify polls for the duration of the block.
    Guarantees bgPoll is put BACK TO WHAT IT WAS even if the test body raises.
    Pre-conditions (e.g. _wait_shell_not_busy) are the caller's responsibility.

    TASK-602 / R17: this delegates to `Dut.saved`, which is the only restore
    mechanism the gate credits. It used to restore with a literal `1` on the way
    out — correct for every caller that found it at 1, and a silent WRITE for any
    that did not; and the `set` was unacknowledged, so a refused restore read as a
    successful one. `bgPoll` answers `get bgPoll` in the field `enabled`
    (`spotifyTaskStorage.cpp:923`), not `val`.
    """
    with dut.saved("bgPoll", field="enabled", set_to=0, timeout=2.0):
        yield
