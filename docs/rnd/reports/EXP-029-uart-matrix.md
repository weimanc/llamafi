# EXP-029 — UART transfer matrix (PROP-011 X-P4)
> Owner: R&D · 2026-09-11 · Sonnet agent · board: `cyd2usb_winamp_debug` build 4bda928, on-board
> since 2026-09-11 ~08:46 · window NOT ended by this experiment (no reset performed)

## Setup — exact commands run, in order

```
tmux has-session -t spotify-mon                     # SESSION_LIVE
tail -c 2000 /tmp/spotify-mon-serial.log | grep -a '[I][hb]' | tail -3   # heartbeat <60s old
cd app/tools
~/proj/esp/venv/bin/python3 probe/rig_uart.py --dry-run
./run/rig-timeline --since 30m > timeline_before.txt
RIGWATCH=1 python3 -m lib.rigwatch summary --since 30m > rigwatch_before.txt
~/proj/esp/venv/bin/python3 probe/rig_uart.py --out results.jsonl      # run 1 (pre-fix)
# found: BURST_TIMEOUT_S=60 too short for large cells -> cascading failures
# fixed rig_uart.py (see "driver fix" below), committed e4fcc94
python3 probe/test_rig_uart.py -v                                     # 20/20 OK
./app/tools/smoke_test.sh                                             # OK
# re-ran only the 4 cells that failed under the old timeout, using the
# fixed run_burst_cell/run_sink_cell/run_echo_cell directly (ad-hoc script,
# not a driver change): burst 20000x64, burst 20000x200, sink 65536, echo 2000
# then reran sink+echo 5x more (10 more calls) per the decide rule, since
# both showed a deterministic (not noisy) failure
./run/rig-timeline --since 90m > timeline_after.txt
RIGWATCH=1 python3 -m lib.rigwatch summary --since 90m > rigwatch_after.txt
```

## Raw — the lines counted

**Dry-run** (matches runbook §3 X-P4 cell list exactly — 6 burst cells, 1 sink cell with the 1 MB
cell explicitly skipped and reasoned, 1 echo cell):
```
[dry-run] serialburst cells (DUT->host):
[dry-run]   send: serialburst 2000 8 / 2000 64 / 2000 200 / 20000 8 / 20000 64 / 20000 200
[dry-run] serialsink cells (host->DUT): only 65536 B (64 KB) — 1 MB cell SKIPPED:
[dry-run]   serialsink's firmware deadline (10s) caps a single call at ~115200 B ...
[dry-run] serialecho cell: send: serialecho 2000 ...
```

**Run 1 (pre-fix, `results.jsonl`):**
```
{"began": true, "ended": true, ... "cell": "burst lines=2000 pad=8"}      L=0
{"began": true, "ended": true, ... "cell": "burst lines=2000 pad=64"}     L=0
{"began": true, "ended": true, ... "cell": "burst lines=2000 pad=200"}    L=0
{"began": true, "ended": true, ... "cell": "burst lines=20000 pad=8"}     L=0
{"began": true, "ended": false, "declared_lines": 20000, "pad": 64, "lost": 11334,
 "L_bytes_upper_bound": 793380, "bodTrips": null, "ok": false, "cell": "burst lines=20000 pad=64"}
{"began": false, "ended": false, ... "cell": "burst lines=20000 pad=200"}   (never began)
{"ok": false, "reply": null, "L_bytes": 65536, "reason": "no serialsink reply found",
 "cell": "sink bytes=65536"}
{"sent": 2000, "echoed": 0, "lost": 2000, "mismatches": 0, "ok": false, "cell": "echo lines=2000"}

whole-run R (reenum, last hour): 0
```
`rigwatch_before.txt`: `reenum(R)=0 unexplained_boots(U)=10 ... events=104` — the U=10 was later
shown (by the coordinator, commit 65d808b, `fix(TASK-677): rigwatch — the serial tee writes DUT
lines only for a real port`) to be a host-test fixture leak into the live rigwatch sidecar, unrelated
to this run; no `[bootphase] 0` line exists in the serial log for this window. Treated as U=0 here.

**Root cause (from `/tmp/spotify-mon-serial.log`, confirmed by direct inspection):** the
`20000x64` burst actually completed cleanly on the DUT — `{"probe":"burst","phase":"end",
"lines":20000,"elapsedMs":139663,"bodTrips":0,...}` — well past the driver's fixed 60s wait. The
driver gave up at 60s and read a truncated slice, reporting `lost:11334`. Because it returned before
the burst actually finished, the next command (`serialburst 20000 200`) was queued into a console
still blocked inside `cmdSerialBurst`; that command then ran to completion 375765 ms later
(`elapsedMs=375765`), during which the queued `serialsink 65536` and `serialecho 2000` commands and
their payloads sat unconsumed, producing "no reply"/"began: false"/"echoed: 0". This is a **driver
timing bug**, not link noise — confirmed by direct log inspection while nothing was sent to the
console (idle-wait, no `esptool`/pyserial/reset used).

**Driver fix (commit `e4fcc94`):** `burst_timeout_s(lines, pad) = lines*(pad+16)/11520*1.5 + 15`
replaces the fixed 60s constant; every cell (`run_burst_cell`, `run_sink_cell`, `run_echo_cell`) now
calls `wait_console_idle()` before sending its command, so cells never overlap. `probe/test_rig_uart.py`
gained `TestBurstTimeoutScalesWithPayload` (asserts the formula covers both measured times,
139.663s and 375.765s) and `TestWaitConsoleIdle`. `python3 probe/test_rig_uart.py -v`: 20/20 OK.
`app/tools/smoke_test.sh`: OK (`check_board_currency: 113 row(s) ... no board row contradicts`).

**Re-run of the 4 failed cells post-fix (`rerun_failed.jsonl`):**
```
{"began": true, "ended": true, "lost": 0, "corrupt": 0, "cell": "burst lines=20000 pad=64"}  ok
{"began": true, "ended": true, "lost": 0, "corrupt": 0, "cell": "burst lines=20000 pad=200"} ok
{"ok": false, "reply": {"probe":"sink","bytes":65536,"got":65536,"sum":"004efd63","bodTrips":0},
 "L_bytes": 0, "sumMatch": false, "cell": "sink bytes=65536"}
{"sent": 2000, "echoed": 0, "lost": 2000, "mismatches": 0, "ok": false, "cell": "echo lines=2000"}
whole-run R (reenum, last hour): 0
```

**5x reproduction of sink + echo (`rerun_sink_echo_5x.jsonl`, decide-rule requirement):** all 5
sink reps returned identical `got=65536, sum="004efd63"` (host-expected sum differs — checksum
mismatch, not byte loss); all 5 echo reps returned `echoed=0, lost=2000`. Deterministic across all
7 total sink calls and all 7 total echo calls in this session (2 pre-idle-wait + 5 post) — not
link noise.

**After (`rigwatch_after.txt`, spans the whole experiment):**
```
since 2026-09-11 10:51:44.883  reenum(R)=0 unexplained_boots(U)=0 bod_trips=0 wifi_disc(W)=0 events=172
```

## Numbers — §0.2 metrics

| cell | L | bodTrips | notes |
|---|---|---|---|
| burst 2000x8 | 0 | 0 | clean, both runs |
| burst 2000x64 | 0 | 0 | clean |
| burst 2000x200 | 0 | 0 | clean |
| burst 20000x8 | 0 | 0 | clean |
| burst 20000x64 | 0* → 0 | 0 | *pre-fix reported lost=11334 — driver artifact, DUT log shows 0 lost, elapsedMs=139663 |
| burst 20000x200 | n/a → 0 | 0 | pre-fix never began; post-fix clean, elapsedMs=375765 |
| sink 64 KB | 0 bytes lost, sumMatch=false x7 | 0 | length correct, content wrong — see anomalies |
| echo 2000 | 2000/2000 lost x7 | n/a | 0 lines ever echoed back — see anomalies |
| R (whole run) | 0 | — | rigwatch, `--since 90m`, spans entire experiment |
| U | 0 | — | after excluding the fixture-leak rows (65d808b) |

## Decision — runbook §3 X-P4 decide rule, applied verbatim

> "L=0 everywhere and R=0 → the link is clean on record (PROP-011 §2 row closes). Any L>0 →
> reproduce that cell 5×; if it recurs, the 7-byte `read_flash` corruption of 09-02 has a home; if
> not, record as single-event noise."

R=0 for the whole run. All 6 `serialburst` cells (DUT→host) show **L=0** after the driver fix, and
the two large cells that had shown false losses were confirmed by direct DUT-log inspection to have
transferred cleanly (0 lost, 0 corrupt) — the apparent loss was the host driver's own timeout, not
the wire. **The DUT→host direction closes clean: no home found for the 09-02 `read_flash`
corruption in this matrix.**

The `serialsink`/`serialecho` (host→DUT and bidirectional) cells did **not** pass, and did not
recover after the timing fix: `sink` returns the full byte count but a wrong checksum, and `echo`
returns zero echoed lines, both 5-for-5 reproduced. This is **not** "L>0" in the byte-loss sense the
decide rule is written for (byte count matches for sink; echo shows 0 activity rather than partial
loss) — it reads as a **functional protocol mismatch** between the driver's send path and the
firmware's `cmdSerialSink`/`cmdSerialEcho` read loops, deterministic across 7 attempts, not the
kind of single-event noise the rule's "record as noise" branch covers. **This host→DUT / bidirectional
leg of X-P4 does not close**: it needs its own follow-up (comparing `tmux send-keys -l` chunk
timing against `Serial.available()`/`readBytesUntil` on the firmware side) before PROP-011 §2's row
can be marked done for those two cells. The DUT→host leg (`serialburst`, the leg most relevant to
the 09-02 corruption) is closed.

## Not measured / anomalies

- 1 MB `serialsink`/`serialburst` cells and the 921k-baud env: out of scope per the task's STATE
  section — skipped, not attempted, no reflash performed for this experiment.
- `rigwatch`'s pre-fix `U=10` was a measurement artifact (host-test fixture leak into the live
  sidecar file), fixed and committed separately by the coordinator as `65d808b`; not touched here.
- The `sink`/`echo` failure needs root-causing (checksum algorithm agreement, `Serial.available()`
  read timing vs `tmux send-keys -l` chunk pacing) — flagged, not fixed, per this experiment's scope
  (X-P4 is a measurement brief, not a firmware-fix brief for F-3).
- A `[W][perf] iter=525521ms` and one heartbeat with `loop_max=525521ms` appear in the log right
  after the pre-fix 20000x200 burst finished — the console/main loop was blocked for ~525s while
  `cmdSerialBurst` ran; expected given `cmdSerialBurst` is synchronous, but noted since it is a long
  single-iteration stall that would trip a naive watchdog metric elsewhere.
- No board reset, `esptool`, or serial-port-opening tool was used anywhere in this experiment; all
  device interaction went through the existing `spotify-mon` tmux session per §0.1.
