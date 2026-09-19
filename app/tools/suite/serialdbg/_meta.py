"""suite/serialdbg/_meta.py — the test record: (cls, scope, effect). TASK-570.

WHY THIS EXISTS. Three separate questions were being answered by reading 10 000
lines of suite source, or not answered at all:

  cls    RIG | HEALTH | CORE | APP | FEATURE     gating precedence   (M-TESTARCH §3)
  scope  an APP_ORDER name, or one of
         shell|boot|taskbar|spotify-chrome|rig   selection           (M-TESTARCH §13)
  effect read-only | mutating | resetting        triage admissibility(M-TESTARCH §16.3)

All three land in ONE pass (design §13.3/§16.7): deciding one now and
retrofitting the others later pays the migration cost twice.

THE CARRIER IS A FUNCTION ATTRIBUTE, NOT A WRAPPED REGISTRY VALUE (design §13.3).
`TESTS` stays `dict[str, callable]`, byte-identical entry text, because
`gate/check_player_binding.py:200` regexes the literal registry entry
`"T_PMT_00"\\s*:\\s*t_pmt_00` as a BLOCKING gate — wrapping the value would red
`run/check`. A decorator sets `fn._meta` and nothing else moves.

SEED, THEN DECLARE (design §13.3). The seed is a DEFAULT, the declaration
OVERRIDES it — not an equality gate. An equality gate would reject the suite's
most deliberate placements on day one (`T_PMT_01..04` live in player.py but are
cross-mode cells), which teaches implementers to weaken the gate.

  * scope is SEEDED from the family module name (validated against APP_ORDER —
    never a typed table) and, inside shell.py, from the id prefix.
  * a declaration overrides its seed and MUST carry a one-word reason. The
    reason is what distinguishes a considered placement from a typo, and it is
    greppable.
  * an undecorated test defaults to (FEATURE, <seed or "unknown">, mutating) —
    conservative on all three axes: blocks nothing, selects into nothing,
    inadmissible in a descent.

`gate/check_test_meta.py` asserts the invariants and prints the census.
"""

from __future__ import annotations

import glob
import importlib
import inspect
import os
import re
import sys

from app_ids_gen import APP_ORDER, DISPLAY

# ---------------------------------------------------------------- the enums

CLASSES = ("RIG", "HEALTH", "CORE", "APP", "FEATURE")
EFFECTS = ("read-only", "mutating", "resetting")

# ---------------------------------------------------------- the ops vocabulary
#
# TASK-705. `ops` is a FOURTH, entirely OPT-IN axis — unlike cls/scope/effect
# it has no seed: an undeclared id carries no ops, and that is never a finding
# (`gate/check_primitive_coverage.py` reports the undeclared count but does not
# fail on it). It exists to answer a question scope/cls/effect cannot: not
# "which app" or "how disruptive", but "which PRIMITIVE OPERATION, out of a
# closed list, does this id's body actually exercise" — so a coverage gate can
# tell a real gap (an op nothing tests) from a hole nobody wrote down.
#
# Opened by the TASK-697 reboot/inject/Stock wedge investigation
# (docs/verification/regression_suite/task697-reboot-inject-stock.md), whose
# read-only coverage inventory named nine primitive operations along that
# composite's causal chain — a reboot, Spotify's backoff schedule and its
# token-refresh failure, dataTask's TLS yield hand-off (idle and busy), a
# PlaneRadar injection and its clear, dataTask's cross-app queue serialisation,
# and a Stock quote fetch. The vocabulary is CLOSED (a typo or a new op both
# fail loudly, `gate/check_primitive_coverage.py`'s P2) and grows only by
# adding a row here with its one-line definition.
OPS = {
    "reboot_ready":
        "the board reaches a ready, addressable state after an in-session "
        "reboot — the composite precondition every [REBOOT] id depends on.",
    "spotify_backoff":
        "spotifyTask's poll-interval schedule as a function of "
        "consecutiveFailures — nextWaitMs()'s doubling/cap formula "
        "(spotifyTaskStorage.cpp ~198-213), not merely the set/get round trip.",
    "spotify_token_refresh_fail":
        "a Spotify token refresh fails against a live TLS session (TASK-675's "
        "pin rot is today's live instance). NOT DRIVABLE today — cmdSet.cpp's "
        "certbreak table (~707-729) excludes spotifyTask.",
    "tls_yield_idle":
        "a dataTask fetcher's tlsYield()/tlsTryYield() request is acked by "
        "spotifyTask while spotifyTask is idle (no request armed to keep it "
        "busy) — the RING_YIELD_REQ -> RING_TLS_STOP_ACK edge, `get dataRing`.",
    "tls_yield_busy":
        "the same TLS yield hand-off while spotifyTask is made busy (`set "
        "spotifyWedge <ms>`, TASK-430) — the ack latency tracks the busy "
        "window instead of acking promptly. This is TASK-697's own shape.",
    "pr_inject":
        "PlaneRadar's synthetic-aircraft injection (`set prInjectAircraft`) "
        "and the offset decay/settle behaviour it drives.",
    "pr_clear_rearms_fetch":
        "`set prClearInject 1` does not merely clear the display — it "
        "backdates PlaneRadarApp's _lastFetch so tick()'s own poll gate fires "
        "a REAL fetch enqueue on a subsequent tick (planeRadarApp.cpp ~27-34, "
        "268-273).",
    "datatask_cross_app_queue":
        "dataTask's single shared request queue accepts a second app's fetch "
        "while a first app's fetch is still dispatched (inFlight) — the "
        "request is observed QUEUED (queueWaiting/pendingMask), not dropped or "
        "double-dispatched, and both complete after release.",
    "stock_quote_fetch":
        "a Stock quote fetch, once triggered, actually completes "
        "(quoteOkCount advances) within its bound.",
}

#: Tuple form, in definition order — what `meta(ops=...)` and the gate iterate.
OPS_ORDER = tuple(OPS)

# ------------------------------------------------- the falsifier vocabulary
#
# TASK-641 (docs/architecture/designs/M-HARNESS2-falsifier-taxonomy.md §2/§3/
# §7). Two more closed enums, on top of cls/scope/effect/ops:
#
#   ROLE  — of each key a body reads: ORACLE (the read the claim is about),
#           PREMISE (a precondition established before asserting), or the
#           default INCIDENTAL (read, but the verdict must not depend on it).
#           There is no ROLES tuple to validate against, because role is not
#           a value the author writes down — it is WHICH of `meta()`'s two
#           dicts a key is placed in. An undeclared key is INCIDENTAL by
#           construction (§2): that is deliberate, not a hole — a forgotten
#           oracle key is caught later by the control arm going FAIL
#           (OVER-DEPENDENT), not silently accepted.
#   SHAPE — declared per ORACLE key, fixes which mutation operator a future
#           driver (TASK-643, not built here) would use against it.
SHAPES = ("SNAPSHOT", "POLL", "TRANSITION", "EVENT", "ABSENCE", "PHYSICAL", "NONE")

#: scope values that are not an app. `spotify-chrome` is deliberately NOT
#: `spotify`: a case-only distinction against APP_ORDER's `Spotify` is a defect
#: in a CLI value (design §13.3) — one `.lower()` anywhere in a resolver and the
#: wrong set is silently selected. The gate rejects case-collisions outright.
NON_APP_SCOPES = ("shell", "boot", "taskbar", "spotify-chrome", "rig")

SCOPES = tuple(APP_ORDER) + NON_APP_SCOPES

#: what an id with no seed and no declaration resolves to.
UNKNOWN_SCOPE = "unknown"

DEFAULT_CLS = "FEATURE"
DEFAULT_EFFECT = "mutating"


# ------------------------------------------------------- the declaration API

def meta(cls: str = None, cls_reason: str = None,
         scope: str = None, scope_reason: str = None,
         effect: str = None, effect_reason: str = None,
         ops: tuple = None,
         oracle: dict = None, premise: "set | tuple" = None,
         falsifier: str = None):
    """Declare metadata on a test function. Everything is optional; whatever is
    given overrides the seed for that axis, and a `scope`/`effect` override must
    carry its `*_reason`.

        @meta(scope="WebRadio", scope_reason="cross-mode")
        def t_pmt_02(dut): ...

    A `scope_reason` with no `scope` is an ANNOTATION: it records why a seeded
    value is nonetheless a considered placement, without hand-typing a value the
    seeder already derives (EC-D2's "zero hand-typed scope values").

    `cls_reason` is a SENTENCE, not a word (TASK-591 / R35). The other two
    reasons are one-word tags because they distinguish a considered placement
    from a typo; `cls_reason` has to carry an argument, because a gating class
    is a claim about the *rest of the run* — it must say what makes this test's
    failure mean the ids after it cannot be trusted. `gate/check_test_meta.py`
    requires one on every RIG/HEALTH/CORE id and rejects a short one; if you
    cannot write the sentence, the id is FEATURE and that is the finding.

    `ops` (TASK-705) is a tuple of names from `OPS` — the PRIMITIVE OPERATIONS
    this id's body actually exercises. Unlike the three axes above it has no
    seed and is OPT-IN: an undeclared id carries no ops (`()`), and that is
    never a finding — most ids exercise nothing in the closed vocabulary.
    Declaring it must be TRUE for the body: `gate/check_primitive_coverage.py`
    does not check truth, only that every declared op is IN `OPS` (P2) and that
    every op in `OPS` has at least one id declaring it ALONE, i.e. a PRIMITIVE
    (P1), or is on the dated ledger. A composite id declares 2+ ops; each of
    those must itself have a primitive or ledger row (P3).

        @meta(ops=("stock_quote_fetch",))
        def t172(dut): ...

    `oracle`/`premise`/`falsifier` (TASK-641, design §7) are a THIRD,
    independently opt-in group — a body may declare `ops` without them or
    vice versa. Like `ops` they have no seed: an id with none of the three is
    entirely unrepresented in the falsifier record, and that is never itself
    a finding (most of the corpus predates this axis). What IS checked, by
    `gate/check_test_meta.py`, is that whatever IS declared is true and
    well-formed:

      * `oracle` maps a key (or `key.field`, when one command's reply carries
        several independently-assertable fields — e.g. `"sig.inkCount"`) to a
        SHAPE from the closed `SHAPES` enum. It must be the read the claim is
        actually about, and it must be a key this id's body really reads —
        the gate checks the `key` part (before any `.field`) against the
        GENERATED set in `app/gen/read_keys.py`, not the author's word, for
        the same reason `ops` is checked against `OPS`: a declaration that
        names a read the body does not make is worse than no declaration.
      * `premise` is a set of key names the body reads as a PRECONDITION
        before its oracle assertion means anything (e.g. `appId` before a
        style readback would mean anything). No shape — a precondition is
        not itself mutated by a shape-specific operator in this design.
      * `falsifier` is `"replay"` (the driver, TASK-643, confirms it against
        a recorded transcript) or `"physical: <what>; expires <ISO date>"`
        when nothing on the host can exercise it (SD eject, audible output,
        a real fetch). An expired physical falsifier is a gate failure, the
        same rule `flaky.yaml`'s `review_by` already enforces (F8).

    None of this builds the mutation driver or its verdict matrix (TASK-643)
    — only makes the claim expressible and checkable ahead of it.

        @meta(oracle={"clockStyle": "SNAPSHOT"}, falsifier="replay")
        def t_clk_03(dut): ...
    """
    d = {}
    if cls is not None:
        d["cls"] = cls
    if cls_reason is not None:
        d["cls_reason"] = cls_reason
    if scope is not None:
        d["scope"] = scope
    if scope_reason is not None:
        d["scope_reason"] = scope_reason
    if effect is not None:
        d["effect"] = effect
    if effect_reason is not None:
        d["effect_reason"] = effect_reason
    if ops is not None:
        d["ops"] = tuple(ops)
    if oracle is not None:
        d["oracle"] = dict(oracle)
    if premise is not None:
        d["premise"] = tuple(sorted(premise))
    if falsifier is not None:
        d["falsifier"] = falsifier

    def _wrap(fn):
        # Set the attribute; do NOT wrap. fn.__name__/inspect must keep working
        # for check_player_binding.py and any future source-level gate.
        fn._meta = d
        return fn
    return _wrap


# ------------------------------------------------------------ scope seeding

def _module_scope_map() -> dict:
    """family module basename -> APP_ORDER name, DERIVED not typed.

    A family module is named after the app it covers; `player.py` matches via
    the app's DISPLAY name ('Player' -> 'LocalPlayer'). Anything unmatched
    (today: `shell`) has no module seed and falls through to the prefix table.
    """
    by_lower = {n.lower(): n for n in APP_ORDER}
    for canonical, shown in DISPLAY.items():
        by_lower.setdefault(shown.lower(), canonical)
    return by_lower


#: id prefix -> scope. Mostly INSIDE shell.py (design §13.2's measured table);
#: T_TBFB/T_BI are real prefixes but not app names, so they seed a scope, not
#: an app — which is exactly what this field is for.
#:
#: T_DH_ (TASK-565) is the one entry from outside shell.py. The HEALTH family
#: lives in its own module (health.py, §4.5 — a separate registry, merged into
#: neither build_all_tests() nor default_tests), and `health` is deliberately
#: NOT a scope: scope answers "which change selects this test", and the health
#: checks exercise the serial console and the app shell. Seeding by prefix also
#: keeps them out of the catch-all, which the gate reserves for shell.py.
PREFIX_SCOPES = {
    "T_DH_": "shell",
    "T_WX_": "Weather",
    "T_CX_": "Crypto",
    "T_GOL_": "Life",
    "T_MA_": "Matrix",
    "T_TBFB_": "taskbar",
    "T_BI_": "boot",
}

#: shell.py is the multi-app catch-all: its residue seeds to `shell`, a DEFAULT
#: that a declaration overrides (design §13.2 measured 15 app-scoped ids inside
#: it, so this is not an identity).
CATCH_ALL_SCOPE = "shell"


def seed_scope(test_id: str, module_basename: str) -> tuple:
    """-> (scope, how) where how is 'module' | 'prefix' | 'catch-all'."""
    app = _module_scope_map().get(module_basename.lower())
    if app:
        return (app, "module")
    for pref, sc in sorted(PREFIX_SCOPES.items(), key=lambda kv: -len(kv[0])):
        if test_id.startswith(pref):
            return (sc, "prefix")
    return (CATCH_ALL_SCOPE, "catch-all")


def seed_cls(scope: str) -> str:
    """`shell|boot|taskbar` DEFAULTS to CORE — a default, not an invariant
    (design §13.3). `rig` is RIG. Everything else takes the conservative
    FEATURE, and a declaration promotes it."""
    if scope == "rig":
        return "RIG"
    if scope in ("shell", "boot", "taskbar", "spotify-chrome"):
        return "CORE"
    return DEFAULT_CLS


# ----------------------------------------------------------- effect seeding

_READ_VERBS = {"get", "info", "help", "dump", "list", "ls"}
_RESET_VERBS = {"reboot", "restart"}

#: Dut methods that change device state without going through a command string.
_MUTATING_DUT_METHODS = ("set_cooldown_zero",)

_CMD_RE = re.compile(r"\.(?:cmd|send|cmd_drain|cmd_raw)\(\s*(?:f\s*)?[\"']([^\"']*)")
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _reachable_source(fn) -> str:
    """The test's own source plus, transitively, the source of every suite-level
    helper it calls. A test that only issues `get` itself but calls
    `_switch_to_stock` is mutating, and nothing else would notice
    (design §16.3's reference case)."""
    seen: set = set()
    chunks: list = []

    try:
        helpers = importlib.import_module("suite.serialdbg._helpers")
    except Exception:                                       # pragma: no cover
        helpers = None

    def _walk(f, depth: int):
        if id(f) in seen or depth > 6:
            return
        seen.add(id(f))
        try:
            src = inspect.getsource(f)
        except (OSError, TypeError):                         # pragma: no cover
            return
        chunks.append(src)
        mod = sys.modules.get(f.__module__)
        for name in set(_CALL_RE.findall(src)):
            for owner in (mod, helpers):
                g = getattr(owner, name, None) if owner is not None else None
                if (inspect.isfunction(g)
                        and g.__module__.startswith("suite.serialdbg")):
                    _walk(g, depth + 1)

    _walk(fn, 0)
    return "\n".join(chunks)


def seed_effect(fn) -> str:
    """Derive read-only / mutating / resetting from the commands the step can
    actually issue. Conservative by construction: anything unrecognised is
    `mutating`, so a step nobody classified is never admitted to a descent by
    omission (EC-S1)."""
    if fn is None:
        return DEFAULT_EFFECT
    src = _reachable_source(fn)
    if not src:
        return DEFAULT_EFFECT
    verbs = {c.strip().split(" ")[0].split("{")[0].strip().lower()
             for c in _CMD_RE.findall(src)}
    verbs.discard("")
    if verbs & _RESET_VERBS:
        return "resetting"
    if any(m in src for m in _MUTATING_DUT_METHODS):
        return DEFAULT_EFFECT
    if verbs and verbs <= _READ_VERBS:
        return "read-only"
    return DEFAULT_EFFECT


# ------------------------------------------------------------- the resolver

def resolve(test_id: str, fn, module_basename: str, declared: dict = None) -> dict:
    """Seed, then apply the declaration. Returns the full record plus enough
    provenance for the gate to tell a seed from a hand-typed value."""
    decl = dict(declared or {})
    if fn is not None:
        decl.update(getattr(fn, "_meta", {}) or {})

    scope_seed, how = seed_scope(test_id, module_basename)
    scope = decl.get("scope", scope_seed)
    cls = decl.get("cls", seed_cls(scope))
    effect_seed = seed_effect(fn)
    effect = decl.get("effect", effect_seed)
    ops = tuple(decl.get("ops", ()) or ())
    oracle = dict(decl.get("oracle", {}) or {})
    premise = tuple(decl.get("premise", ()) or ())
    falsifier = decl.get("falsifier")

    return {
        "id": test_id,
        "cls": cls,
        "scope": scope,
        "effect": effect,
        "ops": ops,
        "ops_declared": "ops" in decl,
        "oracle": oracle,
        "oracle_declared": "oracle" in decl,
        "premise": premise,
        "premise_declared": "premise" in decl,
        "falsifier": falsifier,
        "falsifier_declared": "falsifier" in decl,
        "module": module_basename,
        "scope_seed": scope_seed,
        "scope_seeded_by": how,
        "scope_declared": "scope" in decl,
        "scope_reason": decl.get("scope_reason"),
        "cls_declared": "cls" in decl,
        "cls_seed": seed_cls(scope),
        "cls_reason": decl.get("cls_reason"),
        "effect_seed": effect_seed,
        "effect_declared": "effect" in decl,
        "effect_reason": decl.get("effect_reason"),
    }


# ----------------------------------------------- the file -> scope map (§13.4)

_HERE = os.path.dirname(os.path.abspath(__file__))
#: app/tools/suite/serialdbg -> repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))


def app_source_map(root: str = None) -> dict:
    """`find app/src -name '*App.cpp'` -> {APP_ORDER name: path}.

    The GLOB is the specification, not `app/src/apps/` — two apps (Stock,
    Aquarium) predate that directory and were never moved, so an
    `app/src/apps/*App.cpp` glob silently loses the second-largest family in the
    suite (design §13.4, corrected at the must-fix pass). Raises if the derived
    names are not exactly APP_ORDER, so an app added under a new directory fails
    loudly instead of losing its ids.
    """
    root = root or REPO_ROOT
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "app", "src", "**", "*App.cpp"),
                                 recursive=True)):
        stem = os.path.basename(path)[: -len("App.cpp")]
        out[stem[:1].upper() + stem[1:]] = path
    if set(out) != set(APP_ORDER):
        raise AssertionError(
            "app/src/**/*App.cpp does not match APP_ORDER: "
            f"missing={sorted(set(APP_ORDER) - set(out))} "
            f"extra={sorted(set(out) - set(APP_ORDER))}")
    return out


#: directory prefix -> non-app scope, for `--scope <path>`.
_PATH_SCOPES = (
    ("app/src/shell", "shell"),
    ("app/src/debug", "shell"),
    ("app/src/boot", "boot"),
    ("app/src/taskbar", "taskbar"),
    ("app/src/winamp", "Spotify"),
    ("app/src/spotify", "spotify-chrome"),
    ("run/", "rig"),
    ("app/tools/lib", "rig"),
)


def scope_from_path(value: str, root: str = None) -> str:
    """Resolve a changed FILE to a scope. Raises ValueError if it cannot."""
    root = root or REPO_ROOT
    # Accept a path relative to the CWD or to the repo root — run/test-targeted
    # invokes the runner from app/, and a developer names the file they changed
    # relative to wherever they are standing.
    p = os.path.abspath(value)
    if not os.path.exists(p) and not os.path.isabs(value):
        p = os.path.abspath(os.path.join(root, value))
    rel = os.path.relpath(p, root).replace(os.sep, "/")
    base = os.path.basename(rel)
    if base.endswith("App.cpp") or base.endswith("App.h"):
        stem = base[: -len("App.cpp")] if base.endswith("App.cpp") else base[: -len("App.h")]
        name = stem[:1].upper() + stem[1:]
        if name in APP_ORDER:
            return name
        raise ValueError(f"{rel}: '{name}' is not an APP_ORDER app")
    for prefix, scope in _PATH_SCOPES:
        if rel.startswith(prefix):
            return scope
    raise ValueError(
        f"cannot resolve {rel} to a scope. Pass a scope name directly, one of: "
        + ", ".join(SCOPES))


def resolve_selector(value: str, root: str = None) -> str:
    """`--scope` takes either a scope name or a path. Scope names win, and the
    match is CASE-SENSITIVE — `Spotify` and `spotify-chrome` are different sets
    and a case-insensitive match here is the defect §13.3 renamed the enum to
    prevent."""
    if value in SCOPES:
        return value
    return scope_from_path(value, root)
