# M-ROWGATE — a length gate for task-board rows

Status: proposed

## 1. Problem

`BP-069` (2026-08-25, human) says a `tasks*.md` row is a pointer — id, priority, status, a
one-line title, a design-doc link where one applies, and a commit hash — not a record. Before that
ruling, individual rows in `tasks-architecture.md` had grown past 1,000 words each: full diff
summaries, byte-deltas, DUT logs and judgment-call rationale pasted directly into a table cell. An
archive pass (2026-08-25) moved the worst offenders out and the row's own file now documents the
convention with a template and a worked example — but `BP-064`'s own finding about `M-CODEQUAL`
applies here too: **a prose convention, however well-placed, is a hope, not a gate.** Nothing stops
the next task-closing agent from doing exactly what today's agents did, in good faith, because the
row was the only place the evidence seemed to have anywhere to go.

This is the same failure shape `run/check-docs`'s `SPIKE` check (`TASK-482`) exists to prevent for a
different kind of drift — a rule that is correct and written down, with nothing mechanical behind it.

## 2. What this is not

Not a rewrite of `check_docs.py`'s C1–C6 taxonomy. Those checks are about **documentation citation
decay** — a `file:line` that rotted, a `Status:` word that lied. This is a different kind of fact: a
task board's own row *shape*. Named and gated separately, same reasoning `SPIKE` already used for
staying outside the C-numbering (`check_docs.py`'s own module docstring, `SPIKE` section) — the
design doc that introduced it never tied the two mechanisms together, and there is no reason to force
this one into that taxonomy either.

Not a semantic check. It does not know whether a row's content is a diff summary or a legitimate
long title — it measures length, on the theory (already proven true by the actual 2026-08-25 rows)
that a genuine pointer is short and a smuggled verification narrative is not. A row that is long and
legitimate gets the same exemption mechanism every other `check_docs.py` finding already has.

## 3. Check spec

**Name**: `ROWLEN` (advisory-only key in `check_docs.py`'s `Result` list, parallel to `SPIKE`).

**Corpus**: `docs/project/tasks.md`, `docs/project/tasks-architecture.md`,
`docs/project/tasks-winamp-player.md` — by name, not by a new directory rule. `tasks-archive.md` is
already exempt (`EXEMPT_BASENAMES`) and stays that way: it is the historical record `BP-069` moves
verbose content *to*, and archived rows are expected to be long. Any future task board split from
one of the three above inherits the same treatment — add it to the named list, the same way
`EXTRA_GATED` is a short explicit list rather than a glob.

**Mechanism**: for each gated file, for each physical line matching a task-row pattern
(`^\|\s*\*{0,2}TASK-\d+\*{0,2}\s*\|` — handles both `TASK-472` and `**TASK-472**`), measure the raw
line length in characters. A row is one physical line in this project's table convention (confirmed
by every row inspected during the 2026-08-25 archive pass), so this is a single `len(line)` check,
not a markdown table parser — same "five-line grep" simplicity bar `M-TOOLING §4` set for `SPIKE`.

**Threshold**: **400 characters**, starting point. This is not measured against a real baseline yet
— `check_docs.py`'s own established pattern (`C2`/`C4`/`SPIKE` in `M-TOOLING §4`/`M-DOCLIFE §4`) is
"verify the count is near zero before landing even advisory, because a check that reads a large
number on day one gets ignored, not fixed." **Whoever implements this must run it against current
`tasks*.md` first and adjust the number if the real distribution doesn't support it** — the
archive pass already cleared the worst offenders, so the expectation is a small or zero count, but
that is an expectation, not a measurement, and this doc does not get to assert one it hasn't taken.

**Exemption**: reuse the existing `check_docs.py :: IGNORE_MARKER` (`<!-- check-docs: ignore-line -->`)
rather than invent a second mechanism. A row that is long for a legitimate reason (a genuinely dense
one-line title, not a narrative) carries the marker on the same line.

## 4. Rollout

Lands **advisory only**. Per the same reasoning `TASK-482` used for `SPIKE`: `C5`/`C1-delta`/`C2`/`C4`
each went blocking specifically because they read 0 on landing day; this check has no such
guarantee until it's actually run against the corpus. Promotion to blocking is a separate PM/human
call, made after this has been advisory long enough to show it isn't false-positiving on legitimate
long rows — not decided here.

## 5. Negative test (BP-068)

Ships with `T_DOC_16` (or the next free id): a fixture row deliberately over the threshold must FAIL
the check, and a fixture row at/under threshold, plus a fixture row over threshold but carrying the
ignore marker, must both PASS — the same three-case shape (positive control, threshold edge, marker
exemption) `SPIKE`'s own `T_DOC_15` used. `test_check_docs.py`'s golden fixture and `golden.txt` need
the usual regeneration this class of change always requires (see `TASK-482`'s own landing note on
`check_docs.py`'s existing golden-file discipline).

## 6. Open question

Whether `400` survives contact with the real corpus is genuinely open — flagged in §3, not decided
here. Left for whoever implements this to measure and, if needed, revise before landing.
