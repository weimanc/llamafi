# PROP-010 — M-TESTARCH OQ-A/OQ-B: T1 host-shim spike and `set fault` byte-cost spike

> Owner: R&D
> Status: **PLAN OF ACTION — not started.** Written before either spike runs,
> per human request to have a plan reviewed before execution begins.
> Branch (both rungs): `rnd/testarch-oq-spikes`
> Origin: [`M-TESTARCH-test-architecture.md` §10](../../architecture/designs/M-TESTARCH-test-architecture.md#10-still-genuinely-open),
> OQ-A and OQ-B — both are "priced/proven before promised" questions the
> design doc explicitly declined to answer without a spike.

## Premise

M-TESTARCH §10 lists four open questions. Two of them (OQ-A, OQ-B) are
spike-shaped — bounded, falsifiable, no live-DUT dependency for OQ-A and
DUT-optional for OQ-B (firmware link, not runtime behaviour). The other two
(OQ-C, OQ-D) are not spikes — they're a documentation/evidence call and a
procurement-costing call respectively, and are handled separately as an
Architect note on the design doc, not R&D work (see that note for
disposition).

This proposal covers OQ-A and OQ-B only, as two independent rungs. Neither
blocks the other; they can run in either order or in parallel across two
sessions.

## Question to answer

**Rung 1 (OQ-A)**: Does a ~200–300 line host shim (`arduino_shim` +
`fs_shim`) let `m3u.h` — and by extension `settingsStorage.h`,
`asciiFold.h`, `textFit.h`, `timeFmt.h` — compile and link on the host, with
zero behaviour in the shim itself? If yes, T1 is a real tier today, not
contingent on D0. If it drags in a meaningful slice of `app/src` transitively,
T1 is deferred and the document should say so.

**Rung 2 (OQ-B)**: What does a minimal `set fault <subsystem> <mode>`
surface (one subsystem, one mode — not the full matrix) cost in
`.dram0.bss` on `cyd2usb_winamp_debug`, the board that has overflowed this
segment four times on record (BP-053, LL-117)? If headroom doesn't cover
even the minimal case, the fuller proposal in M-TESTARCH §4 is dead before
design effort is spent on it.

## Suggested ladder (cheap-kill-first, LL-087)

### Rung 1 — T1 host shim (OQ-A)

1. **Zero-shim baseline first.** Stand up `app/test/host/main.cpp` as a
   bare runner against the three files M-TESTARCH already confirmed have no
   Arduino dependency at include level: `util/mathUtil.{h,cpp}`,
   `util/asciiFold.h`, `util/textFit.h`. This should compile with no shim at
   all — if it doesn't, the doc's own include-level check was wrong and
   that's worth knowing before rung 2 is attempted. ~1 hour.
2. **Shim spike, timeboxed to one day** (the document's own bound — do not
   extend without checking in). Build `arduino_shim/` (String, `millis()`,
   `Serial`, `min`/`max`, `F()`) and `fs_shim/` (SD/File over
   `std::filesystem`) only as far as `m3u.h` needs, not speculatively wider.
   Try `m3u.h` against it.
3. **Report the actual pull-in, not just pass/fail.** If `m3u.h` compiles,
   also attempt `settingsStorage.h`, `asciiFold.h`, `textFit.h`, `timeFmt.h`
   against the same shim (M-TESTARCH's own list) — record which land clean
   and which drag in something unexpected the doc didn't anticipate.

### Rung 2 — `set fault` byte cost (OQ-B)

1. **Pick the cheapest fault to price, not the whole matrix.** M-TESTARCH
   §4 lists "drop the next TLS handshake, return a short read, fail the
   next allocation" as examples. Price **one** — recommend "fail the next
   allocation" (a single static counter + one branch in the allocator path,
   no subsystem-specific state) as the minimal-footprint candidate.
2. **Measure, don't estimate.** `nm --size-sort -S` / `size` diff against a
   clean `cyd2usb_winamp_debug` baseline build, same method LL-117
   documents as the only one that's caught real vs. illusory savings on
   this board before. Report the number, not a guess from `sizeof()`.
3. **If it doesn't fit**, that's a valid, useful outcome — record current
   headroom (re-measure fresh; EXP-021 already established this board's
   headroom is a snapshot, not a durable property) and stop. Do not spend
   time minimizing the fault surface further inside this spike; that's a
   production-design question if rung 2 clears, not an R&D one.

## Kill gates

- **Rung 1**: `m3u.h` transitively requires more than the five files
  M-TESTARCH names (i.e. the shim would have to grow to cover code the doc
  didn't anticipate) → T1 is deferred until after D0; document that
  honestly instead of forcing the shim wider.
- **Rung 2**: the single cheapest fault mode ("fail next allocation") does
  not fit current `.dram0.bss` headroom on `cyd2usb_winamp_debug` → the
  fuller `set fault` proposal in §4 does not clear even its minimal case;
  stop, do not price additional fault modes.

## Deliverables

Two EXP reports under `docs/rnd/reports/`, next free ids at time of
execution (**EXP-023** and **EXP-024** as of this writing — reserve fresh
before filing, per PROP-009's own note that snapshot numbers aren't
durable). Each report states Validated / Invalidated / Inconclusive per the
standard R&D report format, independently — rung 1's outcome does not gate
rung 2's.

**Production integration is NOT part of this activity.** If rung 1
validates, hand `M-TESTARCH-test-architecture.md` §10's OQ-A disposition to
Architect/PM to schedule as an actual T1 tier task. If rung 2 validates,
hand the priced number to Architect for the `set fault` design (still not
built — this only prices it, per §4's own "that is a proposal, not a
decision").

## Recommended next step

Hand to human operator for go-ahead on branch cut, then execute rung 1
first (higher stated leverage, zero DUT dependency, faster to a clean
pass/fail). Rung 2 can follow independently once a `cyd2usb_winamp_debug`
baseline build is available.

## Branch

`rnd/testarch-oq-spikes` (fresh cut from current `master` at execution
time — do not reuse a stale branch; check staleness the way EXP-021 did for
`rnd/webradio-wave-spike` before assuming any existing branch is usable).
