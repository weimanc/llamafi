# EXP-038 — DUT1 retested on a different port and cable: the failure does not reproduce

> Owner: R&D · 2026-09-12 00:05–00:15 · operator: Opus · board **DUT1** `d4:8a:fc:c8:ee:d0` on host
> USB port `5-1` (`pci-0000:c3:00.3`) with a **different cable** from its earlier tests · instrument
> rig/bare_bod (F-4) · driver `probe/rig_ladder.py`.
> **This report supersedes [EXP-037](EXP-037-dut2-replication.md)'s decision.** Its "DUT1-specific
> board marginality" reading is no longer supported.

## Setup

The human states that **DUT2's run used DUT1's original port and cable**, and that DUT1 now sits on a
different port with a different cable. That makes this retest the second half of the control: if the
sag and the USB drop follow the board, DUT1 must still show them here.

```
cd app/tools
probe/rig_ladder.py --i-know-this-resets-the-board --port <DUT1 by-path c3:00.3> --rungs 2 --levels 7 --reps 3
probe/rig_ladder.py --i-know-this-resets-the-board --no-stop --port <DUT1 ...> --rungs 2 --levels 1,7 --reps 3
```
rigwatch's daemon was filtering DUT2's port (`1-1`) during this run, so its R/U do not cover DUT1;
the driver's own `usb_drop` per boot is the drop measurement here.

**Board identity, checked after the run, not inferred:** `read_mac` on the retested socket
(`pci-0000:c3:00.3`) returns `d4:8a:fc:c8:ee:d0` — DUT1. Its debug firmware was restored afterwards
with `PORT=<c3 by-path> ./run/flash-debug` (log line `Serial port …c3:00.3…`). One earlier restore
attempt used `DUT_PORT_PATH=c3:00.3 ./run/flash-debug` and flashed **DUT2** instead: `run/lib.sh`
sources `run/local.env` after the caller's environment, so that file's plain `export` won. It
re-flashed DUT2 with the firmware it already had (`a0c95c7`), touching no data. `run/local.env`'s
exports are now `${VAR:-default}` and the runbook §0.3 records the override order.

## Raw

```
{"rung": 2, "level": 7, "rep": 1..3, "tripped": false, "ready": true, "bootreason": 1, "armed_thres": 7, "wifi_ip": true, "usb_drop": false}
{"rung": 2, "level": 1, "rep": 1..3, "tripped": false, "ready": true, "bootreason": 1, "armed_thres": 1, "wifi_ip": true, "usb_drop": false}
{"rung": 2, "level": 7, "rep": 1..3, "tripped": false, "ready": true, "bootreason": 1, "armed_thres": 7, "wifi_ip": true, "usb_drop": false}
{"summary": {"2": {"trips_by_level": {"1": 0, "7": 0}, "b_boot": null}}}
```
(one `wifi_ip` false among the first three boots — that boot still reached `ready`; WiFi connected on
8 of 9 boots overall.)

## Numbers

| condition | board | port + cable | trips @7 | trips @1 | USB drops @1 |
|---|---|---|---|---|---|
| EXP-035/036 (16:40–19:30) | DUT1 | original `1-1` + original cable | **3/3 at 7,5,3,2** | n/a (dropped) | **9/9** |
| EXP-037 (22:10–23:30) | DUT2 | **same** `1-1` + same cable | 0/3 | 0/6 | **0/12** |
| **this run (00:05)** | **DUT1** | `5-1` + different cable | **0/3** | **0/3** | **0/3** |

## Decision

**The failure follows neither the board nor the cable/port on its own.** DUT1 failed on the original
port+cable and passes on the other one; DUT2 passes on the *same* original port+cable that DUT1
failed on. No single-factor explanation survives:

* **board alone** — refuted by this run (same board, no trips, no drops);
* **cable/port alone** — refuted by EXP-037 (same cable and port, other board, no trips);
* **board × cable/port interaction** — still possible (a marginal cable that only this board's
  inrush exposes);
* **a time-varying condition** — still possible and now the leading candidate: DUT1's failing data
  came after ~2 h of continuous flashing, resets and WiFi churn (board temperature, and an AP that
  was dropping out — EXP-026/035 recorded `NO_AP_FOUND` storms), whereas both passing runs were cold
  boards in a quiet period.

This also reframes the whole 2026-09-11 sequence: **EXP-035's "B_boot ≤ 2 on every WiFi rung" and the
level-≤1 USB drop are properties of DUT1 in that session's condition, not established properties of
the board, the cable, or the CYD design.** TASK-557 cannot close as a board defect on this evidence.

## Next steps (in order; each is decisive for one cell)

1. **Re-run DUT1 on the original port + cable now** (swap the two boards' cables). If it fails again
   → board × cable/port interaction, and the cable is the thing to replace. If it passes → the
   failure is gone, and the condition (temperature/AP/uptime) is the driver.
2. **If step 1 passes: provoke the condition** — repeat the ladder on DUT1 after ~2 h of continuous
   flash/reset/WiFi churn, or with the AP made to disappear (`set scanLoop`), and watch for the
   trips returning.
3. Only then revisit X-P3 (supply A/B with a meter), whose value now depends on which cell above
   reproduces the fault.

## Not measured / anomalies

- 9 boots per cell is thin for a fault whose earlier rate was 100 % — adequate to see a 9/9 → 0/9
  flip, not to bound a low rate.
- No measurement of the actual rail voltage anywhere; all statements are comparator trip/no-trip.
- DUT1's board temperature was not measured (no sensor reading in the firmware; the ESP32's internal
  sensor is a candidate — see EXP-035's anomalies).
- rigwatch R/U did not cover DUT1's port during this run (daemon filtered `1-1`).
