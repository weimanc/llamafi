# M-HARNESS2 — Architect review

> Owner: **Architect**
> Status: review — advisory, binding on nothing until the ADRs in §8 are taken
> Written: 2026-09-03
> Reviews: [M-HARNESS2 requirements](../../verification/M-HARNESS2-requirements.md) (@VE, 55 reqs, 37 MUST / 18 SHOULD)
> Against: [ADR-060](../decisions/ADR-060.md) levels · [architecture.md](../architecture.md) ·
> [M-TESTARCH](M-TESTARCH-test-architecture.md) §2/§2c/§3b/§4/§5 ·
> [M-TESTBASE phase 1](M-TESTBASE-phase1-player-gate.md) §4/§5 ·
> [M-MEMBUDGET](M-MEMBUDGET-memory-budget.md) + `app/mem_manifest.yaml`
> Method: static only. No DUT, no serial port, no flash — the board stays pinned per TASK-557.
> Nothing under `app/tools/` was imported; everything below is read, grepped or arithmetic.

---

## 0. Overall verdict

**I would sign this off, with four changes that alter what the firmware is asked to do and five
decisions taken as ADRs first.** The document's central claim — that test quality is a property of
the observable rather than of the test, evidenced by an 11-fold SOUND spread with author, harness and
period held constant — is the strongest argument anyone has made about this project's test suite, and
it is correct; group OBS is the right thing to build and most of the rest of the document is
competent tightening of machinery that already exists. What it gets wrong is architectural, not
evidential: **R3** places the observability contract on a seam that does not exist (`dbgGet` is not
part of the `App` interface — `app/src/app.h` has no such member, and four apps' surfaces are typed
branches in `cmdGet.cpp`), and it asks thirteen apps to each implement two observables the shell
could publish once, more cheaply and less falsifiably; **R5** specifies a signature "over the buffer
the app drew from" when no such buffer exists on this target — TFT_eSPI writes straight to the
panel's GRAM and only Aquarium and the Stock heatmap use a sprite — which reads as a fatal objection
and is not, because the mechanism it needs is already shipped and DUT-proven (`tft.readRect()`, MISO
wired, `colorprobe` 25/25); **R25** is written as the document's only flag-day and does not have to
be one; and **R51** resolves a real blocker with a suppression flag on a lifecycle the test entry
points should not own at all. Cost is not the objection anyone expected it to be: the OBS contract is
**~150 B of `.dram0.bss` and ~8–12 KB of flash** as written, **~60 B and ~5 KB** with my amendment —
affordable against the 2026-08-07 debug headroom of 9 920 B, and *unaffordable* against the 0 B
headroom this project measured in July, which is why it must land per-app against a freshly derived
`.map` under an ADR-060 D0a-style ceiling rather than as one sweep.

---

## 1. Group OBS — is the app-observability contract the right seam?

### 1.1 The seam as written does not exist

**R3** says an app must publish four observables "through its `dbgGet` surface". Three facts make
that unbuildable as stated:

* **`dbgGet` is not part of the `App` interface.** `app/src/app.h:11-92` declares `init`, `resume`,
  `suspend`, `tick`, `handleInput`, `hasPendingAsync`, `hasError`, `isConnecting`,
  `isNavigationTap`, `hasInFlightOp`, `~App`. There is no `dbgGet` and no `dbgSet`. The obligation
  lives only in prose, at `docs/architecture/designs/NEW-APP-CHECKLIST.md:89-93`, and it is a human
  checkbox.
* **Four of thirteen apps do not have one.** Clock's surface is typed branches in the console
  (`app/src/debug/serialConsole/cmdGet.cpp:546`, `:554` reach into `g_ClockApp` directly);
  LocalPlayer's is the same shape at `:594`, `:634-653`; Spotify's goes through
  `spotifyDisplay->dbgGet(...)` at `:489`; Weather's is a single `dataReady()` call at `:424`.
  M-TESTARCH §2.3's build note already recorded this (Clock and LocalPlayer "pass" A6 because their
  surfaces are `cmdGet` branches, not overrides) — R3 would convert that observation into a
  contract without ever giving the contract a place to live.
* **The console types app names.** `cmdGet.cpp` names `g_ClockApp`, `g_WeatherApp`, `g_CryptoApp`,
  `g_LifeApp`, `g_LocalPlayerApp`, `g_SettingsApp` in its own body. A conformance gate generated over
  `APP_ORDER` (R3's stated verification, extending `check_app_conformance.py`) can only assert
  something a generated enumeration can reach; today it reaches `cmdGet.cpp` by regex, which is why
  `check_app_conformance.py` carries a `CMDGET` path constant that TASK-471 had to hand-edit.

So the honest reading is: **R3 is a firmware interface change wearing a test-harness hat, and it
should be admitted as one.** That is not an objection to it. It is an objection to landing it as a VE
gate over an informal convention rather than as an interface.

### 1.2 Where it belongs, clause by clause

| Clause | Belongs | Who implements | Where the code lives |
|---|---|---|---|
| (a) identity | **the shell** — not the app | @Developer, once | `shell/appShell.cpp` + `cmdGet.cpp` |
| (b) progress | **the shell**, over the `App` seam it already dispatches | @Developer, once | `shell/appShell.cpp` (a counter array bumped in `appTick`) |
| (c) result | **the app** — genuinely app-specific | @Developer, per app | each `apps/*.cpp` `dbgGet` |
| (d) entry-state | **the app** — genuinely app-specific | @Developer, per app | each `apps/*.cpp` `dbgGet` |

**(a) is the clause I reject as an app obligation.** R3(a) asks each app to publish "an identity
observable proving the app is the active one, readable only when it is (not a global)". The shell
already owns that fact — `currentAppId` — and asking thirteen apps to re-publish it creates thirteen
places for it to be wrong and nothing that can cross-check them. `A-8`'s actual defect is not that
Clock lacks an identity key; it is that Clock's keys **answer when Clock is not active**, so a
`switchApp` that stopped switching would fail no clock id. The correct contract is therefore a
*negative* one, and it is a property of the console, not of the app: **a per-app key must be refused
with a named error when its owning app is not the active app.** That is one shared guard in the
console's delegation path plus one generated conformance row ("for each app in `APP_ORDER`, its keys
answer while active and refuse while not"), and it fixes `A-8` for all thirteen apps at once,
including the four that have no `dbgGet` at all. Thirteen hand-written identity keys fix it for none
of them, because each one is written by the same author who wrote the app.

**(b) belongs in the shell for the same reason, and the reason is falsifiability.** A progress
counter that the app increments in its own tick is a counter the app can be wrong about in exactly
the way the test is trying to detect. A counter the *shell* increments around its `appTick()` call is
one the app cannot fake, costs one `uint32_t` per app in one array, and is written once. R3's phrase
"written exclusively by the app's own tick/render path" is aiming at something real — distinguishing
"tick ran" from "render happened" — but that distinction is R5's job (a render signature), not a
counter's. Two counters, both shell-owned, would answer it fully: ticks dispatched, and repaints
accepted (the precedent is `get pleditRepaints`, ADR-059 D12).

**(c) and (d) are correctly per-app and I accept them unchanged.** `G-3` (`get fetchErrorCode` does
not exist) and `B-5` (`stockMode` settable, not gettable) are exactly the shape of defect a per-app
contract catches, and WP-Z's own costing — "each is a `case` in an existing `dbgGet` whose struct
field already exists" — is right; I checked `apps/cryptoApp.cpp`'s chain and a new key there is four
lines.

### 1.3 The interface this implies

Once (a) and (b) move to the shell, the residual per-app obligation is small enough to state as an
interface rather than a checklist:

> **`App` gains two pure-virtual-with-safe-default debug accessors under `SERIAL_DEBUG`:
> `dbgGet(const char*, char*, int) const` and `dbgSet(const char*, const char*)`**, defaulting to
> `false`, with the console delegating through `g_apps[]` instead of naming instances.

That is a change to **IFC-003 (App lifecycle and shell dispatch)**, which is v1 and exists. It is the
right home: M-TESTARCH §4 I4 already argues "the debug surface is part of every component's
interface", ADR-060 D0 made the apps components, and this is the sentence that finishes it. It also
deletes six typed instance names from `cmdGet.cpp` and makes `gen_get_keys.py` correct by
construction for the app half.

Direction check against ADR-060 D2a: `debug/` is level 2, `apps/` is level 3, `app.h` is level 0.
Putting the accessor on `app.h` and delegating through `shell/appTable.h`'s `g_apps[]` is a level
2 → level 0 dependency in the console and a level 3 → level 0 dependency in each app. Both are
downward. **No level violation.** The current arrangement — `cmdGet.cpp` (L2) naming `g_ClockApp`
(L3) — is the upward one, and this amendment removes it. That is worth saying plainly: R3, done at
the right seam, *repairs* an existing levelization violation rather than creating one.

### 1.4 What I concede

The admission rule — "an app earns FEATURE coverage by publishing observables, and one that cannot
gets a dated `UNOBSERVABLE` record rather than quiet green rows" — is the best idea in the document
and I would not weaken it. **R4** is correct as written and its ledger shape (dated, task-owned, no
wildcards, a stale row is itself a failure) is the pattern C6 already proved. **R6**'s framing that
"observables built without a test, and tests written without an observable, are the same defect from
two ends" is exactly right, and `H-5` is the sharper half of it.

---

## 2. What does it cost?

### 2.1 The constraint, stated correctly

Assumption **A4** understates the constraint in a way that matters. It says "the debug build is the
memory-constrained one". EXP-016 measured something stronger:

> "it isn't 'the debug env is tight,' it's **`SERIAL_DEBUG`'s own static footprint consumes ~all of
> this chip's static-BSS headroom, in any build that includes it**" — a production build with
> `-DSERIAL_DEBUG` only landed at the identical `_bss_end` address as full debug.

So every firmware obligation in this document — R3(b–d), R5, R8, R14, R25, R26, R27 — draws from
**one shared pool**, and the pool has been measured at 0 B (EXP-015/021, 2026-07-29/30), 40 B
(2026-08-02, after the M-CEEFAX cut), 304 B (ADR-059 `:425`) and 9 920 B (M-PLEDIT, 2026-08-07,
post-`get player`). The spread is not noise; it is reclaim events. **Any number in this section is
dead the moment someone lands a buffer**, and the governing rule is ADR-060 D8's: re-derive fresh
from `run/build-debug` + the `.map`, never remember.

Flash is not the constraint. `app0` is `0x280000` = 2 621 440 B (`app/partitions_no_ota.csv`); the
debug binary was 1 873 168 B at the last recorded measurement — **~748 KB spare**.

### 2.2 The four observables, priced

Unit costs, from the shipped implementations:

| Item | Evidence | Cost |
|---|---|---|
| one `dbgGet` key branch | `apps/cryptoApp.cpp` `dbgGet` — `strcmp` + `snprintf` + format literal | ~90 B `.text` + ~60 B `.rodata` ≈ **150 B flash**, 0 B RAM |
| one `uint32_t` counter | — | **4 B `.dram0.bss`** (8 B once aligned beside a status byte) |
| an aggregated multi-field key | `get player`, `cmdGet.cpp:575-599` — 12 fields in one line | M-PLEDIT measured the whole P2 change at **+16 B `.dram0.bss`, +656 B debug flash** |
| a debug injector flag | EXP-024 / PROP-010 rung 2, cited by R8 | **+8 B `.dram0.bss`** |
| `set queue N` (a whole injection command) | M-PLEDIT measurements table | **+752 B debug flash, 0 B RAM** |

**As R3 is written** (four observables × 13 apps, per-app):

* 52 new keys × ~150 B ≈ **7.8 KB flash**, plus per-app plumbing ≈ **8–12 KB debug flash**.
* progress + result state where it does not already exist: ~8 B × 13 = **~104 B `.dram0.bss`**,
  realistically **120–150 B** with alignment and the odd `char[]` for an entry-state name.
* CPU: one increment per active app tick — unmeasurable. There is only ever one active app.

**With my §1.2 amendment** (identity + progress once in the shell):

* one `uint32_t g_appTicks[APP_COUNT]` = **52 B `.dram0.bss`**, one console branch ≈ **300 B flash**,
  replacing 26 per-app branches ≈ 3.9 KB.
* residual per-app (result + entry-state, and many apps already have the field): **~4 B RAM × 13 ≈
  52 B**, ~26 keys ≈ **4 KB flash**.
* Total: **~60–110 B `.dram0.bss`, ~4.5–5 KB debug flash.**

### 2.3 Verdict on affordability

**Affordable as amended; affordable-but-uncomfortable as written; and it would have been
unaffordable in July.** 150 B against a 9 920 B headroom is 1.5 %; 150 B against the 0 B headroom
EXP-021 measured is a link failure. The document should not promise the contract as a single
deliverable. The affordable subset, in landing order:

1. **The shell half — identity guard + tick/repaint counters.** ~60 B RAM, ~300 B flash, one commit,
   fixes `A-8` for all thirteen apps. Do this first; it is the highest ratio in the whole document.
2. **R14's armed-injection enumeration.** ~8 B (a bitmask over a generated injector list, not a
   string), and it is the only requirement that catches the *fourth* leaked injector.
3. **Result + entry-state, per app, one app per commit, each with a re-derived `.map` delta and an
   ADR-060 D0a-style per-app ceiling of 32 B `.dram0.bss`.** A ceiling that low is deliberate: it
   forces reuse of existing fields (`_s.lastCryptoFetch`, `dataTask::lastCryptoHttpCode()`) instead
   of new state, which is what WP-Z's costing assumed anyway.
4. **R5's signature command** — see §3; it is ~0 B static because it reuses screendump's per-call
   `malloc`.

What I would cut if the pool is at 0 B again: clause (d) entry-state as a *new* field. Everything
else is either shell-owned, reuse of existing fields, or transient heap.

---

## 3. The render-signature idea — is it sound?

**Short answer: the idea is sound, the specification is wrong about this target, and the correction
makes it cheaper and stronger than proposed.** This is the load-bearing idea for the Clock problem
and it survives.

### 3.1 The specification's error

R5 asks for "a device-computed signature over **the buffer the app drew from**". On this hardware
there is usually no such buffer. `apps/clockApp.h` draws directly to the global `tft`
(`display/tft.h`) — `_drawDigital`, `_drawFlipPanel`, `_drawNixieTube`, `_drawVFDDigitSlot` are all
immediate-mode TFT_eSPI calls. A repo-wide grep finds `TFT_eSprite` in exactly **two** places:
`aquarium/aquariumApp.h:226` and `stock/stockHeatmap.cpp:182`. Clock — the family this requirement
exists for, at 7 % SOUND — has no buffer to hash, and `clockApp.h:194-197` explains why in its own
comment: a full-tube `uint16_t` scratch is 10.6 KB, "enough to overflow this board's tight DRAM
budget", so the Nixie renderer tints in bands. **Adding a shadow framebuffer to make R5 implementable
is not on the table**: 320×240×2 = 150 KB, against a 290 KB INTERNAL ceiling with 60 KB reserved for
TLS (`app/mem_manifest.yaml`).

Nor is hooking the render path. TFT_eSPI's drawing entry points are not virtual in the general case,
the library is a `lib_deps` dependency rather than a vendored fork (unlike `SD` and
`WiFiClientSecure` in `app/lib/`), and a tee that hashed draw primitives would hash *intent*, not
result — it would report a face as drawn even if the SPI write never reached the panel, which is one
of the failure modes worth catching.

### 3.2 The correction: hash the panel, not a buffer

The mechanism R5 needs is already shipped, already DUT-proven, and already has a `run/` script:
**GRAM readback**. `app/src/debug/serialConsole/cmdMisc.cpp:66-131` implements `screendump` — it
calls `tft.readRect(x, y+ry, w, rows, band)` in 8-row bands, undoes TFT_eSPI's deliberate byte swap,
base64s and streams. MISO is wired (`app/platformio.ini:37` `-DTFT_MISO=12`) and the read clock is
set to a value that was *empirically* stabilised (`:57` `-DSPI_READ_FREQUENCY=2500000`, lowered from
20 MHz by TASK-340 for signal integrity). `cmdColorProbe` (`cmdMisc.cpp:135-190`) verified the whole
readback path against known values **25/25**.

So the requirement should read: *a device-computed FNV-1a signature over a `tft.readRect()` region,
exposed as an on-demand console command.* Concretely, `get sig <x> <y> <w> <h>` returning
`{hash, inkCount, distinctColors, bgColor}` — screendump's band loop with the base64 and the
`Serial.write` replaced by a rolling hash and three counters.

This is **strictly better than the proposal in three ways**. It is ground truth — downstream of the
app, the renderer, the SPI bus and the panel, so it catches failure modes a draw-log hash cannot. It
costs **0 B static** (the band buffer is already `malloc`/`free` per call, TASK-423) and a few
hundred bytes of flash. And it works identically for all thirteen apps, sprite or not, with no
per-app code at all — which is the property R3 kept failing to have.

### 3.3 Frame timing

**None, because it must not be in the render path.** The signature is computed on demand, from the
host, between frames, exactly as `screendump` is today. Read cost is arithmetic: `readRect` moves 3
bytes per pixel at 2.5 MHz, so a region of *w×h* pixels costs roughly `w·h·24 / 2.5e6` seconds —
**~69 ms for a 120×60 clock face, ~0.74 s for the full 320×240 panel**. Screendump's ~18 s is
serial-transfer-bound (115 200 baud), not readback-bound; dropping the transfer is what makes this
usable inside a test body. Two operational constraints carry over from the shipped command and must
be restated in the requirement: the TWDT is 15 s with `panic=true`, so any multi-band loop must feed
it (`cmdMisc.cpp:99` `esp_task_wdt_reset()`); and the app must be quiescent when the region is read,
which is what `get idle` is for (M-TESTBASE P4). A signature taken mid-repaint is a torn read.

### 3.4 Determinism — the real problem, and the omission

Stability across legitimate redraws is where this either works or does not, and the answer differs
per assertion type:

* **Deterministic and assertable against a golden**: static content only. A Clock face's *chrome* —
  tube outlines, bezel, VFD off-segments, the date row's background — is drawn from constants and
  fixed palettes. RGB565, no dithering, no alpha, no antialiasing in the TFT_eSPI paths this project
  uses; `colorprobe`'s 25/25 says the write→read round trip is bit-exact. **A golden hash over a
  chrome-only region is legitimate.**
* **Not assertable against a golden**: anything containing the time, a blink phase, an animation
  frame, RSSI, or a VU level. `clockApp.h:210-215` documents the colon blinking at 0.5 Hz and both
  circles being redrawn every frame. A hash over the digits region changes every second by design.
* **The omission**: **there is no time injection in the console.** `cmdSet.cpp` implements
  `clockStyle`, `nixieTheme`, `vfdTheme`, `dateFmt`, `playerMode`, `wifiKick`, `certbreak`… and no
  `set now`/frozen clock. Without one, a golden signature over any digit region is unwritable, and
  R5's promise for the Clock family rests on regions that do not contain the thing the family is
  about. **This is a prerequisite the requirements document does not name**, and it is small: a
  `set now <epoch>` plus a "clock frozen" flag under `SERIAL_DEBUG`, ~8 B and a branch. I would make
  it a numbered requirement.

For everything the golden cannot cover, the assertions must be **differential or structural**, and
these are the ones that actually answer `H-2`:

| Claim | Signature assertion | Kills the black rectangle? |
|---|---|---|
| "the face rendered at all" | `inkCount > N` and `distinctColors > 1` over the canvas | **yes — directly**; a solid black region has ink 0 and 1 colour |
| "the face changed when the style changed" | `sig(styleA) != sig(styleB)`, both non-constant | yes |
| "the flip animation ran" | ≥3 samples across the window, ≥2 distinct signatures | yes |
| "the colon blinks" | two samples one second apart differ in the colon region only | yes |
| "the chrome is unchanged after a repaint" | golden hash over a static sub-region | yes |

Note that **the single most valuable assertion needs no golden and no frozen clock**:
`inkCount`/`distinctColors` over the canvas turns "a clock face rendering as a solid black rectangle
passes all fourteen ids and all five criteria" (`H-2`) into a failing constant, today, with one
command. That alone is worth the requirement.

### 3.5 The failure mode the requirement must own

A readback that returns garbage is a **false FAIL**, and this project has already been bitten by the
underlying physics once (TASK-340: 20 MHz reads were unreliable on this board's MISO). A signature
assertion is therefore exactly the negative-assertion hazard **R12** describes, one layer down: if
the readback channel is dead, every signature comparison "fails" and blames the firmware. **Every
signature-based id must be preconditioned on a live readback channel**, and the check already exists
as `colorprobe`. That belongs in the HEALTH class — see my amendment to R39.

### 3.6 Answer

**The idea works.** Re-specified as an on-demand FNV over `tft.readRect()`, with ink/entropy metrics
beside the hash, gated by a `colorprobe` liveness check and supported by a `set now` time freeze, it
is sound for display content, costs no static RAM, does not touch the render path, and makes the
Clock family's central claim falsifiable for the first time. If it had *not* worked, the replacement
would have been `run/screendump` plus host-side image comparison for every visual claim — one 18 s
serial dump per assertion, which at Clock's fourteen ids is four minutes of a 60-minute budget for
one family, and which is why the device-side signature is worth specifying properly rather than
abandoning.

---

## 4. Seams and layering

### 4.1 Violations found

**R10 (host-side transcript mutation) cannot live where its verification implies.** The requirement
cites "the negative suites in `gate/` (BP-068)" as the precedent and the `gate/check_*.py` pattern as
the mechanism. But a mutation job must **import the suite bodies** to replay them, and M-TOOLING's
dependency rule is explicit: levels depend downward only, and *"nothing depends on `gate/`. A gate is
a leaf."* A gate importing `suite/serialdbg/` is an upward dependency (level 2 → level 3) and
inverts the rule the rest of the document is defending. **Amendment**: the replay engine is a `lib/`
member (`lib/replay.py` — transcript record/playback against a stubbed transport, no suite
knowledge); the *job* that drives it over every registered id is a **runner mode**
(`suite/serialdbg/runner.py --mutate`), which may import both. `gate/` gets only the thin
well-formedness check that every id declares a falsifier — which is where R9 already puts it.

**R10 also has an ordering dependency the migration table misses.** It cannot run until **R48** is
done: six modules execute their suite at import. R10 is listed as `additive` and R48 as `ratchet`;
in practice R48 is R10's precondition and should be sequenced before it, not merely counted.

**R3 creates an interface without saying so** — covered in §1.3. As written it is also the one
requirement that would *entrench* the existing L2→L3 violation (`cmdGet.cpp` naming `g_ClockApp`) by
building a gate on top of it.

**R25 changes a published wire format with no version story.** See §4.3.

### 4.2 Non-violations — checked and cleared

* **ADR-060 levels.** Every firmware obligation in the document lands in `debug/` (L2) reading L0–L3
  state downward, or in an app (L3) publishing its own state. None makes a lower level include
  `apps/` or `shell/`. R3 as amended removes a violation. **Clean.**
* **ADR-060 D0/D0a component budgets.** The per-component ≤256 B `dram0_0_seg` rule is the right
  precedent for §2.3's per-app ceiling, and the document does not contradict it — it simply never
  cites it. It should.
* **ADR-061 debug/production separation.** Non-goal 6 ("every firmware obligation lands inside
  `SERIAL_DEBUG`") is correct and is already true by construction (M-TESTARCH §4 I3). No conflict.
* **`lib/` → `suite/` direction elsewhere.** R18's "one shared typed accessor in `lib/`", R24's
  single timeout policy, R29/R30's artifact, R33's single results layer and R47's single session
  layer all push work *downward* into `lib/`. That is the correct direction and it is the document's
  best structural instinct. **R33 additionally repairs the one violation M-TESTARCH §5 names** —
  `report.py`/`results.py` type-importing `Dut` from the suite it serves.

### 4.3 What should be an IFC

The document creates or tightens **three interfaces and names none of them**. That is my largest
process objection.

| Interface | Requirements that bind it | Status | My call |
|---|---|---|---|
| The serial debug console (`get`/`set`/`tap`/`drag`/`switchApp`) | R7, R14, R25, R26, R27, plus R3/R5's new keys | **has no IFC number at all**, despite `architecture.md:105-107` calling it "the DUT test surface for the whole VE suite" and M-TESTARCH §4 calling it "the test API" | **new IFC-007.** This is the seam the entire T3 tier is a client of, and it is the only major seam in the system with no contract document. IFC-004/005/006 are reserved stubs for far smaller things. |
| `App` debug surface | R3, R6, R15 | **IFC-003 v1 exists** and does not mention `dbgGet` | **amend IFC-003**, per §1.3 |
| The run result artifact | R28, R29, R30, R31, R32, R33 | none — the current interface is an unspecified `printf` at `lib/results.py:271` that a `sed` regex parses | **new IFC-008.** This is also the standing answer to WP-Z `A-7` / TASK-619: *specify it as an IFC, and make it the JSON sidecar* — both halves of the question, not one or the other. |

### 4.4 What should be an ADR

See §8. The short version: **five decisions**, of which two (the App interface change, and the
render-verification mechanism) change firmware and one (the DUT firmware lifecycle) changes a
standing operational instruction.

---

## 5. Conflicts with existing designs

### 5.1 M-TESTARCH §3b — duplicated, not contradicted, and one primitive is quietly re-scoped

M-TESTARCH §3b.3 proposed four ordered primitives. The mapping is clean:

| §3b.3 primitive | M-HARNESS2 | Relationship |
|---|---|---|
| 1. correlated commands | **R25** | same requirement, restated; §3b.6 already priced it as "a breaking change to the wire format … should land *with* the `lib/dut.py` extraction" — **that landing has passed** (M-TESTBASE P1 shipped `lib/dut.py`), so R25 now costs strictly more than §3b.6 planned. M-HARNESS2 §14 does not say this. |
| 2. completion semantics | **R27** | R27 is **narrower and better**: it splits the cheap half (read the `"skipped"` flag the reply already carries — `H-8`) from the firmware half (change ack timing). §3b.3 conflated them. |
| 3. quiescence predicate | — | **landed** (TASK-518, `get idle`). Correctly not re-proposed. |
| 4. watch / subscribe | **R26** | same, with §3b.3's scope discipline (~10 keys, derived from the loops) preserved verbatim. |

**No contradiction.** But M-HARNESS2 should state that it *supersedes* §3b.3 as the live version of
items 1, 2 and 4, and should carry §3b.6's honest-cost paragraph forward — particularly the sentence
about item 1 landing with the session-layer change, because that opportunity is gone.

One genuine tension: M-TESTARCH §3b.4 says physical waits "must remain" and names the DRD reset gap,
WiFi association and firmware connect timeouts. **R23** admits this ("a physical wait whose duration
cites a firmware constant by name") but **AC11** sets the target at "≤ 25, each citing a firmware
constant" without deriving it from the number of genuinely physical waits. 25 is a round number, not
a measurement, in a document whose whole discipline is that every number is measured. Flag, not
block.

### 5.2 M-TESTBASE phase 1 §5 — three deferrals reopened, one legitimately

M-TESTBASE §5's deferral table is explicit, and M-HARNESS2 §16 claims to leave it alone ("R41 is the
only one this document touches, and it is a SHOULD"). That claim is **not quite true**:

* **"Correlation IDs / `watch` subscribe — phase 2. Gated on P4 producing evidence."** M-HARNESS2
  proposes both, as **R25 (MUST)** and R26 (SHOULD). P4's evidence *did* arrive — `get idle`
  measured 2.06 s busy→idle cold against sub-50 ms warm, i.e. correctness rather than speed — and
  R26 honestly reads that as an argument for a *narrow* subscribe. Fine. But **R25 is a MUST that
  M-TESTBASE deferred to phase 2 on an evidence gate**, and the evidence that arrived argues for
  less protocol work, not more. R25's justification is different and stronger (`C-18`, `C-2` — a
  one-reply desync is undetectable and `T-UART-01`'s `except` branch is unreachable), so I do not
  reject it; I require it to be re-scoped as additive (§6 of the disputed table).
* **"Conformance matrix for all 13 apps — the *pattern* is proven by P3 on the 3 modes first.
  Generalise after."** **R41** reopens this, and the document grades it SHOULD with the right
  reason. Accepted; P3 has landed and the pattern is proven, so the deferral has expired on its own
  terms.
* **"T1 host unit tier + Arduino shim"** stays deferred in both documents (A3, non-goal 4).
  Consistent.

### 5.3 M-TESTARCH §2c — the levels claim that must not be quoted back

M-TESTARCH §2c measured that **L0+L1 are 15 849 lines, 54 % of the firmware, with zero tests
addressing them**, and that every executable id enters through L2 and asserts on L3. **M-HARNESS2
does not change this and does not claim to** — but AC1's headline ("share of registered ids that
assert what they claim: 54 % → ≥ 85 %") reads like a coverage figure and will be quoted as one.
§2c's rule applies unchanged: *these are end-to-end coverage figures for L3 behaviour and must never
be quoted as component coverage.* The requirements document should carry that sentence in §13. That
is an omission, not a conflict.

### 5.4 TASK-566 / the class-order switch

M-HARNESS2 non-goal 8 correctly refuses to decide the switch and instead states what would have to
be true (**R35**–**R38**, **R20**). I agree with that boundary and with VE's reading that the switch
must not flip yet. **R35** + **AC8** (43 of 43 CORE ids declared, with written reasons) and **R36**
(no gating class depends on the network) are the two exit criteria I would accept as sufficient;
**R20**'s shuffle is desirable but should not gate the switch, because it is the most DUT-expensive
item in the document and the switch's risk is fully characterised by `B-1`/`B-2` without it.

---

## 6. The pinned-board requirement (RIG / R51)

**Half clean, half workaround — and the workaround half will rot.**

The clean half is not really about pinning at all. *"MUST record which firmware it ran against"* and
*"MUST refuse to run rather than silently reflash when the requested build and the board's build
disagree"* are permanent properties of a trustworthy gate, they are already half-built
(`run/player-gate` checks build identity; `run/wr-gate` does not — `F-19`), and they are really
**R30**'s build-identity field seen from the entry point. I would accept those two clauses in any
world, pinned board or not.

The rotting half is *"MUST support running without restoring production firmware"*. As proposed —
and as TASK-618 frames it — that becomes a `DUT_NO_RESTORE=1` opt-out on a variable
`run/lib.sh:16` makes deliberately non-overridable. Three ways that decays:

1. **It is a suppression flag on an unconditional side effect.** The trap fires on success, failure
   and interrupt; the flag makes it fire *sometimes*. Every future reader must now know which mode
   they are in to know what state the board is in afterwards, and the failure is silent in both
   directions.
2. **Its justification has an expiry nobody owns.** A6 says "for the life of TASK-557 and possibly
   beyond". A flag whose reason is a task will outlive the task; this repo's own `wifi_creds.h` shim
   sat dead in the build for months (TASK-404).
3. **It entrenches the wrong ownership.** The real defect is that a *test* entry point owns
   *firmware lifecycle*. That coupling is why WP-Z's 80-minute session — which would settle 32 of 58
   open items — cannot be run at all.

**The non-rotting form is to remove the coupling, not to add a flag**: test entry points **verify and
refuse**, never flash and never restore. Flashing becomes an explicit caller action via the existing
`run/flash*` scripts, which is already how `run/flash-player`, `run/flash-webradio` and
`run/screendump` behave (none of them restores production). The entry point then reads the board's
build identity, compares it to what the run declares, and exits 4 ("the board is not a valid
subject", M-TESTARCH precedence §4) if they differ. That is smaller than the flag, deletes the trap
instead of guarding it, and gives **R30** its ELF hash for free.

**Interim**: sanction `DUT_NO_RESTORE=1` as a *dated exception owned by TASK-618*, with the ledger
row naming the verify-and-refuse conversion as its retirement condition — the same ledger discipline
this document imposes on everything else. It should not be the permanent answer, and R51 should not
be written as though it is.

One thing R51 gets exactly right and I want to reinforce: *"the safe resolution is an opt-out, **not**
killing the script mid-flight, which races the trap-guarded restore and can boot-loop the board."*
That is a recorded hazard on this rig and it belongs in the requirement.

---

## 7. Disputed requirements

Verdicts on the 13 requirements I engage with substantively; the remaining 42 I accept, 10 of them
with the comments recorded below.

| Req | Verdict | Objection (one sentence) | Amendment I would accept |
|---|---|---|---|
| **R3**(a) identity | **REJECT** | Identity is a shell fact and thirteen app-authored copies of it can each be wrong in the same way the test is trying to detect. | Replace with a console-level guard: a per-app key is refused with a named error when its owning app is not active, asserted by one generated conformance row over `APP_ORDER`. |
| **R3**(b–d) | **AMEND** | The stated seam (`dbgGet`) is not part of the `App` interface and four apps do not have one, so the contract has no home. | Add `dbgGet`/`dbgSet` to `app.h` under `SERIAL_DEBUG` and record it in IFC-003; move progress to a shell-owned counter array; keep result and entry-state per-app with a 32 B `.dram0.bss` ceiling each. |
| **R5** | **AMEND** | There is no "buffer the app drew from" on this target — Clock draws immediate-mode to GRAM and only two files use a sprite. | Re-specify as an on-demand FNV over `tft.readRect()` (`get sig x y w h`, reusing `cmdMisc.cpp`'s band loop), returning hash + ink count + distinct-colour count; explicitly out of the render path; add a `set now` time freeze as a named prerequisite. |
| **R6** | **AMEND** | A MUST whose only enforcement is "a review item" fails this document's own standard, stated in its §1. | Split: R6a (apps) MUST, mechanised by R3's conformance rows; R6b (non-app features) SHOULD, review-enforced and labelled as such. |
| **R7** | **AMEND** | Three MUSTs (R1, R3, R42) consume the generated key list, and the generator is measurably wrong — `gen_get_keys.py:44` globs `app/src/**/*.h` only, so every `dbgGet` body moved to `.cpp` by TASK-471 is invisible. | Promote the *generator-completeness* clause to MUST (full-tree scan, count compared in `run/check`); keep additive-only/no-renames as SHOULD, where BP-024's clean record justifies it. |
| **R10** | **AMEND** | The replay engine must import suite bodies, and `gate/` is a leaf that nothing may depend on — putting it there inverts M-TOOLING's own dependency rule. | Engine in `lib/replay.py` (transport-stub only, no suite knowledge); driver as `runner.py --mutate`; `gate/` keeps only the "every id declares a falsifier" check. Sequence it after R48, which is its precondition. |
| **R15** | **AMEND** | Auto-clearing injection flags in `resume()` silently breaks the legitimate arm→switch→observe pattern and hides the leak R14 exists to attribute. | Clear on `init()` only, plus one explicit `set injclear` the harness calls at boundaries; leave detection to R14, which does not depend on firmware discipline. |
| **R20** | **AMEND** | A MUST that §14 files as "scheduled, a calendar item, not a continuous gate" is a SHOULD with a date, and AC13's three consecutive full runs is ~3 h of the scarcest resource on the project. | Split as R11 already does: the shuffle *capability* and its verdict-diff report are MUST; the *campaign* is SHOULD/scheduled. Answers §17 OQ5: per-family shuffle first, cross-FEATURE only after a family-level run comes back clean. |
| **R25** | **AMEND** | It is written as a flag-day wire-format change touching every consumer, and it does not have to be one. | Make the sequence id **optional and echoed only when supplied** (`get#7 wifi` → the reply carries `"seq":7`): unpatched consumers keep working, `lib/dut.py` opts in immediately, the count of non-correlated call sites becomes the ratchet, and the document's only flag-day disappears. |
| **R26** | **DEFER** | Async push lines break the one-line request/response invariant every existing consumer assumes, on the memory-constrained build, for a win P4's evidence suggests is correctness on ~10 keys. | Defer to an ADR taken jointly with R25; do not build it before the correlated-reply ratchet is complete and the ~10-key list has been derived mechanically from the loops. |
| **R39** | **AMEND** | The five listed checks omit the one that every R5 assertion depends on: proof that the display readback channel is alive. | Add a sixth: a `colorprobe`-shaped write/read round trip as a HEALTH check. Without it a degraded MISO read (TASK-340's exact failure) reports every render signature as a firmware defect. |
| **R45** | **AMEND** | "Wire it in or delete it" states the rule without taking the decision, which WP-Z routed to me as TASK-619 `A-17`. | **Decision**: `app/gen/mem_layout.h` has real firmware consumers (`main.cpp:140`, `dataTaskStorage.cpp:23`) and stays. `app/gen/mem_layout.py` — generated "for the test suite", zero importers — is **kept only if R42's mirror gate consumes it as a parse source within one milestone; otherwise deleted**, with the deadline in the ledger row. |
| **R51** | **AMEND** | The pinning clause resolves a real blocker with a suppression flag on a lifecycle the test entry points should not own. | Test entry points **verify and refuse** (read the board's build identity, exit 4 on mismatch) and never flash or restore; flashing stays an explicit caller action. Sanction `DUT_NO_RESTORE=1` as a dated TASK-618 exception whose retirement condition is that conversion. |
| **R53** | **AMEND** | Budgets that are "reported, not failed" are a SHOULD, and the measurement itself is already R30's artifact field; the APP ≤6 min figure has no derivation. | Fold the measurement into R30 (per-class elapsed in the artifact, MUST); keep the budget *table* as a SHOULD-grade target; derive or drop the APP row — 13 apps × ~7 rows on a DUT where a cold app switch alone measured 2.06 s busy→idle is not obviously a 6-minute job. |

**Accepted with comment** (no amendment required):

* **R2** — I went looking for the false-positive shape (a legitimate `set X` … `get X` with the
  interposition off-body) and the `interposed:` justification field covers it. Sound as written.
* **R8** — correctly SHOULD; the honesty about the benefit side being unmeasured is exemplary and
  should be the house style.
* **R14** — the cheapest firmware ask in the document (~8 B) and the only one that catches the
  *fourth* leaked injector. Strengthen the implementation note: a bitmask over a **generated**
  injector list, not a hand-maintained string, so it cannot drift from the injectors it enumerates.
* **R16** — this also settles TASK-619 `B-14`: **keep the `effect` axis.** WP-B was right that a
  field with no consumer should go; R14/R17/R19 are now that consumer, and `persisting` is a real
  new value (`H-10`'s ~50 flash writes per run).
* **R28** — `UNMET` is the right addition and "a test that cannot run is not *not applicable*, it is
  an unestablished premise" is the correct framing. The exit-code question (§17 OQ3) is an ADR item,
  not a detail.
* **R34** — agreed, and it is the counterweight AC1 needs: a coverage figure generated from the
  binding cannot be improved by writing tests that cannot fail.
* **R36** — agreed without reservation. "A network outage must not be able to declare the firmware
  untestable" is the sentence I would put at the top of the gating section.
* **R41** — I wanted this at MUST and withdraw: the existing hand-copies are correct today, the
  migration is real, and M-TESTBASE's "prove the pattern on 3 modes first" deferral has expired on
  its own terms rather than been overridden. SHOULD is right.
* **R44** — honestly graded down, for the right reason. A ratchet that never completes is not a MUST.
* **R48** — the strongest requirement in the document. Six modules that reset the board at import
  contaminated a live TASK-557 observation window *during the review that found them*; this is a
  defect with a live cost, and the fix is a `__main__` guard each.

**Counts: ACCEPT 42** (10 with comment, 32 without) **· AMEND 12 · REJECT 1** (R3 clause (a))
**· DEFER 1.**

---

## 8. Architectural omissions

Things that matter and that the requirements document does not say.

1. **No interface is named.** Three interfaces are created or tightened and none gets an IFC number
   (§4.3). The console in particular — "the test API", the surface the entire T3 tier is a client of
   — is the largest seam in the system with no contract document, while IFC-004/005/006 are reserved
   stubs for smaller things.
2. **The `App` interface change is invisible.** R3 reads as a VE gate; it is an ABC change plus a
   console refactor plus thirteen app edits, and nobody has scheduled that.
3. **A4 understates the memory constraint.** It is not "the debug env is tight" but "`SERIAL_DEBUG`'s
   static footprint consumes ~all of this chip's static-BSS headroom in *any* build that includes it"
   (EXP-016). Every firmware requirement here draws from one pool that has been measured at 0 B.
   There is no per-requirement ceiling and no ADR-060 D0a citation.
4. **No host-gate budget.** The document proposes roughly fifteen new `run/check`/`check-docs` gates
   and budgets DUT seconds to the second (§12) while saying nothing about the gate that runs on every
   commit. `run/check` is 11 gates today and its entire value is that a developer will actually run
   it. A host-side budget (I would suggest ≤ 90 s wall-clock for `run/check`, ≤ 15 s for
   `check-docs`) belongs beside R53.
5. **No time injection, and R5 needs one.** `cmdSet.cpp` has no `set now`; without it no golden
   signature over any Clock digit region is writable, which is the family R5 exists for (§3.4).
6. **No liveness precondition for the readback channel.** R12 requires negative assertions to prove
   their channel is live; R5's channel is a 2.5 MHz SPI read that this project has already seen fail
   at a higher clock, and nothing preconditions on it (§3.5, amendment to R39).
7. **Silent on region coordinates for R5.** The panel is 320×240 with a 45 px taskbar and a 275×240
   canvas; `shell_layout.h` is generated and `run/audit-origin` exists for exactly this class of
   error. Signature regions must be derived from the generated layout under R42, not typed — the
   document's own mirror rule, unapplied to its newest mechanism.
8. **AC1's 54 % → 85 % will be misread as coverage.** M-TESTARCH §2c's rule — these are end-to-end
   figures for L3 behaviour and are not component coverage — needs restating in §13, or the number
   will be quoted at a milestone review.
9. **No statement of who pays.** §17 OQ1 asks the question; the requirements are written as MUSTs
   regardless. R3(b–d), R5, R14, R25, R26, R27 and the `set now` prerequisite are all @Developer work
   on the constrained build, and none of it is in a task board.
10. **The §14 migration table has an unstated ordering constraint.** R48 is R10's precondition; R25
    is R26's; R28/R31 precede R38; R42's parse sources must exist before R5's coordinates and R44's
    citations can reference them. The table sorts by *mode*, which hides the *dependency* graph.

---

## 9. What I would need decided by ADR before implementation starts

Five decisions. The first three change firmware; the fourth changes what a gate means; the fifth
changes a standing operational instruction.

| # | Decision | Why it must be an ADR, not a design note |
|---|---|---|
| **A** | **Does `App` gain a debug surface?** Specifically: add `dbgGet`/`dbgSet` to `app.h` under `SERIAL_DEBUG` with safe defaults; move identity and progress to shell ownership; delegate through `g_apps[]` and delete the six typed instance names from `cmdGet.cpp`; record it all in IFC-003. | It changes the system's primary seam (`architecture.md:95`), touches all thirteen apps, and repairs an L2→L3 levelization violation. ADR-060's component model is what makes it coherent; nothing smaller than an ADR can amend it. |
| **B** | **Is GRAM readback the sanctioned render-verification mechanism?** Sanction `get sig` over `tft.readRect()`, the on-demand-only rule (never in the render path), the ink/entropy metrics beside the hash, the `colorprobe` HEALTH precondition, and the `set now` time freeze as a named prerequisite. | It commits the project to a verification approach for every future visual claim, it depends on a hardware property (MISO wired, 2.5 MHz) that a board revision could remove, and R5 is a MUST that cannot be met without it. |
| **C** | **Is the serial console a versioned interface, and may it push?** Give it IFC-007. Decide (i) correlated replies as *optional and additive* rather than a flag-day, (ii) whether unsolicited event lines are permitted at all, and (iii) the additive-only/no-rename rule with its generated key list as the gate. | R25 is the document's only flag-day and touches every consumer; R26 would break the one-line request/response invariant every consumer assumes. Both are irreversible in practice. |
| **D** | **Is the result artifact the interface?** Adopt R28's closed verdict vocabulary including `UNMET`, R29's schema-versioned JSON as the sole machine interface, R30's premise fields, and R31's typed gating — as IFC-008. Decide `UNMET`'s exit code (§17 OQ3) against M-TESTARCH precedence §4's 3-vs-4 split and EC-G7's enumerated consumers. | This is WP-Z `A-7` / TASK-619 arriving as a decision. It changes what every gate blocks on, it retires a `sed` parser that already produced a false REGRESS (TASK-573), and the exit code is a consumer contract with named consumers. |
| **E** | **Who owns firmware lifecycle at a DUT entry point?** My proposal: entry points verify-and-refuse, never flash or restore; `DUT_NO_RESTORE=1` is sanctioned only as a dated TASK-618 exception with that conversion as its retirement condition. | It overrides a deliberate non-overridable in `run/lib.sh:16`, it is currently blocking an 80-minute session that would settle 32 of 58 open items, and getting it wrong can boot-loop the board. |

Two further items I would want @PM to decide, which are policy rather than architecture: whether the
**admission rule** (no FEATURE test counted as coverage until R3 is met) is adopted — §17 OQ1 — and
who schedules the @Developer work in omission 9.

---

## 10. Summary of what I am signing

**Yes**, with: R3 re-seated on `app.h`/IFC-003 with identity and progress moved to the shell; R5
re-specified as on-demand GRAM readback with a time-freeze prerequisite; R25 made additive; R51
converted to verify-and-refuse; ADRs A–E taken first; and the OBS contract landed one app per commit
against a freshly derived `.map`, never as a sweep.

**The single highest-ratio item in the document is not in the document**: the shell-side identity
guard and tick counter — ~60 B of `.dram0.bss`, one commit — which fixes `A-8` for all thirteen apps
including the four that have no `dbgGet` at all. It should land before anything else in group OBS.
