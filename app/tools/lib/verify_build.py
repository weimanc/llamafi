#!/usr/bin/env python3
"""Read what is on the board; refuse if it is not what the run needs.

ADR-067 / TASK-633. This is the board-side half of a DUT entry point's
verify-and-refuse contract. The host-side half is ``require_build`` in
``run/lib.sh``, which declares the env and exports ``DUT_ENV``; this module
opens the port, reads the build identity, and exits:

======  ================================================================
exit    meaning
======  ================================================================
0       the board is running the declared build. Proceed.
3       RIG — ``elf-mismatch`` or ``prod-firmware-flashed``. The board is
        present, addressable and answering; the host is pointed at a
        subject the run did not ask for. M-TESTARCH precedence §4 rule 2
        names both reasons in the RIG vocabulary, at 3. **Not 4**: exit 4
        means the board is unfit (a HEALTH condition), and routing a
        wrong-build refusal there would split one condition across two
        codes depending on which layer noticed it (ADR-067 D2).
4       HEALTH — the board is not a valid subject at all.
2       the host could not do its own job (bad arguments, no artifact).
======  ================================================================

Why this exists as a separate entry point rather than as a check inside each
driver: five of the fourteen entry points drive tools that define their own
private ``SerialDut`` class or open a raw ``serial.Serial`` — ``run/ae04``,
``run/wr-gate``, ``run/wr-soak``, ``run/browser-player``,
``run/playorder-player``. None of them has ever read a build identity, which is
finding ``F-19`` stated for one script and true of five. Putting the check in
the entry point makes it uniform, puts the refusal where ADR-067 puts it, and
does not depend on fourteen drivers each mapping an exception to the right exit
code.

**Reset budget.** This opens the port, and a port open asserts DTR, which resets
the ESP32. That is not an added reset: it replaces the flash this entry point
used to perform, which reset the board too. ``Dut.close()`` stamps the DRD gap
file (BP-018), so a driver that opens through ``lib.dut`` afterwards waits out
the remainder of the window by itself. A driver that opens a raw port does not
consult that file — for those, the caller's existing ``sleep $BOOT_WAIT`` is
what separates the two opens, exactly as it separated the flash from the open
before.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

#: RIG. The board answered; it is the wrong subject. ADR-067 D2.
EXIT_REFUSED = 3
#: HEALTH. The board is not a valid subject.
EXIT_HEALTH = 4
#: The host could not do its own job.
EXIT_HOST = 2

#: SetupFailure reasons that mean "wrong build on the board", as opposed to
#: "could not reach a board" or "the board is unwell". Both are already RIG.
_WRONG_BUILD_REASONS = ("elf-mismatch", "prod-firmware-flashed")


def _banner(lines: list[str]) -> str:
    width = 70
    out = ["", "╔" + "═" * width + "╗",
           "║" + "  REFUSED — the board is not running the build this run needs".ljust(width) + "║",
           "╚" + "═" * width + "╝"]
    out.extend(lines)
    return "\n".join(out)


def verify(port: str, env: str, who: str, log_file: str | None = None,
           build_root: pathlib.Path | None = None) -> int:
    """Open the board, read its identity, return the exit code.

    Never raises for a board-side condition: every one of them is a refusal
    with a code, because a traceback out of a preflight is indistinguishable
    from the harness being broken.
    """
    # Imported here, not at module scope: importing lib.dut must not be what
    # decides whether NO_WIFI was set, and check_import_safety.py holds this
    # module to no board access at import time.
    from lib.dut import Dut, SetupFailure  # noqa: PLC0415

    # `build_root` exists so the negative suite can point this at a fixture
    # tree and exercise every board-side arm on a host with no build artifacts
    # (and no board). It is not a runtime knob: nothing passes it in anger.
    root = build_root or (pathlib.Path(__file__).resolve().parent.parent.parent / ".pio" / "build")
    expected = pathlib.Path(root) / env / "firmware.bin"
    if not expected.is_file():
        # The host cannot verify. That is a refusal, not a warning — a run that
        # skips the comparison is the state ADR-067 exists to end.
        print(_banner([
            f"  entry point : {who}",
            f"  WANTED      : {env}",
            f"  ON THE BOARD: unread — no host artifact for '{env}' to compare against",
            f"                (looked for {expected})",
            "",
            f"  Build it, then flash it, then re-run:",
            f"    cd app && ~/.platformio/penv/bin/pio run -e {env}",
            f"    ./run/flash-debug        # or the run/flash* script for this env",
        ]), file=sys.stderr)
        return EXIT_REFUSED

    dut = None
    try:
        dut = Dut(port, log_file=log_file)
    except SetupFailure as e:
        reason = getattr(e, "reason", "?")
        cls = getattr(e, "cls", "RIG")
        if reason in _WRONG_BUILD_REASONS:
            print(_banner([
                f"  entry point : {who}",
                f"  WANTED      : {env}",
                f"  ON THE BOARD: {_describe(reason, e)}",
                "",
                "  " + _remedy(env),
                "",
                f"  NO TESTS RAN. Rig condition (exit {EXIT_REFUSED}), not a test failure —",
                "  the board answered fine, it is just the wrong subject.",
                "",
                "  ADR-067: this entry point does not flash and does not restore.",
                "  The board keeps whatever build the last flash put there.",
                "",
                "  ── the harness's own report ──",
                str(e),
            ]), file=sys.stderr)
            return EXIT_REFUSED
        # Some other setup failure: still not a test result. HEALTH conditions
        # are 4; everything else stays RIG at 3.
        print(f"\n[{who}] SETUP FAILURE ({cls}/{reason}) — NO TESTS RAN\n{e}",
              file=sys.stderr)
        return EXIT_HEALTH if cls == "HEALTH" else EXIT_REFUSED
    except Exception as e:  # noqa: BLE001 — a preflight must not traceback
        print(f"\n[{who}] could not address a board on {port}: "
              f"{type(e).__name__}: {e}\n"
              f"  NO TESTS RAN. Rig condition (exit {EXIT_REFUSED}).", file=sys.stderr)
        return EXIT_REFUSED

    try:
        print(f"[{who}] verified: board={dut.board_id or '?'} "
              f"({dut.board_id_source}) elf={dut.elf or '?'} "
              f"expected={dut.elf_expected or '?'} build={env}")
    finally:
        try:
            dut.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


def _describe(reason: str, e) -> str:
    if reason == "prod-firmware-flashed":
        return ("PRODUCTION firmware — the debug console is compiled out, so "
                "no test can run against it")
    flashed = getattr(e, "flashed_elf", None)
    return f"a different build (elf mismatch{'' if not flashed else f': {flashed}'})"


def _remedy(env: str) -> str:
    return (f"Flash it yourself, on purpose:  ./run/flash-debug   "
            f"(DUT_ENV={env})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", required=True)
    ap.add_argument("--env", default=os.environ.get("DUT_ENV", ""),
                    help="build the run requires; defaults to $DUT_ENV")
    ap.add_argument("--who", default="entry point", help="name for the refusal")
    ap.add_argument("--log-file", default=None)
    a = ap.parse_args(argv)
    if not a.env:
        print("ERROR: no --env and no DUT_ENV — this run does not state which "
              "build it needs, so it cannot be verified.", file=sys.stderr)
        return EXIT_HOST
    return verify(a.port, a.env, a.who, a.log_file)


if __name__ == "__main__":  # pragma: no cover — TASK-609 import-safety guard
    sys.exit(main())
