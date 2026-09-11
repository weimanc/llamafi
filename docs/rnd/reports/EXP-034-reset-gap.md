# EXP-034 — X-P6: reset-gap sweep, n=30 per gap (PROP-011 X-P6)

> Owner: R&D · 2026-09-11 16:00–16:37 · operator: Opus (the Sonnet agent declined relayed approval
> for hardware resets; the human approved in the main conversation) · board: CYD on host port 1-1,
> `cyd2usb_winamp_debug` at `39246e0`, monitor stopped for the run.
> **Window ended:** 01 h 38 m (last heartbeat before the first reset), captured to
> `/tmp/claude-1000/xp6/window_before.txt` (16 572 timeline lines) per runbook §0.1 rule 2.

## Setup

Driver `app/tools/probe/rig_resetgap.py` (`33eab98`), TASK-555's method scaled from n=3 to n=30:

```
per trial:  stamp reset → esptool --before default_reset --after hard_reset chip_id   (reset 1, app boots)
            sleep GAP
            stamp reset → esptool --before default_reset --after hard_reset chip_id   (reset 2)
            sleep 3
            esptool --before no_reset --after no_reset --connect-attempts 1 chip_id    (probe)
probe syncs  → chip in ROM bootloader → WEDGED;   probe cannot sync → app running → OK
```

```
cd app/tools && nohup systemd-inhibit --what=sleep --mode=block … env RIGWATCH=1 PYTHONPATH=. \
  python3 probe/rig_resetgap.py --i-know-this-resets-the-board --gaps 1,2,4,8,12 --trials 30 \
  --out /tmp/claude-1000/xp6/trials.jsonl
```

## Raw

```
{"gap": 1.0, "trial": 1, "rc1": 0, "rc2": 0, "rc_probe": 2, "wedged": false, "t0": 1789139597.05, "reenum": 0}
{"gap": 1.0, "trial": 2, "rc1": 0, "rc2": 0, "rc_probe": 2, "wedged": false, "t0": 1789139606.913, "reenum": 0}
…  (150 rows, all rc1=0 rc2=0 rc_probe=2 wedged=false reenum=0)
{"gap": 12.0, "trials": 30, "wedged": 0, "reset_fail": 0, "reenum": 0}
rigwatch summary --since 45m: reenum(R)=0 unexplained_boots(U)=0 bod_trips=0 wifi_disc(W)=0 events=327
harness reset stamps in window: 300   (2 per trial × 150)
```

`rc_probe=2` on every trial is esptool's "Failed to connect … No serial data received" — the
application was running, i.e. not wedged.

## Numbers

| gap | trials | wedged | reset failures | re-enumerations |
|---|---|---|---|---|
| 1 s | 30 | **0** | 0 | 0 |
| 2 s | 30 | **0** | 0 | 0 |
| 4 s | 30 | 0 | 0 | 0 |
| 8 s | 30 | 0 | 0 | 0 |
| 12 s | 30 | 0 | 0 | 0 |
| **total** | **150** (300 resets) | **0** | **0** | **0** |

R=0, U=0 over the run: every one of the 300 boots is explained by a stamp.

## Decision

Runbook X-P6: *0 wedges at ≤ 2 s over 30 trials on both builds → BP-018's 12 s gap meets its own
written retirement criterion; any wedge → the gap stays.*

**0/60 at ≤ 2 s (0/150 overall) — but the criterion is NOT met, and the rule is not retired.**
BP-018's criterion asks for ≥ 30 trials at ≤ 2 s on a quiet rig **and** on a flapping rig; this run
is the quiet leg only (R=0 throughout, no re-enumeration in 300 resets). The runbook's "both builds"
leg (production) is also not run — the board is pinned to the debug build. What this run does settle:
TASK-376's "back-to-back resets drop this CYD into download mode" does **not** reproduce at any gap
from 1 s to 12 s at n=30 on this board, supply and cable today — the upper bound on the wedge rate
at ≤ 2 s is ~5 % (0/60, 95 % one-sided).

## Not measured / anomalies

- Flapping-rig leg: no flapping rig is available (R has been 0 since 2026-09-02 on the BOD_WATCH
  build). The next time rigwatch reports R>0, re-run `rig_resetgap.py --gaps 1,2 --trials 30`.
- Production build: not run (pin). Its IDF brownout ISR is armed, which is the build most likely to
  behave differently on a reset during a sag.
- `[bootreason]` per boot was not captured (the monitor was stopped, so the boots were unobserved
  except through the probe and rigwatch's kernel events); the probe is the wedge criterion, not the
  boot reason.
