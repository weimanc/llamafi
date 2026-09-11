# PROP-011 — Rig ground truth: a measured stability baseline for the CYD test rig

> Owner: R&D
> Status: **PLAN OF ACTION — not started.** Written 2026-09-10 at the human's request, after
> "rig instability" had been cited as the cause of failed runs for six weeks with four retracted
> causal claims on record (TASK-557). Reviewed before execution, per PROP-010's precedent.
> Branch: `rnd/rig-ground-truth` for anything throwaway; the P0 tooling lands on `master` under
> TASK-677 because it is harness infrastructure, not an experiment.
> Origin: TASK-557 (open, P2, master blocker for M-HARNESS2 Phase 3/5 and the M-TESTARCH order
> switch), TASK-576, TASK-578. Filed alongside **TASK-677** (rigwatch) and **TASK-678** (BOD flag
> split) on [tasks-harness2.md § Rig stability](../../project/tasks-harness2.md).

## Premise

Every prior TASK-557 window reasoned from one observation window at a time, and the record shows
what that cost: "it's the cable", "the re-plug fixed it", "the port-open causes it", "the CH340
loses VBUS" — each asserted, each retracted. The instrumentation that produced the good results
(the BOD comparator, the bootloader-vs-app A/B) survived; the instrumentation that would have
prevented the bad ones (host-timestamped correlation of kernel events with harness actions and DUT
output) was never built. This proposal builds the correlation first, then runs the experiments that
were named but never executed.

## 1. Ground truth as of 2026-09-10 13:10

Two records that had never been cross-read, both taken today without touching the board.

### 1.1 Host kernel log (`journalctl -k`, host up since 2026-08-28)

| day | CH340 re-enumerations on port `1-1` |
|---|---|
| 08-28 | 1 |
| 08-31 | 29 |
| 09-01 | **1367** — orphaned-monitor storm (TASK-558) + block A/B |
| 09-02 | **434** — the 77-in-120 s A/B + threshold sweeps |
| 09-03, 09-04 | 0 |
| 09-05 | 1 — 2 min between detach and attach: a human unplug (20:05) |
| 09-06 → 09-10 | **0** |

`-DBOD_WATCH` was pinned on the board 2026-09-02 (`354f3b1`). Since then: **zero unexplained
re-enumerations in eight days**, across two deliberate reflashes. All twelve `-71` USB errors ever
logged for the port fall on 09-01 during the storm and are enumeration failures ("device not
accepting address", "descriptor read error") — a device being reset mid-enumeration, not link
noise. No over-current report, ever. The DUT is attached **directly to root-hub port 1-1** of the
laptop's xHCI controller — no hub — as a full-speed device declaring `bMaxPower=98mA`, which it
exceeds several times over whenever the radio is up. The unrelated periodic `usb 1-4 reset` lines
are the fingerprint reader.

### 1.2 Board serial log (`/tmp/spotify-mon-serial.log`, 158 boots)

Current boot at time of reading: **21 h 11 m**, `thres=7` (most sensitive, ≈2.80 V indicative),
`bodmit mask=0` (unmitigated):

- **1** BOD trip — the deterministic boot-window one, `tag=wifi-end t=1518ms`.
- **0** steady-state (`tag=run`) trips in 21 h.
- `discCount=23` WiFi disconnects.

The boot immediately before it (build `Sep 9 2026 11:19`, 56 min):

- `discCount=753` — reason 201 `NO_AP_FOUND` ×353, 200 beacon-timeout ×19, 202 ×15, 39 ×3.
- **118** `tag=run` BOD trips.

Same firmware, cable, port and host, about five hours apart. **Steady-state sag trips track WiFi
activity, not wall time.** This is the variable no prior window controlled, and it is sufficient to
explain "non-stationary": the rig was riding on a non-stationary AP (LL-096, TASK-426).

The first reading of this — "every reconnect is a PHY bring-up, so trips ≈ reconnects" — was
**refuted the same evening by P1 (§8)**: 20 forced re-associations to a present AP produced 0 trips.
What trips the rail is the firmware's **`NO_AP_FOUND` retry loop** — a full active scan every ~2.4 s
for as long as the AP is absent. Direction of causality: AP absence → retry loop → sag. See §9.

Reading note: `[wifi-ev]` lines are rate-limited (`suppressed=N`); this boot logged 2 disconnect
lines against a counter of 23. Count from `wifiDiag::discCount` in the heartbeat, never from log
lines.

## 2. Variables, prior experiments, verdicts

| variable | controlled before? | experiment | verdict | gap |
|---|---|---|---|---|
| host port-open / DTR reset | yes | 20 ROM-bootloader resets | 0 drops — DTR exonerated as a *sufficient* cause | — |
| app boot vs bootloader | yes | block A/B 0/20 vs 10/20 (p=0.0004); interleaved 0/12 vs 0/12 | strong association; null on the confound-free re-run because the effect was absent | effect must be present to re-test |
| orphaned `pio device monitor` | found by accident | kill → 0 drops in 135 s | host-generated; ~420 events | fixed, TASK-558 |
| open cadence (8 s < 12 s window) | no | code read | real defect, fixed TASK-559 | never shown to *cause* a drop |
| IDF brownout ISR | yes | ISR cleared → 0/120 s vs 77/120 s | **the mechanism that turns a sag into a USB drop** | workaround only; production still boot-loops |
| sag depth | swept 0–7 | levels 2/3 trip, 0/1 do not | bracketed ≈2.5 V (indicative table) | one day, one supply, no meter |
| backlight duty, WiFi TX power | yes | 4 variants × 2 levels × 3 reps = 24/24 trip | **not the driver** | — |
| WiFi PHY bring-up current | inferred | — | sole remaining firmware-side suspect | never isolated from the rest of boot |
| WiFi reconnect rate | **never a variable** | §1.2, found today | 753 disc → 118 trips; 23 → 0 | causality direction |
| cable / hub / host port / supply | **no** | none | — | the decisive test, named in every window, never run |
| regulator-limited vs upstream 5 V | no | none | — | needs a meter, or the trip threshold as a proxy (P3) |
| thermal / time of day | no | anecdote ("progressed over hours") | — | confounded with AP behaviour |
| UART byte integrity DUT→host | once | `serialburst` 4×2000 lines → 0 lost; `read_flash` 1 corrupt block / ~15 MB | clean | host checker `burst_check.py` was **never committed** |
| UART host→DUT, bidirectional | no | none | — | no firmware sink exists |
| baud / payload size | no | none | — | `Serial.begin(115200)` is fixed |
| SD at boot (`SD_BOOT_MOUNT`) | on in debug env | — | not isolated | one rung of P2 |
| speaker amplifier (SC8002B) | n/a | — | no speaker fitted on this rig | must remain unfitted for every run here |

**Repeatable?** Bootloader/app A/B — yes, cheap. Threshold sweep — yes (`bod N` + `reboot`).
Mitigation matrix — yes (`bodmit`). Orphan storm — do not. Interleaved A/B — only informative while
the effect is present, which under `-DBOD_WATCH` it is not: re-run it on the **production** build,
the one that still fails. Burst — needs its host checker rewritten (P0).

## 3. Instruments

**Have.** Kernel udev log (the one host-side truth for "the USB link dropped"); `/dev/usbmon1`
(debugfs usbmon is blocked by Secure Boot lockdown); the BOD comparator (8 levels, latched RAW
status, tags `time`/`wifi-end`/`run`/`ready`, `bod` query, RTC_NOINIT threshold across reboots);
`[bootreason]` (separates SW/PANIC/WDT/BROWNOUT; cannot separate our DTR reset from a power
cycle — both read `POWERON`); `[bootphase]` + the harness generation counter; heartbeat
`uptime/disc/heap`; `wifiDiag::discCount` with reason codes; `serialburst` (DUT→host, checksummed,
BOD-polled inside the emit loop); `esptool read_flash`; `Dut._port_open_time` (written since
TASK-557, read by nothing); `run/dut-health`.

### 3.1 The BOD comparator: from polled latch to interrupt (TASK-678)

Today `bodWatch` reads a one-bit latch every 200 ms from `loop()`. That yields "at least one dip
since the last look" — no count within the interval, no timing better than 200 ms, no depth per
event (depth needs a reboot per threshold level). The interrupt path uses the same hardware line
ESP-IDF already uses for its panic; we take it over.

**Mechanics (Arduino-ESP32 2.0.17 = IDF 4.4).** IDF's `esp_brownout_init()` registers a static
`rtc_brownout_isr_handler` on the shared RTC ISR. `esp_brownout_disable()` (same file) deregisters
and clears it. **Step 0** is `nm libesp_system.a | grep brownout` on the precompiled framework to
confirm the symbol is exported; if not, the fallback is a 1 kHz high-priority polling task (worse
than the ISR, still 200× better than today). Then `rtc_isr_register(bodIsr, NULL,
RTC_CNTL_BROWN_OUT_INT_ENA_M)` and set `INT_ENA`. `bodIsr` is `IRAM_ATTR`, no printf, no malloc,
`FromISR` calls only; it writes a lock-free ring that `loop()` drains and prints.

| capture | how | resolution | what it buys |
|---|---|---|---|
| timestamp | `esp_timer_get_time()` in the ISR | µs | places a dip against `[wifi-ev]`, `[bootphase]`, a harness `mark` |
| count | one ring entry per edge; re-clear + re-enable in the ISR | every dip | the 118 trips / 56 min on 09-09 was a lower bound |
| duration | bounded spin on `BROWN_OUT_DET` inside the ISR (cap 1–2 ms) | µs | first shape information: inrush spike vs slow sag |
| depth per event | **ladder**: trip at 7 → threshold 6, clear, test DET … down to 0, restore 7 on exit | one comparator step, per event | replaces the reboot-per-level sweep; gives a depth *distribution* over a soak. Comparator settle time after a threshold write is unknown — **measure it first** against a known-long dip |
| context | boot phase, WiFi-status shadow, last console command id, backlight duty, SD-busy flag — globals read in the ISR | — | "what was the board doing" — the field every prior window guessed at |
| external trigger | toggle a spare header GPIO (27 or 22) on entry | ns | scope / logic-analyser trigger; host-independent correlation with the USB drop |

**Harness features this unlocks.**

1. `get bod` as a structured dbgGet key: `{count, firstUs, lastUs, minLevel, maxDurUs, hist[8],
   phaseAtFirst}`. Every suite test reads it before and after its body → a **B covariate** on each
   result, in the same way TASK-571 stamps `health=`/`last-phase=`. A steady-state dip inside a
   test body is a RIG annotation, automatically.
2. HEALTH id **`T_DH_06`**: boot-window dip count and depth inside a declared band (e.g. exactly
   one dip, level ≥ 2, duration < X µs). Drift out of the band is supply degradation caught before
   it becomes a flake — the first HEALTH check that watches hardware rather than firmware liveness.
3. Console `mark <label>`: firmware logs `esp_timer` at receipt; rigwatch (TASK-677) aligns DUT µs
   to host time via the tee timestamps → a dip sits between "harness sent X" and "kernel detach" to
   the millisecond.
4. Depth histogram over P5's 72 h soak — the number TASK-578 needs: how often the rail reaches
   level 0, the production reboot point. Polling cannot produce this.
5. `BOD_POLICY` lives in the same ISR: deep level + duration past a debounce → `g_bodDeep`;
   `loop()` blocks SPIFFS/NVS/SD writes, flushes the log, controlled `esp_restart()` with
   `[bod] policy restart` on the wire — a *named* reboot in place of `POWERON`. Testable without a
   sag: `set fault bod <level>` invokes the handler body, so the R34 runtime gate can prove the
   harness parses the policy line.
6. P1 becomes quantitative: trips per reconnect with µs offsets from `STA_DISCONNECTED` — the
   direction of causality falls out of the ordering (dip before the disconnect event, or after
   `STA_START`).

**Unchanged constraints.** One threshold register: interrupt mode at level 7 still removes IDF's
reset path, so `BOD_POLICY` is the replacement, not an option. Still VDD3P3 only. ISR budget: the
spin and the ladder must be capped — a 2 ms stall on the shared RTC ISR is fine for a rig build,
not for production; a production policy build caps lower or disables the ladder.

**Lack.** Any voltage measurement. GPIO35/ADC1_CH7 is the board's only free ADC pin; a two-resistor
divider from the 5 V input gives the *5 V* rail in software. The 3.3 V rail cannot be read by the
chip that runs on it — the comparator is the only 3.3 V instrument and it stays that way. A €10
inline USB V/A meter answers the 5 V question in an afternoon and is the single cheapest purchase
in this proposal. No thermal sensing. No host→DUT integrity path. Baud not configurable.

## 4. Metrics — defined before anything runs

| symbol | definition | source |
|---|---|---|
| **R** | CH340 re-enumerations per hour on the DUT's `by-path` node | kernel log via rigwatch (TASK-677) |
| **B_boot** | the lowest BOD level that trips during the boot window | `bod N` sweep, 3 boots per level |
| **B_run** | steady-state BOD trips per WiFi reconnect | `bod` query ÷ Δ`discCount` |
| **W** | WiFi disconnects per hour | `wifiDiag::discCount` |
| **L** | bytes lost or corrupted per MB, per direction | `serialburst` / `serialsink` + host checker |
| **U** | unexplained boots: `[bootphase] 0` with no harness-stamped reset in the ±3 s window | rigwatch timeline |

"Stable" for the purpose of every downstream claim: **R = 0 and U = 0 over 24 h, with W recorded.**
A run report that cannot state R and W did not measure the rig.

## 5. Plan

> **Executable form:** [PROP-011-runbook.md](PROP-011-runbook.md) — per-experiment briefs (agent
> tier, board cost, exact commands, decide-rules, report template) written so Sonnet/Haiku agents
> can run the legwork. Its §0.4 table is the status board; this section stays the rationale.

### P0 — correlation infrastructure (host only, lands on `master` as TASK-677)

This is the prerequisite for every phase below and the cheapest thing in the proposal.

- `tools/lib/rigwatch.py`: tails `journalctl -k -f -o json` (unprivileged on this host —
  verified), filtered to the DUT's **`by-path`** node (not `ttyUSBn`, which changes on every
  re-enumeration), writes `{host_ts, kind: attach|detach|reset|error, devnum, tty}` to
  `rig_events.jsonl`. Started by `run/monitor-start`; runnable standalone.
- Every `run/*` action stamps the same file: `flash-begin/end`, `port-open`, `port-close`,
  `monitor-start/stop`, `run-begin/end <run-id>`. `Dut._port_open_time` finally gets a reader.
- `_TeeSerial` records a host receive-timestamp per line; `[bootreason]`, `[bootphase]`, `[bod]`,
  `[wifi-ev]`, `[hb]` lines are mirrored into the event stream as `dut` events.
- The run artifact (TASK-608 schema) gains `rig: {reenum, unexplained_boots, bod_trips, wifi_disc,
  events[]}`. **R > 0 or U > 0 auto-annotates the run RIG** — M-TESTARCH's class, decided by data
  instead of by whoever reads the log.
- `run/rig-timeline [--since]`: one ordered merge of host, harness and DUT events with relative
  offsets. This is the cause-vs-effect tool that did not exist for any prior window.
- Free consequence: rigwatch knows every reset, so it reports "observation window ended after
  39 h 38 m by `flash-debug`" itself; the manual check in `dut_workflow.md §5a` becomes a line in
  the run output.
- Gating: `run/lib.sh` sources `run/local.env` (gitignored) if present; `RIGWATCH=1` plus the
  DUT `by-path` live there. A public checkout has no such file and behaves exactly as today.
- Re-commit the burst checker as `tools/probe/burst_check.py` (it never was — `git log` shows no
  history for it anywhere).

### P1 — causality of steady-state trips (live board, no reflash, ~1 h) — **RUN 2026-09-10, see §8**

Board as it sits, BOD armed at 7, rigwatch running.

1. 30 min on a stable link → read `bod`. Expected 0 (§1.2 says so; make it a record, not a recollection).
2. Force 20 reconnects from the console (WiFi off/on, or a bogus SSID then the real one) → read
   `bod` and `discCount` → **B_run**.
3. TLS load alone is already present — TASK-675's `-9984` failure runs a handshake attempt every
   poll — and (1) covers it.

Runs tonight with the polled latch (count only). Re-run once TASK-678's ISR lands: µs offsets
between each dip and the `STA_DISCONNECTED`/`STA_START` events settle the direction of causality
outright (§3.1 item 6).

If B_run ≈ 1 trip per reconnect, AP flapping is a *driver* of the sag and W becomes a mandatory
covariate on every RIG/flake verdict. If B_run ≈ 0 with the sag still present in the boot window,
the 118-trip boot needs another explanation and the direction sag→radio is back on the table.

### P2 — load ladder (BOD as sensor, ~2 h, reflashes: ends the running window — say so)

Threshold sweep per rung, 3 boots per level; output **B_boot** per rung.

| rung | build | isolates |
|---|---|---|
| 0 | ROM bootloader (`--after no_reset`) | nothing running — the true bare minimum; already arm A of the 08-31 A/B |
| 1 | `~/proj/webradio-bare` (EXP-009's 104-line rig, no WiFi) + `bodWatch.cpp` ported in | CPU + flash only |
| 2 | rung 1 + `WiFi.begin()` | PHY bring-up alone |
| 3 | rung 2 + TFT init + backlight full | display load |
| 4 | rung 3 + `SD.begin()` | SD inrush |
| 5 | `cyd2usb_winamp_debug` as shipped | everything |

Answers "is it the PHY alone, or the sum of loads". Yes, the bootloader is the legitimate
bare-minimum control — it is what the existing A/B already used, and `esptool` can run bulk
transfers against it.

### P3 — supply A/B (human present, ~2 h; the decisive test)

Same full-debug firmware. Per condition: B_boot sweep, then 100 application boots on the
**production** build with R counted.

Conditions: as-is (laptop root port, current cable) / short thick cable, same port / powered hub /
the laptop's other USB socket / bench 5 V into the CYD's second USB connector with data on the
CH340 connector (the two-USB variant makes this possible; verify the two connectors' power paths
are joined before trusting the result) / inline V/A meter on the 5 V leg if one is to hand.

**Decision rule.** If B_boot does not move across supplies, the sag is downstream of the
regulator — regulator-limited — and no cable, hub or socket will ever help; the fix is hardware
(bulk capacitance on 3.3 V, or an LDO with lower dropout) and TASK-557 closes as a board defect.
If B_boot moves, the sag is upstream and the fix is cheap and external. Either outcome closes the
"is it the cable" question with a number.

### P4 — UART transfer matrix (BOD armed, R counted, ~1 h)

- DUT→host: `serialburst` with pad ∈ {8, 64, 200} × lines ∈ {2 000, 20 000}.
- host→DUT: new console command `serialsink <bytes>` — counts and checksums what it receives,
  acks the count. This direction has never been tested.
- bidirectional: `serialecho` — host sends numbered lines, firmware echoes, host diffs.
- baud 115200 vs 921600 — `Serial.begin()` rate becomes a debug build flag.

**L** per cell. Expected 0 everywhere; "expected" is exactly why it has to be on the record before
anyone next says "the link is flaky".

### P5 — production-build soak (72 h × 2)

`-DBOD_WATCH` build and the production build (IDF ISR armed), R/W/B/U logged hourly by rigwatch.
Production boot-loops on a deep sag: how often, at what W? This is the evidence TASK-578's ruling
needs and does not have. The production leg ends the pinned board's window and violates the pin —
**needs the human's explicit go**, and the board is returned to the debug build afterwards.

### P6 — harness cadence, controlled (~1 h)

Re-run TASK-555's reset-gap sweep (1/2/4/8/12 s) at n ≥ 30 on *both* builds with `[bootreason]`
per boot and R counted. BP-018's 12 s is currently "not derived from anything measured" by its own
amended text; this either grounds the number or retires the rule under its written criterion.

## 6. Order and cost

P0 → P1 (polled) → **TASK-678 step 0 + settle-time measurement** → P1 (ISR, quantitative) → P2 →
P3 → P4 → P5 → P6. P0 is ~1 day host work; TASK-678 is ~1 day firmware work and can proceed in
parallel with P0. P1 is free and can run tonight. P2's depth-per-rung and P5's depth histogram both
assume the ISR ladder; with polling only they degrade to the reboot-per-level sweep. P2–P4
are one DUT afternoon each. P5 is calendar time. P3 needs the human and (ideally) a €10 meter.

## 7. What this proposal is careful not to claim

- That the rig is stable. R has been 0 for eight days under a *workaround*; production is the
  build that fails, and P5 is the first time it will be measured rather than described.
- That the AP is the cause. §1.2 is one pair of boots; P1 is the test.
- Absolute voltages. The 0:2.43 V … 7:2.80 V table is the widely published one and is not
  verifiable from the precompiled framework here; every number derived from it is indicative
  until a meter says otherwise.
- That the 7-byte `read_flash` corruption is explained. It is one event in ~15 MB with no
  reproduction; P4 is where it either recurs or is left as noise.

## 8. P1 results — 2026-09-10, live board, no reflash, rigwatch recording

**(a) Baseline.** 29 h 02 m uptime, `thres=7`, `bod` → `tripsSinceArm=1` (the boot-window trip),
`disc=23`. **0 steady-state trips in 29 h across 23 disconnect events.**

**(b) 20 forced re-associations** (`set wifiDisc N` through the existing monitor, 15 s apart,
21:02–21:07, every cycle stamped by rigwatch): `disc` 23 → 63 (each kick = one `reason=8` leave +
one or two `reason=201` before `STA_GOT_IP` ~1.5 s later), 13 re-associations logged (rate-limited),
20 acks, **0 `[bod] TRIP`, 0 resets.** `bod` after: `tripsSinceArm=1`, unchanged. **B_run = 0/20.**

**(c) Re-read of the 118-trip boot (09-09 11:19, 56 min)** with the same lens, from the log alone:

| WiFi event immediately preceding each `tag=run` trip | trips |
|---|---|
| `STA_DISCONNECTED reason=201` (NO_AP_FOUND) | **99** |
| `STA_CONNECTED` / `STA_GOT_IP` (the connect that ended a retry burst) | 14 |
| `reason=200` (beacon timeout) | 2 |
| `reason=202` | 2 |
| `STA_START` | 0 (there was one, at boot) |

The 201s arrive at a **2.4 s cadence** in runs of 5–40 (`2.4 2.4 2.4 3.1 2.5 2.5 2.5 | 94.0 | 2.4 × 9 …`)
— the ESP-IDF auto-reconnect retrying a scan+connect while no AP answers — and the trips land inside
those runs, typically one per 2–3 retries, never during the long quiet gaps.

**Verdict.** Association, TLS traffic and isolated scans do not sag the rail below level 7. A
**sustained full-channel active-scan loop with no AP found** does, repeatedly, for as long as it
lasts. So (1) the direction is **AP absence → firmware retry loop → sag**, not sag → radio loss —
a sag cannot make an AP vanish for 94 s stretches on a metronomic 2.4 s cadence; (2) the covariate
every rig verdict needs is not `disc` but **time spent in `NO_AP_FOUND` retry** (W′ = count of
`reason=201` in-window); (3) the boot-window trip is the same phenomenon in miniature — WiFi init
scans all channels once. Production's IDF brownout ISR would have rebooted this board ~118 times in
that hour; the "rig instability" that blocked runs on flapping-AP days was this loop.

**Consequences for the plan.** P2's ladder stays (it measures depth per load; P1 measured the
trigger). P3 unchanged. **A firmware lever now exists that the mitigation matrix missed:** back
off the `NO_AP_FOUND` retry (exponential, capped) — it removes the sustained sag at source, and it
is the same loop TASK-426 documented as the boot-wedge mechanism. Filed as a candidate, not a
decision: **TASK-679** (retry backoff when the AP is absent, `-DBOD_WATCH`-measured before/after).
P1(c) proper — a bounded, non-persistent way to *provoke* the retry loop from the console (`set
scanLoop <s>`, no NVS write) — joins TASK-678's console additions, since it costs a reflash and the
board's current 29 h window is worth more than the confirmation tonight.

**CORRECTED 2026-09-11 by X-P1c ([EXP-026](../reports/EXP-026-p1c-scanloop-trips.md)).** The
verdict above was correlation. Provoking the identical `NO_AP_FOUND` retry loop with `set scanLoop`
— 300 s, 121 retry events, same board/cable/port, plus ~4 min of a natural outage — produced
**0 trips at level 7**. The 09-09 boot's 99 in-loop trips had a co-factor that is not the retry
loop itself and is **unidentified** (deeper sag that day; concurrent TLS retries; or an
instrument difference between the polled latch and the ISR — each named and untested in EXP-026
§4). What survives of §8: re-association does not trip (still 0/20); the boot-window trip is
deterministic and caught every boot by both instruments; W′ remains the right covariate to record,
but it is no longer shown to be the driver. TASK-679 (retry backoff) stays filed as a robustness
candidate, not as a rig fix. The depth ladder built for F-1 is **inert on this dip** (`dur=0
min=7` on every event — DET is clear before the ISR runs), so depth still comes from the
reboot-per-level sweep until the adaptive-descent variant lands.

**What P1 did not measure.** Trip depth (only level-7 presence/absence — the ISR ladder is
TASK-678); whether a *single* scan with the AP absent trips (all observed trips were inside runs);
anything about the 5 V rail.

## 9. Disposition of the finger-pointing, on today's evidence

- **Cable / host USB link:** clear — 0 protocol errors outside reset storms, 12 MB clean bulk
  read, 0 loss in the in-app burst.
- **Harness:** guilty twice (orphaned monitors, open cadence), both fixed, both fixes measured.
- **Board:** 3.3 V sags to ≈2.5 V on every PHY bring-up; IDF's ISR turns a survivable transient
  into a reboot loop. Real, hardware, unfixed.
- **AP / RF environment:** the un-indicted co-driver — now indicted by P1 (§8): AP absence drives
  the firmware's 2.4 s scan-retry loop, and that loop is what sags the rail in steady state.
- **Firmware:** one lever nobody pulled — the unbounded `NO_AP_FOUND` retry cadence (TASK-679
  candidate).
- **Flakes filed as RIG since 2026-09-02:** R was 0. Each needs W read before the label stands.
