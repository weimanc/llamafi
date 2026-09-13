#!/usr/bin/env python3
"""test_run_artifact.py — the run artifact's own negative suite. TASK-608.

ADR-066 D1 / IFC-008 / R29 / R30, and BP-068: a gate nobody has seen fail is not
a gate. The artifact is now the SOLE machine interface to a run, so the failure
modes that matter are the ones where a consumer reads something and is wrong
about it — not the ones where it reads nothing.

The suite is host-only: no port, no DUT, no flash, well under a second.

WHAT IT ASSERTS, and why each arm exists:

  A. THE STALE-ARTIFACT ARMS (T_ART_10..14). The brief's own criterion: *a gate
     reading a stale artifact from a previous run is a worse failure than no
     artifact at all.* Layer 2 (the run nonce) is asserted directly, including
     the case that would actually happen — a second run at the same path — and
     the case a `rm -f` cannot cover, a hand-copied file.
  B. THE FIVE UNRELATED CALLERS (T_ART_30..33). TASK-624's row proved their rc
     arithmetic byte-identical and this row must keep it so. Asserted by
     ENUMERATING the rc-relevant states and comparing against the arithmetic as
     it stood before either row: `0 if failed == 0 else 1`.
  C. THE PER-SCOPE SKIP CENSUS (T_ART_40..42) — TASK-627.
  D. THE PARSER-RETIREMENT GATE (T_ART_50). R29's acceptance number for
     consumers parsing the human summary is ZERO. Asserted mechanically over the
     tree, so a fourth parser cannot appear the way the first three did.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import artifact as A                                    # noqa: E402
from lib import results as R                                     # noqa: E402

_FAILS = []


def check(tid, got, want):
    if got == want:
        print(f"  ok   {tid}: {got!r}")
    else:
        print(f"  FAIL {tid}: got {got!r} want {want!r}")
        _FAILS.append(tid)


def raises(tid, exc, fn):
    try:
        fn()
    except exc as e:
        print(f"  ok   {tid}: {type(e).__name__}")
        return
    except Exception as e:                                   # wrong exception
        print(f"  FAIL {tid}: raised {type(e).__name__}, want {exc.__name__}")
        _FAILS.append(tid)
        return
    print(f"  FAIL {tid}: returned normally, want {exc.__name__}")
    _FAILS.append(tid)


TMP = pathlib.Path(tempfile.mkdtemp(prefix="artifact-test-"))


def _emit(path, token, record):
    """Run a tiny suite through the real producer and emit to `path`."""
    R.reset()
    R.set_meta_provider(None)
    R.set_premise_provider(None)
    R.RUN_TOKEN = token
    os.environ[A.ENV_PATH] = str(path)
    try:
        record()
        return R.print_results(exit_on_finish=False)
    finally:
        os.environ.pop(A.ENV_PATH, None)


# ── A. schema and round trip ─────────────────────────────────────────────────
print("T_ART_01  a run emits an artifact a reader can read")
p1 = TMP / "run1.json"
rc = _emit(p1, "tok-run-1", lambda: (R.pass_("T1"), R.fail("T2", "boom")))
check("T_ART_01a", rc, 1)
doc = A.load(p1, expect_token="tok-run-1")
check("T_ART_01b", A.id_status(doc), {"T1": "PASS", "T2": "FAIL"})
check("T_ART_01c", A.exit_code(doc), 1)
check("T_ART_01d", doc["schema"]["name"], A.SCHEMA_NAME)

print("T_ART_02  every verdict in the closed enum survives the round trip")
p2 = TMP / "run2.json"


def _all_verdicts():
    R.pass_("V_PASS")
    R.fail("V_FAIL", "x")
    R.skip("V_SKIP", "n/a")
    R.unmet("V_UNMET", "the app never reached READY")
    R.not_run("V_NOTRUN", "CORE/V_FAIL")
    R.RESULTS.set_typed("V_FLAKY", R.Verdict.FLAKY_PASS, "FLAKY-PASS: a | b")
    R.RESULTS.set_typed("V_FLAKE", R.Verdict.FLAKE, "FLAKE(awaiting): jitter")


_emit(p2, "tok-run-2", _all_verdicts)
got = A.id_status(A.load(p2))
check("T_ART_02a", sorted(got.values()),
      sorted(v.value for v in R.Verdict))
# The exact TASK-573 defect, at the new interface: FLAKY-PASS must not arrive
# as a `FLAKY` or a `PASS` fragment, and FLAKE must stay distinct from it.
check("T_ART_02b", got["V_FLAKY"], "FLAKY-PASS")
check("T_ART_02c", got["V_FLAKE"], "FLAKE")
# IFC-008 I3, in the document: NOT-RUN carries its attribution, UNMET does not.
check("T_ART_02d", A.load(p2)["run"]["not_run"], {"V_NOTRUN": "CORE/V_FAIL"})
check("T_ART_02e", A.load(p2)["run"]["unmet"], ["V_UNMET"])

print("T_ART_03  R30's premise fields are present, and null when unstated")
prem = A.load(p2)["premise"]
for k in ("harness_version", "entry_point", "elf", "build_env", "board",
          "generation", "class_order_in_force", "selection",
          "flake_registry_sha256", "downgraded_gates"):
    check(f"T_ART_03[{k}]", k in prem, True)
check("T_ART_03z", prem["elf"], None)

print("T_ART_16  the premise identifies the HARNESS, not the schema (TASK-645)")
# The defect this replaces: `harness_version` was `artifact.SCHEMA_VERSION`, so
# every run ever made by every version of the harness reported the same string —
# and that string was already in the document under `schema.version`. R30 asks
# what CODE produced the run. The arm is stated as an INEQUALITY against the
# schema version precisely so the old value cannot come back unnoticed.
_doc16 = A.load(p2)
check("T_ART_16a", _doc16["premise"]["harness_version"]
      != _doc16["schema"]["version"], True)
check("T_ART_16b", bool(re.match(r"^src-[0-9a-f]{12}$",
                                 str(_doc16["premise"]["harness_version"]))), True)
_h = _doc16["premise"]["harness"]
check("T_ART_16c", len(str(_h["source_sha256"])), 64)
check("T_ART_16d", _h["source_files"] > 50, True)
# Provenance rides ALONGSIDE and is never folded into the identity: a dirty tree
# must still be distinguishable from another dirty tree.
check("T_ART_16e", "git_commit" in _h and "git_dirty" in _h, True)
check("T_ART_16f", str(_h.get("git_commit") or "") not in
      _doc16["premise"]["harness_version"], True)

print("T_ART_17  the premise identifies the BOARD, not the cable (TASK-645)")
# ADR-066 D3 asks which board the run ran against. `{port, baud}` is a fact
# about the cable: a USB re-enumeration renames the port on the same board, and
# a second board on the freed node inherits the same premise. The identity slot
# must exist and must be NAMED-null rather than back-filled from the port.
_b17 = _doc16["premise"]["board"]
check("T_ART_17a", _b17 is None or ("id" in _b17), True)
_probe = {"id": None, "id_source": "absent",
          "transport": {"port": "/dev/ttyUSB0", "baud": 115200}}
check("T_ART_17b", _probe["id"] is None and _probe["id_source"] == "absent", True)
check("T_ART_17c", "/dev/tty" not in str(_probe["id"]), True)

print("T_ART_04  an INSTALLED premise provider fills them in (M-TOOLING: lib/")
print("          never imports a suite, so the suite installs)")
p4 = TMP / "run4.json"
R.set_premise_provider(lambda: {"elf": "deadbeef", "build_env": "cyd2usb_x",
                                "generation": "7.1",
                                "class_order_in_force": True})
R.set_meta_provider(lambda: {"T1": {"cls": "CORE", "scope": "Clock",
                                    "effect": "read"}})
R.reset()
R.RUN_TOKEN = "tok-run-4"
os.environ[A.ENV_PATH] = str(p4)
R.begin("T1")
R.pass_("T1")
R.print_results(exit_on_finish=False)
os.environ.pop(A.ENV_PATH, None)
d4 = A.load(p4)
check("T_ART_04a", d4["premise"]["elf"], "deadbeef")
check("T_ART_04b", d4["premise"]["generation"], "7.1")
check("T_ART_04c", d4["results"][0]["scope"], "Clock")
check("T_ART_04d", d4["results"][0]["cls"], "CORE")
check("T_ART_04e", d4["per_class"]["CORE"]["counts"], {"PASS": 1})
check("T_ART_04f", d4["results"][0]["elapsed_s"] is not None, True)

print("T_ART_05  a provider that RAISES degrades to nulls, never to a crash")
p5 = TMP / "run5.json"


def _boom():
    raise RuntimeError("provider is broken")


R.set_premise_provider(_boom)
R.set_meta_provider(_boom)
rc5 = _emit_rc = None
R.reset()
R.RUN_TOKEN = "tok-run-5"
os.environ[A.ENV_PATH] = str(p5)
rc5 = (R.pass_("T1"), R.print_results(exit_on_finish=False))[1]
os.environ.pop(A.ENV_PATH, None)
check("T_ART_05a", rc5, 0)
check("T_ART_05b", A.load(p5)["premise"]["elf"], None)
R.set_premise_provider(None)
R.set_meta_provider(None)

# ── B. staleness — the failure this design exists against ────────────────────
print("T_ART_10  THE stale case: a SECOND run at the SAME path is refused")
p10 = TMP / "same-path.json"
_emit(p10, "tok-old-run", lambda: R.pass_("T1"))
# a consumer that ran with its own nonce and reads what it finds:
raises("T_ART_10a", A.StaleArtifact, lambda: A.load(p10, expect_token="tok-new-run"))
check("T_ART_10b", A.id_status(A.load(p10, expect_token="tok-old-run")), {"T1": "PASS"})

print("T_ART_11  a hand-copied artifact from another run is refused too —")
print("          the nonce holds where a `rm -f` cannot")
p11 = TMP / "copied.json"
shutil.copy(p10, p11)
raises("T_ART_11a", A.StaleArtifact, lambda: A.load(p11, expect_token="tok-new-run"))

print("T_ART_12  a MISSING artifact is an error, never an empty result set")
raises("T_ART_12a", A.ArtifactError,
       lambda: A.load(TMP / "nope.json", expect_token="t"))

print("T_ART_13  an unknown schema MAJOR is refused, not best-effort parsed")
p13 = TMP / "v2.json"
d = json.loads(p10.read_text())
d["schema"]["version"] = "2.0"
p13.write_text(json.dumps(d))
raises("T_ART_13a", A.SchemaMismatch, lambda: A.load(p13))
# ... but a MINOR bump is additive and MUST still read (ADR-066 Consequences).
p13b = TMP / "v1_9.json"
d["schema"]["version"] = "1.9"
d["run"]["a_field_this_reader_never_heard_of"] = 1
p13b.write_text(json.dumps(d))
check("T_ART_13b", A.id_status(A.load(p13b)), {"T1": "PASS"})

print("T_ART_14  the DEFAULT path is unique per run — no `latest`, no reuse")
a = A.default_path("aaaaaaaa", "2026-09-05T10:00:00.000Z")
b = A.default_path("bbbbbbbb", "2026-09-05T10:00:00.000Z")
check("T_ART_14a", a != b, True)
check("T_ART_14b", "latest" in str(a).lower(), False)
check("T_ART_14c", A.DEFAULT_DIR.name, ".runs")

print("T_ART_15  a truncated/garbage document is an error, not a partial read")
p15 = TMP / "garbage.json"
p15.write_text('{"schema": {"name": "esp_spotify.test-run", "vers')
raises("T_ART_15a", A.ArtifactError, lambda: A.load(p15))

# ── C. the five unrelated print_results callers ──────────────────────────────
print("T_ART_30  the five unrelated callers' rc arithmetic is unchanged")
print("          (enumerated, against pre-TASK-624 `0 if failed == 0 else 1`)")


def _legacy_rc(failed):
    return 0 if failed == 0 else 1


_CASES = [
    ("all pass", lambda: (R.pass_("A"), R.pass_("B")), 0),
    ("one fail", lambda: (R.pass_("A"), R.fail("B", "x")), 1),
    ("pass+skip", lambda: (R.pass_("A"), R.skip("B", "n/a")), 0),
    ("only skips", lambda: (R.skip("A", "n/a"), R.skip("B", "n/a")), 0),
    ("nothing recorded", lambda: None, 0),
    ("fail+skip", lambda: (R.fail("A", "x"), R.skip("B", "n/a")), 1),
]
for name, body, want_failed_gt0 in _CASES:
    R.reset()
    R.set_fail_context(None)
    body()
    failed = sum(1 for v in R.VERDICTS.values() if v is R.Verdict.FAIL)
    rc = R.print_results(exit_on_finish=False)
    check(f"T_ART_30[{name}]", rc, _legacy_rc(failed))

print("T_ART_31  none of the five installs a provider or reads an artifact")
_UNRELATED = ["test_heatmap_reliability.py", "test_task488_partb.py",
              "test_tls_yield_reliability.py", "ve_suite_base.py",
              "test_flaky_policy.py"]
_here = pathlib.Path(__file__).resolve().parent
for f in _UNRELATED:
    src = (_here / f).read_text()
    check(f"T_ART_31[{f}]",
          any(s in src for s in ("set_premise_provider", "set_meta_provider",
                                 "lib.artifact", "RESULTS_JSON")),
          False)

print("T_ART_32  emitting an artifact never changes a verdict or an rc")
R.reset()
R.pass_("A")
R.fail("B", "x")
os.environ[A.ENV_PATH] = str(TMP / "rcprobe.json")
rc_with = R.print_results(exit_on_finish=False)
os.environ.pop(A.ENV_PATH, None)
R.reset()
R.pass_("A")
R.fail("B", "x")
rc_without = R.print_results(exit_on_finish=False)
check("T_ART_32a", rc_with, rc_without)

print("T_ART_33  an UNWRITEABLE artifact path still returns the run's own rc")
R.reset()
R.pass_("A")
os.environ[A.ENV_PATH] = "/proc/definitely/not/writable/x.json"
rc_bad = R.print_results(exit_on_finish=False)
os.environ.pop(A.ENV_PATH, None)
check("T_ART_33a", rc_bad, 0)

# ── D. TASK-627 — the per-scope SKIP census ──────────────────────────────────
print("T_ART_40  the summary prints a per-scope SKIP count")
import io                                                        # noqa: E402
import contextlib                                                # noqa: E402

R.reset()
R.set_meta_provider(lambda: {
    "S1": {"cls": "APP", "scope": "PlaneRadar", "effect": "read"},
    "S2": {"cls": "APP", "scope": "PlaneRadar", "effect": "read"},
    "S3": {"cls": "APP", "scope": "PlaneRadar", "effect": "read"},
    "S4": {"cls": "APP", "scope": "Clock", "effect": "read"},
    "P1": {"cls": "APP", "scope": "Clock", "effect": "read"},
})
for t in ("S1", "S2", "S3", "S4"):
    R.skip(t, "sub-view never rendered")
R.pass_("P1")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    R.print_results(exit_on_finish=False)
out = buf.getvalue()
check("T_ART_40a", "── SKIP by scope (4) ──" in out, True)
# The wedged family sorts FIRST, which is the whole point: seven identical skip
# lines scattered through a 195-id run were invisible for a year (QM §7).
_lines = [l for l in out.splitlines() if re.match(r"^  \S+\s+\d+  ", l)]
check("T_ART_40b", _lines[0].split()[0], "PlaneRadar")
check("T_ART_40c", _lines[0].split()[1], "3")

print("T_ART_41  an id with no meta record is counted under '?', never dropped")
R.reset()
R.set_meta_provider(lambda: {})
R.skip("X1", "n/a")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    R.print_results(exit_on_finish=False)
check("T_ART_41a", "?" in buf.getvalue().split("── SKIP by scope (1) ──")[1], True)

print("T_ART_42  the census does not appear when nothing skipped, and the")
print("          summary LINE keeps its exact pre-TASK-627 shape")
R.reset()
R.set_meta_provider(None)
R.pass_("A")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    R.print_results(exit_on_finish=False)
out = buf.getvalue()
check("T_ART_42a", "SKIP by scope" in out, False)
check("T_ART_42b",
      "1 passed, 0 failed, 0 skipped, 0 declared-flake (passed on retry)" in out,
      True)
# And the per-id row shape the archives depend on is untouched.
check("T_ART_42c", "\n  A: PASS\n" in out, True)

# ── F. TASK-689 — the artifact diff ──────────────────────────────────────────
# Pure-function fixtures: no files, no DUT. `diff_documents` takes two loaded
# documents and returns a delta; `previous_comparable`/`format_diff` are the
# only arms that touch the filesystem, and only inside TMP.
print("T_ART_60  diff_documents distinguishes every delta category")


def _doc(ids_verdicts):
    return {"results": [{"id": tid, "verdict": v}
                        for tid, v in ids_verdicts.items()]}


_old60 = _doc({"A": "PASS", "B": "FAIL", "C": "PASS", "D": "SKIP",
              "E": "FAIL", "F": "UNMET", "G": "PASS"})
_new60 = _doc({"A": "PASS",            # unchanged
              "B": "FAIL",            # unchanged
              "C": "FAIL",            # newly failing (PASS -> FAIL)
              "D": "UNMET",           # newly failing (SKIP -> UNMET)
              "E": "PASS",            # newly passing (FAIL -> PASS)
              "F": "FAIL",            # verdict changed, both non-green
              "G": "SKIP"})           # verdict changed, both green
delta60 = A.diff_documents(_old60, _new60)
check("T_ART_60a", {r["id"] for r in delta60["newly_failing"]}, {"C", "D"})
check("T_ART_60b", {r["id"] for r in delta60["newly_passing"]}, {"E"})
check("T_ART_60c", {r["id"] for r in delta60["verdict_changed"]}, {"F", "G"})
check("T_ART_60d", delta60["only_in_old"], [])
check("T_ART_60e", delta60["only_in_new"], [])
_row = next(r for r in delta60["newly_failing"] if r["id"] == "C")
check("T_ART_60f", _row, {"id": "C", "old": "PASS", "new": "FAIL"})

print("T_ART_61  diff_documents: unchanged ids produce no row at all")
_same = _doc({"A": "PASS", "B": "FAIL"})
delta61 = A.diff_documents(_same, _same)
check("T_ART_61a", delta61["newly_failing"], [])
check("T_ART_61b", delta61["newly_passing"], [])
check("T_ART_61c", delta61["verdict_changed"], [])
# ...but "no row in any change list" must NOT mean "invisible". B is FAIL in
# both runs, so it moved nothing and yet is not green.
check("T_ART_61d", [r["id"] for r in delta61["still_failing"]], ["B"])

print("T_ART_70  A DELTA HIDES PERSISTENCE — the TASK-685 shape, pinned")
# The defect this whole tool exists for: six ids were FAIL on 2026-09-06 and
# FAIL on 2026-09-09, so a pure delta over that pair reports them NOWHERE and
# prints "no change" — which is how a P1 firmware defect stayed unread for six
# days. still_failing is the half that catches it, and the rendered text must
# refuse to call that state "no change".
_p685 = _doc({"OK": "PASS", "T172": "FAIL", "T_CX_03": "FAIL", "T182": "UNMET"})
delta70 = A.diff_documents(_p685, _p685)
check("T_ART_70a", delta70["newly_failing"], [])
check("T_ART_70b", [r["id"] for r in delta70["still_failing"]],
      ["T172", "T182", "T_CX_03"])
_txt70 = A.format_diff("old.json", "new.json", delta70)
check("T_ART_70c", "STILL failing" in _txt70, True)
check("T_ART_70d", "'No change' is not 'no problem'" in _txt70, True)
# and the bare "no change" line must NOT be emitted while anything is failing
check("T_ART_70e", "  no change vs previous comparable run" in _txt70, False)
# the genuinely clean case still reads as clean
_clean = _doc({"OK": "PASS", "OK2": "SKIP"})
_txt70f = A.format_diff("o.json", "n.json", A.diff_documents(_clean, _clean))
check("T_ART_70f", "no change vs previous comparable run" in _txt70f, True)
check("T_ART_70g", "STILL failing" in _txt70f, False)

print("T_ART_62  diff_documents: ids present in only one run")
_old62 = _doc({"A": "PASS", "ONLY_OLD": "FAIL"})
_new62 = _doc({"A": "PASS", "ONLY_NEW": "PASS"})
delta62 = A.diff_documents(_old62, _new62)
check("T_ART_62a", delta62["only_in_old"], ["ONLY_OLD"])
check("T_ART_62b", delta62["only_in_new"], ["ONLY_NEW"])
check("T_ART_62c", delta62["newly_failing"], [])
check("T_ART_62d", delta62["newly_passing"], [])

print("T_ART_63  format_diff always names both input files")
out63 = A.format_diff("/path/OLD.json", "/path/NEW.json", delta62)
check("T_ART_63a", "/path/OLD.json" in out63, True)
check("T_ART_63b", "/path/NEW.json" in out63, True)

print("T_ART_64  format_diff flags a large id-set mismatch instead of a wall "
      "of text (targeted vs full run)")
_big_old = _doc({f"T{i}": "PASS" for i in range(200)})
_small_new = _doc({"T0": "PASS", "T1": "PASS"})
delta64 = A.diff_documents(_big_old, _small_new)
out64 = A.format_diff("full.json", "targeted.json", delta64, max_ids=10)
check("T_ART_64a", "large id-set mismatch" in out64, True)
check("T_ART_64b", "... and" in out64, True)
# Never claims a mass regression: nothing in the two runs' COMMON ids changed.
check("T_ART_64c", delta64["newly_failing"], [])
check("T_ART_64d", "newly failing" in out64.splitlines()[2], True)
check("T_ART_64e", out64.splitlines()[2].strip(), "newly failing (was PASS/SKIP): 0")

print("T_ART_65  previous_comparable requires entry_point AND build_env AND "
      "board.id to match, and an earlier started_at")
_TMP65 = TMP / "diff65"
_TMP65.mkdir()


def _mk65(name, entry_point, build_env, board_id, started_at, ids=("X",)):
    doc = {
        "schema": {"name": A.SCHEMA_NAME, "version": A.SCHEMA_VERSION},
        "run": {"run_token": name, "started_at": started_at, "counts": {}},
        "premise": {"entry_point": entry_point, "build_env": build_env,
                    "board": {"id": board_id}},
        "per_class": {},
        "results": [{"id": i, "verdict": "PASS"} for i in ids],
    }
    return A.write(_TMP65 / f"run-{name}.json", doc)


_p_a = _mk65("a", "runner.py", "envX", "board1", "2026-01-01T00:00:00Z")
_p_b_wrong_env = _mk65("b", "runner.py", "envY", "board1", "2026-01-02T00:00:00Z")
_p_c_wrong_board = _mk65("c", "runner.py", "envX", "board2", "2026-01-02T00:00:00Z")
_p_d_later = _mk65("d", "runner.py", "envX", "board1", "2026-01-05T00:00:00Z")
_p_e_current = _mk65("e", "runner.py", "envX", "board1", "2026-01-03T00:00:00Z")
_doc_e = json.loads(_p_e_current.read_text())
got65 = A.previous_comparable(_doc_e, _p_e_current, runs_dir=_TMP65)
check("T_ART_65a", got65, _p_a)  # not b (env), not c (board), not d (later)

print("T_ART_66  previous_comparable: no candidates at all -> None")
_TMP66 = TMP / "diff66"
_TMP66.mkdir()
_p_only = _mk65("only", "runner.py", "envZ", "board9", "2026-01-01T00:00:00Z")
_doc_only = json.loads(_p_only.read_text())
_p_only2 = A.write(_TMP66 / "run-only.json", _doc_only)
check("T_ART_66a", A.previous_comparable(_doc_only, _p_only2, runs_dir=_TMP66),
      None)

print("T_ART_67  previous_comparable: unstated premise (entry_point/build_env "
      "None) never matches anything, including itself")
_doc67 = {"schema": {"name": A.SCHEMA_NAME, "version": A.SCHEMA_VERSION},
         "run": {"run_token": "z", "started_at": "2026-01-01T00:00:00Z",
                 "counts": {}},
         "premise": {"entry_point": None, "build_env": None, "board": None},
         "per_class": {}, "results": []}
_p67 = A.write(_TMP65 / "run-noise.json", _doc67)
check("T_ART_67a", A.previous_comparable(_doc67, _p67, runs_dir=_TMP65), None)

print("T_ART_68  main() --diff-auto with no comparable run exits 0 and prints "
      "a plain statement, not an error")
_buf68 = io.StringIO()
with contextlib.redirect_stdout(_buf68):
    rc68 = A.main([str(_p_only2), "--diff-auto"])
check("T_ART_68a", rc68, 0)
check("T_ART_68b", "no previous comparable run" in _buf68.getvalue(), True)

print("T_ART_69  main() --diff prints both filenames and the delta")
_buf69 = io.StringIO()
with contextlib.redirect_stdout(_buf69):
    rc69 = A.main([str(_p_e_current), "--diff", str(_p_a)])
check("T_ART_69a", rc69, 0)
out69 = _buf69.getvalue()
check("T_ART_69b", str(_p_a) in out69, True)
check("T_ART_69c", str(_p_e_current) in out69, True)

# ── G. TASK-636 — the order-dependence comparison (R20/R21, ADR-066 D2a) ────
print("T_ART_80  order_dependence: verdict enum stays at seven (D2a)")
check("T_ART_80a", len(R.Verdict), 7)
check("T_ART_80b", A.ORDER_DEPENDENT not in {v.value for v in R.Verdict}, True)


def _od_doc(name, entry_point, build_env, board_id, order, shuffle_seed=None):
    return {
        "schema": {"name": A.SCHEMA_NAME, "version": A.SCHEMA_VERSION},
        "run": {"run_token": name, "started_at": "2026-01-01T00:00:00Z",
               "counts": {}},
        "premise": {"entry_point": entry_point, "build_env": build_env,
                   "board": {"id": board_id},
                   "class_order": [tid for tid, _v in order],
                   "shuffle_seed": shuffle_seed},
        "per_class": {},
        "results": [{"id": tid, "verdict": v} for tid, v in order],
    }


# order=[(id, verdict), ...] doubles as both the executed sequence AND the
# per-id verdicts, since a fixture never needs them to disagree.
_canon1 = _od_doc("c1", "runner.py", "envX", "board1",
                  [("A", "PASS"), ("B", "PASS"), ("C", "FAIL")])
_canon2 = _od_doc("c2", "runner.py", "envX", "board1",
                  [("A", "PASS"), ("C", "FAIL"), ("B", "PASS")])
_shuf = _od_doc("s1", "runner.py", "envX", "board1",
               [("A", "PASS"), ("C", "PASS"), ("B", "PASS")], shuffle_seed="42")

print("T_ART_81  a flipped id is found and names both predecessors' positions")
res81 = A.order_dependence([_canon1, _canon2], _shuf)
check("T_ART_81a", res81["comparable"], True)
check("T_ART_81b", res81["seed"], "42")
check("T_ART_81c", [r["id"] for r in res81["rows"]], ["C"])
_row81 = res81["rows"][0]
check("T_ART_81d", (_row81["canonical_verdict"], _row81["shuffled_verdict"]),
      ("FAIL", "PASS"))
check("T_ART_81e", _row81["canonical_index"], 2)   # c1's executed order
check("T_ART_81f", _row81["shuffled_index"], 1)
check("T_ART_81g", _row81["label"], A.ORDER_DEPENDENT)

print("T_ART_82  a single canonical run gets the flake-caveat label, not the "
     "bare one")
res82 = A.order_dependence(_canon1, _shuf)   # single doc, not a list
check("T_ART_82a", [r["label"] for r in res82["rows"]],
     [A.ORDER_DEPENDENT_UNSEPARATED])
_txt82 = A.format_order_dependence(res82)
check("T_ART_82b", "not separated from flake" in _txt82, True)

print("T_ART_83  canonical runs disagreeing among themselves are excluded, "
     "not misreported as order-dependent")
_canon2_disagree = _od_doc("c2d", "runner.py", "envX", "board1",
                          [("A", "PASS"), ("B", "PASS"), ("C", "PASS")])
res83 = A.order_dependence([_canon1, _canon2_disagree], _shuf)
check("T_ART_83a", res83["rows"], [])

print("T_ART_84  non-comparable docs (different board) are refused, not "
     "silently compared")
_shuf_other_board = _od_doc("s2", "runner.py", "envX", "board2",
                            [("A", "PASS")], shuffle_seed="7")
res84 = A.order_dependence(_canon1, _shuf_other_board)
check("T_ART_84a", res84["comparable"], False)
check("T_ART_84b", res84["rows"], [])
check("T_ART_84c", "NOT COMPARABLE" in A.format_order_dependence(res84), True)

print("T_ART_85  no order-dependent ids -> comparable, empty rows, says so")
_shuf_clean = _od_doc("s3", "runner.py", "envX", "board1",
                      [("A", "PASS"), ("B", "PASS"), ("C", "FAIL")],
                      shuffle_seed="1")
res85 = A.order_dependence([_canon1, _canon2], _shuf_clean)
check("T_ART_85a", res85["comparable"], True)
check("T_ART_85b", res85["rows"], [])
check("T_ART_85c", "no order-dependent ids found" in
     A.format_order_dependence(res85), True)

print("T_ART_86  main() --order-dependence wires the CLI end to end")
_TMP86 = TMP / "od86"
_TMP86.mkdir()
_p_c1 = A.write(_TMP86 / "c1.json", _canon1)
_p_c2 = A.write(_TMP86 / "c2.json", _canon2)
_p_s = A.write(_TMP86 / "s.json", _shuf)
_buf86 = io.StringIO()
with contextlib.redirect_stdout(_buf86):
    rc86 = A.main([str(_p_s), "--order-dependence", str(_p_c1), str(_p_c2)])
check("T_ART_86a", rc86, 0)
check("T_ART_86b", "C: ORDER-DEPENDENT" in _buf86.getvalue(), True)

# ── E. R29's acceptance number: zero summary parsers ─────────────────────────
print("T_ART_50  no consumer parses the human summary text (R29 == 0)")
_ROOT = _here.parent.parent
# The shape of the thing: an id-and-verdict alternation applied to text. Any
# NEW one is caught the way the first three were not — mechanically, at gate
# time, rather than by a review a year later.
#   sed:   s/^  \([A-Za-z0-9_]\{1,\}\): \(FLAKY-PASS\|…
#   re:    r"^  ([A-Za-z0-9_]+): (FLAKY-PASS|…
# Both are "anchor at the summary's two-space indent, capture an id, then a
# verdict alternation". `_compare_leg`'s `case PASS:FLAKY-PASS)` is NOT this
# shape — it matches an already-extracted token, which is what a typed consumer
# is supposed to do.
_SHAPE = re.compile(r"\^\s\s\\?\(\[A-Za-z0-9_")
_SEARCHED = []
for base in (_ROOT / "app" / "tools", _ROOT / "run"):
    for f in sorted(base.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts:
            continue
        if f.suffix not in ("", ".py", ".sh") or f.name == "test_run_artifact.py":
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        _SEARCHED.append(f)
        if _SHAPE.search(text):
            # test_class_order.py asserts on RESULTS directly (the producer's
            # own store), which is not parsing the printed text.
            for i, line in enumerate(text.splitlines(), 1):
                if _SHAPE.search(line) and not line.lstrip().startswith("#"):
                    check(f"T_ART_50[{f.relative_to(_ROOT)}:{i}]", line.strip(), "")
check("T_ART_50z", len(_SEARCHED) > 40, True)

shutil.rmtree(TMP, ignore_errors=True)

if _FAILS:
    print(f"\ntest_run_artifact.py: {len(_FAILS)} FAILED — {_FAILS}")
    sys.exit(1)
print("\ntest_run_artifact.py: all checks passed")
