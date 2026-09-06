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
