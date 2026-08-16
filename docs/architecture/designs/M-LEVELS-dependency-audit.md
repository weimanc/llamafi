# Design — M-LEVELS: auditing the dependency graph ADR-060 D2a asserts

> Owner: Architect
> Status: **skeleton** — 2026-08-16
> Tracked-as: TASK-485
> Governs: [ADR-060](../decisions/ADR-060.md) D2a / D2b

> **⚠ SKELETON — A STARTING POINT, NOT A DESIGN.**
> This document exists so the problem has a home, an owner and a record of what is already known.
> It deliberately reaches **no conclusions**. Every "Known" item below was measured or read during
> the 2026-08-16 architecture pass; every "Open" item is genuinely unanswered. A thorough design
> revisit should expect to **restructure this document**, not merely fill it in — and should feel
> free to discard framing that turns out to be wrong. Per BP-DOC-3 (candidate): an admitted gap
> beats an invented contract.

---

## Known

- **ADR-060 D2a declares four levels and has never been audited.** The levels were asserted from
  reading, not from a generated graph:

  ```
  level 3  apps/            level 1  audio/ player/ winamp/ settings/ taskbar/
  level 2  shell/ boot/ debug/    level 0  util/ gen/ touch/ app.h
  level −1 app/lib/  (D2b — vendored; may be depended on, never depends upward)
  ```

- **One violation is known by inspection**: `apps/spotifyApp` and `apps/webRadioApp` include
  `winamp/winampDisplay.h`, which reaches back into player-mode concepts. ADR-059's capability mask
  is the accepted fix and has **landed** (`winampDisplay.h` gates zones on `_playerCaps`), so this
  violation may already be narrower than recorded.
- **One boundary crossing is declared**: `mb_arena` — project-authored, inside the vendored fork,
  fan-in from both trees (D2b).
- **72 `extern` declarations** across headers point back into `main.cpp`. Every one is a level
  inversion by definition: a lower-level header reaching up into the entry point.
- **No include graph has ever been generated.** Not once, by anyone.

## Open

- **OQ1 — what does the real graph look like?** A generated include graph is a few lines of Python
  and would replace every assertion above with a measurement. This should be the *first* action, not
  a later one.
- **OQ2 — are there cycles?** Unknown. `winamp/` ↔ player-mode is the suspected one; `settings/`
  including app headers is another candidate worth checking.
- **OQ3 — is `settings/` level 1 or level 3?** It holds shared widgets (`keyboardWidget`,
  `sliderWidget`, `settingsWidgets`) used beyond Settings *and* app-specific sections. It may need
  splitting across two levels — M-SRCLAYOUT OQ2 raised this and did not resolve it.
- **OQ4 — should the levels be gated?** A cycle check in `run/check` would make D2a enforceable
  rather than aspirational. Same argument as IFC-002's enforcement table: the rule with a check is
  the rule that holds.

## Do not lose

The audit is cheap and objective, and it may **contradict D2a**. That is a success condition, not a
failure: a measured graph that disagrees with the asserted one is exactly why this task exists.
