#!/usr/bin/env python3
"""test_triage_context.py — mode P, passive failure triage (TASK-571).

Host-only, no DUT, sub-second. Wired into smoke_test.sh.

Why this exists: mode P (M-TESTARCH §14.2 / EC-T1) puts the session's health
verdict, `last-phase=`, `gen=` and the failing id's `(cls, scope)` onto every
FAIL record. That record is a STRING that other tools parse — `run/player-gate`
scores a run with a line-oriented sed over the summary — and TASK-573 was a live
gate defect where exactly such a status string silently failed to parse. The
format is therefore pinned here rather than discovered on a gate run.

It also pins the two properties that make mode P safe to have on unconditionally:

  * it never touches the device (modes D and I, which would, are CUT — §20), and
  * a broken provider degrades to the pre-TASK-571 record instead of changing a
    verdict or raising out of fail().
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lib import results as R                            # noqa: E402
from suite.serialdbg import _triage                     # noqa: E402

_failures = []


def check(label, got, want):
    if got != want:
        _failures.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}: {got}")


def check_in(label, needle, hay):
    if needle not in hay:
        _failures.append(f"{label}: {needle!r} not in {hay!r}")
        print(f"  FAIL {label}: {needle!r} not in {hay!r}")
    else:
        print(f"  ok   {label}")


class _FakeDut:
    """Reads only. If mode P ever grows a device call, this object has none and
    the test that exercises it will raise rather than silently pass."""

    def __init__(self, last_phase="6 ready", gen="7.1"):
        self._lp = last_phase
        self._gen = gen

    def last_phase(self):
        return self._lp

    def gen_tag(self):
        return self._gen


def _meta(cls="FEATURE", scope="LocalPlayer"):
    return {"T_PLR_25": {"id": "T_PLR_25", "cls": cls, "scope": scope,
                         "effect": "mutating"}}


# ── T_TRI_01  the record's shape ─────────────────────────────────────────────
print("T_TRI_01  context line carries all four EC-T1 fields, in order")
line = _triage.context("T_PLR_25", _FakeDut(), _meta())
check("T_TRI_01a", line,
      '[triage] health=unavailable(no-HEALTH-class;TASK-565) '
      'last-phase="6 ready" gen=7.1 cls=FEATURE scope=LocalPlayer')

print("T_TRI_02  a multi-word last-phase is quoted, so the fields stay separable")
check("T_TRI_02a", '"6 ready"' in line, True)

print("T_TRI_03  no boot observed -> gen=?, and it is not tidied away")
check("T_TRI_03a", "gen=?" in _triage.context("T_PLR_25", _FakeDut(gen="?"), _meta()), True)
print("T_TRI_04  no phase line seen -> last-phase=none, distinct from '?'")
check("T_TRI_04a",
      "last-phase=none" in _triage.context("T_PLR_25", _FakeDut(last_phase=None), _meta()), True)
print("T_TRI_05  an id with no record degrades per-field, not by omission")
check("T_TRI_05a", "cls=? scope=?" in _triage.context("T_NOPE", _FakeDut(), _meta()), True)


# ── health verdict, including the TASK-565 degradation ───────────────────────
print("T_TRI_06  no HEALTH class in the registry -> unavailable, never 'ok'")
check("T_TRI_06a", _triage.health_verdict(_meta(), {}),
      "unavailable(no-HEALTH-class;TASK-565)")

_h = {"T_DH_01": {"cls": "HEALTH"}, "T_DH_02": {"cls": "HEALTH"}}
print("T_TRI_07  HEALTH ids present but not run -> not-run, not 'ok'")
check("T_TRI_07a", _triage.health_verdict(_h, {}), "not-run(0/2)")
print("T_TRI_08  all HEALTH ids PASS -> ok")
check("T_TRI_08a", _triage.health_verdict(_h, {"T_DH_01": "PASS", "T_DH_02": "PASS"}), "ok")
print("T_TRI_09  a failing HEALTH id is named")
check("T_TRI_09a", _triage.health_verdict(_h, {"T_DH_01": "PASS", "T_DH_02": "FAIL: x"}),
      "FAIL(T_DH_02)")
print("T_TRI_10  FLAKY-PASS is NOT a pass — degraded, not ok (results.py policy)")
check("T_TRI_10a",
      _triage.health_verdict(_h, {"T_DH_01": "PASS", "T_DH_02": "FLAKY-PASS: a | b"}),
      "degraded(T_DH_02)")
print("T_TRI_11  a SKIPped HEALTH id is not health either")
check("T_TRI_11a", _triage.health_verdict(_h, {"T_DH_01": "PASS", "T_DH_02": "SKIP: n/a"}),
      "degraded(T_DH_02)")
print("T_TRI_12  a partly-run HEALTH set says so")
check("T_TRI_12a", _triage.health_verdict(_h, {"T_DH_01": "PASS"}), "ok(1/2)")


# ── the hook in lib/results.py ───────────────────────────────────────────────
print("T_TRI_13  with no provider installed, fail() is byte-identical to before")
R.set_fail_context(None)
R.reset()
R.fail("T_X", "boom")
check("T_TRI_13a", R.RESULTS["T_X"], "FAIL: boom")

print("T_TRI_14  with mode P installed, the FAIL record carries the context")
R.reset()
R.set_fail_context(_triage.make_provider(_FakeDut(), _meta()))
R.fail("T_PLR_25", "boom")
rec = R.RESULTS["T_PLR_25"]
check_in("T_TRI_14a", "FAIL: boom  [triage] ", rec)
check_in("T_TRI_14b", "gen=7.1 cls=FEATURE scope=LocalPlayer", rec)

print("T_TRI_15  the record still starts with FAIL — run/player-gate's parser")
# `sed -n 's/^  \([A-Za-z0-9_]\{1,\}\): \(FLAKY-PASS\|...\|FAIL\|...\).*/\1 \2/p'`
import re                                                        # noqa: E402
summary = f"  T_PLR_25: {rec}"
m = re.match(r"^  ([A-Za-z0-9_]+): (FLAKY-PASS|NOT-RUN|PASS|FAIL|SKIP|FLAKE).*", summary)
check("T_TRI_15a", (m.group(1), m.group(2)) if m else None, ("T_PLR_25", "FAIL"))

print("T_TRI_16  the annotated record is exactly one line")
check("T_TRI_16a", "\n" in rec, False)

print("T_TRI_17  annotation is idempotent — never appended twice")
check("T_TRI_17a", rec.count("[triage]"), 1)
check("T_TRI_17b", R._annotate("T_PLR_25", rec), rec)

print("T_TRI_18  a provider that raises degrades to the plain record")
R.reset()
def _boom(tid):
    raise RuntimeError("provider is broken")
R.set_fail_context(_boom)
R.fail("T_Y", "boom")
check("T_TRI_18a", R.RESULTS["T_Y"], "FAIL: boom")

print("T_TRI_19  a multi-line context is flattened, not passed through")
R.reset()
R.set_fail_context(lambda tid: "[triage] a=1\nb=2")
R.fail("T_Z", "boom")
check("T_TRI_19a", R.RESULTS["T_Z"], "FAIL: boom  [triage] a=1 b=2")

print("T_TRI_20  a reproduced declared flake's FAIL is annotated too")
R.reset()
R.set_fail_context(_triage.make_provider(_FakeDut(), _meta()))
R.RESULTS["T_Q"] = "FAIL: declared flake REPRODUCED on retry — x"
check("T_TRI_20a", "[triage]" in R._annotate("T_Q", R.RESULTS["T_Q"]), True)

print("T_TRI_21  modes D and I are not built — no flag, no entry point")
_runner = (pathlib.Path(__file__).resolve().parent
           / "suite" / "serialdbg" / "runner.py").read_text()
for _flag in ("--triage", "--isolate-on-fail"):
    check(f"T_TRI_21 {_flag} is not an argument",
          f'add_argument("{_flag}"' in _runner, False)
check("T_TRI_21c  no standalone triage script (EC-T5)",
      (pathlib.Path(__file__).resolve().parents[2] / "run" / "dut-triage").exists(), False)

# ── T_TRI_22  the TASK-565 transition, against the LIVE registry ─────────────
# The cheapest possible end-to-end check that both halves are wired: mode P said
# `unavailable(no-HEALTH-class;TASK-565)` for exactly as long as no id resolved
# to cls=HEALTH. If health.py's decorations ever stop resolving — a dropped
# @meta(cls=...), a family module rename, a registry that stops being merged
# into build_all_meta() — the verdict silently reverts to "unavailable" and
# every FAIL in every run loses its health context with nothing printed.
print("T_TRI_22  the live registry HAS a HEALTH class (TASK-565 landed)")
import suite.serialdbg as _live_suite                                # noqa: E402
_live = _live_suite.build_all_meta()
_live_health = sorted(t for t, r in _live.items() if r["cls"] == "HEALTH")
check("T_TRI_22a  the three ids", _live_health, ["T_DH_01", "T_DH_02", "T_DH_03"])
check("T_TRI_22b  verdict is no longer 'unavailable'",
      _triage.health_verdict(_live, {}), "not-run(0/3)")
check("T_TRI_22c  and reports for real once they run",
      _triage.health_verdict(_live, {t: "PASS" for t in _live_health}), "ok")
check("T_TRI_22d  a failing health id is named from the live registry",
      _triage.health_verdict(_live, {"T_DH_01": "PASS", "T_DH_02": "FAIL: x",
                                     "T_DH_03": "PASS"}), "FAIL(T_DH_02)")

R.set_fail_context(None)
R.reset()

print()
if _failures:
    print(f"FAILED ({len(_failures)}):")
    for f in _failures:
        print(f"  - {f}")
    sys.exit(1)
print("test_triage_context.py: all checks passed")
