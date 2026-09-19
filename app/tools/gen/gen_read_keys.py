#!/usr/bin/env python3
r"""gen_read_keys.py — the generated read-key set. TASK-641 (design
docs/architecture/designs/M-HARNESS2-falsifier-taxonomy.md §2, §7).

WHAT THIS IS. Every id in the suite (`suite.serialdbg.build_all_tests()` +
`build_health_tests()`) reads some set of `get <key>` / `set <key>` /
`log:<pattern>` / `cmd <verb>` values on its healthy path. §7 wants that set
GENERATED, not hand-typed, so `gate/check_test_meta.py`'s future `oracle=`
declarations can be checked against it instead of trusted on the author's
word.

TASK-713: a fourth kind, `cmd`. `get`/`set` cover a named-variable read/write;
`log` covers a `drain_log_lines(...)` pattern; neither has a vocabulary for a
body that binds the REPLY to some other command (`tap`, `drag`, `switchApp`,
`advance`, `info`, `playerCycle`, `reconnect`, `tick`, `reboot`, `release`, …)
and reads a field off it — `r = dut.cmd("tap 10 20"); r.get("hit")` has no
representable oracle key before this. `("cmd", "tap")` is that key: the
COMMAND VERB is the key (coarse — one `cmd tap` entry covers every `tap` at
every coordinate, exactly as one `get appId` entry covers many `get appId`
calls), and a field on its reply is the dotted field the same way `sig.ink
Count` already works for `get sig`. See `_CMD_RE` below for why "issued", not
"issued AND its reply read", is what earns the key — it matches the
"issued" standard `get`/`set` already used (a transcript exchange, or a
literal `dut.cmd("get X")` call site, earns its key whether or not the return
value is ever assigned to a name), not a stricter one invented just for this
kind.

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
     depth-bounded — `suite/serialdbg/_meta.py`'s `_reachable_source`, which
     already does that walk for scope/effect seeding and is IMPORTED here, not
     copied: a mirrored walk drifts silently and in the unsafe direction, which
     is the TASK-600 lesson below applied to this file's own code). An id
     resolved this way is marked `status: "APPROX"` and any read
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

WHAT IS STILL OUTSIDE THE VOCABULARY, AFTER TASK-713 ADDED `cmd`. Two ids
carry NO key of any kind, and neither is a hole this generator should close:

  * `T094` (app/tools/suite/serialdbg/shell.py:709) is a physical-tap test —
    its oracle is a human watching the board. That is the taxonomy's
    `PHYSICAL` shape, which by design has no host operator and is carried by
    the record's `falsifier` field with an expiry, not by a read key.
  * `T133` (app/tools/suite/serialdbg/shell.py:845) asserts on the CHECKOUT:
    part A greps `lib/SpotifyArduino/src/SpotifyArduino.cpp` for a zero-init
    guard. A host-file oracle is outside this set's universe — the set is
    device reads — and that same host-file dependence is why TASK-591 demoted
    the id out of CORE (`check_gating_offline.py`'s N4).

Both are named here because "0 unresolved reads" in the census is a claim
about the WALK, not about whether every id has a declarable oracle, and the
difference is easy to read past.

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
#: Any other command word (`tap`, `drag`, `switchApp`, `advance`, `info`,
#: `playerCycle`, `reconnect`, `tick`, `reboot`, `release`, …). Tried only
#: after `_GETSET_RE` fails to match, so `get`/`set` keep their existing
#: (kind, key) shape untouched — this never reclassifies a get/set command.
_CMD_RE = re.compile(r"^(\S+)")

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
            if m:
                kind, key = m.group(1), m.group(2)
                if "{" in key:
                    unresolved.append(f"{kind} <dynamic key>: {content!r}")
                else:
                    keys.add((kind, key))
                continue
            cm = _CMD_RE.match(content.strip())
            if cm:
                verb = cm.group(1)
                if "{" in verb:
                    unresolved.append(f"cmd <dynamic verb>: {content!r}")
                else:
                    keys.add(("cmd", verb))
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
        c = (cmd or "").strip()
        m = _GETSET_RE.match(c)
        if m:
            keys.add((m.group(1), m.group(2)))
            continue
        cm = _CMD_RE.match(c)
        if cm:
            keys.add(("cmd", cm.group(1)))
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
        "kind_counts": {},
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

    # Honest census, per-kind (TASK-713): counted over the FINAL per-id key
    # sets (transcript + static log-scan merged), so it reflects exactly what
    # `emit()` writes — not an intermediate source-by-source tally that could
    # drift from the output.
    kind_counts: dict = {}
    for rec in records.values():
        for kind, _key in rec["keys"]:
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
    stats["kind_counts"] = kind_counts

    return records, stats


# ── emit ──────────────────────────────────────────────────────────────────────

def emit(records: dict, out_path: pathlib.Path) -> None:
    lines = [
        "# AUTO-GENERATED by gen_read_keys.py — do not edit by hand.",
        "# Re-run: python3 app/tools/gen/gen_read_keys.py",
        "",
        "# id -> {\"status\": \"transcript\" | \"APPROX\",",
        "#        \"keys\": [[kind, key], ...],   # kind in get/set/log/cmd",
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
    kc = stats.get("kind_counts") or {}
    print("  keys by kind: " + ", ".join(
        f"{k}={v}" for k, v in sorted(kc.items())))
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
        description="Generate app/gen/read_keys.py, the per-id get/set/log/cmd "
                    "read-key set (TASK-641/685, transcript-first with a "
                    "static APPROX fallback).")
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
