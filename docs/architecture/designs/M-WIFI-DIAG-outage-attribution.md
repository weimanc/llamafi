# M-WIFI-DIAG — WiFi outage attribution: instrument first, then isolate

> Owner: Architect · Status: **APPROVED 2026-07-02 (human)** — panel-reviewed (PM/QM/VE:
> approve-with-changes, dispositions applied in place, see §8); TASK-274/275 filed · 2026-07-02
> Trigger: TASK-238 (ADR-045 gate) blocked 7/10 by unattributed network outages; TASK-272/273 fixed the
> two firmware defects the gate surfaced, but the *residual* outages remain unexplained.
> Couples: TASK-238 (consumer of the verdict), TASK-272 (power-save fix), TASK-273 (skip pacing),
> `run/wr-gate` harness. Related lessons: LL-069 (sensor-blind gates), LL-082/LL-087 (minimal isolating
> control beats subtracting from the complex artifact), LL-091 (observe ground truth, don't infer it).

## 1. Context & problem statement

One evening of DUT work (2026-07-02) produced repeated transient network outages that the application
experiences as instant `connect(): errno 118 EHOSTUNREACH` + `DNS Failed` bursts lasting 10 s to >32 s.
TASK-272 (`WiFi.setSleep(false)`) and TASK-273 (auto-skip pacing) fixed the firmware's two *reactions* to
these outages; the outages themselves persist and now gate TASK-238 (gate run 4: all 3 failing trials were
outage-shaped; all 7 clean trials were flawless — 0 skips, instant connect, 60 s holds).

**The blind spot:** every observation so far is at the application layer. `CORE_DEBUG_LEVEL=1` suppresses
Arduino WiFi events, so we have never seen what the radio itself experienced — no disconnect events, no
reason codes, no reconnect timeline. RSSI in the heartbeat is sampled from a Spotify-poll context and reads
0 or a real value depending on build/path — untrustworthy. We are diagnosing a link-layer problem through a
socket-layer keyhole.

### Evidence inventory (all 2026-07-02, `cyd2usb_webradio` unless noted)

| # | Symptom | Key property |
|---|---|---|
| E1 | Boot-window drop ~35 s uptime, recovered by ~60 s | near-deterministic; heartbeat read `rssi(0)` during it — *caveat: that sensor is untrustworthy (§1 blind spot); treat as weak corroboration only* |
| E2 | First connect after ≥45–70 s network idle fails EHOSTUNREACH+DNS for 10–30 s | survived `setSleep(false)`; **reproduced twice, n=2** (gate trial 1: 11 skips, ttfp 20.4 s, both runs) |
| E3 | Mid-run outages (~26 s, >32 s) with back-to-back traffic | ~every 2–5 min; adjacent identical-cadence trials clean |
| E4 | Station fetch yields 0/3/4/13/16 stations across boots | separate cause: radio-browser mirror lottery × one-shot no-retry fetch |
| E5 | Same build clean all morning (EXP-012: ~40 min of surveys, zero errno 118) | single-day morning/evening contrast (n=1 day) |

### Hypotheses

- **H-A (environment):** AP inactivity kick (threshold apparently between 45 s and 60 s), evening 2.4 GHz
  congestion, mesh/band-steering. Supported by E5 and by host-side curl staying clean.
- **H-B (our firmware/stack):** something protocol-timed (DHCP renew, lwip state) or periodic in our build.
  Supported by E2's suspicious determinism — random RF does not reproduce ttfp to 0.1 s.
- **H-C (DUT hardware):** CYD's weak antenna + noisy 3.3 V rail (display + DAC + WiFi TX peaks).
  Weakened by E5 (clean mornings) and E2 (deterministic timing).

E4 is excluded from this design's scope: cause understood (mirror lottery × no fetch retry); its fix is an
app-level fetch-retry decision parked with PM (TASK-272 item 4).

## 2. Design principle

**Instrument before isolating.** Every isolation experiment run blind costs a DUT cycle and yields another
inference; the event logger converts each future outage into an attributed fact. So Phase 1 is firmware
instrumentation + one correlated gate run; Phases 2–4 are pre-planned but **sketch-only** until Phase 1
data picks among them (LL-089 scope discipline: design to the depth the next gate needs).

## 3. Phase 1 — instrumentation (implementation depth)

### 3.1 WiFi event logger (firmware, all builds)

Register one `WiFi.onEvent` handler at setup (before `WiFi.begin`), logging **every** Arduino WiFi event
with millis timestamp and, for disconnects, the reason code:

```
[wifi-ev] t=37161 ev=5 STA_DISCONNECTED reason=4        // 4 = INACTIVITY — would confirm H-A instantly
[wifi-ev] t=39004 ev=4 STA_CONNECTED
[wifi-ev] t=39400 ev=7 STA_GOT_IP ip=192.168.1.181
```

- Serial `printf` direct (not LOG_*) so it survives any log-level config; one line per event; grep-stable
  prefix `[wifi-ev]` (a **stable contract** — harnesses parse it). Each line is assembled in a local buffer
  and emitted with a single write: the handler runs on the WiFi event task, and interleaved `printf`s from
  two tasks tear lines (VE-8).
- **Flap guard** (QM, OQ1 condition): cap at ~10 event lines/min with a `suppressed=N` summary line — a
  pathological AP must not storm the serial log/monitor.
- Cost: a few hundred bytes flash, zero steady-state RAM. Ships in **all** builds (production included) —
  these events are rare, and production Spotify polling suffers the same outages (TASK-272 note).
- The disconnect **reason code** is the single most informative datum this whole effort lacks
  (inactivity=4, beacon-timeout=200, deauth=2/3, assoc-expired=1…).
- **Sensor positive control (QM-2, TASK-274 acceptance):** before any negative-evidence attribution is
  trusted, force a disconnect (`WiFi.disconnect()` via serial or AP off) and show the `[wifi-ev]` line
  fires with a reason code. Attribution-by-absence is only valid once the sensor is proven live (LL-091).

### 3.2 `get wifi` serial accessor (debug builds)

JSON one-liner the harness can poll at 1 Hz during trials:

```json
{"ok":true,"cmd":"get","var":"wifi","ms":123456,"status":3,"rssi":-52,"ip":"192.168.1.181","ch":6,
 "discCount":2,"lastDiscReason":4,"lastDiscMs":37161,"lastGotIpMs":39400,"last":true}
```

`discCount/lastDiscReason/lastDiscMs/lastGotIpMs` come from the 3.1 handler's counters (plain statics,
handler registered before `WiFi.begin`, shell-owned in `main.cpp` — OQ2 resolved). The harness attributes a
trial's failure window to a link event without parsing the async log. `ms` (current `millis()`) is the
**device→host clock anchor** (VE-2): the harness stamps host time at each poll and builds the linear map
that lines device event timestamps up with the ping log. `lastGotIpMs` bounds the outage *end* even when an
async event line is lost. Counters reset on every DTR reboot — the harness re-baselines after each
(fetch-retry can reboot up to 3×, VE-7). Replaces the untrustworthy heartbeat RSSI as the WiFi ground
truth; the heartbeat RSSI itself gets a fix-or-remove disposition inside TASK-274 (QM-5).

Spec is **VE-gated** (BP-024): VE signs off the field set before TASK-274 implementation is final.

### 3.3 Harness correlation (host-side + harness rework)

**Prerequisite harness redesign (VE-1, blocker):** the current `SerialDut.cmd()` calls
`reset_input_buffer()` before every command, which *discards* async `[wifi-ev]` lines at the 2 s poll
cadence — the correlation §3.3 needs is unimplementable on the current harness. TASK-275 therefore starts
with a `SerialDut` rework: one continuous reader loop tees **every** serial line to a host-timestamped
log file; `cmd()` consumes JSON replies from that stream instead of resetting the buffer. This is named
harness *development* work, not run execution (PM-3).

- `run/wr-gate` gains a parallel host `ping -D -i 1` of the DUT IP (`wr-gate-ping.log`, epoch timestamps).
  Ping mechanics (VE-6): re-read `get wifi` and restart ping when the DUT IP changes across DTR reboots;
  exclude reboot windows from classification; pre-flight one known-good ping to rule out AP client
  isolation; host must be on Ethernet/other band, not the same 2.4 GHz cell.
- **Upstream control (QM-3):** the host concurrently probes the same external endpoint the DUT is
  connecting to (curl loop, 10 s cadence). "No-link-evidence" attribution requires host-side external
  success in-window — otherwise the outage is WAN/upstream, a fifth class.
- Gate harness polls `get wifi` once per trial-poll tick, stamps `discCount` deltas + the millis anchor
  into the per-trial record.

### 3.4 Phase 1 exit gate (agent-executable, QM-1)

**Outage window definition:** starts at the first failed connect (or first lost ping, whichever earlier);
ends at the first successful connect (or `lastGotIpMs`, whichever later). Windows inside a DUT reboot are
excluded.

**Attribution classes (per window):**

| Class | Signal |
|---|---|
| link-down | `[wifi-ev]` disconnect (any reason) or `discCount` delta in-window — *includes fast-reassoc: if a disconnect event exists, the window is link-attributed regardless of how long connects keep failing afterwards; the fail-after-reassoc duration is recorded as a recovery metric, not a separate class* (VE-5) |
| IP-layer | ping dead ≥2 s, no disconnect event |
| WAN/upstream | DUT-side failures while host-side external probe also fails in-window |
| no-link-evidence | ping alive, host external probe fine, no event, DUT connects failing (formerly "firmware" — renamed because it is absence-of-evidence, VE-3; consequence: second-vantage check first, then targeted firmware capture) |
| unattributed | signals conflict or are incomplete — consequence: rerun with widened capture, do **not** guess (QM-1) |

**Run protocol & exit:** run in the previously-dirty evening window. Continue until **≥3 outage windows
are captured** or a hard cap of ~90 min on-air (VE/QM OQ3). The run is simultaneously scored against the
ADR-045 bar (PM-2): a clean run in the dirty window closes TASK-238 directly — do not extend it hunting
for outages; the production `[wifi-ev]` sensor keeps collecting passively from then on (PM OQ3).
**The attribution table is the deliverable**, not the pass rate. Mixed runs act per-category,
link-down first (VE-4).

## 4. Phases 2–4 — isolation (sketch only, gated on Phase 1)

| Phase | Experiment | Runs iff Phase 1 says… | Decides |
|---|---|---|---|
| 2 | **Hotspot A/B**: same gate, DUT on a phone hotspot — trials **interleaved AP↔hotspot in one session** (LL-090 same-session pairing, QM-7) | link-attributed outages | H-A vs H-B/C: clean on hotspot → AP confirmed; rerun TASK-238 gate on healthy AP and close |
| 3 | **Router-side check**: AP admin logs for the DUT MAC, DHCP lease length | link-attributed + reason ∈ {inactivity, deauth} | names the AP mechanism; possible zero-code fix (AP setting) |
| 4 | **Bare-rig control**: `~/proj/webradio-bare/` idle-60s→connect loop, same AP | firmware-attributed, or hotspot also dirty | H-B vs H-C: bare rig clean → our stack; bare rig dirty → hardware/AP interaction |

Deliberately not designed further (LL-089): no mechanism work on keepalives, reconnect strategies, or
retry-from-terminal until Phase 1 attributes the outages. Those are candidate *responses*, and designing
them now risks building for the wrong cause.

## 5. Decision matrix

Per-window classes roll up per-category; mixed runs act on every category present, link-down first (VE-4).

| Phase 1 attribution | Action |
|---|---|
| Link-down, reason=inactivity/deauth | H-A: Phase 2/3; fix at AP or add link keepalive (new task, design then) |
| Link-down, beacon timeout | H-A/H-C mix: Phase 2 then 4 (regardless of clustering — VE-4 gap ii) |
| Link-down, any other reason code | catch-all (VE-4 gap i): look the code up, then Phase 2/3 with that specific mechanism in hand |
| IP-layer only (ping dead, no disconnect event) | DHCP/router: Phase 3 (lease length), possible static-IP experiment |
| WAN/upstream (host external probe also failing) | environment beyond the LAN: rerun in a healthy window; nothing to fix here (QM-3) |
| No-link-evidence (ping + host probe alive through "outage") | second-vantage check (ping DUT from router/another host) first; only then H-B heap/lwip capture as a new focused task (VE-3) |
| Unattributed windows present | widen capture, rerun; no dispatch on guesses (QM-1) |
| No outages recur (in the dirty window) | score the run against ADR-045 and close TASK-238 (PM-2); production sensor keeps collecting passively |

## 6. Interfaces & tasks (proposed to PM; both under **M-WEBRADIO**, no new milestone — PM-4)

- **TASK-274** — Phase 1 firmware (Developer, ~1 session incl. run/check + DUT smoke): `[wifi-ev]` logger
  with flap guard (all builds) + `get wifi` accessor with millis anchor (debug). Acceptance includes the
  forced-disconnect sensor positive control (QM-2) and the heartbeat-RSSI fix-or-remove disposition (QM-5).
  Accessor field set VE-gated before final (BP-024).
- **TASK-275** — Phase 1 harness + run (VE): **(a)** SerialDut continuous-reader rework + ping/upstream
  probes + attribution scoring (development work, named explicitly — PM-3/VE-1); **(b)** the instrumented
  evening run per §3.4, dual-scored: attribution table AND ADR-045 pass rate (PM-2). Artefact disposition
  (BP-040): the firmware sensor ships permanently (it *is* the product fix for the blind spot); the ping
  harness stays in `run/wr-gate` behind a flag; no throwaway artefacts. QM retrospective triggers at
  TASK-275 close (QM-7).
- TASK-238 stays open pending §5's outcome; **the ADR-045 bar ruling is escalated to the human NOW, in
  parallel — it is a cheaper independent path to closing TASK-238 and must not serialize behind Phase 1**
  (PM-1).
- Parked candidates stay parked pending attribution (PM-5): fetch-retry (TASK-272 item 4),
  retry-from-terminal (TASK-273 follow-on).

## 7. Open questions — resolved by panel

- **OQ1 → production builds** (QM): debug-only recreates the exact blind spot this design closes, in the
  build where TASK-272 says Spotify polling suffers the same outages. Condition: flap guard + stable
  `[wifi-ev]` prefix contract (folded into §3.1).
- **OQ2 → shell-owned, `main.cpp`** (VE + Architect concur): an app-local accessor dies with the app on
  `suspend()` — exactly when inter-trial outages must remain observable. Counters are plain statics;
  handler registered before `WiFi.begin`.
- **OQ3 → merged rule** (PM/QM/VE): run in the known-dirty evening window; exit at ≥3 captured outage
  windows or ~90 min on-air; a clean dirty-window run is scored against ADR-045 and closes TASK-238 —
  never extended hunting for outages, because the shipped sensor collects passively forever after.

## 8. Panel dispositions (2026-07-02)

PM / QM / VE all returned **approve-with-changes**; every blocker/major is applied in place above:
VE-1 blocker (harness reset destroys async evidence) → §3.3 SerialDut rework; VE-2 (clock anchor) → §3.2
`ms`/`lastGotIpMs`; VE-3 + QM-3 ("firmware" bucket is absence-of-evidence; missing WAN class) → §3.4
five-class taxonomy + §5 rows; VE-4 (matrix gaps/mixed runs) → §5 catch-all + precedence; VE-5
(fast-reassoc ambiguity) → §3.4 pre-declared classification; QM-1 (gate not agent-executable) → §3.4
window definition + unattributed bucket + merged OQ3; QM-2 (sensor positive control) → §3.1 + TASK-274
acceptance; PM-1/2/3/4 → §6 (parallel bar escalation, dual-scored run, named harness work, M-WEBRADIO
accounting); QM-4/5 (evidence overclaims, rssi(0) caveat) → §1 table; VE-6/7/8 (ping mechanics, counter
reset, line tearing) → §3.2/3.3; QM-6 (BP-040/024) → §6; QM-7 (LL-090 pairing, retro trigger) → §4/§6.
QM-8 (duplicate LL-069 id in lessons_learned.md) is QM-file housekeeping, handled outside this doc.
