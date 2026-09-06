# Private-results-layer exceptions — `check_private_results.py`

> Owner: **Verification Engineer** · Gate: `app/tools/gate/check_private_results.py`
> Filed by TASK-646 (WP-A `A-6`), opened 2026-09-06 with **1 row**.

The gate asserts that only `app/tools/lib/results.py` defines a verdict
recorder. A private copy of the results layer is invisible at the call site —
`pass_(tid)` and `fail(tid, why)` read identically whether they are the shared
implementation or a frozen fork of it — and `run_sync_tests.py` carried one for
a year, which cost its twenty ids the flaky policy, `NOT-RUN`, `UNMET`, the
verdict invariants and (from TASK-608) any machine interface at all.

**This ledger is dated, owned and shrink-only** (BP-074). A row must name an
owning task and the date it was opened. **A row that no longer matches a finding
is itself a blocking failure** — delete it in the commit that removes the
finding.

**Adding a row is not the way to pass this gate.** The way to pass it is to
import the layer. A row is only appropriate where the file is not a DUT suite at
all and its store is not a verdict record.

| file | rule | owner | since | why it is not a private verdict layer |
|---|---|---|---|---|
| `app/tools/test_flaky_policy.py` | R3 | TASK-646 | 2026-09-06 | A HOST unit test **of** `lib/results.py`, not a DUT suite. Its `RESULTS` is this file's own pass/fail tally for its ~30 arms — no test id in it is a firmware verdict, nothing consumes it, and it never reaches an artifact. It reads the shared layer's real store as `R.RESULTS` on the same page (lines 207, 314), which is the store under test; renaming its local tally would obscure that distinction rather than remove a duplication. |
