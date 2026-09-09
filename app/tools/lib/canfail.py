#!/usr/bin/env python3
"""lib/canfail.py — can this id go red AT RUNTIME? Answered by running it.

TASK-671 / M-HARNESS2 R34, the executable half.

── THE GAP THIS CLOSES ───────────────────────────────────────────────────────

`gate/check_no_reachable_fail.py` asks R34's question — "can this cell ever be
red?" — of the SOURCE: is a `fail()` reachable through the body's call graph?
That is a necessary condition and it is cheap, and it is not the question. A
`fail()` that is reachable in the text can still be unreachable in every run:

  * an inverted guard that passes exactly on the regression (`C-1`, `T-BUSY-05`);
  * a body that answers every deviation with `skip()`/`unmet()` before the
    `fail()` is ever consulted (the "skip on regression" residue, `D-2`);
  * a `fail()` inside a helper that is only called on a path no reply sequence
    produces;
  * a `fail()` whose guard compares two reads of the same key, so any
    perturbation that reaches one reaches the other.

None of those is decidable from the text without a program analysis that
`check_no_reachable_fail.py`'s docstring correctly refuses to attempt. So this
module does not analyse the body. It RUNS the body — the real body, through the
real `Dut`, under the runner's real exception arms (`lib/dispatch.py`) — against
a recorded healthy transcript that has been POISONED from some exchange onward,
and observes what verdict the body records. A FAIL observed that way is not a
prediction about the body; it is the body going red.

── WHAT A RECORDED TRANSCRIPT IS, FOR THIS QUESTION ──────────────────────────

`lib/replay.py` refuses a transcript whose ELF stamp does not match the built
firmware, because for FALSIFICATION (R9/R10, TASK-641/642/643) the transcript
stands in for what the current firmware would say, and a stale one is a lie
about the firmware. **This module waives that check on purpose, and the reason
is not convenience.** R34 is a question about the BODY, not about the firmware.
"Is there a reply sequence under which this body records FAIL?" is answered by
exhibiting one — and a reply sequence the firmware once produced, mutated, is a
reply sequence. Whether the firmware would still produce it is a different
question, asked by a different requirement, and it is not asked here. What DOES
have to hold is that the transcript is a healthy path for THIS body: the
unmutated replay must run to a PASS with no transcript miss. If the body changed
so that it asks something the recording does not answer, the replay misses and
the row is INCONCLUSIVE — decided by executing the body, not by hashing it.

The `ReplayResult`s produced under a waived ELF check have `is_confirmation ==
False`, and nothing here counts them as confirmations. They are counted as what
they are: observed verdicts.

── THE FOUR POISONS, TWO EXTENTS ──────────────────────────────────────────────

Each exchange of the recording — one command and the lines that answered it —
is identified by its POSITION in record order. A poison rewrites the reply at
position `k` (`AT`), or at every position `>= k` (`ONWARD`):

  PERTURB  every field except ok/var/cmd/last gets a different value of the
           same type. Deterministic: equal inputs perturb equally, which is why
           `AT` exists — a guard comparing two reads of one key is only moved
           by perturbing one of them.
  DROP     every field except ok/var/cmd/last is removed. The reply says `ok`
           and carries no data — the shape `check_defaulted_reads.py` chases:
           a body that PASSES on a dropped field was satisfied by a default.
  REFUSE   `{"ok": false, "var": ..}`. The device declines the question.
  SILENCE  the exchange answers nothing. `NoAnswer` on the typed path,
           `TimeoutError` on the raw one.

The sweep tries every (poison, extent, k) in a fixed order and stops at the
first ASSERTION-grade FAIL. It is a search for an existence proof, and it either
finds one or exhausts the space; the space is finite and printed.

── HOW A FAIL IS GRADED — the part a naive version gets wrong ────────────────

Not every FAIL is the body going red on its subject, and a gate that counted
them all would pass exactly the bodies R34 exists to catch:

  ASSERTION  `fail()` called from suite code on a reply the device gave. The
             body made a claim about its subject and the claim was false. THIS
             is R34's red, and the only grade that earns it.
  CONTRACT   the `BadField` arm: a typed read the device answered with the
             wrong SHAPE (field missing, `ok:false`, wrong type). Real red, but
             the harness's accessor asserted the reply format; the body asserted
             nothing about its subject. Every body with one typed read goes red
             this way under DROP — so if this counted, `C-1`'s inverted guard
             would pass the gate on the strength of a `get_int` it never looks
             at. Measured while building the negative suite, not predicted.
  ACCIDENT   the `TimeoutError` / `Exception` arm of the dispatch: the body
             crashed on the input. The cell is red, but nothing was asserted;
             a body whose only red is an accident goes red on a silent board
             and green on a wrong one.
  POLICY     `results.flake()` failing closed (undeclared/expired flake). The
             harness refused a claim; the body asserted nothing. `T084`,
             `T087`, `T091`, `T092` and `T_WR_EJECT_01` go red exactly this way
             on hardware — and the static gate correctly says they have no
             reachable `fail()`. Both are right, about different things.

The grade is read off `lib/dispatch.run_body`'s returned `Arm` and off which
function called `results.fail` — never off the record string.

── OUTCOMES ──────────────────────────────────────────────────────────────────

  RED                    an ASSERTION FAIL was observed; the evidence names
                         the poison, extent, position and command
  RED_WITHOUT_ASSERTION  red was observed, but only through CONTRACT, ACCIDENT
                         or POLICY; the detail names which. The cell can be
                         red; the body never says anything to make it so
  NEVER_RED              every (poison, extent, k) left the body green or unmet
  BASELINE_NOT_PASS   the unmutated replay did not PASS — the recording is not
                      a healthy path and nothing can be learnt by poisoning it
  INCONCLUSIVE        the baseline missed, crashed the engine, or its verdict
                      depends on host time (`replay_test`'s own refusals)

The gate blocks on the middle two (with a dated ledger), notes the next two,
and counts ids with no recording separately. It never turns an INCONCLUSIVE
into a finding — that is `lib/replay.py`'s rule and it is not relaxed here.

Depends downward only: `lib.replay`, `lib.dispatch`, `lib.results`. Never
imports a suite; the body arrives as an argument.
"""

from __future__ import annotations

import contextlib
import copy
import enum
import io
import json
import sys
import time as _time_mod

from . import dispatch as _dispatch
from . import replay as RP
from . import results as R

#: Reply fields that are never poisoned: they carry correlation and framing, not
#: data. Poisoning `var` would turn every read into a NoAnswer (a different,
#: already-covered poison); poisoning `last` would hang multi-part reads.
FRAMING = frozenset({"ok", "var", "cmd", "last"})


class Poison(enum.Enum):
    PERTURB = "perturb"
    DROP = "drop"
    REFUSE = "refuse"
    SILENCE = "silence"


class Extent(enum.Enum):
    AT = "at"          # only exchange k
    ONWARD = "onward"  # exchanges k, k+1, ... to the end


class Grade(enum.Enum):
    ASSERTION = "assertion"
    CONTRACT = "contract"
    ACCIDENT = "accident"
    POLICY = "policy"


class Outcome(enum.Enum):
    RED = "RED"
    RED_WITHOUT_ASSERTION = "RED-WITHOUT-ASSERTION"
    NEVER_RED = "NEVER-RED"
    BASELINE_NOT_PASS = "BASELINE-NOT-PASS"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNRECORDED = "UNRECORDED"


#: Outcomes a gate may block on. The other three are not findings about the
#: body: two are about the recording, one is about its absence.
BLOCKING = frozenset({Outcome.RED_WITHOUT_ASSERTION, Outcome.NEVER_RED})

#: Search order. PERTURB first because it is the poison most likely to reach an
#: assertion (the device answered, plausibly, wrongly); SILENCE last because on
#: raw-`cmd` bodies it is guaranteed to produce an ACCIDENT and would otherwise
#: dominate the evidence.
ORDER = ((Poison.PERTURB, Extent.AT), (Poison.PERTURB, Extent.ONWARD),
         (Poison.DROP, Extent.AT), (Poison.DROP, Extent.ONWARD),
         (Poison.REFUSE, Extent.AT), (Poison.REFUSE, Extent.ONWARD),
         (Poison.SILENCE, Extent.AT), (Poison.SILENCE, Extent.ONWARD))


# ── poisons ──────────────────────────────────────────────────────────────────

def perturb_value(v):
    """A value of the same JSON type that is not `v`. Deterministic."""
    if isinstance(v, bool):
        return not v
    if isinstance(v, int):
        return v + 1
    if isinstance(v, float):
        return v + 1.0
    if isinstance(v, str):
        return v + "~"
    if v is None:
        return "~"
    if isinstance(v, list):
        return [] if v else ["~"]
    if isinstance(v, dict):
        return {} if v else {"~": "~"}
    return "~"


def poison_reply(obj: dict, poison: Poison) -> dict:
    """The poisoned form of one decoded JSON reply. PERTURB/DROP/REFUSE only —
    SILENCE is not a rewrite of a reply, it is the absence of one."""
    if poison is Poison.PERTURB:
        return {k: (v if k in FRAMING else perturb_value(v)) for k, v in obj.items()}
    if poison is Poison.DROP:
        return {k: v for k, v in obj.items() if k in FRAMING}
    if poison is Poison.REFUSE:
        out = {"ok": False, "err": "poisoned"}
        for k in ("var", "cmd", "last"):
            if k in obj:
                out[k] = obj[k]
        return out
    raise ValueError(poison)


def poison_transcript(t: RP.Transcript, poison: Poison, extent: Extent,
                      k: int) -> RP.Transcript:
    """A COPY of `t` with exchange position `k` (AT) or positions `>= k`
    (ONWARD) poisoned. Positions are record order; the keyed store is unchanged,
    so a body that branches elsewhere still misses exactly as it should."""
    out = RP.Transcript(t.tid, t.elf, t.build_env, t.recorded_at, t.gen)
    out.preamble = list(t.preamble)
    for pos, ((cmd, nth), lines) in enumerate(t.exchanges.items()):
        hit = (pos == k) if extent is Extent.AT else (pos >= k)
        if not hit:
            out.exchanges[(cmd, nth)] = list(lines)
            continue
        if poison is Poison.SILENCE:
            out.exchanges[(cmd, nth)] = []
            continue
        new = []
        for ln in lines:
            s = (ln or "").strip()
            if s.startswith("{"):
                try:
                    obj = json.loads(s)
                except (ValueError, json.JSONDecodeError):
                    new.append(ln)
                    continue
                if isinstance(obj, dict):
                    new.append(json.dumps(poison_reply(copy.deepcopy(obj), poison)))
                    continue
            new.append(ln)
        out.exchanges[(cmd, nth)] = new
    return out


# ── grading ──────────────────────────────────────────────────────────────────

class _FailWitness:
    """Records, for every FAIL verdict written during one replay, whether it
    came through `results.flake` (POLICY) or not. Hooks the results STORE's
    single choke point (`RESULTS.set_typed`) rather than rebinding `fail`:
    suite modules import `fail` by name (`from lib.results import fail`), so a
    rebound `results.fail` never sees their calls — measured on the first real
    recording, where 119 bodies graded zero assertions. The store is the one
    place every verdict passes, however the recorder was imported."""

    def __init__(self):
        self.calls: list = []       # [(tid, from_flake: bool)]
        self._orig = None

    def __enter__(self):
        store = R.RESULTS
        orig = store.set_typed
        self._orig = orig
        witness = self

        def set_typed(tid, verdict, record):
            if verdict is R.Verdict.FAIL:
                from_flake = False
                f = sys._getframe(1)
                while f is not None:
                    if (f.f_code.co_name == "flake"
                            and f.f_globals.get("__name__", "").endswith("results")):
                        from_flake = True
                        break
                    f = f.f_back
                witness.calls.append((tid, from_flake))
            return orig(tid, verdict, record)

        store.set_typed = set_typed
        return self

    def __exit__(self, *exc):
        try:
            del R.RESULTS.set_typed          # instance attr; class method resumes
        except AttributeError:
            pass
        return False


def _grade(arm, witness: _FailWitness, tid: str):
    """The grade of the FAIL a replay recorded for `tid`, or None if the last
    fail() was for another id (bodies occasionally record for helpers' ids)."""
    if arm in (_dispatch.Arm.TIMEOUT, _dispatch.Arm.EXCEPTION):
        return Grade.ACCIDENT
    if arm is _dispatch.Arm.BAD_FIELD:
        return Grade.CONTRACT
    mine = [fl for (t, fl) in witness.calls if t == tid]
    if not mine:
        return None
    return Grade.POLICY if mine[-1] else Grade.ASSERTION


# ── the sweep ────────────────────────────────────────────────────────────────

class Evidence:
    __slots__ = ("poison", "extent", "k", "cmd", "grade", "record")

    def __init__(self, poison, extent, k, cmd, grade, record):
        self.poison, self.extent, self.k = poison, extent, k
        self.cmd, self.grade, self.record = cmd, grade, record

    def __str__(self):
        return (f"{self.poison.value}/{self.extent.value} @{self.k} "
                f"`{self.cmd}` -> {self.grade.value}: {self.record[:90]}")


class Sweep:
    """The result of `sweep()` for one id."""

    __slots__ = ("tid", "outcome", "evidence", "detail", "n_exchanges",
                 "replays", "misses", "grades", "baseline", "wall_s")

    def __init__(self, tid, outcome, detail="", evidence=None, n_exchanges=0,
                 replays=0, misses=0, grades=None, baseline=None, wall_s=0.0):
        self.tid, self.outcome, self.detail = tid, outcome, detail
        self.evidence, self.n_exchanges = evidence, n_exchanges
        self.replays, self.misses = replays, misses
        self.grades = grades or {g: 0 for g in Grade}
        self.baseline, self.wall_s = baseline, wall_s

    def line(self) -> str:
        head = f"  {self.tid:14s} {self.outcome.value:18s}"
        if self.outcome is Outcome.RED:
            return f"{head} {self.evidence}  [{self.replays} replays]"
        tail = (f"  [{self.replays} replays, {self.misses} misses, "
                f"contract={self.grades[Grade.CONTRACT]} "
                f"accident={self.grades[Grade.ACCIDENT]} "
                f"policy={self.grades[Grade.POLICY]}]")
        return f"{head} {self.detail}{tail}"


def _wrapped(tid, body, arm_box):
    def run(dut):
        arm_box[0] = _dispatch.run_body(tid, body, dut)
    return run


def sweep(tid: str, body, transcript: RP.Transcript, *,
          order=ORDER, max_positions: int = 400, quiet: bool = True) -> Sweep:
    """Search for a reply sequence under which `body` records an ASSERTION FAIL.

    `body` is the registered test body (one `dut` argument). `transcript` is a
    recording of it — from hardware via `replay.recording`, or from a scripted
    device in a negative suite; the engine does not care which.

    `max_positions` bounds the sweep on a pathological recording (a poll loop
    that recorded thousands of exchanges). Positions past it are not poisoned
    AT; ONWARD from the last position inside the bound still covers them.
    `quiet` swallows the `[PASS]`/`[FAIL]` lines the results layer prints per
    verdict — a sweep records hundreds of them and none is a run.
    """
    if quiet:
        with contextlib.redirect_stdout(io.StringIO()):
            return sweep(tid, body, transcript, order=order,
                         max_positions=max_positions, quiet=False)
    t0 = _time_mod.monotonic()
    n = len(transcript.exchanges)
    arm_box = [None]
    run = _wrapped(tid, body, arm_box)

    # 1. Baseline: the recording must be a healthy path for THIS body.
    with _FailWitness():
        base = RP.replay_test(tid, run, transcript, elf_check=False,
                              probe_time=True)
    if base.status is not RP.Status.OK:
        return Sweep(tid, Outcome.INCONCLUSIVE,
                     f"baseline {base.reason.value}: {base.detail}",
                     n_exchanges=n, replays=1, baseline=base,
                     wall_s=_time_mod.monotonic() - t0)
    if base.verdict is not R.Verdict.PASS:
        return Sweep(tid, Outcome.BASELINE_NOT_PASS,
                     f"unmutated replay records {base.verdict.value}, not PASS — "
                     f"the recording is not a healthy path; re-record",
                     n_exchanges=n, replays=1, baseline=base,
                     wall_s=_time_mod.monotonic() - t0)

    # 2. The search.
    positions = list(transcript.exchanges)
    grades = {g: 0 for g in Grade}
    replays, misses = 1, 0
    limit = min(n, max_positions)
    for poison, extent in order:
        for k in range(limit):
            mutated = poison_transcript(transcript, poison, extent, k)
            arm_box[0] = None
            with _FailWitness() as w:
                res = RP.replay_test(tid, run, mutated, elf_check=False,
                                     probe_time=False)
            replays += 1
            if res.status is not RP.Status.OK:
                if res.reason is RP.Reason.TRANSCRIPT_MISS:
                    misses += 1
                continue
            if res.verdict is not R.Verdict.FAIL:
                continue
            g = _grade(arm_box[0], w, tid)
            if g is None:
                continue
            grades[g] += 1
            if g is Grade.ASSERTION:
                ev = Evidence(poison, extent, k, positions[k][0], g, res.record)
                return Sweep(tid, Outcome.RED, evidence=ev, n_exchanges=n,
                             replays=replays, misses=misses, grades=grades,
                             baseline=base, wall_s=_time_mod.monotonic() - t0)

    seen = [g.value for g in (Grade.CONTRACT, Grade.ACCIDENT, Grade.POLICY)
            if grades[g]]
    if seen:
        out, why = Outcome.RED_WITHOUT_ASSERTION, (
            f"red only through {'/'.join(seen)}: the cell can be red, but the "
            f"body never asserts anything about its subject to make it so")
    else:
        out, why = Outcome.NEVER_RED, (
            f"{len(order)} poisons x {limit} positions left the body green or "
            f"unmet every time")
    return Sweep(tid, out, why, n_exchanges=n, replays=replays, misses=misses,
                 grades=grades, baseline=base, wall_s=_time_mod.monotonic() - t0)
