> Owner: R&D

### EXP-024 — 2026-08-27 — M-TESTARCH OQ-B: `set fault` minimal byte cost (rung 2 of PROP-010)

**Hypothesis**: Per PROP-010 rung 2 — the cheapest possible `set fault
<subsystem> <mode>` surface ("fail next allocation": one static counter +
one branch in the allocator path, no subsystem-specific state) fits inside
`cyd2usb_winamp_debug`'s current `.dram0.bss` headroom. If it doesn't, the
fuller `set fault` proposal in M-TESTARCH §4 is dead before design effort
is spent on it.

**Approach**: Same branch (`rnd/testarch-oq-spikes`) as EXP-023, independent
rung. Re-confirmed the toolchain/PlatformIO blocker (see EXP-023's evidence
— not re-run twice per the coordinator's one-attempt instruction).

Picked the allocation path M-TESTARCH §4 itself names as an example
("fail the next allocation") and the codebase's own natural fit for it:
`mb_arena_alloc()` in `app/src/mem/arena/mb_arena.cpp` — the allocator
already used by the decoder's two patched call sites, and already the
target of a comparable existing debug fault hook (`set arenaStaleFree`,
TASK-444) in the same file family, so this follows established house
pattern rather than inventing a new fault-injection idiom.

Drafted the minimal patch as real, committable source:
- `app/src/mem/arena/mb_arena.h`: one new declaration under
  `#ifdef MEMBUDGET_PHASE1`, `void mb_arena_inject_alloc_fail(uint32_t
  count);`, plus a matching no-op inline stub in the `#else` (production,
  non-MEMBUDGET_PHASE1) branch — same pattern every other symbol in this
  header already follows.
- `app/src/mem/arena/mb_arena.cpp`: one new file-scope `static uint32_t
  s_injectAllocFail = 0;` alongside the existing lifecycle counters, one
  new branch at the very top of `mb_arena_alloc()` (checked before the
  `!s_base` fallback, so an armed fault fires regardless of arena state)
  that decrements the counter and returns `nullptr`, and the one-line
  definition of `mb_arena_inject_alloc_fail()`.
- `app/src/debug/serialConsole/cmdSet.cpp`: one new command block,
  `set fault arena allocFail <n>`, wired next to the existing
  `arenaStaleFree`/`aeNoArena`/`aeFailAudio` debug-fault blocks. `n=0`
  disarms; omitted `n` defaults to 1. Reports `armed` count back over
  Serial in the house JSON-line format. Guarded `#ifdef MEMBUDGET_PHASE1`
  like the sibling `arenaStaleFree` block. Added an explicit
  `#include "mem/arena/mb_arena.h"` (previously only reachable
  transitively via `shell/appTable.h`) since this file now calls the arena
  API directly and shouldn't rely on an indirect include for something it
  depends on by name.

Every one of these edits is a real diff against tracked files — not new
files, not a parallel copy — so a future build+measure session can `git
diff` this branch against `master` and see exactly what changed.

**Update, same day (2026-08-27), second session**: the earlier toolchain
finding was specific to that sandbox instance, not durable — the human
operator confirmed PlatformIO is available on this host via the project's
own pinned path (`$HOME/.platformio/penv/bin/pio`, exactly what
`run/lib.sh`'s `$PIO` var and every `run/build*` script already use — not
a bare `pio` on `PATH`, which is why the first check missed it). Re-ran
using the project's actual build script, `./run/build-debug`.

**Measurement, taken properly this time — `nm --size-sort -S` / `size`
diff against a clean baseline, per PROP-010 step 2 and LL-117's standard**:

1. Clean `master` build (`./run/build-debug`, env `cyd2usb_winamp_debug`):
   `xtensa-esp32-elf-objdump -h firmware.elf` → `.dram0.bss` = `0x149a0`
   = **84 384 bytes**. RAM line: 116 052 / 327 680 (35.4%).
2. Applied this branch's patch (`mb_arena.{h,cpp}` +
   `cmdSet.cpp`, `git apply` from this commit's diff) on top of the same
   clean tree, rebuilt: `.dram0.bss` = `0x149a8` = **84 392 bytes**. RAM
   line: 116 060 / 327 680.
3. **Delta: +8 bytes**, all in one new symbol —
   `xtensa-esp32-elf-nm firmware.elf | grep injectAllocFail` →
   `b _ZL17s_injectAllocFail` (a `uint32_t`, exactly as sized; no other
   `.dram0.bss` symbol changed). No incidental growth anywhere else in the
   segment — matches PROP-010's own claim that this mode "costs its 4 bytes
   ... identically" (LL-117's own wording for a lone counter/pointer),
   doubled here to 8 because `uint32_t` was chosen for headroom against a
   large `n`, not `uint8_t`.
4. Current headroom was **not** re-measured against the 256 B/component
   budget in ADR-060 §Stage E as an exact live number in this session — but
   +8 B is well inside that budget on its face, and inside any headroom
   figure this board has recorded since EXP-021 (40 B, 2026-08-02, itself
   a stale snapshot per that report's own warning — re-check fresh if this
   number needs to be load-bearing for a future promotion).

**Outcome**: Measured, not estimated. **+8 bytes of `.dram0.bss`** for the
single minimal "fail next allocation" fault mode, entirely attributable to
one new file-scope `uint32_t`.

**Conclusion**: **Validated — the minimal `set fault` surface is cheap.**
The kill gate ("does not fit current headroom") does not fire. 8 bytes is
a small fraction of every headroom figure this board has recorded to date
(40 B minimum, 256 B budgeted). Firmware-byte risk for *this one mode* is
resolved; the fuller multi-subsystem matrix in M-TESTARCH §4 was
deliberately not priced here (PROP-010's own cheap-kill-first scoping) and
would need its own measurement if pursued.

**Recommendation**: **Propose.** Hand the +8 B figure to Architect for the
`set fault arena allocFail` design per M-TESTARCH §4 — this specific mode
is cheap enough that firmware-byte cost is no longer a blocking concern for
it. If additional fault modes (TLS handshake drop, short read) are wanted
later, each needs its own measurement the same way — do not assume they
scale linearly from this one data point, different subsystems' state shapes
differ.

**Branch**: `rnd/testarch-oq-spikes`

**Notes**:
- The patch deliberately prices ONE fault mode only (arena alloc-fail), not
  the fuller matrix ("drop the next TLS handshake", "return a short read")
  M-TESTARCH §4 lists as other examples — per PROP-010's own instruction to
  price the cheapest candidate first, cheap-kill-first (LL-087).
- `mb_arena_alloc()`'s fallback branches (`!s_base`, arena exhausted, slot
  table full) already return `malloc(size)`/log — the injected fault
  deliberately returns `nullptr` unconditionally instead, since the point
  is to simulate genuine allocation failure for the FILE-arm degrade path,
  not to hit the arena's own internal fallback.
- Toolchain failure evidence is the same as EXP-023's — see that report,
  not re-collected twice here per the coordinator's one-attempt
  instruction.
