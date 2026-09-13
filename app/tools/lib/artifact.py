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
#:
#: 1.2 (TASK-645): `premise.harness` (new, additive) plus two premise fields that
#: changed value-space — `premise.harness_version` now carries the HARNESS's
#: identity (lib/version.py) rather than a copy of `schema.version`, and
#: `premise.board` is `{id, id_source, transport}` rather than `{port, baud}`.
#:
#: WHY THAT IS A MINOR AND NOT A MAJOR, stated so a later reader can disagree
#: with the reasoning rather than guess at it. The MAJOR rule protects READERS
#: from a field whose meaning moved under them. Neither of these fields ever
#: carried the value its own contract specified: R30 asks which harness produced
#: the run and got the document format's version number; ADR-066 D3 asks which
#: BOARD it ran against and got the cable. Filling a field with the value it was
#: always defined to hold is a defect fix, not a re-meaning. The reader count was
#: taken mechanically, not assumed: `premise.` has ZERO consumers outside this
#: package (`lib/baseline.py` reads `id_status` only, `run/player-gate` reads
#: `results[]`, `test_run_artifact.py` asserts key PRESENCE), so nothing can be
#: taught what nothing reads. T_ART_16/17 keep both fields from regressing.
#: **Whether a corrected field is a MINOR or a MAJOR is a specification question
#: and belongs to @Architect — parked on TASK-644, which already owns IFC-008's
#: unfilled clauses. If the ruling is MAJOR, the change is `SCHEMA_MAJOR = 2`
#: and this comment; nothing else here moves.**
#:
#: 1.3 (TASK-677 / PROP-011 §5 P0): `run.rig` (new, additive, optional) — the
#: host+DUT fault-correlation summary for this run's window (R/U/bod_trips/W
#: per PROP-011 §4), present only when RIGWATCH=1 (see run/local.env.example).
#: `null` on any run without it, including every run on a public checkout —
#: an old reader that does not know the key simply never looks at it, which is
#: exactly what MINOR promises.
#:
#: 1.4 (TASK-636 / M-HARNESS2-requirements R20-R21): `premise.shuffle_seed`
#: (new, additive, optional) — the seed passed to `runner.py --shuffle-family`,
#: or `null` on every run that did not pass it (which is every run before this
#: change, and most runs after it). The EXECUTED order itself needed no new
#: field: `premise.class_order` already records the sequence ids actually ran
#: in for every run, shuffled or not (`_gate.EXECUTED_ORDER`, set
#: unconditionally by `run_suite()`) — this field only carries the seed, so a
#: later reader can reproduce the same permutation via
#: `lib.shuffle.shuffle_family()` instead of treating `class_order` as
#: unexplained. See `order_dependence()` below for the cross-run comparison
#: this exists to feed — ADR-066 D2a: that comparison's `ORDER-DEPENDENT`
#: outcome is NOT an eighth verdict and lives only in the comparison's own
#: report, never in `results[].verdict`.
SCHEMA_MINOR = 4
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


# ── diff (TASK-689) ──────────────────────────────────────────────────────────
#
# The gap this closes: an artifact is written every run (TASK-608/645) and
# NOTHING in the tree diffs two of them — `run/player-gate` is the only reader
# and it compares against a hand-kept markdown baseline, never the previous
# run. Six deterministic FAILs sat in the 2026-09-06 and 2026-09-09 artifacts,
# unread, until 2026-09-12 (TASK-685). This is a REPORT, not a gate — see the
# wiring in `run/test`/`run/test-targeted` for why it must never touch an exit
# code.
#
# Verdict polarity is duplicated here (not imported from `lib.results`) on
# purpose: `results.py` already imports THIS module (deferred, to avoid a
# cycle — see `write_artifact`'s docstring); making the dependency mutual at
# module-import time is exactly the kind of layering violation this project's
# "lib/ never imports a suite, levels depend downward only" rule exists to
# forbid one layer up. The values themselves are the closed vocabulary in
# `lib.results.Verdict` and move only if that enum does.

#: R28's "may a gate treat it as green?" set, mirrored from `lib.results.GREEN`.
GREEN_VERDICTS = frozenset({"PASS", "SKIP"})


def diff_documents(old: dict, new: dict) -> dict:
    """Pure diff between two loaded artifact documents. No files touched.

    Returns:
      {
        "newly_failing":  [{"id","old","new"}, ...],  # GREEN -> not GREEN
        "newly_passing":  [{"id","old","new"}, ...],  # not GREEN -> GREEN
        "verdict_changed":[{"id","old","new"}, ...],  # changed, neither of the
                                                       # above (e.g. two
                                                       # non-PASS verdicts, or
                                                       # PASS<->SKIP)
        "only_in_old":    [id, ...],   # ran before, absent now
        "only_in_new":    [id, ...],   # absent before, ran now
        "still_failing":  [{"id","verdict"}, ...],  # not GREEN in BOTH runs
      }

    `still_failing` exists because a DELTA HIDES PERSISTENCE, and persistence is
    what this tool was built to stop losing. The six `lastPlaylistDraw` ids of
    TASK-685 were FAIL on 2026-09-06 and FAIL on 2026-09-09, so they are not in
    any of the three change lists above: a pure delta over that pair reports
    them nowhere, and prints "no change". That is precisely the false
    confidence that let a P1 firmware defect sit unread for six days. A tool
    that answered "what changed?" and stopped there would have institutionalised
    it.

    Ordering within each list is sorted by id, so output is deterministic and
    diffable itself. Unit-testable with hand-built `{"results": [...]}` dicts —
    no file I/O anywhere in this function.
    """
    old_status = id_status(old)
    new_status = id_status(new)
    old_ids = set(old_status)
    new_ids = set(new_status)
    newly_failing, newly_passing, verdict_changed = [], [], []
    still_failing = [
        {"id": t, "verdict": new_status[t]}
        for t in sorted(old_ids & new_ids)
        if new_status[t] not in GREEN_VERDICTS
        and old_status[t] not in GREEN_VERDICTS
    ]
    for tid in sorted(old_ids & new_ids):
        ov, nv = old_status[tid], new_status[tid]
        if ov == nv:
            continue
        row = {"id": tid, "old": ov, "new": nv}
        ov_green = ov in GREEN_VERDICTS
        nv_green = nv in GREEN_VERDICTS
        if ov_green and not nv_green:
            newly_failing.append(row)
        elif not ov_green and nv_green:
            newly_passing.append(row)
        else:
            verdict_changed.append(row)
    return {
        "newly_failing": newly_failing,
        "newly_passing": newly_passing,
        "verdict_changed": verdict_changed,
        "only_in_old": sorted(old_ids - new_ids),
        "only_in_new": sorted(new_ids - old_ids),
        "still_failing": still_failing,
    }


def _premise_key(doc: dict):
    """(entry_point, build_env, board_id) — what makes two runs comparable."""
    prem = doc.get("premise") or {}
    board = prem.get("board")
    board_id = board.get("id") if isinstance(board, dict) else board
    return (prem.get("entry_point"), prem.get("build_env"), board_id)


def previous_comparable(current_doc: dict, current_path,
                        runs_dir=None) -> "pathlib.Path | None":
    """Scan `runs_dir` (default L1's `.runs/`) for the most recent artifact
    comparable to `current_doc` — same `premise.entry_point`, same
    `premise.build_env`, and same `premise.board.id` — with an earlier
    `run.started_at`. -> its path, or None if there is no candidate.

    Deliberately a SCAN, every call, never a cache or an index file. L1 (this
    module's own docstring) forbids a `latest.json`/symlink on the writing
    side precisely so a hurried consumer can't read a stale stable name
    without noticing; a stable *index* on the reading side would be the same
    defect wearing a different hat. `.runs/` holds on the order of hundreds of
    files (TASK-608's estimate: ~40 kB/run, ungitignored growth), so a linear
    scan costs milliseconds, not a design tradeoff.

    A run with no `build_env` (a host-only test script, `entry_point` like
    `test_class_order.py` or `-c`) never matches anything, itself included —
    there is no meaningful "previous run" for those, and matching on
    `entry_point is None` alone would pair up unrelated host invocations.
    """
    key = _premise_key(current_doc)
    if key[0] is None or key[1] is None:
        return None
    runs_dir = pathlib.Path(runs_dir) if runs_dir else DEFAULT_DIR
    cur_path = pathlib.Path(current_path).resolve()
    cur_started = (current_doc.get("run") or {}).get("started_at") or ""
    best = None  # (started_at, path)
    if not runs_dir.is_dir():
        return None
    for p in sorted(runs_dir.glob("run-*.json")):
        try:
            if p.resolve() == cur_path:
                continue
        except OSError:
            continue
        try:
            doc = load(p)
        except ArtifactError:
            continue  # unreadable / stale-schema artifact: not a candidate
        if _premise_key(doc) != key:
            continue
        started = (doc.get("run") or {}).get("started_at") or ""
        if not started or started >= cur_started:
            continue
        if best is None or started > best[0]:
            best = (started, p)
    return best[1] if best else None


# ── order-dependence comparison (TASK-636 / R20-R21 / ADR-066 D2a) ──────────
#
# ADR-066 D2a is explicit about what this may and may not be: `ORDER-DEPENDENT`
# is a comparison outcome over TWO (OR MORE) IFC-008 artifacts, keyed by id,
# naming both orders — never an eighth member of `lib.results.Verdict`, never
# written into `results[].verdict`, never taught to `classify()`. Both inputs
# below are ordinary seven-verdict documents; this function is a NEW CONSUMER
# of IFC-008, not a change to it (same posture as `diff_documents`, TASK-689,
# which this deliberately sits next to rather than forking).
#
# THE FLAKE CAVEAT (TASK-566: ~7% of ids are non-stationary flakes). A single
# canonical-vs-shuffled PAIR cannot distinguish "this id's outcome depends on
# execution order" from "this id is just flaky today" — a flake could differ
# from one canonical run to the next with no shuffle involved at all. So a
# differing id is labelled the bare `ORDER-DEPENDENT` only when the CALLER
# supplied 2+ canonical (registry-order) artifacts and they all AGREE on that
# id's verdict — agreement across canonical runs is the evidence that rules
# out "this id just flips on its own". With exactly one canonical artifact the
# row is still reported (never silently dropped: the whole point, per R21's
# rationale, is that a flake declaration is where order dependence goes to be
# forgotten), but labelled `ORDER-DEPENDENT (single pair — not separated from
# flake)` so a reader cannot mistake a hint for a finding.
#
# THIS IS A REPORT, NEVER A GATE (same stance as TASK-689's diff_documents):
# no exit code anywhere in this module is a function of what it returns.

#: The label vocabulary this comparison prints. Neither string is a `Verdict`
#: member and neither is ever assigned to `results[].verdict` — see the module
#: docstring above and ADR-066 D2a.
ORDER_DEPENDENT = "ORDER-DEPENDENT"
ORDER_DEPENDENT_UNSEPARATED = "ORDER-DEPENDENT (single pair — not separated from flake)"


def _comparable_runs(a: dict, b: dict) -> bool:
    """Same comparability rule `previous_comparable` already uses: same
    entry_point, build_env and board id, and neither unstated."""
    key_a, key_b = _premise_key(a), _premise_key(b)
    return key_a[0] is not None and key_a[1] is not None and key_a == key_b


def _executed_order(doc: dict) -> list:
    """The sequence ids actually ran in. `premise.class_order` carries this
    for EVERY run (`_gate.EXECUTED_ORDER`, set unconditionally by
    `run_suite()`) despite the field's name predating TASK-636 — it is not
    only populated under `--class-order`. See SCHEMA_MINOR 1.4's note."""
    return list((doc.get("premise") or {}).get("class_order") or [])


def order_dependence(canonical_docs, shuffled_doc: dict) -> dict:
    """Compare one or more CANONICAL (registry-order) artifacts against one
    SHUFFLED (per-family, `--shuffle-family`) artifact. Pure: no files touched,
    both/all documents already loaded.

    `canonical_docs`: a single document, or a list of 1+ documents — all from
    registry-order runs (no `--shuffle-family`) of otherwise-comparable runs
    (see `_comparable_runs`). Per IFC-008 I8, artifacts are never merged: each
    is read as its own id->verdict map and only membership/values are compared
    across them, never flattened into one dict.

    Returns:
      {
        "comparable": bool,
        "reason": str or None,        # set (and rows == []) when not comparable
        "seed": <shuffled_doc's premise.shuffle_seed>,
        "n_canonical": <int>,         # how many canonical docs were supplied
        "canonical_order": [...],     # first canonical doc's executed order
        "shuffled_order": [...],
        "rows": [
          {"id", "canonical_verdict", "shuffled_verdict",
           "canonical_index", "shuffled_index",  # position in each order, or
                                                  # None if absent from it
           "n_canonical", "label"},
          ...
        ],  # sorted by id
      }

    An id enters `rows` only when EVERY supplied canonical doc has it, the
    shuffled doc has it, and all the canonical docs AGREE with each other on
    its verdict but the shuffled doc's verdict differs. Canonical docs that
    disagree AMONG THEMSELVES on an id are excluded from `rows` for that id —
    that disagreement is flake evidence with no shuffled run needed to see it,
    and reporting it here as order dependence would misattribute it.
    """
    docs = canonical_docs if isinstance(canonical_docs, list) else [canonical_docs]
    if not docs:
        raise ValueError("order_dependence: at least one canonical doc required")
    for d in docs:
        if not _comparable_runs(d, shuffled_doc):
            return {"comparable": False,
                    "reason": ("premise mismatch (entry_point/build_env/board) "
                               "between a canonical run and the shuffled run, "
                               "or one of them never stated its premise"),
                    "seed": None, "n_canonical": len(docs),
                    "canonical_order": [], "shuffled_order": [], "rows": []}

    canon_status = [id_status(d) for d in docs]
    shuf_status = id_status(shuffled_doc)
    common = set(shuf_status)
    for s in canon_status:
        common &= set(s)
    if not common:
        return {"comparable": False,
                "reason": ("no id is present in BOTH the shuffled run and "
                           "every canonical run supplied — likely a selection "
                           "mismatch (compare the same id set in every run)"),
                "seed": None, "n_canonical": len(docs),
                "canonical_order": [], "shuffled_order": [], "rows": []}

    def _index(order, tid):
        try:
            return order.index(tid)
        except ValueError:
            return None

    canonical_order = _executed_order(docs[0])
    shuffled_order = _executed_order(shuffled_doc)
    n = len(docs)
    rows = []
    for tid in sorted(common):
        canon_verdicts = {s[tid] for s in canon_status}
        if len(canon_verdicts) != 1:
            continue  # canonical runs disagree among themselves — not this id
        canon_v = next(iter(canon_verdicts))
        shuf_v = shuf_status[tid]
        if canon_v == shuf_v:
            continue
        rows.append({
            "id": tid,
            "canonical_verdict": canon_v,
            "shuffled_verdict": shuf_v,
            "canonical_index": _index(canonical_order, tid),
            "shuffled_index": _index(shuffled_order, tid),
            "n_canonical": n,
            "label": ORDER_DEPENDENT if n >= 2 else ORDER_DEPENDENT_UNSEPARATED,
        })
    return {
        "comparable": True,
        "reason": None,
        "seed": (shuffled_doc.get("premise") or {}).get("shuffle_seed"),
        "n_canonical": n,
        "canonical_order": canonical_order,
        "shuffled_order": shuffled_order,
        "rows": rows,
    }


def format_order_dependence(result: dict, max_ids: int = 20) -> str:
    """Human summary of `order_dependence()`'s return."""
    lines = []
    if not result["comparable"]:
        lines.append(f"[order-dependence] NOT COMPARABLE: {result['reason']}")
        return "\n".join(lines)
    lines.append(f"[order-dependence] seed={result['seed']!r} "
                 f"n_canonical={result['n_canonical']}")
    rows = result["rows"]
    if not rows:
        lines.append(f"  no order-dependent ids found (0 differed across "
                     f"{result['n_canonical']} canonical run(s) vs the "
                     f"shuffled run)")
        return "\n".join(lines)
    lines.append(f"  {len(rows)} id(s) differ between canonical and shuffled "
                 f"order:")
    for row in rows[:max_ids]:
        lines.append(
            f"    {row['id']}: {row['label']}"
            f"  canonical={row['canonical_verdict']}"
            f"(pos={row['canonical_index']})"
            f"  shuffled={row['shuffled_verdict']}(pos={row['shuffled_index']})")
    if len(rows) > max_ids:
        lines.append(f"    ... and {len(rows) - max_ids} more")
    if result["n_canonical"] < 2:
        lines.append("  NOTE: only one canonical run was supplied — TASK-566's "
                     "~7% non-stationary-flake rate means these rows are NOT "
                     "yet separated from ordinary flake. Supply 2+ agreeing "
                     "canonical runs to drop this caveat.")
    return "\n".join(lines)


def format_diff(old_path, new_path, delta: dict, max_ids: int = 10) -> str:
    """Human summary of `delta` (from `diff_documents`). ALWAYS names both
    input files — a delta whose inputs are invisible is the same class of
    defect as the artifact nobody read (TASK-689's own brief).

    Caps long id lists at `max_ids` and says so, rather than dumping a wall of
    text — the case that matters in practice is a targeted run (a handful of
    ids) diffed against a full run (hundreds): every id the full run has and
    the targeted one doesn't would otherwise print as "only_in_old", looking
    exactly like a mass regression when it is a selection difference.
    """
    lines = []
    lines.append(f"[artifact-diff] old: {old_path}")
    lines.append(f"[artifact-diff] new: {new_path}")

    def _fmt_rows(label, rows):
        lines.append(f"  {label}: {len(rows)}")
        for row in rows[:max_ids]:
            lines.append(f"    {row['id']}: {row['old']} -> {row['new']}")
        if len(rows) > max_ids:
            lines.append(f"    ... and {len(rows) - max_ids} more")

    def _fmt_ids(label, ids):
        lines.append(f"  {label}: {len(ids)}")
        for tid in ids[:max_ids]:
            lines.append(f"    {tid}")
        if len(ids) > max_ids:
            lines.append(f"    ... and {len(ids) - max_ids} more")

    only_old, only_new = delta["only_in_old"], delta["only_in_new"]
    _fmt_rows("newly failing (was PASS/SKIP)", delta["newly_failing"])
    _fmt_rows("newly passing (was FAIL/UNMET/etc)", delta["newly_passing"])
    _fmt_rows("verdict changed", delta["verdict_changed"])
    # A large only_in_* set is very likely a targeted-vs-full selection
    # mismatch, not a run that lost/gained hundreds of ids outright — flag it
    # instead of printing (or implying) "everything is newly missing".
    if only_old or only_new:
        note = ""
        if len(only_old) + len(only_new) > 20:
            note = ("  (large id-set mismatch — this usually means the two "
                    "runs selected DIFFERENT test sets, e.g. a targeted run "
                    "vs a full one, not that this many ids vanished)")
        lines.append(f"  id-set mismatch{note}")
        _fmt_ids("  only in old run", only_old)
        _fmt_ids("  only in new run", only_new)
    # ALWAYS state persistence, changed or not. A delta answers "what moved?",
    # and an id broken in both runs moved nothing — so a tool that printed only
    # the delta would have said "no change" over a pair in which six ids were
    # failing, which is how TASK-685 stayed unread for six days. The standing
    # count is the half that would have caught it.
    still = delta.get("still_failing") or []
    if still:
        lines.append(f"  STILL failing (unchanged, NOT a regression — but not "
                     f"green either): {len(still)}")
        for row in still[:max_ids]:
            lines.append(f"    {row['id']}: {row['verdict']}")
        if len(still) > max_ids:
            lines.append(f"    ... and {len(still) - max_ids} more")
    if not (delta["newly_failing"] or delta["newly_passing"] or
            delta["verdict_changed"] or only_old or only_new):
        if still:
            lines.append(f"  nothing CHANGED vs the previous comparable run — "
                         f"{len(still)} id(s) are failing in both. 'No change' "
                         f"is not 'no problem'.")
        else:
            lines.append("  no change vs previous comparable run")
    return "\n".join(lines)


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
    ap.add_argument("--diff", metavar="OTHER", default=None,
                    help="TASK-689: diff this artifact (treated as the NEWER "
                         "run) against OTHER (the OLDER run); prints a human "
                         "summary and both filenames. REPORT ONLY — exit code "
                         "is unaffected by the diff's content, see main().")
    ap.add_argument("--diff-auto", action="store_true",
                    help="TASK-689: same as --diff, but OTHER is found by "
                         "scanning .runs/ for the most recent run comparable "
                         "to this one (same entry_point/build_env/board). "
                         "Prints nothing and exits 0 if no comparable run "
                         "exists — that is a normal state (first run of its "
                         "kind), not an error.")
    ap.add_argument("--order-dependence", nargs="+", metavar="CANONICAL",
                    default=None,
                    help="TASK-636/R20-R21: treat THIS artifact (`path`) as "
                         "the SHUFFLED (--shuffle-family) run and compare it "
                         "against one or more CANONICAL (registry-order) run "
                         "artifacts, reporting per-id rows whose verdict "
                         "differs. REPORT ONLY, exit code unaffected — see "
                         "main() below. Supply 2+ canonical paths (from "
                         "agreeing runs) to get the unqualified "
                         "ORDER-DEPENDENT label; with exactly one, rows carry "
                         "a flake-caveat label instead (TASK-566: ~7% "
                         "non-stationary). ADR-066 D2a: this is a comparison "
                         "outcome over artifacts, never an eighth verdict.")
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
    if a.diff is not None or a.diff_auto:
        if a.diff is not None:
            old_path = a.diff
        else:
            old_path = previous_comparable(doc, a.path)
            if old_path is None:
                print("[artifact-diff] no previous comparable run in "
                      f"{DEFAULT_DIR} (same entry_point/build_env/board) — "
                      "nothing to diff against yet.")
                return 0
        try:
            old_doc = load(old_path)
        except ArtifactError as e:
            print(f"ERROR [artifact]: {e}", file=__import__("sys").stderr)
            return 1
        delta = diff_documents(old_doc, doc)
        print(format_diff(old_path, a.path, delta))
        return 0
    if a.order_dependence:
        try:
            canon_docs = [load(p) for p in a.order_dependence]
        except ArtifactError as e:
            print(f"ERROR [artifact]: {e}", file=__import__("sys").stderr)
            return 1
        result = order_dependence(canon_docs, doc)
        print(format_order_dependence(result))
        return 0
    if a.ids_status or True:
        for tid, verdict in id_status(doc).items():
            print(f"{tid} {verdict}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
