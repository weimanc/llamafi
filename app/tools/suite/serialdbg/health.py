"""suite/serialdbg/health.py — the HEALTH class, T_DH_01..03. TASK-565.

M-TESTARCH §3.1. **Class answers *whether a test may run yet*.** A HEALTH check
belongs here if its failure INVALIDATES EVERY OTHER TEST IN THE RUN, and it can
be established in seconds with read-only console commands:

  T_DH_01  the shell answers CORRECT data, not merely answers
  T_DH_02  the device's own view of the network is coherent (`get wifiCfg`)
  T_DH_03  app switching is alive

Two candidates were cut at review and are deliberately absent: a loop()-liveness
check (redundant with TASK-564's `[bootphase] 6 ready` gate) and a heap/stack
floors check (`T_DH_04`, deferred to TASK-569 — no derivable bound exists, and
the signal it reads is invalid at the moment the health class reads it).

WHY THESE THREE USE NO TAP INJECTION. Tap/drag dispatch is CORE (class 2). §3
forbids a test from asserting a claim belonging to a lower class, so a HEALTH
check may not be built on the tap path: a broken injection dispatch would then
be reported as a dead board. T_DH_03 therefore switches apps with the
`switchApp` console command, which is the shell's own switch machinery with no
CORE machinery underneath it. (The taskbar-tap path is asserted by the APP-class
A1 row, which is where that claim belongs.)

THE REGISTRY IS SEPARATE, ON PURPOSE (§4.5). `HEALTH_TESTS` is merged into
neither `build_all_tests()` nor `default_tests`, because the ids must be
ADDRESSABLE (`run/test-targeted T_DH_01` must work) and NOT FILTERABLE OUT
(`--tests <list without T_DH_*>` must not become a way to skip the gate).
Putting them in `build_all_tests()` gives neither and makes the one mutating
check run twice. They DO appear in `build_all_meta()` — the record is what mode
P's `health_verdict()` reads, and a health class the triage layer cannot see is
not a health class.

WHAT IS NOT BUILT HERE, AND WHERE IT LIVES. The unconditional gate phase, the
`NOT-RUN` bucket and exit 4 for a suite run are **TASK-566** (§4.1), which must
land with its six consumers or a HEALTH failure reads as `REGRESS` from
`run/player-gate`. This task builds the checks, the standalone pre-flight
(`run/dut-health`) and the premise line. Consequently §4.5's "a passing health
check contributes no RESULTS row" does not apply yet: its stated reasons — pass
count inflation and `NOT-RUN` bookkeeping — are both artefacts of that gate
phase, and until it exists the only way a health id runs is by being explicitly
selected, where it IS the run. Recording the pass is also what lets mode P
report `ok` rather than `not-run(0/3)`.

THE FLAKE POLICY DOES NOT APPLY (§4.4). No health id is declared in flaky.yaml
and the dispatch below never calls `run_with_flake_retry`: retrying a health
check doubles its cost, re-runs the one mutating check, and produces a
`FLAKY-PASS` with no defined meaning for a binary "is this board a valid
subject". A health check may retry INTERNALLY on a bounded deadline — that is a
bound, not a flake.
"""

from __future__ import annotations

import json
import re
import time

from app_ids_gen import APP_ORDER
from lib import dut as _dutmod
from lib.dut import Dut
from lib.results import BLOCKING, fail, pass_, verdict_of
from suite.serialdbg._meta import meta

# ── T_DH_01 ──────────────────────────────────────────────────────────────────

#: `get playerMode`'s three names (cmdGet.cpp `kPmNames`). A reply outside this
#: set is the "answers, but with garbage" case T_DH_01 exists to catch.
_PLAYER_MODES = ("Spotify", "WebRadio", "Player")

_ELF_RE = re.compile(r"^[0-9a-f]{8}$")


@meta(cls="HEALTH", effect="read-only",
      effect_reason="three-gets",
      cls_reason="Every id in every family is a sequence of console commands read "
                 "back as JSON. If a reply comes back truncated or one reply behind "
                 "the request, `Dut.cmd` returns the wrong line with `ok:true` and "
                 "the whole run scores fields it never asked for — the "
                 "`variant spotify=None` case that silently SKIPped 16 tests. "
                 "WP-C C-8 is right that the FIELDS it checks are compile-time "
                 "constants; the premise it actually establishes is reply "
                 "INTEGRITY, and that premise is genuinely shared by all 216 ids.")
def t_dh_01(dut: Dut) -> None:
    """The shell answers CORRECT data, not merely answers.

    `info`, `get variant` and `get playerMode` must each reply with non-null
    fields. This is the check that turns a `variant spotify=None` — a reply the
    harness accepted, then silently SKIPped 16 tests on — into a named health
    failure instead of a spray of skips nobody reads.
    """
    tid = "T_DH_01"
    bad = []

    try:
        r = dut.cmd("info", timeout=3.0)
    except TimeoutError as e:
        fail(tid, f"`info` did not answer: {e}")
        return
    if not r.get("ok"):
        bad.append(f"info: ok={r.get('ok')!r}")
    if not _ELF_RE.match(str(r.get("elf") or "")):
        bad.append(f"info.elf={r.get('elf')!r} (want 8 hex chars)")
    if not r.get("build"):
        bad.append(f"info.build={r.get('build')!r}")
    try:
        if int(r.get("heap", 0)) <= 0:
            bad.append(f"info.heap={r.get('heap')!r}")
    except (TypeError, ValueError):
        bad.append(f"info.heap={r.get('heap')!r} (not a number)")

    try:
        v = dut.cmd("get variant", timeout=3.0)
    except TimeoutError as e:
        fail(tid, f"`get variant` did not answer: {e} (info was {r})")
        return
    if not v.get("ok") or v.get("spotify") not in ("on", "off"):
        bad.append(f"variant.spotify={v.get('spotify')!r} (want 'on'/'off')")

    try:
        pm = dut.cmd("get playerMode", timeout=3.0)
    except TimeoutError as e:
        fail(tid, f"`get playerMode` did not answer: {e}")
        return
    if not pm.get("ok") or pm.get("name") not in _PLAYER_MODES:
        bad.append(f"playerMode.name={pm.get('name')!r} (want one of {_PLAYER_MODES})")
    if pm.get("val") not in (0, 1, 2):
        bad.append(f"playerMode.val={pm.get('val')!r}")

    if bad:
        fail(tid, "shell answers, but not with correct data: " + "; ".join(bad))
        return
    pass_(tid, f"elf={r.get('elf')} variant={v.get('spotify')} "
               f"playerMode={pm.get('name')}")


# ── T_DH_02 ──────────────────────────────────────────────────────────────────

#: `[wifiCfg] err=0 ssid="…" pwlen=… bssid_set=0 bssid=… ch=…` (cmdGet.cpp).
_WIFICFG_RE = re.compile(r'\[wifiCfg\]\s+err=(-?\d+)\s+ssid="([^"]*)"\s+'
                         r'pwlen=(\d+)\s+bssid_set=(\d+)')

_ZERO_IPS = ("", "0.0.0.0", "(IP unset)")


def read_wifi_cfg(dut: Dut, timeout: float = 5.0) -> dict:
    """`get wifiCfg`, parsed. Returns {} if the bare line never arrived.

    TWO IMPLEMENTATION FACTS, BOTH FROM §3.1 AND BOTH LOAD-BEARING:

    1. The payload is a bare `[wifiCfg]` LOG line, not JSON, so `cmd()` discards
       it (the §2.2a I1 violation). It has to be read with `drain_log_lines()`.
    2. `drain_log_lines()` leaves the trailing JSON ack in the buffer. Not
       draining it desynchronises the NEXT `read_json()` by one reply — the
       TASK-548 bug class, which is why this is written down rather than left to
       the implementer.
    """
    dut.send("get wifiCfg")
    lines = dut.drain_log_lines(r"\[wifiCfg\]", 1, timeout=timeout)
    # (2) — swallow the ack that drain_log_lines walked past. A miss here is not
    # fatal on its own, so it is bounded and never raises.
    try:
        dut.read_json(timeout=2.0)
    except TimeoutError:
        pass
    if not lines:
        return {}
    m = _WIFICFG_RE.search(lines[0])
    if not m:
        return {"raw": lines[0]}
    return {"raw": lines[0], "err": int(m.group(1)), "ssid": m.group(2),
            "pwlen": int(m.group(3)), "bssid_set": int(m.group(4))}


@meta(cls="HEALTH", scope="boot", scope_reason="wifi-identity",
      effect="read-only", effect_reason="ip+wifiCfg",
      cls_reason="TASK-426's wedge — a failed boot leaves STA retrying a dead SSID "
                 "forever — presents downstream as every network-app id failing its "
                 "fetch, i.e. as a firmware defect in Stock, Weather, Crypto, "
                 "Teletext, PlaneRadar and WebRadio at once. A board that is not "
                 "associated cannot produce a trustworthy verdict for any of them, "
                 "so the run must stop here rather than attribute the rig's state to "
                 "the firmware. Bounded by WP-C C-9: it proves association, not "
                 "reachability, and not that the SSID is the expected one.")
def t_dh_02(dut: Dut) -> None:
    """The device's own view of the network is coherent.

    `get ip` non-zero AND `get wifiCfg`'s ssid/bssid_set consistent with an
    association. Bound: TASK-426's wedge signature — a failed boot leaves STA
    configured for a dead SSID and auto-reconnect retries it forever, so the
    board looks associated to nobody and `get wifiCfg` is the tool that says so.
    It existed, was purpose-built for exactly this state, and was never run.
    """
    tid = "T_DH_02"
    if getattr(_dutmod, "_NO_WIFI", False):
        from lib.results import skip
        skip(tid, "--no-wifi: this run asserts nothing about the network, so a "
                  "network-identity check cannot gate it")
        return

    try:
        r = dut.cmd("get ip", timeout=3.0)
    except TimeoutError as e:
        fail(tid, f"`get ip` did not answer: {e}")
        return
    ip = str(r.get("ip") or "").strip()

    cfg = read_wifi_cfg(dut)
    if not cfg:
        fail(tid, "no [wifiCfg] line within 5 s — the STA config is unreadable, "
                  "so nothing can be said about which network this board thinks "
                  "it is on")
        return
    if "err" not in cfg:
        fail(tid, f"[wifiCfg] line did not parse: {cfg.get('raw')!r}")
        return

    bad = []
    if cfg["err"] != 0:
        bad.append(f"esp_wifi_get_config err={cfg['err']}")
    if not cfg["ssid"]:
        bad.append("wifiCfg.ssid is empty — the STA has no configured network")
    if ip in _ZERO_IPS:
        bad.append(f"ip={ip!r} — not associated (TASK-426's wedge signature is "
                   f"exactly this: a configured ssid with no association, "
                   f"auto-reconnect retrying a dead AP forever)")
    if bad:
        fail(tid, "device-side network identity incoherent: " + "; ".join(bad)
                  + f"  [{cfg.get('raw')}]")
        return
    pass_(tid, f"ip={ip} ssid={cfg['ssid']!r} bssid_set={cfg['bssid_set']}")


# ── T_DH_03 ──────────────────────────────────────────────────────────────────

def _app_id(dut: Dut, timeout: float = 3.0):
    r = dut.cmd("get appId", timeout=timeout)
    if not r.get("ok"):
        return None
    return r.get("name")


def _switch_app_cmd(dut: Dut, name: str, timeout: float = 5.0) -> bool:
    """`switchApp <id>` and verify. NOT a taskbar tap — see the module header:
    tap dispatch is CORE, and a HEALTH check may not rest on it."""
    dut.cmd(f"switchApp {APP_ORDER.index(name)}", timeout=timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _app_id(dut) == name:
            return True
        time.sleep(0.2)
    return False


def _wait_idle(dut: Dut, timeout: float = 10.0):
    """-> (idle, last_reply). Bounded internal retry, which §4.4 permits: it is
    a deadline, not a flake."""
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        try:
            last = dut.cmd("get idle", timeout=3.0)
        except TimeoutError:
            last = {}
        if last.get("idle"):
            return True, last
        time.sleep(0.3)
    return False, last


@meta(cls="HEALTH", effect="mutating",
      effect_reason="switches-apps-and-restores",
      cls_reason="Roughly 150 ids begin by putting a named app on screen and end by "
                 "restoring Spotify. If the shell cannot switch apps, or cannot "
                 "reach quiescence after a switch, every one of them asserts against "
                 "whichever app is actually up — and reports the mismatch as a defect "
                 "in the app it believed it was testing. It is also the only health "
                 "check that reads a value the firmware can genuinely get wrong "
                 "(WP-C rates it the one SOUND check of the three).")
def t_dh_03(dut: Dut) -> None:
    """App switching is alive: switch to a neighbour and back, `appId` correct
    at each step, `get idle` returns idle.

    The human's observed symptom, which today nothing tests at all.

    It is the only health check that MUTATES device state, so per §3.1 it is
    declared `effect: mutating`, restores the entry app, and reports entry/exit
    `appId` (the `[TASK-407] entry/exit playerMode` snapshot is the precedent).
    It runs LAST, so a failure inside it cannot leave the board on an unexpected
    app for the rest of the run. Because it mutates, it is admissible HERE — a
    pre-flight check runs before the board's state is evidence — and
    inadmissible in a triage descent (§16.3). Same check, different context.
    """
    tid = "T_DH_03"
    entry = _app_id(dut)
    if entry is None or entry not in APP_ORDER:
        fail(tid, f"`get appId` did not name a known app at entry ({entry!r}) — "
                  f"nothing can be switched from an unknown app")
        return

    # A neighbour with no fetch of its own, so the check measures the switch and
    # not an app's network luck. WebRadio is excluded by construction: it is
    # eject-entered and has no taskbar slot.
    neighbour = "Clock" if entry != "Clock" else "Spotify"

    print(f"  [T_DH_03] entry appId: {entry}")
    if not _switch_app_cmd(dut, neighbour):
        fail(tid, f"switchApp -> {neighbour} did not take; appId still "
                  f"{_app_id(dut)!r} (entry was {entry})")
        return
    idle, last = _wait_idle(dut)
    if not idle:
        fail(tid, f"after switching to {neighbour} the shell never went idle "
                  f"within 10 s: {last} (entry {entry}) — restoring")
        _switch_app_cmd(dut, entry)
        return
    if not _switch_app_cmd(dut, entry):
        exitid = _app_id(dut)
        fail(tid, f"switch BACK to {entry} did not take; appId={exitid!r} — the "
                  f"board is NOT on its entry app")
        return
    idle2, last2 = _wait_idle(dut)
    print(f"  [T_DH_03] exit appId: {_app_id(dut)}")
    if not idle2:
        fail(tid, f"after switching back to {entry} the shell never went idle "
                  f"within 10 s: {last2}")
        return
    pass_(tid, f"{entry} -> {neighbour} -> {entry}, idle at each step")


# ── the registry ─────────────────────────────────────────────────────────────

#: §4.5. Merged into neither build_all_tests() nor default_tests. Ordered:
#: T_DH_03 mutates, so it runs last.
HEALTH_TESTS = {
    "T_DH_01": t_dh_01,
    "T_DH_02": t_dh_02,
    "T_DH_03": t_dh_03,
}

#: EC-G4. Printed BEFORE the verdict, on every `run/dut-health` run,
#: unconditionally. §5 E4: opening the port asserts DTR and resets the ESP32,
#: and per TASK-426 a reset is PRECISELY what clears the dead-SSID wedge — so
#: running this after forming a theory about a misbehaving board destroys the
#: state it was invoked to diagnose and manufactures a healthy-looking verdict.
RESET_WARNING = (
    "┌─ run/dut-health — READ THIS BEFORE THE VERDICT ──────────────────────────\n"
    "│ This opened the port, which RESET the board. This verdict describes the\n"
    "│ boot that reset caused, not the state you were investigating.\n"
    "│ It is a PRE-FLIGHT check ('is this board fit to test now?'), never a\n"
    "│ post-mortem. A wedged board is diagnosed from the monitor's disk log\n"
    "│ (run/monitor-read) and the [bootphase]/heartbeat stream already being\n"
    "│ captured — read that FIRST; the pre-reset state does not survive this.\n"
    "└──────────────────────────────────────────────────────────────────────────"
)


def run_health(dut: Dut, ids=None) -> list:
    """Run the health checks in registry order and return the failing ids.

    Never via `run_with_flake_retry` (§4.4). Never catches its own exceptions
    into silence: a health check that raises is a health FAIL, because the
    alternative is a run that proceeds on an unestablished premise.
    """
    ids = list(ids) if ids else list(HEALTH_TESTS)
    for tid in ids:
        try:
            HEALTH_TESTS[tid](dut)
        except TimeoutError as e:
            fail(tid, f"TimeoutError: {e}")
        except Exception as e:                                # noqa: BLE001
            fail(tid, f"Exception: {type(e).__name__}: {e}")
    # TYPED (TASK-624, R31/R38): `BLOCKING` is {FAIL, UNMET}. A health check
    # whose own premise could not be established has NOT certified the board —
    # `C-4` is a skipped health check announced as `[health] PASS` with a
    # sentence asserting the thing that did not run. Was
    # `RESULTS.get(t,"").startswith("FAIL")`.
    return [t for t in ids if verdict_of(t) in BLOCKING]


# ── E5: the premise line ─────────────────────────────────────────────────────

def premise(dut: Dut, switch_verdict: str = "not-run") -> str:
    """The `[health]` line — M-TESTARCH §5 E5 / EC-G5.

    Every DUT run states its own premise, so that a retrospective claim about
    the board is checkable against the run's own artefact instead of against
    memory. The boot-window design's §1.1 names the defining problem as *"no
    run's premise is verifiable after the fact"*; this is the line that makes it
    verifiable.

    The heap figures are REPORTED, NEVER ASSERTED (§5 E5, §3.1's deferred
    T_DH_04): this project's own recorded rule is that no heap number is
    trustworthy before ~150 s of settle, and this line is printed at boot+0.
    They are context for a later reader, not a gate.

    Best-effort in every field: a premise line that can abort a run is worse
    than no premise line.
    """
    def _try(fn, default="?"):
        try:
            return fn()
        except Exception:
            return default

    ip = _try(lambda: dut.cmd("get ip", timeout=3.0).get("ip") or "?")
    cfg = _try(lambda: read_wifi_cfg(dut), {})
    ssid = json.dumps(cfg.get("ssid")) if cfg.get("ssid") is not None else "?"
    heap = _try(lambda: dut.cmd("get heap", timeout=3.0), {})
    appid = _try(lambda: _app_id(dut) or "?")
    elapsed = _try(lambda: f"{time.monotonic() - dut._port_open_time:.1f}s")

    line = (f"[health] last-phase={_q(dut.last_phase() or 'none')} "
            f"gen={_try(dut.gen_tag)} "
            f"since-open={elapsed} ip={ip} ssid={ssid} "
            f"freeInt={heap.get('freeInt', '?')} lfbInt={heap.get('lfbInt', '?')} "
            f"appId={appid} switch={switch_verdict}")
    return line


def _q(text: str) -> str:
    text = str(text)
    return f'"{text}"' if (not text or " " in text) else text
