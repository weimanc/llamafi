# Over-length task-board rows — the ROWLEN ledger

> Owner: **@Developer** · Machine-read by `app/tools/gate/check_docs.py` (check **ROWLEN**)
> Opened **2026-09-05** by [TASK-647](../project/tasks-harness2.md)
> Rule: [BP-069](../quality/best_practices.md) · Design:
> [M-ROWGATE-task-board-length-check.md](../architecture/designs/M-ROWGATE-task-board-length-check.md)

## What this file is

`run/check-docs`'s **ROWLEN** check asserts BP-069: a `tasks*.md` row is a **pointer** — id,
priority, status, a one-line title, a design-doc link, a commit hash — not a record. Verbatim
status narrative belongs in the design doc, the disposition document, or `tasks-archive.md`.

ROWLEN was **advisory from 2026-08-26 to 2026-09-05**, and both halves of what advisory does to a
finding happened in that window:

* the count sat at 18 and nobody cleared a row of it;
* and it was **18 of the wrong corpus**. The check enumerated three board filenames by hand.
  `docs/project/tasks-harness2.md` was created on 2026-09-03 and was never in that tuple, so it was
  never scanned. By 2026-09-04 **eleven** of its rows were over threshold — one at 829 characters,
  all grown in a single day — while `run/check-docs` printed a clean-looking `18 over-length of 103`
  that did not include a single row from that board. The PM trimmed them by hand in `03e5b43`; no
  gate was involved, and no gate would have been.

TASK-647 fixes both: the corpus is now the glob `docs/project/tasks*.md` (so a new board is in
scope the day it is created, the way C2 already discovers new boards), and the check is
**blocking** against this ledger.

**Opening size: 18 rows, measured 2026-09-05** against the post-`03e5b43` tree — not an estimate.
All 18 are in `tasks-architecture.md`; `tasks.md`, `tasks-winamp-player.md` and `tasks-harness2.md`
are at **zero** and are therefore protected from the first commit onward.

## The rules that make this a gate and not an amnesty

1. A row here suppresses **one** finding, keyed on `(board file, the row's own TASK- id)`. Keyed on
   the id and never on a line number, because board rows move on every edit and a key that moves is
   an exemption that silently transfers to a different row.
2. **A stale row is a BLOCKING failure.** When a row is trimmed under threshold, ROWLEN fails with
   `stale exception … delete this row` until the row here is removed. **The list can only shrink.**
3. There is **no file, directory or wildcard exemption**, by design. `tasks-archive.md` is out of
   scope through `EXEMPT_BASENAMES` — it is the historical record BP-069 moves verbose content *to*,
   and that is the pressure valve: the honest fix for a long row is to move the narrative to the
   archive or a design doc, which is cheaper than adding a row here.
4. Every row needs an owning `TASK-` id and an ISO `since` date.
5. The per-line `<!-- check-docs: ignore-line -->` marker still works and is unchanged. Use it for a
   row that is genuinely a dense pointer; use this ledger for a row that is a smuggled record and is
   owed a trim.

## How to clear a row

Move the narrative to where it belongs (the design doc, the disposition document, or
`tasks-archive.md` with a `[full record in tasks-archive.md](...)` link — `TASK-470`'s row is the
worked example), leave the pointer, then delete the row here. Both edits go in one commit: rule 2
makes a half-applied clearance fail.

## Ledger

Owner = the task whose row this is, i.e. the one that can decide what the pointer should say.

| board | row | why it is over threshold today | owner | since |
|---|---|---|---|---|
| `docs/project/tasks.md` | `TASK-462` | 579 chars — carries the investigation note for the `cmdGet`/`cmdSet` table | TASK-462 | 2026-09-05 |
| `docs/project/tasks.md` | `TASK-549` | 787 chars — carries the §10 OQ-B pricing and hand-off narrative | TASK-549 | 2026-09-05 |
| `docs/project/tasks-harness2.md` | `TASK-564` | 742 chars — enumerates the seven per-phase deadlines | TASK-564 | 2026-09-05 |
| `docs/project/tasks-harness2.md` | `TASK-566` | 2 019 chars — the landed-inert record for the class-order switch | TASK-566 | 2026-09-05 |
| `docs/project/tasks-harness2.md` | `TASK-567` | 765 chars — the 187-site `skip()` adjudication split, counted in the row | TASK-567 | 2026-09-05 |
| `docs/project/tasks-harness2.md` | `TASK-573` | 1 199 chars — the live gate defect written up in the row | TASK-573 | 2026-09-05 |
| `docs/project/tasks-harness2.md` | `TASK-574` | 823 chars — the 74 masked-FAIL `skip()` sites, described inline | TASK-574 | 2026-09-05 |
| `docs/project/tasks-harness2.md` | `TASK-575` | 1 361 chars — the `_TeeSerial` defect and its fix, in the row | TASK-575 | 2026-09-05 |
| `docs/project/tasks-harness2.md` | `TASK-576` | 3 129 chars — the stale-monitor-log session narrative | TASK-576 | 2026-09-05 |
| `docs/project/tasks-harness2.md` | `TASK-577` | 812 chars — the `sdprobe` revert rationale | TASK-577 | 2026-09-05 |

**18 rows. One board.** The three other live boards are at zero and stay there.
