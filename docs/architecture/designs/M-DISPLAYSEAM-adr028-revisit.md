# Design — M-DISPLAYSEAM: re-examining the ADR-028 rejection

> Owner: Architect
> Status: proposed
> As-built: 2026-08-16
> Tracked-as: TASK-487
> Revisits: [ADR-028](../decisions/ADR-028.md) (rejected 2026-07-18)

> **⚠ SKELETON — A STARTING POINT, NOT A DESIGN.**
> This document exists so the problem has a home, an owner and a record of what is already known.
> It deliberately reaches **no conclusions**. Every "Known" item below was measured or read during
> the 2026-08-16 architecture pass; every "Open" item is genuinely unanswered. A thorough design
> revisit should expect to **restructure this document**, not merely fill it in — and should feel
> free to discard framing that turns out to be wrong. Per BP-DOC-3 (candidate): an admitted gap
> beats an invented contract.

**This is not a proposal to resurrect ADR-028.** The likely outcome is that the rejection stands.
It is a re-read, because two of its premises have moved.

---

## Known

- **ADR-028 (canvas abstraction) was rejected 2026-07-18**, reasoning: *"no remaining driver for a
  runtime canvas indirection on a 240×320 single-display product"* — portability needs met host-side
  by M-PREVIEW-FRAMEWORK, PC-mirror out of scope per ADR-006.
- **That reasoning was sound at the time** and the rejection has held for a month.
- **Two premises have since moved:**
  1. **ADR-061 D9 step 1 requires `display/tft.{h,cpp}` as an owned component anyway** — so "an
     owned display component" is now happening regardless of ADR-028.
  2. **ADR-060 D0 makes host unit tests possible for the first time.** A test seam is a driver
     ADR-028's rejection did not weigh, because it did not exist.
- **The scale of the coupling**: **797 `tft.` call sites across 24 files** — the highest-fan-in
  symbol in the firmware, currently defined at `cheapYellowLCD.h:7`, inside *vendored upstream
  compatibility code that nobody owns*.
- **A partial seam already exists**: `util/tftViewportRepair.h` was written because clip/viewport
  restoration was got wrong repeatedly.

## Open

- **OQ1 — does a test seam justify indirection that portability did not?** The honest answer may be
  no: 797 call sites is a large blast radius for a benefit nobody has demanded.
- **OQ2 — is there a cheaper seam than a canvas?** Owning `display/tft` (D9 step 1) may be
  sufficient on its own — a named component with a contract (IFC-006) and no runtime indirection.
  This is the lean.
- **OQ3 — what would a host renderer actually need?** M-PREVIEW-FRAMEWORK already renders host-side
  *without* firmware indirection, by re-implementing. That works, and it is also LL-114's mirror
  problem — the previews can drift from what the device draws.
- **OQ4 — does IFC-006 alone close this?** If the contract states the batching, clipping and colour
  conventions, the ADR-028 question may be moot without any code change.

## Do not lose

ADR-028's rejection is **recorded with reasons** and those reasons were right. Any revisit must
engage with them specifically rather than re-litigating from scratch — and must record the outcome on
ADR-028 itself so the next reader does not re-open it a third time.
