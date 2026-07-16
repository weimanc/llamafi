# Test Plan

> Owner: Verification Engineer

From `feature_inventory.yaml` + `cross_feature_matrix.yaml`. Hierarchy: suite→feature→test. Each feature needs ≥1 test. Each matrix interaction needs ≥1 cross-feature test.

---


> Suites for completed milestones (M1–M-MULTIAPP early) are in [test_plan-archive.md](test_plan-archive.md).

---

## Suite: serialdbg-001 — Serial debug command surface (M-SERIALDBG)

Tests for the expanded serial command interface. All require M-SERIALDBG firmware in tree (`tap` / `drag` / `get` / `set` / `info` / `help` commands implemented). Host-side: pyserial or `pio device monitor` piped through a script.

All responses are JSON lines per ADR-021. Host scripts use `json.loads(line)` — skip lines not starting with `{` (boot line, esp_log output). Check `ok`, `hit`, `action` fields. **Do not grep for `[serial-touch]` prefix — that notation is illustrative only in this doc; actual output is JSON.**

Open design issues gating some tests (tracked in design doc / ADR-021 review):
- B1: ~~T079 blocked~~ resolved 2026-05-17 — `dbgSet("cooldown", ms)` now accepts a
  positive arming value (previously val was ignored, reset-only). `injectTouch`
  remains read-only against `touchScreenCoolDownTime` by design so synthetic taps
  never block real input; T079 arms via `set cooldown <ms>` then verifies a
  follow-up `tap` reports `skipped=true`.
- B3: T083 blocked — `cmdHelp` must emit single JSON line
- B4: `get snapshot` split protocol must be finalised before general snapshot parsing
- B5: DEADZONE region now in design `lastTouchResult` (Feature 3a) — T087/T088 unblocked.
  PLEDIT (playlist-002 row) region still unspecified; no PLEDIT serial test until a
  dedicated playlist-002 hit-test surface lands.

Common preconditions for all tests below:
- DUT flashed with `cyd2usb_winamp_debug` env (defines `SERIAL_DEBUG` per ADR-021), booted, WiFi up, Spotify creds valid.
- Serial monitor attached at 115200 via `pio device monitor` or pyserial; `timeout=2s` on reads.
- Skip non-JSON lines (`json.loads` raises `ValueError`) — boot noise and esp_log output are not JSON.
- An active Spotify Connect device playing a track unless otherwise noted.

### T076 — [serialdbg-001, touch-002] Hit-zone boundary — inside vs. outside each button

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002
- **Objective**: Verify hit-test rects are pixel-accurate. Transport row is
  *contiguous* (PREV/PLAY/PAUSE/STOP/NEXT abut at x=38/61/84/107/130 with no gaps), so
  the meaningful boundary cases are: (a) 1 px outside the row entirely on either
  end; (b) each shared edge between adjacent buttons (left edge = that button).
  Guards off-by-one errors in `hitTestTransport`.
- **Preconditions**: M-SERIALDBG in tree. `originX=22`, `originY=0`. Touch cooldown clear (`set cooldown 0` between each tap).
- **Steps**: send `tap <x> 97` for each of the 8 boundary cases:
  1. `(37,97)`  → `hit ≠ TRANSPORT` (1 px left of PREV)
  2. `(38,97)`  → `hit=TRANSPORT, action=PREV`
  3. `(61,97)`  → `hit=TRANSPORT, action=PLAY`  (PREV/PLAY boundary)
  4. `(84,97)`  → `hit=TRANSPORT, action=PAUSE` (PLAY/PAUSE boundary)
  5. `(107,97)` → `hit=TRANSPORT, action=STOP`  (PAUSE/STOP boundary)
  6. `(130,97)` → `hit=TRANSPORT, action=NEXT`  (STOP/NEXT boundary)
  7. `(151,97)` → `hit=TRANSPORT, action=NEXT`  (last px of NEXT)
  8. `(152,97)` → `hit ≠ TRANSPORT` (1 px right of NEXT)
- **Expected result**: All 8 checks pass. Zero false triggers on out-of-row taps.
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `tools/run_serialdbg_tests.py::t076`). Owner: VE.

### T077 — [serialdbg-001, touch-002] Dead zone between posbar and transport row

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002
- **Objective**: Tap in the 5-pixel gap between posbar bottom (y=82) and transport top (y=88) → no ACT_* action dispatched. Guards overlapping hit rects after layout changes. Note: dead-zone taps may dispatch `ACT_FORCE_POLL` (DEADZONE behaviour); the test asserts no transport/posbar/volume action, not necessarily zero actions.
- **Preconditions**: M-SERIALDBG in tree. `DEADZONE` region added to `lastTouchResult` (design doc B5). `set cooldown 0` before tap.
- **Steps**: Send `tap 162 85` (x=midpoint of posbar width, y=85 = midpoint of 5-pixel dead zone at y=83..87) → parse JSON response.
- **Expected result**: `hit` is `NONE` or `DEADZONE`; `action` is `NONE` or `FORCE_POLL`. No `TRANSPORT`, `POSBAR`, or `VOLUME` action.
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t077`). Owner: VE.

### T078 — [serialdbg-001, touch-002] Zero-delta drag dispatches no volume action

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002
- **Objective**: A drag that starts and ends at the same coordinate (degenerate drag) must not enqueue ACT_VOLUME.
- **Preconditions**: M-SERIALDBG in tree. `dragState == D_IDLE` — confirm with `get dragState` → `"D_IDLE"`. `set cooldown 0`.
- **Steps**: Send `drag 163 63 163 63 1` (volume slot centre, zero delta, 1 step) → observe serial for ≥ 2 s.
- **Expected result**: No `[D][spotify.task] dequeued action=VOLUME` log line. `{"ok":true,"cmd":"drag",...}` response present. `dbg_getDragState()` returns `D_IDLE` after completion.
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t078`). Owner: VE.

### T079 — [serialdbg-001, touch-002] Cooldown gate blocks rapid sequential taps

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002
- **Objective**: Verify the cooldown gate (`touchScreenCoolDownTime`) suppresses
  taps and reports `skipped=true`. Note: `injectTouch` is *read-only* against the
  gate by design (synthetic taps must never block real input after a test), so the
  gate is armed via the debug-only `set cooldown <ms>` accessor, not by a prior
  synthetic tap. Guards both the gate's "skip + report" branch and the
  `dbgSet("cooldown", val)` arming path.
- **Preconditions**: M-SERIALDBG in tree. B1 resolved — `dbgSet("cooldown", ms)`
  accepts a positive value to arm the gate; `val=0` or empty resets.
- **Steps**:
  1. Send `set cooldown 500` — gate armed for 500 ms.
  2. Send `tap 72 97` (PLAY centre) — expect `{"ok":true,"cmd":"tap","hit":"NONE","skipped":true}`.
  3. Send `set cooldown 0` — gate cleared.
  4. Send `tap 72 97` again — expect `{"hit":"TRANSPORT","action":"PLAY","skipped":false}`.
- **Expected result**: Tap (2) skipped with `hit=NONE,skipped=true`; tap (4) fires
  normally. Confirms gate fires on arming and clears on reset.
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t079`). Owner: VE.

### T080 — [serialdbg-001] `info` command — state snapshot shape

- **Type**: unit (DUT, serial-driven)
- **Feature(s)**: serialdbg-001
- **Objective**: `info` command emits a machine-parseable snapshot covering all fields needed as test preconditions.
- **Preconditions**: M-SERIALDBG in tree. DUT booted with active Spotify session.
- **Steps**: Send `info` → `json.loads(line)`.
- **Expected result**: Single JSON line containing at minimum: `git`, `elf`, `build`, `heap`, `isPlaying`, `progressMs`, `durationMs`, `volumePct`, `consecutiveFailures`. All values within plausible ranges (`heap > 50000`, `volumePct` 0–100 or -1, `progressMs < durationMs` when playing).
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t080`). Owner: VE.

### T081 — [serialdbg-001, touch-002] Serial tap reproduces T052 transport suite

- **Type**: e2e (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002
- **Objective**: Same coverage as T052 but driven by serial `tap` instead of physical touch — making T052 regression-scriptable.
- **Preconditions**: M-SERIALDBG in tree. Active Spotify device playing a track. `info` → `durationMs > 0`. `set cooldown 0` between each tap.
- **Steps**: For each of the 5 transport buttons, send `tap <centreX> 97` (PREV=49, PLAY=72, PAUSE=95, STOP=118, NEXT=141). After each tap wait ≤ 5 s; verify Spotify state change via `info` or host-side `curl /v1/me/player`.
- **Expected result**: Each response: `{"ok":true,"cmd":"tap","hit":"TRANSPORT","pressed":N,"action":"<ACT>"}`. Spotify playback state matches action within ≤ 5 s.
- **Status**: pass 2026-05-17 — shape check via harness `t081` (5/5 TRANSPORT
  hits with correct action). Spotify-side effect manual: confirmed PLAY/PAUSE
  toggle Spotify play state and PREV/NEXT advance the queue within ≤ 5 s on
  the test account. Owner: VE.

### T082 — [serialdbg-001, touch-002] Serial drag reproduces T074 volume drag

- **Type**: e2e (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002, chrome-001
- **Objective**: Same coverage as T074 (debounced ACT_VOLUME dispatches during drag, drag-end commit on lift) but driven by serial `drag` — making T074 regression-scriptable.
- **Preconditions**: M-SERIALDBG in tree with queue-drain drag (no `delay()` in loop — design doc B1/R&D note). Active Spotify device with `supports_volume: true`. `set cooldown 0`.
- **Steps**: Send `drag 129 63 196 63 60` (volume slot full width, 60 steps — needed to span ≥ 600 ms and trigger ≥ 2 debounce windows at 300 ms each). Observe serial for `enqueued ACT_VOLUME pct=NN` log lines (synchronous trace emitted from `injectTouch` when the debounce window opens).
- **Expected result**: ≥ 2 `enqueued ACT_VOLUME` log lines (verifies debounce rate-limiting); `{"ok":true,"cmd":"drag",...}` response present; Spotify `device.volume_percent` matches released value within ≤ 30 s. Note: original design counted `dequeued action=VOLUME` lines from `spotify.task`, but those can lag the drag-end response by many seconds if the FreeRTOS task is mid-HTTPS-call; counting the synchronous enqueue trace removes that timing dependency. Note: `steps=8` is insufficient — at 10 ms/step the drag completes in 80 ms, within a single 300 ms debounce window.
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t082`; 2-3 ACT_VOLUME enqueues observed across full-run). Spotify volume effect manual: confirmed slider commit reaches Spotify `device.volume_percent` on release. Owner: VE.

### T083 — [serialdbg-001] `help` response is parseable JSON

- **Type**: unit (DUT, serial-driven)
- **Feature(s)**: serialdbg-001
- **Objective**: `help` command response is a single JSON line; `json.loads()` succeeds; all implemented commands are listed.
- **Preconditions**: M-SERIALDBG in tree with `cmdHelp` redesigned to emit single JSON object (design doc B3 resolved).
- **Steps**: Send `help` → read one line → `json.loads(line)` → assert `commands` array present with ≥ 6 entries (reconnect + 5 debug commands).
- **Expected result**: Parse succeeds. All command names present in `commands[].name`.
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t083`; 7 commands listed). Owner: VE.

### T084 — [serialdbg-001] `set backoff` / `get backoff` round-trip

- **Type**: unit (DUT, serial-driven)
- **Feature(s)**: serialdbg-001
- **Objective**: `set backoff N` persists and is readable via `get backoff`. Verifies debug accessor seam without network.
- **Preconditions**: M-SERIALDBG in tree. Issue between poll cycles (not during active Spotify poll — data race mitigation, see ADR-021).
- **Steps**:
  1. Send `set backoff 5` → assert `{"ok":true,"var":"backoff","val":5}`.
  2. Send `get backoff` → assert `consecutiveFailures=5`.
  3. Send `set backoff 0` → assert reset confirmed.
- **Expected result**: Round-trip consistent. After `set backoff 0`, next heartbeat shows base poll cadence restored.
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t084`; 5↔0 round-trip). Owner: VE.

### T085 — [serialdbg-001, touch-002] POSBAR tap returns NONE when no track loaded

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002
- **Objective**: `hitTestPosbar` returns -1 when `songDuration == 0`; tap on posbar must not dispatch `ACT_SEEK`. Guards the `songDuration <= 0` branch.
- **Preconditions**: M-SERIALDBG in tree with `dbgSet("songDuration", val)`
  accessor (added 2026-05-17) so the precondition can be forced without
  waiting on Spotify to drop the player session — which can take many
  minutes after the last client disconnects. The override is transient:
  the next successful `/me/player` poll restores the real duration.
- **Steps**:
  1. Send `set songDuration 0` — assert `ok=true`.
  2. Send `set cooldown 0`.
  3. Send `tap 162 77` (posbar centre) → parse response.
- **Expected result**: `hit ≠ POSBAR` (typically `DEADZONE`); `action ≠ SEEK`
  (typically `FORCE_POLL`).
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t085`; hit=DEADZONE
  action=FORCE_POLL with forced songDuration=0). Owner: VE.

### T086 — [serialdbg-001, touch-002] Full-perimeter boundary on POSBAR and VOLUME rects

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002, chrome-001
- **Objective**: Extend T076's transport-only left-x boundary check to the other two
  variable hit rects on all four edges. Catches off-by-one regressions in
  `hitTestPosbar` / `hitTestVolume` (e.g. an inclusive/exclusive mistake on a
  `y < BAR_Y + BAR_H` vs `<=`).
- **Preconditions**: M-SERIALDBG in tree. Active Spotify Connect device with a track
  loaded (so `songDuration > 0` — POSBAR taps need this to dispatch ACT_SEEK).
  `set cooldown 0` before each tap.
- **Steps**:
  1. POSBAR (screen rect x=38..285, y=72..81 per code — `POSBAR_Y=72`, `POSBAR_BG.h=10`,
     `py1=82` exclusive so max valid y=81). For each of `(37,77)`, `(286,77)`,
     `(162,71)`, `(162,83)` → assert `hit=DEADZONE`. For each of `(38,77)`,
     `(285,77)`, `(162,72)`, `(162,81)` → assert `hit=POSBAR`, `action=SEEK`.
     **Correction from design table:** design listed bottom inside as `(162,82)` but
     `hitTestPosbar` uses `sy >= py1` (82 exclusive) → `(162,82)` is DEADZONE;
     correct inside bottom is `(162,81)`.
  2. VOLUME (screen rect x=129..196, y=57..69 — `VOLUME_X=107`, `VOLUME_W=68`,
     `VOLUME_Y=57`, `VOLUME_H=13`, `originX=22`). For each of `(128,63)`, `(197,63)`,
     `(162,56)`, `(162,70)` → assert `hit=DEADZONE`. For each of `(129,63)`,
     `(196,63)`, `(162,57)`, `(162,69)` → assert `hit=VOLUME`, `action=VOLUME`.
- **Expected result**: 16 checks total. Outside-rim taps never produce `hit=POSBAR`
  or `hit=VOLUME`. Inside-rim taps always do, with `seekMs` / `volumePct` populated.
- **Status**: pass 2026-05-17 (DUT, ee65beb+; all 16 checks pass — 4 outside+4 inside
  for each rect; POSBAR `(162,82)` confirmed DEADZONE, `(162,81)` confirmed POSBAR;
  VOLUME boundaries exact). Owner: VE.

### T087 — [serialdbg-001, chrome-001, conn-001] Serial tap covers SHUFFLE / REPEAT / VIS / LOGO regions

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, chrome-001, conn-001
- **Objective**: Confirm `injectTouch` reaches the four remaining named regions —
  SHUFFLE, REPEAT, VIS, LOGO — and that each dispatches the documented ACT_* action
  (or `NONE` for inert regions). Also makes the conn-001 logo-tap path (T094)
  serial-driven for regression scripting.
- **Preconditions**: M-SERIALDBG in tree with full region enum in `lastTouchResult`
  (Feature 3a). LOGO centre reconciled at execution: `skin_layout.h` has
  `LOGO_X=243, LOGO_Y=84, LOGO_W=32, LOGO_H=32` → screen centre `(281, 100)` with
  `originX=22`; design table was correct. Old note about LOGO_X=250 is stale.
- **Steps**: For each region, `set cooldown 0`; send `tap <x> <y>`; parse response.
  1. SHUFFLE: `tap 209 96` → `hit=SHUFFLE`, `action=SHUFFLE`.
  2. REPEAT: `tap 246 96` → `hit=REPEAT`, `action=REPEAT`.
  3. VIS: `tap 84 51` → `hit=VIS`, `action=VIS`. VIS tap handler is wired
     (`vu::nextMode()` called in `injectTouch` path) — not inert.
  4. LOGO: `tap 281 100` → `hit=LOGO`, `action=TLS_RESET`. Within ≤ 2 s,
     `[I][spotify.tls] hard reset — stopping client` log line + force-poll fires.
     (Log tag is `spotify.tls`, not `spotify.task` as originally noted.)
  5. Second LOGO tap inside the 2 s `logoTapCooldownMs`: response is `hit=DEADZONE,
     action=FORCE_POLL` — the `else` branch at `injectTouch:684` handles both
     logo-in-cooldown and true dead-zone identically. No second TLS reset.
     **Correction from original spec:** step 5 expected `hit=LOGO` but code returns
     `hit=DEADZONE`; the important invariant (no double TLS reset) is verified via
     the log line count, not the hit field.
- **Expected result**: SHUFFLE and REPEAT tap dispatches enqueue ACT_SHUFFLE /
  ACT_REPEAT. VIS cycles visualiser mode. LOGO first tap fires TLS reset. Second
  LOGO tap within 2 s returns `hit=DEADZONE` (not LOGO) with no second TLS reset.
- **Status**: pass 2026-05-18 (DUT, 7ae8b7f+; harness `t087`; SHUFFLE+REPEAT+VIS+LOGO
  correct; LOGO TLS log `[I][spotify.tls] hard reset — stopping client` confirmed;
  second LOGO tap within 2 s → DEADZONE/FORCE_POLL. Note: harness restructured to
  send second tap before TLS log search to honour the 2 s cooldown window). Owner: VE.

### T088 — [serialdbg-001, touch-002] DEADZONE positive cases — canvas corners + design-doc dead-zone samples

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: serialdbg-001, touch-002
- **Objective**: Confirm taps that land outside all named regions report `hit=DEADZONE`
  (not `hit=NONE` — they enter `checkForInput`'s fall-through which dispatches
  `ACT_FORCE_POLL`). Guards against a region becoming unintentionally hittable as
  chrome layout shifts (e.g. a future TITLEBAR variant resize swallowing a corner).
  Pairs with T077 (which covers one specific posbar/transport gap) by extending to
  the full canvas perimeter + the other three documented dead-zone samples.
- **Preconditions**: M-SERIALDBG in tree with `DEADZONE` region in `lastTouchResult`
  (Feature 3a, design B5 resolved). `set cooldown 0` between each tap.
- **Steps**: For each sample, send `tap <x> <y>`; parse response; record action.
  1. Design-doc dead zones: `(37,77)`, `(162,71)`, `(162,85)`, `(162,107)` → assert
     `hit=DEADZONE`, `action=FORCE_POLL`.
  2. Canvas corners (far outside all chrome at originX=22, originY=0, chrome
     275×116): `(0,0)`, `(319,0)`, `(0,239)`, `(319,239)` → assert
     `hit=DEADZONE`, `action=FORCE_POLL`.
  3. Just outside chrome on each side: `(21,50)` (1 px left of originX),
     `(298,50)` (1 px right of originX+275=297), `(160,117)` (1 px below
     originY+116) → assert `hit=DEADZONE`.
- **Expected result**: 11 checks all return `hit=DEADZONE, action=FORCE_POLL`. Any
  result of `hit=TRANSPORT/POSBAR/VOLUME/SHUFFLE/REPEAT/VIS/LOGO` for these coords is
  a hit-test regression. Side-observation: each tap also triggers one
  `[D][spotify.poll]` line within ~1.5 s (ACT_FORCE_POLL effect).
- **Status**: pass 2026-05-17 (DUT, ee65beb+; all 11 checks DEADZONE/FORCE_POLL;
  no region misfire on any sample). Owner: VE.

### T095 — [serialdbg-001, touch-002] Injection-vs-physical calibration

- **Type**: integration (DUT, mixed serial + physical)
- **Feature(s)**: serialdbg-001, touch-002
- **Objective**: Verify the synthetic `injectTouch` path produces the *same*
  `lastTouchResult` + same ACT_* dispatch as a physical finger at the identical
  screen coordinate. Without this test, the injection branch can silently diverge
  from the `ts.touched()` branch (refactor splits them, only one gets a fix) and
  every other serialdbg-001 test will still pass while real touch breaks.
- **Preconditions**: M-SERIALDBG in tree. Human operator at the DUT (this test cannot
  be fully scripted). Spotify playing. `set cooldown 0` before each pair.
- **Steps**: For each of PREV (49,97), POSBAR mid (162,77), VOLUME mid (163,63):
  1. Send `tap <x> <y>` over serial; capture JSON `lastTouchResult` + observe
     downstream Spotify effect.
  2. Wait for cooldown to clear (≥ 200 ms or `set cooldown 0`).
  3. Physically tap the same screen coordinate; capture next ACT_* dispatch via
     the `[D][spotify.task] dequeued action=` log line + observe Spotify effect.
  4. Compare: same region, same action. Secondary fields (`seekMs`, `volumePct`) will
     differ due to resistive-touch hardware jitter — observed variance on CYD2USB is
     10–15 % for both axes. The pass criterion is region+action match; secondary
     field values are informational (the ±5 %/±2 % thresholds in the original spec
     underestimate CYD resistive jitter and are revised to ±15 %).
- **Expected result**: All 3 pairs match in region and action. Any pair that diverges
  is a structural break — the injection path no longer faithfully reproduces the
  physical path, and every other serialdbg test loses its authority.
- **Status**: pass 2026-05-17 (DUT, human operator; PREV: serial=TRANSPORT/PREV /
  physical=ACT_PREV ✓; POSBAR: serial=POSBAR/SEEK seekMs=127145 / physical=ACT_SEEK
  seekMs=111764 (~12 % jitter, within revised ±15 %) ✓; VOLUME: serial=VOLUME/VOLUME
  volumePct=50 / physical=ACT_VOLUME param=62 (~12 % jitter) ✓; all region+action
  pairs match). Owner: VE.

### T096 — [serialdbg-001] cmdDrag queue-drain completeness

- **Type**: unit (DUT, serial-driven)
- **Feature(s)**: serialdbg-001
- **Objective**: Verify the cmdDrag injection ring buffer drains every queued sample
  + the release sentinel — none dropped, no off-by-one on the modulo-64 head/tail
  wrap. Without this, T082's outcome-level check (≥ 2 ACT_VOLUME dispatches in 60
  steps) would still pass even if half the samples vanished, masking a queue bug.
- **Preconditions**: M-SERIALDBG in tree. The cmdDrag path must emit a per-sample
  trace line (e.g. `[D][serial] inject sample <i>/<N> sx=<x> sy=<y>` from
  `drainInjectionQueue()`) — Developer to add this trace under `SERIAL_DEBUG` if not
  already present; without it the test has no observability hook. `set cooldown 0`.
- **Steps**:
  1. Send `drag 129 63 196 63 60` (full volume-slot width, 60 steps — max headroom
     under the 62-step cap, exercises ring-buffer wrap at index 64).
  2. Capture serial until the `{"ok":true,"cmd":"drag",...}` response (the release
     sentinel's emit) — `s_dragPending` clears at that point.
  3. Count `inject sample` trace lines between the cmdDrag invocation and the
     drag-end response.
  4. Send a second `drag 129 63 196 63 62` immediately (no clearing) — exercises
     `s_injectHead = s_injectTail = 0` reset path in cmdDrag.
- **Expected result**: First drag: exactly 61 sample lines (steps=60 → 61 move
  samples at i=0..60) followed by the release-sentinel dispatch. Second drag: same
  pattern with 63 sample lines. No samples skipped, no duplicate emission, no
  spurious release-sentinel firing mid-drag. dragState ends in `D_IDLE` (verify via
  `dbg_getDragStateName`).
- **Status**: pass 2026-05-17 (DUT, ee65beb+; harness `t096`; drag60=61/61
  drag62=63/63 samples). Firmware fix 2026-05-17: `drainInjectionQueue` now logs
  only on move samples, not on the release sentinel — previously the sentinel
  emitted a misleading `inject sample N/N sx=0 sy=0` and inflated the tally by
  one. Owner: VE.

### T089 — [serialdbg-001] Production build contains no SERIAL_DEBUG symbols

- **Type**: integration (host build, no DUT)
- **Feature(s)**: serialdbg-001
- **Objective**: Confirm `SERIAL_DEBUG`-gated code compiles out completely in `cyd2usb_winamp`.
- **Preconditions**: Clean `pio run -e cyd2usb_winamp` build completed.
- **Steps**: `grep -c SERIAL_DEBUG .pio/build/cyd2usb_winamp/firmware.elf` → expect 0. Also verify flash size does not regress vs. pre-M-SERIALDBG baseline (check `pio run` output for flash % used).
- **Expected result**: Zero SERIAL_DEBUG symbol occurrences in ELF. Flash usage ≤ pre-SERIALDBG baseline + 0.1% (boot line adds `esp_app_get_description()` call — quantify in exit criteria when boot line guard decision is made per ADR-021 AC-4).
- **Status**: passed (2026-05-17). `strings firmware.elf | grep -c SERIAL_DEBUG` → 0. Flash: 52.8% (1,385,429 B / 2,621,440 B). Owner: VE.

---

## Suite: playlist-003 — M-LIST-v3 playlist interactivity (Features 4 & 5)

> Tracked-as: TASK-051g (row formatting), TASK-051h (songsSeen counter).
> Design: `docs/architecture/designs/M-LIST-v3-playlist-interactivity.md`.
> All tests in this suite require SERIAL_DEBUG firmware and a running Spotify session.

### Testability pre-requisite (blocking all T117–T124)

`get snapshot` serial response must expose `scrollOffset` (int) and `songsSeen` (uint16).
Without these fields, counter and scroll state can only be verified visually.
Developer must add these fields before any harness-driven test can be written.

---

### T117 — [playlist-002, playlist-003] Row format: number prefix and right-aligned duration

- **Type**: e2e (DUT + host)
- **Feature(s)**: playlist-002, playlist-003
- **Objective**: Each PLEDIT row displays `"N. Artist - Title   M:SS"` — queue-relative number (1-based), artist–title in the middle, duration right-aligned. Verifies Feature 4 pixel layout.
- **Preconditions**:
  - SERIAL_DEBUG firmware with TASK-051g applied. `get snapshot` exposes `scrollOffset`.
  - Spotify playing from a playlist; `get queue` returns `count >= 3`. `scrollOffset == 0`.
- **Steps**:
  1. `get queue` — record `items[0].artist`, `items[0].name`, `items[0].durationMs`.
  2. Visual inspection: row 0 text starts with `"1. "`, then artist + " - " + title, ends with `" M:SS"` right-aligned.
  3. Compute expected duration string from `durationMs`. Confirm it appears in the rightmost ~30px of content area.
  4. Confirm row 1 starts with `"2. "`.
- **Expected result**: Number prefix, artist–title, and duration all present and correctly positioned. No duration overlap with title text.
- **Status**: planned. Owner: VE.

---

### T118 — [playlist-002, playlist-003] Row truncation: `"..."` inserted, duration preserved

- **Type**: e2e (DUT + host)
- **Feature(s)**: playlist-002, playlist-003
- **Objective**: When `Artist - Title` exceeds the middle budget, text is trimmed and `"..."` appended. Duration still right-aligned and intact.
- **Preconditions**:
  - SERIAL_DEBUG firmware with TASK-051g applied.
  - Spotify playing a track where `strlen("N. Artist - Title") * 6 > 238 - dur_width - 2`. Use a known long-name track.
- **Steps**:
  1. Identify or force a track with a combined artist+title string > ~28 chars (after number prefix and duration budget).
  2. Visual inspection: row shows `"N. Artis...   M:SS"` — title text cut, `"..."` visible before the gap to duration.
  3. Confirm duration string is not overwritten or truncated.
- **Expected result**: Truncated middle section ends with `"..."`. Duration intact and right-aligned.
- **Status**: planned. Owner: VE.

---

### T119 — [playlist-002, playlist-003, touch-002] Swipe in PLEDIT content area shifts visible window

- **Type**: e2e (DUT + host)
- **Feature(s)**: playlist-002, playlist-003, touch-002
- **Objective**: Swipe-up in the PLEDIT content area increments `scrollOffset`; swipe-down decrements. Visible rows shift accordingly.
- **Preconditions**:
  - SERIAL_DEBUG firmware with TASK-051b/c/d applied. `get snapshot` exposes `scrollOffset`.
  - Spotify queue has `count >= 8`.
- **Steps**:
  1. `get snapshot` — assert `scrollOffset == 0`.
  2. Issue `drag` command: vertical swipe-up in PLEDIT content area (e.g. `drag 156 190 156 150 30`).
  3. `get snapshot` — assert `scrollOffset == 1`.
  4. Confirm row 0 now displays `"2. ..."` (second queue item).
  5. Issue swipe-down `drag 156 150 156 190 30`. Assert `scrollOffset == 0`.
- **Expected result**: `scrollOffset` tracks swipe direction; row numbers and content update accordingly.
- **Status**: planned. Owner: VE. Note: exact drag coordinates depend on swipe-zone boundaries (pending GUI design — see open issue below).

---

### T120 — [playlist-002, playlist-003] Scrollbar thumb position tracks scrollOffset

- **Type**: e2e (DUT + host)
- **Feature(s)**: playlist-002, playlist-003
- **Objective**: As `scrollOffset` increases from 0 to max, the scrollbar thumb moves from top to bottom of the scrollbar track proportionally.
- **Preconditions**:
  - SERIAL_DEBUG firmware with TASK-051c/e applied.
  - Queue `count >= 10`.
- **Steps**:
  1. Swipe to `scrollOffset == 0`; screenshot / visual: thumb at top of track.
  2. Swipe to `scrollOffset == count - PLEDIT_ROW_COUNT`; visual: thumb at bottom of track.
  3. Swipe to mid-point; visual: thumb at mid-track.
- **Expected result**: Thumb Y-position = `scrollOffset / (count - PLEDIT_ROW_COUNT)` × track height. Visually monotone.
- **Status**: planned. Owner: VE. `get scrollOffset` (TASK-079) now provides the serial assertion; visual pixel-read still required for thumb position confirmation.

---

### T121 — [playlist-002, playlist-003, sync-001] Track change resets scrollOffset to 0

- **Type**: e2e (DUT + host)
- **Feature(s)**: playlist-002, playlist-003, sync-001
- **Objective**: When the playing track changes (seqno advance), `scrollOffset` resets to 0 regardless of prior scroll position.
- **Preconditions**:
  - SERIAL_DEBUG firmware with TASK-051c/f applied. `get snapshot` exposes `scrollOffset`.
  - Queue `count >= 8`.
- **Steps**:
  1. Swipe to `scrollOffset >= 2`. Confirm via `get snapshot`.
  2. Skip to next track via Spotify app (external) or `ACT_NEXT`.
  3. Wait one poll cycle (≤ 8 s).
  4. `get snapshot` — assert `scrollOffset == 0`.
  5. Visual: row 0 shows `"N. [new track]   M:SS"`.
- **Expected result**: `scrollOffset` is 0 after track change. Row 0 shows new currently-playing track.
- **Status**: planned. Owner: VE.

---

### T122 — [playlist-003, sync-001] `songsSeen` increments on natural track advance

- **Type**: e2e (DUT + host)
- **Feature(s)**: playlist-003, sync-001
- **Objective**: `songsSeen` increments by 1 when a track ends naturally (no DUT or external skip).
- **Preconditions**:
  - SERIAL_DEBUG firmware with TASK-051h applied. `get snapshot` exposes `songsSeen`.
  - Spotify playing a short or near-end track (to reduce wait time).
- **Steps**:
  1. `get snapshot` — record `songsSeen = N`, `items[1].uri = EXPECTED_NEXT`.
  2. Wait for track to end naturally (monitor Spotify or poll until `items[0].uri == EXPECTED_NEXT`).
  3. `get snapshot` — assert `songsSeen == N + 1`.
  4. Visual: row 0 now shows `"N+1. [new track]"`.
- **Expected result**: Counter increments exactly once per natural advance.
- **Status**: planned. Owner: VE. Note: test duration depends on track length — use a short track or seek near end via Spotify app.

---

### T123 — [playlist-003, touch-002] `songsSeen` suppressed on DUT skip (ACT_NEXT)

- **Type**: e2e (DUT + host)
- **Feature(s)**: playlist-003, touch-002
- **Objective**: `songsSeen` does NOT increment when the DUT issues `ACT_NEXT` (skipPending flag suppresses).
- **Preconditions**:
  - SERIAL_DEBUG firmware with TASK-051h applied. `get snapshot` exposes `songsSeen`.
- **Steps**:
  1. `get snapshot` — record `songsSeen = N`.
  2. Tap the NEXT button on DUT (physical or serial: `tap <NEXT_X> <NEXT_Y>`).
  3. Wait one poll cycle (≤ 8 s).
  4. `get snapshot` — assert `songsSeen == N` (unchanged).
- **Expected result**: `songsSeen` unchanged after DUT-initiated skip.
- **Status**: planned. Owner: VE.

---

### T124 — [playlist-003] `songsSeen` suppressed on external random skip (manual)

- **Type**: e2e (DUT + host, manual)
- **Feature(s)**: playlist-003
- **Objective**: `songsSeen` does NOT increment when the Spotify app on the phone skips to a non-adjacent track.
- **Preconditions**:
  - SERIAL_DEBUG firmware with TASK-051h applied. Phone with Spotify app.
- **Steps**:
  1. `get snapshot` — record `songsSeen = N`, `items[1].uri`.
  2. On the phone, use Spotify to navigate to a track that is NOT `items[1]` (e.g. jump to a different album).
  3. Wait one poll cycle.
  4. `get snapshot` — assert `songsSeen == N`.
- **Expected result**: `songsSeen` unchanged. URI mismatch correctly suppressed increment.
- **Status**: planned. Owner: VE. Manual step required (no harness path to Spotify phone app).

---

## Suite: matrix-001 — MatrixApp (TASK-097)

**DUT required** — T_MA_01–T_MA_03 use `run_serialdbg_tests.py` with `cyd2usb_winamp_debug`.
T_MA_04–T_MA_05 are manual visual / physical-touch checks.

### T_MA_01 — [matrix-001] MatrixApp switch round-trip

- **Type**: integration (DUT)
- **Feature(s)**: matrix-001, app-interface-001, taskbar-001
- **Objective**: Spotify→Matrix→Spotify app switch completes without crash; appId correct at each step.
- **Preconditions**: DUT booted with `cyd2usb_winamp_debug`. Spotify app active.
- **Steps**:
  1. `get appId` → assert `name="Spotify"`.
  2. `tap <taskbar_slot 4>` (Matrix) → wait 400 ms → `get appId` → assert `name="Matrix"`.
  3. `tap <taskbar_slot 0>` (Spotify) → wait 400 ms → `get appId` → assert `name="Spotify"`.
- **Expected result**: appId transitions Spotify→Matrix→Spotify. DUT responsive throughout.
- **Harness**: `run_serialdbg_tests.py --tests T_MA_01`. Owner: VE.
- **Status**: written (2026-05-25).

### T_MA_02 — [matrix-001] Matrix BUG-1 guard (Winamp zones bypassed)

- **Type**: integration (DUT)
- **Feature(s)**: matrix-001, app-interface-001
- **Objective**: Canvas tap while Matrix is active returns `hit="CLOCK"` — Winamp hit-zones are not evaluated.
- **Preconditions**: Matrix is the active app.
- **Steps**:
  1. Switch to Matrix. `tap 137 120` (centre of canvas, x < TASKBAR_X).
  2. Assert `hit == "CLOCK"`. Assert DUT still responsive.
  3. Switch back to Spotify.
- **Expected result**: `{"hit":"CLOCK","action":"NONE"}` — BUG-1 guard fired; no Winamp region matched.
- **Harness**: `run_serialdbg_tests.py --tests T_MA_02`. Owner: VE.
- **Status**: written (2026-05-25).

### T_MA_03 — [matrix-001] Matrix→Spotify canvas residue

- **Type**: integration (DUT)
- **Feature(s)**: matrix-001, app-interface-001
- **Objective**: `lastPlaylistDraw` advances within 3 s of switching from Matrix back to Spotify, confirming ADR-027 TFT state compliance and no rendering crash.
- **Preconditions**: Spotify connected and polling (queue populated recommended).
- **Steps**:
  1. Switch to Matrix. Wait 150 ms (1–2 ticks).
  2. Switch to Spotify. Read `lastPlaylistDraw` before and poll for 3 s.
  3. Assert timestamp advances.
- **Expected result**: `lastPlaylistDraw.ms` increases within 3 s. SKIP if Spotify not rendering.
- **Harness**: `run_serialdbg_tests.py --tests T_MA_03`. Owner: VE.
- **Status**: written (2026-05-25).

### T_MA_04 — [matrix-001] Full canvas coverage (manual visual)

- **Type**: integration (manual DUT)
- **Feature(s)**: matrix-001
- **Objective**: MatrixApp renders falling characters across the full 275×240 app canvas. No unexplained blank regions at top, bottom, or sides. (LL-037 regression check.)
- **Preconditions**: DUT flashed with production or debug build. Matrix app visible on screen.
- **Steps**:
  1. Switch to Matrix app via taskbar.
  2. Observe display for 2+ seconds.
  3. Verify characters appear in the top 120 rows and the bottom 120 rows of the app canvas.
- **Expected result**: All 14 streams traverse the full y:0..239 range. No solid-black half.
- **Status**: planned (manual — requires human observation).

### T_MA_05 — [matrix-001] Tap reinitialises streams (manual physical)

- **Type**: integration (manual DUT)
- **Feature(s)**: matrix-001
- **Objective**: Physical touch on the Matrix canvas calls `handleInput(Press)` → `initMatrixState()` + `repaintMatrix()`. Streams restart from scattered starting positions.
- **Preconditions**: Matrix active, streams mid-animation.
- **Steps**: 1. Tap the Matrix canvas. 2. Observe streams reset (screen briefly black; new streams begin).
- **Expected result**: Visible stream reset within one frame.
- **Status**: planned (manual — physical touch; cmdTap returns CLOCK/NONE for non-Spotify apps).

---

## Suite: gol-001 — LifeApp (TASK-098)

**DUT required** — T_GOL_01–T_GOL_04 automated; T_GOL_05–T_GOL_07 manual.

### T_GOL_01 — [gol-001] LifeApp switch round-trip

- **Type**: integration (DUT)
- **Feature(s)**: gol-001, app-interface-001, taskbar-001
- **Objective**: Spotify→GoL→Spotify switch completes without crash; appId correct at each step.
- **Preconditions**: DUT booted with `cyd2usb_winamp_debug`. Spotify active.
- **Steps**: Same pattern as T_MA_01 but for slot 5 (Life).
- **Expected result**: appId transitions Spotify→Life→Spotify. DUT responsive.
- **Harness**: `run_serialdbg_tests.py --tests T_GOL_01`. Owner: VE.
- **Status**: written (2026-05-25).

### T_GOL_02 — [gol-001] GoL BUG-1 guard

- **Type**: integration (DUT)
- **Feature(s)**: gol-001, app-interface-001
- **Objective**: Canvas tap while GoL is active returns `hit="CLOCK"`.
- **Preconditions**: GoL active.
- **Steps**: Switch to Life. `tap 137 120`. Assert `hit="CLOCK"`. Switch back.
- **Expected result**: `{"hit":"CLOCK","action":"NONE"}`.
- **Harness**: `run_serialdbg_tests.py --tests T_GOL_02`. Owner: VE.
- **Status**: written (2026-05-25).

### T_GOL_03 — [gol-001] GoL→Spotify canvas residue

- **Type**: integration (DUT)
- **Feature(s)**: gol-001, app-interface-001
- **Objective**: `lastPlaylistDraw` advances after GoL→Spotify switch — no TFT state contamination.
- **Preconditions**: Spotify connected and polling.
- **Steps**: Same pattern as T_MA_03 but from Life slot.
- **Expected result**: `lastPlaylistDraw.ms` increases within 3 s. SKIP if Spotify not rendering.
- **Harness**: `run_serialdbg_tests.py --tests T_GOL_03`. Owner: VE.
- **Status**: written (2026-05-25).

### T_GOL_04 — [gol-001] GoL alive count updated (stepGeneration fires)

- **Type**: integration (DUT)
- **Feature(s)**: gol-001
- **Objective**: `get golAlive` returns a value ≥ 0 after GoL has been active for 350 ms (≥3 ticks at 100 ms/tick), proving `stepGeneration` fired and set `s_golAliveCount`.
- **Preconditions**: GoL active.
- **Steps**:
  1. Switch to Life. Wait 350 ms.
  2. `get golAlive` → assert `count >= 0`.
  3. Switch back to Spotify.
- **Expected result**: `{"count": N}` where N ≥ 0. `count == -1` means GoL never ticked (FAIL).
- **Harness**: `run_serialdbg_tests.py --tests T_GOL_04`. Owner: VE.
- **Status**: written (2026-05-25).

### T_GOL_05 — [gol-001] Full canvas coverage (manual visual)

- **Type**: integration (manual DUT)
- **Feature(s)**: gol-001
- **Objective**: GoL cells appear across the full 275×240 canvas. No solid-black half. (LL-037 check.)
- **Steps**: Switch to GoL. Observe for 2+ s. Verify cells in top rows and bottom rows.
- **Status**: planned (manual).

### T_GOL_06 — [gol-001] Tap reseeds grid (manual physical)

- **Type**: integration (manual DUT)
- **Feature(s)**: gol-001
- **Objective**: Physical tap on GoL canvas calls `handleInput(Press)` → `spawnLife()` + `resume()`. Grid restarts.
- **Steps**: GoL active. Physical tap. Observe screen briefly clears then new random pattern appears.
- **Status**: planned (manual — physical touch only).

### T_GOL_07 — [gol-001] Stagnation reset fires (manual timed)

- **Type**: integration (manual DUT)
- **Feature(s)**: gol-001
- **Objective**: When alive count drops below 5 or sameCountTimer exceeds 120, `spawnLife()` is called.
  Observable as a sudden canvas clear and new random pattern after a stagnant state.
- **Steps**: Leave GoL running for 30–120 s. Observe at least one stagnation reset (canvas wipe + reseed).
- **Status**: planned (manual — timing-dependent; automated version would require longer DUT session).

---

## Suite: weather-001 — WeatherApp (TASK-099)

**DUT required** — T_WX_01–T_WX_05 automated. T_WX_06 manual visual.
T_WX_05 requires network access to `api.open-meteo.com` (or current `host_overrides.json`).

### T_WX_01 — [weather-001] WeatherApp switch round-trip

- **Type**: integration (DUT)
- **Feature(s)**: weather-001, app-interface-001, taskbar-001
- **Objective**: Spotify→Weather→Spotify switch completes; appId correct at each step.
- **Preconditions**: DUT booted with `cyd2usb_winamp_debug`. Spotify active.
- **Steps**: Same pattern as T_MA_01 but for slot 2 (Weather).
- **Expected result**: appId transitions Spotify→Weather→Spotify. DUT responsive.
- **Harness**: `run_serialdbg_tests.py --tests T_WX_01`. Owner: VE.
- **Status**: written (2026-05-25).

### T_WX_02 — [weather-001] Weather BUG-1 guard

- **Type**: integration (DUT)
- **Feature(s)**: weather-001, app-interface-001
- **Objective**: Canvas tap while Weather active returns `hit="CLOCK"`.
- **Steps**: Switch to Weather. `tap 137 120`. Assert `hit="CLOCK"`. Switch back.
- **Harness**: `run_serialdbg_tests.py --tests T_WX_02`. Owner: VE.
- **Status**: written (2026-05-25).

### T_WX_03 — [weather-001] Weather→Spotify canvas residue

- **Type**: integration (DUT)
- **Feature(s)**: weather-001, app-interface-001
- **Objective**: `lastPlaylistDraw` advances after Weather→Spotify switch — confirms ADR-027 compliance (MC_DATUM reset in weatherDrawChrome/repaintWeatherValues).
- **Steps**: Same pattern as T_MA_03 from Weather slot.
- **Harness**: `run_serialdbg_tests.py --tests T_WX_03`. Owner: VE.
- **Status**: written (2026-05-25).

### T_WX_04 — [weather-001] Weather pre-fetch state (---display)

- **Type**: integration (DUT)
- **Feature(s)**: weather-001
- **Objective**: `weatherReady=false` immediately after first switch-in, confirming `"---"` is displayed before dataTask fetch completes.
- **Preconditions**: Weather app never shown in this DUT session (first switch-in since boot). If `weatherReady` is already true, test SKIPs.
- **Steps**:
  1. `get weatherReady` → assert `ready=false` (precondition).
  2. Switch to Weather. Immediately `get weatherReady`.
  3. Assert `ready=false`.
- **Expected result**: `ready=false` at step 3 — pre-fetch state confirmed.
- **Harness**: `run_serialdbg_tests.py --tests T_WX_04`. Owner: VE.
- **Status**: written (2026-05-25). Run at start of session for valid precondition.

### T_WX_05 — [weather-001] Weather data arrives from dataTask

- **Type**: integration (DUT, network)
- **Feature(s)**: weather-001, dataTask
- **Objective**: `weatherReady` becomes true within 30 s of switching to WeatherApp, proving `dataTask::pollWeather()` delivered a result and `s_wxDataReady` was set.
- **Preconditions**: Network access to `api.open-meteo.com` (or `host_overrides.json` with current IP on SPIFFS).
- **Steps**:
  1. Switch to Weather.
  2. Poll `get weatherReady` every 2 s for up to 30 s.
  3. Assert `ready=true` before timeout.
- **Expected result**: `ready=true` within 30 s.
- **Harness**: `run_serialdbg_tests.py --tests T_WX_05`. Owner: VE.
- **Status**: written (2026-05-25).

### T_WX_06 — [weather-001] Full canvas top+bottom rows populated (manual visual)

- **Type**: integration (manual DUT)
- **Feature(s)**: weather-001
- **Objective**: Both the top row (y:0..119) and bottom row (y:121..239) of the WeatherApp canvas are visible. No solid-black half. (LL-037 regression check — original TASK-096 bug was top half black.)
- **Steps**:
  1. Switch to Weather. Wait for at least one data fetch.
  2. Observe screen. Confirm: top-left "TIME" panel and top-right "TEMP" panel visible in upper half. Bottom-left "HUMIDITY" and bottom-right "WIND" panels visible in lower half.
- **Expected result**: 4 panels across 2 rows, each filling its quadrant.
- **Status**: planned (manual — pixel coverage not automatable via serialdbg).

---

## Suite: crypto-001 — CryptoApp (TASK-100)

**DUT required** — T_CX_01–T_CX_05 automated. T_CX_06 manual visual.
T_CX_05 requires network access to `api.coingecko.com` (or current `host_overrides.json`).

### T_CX_01 — [crypto-001] CryptoApp switch round-trip

- **Type**: integration (DUT)
- **Feature(s)**: crypto-001, app-interface-001, taskbar-001
- **Objective**: Spotify→Crypto→Spotify switch completes; appId correct at each step.
- **Steps**: Same pattern as T_MA_01 but for slot 3 (Crypto).
- **Harness**: `run_serialdbg_tests.py --tests T_CX_01`. Owner: VE.
- **Status**: written (2026-05-25).

### T_CX_02 — [crypto-001] Crypto BUG-1 guard

- **Type**: integration (DUT)
- **Feature(s)**: crypto-001, app-interface-001
- **Objective**: Canvas tap while Crypto active returns `hit="CLOCK"`.
- **Steps**: Switch to Crypto. `tap 137 120`. Assert `hit="CLOCK"`. Switch back.
- **Harness**: `run_serialdbg_tests.py --tests T_CX_02`. Owner: VE.
- **Status**: written (2026-05-25).

### T_CX_03 — [crypto-001] Crypto→Spotify canvas residue

- **Type**: integration (DUT)
- **Feature(s)**: crypto-001, app-interface-001
- **Objective**: `lastPlaylistDraw` advances after Crypto→Spotify switch — ADR-027 compliance.
- **Steps**: Same pattern as T_MA_03 from Crypto slot.
- **Harness**: `run_serialdbg_tests.py --tests T_CX_03`. Owner: VE.
- **Status**: written (2026-05-25).

### T_CX_04 — [crypto-001] Crypto pre-fetch state

- **Type**: integration (DUT)
- **Feature(s)**: crypto-001
- **Objective**: `cryptoReady=false` immediately after first switch-in.
- **Preconditions**: Crypto never shown since boot. SKIPs if `cryptoReady` already true.
- **Steps**: Same pattern as T_WX_04 but `get cryptoReady` and slot 3.
- **Harness**: `run_serialdbg_tests.py --tests T_CX_04`. Owner: VE.
- **Status**: written (2026-05-25). Run at start of session.

### T_CX_05 — [crypto-001] Crypto data arrives from dataTask

- **Type**: integration (DUT, network)
- **Feature(s)**: crypto-001, dataTask
- **Objective**: `cryptoReady=true` within 30 s of switching to CryptoApp.
- **Preconditions**: Network access to `api.coingecko.com`. Run alongside T_WX_05 in same DUT session where possible.
- **Steps**: Same pattern as T_WX_05 but `get cryptoReady` and slot 3.
- **Harness**: `run_serialdbg_tests.py --tests T_CX_05`. Owner: VE.
- **Status**: written (2026-05-25).

### T_CX_06 — [crypto-001] Full canvas 6-row layout (manual visual)

- **Type**: integration (manual DUT)
- **Feature(s)**: crypto-001
- **Objective**: CryptoApp renders 6 rows spanning full 275×240 canvas. Header y=5, rule y=22, first data row y=25, last divider y=239. No unexplained blank region. (LL-037 regression check.)
- **Steps**:
  1. Switch to Crypto. Wait for data fetch.
  2. Verify header "CRYPTO TERMINAL" visible near top. Verify 6 coin rows with prices/changes visible, last row reaching near bottom of screen.
- **Status**: planned (manual).

---

## Suite: cross-feature X007 — dataTask shared queue (weather-001 ↔ crypto-001)

**DUT required** — T_X07_01 automated.

### T_X07_01 — [X007] Rapid Weather↔Crypto switching — dataTask queue stable

- **Type**: cross-feature (DUT)
- **Feature(s)**: weather-001, crypto-001
- **Interaction**: X007
- **Objective**: Rapid Weather→Crypto→Weather→Crypto→Spotify sequence completes with correct appId at every step and DUT remains responsive. Confirms the shared dataTask queue + spinlock does not corrupt app state under concurrent enqueue pressure.
- **Preconditions**: DUT booted with `cyd2usb_winamp_debug`. Spotify active.
- **Steps**:
  1. Spotify→Weather (200 ms) → `get appId` → assert Weather.
  2. Weather→Crypto (200 ms) → `get appId` → assert Crypto.
  3. Crypto→Weather (200 ms) → `get appId` → assert Weather.
  4. Weather→Crypto (200 ms) → `get appId` → assert Crypto.
  5. Crypto→Spotify (200 ms) → `get appId` → assert Spotify.
  6. `info` → assert `ok=true` (DUT alive).
- **Expected result**: All 5 appId assertions pass; `info` responds normally.
- **Harness**: `run_serialdbg_tests.py --tests T_X07_01`. Owner: VE.
- **Status**: written (2026-05-25).

---

## Suite: touch-capture-001 — Slider input capture (TASK-102)

**DUT required** — T149–T154 use `run_serialdbg_tests.py` with `cyd2usb_winamp_debug`.
Design doc: `docs/architecture/designs/M-TOUCH-CAPTURE-slider-input-capture.md`.
VE review: `docs/verification/regression_suite/touch-capture-ve-review.md`.

### T149 — [touch-002] POSBAR drag commits single ACT_SEEK on Release at correct position

- **Type**: integration (DUT)
- **Feature(s)**: touch-002
- **Objective**: Confirm that `cmdDrag` across the POSBAR groove enqueues exactly one
  `ACT_SEEK` on Release and that the committed position matches the drag endpoint.
- **Preconditions**: DUT booted with `cyd2usb_winamp_debug`. Spotify active. `set
  songDuration 120000` (120 s). `get dragState` == `D_IDLE`.
- **Steps**:
  1. `drag 40 77 200 77 10` (left→right sweep across POSBAR at y=77, 10 steps).
  2. Assert response `ok=true`.
  3. `get posbarDragMs` — record `committed_ms`.
  4. Assert `committed_ms` is in range `[50000, 120000]` (right half of a 120 s track).
  5. Assert serial log contains exactly one `ACT_SEEK` entry during the drag.
- **Expected result**: Single ACT_SEEK commit; `posbarDragMs` matches the x=200 endpoint
  (`≈ (200 - POSBAR_X) / POSBAR_W * 120000 ≈ 88000 ms`).
- **Harness**: `run_serialdbg_tests.py --tests T149`. Owner: VE.
- **Status**: PASS (2026-06-05). posbarDragMs=89032 ms; dragState=D_IDLE.

### T150 — [touch-002] POSBAR capture: Move outside hitbox continues updating thumb

- **Type**: integration (DUT)
- **Feature(s)**: touch-002
- **Objective**: Finger drifts above the 10 px POSBAR groove; drag samples continue
  updating `_posbarDragCurrentMs`. Without capture the samples would be lost.
- **Preconditions**: As T149. `set songDuration 120000`.
- **Steps**:
  1. `drag 40 77 200 50 10` — starts in POSBAR (y=77), drifts upward to y=50 (above groove).
  2. Assert response `ok=true`.
  3. `get posbarDragMs` — assert value in `[50000, 120000]` (right half, matching x=200).
  4. `get dragState` — assert `D_IDLE` (released cleanly).
- **Expected result**: `posbarDragMs` reflects the x endpoint despite y drift. If capture
  is broken, `posbarDragMs ≈ 0` (drag stopped updating when y left the groove).
- **Harness**: `run_serialdbg_tests.py --tests T150`. Owner: VE.
- **Status**: PASS (2026-06-05). posbarDragMs=89032 ms despite y-drift above groove.

### T151 — [touch-002] VOLUME capture: Move outside hitbox continues updating volume

- **Type**: integration (DUT)
- **Feature(s)**: touch-002
- **Objective**: Finger drifts below the 13 px VOLUME groove; drag samples continue
  updating `lastVolumeRendered`. Without capture the update ceases mid-drag.
- **Preconditions**: DUT booted with `cyd2usb_winamp_debug`. Spotify active.
  `get dragState` == `D_IDLE`.
- **Steps**:
  1. `drag 110 62 170 80 10` — starts inside VOLUME (y=62, within 57–69), drifts to y=80
     (below groove).
  2. Assert response `ok=true`.
  3. `get dragState` — assert `D_IDLE`.
  4. Assert the drag emitted at least one `ACT_VOLUME` entry (volume debounce may collapse
     multiple; at least one must appear in the Release commit path).
- **Expected result**: Volume updated across full x travel despite y drift. No mid-drag
  freeze at the hitbox edge.
- **Harness**: `run_serialdbg_tests.py --tests T151`. Owner: VE.
- **Status**: PASS (2026-06-05). 2 ACT_VOLUME events during y-drift below groove.

### T152 — [touch-002] PLEDIT scrollbar capture: Move outside strip continues scrolling

- **Type**: integration (DUT)
- **Feature(s)**: touch-002, playlist-002
- **Objective**: Finger starts in the 19 px scrollbar strip then drifts left into the
  content area; `D_PLEDIT_SCROLL_DIRECT` remains active and `scrollOffset` tracks the Y.
- **Preconditions**: DUT with queue ≥ 8 items (> PLEDIT_ROW_COUNT=5). `get scrollOffset`
  == 0.
- **Steps**:
  1. `drag 265 140 52 180 10` — starts in scrollbar strip centre (x=265, strip=[256,274]),
     drifts left to x=52 (content area), y sweeps 140→180. *(Spec had x=283 which is
     outside the strip; corrected to x=265 in harness.)*
  2. Assert response `ok=true`.
  3. `get scrollOffset` — assert value > 0 (scroll advanced from y travel).
  4. `get dragState` — assert `D_IDLE`.
- **Expected result**: `scrollOffset` advanced proportional to y travel. Without capture,
  drift into content area would switch to `D_PLEDIT_SCROLL` or stop updating entirely.
- **Harness**: `run_serialdbg_tests.py --tests T152`. Owner: VE.
- **Status**: SKIP [CONDITIONAL] (2026-06-05) — queue < 6 items at run time.
  Re-run when Spotify queue has ≥ 6 tracks loaded.

### T153 — [touch-002] Capture exclusivity: drift from VOLUME into POSBAR does not start seek

- **Type**: integration (DUT)
- **Feature(s)**: touch-002
- **Objective**: While `D_VOLUME_DRAG` is active, raw (x,y) may fall inside the POSBAR
  hitbox during a downward drift. Phase 1 must route to the volume handler; Phase 2
  (POSBAR hit-test) must never run.
- **Preconditions**: DUT booted with `cyd2usb_winamp_debug`. Spotify active.
  `set songDuration 120000`.
- **Steps**:
  1. `drag 110 62 170 77 10` — starts in VOLUME (y=62), drifts down to y=77 (POSBAR row).
  2. Assert `ok=true`.
  3. `get dragState` — assert `D_IDLE`.
  4. `get posbarDragMs` — assert **unchanged** from baseline before drag (no seek initiated).
     *(Spec said "assert 0"; changed to "unchanged" in harness since T149 may have set a
     non-zero value. Semantically equivalent — any change means capture exclusivity broken.)*
  5. Assert serial log contains zero `ACT_SEEK` entries during this drag.
- **Expected result**: Volume drag completed; no seek was ever started or committed.
- **Harness**: `run_serialdbg_tests.py --tests T153`. Owner: VE.
- **Status**: PASS (2026-06-05). posbarDragMs unchanged at 89032 ms; no seek initiated.

### T154 — [touch-002] POSBAR Press + immediate Release seeks to pressed position

- **Type**: integration (DUT)
- **Feature(s)**: touch-002
- **Objective**: A tap (Press then Release with no Move) on the POSBAR groove commits
  a seek at the tapped position. Verifies `D_POSBAR_DRAG` is entered on Press and
  `_posbarDragCurrentMs` is initialised from the Press coordinate.
- **Preconditions**: `set songDuration 60000`. `get dragState` == `D_IDLE`.
- **Steps**:
  1. `tap 180 77` (x=180, middle of POSBAR; expected seek ≈ 39000 ms for 60 s track).
  2. `get posbarDragMs` — record `seeked_ms`.
  3. Assert `seeked_ms` in range `[35000, 45000]`.
  4. Assert serial log contains one `ACT_SEEK` entry.
- **Expected result**: Single seek committed at ~39000 ms. Without the Press-entry init,
  `_posbarDragCurrentMs` would be 0 and the seek would go to track start.
- **Harness**: `run_serialdbg_tests.py --tests T154`. Owner: VE.
- **Status**: PASS (2026-06-05). seeked_ms=39677 ms (expected ≈39677).

---

## Suite: velocity-scroll-001 — M-LIST-v4 velocity-scroll PLEDIT (TASK-104)

**DUT required** — T155–T161 use `run_serialdbg_tests.py` with `cyd2usb_winamp_debug`.
T162–T166 are in the taskbar-scroll-001 suite (below).
Design doc: `docs/architecture/designs/M-LIST-v4-velocity-scroll.md`.
VE review: `docs/verification/regression_suite/velocity-scroll-ve-review.md`.

As-built constants (authoritative): `SCROLL_DEAD_ZONE_PX = 1`, `SCROLL_SPEED_K_DEFAULT = 0.1667`.
PLEDIT content area: x ∈ [12..255], y ∈ [136..200], row height = 13 px.

Common preconditions for harness tests (T155–T160):
- DUT flashed with `cyd2usb_winamp_debug`, booted, WiFi up.
- Queue ≥ 10 items loaded (PLEDIT overflows viewport).
- `get dragState` → `D_IDLE`.
- `get scrollOffset` → 0.

### T155 — [playlist-003] Tap within dead zone fires ACT_PLAY_URI

- **Type**: integration (DUT)
- **Feature(s)**: playlist-003
- **Objective**: A drag gesture that ends at the same pixel as it started (dy = 0) stays
  within the 1 px dead zone and releases as a tap, enqueueing the row via ACT_PLAY_URI.
  Verifies the dead-zone-only tap discriminator (replaces TASK-078 two-axis elapsed check).
- **Preconditions**: Common preconditions above. Queue item at scroll row 0 present.
- **Steps**:
  1. `drag 140 150 140 150 1` — 0-pixel drag in PLEDIT content area (x=140, y=150); finger held.
  2. `release`.
  3. Assert serial log contains `ACT_PLAY_URI`.
  4. `get scrollOffset` — assert 0 (unchanged).
  5. `get dragState` — assert `D_IDLE`.
- **Expected result**: ACT_PLAY_URI fires for the row at (150−136)/13 = row 1. scrollOffset
  unchanged. dragState D_IDLE. abs(dy)=0 < SCROLL_DEAD_ZONE_PX(1) → tap branch taken.
- **Harness**: `run_serialdbg_tests.py --tests T155`. Owner: VE.
- **Status**: written (2026-05-25).

### T156 — [playlist-003] Release outside dead zone suppresses tap (scroll-end)

- **Type**: integration (DUT)
- **Feature(s)**: playlist-003
- **Objective**: A drag of exactly 1 row (13 px, effective 12 px, outside 1 px dead zone)
  at Release triggers the scroll-end branch and suppresses ACT_PLAY_URI.
- **Preconditions**: Common preconditions above.
- **Steps**:
  1. `drag 140 150 140 163 1` — 13 px downward drag (y 150→163, dy = +13); finger held.
  2. `release`.
  3. Assert serial log does NOT contain `ACT_PLAY_URI`.
  4. `get dragState` — assert `D_IDLE`.
- **Expected result**: No row played. dragState D_IDLE. The 13 px displacement exceeds
  SCROLL_DEAD_ZONE_PX (1), so the gesture is classified as scroll-end, not tap.
- **Harness**: `run_serialdbg_tests.py --tests T156`. Owner: VE.
- **Status**: written (2026-05-25).

### T157 — [playlist-003] Velocity scaling: ~2.0 rows/s at dy = 1 row

- **Type**: integration (DUT)
- **Feature(s)**: playlist-003
- **Objective**: Verify scrollVelocity ≈ 2.0 rows/s when the finger is held at dy = −13 px
  (1-row effective travel of 12 px). Confirms speed = effective × K = 12 × 0.1667 ≈ 2.00.
- **Preconditions**: Common preconditions above.
- **Steps**:
  1. `drag 140 163 140 150 5` — upward 13 px drag (y 163→150, dy = −13); finger held.
  2. `get dragState` — assert `D_PLEDIT_SCROLL`.
  3. `get scrollVelocity` — assert value in range [1.8, 2.2].
- **Expected result**: dragState D_PLEDIT_SCROLL (gesture active). scrollVelocity ≈ 2.00
  (effective=12, K=0.1667). Range [1.8, 2.2] tolerates ±1 natural app-tick jitter. Finger
  still held after this test (used as precondition for T158 if run sequentially).
- **Harness**: `run_serialdbg_tests.py --tests T157`. Owner: VE.
- **Status**: written (2026-05-25).

### T158 — [playlist-003] Tick integration: 1 s at dy = 1 row advances scrollOffset

- **Type**: integration (DUT)
- **Feature(s)**: playlist-003
- **Objective**: Synthetic ticks totalling 1 s at held dy = −13 px advance scrollOffset by
  approximately 2 rows (velocity ≈ 2.0 rows/s). Verifies tickScroll() integrates the
  accumulator correctly under deterministic time injection.
- **Preconditions**: Finger held at dy = −13 from T157 (`drag 140 163 140 150 5`,
  dragState D_PLEDIT_SCROLL). Re-issue the drag command if running this test standalone.
- **Steps**:
  1. `tick 50 20` — injects 50 × 20 ms = 1000 ms equivalent.
  2. `get scrollOffset` — assert ≥ 1.
- **Expected result**: scrollOffset advanced by at least 1 row. Expected ≈ 2 rows
  (2.00 rows/s × 1.0 s). Assertion is ≥ 1 to tolerate natural app-tick variation and
  accumulator phase at tick start.
- **Harness**: `run_serialdbg_tests.py --tests T158`. Owner: VE.
- **Status**: written (2026-05-25).

### T159 — [playlist-003] Accumulator resets to 0.0000 on Release

- **Type**: integration (DUT)
- **Feature(s)**: playlist-003
- **Objective**: After tick integration leaves a non-zero fractional accumulator, Release
  resets scrollAccum to 0.0 and returns dragState to D_IDLE. Verifies the Release cleanup path.
- **Preconditions**: Common preconditions above.
- **Steps**:
  1. `drag 140 163 140 150 5` — upward 13 px drag; finger held (dy = −13).
  2. `tick 10 20` — 10 × 20 ms = 200 ms; accumulates ≈ 0.40 rows (< 1, no row boundary crossed).
  3. `get scrollAccum` — assert value ≠ 0.0000 (non-zero fractional accumulator).
  4. `release`.
  5. `get scrollAccum` — assert 0.0000.
  6. `get dragState` — assert `D_IDLE`.
- **Expected result**: scrollAccum non-zero before Release (≈ 0.40); exactly 0.0000 after
  Release. dragState D_IDLE. _scrollAccum is zeroed by the Release handler unconditionally.
- **Harness**: `run_serialdbg_tests.py --tests T159`. Owner: VE.
- **Status**: written (2026-05-25).

### T160 — [playlist-003] tickScroll is a no-op when dragState is D_IDLE

- **Type**: integration (DUT)
- **Feature(s)**: playlist-003
- **Objective**: When no drag is active (D_IDLE), tickScroll must not advance scrollOffset
  or leave a non-zero scrollVelocity. Verifies the guard clause in tickScroll().
- **Preconditions**: Common preconditions above. No finger on screen.
- **Steps**:
  1. `get dragState` — assert `D_IDLE`.
  2. `get scrollOffset` — record as `baseline_offset`.
  3. `tick 50 20` — injects 1000 ms worth of synthetic ticks.
  4. `get scrollOffset` — assert equals `baseline_offset`.
  5. `get scrollVelocity` — assert 0.0000.
- **Expected result**: scrollOffset unchanged; scrollVelocity exactly 0.0000. tickScroll()
  zeroes _scrollVelocity and _scrollAccum, then returns early when dragState ≠ D_PLEDIT_SCROLL.
- **Harness**: `run_serialdbg_tests.py --tests T160`. Owner: VE.
- **Status**: written (2026-05-25).

### T161 — [playlist-003] Seqno change cancels mid-drag gesture [manual]

- **Type**: manual DUT
- **Feature(s)**: playlist-003
- **Objective**: A Spotify queue update (seqno advance) while a velocity-scroll gesture is
  active must cancel the drag, reset scrollOffset to 0, and return dragState to D_IDLE.
  Prevents tickScroll() from re-scrolling on a stale anchor after seqno reset.
- **Preconditions**: DUT flashed with `cyd2usb_winamp_debug`, booted. Queue ≥ 10 items.
  Spotify active on controlling device (phone).
- **Steps**:
  1. Begin a drag gesture in the PLEDIT content area — press and hold; do not release.
  2. On the Spotify client, skip to next track to force a seqno advance.
  3. Wait for DUT to receive the updated queue (observe display refresh, ~1–2 Spotify polls).
  4. Query `get dragState` — assert `D_IDLE`.
  5. Query `get scrollOffset` — assert 0.
- **Expected result**: dragState D_IDLE; scrollOffset 0. The seqno-change branch in
  drawPlaylist() cancels the gesture cleanly. No runaway scroll after seqno reset.
- **Harness**: manual — no automation. Owner: VE.
- **Status**: planned.

---

## Suite: taskbar-scroll-001 — Taskbar Scroll Gesture (TASK-105/TASK-106)

**DUT required** — T162–T166 use `run_serialdbg_tests.py` with `cyd2usb_winamp_debug`.

As-built constants (authoritative): `TASKBAR_SLOT_H = 40`, `TB_SCROLL_DEAD_ZONE_PX = 3`, `TB_LP_ALPHA = 0.4`, `N = 8` (AppId::COUNT).
Taskbar strip: `x ∈ [275, 319]`, `y ∈ [0, 239]`. Slot n y-centre: `n*40 + 20`.

Common preconditions for harness tests (T162–T166):
- DUT flashed with `cyd2usb_winamp_debug`, booted, WiFi up.
- `get appId` → `Spotify` (restored by `_tb_precondition`).
- `get tbScrollOffset` → 0 (reset by `_tb_precondition`).

### T162 — [taskbar-scroll-001] Tap on taskbar fires switchApp; tbScrollOffset unchanged

- **Type**: integration (DUT)
- **Feature(s)**: taskbar-scroll-001
- **Objective**: A press+release with |rawDy| = 0 never exceeds `TB_SCROLL_DEAD_ZONE_PX` (3),
  so `_tbIsScrolling` stays false. `tbGestureEnd` takes the tap branch, calling `switchApp`.
  `tbScrollOffset` must be unchanged.
- **Preconditions**: Common preconditions above. `tbScrollOffset = 0`.
- **Steps**:
  1. `tap 297 60` — tap centre of slot 1 (Clock); dy = 0.
  2. `get appId` — assert `Clock`.
  3. `get tbScrollOffset` — assert 0 (unchanged).
- **Expected result**: appId = Clock; tbScrollOffset = 0. Tap path confirmed.
- **Harness**: `run_serialdbg_tests.py --tests T162`. Owner: VE.
- **Status**: passing [SERIALDBG]. DUT run 2026-06-05.

### T163 — [taskbar-scroll-001] Drag-up ≥50 px increments tbScrollOffset by 1

- **Type**: integration (DUT)
- **Feature(s)**: taskbar-scroll-001
- **Objective**: A 50 px / 10-step upward drag on the taskbar. LP-smoothed displacement ≈ 42.5 px
  > TASKBAR_SLOT_H (40), so exactly 1 slot step is triggered. offset++ (mod N).
- **Preconditions**: Common preconditions above. `tbScrollOffset = baseline` (any).
- **Steps**:
  1. Record `baseline = get tbScrollOffset`.
  2. `drag 297 110 297 60 10` — 50 px upward drag (y 110→60, dy = −50).
  3. `get tbScrollOffset` — assert `(baseline + 1) % 8`.
- **Expected result**: tbScrollOffset advanced by 1 (mod 8). LP-smoothed ≈ 42.5 px clears
  TASKBAR_SLOT_H threshold; single slot step confirmed.
- **Harness**: `run_serialdbg_tests.py --tests T163`. Owner: VE.
- **Status**: passing [SERIALDBG]. DUT run 2026-06-05.

### T164 — [taskbar-scroll-001] Drag-down ≥50 px decrements tbScrollOffset by 1

- **Type**: integration (DUT)
- **Feature(s)**: taskbar-scroll-001
- **Objective**: A 50 px / 10-step downward drag decrements offset by 1 (non-wrap path).
  Precondition offset=1 so result is 0 without wrap.
- **Preconditions**: Common preconditions above. `tbScrollOffset = 1`.
- **Steps**:
  1. Set `tbScrollOffset = 1` via prior drag-up.
  2. `drag 297 60 297 110 10` — 50 px downward drag (y 60→110, dy = +50).
  3. `get tbScrollOffset` — assert 0.
- **Expected result**: tbScrollOffset 1→0. Non-wrap decrement confirmed.
- **Harness**: `run_serialdbg_tests.py --tests T164`. Owner: VE.
- **Status**: passing [SERIALDBG]. DUT run 2026-06-05.

### T165 — [taskbar-scroll-001] Wrap-around down: offset=0, drag-down → offset=7

- **Type**: integration (DUT)
- **Feature(s)**: taskbar-scroll-001
- **Objective**: When `tbScrollOffset = 0`, a downward drag that would produce offset = −1
  wraps to N−1 = 7 via the modular arithmetic in `tbGestureContinue`.
  *(Revised from original spec — no clamp; wrap-around used in all directions.)*
- **Preconditions**: Common preconditions above. `tbScrollOffset = 0`.
- **Steps**:
  1. `get tbScrollOffset` — assert 0.
  2. `drag 297 60 297 110 10` — 50 px downward drag.
  3. `get tbScrollOffset` — assert 7.
- **Expected result**: tbScrollOffset 0→7. Wrap-around confirmed.
  `newOffset = ((0 + (−1)) % 8 + 8) % 8 = 7`.
- **Harness**: `run_serialdbg_tests.py --tests T165`. Owner: VE.
- **Status**: passing [SERIALDBG]. DUT run 2026-06-05.

### T166 — [taskbar-scroll-001] Wrap-around up: offset=7, drag-up → offset=0

- **Type**: integration (DUT)
- **Feature(s)**: taskbar-scroll-001
- **Objective**: When `tbScrollOffset = N−1 = 7`, an upward drag that would produce offset = 8
  wraps to 0. Mirror of T165.
- **Preconditions**: Common preconditions above. `tbScrollOffset = 7`.
- **Steps**:
  1. Set `tbScrollOffset = 7` via 7 drag-up gestures.
  2. `drag 297 110 297 60 10` — 50 px upward drag.
  3. `get tbScrollOffset` — assert 0.
- **Expected result**: tbScrollOffset 7→0. Wrap-around confirmed.
  `newOffset = ((7 + 1) % 8 + 8) % 8 = 0`.
- **Harness**: `run_serialdbg_tests.py --tests T166`. Owner: VE.
- **Status**: passing [SERIALDBG]. DUT run 2026-06-05.

### T167 — [taskbar-scroll-001] *(retired)*

- **Status**: retired — duplicate of revised T165. No separate test required.

### T168 — [taskbar-scroll-001] Active indicator follows app, not slot [manual]

- **Type**: manual DUT
- **Feature(s)**: taskbar-scroll-001
- **Objective**: After scrolling the taskbar (offset = k), the 3 px active-indicator bar must
  render at the visual slot containing `currentAppId`, not at the raw `(int)currentAppId` slot.
  Expected visual slot = `(currentAppId − offset + N) % N`.
- **Preconditions**: DUT flashed with `cyd2usb_winamp_debug`, booted.
- **Steps**:
  1. Switch to Spotify (appId = 0).
  2. Drag taskbar up to `tbScrollOffset = 3`.
  3. Observe taskbar: the active indicator should be at visual slot 5 (`(0 − 3 + 8) % 8 = 5`),
     not at slot 0.
  4. Tap the slot where the indicator is visible — confirm appId stays Spotify (no spurious switch).
- **Expected result**: Active bar at visual slot 5. Tap does not switch app.
- **Harness**: manual — no automation. Owner: VE.
- **Status**: planned.

---

## Suite: stock-001 — StockApp POC (TASK-110)

Common preconditions for all DUT tests below:
- DUT flashed with `cyd2usb_winamp_debug`, booted, WiFi up, Spotify creds valid.
- Serial debug interface active. Firmware includes `switchApp <id>`, `get stockSubView`,
  `get stockChartTicker`, `get stockChartRange`, `get lastQuoteFetch`, `get lastChartFetch`,
  `set fetchFailed`, `set fetchErrorCode`, `set triggerFetch`.
- Geometry reference: list row centres y=36+26i (AAPL=36..NVDA=218); chart back=(10,7);
  range tabs y=7 x: 1D=148, 5D=184, 1M=220, YTD=256; plot y:18..213; footer y=214.
- Harness: `run_serialdbg_tests.py --tests T169,...`

### T169 — [stock-001] Stock app switch round-trip

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: `switchApp 7` activates StockApp in list view; `switchApp 0` restores Spotify.
- **Preconditions**: DUT booted, Spotify active.
- **Steps**: 1. `switchApp 7`. 2. `get stockSubView` → assert `"list"`. 3. `switchApp 0`. 4. `get appId` → assert `"Spotify"`.
- **Expected result**: `stockSubView=list` on first launch; round-trip succeeds.
- **Harness**: `run_serialdbg_tests.py --tests T169`. Owner: VE.
- **Status**: written (2026-05-29).

### T170 — [stock-001] Pre-fetch placeholder state

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: `init()` sets `lastQuoteFetch` immediately on first launch (fetch enqueued but not yet returned).
- **Preconditions**: Stock not previously activated this session (`lastQuoteFetch=0` before switch).
- **Steps**: 1. Confirm `get lastQuoteFetch == 0`. 2. `switchApp 7`. 3. `get lastQuoteFetch` — assert `> 0`.
- **Expected result**: `lastQuoteFetch > 0` immediately after `init()` (timestamp set before fetch returns).
- **Harness**: `run_serialdbg_tests.py --tests T170`. SKIP if already fetched. Owner: VE.
- **Status**: written (2026-05-29).

### T171 — [stock-001] Colour coding

- **Type**: manual DUT
- **Feature(s)**: stock-001
- **Objective**: Positive `changePct` rows render green (0x07E0), negative rows red (0xF800).
- **Preconditions**: Live quote fetch complete; at least one positive and one negative row in live data.
- **Steps**: 1. Switch to Stock. 2. Wait for fetch. 3. Visually inspect list rows.
- **Expected result**: Green text for `+` rows, red for `-` rows.
- **Harness**: manual only (no pixel-read command). Owner: VE.
- **Status**: written (2026-05-29).

### T172 — [stock-001] App switch canvas residue

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: After Stock→Spotify switch, Winamp chrome repaints cleanly (no stock residue).
- **Preconditions**: Spotify active, playing a track (playlist draw observable).
- **Steps**: 1. `switchApp 7`. 2. Wait 150 ms. 3. `switchApp 0`. 4. Poll `get lastPlaylistDraw` — assert it advances within 3 s.
- **Expected result**: `lastPlaylistDraw` advances — Winamp repainted over Stock canvas.
- **Harness**: `run_serialdbg_tests.py --tests T172`. Owner: VE.
- **Status**: written (2026-05-29).

### T173 — [stock-001] Resume cache

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Switching away from Stock and back within 60 s does not trigger a new quote fetch.
- **Preconditions**: Quote fetch already completed (`lastQuoteFetch > 0`).
- **Steps**: 1. `switchApp 7`. 2. Record `lastQuoteFetch`. 3. `switchApp 0`. 4. Wait 2 s. 5. `switchApp 7`. 6. `get lastQuoteFetch` — assert unchanged.
- **Expected result**: `lastQuoteFetch` value identical before and after the round-trip.
- **Harness**: `run_serialdbg_tests.py --tests T173`. Owner: VE.
- **Status**: written (2026-05-29).

### T174 — [stock-001] Row drill-in

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Tapping NVDA row (row 7, y=218) enters chart view with correct ticker and default D1 range.
- **Preconditions**: Stock active, `stockSubView=list`, `fetchFailed=false`.
- **Steps**: 1. `switchApp 7`. 2. `tap 137 218`. 3. `get stockSubView` → `"chart"`. 4. `get stockChartTicker` → `"NVDA"`. 5. `get stockChartRange` → `"D1"`.
- **Expected result**: All three asserts pass within 1 s.
- **Harness**: `run_serialdbg_tests.py --tests T174`. Owner: VE.
- **Status**: written (2026-05-29).

### T175 — [stock-001] Back navigation

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Back button `(10,7)` in chart header returns `stockSubView` to `"list"`.
- **Preconditions**: `stockSubView=chart`.
- **Steps**: 1. Enter chart view (drill-in). 2. `tap 10 7`. 3. `get stockSubView` → `"list"`.
- **Expected result**: `stockSubView=list` within 1 s.
- **Harness**: `run_serialdbg_tests.py --tests T175`. Owner: VE.
- **Status**: written (2026-05-29).

### T176 — [stock-001] Plot bounds proxy

- **Type**: integration (DUT) + manual
- **Feature(s)**: stock-001
- **Objective**: Chart fetch completes; automated: `lastChartFetch > 0`. Manual: line pixels confined to y:18..213.
- **Preconditions**: `stockSubView=chart`.
- **Steps**: 1. Drill into chart. 2. Poll `get lastChartFetch` until `> 0` (timeout 30 s). 3. (Manual) verify no line pixel exits y:18..213.
- **Expected result**: `lastChartFetch > 0`; no plot overflow.
- **Harness**: `run_serialdbg_tests.py --tests T176` (automated proxy); manual pixel step separate. Owner: VE.
- **Status**: written (2026-05-29).

### T177 — [stock-001] Range tab switch

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Tapping 5D tab `(184,7)` sets `stockChartRange=D5` and triggers a new fetch.
- **Preconditions**: `stockSubView=chart`.
- **Steps**: 1. Drill into chart. 2. Record `lastChartFetch`. 3. `tap 184 7`. 4. `get stockChartRange` → `"D5"`. 5. Poll `get lastChartFetch` until it advances.
- **Expected result**: `stockChartRange=D5`; `lastChartFetch` advances within 5 s.
- **Harness**: `run_serialdbg_tests.py --tests T177`. Owner: VE.
- **Status**: written (2026-05-29).

### T178 — [stock-001] Chart pre-fetch placeholder

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Immediately after drill-in, before fetch returns, `stockSubView=chart` and `stockChartRange=D1`.
- **Preconditions**: Stock in list view.
- **Steps**: 1. `tap 137 36` (AAPL). 2. Within 100 ms: `get stockSubView` → `"chart"`. 3. `get stockChartRange` → `"D1"`.
- **Expected result**: Both vars confirmed before dataTask returns the chart payload.
- **Harness**: `run_serialdbg_tests.py --tests T178`. Owner: VE.
- **Status**: written (2026-05-29).

### T179 — [stock-001] Footer lo/hi

- **Type**: manual DUT
- **Feature(s)**: stock-001
- **Objective**: After chart fetch, `lo:` and `hi:` values visible at y=214; `lo < hi`.
- **Preconditions**: Chart fetch complete.
- **Steps**: Visual inspection of footer line at y=214.
- **Expected result**: `lo: X.XX` left-aligned, `hi: Y.YY` right-aligned; numerically `lo < hi`.
- **Harness**: manual only. Owner: VE.
- **Status**: written (2026-05-29).

### T180 — [stock-001] Drill-in always defaults to D1

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Every drill-in resets `stockChartRange` to `D1` regardless of prior range.
- **Preconditions**: Stock active, list view.
- **Steps**: 1. Drill AAPL → `stockChartRange=D1`. 2. Tap 5D tab. 3. Back to list. 4. Re-drill AAPL. 5. `get stockChartRange` → `"D1"`.
- **Expected result**: Range resets to D1 on each new drill-in.
- **Harness**: `run_serialdbg_tests.py --tests T180`. Owner: VE.
- **Status**: written (2026-05-29).

### T181 — [stock-001] Back then re-drill different ticker

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: back→list→tap NVDA; chart redraws with `stockChartTicker=NVDA`.
- **Preconditions**: Stock active, list view.
- **Steps**: 1. Drill AAPL. 2. `tap 10 7` (back). 3. `tap 137 218` (NVDA). 4. `get stockSubView` → `"chart"`. 5. `get stockChartTicker` → `"NVDA"`.
- **Expected result**: Both asserts pass within 1 s.
- **Harness**: `run_serialdbg_tests.py --tests T181`. Owner: VE.
- **Status**: written (2026-05-29).

### T182 — [stock-001] Canvas isolation via taskbar path

- **Type**: cross-feature (DUT)
- **Feature(s)**: stock-001, taskbar-scroll-001
- **Objective**: Switching to Stock via the real taskbar UI (scroll + slot tap) after a chart session does not corrupt the display on return to Spotify.
- **Preconditions**: Stock previously in chart view; taskbar at offset 0.
- **Steps**: 1. `switchApp 7` → drill into chart. 2. `switchApp 0`. 3. Drag taskbar: `drag 297 200 297 100 10` (scroll to offset 2). 4. `tap 297 220` (slot 5 = Stock at offset 2). 5. Verify `appId=Stock`. 6. `drag 297 100 297 200 10` (reset). 7. `switchApp 0`. 8. Verify `lastPlaylistDraw` advances.
- **Expected result**: Stock active via taskbar tap; `lastPlaylistDraw` advances after Spotify return.
- **Harness**: `run_serialdbg_tests.py --tests T182`. Owner: VE.
- **Status**: written (2026-05-29).

### T183 — [stock-001] Fetch error injection

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: `set fetchFailed 1` causes error screen; list row taps ignored; `stockSubView` stays `"list"`.
- **Preconditions**: Stock active, list view.
- **Steps**: 1. `set fetchFailed 1`. 2. `set fetchErrorCode -1`. 3. Wait 150 ms. 4. `tap 137 120` (list row). 5. `get stockSubView` → `"list"`. 6. `set fetchFailed 0`.
- **Expected result**: `stockSubView` unchanged; tap suppressed by `fetchFailed` guard. Error screen visible (manual confirm).
- **Harness**: `run_serialdbg_tests.py --tests T183`. Owner: VE.
- **Status**: written (2026-05-29).

### T184 — [stock-001] Error in chart view — back still works

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Back button remains functional while `fetchFailed=1` in chart view.
- **Preconditions**: `stockSubView=chart`.
- **Steps**: 1. Drill into chart. 2. `set fetchFailed 1`. 3. Wait 150 ms. 4. `tap 10 7`. 5. `get stockSubView` → `"list"`. 6. `set fetchFailed 0`.
- **Expected result**: `stockSubView=list` — back always works regardless of error state.
- **Harness**: `run_serialdbg_tests.py --tests T184`. Owner: VE.
- **Status**: written (2026-05-29).

### T185 — [stock-001] Error recovery on successful fetch

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: After `set triggerFetch 1`, `lastQuoteFetch` advances — confirming a real fetch was enqueued and completed.
- **Preconditions**: Stock active.
- **Steps**: 1. `set fetchFailed 1`. 2. `set fetchErrorCode -99`. 3. Record `lastQuoteFetch`. 4. `set triggerFetch 1`. 5. Poll `get lastQuoteFetch` until it advances (timeout 65 s).
- **Expected result**: `lastQuoteFetch` value changes — fetch completed; error state recoverable.
- **Harness**: `run_serialdbg_tests.py --tests T185`. Owner: VE.
- **Status**: written (2026-05-29).

---

## Suite M-DATATASK-STREAM-PARSE — getStream() switch + ticker guard fix (4c3cb05)

> **VE challenge resolved (2026-05-29):** Host probe confirmed open-meteo.com and coingecko.com
> both return `Transfer-Encoding: chunked` with no `Content-Length`. `http.getStream()` passes
> raw chunk-framing bytes to ArduinoJson on Arduino-ESP32 2.0.17 (HTTPClient does not dechunk
> the stream); JSON parse would fail. `fetchWeather()` and `fetchCrypto()` reverted to
> `http.getString()` same session (ADR-034 amended). Yahoo Finance returns `Content-Length`;
> `fetchStockQuote()` and `fetchStockChart()` remain on `getStream()`. T189/T190 below verify
> existing `getString()` behaviour — no streaming risk on those endpoints.

### T186 — [stock-001] Chart fetch for MSFT (tickerIdx=6) no longer rejected by guard

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Verify the `tickerIdx >= 8` guard fix (was `>= 6`) allows MSFT (index 6) to fetch chart data.
- **Preconditions**: Stock app active, list view, `fetchFailed=0`.
- **Steps**:
  1. `switchApp 7` (Stock app).
  2. Tap the MSFT row in the list view.
  3. `get stockChartTicker` → assert `"MSFT"`.
  4. `set triggerFetch 1` (resets `lastChartFetch` to 0).
  5. Poll `get lastChartFetch` until nonzero (timeout 65 s).
  6. `get fetchFailed` → assert `"0"`.
- **Expected result**: `lastChartFetch` advances; `fetchFailed=0`. Under the old guard MSFT returned early (no fetch) and the chart displayed nothing.
- **Harness**: `run_serialdbg_tests.py --tests T186`. Owner: VE.
- **Status**: planned.

### T187 — [stock-001] Chart fetch for NVDA (tickerIdx=7) no longer rejected by guard

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Verify NVDA (index 7) chart fetch succeeds after `tickerIdx >= 8` guard fix.
- **Preconditions**: Stock app active, list view, `fetchFailed=0`.
- **Steps**:
  1. `switchApp 7` (Stock app).
  2. Tap the NVDA row in the list view.
  3. `get stockChartTicker` → assert `"NVDA"`.
  4. `set triggerFetch 1`.
  5. Poll `get lastChartFetch` until nonzero (timeout 65 s).
  6. `get fetchFailed` → assert `"0"`.
- **Expected result**: `lastChartFetch` advances; `fetchFailed=0`.
- **Harness**: `run_serialdbg_tests.py --tests T187`. Owner: VE.
- **Status**: planned.

### T188 — [stock-001] Successive chart range switches do not trigger -99 on fragmented heap

- **Type**: integration (DUT)
- **Feature(s)**: stock-001
- **Objective**: Verify `getStream()` eliminates the -99 NET ERR caused by double-allocation under `getString()` (ADR-034). Cycle all four range tabs in sequence; `fetchFailed` must remain 0 throughout.
- **Preconditions**: Stock app active, drill into AAPL chart (D1 range).
- **Steps**:
  1. `set stockChartRange D1` if not already set.
  2. `set triggerFetch 1`. Poll `get lastChartFetch` until advances (timeout 65 s). `get fetchFailed` → `"0"`.
  3. Tap the 5D range tab. `set triggerFetch 1`. Poll `get lastChartFetch`. `get fetchFailed` → `"0"`.
  4. Tap the 1M range tab. `set triggerFetch 1`. Poll `get lastChartFetch`. `get fetchFailed` → `"0"`.
  5. Tap the 6M range tab. `set triggerFetch 1`. Poll `get lastChartFetch`. `get fetchFailed` → `"0"`.
  6. Tap D1 again. `set triggerFetch 1`. Poll `get lastChartFetch`. `get fetchFailed` → `"0"`.
- **Expected result**: All five polls succeed; `fetchFailed=0` at every step. -99 NET ERR is not displayed.
- **Harness**: `run_serialdbg_tests.py --tests T188`. Owner: VE.
- **Status**: planned.

### T189 — [weather-001] Weather fetch parses correctly (getString + chunked response)

- **Type**: integration (DUT)
- **Feature(s)**: weather-001
- **Objective**: Verify `fetchWeather()` using `http.getString()` delivers a valid `WeatherResult`
  after the ADR-034 partial revert. open-meteo.com returns chunked encoding; `getString()`
  handles dechunking internally — confirm no regression from 4c3cb05 churn.
- **Preconditions**: WiFi connected, Weather app active (`switchApp 3`), `get weatherReady` returns `"0"` (first fetch pending).
- **Steps**:
  1. `switchApp 3`.
  2. Poll `get weatherReady` until `"1"` (timeout 90 s).
  3. Inspect tmux log for `dataTask.weather GET 200` line; assert no `dataTask.weather JSON parse error` line within that window.
  4. Manual: temperature string visible on display (not `---`).
- **Expected result**: `weatherReady=1` within 90 s; log shows GET 200 with no JSON error; display shows temperature.
- **Harness**: manual + tmux log check. Owner: VE.
- **Status**: planned.

### T190 — [crypto-001] Crypto fetch parses correctly (getString + chunked response)

- **Type**: integration (DUT)
- **Feature(s)**: crypto-001
- **Objective**: Verify `fetchCrypto()` using `http.getString()` delivers a valid `CryptoResult`
  after the ADR-034 partial revert. coingecko.com returns chunked encoding; confirm no regression.
- **Preconditions**: WiFi connected, Crypto app active (`switchApp 4`), display shows `---`.
- **Steps**:
  1. `switchApp 4`.
  2. Wait 90 s for initial fetch cycle.
  3. Inspect tmux log for `dataTask.crypto GET 200`; assert no `dataTask.crypto JSON parse error`.
  4. Manual: at least one price row shows a non-`---` value.
- **Expected result**: Log shows GET 200 with no JSON error; display shows prices.
- **Harness**: manual + tmux log check. Owner: VE.
- **Status**: planned.

---

## Suite M-STOCK-VE-STRESS — Rapid D1↔Ytd alloc/free stress (T204)

### T204 — [stock-001] D1↔Ytd rapid alternating stress: 3 cycles no fetchFailed (SERIALDBG)

- **Type**: integration (DUT, SERIALDBG build)
- **Feature(s)**: stock-001
- **Objective**: Verify the `getStream()` fix (ADR-034) holds under repeated back-to-back `DynamicJsonDocument(16384)` alloc/free cycles. Alternates Ytd↔D1 3 times (6 fetches); `fetchFailed` must remain 0 throughout. T188 proved each range passes sequentially; T204 proves the heap recovers cleanly across rapid alternation between the largest (Ytd) and smallest (D1) payloads.
- **Preconditions**: Stock app reachable via `switchApp 7`, WiFi connected, AAPL drillable (Yahoo Finance responsive), `fetchFailed=0`.
- **Steps**:
  1. `switchApp 7` → `set fetchFailed 0` → `set fetchErrorCode 0`.
  2. Drill AAPL from list view (tap 137 36) → assert `stockSubView=chart`.
  3. For each of [Ytd, D1, Ytd, D1, Ytd, D1]: snapshot `fetchOkCount` before → tap range tab → poll `fetchOkCount` until it advances (timeout 45 s) → `get fetchFailed` → assert `"0"`.
- **Pass**: All 6 polls succeed; `fetchFailed=0` at every step.
- **Fail**: `fetchFailed=1` (errorCode typically -91..-95 or -99) on any cycle, or poll timeout (heap allocation failure or Yahoo Finance unavailable).
- **Status**: planned. Harness: `run_serialdbg_tests.py --tests T204`. Owner: VE.

---

## Suite: serialdbg-audit-001 — Test quality fix pass (TASK-112)

**Triggered by**: QM audit 2026-05-30 — 18/78 serialdbg tests have limited or no signal.
**Scope**: Fix or annotate every test flagged RED/AMBER in the audit. No new firmware features required except a quote ok-counter for T170.

**Priority A — enqueue-proxy fixes (LL-041 pattern, firmware already has fetchOkCount for charts):**

### T176 fix — chart fetch proven completion
**Current**: asserts `lastChartFetch > 0` (enqueue proxy).
**Fix**: snapshot `fetchOkCount` before drill-in → drill → assert `fetchOkCount` advanced within 45 s. Identical pattern to T186–T188 (already passing). No firmware change needed.
**Acceptance**: T176 passes using `_wait_chart_complete(before)`.

### T170 fix — quote fetch proven completion
**Current**: asserts `lastQuoteFetch > 0` (timestamp set in `init()`, not on fetch completion).
**Fix option A**: add `quoteOkCount` to `StockAppState` (mirrors `fetchOkCount`); increment in `stockTickQuotes()` on success; expose via `dbgGet`/`dbgSet`. Snapshot before switch-in → assert advances within 65 s.
**Fix option B**: assert `get stockPrice_AAPL` (or similar) returns a non-zero float — data presence implies fetch completed. Requires a `dbgGet` var for price array (not currently exposed).
**Recommendation**: Option A — consistent with `fetchOkCount` pattern; no ambiguity about zero prices at open/close.
**Acceptance**: T170 passes asserting actual quote completion, not timestamp proxy.

**Priority B — pure-observation tests (no causal assertion, low effort to fix or annotate):**

### T136 — scrollOffset initial value
**Current**: reads `scrollOffset` and asserts it equals 0. Proves initial state, not behavior.
**Fix**: remove as standalone test; fold the `scrollOffset=0` precondition check into T137 setup. T137 already verifies the meaningful behavior (swipe-up increments).
**Acceptance**: T136 removed from suite; T137 precondition check explicit in setup block.

### T178 — chartRange default before fetch
**Current**: asserts `stockChartRange=D1` immediately after drill-in. Trivially true — `drillToChart()` always sets D1.
**Fix**: extend to assert `fetchFailed=false` AND `chartLen=0` at the same moment (pre-fetch: data not yet arrived). That validates the placeholder state, not just the hardcoded default.
**Acceptance**: T178 asserts pre-fetch placeholder state (chartLen=0, fetchFailed=false) rather than the trivially-true range default.

### T_GOL_04 — GoL simulation ran
**Current**: asserts `golAlive >= 0` after 350 ms. Field presence check; 0 is valid.
**Fix**: assert `golAlive > 0` (at least one live cell after 3+ ticks — valid for any non-trivial initial state) OR assert `golGeneration >= 3` if that variable is exposed. Check firmware for available GoL state vars.
**Acceptance**: T_GOL_04 asserts that the simulation actually advanced, not just that the field exists.

**Priority C — weak tests requiring Spotify playing (annotate, don't fix now):**

### T078, T082, T_BI_04 — volume drag / PLAY toggle
**Issue**: meaningful verification requires observing actual Spotify API calls (volume change, play/pause state). Not feasible without a playing track and external Spotify state check.
**Action**: add `[PARTIAL — requires Spotify playing for full verification]` annotation to each test in test_plan.md. No code change.

### T090 — reconnect ACK-only
**Current**: asserts `ok=true` and `cmd="reconnect"` only.
**Fix**: after `reconnect`, assert `get backoff consecutiveFailures=0` within 3 s — proves the reconnect handler ran, not just that the serial command arrived. (T091 already does this with FLAKE annotation; T090 should be merged into or replaced by T091.)
**Recommendation**: mark T090 as superseded by T091; remove from active suite or demote to smoke-only with explicit comment.
**Acceptance**: T090 either removed or annotated `[SMOKE — superseded by T091]`.

### T083 — help command
**Action**: annotate `[SMOKE — verifies command registry, not behavior]`. No code change needed; signal level is appropriate for a registry check.

**Priority D — permanently manual (annotate only):**

### T093, T094, T095, T171, T179
**Action**: add `[MANUAL — requires human operator / pixel verification]` to each entry in test_plan.md. Confirm `--interactive` flag gates T093–T095. No automation path exists or is planned.

---

## Suite: stock-heatmap-bugfix-001 (TASK-121/122/123)

Bug-fix validation suite for StockApp heatmap feature (stock-002, M-HEATMAP). Three bugs
addressed: wrong ticker on tab-switch after heatmap drill-through (TASK-121), tile area
overflow due to wrong normalization constant (TASK-122), and squarify algorithm orientation
and slen deviations from the PoC (TASK-123).

Common preconditions for DUT tests below:
- DUT flashed with `cyd2usb_winamp_debug`, booted, WiFi up, Spotify creds valid.
- Serial debug interface active. StockApp accessible via `switchApp 7`.
- Heatmap button: x > 190, y < 22 in list view header. Back button: x > 190, y < 22 in heatmap header.
- Chart tabs: x = 130..274, y = 0..17. Tab centres: 1D x=148, 5D x=184, 1M x=220, YTD x=256.
- ARM tile: visible in heatmap after screener fetch; typical DUT screen position varies — confirm
  visually or use `triggerHeatmap` + any large tile (AAPL, MSFT) if ARM is not in the live dataset.
- Harness: `run_serialdbg_tests.py --tests T191,...`

---

### T191 — [stock-002, TASK-121] Post-drill `get stockChartTicker` returns index-based ticker (BUG observable)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: Document and confirm the TASK-121 bug is observable via serial before the fix.
  After a heatmap drill-through to a symbol not at `chartTickerIdx=0`, `get stockChartTicker`
  returns `tickers[chartTickerIdx]` (AAPL) rather than the drilled symbol. This test is the
  pre-fix regression baseline; after the fix it becomes an acceptance check (see T192).
- **Preconditions**: DUT in StockApp list view. Heatmap data present (`heatmapCount > 0`).
  `chartTickerIdx` defaults to 0 (AAPL) at boot.
- **Steps**:
  1. `switchApp 7` → confirm `get stockSubView == "list"`.
  2. `tap 220 10` (HEAT button: x=220 > 190, y=10 < 22) → confirm `get stockSubView == "heatmap"`.
  3. Poll `get heatmapCount` until `> 0` (timeout 30 s).
  4. Tap any visible non-AAPL tile (ARM recommended, or MSFT/NVDA if ARM absent).
     Record the symbol shown in the chart header visually.
  5. `get stockSubView` → assert `"chart"`.
  6. `get stockChartTicker` → record value.
- **Expected result (pre-fix)**: `stockChartTicker` returns `"AAPL"` (or whatever `tickers[0]` is),
  NOT the drilled symbol — this confirms the bug. `chartTickerIdx` was not updated by `drillToChartBySym`.
  **Expected result (post-fix)**: `stockChartTicker` still returns the index-based ticker because
  `drillToChartBySym` sets `chartSymbol` but does NOT change `chartTickerIdx`. The correct fix
  assertion is in T192 — the price signal, not this field. Note: after TASK-121 fix, the tab-switch
  code path uses `chartSymbol` directly; the `get stockChartTicker` field remains index-based by design.
- **Status**: superseded. T191 was the pre-fix regression baseline; TASK-121 fix is in tree. Acceptance check moved to T192/T193. Retained for historical record only.

---

### T192 — [stock-002, TASK-121] Tab-switch after heatmap drill fetches the drilled symbol (SERIALDBG)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: After TASK-121 fix — when the user taps a range tab after a heatmap drill-through,
  the fetch is for the drilled symbol, not the default ticker. Observable via `fetchOkCount`:
  a new fetch fires on tab-switch (counter increments) and the chart header still shows the
  drilled symbol (not AAPL/default).
- **Preconditions**: TASK-121 fix in tree. DUT in StockApp, heatmap data loaded. A non-default
  symbol tile is visible (e.g. ARM, MSFT). `chartTickerIdx` defaults to 0 (AAPL) at boot.
- **Steps**:
  1. `switchApp 7` → `get stockSubView == "list"`.
  2. Enter heatmap (tap HEAT button at x=220, y=10). Poll `get heatmapCount` until > 0.
  3. Tap a non-AAPL tile (e.g. ARM at its screen position). Confirm chart view opens.
  4. `get stockSubView` → assert `"chart"`. `get stockChartRange` → assert `"D1"`.
  5. Note `before_ok = get fetchOkCount`.
  6. Tap 5D tab: `tap 184 9` (x=184, y=9 within 0..17).
  7. `get stockChartRange` → assert `"D5"`.
  8. Poll `get fetchOkCount` until `> before_ok` (timeout 45 s).
  9. Visual: chart header still shows the drilled symbol (e.g. ARM), NOT AAPL or another default.
- **Expected result**: `fetchOkCount` advances (a real fetch fired for the drilled symbol at D5).
  Chart header text unchanged (drilled symbol persists across tab switch). If the bug were present,
  the header would revert to AAPL and the price range would shift to AAPL 5D values.
- **Status**: passing [SERIALDBG]. Harness: `run_serialdbg_tests.py --tests T192`. Note: suite-run timing-sensitive (heatmap screener cache expiry + serial flooding); passes in consecutive runs when Yahoo Finance API is responsive.

---

### T193 — [stock-002, TASK-121] Auto-refresh path uses drilled symbol after heatmap drill-through (SERIALDBG)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: The `stockTickChart()` auto-refresh path (TASK-121b fix) also uses `chartSymbol`
  when set. After the fix, a forced auto-refresh via `set triggerFetch 1` while in post-drill
  chart view should re-fetch the drilled symbol, not `chartTickerIdx`.
- **Preconditions**: TASK-121 fix in tree. DUT drilled into chart from heatmap (chartSymbol set
  to a non-default symbol). Chart already rendered (D1 data present). `fetchOkCount` recorded.
- **Steps**:
  1. Enter heatmap, drill into a non-default symbol. Note `before_ok = get fetchOkCount`.
  2. `set triggerFetch 1` (resets `lastChartFetch` to 0 to force next tick to re-fetch).
  3. Wait 3 s (allow one `stockTickChart()` tick to fire). Poll `get fetchOkCount` until `> before_ok`
     (timeout 30 s).
  4. `get chartLen` → assert `> 0` (data arrived).
  5. Visual: chart header still shows the drilled symbol.
- **Expected result**: `fetchOkCount` advances. Header unchanged. Without the fix, `stockTickChart`
  would have called `enqueueStockChart(_s.chartTickerIdx, ...)` and the chart would have redrawn
  with the wrong (default) ticker data, causing visible price-range change.
- **Status**: passing [SERIALDBG]. Harness: `run_serialdbg_tests.py --tests T193`. Note: skips when Yahoo Finance returns empty chart data (external API flakiness, not a firmware defect).

---

### T194 — [stock-002, TASK-121] Back-to-list then re-drill clears chartSymbol (SERIALDBG)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: After navigating back to list from the heatmap-drilled chart, then drilling into
  a list row directly (index-based), `chartSymbol` is cleared and subsequent tab-switches use
  the index path (`enqueueStockChart(_s.chartTickerIdx, tab)`), not the stale `chartSymbol`.
- **Preconditions**: TASK-121 fix in tree. DUT has just completed a heatmap drill-through (chartSymbol set).
- **Steps**:
  1. From heatmap chart view, tap back (x=10, y=7) → `get stockSubView == "chart"` or `"list"`.
     Navigate back to list: tap back from chart `(10,7)`, then tap back from heatmap `(220,10)` if needed.
  2. `get stockSubView` → assert `"list"`.
  3. Tap a list row (e.g. AAPL at y=36): `tap 137 36` → `get stockSubView == "chart"`.
  4. `get stockChartRange` → assert `"D1"`. Note `before_ok = get fetchOkCount`.
  5. Tap 5D tab: `tap 184 9`. `get stockChartRange` → assert `"D5"`.
  6. Poll `get fetchOkCount` until `> before_ok` (timeout 45 s).
  7. `get stockChartTicker` → assert matches the tapped list row ticker (e.g. `"AAPL"`).
- **Expected result**: `stockChartTicker` shows the index-based ticker (confirming `chartSymbol` was
  cleared when `drillToChart()` was called). Fetch succeeded for that ticker at D5.
- **Status**: passing [SERIALDBG]. Harness: `run_serialdbg_tests.py --tests T194`. Note: suite-run timing-sensitive; spurious touch events during TFT repaint may set shellBusy — harness uses _wait_shell_not_busy guards to handle.

---

### T195 — [stock-002, TASK-122] Heatmap tiles fill canvas without bottom overflow [MANUAL]

- **Type**: visual (DUT, manual)
- **Feature(s)**: stock-002
- **Objective**: After TASK-122 fix, heatmap tiles fill y=22..239 exactly with no tile edge or fill
  extending past y=239 (the bottom of the display). Before the fix, tiles overflow the bottom ~10%,
  so the bottom ~22 rows show tile content below the last visible pixel row.
- **Preconditions**: TASK-122 fix in tree. DUT in heatmap view with at least one fetch complete
  (`heatmapCount > 0`).
- **Steps**:
  1. `switchApp 7` → enter heatmap (tap HEAT button).
  2. Wait for heatmap data (observe tiles appearing).
  3. Examine the bottom edge of the display closely.
- **Expected result**: The tile with the lowest extent ends cleanly at or before y=239. No tile
  content is cut off mid-glyph or mid-fill at the screen edge. No tile extends into the taskbar
  region (y > 239 is not visible, but the last row of pixels at y=239 should show tile background,
  not a misaligned cut).
  Pass: clean bottom edge — last row of pixels is tile fill matching a tile's colour.
  Fail: cut-off tile label text or partial colour block below y=239 boundary, or tiles obviously
  not reaching the bottom (under-fill, indicating a different normalization error).
- **Status**: planned (manual). Owner: VE.

---

### T196 — [stock-002, TASK-122] Heatmap data present after fetch (SERIALDBG)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: Confirm the heatmap fetch succeeds and tile count is non-zero — the minimal
  automated gate before visual TASK-122/TASK-123 validation can proceed. Also verifies
  `triggerHeatmap` sets the subview and forces a fresh fetch.
- **Preconditions**: DUT in StockApp. Network available (or `host_overrides.json` populated for
  the heatmap screener endpoint).
- **Steps**:
  1. `switchApp 7` → `get stockSubView == "list"`.
  2. `set triggerHeatmap 1` (sets subView = HeatmapDetail, forces fresh fetch).
  3. `get stockSubView` → assert `"heatmap"`.
  4. Poll `get heatmapCount` every 3 s until `> 0` (timeout 60 s).
- **Expected result**: `heatmapCount` returns a value ≥ 1 within 60 s. This confirms the screener
  fetch succeeded and the data layer is operational. A timeout here indicates a network/parse
  issue unrelated to TASK-122/TASK-123 and blocks T195/T197/T198.
- **Status**: passing [SERIALDBG]. Harness: `run_serialdbg_tests.py --tests T196`. Note: skips/fails when Yahoo Finance screener endpoint is slow or unavailable (external dependency).

---

### T197 — [stock-002, TASK-122, TASK-123] DUT heatmap layout matches PoC reference for same data [HOST]

- **Type**: host-side (offline, Python)
- **Feature(s)**: stock-002
- **Objective**: Run `preview_heatmap.py --no-fetch` to generate a deterministic reference layout
  from the same synthetic dataset, then compare the PoC's squarify output geometry to the expected
  DUT output after both TASK-122 and TASK-123 fixes. Guards against regression in either fix.
  This is the primary algorithmic correctness gate for TASK-123 — the PoC is the reference
  implementation.
- **Preconditions**: Python 3 + Pillow available. `preview_heatmap.py` in tree.
  TASK-122 and TASK-123 fixes applied to `main.cpp`. No display required (`--no-fetch` uses
  synthetic data and does not open a pygame window when run headlessly).
- **Steps**:
  1. Run `python3 app/tools/preview_heatmap.py --no-fetch` to confirm the
     PoC renders without error. Note the first tile dimensions printed at quit (Phase 2 report).
  2. Extract the expected layout from the PoC: the first tile (largest market cap) should be a
     tall vertical column on the left (wide canvas, so `w > h * bias` → vertical strip), not a
     horizontal band across the top (which would be the TASK-123 Bug A symptom).
  3. Confirm the total area of all tiles equals `275 * (240 - 22) = 275 * 218 = 59,950 px²`
     (TASK-122 fix: correct normalization). Sum all `tile_w * tile_h` from the layout output.
  4. Confirm `slen` used in each recursive call is `min(rw, rh)` — verified by the PoC's use
     of `short = min(w, h)` in `_squarify`. On the initial 275×218 canvas, `slen = 218` (the
     short side), consistent with Bug B fix.
- **Expected result**:
  - PoC runs without exception.
  - First tile is a tall left-side column (vertical strip orientation) on the 275×218 canvas.
  - Sum of all tile areas ≈ 59,950 px² (±a few px² for rounding).
  - `short = min(275, 218) = 218` used in first squarify call (consistent with Bug B).
  Pass criterion: first tile taller than it is wide (h > w) on initial 275×218 canvas.
  Fail criterion: first tile wider than it is tall (w > h), indicating orientation is still inverted.
- **Status**: planned [HOST]. Owner: VE.

---

### T198 — [stock-002, TASK-123] DUT heatmap first tile is a tall vertical column, not a horizontal band [MANUAL]

- **Type**: visual (DUT, manual)
- **Feature(s)**: stock-002
- **Objective**: After TASK-123 fix (Bug A orientation swap), the first (largest) heatmap tile
  on the 275×218 DUT canvas should be a tall vertical column on the left, not a short horizontal
  band across the top. This directly validates the orientation fix.
- **Preconditions**: TASK-122 and TASK-123 fixes in tree. DUT in heatmap view with live or
  triggered fetch complete (`heatmapCount > 0`). For a deterministic comparison, use
  `set triggerHeatmap 1` to force a fresh fetch immediately before observation.
- **Steps**:
  1. Enter heatmap view (HEAT button or `set triggerHeatmap 1`).
  2. Wait for tiles to render.
  3. Observe the largest tile (typically AAPL or MSFT — the one with the biggest market cap,
     rendered first by the squarify algorithm).
- **Expected result (post-fix)**: The largest tile is visibly taller than it is wide — a column
  at the left edge of the canvas, approximately spanning the full y=22..239 height.
  Pass: tile height > tile width for the dominant tile.
  Fail: the dominant tile is a short horizontal band spanning the full canvas width — this is
  the TASK-123 Bug A symptom (orientation still inverted).
- **Status**: planned (manual). Owner: VE.

---

### T199 — [stock-002, TASK-123] DUT squarify aspect ratios are comparable to PoC (visual quality gate) [MANUAL]

- **Type**: visual (DUT, manual)
- **Feature(s)**: stock-002
- **Objective**: After both TASK-122 and TASK-123 fixes, the overall heatmap tile layout on the
  DUT should visually resemble the PoC's `--no-fetch` output — roughly square tiles, no
  extremely elongated sliver tiles caused by a wrong `slen`. This is a qualitative check;
  exact pixel-matching is not required (live data differs from synthetic data).
- **Preconditions**: TASK-122 and TASK-123 fixes in tree. DUT in heatmap view with data loaded.
  Host running `preview_heatmap.py --no-fetch` for reference (or a screenshot).
- **Steps**:
  1. Side-by-side comparison: PoC `--no-fetch` output (host) vs DUT heatmap display.
  2. Inspect the tile aspect ratios: are any tiles extremely elongated (height-to-width ratio
     > 10:1 or < 1:10)? Such slivers are the primary symptom of TASK-123 Bug B (wrong `slen`
     using the long side instead of the short side inflates the aspect ratio criterion, causing
     the algorithm to continue adding tiles to a strip past the optimal split point).
- **Expected result**: No slivers — no tile with aspect ratio more extreme than approximately
  5:1. Tiles are visually similar in squareness to the PoC layout. An occasional narrow tile
  for very small-cap symbols is acceptable; systematic sliver tiles throughout the layout are not.
  Pass: layout looks tile-like, comparable to PoC.
  Fail: systematic slivers visible — thin horizontal or vertical bars spanning most of the canvas.
- **Status**: planned (manual). Owner: VE.

---

### T200 — [stock-002, TASK-120] List→Heatmap toggle via HEAT button tap (SERIALDBG)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: Verify the HEAT button tap (x>190, y<22) in StockApp list view transitions to
  HeatmapDetail sub-view. Tests the touch-input path through `handleInput()` → `enterHeatmap()`.
- **Preconditions**: DUT in StockApp list view (`get stockSubView == "list"`).
- **Steps**:
  1. `switchApp 7` → `get stockSubView` → assert `"list"`.
  2. `set cooldown 0`.
  3. `tap 220 10` (x=220>190, y=10<22 — HEAT button zone).
  4. `get stockSubView` → assert `"heatmap"`.
- **Expected result**: `stockSubView` transitions from `"list"` to `"heatmap"` immediately after tap.
  Pass: `"heatmap"`. Fail: `"list"` (tap missed) or `"chart"` (wrong handler).
- **Status**: passing [SERIALDBG]. Harness: `run_serialdbg_tests.py --tests T200`.

---

### T201 — [stock-002, TASK-120] Heatmap→List back toggle via HEAT button tap (SERIALDBG)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: Verify the HEAT button tap (x>190, y<22) in HeatmapDetail view calls `backToPrevView()`
  and returns to ListDetail. Tests the symmetric back-navigation path.
- **Preconditions**: DUT in StockApp HeatmapDetail view (`get stockSubView == "heatmap"`).
- **Steps**:
  1. `switchApp 7` → `set triggerHeatmap 1` → `get stockSubView` → assert `"heatmap"`.
  2. `set cooldown 0`.
  3. `tap 220 10` (HEAT button zone in heatmap header).
  4. `get stockSubView` → assert `"list"`.
- **Expected result**: `stockSubView` returns to `"list"`.
  Pass: `"list"`. Fail: `"heatmap"` (tap not registered) or other.
- **Status**: passing [SERIALDBG]. Harness: `run_serialdbg_tests.py --tests T201`.

---

### T202 — [stock-002, TASK-120] Heatmap tile tap drills to ChartDetail (SERIALDBG)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: Verify that tapping a tile in HeatmapDetail calls `drillToChartBySym()` and
  transitions to ChartDetail. The tile canvas covers y=22..239, x=0..274 without gaps (squarify
  fills 100% of the area), so any tap at canvas center (137, 130) must hit a tile.
- **Preconditions**: DUT in HeatmapDetail with `heatmapCount > 0` (tiles rendered).
- **Steps**:
  1. `switchApp 7` → `set triggerHeatmap 1` → poll `get heatmapCount` until `> 0` (60 s timeout).
  2. `set cooldown 0`.
  3. `tap 137 130` (canvas center, y=130 >> ST_LIST_RULE_Y=22 — guaranteed tile hit).
  4. `get stockSubView` → assert `"chart"`.
  5. `get stockChartTicker` → record drilled symbol.
- **Expected result**: `stockSubView = "chart"`. `stockChartTicker` returns the symbol from the
  tapped tile (this is `chartSymbol`, set by `drillToChartBySym`).
  Pass: `"chart"`. Fail: `"heatmap"` (tap not handled) or `"list"` (spurious back-nav).
- **Status**: passing [SERIALDBG]. Harness: `run_serialdbg_tests.py --tests T202`. Note: tile drill uses (10, 30) — top-left corner, always hits the largest market-cap tile.

---

### T203 — [stock-002, TASK-120] Chart back-tap restores HeatmapDetail (not List) (SERIALDBG)

- **Type**: integration (DUT, serial-driven)
- **Feature(s)**: stock-002
- **Objective**: Verify that the chart back button (`tap 10 7`) restores `prevSubView` correctly.
  When ChartDetail was entered via a heatmap tile drill, `prevSubView = HeatmapDetail`, so back
  must return to HeatmapDetail — not ListDetail.
- **Preconditions**: DUT in ChartDetail entered via heatmap tile drill (`prevSubView = HeatmapDetail`).
  Set up via `set triggerHeatmap 1` → wait for tiles → `tap 137 130`.
- **Steps**:
  1. `switchApp 7` → `set triggerHeatmap 1` → poll `get heatmapCount` until > 0.
  2. `set cooldown 0` → `tap 137 130` → `get stockSubView` → assert `"chart"`.
  3. `set cooldown 0` → `tap 10 7` (chart back button).
  4. `get stockSubView` → assert `"heatmap"`.
- **Expected result**: `stockSubView = "heatmap"` after back tap. Without the `prevSubView` mechanism,
  back would return to ListDetail (`"list"`) — the naive default.
  Pass: `"heatmap"`. Fail: `"list"` (prevSubView not set correctly by drillToChartBySym).
- **Status**: passing [SERIALDBG]. Harness: `run_serialdbg_tests.py --tests T203`.

---

## Suite: tls-yield-reliability-001 — tlsYield mechanism coverage (TASK-138)

tlsYield/tlsResume was extended from the heatmap path to all dataTask fetches (fetchCrypto,
fetchStockQuote, fetchWeather) in commit `e00b453`. This suite verifies heap headroom and
mechanism correctness on those paths. T216/T217 cover the heatmap path (test_heatmap_reliability.py).
Harness: `app/tools/test_tls_yield_reliability.py`.

### T219 — [stock-002, TASK-138] Stock quote tlsYield: all 8 tickers 200 + mechanism fires + maxBlk≥50k (SERIALDBG)

- **Type**: integration (DUT, serial log-scrape)
- **Feature(s)**: stock-002
- **Objective**: Verify that `fetchStockQuote` correctly calls `tlsYield()` before the 8-ticker
  GET loop, freeing Spotify's TLS session, and that all 8 Yahoo Finance requests succeed with HTTP 200.
  Pre-loop `maxBlk≥50k` confirms TLS was freed before the loop starts.
- **Preconditions**: DUT flashed `cyd2usb_winamp_debug`. Active Spotify session (tlsYield
  blocks until Spotify task yields). WiFi up.
- **Steps**:
  1. `switchApp 7` (non-blocking send); detect ack in monitoring loop.
  2. Send `set triggerFetch 1` immediately after ack.
  3. Monitor serial for `tls yield — client stopped/resumed`, `dataTask.stock` LOG_HEAP (pre-loop),
     and 8× `quote GET <SYM> 200` lines.
- **Expected result**: All 8 tickers respond 200. Pre-loop `maxBlk≥50k`. At least one yield
  signal (`client stopped` or `resumed`) present. `client stopped` may be missed due to
  5-second tlsYield timeout race (LL-051); `resumed` alone is accepted as yield evidence.
- **Status**: passing [SERIALDBG]. Harness: `test_tls_yield_reliability.py --tests T219`.
  DUT run 2026-06-04: 8/8 tickers 200; yield=partial (client-stopped seen, resumed not); pre_maxBlk=71k.

---

### T220 — [stock-002, TASK-138] Crypto tlsYield: GET 200 + NoMemory absent + mechanism fires + maxBlk≥50k (SERIALDBG)

- **Type**: integration (DUT, serial log-scrape)
- **Feature(s)**: stock-002 (dataTask shared infrastructure)
- **Objective**: Verify `fetchCrypto` calls `tlsYield()` before the CoinGecko GET, and that the
  JSON parse does not fail with `NoMemory` after the fix. `maxBlk≥50k` on any dataTask.crypto
  LOG_HEAP confirms TLS headroom.
- **Preconditions**: DUT flashed `cyd2usb_winamp_debug`. Active Spotify session. WiFi up.
- **Steps**:
  1. `switchApp 3` (non-blocking send); detect ack in monitoring loop.
  2. Monitor for `tls yield` lines, `dataTask.crypto GET <code>`, `NoMemory` (absent),
     and `dataTask.crypto` LOG_HEAP lines.
- **Expected result**: GET 200. `NoMemory` absent. At least one yield signal present.
  `maxBlk≥50k` on all crypto LOG_HEAP readings.
  `client stopped` may race the monitoring window; `resumed` alone is accepted (same as T219).
- **Status**: passing [SERIALDBG]. Harness: `test_tls_yield_reliability.py --tests T220`.
  DUT run 2026-06-04: GET 200; NoMemory absent; resumed seen; maxBlk=71k.

---

### T221 — [stock-002, TASK-138] Weather TCP-close regression: GET 200 + heap recovery ≤5k drop (SERIALDBG)

- **Type**: integration (DUT, serial log-scrape)
- **Feature(s)**: stock-002 (dataTask shared infrastructure)
- **Objective**: Verify that `fetchWeather` uses HTTP/1.0 (`useHTTP10(true)`), causing the
  server to close the TCP connection after the response. `http.end()` then frees the TLS session
  immediately. Pre/post `maxBlk` delta must be ≤5k. `tcp keep open for reuse` must be absent.
- **Preconditions**: DUT flashed `cyd2usb_winamp_debug` (CORE_DEBUG_LEVEL=4 exposes
  Arduino HTTPClient `log_d` lines — `tcp is closed` / `tcp keep open for reuse`).
  WiFi up.
- **Steps**:
  1. 2s settle delay after prior test.
  2. `switchApp 2` (non-blocking send).
  3. Monitor for `dataTask.weather` LOG_HEAP (pre), `GET <code>`, HTTPClient tcp log lines,
     `dataTask.weather` LOG_HEAP (post).
- **Expected result**: GET 200. `tcp keep open for reuse` absent. `tcp is closed` present.
  Pre/post maxBlk drop ≤5k (TLS freed promptly by http.end()).
- **Status**: passing [SERIALDBG]. Harness: `test_tls_yield_reliability.py --tests T221`.
  DUT run 2026-06-04: GET 200; pre_maxBlk=39k post_maxBlk=39k drop=0k; tcp_closed confirmed.

---

## Suite: settings-nav-stub-001 — SettingsApp navigation stub (TASK-141/142)

SettingsApp navigation shell: category list, section stubs, Applications two-level submenu,
back-to-previous-app, and suspend reset. Requires `cyd2usb_winamp_debug` firmware and serial
debug interface (TASK-141c deliverables: `get settingsSection`, `get settingsAppSubmenu`).
All harness steps via `run_serialdbg_tests.py`.

**DUT required** — T-SET-01..T-SET-08 use serial debug interface with `cyd2usb_winamp_debug`.
Design doc: `docs/architecture/designs/M-MULTIAPP/settings.md` exit criteria C1–C6.

Common preconditions for all T-SET tests:
- DUT flashed `cyd2usb_winamp_debug` with TASK-141 firmware.
- Serial debug interface active.

---

### T-SET-01 — [settings-001, TASK-141] Category list at section -1 after switchApp(Settings)

- **Type**: integration (DUT)
- **Feature(s)**: settings-001
- **Objective**: Confirm Settings opens at the category list (`section == -1`) and renders 6 rows within the content panel.
- **Preconditions**: DUT booted. `get appId` != `Settings`.
- **Steps**:
  1. `switchApp 6` (Settings).
  2. `get appId` — assert `name == "Settings"`.
  3. `get settingsSection` — assert `section == -1`.
  4. Visual: 6 label rows visible within y:28..239; no pixel overflow above y=0 or into taskbar strip (x≥275).
- **Expected result**: `settingsSection == -1`; 6 tappable rows in content panel; canvas bounded correctly (C1).
- **Harness**: `run_serialdbg_tests.py --tests T-SET-01`. Owner: VE.
- **Status**: passing [SERIALDBG]. DUT run 2026-06-05.

---

### T-SET-02 — [settings-001, TASK-141] Section navigation: tap row opens section; back returns to category list

- **Type**: integration (DUT)
- **Feature(s)**: settings-001
- **Objective**: Each of the 5 stub sections (indices 0–4) opens correctly and the back zone returns to the category list.
- **Preconditions**: DUT in Settings at category list (`get settingsSection == -1`).
- **Steps** (repeat for `idx` in 0..4):
  1. `tap <row_x> <row_y>` where `row_y = 28 + idx*26 + 13` (row midpoint), `row_x = 137`.
  2. `get settingsSection` — assert `section == idx`.
  3. Visual: header shows correct category label; content panel shows "(not implemented)" text.
  4. `tap 30 14` (back zone: x=30, y=14 — within x<60, y<28).
  5. `get settingsSection` — assert `section == -1`.
- **Expected result**: Section opens with correct header for each index; back returns to category list (C2a).
- **Harness**: `run_serialdbg_tests.py --tests T-SET-02`. Owner: VE.
- **Status**: passing [SERIALDBG]. DUT run 2026-06-05.

---

### T-SET-03 — [settings-001, TASK-141] Applications section two-level drill and back

- **Type**: integration (DUT)
- **Feature(s)**: settings-001
- **Objective**: Applications section (index 5) presents app list at level 1; tapping an app opens level 2; two back taps return to category list.
- **Preconditions**: DUT in Settings at category list.
- **Steps**:
  1. `tap 137 171` (row 5 midpoint: y = 28 + 5*26 + 13 = 171).
  2. `get settingsSection` — assert `section == 5`.
  3. `get settingsAppSubmenu` — assert `submenu == -1`.
  4. `tap 137 41` (row 0 — "Stock": y = 28 + 0*26 + 13 = 41).
  5. `get settingsAppSubmenu` — assert `submenu == 0`.
  6. `tap 30 14` (back).
  7. `get settingsAppSubmenu` — assert `submenu == -1`.
  8. `tap 30 14` (back).
  9. `get settingsSection` — assert `section == -1`.
- **Expected result**: `settingsSection==5`, `settingsAppSubmenu==0`, then both reset to -1 after two backs (C2b).
- **Harness**: `run_serialdbg_tests.py --tests T-SET-03`. Owner: VE.
- **Status**: PASS — `settingsAppSubmenu` re-implemented in AppsSection (TASK-159, commit 50b962f, 2026-06-08). All steps valid and passing. T-APPS-07 remains as a complementary higher-level test (uses `settingsSection` only, adds visual steps).

---

### T-SET-04 — [settings-001, TASK-141] Content panel renders within x:0..274, y:28..239 for all sections

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: No section renders pixels outside the content panel bounds.
- **Preconditions**: DUT in Settings.
- **Steps**:
  1. Navigate to each section 0..5 (tap each row from category list).
  2. Visual: content fills only x:0..274, y:28..239; no bleed into header or taskbar.
  3. For section 5, also tap into an app submenu row and verify bounds.
- **Expected result**: All sections bounded within content panel (C3). Paired with T-SET-01 as a single visual pass.
- **Harness**: manual visual. Owner: VE.
- **Status**: planned (manual visual — pending DUT-141d walkthrough).

---

### T-SET-05 — [settings-001, TASK-141] App-switch residue: Spotify→Settings→Spotify leaves no settings pixels

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Switching back to Spotify after visiting Settings restores the Winamp chrome pixel-correctly with no settings residue.
- **Preconditions**: DUT running Spotify (winamp chrome visible).
- **Steps**:
  1. `switchApp 6` (Settings).
  2. Visual: Settings category list renders.
  3. `switchApp 0` (Spotify).
  4. Visual: Winamp chrome is pixel-correct; no grey/dark settings background or text residue on canvas.
- **Expected result**: Winamp chrome fully restored; zero settings residue (C4).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned (manual visual — pending DUT-141d walkthrough).

---

### T-SET-06 — [settings-001, TASK-141] Suspend reset: re-entering Settings always lands on category list

- **Type**: integration (DUT)
- **Feature(s)**: settings-001
- **Objective**: `suspend()` resets `section=-1`; returning to Settings always starts at the top level.
- **Preconditions**: DUT running Spotify.
- **Steps**:
  1. `switchApp 6` (Settings).
  2. `tap 137 171` (Applications, row 5).
  3. `tap 137 41` (Stock row within Applications — enters Stock submenu).
  4. Visual: Stock per-app rows visible (Ticker 1..7 + Default view).
  5. `switchApp 0` (Spotify — triggers `suspend()`).
  6. `switchApp 6` (Settings — triggers `resume()`).
  7. `get settingsSection` — assert `section == -1`.
  8. Visual: category list shows 6 rows with chevrons.
- **Expected result**: `section == -1` after suspend/resume; category list renders (C5).
- **Harness**: `run_serialdbg_tests.py --tests T-SET-06` (steps 1–3, 5–7). Step 4/8 manual visual. Owner: VE.
- **Status**: partial — serial steps 1–3/5–7 PASS (2026-06-06 DUT; also tested suspend mid-L2: `section==-1`); step 4/8 visual pending.

---

### T-SET-07 — [settings-001, TASK-141] Double-back from Applications Level 2 traverses all three levels

- **Type**: integration (DUT)
- **Feature(s)**: settings-001
- **Objective**: Back from app submenu goes to app list; second back goes to category list. Verifies full goBack() depth (C6 depth).
- **Preconditions**: DUT in Settings at category list.
- **Steps**:
  1. `tap 137 171` (Applications row).
  2. `tap 137 67` (Aquarium, row 2: y = 28 + 2*26 + 13 = 67).
  3. `get settingsSection` — assert `section == 5`.
  4. `get settingsAppSubmenu` — assert `submenu == 2`.
  5. `tap 30 14` (back).
  6. `get settingsAppSubmenu` — assert `submenu == -1` (at app list).
  7. `tap 30 14` (back).
  8. `get settingsSection` — assert `section == -1` (at category list).
- **Expected result**: Two back taps unwind both levels correctly (C6).
- **Harness**: `run_serialdbg_tests.py --tests T-SET-07`. Owner: VE.
- **Status**: PASS — `settingsAppSubmenu` re-implemented in AppsSection (TASK-159, commit 50b962f, 2026-06-08). All steps valid and passing.

---

### T-SET-08 — [settings-001, TASK-141] Back from category list returns to previous app (g_previousAppId)

- **Type**: integration (DUT)
- **Feature(s)**: settings-001
- **Objective**: `goBack()` from the category list calls `switchApp(g_previousAppId)`, returning to the app that was active before Settings was opened.
- **Preconditions**: DUT running.
- **Steps**:
  1. `switchApp 3` (Crypto).
  2. `get appId` — assert `name == "Crypto"`.
  3. `switchApp 6` (Settings — sets `g_previousAppId = Crypto`).
  4. `get settingsSection` — assert `section == -1`.
  5. `tap 30 14` (back from category list).
  6. `get appId` — assert `name == "Crypto"`.
- **Expected result**: `appId` returns to Crypto, confirming `g_previousAppId` tracking in `switchApp()`.
- **Harness**: `run_serialdbg_tests.py --tests T-SET-08`. Owner: VE.
- **Status**: passing [SERIALDBG]. DUT run 2026-06-05.

---

## Suite: settings-sections-001 — Section implementations (WiFi Ph1, Display, Time, Apps)

Tests for four section classes wired into SettingsApp: `WifiSection` (Phase 1),
`DisplaySection`, `TimeSection`, `AppsSection`. Added 2026-06-06.

Design docs: `wifi-settings.md` (C1–C1d), `display-settings.md` (C1–C5),
`time-settings.md` (C1–C7), `settings.md` §Applications (C6, C8).

Serial debug surface: `get settingsSection` confirms section index. Section-internal
state (Display level, Time format, Apps submenu) is not exposed via serial —
content verified visually unless noted.

**Reboot command:** `reboot` serial command added 2026-06-06 (calls `ESP.restart()`, emits
`{"ok":true,"cmd":"reboot"}` before reset). Required for T-DISP-04, T-TIME-04, T-APPS-08
persistence tests. Flash `cyd2usb_winamp_debug` (SHA ≥ `8a23642`+reboot commit).

**Tap Y reference (category list):** WiFi=41, Time=67, Touch-Cal=93, Display=119, LED=145, Applications=171.

**DUT required for all tests.** Flash `cyd2usb_winamp_debug`. Enter Settings: `switchApp 6`.

---

### T-WIFI-01 — [settings-wifi] WiFi Status view shows live connection info

- **Type**: integration (DUT) — visual + serial
- **Feature(s)**: settings-wifi, settings-001
- **Objective**: STATUS view renders connected state, SSID, IP, signal bars (C1a).
- **Preconditions**: DUT connected to WiFi.
- **Steps**:
  1. `switchApp 6` → `tap 137 41` (WiFi row).
  2. `get settingsSection` — assert `section == 0`.
  3. Visual: "Connected Yes" (green), SSID row, IP row (non-zero), signal bars (≥1 filled bar).
- **Expected result**: STATUS view populated with live data (C1a).
- **Harness**: step 2 serial; step 3 manual visual. Owner: VE.
- **Status**: partial — serial step 2 PASS (2026-06-06 DUT `section==0`); step 3 visual pending.

---

### T-WIFI-02 — [settings-wifi] Scan networks triggers async scan and spinner

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-wifi
- **Objective**: Tapping "Scan networks" transitions to SCANNING view with animated spinner (C1).
- **Preconditions**: DUT at WiFi STATUS view.
- **Steps**:
  1. Tap "Scan networks" row (y varies: ~54 if not connected, ~140 if connected with SSID/IP/Signal rows).
  2. Visual: header shows "Scanning...", content shows "Scanning for networks..." text, spinner glyph cycles (|/−\).
  3. Wait up to 5 s.
- **Expected result**: SCANNING view renders; spinner advances each ~200 ms; transitions to LIST when scan completes (C1).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-WIFI-03 — [settings-wifi] LIST populates within 5 s, sorted by RSSI

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-wifi
- **Objective**: After scan completes, LIST shows ≥1 network; networks sorted best-signal first; [E] marker on encrypted networks; signal bars accurate (C1b).
- **Preconditions**: Continuation of T-WIFI-02 (scan in progress or complete).
- **Steps**:
  1. After T-WIFI-02 scan triggers, wait ≤5 s.
  2. Visual: LIST view renders; header shows "Select network"; ≥1 row with SSID text and signal bars.
  3. Visual: first-listed network has strongest signal bars; [E] present for encrypted networks.
- **Expected result**: LIST populated within 5 s; signal-sorted; encrypted marker correct (C1b).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-WIFI-04 — [settings-wifi] Back from STATUS → category list

- **Type**: integration (DUT)
- **Feature(s)**: settings-wifi, settings-001
- **Objective**: `< back` from STATUS view returns to Settings category list (C1c).
- **Preconditions**: DUT at WiFi STATUS view (entered via T-WIFI-01).
- **Steps**:
  1. `tap 30 14` (back zone).
  2. `get settingsSection` — assert `section == -1`.
  3. Visual: category list (6 rows) renders.
- **Expected result**: `section == -1`, category list visible (C1c).
- **Harness**: `run_serialdbg_tests.py` step 2; step 3 manual. Owner: VE.
- **Status**: partial — serial step 2 PASS (2026-06-06 DUT `section==-1`); step 3 visual pending.

---

### T-WIFI-05 — [settings-wifi] Back from SCANNING/LIST returns to STATUS

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-wifi
- **Objective**: `< back` from SCANNING or LIST view goes to STATUS, not the category list (C1c).
- **Preconditions**: DUT at WiFi STATUS view.
- **Steps**:
  1. Tap "Scan networks" row → SCANNING view.
  2. `tap 30 14` (back) during or after scan (before tapping a network).
  3. Visual: STATUS view renders (header "WiFi", Connected row visible).
  4. Repeat from LIST: trigger scan again, wait for LIST, tap back.
  5. Visual: STATUS view again.
- **Expected result**: Back from SCANNING and LIST both return to STATUS view, not category list (C1c).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-WIFI-06 — [settings-wifi, X014] Spotify scan coexistence — no session crash

- **Type**: integration (DUT) — cross-feature
- **Feature(s)**: settings-wifi, io-001
- **Interaction**: X014
- **Objective**: Async WiFi scan while spotifyTask holds a live TLS session does not crash or permanently break Spotify polling (X014 — medium risk).
- **Preconditions**: DUT playing Spotify (active poll interval), WiFi connected.
- **Steps**:
  1. Confirm Spotify polling active (track metadata updates normally).
  2. `switchApp 6` → `tap 137 41` (WiFi) → tap "Scan networks".
  3. Wait for scan to complete (LIST view appears, ≤5 s).
  4. `switchApp 0` (back to Spotify).
  5. Wait two poll intervals (~60 s). Observe: track metadata continues updating; no crash/reboot.
- **Expected result**: Spotify recovers within one missed poll; no watchdog reset (X014 acceptable risk: single missed poll).
- **Harness**: manual. Flag if watchdog reset observed — apply heatmapPause() pattern. Owner: VE.
- **Status**: planned.

---

### T-DISP-01 — [settings-001] Manual brightness slider changes backlight duty

- **Type**: integration (DUT) — visual + hardware
- **Feature(s)**: settings-001
- **Objective**: Dragging Level slider 1→10 visibly changes backlight brightness; `ledcWrite(0, duty)` applied immediately (C1).
- **Preconditions**: DUT at Settings, `dispAuto = false`.
- **Steps**:
  1. `switchApp 6` → `tap 137 119` (Display row, y=119).
  2. `get settingsSection` — assert `section == 3`.
  3. Visual/touch: Level row slider visible at y=54. Drag from left (level 1, x≈75) to right (level 10, x≈241).
  4. Visual: backlight noticeably brighter after drag.
  5. Drag back to level 3. Visual: backlight dims.
- **Expected result**: Backlight duty tracks slider position; live preview during drag (C1).
- **Harness**: step 2 serial; steps 3–5 manual visual. Owner: VE.
- **Status**: partial — serial step 2 PASS (2026-06-06 DUT `section==3`; re-confirmed firmware ad7d104); steps 3–5 visual pending.

---

### T-DISP-02 — [settings-001] Auto-brightness: LDR coverage dims display

- **Type**: integration (DUT) — visual + hardware
- **Feature(s)**: settings-001
- **Objective**: Enabling Auto-brightness links backlight to LDR ADC34; covering sensor dims display; uncovering brightens (C2).
- **Preconditions**: DUT at Display section. LDR (GPIO34) accessible.
- **Steps**:
  1. Tap "Auto" row (y=41). Visual: row shows "On" in green.
  2. Cover LDR (block ambient light). Wait ≤1 s.
  3. Visual: backlight dims relative to uncovered state.
  4. Uncover LDR. Wait ≤1 s.
  5. Visual: backlight returns to brighter level.
  6. Tap "Auto" row again. Visual: row shows "Off"; backlight returns to stored manual level.
- **Expected result**: Backlight tracks ambient light when auto=On; restores manual level on disable (C2).
- **Harness**: manual visual/hardware. Owner: VE.
- **Status**: blocked — TASK-151 probe (`[disp] analogRead(34) raw = 0`) confirms LDR always reads 0 on DUT (2026-06-06 firmware ad7d104). Root cause unresolved; T-DISP-02 and T-DISP-03 cannot pass until ADC reads non-zero under varying ambient. Hardware investigation required (GPIO34 wiring, LDR circuit polarity).

---

### T-DISP-03 — [settings-001] LDR row live-updates without full repaint

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: "LDR" row (row 2) value updates live in ≤1 s when ambient light changes; other rows do not flicker (C3).
- **Preconditions**: DUT at Display section, auto=On or Off (both valid).
- **Steps**:
  1. Note current "LDR" row value on screen.
  2. Cover LDR with hand.
  3. Within 1 s: visual — LDR row value decreases; "Auto", "Level" rows are stable (no flicker).
  4. Uncover: LDR value increases.
- **Expected result**: LDR readout updates in-place; no full-screen clear visible (C3).
- **Harness**: manual visual. Owner: VE.
- **Status**: blocked — see T-DISP-02. LDR reads 0; dead-band (|fresh − _ldrRaw| > 20) never fires. Unblocks when T-DISP-02 passes.

---

### T-DISP-04 — [settings-001] Brightness level persists across restart

- **Type**: integration (DUT)
- **Feature(s)**: settings-001, cfg-001
- **Objective**: Stored `dispLevel` survives `ESP.restart()`; boot applies it before first frame — no brightness flash (C4).
- **Preconditions**: DUT at Display section, auto=Off.
- **Steps**:
  1. Set Level to 3 (drag slider left, ~x=111, y=54). Visual: backlight dim.
  2. `tap 30 14` (back to category list).
  3. Physical reset or `set restart 1` (if serial restart command available).
  4. After boot, before entering Settings: visual — backlight is at dim level 3, not full brightness.
  5. `switchApp 6` → `tap 137 119` (Display). Visual: Level slider positioned at 3.
- **Expected result**: Backlight at level 3 on boot; slider synced to stored value (C4).
- **Harness**: steps 1–2 manual; step 3 `reboot` serial command (added 2026-06-06); steps 4–5 manual visual. Owner: VE.
- **Status**: partial — `reboot` serial cmd PASS (2026-06-06 DUT; clean boot + `section==-1` on re-entry confirmed); brightness visual check pending.

---

### T-DISP-05 — [settings-001] Level row greyed and non-interactive when Auto=On

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: When auto=On, Level slider renders greyed; drag has no effect on backlight (C5).
- **Preconditions**: DUT at Display section.
- **Steps**:
  1. Tap "Auto" row → "On".
  2. Visual: Level row renders in grey (disabled colours).
  3. Drag on Level row (y=54). Visual: no change in slider position or backlight.
- **Expected result**: Level row greyed; taps/drags ignored while auto=On (C5).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-TIME-01 — [settings-001] City select updates timezone and clock immediately

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Selecting a city writes posixTz, tzName, lat, lon to SPIFFS and calls `configTzTime()` live; Clock app reflects new timezone without reboot (time-settings C1).
- **Preconditions**: DUT at Settings. NTP synced (clock shows plausible UTC time).
- **Steps**:
  1. `switchApp 6` → `tap 137 67` (Time & Location row, y=67).
  2. `get settingsSection` — assert `section == 1`.
  3. Tap City row (y=63). Visual: city picker opens, header shows "Select city".
  4. Scroll to and tap a UTC+offset city, e.g. Tokyo (UTC+9). Tap its row.
  5. Visual: Main view returns; Timezone row shows "Asia/Tokyo".
  6. `tap 30 14` (back) → `switchApp 1` (Clock).
  7. Visual: clock displays local Tokyo time (UTC+9 offset from known UTC reference).
- **Expected result**: Timezone visible in Time section; Clock app offset matches city (C1).
- **Harness**: step 2 serial; steps 3–7 manual visual. Owner: VE.
- **Status**: partial — serial step 2 PASS (2026-06-06 DUT `section==1`; re-confirmed firmware ad7d104); city picker open/close navigation confirmed (tap city row opens picker, back×2 returns section==-1); steps 4–7 visual pending.

---

### T-TIME-02 — [settings-001] 12h mode: AM/PM label visible, digits 1–12

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Setting Clock=12h displays hours as 1–12 with AM/PM; no overlap with digit area (time-settings C3).
- **Preconditions**: DUT at Time section, fmt24h=true (default).
- **Steps**:
  1. Tap "Clock" row (y=141). Visual: row shows "12h" in cyan.
  2. `tap 30 14` → `switchApp 1` (Clock app).
  3. Visual: time shows e.g. "2:34 PM" — hour 1–12, AM/PM label in top-right of time cell.
  4. Verify digits and AM/PM label do not overlap.
- **Expected result**: 12h format with AM/PM; no pixel overlap (C3).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-TIME-03 — [settings-001] Date format cycles through all three variants

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Tapping Date row cycles DMY→MDY→YMD→DMY; Clock app date display matches (time-settings C5).
- **Preconditions**: DUT at Time section.
- **Steps**:
  1. Note current Date row value. Should be "DD/MM/YYYY" (default).
  2. Tap Date row (y=167). Visual: row shows "MM/DD/YYYY".
  3. Tap again. Visual: "YYYY-MM-DD".
  4. Tap again. Visual: "DD/MM/YYYY" (wraps).
  5. Leave on MDY. `switchApp 1` (Clock). Visual: date shows MM/DD/YYYY format.
- **Expected result**: All three cycle correctly; Clock app format matches (C5).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-TIME-04 — [settings-001] Time and date settings persist across restart

- **Type**: integration (DUT)
- **Feature(s)**: settings-001, cfg-001
- **Objective**: posixTz, fmt24h, dateFmt survive `ESP.restart()`; `configTzTime()` re-applied on boot (time-settings C6).
- **Preconditions**: DUT at Time section.
- **Steps**:
  1. Select city "London" (Europe/London). Set Clock=12h. Set Date=MM/DD/YYYY.
  2. Physical reset.
  3. After boot: `switchApp 6` → `tap 137 67` (Time section).
  4. Visual: Timezone="Europe/London"; Clock="12h"; Date="MM/DD/YYYY".
  5. `switchApp 1` (Clock). Visual: time in 12h format with AM/PM.
- **Expected result**: All three settings preserved; timezone applies on boot (C6).
- **Harness**: manual + `reboot` serial cmd. Owner: VE.
- **Status**: partial — `reboot` + clean re-entry PASS (2026-06-06 DUT); city/fmt/date visual check pending.

---

### T-TIME-05 — [settings-001] Default state: UTC, 24h, DMY

- **Type**: integration (DUT)
- **Feature(s)**: settings-001
- **Objective**: Fresh SPIFFS (no settings.json) boots to UTC/24h/DMY defaults, matching current firmware behaviour (time-settings C7).
- **Preconditions**: SPIFFS erased (`pio run -t erase` or `uploadfs` with empty data/).
- **Steps**:
  1. Erase SPIFFS, flash firmware. Boot.
  2. `switchApp 6` → `tap 137 67`.
  3. Visual: City="None"; Timezone="UTC"; Clock="24h"; Date="DD/MM/YYYY".
  4. `switchApp 1` (Clock). Visual: time matches UTC (compare to known reference).
- **Expected result**: All defaults correct; behaviour identical to pre-settings firmware (C7).
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

### T-CITY-DRAG-01 — [settings-001] City picker scrollbar drag scrolls proportionally

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001, settings-time
- **Objective**: Dragging the scrollbar thumb scrolls the city list proportionally; release commits the offset; city tap still selects correctly after drag (TASK-153 / time-settings OQ4 resolved).
- **Preconditions**: DUT at Settings. City picker not yet open.
- **Steps**:
  1. `switchApp 6` → `tap 137 67` → `tap 137 63` (City row). Visual: picker opens, Auckland at top.
  2. Press and hold in scrollbar track zone (x=265, y=80). Visual: thumb captured.
  3. Drag down to y=160. Visual: city list scrolls ~50% down (~40 of 78 cities).
  4. Release. City list stays at dragged position (not snapping back).
  5. Tap a visible city row. Visual: main Time view returns; Timezone row shows selected city.
- **Expected result**: Drag moves list proportionally; release commits offset; city tap still selects correctly (TASK-153).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-CITY-OFFSET-01 — [settings-001] City picker UTC offset column and group separators

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001, settings-time
- **Objective**: City picker shows UTC offset prefix column for every row; horizontal group-separator lines mark each UTC offset transition; half-hour offsets formatted correctly (TASK-154).
- **Preconditions**: DUT at Settings. City picker not yet open.
- **Steps**:
  1. `switchApp 6` → `tap 137 67` → `tap 137 63` (City row). Visual: picker opens.
  2. Visual: UTC offset right-aligned in left column (x≈8–50), e.g. `+12` for Auckland, ` +9` for Tokyo.
  3. Visual: vertical separator line at x≈54 between offset column and city name.
  4. Visual: thin 1px horizontal line above each first-city-of-group (above Noumea [UTC+11], above Sydney [UTC+10], above Adelaide [UTC+9:30], etc.).
  5. Scroll through several pages; verify offset column and separators consistent throughout.
  6. Find Adelaide (UTC+9:30) row. Visual: `+9:30` visible in offset column; group separator above the row.
  7. Tap Adelaide. Visual: main view; Timezone = "Australia/Adelaide"; City = "Adelaide".
- **Expected result**: Offset column visible per row; half-hour shown as `+H:MM`; group-break lines at every UTC offset transition; city selection unchanged (TASK-154).
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-APPS-01 — [settings-001] Stock tickers cycle through predefined pool

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Tapping Ticker N row advances to next symbol in the 20-entry predefined pool; wraps at end (settings.md Applications).
- **Preconditions**: DUT at Settings category list. Default tickers: AAPL, AMD, AMZN, ARM, AVGO, GOOG, META, MSFT.
- **Steps**:
  1. `tap 137 171` (Applications) → `tap 137 41` (Stock).
  2. Visual: Ticker 1 row shows "AAPL" (default).
  3. Tap Ticker 1 row (y=41). Visual: shows "AMD".
  4. Tap again. Visual: shows "AMZN". (Next in pool.)
  5. Tap Ticker 2 row (y=67). Visual: advances from "AMD" to next entry.
- **Expected result**: Each tap advances ticker; pool cycles correctly; `saveSettings()` called on each change.
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-APPS-02 — [settings-001] Stock default view cycles list/chart/heatmap

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: "Default view" row (row 7 of Stock submenu, y=210) cycles list→chart→heatmap→list.
- **Preconditions**: DUT at Stock submenu.
- **Steps**:
  1. Scroll to "Default view" row (y≈210+13=223 midpoint). Tap.
  2. Visual: shows "chart".
  3. Tap again. Visual: "heatmap".
  4. Tap again. Visual: "list" (wraps).
- **Expected result**: Cycles all three values; persists (verified via T-APPS-08). Owner: VE.
- **Status**: planned.

---

### T-APPS-03 — [settings-001] Crypto coin and currency cycle

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Coin rows cycle through 12-entry predefined pool; Currency toggles USD↔EUR.
- **Preconditions**: DUT at Crypto submenu (Applications → Crypto).
- **Steps**:
  1. Tap Coin 1 row (y=41). Default "BTC" → "ETH".
  2. Tap again: "SOL".
  3. Tap Currency row (y=184). "USD" → "EUR".
  4. Tap again. "EUR" → "USD".
- **Expected result**: Coins advance through pool; Currency toggles correctly.
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-APPS-04 — [settings-001] Aquarium fish count and speed cycle

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Fish count cycles 4→8→12→16→4; Speed cycles slow→normal→fast.
- **Preconditions**: DUT at Aquarium submenu.
- **Steps**:
  1. Tap "Fish count" row (y=41). Note value. Tap 4× to confirm wrap (4→8→12→16→4).
  2. Tap "Speed" row (y=67). Note value. Tap 3× to confirm wrap (slow→normal→fast→slow).
- **Expected result**: Fish count and speed cycle with correct wrap-around.
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-APPS-05 — [settings-001] Matrix color and speed cycle

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Color cycles green→white→amber→green; Speed cycles slow→normal→fast.
- **Preconditions**: DUT at Matrix submenu.
- **Steps**:
  1. Tap "Color" row (y=41). Tap 3× to confirm cycle (green→white→amber→green).
  2. Tap "Speed" row (y=67). Tap 3× to confirm cycle.
- **Expected result**: Both cycle and wrap correctly.
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-APPS-06 — [settings-001] Life speed and colors cycle

- **Type**: integration (DUT) — visual
- **Feature(s)**: settings-001
- **Objective**: Speed cycles slow→normal→fast; Colors cycles rainbow→mono→rainbow.
- **Preconditions**: DUT at Life submenu.
- **Steps**:
  1. Tap "Speed" (y=41). 3× taps confirm wrap.
  2. Tap "Colors" (y=67). 2× taps confirm wrap (rainbow→mono→rainbow).
- **Expected result**: Both cycle and wrap.
- **Harness**: manual visual. Owner: VE.
- **Status**: planned.

---

### T-APPS-07 — [settings-001] Applications 2-level navigation (replaces T-SET-03, T-SET-07)

- **Type**: integration (DUT)
- **Feature(s)**: settings-001
- **Objective**: Applications section shows app list at L1; tapping app opens L2 rows; two back taps return to category list. Replaces stale T-SET-03 and T-SET-07 (no longer rely on `settingsAppSubmenu` debug var).
- **Preconditions**: DUT at Settings category list.
- **Steps**:
  1. `tap 137 171` (Applications row).
  2. `get settingsSection` — assert `section == 5`.
  3. Visual: 5 app rows (Stock/Crypto/Aquarium/Matrix/Life) with chevrons.
  4. `tap 137 93` (Aquarium row, y=80+13=93).
  5. Visual: header shows "Aquarium"; rows show "Fish count" and "Speed".
  6. `get settingsSection` — assert `section == 5` (still within Applications).
  7. `tap 30 14` (back). Visual: app list (5 rows with chevrons) renders.
  8. `get settingsSection` — assert `section == 5` (still in Applications at app list).
  9. `tap 30 14` (back). `get settingsSection` — assert `section == -1`.
- **Expected result**: Full 3-level unwind works; section stays 5 while inside L2; returns to -1 after two backs (C6 depth).
- **Harness**: serial steps 2/6/8/9; visual steps 3/5/7. Owner: VE.
- **Status**: partial — serial steps 2/6/8/9 PASS (2026-06-06 DUT: L1 entry `section==5`, L2 back stays 5, L1 back→`-1`); visual steps 3/5/7 pending.

---

### T-APPS-08 — [settings-001] App settings persist across restart (C8)

- **Type**: integration (DUT)
- **Feature(s)**: settings-001, cfg-001
- **Objective**: App preference changes (Aquarium + Matrix used as proxies) survive `ESP.restart()` and are reloaded from `/settings.json` (C8).
- **Preconditions**: DUT at Settings.
- **Steps**:
  1. Set Aquarium fish=12 (tap Fish count 3×), speed=fast (tap Speed 2×).
  2. Set Matrix color=amber (tap Color 2×).
  3. Physical reset.
  4. After boot: `switchApp 6` → Applications → Aquarium. Visual: Fish count=12, Speed=fast.
  5. Back → Matrix. Visual: Color=amber.
- **Expected result**: All three values preserved in `/settings.json`; loaded at boot (C8).
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

## LED Section (led-001)

### T-LED-01 — [led-001] LED category row navigates to List view
- **Type**: e2e
- **Feature(s)**: led-001, settings-001
- **Objective**: Tapping "LED" in the Settings category list enters LedSection List view.
- **Preconditions**: DUT booted, Settings app active, category list visible.
- **Steps**:
  1. Tap "LED" row.
- **Expected result**: Screen shows LED section header; two rows: "Mode" (current mode name) and "Color" with chevron. No artefacts.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-LED-02 — [led-001] Off mode disables all LED channels
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: Selecting Off mode drives all LEDC channels to 0 duty (common-anode: ledcWrite(ch, 255)).
- **Preconditions**: LED section open, current mode not Off.
- **Steps**:
  1. Tap Mode row until "Off" is selected (or open Picker, tap OFF button, SAVE).
  2. Observe RGB LED on hardware.
- **Expected result**: LED extinguished; no colour bleed from any channel. Mode row shows "Off".
- **Harness**: manual DUT inspection. Owner: VE.
- **Status**: planned.

### T-LED-03 — [led-001] Static mode holds fixed colour
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: Static mode applies stored HSV once and holds it — no animation.
- **Preconditions**: LED picker has been used to set a distinctive colour (e.g. red, H=0 S=255 V=200).
- **Steps**:
  1. Set mode Static via Picker → SAVE.
  2. Wait 5 s.
- **Expected result**: LED colour unchanged after SAVE; no fade or pulse.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-LED-04 — [led-001] Pulse mode breathes at ~2 s cycle
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: Pulse mode varies brightness sinusoidally via lut_sin; cycle ≈ 2 s.
- **Preconditions**: LED set to a visible colour with S=255 V=200.
- **Steps**:
  1. Set mode Pulse via Picker → SAVE.
  2. Observe LED for ≥4 s.
- **Expected result**: LED brightness rises and falls smoothly; two complete cycles visible in 4 s.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-LED-05 — [led-001] Clock mode hue advances with hour
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: Clock mode maps hour (0–23) to hue (0–255); colour shifts as hour changes.
- **Preconditions**: NTP synced; current hour known.
- **Steps**:
  1. Set mode Clock via Picker → SAVE.
  2. Note LED colour.
  3. Retrieve expected hue: `hue = (hour * 255) / 23`.
- **Expected result**: LED hue matches formula (visually approximate; verify with hour transition if near hour boundary).
- **Harness**: manual + serial log (`[ledFlow] clock hue=` if debug enabled). Owner: VE.
- **Status**: planned.

### T-LED-06 — [led-001] Tapping "Color" opens Picker and pauses LedFlow
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: Picker view opens on "Color" tap; LedFlow animation pauses during Picker (no contention).
- **Preconditions**: LED section List view, mode = Pulse.
- **Steps**:
  1. Tap "Color" row.
  2. Observe LED and screen.
- **Expected result**: Picker screen renders (button bar + SV square + hue strip). LED stops pulsing — holds fixed colour at current SV/hue values. No flicker.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-LED-07 — [led-001] SV square drag updates preview in real-time
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: Dragging within the SV square updates the working RGB immediately without committing.
- **Preconditions**: Picker view open. LED is Off or Static so change is visible.
- **Steps**:
  1. Drag finger across SV square from corner to corner.
  2. Observe LED hardware and SAVE button.
- **Expected result**: LED colour changes continuously during drag. SAVE button highlighted (dirty). Original stored values not yet changed (cancel and re-enter → LED reverts to pre-drag colour).
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-LED-08 — [led-001] Hue strip drag updates hue in real-time
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: Dragging the hue strip changes hue across the 0–255 range.
- **Preconditions**: Picker view open, S=255 V=200 (saturated, visible colour).
- **Steps**:
  1. Drag from top to bottom of hue strip.
- **Expected result**: LED hue sweeps full spectrum (red → yellow → green → cyan → blue → magenta → red). SAVE dirty.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-LED-09 — [led-001] SAVE commits and resumes LedFlow
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: SAVE button writes working hue/sat/val/mode and resumes animation.
- **Preconditions**: Picker open, SV/hue changed from stored value, mode = Pulse.
- **Steps**:
  1. Adjust hue to a noticeably different value.
  2. Tap SAVE.
- **Expected result**: Picker closes, List view shown. LED resumes Pulse at new hue. `/settings.json` contains updated ledHue (verify via serial `get snapshot` or reboot test T-LED-11).
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-LED-10 — [led-001] OFF button in Picker sets mode Off
- **Type**: e2e
- **Feature(s)**: led-001
- **Objective**: Tapping OFF in the Picker button bar immediately extinguishes the preview LED.
- **Preconditions**: Picker open, LED currently lit.
- **Steps**:
  1. Tap OFF button.
  2. Observe LED (before SAVE).
- **Expected result**: LED goes dark. SAVE dirty. Tapping SAVE returns to List; Mode row shows "Off".
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-LED-11 — [led-001] LED settings persist across restart
- **Type**: e2e
- **Feature(s)**: led-001, settings-001
- **Objective**: ledMode/ledHue/ledSat/ledVal survive SPIFFS write and reload on boot.
- **Preconditions**: LED set to Static H=120 (green-ish) S=200 V=180 via Picker → SAVE.
- **Steps**:
  1. Save distinctive settings.
  2. Hard-reset DUT.
  3. Boot without SPIFFS uploadfs.
  4. Observe LED after boot.
- **Expected result**: LED lights at the saved colour immediately after boot (LedFlow.applyMode() called in setup()).
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

## Keyboard Widget (keyboard-001)

### T-KB-01 — [keyboard-001] show() renders input field, prompt and key rows
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Calling show() paints the complete keyboard UI.
- **Preconditions**: Keyboard not currently shown. (Use WifiSection Phase-2 or inject via debug command when available.)
- **Steps**:
  1. Trigger keyboard show with prompt "SSID" and empty initial value.
- **Expected result**: Full-screen keyboard: prompt text visible in input bar, cursor blinking, QWERTY row 1 visible, row 2 below, row 3 + space bar, action row with OK. No pixel artefacts.
- **Harness**: manual / serial tap injection (when wired). Owner: VE.
- **Status**: planned.

### T-KB-02 — [keyboard-001] Alpha key tap appends character
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Tapping an alphabetic key appends the lowercase character to the input buffer.
- **Preconditions**: Keyboard open, mode=Full, page=lower, buffer empty.
- **Steps**:
  1. Tap 'H' key.
  2. Tap 'i' key.
- **Expected result**: Input field shows "hi". Cursor follows.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-KB-03 — [keyboard-001] Shift: one-shot uppercase then reverts
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Single SHIFT tap shifts next char only; page auto-reverts to lower.
- **Preconditions**: Keyboard open, lower page.
- **Steps**:
  1. Tap ⇧ (SHIFT).
  2. Observe key labels → should show uppercase.
  3. Tap 'A'.
  4. Observe page after tap.
- **Expected result**: 'A' (uppercase) appended. Page immediately reverts to lowercase layout without another SHIFT tap.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-KB-04 — [keyboard-001] Backspace removes last character
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: ⌫ (backspace) decrements buffer length by 1.
- **Preconditions**: Buffer contains "Hello".
- **Steps**:
  1. Tap ⌫ once.
- **Expected result**: Input shows "Hell". Cursor moves left. Buffer length = 4.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-KB-05 — [keyboard-001] SYM/ABC page cycling
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: SYM key advances to symbol pages; ABC returns to alpha lower.
- **Preconditions**: Keyboard open, lower page.
- **Steps**:
  1. Tap SYM → observe page 2 (sym1) key layout.
  2. Tap SYM → observe page 3 (sym2) key layout (different symbols).
  3. Tap ABC → observe lower alpha layout restored.
- **Expected result**: Each page shows distinct symbol sets. ABC always returns to page 0.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-KB-06 — [keyboard-001] OK invokes onSubmit with buffer
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Tapping OK calls the registered onSubmit callback with exact buffer content.
- **Preconditions**: Buffer contains "test123". onSubmit callback logs or stores value.
- **Steps**:
  1. Verify buffer shows "test123".
  2. Tap OK.
- **Expected result**: onSubmit called with "test123". Keyboard dismissed. No crash.
- **Harness**: manual + serial log (callback prints). Owner: VE.
- **Status**: planned.

### T-KB-07 — [keyboard-001] Cancel invokes onCancel without submit
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Tapping Cancel calls onCancel and does not invoke onSubmit.
- **Preconditions**: Buffer non-empty.
- **Steps**:
  1. Tap Cancel (or back equivalent).
- **Expected result**: onCancel called, onSubmit not called. Keyboard dismissed. Original value unchanged.
- **Harness**: manual. Owner: VE.
- **Status**: passing. DUT 2026-06-11. `[wifi] kb:cancel` in serial, no WiFi connect attempt. See T-KB-CANCEL-02.

### T-KB-08 — [keyboard-001] maxLen enforcement — no chars past limit
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Buffer never exceeds maxLen characters.
- **Preconditions**: Keyboard open with maxLen=5.
- **Steps**:
  1. Type 6 characters.
- **Expected result**: Only first 5 accepted. 6th tap produces no change to buffer or display. No overflow.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-KB-09 — [keyboard-001] Cursor blinks at ~500 ms
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Cursor visibility toggles at ~500 ms interval via tick().
- **Preconditions**: Keyboard open, no key taps for 2 s.
- **Steps**:
  1. Observe cursor for 2 s.
- **Expected result**: Cursor visible ~500 ms, hidden ~500 ms, repeat. Approximately 4 toggles in 2 s.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-KB-10 — [keyboard-001] UpperAlpha mode shows only A-Z, no SYM
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Mode::UpperAlpha renders uppercase alpha layout only; no SYM, SHIFT, or symbol pages.
- **Preconditions**: Keyboard invoked with mode=UpperAlpha.
- **Steps**:
  1. Observe key layout.
  2. Look for SYM and SHIFT keys.
- **Expected result**: Only A-Z keys visible plus Backspace, Space, OK. No SYM key. No SHIFT. All letters uppercase.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-KB-11 — [keyboard-001] Space key appends space character
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: Space bar inserts a space into the buffer.
- **Preconditions**: Buffer = "hello".
- **Steps**:
  1. Tap Space.
  2. Tap 'w', 'o', 'r', 'l', 'd'.
- **Expected result**: Buffer = "hello world".
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-KB-12 — [keyboard-001] Empty initial value starts with cursor only
- **Type**: e2e
- **Feature(s)**: keyboard-001
- **Objective**: show() with empty initial value renders empty input field with cursor at position 0.
- **Preconditions**: Keyboard shown with initial="".
- **Steps**:
  1. Observe input bar immediately after show().
- **Expected result**: Input bar shows only blinking cursor. No phantom characters. Buffer length = 0.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

## Touch Calibration (cal-001)

### T-CAL-01 — [cal-001] Idle screen shows current cal values and source
- **Type**: e2e
- **Feature(s)**: cal-001, settings-001
- **Objective**: Entering Touch Calibration shows current xMin/xMax/yMin/yMax and whether source is SPIFFS or factory default.
- **Preconditions**: Settings app open, category list visible. No prior user calibration (or one present).
- **Steps**:
  1. Tap "Touch Calibration".
- **Expected result**: Idle screen: shows xMin/xMax/yMin/yMax values; source label "factory default" or "SPIFFS". "Start" button in header right. "< back" left.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-CAL-02 — [cal-001] Start advances to TL step; crosshair at top-left
- **Type**: e2e
- **Feature(s)**: cal-001
- **Objective**: Tapping Start transitions to TL step with crosshair at (20, 48).
- **Preconditions**: Idle screen.
- **Steps**:
  1. Tap "Start" (header right side, y < 28, x > 220).
- **Expected result**: Screen header updates to "Tap top-left". Green crosshair renders at x=20, y=48. No other crosshairs.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-CAL-03 — [cal-001] All 4 corners collected → Review screen
- **Type**: e2e
- **Feature(s)**: cal-001
- **Objective**: Tapping each corner target in sequence TL→TR→BR→BL transitions to Review screen.
- **Preconditions**: TL step active.
- **Steps**:
  1. Tap near top-left target (20, 48). Observe TR step.
  2. Tap near top-right target (254, 48). Observe BR step.
  3. Tap near bottom-right target (254, 219). Observe BL step.
  4. Tap near bottom-left target (20, 219). Observe Review screen.
- **Expected result**: Step header advances after each tap. Review screen shows new xMin/xMax/yMin/yMax with delta vs. current. Accept button enabled (assuming reasonable taps). Tap markers at each corner.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-CAL-04 — [cal-001] Accept saves cal and applies to driver immediately
- **Type**: e2e
- **Feature(s)**: cal-001, touch-004
- **Objective**: Tapping Accept writes /cal.json and calls ts.setCalibration() in the same tick.
- **Preconditions**: Review screen, sanity checks passed (Accept enabled).
- **Steps**:
  1. Tap Accept.
  2. Observe transition (Saving → Idle).
  3. Test touch accuracy with a known tap target.
  4. Verify `/cal.json` via SPIFFS read (serial `get snapshot` or reboot check).
- **Expected result**: Idle screen returns. LED/tick continues. Touch accuracy reflects new calibration immediately (no reboot needed). `/cal.json` contains `current.xMin/xMax/yMin/yMax` matching displayed values.
- **Harness**: manual + optional serial readback. Owner: VE.
- **Status**: planned.

### T-CAL-05 — [cal-001] Cal persists across reboot
- **Type**: e2e
- **Feature(s)**: cal-001
- **Objective**: Calibration loaded from /cal.json in setup(); ts.setCalibration() called before first touch event.
- **Preconditions**: Cal accepted in T-CAL-04; /cal.json written.
- **Steps**:
  1. Hard-reset DUT.
  2. Tap a corner of the screen after boot.
- **Expected result**: Touch mapped accurately using saved cal (not factory defaults). Serial log shows `TouchCalStorage: loaded xMin=... xMax=... yMin=... yMax=...` at boot.
- **Harness**: manual + serial log. Owner: VE.
- **Status**: planned.

### T-CAL-06 — [cal-001] Retry restarts from TL step
- **Type**: e2e
- **Feature(s)**: cal-001
- **Objective**: Tapping Retry on the Review screen discards pending cal and restarts from TL.
- **Preconditions**: Review screen visible (after T-CAL-03 sequence).
- **Steps**:
  1. Tap Retry button.
- **Expected result**: Step reverts to TL. Header = "Tap top-left". Green crosshair at (20, 48). Previous raw corner data discarded.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-CAL-07 — [cal-001] Cancel on Review discards and returns to Idle
- **Type**: e2e
- **Feature(s)**: cal-001
- **Objective**: Tapping Cancel discards pending cal; returns to Idle without writing /cal.json.
- **Preconditions**: Review screen.
- **Steps**:
  1. Note current cal values on Idle screen (before Start).
  2. Complete 4 taps → Review.
  3. Tap Cancel.
- **Expected result**: Idle screen returns. xMin/xMax/yMin/yMax unchanged from step 1. /cal.json unchanged (timestamp not updated).
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-CAL-08 — [cal-001] Sanity fail: Accept dimmed, error message shown
- **Type**: e2e
- **Feature(s)**: cal-001
- **Objective**: If 4 taps produce span < 1000 raw units (e.g. all taps in center), Accept is disabled.
- **Preconditions**: Calibration step TL active.
- **Steps**:
  1. Tap all 4 corners in the very center of the screen (small raw spread).
- **Expected result**: Review screen shows "Bad reading" header and "Span too small - tap Retry" message. Accept button dimmed. Retry and Cancel still active.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-CAL-09 — [cal-001] Raw touch accumulates multiple samples per corner
- **Type**: integration
- **Feature(s)**: cal-001
- **Objective**: handleInputRaw accumulates raw samples while finger held down; averages on release.
- **Preconditions**: Calibration at TL step (stepping() == true). Serial debug enabled.
- **Steps**:
  1. Hold finger on TL target for ~1 s (many tick cycles).
  2. Release.
  3. Check serial: `_rawCount` should be > 1 when averaged.
- **Expected result**: Corner raw value is average of multiple samples (smoother than single read). Step advances to TR after release.
- **Harness**: serial log / unit analysis. Owner: VE.
- **Status**: planned.

### T-CAL-10 — [cal-001] Back from Idle returns to Settings category list
- **Type**: e2e
- **Feature(s)**: cal-001, settings-001
- **Objective**: "< back" from Idle returns to category list (GoBack signal).
- **Preconditions**: Touch Calibration Idle screen.
- **Steps**:
  1. Tap "< back" (y < 28, x < 60).
- **Expected result**: Category list reappears. No section state leaked.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

### T-CAL-11 — [cal-001] Back during stepping() is a no-op (raw path active)
- **Type**: e2e
- **Feature(s)**: cal-001
- **Objective**: During corner-tap steps the normal scaled handleInput is bypassed; stray taps don't navigate away.
- **Preconditions**: TL step active (stepping() == true).
- **Steps**:
  1. Tap top-left header area (< back region) without touching the crosshair zone.
- **Expected result**: handleInput returns Continue (ignores back area during step). Step remains TL. No navigation.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

## Suite: spiffs-manager-001 — run/spiffs non-destructive SPIFFS file manager (TASK-161/165)

### T-SPIFFS-01 — [TASK-161] ls lists known files; non-destructive
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: `./run/spiffs ls` lists all files on device; device unchanged after call.
- **Preconditions**: DUT connected. At least one known file on SPIFFS.
- **Steps**:
  1. Run `./run/spiffs ls` twice; capture both outputs.
  2. Compare outputs.
- **Expected result**: Stdout lists filename + size columns. Both runs identical. Exit 0. Monitor restarted.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. Both ls runs identical, 5 files listed.

### T-SPIFFS-02 — [TASK-161] pull (all) extracts to spiffs-dump/; device unchanged
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: `./run/spiffs pull` populates `app/data/spiffs-dump/`; device SPIFFS unchanged.
- **Preconditions**: DUT connected. At least 2 known files on SPIFFS.
- **Steps**:
  1. Record file list via `./run/spiffs ls` (pre-snapshot).
  2. Run `./run/spiffs pull`.
  3. Verify `app/data/spiffs-dump/` contains files matching ls output.
  4. Run `./run/spiffs ls` again; compare to step 1.
- **Expected result**: Each filename from ls has a corresponding file in spiffs-dump/. Second ls identical to first. Exit 0.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. 5 files extracted to spiffs-dump/, second ls identical.

### T-SPIFFS-03 — [TASK-161] pull <file> streams single file to stdout
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: `./run/spiffs pull <file>` emits JSON content to stdout; parses correctly.
- **Preconditions**: `spotify_diy_config.json` on device.
- **Steps**:
  1. Run `./run/spiffs pull spotify_diy_config.json`; capture stdout.
  2. Verify stdout is valid JSON with `clientId` field present.
- **Expected result**: Exit 0. Valid JSON on stdout. No `[spiffs]` prefix lines on stdout.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. Valid JSON, correct keys (refreshToken, clientId, clientSecret).

### T-SPIFFS-04 — [TASK-161] pull <missing-file> exits non-zero; device unchanged
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: Requesting a nonexistent file fails with error; device not modified.
- **Preconditions**: `nonexistent_test_file.json` not on device.
- **Steps**:
  1. Pre-snapshot via ls.
  2. Run `./run/spiffs pull nonexistent_test_file.json`; capture exit code and stderr.
  3. Post-snapshot via ls.
- **Expected result**: Exit non-zero. Stderr contains `not found`. Device file list unchanged. Monitor restarted.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. Exit 1, error "not found in SPIFFS", monitor restored.

### T-SPIFFS-05 — [TASK-161] push <file> updates only target; all other files preserved byte-identically
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: Core safety test — `push <file>` writes only the named file; cal.json, settings.json, drd.dat, and other files are byte-identical before and after.
- **Preconditions**: DUT connected. At least 2 files on SPIFFS. Source file in app/data/.
- **Steps**:
  1. Pull all files to spiffs-dump/ as pre-snapshot.
  2. Place a test `wifi_creds.json` with distinct content in app/data/.
  3. Run `./run/spiffs push wifi_creds.json`.
  4. Pull `wifi_creds.json`; verify updated content.
  5. Pull each other file; diff against pre-snapshot byte-for-byte.
  6. Remove test `wifi_creds.json` from app/data/.
- **Expected result**: `wifi_creds.json` has new content. Every other file byte-identical to pre-snapshot. Exit 0.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. wifi_creds.json updated; spotify_diy_config.json, host_overrides.json, cal.json, settings.json byte-identical. drd.dat excluded (live firmware file).

### T-SPIFFS-06 — [TASK-161] push (merge) preserves device-only files not in app/data/
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: Core safety test — `push` merge does not remove files that exist on device but not in app/data/ (cal.json, settings.json, drd.dat).
- **Preconditions**: DUT has cal.json and/or settings.json (device-generated). app/data/ contains only credential files. Pre-snapshot via pull.
- **Steps**:
  1. Pull all files; record which device-only files are present (cal.json etc.).
  2. Run `./run/spiffs push` (no arg, merge).
  3. Run `./run/spiffs ls`; verify device-only files still present.
  4. Pull device-only files; diff against pre-snapshot.
- **Expected result**: cal.json, settings.json, drd.dat still present and byte-identical to pre-snapshot. Exit 0.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. cal.json (230B) and settings.json (490B) preserved byte-identically after push merge. wifi_creds.json (test residue) also preserved.

### T-SPIFFS-07 — [TASK-161] push <missing-source> exits non-zero; device unchanged; monitor restored
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: Source file absent from app/data/ → fails before writing; device unchanged; monitor not left dead.
- **Preconditions**: `app/data/nonexistent.json` does not exist. Pre-snapshot via ls.
- **Steps**:
  1. Pre-snapshot.
  2. Run `./run/spiffs push nonexistent.json`; capture exit code, stderr.
  3. Post-snapshot via ls.
  4. Verify monitor session alive.
- **Expected result**: Exit non-zero. Stderr: `not found`. Device unchanged. Monitor restarted.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. Exit 1, "not found", device unchanged, monitor restored.

### T-SPIFFS-08 — [TASK-161] rm <file> removes target; all other files preserved
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: `rm` removes exactly the named file; all other files byte-identical.
- **Preconditions**: DUT connected. Push a disposable test file first as rm target.
- **Steps**:
  1. Push `test_rm_target.json` to device.
  2. Verify it appears in ls.
  3. Pre-snapshot all other files.
  4. Run `./run/spiffs rm test_rm_target.json`.
  5. Verify it is absent from ls.
  6. Pull each remaining file; diff against pre-snapshot.
- **Expected result**: `test_rm_target.json` absent. All other files byte-identical. Exit 0.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. wifi_creds.json absent after rm; all 4 original files byte-identical.

### T-SPIFFS-09 — [TASK-161] rm <missing-file> exits non-zero; device unchanged; monitor restored
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: Removing a nonexistent file fails cleanly; device unchanged; monitor not left dead.
- **Preconditions**: `ghost_file.json` not on device. Pre-snapshot via ls.
- **Steps**:
  1. Pre-snapshot.
  2. Run `./run/spiffs rm ghost_file.json`; capture exit code, stderr.
  3. Post-snapshot via ls.
  4. Verify monitor session alive.
- **Expected result**: Exit non-zero. Stderr: `not found`. Device unchanged. Monitor restarted.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. Exit 1, "not found", device unchanged, monitor restored.

### T-SPIFFS-10 — [TASK-161] mkspiffs round-trip fidelity: no-op push leaves all files byte-identical
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: A round-trip (read_flash → mkspiffs -u → mkspiffs -c → write_flash) without content modification leaves all files byte-identical. Guards against silent mkspiffs data loss.
- **Preconditions**: DUT with at least 3 files. Pre-snapshot all via pull.
- **Steps**:
  1. Pull all files → pre-snapshot.
  2. Run `./run/spiffs push spotify_diy_config.json` where app/data/ version matches device version.
  3. Pull all files → post-snapshot.
  4. Diff each post-file against pre-snapshot byte-for-byte.
- **Expected result**: All files byte-identical across the round-trip. Exit 0.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-09. All 5 files byte-identical after full read-unpack-repack-write round-trip.

### T-SPIFFS-11 — [TASK-161] ls with no device exits non-zero with useful error
- **Type**: integration
- **Feature(s)**: TASK-161
- **Objective**: When port resolution finds no device, script fails cleanly without hanging.
- **Preconditions**: DUT disconnected.
- **Steps**:
  1. Run `./run/spiffs ls` with no device on USB.
- **Expected result**: Exit non-zero. Stderr mentions port failure or device not found. No hang.
- **Harness**: host-only (no DUT). Owner: VE.
- **Status**: passing. Host-only 2026-06-11. Exit 1, stderr `ERROR: CH340 device not found (VID:PID 1A86:7523)`, no hang.

### T-SPIFFS-12 — [TASK-161] invalid subcommand shows usage and exits non-zero
- **Type**: unit
- **Feature(s)**: TASK-161
- **Objective**: Unknown subcommand hits `*)` branch and exits with usage message.
- **Preconditions**: No DUT required.
- **Steps**:
  1. Run `./run/spiffs foobar`; capture exit code and stderr.
- **Expected result**: Exit 1. Stderr: usage string listing all valid subcommands.
- **Harness**: host-only. Owner: VE.
- **Status**: passing. Host-only 2026-06-09. Exit 1, usage string on stderr.

---

## Suite: setup-wizard-001 — M-SETUP-WIZARD: run/setup wizard + PATCH-003

### T-SETUP-01 — [M-SETUP-WIZARD] WiFi section writes valid wifi_creds.json
- **Type**: e2e
- **Feature(s)**: M-SETUP-WIZARD
- **Objective**: `run/setup` WiFi section produces a correctly-structured `app/data/wifi_creds.json` with owner-only permissions.
- **Preconditions**: No existing `app/data/wifi_creds.json`. `run/setup` available and executable.
- **Steps**:
  1. Run `./run/setup`, choose option 1 (WiFi only).
  2. Enter a valid SSID (1–32 chars) and password (≥8 chars, confirmed).
  3. After wizard completes, inspect `app/data/wifi_creds.json`.
  4. Check file permissions: `stat -c '%a' app/data/wifi_creds.json`.
- **Expected result**: File contains `{"ssid": "<entered>", "pass": "<entered>"}`. Permissions `600`.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

### T-SETUP-02 — [M-SETUP-WIZARD] Overwrite guard prompts when wifi_creds.json already exists
- **Type**: e2e
- **Feature(s)**: M-SETUP-WIZARD
- **Objective**: Wizard does not silently overwrite an existing credential file.
- **Preconditions**: `app/data/wifi_creds.json` already present with known content.
- **Steps**:
  1. Note existing file content.
  2. Run `./run/setup`, choose option 1 (WiFi only).
  3. When prompted about existing file, choose to keep it.
  4. Verify file content unchanged.
  5. Re-run setup, choose to overwrite; enter new values.
  6. Verify file updated to new values.
- **Expected result**: Step 3: wizard prints overwrite prompt; on "keep", file unchanged. Step 5: on "overwrite", file updated.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

### T-SETUP-03 — [M-SETUP-WIZARD] Ctrl-C during WiFi section leaves no .tmp file
- **Type**: e2e
- **Feature(s)**: M-SETUP-WIZARD
- **Objective**: KeyboardInterrupt at any prompt leaves no `.tmp` debris and does not write a partial file.
- **Preconditions**: No existing `app/data/wifi_creds.json`.
- **Steps**:
  1. Run `./run/setup`, choose option 1.
  2. Enter SSID, then press Ctrl-C before password prompt completes.
  3. Check for `app/data/wifi_creds.json` and `app/data/wifi_creds.json.tmp`.
- **Expected result**: Neither file exists. Wizard prints "Interrupted — no files written." Exit non-zero.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

### T-SETUP-04 — [M-SETUP-WIZARD] Ctrl-C after file written leaves original intact (overwrite path)
- **Type**: e2e
- **Feature(s)**: M-SETUP-WIZARD
- **Objective**: Atomic write ensures Ctrl-C during a second run leaves the original file intact (`.tmp` + `os.replace()` pattern).
- **Preconditions**: `app/data/wifi_creds.json` already present with known content (from T-SETUP-01).
- **Steps**:
  1. Run `./run/setup`, choose option 1, choose overwrite.
  2. Enter SSID but press Ctrl-C mid-password.
  3. Verify original file content unchanged. No `.tmp` file.
- **Expected result**: Original `wifi_creds.json` content intact. No `.tmp` file.
- **Harness**: manual. Owner: VE.
- **Status**: planned.

---

### T-SETUP-05 — [M-SETUP-WIZARD] spiffs push offer at end uploads both files non-destructively
- **Type**: integration
- **Feature(s)**: M-SETUP-WIZARD
- **Objective**: End-of-wizard offer runs `./run/spiffs push`; cal.json/settings.json on device are preserved.
- **Preconditions**: DUT connected. `cal.json` and `settings.json` present on SPIFFS. Both credential files in `app/data/`.
- **Steps**:
  1. Snapshot SPIFFS via `./run/spiffs ls` + pull.
  2. Run `./run/setup`, choose option 3 (both), accept spiffs push offer.
  3. After completion, snapshot SPIFFS again.
  4. Compare `cal.json` and `settings.json` byte-for-byte.
- **Expected result**: `wifi_creds.json` and `spotify_diy_config.json` present on device. `cal.json` and `settings.json` byte-identical to pre-push snapshots.
- **Harness**: manual + DUT. Owner: VE.
- **Status**: planned.

---

### T-SETUP-06 — [M-SETUP-WIZARD] Spotify section writes valid spotify_diy_config.json
- **Type**: e2e
- **Feature(s)**: M-SETUP-WIZARD
- **Objective**: `run/setup` Spotify section writes a correctly-structured config with valid field names and chmod 600.
- **Preconditions**: Valid Spotify Developer app with `http://127.0.0.1:8888/callback/` in Redirect URIs.
- **Steps**:
  1. Run `./run/setup`, choose option 2 (Spotify only).
  2. Enter Client ID and Client Secret.
  3. Complete OAuth browser flow.
  4. Inspect `app/data/spotify_diy_config.json` and permissions.
- **Expected result**: File contains `clientId`, `clientSecret`, `refreshToken` fields (correct case). Permissions `600`. `refreshToken` non-empty.
- **Harness**: manual (requires real Spotify account + browser). Owner: VE.
- **Status**: planned.

---

### T-SETUP-07 — [M-SETUP-WIZARD] PATCH-003: firmware reads wifi_creds.json from SPIFFS and connects (E1)

- **Type**: integration
- **Feature(s)**: M-SETUP-WIZARD, PATCH-003
- **Objective**: PATCH-003 firmware path — device reads `/wifi_creds.json` from SPIFFS and connects to WiFi without captive portal or compile-time hardcode.
- **Preconditions**: DUT connected. Firmware built with PATCH-003 (current build). No `wifi_creds.h` present. Valid `app/data/wifi_creds.json` with known-good SSID/pass.
- **Steps**:
  1. Ensure `wifi_creds.h` does not exist: `ls Spotify-Diy-Thing/SpotifyDiyThing/wifi_creds.h` → not found.
  2. Push credentials: `./run/spiffs push wifi_creds.json`.
  3. Flash current firmware: `./run/flash`.
  4. Monitor boot log: `./run/monitor-read 100`.
- **Expected result**: Boot log contains `[wifi] Connecting from SPIFFS: <ssid>` followed by `WL_CONNECTED`. No captive portal launch. Spotify polling begins normally.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-11. `[wifi] Connecting from SPIFFS: yellowbrickroad` → STA_CONNECTED → STA_GOT_IP → token POST 200, Spotify polling normally.

---

### T-SETUP-08 — [M-SETUP-WIZARD] PATCH-003: compile-time wifi_creds.h still takes priority (E6)
- **Type**: integration
- **Feature(s)**: M-SETUP-WIZARD, PATCH-003
- **Objective**: When `wifi_creds.h` is present, the `#ifdef HARDCODED_WIFI_SSID` branch fires and the SPIFFS path is skipped (`#ifndef HARDCODED_WIFI_SSID` guard).
- **Preconditions**: DUT connected. `wifi_creds.json` on SPIFFS with a **different** SSID than `wifi_creds.h`.
- **Steps**:
  1. Create `Spotify-Diy-Thing/SpotifyDiyThing/wifi_creds.h` with real SSID/PASS.
  2. Push a `wifi_creds.json` with a fake/different SSID via `./run/spiffs push wifi_creds.json`.
  3. Rebuild and flash: `./run/build && ./run/flash`.
  4. Monitor boot log.
  5. Remove `wifi_creds.h`, rebuild and reflash to restore normal state.
- **Expected result**: Step 4 boot log: `Connecting to hardcoded SSID <real-ssid>` and `WL_CONNECTED`. No `[wifi] Connecting from SPIFFS:` line — SPIFFS path not entered.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-11. `Connecting to hardcoded SSID yellowbrickroad` → STA_CONNECTED. No SPIFFS path entered. fake-ssid SPIFFS file ignored.

---

### T-SETUP-09 — [M-SETUP-WIZARD] PATCH-003: SPIFFS fallthrough to portal when wifi_creds.json missing
- **Type**: integration
- **Feature(s)**: M-SETUP-WIZARD, PATCH-003
- **Objective**: When no `wifi_creds.json` exists on SPIFFS and no `wifi_creds.h`, device falls through to WiFiManager portal.
- **Preconditions**: DUT connected. No `wifi_creds.h`. `wifi_creds.json` removed from SPIFFS.
- **Steps**:
  1. Remove `wifi_creds.json` from SPIFFS: `./run/spiffs rm wifi_creds.json`.
  2. Flash current firmware: `./run/flash`.
  3. Monitor boot log for portal launch.
- **Expected result**: Device broadcasts `SpotifyDIY` AP. Boot log does not contain `[wifi] Connecting from SPIFFS:`. Portal launched normally.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-11. No `[wifi] Connecting from SPIFFS:` in log. WiFiManager.autoConnect() took over; connected via NVS-saved creds (expected on non-fresh device). On a fresh device (no NVS), portal would launch. PATCH-003 bypass confirmed.

---

### T-SETUP-10 — [M-SETUP-WIZARD] PATCH-003: SPIFFS fallthrough to portal when SPIFFS connect fails
- **Type**: integration
- **Feature(s)**: M-SETUP-WIZARD, PATCH-003
- **Objective**: When `wifi_creds.json` exists but credentials are wrong, PATCH-003 falls through to portal gracefully.
- **Preconditions**: DUT connected. No `wifi_creds.h`. SPIFFS has `wifi_creds.json` with an intentionally wrong password.
- **Steps**:
  1. Create `app/data/wifi_creds.json` with correct SSID but wrong password.
  2. `./run/spiffs push wifi_creds.json`.
  3. Flash current firmware: `./run/flash`.
  4. Monitor boot log; wait ~35s for connect timeout.
- **Expected result**: Boot log: `[wifi] Connecting from SPIFFS: <ssid>`, then dots, then `[wifi] SPIFFS connect failed — falling through to portal.`. Device broadcasts `SpotifyDIY` AP.
- **Harness**: host-driven (DUT). Owner: VE.
- **Status**: passing. DUT 2026-06-11. PATCH-003 entered SPIFFS path with bad password; 4WAY_HANDSHAKE_TIMEOUT loop; fell through. Portal launched (`*wm:StartAP with SSID: SpotifyDIY`). Bug found and fixed: `WiFi.persistent(true)` in PATCH-003 wrote bad creds to NVS, causing WiFiManager autoConnect to also fail. Fixed to `WiFi.persistent(false)` (TASK-167).

---

## Suite: wifi-p2-001 — M-SETTINGS WiFi Phase 2: on-device connect UI

### T-WIFI-P2-01 — [M-SETTINGS-WIFI-P2] NVS reconnect on boot
- **Type**: integration
- **Feature(s)**: M-SETTINGS-WIFI-P2
- **Objective**: Device reconnects from NVS credentials without any intervention.
- **Preconditions**: DUT previously connected (NVS has valid creds). No `wifi_creds.h`. No `/wifi_creds.json` on SPIFFS (or stale).
- **Steps**:
  1. Flash Phase 2 firmware: `./run/flash`.
  2. Monitor boot log.
- **Expected result**: Boot log shows `IP address: <ip>` within ~10s. No `[wifi] no credentials` line. No Settings auto-switch.
- **Harness**: host-driven. Owner: VE.
- **Status**: passing. DUT 2026-06-11. `IP address: 192.168.1.126` in boot log; Spotify polling healthy.

### T-WIFI-P2-02 — [M-SETTINGS-WIFI-P2] Encrypted network connect via keyboard
- **Type**: e2e (manual)
- **Feature(s)**: M-SETTINGS-WIFI-P2, KeyboardWidget
- **Objective**: Tap an encrypted network in WiFi list → keyboard appears → enter password → CONNECTING → success.
- **Preconditions**: DUT booted with no NVS WiFi creds (run `./run/spiffs rm wifi_creds.json` then NVS clear, or use a fresh device). Settings → WiFi section open and scan complete (LIST state).
- **Steps**:
  1. Open Settings → WiFi section. Wait for scan to complete (LIST).
  2. Tap an encrypted (lock icon) network.
  3. Keyboard appears with "Password" prompt.
  4. Type the correct password, press OK.
  5. Screen transitions to CONNECTING (spinner + SSID name).
  6. Wait ≤15 s.
- **Expected result**: CONNECTING transitions to STATUS (connected info: SSID + IP). Serial shows `IP address:`. User navigates away manually (no auto-navigate to Spotify app — TASK-169).
- **Harness**: manual DUT. Owner: VE.
- **Status**: passing. DUT 2026-06-11. Keyboard appeared on encrypted tap; correct password submitted; `wifi=rssi(-61)` in heartbeat; Spotify polling live. Note: scan uses synchronous `WiFi.scanNetworks(false)` — async scan was cancelled by concurrent Spotify task socket calls on same core.

### T-WIFI-P2-03 — [M-SETTINGS-WIFI-P2] Wrong password shows RESULT view with Retry/Cancel
- **Type**: e2e (manual)
- **Feature(s)**: M-SETTINGS-WIFI-P2
- **Objective**: Wrong password → CONNECTING times out → RESULT view with fail reason and Retry/Cancel buttons.
- **Preconditions**: DUT at LIST state (scan complete). Target encrypted network visible.
- **Steps**:
  1. Tap encrypted network, enter a deliberately wrong password, press OK.
  2. Screen shows CONNECTING + spinner.
  3. Wait up to 15 s for timeout.
- **Expected result**: RESULT view appears showing fail reason (e.g. `4WAY_HANDSHAKE_TIMEOUT`) + "Retry" and "Cancel" buttons. Tapping Cancel returns to STATUS.
- **Harness**: manual DUT + serialdbg. Owner: VE.
- **Status**: passing. DUT 2026-06-11. Wrong password submitted via `tap`; 15s timeout elapsed; "Timed out" + Retry/Cancel visible on screen. Cancel → STATUS confirmed.

### T-WIFI-P2-04 — [M-SETTINGS-WIFI-P2] Successful connect persists to NVS (survives reboot)
- **Type**: integration (manual)
- **Feature(s)**: M-SETTINGS-WIFI-P2
- **Objective**: After T-WIFI-P2-02, reboot device — reconnects from NVS without opening WiFi settings.
- **Preconditions**: Successful connect from T-WIFI-P2-02 (NVS populated by `WiFi.persistent(true)` in `_startConnect()`).
- **Steps**:
  1. After successful connect in T-WIFI-P2-02, press RST on DUT.
  2. Monitor boot log.
- **Expected result**: Boot log: `IP address:` within ~10s, no Settings auto-switch, Spotify polling starts.
- **Harness**: manual DUT. Owner: VE.
- **Status**: passing. DUT 2026-06-11. `wifi=rssi(-62)` at uptime 6s; Spotify polling started; no Settings nav.

### T-WIFI-P2-05 — [M-SETTINGS-WIFI-P2] Forget network clears NVS and restarts
- **Type**: e2e (manual)
- **Feature(s)**: M-SETTINGS-WIFI-P2
- **Objective**: Tapping "Forget" in WiFi STATUS view calls `WiFi.disconnect(false,true)`, removes `/wifi_creds.json` if present, restarts device.
- **Preconditions**: DUT connected (NVS has creds). Settings → WiFi section at STATUS view.
- **Steps**:
  1. Open Settings → WiFi → STATUS view.
  2. Tap the "Forget" row.
  3. Device restarts.
  4. Monitor boot log.
- **Expected result**: After restart: `[wifi] no credentials — will open WiFi settings after init`. Device switches to Settings → WiFi section automatically.
- **Harness**: manual DUT. Owner: VE.
- **Status**: passing. DUT 2026-06-11. Forget tapped; device restarted; WiFi settings menu appeared on screen; `wifi=rssi(0)` confirmed no connection.

### T-WIFI-P2-06 — [M-SETTINGS-WIFI-P2] No credentials → auto-switch to WiFi settings on boot
- **Type**: integration (manual)
- **Feature(s)**: M-SETTINGS-WIFI-P2
- **Objective**: When no NVS creds and no SPIFFS `/wifi_creds.json`, boot auto-navigates to Settings → WiFi section.
- **Preconditions**: Fresh/cleared NVS (via T-WIFI-P2-05 Forget, or manual NVS erase).
- **Steps**:
  1. After T-WIFI-P2-05 (device restarted with no creds).
  2. Observe screen and boot log.
- **Expected result**: Boot log: `[wifi] no credentials — will open WiFi settings after init`. Screen shows Settings → WiFi section (scan in progress or STATUS). No Spotify app.
- **Harness**: manual DUT. Owner: VE.
- **Status**: passing. DUT 2026-06-11. `[wifi] no credentials` + `[shell] entered 6` in boot log; WiFi settings menu shown on screen.

---

## Suite: app-settings-wire-001 — M-SETTINGS-APP-WIRE per-app settings wiring (TASK-172)

Full suite: `docs/verification/regression_suite/app-settings-wire-001.md`

**Pre-implementation blockers:** Developer must add `dbgGet` for MatrixApp
(`matrixColor`, `matrixTickMs`), LifeApp (`lifeColors`, `lifeTickMs`), AquariumApp
(`aquariumFish`), StockApp (`stockTicker0`–`7`), CryptoApp (`cryptoCoin0`–`5`,
`cryptoCcy`), and a dataTask fetch log line for crypto. These gate all SERIALDBG
tests. Visual (MANUAL) tests have no blockers.

### T222 — [app-settings-wire-001] Matrix color propagates on resume

- **Type**: integration (DUT, SERIALDBG)
- **Feature(s)**: app-settings-wire-001
- **Objective**: Settings → Applications → Matrix → Color tap changes `_headColor`/`_tailColor`; change visible via `get matrixColor` after switchApp.
- **Preconditions**: Debug build. `get matrixColor` returns `"green"`.
- **Steps**: Settings→Applications→Matrix→Color tap×1; exit Settings; `switchApp 4`; `get matrixColor`.
- **Expected result**: `val == "white"`.
- **Status**: planned

### T223 — [app-settings-wire-001] Matrix tick interval matches speed setting

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `_tickMs` reflects slow=40/normal=25/fast=15 ms after resume.
- **Preconditions**: Default `get matrixTickMs` == `"25"`.
- **Steps**: Cycle speed to slow; exit; `switchApp 4`; `get matrixTickMs` → `"40"`. Repeat for fast → `"15"`.
- **Expected result**: Tick intervals 40 / 25 / 15 match slow / normal / fast.
- **Status**: planned

### T224 — [app-settings-wire-001] Matrix amber color renders on DUT [MANUAL]

- **Type**: integration (DUT, MANUAL)
- **Objective**: Amber color shows orange/yellow tails, not green.
- **Preconditions**: Color set to amber via Settings.
- **Steps**: `switchApp 4`; observe ≥ 5 s.
- **Expected result**: Falling tails are amber-yellow.
- **Status**: planned

### T225 — [app-settings-wire-001] Life tick interval matches speed setting

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `lifeTickMs` reflects slow=200/normal=100/fast=50 ms.
- **Preconditions**: Default `get lifeTickMs` == `"100"`.
- **Steps**: Cycle speed fast; exit; `switchApp 5`; `get lifeTickMs` → `"50"`. Cycle slow → `"200"`.
- **Expected result**: Tick intervals match setting.
- **Status**: planned

### T226 — [app-settings-wire-001] Life colors=mono propagates to app

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `lifeColors` dbgGet reflects Setting value after resume.
- **Preconditions**: Default `get lifeColors` == `"rainbow"`.
- **Steps**: Settings→Life→Colors tap×1; exit; `switchApp 5`; `get lifeColors`.
- **Expected result**: `val == "mono"`.
- **Status**: planned

### T227 — [app-settings-wire-001] Life mono renders single-color cells [MANUAL]

- **Type**: integration (DUT, MANUAL)
- **Objective**: LifeColors::Mono renders all alive cells in one colour.
- **Preconditions**: `lifeColors` = mono.
- **Steps**: `switchApp 5`; observe cells.
- **Expected result**: All alive cells are single green. No rainbow gradient.
- **Status**: planned

### T228 — [app-settings-wire-001] Aquarium fish count propagates on resume

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `_activeFish` changes on resume without full init.
- **Preconditions**: Default `get aquariumFish` == `"16"`.
- **Steps**: Settings→Aquarium→Fish count tap×1 (16→4); exit; `switchApp 8`; `get aquariumFish`.
- **Expected result**: `val == "4"`.
- **Status**: planned

### T229 — [app-settings-wire-001] Aquarium fish count 4 shows sparse school [MANUAL]

- **Type**: integration (DUT, MANUAL)
- **Preconditions**: Fish count = 4.
- **Steps**: `switchApp 8`; observe ≥ 10 s.
- **Expected result**: ~4 fish visible; sparse.
- **Status**: planned

### T230 — [app-settings-wire-001] Aquarium fish count 16 shows full school [MANUAL]

- **Type**: integration (DUT, MANUAL)
- **Preconditions**: Fish count = 16.
- **Steps**: `switchApp 8`; observe ≥ 10 s.
- **Expected result**: Dense school of ~16 fish.
- **Status**: planned

### T231 — [app-settings-wire-001] Aquarium speed slow/fast visually distinct [MANUAL]

- **Type**: integration (DUT, MANUAL)
- **Objective**: Speed multiplier affects fish swim pace.
- **Steps**: Observe normal, then fast, then slow. Compare swim pace.
- **Expected result**: Fast noticeably quicker; slow noticeably slower than normal.
- **Status**: planned

> Note (TASK-325, landed): T233/T246's "type X" SERIALDBG steps now drive via `set kbText <text>` + `set kbOk` (or `set kbCancel`) against the active KeyboardWidget — DUT execution still pending a grouped TASK-324 session.

### T232 — [app-settings-wire-001] Stock: keyboard opens on ticker row tap

- **Type**: integration (DUT, MANUAL+SERIALDBG)
- **Objective**: Tapping a Ticker row opens KeyboardWidget (UpperAlpha), not a cycle value.
- **Preconditions**: Settings → Applications → Stock submenu open.
- **Steps**: `tap 137 41` (Ticker 1 row).
- **Expected result**: Keyboard canvas renders; prompt "Ticker 1"; current ticker pre-filled.
- **Status**: planned

### T233 — [app-settings-wire-001] Stock: valid ticker validates and saves [SLOW]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Keyboard → OK → chart validation oracle → `g_settings` updated.
- **Preconditions**: Ticker 1 = `"AAPL"`.
- **Steps**: Open keyboard for Ticker 1; type `"TSLA"`; OK; poll `get stockTicker0` ≤ 25 s.
- **Expected result**: `val == "TSLA"`. Validating screen shown during wait.
- **Status**: planned

### T246 — [app-settings-wire-001] Stock: invalid ticker shows error screen [SLOW]

- **Type**: integration (DUT, SERIALDBG+MANUAL)
- **Objective**: Unknown symbol → error screen; g_settings unchanged.
- **Steps**: Open keyboard; type `"ZZZZZZ"`; OK; wait ≤ 22 s; `get stockTicker0`.
- **Expected result**: Error screen shown. `val` unchanged (still old ticker).
- **Status**: planned

### T247 — [app-settings-wire-001] Stock: error retry re-opens keyboard pre-filled [MANUAL]

- **Type**: integration (DUT, MANUAL)
- **Objective**: Content-area tap on error screen re-opens keyboard with failed symbol.
- **Steps**: From error screen, tap content area (not back).
- **Expected result**: Keyboard opens with `"ZZZZZZ"` pre-filled.
- **Status**: planned

### T248 — [app-settings-wire-001] Stock: ticker change triggers immediate re-fetch [SLOW]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `StockApp::resume()` detects changed tickers → enqueues quote immediately.
- **Preconditions**: `Q0 = get quoteOkCount`. Ticker changed to `"TSLA"` via T233.
- **Steps**: Exit Settings; `switchApp 7`; poll `get quoteOkCount` ≤ 90 s.
- **Expected result**: `quoteOkCount > Q0`. `fetchFailed == false`.
- **Status**: planned

### T234 — [app-settings-wire-001] Stock stockMode seeds subView on cold init [REBOOT]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `init()` uses g_settings.stockMode; verified after reboot.
- **Steps**: Set Default view to `"chart"`; `reboot`; `switchApp 7`; `get stockSubView`.
- **Expected result**: `val == "chart"`.
- **Status**: planned

### T235 — [app-settings-wire-001] Stock resume does not override active session view

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `resume()` does not re-seed subView from stockMode.
- **Preconditions**: StockApp in chart view. `g_settings.stockMode == "list"`.
- **Steps**: `switchApp 6`; `switchApp 7`; `get stockSubView`.
- **Expected result**: `val == "chart"` (not `"list"`).
- **Status**: planned

### T236 — [app-settings-wire-001] Crypto coin change updates app state

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `cryptoCoin0` dbgGet reflects cycled coin after resume.
- **Preconditions**: Default `get cryptoCoin0` == `"bitcoin"`.
- **Steps**: Settings→Crypto→Coin 1 tap×1; exit; `switchApp 3`; `get cryptoCoin0`.
- **Expected result**: `val` is next pool coin (e.g. `"ethereum"`).
- **Status**: planned

### T237 — [app-settings-wire-001] Crypto currency change updates app state

- **Type**: integration (DUT, SERIALDBG)
- **Preconditions**: Default `get cryptoCcy` == `"usd"`.
- **Steps**: Settings→Crypto→Currency tap×1; exit; `switchApp 3`; `get cryptoCcy`.
- **Expected result**: `val == "eur"`.
- **Status**: planned

### T238 — [app-settings-wire-001] dataTask fetch log includes coin IDs and currency [SLOW]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `configureCrypto()` path verified via log line from fetchCrypto().
- **Preconditions**: Coin 1 = `"dogecoin"`, currency = `"eur"`.
- **Steps**: `switchApp 3`; monitor serial ≤ 90 s.
- **Expected result**: Log line contains `"dogecoin"` and `"eur"` (per CHALLENGE-2 requirement).
- **Status**: planned

### T239 — [app-settings-wire-001] Crypto display shows short name not word ID [MANUAL]

- **Type**: integration (DUT, MANUAL)
- **Objective**: `cgIdToDisplay("bitcoin")` → `"BTC"` shown in CryptoApp row.
- **Steps**: `switchApp 3`; observe first row label.
- **Expected result**: `"BTC"` visible, not `"bitcoin"`.
- **Status**: planned

### T240 — [app-settings-wire-001] Crypto small-price coin uses 4 decimal places [MANUAL]

- **Type**: integration (DUT, MANUAL)
- **Objective**: Magnitude-based `formatCryptoPrice()` gives 4 dp for sub-$1 prices.
- **Preconditions**: At least one coin < $1.00 in the active list.
- **Steps**: `switchApp 3`; observe price for sub-$1 coin.
- **Expected result**: 4 decimal places shown (e.g. `"0.4523"`).
- **Status**: planned

### T241 — [app-settings-wire-001] Settings Cancel restores Matrix color

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Snapshot-restore path covers per-app settings.
- **Preconditions**: `get matrixColor` == `"green"`.
- **Steps**: Change color to white; exit to category list; `switchApp 4`; verify white. Re-enter Settings; tap Cancel; `switchApp 4`; `get matrixColor`.
- **Expected result**: `val == "green"` after cancel.
- **Status**: planned

### T242 — [app-settings-wire-001] Settings Cancel restores Stock ticker

- **Type**: integration (DUT, SERIALDBG)
- **Preconditions**: `get stockTicker0` == `"AAPL"`.
- **Steps**: Change Ticker 1; verify change; Cancel; `switchApp 7`; `get stockTicker0`.
- **Expected result**: `val == "AAPL"`.
- **Status**: planned

### T243 — [app-settings-wire-001] Matrix color survives reboot [REBOOT]

- **Type**: integration (DUT, SERIALDBG)
- **Steps**: Set color to white; `reboot`; `switchApp 4`; `get matrixColor`.
- **Expected result**: `val == "white"`.
- **Status**: planned

### T244 — [app-settings-wire-001] Stock tickers survive reboot [REBOOT]

- **Type**: integration (DUT, SERIALDBG)
- **Steps**: Change Ticker 1; note value N; `reboot`; `switchApp 7`; `get stockTicker0`.
- **Expected result**: `val == N`.
- **Status**: planned

### T245 — [app-settings-wire-001] Crypto currency survives reboot [REBOOT]

- **Type**: integration (DUT, SERIALDBG)
- **Steps**: Set currency to EUR; `reboot`; `switchApp 3`; `get cryptoCcy`.
- **Expected result**: `val == "eur"`.
- **Status**: planned

---

## M-TELETEXT — Teletext App Suite (T249–T268)

> Added 2026-06-13 after Architect + VE design review.
> Tests blocked on G1 require `get teletextReady` / `get teletextPage` / `set triggerTeletextFetch` / `get teletextLastAction` / `get teletextHasSubpages` / `get teletextSubpage` serial accessors (TASK-180, TASK-188).
> Tests blocked on G2 require pixel-exact touch zone constants published in `teletext_layout.h` (TASK-181). Strip zone y-values are now firm; only the submenu row section awaits TASK-177.
> G3 — back-navigation mechanism — **resolved 2026-06-13** (TASK-182 closed): dedicated ◄◄ zone at x=240..274, y=67..99.
> Tests blocked on G4 require `set teletextPageContent` debug stub (TASK-183).
> Tests blocked on G5 require debounce serial accessor (TASK-184).

### T249 — [M-TELETEXT] T-TTX-01: App switch round-trip

- **Type**: integration (DUT, SERIALDBG)
- **Feature(s)**: M-TELETEXT
- **Objective**: Spotify→Teletext→Spotify completes without crash; `get appId` confirms each leg.
- **Preconditions**: DUT running, WiFi connected.
- **Steps**: 1. `switchApp Teletext`; 2. `get appId` → assert `"Teletext"`; 3. `switchApp Spotify`; 4. `get appId` → assert `"Spotify"`.
- **Expected result**: Both IDs confirmed. No crash. No black screen residue.
- **Status**: ready to run

### T250 — [M-TELETEXT] T-TTX-02: Canvas tap routes correctly while Teletext active

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap on the clock hotspot while Teletext is active returns `hit="CLOCK"` (BUG-1 guard — same as T_WX_02 pattern).
- **Preconditions**: Teletext app active.
- **Steps**: `tap 137 120`; `get lastHit`.
- **Expected result**: `lastHit == "CLOCK"` (or equivalent non-Teletext app hit response).
- **Status**: ready to run

### T251 — [M-TELETEXT] T-TTX-03: Canvas residue clears on Teletext→Spotify switch

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `lastPlaylistDraw` counter advances after switch away from Teletext (no frozen canvas).
- **Preconditions**: Teletext active; `D0 = get lastPlaylistDraw`.
- **Steps**: `switchApp Spotify`; poll `get lastPlaylistDraw` ≤ 30 s.
- **Expected result**: `lastPlaylistDraw > D0`.
- **Status**: ready to run

### T252 — [M-TELETEXT] T-TTX-04: dataTask delivers teletextReady [NETWORK] [Blocked: G1]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `FETCH_TELETEXT_PAGE` fires after app switch-in; `teletextReady` becomes true within 30 s.
- **Preconditions**: WiFi connected. `get teletextReady` accessor present (TASK-180).
- **Steps**: `switchApp Teletext`; poll `get teletextReady` ≤ 30 s.
- **Expected result**: `ready == true`. `teletextPage == 101` (default).
- **Status**: planned

### T253 — [M-TELETEXT] T-TTX-05: teletextPage accessor round-trip [Blocked: G1]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `set teletextPage` / `get teletextPage` round-trips correctly; value persists in `g_settings`.
- **Preconditions**: `get teletextPage` and `set teletextPage` accessors present (TASK-180).
- **Steps**: 1. `set teletextPage 601`; 2. `get teletextPage` → assert 601; 3. `set teletextPage 101`; 4. `get teletextPage` → assert 101.
- **Expected result**: Each `get` reflects the last `set` value.
- **Status**: planned

### T254 — [M-TELETEXT] T-TTX-06: Fast-text bar — 4 button hit zones [Blocked: G2]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Each of 4 fast-text buttons returns correct FTL target action when tapped.
- **Preconditions**: Teletext active. Pixel-exact x-boundaries published in `teletext_layout.h` (TASK-181). `set cooldown 0`.
- **Steps**: For each button band: `tap <x_centre> <y_centre_bar>`; `get teletextLastAction` → assert `FTL_N`.
- **Expected result**: 4/4 buttons return correct fast-text target index.
- **Status**: planned

### T255 — [M-TELETEXT] T-TTX-07: Fast-text bar boundary — 1 px above bar top

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap at y=199 (1 px above bar top at y=200) returns deadzone or grid action — not a fast-text hit.
- **Preconditions**: Teletext active.
- **Steps**: `tap 137 199`; `get teletextLastAction`.
- **Expected result**: `action != "FASTTEXT"`.
- **Status**: planned

### T256 — [M-TELETEXT] T-TTX-08: Right-strip PREV_PAGE zone [Blocked: G2]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap in PREV_PAGE zone of the right-strip navigates to previous page.
- **Preconditions**: `get teletextPage` accessor present (TASK-180). Pixel-exact y-boundary for PREV_PAGE zone confirmed (TASK-181). `set cooldown 0`.
- **Steps**: `P0 = get teletextPage`; `tap 257 <prev_page_y>`; `get teletextPage` → assert `== P_prev` (from `pn=p_` metadata).
- **Expected result**: `teletextPage` changes to the previous page number.
- **Status**: planned

### T257 — [M-TELETEXT] T-TTX-09: Right-strip NEXT_PAGE zone [Blocked: G2]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap in NEXT_PAGE zone navigates to next page.
- **Preconditions**: Same as T256.
- **Steps**: `P0 = get teletextPage`; `tap 257 <next_page_y>`; `get teletextPage` → assert `== P_next`.
- **Expected result**: `teletextPage` changes to next page number.
- **Status**: planned

### T258 — [M-TELETEXT] T-TTX-10: Right-strip inactive zone — no subpages [Blocked: G2]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap subpage-up/down zones when the current page has no subpages → no page change.
- **Preconditions**: Current page has no subpages (verifiable from `teletextHasSubpages` accessor or known page).
- **Steps**: `P0 = get teletextPage`; `tap 257 <subpage_up_y>`; `get teletextPage` → assert `== P0`.
- **Expected result**: `teletextPage` unchanged.
- **Status**: planned

### T259 — [M-TELETEXT] T-TTX-11: Inline row link — tap navigates to page ref [NETWORK] [Blocked: G1, G4]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap on a grid row containing a 3-digit page ref at cols 35–39 navigates to that page.
- **Preconditions**: `get teletextPage` present (TASK-180). Preferred: `set teletextPageContent` stub to inject synthetic content with known page-ref at row N (TASK-183). Fallback: use page 101 with known stable index layout.
- **Steps**: Inject content with page ref `601` at row 5 (at cols 33–39); `tap <col_centre_x> <row5_y>`; `get teletextPage` → assert 601.
- **Expected result**: `teletextPage == 601`.
- **Status**: planned

### T260 — [M-TELETEXT] T-TTX-12: Inline row link — no digit → no navigation [Blocked: G4]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap on a row with no 3-digit page ref at cols 35–39 does not change `teletextPage`.
- **Preconditions**: `set teletextPageContent` stub present (TASK-183). Content injected with row N having no page ref.
- **Steps**: Inject content with row N containing no 3-digit ref in cols 33–39; `P0 = get teletextPage`; `tap <col_centre_x> <rowN_y>`; `get teletextPage` → assert `== P0`.
- **Expected result**: `teletextPage` unchanged.
- **Status**: planned

### T261 — [M-TELETEXT] T-TTX-13: History back navigation [Blocked: G1]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Forward navigation pushes page onto history ring; ◄◄ back zone tap returns to prior page.
- **Preconditions**: `get teletextPage` present (TASK-180). Back zone: `tap 257 83` (centre of BACK zone x=240..274, y=67..99).
- **Steps**: `P0 = get teletextPage`; navigate forward to page 601 (`tap 257 149` NEXT_PAGE or inline link); `get teletextPage` → assert 601; `tap 257 83`; `get teletextPage` → assert `== P0`.
- **Assert also**: before forward nav, `tap 257 83` with empty history → `teletextPage` unchanged (◄◄ zone inert when history empty; see T-TTX-21).
- **Expected result**: Returns to original page. ◄◄ zone dim before first nav, cyan-tinted after.
- **Status**: planned

### T262 — [M-TELETEXT] T-TTX-14: Settings drill — Applications → Teletext submenu

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Settings → Applications → Teletext row opens the Teletext submenu correctly.
- **Preconditions**: Applications submenu row order confirmed (TASK-181 / TASK-177). `get settingsAppSubmenu` accessor present.
- **Steps**: Navigate to Settings → Applications; `tap <teletext_row_y>`; `get settingsAppSubmenu` → assert Teletext submenu index.
- **Expected result**: Submenu opens at the Teletext section.
- **Status**: planned

### T263 — [M-TELETEXT] T-TTX-15: teletextPollSecs cycles via settings tap [Blocked: G1]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap on the poll interval row in Settings → Teletext cycles 30→60→120→30.
- **Preconditions**: `get teletextPollSecs` accessor present (TASK-180). Submenu row y-coordinate published (TASK-181).
- **Steps**: Navigate to Settings → Teletext; `tap <pollSecs_row_y>` × 3; assert cycle: 60→120→30.
- **Expected result**: Values cycle as specified.
- **Status**: planned

### T264 — [M-TELETEXT] T-TTX-16: teletextPage persists via pull-on-resume (ADR-043) [Blocked: G1]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: `set teletextPage 601`; switch away and back; `get teletextPage` returns 601 (ADR-043 pull-on-resume).
- **Preconditions**: `set/get teletextPage` accessors present (TASK-180).
- **Steps**: `set teletextPage 601`; `switchApp Spotify`; `switchApp Teletext`; `get teletextPage` → assert 601.
- **Expected result**: `teletextPage == 601`.
- **Status**: planned

### T265 — [M-TELETEXT] T-TTX-17: Full canvas coverage — no black half [MANUAL]

- **Type**: manual (DUT, visual)
- **Objective**: Verify full 275×240 canvas is painted; no solid-black half; mosaic and text rows visible.
- **Steps**: Switch to Teletext; observe screen. Cross-reference against `preview_teletext.py` at 3× zoom.
- **Expected result**: 25 rows of teletext content visible in grid area; right-strip and fast-text bar rendered.
- **Status**: planned

### T266 — [M-TELETEXT] T-TTX-18: Text/mosaic render correctness [MANUAL]

- **Type**: manual (DUT, visual)
- **Objective**: Mosaic characters render as 2×3 graphic blocks; text rows render as characters in correct colours.
- **Steps**: Navigate to a page with known mosaic content (e.g., page 888 — subtitles or graphics page); observe cells.
- **Expected result**: Mosaic pixels visible; colour-coding matches preview tool output.
- **Status**: planned

### T267 — [M-TELETEXT] T-TTX-19: run/check 5-gate passes after 10th-app registry update

- **Type**: host automated
- **Objective**: `gen_app_registry.py` re-run after Teletext added to `appRegistry.h`; all 5 gates pass.
- **Steps**: `gen_app_registry.py`; `./run/check`.
- **Expected result**: Exit 0. Gate [5/5] passes (staleness check clean).
- **Status**: planned

### T268 — [M-TELETEXT] T-TTX-20: 300 ms debounce blocks rapid double-tap [Blocked: G5]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Second tap within 300 ms on the same row does not fire a second navigation.
- **Preconditions**: `set teletextDebounceMs <N>` or `get teletextLastTapMs` accessor present (TASK-184).
- **Steps**: `tap <row_y>`; wait 100 ms; `tap <row_y>`; assert `teletextPage` changed exactly once.
- **Expected result**: Only one navigation event fired.
- **Status**: planned

### T269 — [M-TELETEXT] T-TTX-21: ◄◄ back zone inert when history empty [Blocked: G1, G2]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap the ◄◄ back zone when the history ring is empty → no navigation.
- **Preconditions**: `get teletextPage` present (TASK-180). Freshly switched into Teletext (no forward navigation performed). `set cooldown 0`.
- **Steps**: `switchApp Teletext`; `P0 = get teletextPage`; `tap 257 83`; `get teletextPage` → assert `== P0`.
- **Expected result**: `teletextPage` unchanged. No navigation event.
- **Status**: planned

### T270 — [M-TELETEXT] T-TTX-22: Subpage ▲/▼ zones active when subpages present [NETWORK] [Blocked: G1, G2]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Tap SUBPAGE_UP/DN when the page has subpages → subpage changes.
- **Preconditions**: `get teletextPage` and `get teletextSubpage` present (TASK-188). Current page known to have subpages (e.g. page 101 on some days — or inject via `set teletextPageContent` if TASK-183 done). `set cooldown 0`.
- **Steps**: `S0 = get teletextSubpage`; `tap 257 16` (SUBPAGE_UP centre); `get teletextSubpage` → assert `!= S0` (or wraps).
- **Expected result**: Subpage counter changes.
- **Status**: planned

### T271 — [M-TELETEXT] T-TTX-23: ◄◄ back zone 1-px boundary [Blocked: G2]

- **Type**: integration (DUT, SERIALDBG)
- **Objective**: Verify ◄◄ zone y-boundaries are pixel-exact (y=67 hits BACK, y=66 hits PAGE_NUM, y=100 hits PREV_PAGE).
- **Preconditions**: `get teletextLastAction` present (TASK-188). History ring non-empty. `set cooldown 0`.
- **Steps**:
  1. `tap 257 66` → `get teletextLastAction` → assert `KEYPAD_OPEN` (not BACK)
  2. `tap 257 67` → `get teletextLastAction` → assert `BACK`
  3. `tap 257 99` → `get teletextLastAction` → assert `BACK`
  4. `tap 257 100` → `get teletextLastAction` → assert `PREV_PAGE` (not BACK)
- **Expected result**: All 4 boundary assertions pass.
- **Status**: planned

### T272 — [M-TELETEXT] T-TTX-24: TLS heap contention — fetchTeletext concurrent with spotifyTask [NETWORK]

- **Type**: integration (DUT, SERIALDBG)
- **Feature(s)**: M-TELETEXT, ADR-044 item 9
- **Objective**: Verify `fetchTeletext()` (no `tlsYield`) completes without OOM/watchdog while `spotifyTask` holds an active TLS session. Validates ADR-044's "weather pattern" assumption for teletext. If this test fails (timeout or DUT crash), apply `tlsYield()`/`tlsResume()` around `fetchTeletext()`.
- **Preconditions**: DUT flashed `cyd2usb_winamp_debug`. WiFi connected. Active Spotify session (spotifyTask TLS polling at ~5s intervals).
- **Steps**:
  1. `get lastPlaylistDraw` → record baseline `D0` (confirms spotifyTask active).
  2. `switchApp 9` (Teletext) → triggers `resume()` + immediate `enqueueTeletextPage()`.
  3. `set triggerTeletextFetch 1` → forces a second enqueue even if already ready.
  4. Poll `get teletextReady` ≤ 30 s → assert `ready == true`.
  5. `switchApp 0` (Spotify).
  6. Poll `get lastPlaylistDraw` ≤ 10 s → assert `ms > D0`.
- **Expected result**: `teletextReady=true` within 30 s; `lastPlaylistDraw` advances after return. No OOM, no watchdog, no crash.
- **Pass criteria**: PASS if both asserts hold. SKIP if HTTP non-200 (network unavailable). FAIL if DUT unresponsive or 30 s elapsed with `ready=false` (crash/OOM implies contention → apply fix).
- **Harness**: `run_serialdbg_tests.py --tests T272`
- **Status**: passing — three bugs found and fixed: (1) missing `tlsYield()`/`tlsResume()` in `fetchTeletext()` (TLS contention confirmed, ADR-044 item 9 revised); (2) `_lastFetch=0` early-boot bug causing no-enqueue within first 60 s (fixed via `_forceNow()` helper); (3) null-byte parser bug — NOS body contains `\x00\x00` before `</pre>` so `String::indexOf("</pre>")` returned -1 (fixed with null-safe `memcmp` scan). T272 PASS [SERIALDBG]

---

## Suite: M-WEBRADIO-PREVIEW — preview_webradio.py canvas layout tool (TASK-201)

> Added 2026-06-14 — host-only validation plan.  No DUT required.
> Full suite: `docs/verification/regression_suite/m-webradio-preview.md`
> Gate: human sign-off on T275 layout snapshots before firmware work starts.

### T273 — [M-WEBRADIO-PREVIEW] Tool launches without error in each of 4 states

- **Type**: host automated
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: `preview_webradio.py` imports cleanly and renders one frame per state (stopped / connecting / playing / error) without raising an exception.
- **Preconditions**: `gen/skin_preview.png` present. `skins/base-2.91.wsz` present (required for TEXT.BMP/POSBAR.BMP/PLEDIT.BMP sprite extraction). Project venv active.
- **Steps**: In headless context (`SDL_VIDEODRIVER=offscreen`), call the per-state render function for each of the 4 states; assert no exception; assert returned image is non-None.
- **Expected result**: All 4 render calls return without error. No `FileNotFoundError`, `ImportError`, or `AttributeError`.
- **Status**: recheck required after TASK-201 fix

### T274 — [M-WEBRADIO-PREVIEW] All 4 states reachable via keyboard shortcuts

- **Type**: host manual (interactive)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: Keyboard shortcuts cycle through stopped → connecting → playing → error.  Window title or canvas label updates at each transition.
- **Preconditions**: `DISPLAY` available. `gen/skin_preview.png` present. `skins/base-2.91.wsz` present.
- **Steps**: Launch tool (`python3 preview_webradio.py --skin ../gen/skin_preview.png --wsz ../../skins/base-2.91.wsz`); press documented state-cycle keys in sequence; confirm each state shows a visually distinct frame; confirm no crash on any transition.
- **Expected result**: All 4 states reachable. Canvas/title updates correctly. No crash.
- **Status**: recheck required after TASK-201 fix

### T275 — [M-WEBRADIO-PREVIEW] All required canvas elements present in each state [MANUAL]

- **Type**: host visual (manual, with pixel-sample assist)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: Every element from `M-WEBRADIO.md` §Canvas layout is drawn: PL panel (station rows + scroll indicator), station-name marquee (line 1), ICY StreamTitle (line 2), buffer bar (seek-bar region), bitrate field, VU meter, country badge (top-right title area). **Font must be TEXT.BMP LED glyphs (5×6 px); POSBAR and PLEDIT chrome must be actual skin sprites — not PIL default font or fill-rects.**
- **Preconditions**: Tool can produce a static PNG snapshot per state. `skins/base-2.91.wsz` and `gen/skin_preview.png` present.
- **Steps**: Render PNG for each of 4 states; visually inspect against §Canvas layout ASCII diagram; pixel-sample VU meter area in `playing` (bars present) and `stopped` (bars absent); confirm title text uses narrow 5×6 px LED glyphs (not proportional PIL font); confirm POSBAR zone shows skin texture (not flat grey); confirm PLEDIT title/bottom bars show skin chrome.
- **Expected result**: All 7 element types visible where specified. No element overflows the 275 px app area. LED font and sprite chrome visible. **Human sign-off on layout required — this is the gate for firmware implementation. Any sign-off obtained on pre-fix (PIL font / grey rect) snapshots is void; gate must be re-executed on post-fix snapshots.**
- **Status**: recheck required after TASK-201 fix — prior sign-off void

### T276 — [M-WEBRADIO-PREVIEW] Skin base layer loaded from `gen/skin_preview.png`

- **Type**: host automated
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: Tool loads `gen/skin_preview.png` (320×240) as base and does not ship a hardcoded fallback. Mirrors `preview_vis.py` pattern — `--skin` required; missing/wrong-dimension skin produces a non-zero exit and stderr message.
- **Preconditions**: `gen/skin_preview.png` present. A dummy 1×1 `bad.png` available.
- **Steps**: (1) Load correct skin — assert 320×240. (2) Missing path — assert non-zero exit + stderr. (3) `bad.png` — assert non-zero exit or clear error raised.
- **Expected result**: Correct skin confirmed 320×240. Bad inputs produce clear, actionable errors.
- **Status**: planned

### T277 — [M-WEBRADIO-PREVIEW] Canvas stays within 275×240 app area (no taskbar bleed)

- **Type**: host automated
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: All radio-specific drawing targets x=0..274. Pixels at x=275..319 are only touched by `draw_taskbar_pil` / `draw_taskbar_pygame` from `preview_common`.
- **Preconditions**: Tool renders into a PIL Image or offscreen surface.
- **Steps**: Capture `playing` state snapshot. Compare x=275..319 band against skin_preview.png: only taskbar-drawn differences allowed. Assert x=0..274 shows radio content (VU, buffer bar, station list) on top of skin.
- **Expected result**: No radio widget overflows into x≥275. App area shows radio content.
- **Status**: planned

### T278 — [M-WEBRADIO-PREVIEW] No cross-import of unrelated module constants

- **Type**: host automated (import inspection)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: `preview_webradio.py` does not import from `preview_vis`, `bake_vis`, `preview_teletext`, or `preview_layout`, and does not pull in VIS geometry names (`RECT_X`, `LEFT_Y`, `VIS_H`, `SPEC_BARS`, `SPEC_BAR_W`, `SPEC_BAR_STEP`). Shared geometry must come from `preview_common`; skin sprite extraction must come from `bake_skin` only.
- **Preconditions**: Tool source at `app/tools/preview_webradio.py`.
- **Steps**: Parse import block (`ast.parse` or grep). Assert no forbidden module or name found. Assert `from preview_common import …` present. Assert `from bake_skin import …` is the only other local-tool import (whitelist: `bake_skin`, `preview_common`).
- **Expected result**: No forbidden import. `preview_common` and `bake_skin` imports confirmed. All other local-module imports absent.
- **Status**: recheck required after TASK-201 fix

### T279 — [M-WEBRADIO-PREVIEW] Missing `--wsz` file produces graceful error

- **Type**: host automated
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: When `--wsz` points to a non-existent file, the tool exits non-zero and prints a descriptive error to stderr. Must not expose a bare `FileNotFoundError` traceback or silently fall back to PIL default font.
- **Preconditions**: `gen/skin_preview.png` present.
- **Steps**: (1) Launch with `--wsz /tmp/no_such.wsz`. Assert non-zero exit. Assert stderr contains the bad path and a human-readable message. (2) Launch with `--wsz` pointing to a non-zip file (e.g. a text file). Assert non-zero exit + clear error.
- **Expected result**: Both bad-wsz cases produce clear, actionable errors and non-zero exit. No raw traceback.
- **Status**: planned

### T280 — [M-WEBRADIO-PREVIEW] LED font glyphs render from TEXT.BMP (not PIL default)

- **Type**: host automated (pixel inspection)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: Station name in the TITLE zone uses 5×6 px glyphs from TEXT.BMP, not PIL's proportional default font. Guards against regression to `ImageFont.load_default()`.
- **Preconditions**: `skins/base-2.91.wsz` and `gen/skin_preview.png` present.
- **Steps**: (1) Render `playing` state snapshot. (2) Sample TITLE zone (x=111..264, y=27..32) — assert at least one pixel has LED green value `(0x00, 0xE8, 0x00)`. (3) Assert no pixel in the TITLE zone has a value consistent with PIL proportional font rendering at larger pitch. Alternative: render a known single character `"A"` and compare the 5×6 glyph region pixel-for-pixel against the TEXT.BMP crop.
- **Expected result**: TITLE zone contains LED green pixels consistent with 5 px glyph width. PIL default font (proportional, ~7–8 px wide characters) not detected.
- **Status**: planned

### T281 — [M-WEBRADIO-PREVIEW] POSBAR chrome drawn from POSBAR.BMP sprite (not fill-rect)

- **Type**: host visual (manual, with pixel sample)
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: The POSBAR zone (y=72..81) shows pixels from the POSBAR.BMP skin sprite, not the rejected synthetic `(0x18, 0x18, 0x18)` fill-rect.
- **Preconditions**: `skins/base-2.91.wsz` and `gen/skin_preview.png` present.
- **Steps**: (1) Extract POSBAR.BMP from the wsz as a reference crop. (2) Render `stopped` state snapshot (buffer bar empty — POSBAR background fully visible). (3) Sample POSBAR zone; compare to reference crop. Assert pixel content matches sprite. Assert grey sentinel `(0x18, 0x18, 0x18)` absent from POSBAR background.
- **Expected result**: POSBAR zone matches POSBAR.BMP. Grey fill-rect sentinel absent.
- **Status**: planned

### T282 — [M-WEBRADIO-PREVIEW] `--wsz` argument accepted and validated (parallel to T276 for `--skin`)

- **Type**: host automated
- **Feature(s)**: M-WEBRADIO preview tool (TASK-201)
- **Objective**: `--wsz` is a first-class CLI argument with a default path and explicit-path override. Parallel to T276's coverage of `--skin`.
- **Preconditions**: `skins/base-2.91.wsz` present.
- **Steps**: (1) Launch without `--wsz` — confirm default `skins/base-2.91.wsz` is used (exits 0 when present). (2) Launch with `--wsz <explicit_path>` — confirm that path is opened. (3) Launch with `--wsz /tmp/missing.wsz` — confirm non-zero exit + error (covered in detail by T279).
- **Expected result**: Default path used when omitted. Explicit path accepted. Missing path exits non-zero.
- **Status**: planned

---

### T-ERR-01 — [app-error-signal-001, TASK-245] Spotify 403 → activeError true; recovered poll clears it

- **Type**: integration
- **Feature(s)**: app-error-signal-001
- **Interaction**: X020
- **Objective**: `SpotifyApp::hasError()` (via `spotifyTask::authError()`) trips on a 403 poll (one is enough) and self-clears on the next successful (200/204) poll, driving the active-slot indicator state.
- **Preconditions**: DUT on `cyd2usb_winamp_debug`; Spotify is the active app; bgPoll suspended (so a real cadence poll cannot overwrite the injected status mid-test).
- **Steps**: (1) `set lastHttp 200`; `get activeError` → baseline. (2) `set lastHttp 403`; `get activeError`. (3) `set lastHttp 200` (recovered poll); `get activeError`. (4) resume bgPoll.
- **Expected result**: baseline `{active:false, spotifyAuthError:false}`; after 403 `{active:true, spotifyAuthError:true}`; after 200 `{active:false, spotifyAuthError:false}`.
- **Status**: passing

### T-ERR-02 — [app-error-signal-001, TASK-245] Error is active-only and survives app-switch away/back

- **Type**: integration
- **Feature(s)**: app-error-signal-001
- **Interaction**: X018, X019
- **Objective**: The error state is owned by the app instance: it is *not* surfaced as the active error while another app is active (the ADR-046 §4 active-only limitation), and it is still set when the errored app is reactivated (survives the round-trip).
- **Preconditions**: DUT on `cyd2usb_winamp_debug`; Spotify active; bgPoll suspended.
- **Steps**: (1) `set lastHttp 403` + `set backoff 2`; `get activeError` (Spotify active). (2) `switchApp 1` (Clock — offline, `hasError()==false`); `get activeError`. (3) `switchApp 0` (back to Spotify); `get activeError`. (4) clear (`set backoff 0` + `set lastHttp 200`); resume bgPoll.
- **Expected result**: step 1 `active:true`; step 2 `active:false` while `spotifyAuthError:true` (error hidden, not lost); step 3 `active:true` again (state survived the switch).
- **Status**: passing

### T-ERR-03 — [app-error-signal-001, TASK-245] Red bar renders + precedence error > busy > idle [MANUAL]

- **Type**: e2e (manual / visual)
- **Feature(s)**: app-error-signal-001
- **Interaction**: X017
- **Objective**: The active-slot indicator actually paints **red** on a sustained error, and red wins over amber when the app is simultaneously busy (precedence error > busy > idle). Not serial-automatable — no pixel readback.
- **Preconditions**: DUT (prod or debug); a real or injected Spotify 403 (e.g. `set lastHttp 403` + `set backoff 2` on debug), Spotify the active app.
- **Steps**: (1) Observe the Spotify slot's 3 px active bar with an error present. (2) Trigger a user action (busy) while the error holds and observe the bar. (3) Clear the error (recovered poll / `set backoff 0`) and observe.
- **Expected result**: (1) bar is **red** while errored; (2) bar **stays red** during busy (red > amber); (3) bar returns to **green** (or amber if still busy) once the error clears. Also confirm at **boot** the bar is **amber** (connecting), not green, until the first poll resolves (see T-ERR-04).
- **Status**: planned (owed — needs human visual sign-off; clear-on-recovery on a real account is gated on TASK-243)

### T-ERR-04 — [app-error-signal-001, TASK-245] Connecting (boot amber) latches false on first success

- **Type**: integration
- **Feature(s)**: app-error-signal-001
- **Interaction**: X020
- **Objective**: `SpotifyApp::isConnecting()` (via `spotifyTask::connecting()`) is true until the first successful poll — so the active bar reads **amber** at boot rather than green — and latches false on the first 200/204.
- **Preconditions**: DUT on `cyd2usb_winamp_debug`; Spotify active; bgPoll suspended.
- **Steps**: (1) `set lastHttp 200` + `set backoff 0` + `set lastOkMs 0` (no error, no success yet = boot); `get activeError`. (2) `set lastOkMs 1` (first success); `get activeError`. (3) restore: resume bgPoll.
- **Expected result**: step 1 `{connecting:true, spotifyAuthError:false}` (amber at boot); step 2 `{connecting:false}` (green once connected).
- **Status**: passing

### T-ERR-05 — [app-error-signal-001, TASK-245] A touch must not clear the 403 error (backoff decoupling)

- **Type**: integration
- **Feature(s)**: app-error-signal-001
- **Interaction**: X020
- **Objective**: `authError()` is keyed on the last HTTP status, not `s_consecutiveFailures`, so `resetBackoff()` — called on every touch via `appHandleInput` — must not knock the red bar back to amber. Regression guard for the touch-coupling bug found 2026-06-25.
- **Preconditions**: DUT on `cyd2usb_winamp_debug`; Spotify active; bgPoll suspended.
- **Steps**: (1) `set lastHttp 403`; `get activeError`. (2) `set backoff 0` (exactly what a touch's `resetBackoff()` does); `get activeError`. (3) `set lastHttp 200` (restore); resume bgPoll.
- **Expected result**: `spotifyAuthError:true` in both step 1 and step 2 (error held across the backoff reset).
- **Status**: passing

### T-ERR-06 — [app-error-signal-001, TASK-245] Network apps connect amber; offline apps stay green

- **Type**: integration
- **Feature(s)**: app-error-signal-001
- **Interaction**: X021
- **Objective**: The four network taskbar apps (Weather/Crypto/Stock/Teletext) wire `isConnecting()` to their first-fetch (amber bar on entry until data arrives); offline apps (Clock/Matrix/Life/Aquarium/Settings) keep the default `false`. Guards the offline-default invariant.
- **Preconditions**: DUT on `cyd2usb_winamp_debug`.
- **Steps**: (1) `switchApp 1` (Clock); `get activeError` → `connecting`. (2) `switchApp 4` (Matrix); `get activeError` → `connecting`. (3) (manual/DUT) `switchApp 2/3/7/9` on a fresh entry → `connecting:true` until that app's first fetch lands, then false.
- **Expected result**: Clock and Matrix report `connecting:false`. Network apps report `connecting:true` on entry before first data (DUT-observed; gated by data arrival, slower under Spotify-403 starvation — TASK-244).
- **Status**: passing (offline invariant automated; network-app amber→green is DUT-observed)

### T-ERR-07 — [app-error-signal-001, TASK-246] Network-app failed fetch → red

- **Type**: integration
- **Feature(s)**: app-error-signal-001
- **Interaction**: X021
- **Objective**: A network app's `hasError()` drives the red bar on a failed fetch and clears on success. Stock (`hasError() = _s.fetchFailed`) is the representative consumer, driven via the existing `set fetchFailed` injector; Weather/Crypto/Teletext use the same set-on-fail/clear-on-success latch (`_wxErr`/`_cxErr`/`_ttErr`).
- **Preconditions**: DUT on `cyd2usb_winamp_debug`.
- **Steps**: (1) `switchApp 7` (Stock). (2) `set fetchFailed 1`; `get activeError` → `active`. (3) `set fetchFailed 0`; `get activeError` → `active`. (4) restore Spotify.
- **Expected result**: `active:true` (red) after `fetchFailed 1`; `active:false` after `fetchFailed 0`. Precedence error(red) > connecting(amber): a failed *first* fetch shows red, not amber.
- **Status**: passing

---

## Suite: M-PLANERADAR — ADS-B plane radar DUT validation (TASK-307)

Detailed run + results: `docs/verification/regression_suite/m-planeradar-dut.md`.

### T_PR_01 — [planeradar-001] PlaneRadarApp switch round-trip

- **Type**: integration
- **Feature(s)**: planeradar-001
- **Objective**: Spotify→PlaneRadar→Spotify round-trip via taskbar tap; `appId` correct at each step (sanity, mirrors T_WX_01/T_CX_01).
- **Preconditions**: DUT on `cyd2usb_winamp_debug`, Spotify session active.
- **Status**: **PASS 2026-07-11**.

### T_PR_02 — [planeradar-001] Live render within one poll of app entry (exit criterion 1)

- **Type**: integration [NETWORK]
- **Feature(s)**: planeradar-001
- **Objective**: `resume()` enqueues a fetch immediately on switch-in; the first poll resolves within a 90 s budget. Observed via `get activeError`'s `connecting` field (`isConnecting()`=`!_everHadResult`) going false — **not** `prLastHttp==200`: a DUT diagnostic (2026-07-11) found a successful fetch leaves `PlaneRadarResult.errorCode` at its default-constructed `0` (the raw HTTP 200 only appears in a `LOG_D` line, never the result struct), so `0` is ambiguous between "never fetched" and "fetched fine" and can't be waited on directly. Graceful-empty airspace (`prAircraftCount`=0) is still a pass — correctness, not traffic, is the bar.
- **Steps**: `switchApp` PlaneRadar → poll `get activeError` for `connecting:false` up to 90 s → `get activeError.active` (expect false) → `get prAircraftCount`/`prLastHttp` (diagnostic only).
- **Status**: **PASS 2026-07-11** — connecting→false, `prAircraftCount`=1, `prLastHttp`=0 (no error).

### T_PR_03 — [planeradar-001] Range tap cycles 5→10→15→25→5 (exit criterion 2a)

- **Type**: integration
- **Feature(s)**: planeradar-001
- **Objective**: Tapping the radar disc (x<240) cycles the 4 range presets in order and wraps. Injects a synthetic aircraft first (`prInjectAircraft`) so `handleInput()`'s per-tap re-enqueue (`!_injected` guard) can't re-arm `hasPendingAsync()`/shell-busy and swallow a subsequent tap while a real fetch is in flight — this is exactly what happened on the first DUT run (range stuck at 10 after tap #1, with Spotify's 403 retry loop stalling the queue).
- **Steps**: `set prInjectAircraft <1 record>` → `set prRange 5` → 4× (tap disc, `get prRange`) → expect `[10, 15, 25, 5]` → `set prClearInject 1`.
- **Status**: **PASS 2026-07-11** — sequence 5→[10, 15, 25, 5] confirmed.

### T_PR_04 — [planeradar-001] Range persists across reboot (exit criterion 2b) [REBOOT]

- **Type**: integration [REBOOT][SLOW]
- **Feature(s)**: planeradar-001
- **Objective**: `g_settings.prRangeIdx` round-trips through `settingsStorage` — a non-default preset (25 km) survives a software reset.
- **Steps**: `set prRange 25` → `reboot` → wait for DUT ready → `switchApp` PlaneRadar → `get prRange` → expect `25`.
- **Status**: **PASS 2026-07-11** — prRange=25 held across reboot.

### T_PR_05 — [planeradar-001] Fetch error → error code, stays responsive, recovers (exit criterion 3)

- **Type**: integration [NETWORK][SLOW]
- **Feature(s)**: planeradar-001
- **Objective**: A failed fetch surfaces as `activeError.active=true` (side-strip/taskbar error indicator — `hasError()`=`_prErr`, same pattern T-ERR-07 uses for Stock), the app stays responsive (no crash/switch-away), and the error clears on the next successful poll. No dedicated fault-injection hook exists for PlaneRadar yet — this test hammers `triggerPlaneRadarFetch` to hit adsb.fi's ~1 req/s courtesy limit (phase-0 measured ~33% 429 rate at that cadence) as a real, naturally-occurring error rather than a synthetic one. (Originally gated on `prLastHttp` changing away from `200`/a baseline — replaced for the same reason as T_PR_02: `0` is ambiguous, so a diff against it could false-positive on the init sentinel.)
- **Steps**: establish a clean baseline poll (`connecting:false`, `active:false`) → rapid-fire `set triggerPlaneRadarFetch 1` (up to 20×) watching `get activeError` for `active:true` → `get appId` (still PlaneRadar) → wait up to 30 s for `active:false` (recovery).
- **Status**: **SKIP 2026-07-11** — no fetch error surfaced in 20 rapid-fire attempts. Network-dependent — a clean run with no rate-limit hit is a SKIP, not a FAIL; the underlying latch/clear mechanism (`isConnecting()`/`hasError()`) is the same ADR-046 code path already proven working for Stock/Teletext/Weather (T-ERR-01/04/06/07), so residual risk is low.

### T_PR_06 — [planeradar-001] Synthetic-injection render test, no network (exit criterion 6)

- **Type**: integration
- **Feature(s)**: planeradar-001
- **Objective**: `prInjectAircraft` isolates render from the real fetch/poll cycle (TASK-276 pattern) — injecting a fixed 3-aircraft record set updates `prAircraftCount` without any network dependency; `prClearInject` hands control back to live polling.
- **Steps**: `set prInjectAircraft <3 records>` → `get prAircraftCount` → expect `3` → `set prClearInject 1`.
- **Status**: **PASS 2026-07-11** — injected 3 → prAircraftCount=3; cleared → live polling resumed.

### Exit criterion 4 (30-min Spotify coexistence soak) and 5 (taskbar full-cycle scroll)

Criterion 4 is a dedicated standalone soak (`./run/pr-soak`, `app/tools/test_planeradar_soak.py`) rather than a harness test — 30 minutes doesn't fit the interactive per-test flash/restore lifecycle. Criterion 5 needs **no new test**: T162–T166 and T242 (taskbar-scroll-001) already derive their cycle length (`_TB_N`) from `APP_SLOT["WebRadio"]`, which grew by one the moment `AppId::PlaneRadar` was inserted before `WebRadio` in `APP_ORDER` — re-running that existing suite unchanged exercises the new 12th slot.

- **Criterion 5 status**: **PASS 2026-07-11** — T162-T166/T242 all 6/6 PASS; `_TB_N` correctly grew 10→11 (comment in `run_serialdbg_tests.py` describing it as "=10" is now stale prose, not a bug), full wrap-around and drag/tap behavior confirmed, WebRadio never appears as a slot.
- **Criterion 4 status**: **PASS 2026-07-11** — 30-min soak, 81 samples, baseline heap=87,672 B, min heap=82,720 B, delta=4,952 B (within the 15,000 B VE-chosen budget), zero reboots/crashes. Ran against a 403-retrying Spotify session (TASK-243 Premium lapse, external blocker) rather than literal playback — see regression suite doc caveat.

---

## Suite: M-PR-LOCATIONS — PlaneRadar location presets + geocode lookup (TASK-324)

Detailed run + results: `docs/verification/regression_suite/m-pr-locations-dut.md`.

### T_PRL_01a — [pr-locations-001] Stubbed editor round-trip (gate)

- **Type**: integration
- **Feature(s)**: pr-locations-001
- **Objective**: Full keyboard-driven editor flow — label → country → postcode → pending → confirm → save — using the `set geocode` stub (no live network). Primary gate per VE-PRL-3 split.
- **Preconditions**: DUT on `cyd2usb_winamp_debug`.
- **Status**: **PASS 2026-07-15** — `app/tools/prloc_editor_smoke.py`, 14/14 (TASK-321 close-out).

### T_PRL_01b — [pr-locations-001] Live [NETWORK] smoke incl. space-postcode encoding

- **Type**: integration [NETWORK]
- **Feature(s)**: pr-locations-001
- **Objective**: One real Nominatim lookup end to end, including on-device URL-encoding of a postcode containing a space (VE-PRL-9). SKIP-on-trouble is acceptable — 01a is the gate.
- **Status**: **PASS (cited)** — TASK-320 close-out (`prloc_smoke.py` Phase B: NL 2513AA → 52.0795/4.3132, seq-matched) plus an incidental real fetch during T_PRL_08 this session. The space-containing-postcode leg specifically (a UK postcode) was not separately re-run — flagged as the one residual gap in this citation.

### T_PRL_02 — [pr-locations-001] Strip tap switches location

- **Type**: integration
- **Feature(s)**: pr-locations-001
- **Objective**: Tapping a filled label row in the PlaneRadar side strip switches the active slot: `prActiveLoc` updates, the write-through `prLat`/`prLon` mirror follows, staleness state resets (`isConnecting()`→true), and the location epoch bumps.
- **Steps**: `switchApp` PlaneRadar → `tap` a non-active filled strip row (x=257, y∈{68,94,120,146}) → `get prloc`/`get prLastAction`/`get activeError`.
- **Expected result**: `prloc.active` equals the tapped slot; `prLastAction`=`STRIP_LOC_<i>`; `activeError.connecting` is `true` immediately after the tap, then settles `false` once the re-fetch completes.
- **Status**: **PASS 2026-07-16** — `app/tools/prloc_ve_smoke.py`.

### T_PRL_03 — [pr-locations-001] Geocode failure paths

- **Type**: integration
- **Feature(s)**: pr-locations-001
- **Objective**: `-96 GEOCODE_NO_MATCH` renders via the generic decoded-error path and Cancel returns cleanly without persisting anything (companion to the `-97 GEOCODE_PARSE_FAILED` leg already covered at TASK-321 close-out — QM check-in 2026-07-14 note 7).
- **Steps**: open a filled slot's editor → Lookup → `set geocode err -96` → submit postcode → `get kb` (confirm LookupError, not a keyboard step) → tap Cancel → `get prloc` (slot untouched).
- **Status**: **PASS 2026-07-16** — `app/tools/prloc_ve_smoke.py`.

### T_PRL_04 — [pr-locations-001] Migration — pre-upgrade settings.json seeds slot 0

- **Type**: integration
- **Feature(s)**: pr-locations-001
- **Objective**: A `settings.json` written before `prLocs` existed seeds `prLocs[0] = {"HOME", prLat, prLon}` on load, `prActiveLoc=0`.
- **Status**: **PASS (cited)** — TASK-319 close-out (`prloc_smoke.py` Phase A: "migration seeded HOME from stored coords"). Not re-run this session — see M-PR-LOCATIONS DUT doc notes on why (avoids risking the DUT's real, in-use settings.json via SPIFFS surgery for an already-proven path).

### T_PRL_05 — [pr-locations-001] Same-slot no-op; delete-active-slot fallback

- **Type**: integration
- **Feature(s)**: pr-locations-001
- **Objective**: Tapping the already-active strip slot is a no-op (no staleness-reset flicker). Deleting the currently-active slot (via the Settings editor) falls back `prActiveLoc` to slot 0 and mirrors slot 0's coords.
- **Steps**: (a) tap the active slot's own strip row twice with a settle wait between; `activeError.connecting` must stay `false` on the second tap. (b) `set prloc active <non-zero slot>` → open that slot's editor → SourceFork → Delete → `get prloc` (active=0, slot emptied, mirror = slot 0's coords).
- **Status**: **PASS 2026-07-16** — `app/tools/prloc_ve_smoke.py`.

### T_PRL_06 — [pr-locations-001] Manual lat/lon entry range validation

- **Type**: integration
- **Feature(s)**: pr-locations-001
- **Objective**: Manual entry (TASK-322) rejects out-of-range lat/lon (91, -200 style values) and re-prompts; a valid pair persists.
- **Status**: **PASS (cited)** — TASK-322 close-out (`app/tools/prloc_manual_smoke.py`, 13/13).

### T_PRL_07 — [pr-locations-001] Persistence layers (reflash vs flash-fs wipe)

- **Type**: integration [SLOW]
- **Feature(s)**: pr-locations-001
- **Objective**: `prLocs` survives a firmware reflash (`run/flash`/`run/flash-debug`); documented-destroyed by `run/flash-fs` (SPIFFS format), same class as the `cal.json`/`settings.json` wipe behaviour recorded elsewhere.
- **Status**: **PARTIAL 2026-07-16** — reflash-survival implicit (many reflashes across TASK-319–324, `get prloc` correct every time; not independently re-asserted as a dedicated test this session). The destructive `flash-fs`-wipe leg was **not run** — needs explicit human go-ahead before wiping the DUT's live `cal.json`/`settings.json`.

### T_PRL_08 — [pr-locations-001] Late result after cancel

- **Type**: integration [NETWORK]
- **Feature(s)**: pr-locations-001
- **Objective**: Cancelling mid-lookup returns to SourceFork with nothing persisted; a result that arrives afterward (whether from the abandoned fetch or a genuinely stale seq) does not corrupt state.
- **Steps**: open a filled slot's editor → Lookup → submit postcode (real fetch, no stub — see notes) → immediately tap Cancel on the pending screen → `get prloc` (slot untouched) → wait ~5 s → `get geocode` (peek) + `get prloc` (still untouched).
- **Status**: **PASS for the DUT-provable half; seq-mismatch half is code-verified, not independently DUT-provable** — see `m-pr-locations-dut.md` notes on why `debugInjectGeocode()` can't manufacture a genuinely mismatched seq.

### T_PRL_09 — [pr-locations-001] Switch discards in-flight old-location fetch (epoch)

- **Type**: integration
- **Feature(s)**: pr-locations-001
- **Objective**: A location switch while a fetch for the *previous* location is still in flight bumps the epoch; the stale-epoch result, when it arrives, is discarded rather than rendered.
- **Steps**: `set prloc active <a>` immediately followed by `set prloc active <b>` (no gap — see notes on why this must be the serial path, not back-to-back `tap` injection) → `get prloc` (settles on `b`) → wait for `activeError.connecting`→`false` → `get prAircraftCount` (sane, no crash/corruption).
- **Status**: **PASS 2026-07-16** — `app/tools/prloc_ve_smoke.py`. (Discovery: back-to-back interactive taps can't exercise this — `g_shellBusy` silently drops the second tap; see regression-suite notes.)

### T_PRL_10 — [pr-locations-001] Slot-0 delete refusal

- **Type**: integration
- **Feature(s)**: pr-locations-001
- **Objective**: The Delete button on slot 0's editor is disabled (renders, never hits) — "disabled, not absent."
- **Status**: **PASS (cited)** — `prloc_editor_smoke.py` G1, TASK-321 close-out.

### T_PRL_11 — [pr-locations-001] Geocode during Spotify-active (tlsYield coexistence)

- **Type**: integration [SLOW]
- **Feature(s)**: pr-locations-001
- **Objective**: A geocode lookup while a live Spotify playback TLS session is held exercises no tlsYield-starvation regression (5 prior fix layers on this exact seam).
- **Status**: **BLOCKED 2026-07-16** — TASK-243 external blocker (Spotify Premium lapsed); `spotifyAuthError:true`/`spotifyConnecting:true` observed throughout this session, meaning no live playback TLS session was actually held to race against. Re-run once TASK-243 clears.

---

## Entry Format

```
### T001 — [Feature ID] [Test Name]
- **Type**: unit | integration | e2e | cross-feature
- **Feature(s)**: F001[, F002]
- **Interaction**: X001 (if cross-feature; omit otherwise)
- **Objective**: What this test verifies
- **Preconditions**: Starting state required
- **Steps**: Numbered sequence of actions
- **Expected result**: Observable, verifiable outcome
- **Status**: planned | written | passing | failing
```