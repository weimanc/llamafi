#!/usr/bin/env python3
"""lib/artifact.py — the run result artifact: schema, reader, staleness guard.

TASK-608 / ADR-066 D1 / IFC-008 / R29 / R30.

WHAT THIS REPLACES. Until this module the machine interface to a test run was a
`printf`: `lib/results.py` printed `  <id>: <STATUS>[: reason]` and three
separate consumers recovered verdicts from that text with a regex. That is not a
hypothetical hazard — `results.py` wrote `FLAKY-PASS`, `run/player-gate`'s sed
alternation carried `FLAKE`, `FLAKE` != `FLAKY`, the line was dropped, the cell
scored MISSING and the gate printed **REGRESS** for a firmware regression that
never happened (TASK-573). The polarity was the worst available: the UNRESOLVED
flake parsed and the RESOLVED one did not.

ADR-066 D1: the artifact is the sole machine interface; the human summary stays
for humans and is explicitly NOT a contract (IFC-008 I6).

── PATH AND LIFETIME (IFC-008 "Not yet decided" item 1, decided here) ──────────

The brief's constraint is the decisive one: *a gate reading a stale artifact
from a previous run is a worse failure than no artifact at all.* A stale read is
silent and wears the shape of a real result; a missing file is loud. So the
design is chosen against staleness first and convenience second, in three
layers:

  L1 — THE DEFAULT PATH IS UNIQUE PER RUN. `.runs/run-<UTC>-<pid>-<token8>.json`
       under `app/tools/`. Nothing is ever overwritten, so "the file at the path
       I read is from an older run" cannot arise by path reuse. There is
       deliberately NO `latest.json` and NO symlink: a stable name is precisely
       the artefact a hurried consumer reads without noticing it did not change.

  L2 — A CONSUMER THAT NEEDS A KNOWN PATH OWNS THE PATH AND THE NONCE. It sets
       `RESULTS_JSON=<path>` and `RESULTS_RUN_TOKEN=<nonce>`, deletes the path
       first, and reads back with `load(path, expect_token=nonce)`. A file from
       any other run carries a different token and is REFUSED as `StaleArtifact`
       — not repaired, not warned about, refused. This is the airtight layer:
       it holds even if the consumer forgets to delete, even if two runs race,
       and even if a human copies an old artifact into place.

  L3 — THE READER REFUSES WHAT IT DOES NOT UNDERSTAND. An unknown schema MAJOR
       is an error, never a best-effort parse; a missing file is an error, never
       an empty result set. `parse_log`'s old behaviour — silently yield {} for
       a run that never reached its summary — is exactly how an aborted leg
       became "every cell MISSING" in one consumer and "no rows, no problem" in
       another.

Lifetime: the run's own artifacts are disposable. `.runs/` is gitignored and
holds nothing a gate needs after its own run; `run/player-gate` keeps the copy
it asked for inside its own `OUT_DIR` alongside the leg logs, which is where its
evidence has always lived. Nothing prunes `.runs/` automatically — a background
job deleting evidence is a worse trade than a directory that grows by ~40 kB a
run — but nothing reads it by name either, so growth is inert.

── SCHEMA ─────────────────────────────────────────────────────────────────────

`schema.version` is `MAJOR.MINOR`. Additive-only within a MAJOR (ADR-066
"Consequences", the same rule ADR-065 D4 puts on IFC-007): a new field bumps
MINOR and old readers keep working; a removal or a re-meaning bumps MAJOR and
every reader must be taught. `load()` accepts any MINOR at the MAJOR it knows.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

#: MAJOR.MINOR. See the schema note above.
SCHEMA_NAME = "esp_spotify.test-run"
SCHEMA_MAJOR = 1
#: 1.1 (TASK-631): `results[].exchanges` — the last 20 command/reply pairs
#: behind a blocking verdict, or null. Additive, so 1.0 readers are unaffected.
SCHEMA_MINOR = 1
SCHEMA_VERSION = f"{SCHEMA_MAJOR}.{SCHEMA_MINOR}"

#: Where a run writes when the caller named no path (layer L1).
DEFAULT_DIR = pathlib.Path(__file__).resolve().parents[1] / ".runs"

#: The two knobs a consumer sets. Deliberately env vars and not only CLI flags:
#: `run/player-gate` drives `runner.py` through a subshell, and the five
#: unrelated `print_results` callers have their own argument parsers that must
#: not need touching (they set neither, and so emit to the L1 default).
ENV_PATH = "RESULTS_JSON"
ENV_TOKEN = "RESULTS_RUN_TOKEN"

_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ArtifactError(Exception):
    """Base: this artifact cannot be used as a machine interface."""


class StaleArtifact(ArtifactError):
    """The file exists but is not this run's.

    Its own class because it is the failure this module is designed against,
    and because a consumer's handling of it differs from a missing file: a
    missing artifact means the run never got that far, a stale one means
    something is wrong with how the run was invoked.
    """


class SchemaMismatch(ArtifactError):
    """An artifact at a MAJOR this reader was not taught."""


def valid_token(token: str) -> bool:
    return bool(token) and bool(_TOKEN_RE.match(str(token)))


def default_path(token: str, when: str) -> pathlib.Path:
    """L1's unique-per-run path. `when` is an ISO-8601 UTC stamp."""
    stamp = re.sub(r"[^0-9T]", "", when.replace("Z", ""))[:15]
    return DEFAULT_DIR / f"run-{stamp}-{os.getpid()}-{str(token)[:8]}.json"


# ── writing ──────────────────────────────────────────────────────────────────

def write(path, document: dict) -> pathlib.Path:
    """Write `document` atomically. -> the path written.

    Atomic because a consumer may look while a run is finishing, and half a
    JSON document is a parse error that reads like a broken schema rather than
    like a race.
    """
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n")
    tmp.replace(p)
    return p


# ── reading ──────────────────────────────────────────────────────────────────

def load(path, expect_token: str = None) -> dict:
    """Read an artifact. Raises rather than degrading.

    `expect_token` is L2 and is the whole staleness guard: pass the nonce the
    run was invoked with and an artifact from any other run is refused. Omitting
    it is legitimate for a human-driven tool (`lib.baseline` over archived
    artifacts) and illegitimate for a gate.
    """
    p = pathlib.Path(path)
    if not p.exists():
        raise ArtifactError(
            f"{p}: no run artifact. The run did not reach its summary, or it "
            f"was never told to write one ({ENV_PATH}). An absent artifact is "
            f"NOT an empty result set — no id in it has any verdict, including "
            f"the ones that would have passed.")
    try:
        doc = json.loads(p.read_text())
    except Exception as e:
        raise ArtifactError(f"{p}: unreadable run artifact ({e})") from None
    schema = (doc or {}).get("schema") or {}
    if schema.get("name") != SCHEMA_NAME:
        raise SchemaMismatch(
            f"{p}: not an {SCHEMA_NAME} artifact (schema.name="
            f"{schema.get('name')!r})")
    try:
        major = int(str(schema.get("version", "")).split(".", 1)[0])
    except ValueError:
        raise SchemaMismatch(f"{p}: unparseable schema.version "
                             f"{schema.get('version')!r}") from None
    if major != SCHEMA_MAJOR:
        raise SchemaMismatch(
            f"{p}: schema MAJOR {major}, this reader knows {SCHEMA_MAJOR}. A "
            f"MAJOR bump means a field changed meaning or went away; guessing "
            f"is how a gate reads a verdict that is not there.")
    if expect_token is not None:
        got = ((doc.get("run") or {}).get("run_token"))
        if got != expect_token:
            raise StaleArtifact(
                f"{p}: run_token {got!r} is not this run's ({expect_token!r}). "
                f"This artifact belongs to a DIFFERENT run — reading it would "
                f"score a gate against results the run under test never "
                f"produced. Refused (TASK-608 L2).")
    return doc


def id_status(doc: dict) -> dict:
    """-> {id: verdict token}. The typed replacement for the summary regex."""
    return {r["id"]: r["verdict"] for r in (doc.get("results") or [])}


def counts(doc: dict) -> dict:
    return dict((doc.get("run") or {}).get("counts") or {})


def exit_code(doc: dict):
    return (doc.get("run") or {}).get("exit_code")


# ── CLI: the shape `run/player-gate` consumes ────────────────────────────────

def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="read a run artifact (TASK-608 / IFC-008)")
    ap.add_argument("path")
    ap.add_argument("--token", default=None,
                    help="the run nonce; an artifact from another run is "
                         "refused as stale (exit 2)")
    ap.add_argument("--ids-status", action="store_true",
                    help="print `<id> <VERDICT>` per line — run/player-gate's "
                         "input format, replacing its sed parser")
    ap.add_argument("--exit-code", action="store_true")
    a = ap.parse_args(argv)
    try:
        doc = load(a.path, expect_token=a.token)
    except StaleArtifact as e:
        print(f"ERROR [artifact]: {e}", file=__import__("sys").stderr)
        return 2
    except ArtifactError as e:
        print(f"ERROR [artifact]: {e}", file=__import__("sys").stderr)
        return 1
    if a.exit_code:
        print(exit_code(doc))
        return 0
    if a.ids_status or True:
        for tid, verdict in id_status(doc).items():
            print(f"{tid} {verdict}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
