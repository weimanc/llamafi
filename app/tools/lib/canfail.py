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

── THE RESTORE-EVIDENCE BYPRODUCT (TASK-673, R17's runtime arm) ──────────────

`check_restore_manager.py`'s static gate credits a mutation only when it sits
lexically inside `with dut.saved(...)`/`dut.injected(...)`; it cannot see a
restore that is only reachable on the FAIL path, a `with` whose exit raised and
was swallowed, or a restore of the wrong variable at runtime. `sweep()` already
drives every poisoned replay that can reach a FAIL/UNMET verdict — this is a
read over that same execution, not a second engine (M-HARNESS2 §4's rule for
every arm in this family).

`_RestoreWitness` patches the SAME two choke points `_FailWitness` already
uses for grading (`StubTransport.write`, so it sees a command whether or not it
hits the transcript; `RESULTS.set_typed`, the one place every verdict is
written) and is armed for every replay the search loop already performs — no
extra replay calls. For each such run that reaches a FAIL/UNMET verdict,
`_restore_leaks()` reads the command log:

  * a `set VAR ...` that was ACKED (the only way one can appear before the
    verdict at all — a MISS there aborts the body before any verdict, voiding
    the row before this code ever runs) at some position before the verdict
    is a MUTATION on this path;

  SECOND CORRECTION — "hit the transcript" is NOT "the device acked", AND
  EACH OF THE FOUR POISONS WAS CHECKED AGAINST THE MUTATING `set`'S OWN REPLY,
  DELIBERATELY, NOT LEFT TO BE DISCOVERED:

    * REFUSE rewrites the reply to `{"ok": false, ...}` (`poison_reply`). The
      write still hits the transcript (no `TranscriptMiss`), but the device
      DECLINED — `set_val` raises `BadField`, the `with` body (and its
      restore) never runs, and NOTHING was mutated. Measured on the live
      corpus: `T-BUSY-01b`'s properly `dut.saved(...)`-managed `bgPoll` write,
      REFUSE-poisoned, was reported as `NO_RESTORE_ATTEMPTED` under the first
      draft — a false positive, the same shape as `T-CDWN-02`'s.
      `_replied_ok()` reads the REPLY, not "did the lookup succeed", and
      closes it: `acked` is `False` for a `TranscriptMiss` AND for an
      answered-but-refused `set`, because both mean the same thing here —
      nothing was mutated (or restored) on this path.
    * PERTURB and DROP are BOTH SAFE on a `set`'s own reply, checked, not
      assumed: `ok` is a `FRAMING` field, and `poison_reply` preserves every
      `FRAMING` field verbatim under both poisons (PERTURB perturbs only
      non-framing fields; DROP keeps only framing ones). A `set` ack's reply
      is normally framing-only (`{"ok":true,"cmd":"set","var":"X"}`), so
      neither poison has anything to touch — the ack survives untouched, and
      the mutation genuinely happened.
    * SILENCE leaves NO reply lines for the exchange at all. `_replied_ok([])`
      is `False` — correctly not an ack — even though `StubTransport.write`
      itself does not raise (a SILENCE-poisoned exchange is still a recorded
      entry, just with an empty line list); the caller's own read then times
      out (`NoAnswer`/`TimeoutError`, depending on the accessor), which is a
      SEPARATE reason nothing was mutated, reaching the same `acked=False`.
  * for each mutated var, ANY later `set VAR ...` ANYWHERE in the whole log —
    before the verdict too, not only after it, see the correction below — is a
    SET-BACK ATTEMPT, whether or not it hit the transcript. No later `set VAR`
    at all -> `NO_RESTORE_ATTEMPTED`, R17's C-15 shape and the only kind
    `check_restore_manager.py`'s runtime arm reports as a finding. A later one
    that never acked -> `RESTORE_ATTEMPTED_UNRECORDED`: the recording cannot
    answer for it (a healthy run rarely walks the same tail as a poisoned one —
    `lib/replay.py`'s "miss AFTER does not void" note says this at length), and
    it is evidence of nothing. Reported, tagged, never folded into either
    "clean" or "leak".

  CORRECTION FROM THE FIRST DRAFT, KEPT HERE ON PURPOSE. "attempted after the
  verdict" (not "anywhere later") was the original rule, and it produces a real
  false positive: `T-CDWN-02`'s `shellBusy` mutation is properly
  `with dut.injected(...)`-managed, but the manager's restore fires the instant
  the `with` block exits — in that body, BEFORE the later `fail()` that reads
  the tap reply's shape, not after it. A verdict-relative split flags a clean,
  manager-protected mutation as a leak. `_restore_leaks()` in this file checks
  for a later occurrence ANYWHERE in the log instead — see its docstring.

Restore evidence accumulates in `Sweep.restore_leaks` across every replay the
search performs before it stops (all of them, for `NEVER_RED`/
`RED_WITHOUT_ASSERTION`; up to and including the winning one, for `RED`).

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


# ── restore evidence (TASK-673) ─────────────────────────────────────────────

_SET_VAR_RE = __import__("re").compile(r"^\s*set\s+([A-Za-z_][A-Za-z0-9_]*)\b")


class RestoreLeak:
    """One (var, path) finding read off a single poisoned replay's command log.

    `kind` is `NO_RESTORE_ATTEMPTED` (a real finding: nothing ever set `var`
    back once the verdict was FAIL/UNMET) or `RESTORE_ATTEMPTED_UNRECORDED`
    (a set-back WAS attempted but the healthy recording cannot answer for it —
    not a finding, see the module docstring's trap warning)."""

    __slots__ = ("var", "poison", "extent", "k", "cmd", "verdict", "kind")

    def __init__(self, var, poison, extent, k, cmd, verdict, kind):
        self.var, self.poison, self.extent, self.k = var, poison, extent, k
        self.cmd, self.verdict, self.kind = cmd, verdict, kind

    def __str__(self):
        return (f"{self.poison.value}/{self.extent.value} @{self.k} "
                f"`{self.cmd}` (verdict {self.verdict.value}) -> {self.kind}")


def _replied_ok(lines) -> bool:
    """True iff at least one recorded reply LINE for an exchange is a JSON
    object carrying `"ok": true`. `[]` (SILENCE — no reply at all) and a reply
    with no valid JSON object (a poison that mangled the line, or a
    non-JSON debug line with no JSON line among them) are both False — a
    command the device never actually acknowledged, same as an explicit
    `ok:false` refusal.

    This is the fix for the TASK-673 review defect: "the recording had an
    answer for this command" (does `write()` raise `TranscriptMiss`?) and "the
    device ACKED it" (does the reply say `ok:true`?) are different questions,
    and `poison_reply`'s REFUSE branch — `{"ok": false, "err": "poisoned", ...}`
    — is specifically a case where the FIRST is true and the SECOND is false.
    A REFUSE on a mutating `set` still hits the transcript (no `TranscriptMiss`)
    but the reply says the device declined, so `set_val` raises `BadField` and
    nothing was ever mutated. Conflating the two flagged `T-BUSY-01b`'s
    properly `dut.saved(...)`-managed `bgPoll` write as a leak — the REFUSE
    poison aborted `_bgpoll_suspended` before its `with` body (and its
    restore) ever ran, so there was nothing to leak in the first place."""
    for ln in lines:
        s = (ln or "").strip()
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict) and obj.get("ok") is True:
            return True
    return False


class _RestoreWitness:
    """Records, for ONE replay: every command `StubTransport.write()` saw, in
    record order, as `(cmd, acked)` — and the position in that log (`log`
    index) of the first `RESULTS.set_typed()` write for `tid` that recorded
    FAIL or UNMET. See the module docstring for why both choke points, and
    what a `None` `verdict_at` means (the run never reached FAIL/UNMET).

    `acked` is NOT "the write hit the transcript" — a command's reply text is
    read back (via the SAME `Transcript.get()` the stub itself just used, so
    this reads the ALREADY-POISONED reply, not the healthy one) and `acked` is
    true only if that reply is a JSON object saying `ok:true` (`_replied_ok`).
    A `TranscriptMiss` is `acked=False` (never answered at all); a REFUSE
    poison's `{"ok":false,...}` is ALSO `acked=False` (answered, and declined)
    — both mean "nothing was mutated/restored here", which is the only
    distinction `_restore_leaks()` needs. See `_replied_ok`'s docstring for
    the regression this closes (`T-BUSY-01b`)."""

    def __init__(self, tid):
        self.tid = tid
        self.log: list = []
        self.verdict_at = None
        self.verdict = None
        self._orig_write = None
        self._orig_set_typed = None

    def __enter__(self):
        self._orig_write = RP.StubTransport.write
        self._orig_set_typed = R.RESULTS.set_typed
        me = self

        def write(this, b):
            cmd = b.decode(errors="replace").strip()
            try:
                n = me._orig_write(this, b)
            except RP.TranscriptMiss:
                me.log.append((cmd, False))
                raise
            # The write succeeded — the (possibly poisoned) transcript HAD an
            # exchange for this (cmd, nth). `_orig_write` already incremented
            # `this.seen[cmd]`; look the SAME exchange back up (a second read
            # of an immutable store, not a second dispatch) to read what it
            # actually replied, poisoning included.
            nth = this.seen[cmd] - 1
            try:
                lines = this.t.get(cmd, nth)
            except RP.TranscriptMiss:
                lines = []            # unreachable in practice; fail safe
            me.log.append((cmd, _replied_ok(lines)))
            return n

        def set_typed(tid, verdict, record):
            if (me.verdict_at is None and tid == me.tid
                    and verdict in (R.Verdict.FAIL, R.Verdict.UNMET)):
                me.verdict_at = len(me.log)
                me.verdict = verdict
            return me._orig_set_typed(tid, verdict, record)

        RP.StubTransport.write = write
        R.RESULTS.set_typed = set_typed
        return self

    def __exit__(self, *exc):
        RP.StubTransport.write = self._orig_write
        try:
            del R.RESULTS.set_typed          # instance attr; class method resumes
        except AttributeError:
            pass
        return False


def _restore_leaks(poison, extent, k, w: _RestoreWitness) -> list:
    """-> [RestoreLeak], read off one witnessed replay that reached FAIL/UNMET.

    `[]` if `w.verdict_at is None` (the run never reached a verdict this arm
    cares about) — including every run that stayed PASS/SKIP under poison.

    THE RULE, and why it is NOT "before the verdict" vs "after it" (that was
    the first draft, and it produces a real false positive: measured on
    `T-CDWN-02`, whose `shellBusy` mutation is properly `with dut.injected(...)`
    -managed — the manager's restore fires the instant the `with` block exits,
    which in that body is BEFORE the later `fail()` that reads the tap's reply
    shape, not after it. A strict verdict-relative split flags a clean,
    manager-protected mutation as a leak.).

    The actual question is not "did the set-back happen before or after the
    verdict was written" — a body's own control flow decides that incidentally
    — it is "did ANY set-back get attempted at all, anywhere later in the run,
    once the var was mutated for this path". So: a var counts as MUTATED on
    this path if it has an ACKED `set VAR ...` at some position before the
    verdict (the only way one can appear there at all — see the module
    docstring on why a miss there voids the row before this code runs). Given
    that first mutating position, look at EVERY later `set VAR ...` in the
    WHOLE log — before the verdict too (a manager's restore that runs promptly,
    still inside the same `with` block, counts) or after it (the common shape,
    a branch-specific restore call) — whether or not it hit the transcript:

      * at least one later occurrence -> a set-back was ATTEMPTED. Not a
        finding, regardless of whether it was acked (see the next kind).
      * a later occurrence exists but NONE of them acked -> `RESTORE_
        ATTEMPTED_UNRECORDED`: attempted, but every attempt either missed the
        transcript or was explicitly refused (`_replied_ok` treats both as
        `acked=False` — see its docstring). Not a finding (see the module
        docstring's trap warning).
      * no later occurrence at all -> `NO_RESTORE_ATTEMPTED`: nothing ever
        touched this var again on this path. R17's C-15 shape, and the only
        kind this reports as a finding.

    `acked`, EVERYWHERE ABOVE, MEANS THE REPLY SAID `ok:true` — NOT "the
    lookup found an exchange". Those differ exactly where a poison lives: a
    REFUSE-poisoned `set` hits the transcript (no `TranscriptMiss`) but its
    reply is `{"ok":false,...}`, and `set_val` raises on it, so nothing was
    mutated at all. The first draft of this function used "did the write
    raise" as `ok`, and it produced a real false positive — `T-BUSY-01b`'s
    `bgPoll` write is `dut.saved(...)`-managed (`_bgpoll_suspended`), and a
    REFUSE poison on it aborts `_bgpoll_suspended` before its `with` body (and
    its restore) ever runs, so there is nothing to leak; the old rule reported
    one anyway. `_replied_ok()` (this module) reads the actual reply instead.

    A KNOWN LOWER BOUND, NOT CLOSED HERE. "ANY later `set VAR`" credits a
    second, unrelated mutation of the SAME var as if it were a restore. A body
    that mutates `wrStop` (or `wrDeadUrls`, `prPollSec`, `wrAutoSkip`,
    `wrHwMod`, `wrMaxVol`, `wrPlay`, `spotifyWedge` — all measured with
    repeated same-var `set`s inside one id in the live corpus) three times and
    never actually restores it would be cleared by this rule: the second and
    third `set` each count as "a later occurrence", whether or not either one
    puts the ORIGINAL value back. `T_WR_VOL_CLAMP`'s repeated `wrMaxVol` writes
    were checked by hand and its `finally:` genuinely restores the stock
    default `10` — not a leak — but that was verified by reading the body, not
    by this arm, and the arm would have cleared a real repeat-mutation leak on
    the same shape identically. Closing this needs a VALUE-aware comparison —
    the eventual state against the pre-mutation snapshot, not merely "was the
    var touched again" — which this function does not attempt. Every count
    this module and its caller report is a lower bound for exactly this
    reason, stated wherever the count is presented.
    """
    if w.verdict_at is None:
        return []
    occurrences: dict = {}
    for idx, (cmd, ok) in enumerate(w.log):
        m = _SET_VAR_RE.match(cmd)
        if m:
            occurrences.setdefault(m.group(1), []).append((idx, ok, cmd))
    out = []
    for var, occ in occurrences.items():
        before = [o for o in occ if o[0] < w.verdict_at and o[1]]
        if not before:
            continue                       # never successfully mutated pre-verdict
        first_idx, _ok, first_cmd = before[0]
        later = [o for o in occ if o[0] > first_idx]
        if not later:
            out.append(RestoreLeak(var, poison, extent, k, first_cmd, w.verdict,
                                   "NO_RESTORE_ATTEMPTED"))
        elif not any(o[1] for o in later):
            out.append(RestoreLeak(var, poison, extent, k, first_cmd, w.verdict,
                                   "RESTORE_ATTEMPTED_UNRECORDED"))
        # else: a later set-back exists (acked) — clean, not reported.
    return out


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
                 "replays", "misses", "grades", "baseline", "wall_s",
                 "restore_leaks")

    def __init__(self, tid, outcome, detail="", evidence=None, n_exchanges=0,
                 replays=0, misses=0, grades=None, baseline=None, wall_s=0.0,
                 restore_leaks=None):
        self.tid, self.outcome, self.detail = tid, outcome, detail
        self.evidence, self.n_exchanges = evidence, n_exchanges
        self.replays, self.misses = replays, misses
        self.grades = grades or {g: 0 for g in Grade}
        self.baseline, self.wall_s = baseline, wall_s
        #: [RestoreLeak], TASK-673 — every restore-evidence finding observed
        #: across the replays this sweep actually performed. `[]` unless a
        #: FAIL/UNMET path was reached; see `_restore_leaks()`.
        self.restore_leaks = restore_leaks if restore_leaks is not None else []

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
    restore_leaks: list = []
    replays, misses = 1, 0
    limit = min(n, max_positions)
    for poison, extent in order:
        for k in range(limit):
            mutated = poison_transcript(transcript, poison, extent, k)
            arm_box[0] = None
            with _FailWitness() as w, _RestoreWitness(tid) as rw:
                res = RP.replay_test(tid, run, mutated, elf_check=False,
                                     probe_time=False)
            replays += 1
            # TASK-673: restore evidence is read off EVERY replay that reached
            # a FAIL/UNMET verdict, regardless of grade — a FAIL-without-
            # assertion path and an UNMET path both leave the device in
            # whatever state the body's own logic left it in, same as a real
            # FAIL does. This does not consume `res`/`grades`; it is a pure
            # read alongside the grading below.
            restore_leaks.extend(_restore_leaks(poison, extent, k, rw))
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
                             baseline=base, wall_s=_time_mod.monotonic() - t0,
                             restore_leaks=restore_leaks)

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
                 restore_leaks=restore_leaks,
                 grades=grades, baseline=base, wall_s=_time_mod.monotonic() - t0)
