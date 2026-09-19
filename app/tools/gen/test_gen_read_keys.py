#!/usr/bin/env python3
"""Negative tests for gen_read_keys.py + check_read_keys.py — BP-068. TASK-641/685.

Pins the behaviours the design (M-HARNESS2-falsifier-taxonomy §2, §7)
actually depends on:

  P1  a transcript-backed id yields its exact `get`/`set`/`cmd` command set —
      no more, no less than what is on the wire in the recording.
  P2  an id with NO transcript is marked APPROX (the static fallback).
  P3  an unresolved f-string key is LISTED, never guessed at, and demotes the
      id's status to APPROX even when a transcript exists (the `log:<pattern>`
      half is always static — see the module docstring).
  P4  the staleness gate (`check_read_keys.py`) is a real gate: it PASSES
      against a correct regenerate-and-diff and FAILS when the committed file
      is mutated out from under it.
  P5  TASK-713: the `cmd` kind. A non-get/set command (`tap`, `info`, …) that
      is ISSUED earns its `("cmd", verb)` key whether or not the body ever
      reads a field off the reply — the same "issued earns the key" standard
      `get`/`set` already use (a `dut.cmd("get X")` call site with the return
      value discarded still earns `("get", "X")` today; a wire-level
      transcript cannot tell "issued" from "issued and read" apart in the
      first place, since replay has no visibility into what the Python body
      did with the parsed reply — only that it asked for one). Keying on the
      READ site instead would need a second, much fuzzier walk (which local
      binds a field off which reply) for a benefit this generator does not
      need: `check_test_meta.py`'s falsifier check only needs to know the key
      is REPRESENTABLE, not that a specific call site consumed it, and a
      command issued without its reply ever inspected is still a true
      constraint on the healthy path (the firmware sent something back, and
      whatever it sent forms a fresh unread oracle if a future body ever asks
      for one).  A dynamic (non-literal) verb stays unresolved, never
      invented, exactly like a dynamic get/set key.

No DUT, no build, no network, no writes to the live `suite/serialdbg/
transcripts/` tree (P1/P2/P3 build throwaway `Transcript`/function objects
directly rather than dropping files into the live suite — TASK-600's own
lesson about probes landing in the live tree, avoided by construction here).

Run: python3 app/tools/gen/test_gen_read_keys.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLS))

import gen_read_keys as G                                # noqa: E402
from lib import replay as RP                             # noqa: E402
sys.path.insert(0, str(TOOLS / "gate"))
import check_read_keys as CK                             # noqa: E402


def one(fs, needle):
    hits = [f for f in fs if needle in f]
    assert hits, f"expected a finding containing {needle!r}, got {fs}"
    return hits


def none(fs):
    assert not fs, f"expected no findings, got {fs}"


# ── P1 — transcript-backed exactness ────────────────────────────────────────

def case_transcript_exact_command_set():
    t = RP.Transcript(tid="H2_PROBE_T1")
    t.add("get appId", ['{"ok":true,"var":"appId","name":"Clock"}'])
    t.add("set clockStyle 0", ['{"ok":true,"var":"clockStyle"}'])
    t.add("switchApp 1", ['{"ok":true}'])          # not get/set — TASK-713: cmd kind
    t.add("tap 10 20", ['{"ok":true}'])            # not get/set — TASK-713: cmd kind
    keys = G._transcript_keys(t)
    assert keys == {("get", "appId"), ("set", "clockStyle"),
                    ("cmd", "switchApp"), ("cmd", "tap")}, keys


def case_transcript_missing_command_is_absent():
    """A key the recording never exercised must not appear — the transcript
    is exact for what happened, and only for what happened."""
    t = RP.Transcript(tid="H2_PROBE_T2")
    t.add("get heap", ['{"ok":true,"var":"heap","val":123}'])
    keys = G._transcript_keys(t)
    assert keys == {("get", "heap")}, keys
    assert ("get", "backoff") not in keys


# ── P2 — no transcript -> APPROX, via build_records() end to end ───────────

def case_no_transcript_ids_are_approx():
    records, stats = G.build_records()
    no_transcript = [tid for tid in records
                     if not (G.TRANSCRIPTS_DIR / f"{tid}.json").exists()]
    assert no_transcript, "fixture assumption broken: every id has a transcript"
    for tid in no_transcript:
        assert records[tid]["status"] == "APPROX", (
            f"{tid} has no transcript but was not marked APPROX: {records[tid]}")
    assert stats["approx"] >= len(no_transcript)


def case_transcript_backed_ids_outnumber_approx():
    """A coarse sanity floor, not a tripwire on the exact split (that shifts
    as transcripts are recorded) — catches the generator silently falling
    back to APPROX for everything, which a per-id check would not catch if
    every case in this file also regressed the same way."""
    _records, stats = G.build_records()
    assert stats["transcript_backed"] > stats["approx"], stats
    assert stats["ids_total"] == (stats["transcript_backed"] + stats["approx"])


# ── P3 — unresolved f-string keys are listed, not invented ─────────────────

def case_fstring_dynamic_get_key_unresolved():
    blob = 'def t(dut, var):\n    dut.cmd(f"get {var}")\n'
    keys, unresolved = G._extract_full(blob)
    assert not keys, f"a fully dynamic key must not be guessed at: {keys}"
    one(unresolved, "get <dynamic key>")


def case_fstring_static_key_dynamic_value_resolved():
    """The key half of `f"set clockStyle {value}"` IS static — only the VALUE
    is dynamic — so this must resolve, not land in unresolved. Distinguishing
    the two is the whole point of listing rather than guessing: a body that
    always targets the same key must not be penalised for a normal parameter."""
    blob = 'def t(dut, value):\n    dut.cmd(f"set clockStyle {value}")\n'
    keys, unresolved = G._extract_full(blob)
    assert ("set", "clockStyle") in keys, keys
    assert not unresolved, unresolved


def case_dynamic_log_pattern_unresolved():
    blob = 'def t(dut, pattern):\n    dut.drain_log_lines(pattern, 1, timeout=1)\n'
    keys, unresolved = G._extract_log_only(blob)
    assert not keys, keys
    one(unresolved, "log <dynamic pattern>")


def case_raw_string_log_pattern_resolved():
    """The regression this generator itself shipped with: a raw-string log
    pattern (`r"\\[wifiCfg\\]"`, the real T_DH_02 body) was mis-parsed as
    non-literal because `_literal_content` did not strip the `r` prefix."""
    blob = r'def t(dut):' + "\n" + r'    dut.drain_log_lines(r"\[wifiCfg\]", 1)' + "\n"
    keys, unresolved = G._extract_log_only(blob)
    assert not unresolved, unresolved
    assert ("log", r"\[wifiCfg\]") in keys, keys


def case_bare_variable_command_unresolved():
    """`dut.cmd(cmd_str)` with no string literal at all — the fully dynamic
    case at the other end from the f-string one."""
    blob = 'def t(dut, cmd_str):\n    dut.cmd(cmd_str)\n'
    keys, unresolved = G._extract_full(blob)
    assert not keys, keys
    one(unresolved, "non-literal command")


def case_get_val_var_name_resolved():
    blob = 'def t(dut):\n    return dut.get_int("lastPlaylistDraw", field="ms")\n'
    keys, unresolved = G._extract_full(blob)
    assert ("get", "lastPlaylistDraw") in keys, keys
    assert not unresolved, unresolved


def case_dut_wrapper_reads_fixed_key():
    """`wait_shell_cooldown_clear()` issues `get shellCooldown` without the
    body ever spelling the key out — the fixed-wrapper table must still find
    it, or every id using this common helper silently loses that read."""
    blob = 'def t(dut):\n    dut.wait_shell_cooldown_clear()\n'
    keys, unresolved = G._extract_full(blob)
    assert ("get", "shellCooldown") in keys, keys
    assert not unresolved, unresolved


# ── P5 — TASK-713: the `cmd` kind ───────────────────────────────────────────

def case_cmd_key_from_bound_and_read_reply():
    """The headline case: `r = dut.cmd("tap 10 20"); r.get("hit")` — a bound
    reply whose field is actually read — must resolve to `("cmd", "tap")`."""
    blob = 'def t(dut):\n    r = dut.cmd("tap 10 20")\n    return r.get("hit")\n'
    keys, unresolved = G._extract_full(blob)
    assert ("cmd", "tap") in keys, keys
    assert not unresolved, unresolved


def case_cmd_key_from_issued_reply_never_read():
    """A `tap` issued with the reply discarded entirely still earns its key —
    see the module docstring's P5 note for why "issued", not "issued and
    read", is the standard applied (it matches what `get`/`set` already do,
    and a wire-level transcript cannot see which call sites read a field
    off a parsed reply in the first place)."""
    blob = 'def t(dut):\n    dut.cmd("tap 10 20")\n'
    keys, unresolved = G._extract_full(blob)
    assert ("cmd", "tap") in keys, keys
    assert not unresolved, unresolved


def case_cmd_dynamic_verb_unresolved():
    """A fully dynamic command verb (not just a dynamic argument after it)
    must be listed, never invented as a fabricated key."""
    blob = 'def t(dut, verb):\n    dut.cmd(f"{verb} 10 20")\n'
    keys, unresolved = G._extract_full(blob)
    assert not any(kind == "cmd" for kind, _key in keys), keys
    one(unresolved, "cmd <dynamic verb>")


def case_witness_ids_now_declarable():
    """T077 (tap reply oracle) and T_CLK_11 (info reply oracle) are the two
    measured witnesses TASK-713 exists for — both must now carry a `cmd` key
    in the live generated set."""
    records, _stats = G.build_records()
    assert ("cmd", "tap") in records["T077"]["keys"], records["T077"]
    assert ("cmd", "info") in records["T_CLK_11"]["keys"], records["T_CLK_11"]


def case_determinism_two_runs_byte_identical():
    """Two independent `build_records()` + `emit()` runs must produce
    byte-identical output — no dict-order or timestamp dependence anywhere
    in the new `cmd`-kind code path."""
    records1, _ = G.build_records()
    records2, _ = G.build_records()
    with tempfile.TemporaryDirectory(prefix="rk_det_a_") as d1, \
         tempfile.TemporaryDirectory(prefix="rk_det_b_") as d2:
        p1 = Path(d1) / "read_keys.py"
        p2 = Path(d2) / "read_keys.py"
        G.emit(records1, p1)
        G.emit(records2, p2)
        assert p1.read_text() == p2.read_text()


# ── P4 — the staleness gate is a real gate ──────────────────────────────────

def case_staleness_gate_passes_on_live_tree():
    with tempfile.TemporaryDirectory(prefix="rk_p4_") as tmp:
        rc, output = CK.regenerate(tmp)
        findings = CK.evaluate(tmp, rc, output)
    none(findings)


def case_staleness_gate_fails_on_mutated_committed_file():
    """Corrupt a SCRATCH COPY that stands in for the committed file — never
    touch the real `app/gen/read_keys.py` — and assert the comparison catches
    it. `evaluate()` takes the committed path only through the module-level
    `CK.COMMITTED` constant, so this patches that constant for the duration of
    the case and restores it in `finally`, exactly like the diff it is
    checking never being allowed to leak into the real gate's next run."""
    old_committed = CK.COMMITTED
    with tempfile.TemporaryDirectory(prefix="rk_p4_mutate_") as tmp:
        fake_committed = os.path.join(tmp, "read_keys.py")
        with open(old_committed, "r", encoding="utf-8") as f:
            original = f.read()
        with open(fake_committed, "w", encoding="utf-8") as f:
            f.write(original.replace("READ_KEYS = {", "READ_KEYS = {  # TAMPERED\n"))
        CK.COMMITTED = fake_committed
        try:
            with tempfile.TemporaryDirectory(prefix="rk_p4_fresh_") as fresh_dir:
                rc, output = CK.regenerate(fresh_dir)
                findings = CK.evaluate(fresh_dir, rc, output)
            one(findings, "STALE")
        finally:
            CK.COMMITTED = old_committed


def case_staleness_gate_fails_when_committed_file_missing():
    old_committed = CK.COMMITTED
    CK.COMMITTED = os.path.join(tempfile.gettempdir(),
                                "h2_probe_definitely_missing_read_keys.py")
    try:
        with tempfile.TemporaryDirectory(prefix="rk_p4_missing_") as fresh_dir:
            rc, output = CK.regenerate(fresh_dir)
            findings = CK.evaluate(fresh_dir, rc, output)
        one(findings, "does not exist")
    finally:
        CK.COMMITTED = old_committed


CASES = [
    ("P1a transcript command set is exact (no extra)",
     case_transcript_exact_command_set),
    ("P1b a key the recording never sent is absent",
     case_transcript_missing_command_is_absent),
    ("P2a every id with no transcript is APPROX",
     case_no_transcript_ids_are_approx),
    ("P2b transcript-backed ids outnumber APPROX",
     case_transcript_backed_ids_outnumber_approx),
    ("P3a fully dynamic get key -> unresolved, not guessed",
     case_fstring_dynamic_get_key_unresolved),
    ("P3b static key / dynamic value -> resolved",
     case_fstring_static_key_dynamic_value_resolved),
    ("P3c dynamic log pattern -> unresolved",
     case_dynamic_log_pattern_unresolved),
    ("P3d raw-string log pattern resolves (regression guard)",
     case_raw_string_log_pattern_resolved),
    ("P3e bare-variable command -> unresolved",
     case_bare_variable_command_unresolved),
    ("P3f get_int(\"var\") resolves to a plain get key",
     case_get_val_var_name_resolved),
    ("P3g dut.py convenience wrapper resolves its fixed key",
     case_dut_wrapper_reads_fixed_key),
    ("P5a bound-and-read tap reply -> cmd tap",
     case_cmd_key_from_bound_and_read_reply),
    ("P5b issued tap, reply never read -> cmd tap still earned",
     case_cmd_key_from_issued_reply_never_read),
    ("P5c fully dynamic command verb -> unresolved, not guessed",
     case_cmd_dynamic_verb_unresolved),
    ("P5d T077/T_CLK_11 are now declarable (cmd tap / cmd info present)",
     case_witness_ids_now_declarable),
    ("P5e two independent runs are byte-identical",
     case_determinism_two_runs_byte_identical),
    ("P4a staleness gate passes on the live (regenerated) tree",
     case_staleness_gate_passes_on_live_tree),
    ("P4b staleness gate fails on a mutated committed file",
     case_staleness_gate_fails_on_mutated_committed_file),
    ("P4c staleness gate fails when the committed file is missing",
     case_staleness_gate_fails_when_committed_file_missing),
]


def main() -> int:
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"test_gen_read_keys: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
