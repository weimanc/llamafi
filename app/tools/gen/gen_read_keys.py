#!/usr/bin/env python3
r"""gen_read_keys.py — the generated read-key set. TASK-641 (design
docs/architecture/designs/M-HARNESS2-falsifier-taxonomy.md §2, §7).

WHAT THIS IS. Every id in the suite (`suite.serialdbg.build_all_tests()` +
`build_health_tests()`) reads some set of `get <key>` / `set <key>` /
`log:<pattern>` values on its healthy path. §7 wants that set GENERATED, not
hand-typed, so `gate/check_test_meta.py`'s future `oracle=` declarations can be
checked against it instead of trusted on the author's word.

TWO SOURCES, TRANSCRIPT FIRST (§2):

  1. TRANSCRIPT (`suite/serialdbg/transcripts/<id>.json`, `lib.replay.Transcript`
     — TASK-628). Exact: `.exchanges` is keyed `(cmd, nth)` in record order, and
     every `get X` / `set X ...` the body actually sent on the recording's
     healthy path is a key in that mapping. This is ground truth, not a guess.
     `drain_log_lines()` reads are NOT commands sent on the wire — a transcript
     never carries them as a distinct exchange key — so even a transcript-backed
     id still needs a small STATIC scan, restricted to `.drain_log_lines(...)`
     call sites reachable from the body, to find its `log:<pattern>` reads.

  2. STATIC WALK (no transcript). A source-level walk of the test function and
     every same-package helper function it can reach (BFS over bare-name calls,
     depth-bounded — the same technique `suite/serialdbg/_meta.py`'s
     `_reachable_source` already uses for scope/effect seeding, duplicated here
     deliberately rather than imported: this generator must be able to prove
     its OWN coverage, per the TASK-600 lesson below, not inherit an unaudited
     helper). An id resolved this way is marked `status: "APPROX"` and any read
     whose key could not be pinned to a literal (an f-string like
     `f"get {var}"`, or a fully dynamic argument) is listed under
     `"unresolved"` rather than guessed at.

THE TASK-600 LESSON, APPLIED. `gen_get_keys.py` claimed two sources and
delivered one for months: a glob that missed a moved file, and a regex that
missed an out-of-line definition — 43 of 111 keys, silently. This generator
cannot cross-check itself against an independent oracle the way
`gate/check_get_keys.py` does (there is no second, dumber way to read a
transcript, and a full-tree regex over test bodies would just be this
generator's own algorithm wearing a hat) — so instead it prints an HONEST
CENSUS every run: ids total, transcript-backed vs APPROX, keys found by each
source, and every id it could not resolve a function for at all. An unresolved
id is a printed line, never a silent zero.

OUTPUT: `app/gen/read_keys.py`, in the house style of `app/tools/app_ids_gen.py`
— data only, no timestamps, ids and keys sorted so two runs are byte-identical
(`gate/check_read_keys.py` — inside `app/tools/smoke_test.sh`, not
`check_build.sh` — regenerates to a temp dir and diffs).

Re-run after editing a test body or recording a new transcript:
    python3 app/tools/gen/gen_read_keys.py
"""

from __future__ import annotations

import argparse
import inspect
import os
import pathlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))
sys.path.insert(0, TOOLS)

from lib import replay as RP                                       # noqa: E402

TRANSCRIPTS_DIR = pathlib.Path(TOOLS) / "suite" / "serialdbg" / "transcripts"
DEFAULT_OUT = pathlib.Path(ROOT) / "app" / "gen"

# ── the reachable-source walk ────────────────────────────────────────────────
#
# NOT a second copy. `suite/serialdbg/_meta.py:265` already does this walk —
# BFS over bare-name calls, resolved against the function's own module and
# `suite.serialdbg._helpers`, depth-bounded — to seed scope/effect, and the
# first draft of this generator mirrored it line for line (same `_CALL_RE`,
# same depth 6, same resolution order). A mirror of a walk is a mirror that
# drifts: the day someone widens `_meta`'s call regex, this file would keep
# the old one and quietly report a smaller read set, which is exactly the
# failure `gen_get_keys.py` shipped (43 of 111 keys, TASK-600/R7). Imported
# instead, so there is one walk with one behaviour.

from suite.serialdbg._meta import _reachable_source as _walk_reachable  # noqa: E402


def _reachable_source(fn) -> str:
    """-> the concatenated source of every function reachable from `fn`.

    A one-line pass-through so this file names what it uses. The walk itself,
    and the `suite.serialdbg._helpers` import it needs, live in `_meta`.
    """
    return _walk_reachable(fn)


# ── extracting (kind, key) pairs from source text ───────────────────────────
#
# `dut.cmd(...)` / `.send(...)` / `.cmd_drain(...)` / `.read_reply(...)` take a
# full command string ("get X", "set X Y", "tap 10 20" — only the first two
# kinds are reads this generator cares about). `.get_val/_int/_float/_str/_bool`
# and `.set_val` take the bare key name as their first argument. Capturing the
# RAW first-argument text (stopping at the first top-level comma or paren) lets
# one extraction handle both a plain string literal and an f-string whose
# placeholder falls after a literal prefix — `f"set clockStyle {value}"` still
# resolves to key "clockStyle" because the placeholder is in the VALUE
# position, not the key.

_METHOD_ARG_RE = re.compile(
    r"\.(cmd|send|cmd_drain|read_reply"
    r"|get_val|get_int|get_float|get_str|get_bool|set_val)\(\s*([^,)]*)")
_LOG_ARG_RE = re.compile(r"\.drain_log_lines\(\s*([^,)]*)")
_GETSET_RE = re.compile(r"^(get|set)\s+(\S+)")

_STRING_METHODS = {"cmd", "send", "cmd_drain", "read_reply"}
_VARNAME_METHOD_KIND = {
    "get_val": "get", "get_int": "get", "get_float": "get",
    "get_str": "get", "get_bool": "get", "set_val": "set",
}

#: `dut.py` convenience wrappers that issue a fixed key without the body ever
#: spelling it out. Small and hand-maintained deliberately — these are the
#: WIRE PROTOCOL fixed inside `lib/dut.py`, not suite behaviour, so walking
#: into `lib/dut.py`'s own source is out of scope (§ the design's "the body and
#: the same-package helpers it reaches").
_DUT_WRAPPER_RE = re.compile(
    r"\.(wait_shell_cooldown_clear|set_cooldown_zero|wait_for_queue)\s*\(")
_DUT_WRAPPER_READS = {
    "wait_shell_cooldown_clear": (("get", "shellCooldown"),),
    "set_cooldown_zero": (("set", "cooldown"),),
    "wait_for_queue": (("get", "queue"),),
}


#: Python string-literal prefixes this generator must strip before looking for
#: the opening quote: plain, f-string, raw, and the (rare, but legal) raw-f
#: combination in either letter order. Case-folded since Python accepts both.
_STR_PREFIXES = ("f", "r", "fr", "rf", "b", "rb", "br")


def _literal_content(raw: str):
    """-> the string literal's content, or None if `raw` is not a string
    literal at all (a bare variable/expression passed as the argument)."""
    raw = raw.strip()
    low = raw.lower()
    for pfx in sorted(_STR_PREFIXES, key=len, reverse=True):
        if low[:len(pfx) + 1] == pfx + "'" or low[:len(pfx) + 1] == pfx + '"':
            raw = raw[len(pfx):]
            break
    if raw[:1] in ("'", '"'):
        q = raw[0]
        if len(raw) >= 2 and raw.endswith(q):
            return raw[1:-1]
        return raw[1:]          # unterminated / regex captured past the quote
    return None


def _extract_full(blob: str) -> tuple[set, list]:
    """get/set (from cmd-string and var-name call sites) + log, over `blob`."""
    keys: set = set()
    unresolved: list = []
    for method, rawarg in _METHOD_ARG_RE.findall(blob):
        content = _literal_content(rawarg)
        if method in _STRING_METHODS:
            if content is None:
                unresolved.append(f"{method}(...) non-literal command: "
                                  f"{rawarg.strip()!r}")
                continue
            m = _GETSET_RE.match(content.strip())
            if not m:
                continue          # not a get/set command (tap/drag/switchApp/…)
            kind, key = m.group(1), m.group(2)
            if "{" in key:
                unresolved.append(f"{kind} <dynamic key>: {content!r}")
            else:
                keys.add((kind, key))
        else:
            kind = _VARNAME_METHOD_KIND[method]
            if content is None:
                unresolved.append(f"{kind} <dynamic var>: {rawarg.strip()!r}")
            elif "{" in content:
                unresolved.append(f"{kind} <dynamic var>: {content!r}")
            else:
                keys.add((kind, content))
    log_keys, log_unresolved = _extract_log_only(blob)
    keys |= log_keys
    unresolved += log_unresolved
    for name in _DUT_WRAPPER_RE.findall(blob):
        keys.update(_DUT_WRAPPER_READS[name])
    return keys, unresolved


def _extract_log_only(blob: str) -> tuple[set, list]:
    keys: set = set()
    unresolved: list = []
    for rawarg in _LOG_ARG_RE.findall(blob):
        content = _literal_content(rawarg)
        if content is None:
            unresolved.append(f"log <dynamic pattern>: {rawarg.strip()!r}")
        elif "{" in content:
            unresolved.append(f"log <dynamic pattern>: {content!r}")
        else:
            keys.add(("log", content))
    return keys, unresolved


def _transcript_keys(t) -> set:
    keys = set()
    for (cmd, _nth) in t.exchanges:
        m = _GETSET_RE.match((cmd or "").strip())
        if m:
            keys.add((m.group(1), m.group(2)))
    return keys


# ── the id -> function registry ──────────────────────────────────────────────

def _id_function_map() -> dict:
    """id -> test function, or None if the registry itself maps it to None
    (shell.py's three interactive ids — TESTS["T093"] etc. are `None` by
    design, dispatched by name in runner.py, per suite/serialdbg/__init__.py).
    """
    import importlib

    from suite.serialdbg import (_FAMILY_MODULES, _HEALTH_MODULE,
                                 build_all_tests, build_health_tests)

    out = {}
    out.update(build_health_tests())
    out.update(build_all_tests())

    # Fallback for registry entries that are None: the real function usually
    # still exists (named t<lower(id)>) for interactive dispatch. Search every
    # family + health module rather than assume a naming convention holds
    # everywhere — an id this can't find stays None and is CENSUSED, not
    # silently skipped.
    missing = [tid for tid, fn in out.items() if fn is None]
    if missing:
        modules = list(_FAMILY_MODULES) + [_HEALTH_MODULE]
        mods = []
        for name in modules:
            try:
                mods.append(importlib.import_module(f"suite.serialdbg.{name}"))
            except Exception:                                   # pragma: no cover
                continue
        for tid in missing:
            for mod in mods:
                g = getattr(mod, tid.lower(), None)
                if inspect.isfunction(g):
                    out[tid] = g
                    break
    return out


# ── the per-id record ────────────────────────────────────────────────────────

def build_records() -> tuple[dict, dict]:
    """-> (id -> record, stats). Record:
        {"status": "transcript" | "APPROX",
         "keys": sorted [[kind, key], ...],
         "unresolved": sorted [str, ...]}
    """
    id_fn = _id_function_map()

    records: dict = {}
    stats = {
        "ids_total": len(id_fn), "transcript_backed": 0, "approx": 0,
        "keys_from_transcript": 0, "keys_from_static": 0,
        "unresolved_ids": [], "unresolvable_fn": [],
    }

    for tid in sorted(id_fn):
        fn = id_fn[tid]
        tpath = TRANSCRIPTS_DIR / f"{tid}.json"
        if tpath.exists():
            try:
                t = RP.Transcript.load(tpath)
            except (OSError, ValueError, RP.ReplayError) as e:
                # Unreadable transcript is not silently "no transcript" — it is
                # its own finding, folded into unresolvable_fn so it prints.
                stats["unresolvable_fn"].append(
                    f"{tid}: transcript unreadable ({type(e).__name__}: {e})")
                t = None
            if t is not None:
                keys = _transcript_keys(t)
                stats["keys_from_transcript"] += len(keys)
                if fn is not None:
                    blob = _reachable_source(fn)
                    log_keys, unresolved = _extract_log_only(blob)
                else:
                    log_keys, unresolved = set(), [
                        "no walkable function found for this id — cannot scan "
                        "for log:<pattern> reads even though a transcript "
                        "exists"]
                keys |= log_keys
                stats["keys_from_static"] += len(log_keys)
                status = "APPROX" if unresolved else "transcript"
                if status == "APPROX":
                    stats["approx"] += 1
                    stats["unresolved_ids"].append(tid)
                else:
                    stats["transcript_backed"] += 1
                records[tid] = {
                    "status": status,
                    "keys": sorted(keys),
                    "unresolved": sorted(unresolved),
                }
                continue
        # No transcript (or an unreadable one) — full static fallback.
        if fn is None:
            stats["unresolvable_fn"].append(
                f"{tid}: no transcript and no walkable function found "
                f"(registry maps it to None with no t<id> fallback)")
            records[tid] = {"status": "APPROX", "keys": [],
                            "unresolved": ["no walkable function"]}
            stats["approx"] += 1
            stats["unresolved_ids"].append(tid)
            continue
        blob = _reachable_source(fn)
        keys, unresolved = _extract_full(blob)
        stats["keys_from_static"] += len(keys)
        stats["approx"] += 1
        if unresolved:
            stats["unresolved_ids"].append(tid)
        records[tid] = {
            "status": "APPROX",
            "keys": sorted(keys),
            "unresolved": sorted(unresolved),
        }

    return records, stats


# ── emit ──────────────────────────────────────────────────────────────────────

def emit(records: dict, out_path: pathlib.Path) -> None:
    lines = [
        "# AUTO-GENERATED by gen_read_keys.py — do not edit by hand.",
        "# Re-run: python3 app/tools/gen/gen_read_keys.py",
        "",
        "# id -> {\"status\": \"transcript\" | \"APPROX\",",
        "#        \"keys\": [[kind, key], ...],   # kind in get/set/log",
        "#        \"unresolved\": [str, ...]}     # f-string/dynamic reads, listed not guessed",
        "READ_KEYS = {",
    ]
    for tid in sorted(records):
        rec = records[tid]
        lines.append(
            f"    {tid!r}: {{'status': {rec['status']!r}, "
            f"'keys': {rec['keys']!r}, 'unresolved': {rec['unresolved']!r}}},"
        )
    lines.append("}")
    lines.append("")
    out_path.write_text("\n".join(lines))


def print_census(stats: dict) -> None:
    print(f"gen_read_keys: {stats['ids_total']} ids total "
          f"({stats['transcript_backed']} transcript-backed, "
          f"{stats['approx']} APPROX)")
    print(f"  keys found: {stats['keys_from_transcript']} from transcripts, "
          f"{stats['keys_from_static']} from the static walk")
    if stats["unresolved_ids"]:
        print(f"  {len(stats['unresolved_ids'])} id(s) carry at least one "
              f"unresolved (dynamic) read: "
              f"{', '.join(stats['unresolved_ids'][:12])}"
              + (" …" if len(stats["unresolved_ids"]) > 12 else ""))
    else:
        print("  0 ids carry an unresolved read")
    if stats["unresolvable_fn"]:
        print(f"  {len(stats['unresolvable_fn'])} id(s) had NO walkable "
              f"function at all:")
        for line in stats["unresolvable_fn"]:
            print(f"    {line}")
    else:
        print("  every id resolved to a walkable function")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate app/gen/read_keys.py, the per-id get/set/log "
                    "read-key set (TASK-641, transcript-first with a static "
                    "APPROX fallback).")
    parser.add_argument("--out-dir", metavar="DIR",
                        help="write read_keys.py to DIR instead of app/gen/")
    parser.add_argument("--list", action="store_true",
                        help="also print every id's resolved keys")
    args = parser.parse_args(argv)

    records, stats = build_records()
    print_census(stats)

    out_dir = pathlib.Path(args.out_dir) if args.out_dir else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "read_keys.py"
    emit(records, out_path)
    print(f"wrote {out_path}")

    if args.list:
        for tid in sorted(records):
            rec = records[tid]
            print(f"  {tid} [{rec['status']}] {rec['keys']}"
                  + (f"  UNRESOLVED: {rec['unresolved']}"
                     if rec["unresolved"] else ""))

    if not records:
        print("ERROR: no ids resolved at all — did the suite registry move?",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
