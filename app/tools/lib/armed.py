#!/usr/bin/env python3
"""lib/armed.py — TASK-635 boundary-check decision logic (R14, harness half).

Binding design: docs/architecture/designs/M-HARNESS2-armed-state-task635.md
§3/§4. This module is PURE decision logic: no `serial` import, no port, no
`Dut` — `gate/check_import_safety.py` must stay green, and the whole point of
keeping this pure is that the inversion test (`lib/test_armed.py`) can drive
every branch with a stubbed reply and no device (BP-068's stub-the-serial
pattern, same as `_gate.py`'s EC-G8).

THE WIRE SHAPE (IFC-007, additive, design §2.4):

    get armed    -> {"ok":true,"cmd":"get","var":"armed","n":2,
                      "armed":["wrDeadUrls","nowFrozen"],"last":true}
    set injclear -> {"ok":true,"cmd":"set","var":"injclear","n":2,
                      "cleared":["wrDeadUrls","nowFrozen"]}

Older firmware (the `get armed` var does not exist yet) answers with
`cmdGet.cpp`'s generic unknown-var reply:

    {"ok":false,"cmd":"get","error":"unknown var","var":"armed"}

`parse_armed()` reduces both that shape AND a timeout/garbled reply (the
caller passes `None` for either) to `None` — "unsupported", tolerated, never a
verdict change (design §3: "the stub the DEV review's Day 8 asked for, so the
harness does not wait on a flash").

THE DECISION (design §3):

  * `armed == []`        -> nothing.
  * `armed` non-empty    -> the id that just ran gets a FAIL naming the
    injectors. If it already had a FAIL/UNMET/SKIP record, that text is kept
    INSIDE the new reason — a leak must never erase the original finding, it
    adds to it.
  * `armed is None`      -> no verdict change. The caller (runner.py) is
    responsible for printing the "tolerated" notice ONCE per run; this module
    exposes a tiny stateful notifier (`BoundaryNotifier`) for that so the
    once-per-run bookkeeping is still driven by pure, testable logic rather
    than a print-flag scattered in the runner.

Session start (design §3, last paragraph): anything armed before the first id
ran cannot be attributed to a test in this run, so it is cleared and reported
as a rig note, attributed to nobody. `session_start_note()` builds that text;
it does NOT touch `RESULTS` — there is no id to blame.

No `Verdict` member is added (ADR-066 D2a). A leak is a FAIL with a reason.
"""

from __future__ import annotations

from typing import Optional

from . import results as _results


def parse_armed(reply: Optional[dict]) -> Optional[list]:
    """`get armed`'s JSON reply -> the armed-name list, or `None`.

    `None` covers every "this harness cannot trust the list" case in one
    place: a timeout (the caller passes `None` straight through), the
    unknown-var shape older firmware answers with, and any other malformed or
    unexpected reply. Treating all of those alike is deliberate — the
    boundary check must never mistake "I don't know" for "nothing is armed".
    """
    if not isinstance(reply, dict):
        return None
    if reply.get("ok") is not True or reply.get("var") != "armed":
        return None
    armed = reply.get("armed")
    if not isinstance(armed, list):
        return None
    return [str(x) for x in armed]


#: The console's `set` parser requires `set <var> <val>` and answers `bad args`
#: to a bare `set injclear` — found on the DUT 2026-09-13, after every host arm
#: had passed against a stub. The value is ignored by the handler.
INJCLEAR_CMD = "set injclear 1"
GET_ARMED_CMD = "get armed"

UNSUPPORTED = "unsupported"
UNREADABLE = "unreadable"


def reply_status(reply: Optional[dict]):
    """Why `parse_armed()` returned `None`: `UNSUPPORTED` for the unknown-var
    shape (older firmware — announce once), `UNREADABLE` for anything else (a
    timeout or a malformed reply on firmware that HAS the key). The two must not
    share one once-per-run notice: after the firmware lands, an unreadable read
    means THIS boundary went unchecked, and that is said every time."""
    if (isinstance(reply, dict) and reply.get("ok") is False
            and reply.get("var") == "armed"
            and "unknown" in str(reply.get("error", ""))):
        return UNSUPPORTED
    return UNREADABLE


def unreadable_note(context: str) -> str:
    return (f"[armed] boundary UNCHECKED {context}: `get armed` gave no usable "
            f"reply — a leak here would go unattributed. No verdict changed.")


def clear_failed_note(context: str, still: list) -> str:
    return (f"[armed] set injclear {context} did NOT clear: {', '.join(still)} "
            f"— the next id may inherit it and be wrongly blamed.")


def leak_reason(tid: str, armed: list) -> str:
    """The FAIL text for a non-empty boundary check after `tid`.

    Keeps the original record TEXT (whatever verdict it was — FAIL, UNMET,
    SKIP, or a plain PASS) inside the new reason, per design §3: a leak must
    not erase what the test itself found.
    """
    names = ", ".join(armed)
    original = _results.RESULTS.get(tid)
    if original:
        return (f"boundary check: still armed after {tid}: {names} "
                f"(original record: {original})")
    return f"boundary check: still armed after {tid}: {names}"


def apply_leak(tid: str, armed: list) -> None:
    """Non-empty `get armed` after `tid` ran: FAIL `tid`, whatever it recorded.

    A no-op for an empty list — callers may call this unconditionally after
    checking truthiness, but guarding here too keeps the function safe to call
    directly from a test without duplicating the check.
    """
    if not armed:
        return
    _results.fail(tid, leak_reason(tid, armed))


def session_start_note(armed: list) -> str:
    """The rig-note text for a session-start leak. Attributed to nobody —
    no `RESULTS` write happens for this; the caller only prints it and issues
    `set injclear`."""
    names = ", ".join(armed)
    return (f"[armed] session start: {names} already armed before any test in "
            f"this run — not attributable to any id here, clearing "
            f"(set injclear) and continuing. This is a rig note, not a "
            f"verdict.")


class BoundaryNotifier:
    """Once-per-run bookkeeping for the `None` (unsupported/timeout) case.

    A tiny, deliberately non-serial piece of state so the "print it once" rule
    is exercised by the pure test suite instead of living as an untested flag
    inside the runner's closures.
    """

    def __init__(self) -> None:
        self._told = False

    def none_notice(self) -> Optional[str]:
        """Call once per `get armed` read that came back `None`. Returns the
        notice text the FIRST time, `None` every time after."""
        if self._told:
            return None
        self._told = True
        return ("[armed] `get armed` is unsupported on this firmware (or the "
                "read timed out) — boundary check tolerated, no verdict "
                "changed. This notice prints once per run.")
