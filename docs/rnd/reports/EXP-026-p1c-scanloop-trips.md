# EXP-026 — X-P1c: does the NO_AP_FOUND retry loop trip the brownout comparator? (PROP-011 X-P1c)

> Owner: R&D · 2026-09-11 · operator: Fable (the F-1 firmware needed a live-fix cycle first — §1)
> Board: CYD on host port 1-1, `cyd2usb_winamp_debug` at `e9f659f+` (build 08:23:34, storm-proof
> ISR; committed after the run as the fix commit that follows `e9f659f`). Console via the tmux
> monitor, rigwatch recording, stamps `X-P1c-begin/run/end`.
> **Window ended:** the 40 h 08 m window (R=0, 1 boot trip, disc 63) was ended deliberately at
> 08:07 for this reflash; captured to the session scratchpad before flashing (§0.1 rule 2).

## 1. Setup — what actually happened, in order

1. `run/flash-debug` with the F-1…F-5 build (`e9f659f`). **Boot loop**: CH340 re-enumerating every
   ~1.5 s (devnum climbing, one kernel `error`); the monitor died on the first drop. A 30 s direct
   capture across re-enumerations read `[bootreason] 6 TASK_WDT`, `task_wdt: loopTask (CPU 1)`,
   `CPU 0: wifi, CPU 1: IDLE1`, and `[bod] armed … regAfter=0x7bff0000 … intEna=1 isr=1` — the
   proven polled build had `regAfter=0x7bffc000`. Two deltas: the ISR re-enabled itself on a
   level-asserted latch (storm → loopTask starved → TWDT at 15 s), and `esp_brownout_disable()`
   had zeroed `PD_RF_ENA`/`CLOSE_FLASH_ENA`. Fixed (ISR self-disarms, `loop()` re-arms ≤ 1/200 ms
   once DET clears; HW bits restored from the pre-disable value); reflashed (needed 3 attempts —
   the port kept vanishing).
2. New build stable: 1 kernel event in the 20 s after flash (the flash's own), monitor survives,
   `[bod] armed … regAfter=0x7bffc000 … intEna=1 isr=1`, boot trip `tag=wifi-end … us=797017 dur=0
   min=7 ctx=03`, `get bod` → `count=1 rearms=1 holdoffs=0 disarmed=false`. `mark t1` → `[mark] t1
   us=100002523`. `set fault bod 3` → synthetic `[bod] TRIP … dur=1 min=3`, `hist[3]=1`.
3. First `set scanLoop 30`: `r201=276 reconnected=1`, SSID intact — but `get bod` read
   `disarmed:true`: the command blocks `loop()`, so the ISR was never re-armed after its first
   event. Fixed (poll/re-arm inside the wait loop, `bodTrips` and the real `discCount` delta in the
   JSON), reflashed.
4. **The pre-fix `scanLoop` (the agent's F-2 as committed, 08:26 run) wrote to NVS**:
   `WiFi.persistent(false)` is applied only at first WiFi init (`WiFiGeneric.cpp:694`), so the
   bogus `begin()` persisted. Consequence at the next boot: NVS stage failed, the board came up
   `wifi=DOWN`, the supervisor cycled candidates (`[wifi-sup] kick=1 … "<home-ssid>" cand=1/2`,
   `kick=2 … "<home-ssid>" cand=2/2`), and runs 1–3 below started with the board
   already in its own retry loop. The host could see the AP throughout (`nmcli`: ch 3, signal 80).
   Self-healed when the list stage connected with FLASH storage; after the run `get wifiCfg` reads
   the right SSID and a controlled `reboot` reaches `STA_GOT_IP` at 8.4 s (the NVS stage still
   burns its window first — one more boot should clear it).
5. X-P1c proper: `set scanLoop 60` × 3, then `set scanLoop 120`, `get bod` after each, 08:32–08:41.

## 2. Raw

```
{"ok":true,"cmd":"set","var":"scanLoop","secs":60,"r201":600,"disc":24,"bodTrips":0,"reconnected":0,"savedSsid":"<home-ssid>"}
{"ok":true,"cmd":"set","var":"scanLoop","secs":60,"r201":600,"disc":24,"bodTrips":0,"reconnected":0,"savedSsid":"<home-ssid>"}
{"ok":true,"cmd":"set","var":"scanLoop","secs":60,"r201":600,"disc":24,"bodTrips":0,"reconnected":0,"savedSsid":"<home-ssid>"}
{"ok":true,"cmd":"set","var":"scanLoop","secs":120,"r201":1175,"disc":49,"bodTrips":0,"reconnected":1,"savedSsid":"<home-ssid>"}
get bod after run 4: {"count":1,"dropped":0,"minLevel":7,"maxDurUs":0,"hist":[0,0,0,0,0,0,0,1],"thres":7,"armed":true,"rearms":1,"holdoffs":0,"disarmed":false}
reason=201 lines logged per run (rate-limited): 20, 13, 16, 21
heartbeat after: wifi=rssi(-64) disc=176 uptime=00:09:00
```

Plus the natural experiment before run 1: the board sat in its own NO_AP_FOUND loop from boot
(`disc=54` at 2 min 20 s, `disc=97` at 4 min 07 s) with `get bod count=1` throughout.

## 3. Numbers

| metric | value |
|---|---|
| scan-loop time provoked | 300 s (+ ~4 min natural, §1.4) |
| retry events (`discCount` delta) | 24 + 24 + 24 + 49 = **121** (+ ~96 natural) |
| W′ (`r201` × 0.1 s) | 60 + 60 + 60 + 117.5 s |
| **B_run** (trips at level 7) | **0 / 121** (and 0 in the natural loop) |
| boot-window trip | 1 per boot, every boot, `dur=0 min=7` |
| R during the experiment | 0 after the flash reflashes settled |
| U | 0 (every boot stamped: flash, monitor-start, `reboot` via console) |

## 4. Decision

Runbook rule: *trips/retry ≥ 0.2 → AP-absent scanning is the driver; trips ≈ 0 → P1(c) of
09-09 was something else; escalate, do not guess.* **Result: 0/121 → escalate.**

PROP-011 §8's inference — "99/117 steady-state trips sit inside `reason=201` runs, therefore the
retry loop is the driver" — was **correlation**. Provoking the identical loop today, on the same
board, cable and port, with the AP absent for 300 s, produced no level-7 trip. The 09-09 boot's
co-factor is **unidentified**. Candidates, none tested: (a) a genuinely deeper/longer sag that day
(the depth is known to move day to day — 09-02's `BROWNOUT` at level 0 in the morning, no trip
below level 1 by evening); (b) something else the firmware did during that outage — TLS retries
with `Host is unreachable` were interleaved in that log; (c) an instrument difference: the polled
build read the RAW latch, which catches any crossing; the ISR path clears a pending RAW when it
re-arms, and stays disarmed through `setup()` after the boot trip — but the boot trip *is* caught
every boot, so a retry dip of the same shape would be too. (c) is checkable by flashing the polled
build during a natural outage; (a) and (b) need the depth ladder to work, which it does not yet:

**Instrument finding.** Every captured event has `dur=0 min=7`: `BROWN_OUT_DET` is already clear
by the time the ISR runs, so the bounded spin and the in-event depth ladder measure nothing — the
dip is shorter than interrupt latency (or the RAW latch fires on a sub-µs crossing). The
`BOD_LADDER_SETTLE_US` question is moot for this dip shape. Depth therefore still comes from the
reboot-per-level sweep (`bod N` → `reboot`), or from an **adaptive descent across events**
(re-arm one level lower after each trip; the floor is where trips stop) — the latter works for
steady-state events and is the F-1 follow-up.

## 5. Not measured / anomalies

- Depth of anything (ladder inert, see above). The 09-09 trips' depth is unknown too — they were
  presence/absence at level 7.
- Whether the polled build sees trips today (the A/B in (c)); no natural outage was available once
  the NVS state self-healed, and `scanLoop` does not exist on the old build.
- `reconnected:0` on runs 1–3 is the NVS-state accident of §1.4, not a `scanLoop` defect: the
  driver's saved config at the time was the supervisor's candidate 1, which does not exist here.
- `run/check` ran cold at 110–118 s against the 90 s budget on every pass today; pre-existing.
