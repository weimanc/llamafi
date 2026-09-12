# EXP-039 — The fault is a board × cable/port PAIRING: DUT1 fails only on its original cable

> Owner: R&D · 2026-09-12 00:30–00:45 · operator: Opus (human swapped the cables between runs and
> confirmed each step) · instrument rig/bare_bod (F-4) · driver `probe/rig_ladder.py`.
> Closes the question [EXP-038](EXP-038-dut1-retest.md) opened. Together they supersede
> [EXP-037](EXP-037-dut2-replication.md)'s "DUT1-specific board marginality" reading.

## Setup

Four cells, one variable at a time, each 3 boots of the bare rig at the stated arm level (WiFi rung),
each board identified by `read_mac` on its socket **in the same command as the check**:

| cell | board | port + cable |
|---|---|---|
| A (EXP-035/036) | DUT1 `d4:8a:fc:c8:ee:d0` | original: `1-1` (`c1:00.3`) + original cable |
| B (EXP-037) | DUT2 `8c:94:df:92:3c:94` | **the same** `1-1` + original cable |
| C (EXP-038) | DUT1 | other: `5-1` (`c3:00.3`) + other cable |
| D (this run) | DUT1 | back on original `1-1` + original cable |

```
probe/rig_ladder.py --i-know-this-resets-the-board --port <c1 by-path> --rungs 2 --levels 7 --reps 3
probe/rig_ladder.py --i-know-this-resets-the-board --no-stop --port <c1 ...> --rungs 2 --levels 1,7 --reps 3
```

## Raw (cell D)

```
wifi7  L7: trips 3/3  drops 0  wifi_ip 2/3  ready 3/3  armed [7]
level1 L7: trips 3/3  drops 0  wifi_ip 2/3  ready 3/3  armed [7]
level1 L1: trips 0/3  drops 3/3  wifi_ip 0/3  ready 0/3  armed [None]   <- no boot got as far as printing its arm level
kernel: 5 × "usb 1-1: new full-speed USB device" during the run
```

## Numbers — the 2×2

| cell | board | port+cable | trips @7 | USB drops @1 |
|---|---|---|---|---|
| A | DUT1 | original | **3/3** | **9/9** |
| B | DUT2 | original | 0/3 | 0/12 |
| C | DUT1 | other | 0/3 | 0/3 |
| **D** | **DUT1** | **original** | **3/3** | **3/3** |

## Decision

**The fault is the pairing of DUT1 with its original cable/port, and it reproduces on demand.**
A and D agree (3/3 trips, USB drops at level 1); C removes the cable/port and the fault vanishes on
the same board; B removes the board and the fault vanishes on the same cable/port. So:

* **board alone** — refuted (cell C);
* **cable/port alone** — refuted (cell B);
* **condition/temperature/AP** — refuted as the *necessary* factor: cell D reproduced from a cold
  board within ~15 minutes of cell C's clean run, no 2-hour churn needed. (It may still modulate the
  rate; it is not what makes the difference.)
* **board × cable/port interaction** — the only surviving explanation, and now demonstrated
  4 cells / 4 consistent.

Mechanism, consistent with every measurement so far: that cable (or that socket) has enough extra
series resistance that DUT1's WiFi-inrush current pulls its 3V3 rail below the comparator threshold,
while DUT2 — same model, same silicon revision, evidently lower inrush or better decoupling — stays
above it on the identical cable. This is the first explanation that fits EXP-025's non-stationarity
too: a marginal contact resistance changes with reseating, temperature and cable flex, which is
exactly the "spontaneous recovery" pattern TASK-557 recorded for weeks.

**TASK-557 disposition:** not a board defect and not a design property. It is a **rig wiring fault**,
reproducible by pairing. Recommended action, in order:
1. Replace that USB cable (and prefer the other host socket), then re-run cell D — expect 0/3 trips.
2. Keep DUT2's cable/port assignment as the reference rig.
3. Only if the fault survives a new cable on that socket: suspect the socket/hub path, and then a
   meter on 5 V/3V3 is finally worth it (X-P3), now with a known-reproducing configuration.

## Not measured / anomalies

- 3 boots per cell here (9 in cell A) — enough for a 3/3 vs 0/3 flip, not to bound a low rate.
- Still no voltage measurement anywhere: every statement is comparator trip/no-trip.
- Cable and socket are not separated from each other: the swap moved both together. Cell D used
  `1-1` + original cable as one unit. Separating them needs the original cable on `5-1`, or a third
  cable on `1-1` — one extra run each, and step 1 above effectively does the second.
- `wifi_ip` was 2/3 in both level-7 cells; the third boot reached `ready` without an IP. WiFi
  association is not required for the trip — the sag is at PHY bring-up (EXP-035).
