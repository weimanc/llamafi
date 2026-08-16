# Design — M-ERRMODEL: what an error *is* in this system

> Owner: Architect
> Status: **skeleton** — 2026-08-16
> Tracked-as: TASK-484

> **⚠ SKELETON — A STARTING POINT, NOT A DESIGN.**
> This document exists so the problem has a home, an owner and a record of what is already known.
> It deliberately reaches **no conclusions**. Every "Known" item below was measured or read during
> the 2026-08-16 architecture pass; every "Open" item is genuinely unanswered. A thorough design
> revisit should expect to **restructure this document**, not merely fill it in — and should feel
> free to discard framing that turns out to be wrong. Per BP-DOC-3 (candidate): an admitted gap
> beats an invented contract.

---

## Known

At least **four overlapping conventions** are in use, with no stated relationship between them:

| Convention | Where | Shape |
|---|---|---|
| Numeric codes | `StockApp`, dataTask results | `-91`…`-95`, `-100`; app-specific meanings |
| Boolean flags | `fetchFailed`, `_settled`, `activeError` | per-app members |
| `App` predicates | `hasError()`, `isConnecting()` | IFC-003 S2/S3, polled by the shell |
| Sentinels | `certSentinel()`, `consumeCertBreak()` | TLS/cert-specific |

- **`errorCode == 0` is ambiguous** and IFC-001 says so in writing: *"0 = ok is **ambiguous**"*.
  The working instruction recorded elsewhere is "gate on `activeError`" — a workaround for an
  unspecified model, not a model.
- **Precedence is specified only for the indicator.** ADR-046 / X017 fix `error > busy/connecting >
  idle` for the taskbar active-slot colour. Nothing specifies precedence anywhere else.
- **Stickiness is app-owned** (IFC-003 I7): set on detection, cleared on next success, survives an
  app switch. That part *is* well defined.
- **Some errors are external and permanent** (TASK-243 Spotify Premium lapse) and some are transient
  (a 429, a DNS miss). Nothing in the model distinguishes them, yet the retry behaviour differs.

## Open

- **OQ1 — is there one error type, or a per-layer type?** A `Result<T,E>`-shaped return is
  attractive but `-std=gnu++11` and no exceptions constrain the options.
- **OQ2 — who owns an error's lifetime?** Today: the app. Should a dataTask result carry an error the
  app merely displays, or should the app interpret it?
- **OQ3 — transient vs sustained.** `hasError()` means "will not self-heal by retrying". Nothing
  computes that; each app decides ad hoc.
- **OQ4 — how does an error reach the user?** Taskbar colour, screenLog, the marquee and a serial log
  are four channels with no routing rule.
- **OQ5 — is `errorCode == 0` fixable?** Changing it touches every `poll*()` caller. Possibly the
  single highest-value change in this document, possibly not worth the churn.

## Do not lose

IFC-001 already flags the `0` ambiguity in a shipped contract. Whatever this design concludes,
IFC-001 must be amended in the same pass or the contract and the model diverge immediately.
