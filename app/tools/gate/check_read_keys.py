#!/usr/bin/env python3
"""check_read_keys.py — `app/gen/read_keys.py` may not be stale. TASK-641.

WHAT THIS ASSERTS. `gen/gen_read_keys.py` regenerates `app/gen/read_keys.py`
from the live suite registry + `suite/serialdbg/transcripts/`. This gate
re-runs the generator into a temp dir and diffs the result against the
committed file, byte for byte — the same pattern `check_build.sh`:93-105 uses
for `gen_app_registry.py`'s `app_ids_gen.py`/`configurable_apps.h`, copied
here rather than added as a new numbered `check_build.sh` gate: the project's
counted gate total (11) does not move when a host check is added, because
every host-side gate already lives inside gate 8 (`smoke_test.sh`) — see
`CLAUDE.md`'s "Build check" section. So this landing point is `smoke_test.sh`,
not `check_build.sh`.

A gate never lands advisory (M-HARNESS2 convention): a staleness check is
either at zero by construction — regenerate, diff, done — or it isn't a gate.
There is no ledger here because there is nothing to grandfather: unlike
`check_get_keys.py`'s enumeration-completeness question (which needed an
independent oracle to even ask), "is the committed file what the generator
would produce right now" has a single unambiguous answer every time.

No DUT, no build, no network. Sub-second.

    python3 app/tools/gate/check_read_keys.py
"""

from __future__ import annotations

import filecmp
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(TOOLS))

GENERATOR = os.path.join(TOOLS, "gen", "gen_read_keys.py")
COMMITTED = os.path.join(ROOT, "app", "gen", "read_keys.py")


def regenerate(out_dir: str, python: str = None) -> tuple[int, str]:
    """Run the generator into `out_dir`. -> (returncode, combined output)."""
    python = python or sys.executable
    proc = subprocess.run(
        [python, GENERATOR, "--out-dir", out_dir],
        capture_output=True, text=True, cwd=TOOLS,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def evaluate(out_dir: str, rc: int, output: str) -> list:
    """Pure: the findings, so the negative suite can drive it without spawning
    a subprocess itself."""
    findings = []
    if rc != 0:
        findings.append(f"gen_read_keys.py exited {rc}:\n{output}")
        return findings
    fresh = os.path.join(out_dir, "read_keys.py")
    if not os.path.isfile(fresh):
        findings.append(f"gen_read_keys.py did not write {fresh}")
        return findings
    if not os.path.isfile(COMMITTED):
        findings.append(f"{COMMITTED} does not exist — never generated?")
        return findings
    if not filecmp.cmp(fresh, COMMITTED, shallow=False):
        findings.append(
            f"{COMMITTED} is STALE — differs from a fresh "
            f"`python3 app/tools/gen/gen_read_keys.py` run. Re-run the "
            f"generator and commit the result.")
    return findings


def main(argv) -> int:
    with tempfile.TemporaryDirectory(prefix="read_keys_stale_") as tmp:
        rc, output = regenerate(tmp)
        findings = evaluate(tmp, rc, output)
    if findings:
        print(f"check_read_keys: FAIL: {len(findings)} finding(s)")
        for f in findings:
            print(f"  {f}")
        return 1
    print(f"check_read_keys: {COMMITTED} is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
