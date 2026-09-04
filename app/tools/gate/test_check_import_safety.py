#!/usr/bin/env python3
"""Negative tests for check_import_safety.py — BP-068. TASK-609 / R48.

A gate that has never been seen to fail is not a gate, and this one has a second
obligation on top: it must be shown that the CHECKER cannot open the real port
while proving that nothing else does. Case B4 is that proof — a probe module
reports what its `serial` module actually is, and the assertion is that it is the
in-memory stub, not the installed pyserial.

Every case writes a throwaway module into a temp directory and runs the real
checker over it. Two positive controls guard the other direction: a clean module
produces no finding, and a module that merely exits at import is reported as
skipped rather than failed — a gate that cannot tell "touched the board" from
"could not be imported" would be unusable on this tree, where 12 modules do not
import standalone for unrelated reasons.

No DUT, no serial port, no build, no network.
Run: python3 app/tools/gate/test_check_import_safety.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import check_import_safety as C                        # noqa: E402

_TMP: list[str] = []


def probe(body: str, name: str) -> str:
    """Write `body` to a module under the repo root and return its rel path.

    The checker resolves modules relative to the repo root, so the probes live
    in a temp directory *inside* it and are removed at the end of the run.
    """
    d = os.path.join(C.ROOT, ".h2-import-safety-probes")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(body)
    _TMP.append(p)
    return os.path.relpath(p, C.ROOT).replace(os.sep, "/")


def findings(rels, per_timeout: int = 8):
    return C.evaluate(C.run(rels, per_timeout=per_timeout))


def one(fs, needle):
    hits = [f for f in fs if needle in f]
    assert hits, f"expected a finding containing {needle!r}, got {fs}"
    return hits


def none(fs):
    assert not fs, f"expected no findings, got {fs}"


# ── negative cases: the checker must catch these ─────────────────────────────

def case_serial_at_import():
    rel = probe("import serial\nserial.Serial('/dev/ttyUSB0', 115200)\n",
                "p_serial.py")
    one(findings([rel]), "serial.Serial")


def case_builtin_open_on_tty():
    rel = probe("open('/dev/ttyUSB0', 'rb')\n", "p_open.py")
    one(findings([rel]), "via open")


def case_os_open_on_tty():
    rel = probe("import os\nos.open('/dev/ttyUSB0', os.O_RDWR)\n", "p_osopen.py")
    one(findings([rel]), "via os.open")


def case_swallowed_exception_is_still_caught():
    """The RECORDING is the detector, not the exception.

    A module that wraps its port open in a bare `except` would defeat any
    checker that inferred the touch from the child's exit code or traceback.
    """
    rel = probe("import serial\n"
                "try:\n"
                "    serial.Serial('/dev/ttyUSB0')\n"
                "except Exception:\n"
                "    pass\n", "p_swallow.py")
    one(findings([rel]), "serial.Serial")


def case_hang_is_a_finding():
    """An import that never terminates is an import-time side effect too — it is
    how a module-level poll loop presents."""
    rel = probe("while True:\n    pass\n", "p_hang.py")
    one(findings([rel], per_timeout=2), "did not terminate")


def case_reimport_after_clearing_sys_modules_still_stubbed():
    """Barrier 2: a module that deletes the sys.modules entry and imports again
    must still get the stub, not pyserial."""
    rel = probe("import sys\n"
                "sys.modules.pop('serial', None)\n"
                "import serial\n"
                "serial.Serial('/dev/ttyUSB0')\n", "p_reimport.py")
    fs = findings([rel])
    # Either the on-disk stub raised (recorded as a skip, no trip) or the
    # in-memory stub tripped; what must NEVER happen is a real port open. The
    # assertion is that the checker did not silently pass a module that reached
    # a `Serial(...)` call — one of the two stub layers has to have answered.
    res = C.run([rel])
    reached_stub = bool(fs) or any(
        "import-safety stub" in why or "at import time" in why
        for _m, why in res["skipped"])
    assert reached_stub, f"neither stub layer answered: {res}"


def case_child_death_is_attributed():
    """`os._exit` at module level kills the child; the progress log must still
    name the module that did it."""
    rel = probe("import os\nos._exit(0)\n", "p_hardexit.py")
    one(findings([rel]), "died without finishing")


# ── positive controls: the checker must NOT flag these ───────────────────────

def case_clean_module_is_clean():
    rel = probe("VALUE = 1\n\n\ndef main():\n    return VALUE\n", "p_clean.py")
    none(findings([rel]))


def case_guarded_module_is_clean():
    """The exact shape the six fixed modules now have."""
    rel = probe("import serial\n\n\n"
                "def main():\n"
                "    serial.Serial('/dev/ttyUSB0')\n\n\n"
                'if __name__ == "__main__":\n'
                "    main()\n", "p_guarded.py")
    none(findings([rel]))


def case_unrelated_import_failure_is_not_a_failure():
    rel = probe("import a_package_that_does_not_exist_h2\n", "p_missingdep.py")
    res = C.run([rel])
    none(C.evaluate(res))
    assert res["skipped"], "an unimportable module must be reported as skipped"


def case_sys_exit_at_import_is_not_a_failure():
    rel = probe("import sys\nsys.exit(2)\n", "p_sysexit.py")
    res = C.run([rel])
    none(C.evaluate(res))
    assert res["skipped"], "a SystemExit at import must be reported as skipped"


# ── the checker's own safety ─────────────────────────────────────────────────

def case_child_sees_the_stub_not_pyserial():
    """B4 — the proof that the gate itself cannot open the real port.

    The probe records what `serial` resolves to inside the child. The stub is an
    in-memory `types.ModuleType` with no `__file__`; the installed pyserial has
    one. If this ever reports a real file path, the checker is running against
    the genuine transport and every other case here is worthless.
    """
    out = os.path.join(C.ROOT, ".h2-import-safety-probes", "serial_identity.txt")
    rel = probe("import serial, os\n"
                "with open(%r, 'w') as fh:\n"
                "    fh.write(repr(getattr(serial, '__file__', None)) + '|' +\n"
                "             repr(getattr(serial.Serial, '__qualname__', None)))\n"
                % out, "p_identity.py")
    _TMP.append(out)
    C.run([rel])
    got = open(out, encoding="utf-8").read()
    assert got.startswith("None|"), f"child did not get the in-memory stub: {got}"
    assert "_StubSerial" in got, f"child's Serial is not the stub: {got}"


def case_sentinel_port_is_not_a_device():
    """Barrier 4 — resolve_port() returns $PORT before shelling out to udevadm,
    so the sentinel must be a path that cannot be a serial device."""
    assert not os.path.exists(C.SENTINEL_PORT), \
        f"{C.SENTINEL_PORT} exists — pick a sentinel that cannot be a device"
    assert not C.SENTINEL_PORT.startswith("/dev/"), \
        "the sentinel port must not live under /dev/"


def case_live_tree_is_clean():
    """The positive control that matters: the real app/tools/ tree passes."""
    none(C.evaluate(C.run(C.module_files())))


def case_evaluate_is_pure():
    assert C.evaluate({"trips": [], "died": None, "rc": 0}) == []
    fs = C.evaluate({"trips": [("m.py", "serial.Serial", "port='x'")],
                     "died": None, "rc": 0})
    assert len(fs) == 1 and "m.py" in fs[0]


CASES = [
    ("N1  serial.Serial() at import",          case_serial_at_import),
    ("N2  open('/dev/tty*') at import",        case_builtin_open_on_tty),
    ("N3  os.open('/dev/tty*') at import",     case_os_open_on_tty),
    ("N4  swallowed exception still caught",   case_swallowed_exception_is_still_caught),
    ("N5  a hanging import is a finding",      case_hang_is_a_finding),
    ("N6  re-import after clearing modules",   case_reimport_after_clearing_sys_modules_still_stubbed),
    ("N7  os._exit is attributed",             case_child_death_is_attributed),
    ("P1  a clean module is clean",            case_clean_module_is_clean),
    ("P2  a __main__-guarded module is clean", case_guarded_module_is_clean),
    ("P3  missing dependency is not a fail",   case_unrelated_import_failure_is_not_a_failure),
    ("P4  SystemExit at import is not a fail", case_sys_exit_at_import_is_not_a_failure),
    ("B4  child sees the stub, not pyserial",  case_child_sees_the_stub_not_pyserial),
    ("B5  the sentinel port is not a device",  case_sentinel_port_is_not_a_device),
    ("P5  the live app/tools/ tree is clean",  case_live_tree_is_clean),
    ("U1  evaluate() is pure",                 case_evaluate_is_pure),
]


def main() -> int:
    failed = 0
    try:
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
    finally:
        for p in _TMP:
            try:
                os.remove(p)
            except OSError:
                pass
        d = os.path.join(C.ROOT, ".h2-import-safety-probes")
        try:
            os.rmdir(d)
        except OSError:
            pass
    print(f"test_check_import_safety: {len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
