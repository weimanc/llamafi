"""lib/falsify_ops.py — mutation operators for the TASK-641/642/643 falsifier
record's `THRESHOLD` and `SUBSTRING` shapes (M-HARNESS2 §3, TASK-714).

WHY THIS IS A SEPARATE MODULE, NOT MORE FUNCTIONS IN `lib/canfail.py`.
`canfail.py`'s `perturb_value`/`poison_reply`/`poison_transcript` are the R34
sweep's shared poison — two blocking gates consume that exact sweep and its
counts are a ratchet:

  * `gate/check_can_go_red.py` — currently 129 of 196 RED against a 6-row
    ledger.
  * `gate/check_restore_manager.py`'s TASK-673 runtime arm — currently 14
    ledgered vars, over the same replays.

Widening `perturb_value` (or adding a new `Poison` member it would have to
dispatch through) to reach the two claim shapes this file exists for would
move both of those numbers as a side effect of a falsifier-record change,
which has nothing to do with either gate. TASK-641/642/643 is a DIFFERENT
question — "what would confirm this id's declared oracle" — answered by a
DIFFERENT, future driver (TASK-643, not built), and it gets its own operators.

THE TWO GAPS MEASURED (docs/architecture/designs/M-HARNESS2-falsifier-
taxonomy.md §3, TASK-714 amendment; also `suite/serialdbg/clock.py`'s comment
above `t_clk_11` before this task, and `suite/serialdbg/player.py`'s comment
above `t_plr_12`):

  1. NUMERIC THRESHOLD. `T_CLK_11` fails iff `h0 - h1 >= 4096`, a derived
     delta between two `info.heap` reads. `SNAPSHOT`'s operator moves an int
     by exactly `+1` — nowhere near a 4096 B floor. `TRANSITION`'s operator
     freezes the after-read to the before value, forcing the delta to exactly
     0 — the tightest possible PASS, the opposite of falsification. No shape
     in the enum could move a bounded delta past its own bound, because none
     of them is TOLD the bound.
  2. PREFIX/CONTAINMENT STRINGS. `T_PLR_08`/`T_PLR_10`/`T_PLR_11` check
     `.startswith(...)` and `x in y` against string reads. `perturb_value`'s
     append-`"~"` survives both: `"./music/track.mp3~".startswith("./")` is
     still `True`, and `"(120)" in "Title (120)~"` is still `True` — verified
     by hand before writing this module. `SNAPSHOT` needs a string operator
     that actually changes every substring, not one that only changes
     equality.

THE THIRD GAP — `.ok`-ONLY CHECKS — HAS NO OPERATOR HERE, ON PURPOSE. `ok` is
in `canfail.FRAMING` and `poison_reply` never touches it, deliberately:
poisoning `ok` would turn every exchange into a REFUSE, indistinguishable from
the poison that already exists for that. A body whose only assertion is
"the reply says ok" cannot be falsified by data mutation at all — the failure
mode is a `RefuseAll` transport-level condition, not a reply-field mutation,
and it is out of scope for a `Transcript.mutate`-shaped operator by
construction. Documented as a known, deliberate non-target (§3's own table
amendment) so nobody re-derives it as a missing shape.

BOTH OPERATORS ARE PLAIN VALUE FUNCTIONS, THE SAME SHAPE AS
`canfail.perturb_value` — deterministic (same input, same output), so a
sweep or driver replaying them twice gets the same poisoned transcript both
times. They do not touch `lib.replay.Transcript` themselves; `mutate_field()`
below is a thin wrapper over `Transcript.mutate()` (already built in
`lib/replay.py`, whose own docstring calls it "the primitive TASK-643 drives;
NOT the driver") — picking WHICH key/occurrence to mutate is this file's job,
same as `canfail.poison_transcript` picks positions for the R34 sweep, but
using the generic primitive instead of `canfail`'s AT/ONWARD position search
(which exists to answer a different question — "does ANY position make this
body go red" — that TASK-643's driver does not ask; it mutates the exact
declared oracle key).

Depends downward only: `lib.replay`. Never imports `lib.canfail`, a suite, or
a gate — a future TASK-643 driver imports THIS, not the other way round.
"""

from __future__ import annotations

from . import replay as RP

#: Printable ASCII range `scramble_string` rotates within — chosen because
#: every corpus string this shape declares against (file paths, playlist row
#: text, UTF-8-folded titles) lives there; see the module docstring for the
#: measurement that motivated it.
_PRINTABLE_LO = 0x20
_PRINTABLE_HI = 0x7E
_PRINTABLE_SPAN = _PRINTABLE_HI - _PRINTABLE_LO + 1     # 95


def perturb_threshold(v, bound):
    """The `THRESHOLD` shape's operator: `v` moved DOWN by more than `bound`.

    Every `THRESHOLD` instance measured in the corpus (`T_CLK_11`'s heap-cycle
    leak, `T_PLR_12`'s `d_load`/`d_free`) is a check of the shape
    `earlier_reading - later_reading [> or abs(...) >] bound`, applied to the
    LATER occurrence of the oracle key (the driver's job, via `mutate_field`
    below, is choosing that occurrence — same division of labour as
    `canfail`'s `Extent.AT` choosing which of two reads of one key to touch).
    Decreasing that later reading by more than `bound` INCREASES the delta by
    the same amount, past the bound, regardless of the delta's original sign
    or magnitude — a single direction is therefore enough for every measured
    instance. See the module docstring's amendment note: the opposite polarity
    (a claim that fails when a reading grows too much, e.g.
    `later - earlier > bound`) is not observed anywhere in today's corpus and
    is a named, undecided case, not silently assumed to work.

    Deterministic and type-checked the same way `canfail.perturb_value`
    dispatches on type — but raising, not falling back to a string tag, on a
    type the shape does not apply to: a `THRESHOLD` key that is not numeric is
    a bad declaration, and this operator should say so loudly rather than
    silently emitting an `f"{v}~"` that would falsify nothing.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise TypeError(
            f"THRESHOLD operator applies to a numeric field, got "
            f"{type(v).__name__}: {v!r}")
    if isinstance(bound, bool) or not isinstance(bound, (int, float)) or bound <= 0:
        raise ValueError(f"bound must be a positive number, got {bound!r}")
    step = bound + (1 if isinstance(bound, int) else 1.0)
    return v - step


def scramble_string(v):
    """The `SUBSTRING` shape's operator: every character of `v` replaced by a
    deterministic cyclic shift, so no nonempty substring of the original
    survives unchanged — unlike `canfail.perturb_value`'s `v + "~"`, which
    changes nothing before the appended character and therefore preserves
    every prefix and every substring that does not include the tail.

    Printable ASCII (0x20-0x7E) rotates by one position within that 95-symbol
    range (`'A' -> 'B'`, `'~' -> ' '`, wrapping); anything outside it (the
    UTF-8-folded `'?'` placeholders are themselves plain ASCII, so this is only
    reached by an oracle string with real non-ASCII content) shifts by one
    Unicode code point modulo the whole codepoint space. Both are fixed-point-
    free permutations (shifting by exactly 1 within a cycle never maps a
    symbol to itself), which is the property this operator needs: a needle
    that is a single repeated character would otherwise survive if the shift
    happened to be a multiple of the alphabet it lives in — not possible here
    since the shift is always exactly 1.

    A degenerate check against the EMPTY string (`"" in y` or `y.startswith("")`,
    always `True` for any `y`) cannot be falsified by any operator, including
    this one — not a corpus instance today, called out here so it is not
    "discovered" again as a bug in this function.
    """
    if not isinstance(v, str):
        raise TypeError(
            f"SUBSTRING operator applies to a string field, got "
            f"{type(v).__name__}: {v!r}")
    out = []
    for ch in v:
        cp = ord(ch)
        if _PRINTABLE_LO <= cp <= _PRINTABLE_HI:
            out.append(chr(_PRINTABLE_LO + (cp - _PRINTABLE_LO + 1) % _PRINTABLE_SPAN))
        else:
            out.append(chr((cp + 1) % 0x110000))
    return "".join(out)


def by_var(name: str, nth: int = None):
    """A `mutate_field` `match` — the exchange is a `get`/`set` reply naming
    `var == name`, optionally restricted to occurrence `nth` (record order,
    same numbering as `Transcript.exchanges`' `(cmd, nth)` keys)."""
    def match(cmd, n, obj):
        return obj.get("var") == name and (nth is None or n == nth)
    return match


def by_cmd(name: str, nth: int = None):
    """A `mutate_field` `match` for a reply with no `var` (a raw `cmd`, e.g.
    `info`) — matches `cmd == name`, optionally restricted to `nth`."""
    def match(cmd, n, obj):
        return obj.get("cmd") == name and (nth is None or n == nth)
    return match


def mutate_field(transcript: "RP.Transcript", match, field: str, op, *op_args):
    """A COPY of `transcript` with `field` rewritten by `op(old, *op_args)` on
    every exchange `match(cmd, nth, obj)` selects and that actually carries
    `field`. Thin wrapper over `Transcript.mutate()` (`lib/replay.py`) — the
    generic primitive that module's own docstring reserves for exactly this:
    "the primitive TASK-643 drives; NOT the driver. Choosing WHICH key to
    mutate is a claim about the test's vocabulary and belongs to TASK-641/642's
    falsifier declaration, not here." `by_var`/`by_cmd` above build `match`;
    `op` is `perturb_threshold` or `scramble_string`.
    """
    def pred(cmd, nth, obj):
        return field in obj and match(cmd, nth, obj)

    def fn(obj):
        obj[field] = op(obj[field], *op_args)
        return obj

    return transcript.mutate(pred, fn)
