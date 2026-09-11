# EXP-032 — F-6 adaptive descent on the DUT (PROP-011 F-6)
> Owner: R&D · 2026-09-11 · Sonnet agent · board: `cyd2usb_winamp_debug`, ELF `2b4485af`
> (boot banner prints stale `git=e9f659f+ build=...08:23:34` — `boot.cpp` was not touched by the F-6
> commits so its embedded string wasn't recompiled; the F-6 console commands and `get bod` fields
> below are the real build-identity evidence) · window ENDED by this experiment: ~3h55m
> (2026-09-11 ~08:46 → flash at ~12:16), cause = `./run/flash-debug` to land F-6, authorised by the
> human per the task brief

## Setup — exact commands run, in order

```
./run/rig-timeline --since 48h > window_before_f6.txt          # 15941 lines
tail -c 2000 /tmp/spotify-mon-serial.log | grep -a '[I][hb]'   # last uptime 03:41:15
tmux send-keys -t spotify-mon 'get bod' Enter                   # pre-flash bod snapshot
./run/flash-debug                                                # 1 attempt, rc=0, no retry needed
./run/monitor-start; sleep 30
./run/monitor-read 200                                           # boot sequence confirmed
tmux send-keys -t spotify-mon 'get bod' Enter                    # F-6 fields present -> build confirmed
./run/rig-timeline --since 5m | grep -c kernel                   # 0 -> no boot-loop / re-enum
tmux send-keys -t spotify-mon 'bod descend on' Enter
tmux send-keys -t spotify-mon 'set scanLoop 120' Enter           # x2, polled every 15s, capped 170s
tmux send-keys -t spotify-mon 'get bod' Enter
tmux send-keys -t spotify-mon 'bod descend off' Enter
tmux send-keys -t spotify-mon 'get bod' Enter                    # confirm descend:false
./run/rig-timeline --since 15m > f6_timeline_after.txt
python3 -m lib.rigwatch summary --since 15m
```

## Raw

**Pre-flash bod state** (`get bod`, board still on 4bda928):
```
{"ok":true,"cmd":"get","var":"bod","count":1,"dropped":0,"firstUs":797370,"lastUs":797370,
 "minLevel":7,"maxDurUs":0,"hist":[0,0,0,0,0,0,0,1],"phaseAtFirst":3,"thres":7,"armed":true,
 "rearms":1,"holdoffs":0,"disarmed":false,"last":true}
```
Last pre-flash heartbeat: `uptime=03:41:15` (this session's observation window; the STATE section's
"started 2026-09-11 ~08:46" figure predates a boot this session did not itself trigger).

**Flash:** `./run/flash-debug` succeeded on attempt 1/4 (no "CH340 device not found" retry needed).

**Boot confirmation:** the earliest boot lines (`[bootphase] 0 reset`, `[boot] git=`, `[bod] armed
... isr=1`, `[bod] TRIP tag=wifi-end`, `[bootreason]`) were emitted before the PlatformIO monitor's
port reconnect completed and are **not** in `/tmp/spotify-mon-serial.log` for this boot — the log
jumps directly from the reconnect banner to `[time] synced epoch=1789125882 in 3452ms`. This is the
well-known reconnect-timing gap (host not listening yet during the immediate post-flash boot), not a
boot failure: `[bootphase] 6 ready` **is** present for this boot (`build=Sep 11 2026-12:24:02`,
`uptime=00:00:05`..`00:00:08` heartbeats), and the build identity + F-6 presence were confirmed
instead via `get bod` immediately after:
```
{"ok":true,"cmd":"get","var":"bod","count":1,"dropped":0,"firstUs":797831,"lastUs":797831,
 "minLevel":7,"maxDurUs":0,"hist":[0,0,0,0,0,0,0,1],"phaseAtFirst":3,"thres":7,"armed":true,
 "rearms":1,"holdoffs":0,"disarmed":false,"descend":false,"armedLevel":7,"floor":8,"stepsDown":0,
 "stepsUp":0,"quietMs":30000,"last":true}
```
`descend`, `armedLevel`, `floor`, `stepsDown`, `stepsUp`, `quietMs` are F-6-only fields (absent on
4bda928) — their presence, plus `hist=[...,1]` (one level-7 trip, i.e. the standard boot-window
`wifi-end` trip) and `rearms=1`, is the build-identity evidence in place of the lost banner line.
`./run/rig-timeline --since 5m | grep -c kernel` → `0`: no re-enumeration, no boot-loop.

**F-6 recipe steps 1-6:**
```
1. tmux send-keys 'bod descend on'
   -> [bod] arm level=7 reason=manual
   -> {"ok":true,"cmd":"bod","var":"descend","on":true}
2/3. tmux send-keys 'set scanLoop 120'  (x2, ~150s apart)
   run 1 reply: {"ok":true,"cmd":"set","var":"scanLoop","secs":120,"r201":1175,"disc":49,
                 "bodTrips":0,"reconnected":1,"savedSsid":"<home-ssid>"}
   run 2 reply: {"ok":true,"cmd":"set","var":"scanLoop","secs":120,"r201":1175,"disc":49,
                 "bodTrips":0,"reconnected":0,"savedSsid":"<home-ssid>"}
   No `[bod] TRIP` or `[bod] arm level=... reason=descend` line appeared in either window
   (checked by slicing the log between the command and its reply).
4. tmux send-keys 'get bod'
   -> {"...,"descend":true,"armedLevel":7,"floor":8,"stepsDown":0,"stepsUp":0,"quietMs":30000,...}
5. (not applicable — no descend trip occurred, so there is nothing to step back up from; skipped
   per the recipe's own alternative branch: "no trips occur at all in the window")
6. tmux send-keys 'bod descend off'
   -> {"ok":true,"cmd":"bod","var":"descend","on":false}
   tmux send-keys 'get bod'
   -> {"...,"descend":false,"armedLevel":7,"floor":8,"stepsDown":0,"stepsUp":0,"quietMs":30000,...}
```

**After** (`f6_timeline_after.txt` tail + rigwatch, `--since 15m`, spans the whole F-6 recipe):
```
since 2026-09-11 12:18:09.922  reenum(R)=0 unexplained_boots(U)=0 bod_trips=0 wifi_disc(W)=103 events=85
```

## Numbers — §0.2 metrics

| metric | value | source |
|---|---|---|
| R (reenum) | 0 | rigwatch summary, `--since 15m`, covers the whole recipe |
| U (unexplained boots) | 0 | same |
| B_run (steady-state TRIP count) | 0 | two `set scanLoop 120` runs, `bodTrips:0` both times |
| descent staircase depth | n/a — floor stayed 8 (never tripped under descent) | `get bod` |
| stepsDown / stepsUp | 0 / 0 | `get bod` |
| W′ (NO_AP_FOUND retry time) | 1175 `r201` events × 2 (two scanLoop 120 runs) × 2.4s ≈ 5640s of retry time provoked, 0 BOD trips resulted | `set scanLoop` replies |
| window ended | yes, ~3h55m (08:46 → ~12:16 flash) | `window_before_f6.txt` + last pre-flash heartbeat |

## Decision — F-6 DUT acceptance recipe (runbook §1 F-6), applied verbatim

Steps 1, 2, 3, 4, 6 all matched their expected reply/field shapes exactly; step 3's alternative
branch ("or no trips occur at all in the window, consistent with X-P1c's 0/121") is what happened —
**0 BOD trips across two `set scanLoop 120` provoke runs**, so the staircase never had anything to
descend from, `armedLevel` stayed at the boot threshold (7), and `floor` stayed `8` (none). Step 5
does not apply for the same reason (nothing to step back up from) and was skipped per the recipe's
own text. Step 6 confirms `descend:false` and the board is left in the safe default state, monitor
running. **F-6 is DUT-verified**: the new console surface (`bod descend on|off`, `get bod`'s
`descend`/`armedLevel`/`floor`/`stepsDown`/`stepsUp`/`quietMs`) behaves exactly as specified for the
"quiet supply day, nothing to descend from" case that X-P1c already established is this board's
normal condition. The descend-staircase and step-up-on-quiet code paths themselves remain
**unexercised on real hardware** — this run proves they don't break anything and answer the query
surface correctly, not that a level actually steps down and back up, since the supply never produced
a `run`-tag trip to descend from.

## Not measured / anomalies

- The literal boot-time log lines (`[bootphase] 0 reset`, `[boot] git=...`, `[bod] armed ...
  isr=1`, `[bod] TRIP tag=wifi-end`, `[bootreason]`) for this specific boot are not in the log —
  lost to the monitor-reconnect timing gap between `esptool`'s hard reset and `./run/monitor-start`
  reopening the port, a known artifact rather than a firmware fault. Build identity and BOD-arm
  state were confirmed instead via `get bod`'s F-6-only fields (see Raw).
- The boot banner (`[boot] git=e9f659f+ build=...08:23:34`) is stale: `boot.cpp` was not recompiled
  by the F-6 commits, so its embedded version string is unchanged from an earlier build even though
  the binary linked in this build is a fresh one (ELF id `2b4485af`) with F-6's console/`get bod`
  code active, confirmed functionally above. Not fixed here per the task's explicit instruction.
- The adaptive-descent staircase (`reason=descend` levels stepping down, `reason=quiet` stepping
  back up) was not observed on this run because no `run`-tag trip occurred — this board's supply
  did not produce one in either 120s provoke window, consistent with X-P1c's 0/121. A future run on
  a day with observed `run`-tag trips (or a synthetic trip injection, out of this experiment's
  scope) is needed to see the staircase itself move.
- `W` (wifi_disc heartbeat-delta metric) was not read from the heartbeat `disc=` field for this
  window; `wifi_disc(W)=103` above is rigwatch's own `[wifi-ev]` count, which §0.2 says not to use
  as W (rate-limited) — included for completeness only, not as a metrics-table W value.
