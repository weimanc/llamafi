# EXP-033 — F-6 staircase and windowed echo on the DUT (PROP-011 F-6, X-P4)
> Owner: R&D · 2026-09-11 · agent tier: Sonnet · board: `cyd2usb_winamp_debug` @ `4033090`/`9aec229`
> (build `Sep 11 2026-14:15:44`) · window ended: yes, ~1h39m (last heartbeat uptime 01:38:56 before
> the reflash; POWERON boot confirmed stable, 0 kernel re-enum in the first 2 min)

## Setup — exact commands run, in order

```
./run/rig-timeline --since 48h > window_before.txt   # last hb uptime=01:38:56
./run/flash-debug                                    # attempt 1/4, SUCCESS, no CH340 retry needed
./run/monitor-start
# waited for [bootphase] 6 ready / [bootreason] 1 POWERON
./run/rig-timeline --since 2m | grep -c kernel        # 0

tmux send-keys -t spotify-mon 'bod quiet 5000' Enter
tmux send-keys -t spotify-mon 'bod descend on' Enter
for i in 1..8: tmux send-keys -t spotify-mon 'set fault bod 7' Enter; sleep 1
tmux send-keys -t spotify-mon 'get bod' Enter
# waited 45s with no further faults
tmux send-keys -t spotify-mon 'get bod' Enter
tmux send-keys -t spotify-mon 'bod descend off' Enter
tmux send-keys -t spotify-mon 'bod quiet 30000' Enter

cd app/tools
RIGWATCH=1 python3 probe/rig_uart.py --cells echo --out /tmp/claude-1000/xf6/echo.jsonl
RIGWATCH=1 python3 -m lib.rigwatch summary --since 60m
```

## Raw — the lines counted

Boot confirmation:
```
[bootphase] 6 ready
[bootphase] 0 reset
[bootreason] 1 POWERON
[bootphase] 1 fs
[bootphase] 2 display
[bootphase] 3 wifi
[bootphase] 4 time
[bootphase] 5 services
[bootphase] 6 ready
```

F-6 descent staircase (`set fault bod 7` x8, `bod quiet 5000`, `bod descend on` first):
```
{"ok":true,"cmd":"bod","var":"quiet","ms":5000}
[bod] arm level=7 reason=manual
{"ok":true,"cmd":"bod","var":"descend","on":true}
{"ok":true,"cmd":"set","var":"fault","synthetic":"bod","level":7}
[bod] TRIP tag=run t=42493ms thres=7 trips=2 det=0 us=42398159 dur=1 min=7 ctx=c5
[bod] arm level=6 reason=descend
{"ok":true,"cmd":"set","var":"fault","synthetic":"bod","level":7}
[bod] TRIP tag=run t=43494ms thres=6 trips=3 det=0 us=43404119 dur=1 min=7 ctx=c5
[bod] arm level=5 reason=descend
{"ok":true,"cmd":"set","var":"fault","synthetic":"bod","level":7}
[bod] TRIP tag=run t=44494ms thres=5 trips=4 det=0 us=44407302 dur=1 min=7 ctx=c5
[bod] arm level=4 reason=descend
{"ok":true,"cmd":"set","var":"fault","synthetic":"bod","level":7}
[bod] TRIP tag=run t=45494ms thres=4 trips=5 det=0 us=45413001 dur=1 min=7 ctx=c5
[bod] arm level=3 reason=descend
{"ok":true,"cmd":"set","var":"fault","synthetic":"bod","level":7}
[bod] TRIP tag=run t=46494ms thres=3 trips=6 det=0 us=46418066 dur=1 min=7 ctx=c5
[bod] arm level=2 reason=descend
{"ok":true,"cmd":"set","var":"fault","synthetic":"bod","level":7}
[bod] TRIP tag=run t=47494ms thres=2 trips=7 det=0 us=47423139 dur=1 min=7 ctx=c5
[bod] arm level=1 reason=descend
{"ok":true,"cmd":"set","var":"fault","synthetic":"bod","level":7}
[bod] TRIP tag=run t=48494ms thres=1 trips=8 det=0 us=48427070 dur=1 min=7 ctx=c5
[bod] arm level=0 reason=descend
{"ok":true,"cmd":"set","var":"fault","synthetic":"bod","level":7}
[bod] TRIP tag=run t=49494ms thres=0 trips=9 det=0 us=49434567 dur=1 min=7 ctx=c5
{"ok":true,"cmd":"get","var":"bod","count":9,"dropped":0,"firstUs":796686,"lastUs":49434567,
 "minLevel":7,"maxDurUs":1,"hist":[0,0,0,0,0,0,0,9],"phaseAtFirst":195,"thres":0,"armed":true,
 "rearms":9,"holdoffs":0,"disarmed":false,"descend":true,"armedLevel":0,"floor":0,"stepsDown":7,
 "stepsUp":0,"quietMs":5000,"last":true}
```
(8th fault, at armed level 0, produced trip #9 but no further `reason=descend` line — level 0 has
no step below it, matching bodWatchRearm()'s `if (s_thres > 0)` guard.)

Quiet step-up staircase (waited 45s past the last trip, no further faults sent):
```
[bod] arm level=1 reason=quiet
[bod] arm level=2 reason=quiet
[bod] arm level=3 reason=quiet
[bod] arm level=4 reason=quiet
[bod] arm level=5 reason=quiet
[bod] arm level=6 reason=quiet
[bod] arm level=7 reason=quiet
{"ok":true,"cmd":"get","var":"bod","count":9,"dropped":0,"firstUs":796686,"lastUs":49434567,
 "minLevel":7,"maxDurUs":1,"hist":[0,0,0,0,0,0,0,9],"phaseAtFirst":195,"thres":7,"armed":true,
 "rearms":9,"holdoffs":0,"disarmed":false,"descend":true,"armedLevel":7,"floor":0,"stepsDown":7,
 "stepsUp":7,"quietMs":5000,"last":true}
```
Each `reason=quiet` line landed ~2.4s apart in wall-clock command time (quietMs=5000, but the
`get bod` at the top of the wait window and console traffic mean the timer's own 5000ms floor is
the correct read — the printed levels are what matters and they are monotone 1..7 with no skips).

Cleanup:
```
{"ok":true,"cmd":"bod","var":"descend","on":false}
{"ok":true,"cmd":"bod","var":"quiet","ms":30000}
```

Windowed echo (`--cells echo`, default `--window 8`):
```
{"sent": 2000, "echoed": 2000, "lost": 0, "mismatches": 0, "ok": true, "cell": "echo lines=2000 window=8"}

whole-run R (reenum, last hour): 0
```

R/U over the session:
```
since 2026-09-11 13:18:58.553  reenum(R)=0 unexplained_boots(U)=0 bod_trips=9 wifi_disc(W)=46 events=176
```

## Numbers

| metric | value |
|---|---|
| descent staircase levels (in order) | 7→6→5→4→3→2→1→0 |
| stepsDown | 7 |
| floor | 0 |
| armedLevel after descent | 0 |
| quiet step-up staircase levels (in order) | 1→2→3→4→5→6→7 |
| stepsUp | 7 |
| armedLevel after quiet | 7 (capped at boot threshold) |
| echo, window=8 | 2000/2000 echoed, 0 mismatches, 0 lost |
| R (reenum, session) | 0 |
| U (unexplained boots, session) | 0 |
| boot check | `[bootphase] 6 ready`, `[bootreason] 1 POWERON`, kernel re-enum count (2 min) = 0 |

## Decision — runbook rule applied, verbatim, with outcome

Runbook §1 F-6 acceptance step 3: "Either a `[bod] arm level=<n> reason=descend` staircase appears
(each line's level one lower than the last, down to some floor) or no trips occur at all in the
window." — **staircase appeared**, one line per fault, monotone 7→0, matches.

Step 4: "`armedLevel` should equal the last `reason=` line's level ... `floor` should equal the
lowest `thres=` on any `[bod] TRIP tag=run` line in the window ... or 8 if nothing tripped." —
`armedLevel=0` = last `reason=descend` level; `floor=0` = lowest thres that tripped. Matches.

Step 5: "wait `quietMs` ... past the last trip with no further provoke command running → expect a
`reason=quiet` line stepping back toward the boot threshold." — **7 step-up lines appeared**,
monotone 1→7, capped at the boot threshold (7), matches.

Both descent and step-up are now DUT-verified via synthetic faults. Runbook §0.4 F-6 row and
runbook §0.1-referenced X-P4 echo re-spec are updated accordingly (see commit).

## Not measured / anomalies

- This run used `set fault bod 7` (synthetic, `min=7` every time) rather than a real supply sag, so
  the staircase exercises bodWatchRearm()'s descent/step-up logic but not the ISR's own in-event
  ladder (still `dur=0`-shaped and inert on this dip per EXP-026 — unchanged, out of scope here).
- Quiet-step wall-clock spacing was not independently stopwatched; only the printed `[bod] arm
  ... reason=quiet` lines and their level order were checked, per the runbook's acceptance text.
- Echo cell tried only `--window 8` (default) — it hit target on the first attempt, so the
  runbook's `--window 4` fallback path was not exercised this session.
- `--cells burst,sink` were not re-run this session (out of scope — only the echo re-spec and the
  F-6 staircase were owed).
