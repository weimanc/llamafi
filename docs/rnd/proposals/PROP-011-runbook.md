# PROP-011 runbook — executable test specs for cheaper agents

> Owner: R&D · Written 2026-09-10 (Fable) so that Sonnet/Haiku agents can do the legwork of
> [PROP-011](PROP-011-rig-ground-truth.md) without re-deriving it. **Every experiment below is a
> self-contained brief**: prerequisites, agent tier, board cost, exact commands, what to capture,
> how to decide, where to record. An agent executing one reads §0 first and the one section it was
> assigned — nothing else is required.
> Status per experiment is tracked **in this file's §0.4 table only**; results go to `EXP-0NN` reports.

---

## 0. Read first — rules that apply to every experiment

### 0.1 Agent operating rules (paste into every brief by reference: "PROP-011-runbook §0.1")

1. **Never open the serial port yourself.** No `pio device monitor`, no pyserial, no `esptool`
   unless the experiment says so explicitly. A port open asserts DTR → resets the board → ends the
   TASK-557 observation window. Read the board through the existing tmux monitor:
   `tmux send-keys -t spotify-mon '<cmd>' Enter` to send, `./run/monitor-read N` or
   `/tmp/spotify-mon-serial.log` to read. `./run/rig-timeline` and `python3 -m lib.rigwatch` are
   file-only and always safe.
2. **Never run `run/flash*`, `run/test*`, `run/dut-health`, soaks or gates that touch the board
   unless the experiment's "Board cost" line says a reflash is part of it — and then only after
   `./run/rig-timeline --since 48h` has been captured and pasted into the result, because the
   reflash ends the window and the window's length is TASK-557 data.**
3. **Never restore production** (`run/flash` = `cyd2usb_winamp`). The board is pinned to
   `cyd2usb_winamp_debug` (`-DBOD_WATCH`). Only P5's production leg lifts the pin, only with the
   human's explicit go recorded in the result.
4. **Never kill a running `run/*` script, the `spotify-mon` tmux session, or the rigwatch daemon
   (`/tmp/spotify-rigwatch.pid`).** Never `pgrep -f 'pio device monitor'` without the `[p]io`
   bracket form (it matches your own shell).
5. Firmware changes go through `./run/check` (11 gates) and `./run/check-docs` (7 checks) before
   any flash. Host changes: `app/tools/smoke_test.sh` at minimum. Do not weaken a gate; do not edit
   a ledger to make a finding go away.
6. **Report numbers, never adjectives.** "Stable" means R=0 and U=0 over the stated window with W′
   recorded (§0.2). Every result pastes the raw lines it counted from.
7. Do not commit. Leave the tree for review; the report says exactly which files changed.
8. Firmware is `-std=gnu++11`: no aggregate brace-init with NSDMI structs. Debug env builds at
   `CORE_DEBUG_LEVEL=1` — a `log_w()` you expect to see will not print; read state back instead.

### 0.2 Metrics (PROP-011 §4, plus P1's refinement)

| symbol | definition | how to read it |
|---|---|---|
| **R** | CH340 re-enumerations on the DUT's USB port | `python3 -m lib.rigwatch summary --since <w>` → `reenum` |
| **U** | DUT boots (`[bootphase] 0`) with no harness stamp within ±3 s | same → `unexplained_boots` |
| **B_boot** | lowest BOD level (0–7) that trips in the boot window | `bod N` → `reboot` sweep; `[bod] TRIP tag=wifi-end` present/absent |
| **B_run** | steady-state `[bod] TRIP tag=run` count per unit of driver | `bod` query → `tripsSinceArm`, minus the boot trip |
| **W** | WiFi disconnects | heartbeat `disc=N` delta — never `[wifi-ev]` line counts (rate-limited) |
| **W′** | seconds spent in `NO_AP_FOUND` retry | count of `reason=201` lines × 2.4 s (P1 found this, not W, is the sag driver) |
| **L** | bytes lost or corrupt per MB per direction | `burst_check.py` / `serialsink` report |

Indicative BOD level → volts (published table, **unverified** on this silicon): 0:2.43 1:2.48
2:2.53 3:2.58 4:2.62 5:2.67 6:2.72 7:2.80.

### 0.3 Board and tooling facts an agent needs

- Board: ESP32-2432S028R CYD, two-USB variant, on host USB port `1-1` (root hub, no hub), node
  `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`. `run/local.env` has `RIGWATCH=1`.
- Debug env `cyd2usb_winamp_debug` (`-DBOD_WATCH -DSERIAL_DEBUG -DSD_BOOT_MOUNT`, CORE_DEBUG_LEVEL=1).
  Production `cyd2usb_winamp`. Bare rig: `~/proj/webradio-bare/` (104-line `main.cpp`, not a git
  repo, `[env:bare]`, `-DWITH_TFT` optional).
- Console (debug build, 115200): `bod [0..7]`, `bodmit [0..3]`, `reboot`, `get wifiCfg`,
  `set wifiDisc <x>` (leave + `WiFi.begin()`), `set wifiKick <x>` (quiesced single connect),
  `serialburst [lines] [pad]`, `get sig`, `uptime` via heartbeat `[I][hb] … uptime=HH:MM:SS`.
  `bod N` and `bodmit N` persist in RTC_NOINIT across `reboot` (not across power cycle).
- BOD trips print `[bod] TRIP tag=<time|wifi-end|run|ready> t=<ms> thres=<n> trips=<k> det=<0|1>`;
  `det=0` on a trip is normal (latched transient). The boot-window trip at level 7 lands at
  t≈1.5 s, tag `wifi-end`, every boot — it is the control that the sensor is alive.
- `esptool`: `~/.platformio/packages/tool-esptoolpy/esptool.py`. `--after no_reset` leaves the
  chip in the ROM bootloader (no app, no WiFi — the bare-minimum load); `--after hard_reset` boots
  the app. Both `--before default_reset`. **These open the port — allowed only where stated.**
- **A console `reboot` must be stamped** or rigwatch reports it as an UNEXPLAINED boot (U).
  Drivers going through `lib/monitor_tmux.send()` stamp it automatically; by hand, run
  `(cd app/tools && RIGWATCH=1 python3 -m lib.rigwatch stamp reset who=console)` immediately
  before `tmux send-keys -t spotify-mon 'reboot' Enter`.
- Reading BOD state without a reset: `tmux send-keys -t spotify-mon 'bod' Enter; sleep 2;
  tail -c 6000 /tmp/spotify-mon-serial.log | grep -a '"cmd":"bod"' | tail -1`.
- A ~150 s heap settle after any reset before trusting heap numbers (LL/BP-063); irrelevant to BOD.

### 0.4 Status board

| id | experiment | tier | needs | board cost | status |
|---|---|---|---|---|---|
| X-P1a/b | baseline + forced re-association | done | — | none | **DONE 2026-09-10**, PROP-011 §8 |
| F-1 | firmware: BOD ISR instrument (TASK-678 core) | Sonnet | — | 1 reflash (shared with F-2..F-5) | done (`a7000c5`, storm fix `4bda928`); DUT-verified 2026-09-11 **except depth**: ladder inert (`dur=0 min=7`, EXP-026 §4) |
| F-2 | firmware: `set scanLoop <s>` provoke command | Sonnet | — | shared | done (`c36594c`; NVS-safety + bodTrips fixes `e9f659f`/`4bda928`); DUT-verified |
| F-3 | firmware: `serialsink`, `serialecho`, `-DSERIAL_BAUD` | Sonnet | — | shared | done (`89625be`) |
| F-4 | firmware: bodWatch ported into the bare rig | Opus | — | separate board flashes (P2) | **done (`e522a73`)** — tracked copy at `rig/bare_bod/` (outside `app/`), rungs `-DBARE_WIFI/TFT/SD`, arm level `-DBARE_BOD_THRES`; all 4 rungs compile |
| F-5 | firmware: `-DBOD_WATCH` orthogonal flag + `BOD_POLICY` stub | Sonnet | Architect ruling for defaults only | shared | done (`c4291bf`) |
| H-1 | host: `rig_p1c.py`, `rig_sweep.py`, `rig_ladder.py`, `rig_uart.py`, `rig_resetgap.py` drivers | Sonnet/Opus | F-1..F-3 merged | none | done; fixture suites in `smoke_test.sh`; `rig_uart` run on the DUT (EXP-029/033), `rig_resetgap` (EXP-034), `rig_ladder` implemented (`e522a73`) and running X-P2 |
| F-6 | firmware: adaptive-descent depth (re-arm one level lower after each trip; floor = where trips stop) — replaces the in-event ladder, which is inert on this dip | Sonnet | F-1 | 1 reflash | **DUT-verified 2026-09-11 incl. descent + quiet step-up via synthetic faults** ([EXP-033](../reports/EXP-033-f6-staircase-echo.md)) |
| X-P1c | provoke the NO_AP_FOUND loop, trips per retry | Haiku/Sonnet | F-1, F-2, H-1 | none after the F-flash | **DONE 2026-09-11 — 0/121, refutes P1's inference** ([EXP-026](../reports/EXP-026-p1c-scanloop-trips.md)) |
| X-P2 | load ladder, B_boot per rung | Sonnet | F-1, F-4, H-1 | ~12 reflashes, ends window | open |
| X-P3 | supply A/B | **human + Sonnet** | F-1, H-1, cable/hub/meter | ~100 boots | open |
| X-P4 | UART transfer matrix | Sonnet | F-3, H-1 | none | **DONE 2026-09-11 — link clean both directions**: burst DUT→host 6 cells L=0; sink host→DUT 64 KB L=0 after the `3a30e1c` trailing-LF fix; R=0. Echo cell = RX-overflow instrument limit, re-spec'd as host windowing (`--window 8`, default) — re-run 2026-09-11 hit **2000/2000 echoed, 0 mismatches on the first attempt** ([EXP-033](../reports/EXP-033-f6-staircase-echo.md); original defect analysis in [EXP-029](../reports/EXP-029-uart-matrix.md) §Correction) |
| X-P5 | 72 h soaks, debug then production | Sonnet (monitoring) | F-1, F-5, **human go for production** | ends window; lifts pin | open |
| X-P6 | reset-gap sweep n≥30 | Opus | F-1 | ~300 resets | **DONE 2026-09-11 (quiet-rig leg)** — 0/150 wedged incl. 0/60 at ≤2 s, R=0 U=0; BP-018 not retired (flapping-rig + production legs owed) ([EXP-034](../reports/EXP-034-reset-gap.md)) |

Order: F-1…F-5 in one firmware commit set → one reflash → X-P1c → X-P4 (no further resets) →
X-P2 → X-P3 → X-P6 → X-P5. The first reflash ends the current window; capture it (§0.1 rule 2).

---

## 1. Firmware work items (all `app/src`, debug env unless stated)

### F-1 — interrupt-driven BOD instrument (TASK-678 core)

**Files:** `app/src/debug/bodWatch.{h,cpp}`, `app/src/debug/serialConsole/cmdMisc.cpp` (`bod`),
`cmdGet.cpp` (`get bod`), `console.cpp` (`mark`). Design: PROP-011 §3.1.

**Step 0 (host, 5 min):** `nm ~/.platformio/packages/framework-arduinoespressif32/tools/sdk/esp32/lib/libesp_system.a | grep -i brownout`.
**Done 2026-09-10:** `00000000 T esp_brownout_disable` — exported; `rtc_brownout_isr_handler` is
local (`t`). **Take the ISR path.** (The fallback — a pinned task polling the RAW latch at 1 kHz — is
not needed; keep this line so the reason is on record.) Declare it yourself:
`extern "C" void esp_brownout_disable(void);` — it is not in a public header of this IDF.

**Behaviour:**
- Arm as today (threshold from RTC_NOINIT, RST_ENA off) **plus**: `esp_brownout_disable()`,
  `rtc_isr_register(bodIsr, NULL, RTC_CNTL_BROWN_OUT_INT_ENA_M)`, set INT_ENA.
- `bodIsr` (`IRAM_ATTR`): read `esp_timer_get_time()`; bounded spin (≤ 2000 µs) on `BROWN_OUT_DET`
  to measure duration; **ladder**: lower the threshold one level at a time while DET stays set,
  record the lowest level reached, restore the armed level; capture context byte (boot phase,
  WiFi status shadow, backlight duty, SD-busy flag); push `{t_us, dur_us, min_level, ctx}` into a
  64-entry ring (drop-oldest, count drops); clear INT, re-enable. No printf, no malloc, no locks.
- `loop()` drains the ring → `[bod] TRIP tag=<phase> t=<ms> us=<t_us> dur=<dur_us> min=<lvl>
  thres=<n> trips=<k> ctx=<hex>` (keep the existing fields so rigwatch's regex still matches).
- `get bod` → JSON `{count, dropped, firstUs, lastUs, minLevel, maxDurUs, hist:[8], phaseAtFirst,
  thres, armed}`. `bod` (query) unchanged; `bod N` unchanged.
- `mark <label>` → prints `[mark] <label> us=<esp_timer>` and stamps nothing else.
- `set fault bod <level>` → invokes the ISR body with a synthetic reading (for the R34 runtime gate).

**Acceptance (host):** `./run/check` 11/11; `check_get_keys.py` sees the new `get bod`; a negative
transcript for `set fault bod` added under `check_can_go_red.py`'s corpus. **Acceptance (DUT, after
the shared reflash):** boot shows `[bod] armed … isr=1`; the boot-window trip now carries `us=`,
`dur=`, `min=`; `get bod` answers; a `mark x` line appears within 100 ms of sending. Measure the
comparator settle time once: with `bod 7`, the ladder's `min` on the boot trip vs the reboot-sweep
result from 2026-09-02 (levels 2/3 tripped, 0/1 did not) — they must agree within one level, else
the ladder's per-step delay is too short; tune and re-measure.

### F-2 — `set scanLoop <seconds>` (provoke the NO_AP_FOUND retry loop, non-persistent)

**File:** `cmdSet.cpp`, next to `wifiKick`. Behaviour: `WiFi.persistent(false)`; remember the current
SSID via `esp_wifi_get_config`; `WiFi.disconnect(false)`; `WiFi.begin("PROP011-no-such-ap-<rand>",
"x")` with auto-reconnect ON so IDF's own retry loop runs; after `<seconds>` (bounded 5–300, TWDT fed
every 100 ms), `WiFi.disconnect(false)`; `WiFi.begin()` with the saved config; report
`{"ok":true,"cmd":"set","var":"scanLoop","secs":N,"r201":<count during>,"reconnected":<0|1>}`.
Must **never** write NVS (that is TASK-426's wedge). Acceptance: after the command the board is
back on the real SSID with an IP within 20 s; `get wifiCfg` shows the original SSID.

### F-3 — UART direction/baud instruments

- `serialsink <bytes>`: read exactly `<bytes>` from Serial (timeout 10 s), running sum8 checksum and
  count; print `{"probe":"sink","bytes":N,"got":M,"sum":"%08x","bodTrips":k}`. Feed TWDT.
- `serialecho <lines>`: for each received line, echo it back prefixed `E#`; end with a JSON summary.
- `-DSERIAL_BAUD=<n>` build flag consumed by `Serial.begin()` (default 115200; `pio` `monitor_speed`
  must follow — add `cyd2usb_winamp_debug_921k` extending the debug env with the flag and
  `monitor_speed = 921600`, and register it in `run/check`'s env matrix if the matrix is
  enumerated by hand).

### F-6 — adaptive-descent depth (filed from EXP-026)

**Files:** `app/src/debug/bodWatch.{h,cpp}`, `app/src/debug/serialConsole/cmdMisc.cpp` (`bod`),
`cmdGet.cpp` (`get bod`), `console.cpp` (help text). **Why:** EXP-026 §4 found the in-event ladder
inert on this dip shape — every captured event reads `dur=0 min=7`, i.e. `BROWN_OUT_DET` is already
clear by the time the ISR runs, so lowering the threshold mid-event finds nothing. Depth for
steady-state events instead comes from moving the *armed* level itself, across events, in the
consumer — never the ISR.

**Behaviour:** off by default; `bod descend on|off` toggles it immediately (this session) and
persists it in the same RTC_NOINIT block as the boot threshold, so it also survives a console
`reboot` — a cold boot always comes up off. `bod quiet <ms>` sets the step-back-up interval
(default 30000, floored at 1000). In `bodWatchRearm()`, when descend is on and the trip that just
disarmed the ISR happened at armed level L, the re-arm records `floor = min(floor, L)` (a level
that actually tripped) and, if L>0, lowers the register to L-1. Every such trip also resets the
quiet timer. If no trip occurs for `quietMs` while armed strictly below the boot threshold,
`bodWatchTick()` steps back up one level (capped at the boot threshold). The
boot-window trip (`tag=wifi-end`, still inside `setup()`, drained by boot.cpp's own
`bodWatchPoll("wifi-end")`) is excluded by tag so it always fires at the boot threshold — B_boot
from the reboot-per-level sweep stays comparable with descent on or off. Every level change prints
`[bod] arm level=<n> reason=descend|quiet|manual` (`manual` = the `bod descend on` toggle itself,
so rigwatch's timeline has a marker for where a descent run started). `get bod` gains `descend`,
`armedLevel` (the live level — equals `thres` once descent has moved it), `floor` (lowest level
that tripped under descent since arm; 8 = none), `stepsDown`, `stepsUp`, `quietMs`.
*(Corrected 2026-09-11 at review, commit after `e636513`: the first implementation recorded the
level stepped down TO — one below anything observed — and reset the quiet timer only on level
changes, so a board tripping steadily at level 0 would have been stepped up.)*

**Acceptance (host, done):** `./run/build-debug` SUCCESS; `./run/check` 11/11; `./run/check-docs`
7/7.

**Acceptance (DUT, not yet run — recipe for whoever runs it next):**
1. `tmux send-keys -t spotify-mon 'bod descend on' Enter` → expect
   `{"ok":true,"cmd":"bod","var":"descend","on":true}` and a
   `[bod] arm level=<boot-thres> reason=manual` line.
2. `tmux send-keys -t spotify-mon 'set scanLoop 120' Enter`, wait ~150 s, repeat once more.
3. Either a `[bod] arm level=<n> reason=descend` staircase appears (each line's level one lower
   than the last, down to some floor) or no trips occur at all in the window (consistent with
   X-P1c's 0/121 — descent has nothing to descend from on a quiet supply day).
4. `tmux send-keys -t spotify-mon 'get bod' Enter` → `armedLevel` should equal the last `reason=`
   line's level (or the boot threshold if nothing tripped); `floor` should equal the lowest `thres=`
   on any `[bod] TRIP tag=run` line in the window (one above the last `reason=descend` level if the
   staircase stopped on its own), or `8` if nothing tripped.
5. If a `reason=descend` line appeared, wait `quietMs` (default 30 s) past the last trip with no
   further provoke command running → expect a `reason=quiet` line stepping back toward the boot
   threshold.
6. `bod descend off` to leave the board in the safe default before any other experiment reuses it.

### F-4 — bodWatch in the bare rig

Copy `bodWatch.{h,cpp}` into `~/proj/webradio-bare/src/`, call `bodWatchArm(7)` first thing in
`setup()`, `bodWatchTick()` in `loop()`, print `[bootphase] 3 wifi` / `[bod]` lines in the same
format. Add `-DBARE_WIFI`, `-DBARE_TFT`, `-DBARE_SD` build switches so P2's rungs are one flag each.
No console needed: the threshold is a build flag `-DBARE_BOD_THRES=n` (a reflash per level is
acceptable on the bare rig; it has no observation window to protect).

### F-5 — `-DBOD_WATCH` as an orthogonal flag; `BOD_POLICY` stub

Move `-DBOD_WATCH` out of `[env:cyd2usb_winamp_debug]` into a `[bod_watch]` snippet included by the
debug env (so the flag can be added to any env by one line); add `-DBOD_POLICY=<n>` handling in the
ISR: if `min_level ≤ n` and `dur_us ≥ 500` → set `g_bodDeep`; `loop()` prints `[bod] policy
deep=<lvl> dur=<us>` and, if `BOD_POLICY_RESTART` is also defined, flushes and `esp_restart()`s.
**Defaults:** debug env `BOD_POLICY` undefined (observe only); production untouched. The production
default is TASK-578's ruling, not this task's.

---

## 2. Host work item H-1 — experiment drivers (`app/tools/probe/`)

All drivers talk to the board **only** through the tmux monitor (`app/tools/lib/monitor_tmux.py` —
`tmux send-keys -t spotify-mon`, reading `/tmp/spotify-mon-serial.log`); they stamp phases via
`lib.rigwatch.stamp()`. Each has a `--dry-run` that prints the exact command/stamp sequence and
touches nothing. Device-free tests with recorded fixtures (`probe/test_rig_*.py`), wired into
`smoke_test.sh` next to `probe/test_burst_check.py`. Delivered (TASK-677/678, this commit set):

- `probe/rig_p1c.py --secs 60,60,60,120`: reproduces EXP-026 §1 step 5's sequence exactly (stamp
  begin, baseline `get bod`, per-secs: stamp, `set scanLoop N`, sleep N+30s, slice the log, pull the
  scanLoop JSON + trip/reason=201 counts, `get bod`; `get wifiCfg`, stamp end). W′/retries are
  derived from the JSON fields (§0.2), not the rate-limited `reason=201` line count.
- `probe/rig_sweep.py --levels 7,5,3,2,1,0 --reps 3`: `bod N` → `reboot` → wait for `[bootphase] 6`
  → record whether `[bod] TRIP tag=wifi-end` appeared and its `min=`/`dur=`; outputs B_boot and the
  per-level table. **Refuses (exit 3) without `--i-know-this-resets-the-board`** — every rep is a
  real reset — and captures `./run/rig-timeline --since 48h` to a file before the first one.
- `probe/rig_ladder.py`: the argument parser and a REFUSAL only — **BLOCKED on F-4** (not landed).
  Checks for `~/proj/webradio-bare/src/bodWatch.h` as F-4's landing marker; even once F-4 lands, the
  flash/monitor/parse loop itself is not implemented yet (there was nothing to drive it against this
  session). Fixture test pins both the refusal and the "still not implemented" message.
- `probe/rig_uart.py`: the X-P4 matrix. `serialburst` cells (2000/20000 lines × 8/64/200 pad) reuse
  `burst_check.check()` against a tmux-sliced log — no second wire-format parser. `serialsink`: only
  the **64 KB cell is implemented**; the 1 MB cell is not merely slow over tmux, it is unreachable on
  the current firmware — `cmdSerialSink`'s own 10 s deadline (cmdMisc.cpp:377) caps one call at
  ~115 KB at 115200 baud regardless of transport (the `_921k` env would raise that ceiling to
  ~1.15 MB/10 s, but needs its own reflash, out of this session's scope). `serialecho`: 2000
  generated lines fed via `tmux send-keys -l` in 200-line chunks (avoids the per-line subprocess
  cost that would otherwise threaten the firmware's 30 s window), diffed against the E#-prefixed
  replies.

None of the four were run against the live board this session (PROP-011-runbook.md §0.1: `--dry-run`
only) — `rig_p1c.py`'s and `rig_uart.py`'s non-dry-run paths are implemented and fixture-tested but
unexercised on hardware; whoever runs X-P1c again, X-P2, or X-P4 next should treat the first live run
as this session's real acceptance test.

---

## 3. Experiments

### X-P1c — trips per NO_AP_FOUND retry (Haiku/Sonnet, ~20 min, no reset)

**Pre:** F-1, F-2, H-1 on the board. **Board cost:** none.
**Do:** `rig_p1c.py --secs 60 --reps 3`, then `--secs 120 --reps 1`.
**Capture:** per rep: trips, r201, W′, `get bod` histogram; the timeline.
**Decide:** trips/retry ≥ 0.2 and `min_level` distribution → AP-absent scanning is the steady-state
driver, quantified. trips ≈ 0 → P1(c) of 09-09 was something else; escalate, do not guess.
**Record:** `docs/rnd/reports/EXP-026-p1c-scanloop-trips.md`.

### X-P2 — load ladder, B_boot per rung (Sonnet, one DUT afternoon)

**Pre:** F-1, F-4, H-1. **Board cost:** ends the debug window (capture it first, §0.1 rule 2);
~12 flashes; the board is returned to `cyd2usb_winamp_debug` at the end with `./run/flash-debug`.

| rung | build | flags |
|---|---|---|
| 0 | ROM bootloader | `esptool … --after no_reset` (no firmware runs) — BOD not observable; this rung is R/U only: 20 resets, count re-enumerations |
| 1 | bare | `-DBARE_BOD_THRES=n` only |
| 2 | bare + WiFi | `-DBARE_WIFI` |
| 3 | bare + WiFi + TFT | `-DBARE_WIFI -DBARE_TFT` |
| 4 | bare + WiFi + TFT + SD | `-DBARE_WIFI -DBARE_TFT -DBARE_SD` |
| 5 | full debug | `run/flash-debug`, then `rig_sweep.py` |

For rungs 1–4: per level 7,5,3,2,1,0 (in that order, stop descending at the first no-trip level),
3 boots each → B_boot. For rung 5: `rig_sweep.py --levels 7..0 --reps 3`.
**Decide:** the rung where B_boot first drops to ≥ 2 names the load that carries the sag.
**Record:** `EXP-027-load-ladder.md`, table rung × level → trip/3.

### X-P3 — supply A/B (HUMAN present + Sonnet driving, ~2 h)

**Pre:** F-1, H-1; a short thick USB cable, a powered hub, optionally an inline USB V/A meter.
**Board cost:** ~100 boots per condition; ends the window (capture first).
**Conditions, same firmware, same host:** (A) as-is; (B) short thick cable, same port; (C) powered
hub; (D) laptop's other USB socket; (E) bench 5 V into the CYD's second USB connector, data on the
CH340 connector — **before trusting E, verify with a meter that the two connectors' 5 V rails are
common**; (F) any of A–E with the meter inline, read min/avg during boot.
**Per condition:** `rig_sweep.py --levels 7..0 --reps 3` → B_boot; then 30 `reboot`s at level 7
counting `[bod] TRIP` and R.
**Decide (PROP-011 §5 P3 rule):** B_boot unchanged across A–E → regulator-limited → hardware fix
(bulk capacitance on 3.3 V / lower-dropout LDO); TASK-557 closes as a board defect. B_boot rises by
≥ 2 levels under C/E → upstream 5 V; the fix is external.
**Record:** `EXP-028-supply-ab.md`. The human signs the conditions table (BP-075: ACCEPTED, not PASS).

### X-P4 — UART transfer matrix (Sonnet, ~1 h, no reset)

**Pre:** F-3, H-1. **Board cost:** none (the 921k cell needs the `_921k` env → one reflash; run it
last or skip with a note).
**Cells:** DUT→host `serialburst` lines {2000, 20000} × pad {8, 64, 200}; host→DUT `serialsink`
{64 KB, 1 MB}; bidirectional `serialecho` 2000 lines; each at 115200, then the 921k env.
**Capture:** L per cell; `bodTrips` during each cell; R over the whole run.
**Decide:** L=0 everywhere and R=0 → the link is clean on record (PROP-011 §2 row closes). Any
L>0 → reproduce that cell 5×; if it recurs, the 7-byte `read_flash` corruption of 09-02 has a
home; if not, record as single-event noise.
**Record:** `EXP-029-uart-matrix.md`.

### X-P5 — 72 h soaks (Sonnet monitors; HUMAN go for the production leg)

**Pre:** F-1, F-5. **Board cost:** ends the window; the production leg **lifts the TASK-557 pin**
and needs the human's explicit written go in the result.
**Leg 1 (debug, `BOD_POLICY` observe-only):** `./run/flash-debug`, then every hour for 72 h:
`python3 -m lib.rigwatch summary --since 1h --json` appended to `/tmp/p5_debug.jsonl`, plus
`get bod` histogram via the monitor. No other board interaction.
**Leg 2 (production):** `./run/flash` (human go), same hourly capture — production has no console,
so the DUT half is `[bootreason]` lines only: count `9 BROWNOUT` boots and R.
**Decide:** production's brownout reboots per hour vs W′ per hour is the number TASK-578 needs.
**Record:** `EXP-030-72h-soaks.md`; restore `./run/flash-debug` at the end.

### X-P6 — reset-gap sweep at n ≥ 30 (Sonnet, ~1 h)

**Pre:** F-1. **Board cost:** ~150 resets (ends the window).
**Do:** for gap in 1, 2, 4, 8, 12 s: 30 pairs of `esptool … --after hard_reset` (allowed here)
separated by `gap`; after each pair, `[bootreason]` and whether the board answers `bod` within
15 s; R over the run. Repeat on the production build if P5's leg 2 is running anyway.
**Decide:** 0 wedges at ≤ 2 s over 30 trials on both builds → BP-018's 12 s gap meets its own
written retirement criterion; file the retirement. Any wedge → the gap stays, with the measured
minimum.
**Record:** `EXP-031-reset-gap.md`.

---

## 4. Result report template (`docs/rnd/reports/EXP-0NN-<slug>.md`)

```
# EXP-0NN — <title> (PROP-011 <experiment id>)
> Owner: R&D · date · agent tier · board: env + build hash · window ended? (length, cause)
## Setup — exact commands run, in order
## Raw — the lines counted (pasted, not summarised), rig-timeline excerpt
## Numbers — the §0.2 metrics for this run, one table
## Decision — the runbook's decide-rule applied, verbatim, with the outcome
## Not measured / anomalies — anything the numbers do not cover
```

A report with a Decision but no Raw section is not accepted.
