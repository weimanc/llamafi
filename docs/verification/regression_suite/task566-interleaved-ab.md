# TASK-566 — the interleaved class-order A/B (§18.6 a)

> Owner: @VE · executed 2026-09-13 22:02 → 2026-09-14 00:54 · one commit (`2b518597`), one flash,
> board `d48afcc8eed0`, `cyd2usb_winamp_debug`. Precondition list: M-TESTARCH precedence design
> §18.6. This record is **evidence for a decision, not the decision** — TASK-617 re-puts the switch
> to the human.

## Design

Four full `run/test` runs, alternating arms so drift over the night falls on both:
A1 registry → B1 `DUT_CLASS_ORDER=1` → A2 registry → B2 `DUT_CLASS_ORDER=1`. Class order moved 186
of 194 ids. N = 2 per arm, the floor §18.6 (a) names. Run-to-run noise is ~7 % non-stationary
(TASK-566, re-measured at 6.7 % under TASK-575 §9).

| leg | arm | summary | artifact |
|---|---|---|---|
| A1 | registry | 150 P / 13 F / 28 S / 1 flaky-pass / 2 unmet | `run-20260913T210516-1937382-387a8167` |
| B1 | class | 154 P / 10 F / 27 S / 1 flaky-pass / 2 unmet | `run-20260913T214954-1961147-e9f67cad` |
| A2 | registry | 147 P / 15 F / 28 S / 1 flaky-pass / 3 unmet | `run-20260913T223102-1982899-41390182` |
| B2 | class | 155 P / 10 F / 26 S / 1 flaky-pass / 2 unmet | `run-20260913T231533-2006347-ecf43faf` |

**No NOT-RUN in either class-order leg.** No CORE id failed, so the CORE block never fired.

## Failure sets (compare sets, not counts — LL-104)

**Consistently different by arm** (both A legs agree, both B legs agree, and A ≠ B):

| id | registry (A1, A2) | class (B1, B2) | reading |
|---|---|---|---|
| `T_PLR_16` | FAIL, FAIL | PASS, PASS | better under class order; a predecessor effect in registry order |
| `T_WX_04` | SKIP, UNMET | PASS, PASS | better under class order: it runs before the family ids whose visits destroy its premise (B-3 / TASK-594) |

**Consistently worse under class order: none.**

**Failing in all four legs, whatever the order:** `T078`, `T087`, `T092`, `T272`, `T_DTP_01`/`02`
(UNMET), `T_PLR_06`, `T_PLR_15`, `T_PRI_01` (its R14 `prInject` leak, 4/4), `T_WR_TLS_01`.

**One-leg differences, within noise:** `T-BUSY-02`, `T088`, `T237`, `T_CLK_SIG_01`, `T_GOL_03`,
`T_PLR_12`, `T_PLR_13`, `T_PLR_17`, `T_PLR_19`, `T_PLR_24`, `T_PRM_01`, `T_PR_05`, `T_WR_EJECT_02`.

**TASK-697's post-reboot Stock collapse did not occur in any of the four legs.** It happened in both
full runs earlier the same day, so it is non-stationary, as its record says.

## What this does and does not establish

- **(a) is executed.** The switch introduced no failure that both class-order legs show and both
  registry legs do not. It removed two.
- N = 2 cannot separate a true 1-leg flip from noise; nothing in the one-leg list is claimed.
- The switch's other preconditions: **(b) closed 2026-09-13** (all three flake candidates
  adjudicated), **(c) delivered** (TASK-592, 64 adjudicated edges). TASK-617's own exit criterion
  **(ii) still has one row, `T_BI_03`**, which needs a live Spotify queue that TASK-243's lapsed
  Premium cannot provide. That row, and the switch itself, are human calls.
