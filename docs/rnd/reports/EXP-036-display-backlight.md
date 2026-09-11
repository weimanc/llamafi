# EXP-036 — display-only rung and backlight A/B at level 2 (PROP-011 X-P2b-1/2)

> Owner: R&D · 2026-09-11 · agent tier: Sonnet · board: bare rig `~/proj/webradio-bare` rung 6
> (`-DBARE_TFT -DBARE_BOD_THRES=<n>`) for X-P2b-1; `cyd2usb_winamp_debug` build `3e2ec2c` for
> X-P2b-2 · window ended: yes — the X-P2 window from earlier 2026-09-11 was already open/closed;
> this run's own ~2 h pre-capture window ended at the first `rig_ladder` flash (§0.1 rule 2).

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

for m in 0 1 0 1 0 1 0 1 0 1 0 1; do
  RIGWATCH=1 PYTHONPATH=. ~/proj/esp/venv/bin/python3 probe/rig_sweep.py \
    --i-know-this-resets-the-board --levels 2 --reps 1 --all --bodmit $m \
    >> /tmp/claude-1000/xp2b/ab_bodmit.log
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

### X-P2b-2 (full firmware, level 2, bodmit A/B) — `/tmp/claude-1000/xp2b/ab_bodmit.log` (per-boot dicts, in send order 0,1,0,1,0,1,0,1,0,1,0,1)

```
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 7, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'bodmit_seen': True, 'bodmit_mask': 1, 'bodmit_duty': 0, 'bodmit_proved': True}
{'tripped': True, 'min': 7, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 7, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 7, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 7, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 2, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 7, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 0, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
{'tripped': True, 'min': 7, 'dur': 0, 'level': 2, 'rep': 0, 'booted': True, 'bodmit': 1, 'bodmit_seen': True, 'bodmit_mask': 0, 'bodmit_duty': 256, 'bodmit_proved': True}
```

Every run printed `restored: bodmit 0 + bod 7 + reboot sent` and no `REFUSED`/traceback appeared in
the 12-run log (`grep -n "REFUSED\|Traceback"` → 0 hits).

### `rigwatch summary` (R/U)

```
since 2026-09-11 17:05:15.366  reenum(R)=20 unexplained_boots(U)=0 bod_trips=3055 wifi_disc(W)=427 events=4225
[triage] rig: R=20 reenum U=0 unexplained-boot(s) in this run's window — PROP-011 §4's RIG threshold (R=0 and U=0) was not met
```

## Numbers

| id | metric | value |
|---|---|---|
| X-P2b-1 | trips/3 at level 7 (display-only, no WiFi) | 0/3 |
| X-P2b-1 | levels 5, 3, 2 run | not run (descent stopped at 7) |
| X-P2b-2 | `bodmit=0` requests, trips/6 | 6/6 (every boot tripped regardless of arm) |
| X-P2b-2 | `bodmit=1` requests, trips/6 | 6/6 |
| X-P2b-2 | `bodmit=1` requests with the applied-state proof (`mask` bit0 actually set in `[bodmit] inwindow`) | **0/6** |
| X-P2b-2 | `bodmit=0` requests with `mask` bit0 unexpectedly set (proof of the *wrong* arm) | 1/6 (send #3) |
| X-P2b-2 | valid boots per the requested/actual-mask match (bit0 requested == bit0 read) | m=0: 5/6 valid; m=1: **0/6 valid** |
| R/U | reenum / unexplained boots, `--since 2h` | R=20, U=0 |

## Decision

**X-P2b-1** — runbook rule: *trips at 7 → the display alone sags ≥ level 7; no trip at 7 → display
alone contributes < one comparator step.* Result: **0/3 at level 7 → no trip.** The display (TFT
init + backlight full, no WiFi) alone contributes less than one comparator step (~50 mV, indicative
table, unverified) at the boot window. This is consistent with EXP-035's finding that rung 3
(WiFi+TFT) behaved identically to rung 2 (WiFi alone) — the display was never shown to add anything
there either, now confirmed in isolation without WiFi's much larger load riding on top.

**X-P2b-2** — runbook rule: *trip rate at level 2 differs by ≥ 3/6 → the backlight pushes the
WiFi-init dip across ~2.53 V; otherwise no effect at this resolution.* This decision **cannot be
applied**: the applied-state proof shows the `bodmit 1` ("backlight off across WiFi init") request
never actually took effect on the device — 0 of the 6 `bodmit=1` boots read `mask` with bit0 set in
their `[bodmit] inwindow` line; all 6 read `mask=0` (unmitigated), the same as the control arm. One
`bodmit=0` boot (send #3) spuriously read `mask=1` instead — the requested/actual mismatch runs
both directions, not just one-sided silent failure. By the exclusion rule stated in the runbook
brief ("the arm must show it on every boot, else that boot is invalid and excluded"), the
backlight-off arm has **zero valid boots**, so no A/B comparison exists to decide on. All 12 boots
tripped regardless of requested arm (12/12), which is uninformative on its own since the requested
mitigation was not confirmed applied in 11 of the 12 boots (the one boot that *did* read
`mask=1, duty=0` — genuinely backlight-off — still tripped, but n=1 is far below the ≥3/6 threshold
this decision needs).

**Root cause not chased further** (out of scope for this run, would cost additional board resets
not in the ~20-reboot budget): the `bodmit N` console command is dispatched and parsed correctly
(exact `strcmp` match in `console.cpp`, confirmed by reading the source), and `bod N` sent
immediately afterward in the same script invocation is reliably applied every time (all 12 boots
show the correct trip behavior at the requested arm level). The mismatch is specific to `bodmit`
persisting into the *next* boot's RTC_NOINIT read — worth its own instrumented follow-up (e.g. a
`bodmit` query sent immediately before `reboot`, in the same script invocation, to confirm the
write landed before the reset is issued) before spending more board time on this A/B.

## Not measured / anomalies

- X-P2b-1 stopped at level 7 per the ladder's standard descent rule; B_boot for the display-only
  rung is therefore `null` (undefined — no level tripped), not a number to compare against WiFi
  rungs' B_boot ≤ 2.
- The board was found armed at `bod` threshold 1 (not 7) when the monitor first came back up after
  `./run/flash-debug`, carried over from an earlier, unrelated session — not something this run's
  drivers left behind (rig_ladder's rungs never touch the full-firmware `bod` state; rig_sweep's own
  `finally` always restores `bod 7`). Restored by hand (stamped) before X-P2b-2 began.
- R=20 over the `--since 2h` window: this window includes the `flash-debug` reflash, the by-hand
  restore reboot, and 24 `rig_sweep` reboots (12 runs × 2 reboots each, matching the runbook's own
  ~20-reboot estimate) — not further decomposed into "which reboot re-enumerated" here.
- `dur=0` and the alternating `min=2`/`min=7` values in the raw trip lines track F-6's adaptive
  descent floor across boots, not a per-boot effect of the requested arm; they do not correlate with
  `bodmit` request or `bodmit_mask` in this data and were not used in the decision above.
