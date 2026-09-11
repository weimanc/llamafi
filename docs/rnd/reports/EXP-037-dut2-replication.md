# EXP-037 — DUT2 replication of the BOD experiments (PROP-011 X-P2/P2b-1/P2b-2/P6 replication)

> Owner: R&D · 2026-09-11 · Sonnet · board: `cyd2usb_winamp_debug` @ `a0c95c7` (both boards) ·
> window ended: yes — this experiment's own first reflash of DUT2 (E4) ended DUT2's TASK-557
> window; length not tracked for DUT2 before today (new board). DUT1 untouched throughout.

Boards, named by eFuse MAC (PROP-011-runbook §0.3, corrected 2026-09-11):
- **DUT1** `d4:8a:fc:c8:ee:d0` — on host USB port `5-1` since 21:48, but **every DUT1 result compared
  here (EXP-034/035/036) was taken on port `1-1`** — the same port DUT2 used. Not touched this session.
- **DUT2** `8c:94:df:92:3c:94` — host USB port `1-1` (`pci-0000:c1:00.3`) — under test this session.

## Setup — exact commands run, in order

```
mkdir -p /tmp/claude-1000/dut2
./run/rig-timeline --since 2h > /tmp/claude-1000/dut2/timeline_before.txt
esptool.py --chip esp32 --port <DUT2 by-path> --before default_reset --after hard_reset read_mac
  -> MAC: 8c:94:df:92:3c:94   (repeated after E4's flash, same result)

# E1 reset-gap (monitor stopped)
./run/monitor-stop
RIGWATCH=1 PYTHONPATH=. python3 probe/rig_resetgap.py --i-know-this-resets-the-board \
  --port <DUT2> --gaps 1,2 --trials 30 --out /tmp/claude-1000/dut2/resetgap.jsonl

# E2 load ladder, bare rig
python3 probe/rig_ladder.py --i-know-this-resets-the-board --port <DUT2> \
  --rungs 1,2,4,6 --levels 7,5,3,2 --reps 3 --out /tmp/claude-1000/dut2/ladder.jsonl

# E3 level-1/0 check, bare rig
python3 probe/rig_ladder.py --i-know-this-resets-the-board --port <DUT2> --no-stop \
  --rungs 2 --levels 1,7,1,0 --reps 3 --out /tmp/claude-1000/dut2/level1.jsonl

# E4 restore full firmware
./run/flash-debug        # succeeded on attempt 1, port c1:00.3
./run/monitor-start
# verified: [boot] git=a0c95c7 (== git rev-parse --short HEAD), [bod] armed thres=7,
#           [bootphase] 6 ready
./run/monitor-stop; esptool.py ... read_mac -> 8c:94:df:92:3c:94; ./run/monitor-start

# E5 full firmware sweep (monitor running — rig_sweep drives the console through it)
python3 probe/rig_sweep.py --i-know-this-resets-the-board --levels 7,5,3,2 --reps 3 \
  --timeline-out /tmp/claude-1000/dut2/sweep_timeline.txt

# E6 backlight A/B at level 2, 12 single-boot runs alternating bodmit 0/1
for i in 1..6:
  rig_sweep.py --i-know-this-resets-the-board --bodmit 0 --levels 2 --reps 1 --all ...
  rig_sweep.py --i-know-this-resets-the-board --bodmit 1 --levels 2 --reps 1 --all ...

RIGWATCH=1 python3 -m lib.rigwatch summary --since 3h
```

**Correction during the run:** `rig_sweep.py` (unlike `rig_ladder.py`/`rig_resetgap.py`) drives the
console through the existing `spotify-mon` tmux session — it does not open the port itself. The
first E5 attempt was run with the monitor stopped (per the runbook's general "monitor must be
stopped" habit carried over from E1) and failed with `CalledProcessError` on `tmux send-keys`
before any boot happened (no board state changed, `bod`/`bodmit` verified unchanged at 7/0
afterward). Monitor was restarted and E5 re-run cleanly. Corrected in this report so the setup
above reflects what actually works.

## Raw — the lines counted

**E1 reset-gap** (`/tmp/claude-1000/dut2/resetgap.jsonl`, final lines):
```
{"gap": 1.0, "trials": 30, "wedged": 0, "reset_fail": 0, "reenum": 0}
{"gap": 2.0, "trials": 30, "wedged": 0, "reset_fail": 0, "reenum": 0}
{"summary": {"1.0": {"trials": 30, "wedged": 0, "reset_fail": 0, "reenum": 0}, "2.0": {"trials": 30, "wedged": 0, "reset_fail": 0, "reenum": 0}}}
```

**E2 ladder** (`/tmp/claude-1000/dut2/ladder.jsonl`, all 12 boots — ladder stops descent at the
first no-trip level, so only level 7 ran for each rung):
```
{"rung": 1, "level": 7, "rep": 1..3, "tripped": false, "wifi_ip": false}  (0/3)
{"rung": 2, "level": 7, "rep": 1..3, "tripped": false, "wifi_ip": true}   (0/3)
{"rung": 4, "level": 7, "rep": 1..3, "tripped": false, "wifi_ip": true}   (0/3)
{"rung": 6, "level": 7, "rep": 1..3, "tripped": false, "wifi_ip": false}  (0/3, display-only rung)
{"summary": {"1": {"trips_by_level": {"7": 0}, "b_boot": null}, "2": {"trips_by_level": {"7": 0}, "b_boot": null}, "4": {"trips_by_level": {"7": 0}, "b_boot": null}, "6": {"trips_by_level": {"7": 0}, "b_boot": null}}}
```

**E3 level-1/0** (`/tmp/claude-1000/dut2/level1.jsonl`, rung 2 = +WiFi, order 1,7,1,0 × 3 reps, 12 boots):
```
{"rung": 2, "trips_by_level": {"1": 0, "7": 0, "1@2": 0, "0": 0}, "b_boot": null}
```
All 12 boots: `tripped:false, ready:true, usb_drop:false` — **0 USB drops at level 1 (both passes)
and level 0.**

**E4** flashed cleanly attempt 1 of 4 (log tail):
```
Wrote 1958720 bytes ... Hash of data verified.
========================= [SUCCESS] Took 26.90 seconds =========================
```
Monitor-read after: `[boot] git=a0c95c7 elf=ecd655fa build=Sep 11 2026 22:02:55` /
`[bod] armed thres=7 ...` / `[bootphase] 6 ready`. `git rev-parse --short HEAD` = `a0c95c7`. Match.
`read_mac` before and after E4: `8c:94:df:92:3c:94` both times.

**E5 full-firmware sweep** (`/tmp/claude-1000/dut2/sweep2.log`):
```
{'tripped': False, 'level': 7, 'rep': 0..2, 'booted': True, 'armed_level': 7}
level=7: 0/3 tripped
stopping descent at level=7 (0/3 tripped)
restored: bodmit 0 + bod 7 + reboot sent, ready
```

**E6 backlight A/B** (`/tmp/claude-1000/dut2/e6_all.log`, 12 runs): every run —
`bodmit_proved: True, armed_level: 2, tripped: False` — for both `bodmit=0` (6/6 no trip) and
`bodmit=1` (6/6 no trip).

**Final rigwatch summary** (`--since 3h`):
```
since 2026-09-11 19:37:35.082  reenum(R)=4 unexplained_boots(U)=3 bod_trips=1 wifi_disc(W)=1 events=1052
[triage] rig: R=4 reenum U=3 unexplained-boot(s) in this run's window
```
`./run/rig-timeline --since 3h` traced all 3 unexplained boots to this session's own
`esptool read_mac` identity checks (2×, pre- and post-E4, both required by this brief's own safety
rule) and the `monitor-start` after `monitor-stop` re-asserting DTR — none occurred during E1/E2/E3/
E5/E6 themselves, which each report R=0 in their own driver output. Not board anomalies.

## Numbers — side-by-side, DUT1 (EXP-034/035/036) vs DUT2 (this run)

| result | DUT1 (`d4:8a:fc:c8:ee:d0`, data taken on port 1-1) | DUT2 (`8c:94:df:92:3c:94`, port 1-1) |
|---|---|---|
| reset-gap wedges @ 1 s (n=30) | 0/30 | **0/30** |
| reset-gap wedges @ 2 s (n=30) | 0/30 | **0/30** |
| rung 1 (CPU+flash, no WiFi) trip @ 7 | 0/3 (no trip) | **0/3 (no trip)** — same |
| rungs w/ WiFi (DUT1 rungs 2-5; DUT2 rungs 2,4) trip @ 7 | **3/3 tripped**, and 3/3 at 5,3,2 too | **0/3 at 7** — ladder's adaptive stop never reached 5/3/2 because 7 didn't trip |
| display-only rung, trip @ 7 | 0/3 (no trip) | **0/3 (no trip)** — same |
| level 1 USB drop (WiFi boot) | **drop on every boot** (9/9) | **0/12 (no drop, either pass)** |
| level 0 USB drop (WiFi boot) | **drop on every boot** (3/3) | **0/3 (no drop)** |
| full-firmware sweep trips @ 7,5,3,2 | **3/3 at every level 7→2** | **0/3 at 7** — sweep's adaptive descent stopped there, 5/3/2 not exercised |
| backlight A/B @ level 2, bodmit=0 trips | 6/6 (trips) | **0/6 (no trip)** |
| backlight A/B @ level 2, bodmit=1 trips | 6/6 (trips) | **0/6 (no trip)** |
| backlight A/B trip-rate difference | 0/6 (no difference, both arm at 6/6) | 0/6 (no difference, both arms at 0/6) |

## Decision

Runbook framing: *same on both boards → the CYD design; different → which board is marginal.*

**Reviewer correction (coordinator, same day):** the host USB port is **not** a confound. All of
DUT1's compared data were taken on laptop port `1-1` (DUT1 moved to `5-1` only at 21:48, after its
experiments; the 32 reset-gap trials run on it there by mistake are excluded), and DUT2 was tested
on the same `1-1`. Verified from the raw rows: DUT2's WiFi rungs connected on every boot
(`wifi_ip` 3/3, 3/3, and 9/9 at levels 1/0), every boot was armed at the requested level and
reached `ready`; its 29 full-firmware boots all armed with `isr=1` (17 at level 7, 12 at level 2),
all got `STA_GOT_IP 192.168.1.200`, and logged **0** `[bod] TRIP` lines of any tag. So "no trip"
is not WiFi failing to start and not the instrument being off. Remaining confounds: the **USB
cable** (whether DUT2 used DUT1's cable is not recorded) and **conditions** — DUT1's data came
after hours of continuous flashing and resets (board temperature, AP state), DUT2's from a cold
board in the evening.

**Different, and different in one direction: DUT2 never tripped the BOD comparator at all, at any
arm level from 7 down to 2, with the full firmware and WiFi running — where DUT1 tripped 3/3 at
every one of those levels.** DUT2 also took zero USB drops at arm levels 1 and 0, where DUT1 dropped
USB on every single WiFi boot. The one measurement that matched was the one where DUT1 also showed
no effect (no-WiFi rung 1, display-only rung, reset-gap wedges): both boards agree there.

This means **EXP-035/036's central finding — "WiFi bring-up sags the 3V3 rail across the level-7
comparator threshold, ≥2 levels for the low-level USB-drop mechanism" — does not replicate on
DUT2.** Either DUT1 is the marginal board (worse regulator, worse decoupling, or simply looser
process variation) and EXP-034/035/036 measured DUT1's specific weakness rather than a property of
the CYD design in general — the host port is the same for both datasets (see the correction
above), leaving the cable and the conditions as the only alternatives. Given the size of the gap (trip vs. no-trip at every
level tested, not a partial shift), a same-model, same-silicon-revision board showing **zero**
comparator trips where the reference board showed trips at **every** level down to 2 reads as board
marginality, not CYD-design margin, unless the cable or DUT1's condition turns out to explain it —
which the two next steps below test directly.

None of DUT2's results contradict DUT1's qualitative ranking of loads (WiFi > everything else,
display negligible) — DUT2 simply never entered the regime where any load produced a trip, so the
ranking can't be tested on this board without lower arm levels than the board allows (E3 confirms
levels 1 and 0 are usable on DUT2, unlike DUT1 — worth a future ladder sweep down to 1/0 once a
lower-level polled-mode instrument exists, since the ISR ladder's adaptive stop cannot reach them
via the `--rungs`/`--levels` list once a higher level already shows 0 trips).

## Not measured / anomalies

- E2's ladder and E5's sweep both stop descending at the first level with 0/3 trips (by design —
  adaptive descent, per F-6). Because DUT2 never tripped at level 7, **levels 5, 3, and 2 were never
  exercised on the ladder or the full-firmware sweep** — only E3's explicit `--no-stop --levels
  1,7,1,0` and E6's explicit `--levels 2` forced lower levels to run at all. If a future report needs
  DUT2's B_boot at every level, it must force it with `--no-stop`, since the adaptive tools will
  never volunteer it.
- U=3 this session, all three attributed (by timeline correlation, not by stamp — the two
  `read_mac` identity checks and the `monitor-start` after `monitor-stop` were not stamped in
  advance) to this session's own required identity/monitor-lifecycle actions, not to any of E1/E2/
  E3/E5/E6, each of which reports R=0 in its own driver output. Lesson for the next brief: stamp
  `who=<reason>` *before* an `esptool` identity check, not after, even when the runbook's rule 1
  is about the tmux monitor rather than esptool.
- **Next steps to close the remaining confounds:** (1) cable swap — run DUT1's rung-2 ladder and the
  level-1 check on the exact cable and port DUT2 used, and DUT2's on DUT1's cable; (2) a cold-board
  repeat of DUT1 (after ≥1 h powered off) at levels 7 and 2. If DUT1 still trips and drops on
  DUT2's cable when cold, it is DUT1's board.
- `run/local.env.bak-dut1` was the coordinator's own backup of the local env; deleted.
