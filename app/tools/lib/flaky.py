#!/usr/bin/env python3
"""lib/flaky.py — reader and validator for docs/verification/flaky.yaml (TASK-520).

The file has existed since TASK-513 but nothing consumed it, so ADR-059 D13's
"flaky set pre-declared" was unenforceable: any test could call flake() and be
excused, and no entry ever expired. This module is the half that makes the
artifact binding. lib/results.py is the half that enforces it at run time.

The policy (flaky.yaml's own header, M-TESTARCH §7) — implemented here:

  1. Declared BEFORE the run. An id not in `flaky:` is UNDECLARED and its
     flake() call becomes a FAIL. This module answers "is it declared".
  2. Retry once, report both outcomes. lib/results.py owns that.
  3. Every entry carries an owning task and a review_by date; past that date
     the entry is EXPIRED and behaves exactly like UNDECLARED. `status()`
     returns EXPIRED as its own state so the failure message can say which.
  4. Reported separately in the summary. lib/results.py owns that.

FAIL CLOSED. A missing, unparseable or schema-invalid flaky.yaml does not
silently grant flake status to everyone — `load()` raises, and the runtime
path turns the load error into a FAIL reason on every flake() call. A broken
declaration file is a stricter state than no flakes, never a laxer one.

Also runnable as a linter:

    python3 app/tools/lib/flaky.py --check       # schema + expiry, exit 1 on error
    python3 app/tools/lib/flaky.py --check --no-expiry
"""

from __future__ import annotations

import argparse
import datetime
import os
import pathlib
import re
import sys
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:  # pragma: no cover - environment guarantees pyyaml
    yaml = None

# app/tools/lib/flaky.py -> app/tools/lib -> app/tools -> app -> <repo root>
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
DEFAULT_FLAKY_PATH = _REPO_ROOT / "docs" / "verification" / "flaky.yaml"

# Env override exists for the negative tests (test_flaky_policy.py), which must
# be able to point the loader at a deliberately broken file. It is NOT a way to
# opt a run out of the policy: an empty/missing override path still fails closed.
ENV_OVERRIDE = "FLAKY_YAML"

DECLARED = "declared"
UNDECLARED = "undeclared"
EXPIRED = "expired"

_REQUIRED_FIELDS = ("id", "suite", "since", "evidence", "symptom",
                    "owner", "task", "review_by")
_TASK_RE = re.compile(r"^TASK-\d+$")
_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class FlakyError(Exception):
    """flaky.yaml is missing, unparseable, or violates the schema."""


@dataclass
class FlakyEntry:
    id: str
    suite: str
    since: datetime.date
    evidence: str
    symptom: str
    owner: str
    task: str
    review_by: datetime.date
    dependency: str = ""
    suspected: str = ""

    def is_expired(self, today: datetime.date) -> bool:
        return today > self.review_by


@dataclass
class FlakyRegistry:
    path: pathlib.Path
    entries: dict = field(default_factory=dict)      # id -> FlakyEntry
    candidates: dict = field(default_factory=dict)   # id -> note

    def status(self, tid: str, today: datetime.date | None = None):
        """Return (state, entry). state is DECLARED / UNDECLARED / EXPIRED."""
        entry = self.entries.get(tid)
        if entry is None:
            return UNDECLARED, None
        if today is None:
            today = datetime.date.today()
        if entry.is_expired(today):
            return EXPIRED, entry
        return DECLARED, entry

    def expired(self, today: datetime.date | None = None) -> list:
        if today is None:
            today = datetime.date.today()
        return [e for e in self.entries.values() if e.is_expired(today)]


def _as_date(value, where: str) -> datetime.date:
    # PyYAML parses an unquoted YYYY-MM-DD as datetime.date already; a quoted
    # one arrives as str. Accept both, reject anything else (including the
    # common mistake of writing `review_by: 2026-9-17` -> str "2026-9-17").
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value.strip())
        except ValueError:
            raise FlakyError(f"{where}: not an ISO YYYY-MM-DD date: {value!r}")
    raise FlakyError(f"{where}: not a date: {value!r}")


def _resolve_path(path=None) -> pathlib.Path:
    if path is not None:
        return pathlib.Path(path)
    env = os.environ.get(ENV_OVERRIDE)
    if env:
        return pathlib.Path(env)
    return DEFAULT_FLAKY_PATH


def load(path=None) -> FlakyRegistry:
    """Parse and schema-validate flaky.yaml. Raises FlakyError on any problem."""
    p = _resolve_path(path)
    if yaml is None:
        raise FlakyError("PyYAML not installed — cannot read the declared flaky set")
    if not p.is_file():
        raise FlakyError(f"declaration file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise FlakyError(f"{p}: YAML parse error: {e}")

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise FlakyError(f"{p}: top level must be a mapping, got {type(raw).__name__}")

    unknown = set(raw) - {"flaky", "candidates"}
    if unknown:
        raise FlakyError(f"{p}: unknown top-level key(s): {sorted(unknown)}")

    reg = FlakyRegistry(path=p)

    items = raw.get("flaky") or []
    if not isinstance(items, list):
        raise FlakyError(f"{p}: `flaky:` must be a list, got {type(items).__name__}")

    for i, item in enumerate(items):
        where = f"{p}: flaky[{i}]"
        if not isinstance(item, dict):
            raise FlakyError(f"{where}: entry must be a mapping, got {type(item).__name__}")
        missing = [k for k in _REQUIRED_FIELDS
                   if k not in item or item[k] is None
                   or (isinstance(item[k], str) and not item[k].strip())]
        if missing:
            raise FlakyError(f"{where}: missing/empty required field(s): {missing}")
        tid = item["id"]
        if not isinstance(tid, str) or not _ID_RE.match(tid):
            raise FlakyError(f"{where}: bad test id {tid!r}")
        if tid in reg.entries:
            raise FlakyError(f"{where}: duplicate entry for id {tid}")
        task = str(item["task"])
        if not _TASK_RE.match(task):
            raise FlakyError(f"{where} ({tid}): `task` must look like TASK-123, got {task!r}")
        entry = FlakyEntry(
            id=tid,
            suite=str(item["suite"]),
            since=_as_date(item["since"], f"{where} ({tid}) since"),
            evidence=str(item["evidence"]),
            symptom=str(item["symptom"]),
            owner=str(item["owner"]),
            task=task,
            review_by=_as_date(item["review_by"], f"{where} ({tid}) review_by"),
            dependency=str(item.get("dependency", "") or ""),
            suspected=str(item.get("suspected", "") or ""),
        )
        if entry.review_by < entry.since:
            raise FlakyError(f"{where} ({tid}): review_by {entry.review_by} precedes since {entry.since}")
        reg.entries[tid] = entry

    cands = raw.get("candidates") or []
    if not isinstance(cands, list):
        raise FlakyError(f"{p}: `candidates:` must be a list, got {type(cands).__name__}")
    for i, item in enumerate(cands):
        where = f"{p}: candidates[{i}]"
        if not isinstance(item, dict):
            raise FlakyError(f"{where}: entry must be a mapping")
        tid = item.get("id")
        if not isinstance(tid, str) or not _ID_RE.match(tid or ""):
            raise FlakyError(f"{where}: bad or missing id {tid!r}")
        note = item.get("note")
        if not isinstance(note, str) or not note.strip():
            raise FlakyError(f"{where} ({tid}): `note` is required — an unexplained "
                             f"candidate is indistinguishable from a forgotten one")
        if tid in reg.entries:
            raise FlakyError(f"{where} ({tid}): id is BOTH declared and a candidate — "
                             f"a candidate is by definition not yet declared")
        if tid in reg.candidates:
            raise FlakyError(f"{where}: duplicate candidate for id {tid}")
        reg.candidates[tid] = note.strip()

    return reg


# ── cached accessor used by the runtime path ─────────────────────────────────

_CACHE = None          # (path, registry) once loaded successfully
_CACHE_ERROR = None    # FlakyError message if the load failed


def get_registry(path=None):
    """Return (registry, error_message). Exactly one of the two is None.

    Cached per resolved path so a 130-test run parses the file once. Never
    raises: the runtime path must be able to fold the error into a FAIL reason
    rather than crash the whole suite.
    """
    global _CACHE, _CACHE_ERROR
    p = _resolve_path(path)
    if _CACHE is not None and _CACHE[0] == p:
        return _CACHE[1], None
    if _CACHE_ERROR is not None and _CACHE_ERROR[0] == p:
        return None, _CACHE_ERROR[1]
    try:
        reg = load(p)
    except FlakyError as e:
        _CACHE_ERROR = (p, str(e))
        return None, str(e)
    _CACHE = (p, reg)
    _CACHE_ERROR = None
    return reg, None


def reset_cache() -> None:
    """Drop the memoised registry (tests switch FLAKY_YAML between cases)."""
    global _CACHE, _CACHE_ERROR
    _CACHE = None
    _CACHE_ERROR = None


# ── linter ───────────────────────────────────────────────────────────────────

def check(path=None, today: datetime.date | None = None, check_expiry: bool = True) -> int:
    """Validate the file. Returns a process exit code (0 ok, 1 problem)."""
    p = _resolve_path(path)
    try:
        reg = load(p)
    except FlakyError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    if today is None:
        today = datetime.date.today()
    rc = 0
    if check_expiry:
        for e in reg.expired(today):
            days = (today - e.review_by).days
            print(f"FAIL: {p.name}: {e.id} review_by {e.review_by} passed {days} day(s) ago "
                  f"(owner {e.owner}, {e.task}) — re-justify or delete the entry", file=sys.stderr)
            rc = 1
    if rc == 0:
        print(f"OK: {p} — {len(reg.entries)} declared, {len(reg.candidates)} candidate(s)")
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="validate docs/verification/flaky.yaml")
    ap.add_argument("--check", action="store_true", help="schema + expiry check")
    ap.add_argument("--file", default=None)
    ap.add_argument("--today", default=None, help="override today's date (YYYY-MM-DD)")
    ap.add_argument("--no-expiry", action="store_true",
                    help="schema only; do not fail on past review_by dates")
    args = ap.parse_args(argv)
    today = datetime.date.fromisoformat(args.today) if args.today else None
    return check(args.file, today=today, check_expiry=not args.no_expiry)


if __name__ == "__main__":
    sys.exit(main())
