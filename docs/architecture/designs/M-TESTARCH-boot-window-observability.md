# Design — M-TESTARCH: the boot window is unobservable, and the harness is tuned around that

> Owner: Architect
> Status: proposed
> Date: 2026-09-01
> Revised: 2026-09-01 — independent review returned APPROVE WITH CHANGES; seven must-fix items
> applied, TASK-562 withdrawn. See §12 for what changed and what I pushed back on.
> Companion to: [M-TESTARCH](M-TESTARCH-test-architecture.md) (the test architecture this belongs to),
> [harness-sync-rethink](harness-sync-rethink.md) (which covers *steady-state* sync; this covers the boot window)
> Feeds: one ADR + one IFC — **owed on acceptance, not written yet**; ids are allocated when they are
> created, not reserved here (see §9)
> Tracked-as: TASK-560, TASK-561, TASK-563 (TASK-562 withdrawn at review — §5 Option A)
> Registers: serialdbg-001 (extended — boot-phase token stream) · X066

---

## 1. The defect, measured

**The DUT's debug console does not answer for most of boot, the length of that window is decided
by the network rather than by us, and the harness compensates with hand-tuned constants instead of
with a signal.**

Every claim below was verified against the working tree on 2026-09-01. Commands are implied by the
citations so they can be re-run rather than believed.

| # | Claim | Evidence |
|---|---|---|
| 1 | `handleSerialCommands()` has **exactly one** call site in the whole firmware | `app/src/main.cpp:268`, inside `loop()`. Repo-wide grep finds only that call, the declaration (`app/src/debug/serialConsole/console.h:15`), the definition (`app/src/debug/serialConsole/console.cpp:191`) and one comment (`app/src/main.cpp:241`). **Nothing pumps the console during `setup()`.** |
| 2 | `setup()` is long and the console is dead for all of it | `setup()` spans `app/src/boot/boot.cpp:140` to `:731`. `Serial.begin(115200)` is at `:156` — so the UART is *up* within microseconds of reset and the dispatcher is unreachable for the remaining ~590 lines. |
| 3 | setup() blocks in loops that pump *other* subsystems but not the console | The NTP wait at `app/src/boot/boot.cpp:554-558` runs up to 5 s calling `delay(50)`, `yield()` and `winampDisplay.tickMarquee()` — alive, looping, **animating the display**, and deaf to serial. The WiFi cascade does the same at `:306`, `:451` and `:480` (`delay()` + `esp_task_wdt_reset()`). The SPIFFS-failure path at `:226-232` is `while (1) yield();` — a permanently mute board that looks identical, on the wire, to a board that is merely slow. |
| 4 | Boot-to-console is **1 s … 6 s … unbounded**, and the network picks the number | One boot on this device: `[wifi-ev] t=1871 STA_GOT_IP` → `[time] synced … in 4002ms` → first `[I][hb] … uptime=00:00:06`. A different boot, same device: `synced in 0ms`, first heartbeat at `uptime=00:00:01`. The same log carries boots looping on `STA_DISCONNECTED reason=201` (NO_AP_FOUND), where the cascade runs its full candidate list before returning. |
| 5 | The harness bridges that with a blind sleep | `run/lib.sh:19` — `BOOT_WAIT="${BOOT_WAIT:-8}"` — consumed as `sleep "$BOOT_WAIT"` in **12 run scripts**. Eight seconds is a point estimate of a quantity measured at 1 and at 6 and known to be unbounded. |
| 6 | **The readiness gate skips silently for a board that is responsive but not ready** | See §1.1 — this claim was wrong in the first draft and is restated there in full. |

### 1.1 Claim 6, corrected

**The first draft of this document said a missed boot banner makes the harness "declare itself ready
in 2 s and start issuing commands against a board in unknown state, with no failure raised". That is
wrong, and the review caught it.** `Dut.__init__` calls `_verify_debug_firmware()` immediately after
`_wait_for_ready()` (`app/tools/lib/dut.py:293`), which sends `get heap` with a 3 s timeout
(`:548`); `read_json` raises `TimeoutError` when nothing answers (`:623`). **A missed banner against
a genuinely dead or mute board therefore does abort.** The blanket claim is retracted.

What survives are two narrower defects, both real, both belonging to TASK-560:

**(a) The abort takes the wrong path.** `TimeoutError` is not a `SetupFailure`, so it misses the
serial-tail attach at `app/tools/lib/dut.py:294` — the tail that TASK-434 item 4 exists to print —
and it is not caught by `runner.py`'s handlers (`except SetupFailure` → `_setup_fail`,
`except serial.SerialException` → `_classify_serial_failure`, `app/tools/suite/serialdbg/runner.py:189-193`).
It escapes as a bare traceback with exit 1, so `run/test-targeted`'s `[SETUP-FAIL]` block never
prints and TASK-556's classifier never sees it. This is the same legibility hole TASK-434 was filed
to close, reappearing on a path nobody enumerated.

**(b) The genuinely silent case is a board that is *responsive but not ready*.** A board already in
`loop()` — mid-render, or with WiFi down, or still in a WiFi cascade the harness's open interrupted
— answers `get heap` fine. The ELF guard passes. And because every readiness gate in
`_wait_for_ready()` sits **below the early return at `app/tools/lib/dut.py:316`** (there is no
`if boot_seen:` block; the function simply returns when the banner is not seen within 2.0 s at
`:307`), the WiFi wait, TASK-434's bounded extension, the `get ip` fallback, the `get variant` and
`get playerMode` probes, and the first-Spotify-poll wait are **all skipped, with nothing printed and
nothing raised.** The run proceeds against a board whose network state was never established.

**§1.1's consequence follows from (b) only** — not from the retracted blanket claim:

- a suite that reports FAIL on tests whose real precondition (WiFi up, Spotify polled, mode
  restored) was never established;
- `port-busy` / `device-vanished` aborts attributed to the rig, when the harness in fact drove a
  board still inside its WiFi cascade (TASK-556 split those labels apart precisely because the
  wrong label sent an investigation down a false path more than once);
- and — the expensive one — **DUT hours spent on a rig-instability theory**, as in TASK-557, in a
  window where "the harness sometimes starts against an unverified board and says nothing" is a live
  alternative explanation that nothing in the code makes visible.

I am not claiming this caused TASK-557. TASK-557's own record is explicit that the phenomenon is
non-stationary and that nothing is established. I am claiming that while `_wait_for_ready()` can
skip every network gate without saying so, **no run's premise is verifiable after the fact**, and
that is a worse property for a test rig than any individual flake.

---

## 2. Why the constants are a symptom, not a design

The human's read — fragile, full of magic numbers — lands. Here is the inventory of every constant
on the readiness path, re-derived at review (the first draft's table had 8 rows and its prose said
"nine"; the real count is **13**, and two line references were wrong):

| # | Constant | Value | Where | Derived from what? |
|---|---|---|---|---|
| 1 | `BOOT_WAIT` | 8 s | `run/lib.sh:19` | **Nothing.** Not a firmware constant. Was load-bearing for reset safety until TASK-559 in the 4 stamped scripts; still the only gap in 3 others (§3 C3). |
| 2 | banner window | 2.0 s | `app/tools/lib/dut.py:307` | **Nothing.** Long enough for a banner already in flight, short enough not to hurt. Skips every gate below it. |
| 3 | `_DUT_WIFI_WAIT_S` | 25 s | `app/tools/lib/dut.py:164`, used `:323` | **Nothing.** Env-overridable (`DUT_WIFI_WAIT`) precisely because it is a guess; LL-096 tells operators to raise it on stormy days. |
| 4 | `_DUT_WIFI_WAIT_2_S` | 75 s | `app/tools/lib/dut.py:169`, used `:402` | **The one derived number**: sized so 25+75 clears `wifiDiag`'s `WIFI_SUP_DOWN_MS = 60 s`. This is what the rest should look like. |
| 5 | `--no-wifi` shell poll | 90 s | `app/tools/lib/dut.py:367` | Nothing. |
| 6 | …its inner probe | 3.0 s | `app/tools/lib/dut.py:371` | Nothing. |
| 7 | `get ip` probe | 5.0 s | `app/tools/lib/dut.py:416` | Nothing. |
| 8 | `get variant` probe | 5.0 s | `app/tools/lib/dut.py:441` | Nothing. |
| 9 | `get playerMode` probe | 5.0 s | `app/tools/lib/dut.py:465` | Nothing. |
| 10 | first-poll wait | 60 s | `app/tools/lib/dut.py:484` | "covers backoff after a failed startup poll" — plausible, unverified. |
| 11 | post-`reconnect` poll wait | 60 s | `app/tools/lib/dut.py:500` | Same, again. |
| 12 | ELF-guard `get heap` | 3.0 s | `app/tools/lib/dut.py:548` | Nothing — and per §1.1(a) its expiry is the mis-routed abort. |
| 13 | `_DUT_DRD_WINDOW_S` | 12 s | `app/tools/lib/dut.py:114` | **Under review** — TASK-555. Its named rationale (DoubleResetDetector) left the firmware in `ddf6433`, 2026-06-11. |

Thirteen numbers; **one** is derived. The project already knows this is the failure mode — an
"INCONCLUSIVE" test was once really an 8 s host wait against a 10 s `Audio.cpp` connect timeout —
and BP-026 already says count-derived test constants must be symbolic. The timing constants never
got the same treatment because **there was no firmware-side quantity to derive them from**: the
firmware publishes no statement of where it is in boot. The magic numbers are downstream of a
missing interface, so deleting them one at a time cannot work.

**The structural claim of this document**: the harness's boot-window timing is *inference over an
unobservable process*. Every constant above is a prior on a distribution the firmware could simply
report. Fix the observability and most of the constants stop existing; leave it and each retune
buys one rig-condition and creates the next.

---

## 3. Constraints the design must respect

These are not negotiable and any option that ignores one is rejected on that basis alone.

**C1 — Reset-on-open is load-bearing.** The ch341 driver raises DTR during `os.open()` regardless of
userspace settings, so opening the port resets the ESP32; `_wait_for_ready()` is built to observe
*that* boot (`app/tools/lib/dut.py:299`). A prior review established that suppressing the reset
would silently disable every readiness gate — the gates all sit below the `boot_seen` early return,
so a board that does not reboot on open takes exactly the §1.1(b) path. **Do not suppress the reset.
Make the observation of it reliable instead.**

**C2 — The harness cannot watch a boot it did not cause.** Between `pio upload`'s hard reset and the
harness's `open()` there is no observer. Any design that claims to synchronise on the *post-flash*
boot must explain how it sees it; none of the options below do. The boot the harness synchronises on
is the one its own open causes — and that is *fine*, it just has to be the boot it actually
observes. **C1 and C2 together carry more weight than the first draft gave them: because the open
causes the boot, the port is already open when the firmware's first line prints, so a signal emitted
at the top of `setup()` cannot be missed on the boot being gated.** That is the argument that
withdrew TASK-562 (§5 Option A).

**C3 — TASK-559 landed, but it covers a third of the surface. Corrected at review.** The first draft
said "`BOOT_WAIT` is no longer load-bearing for reset safety" flatly. Measured:

- `sleep "$BOOT_WAIT"` appears in **12 run scripts**: `test`, `test-targeted`, `test-sync`,
  `player-gate`, `ae04`, `wr-gate`, `wr-soak`, `pr-soak`, `pr-fetch-soak`, `stress`, `task488`,
  `task424-repro`.
- `stamp_reset_gap` is called in **4**: `run/test:106`, `run/test-targeted:56`, `run/test-sync:46`,
  `run/player-gate:312`.
- Of the 8 unstamped, **3 open a raw `serial.Serial` instead of going through `dut.py`** —
  `run/wr-gate` → `app/tools/test_adr045_gate.py:60`, `run/wr-soak` →
  `app/tools/test_webradio_soak.py:57`, `run/ae04` → `app/tools/test_ae04_teardown.py:107`. Those
  three never consult the gap file at all, so **for them the blind sleep is the only reset gap that
  exists, and stamping alone would be a no-op.**

So C3 is: *`BOOT_WAIT` is no longer load-bearing for reset safety **in the four stamped scripts**,
and remains the sole gap in three others.* This is what makes §5 Option D possible **and** what
bounds it — see §6 TASK-563 and §8 R4.

**C4 — The 12 s window is under review (TASK-555), so nothing here may hardcode a fresh assumption
about it.** Every option below treats `_DUT_DRD_WINDOW_S` as an opaque input owned by dut.py's
existing guard. If TASK-555 retires the rule, nothing in this design changes; if it re-derives a
different number, nothing here changes either. That independence is deliberate.

**C5 — Production behaviour must not change.** The console dispatcher itself ships in production
(only `reconnect` is compiled in — `app/src/debug/serialConsole/console.cpp:82-115`), and the boot
banner is deliberately production-safe (ADR-021 Decision 4). Anything that changes what production
firmware *does* during boot, as opposed to what it *says*, is out of scope.

**C6 — There is an accidental safety invariant, and it must be stated before anyone trades it away.**
Because `handleSerialCommands()` runs only from `loop()`, bytes that arrive during `setup()` sit in
the UART RX buffer and are dispatched on the first `loop()` iteration. **No console command can ever
execute against half-initialised state.** That property is free, total, and currently guaranteed by
construction. It is exactly what §5 Option A proposed to give up, and the review was right that the
design did not confront it.

---

## 4. Goals

1. A run can prove, from its own output, that the board was in a known state before the first test
   command was sent. Today it cannot.
2. The harness never proceeds silently on a missed signal, and never aborts on a path that skips the
   evidence capture.
3. Boot-window timing constants are either derived from a firmware-published quantity or deleted.
4. No change to production boot behaviour, no loss of C6, and no change that makes a wedged board
   harder to recover.

Explicit non-goal: making boot *faster*, or making the WiFi cascade more reliable. Those are
TASK-426/TASK-436 territory. This is about observability only.

---

## 5. Design space

### Option A — Pump the console inside setup()'s wait loops — **WITHDRAWN at review**

The proposal was a `bootPumpTick()` in the blocking waits (`app/src/boot/boot.cpp:306`, `:451`,
`:480`, `:554-558`) calling `handleSerialCommands()`, so the console answers within ~200 ms of reset,
plus a `get bootphase` query for a harness that missed the phase stream.

**Withdrawn. The review's cut argument is correct and the first draft never confronted it.** By C1
and C2, the harness *causes* the boot it gates: DTR fires during `open()`, so the port is already
open when the firmware's first line prints. **A phase stream emitted at the top of `setup()` cannot
be missed on the boot being synchronised on.** Option A's unique payoff over Option B's stream was a
poll for a race that C1 already eliminates — so it was buying nothing the cheaper option did not
already deliver, at the highest price in the document.

The price, itemised, because it should stay on the record:

- **It surrenders C6.** Today no command can run against half-initialised state, by construction.
  Pumping the dispatcher in setup() makes that a matter of allowlist discipline forever after.
- **The allowlist has to be two-level, not one.** `kCmds[]` has **29** entries
  (`app/src/debug/serialConsole/console.cpp:82-115`), but `get` is a single entry dispatching **43**
  sub-keys (`app/src/debug/serialConsole/cmdGet.cpp:40-761`). A real allowlist is ~45 entry points
  wide, each needing an individual "takes no lock, touches no uninitialised pointer" argument, and it
  must be *positive* — a blacklist silently admits every command added later.
- **A TWDT clause is required and was missing.** The NTP loop at `app/src/boot/boot.cpp:554-558`
  never feeds the watchdog; it runs on the single budget reset at `:541`. A permitted command
  executing inside that loop can trip the TWDT and produce an **unstamped reset** — precisely the
  back-to-back-reset hazard TASK-376 recorded and TASK-559 exists to prevent.
- **The advertised "makes the SPIFFS wedge diagnosable" byproduct was not delivered by the proposed
  scope.** The wedge is `while (1) yield();` at `app/src/boot/boot.cpp:230`, which was not among the
  loops to be pumped. Option B's phase stream delivers the same diagnosis for free (a board stuck at
  phase 1 forever), which is the honest place for that claim — and it is now made there.
- **It is the only firmware boot-path change in the document**, so it carried the whole of §8 R1.

**If it is ever revisited**, all four conditions are mandatory and none is optional: two-level
allowlist over ~45 entry points, `reboot` excluded outright (a host that reboots a board mid-cascade
re-enters the C4 reset-pairing hazard), an explicit TWDT-feed clause for any command permitted inside
a non-feeding loop, and either pump `app/src/boot/boot.cpp:230` or drop the wedge-diagnosis claim.
Re-open only if Option B measurably fails.

*(Re-entrancy, for the record if it returns: `handleSerialCommands()` uses `static char buf[160]`
and a static `len` (`app/src/debug/serialConsole/console.cpp:192-193`). setup() and loop() both run
on `loopTask`, so the two call sites are never concurrent — safe today, fragile by construction.)*

### Option B — An explicit boot-phase signal the harness synchronises on

The firmware emits one line per stage boundary, on the model of the existing production-safe boot
banner (`app/src/boot/boot.cpp:197`) and the existing readiness token `[boot] spotify=off` at
`app/src/boot/boot.cpp:690` — which is already commented "*V0 readiness token (harness scrapes
pre-shell)*". **The pattern exists; it was invented ad hoc for one variant and never generalised.**

```
[bootphase] 0 reset          # first line after Serial.begin (boot.cpp:156)
[bootphase] 1 fs             # SPIFFS mounted / settings+cal loaded
[bootphase] 2 display        # chrome painted
[bootphase] 3 wifi           # entering the cascade   (this is the unbounded one)
[bootphase] 4 time           # entering NTP wait
[bootphase] 5 services       # spotifyTask / logserver / apps up
[bootphase] 6 ready          # FIRST line of loop(), once
```

**The literal token `[bootphase]` is normative, not illustrative** — it goes in the IFC (§9). It must
not be "simplified" to `[boot] phase=0`: `_wait_for_ready` matches `"[boot]" in line`
(`app/tools/lib/dut.py:310`), so that spelling would collide with the banner detector and be read as
a reboot signature.

**Cost**: seven `Serial.printf`s. Ships in all builds like the banner does (C5: this changes what the
firmware *says*, not what it *does*). Phase 6 in `loop()` needs a `static bool once` — trivial.
**C6 is untouched** — nothing new dispatches during setup().

**Payoff, concretely**:
- `_wait_for_ready` waits for `[bootphase] 6`, with a per-phase deadline instead of one flat
  wall-clock guess.
- The WiFi wait's 25 s stops being a guess about *the whole boot* and becomes a bound on *phase 3*.
- A board stuck in `while (1) yield()` (`app/src/boot/boot.cpp:226-232`) reports phase 1 forever and
  is diagnosed in one line instead of being indistinguishable from a slow AP.
- `BOOT_WAIT` becomes deletable, where C3 permits (Option D).

**Verdict**: **recommended.** Cheapest, lowest risk, and every other option gets better if it exists.
This is the missing interface that §2 says the magic numbers are downstream of. With Option A
withdrawn, the stream is the whole of B — there is no query half.

### Option C — Make `_wait_for_ready()` fail loudly, and abort on the right path

Today: no banner in 2 s → early return at `app/tools/lib/dut.py:316`, every network gate skipped
(§1.1(b)); and when the board is truly mute, the abort comes out as a bare `TimeoutError` that
bypasses the tail capture and the classifier (§1.1(a)). Proposed:

1. **Probe instead of returning.** The machinery already exists three times over in the same
   function — the `get ip` (`:416`), `get variant` (`:441`) and `get playerMode` (`:465`) probes.
2. **Probe with retries, not once.** `app/tools/suite/serialdbg/runner.py:196` already wraps its warmup `help` in
   `except Exception: pass` because a fresh DUT can be slow to answer, and `wait_shell_cooldown_clear`
   exists because the shell drops input for up to 3 s under load. A single 5 s probe against a board
   mid-render can miss. Retry on a deadline.
3. **Raise `SetupFailure("boot-not-observed", …)`** if the probe budget expires — which routes
   through `app/tools/suite/serialdbg/runner.py:189-190`'s `except SetupFailure` → `_setup_fail`, so TASK-556's classifier owns
   the reason and the `_TeeSerial` ring buffer's tail is attached at `app/tools/lib/dut.py:294` and
   printed. Fixing §1.1(a) means catching the `TimeoutError` case here too, rather than letting it
   escape from `_verify_debug_firmware()`.

**This is largely a hoist, not new code.** `_wait_for_ready`'s `--no-wifi` branch
(`app/tools/lib/dut.py:353-384`) *already* polls `get heap` on a 90 s deadline with a 3 s inner
probe and raises `SetupFailure("shell-unresponsive")` on expiry. TASK-560 is substantially that block
moved above the early return with a shorter deadline and a different reason string. **The knowledge
was present in the same function and was not applied to the first gate** — which makes this small and
high-confidence rather than speculative.

**Cost**: host-only, no firmware, no DUT-behaviour change. Testable without a DUT by stubbing the
serial object, the way `test_serial_classify.py` (TASK-556) stubs `_port_holders`.

**Risk**: it converts a class of silent-wrong-run into a loud abort, so **run/test will start
failing on days it used to "pass"**. Mitigation: a `DUT_BOOT_GATE=warn` escape hatch that downgrades
the raise to a printed warning, so an operator mid-investigation is never blocked by the new gate and
nobody is tempted to revert it wholesale (§8 R3).

**Verdict**: **recommended, and it goes FIRST.** Only item with no firmware dependency and no DUT
risk, and the one that stops bad runs from looking like good ones.

### Option D — Replace blind sleeps with polling, where C3 permits

`sleep $BOOT_WAIT` exists to cover a boot the harness cannot observe (C2). In the **four stamped
scripts** it no longer covers reset safety (C3), so: delete it there and let `Dut.__init__` be the
only thing that waits — it honours the gap file, causes its own observable boot, and with B+C gates
that boot properly.

**In the three raw-`serial.Serial` scripts the sleep must NOT be deleted** (`wr-gate`, `wr-soak`,
`ae04`). They never consult the gap file, so stamping them is a no-op and removing the sleep
re-opens TASK-559 in three places at once. Either migrate them to `Dut` (or to a shared helper that
honours the gap) *first*, or leave their sleep alone and say why in the commit. The remaining
unstamped-but-`Dut`-backed scripts (`pr-soak`, `pr-fetch-soak`, `stress`, `task488`,
`task424-repro` → `app/tools/sdwrite_repro.py:23`) can be stamped and then have their sleep removed,
since `Dut` reads the gap file for them.

This is the only place where "replace a blind sleep with polling" is honestly available. The other
sleeps in the harness are either inside the reset-gap guard (correct, TASK-555's) or steady-state
test-body sleeps (`harness-sync-rethink.md`'s).

**Verdict**: **accept, LAST, and scoped per-script rather than globally.** Landing it before C means
deleting a sleep that was masking the fail-open.

### Option E — Suppress the port-open reset (`hupcl`/DTR-clear) — REJECTED

Superficially it removes the whole problem: no reset on open, so the harness can attach to a running
board. **Rejected on C1.** A board that does not reboot on open takes the §1.1(b) path — every
network gate skipped, silently — so this *generalises* the defect instead of fixing it. It is also
contraindicated by TASK-557's standing advice ("do not change the serial-open path on this
evidence"), and it destroys the one thing the current design gets right: the harness knows the
board's exact age because it caused the boot. Listed only so nobody re-proposes it; if it is ever
revisited it must come *after* C, never before.

### Option F — Firmware-side "harness attached" handshake — REJECTED

Have the firmware hold at a barrier until the host says `go`. Genuinely deterministic, and genuinely
the wrong trade: it changes production boot behaviour (C5), it surrenders C6, and it introduces a way
to leave a board wedged waiting for a host that never arrives (§8 R2 — the worst failure mode in this
document). Revisit only if B+C measurably fail to stabilise the boot window.

---

## 6. Lean

**Do C, then B, then D.** Stated as tasks:

| Order | Task | What | Why here |
|---|---|---|---|
| 1 | **TASK-560** | Probe-with-retries above the early return; raise `SetupFailure("boot-not-observed")` through `runner.py`'s `_setup_fail`; catch `_verify_debug_firmware`'s `TimeoutError` so it stops escaping the tail-attach and the classifier; `DUT_BOOT_GATE=warn` escape hatch (Option C) | Host-only, no firmware, no DUT-behaviour change, and largely a hoist of the existing `--no-wifi` block at `app/tools/lib/dut.py:353-384`. Everything else is an optimisation on top of a gate that currently skips silently. |
| 2 | **TASK-561** | `[bootphase] N name` stream at the seven stage boundaries, all builds (Option B) | Seven printfs. Generalises the ad-hoc token already at `app/src/boot/boot.cpp:690`. Lets 560's gate wait on a *phase* with a per-phase deadline instead of a flat guess. C6 untouched. |
| — | ~~TASK-562~~ | ~~Pump the console in setup()~~ | **WITHDRAWN at review** — C1/C2 mean the stream cannot be missed on the gated boot, so its unique payoff was a poll for an eliminated race, at the cost of C6. Conditions for re-opening are in §5 Option A. |
| 3 | **TASK-563** | Delete `BOOT_WAIT`'s `sleep` **in the four stamped scripts only**; stamp-then-delete for the four `Dut`-backed unstamped ones; **leave `wr-gate`/`wr-soak`/`ae04` alone** until they honour the gap file; derive or delete the remaining boot-window constants (Option D) | The payoff. Must come after 560, or it removes a sleep that is masking the skip. |

**The single most important judgement call**, unchanged and independently upheld at review:
**TASK-560 goes first even though it will make the rig look worse.** It converts a silent
wrong-premise run into a loud abort, so some runs that today report PASS will start reporting
`[SETUP-FAIL] boot-not-observed`. That is not a regression — those runs were never valid — but it
*will* look like one on the day it lands, and it lands while TASK-557 is unresolved and the rig's
stability is itself under investigation. The alternative ordering (firmware first, so the loud gate
has something reliable to synchronise on) is defensible and I considered it. I rejected it because a
rig that cannot distinguish a good run from a bad one cannot be used to evaluate the firmware change
either — TASK-557 has already spent hours on exactly that kind of unfalsifiable measurement, and
TASK-553's whole resolution was an unwritten precondition that nothing checked. Make the premise
checkable first, then improve it. `DUT_BOOT_GATE=warn` is the insurance against that judgement being
wrong on the day.

**What I am not proposing**: touching the reset-on-open path (E), a firmware handshake (F), pumping
the console during setup (A, withdrawn), or any change to `_DUT_DRD_WINDOW_S` (C4, TASK-555's call).

---

## 7. Sequencing against the in-flight test-framework work

| Task | State | Relationship |
|---|---|---|
| TASK-552 | done | None. Port resolution; disjoint code. Its known weakness (gap key changes on re-enumeration) is unaffected either way. |
| TASK-553 | done | **Corroborating, not blocking.** Its root cause was an unwritten fresh-boot precondition nothing verified. TASK-560 is the same defect class at the harness level; TASK-561's phase stream makes "which boot am I on" a stated fact. |
| TASK-554 | done | None. Monitor `pipe-pane` wiring. |
| **TASK-555** | **open** | **Adjacent, deliberately decoupled.** It owns `_DUT_DRD_WINDOW_S`'s rationale and the dead `portal_seen` branch. **Conflict warning:** that dead branch is *inside* `_wait_for_ready()`, which TASK-560 also edits. Land 555's deletion and 560's rewrite in a stated order — I recommend **555 first** (a pure deletion into a smaller function) or, if 560 goes first, have 560 leave the portal branch untouched so 555 stays a clean removal. Do not let two agents rewrite that function in parallel. |
| TASK-556 | done | **Directly reused, both ways.** 560's new `boot-not-observed` reason must route through `app/tools/suite/serialdbg/runner.py:189-190`'s `except SetupFailure` → `_setup_fail` so 556's classifier owns it — and fixing §1.1(a) means the `TimeoutError` that currently *escapes* 556's handlers stops doing so. 556's stub-the-serial-object test pattern (`test_serial_classify.py`) is the model for 560's negative tests. |
| **TASK-557** | **open, unresolved** | **The most important interaction.** 557 is measuring a non-stationary rig phenomenon and its record says *"do not change the serial-open path on this evidence"*. Nothing proposed here changes it — E is rejected on that ground, and withdrawing 562 removes the only firmware boot-path change. **Land 560 and 561 freely (observability only — they add signal to 557's own investigation); hold 563 until 557 has closed or explicitly signed off**, since it changes run-script timing. 561 in particular *helps* 557: a phase stream timestamps how far each boot got, which is precisely the discrimination 557's arm-A/arm-B design was reaching for. |
| TASK-558 | open | **Touches OQ2.** If the phase ordinal is added to the heartbeat, a monitor-only reader (`run/monitor-read`) can see boot progress — which is exactly the surface 558 is making trustworthy. Sequence 558 first or treat OQ2 as a follow-on to it; do not have both edit the heartbeat line in parallel. |
| TASK-559 | done | **Partial prerequisite (C3).** `stamp_reset_gap()` makes 563 safe **in 4 of 12 scripts**. 563 finishes 559's stated remainder — but note 559's row calls the gap "lower risk since no harness open follows", which is true only for the `Dut`-backed scripts; for `wr-gate`/`wr-soak`/`ae04` a raw open *does* follow and the stamp would not help it. That correction belongs in 563. |

**Ordering dependencies, condensed**: 555 ↔ 560 (same function — serialise them, 555 preferred
first) · 560 → 563 (do not delete the sleep while the gate skips silently) · 558 ↔ OQ2 (heartbeat
line) · 557 gates 563 only, now that 562 is withdrawn.

---

## 8. Risks

**R1 — was TASK-562's firmware boot-path change. Retired with the task.** With Option A withdrawn,
nothing in this design executes code during `setup()`, C6 is preserved intact, and the largest
verification burden in the document is gone. Recorded rather than deleted so that anyone re-opening
Option A knows R1 comes back with it, in full.

**R2 — Recoverability.** Nothing proposed here can wedge the board: no option holds boot waiting for
a host (F rejected for this reason), no option changes the reset path (E likewise), and no option
dispatches commands pre-`loop()` (A withdrawn). The residual risk is now **zero on the firmware
side**; TASK-561 adds seven printfs and no control flow.

**R3 — TASK-560 will make the rig look less reliable on the day it lands.** Stated in §6; repeated
here because it is the most likely reason for the change to be reverted by someone who did not read
§6. Every `boot-not-observed` abort it produces is a run that previously produced an invalid PASS or
an unexplained FAIL. The right response to a spike is to read the serial tail it now prints, not to
raise the timeout — and `DUT_BOOT_GATE=warn` exists so an operator can proceed *without* reverting
the gate, which is the failure mode that actually loses the fix.

**R4 — TASK-563 could re-open TASK-559's defect in three scripts.** The claim "deleting the sleep
makes the reset gap longer, not shorter" holds **only** where the subsequent open honours the gap
file. `run/wr-gate`, `run/wr-soak` and `run/ae04` open a raw `serial.Serial`
(`app/tools/test_adr045_gate.py:60`, `app/tools/test_webradio_soak.py:57`,
`app/tools/test_ae04_teardown.py:107`) and never consult it — for them the sleep *is* the gap.
**Exit criterion, three arms**: enumerate every script that flashes, and assert each one either
(i) stamps and is followed by no open, (ii) stamps and opens through `Dut`, or (iii) **opens the port
through a path that honours the gap file** — with (iii) requiring migration before its sleep may be
deleted. This is the asymmetry TASK-559's own row flags as untidy, plus the raw-open case that row
did not distinguish.

**R5 — Doing nothing.** Not free. Every future harness timing failure is diagnosed against a rig
whose runs cannot prove their own premise, and each diagnosis costs DUT hours. Two of the last four
test-framework tasks (553, 557) were investigations into failures whose premise was never
establishable. That is the recurring cost this document argues against.

---

## 9. What is owed on acceptance

Per architect.md, an accepted lean crystallises into a decision record — not written yet, because
the lean is proposed and the human has not signed off:

- **An ADR** (next free id at creation time; ADR-062 is the highest allocated as of 2026-09-01) —
  "the harness synchronises on a firmware-published boot phase, not on inferred log lines and blind
  sleeps", including the C1/C2 reasoning that withdrew Option A.
- **An IFC** (next free id at creation time; IFC-006 is the highest allocated as of 2026-09-01) — the
  `[bootphase]` contract: parties (firmware boot ↔ host harness), transport (UART 115200,
  line-oriented), the ordinal/name table, the invariant that phases are monotonic and `6 ready` is
  emitted exactly once per boot, and **the literal token `[bootphase]` pinned as normative** — the
  spelling `[boot] phase=N` is forbidden because it collides with `_wait_for_ready`'s banner matcher
  at `app/tools/lib/dut.py:310`. VE reviews it for testability before it is finalised.

Neither is created here. Both should be, in the same pass, if the lean is accepted — the phase table
is an interface the moment the harness parses it, and an interface parsed from prose is how the
`_PORTAL_INDICATORS` tuple ended up matching a firmware that has not shipped since June.

**Registry reservation** (architect.md item 10, BP-071): no new feature id — this extends
**serialdbg-001**, whose inventory entry already describes the unconditional `[boot]` banner as a
passive diagnostic and now gains a phase stream alongside it. One new interaction edge is reserved:
**X066** (boot cascade ↔ serial console ↔ harness readiness), in `cross_feature_matrix.yaml`,
`test_coverage: []` until VE lands the suite.

---

## 10. Exit criteria

1. `_wait_for_ready()` has **no path that returns "ready" without a positive observation**, and **no
   abort path that bypasses the tail attach or `_setup_fail`**. Provable by reading the function.
   Negative tests required (BP-068): a stubbed serial that emits nothing must raise
   `boot-not-observed` *through* `_setup_fail`; a stubbed serial that answers `get heap` but never
   reports a link must also raise, not return.
2. A DUT run's own output states the phase the board reached before the first test command was sent.
3. `BOOT_WAIT` no longer appears as a `sleep` argument in any script whose subsequent open honours
   the gap file; it survives, documented, in any script that does not. Every surviving harness
   boot-window constant (§2's 13) either cites the firmware quantity it is derived from or is
   deleted. Target: **at most two** undecided numbers left, both with a named owner.
4. Every script that flashes satisfies one of R4's three arms, enumerated one row per script.
5. `run/check` 11/11, and `run/check-docs` 6/6.

---

## 11. Open questions

- **OQ1** — Should `[bootphase]` ship in production or only under `SERIAL_DEBUG`? I lean *all
  builds*, matching the boot banner's ADR-021 Decision 4 precedent (a passive diagnostic that lets
  any host see where a field unit stalled). Cost is seven printfs and some flash. **Architect lean,
  human call.**
- **OQ2** — Should the phase ordinal be exposed in the heartbeat too, so a monitor-only observer
  (`run/monitor-read`) can see it without a command? Cheap, and it interacts with TASK-558 — see §7.
- **OQ3** — TASK-555's outcome may make the phase stream a *better* basis for the reset-gap rule
  than a wall-clock window (a board that has reached phase 6 is demonstrably past the hazard TASK-376
  described, whatever that hazard turns out to be). Flagged for 555's owner; not assumed here (C4).
- **OQ4** — Does the WiFi cascade need a *sub*-phase signal? Phase 3 is the unbounded one and
  "in the cascade" may be too coarse to set a deadline against. Defer until 561 has produced real
  timings.
- **OQ5** — Should `wr-gate`/`wr-soak`/`ae04` migrate off raw `serial.Serial` onto `Dut`? It would
  close R4 properly rather than documenting around it, and would give three more scripts the
  readiness gate. Out of scope here; it is a M-TESTARCH §3 "one DUT layer" question, and it deserves
  its own row rather than being smuggled into 563.

---

## 12. Review response — what changed, and what I pushed back on

Independent review, 2026-09-01, returned APPROVE WITH CHANGES. All seven must-fix items applied:

| # | Item | Applied |
|---|---|---|
| 1 | §1 claim 6 factually wrong | §1 row 6 now points at §1.1, which **retracts the blanket claim** and replaces it with the two real defects (mis-routed `TimeoutError`; responsive-but-not-ready). §1.1's consequences re-derived from (b). |
| 2 | C3 false; 563 unsafe as scoped | §3 C3 rewritten with the measured 12/4/3 split. §5 Option D, §6 TASK-563 and §8 R4 all re-scoped per-script; R4 gained the third arm verbatim. New OQ5. |
| 3 | X066 "~30 of kCmds[]" | Corrected in `cross_feature_matrix.yaml` — 29 entries, 4 named safe, and the two-level `get` problem stated. |
| 4 | §2 inventory miscounted | Rebuilt: **13 rows**, every line reference re-measured (`:164`/`:169` for the WiFi waits, the 3 s inner probe at `:371`, the 3 s ELF probe at `:548`). |
| 5 | Drop TASK-562 | **Accepted.** Option A marked WITHDRAWN with the C1/C2 argument; C6 added to §3 as the invariant it would have cost; the four re-opening conditions recorded; R1 retired with it; the wedge-diagnosis claim moved to Option B, which actually delivers it. |
| 6 | BP-070 `docs-touched:` | Added to TASK-563's row: `harness-sync-rethink.md:245,357,539,606` (`:606` names `BOOT_WAIT` as an explicit exception to that doc's blind-sleep prohibition) and `run/player-gate:47`. |
| 7 | 560 routing + retries | §5 Option C and §6 rewritten: route through `_setup_fail`, retry the probe on a deadline, catch the `TimeoutError`. |

Nice-to-haves all taken: `DUT_BOOT_GATE=warn` (§5 C, §8 R3); line drift fixed (NTP `:554-558`, early
return `:316`, "one comment" in claim 1, and the "boot_seen branch" phrasing replaced — it is an
early return, not a block); §7 gained 556↔560 and 558↔OQ2 rows; the `[bootphase]` literal is pinned
normative in §9 with the `_wait_for_ready:310` collision named; board rows reordered ascending. The
reviewer's find that `_wait_for_ready` already contains 560's mechanism (`app/tools/lib/dut.py:353-384`)
is now the framing of Option C and is stated in the task row — it makes 560 a hoist, not new code.

**One pushback, on item 2's count.** The review listed **four** scripts whose sleep is the only reset
gap, including `run/task424-repro`. That one is wrong: `run/task424-repro:37` invokes
`app/tools/sdwrite_repro.py`, which imports `Dut` from `lib.dut` (`app/tools/sdwrite_repro.py:23`)
and therefore *does* honour the gap file. It belongs with the stamp-then-delete group, not the
do-not-touch group. **The finding stands and is more important than the count** — it is three
scripts, not four, and the document says three throughout. Flagging it because a "four scripts" claim
propagating into 563's implementation would leave one script carrying a sleep for no reason, which is
the same class of error (an unverified list) that the review is correcting elsewhere.
