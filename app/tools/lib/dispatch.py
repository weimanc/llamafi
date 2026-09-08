#!/usr/bin/env python3
"""lib/dispatch.py — the ONE mapping from "what the body did" to a verdict.

TASK-671. Before this module the mapping lived inline in the serialdbg runner's
`_dispatch._once`: a body that raised `NoAnswer` was an UNMET, one that raised
`BadField` was a contract FAIL, a `TimeoutError` or any other exception was a
FAIL, and a body that returned normally had recorded its own verdict. That is a
fact about the harness — the same fact for every entry point and every replay —
and it was written in exactly one place that no host tool could reach.

The replay-driven gates need it verbatim. `check_can_go_red.py` asks "can this
cell go red at runtime?", and the answer depends on these arms as much as on the
body: under a silent device a body using raw `dut.cmd()` goes red through the
`TimeoutError` arm, not through any `fail()` of its own. A gate that wrapped the
body in its own try/except would be grading a dispatch the real run never
performs — a fake agreeing with itself, the exact thing `lib/replay.py` was
built at the transport to avoid.

So the mapping is a function, the runner calls it, and the gate calls the same
function. The `Arm` it returns says WHICH arm produced the outcome, which the
gate needs and the runner ignores.

Depends downward only (`lib.dut`, `lib.results`); never imports a suite.
"""

from __future__ import annotations

import enum
from typing import Callable

from . import dut as _dut_mod
from .results import fail, unmet


class Arm(enum.Enum):
    """Which dispatch arm the body's execution ended in."""

    #: the body returned normally; whatever verdict exists, the body recorded it
    BODY = "body"
    #: `NoAnswer` — the device never answered THIS question -> UNMET
    NO_ANSWER = "no-answer"
    #: `BadField` — it answered and the answer breaks the contract -> FAIL
    BAD_FIELD = "bad-field"
    #: `TimeoutError` from an untyped read -> FAIL
    TIMEOUT = "timeout"
    #: any other exception — the body crashed -> FAIL
    EXCEPTION = "exception"


#: Arms whose FAIL is the body's own doing, on its subject. `BAD_FIELD` is in the
#: set: a typed read that the device answered wrongly is the assertion TASK-584
#: converted the residue callers to, and its FAIL names the subject. `TIMEOUT`
#: and `EXCEPTION` are not — that red is an accident of the input, not a claim.
ASSERTION_ARMS = frozenset({Arm.BODY, Arm.BAD_FIELD})


def run_body(tid: str, body: Callable, dut) -> Arm:
    """Execute `body(dut)` under the runner's exception-to-verdict mapping.

    Returns the `Arm` the execution ended in. Anything deriving from
    `BaseException` but not `Exception` (a `TranscriptMiss`, `KeyboardInterrupt`)
    passes straight through — a replay miss must reach the engine intact.
    """
    try:
        body(dut)
        return Arm.BODY
    # TASK-596 / R18. These two arms must precede the generic ones: both are
    # RuntimeErrors and would otherwise land in `except Exception` as an
    # undifferentiated FAIL, which is the reporting half of the defect the
    # typed read exists to remove.
    except _dut_mod.NoAnswer as e:
        # The device never answered THIS question, so the body asserted
        # nothing. Its premise did not hold — that is an UNMET, which still
        # blocks and still exits 1 (ADR-066 D4), so nothing is weakened; what
        # changes is that triage is not told the firmware regressed when the
        # serial line was busy.
        unmet(tid, str(e))
        return Arm.NO_ANSWER
    except _dut_mod.BadField as e:
        # It answered, and the answer breaks the contract: a renamed key, a
        # changed reply shape, a wrong-typed value. Reproducible, and
        # somebody's code is wrong.
        fail(tid, f"contract: {e}")
        return Arm.BAD_FIELD
    except TimeoutError as e:
        fail(tid, f"TimeoutError: {e}")
        return Arm.TIMEOUT
    except Exception as e:                       # noqa: BLE001 — the runner's arm
        fail(tid, f"Exception: {e}")
        return Arm.EXCEPTION
