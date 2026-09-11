# EXP-035 — X-P2: load ladder, B_boot per rung, and the level-0/1 USB drop (PROP-011 X-P2)

> Owner: R&D · 2026-09-11 16:40–17:25 · operator: Opus (human approved the hardware resets
> directly in the main conversation) · board: CYD on host port 1-1 · instrument: rig/bare_bod
> (F-4, `e522a73`) for rungs 1–4, `cyd2usb_winamp_debug` at `e48e4b0` for rung 5 · driver
> `probe/rig_ladder.py` (`e522a73`, fixes `27b606d`, `a6ea5c0`, `e48e4b0`) and `probe/rig_sweep.py`.
> **Window ended:** the X-P6 run had already ended it; this run began on a board with no window.

## Setup

Rungs (bare rig build flags, added cumulatively): 1 bare · 2 +`BARE_WIFI` · 3 +`BARE_TFT`
(backlight full) · 4 +`BARE_SD`. Per rung, levels 7 → 0 in order, 3 boots per level, each boot =
rigwatch `reset` stamp + serial open + RTS pulse on EN, read ≤ 30 s. Rung 0: 20 ×
`esptool --before default_reset --after no_reset chip_id` (ROM bootloader only). Rung 5: full
firmware, `rig_sweep.py` (console `bod N` + stamped `reboot`, the 2026-09-02 method).
Raw per-boot rows: `/tmp/claude-1000/xp2/{ladder,targeted,rung4,ab_*}.jsonl`, raw serial text in
the matching `.raw` files.

## Raw (selected; every row is in the jsonl files)

```
rung 1  L7 r1-3   ---- ready                 (no trip)
rung 2  L7..L2    TRIP ready  x12            (3/3 at every level)
rung 2  L1 r1     ---- DROP  noready         kernel: usb 1-1 disconnect dev 70 -> new dev 71, 16:49:26
targeted rung 2, order 1,7,1,0 (--no-stop):
  L1 DROP DROP DROP | L7 TRIP TRIP TRIP (ready) | L1 DROP DROP DROP | L0 DROP DROP DROP
rung 3  L7..L2    TRIP ready  x12 | L1 DROP (boot had printed [bootreason] 1, [bod] armed thres=1)
rung 4  L7..L2    TRIP ready  x12 | L1 DROP DROP DROP | L0 DROP DROP DROP
rung 0  20 bootloader resets: esptool failures 0, kernel attach events 0
A/B at level 1 (3 boots each):
  -DBOD_NO_ISR   (old polled latch)          DROP DROP DROP
  -DBOD_NO_HWACT (ISR, RF/flash actions off) DROP DROP DROP
  no WiFi (rung 1), ISR build                ---- ready x3
  -DBOD_NO_ISR at level 0                    DROP DROP DROP
rung 5 (full firmware)  L7 3/3 · L5 3/3 · L3 3/3 · L2 3/3 tripped, all booted
rung 5  L1 (bod 1 + console reboot)  booted=False x3
```

## Numbers

| rung | load | B_boot (lowest level tripping) | levels 1 and 0 |
|---|---|---|---|
| 0 | ROM bootloader | n/a (no app) | 0 USB drops in 20 resets |
| 1 | CPU + flash | none at 7 (0/3) | L1: 0/3 drops (A/B arm) |
| 2 | + WiFi | ≤ 2 (3/3 at 7,5,3,2) | **drop on every boot** (L1 9/9, L0 3/3) |
| 3 | + WiFi + TFT | ≤ 2 (3/3 at 7,5,3,2) | L1 drop 1/1 (then driver crash, fixed) |
| 4 | + WiFi + TFT + SD | ≤ 2 (3/3 at 7,5,3,2) | **drop on every boot** (L1 3/3, L0 3/3) |
| 5 | full firmware | ≤ 2 (3/3 at 7,5,3,2) | L1: 0/3 boots reached `ready` |

R over the X-P2 window: 41 re-enumerations (40 kernel attach events after 16:05), every one at an
arm level of 1 or 0 or in the level-1 aftermath below; U = 0 (every boot stamped).

## Decision

Runbook X-P2: *the rung where B_boot first drops by ≥ 2 levels names the load that carries the sag.*

1. **WiFi carries the boot-window sag.** Without WiFi the comparator never trips at level 7; with
   WiFi it trips 3/3 at every level from 7 to 2, and adding the display (backlight full) and the SD
   card changes nothing. Rung 5 (everything) is identical to rung 2 (WiFi alone). This confirms
   PROP-011's inference that the PHY bring-up is the load, now measured one load at a time.
2. **B_boot is ≤ 2 on every WiFi rung, but not below it — because levels 1 and 0 cannot be
   measured on this board today.** At an arm level of 1 or 0, every WiFi boot knocks the CH340 off
   USB before `[bootphase] 6 ready`; at levels 2–7, 0 drops in 51 WiFi boots (39 bare-rig: rungs 2–4 ×
   4 levels × 3, plus the targeted run's 3 at level 7; and 12 on the full firmware). It is the threshold
   value that matters, not run order (1 → 7 → 1 gives drop / clean / drop) and not the instrument:
   the old polled latch (`-DBOD_NO_ISR`) and the ISR with the brownout's RF/flash hardware actions
   disabled (`-DBOD_NO_HWACT`) drop identically, and the drop needs WiFi (level 1 without WiFi: 3/3
   clean). This refutes the hypothesis, raised mid-run, that the F-1 interrupt build caused it.
3. **This contradicts EXP-025's 2026-09-02 sweep**, where the full polled firmware at levels 1 and 0
   completed every boot (0 setup failures in 72). Rung 5 re-ran that exact method today (console
   `bod 1` + `reboot`) and 0/3 boots completed. So the 2026-09-02 result did not hold on
   2026-09-11 — the board's behaviour at the lowest thresholds has changed between the two days, or
   depended on a condition not recorded then. Mechanism unknown: the register difference between a
   clean level-2 boot and a dropping level-1 boot in polled mode is the 3-bit threshold field alone
   (`regAfter` 0x53ffc000 vs 0x4bffc000 pattern), with reset, interrupt and hardware actions all off.
   The next instrument is physical: a scope on 3V3 and the CH340's VCC at WiFi init, arm level 2 vs 1.

## The level-1 aftermath (recorded because it is TASK-557 data)

After rung 5's level-1 run, `bod 1` persisted in RTC_NOINIT, so every reboot re-armed at level 1.
The board did **not** boot-loop: it stayed up with WiFi down, and the CH340 re-enumerated every
~61 s (17:15:39, 17:16:40, 17:17:41) — the WiFi supervisor's 60 s re-kick cadence — i.e. **each WiFi
PHY start at level 1 drops USB, with no chip reset.** The monitor went blind at the first drop, so
the console could not restore level 7, and a reflash would not have either (RTC_NOINIT survives it).
Recovered remotely: `esptool --before default_reset --after hard_reset write_mem 0x50000210 0`
(`s_bootThresMagic`, from the ELF) invalidated the saved setting; the next boot armed at 7, got
WiFi, `bod` read `thresNow 7 bootThres 7`, and there were 0 re-enumerations in the next 2 minutes.
**Operating rule this adds:** never leave a board armed at level ≤ 1 — `rig_sweep.py` must restore
level 7 itself, and the runbook's sweep recipes stop at level 2 until the mechanism is known.

## Not measured / anomalies

- **Steady-state trips right after recovery.** The recovered boot (level 7, full firmware) logged
  16 `tag=run` trips (plus `wifi-end` and `services`) in its first ~30 s, while WiFi re-associated
  through 4 × `reason=201`, 1 × `200`, 1 × `2` after an initial `STA_GOT_IP`. In the next 90 s: no
  new trips, WiFi held (`rssi -66`, `disc` flat at 9), 0 re-enumerations; the host saw the AP at
  signal 72. This is the 2026-09-09 shape (steady-state trips during association trouble) and it
  sits beside X-P1c's 0 trips in 121 provoked `NO_AP_FOUND` retries (EXP-026) — recorded, no cause
  inferred. It came at the end of ~2 h of continuous flashing and resets, so board temperature is an
  uncontrolled variable here.
- **B_boot below 2** cannot be measured on this board while levels 1/0 drop USB.
- **No meter or scope**: every voltage in this report is the comparator's indicative table.
- **Rung 3 at level 0** was not run (the first run crashed at rung 3 level 1 before the drop fix).
- **rig_sweep.py** now refuses levels below 2 without `--allow-low-levels` and always restores
  `bod 7` + a stamped `reboot` at the end (commit with this report).
