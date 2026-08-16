# Design — M-TESTARCH: what the test architecture should be

> Owner: **Architect (seams) + VE (plan)** — joint. VE owns `test_plan.md` and `regression_suite/`
> per AGENTS.md; the Architect defines the seams and VE challenges them for testability.
> Status: **skeleton** — 2026-08-16
> Tracked-as: TASK-483
> Companion to: [M-TOOLING](M-TOOLING-host-tool-architecture.md) F1/F2, [ADR-060](../decisions/ADR-060.md) D0

> **⚠ SKELETON — A STARTING POINT, NOT A DESIGN.**
> This document exists so the problem has a home, an owner and a record of what is already known.
> It deliberately reaches **no conclusions**. Every "Known" item below was measured or read during
> the 2026-08-16 architecture pass; every "Open" item is genuinely unanswered. A thorough design
> revisit should expect to **restructure this document**, not merely fill it in — and should feel
> free to discard framing that turns out to be wrong. Per BP-DOC-3 (candidate): an admitted gap
> beats an invented contract.

---

## Known

- **Testing is 100 % integration, on hardware, on one device.** There are no unit tests and no host
  test target. This is the state of the project, not a decision anyone recorded.
- **The taxonomy exists in prose, not in code.** `test_plan.md` is 4 717 lines and defines ~16 id
  families (`T_AE_`, `T_PLR_`, `T_PR_`, `T_WX_`, `T_CX_`, `T_GOL_`, `T_MA_`, `T_BI_`, `T_PRL_` …)
  across 12 `regression_suite/` documents.
- **The runner ignores it.** `run_serialdbg_tests.py` is 10 229 lines: 128 test bodies ordered by id
  *number*, not subject (`T077…T085, T096, T087, T088, T090` — the numeric order has itself broken),
  one flat registry at line 600, one shared helper block at line 62.
- **There is no shared DUT layer.** 33 tools re-implement port resolution; 29 duplicate a serial
  send/expect loop; `ve_suite_base.py` (97 lines, 7 importers) provides result reporting only.
- **D0 changes what is possible.** Self-contained components with declared interfaces are the
  precondition for host-side unit tests. This is arguably the largest payoff of M-SRCLAYOUT and it
  is written down nowhere.
- **Some seams are already mockable.** `dataTask` behind IFC-001 has a typed enqueue/poll API. `tft`
  is not mockable until ADR-061 D9 gives it a component.

## Open

- **OQ1 — is a host unit tier worth it here?** This is VE's call more than the Architect's. "DUT-only,
  but with a real DUT library" may be the honest answer for a project this size. Do not assume the
  textbook pyramid.
- **OQ2 — which seams would a unit tier actually use?** Candidates: `util/*`, `player/m3u`,
  `settings/settingsStorage`, the `PlaylistSource` interface (IFC-005). Anything touching `tft`,
  WiFi or the audio engine is probably DUT-forever.
- **OQ3 — how do test ids stay bound to test code?** Today a `T_XXX` in `test_plan.md` and a
  `def t077` in the runner are bound by nothing. That is LL-114's mirror problem one layer up, and
  `run/check-docs` could gate it.
- **OQ4 — does the runner split (TASK-480) mirror the VE taxonomy, or invent its own?** Lean: mirror.
  Two taxonomies would be strictly worse than one.
- **OQ5 — what is the flaky-test policy?** `ve_suite_base` has a `flake()` state and ADR-059 D13
  requires a pre-declared flaky set; neither is a policy.

## Do not lose

The verification paradox: **the regression suite cannot verify a refactor of itself.** TASK-480 needs
≥3 baseline runs before it lands, and that constraint should be stated wherever the split is planned.
