# EXP-036 — display-only rung and backlight A/B at level 2 (PROP-011 X-P2b-1/2)

> Owner: R&D · 2026-09-11 · agent tier: Sonnet · board: bare rig `~/proj/webradio-bare` rung 6
> (`-DBARE_TFT -DBARE_BOD_THRES=<n>`) for X-P2b-1; `cyd2usb_winamp_debug` build `3e2ec2c` for
> X-P2b-2's counted (corrected) run, driver fixed at `d559856` · window ended: yes — the X-P2
> window from earlier 2026-09-11 was already open/closed; this run's own ~2 h pre-capture window
> ended at the first `rig_ladder` flash (§0.1 rule 2).

## Setup — exact commands run, in order

```
./run/monitor-stop
./run/rig-timeline --since 2h > /tmp/claude-1000/xp2b/timeline_before.txt

cd app/tools
RIGWATCH=1 PYTHONPATH=. ~/proj/esp/venv/bin/python3 probe/rig_ladder.py \
  --i-know-this-resets-the-board --rungs 6 --levels 7,5,3,2 --reps 3 \
  --out /tmp/claude-1000/xp2b/rung6.jsonl

./run/flash-debug          # restore full firmware (attempt 1, no retry needed)
./run/monitor-start
# confirmed [bootphase] 6 ready + [bod] armed thres=... in /tmp/spotify-mon-serial.log

# board was still armed at thres=1 (RTC_NOINIT carried over from an earlier session,
# not from this run) — restored to 7 by hand before X-P2b-2, stamped first:
python3 -m lib.rigwatch stamp reset who=xp2b-restore
tmux send-keys -t spotify-mon 'bod 7' Enter
tmux send-keys -t spotify-mon 'reboot' Enter

# first X-P2b-2 run (pre-fix driver) — invalid, see Not measured/anomalies; superseded
for m in 0 1 0 1 0 1 0 1 0 1 0 1; do
  RIGWATCH=1 PYTHONPATH=. ~/proj/esp/venv/bin/python3 probe/rig_sweep.py \
    --i-know-this-resets-the-board --levels 2 --reps 1 --all --bodmit $m \
    >> /tmp/claude-1000/xp2b/ab_bodmit.log
done

# reviewer fix d559856 applied to rig_sweep.py (waits for ready, checks acks,
# slices the new boot only) — then re-run exactly as before:
for m in 0 1 0 1 0 1 0 1 0 1 0 1; do
  RIGWATCH=1 PYTHONPATH=. ~/proj/esp/venv/bin/python3 probe/rig_sweep.py \
    --i-know-this-resets-the-board --levels 2 --reps 1 --all --bodmit $m \
    >> /tmp/claude-1000/xp2b/ab_bodmit_v2.log
done

RIGWATCH=1 ~/proj/esp/venv/bin/python3 -m lib.rigwatch summary --since 2h
```

## Raw — the lines counted (pasted, not summarised)

### X-P2b-1 (rung 6, display-only, no WiFi) — `/tmp/claude-1000/xp2b/rung6.jsonl`

```
{"rung": 6, "level": 7, "rep": 1, "t": 1789149489.823, "tripped": false, "ready": true, "bootreason": 1, "armed_thres": 7, "wifi_ip": false, "usb_drop": false}
{"rung": 6, "level": 7, "rep": 2, "t": 1789149494.449, "tripped": false, "ready": true, "bootreason": 1, "armed_thres": 7, "wifi_ip": false, "usb_drop": false}
{"rung": 6, "level": 7, "rep": 3, "t": 1789149499.078, "tripped": false, "ready": true, "bootreason": 1, "armed_thres": 7, "wifi_ip": false, "usb_drop": false}
{"rung": 6, "trips_by_level": {"7": 0}, "b_boot": null}
{"summary": {"6": {"trips_by_level": {"7": 0}, "b_boot": null}}}
```

0/3 tripped at level 7 → the driver's `stop_rung` rule (0 trips, 0 drops) stopped the descent there;
levels 5, 3, 2 were never run for this rung.

### X-P2b-2 (full firmware, level 2, bodmit A/B) — corrected re-run, TASK-677 fix `d559856` — `/tmp/claude-1000/xp2b/ab_bodmit_v2.log` (per-boot dicts, in send order 0,1,0,1,0,1,0,1,0,1,0,1)

```
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 1, 'bodmit_duty': 0, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 246, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 1, 'bodmit_duty': 0, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 236, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 1, 'bodmit_duty': 0, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 225, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 1, 'bodmit_duty': 0, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 254, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 1, 'bodmit_duty': 0, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 231, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'armed_level': 2, 'bodmit_seen': True, 'bodmit_mask': 1, 'bodmit_duty': 0, 'bodmit_proved': True}
```

Every run printed `restored: bodmit 0 + bod 7 + reboot sent, ready` (the fixed `finally` now waits
for and confirms that restore boot reaches `[bootphase] 6` before the invocation exits) and no
`INVALID`/`REFUSED`/traceback appeared in the 12-run log (`grep -n "INVALID\|REFUSED\|Traceback"` →
0 hits) — all 12 acks (bare `bod` liveness, `bodmit N`, `bod 2`) landed and were confirmed every
time, `armed_level` reads 2 on every boot, and `bodmit_proved` is `True` on every boot (mask matches
what was actually requested, not just internally self-consistent).

### `rigwatch summary` (R/U, corrected re-run window)

```
since 2026-09-11 17:13:58.538  reenum(R)=4 unexplained_boots(U)=0 bod_trips=3078 wifi_disc(W)=427 events=4577
[triage] rig: R=4 reenum U=0 unexplained-boot(s) in this run's window — PROP-011 §4's RIG threshold (R=0 and U=0) was not met
```

## Numbers

| id | metric | value |
|---|---|---|
| X-P2b-1 | trips/3 at level 7 (display-only, no WiFi) | 0/3 |
| X-P2b-1 | levels 5, 3, 2 run | not run (descent stopped at 7) |
| X-P2b-2 | valid boots (acks confirmed, `armed_level`==2, `bodmit_proved`==True) | 12/12 (both arms 6/6) |
| X-P2b-2 | `bodmit=0` (backlight on) valid boots, trips | 6/6 |
| X-P2b-2 | `bodmit=1` (backlight off in-window) valid boots, trips | 6/6 |
| X-P2b-2 | trip-rate difference between arms | 0/6 |
| R/U | reenum / unexplained boots, `--since 2h` (corrected re-run window) | R=4, U=0 |

## Decision

**X-P2b-1** — runbook rule: *trips at 7 → the display alone sags ≥ level 7; no trip at 7 → display
alone contributes < one comparator step.* Result: **0/3 at level 7 → no trip.** The display (TFT
init + backlight full, no WiFi) alone contributes less than one comparator step (~50 mV, indicative
table, unverified) at the boot window. This is consistent with EXP-035's finding that rung 3
(WiFi+TFT) behaved identically to rung 2 (WiFi alone) — the display was never shown to add anything
there either, now confirmed in isolation without WiFi's much larger load riding on top.

**X-P2b-2** — runbook rule: *trip rate at level 2 differs by ≥ 3/6 → the backlight pushes the
WiFi-init dip across ~2.53 V; otherwise no effect at this resolution.* **Corrected re-run (driver fix
`d559856`), all 12 boots valid:** `bodmit=0` (backlight on through WiFi init) trips 6/6; `bodmit=1`
(backlight forced off through WiFi init) also trips 6/6. Difference = **0/6, below the ≥3/6
threshold → no effect at this resolution.** At the finest usable comparator step (level 2, ~2.53 V),
forcing the backlight off during WiFi bring-up does not measurably change whether the boot-window
dip trips the comparator — consistent with X-P2b-1's finding that the display's static contribution
is below one comparator step to begin with. Combined with EXP-035, WiFi remains the whole
identified load at this resolution; the display (backlight included) is not shown to add to it.

The original run of this experiment (before the driver fix below) produced an invalid A/B and is
superseded — see the anomalies note.

## Not measured / anomalies

- X-P2b-1 stopped at level 7 per the ladder's standard descent rule; B_boot for the display-only
  rung is therefore `null` (undefined — no level tripped), not a number to compare against WiFi
  rungs' B_boot ≤ 2.
- The board was found armed at `bod` threshold 1 (not 7) when the monitor first came back up after
  `./run/flash-debug`, carried over from an earlier, unrelated session — not something this run's
  drivers left behind (rig_ladder's rungs never touch the full-firmware `bod` state; rig_sweep's own
  `finally` always restores `bod 7`). Restored by hand (stamped) before X-P2b-2 began.
- R=4 over the corrected re-run's `--since 2h` window (12 `rig_sweep` runs × 2 reboots each = 24
  reboots, only 4 of which re-enumerated) — not further decomposed into "which reboot
  re-enumerated" here.
- **The first X-P2b-2 run (raw data no longer shown above, superseded) was invalid for three driver
  reasons, not a firmware reason** — reviewer finding, 2026-09-11, fixed in `d559856`:
  1. `rig_sweep`'s `finally` block sent its restore `reboot` and returned without waiting for it to
     complete; the next invocation started ~0.5 s later and typed `bodmit`/`bod`/`reboot` at a board
     that was often still mid-boot, and bytes arriving before `Serial` was ready were dropped.
  2. `run_one_boot` sliced the log from an offset taken *before* sending those commands, so when a
     command was silently dropped it analysed the *previous* boot (its `[bod] armed thres=`) and
     attributed that boot's trip/level to the current request — this is why the original raw log's
     `min=` alternated 2/7/2/7/… and half the "level 2" boots showed `min=7` instead.
  3. `parse_bodmit_proof` called a boot "proved" whenever its own `mask`/`duty` reading was
     internally self-consistent, without checking that `mask` matched what was actually requested —
     so a boot that silently kept the old mask (0) still read `bodmit_proved=True`.
  The fix adds a console-liveness check plus a required ack for every `bodmit`/`bod` send before a
  reboot is ever issued (an unacked boot is recorded `invalid: <reason>` and skipped, no blind
  reboot), slices strictly from the new boot's own `[bootphase] 0`, waits for the restore reboot's
  own `[bootphase] 6` before returning, and requires `mask == requested` for the proof. The
  corrected re-run above has 12/12 valid boots, `armed_level`==2 and `bodmit_proved`==True on every
  one.
- `dur=0` in the raw trip lines is not used in the decision above (F-6's adaptive-descent field, not
  a per-boot effect of the requested arm).
