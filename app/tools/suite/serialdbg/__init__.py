"""suite/serialdbg — the serialdbg-001 regression suite, split by family (TASK-480).

Per-family modules (`clock.py`, `stock.py`, `teletext.py`, `planeradar.py`,
`webradio.py`, `player.py`, `shell.py`) each own a `TESTS: dict[str, callable]`
registry mapping test id -> test function, plus whatever private helpers only
they use. `_helpers.py` holds helpers shared by 2+ families.

`run_serialdbg_tests.py` was the monolith this package replaced. TASK-480
finished: the file is GONE, and `suite/serialdbg/runner.py` is the CLI entry
point `run/test`/`run/test-targeted` invoke. The staged-migration note that
used to live here described a state that ended — it said the monolith was
"still the live CLI entry point", which sent at least one reader to a path
that no longer exists. This module's `build_all_tests()` is the
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


#: The HEALTH family (TASK-565) is NOT in _FAMILY_MODULES: it carries
#: HEALTH_TESTS, not TESTS, and design §4.5 keeps it out of build_all_tests()
#: and out of default_tests so the ids are ADDRESSABLE without being
#: FILTERABLE OUT. It IS in build_all_meta(), because the record is what mode
#: P's health_verdict() reads.
_HEALTH_MODULE = "health"


def build_health_tests() -> dict:
    """The HEALTH class registry, T_DH_01..03 (TASK-565, design §3.1/§4.5).

    Deliberately a SECOND dict rather than a slice of build_all_tests():
    `default_tests` is built by iterating that registry's keys, so a health id
    living there would enter the default selection and run twice — once as the
    gate, once as a peer test — including the one mutating check.
    """
    import importlib

    return dict(importlib.import_module(
        f"suite.serialdbg.{_HEALTH_MODULE}").HEALTH_TESTS)


def build_all_meta() -> dict:
    """id -> the (cls, scope, effect) record, seeded from the module/prefix and
    overridden by any `@meta(...)` declaration. TASK-570, design §13.3.

    A view over the registries, never a second list to keep in step (LL-114:
    parse, don't mirror). The id set is build_all_tests() PLUS
    build_health_tests(): the health ids are not runnable by default (§4.5) but
    they must carry a record, or mode P's health_verdict() cannot see the class
    it reports on.

    A family may also carry `META_OVERRIDES: dict[str, dict]` for registry
    entries that are NOT functions and so cannot hold an attribute. There are
    three today (shell.py's interactive T093/T094/T095 map to None and are
    dispatched by name in runner.py); the design assumed there were none.
    """
    import importlib

    from suite.serialdbg import _meta

    out: dict = {}
    # HEALTH first: the class order the design gates on is RIG < HEALTH < CORE
    # < APP < FEATURE, and this dict's iteration order is what every census and
    # every report reads.
    hmod = importlib.import_module(f"suite.serialdbg.{_HEALTH_MODULE}")
    for tid, fn in hmod.HEALTH_TESTS.items():
        out[tid] = _meta.resolve(tid, fn, _HEALTH_MODULE, None)
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
