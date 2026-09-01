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

def meta(cls: str = None, scope: str = None, scope_reason: str = None,
         effect: str = None, effect_reason: str = None):
    """Declare metadata on a test function. Everything is optional; whatever is
    given overrides the seed for that axis, and a `scope`/`effect` override must
    carry its `*_reason`.

        @meta(scope="WebRadio", scope_reason="cross-mode")
        def t_pmt_02(dut): ...

    A `scope_reason` with no `scope` is an ANNOTATION: it records why a seeded
    value is nonetheless a considered placement, without hand-typing a value the
    seeder already derives (EC-D2's "zero hand-typed scope values").
    """
    d = {}
    if cls is not None:
        d["cls"] = cls
    if scope is not None:
        d["scope"] = scope
    if scope_reason is not None:
        d["scope_reason"] = scope_reason
    if effect is not None:
        d["effect"] = effect
    if effect_reason is not None:
        d["effect_reason"] = effect_reason

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


#: id prefix -> scope, INSIDE shell.py only (design §13.2's measured table).
#: T_TBFB/T_BI are real prefixes but not app names, so they seed a scope, not
#: an app — which is exactly what this field is for.
PREFIX_SCOPES = {
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

    return {
        "id": test_id,
        "cls": cls,
        "scope": scope,
        "effect": effect,
        "module": module_basename,
        "scope_seed": scope_seed,
        "scope_seeded_by": how,
        "scope_declared": "scope" in decl,
        "scope_reason": decl.get("scope_reason"),
        "cls_declared": "cls" in decl,
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
