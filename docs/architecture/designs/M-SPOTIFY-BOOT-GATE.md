# Design — M-SPOTIFY-BOOT-GATE: gate spotifyTask's TLS connect on g_settings.playerMode

> Owner: Architect
> Status: accepted (2026-07-19, human sign-off)
> Date: 2026-07-19
> Feeds: ADR-054 (accepted)
> Tracked-as: — (PM to file)
> Registers: X038 (`player-state-001` × `poll-001`, `cross_feature_matrix.yaml`) — see §Registers

## Context / pain points

`spotifyTask::begin(&spotify)` (`app/src/main.cpp:2372`) — which spawns Spotify's
async HTTP polling task and shortly after connects its persistent TLS session —
is gated **only** by the `DISABLE_SPOTIFY` compile-time macro (a separate,
Spotify-free no-PSRAM build variant, `docs/architecture/designs/
M-WEBRADIO-SPOTIFY-DISABLE.md`, TASK-255 — a different binary entirely, not
the standard `cyd2usb_winamp` production build). It is **not** gated on
`g_settings.playerMode` (`enum class PlayerMode : uint8_t { Spotify = 0,
WebRadio = 1 }`, `app/src/settingsStorage.h:21`) at all — the persisted
runtime preference that governs which app the device boots into
(`main.cpp:2402-2409`, "TASK-260 v2 (OQ-BOOT)"). So on the standard
production build, a boot where the user's own persisted preference is
`WebRadio` still spins up Spotify's task and (as this investigation found,
below) connects its TLS session — regardless of user intent for that
session.

**Primary justification** (per the task that produced this doc): why spin up
and connect a service the user's own persisted preference says they don't
want active this session? A **complementary side effect**, not the primary
driver: a WebRadio-mode boot that never triggers Spotify's TLS connect also
avoids the heap fragmentation `docs/architecture/designs/
M-HEAP-FRAGMENTATION.md` / `ADR-053` measured and parked — see §Finding 2
below for why gating `begin()` alone does **not** actually deliver that side
effect without a companion change.

This design is evaluated independently of M-HEAP-FRAGMENTATION/ADR-053
(both **parked**, human declined Option E for now) — not a resurrection or a
workaround of that parked work.

### Finding 1 — TASK-264 (Q3-a) already built 95% of this; it has an unrecognized boot-race gap

`spotifyTask` already has exactly the mechanism this design would otherwise
need to invent: `setWebRadioActive(bool)` (`spotifyTaskStorage.cpp:605-611`,
TASK-264/Q3-a), called from **every** `switchApp()` transition
(`main.cpp:1973-1977`):

```cpp
// TASK-264 (Q3-a): drop Spotify TLS when WebRadio is active (reclaims ~50 K arena).
#ifndef DISABLE_SPOTIFY
  spotifyTask::setWebRadioActive(next == AppId::WebRadio);
#endif
```

When `active == true` it sets `s_webRadioActive` and kicks
`s_resetTlsPending`; `taskBody()`'s loop top (`spotifyTaskStorage.cpp:370-377`)
then holds `client.stop()` + a 500 ms idle instead of ever polling. This
*is* called on the boot path: `main.cpp:2407-2409` calls
`switchApp(AppId::WebRadio)` when `wifiConnected && g_settings.playerMode ==
WebRadio`, which reaches the exact same `setWebRadioActive(true)` call.

**But it doesn't work at boot, because of a race in `taskBody()`'s loop
shape**, confirmed by direct reading of `spotifyTaskStorage.cpp:328-417`:
`s_resetTlsPending`, `s_tlsYieldReqCount`, and `s_webRadioActive` are only
checked **once, at the top of the `for(;;)` loop, before `xQueueReceive`
blocks**. After `xQueueReceive` returns (whether by dequeuing a real request
or timing out and self-issuing `ACT_POLL`), the code falls straight through
to dispatching the action (`doPoll()` for `ACT_POLL`) — it does **not**
re-check `s_webRadioActive` before that dispatch. Sequence, confirmed by
reading `begin()` (task spawns with an empty queue, base cadence
`kPollPeriodMs = 5000 ms`, `spotifyTaskStorage.cpp:43/382`) and boot order
(`main.cpp:2371-2409`, nothing enqueues to `reqQueue` between `begin()` and
the boot's `switchApp(WebRadio)` call — verified by reading `SpotifyApp::
init()`, `main.cpp:208-210`, which only paints a screen):

1. `t=0`: `begin()` spawns the task. Iteration 1 starts, `s_webRadioActive`
   is still `false` (nothing has set it yet) — the loop proceeds past all
   three top-of-loop checks and blocks in `xQueueReceive` for up to 5000 ms.
2. `t≈+100 ms` (a few more `Serial` lines + app inits later, well inside the
   block): boot reaches `switchApp(AppId::WebRadio)`, which calls
   `setWebRadioActive(true)` — `s_webRadioActive` and `s_resetTlsPending`
   both flip true. This does **not** wake the blocked `xQueueReceive` — only
   `xQueueSend`/`xQueueSendToFront` do that, and nothing sends.
3. `t=5000 ms`: `xQueueReceive` times out (`pdFALSE`), the loop self-issues
   `ACT_POLL`, falls through the (now-true but **unchecked-here**)
   `s_tlsYieldReqCount`/`s_webRadioActive` state, and calls `doPoll()` —
   **the first TLS connect happens here, unconditionally, ~5 s after
   `begin()`, regardless of `playerMode`.**
4. Only on iteration 2 (after `doPoll()` returns) does the loop re-reach the
   top and finally honor `s_webRadioActive == true`, idling from then on.

So today, a `playerMode == WebRadio` boot **still connects Spotify's TLS
once**, ~5 seconds after `begin()`, before TASK-264's own mechanism gets a
chance to prevent it — the mechanism is real and correct for *mid-session*
toggles (proven, see §Finding 4), it simply never got a chance to run before
the first connect on the *boot* path, because nothing seeds its flag before
task creation.

### Finding 2 — the eager access-token refresh at setup() already connects TLS on the SAME shared client, before `begin()` is even reached — independent of any gate on `begin()`

`main.cpp:2363` calls `spotifyRefreshToken(refreshToken)`
(`Spotify-Diy-Thing/SpotifyDiyThing/spotifyLogic.h:66-78`) **unconditionally**,
9 lines before `spotifyTask::begin()` (`main.cpp:2372`). Reading it:

```cpp
void spotifyRefreshToken(const char *refreshToken) {
  spotify.setRefreshToken(refreshToken);
  if (!spotify.refreshAccessToken()) { ... }
}
```

`spotify` (`spotifyLogic.h:9`) is `SpotifyArduino spotify(client, NULL,
NULL)` — the **same global `client` (`WiFiClientSecure client;`,
`main.cpp:72`)** that `spotifyTask`'s poll loop later uses
(`spotifyTaskStorage.cpp:20`, `extern WiFiClientSecure client;`).
`refreshAccessToken()` → `makePostRequest(SPOTIFY_TOKEN_ENDPOINT, ...,
SPOTIFY_ACCOUNTS_HOST)` → `SpotifyArduino::makeRequestWithBody()`
(`app/lib/SpotifyArduino/src/SpotifyArduino.cpp:46-66`) calls
`client->connect(host, portNumber)` directly — a real TLS handshake to
`accounts.spotify.com`, over the identical `client`/mbedTLS-session object
whose *first* connect M-HEAP-FRAGMENTATION measured carving and
permanently splitting ~30-40 KB out of the largest free heap block. Per
that investigation's own finding, **the split survives tear-down** — so
this eager refresh call, happening in `setup()` before `spotifyTask::begin()`
is even reached, likely already triggers the identical fragmentation event,
on **every boot, regardless of `playerMode`.**

**Consequence for this design:** gating `spotifyTask::begin()` (Finding 1's
fix) alone delivers the **primary ask** (don't run Spotify's polling
service when the user doesn't want it) but does **not**, by itself, deliver
the side-effect heap benefit the background motivation for this task
anticipated. Realizing that side benefit requires *also* deferring this
eager refresh call — see §Design space Option B, companion change 2.

### Finding 3 — the eager refresh is functionally redundant; the library already refreshes lazily

`SpotifyArduino` already has `autoTokenRefresh = true` by default
(`SpotifyArduino.h:260`) and calls `checkAndRefreshAccessToken()`
(`SpotifyArduino.cpp:334-344`) automatically before **every** real API call
(`getCurrentlyPlaying`, `getQueue`, `nextTrack`, etc. — confirmed at 8+ call
sites in `SpotifyArduino.cpp`). `checkAndRefreshAccessToken()`'s logic:

```cpp
bool SpotifyArduino::checkAndRefreshAccessToken() {
  unsigned long timeSinceLastRefresh = millis() - timeTokenRefreshed;
  if (timeSinceLastRefresh >= tokenTimeToLiveMs) return refreshAccessToken();
  ...
}
```

Both `timeTokenRefreshed` and `tokenTimeToLiveMs` default to 0, so on a
fresh boot with no explicit refresh yet, this condition is true and the
**first real API call auto-refreshes anyway.** The explicit eager call at
`main.cpp:2363` is therefore not load-bearing for correctness — only
`spotify.setRefreshToken(refreshToken)` (a pure string store, zero network,
same line) needs to run at boot to prime the library; the network round
trip can be deferred to whenever the first real call happens, with the
library's own existing mechanism picking it up automatically.

### Finding 4 — toggle-back-to-Spotify already works, is already DUT-shaped, and doesn't get worse with repeated toggling

Both eject-to-Spotify sites (`app/src/webRadioApp.h:749-750`,
`:962-963`) call `persistPlayerMode(Spotify)` then `switchApp(AppId::
Spotify)`, which reaches the exact same `setWebRadioActive(false)` path —
**already shipped, DUT-proven infrastructure (TASK-264), not something this
design needs to build.** Unlike the boot case (Finding 1), there's no race
here: the transition happens while the task is idling inside the
`s_webRadioActive` branch's `vTaskDelay(500 ms)`, and the very next loop
iteration (≤500 ms later) re-checks the now-false flag and falls through to
`xQueueReceive` — reconnecting at the base cadence (`kPollPeriodMs =
5000 ms`, no backoff accrued since idling never touches
`s_consecutiveFailures`). Total worst-case latency until the next poll
attempt: ≤5.5 s, plus the TLS handshake itself. This is **already the
production behavior today**, independent of this design — this design adds
no new latency characteristic on toggle-back, and per `ADR-046`'s "connecting"
amber state (`SpotifyApp::isConnecting()` → `spotifyTask::connecting()` →
`s_lastSuccessfulPollMs == 0`), this exact latency window is already the
UI-tolerated case the taskbar bar was designed to show amber for. It does
**not** compound on repeated toggling — the task, stack, and queue are never
torn down, only the TLS session cycles, so every toggle-back pays the same
bounded cost, not a growing one.

### Finding 5 — a required companion change: the DUT test harness's readiness wait hard-blocks on a Spotify poll

`run_serialdbg_tests.py`'s `Dut._wait_for_ready()`
(`app/tools/run_serialdbg_tests.py:98-204`) — called on **every** DUT
connection, i.e. at the start of every test run — waits up to 60 s (plus a
`reconnect` retry and another 60 s, ~120 s worst case) for
`"[spotify.poll] ok 200"` **and** `"[spotify.queue] status="` log lines
before considering the DUT ready. The **only** existing bypass is a
`get variant` probe reporting `"spotify":"off"` — the build-time
`DISABLE_SPOTIFY` case (TASK-255's V0 deliverable, comment at
`run_serialdbg_tests.py:153-156`: *"On the Spotify-disabled build there is
no spotifyTask, so the first-poll wait below never completes... probe `get
variant`; on spotify=off, skip the poll wait."*).

If this design ships, a DUT left persisted in `playerMode == WebRadio`
(a completely ordinary state — any prior manual session or test run that
exercised WebRadio and didn't explicitly restore Spotify mode before
disconnecting) would **never** emit `[spotify.poll] ok 200` on that boot —
`spotifyTask` stays deliberately idle. Every subsequent
`Dut()` connection (i.e. every test-harness invocation) would eat the full
~120 s hang before running a single test, with no functional problem on the
device — a real, load-bearing regression to the harness, not a hypothetical
one. **This is not optional polish: it must ship as part of this design**,
mechanically identical in shape to the existing `spotify=off` branch —
add a branch keyed on `get playerMode` reporting `webradio` (or a new,
purpose-built `get variant` field) that accepts "WiFi up + shell responsive"
as ready, exactly like the `DISABLE_SPOTIFY` branch already does.

### Existing infrastructure surveyed

- **TASK-264/Q3-a (`setWebRadioActive`)** — see Finding 1. The direct
  mechanism this design extends, not replaces.
- **M-RECLAIM (`docs/architecture/designs/M-RECLAIM-dynamic-resident.md`)**
  — designed Q3-a (shipped, this is it) vs. Q3-b (`vTaskDelete()` the whole
  task, unshipped, parked). Its own reasoning is the cleanest citation for
  why "keep the task, only gate the connect" avoids a null-safety audit:
  *"Q3-a sidesteps this entirely (task object survives)"*
  (`M-RECLAIM-dynamic-resident.md:122`), contrasted with Q3-b's flagged cost
  *"a null-safety audit across every unconditional `spotifyTask::` accessor
  (LL-085 family)"* (`M-RECLAIM-dynamic-resident.md:120-121`, echoed in
  M-HEAP-FRAGMENTATION's Option B discussion). This design's recommended
  shape (§Lean) is a direct, boot-time extension of the *already-accepted*
  Q3-a reasoning — not a new architectural stance.
- **M-WEBRADIO-SPOTIFY-DISABLE.md (TASK-255, `DISABLE_SPOTIFY`)** — the
  build-time-permanent-absence precedent. Its V2 section confirms the
  null-safety story for "task never created, ever" is genuinely audited and
  complete for that build (link-safety verified across `stackHighWaterBytes
  ()`, `stackSizeBytes()`, `activeError()`, `dbgGet/dbgSet`, `reconnect` —
  each either null-checks `reqQueue`/`g_taskHandle`/`s_tlsYieldedSem`
  explicitly, or reads a plain static that defaults safely without touching
  those handles at all, e.g. `authError()`/`connecting()`/`isHealthy()`).
  Its V0 section is the direct precedent for Finding 5's required harness
  fix — same shape (`get variant` branch), different trigger.
- **`resolvePlayerSlot()` / taskbar (`main.cpp:1865-1867`,
  `renderActiveIndicator`, `ADR-046`).** `resolvePlayerSlot()` reads only
  `g_settings.playerMode`, never `spotifyTask` state — unaffected by this
  design. The taskbar active-bar reads the **active app's**
  `hasError()`/`isConnecting()` (`App` base-class virtuals, `ADR-046`);
  `SpotifyApp::isConnecting()` → `spotifyTask::connecting()` already
  degrades correctly to "always connecting" (amber) while the task has
  never successfully polled — exactly the right rendering for "Spotify
  hasn't been asked to connect yet," no change needed (see Finding 4).

## Goals

1. `spotifyTask` does not attempt a network connection on a boot where the
   user's persisted `playerMode` is `WebRadio` (the primary ask).
2. As a validated (not merely assumed) consequence, such a boot also does
   not trigger the TLS-connect-driven heap fragmentation
   M-HEAP-FRAGMENTATION measured — which Finding 2 shows requires an
   explicit companion change, not something gating `begin()` delivers for
   free.
3. Toggling to Spotify mid-session (eject / Settings) — a normal, expected,
   already-tested user action — continues to work, reusing shipped
   infrastructure rather than inventing new lifecycle machinery.
4. No new null-safety audit burden: every currently-unconditional
   `spotifyTask::` accessor must remain safe to call regardless of whether
   the task has ever polled — ideally by construction, not by an added
   audit pass.
5. No regression to the DUT test harness's readiness detection (Finding 5).
6. Don't reopen or resolve M-HEAP-FRAGMENTATION/ADR-053 — parked,
   out of scope; a boot-time fragmentation-avoidance side effect here is
   welcome but not a rationale to revisit that parked design.

## Design space (options + tradeoffs)

### A — Fully lazy start: defer `begin()` (and the eager token refresh) to first real use
Skip `spotifyRefreshToken()`'s network leg and `spotifyTask::begin()`
entirely on a `playerMode == WebRadio` boot; call both, for the first time,
at the moment the user's first mid-session toggle-to-Spotify fires.

**Reject as primary.** This is the shape the task's own framing worried
about ("is `begin()` mechanically capable of being called later than
`setup()`?") — and the answer is: probably yes as a mechanical matter (WiFi
and NTP are already up by the time any toggle could happen), but it
reopens exactly the null-safety question Goal 4 wants to avoid *by
construction*. Under Option A, `reqQueue`/`g_taskHandle`/`s_tlsYieldedSem`
stay `nullptr` for the **entire WebRadio session** — potentially hours, not
the brief always-present-or-never-present cases the existing null-guards
were proven against (Finding 5's harness fix would also still be needed,
unchanged). M-RECLAIM's own Q3-b analysis already priced this exact class
of audit (`M-RECLAIM-dynamic-resident.md:120-121`) as real, non-trivial
cost — and that was for a *simpler* case (permanent build-time absence)
than this option's *reversible, runtime, open-ended-duration* absence.
Option B below achieves the same primary goal with **zero** null-safety
delta, because it never lets the handles be null in the first place. Not
worth the extra engineering and audit risk for no additional benefit over
B. Parked as a fallback if DUT evidence later shows Option B's seed
mechanism (below) has a gap Option A would close — not expected.

### B — Keep `begin()` unconditional; seed the TLS-idle flag before the task's first iteration (LEAN)
Direct, minimal extension of the already-shipped TASK-264/Q3-a mechanism
(Finding 1), closing its boot-race gap rather than replacing it:

1. **Compute the boot target once, matching the existing boot-switch
   condition exactly** (`main.cpp:2407`'s own guard, factored into a named
   local before it's needed): `bool bootIntoWebRadio = wifiConnected &&
   (g_settings.playerMode == (uint8_t)PlayerMode::WebRadio);`. **This must
   NOT simply read `g_settings.playerMode` on its own** — the no-WiFi edge
   case matters: if WiFi isn't up at boot, `main.cpp:2407`'s guard already
   keeps `currentAppId == Spotify` (visible on screen) regardless of the
   persisted preference, and the Spotify app the user is actually looking
   at must still be allowed to connect once WiFi comes up via the
   background supervisor. Seeding the TLS-idle flag from raw `playerMode`
   without the `wifiConnected` term would silently strand a *visibly
   Spotify* boot in permanent idle — a real regression, not a hypothetical
   one, caught by mirroring the exact condition the existing boot switch
   already uses rather than inventing a second one.
2. **`spotifyTask::begin()` gains a `bool startIdle` parameter**, seeding
   `s_webRadioActive = startIdle` **before** `xTaskCreatePinnedToCore()` is
   called — so the task's very first loop iteration already sees the flag
   as true (if applicable) at its first top-of-loop check, before ever
   reaching `xQueueReceive`/`doPoll()`. This closes Finding 1's race
   directly: there is no longer a window where the flag arrives too late
   for the loop to have already committed to a connect. `main.cpp:2372`
   becomes `spotifyTask::begin(&spotify, bootIntoWebRadio);`.
3. The **existing** `switchApp(AppId::WebRadio)` call at `main.cpp:2408`
   still fires under the same condition and still calls
   `setWebRadioActive(true)` — now purely confirmatory/idempotent (the flag
   is already true), not load-bearing. No change needed there.
4. **Toggle-back is untouched** — Finding 4's existing, shipped,
   already-DUT-exercised path (`setWebRadioActive(false)` via
   `switchApp(Spotify)`) continues to work exactly as today, because
   nothing about the task's lifecycle changes, only its *initial* flag
   value.
5. `reqQueue`, `g_taskHandle`, `s_tlsYieldedSem` are **always** created —
   Goal 4 satisfied by construction, not by an added audit (same reasoning
   M-RECLAIM already used to justify shipping Q3-a over Q3-b).

**Companion change 1 (required to satisfy Goal 2 — Finding 2/3):** gate the
*eager* `refreshAccessToken()` network call the same way. At `main.cpp:2363`,
under `bootIntoWebRadio`, call only `spotify.setRefreshToken(refreshToken)`
(primes the library, zero network) and skip the `spotify.refreshAccessToken()`
leg; rely on `SpotifyArduino`'s already-used `checkAndRefreshAccessToken()`
(`autoTokenRefresh` default `true`, Finding 3) to perform the refresh lazily
on whatever the first real API call turns out to be — which, under this
design, only happens after an explicit toggle-to-Spotify. Not new library
behavior, just not forcing it early. The `forceRefreshToken`
(GPIO0-held-at-boot) / `launchRefreshTokenFlow()` path (`main.cpp:2338-2361`,
missing/invalid-refresh-token bootstrap) is **unaffected** — it's a
credential-acquisition flow, orthogonal to whether the ongoing poll session
connects, and stays unconditional. **Consequence:** a revoked/expired
refresh token surfaces at first-toggle-to-Spotify instead of immediately at
boot, for a WebRadio-mode boot only — an acceptable trade given the whole
point is "don't touch Spotify until asked."

**Companion change 2 (required — Finding 5):** `run_serialdbg_tests.py`'s
`_wait_for_ready()` needs a `playerMode`-aware readiness branch, mechanically
identical in shape to the existing `spotify=off` branch (`:153-171`) — WiFi
up + shell responsive is "ready" when the persisted mode is `WebRadio` (no
poll to wait for), same as the `DISABLE_SPOTIFY` case. VE-owned; a firmware
`get playerMode` command already exists (`main.cpp:3129-3133`) for the probe.

**Why this wins over A:** delivers Goals 1-3 with zero null-safety delta
(Goal 4), reuses 100% of already-shipped/DUT-proven mechanism for the
toggle-back path, and is a small, auditable diff (one new `begin()`
parameter + one boot-time conditional + one refresh-call conditional) built
entirely on infrastructure this project already trusts.

### C — "Defer only the TLS connect, task/queue/refresh always run eagerly"
This is what Finding 1 shows the codebase *believes* it already has
(TASK-264/Q3-a wired to the boot switch) — but doesn't actually deliver,
because of the unrecognized race. Once the race is fixed, this option and
Option B are the same option — B **is** C, done correctly. Not listed as a
separate line item in §Lean; folded into B's narrative rather than presented
as a distinct alternative, since presenting it separately would imply
Option B invented new mechanism where it only fixed a latent gap in
existing mechanism.

### D — Do nothing structural; just move `spotifyTask::begin()` later in `setup()`
Reordering without gating changes **when** the connect happens, not
**whether** it happens on a `WebRadio`-mode boot — doesn't touch Goal 1 at
all. Stated for completeness per the task brief; **reject**, no further
analysis warranted.

## Lean / decision

**Adopt Option B**, with both companion changes bundled as part of the same
change (not a follow-on): (1) seed `spotifyTask`'s TLS-idle flag before task
creation, keyed on the same `wifiConnected && playerMode == WebRadio`
condition the existing boot-switch already uses; (2) skip the eager
`refreshAccessToken()` network leg (keep `setRefreshToken()`) under the same
condition, relying on the library's existing lazy auto-refresh; (3) add the
`playerMode`-aware branch to the DUT harness's readiness wait.

Companion changes 1 and 2 are both required for this design to actually
deliver what it sets out to deliver (Goals 1/2 and Goal 5 respectively) —
shipping only the `begin()` seed (companion 1 omitted) would still leave the
eager-refresh TLS connect firing on every boot regardless of playerMode
(Finding 2), silently failing to deliver the side-benefit the background
motivation named; shipping without companion 2 would silently degrade every
future DUT test run whenever a device happens to be left in WebRadio mode
(Finding 5). If the human wants to scope this down to *only* the primary ask
(Goal 1, not Goal 2's side-benefit), companion 1 can be dropped — but
companion 2 is not optional under any scoping, since it's required
regardless of whether the eager-refresh gating ships (Finding 1's fix alone
already changes whether `[spotify.poll] ok 200` appears on a WebRadio-mode
boot).

Explicitly **not** adopted: Option A (rejected — real, avoidable
null-safety/engineering cost for no benefit over B), Option D (rejected —
doesn't address the goal).

## Open questions

- **OQ1 (companion 1 scope decision).** Confirmed by Finding 2/3 that
  companion change 1 (defer the eager token refresh) is required to deliver
  the side-benefit, and mechanically low-risk (the library already performs
  this exact refresh lazily via `checkAndRefreshAccessToken()`, this is
  "don't force it early," not new behavior). Human sign-off needed on
  whether to bundle it (full Goals 1+2) or ship Goal 1 only and treat the
  side-benefit as a documented non-outcome for now.
- **OQ2 (boot-log observability).** Worth an explicit `Serial.println`
  token (mirroring `"[boot] spotify=off"`, `main.cpp:2380`) when
  `bootIntoWebRadio` is true, e.g. `"[boot] spotify=idle (playerMode=
  webradio)"` — cheap, aids both manual debugging and Finding 5's harness
  fix (belt-and-suspenders alongside the `get playerMode` probe). Developer
  to confirm at implementation.
- **OQ3 (measure, don't assume, the actual heap-fragmentation delta).**
  This design's Goal 2 claim ("no fragmentation on a WebRadio-mode boot,
  once both companion changes ship") should be DUT-verified with the same
  `get heap` / `lfbInt` methodology M-HEAP-FRAGMENTATION used, not merely
  asserted from source reading — confirms companion change 1 actually
  closes Finding 2's gap in practice (e.g., no other code path opens
  `client` before the first real Spotify use).
- **OQ4 (`checkAndRefreshAccessToken()` first-call cost is now user-visible
  latency).** Under companion change 1, the very first real Spotify API
  call after a toggle-to-Spotify now pays *two* sequential network round
  trips before data appears (refresh token POST, then the actual
  `getCurrentlyPlaying()` GET) rather than one (refresh already done at
  boot). Bounded and one-time per session (subsequent polls reuse the
  cached access token for its ~1 h TTL), and within `ADR-046`'s existing
  "connecting" amber tolerance (Finding 4) — but VE should confirm the
  measured latency doesn't materially change the amber-to-green window
  DUT testers are used to seeing.
- **OQ5 (is there a second eager-`client`-touching call site anywhere
  else in `setup()`?).** This investigation traced the one call
  (`spotifyRefreshToken()`) confirmed to open TLS on the shared `client`
  before `spotifyTask::begin()`. Developer should grep for any other
  `client.connect`/`client->connect` call reachable from `setup()` before
  implementing, to make sure companion change 1 is closing the *only* such
  gap, not one of several.

## Exit criteria

- **DUT, ≥5 cold boots with `playerMode` persisted `WebRadio`:** no
  `[spotify.poll]` log line appears at any point before an explicit
  toggle-to-Spotify; `get playerMode` / `get appId` confirm the device is
  actually on the WebRadio app the whole time.
- **DUT, ≥3 cold boots, OQ3's measurement:** `lfbInt`/`get heap` sampled
  well into a WebRadio-mode session (past where the eager refresh used to
  fire) shows no permanent split comparable to M-HEAP-FRAGMENTATION's
  measured ~43 KB ceiling — confirms companion change 1 actually closes
  Finding 2's gap, not just in theory.
- **DUT, ≥5 toggle-to-Spotify actions (fresh WebRadio-mode boot, first
  toggle of the session):** Spotify connects and shows currently-playing
  within a bounded, recorded latency; taskbar shows amber "connecting" per
  `ADR-046` during that window, not a false green or a hang.
- **DUT, ≥3 repeated WebRadio↔Spotify toggle cycles within one boot:**
  confirms Finding 4's "no compounding latency" claim holds under this
  design (task never torn down, only the idle flag flips).
- **DUT, no-WiFi-at-boot-then-later-reconnect scenario** (the edge case
  Option B's §2 explicitly designs around): confirms `currentAppId ==
  Spotify` (visible) still connects normally once WiFi comes up, i.e. the
  `wifiConnected` term in the seed condition actually prevents the stranding
  bug described in §Design space Option B point 1.
- **VE harness regression:** `run_serialdbg_tests.py` connects promptly
  (no ~120 s hang) against a DUT left in `playerMode == WebRadio` from a
  prior session — proves companion change 2 actually closes Finding 5's
  gap on the harness side, not just in the design doc.
- Full serialdbg suite green on `cyd2usb_winamp`; `./run/check` 5-gate
  green.

## Registers

**New cross-feature edge: X038** — `player-state-001` × `poll-001`,
`interaction_type: dependency`, `risk: medium` (boot-order + task-lifecycle
coupling: `poll-001`'s `spotifyTask::begin()` now reads `player-state-001`'s
persisted `g_settings.playerMode` — via the `wifiConnected`-qualified
`bootIntoWebRadio` condition, not the raw field, per Design space Option B
point 1 — to decide whether to seed the task idle at creation time, and
`main.cpp:2363`'s eager token-refresh call reads the same condition to
decide whether to skip its network leg). Both `player-state-001` and
`poll-001` already exist in `feature_inventory.yaml` (`:1348`, `:58`) — no
new feature id needed, this design modifies existing behavior of both
rather than introducing a new capability. Developer to add the X038 row to
`cross_feature_matrix.yaml` at implementation (test_coverage from VE's
Exit-criteria suite above), per the reservation made here.

No other registry entries warranted — this design touches no new UI
surface, no new persisted field, and no new app.
