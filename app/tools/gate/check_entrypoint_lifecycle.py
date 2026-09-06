#!/usr/bin/env python3
"""ADR-067 / TASK-633 — no DUT entry point flashes, and none restores.

Blocking, at ZERO, with no ledger. There is no shrink-only ratchet here because
there is nothing to shrink from: the conversion landed whole, and a single
re-introduced restore re-creates the exact obstruction ADR-067 removed — a
script that cannot be run at all on a board pinned to a debug build (TASK-557).

What it checks, over every executable in ``run/``:

C1  No entry point uploads ``$ENV_PROD``. This is the restore. It is deleted,
    not guarded (ADR-067 D1) — a guarded restore fires *sometimes*, and then
    every future reader must know which mode they are in to know what state the
    board is in.

C2  No entry point that sources ``lib.sh`` and drives a test/soak/gate uploads
    ANY firmware. Flashing is an explicit caller action through ``run/flash*``.
    The ``run/flash*`` scripts themselves are the exception and are named, not
    inferred: flashing is what they are for.

C3  Every entry point that opens a DUT declares the build it needs, by calling
    ``require_build``. A run that does not say which build it requires cannot be
    refused for running the wrong one, and would silently re-acquire the
    property this whole conversion exists to remove.

C4  The documentation does not promise a restore that no longer happens
    (ADR-067's *Constrained* consequence: the promise is REMOVED, not softened).
    A doc that promises a restore is worse than no doc, because a reader trusts
    it and leaves a debug build on the board believing production is back.

Exit 0 clean, 1 with findings. Negative suite:
``gate/test_check_entrypoint_lifecycle.py``.
"""

from __future__ import annotations

import pathlib
import re
import sys

#: Scripts whose JOB is to flash. Named, never inferred from the name pattern —
#: an inferred exemption is one rename away from exempting a test script.
FLASHERS = {
    "flash", "flash-debug", "flash-fs", "flash-player", "flash-webradio",
    "build", "build-debug", "setup", "spiffs",
}

#: Entry points that open a DUT and therefore must declare a required build.
#: This is the ADR-067 §Context list (14 scripts), minus lib.sh which declares
#: nothing of its own, plus nothing: it is a closed set, and a new entry point
#: is expected to be added here in the same commit that adds the script.
MUST_DECLARE = {
    "test", "test-targeted", "test-sync", "player-gate", "wr-gate", "stress",
    "wr-soak", "pr-soak", "pr-fetch-soak", "ae04", "task488",
    "browser-player", "playorder-player", "task424-repro",
}

#: Considered and deliberately EXCLUDED, with the reason, because a
#: half-converted set is worse than either end state — a reader must be able to
#: see that these were looked at and why they are different, not guess.
#:
#: run/dut-health  — carries an EXIT trap but never restored anything (it was
#:   never in ADR-067's list). It is the HEALTH preflight, and its whole job is
#:   to answer "is this board fit". Adding a build declaration would make it
#:   open the port twice for one question, and a second open inside the DRD
#:   window is the hazard BP-018 exists for. It already refuses at exit 4, which
#:   is the correct code for its own subject.
#: run/screendump  — an instrument, not a run. It reads one frame off whatever
#:   is on the board; refusing on build identity would stop it being usable for
#:   the diagnosis it exists for. (It is also broken at import — `A-1`/TASK-589.)
#: run/spiffs      — uploads a FILESYSTEM image, never firmware. Its trap
#:   restarts the monitor. Out of scope by subject, not by exemption.
EXCLUDED_WITH_REASON = {"dut-health", "screendump", "spiffs"}

#: Prose that promises a restore. Matched case-insensitively over docs.
RESTORE_PROMISES = [
    re.compile(r"always restores? prod", re.I),
    re.compile(r"restores? prod(uction)? firmware on exit", re.I),
    re.compile(r"trap[- ]guarded (prod(uction)? )?restore", re.I),
    re.compile(r"kills \+ restores monitor.*restores prod", re.I),
]

#: Docs whose job is to RECORD that the promise was removed. They quote the old
#: wording on purpose; a gate that failed them would make the only honest fix a
#: falsification of the record (QM's rot rule (c)).
DOC_EXEMPT_DIRS = (
    "docs/architecture/decisions/",
    "docs/project/tasks-archive.md",
    "docs/quality/",
    "docs/verification/reviews/",
    "docs/project/M-HARNESS2-PM-review.md",
    "docs/architecture/designs/M-HARNESS2-architect-review.md",
    "docs/architecture/designs/M-HARNESS2-DEV-review.md",
)

_UPLOAD_RE = re.compile(r'run\s+-e\s+"?\$?\{?(\w+)\}?"?\s+-t\s+upload')


def _scripts(root: pathlib.Path):
    run = root / "run"
    for p in sorted(run.iterdir()):
        if p.is_file() and p.suffix in ("", ".sh"):
            yield p


def check(root: pathlib.Path) -> list[str]:
    findings: list[str] = []

    for p in _scripts(root):
        name = p.name
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:  # pragma: no cover
            findings.append(f"{name}: unreadable ({e})")
            continue
        # Only shell entry points. A python file under run/ has no trap.
        if not text.startswith("#!") or "bash" not in text.splitlines()[0]:
            continue

        body = _strip_comments(text)

        for m in _UPLOAD_RE.finditer(body):
            var = m.group(1)
            if name in FLASHERS:
                # A flasher uploading $ENV_PROD is `run/flash` doing its job.
                # The defect ADR-067 names is a TEST entry point owning firmware
                # lifecycle, not the existence of a way to flash production.
                continue
            if var == "ENV_PROD":
                findings.append(
                    f"C1 run/{name}: uploads $ENV_PROD — this is the production "
                    f"restore ADR-067 D1 deleted. A DUT entry point never restores.")
            elif name not in FLASHERS:
                findings.append(
                    f"C2 run/{name}: uploads ${var} — a DUT entry point never "
                    f"flashes (ADR-067 D1). Flashing is the caller's action, "
                    f"through run/flash*.")

        if name in MUST_DECLARE and "require_build" not in body:
            findings.append(
                f"C3 run/{name}: opens a DUT but never calls require_build — it "
                f"does not state which build it needs, so it cannot refuse the "
                f"wrong one (ADR-067 D1).")

    findings.extend(_check_docs(root))
    return findings


def _strip_comments(text: str) -> str:
    """Drop whole-line shell comments.

    Deliberately line-based and deliberately not a shell parser: the point is
    that PROSE about the deleted restore must not read as the restore itself.
    An inline trailing comment is left in place, which is conservative in the
    direction that matters — a false finding is visible, a missed one is not.
    """
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def _check_docs(root: pathlib.Path) -> list[str]:
    findings: list[str] = []
    targets = [root / "CLAUDE.md"]
    docs = root / "docs"
    if docs.is_dir():
        targets.extend(sorted(docs.rglob("*.md")))
    for p in targets:
        rel = str(p.relative_to(root))
        if any(rel.startswith(d) for d in DOC_EXEMPT_DIRS):
            continue
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            for rx in RESTORE_PROMISES:
                if rx.search(line):
                    findings.append(
                        f"C4 {rel}:{i}: promises a restore that no longer "
                        f"happens (ADR-067) — {line.strip()[:100]}")
                    break
    return findings


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = pathlib.Path(argv[argv.index("--root") + 1]).resolve() \
        if "--root" in argv else pathlib.Path(__file__).resolve().parents[3]
    findings = check(root)
    if findings:
        print(f"FAIL: check_entrypoint_lifecycle — {len(findings)} finding(s) "
              f"(ADR-067/TASK-633; blocking at zero, no ledger)")
        for f in findings:
            print(f"  {f}")
        return 1
    print("PASS: check_entrypoint_lifecycle — no entry point flashes or "
          "restores; every one declares its build (ADR-067)")
    return 0


if __name__ == "__main__":  # pragma: no cover — TASK-609 import-safety guard
    sys.exit(main())
