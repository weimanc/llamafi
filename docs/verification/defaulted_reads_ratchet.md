# Defaulted device reads — shrink-only ratchet

> Owner: **@Developer** · Gate: `app/tools/gate/check_defaulted_reads.py`
> Requirement: [R18](M-HARNESS2-requirements.md) (mode: **ratchet**) · Opened by **TASK-596**, 2026-09-04.

**What a row is.** A per-module CAP on the number of two-argument `.get(<key>, <literal>)` calls
made on a **device reply dict**. A defaulted reply read gives a failed read the same *type* as a real
one, so the comparison that follows cannot tell them apart — the S6 defaulting-oracle class. WP-G's
`G-2` is what it costs when the defaulted value lands in an oracle: `_stock_ok_count`'s `-1`
satisfied `_wait_chart_complete` on its first poll and made the Stock family's central fetch oracle
an unconditional pass across nine ids.

**The rules, all enforced by the gate, none of them advisory.**

1. **Blocking.** A module over its cap fails `run/check`. There is no warn-only mode.
2. **Shrink-only, and enforced in both directions.** A cap *above* the module's real count is a
   `D2` failure: when a migration lands, the row comes down with it. Headroom is how a ratchet
   stops ratcheting.
3. **A row is not an excuse, it is a debt with a name.** Every row carries an owning TASK id and
   the ISO date it was opened.
4. **`lib/` may not hold a row at all** (`D5`). The typed accessor lives there; a default in the
   shared layer reaches every caller at once.
5. **A row whose module no longer exists is a failure** (`D3`), not a leftover.
6. **When the last row goes, this file is deleted** — an exemption table holding zero rows is where
   the next amnesty starts. That is the same retirement rule
   `docs/verification/flake_class_exceptions.md` was deleted under.

**How to refresh a row after a migration:**

```sh
cd app/tools && python3 gate/check_defaulted_reads.py --print-counts
```

**Migrate with:** `dut.get_int` / `get_str` / `get_bool` / `get_float` / `get_val` in `lib/dut.py`.
They return a value or raise: `BadField` (the device answered and the answer breaks the contract —
a FAIL) or `NoAnswer` (nothing answered this question — an `UNMET`). Inside a bounded poll loop,
catch `NoAnswer` and let the loop's own deadline be the verdict; never catch `BadField` there.

## Rows

| module | cap | owner | since |
|---|---|---|---|
| `suite/serialdbg/shell.py` | 53 | TASK-596 | 2026-09-04 |
| `suite/serialdbg/player.py` | 39 | TASK-596 | 2026-09-04 |
| `suite/serialdbg/webradio.py` | 34 | TASK-596 | 2026-09-04 |
| `suite/serialdbg/teletext.py` | 9 | TASK-596 | 2026-09-04 |
| `suite/serialdbg/planeradar.py` | 8 | TASK-596 | 2026-09-04 |
| `suite/serialdbg/clock.py` | 2 | TASK-596 | 2026-09-04 |
| `suite/serialdbg/health.py` | 1 | TASK-596 | 2026-09-04 |

**Total: 146**, down from 171 when the gate was written (2026-09-04). `lib/dut.py` (2),
`suite/serialdbg/_helpers.py` (9) and `suite/serialdbg/stock.py` (14) went to zero in TASK-596 /
TASK-585 and have no rows.

**What the remaining 146 cost.** They are mechanical but not blind: each site needs the reply's
field name and its type, and each poll loop needs a decision about whether an unanswered read
should end the id or be re-polled. On the stock migration the rate was roughly 25 sites per hour
including the judgement calls, so ≈ 6 h for the rest — but it is **7 independent, separately
reviewable increments**, one per module, and the two large ones (`shell.py`, `player.py`) should
not be one commit. It also cannot be finished blind: several sites in `player.py` and
`webradio.py` read fields whose firmware type is not obvious from the call site, and confirming
those against `cmdGet.cpp` is the slow part. Nothing here is DUT-blocked.
