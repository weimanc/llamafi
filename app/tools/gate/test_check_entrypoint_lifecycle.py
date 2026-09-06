#!/usr/bin/env python3
"""Negative suite for ADR-067 / TASK-633 (BP-068).

Two subjects, both exercised with **no board and no serial port**:

1. ``gate/check_entrypoint_lifecycle.py`` — break it the way it is meant to
   catch. A gate that has never been shown to fail is a gate nobody has reason
   to believe (BP-068).

2. ``lib/verify_build.py`` — the refusal decision itself, driven against a
   **faked device**. Every board-side outcome ADR-067 names is produced by
   substituting the ``Dut`` constructor, so the mapping
   *condition → exit code → message* is proved on a host with nothing plugged
   in. The one thing this cannot prove is that the real firmware answers
   ``info`` with an ``elf`` field; that is DUT-owed and stated as such, not
   quietly claimed here (BP-074: an assertion whose precondition never occurred
   is inconclusive, not a pass).

Run: ``python3 gate/test_check_entrypoint_lifecycle.py``
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import shutil
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # app/tools
sys.path.insert(0, str(HERE))                 # app/tools/gate

import check_entrypoint_lifecycle as gate  # noqa: E402

FAILURES: list[str] = []
PASSES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASSES
    if cond:
        PASSES += 1
    else:
        FAILURES.append(f"{name}: {detail or 'assertion failed'}")


# ── fixtures ─────────────────────────────────────────────────────────────────

_LIB = """#!/usr/bin/env bash
ENV_PROD="cyd2usb_winamp"
ENV_DEBUG="cyd2usb_winamp_debug"
"""

_CLEAN_ENTRY = """#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
PORT=$(resolve_port)
require_build "$ENV_DEBUG" test "$PORT" || exit $?
_TEST_RC=0
_cleanup() { restart_monitor "$PORT"; exit "$_TEST_RC"; }
trap _cleanup EXIT INT TERM
"$VENV_PY" tools/suite/serialdbg/runner.py --port "$PORT" || _TEST_RC=$?
"""

_FLASHER = """#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
(cd "$PIO_DIR" && "$PIO" run -e "$ENV_PROD" -t upload --upload-port "$PORT")
"""


def _tree(entries: dict[str, str], docs: dict[str, str] | None = None) -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix="adr067-"))
    (root / "run").mkdir()
    (root / "run" / "lib.sh").write_text(_LIB)
    for name, body in entries.items():
        (root / "run" / name).write_text(body)
    (root / "docs").mkdir()
    for rel, body in (docs or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    (root / "CLAUDE.md").write_text("# nothing to see\n")
    return root


def _codes(findings: list[str]) -> set[str]:
    return {f.split(" ", 1)[0] for f in findings}


# ── 1. the gate ──────────────────────────────────────────────────────────────

def test_gate() -> None:
    # A1 — a clean tree passes.
    root = _tree({"test": _CLEAN_ENTRY, "flash": _FLASHER})
    try:
        check("A1 clean tree is clean", gate.check(root) == [], str(gate.check(root)))
    finally:
        shutil.rmtree(root)

    # A2 — the restore, re-introduced, is caught. THE central arm: this is the
    # exact regression the conversion exists to prevent.
    bad = _CLEAN_ENTRY + '(cd "$PIO_DIR" && "$PIO" run -e "$ENV_PROD" -t upload --upload-port "$PORT")\n'
    root = _tree({"test": bad})
    try:
        f = gate.check(root)
        check("A2 re-introduced restore caught", "C1" in _codes(f), str(f))
        check("A2 names the script", any("run/test" in x for x in f), str(f))
    finally:
        shutil.rmtree(root)

    # A3 — a restore hidden inside an EXIT trap is caught too. The original
    # defect's actual shape.
    trapped = _CLEAN_ENTRY.replace(
        '_cleanup() { restart_monitor "$PORT"; exit "$_TEST_RC"; }',
        '_cleanup() {\n  (cd "$PIO_DIR" && "$PIO" run -e "$ENV_PROD" -t upload --upload-port "$PORT")\n'
        '  restart_monitor "$PORT"; exit "$_TEST_RC"; }')
    root = _tree({"test": trapped})
    try:
        check("A3 restore inside the trap caught", "C1" in _codes(gate.check(root)))
    finally:
        shutil.rmtree(root)

    # A4 — flashing ANY build from a test entry point is caught (C2), not just
    # production. ADR-067 D1 is "never flashes", not "never flashes prod".
    root = _tree({"test": _CLEAN_ENTRY + '(cd "$PIO_DIR" && "$PIO" run -e "$ENV_DEBUG" -t upload --upload-port "$PORT")\n'})
    try:
        f = gate.check(root)
        check("A4 debug flash from a test entry point caught", "C2" in _codes(f), str(f))
    finally:
        shutil.rmtree(root)

    # A5 — run/flash IS allowed to flash. A gate that forbade this would forbid
    # the remedy its own message tells the reader to use.
    root = _tree({"flash": _FLASHER,
                  "flash-debug": _FLASHER.replace("ENV_PROD", "ENV_DEBUG")})
    try:
        check("A5 flashers may flash", gate.check(root) == [], str(gate.check(root)))
    finally:
        shutil.rmtree(root)

    # A6 — an entry point that does not declare its build is caught. Without
    # this arm the conversion could be "completed" by deleting the restore and
    # never adding the refusal, which is strictly worse than before.
    root = _tree({"test": _CLEAN_ENTRY.replace(
        'require_build "$ENV_DEBUG" test "$PORT" || exit $?\n', "")})
    try:
        check("A6 missing require_build caught", "C3" in _codes(gate.check(root)),
              str(gate.check(root)))
    finally:
        shutil.rmtree(root)

    # A7 — prose about the deleted restore is not the restore. The conversion
    # leaves comments everywhere saying what used to happen; a gate that read
    # them as violations would force those comments to be deleted, taking the
    # explanation with them.
    commented = _CLEAN_ENTRY + (
        '# was: (cd "$PIO_DIR" && "$PIO" run -e "$ENV_PROD" -t upload --upload-port "$PORT")\n')
    root = _tree({"test": commented})
    try:
        check("A7 a comment about the restore is not a restore",
              gate.check(root) == [], str(gate.check(root)))
    finally:
        shutil.rmtree(root)

    # A8 — a doc promising a restore is caught.
    root = _tree({"test": _CLEAN_ENTRY},
                 docs={"docs/process/x.md": "flash production (always restores prod firmware on exit)\n"})
    try:
        check("A8 restore promise in docs caught", "C4" in _codes(gate.check(root)),
              str(gate.check(root)))
    finally:
        shutil.rmtree(root)

    # A9 — an ADR quoting the old promise is exempt. The record of a removal
    # must be allowed to state what was removed (QM's rot rule (c)).
    root = _tree({"test": _CLEAN_ENTRY},
                 docs={"docs/architecture/decisions/ADR-067.md":
                       "the 'always restores prod firmware on exit' promise must be removed\n"})
    try:
        check("A9 the ADR may quote the promise it deleted",
              gate.check(root) == [], str(gate.check(root)))
    finally:
        shutil.rmtree(root)

    # A10 — the real repository is clean. The gate is only worth its exit code
    # if it is run against the tree it guards.
    real = HERE.parents[2]
    check("A10 real tree passes", gate.check(real) == [],
          "; ".join(gate.check(real))[:400])


# ── 2. the refusal decision, with the device faked ───────────────────────────

class _FakeSetupFailure(Exception):
    def __init__(self, reason, message, cls="RIG"):
        super().__init__(message)
        self.reason = reason
        self.cls = cls


def _install_fake_dut(behaviour):
    """Substitute lib.dut with a fake whose Dut() does `behaviour`.

    The device is entirely absent: no serial import, no port, no board. What is
    under test is the decision — which condition maps to which exit code and
    which words — and that is host logic.
    """
    mod = types.ModuleType("lib.dut")
    mod.SetupFailure = _FakeSetupFailure

    class _Dut:
        def __init__(self, port, log_file=None):
            behaviour(self)
        def close(self):
            pass

    mod.Dut = _Dut
    sys.modules["lib.dut"] = mod
    return mod


def test_verify() -> None:
    sys.path.insert(0, str(HERE.parent / "lib"))
    import importlib
    saved = sys.modules.pop("lib.dut", None)
    try:
        vb = importlib.import_module("lib.verify_build")

        # A tree with a built artifact, so the host-side half is satisfied and
        # the board-side half is what is being measured.
        root = pathlib.Path(tempfile.mkdtemp(prefix="adr067v-"))
        env = "cyd2usb_winamp_debug"
        bindir = root / ".pio" / "build" / env
        bindir.mkdir(parents=True)
        (bindir / "firmware.bin").write_bytes(b"\x00" * 256)

        def _verify(behaviour, e=env):
            _install_fake_dut(behaviour)
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                rc = vb.verify("/dev/null", e, "test-entry",
                               build_root=root / ".pio" / "build")
            return rc, buf_out.getvalue() + buf_err.getvalue()

        # B1 — the happy path. Board matches: exit 0, and it SAYS what it saw.
        def ok(d):
            d.board_id = "aabbccddeeff"
            d.board_id_source = "efuse-mac"
            d.elf = "deadbeef"
            d.elf_expected = "deadbeef"
        rc, out = _verify(ok)
        check("B1 matching build proceeds", rc == 0, f"rc={rc} out={out[:200]}")
        check("B1 names board and elf",
              "aabbccddeeff" in out and "deadbeef" in out, out[:200])

        # B2 — elf mismatch is REFUSED at 3, not 4. ADR-067 D2, the correction
        # the ADR records against its own review.
        def mismatch(d):
            raise _FakeSetupFailure("elf-mismatch", "flashed 1111 expected 2222")
        rc, out = _verify(mismatch)
        if True:
            check("B2 elf-mismatch exits 3", rc == 3, f"rc={rc}")
            check("B2 exit is not 4", rc != 4, f"rc={rc}")
            check("B2 refusal names wanted and found",
                  "WANTED" in out and "ON THE BOARD" in out, out[:300])
            check("B2 refusal says nothing was flashed or restored",
                  "does not flash" in out and "does not restore" in out, out[:400])
            check("B2 refusal is unmissable", "REFUSED" in out, out[:200])
            check("B2 refusal says no tests ran", "NO TESTS RAN" in out, out[:400])

        # B3 — production firmware is the same refusal, same code, different
        # words. Both reasons are RIG in M-TESTARCH's vocabulary.
        def prod(d):
            raise _FakeSetupFailure("prod-firmware-flashed", "console compiled out")
        rc, out = _verify(prod)
        if True:
            check("B3 prod firmware exits 3", rc == 3, f"rc={rc}")
            check("B3 says PRODUCTION", "PRODUCTION" in out, out[:300])

        # B4 — a HEALTH setup failure is 4, NOT 3. The polarity ADR-067 D2 is
        # careful about, in the other direction: a wrong build is not a sick
        # board and a sick board is not a wrong build.
        def unhealthy(d):
            raise _FakeSetupFailure("boot-not-observed", "no boot", cls="HEALTH")
        rc, out = _verify(unhealthy)
        if True:
            check("B4 HEALTH condition exits 4", rc == 4, f"rc={rc}")

        # B5 — no host artifact to compare against is a REFUSAL, not a warning.
        # "I could not verify" must not be allowed to proceed: a run that skips
        # the comparison is the state ADR-067 exists to end.
        rc, out = _verify(ok, e="cyd2usb_no_such_env_at_all")
        check("B5 unverifiable is refused", rc == 3, f"rc={rc}")
        check("B5 says it could not compare", "no host artifact" in out, out[:300])

        # B6 — an unexpected exception is a refusal with a code, never a
        # traceback. A preflight that crashes is indistinguishable from a broken
        # harness, and the reader cannot tell which.
        def boom(d):
            raise OSError("could not open /dev/null")
        rc, out = _verify(boom)
        if True:
            check("B6 unexpected error is a coded refusal", rc == 3, f"rc={rc}")
            check("B6 no traceback", "Traceback" not in out, out[:200])

        # B7 — a run that states no build at all is a HOST error (2), not a
        # silent proceed.
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = vb.main(["--port", "/dev/null", "--env", ""])
        check("B7 no declared build is a host error", rc == 2, f"rc={rc}")

        shutil.rmtree(root)
    finally:
        sys.modules.pop("lib.dut", None)
        if saved is not None:
            sys.modules["lib.dut"] = saved


def main() -> int:
    test_gate()
    test_verify()
    print(f"check_entrypoint_lifecycle negative suite: {PASSES} passed, "
          f"{len(FAILURES)} failed")
    for f in FAILURES:
        print(f"  FAIL {f}")
    if FAILURES:
        return 1
    print("NOTE (BP-074): every board-side arm above ran against a FAKED Dut. "
          "That the real firmware answers `info` with an `elf` field is "
          "DUT-owed and is not claimed here.")
    return 0


if __name__ == "__main__":  # pragma: no cover — TASK-609 import-safety guard
    sys.exit(main())
