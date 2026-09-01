"""suite/serialdbg — the serialdbg-001 regression suite, split by family (TASK-480).

Per-family modules (`clock.py`, `stock.py`, `teletext.py`, `planeradar.py`,
`webradio.py`, `player.py`, `shell.py`) each own a `TESTS: dict[str, callable]`
registry mapping test id -> test function, plus whatever private helpers only
they use. `_helpers.py` holds helpers shared by 2+ families.

`run_serialdbg_tests.py` (the monolith, still the live CLI entry point until
every family is moved — see the design doc's staged migration, M-TOOLING §6)
imports each family's functions/TESTS dict as it is extracted, so its own
ALL_TESTS keeps working unchanged for `run/test`/`run/test-targeted` callers
throughout the migration. This module's `build_all_tests()` is the
in-progress combined registry — currently a smoke check that the mechanism
works, not yet the live path (0 families migrated so far).
"""

from __future__ import annotations

# Populated one family at a time as suite/serialdbg/<family>.py lands and
# defines a module-level TESTS dict. Import order here doesn't matter --
# ids don't collide across families.
_FAMILY_MODULES: list[str] = ["clock", "teletext", "planeradar", "stock", "webradio", "player", "shell"]


def build_all_tests() -> dict:
    """Merge every migrated family's TESTS dict. Empty until families land."""
    import importlib

    merged: dict = {}
    for name in _FAMILY_MODULES:
        mod = importlib.import_module(f"suite.serialdbg.{name}")
        merged.update(mod.TESTS)
    return merged


def build_all_meta() -> dict:
    """id -> the (cls, scope, effect) record, seeded from the module/prefix and
    overridden by any `@meta(...)` declaration. TASK-570, design §13.3.

    Same registry, same ids, same order as build_all_tests() — this is a view
    over it, never a second list to keep in step (LL-114: parse, don't mirror).

    A family may also carry `META_OVERRIDES: dict[str, dict]` for registry
    entries that are NOT functions and so cannot hold an attribute. There are
    three today (shell.py's interactive T093/T094/T095 map to None and are
    dispatched by name in runner.py); the design assumed there were none.
    """
    import importlib

    from suite.serialdbg import _meta

    out: dict = {}
    for name in _FAMILY_MODULES:
        mod = importlib.import_module(f"suite.serialdbg.{name}")
        overrides = getattr(mod, "META_OVERRIDES", {})
        for tid, fn in mod.TESTS.items():
            out[tid] = _meta.resolve(tid, fn, name, overrides.get(tid))
    return out


def ids_for_scope(scope: str, meta: dict = None) -> list:
    """Every id attributed to `scope`, in registry order."""
    meta = meta if meta is not None else build_all_meta()
    return [tid for tid, rec in meta.items() if rec["scope"] == scope]
