# Design — M-BOOT-UI: paint Winamp chrome first, surface boot progress via the title marquee

> Owner: Architect
> Status: draft
> Date: 2026-07-19
> Feeds: ADR-055 (proposed)
> Tracked-as: — (PM to file; suggest TASK-364+)
> Registers: boot-ui-001, X039–X041 (`cross_feature_matrix.yaml`) — see §Registers

## Context / pain points

A timestamped fresh-boot capture this session found the boot sequence paints
the one thing that costs nothing (the flash-resident Winamp skin chrome)
*last*, after everything slow and failure-prone (WiFi, NTP):

- `t=0.78s`: `[boot]` banner.
- `t=0.8–1.2s`: `spotifyDisplay->displaySetup(&spotify)` (`main.cpp:2134`) —
  `tft.init(); tft.setRotation(1); tft.fillScreen(TFT_BLACK);`
  (`Spotify-Diy-Thing/SpotifyDiyThing/cheapYellowLCD.h:69-87`) plus
  `WinampDisplay::displaySetup()`'s override (byte-swap flag only,
  `app/src/winamp/winampDisplay.h:49-55`). **Screen goes solid black here and
  stays black** — no skin chrome yet.
- `t=1.2–1.3s`: SPIFFS mount, `SettingsStorage::load()`,
  `TouchCalStorage::load()`, config file load (`main.cpp:2147-2179`) — fast,
  all local, no network.
- `t=1.3–2.1s` (this capture): WiFi connect. But the code has a **cascading
  fallback with no shared deadline**: hardcoded-SSID attempt (30 s,
  `main.cpp:2199-2208`, compiled in only under `wifi_creds.h`) → NVS-stored
  attempt (10 s, `:2219-2223`) → SPIFFS-file-creds attempt (30 s, `:2237-2241`,
  plus a 15 s re-association settle wait, `:2251-2253`). **Worst case ≈ 85 s**
  of solid black before boot even reaches NTP.
- `t=2.1–4.1s`: NTP sync (bounded 5 s, HTTPS-Date fallback on timeout,
  `main.cpp:2308-2332`).
- `t≈4.1–4.3s`: **only now** does the first real chrome paint happen —
  `main.cpp:2415-2422`'s `g_apps[(int)AppId::Spotify]->init()` (→
  `SpotifyApp::init()` → `winampDisplay.showDefaultScreen()`,
  `main.cpp:208-210`) then `renderTaskbar(...)`. `showDefaultScreen()`
  (`winampDisplay.h:108-117`) calls `repaintChrome()`
  (`winampDisplay.h:122-168`), which is a straight `tft.pushImage()` composite
  from flash-resident arrays (`SKIN_MAIN_BG` etc.) — **this paint itself costs
  no heap and negligible time** (see §1 below for the full cost trace).

The human's ask, verbatim: *"I think I rather want the winamp UI loaded, with
the boot message in the title screen. [...] could we get the winamp UI loaded
as quick as possible. (embedded devices should have instant boot experience,
this is not windows...)"*

The fix direction is obvious in shape — move the free paint earlier, surface
progress through the marquee already used for Spotify track titles,
WebRadio station/ICY titles, and TASK-362's empty-station-list reason string
(`setTitle()`, `winampDisplay.h:189-196`) — this design works out exactly
*how far* earlier it's safe to move, *what* the marquee says at each phase,
and *how much* liveness during the still-blocking waits is worth building now.

### Related work checked for interaction

- **`M-WEBRADIO-WINAMP-UI.md`** (scheduled, TASK-348/349/350/352): repurposes
  the PLEDIT bottom bar (country code), main-window time digits (stream play
  time), the vis area, and the volume slider for WebRadio mode. **No overlap**
  with the title marquee itself — none of its five items touch `setTitle()`.
  The only real question was whether it assumes anything about *when* first
  paint happens or what the title looks like pre-playback. It doesn't: entry
  into WebRadio mode always goes through `switchApp(AppId::WebRadio)`
  (`main.cpp:1952-1985`), which unconditionally wipes the app area
  (`tft.fillRect(0,0,TASKBAR_X,240,TFT_BLACK)`, `:1966`) and calls
  `WebRadioApp::init()`/`resume()` before anything else runs — so whatever
  boot-status text this design leaves in the marquee is torn down and
  repainted by WebRadio's own first real `setTitle()` call the same way it
  already is today when Spotify's first poll lands. No conflict, no shared
  state, no ordering dependency between the two designs.
- **`M-SPOTIFY-BOOT-GATE.md` / `ADR-054`** (TASK-363, just implemented):
  changed *whether* `spotifyTask` connects TLS on a `WebRadio`-mode boot, not
  display timing. Confirmed its two boot-time reads
  (`spotifyTask::authError()`, `spotifyTask::connecting()`, both called from
  `SpotifyApp::hasError()`/`isConnecting()`) are plain statics that default
  safely with no pointer deref (`spotifyTaskStorage.cpp:578-580`,
  `:596-599` — same "reads a plain static" class ADR-054's own Finding 2/V0
  precedent already established) — directly relevant here because this
  design's early chrome paint calls exactly these two accessors (via
  `repaintChrome()`'s `spotifyTask::isHealthy()` check and
  `renderTaskbar()`'s `shell::activeError()`/`activeConnecting()`) **before**
  `spotifyTask::begin()` has ever run. Confirmed safe by the same reasoning
  ADR-054 already validated, not a new audit.

## Goals

1. Replace the black-screen-until-everything-connects boot experience with
   the Winamp chrome painted essentially immediately, independent of WiFi/NTP
   outcome.
2. Surface WiFi-connect and NTP-sync progress through the existing title
   marquee (`setTitle()`), reusing its redraw-on-change behavior — no new
   display mechanism.
3. On a slow/dodgy network, the wait no longer reads as "frozen": distinct
   text per fallback stage, plus marquee-scroll liveness for any text that
   doesn't fit `TITLE_W`.
4. Zero regression to the app-lifecycle bookkeeping downstream (`g_appLaunched`,
   `switchApp()`'s init-vs-resume branching, the boot-time `AppId::WebRadio`/
   `AppId::Settings` switches) — the early paint is additive, not a
   reordering of existing calls.
5. Small, auditable diff, scoped to the `WINAMP_DISPLAY` build family (the
   production `cyd2usb_winamp` env and everything that `extends` it) —
   matching the existing `#ifdef WINAMP_DISPLAY` boundary around
   `SpotifyApp`/`g_apps[]` (`main.cpp:205-269`, `:1820-1828`). The non-Winamp
   `cyd` and `trinity` envs are untouched.

## §1 — What does painting the chrome that early actually need?

Traced every function the early paint would call, to find the true earliest
safe point (not the first plausible-looking one):

- **`winampDisplay.showDefaultScreen()`** (`winampDisplay.h:108-117`) resets
  five plain member fields (`lastThumbPx`, `lastTitle`, `titleScrollOffset`,
  `titleScrollDeadline`, `lastSeconds`, `currentStatusUv`) then calls
  `repaintChrome()`. **No `g_settings` read, no SPIFFS read, no network.**
- **`repaintChrome()`** (`:122-168`): `tft.startWrite()`/`pushImage()` calls
  from flash arrays (`SKIN_MAIN_BG`, `SKIN_TITLEBAR_INACTIVE`, `kDriftPip`),
  `drawTransportButtons()`/`drawEjectButton()`/`drawStatusIndicator()`
  (flash sprites + cached statics), `drawTimeDigits(lastSeconds, force=true)`
  (flash `SKIN_NUMBERS`), `drawVolume()`/`drawShuffle()`/`drawRepeat()` (flash
  atlases keyed off cached statics that `showDefaultScreen()` just reset to
  known sentinels), `vu::invalidate()` (in-memory flag). The only two
  **non-`tft`, non-static** reads: `spotifyTask::isHealthy()`
  (`s_consecutiveFailures < 2`, a plain `int` defaulting to `0`) and
  `spotifyTask::lastSuccessfulPollAgeMs()` (`s_lastSuccessfulPollMs`, a plain
  `uint32_t` defaulting to `0`) — both confirmed safe pre-`spotifyTask::begin()`
  by the same reasoning `ADR-054` already validated for the identical
  accessor family. **No dependency on `SettingsStorage::load()`,
  `spotifyTask::begin()`, WiFi, or NTP.**
- **`renderTaskbar(tft, currentAppId, ...)`** (`taskbar.h:191+`) reads
  `gen/shell_layout.h` and `gen/taskbar_icons.h` — both compile-time-generated,
  flash-resident headers (baked by `run/bake-skin`/icon tooling, not a
  runtime step) — plus `shell::activeError()`/`activeConnecting()`
  (`main.cpp:1843-1850`), which read `g_apps[(int)currentAppId]->hasError()`/
  `isConnecting()`. `g_apps[]` (`main.cpp:1821-1825`) is populated from
  `static SpotifyApp g_SpotifyApp;`-style globals at **static-init time**,
  before `setup()` ever runs — always non-null, always safe to index.
  `currentAppId` (`main.cpp:128`) is `AppId::Spotify` by static initializer.
  `SpotifyApp::hasError()`/`isConnecting()` (`main.cpp:228-235`) call the same
  two `spotifyTask::` statics already covered above. **No dependency beyond
  what `repaintChrome()` already needs.**
- **`winampDisplay.setTitle(text)`** (`:189-196`) — pure string-compare +
  `drawTitleText()` (flash `SKIN_GLYPH` blits). No dependency.

**Conclusion: the true earliest safe point is immediately after
`displaySetup()`** (`main.cpp:2134`) — before SPIFFS mount, before
`SettingsStorage::load()`, before WiFi. Nothing the paint touches needs any
of that. Two real-world considerations argue for placing it slightly later,
right after `TouchCalStorage::load()` + the backlight-PWM handoff
(`main.cpp:2159-2176`, i.e. before `fetchConfigFile()`/`wifiDiag::begin()`),
instead of at the theoretical earliest point:

1. **Backlight sequencing.** `tft.init()` (inside `displaySetup()`) does a
   bare `digitalWrite(TFT_BL, HIGH)` — full brightness, no LEDC channel
   configured yet (`main.cpp:2156-2158`'s own comment). `g_backlight.applyMode()`
   (`:2169`) then applies the user's saved brightness (`dispAuto`/`dispLevel`).
   Painting at the theoretical-earliest point would flash the chrome at full
   brightness for the ~20-100 ms until `applyMode()` runs, then dim —
   cosmetic, not a correctness issue, but avoidable for free by painting
   ~20 lines later.
2. **The SPIFFS-mount-failure path stays exactly as it is today.**
   `SPIFFS.begin()` failing (`main.cpp:2147-2153`) drops into
   `while(1) yield();` — a permanent hang, no screen feedback, existing
   behavior. Painting chrome *before* this check would leave a "working-looking"
   but frozen skin on that hang instead of black — arguably a wash (a
   different kind of misleading), and touching that path is unrelated scope
   (a SPIFFS mount failure is a hardware/corruption fault, not the "dodgy
   WiFi" case this design targets). Painting *after* the SPIFFS gate (as
   recommended) leaves that edge case completely untouched — not a
   regression, not a fix, out of scope by construction.

Net: **~100-400 ms** later than the theoretical floor (SPIFFS mount + two
tiny `load()` calls, both local/fast per the capture), in exchange for
correct backlight sequencing and zero interaction with the SPIFFS-failure
path. Given the actual prize is collapsing an 80+ s worst-case WiFi wait,
not the sub-second SPIFFS/settings phase, this tradeoff is not close.

**The early paint must be an *additional* direct call to
`winampDisplay.showDefaultScreen()` + `renderTaskbar(...)`, not a reordering
of the existing `main.cpp:2415-2422` block.** That block still runs, unchanged,
later: `g_appLaunched[(int)AppId::Spotify] = true; g_apps[(int)AppId::Spotify]->init();`
then `renderTaskbar(...)` again. The second pass is a harmless, cheap,
idempotent repaint (`repaintChrome()`'s own doc comment: "Idempotent given
the cached state") — but critically, **`g_appLaunched` bookkeeping and
`switchApp()`'s init-vs-resume branching are completely untouched**, because
the early paint calls the renderer directly, not through the `App` vtable.
This is Goal 4, made concrete.

## §2 — Boot-status protocol via the title marquee

Reuse `setTitle()`'s existing redraw-on-change + scroll-on-overflow behavior
verbatim — no new mechanism. `TITLE_W = 154px`, `GLYPH_W = 5px` (+1px spacing)
→ **25 chars fit without scrolling** (`app/gen/skin_layout.h:75,78`); text
budget below is chosen to fit that, so the *cheap* option (§3) never needs
scroll to be legible.

Proposed phase strings, each tied to an **existing** call site (adds one
`setTitle()` call per site, no new branching):

| Phase | Call site (`main.cpp`) | Text |
|---|---|---|
| Early paint | new, ~`:2176` | `"STARTING UP..."` |
| WiFi: connecting (any fallback stage — hardcoded-SSID `:2193`, NVS `:2210`, SPIFFS-creds `:2224`, re-assoc settle `:2244-2253`) | all four sites above | `"WI-FI: CONNECTING..."` (single generic string — human decision, OQ1 below: not worth keeping the per-stage granularity in sync) |
| WiFi: connected | `:2264` branch | `"WI-FI: CONNECTED"` (brief — next phase supersedes it almost immediately) |
| WiFi: failed, retrying in background | `:2274` branch (`wifiCredsKnown`) | `"WI-FI: RETRY IN BG"` |
| WiFi: no credentials | `:2286` branch | `"WI-FI SETUP NEEDED"` (very brief — `switchApp(Settings)` at `:2427` supersedes within the same boot, Settings owns the screen from then on) |
| NTP sync | `:2308` | `"TIME: SYNCING..."` |
| NTP: HTTPS-Date fallback | `:2319` branch | `"TIME: HTTPS FALLBACK..."` |

**Deliberately not adding** a `"SPOTIFY: CONNECTING..."` phase after
`spotifyTask::begin()` (`:2400`): `repaintChrome()` already paints the
`SKIN_TITLEBAR_INACTIVE` overlay whenever `!spotifyTask::isHealthy()`
(`:130-134`), and `renderTaskbar()`'s amber "connecting" indicator
(`ADR-046`) already covers this exact window. Adding a redundant text phase
for a state two other UI elements already signal is scope creep for no
incremental clarity — the marquee's real job is filling the **dead air**
before any of the app-level indicators exist, not duplicating them once they
do.

**Transition to real content requires no new code.** `setTitle()`'s own
dedup (`if (strcmp(lastTitle, text) == 0) return;`) means the moment
`printCurrentlyPlayingToScreen()` (Spotify, `:281-296`) or WebRadio's
station-title code calls `setTitle()` with real content, it simply overwrites
whatever boot-status string was last shown — exactly the mechanism TASK-362
already relies on for its "no stations, here's why" case. No explicit
"clear boot status" step to design or implement.

## §3 — Liveness during the still-blocking waits (the real tradeoff)

Today's WiFi/NTP wait loops are tight synchronous loops — nothing else runs.
Two options, evaluated honestly rather than defaulting to the fancier one:

### Option A (cheap): static per-phase text only

Insert the `setTitle()` calls from §2's table at existing phase-transition
points. No change to the loops themselves. **Diff size: ~10 one-line
insertions**, all at call sites the code already visits. **Risk: near zero**
— every call is `winampDisplay.setTitle(const char*)`, a pure display call
with no side effect on WiFi/NTP/task state.

**Value delivered:** replaces black-with-nothing with skin-plus-static-text
for the entire wait duration — the primary ask, done. On a *quick* boot (this
session's capture: WiFi 0.9 s, NTP 2 s) the difference is barely visible
because it barely mattered. On the human's actual complaint case — a *slow*
boot — the user now sees the chrome and a taskbar instead of 80 s of black.

**Consequence of the OQ1 decision below (single generic `"WI-FI: CONNECTING..."`,
not per-stage text):** the stage-progression argument this paragraph
originally made — the string itself changing shape as a weak liveness
signal — no longer applies to the WiFi phase. With one generic string, a
worst-case ~85 s WiFi wait now shows **one unchanging line of text**, not a
progression. That's still a strict improvement over solid black (real skin,
real taskbar, a legible reason why nothing's happening yet), but it raises
the stakes on Option B below: without *some* liveness mechanism, that one
line risks reading as "frozen" in exactly the way the human's complaint was
about, just with nicer wallpaper. Recorded here rather than silently
smoothed over.

### Option B (fuller): also drive marquee scroll during the waits

Every wait loop already calls `esp_task_wdt_reset()` every iteration
(`main.cpp:2205,2221,2239,2252` — added by TASK-288 specifically so
cumulative un-fed time across the whole cascade doesn't trip the watchdog).
That is a **ready-made, already-present, per-iteration hook** — adding
`winampDisplay.tickMarquee()` (`:200`, thin wrapper over the already-`millis()`-
gated `_tickMarquee()`, `:713-725`) immediately alongside each
`esp_task_wdt_reset()` call costs one function call per loop iteration, is
self-throttled internally (only repaints when `titleScrollDeadline` has
elapsed — a no-op the other ~29/30 iterations), and requires **zero
restructuring** of the loops (they stay synchronous, no async/cooperative
rewrite). The NTP loop (`:2311-2314`) doesn't currently call
`esp_task_wdt_reset()` — it calls `yield()` — so its `tickMarquee()` call
rides along the existing `yield()` line instead; no WDT-feeding behavior is
touched by this design either way.

This delivers genuine scroll-liveness for any status text that would
otherwise sit static and *look* frozen — but per §2's budget, **every
proposed phase string fits in `TITLE_W` without scrolling** (longest is now
`"TIME: HTTPS FALLBACK..."` at 23 chars, since OQ1 collapsed the WiFi-phase
strings to the short generic `"WI-FI: CONNECTING..."`), so under the
*current* text list, Option B's scroll never actually engages for **any**
phase string, WiFi included — it only becomes visible if a future phase
string exceeds 25 chars (e.g. embedding an actual SSID name into the WiFi
string). **Concretely, for the ~85 s worst-case WiFi wait specifically**:
Option B is wired up and costs nothing, but delivers nothing either, given
OQ1's generic string is short enough to never scroll — the WiFi phase's
liveness (or lack of it) rides entirely on Option A's static text for now.
If that turns out to read as frozen in practice, the next lever isn't
Option B (already shipped, already inert here) — it's the dot-cycle
animation explicitly scoped out below, or revisiting OQ1's string choice.

**What Option B does *not* do, and was explicitly scoped out per the task
brief:** touch handling during the waits (letting the user abort to WiFi
Settings mid-wait), a live "..." dot-cycle animation (would need the phase
strings to rotate through 2-3 variants on a timer, which *would* trigger
real repaints even without overflow-scroll, but is a distinct small feature
from marquee-scroll reuse), or any restructuring of the loops into
cooperative/async shape. Full input responsiveness during a blocking wait is
a materially bigger change (reading touch state + running a mini gesture
path inside what's currently a pure `delay()`/`esp_task_wdt_reset()` loop) —
real value (a stuck-on-bad-WiFi device becomes navigable without a power
cycle), but a different, larger design, not justified by "don't show a
frozen string" alone.

### Lean: ship both A and B together

They are not actually alternatives in cost — B is a ~4-line addition
(one `tickMarquee()` call inserted at each of the four loop bodies that
already got touched for A's `setTitle()` calls) riding on a hook
(`esp_task_wdt_reset()`/`yield()` per iteration) that already exists for an
unrelated reason. There is no scenario where A ships and B doesn't save
meaningfully more diff or risk — B is priced at effectively zero marginal
cost once A's call sites are already being edited. Ship A's static text +
B's scroll-tick together as one change; do **not** build dot-cycle animation
or touch-responsiveness now (real, larger, separately-scoped work — see §4
below for the same reasoning applied to the fallback cascade itself).

## §4 — The WiFi fallback cascade (flagged, not solved here)

The three-stage fallback (30 s hardcoded → 10 s NVS → 30 s SPIFFS + 15 s
settle = **85 s worst case**, `main.cpp:2199-2253`) is a separate, real
opportunity: painting chrome early and showing status text makes the wait
*look* dramatically better (§3), but does not make it *shorter*.
Shortening or parallelizing that cascade (e.g. racing NVS and SPIFFS creds
concurrently, or capping cumulative wait time across all three stages rather
than letting each budget its own window independently) is genuinely a
different design — it touches WiFi retry/timeout policy, not display
timing, and the two are not entangled: this design's chrome-first change
works identically regardless of whether the cascade is later shortened.
Noting it here per the task brief; not pulling it into this design's scope.
Worth a follow-up design doc if the human wants it addressed (PM to
schedule).

## §5 — Other constraints checked

- **`tft`/SPI availability at the proposed call site:** safe.
  `displaySetup()` (`main.cpp:2134`) runs `tft.init()` unconditionally before
  any of the other setup() work; the proposed call site (~`:2176`) is after
  it. No concurrent SPI user exists at this point in `setup()` —
  `spotifyTask::begin()` and `dataTask::begin()` (the two FreeRTOS tasks that
  could contend for the bus later) haven't been spawned yet.
- **`gen/` codegen freshness:** `gen/shell_layout.h`/`gen/taskbar_icons.h`
  (taskbar) and `gen/skin_assets.c`/`gen/skin_layout.h`
  (chrome/title glyphs) are host-baked artifacts checked into the repo
  (`run/bake-skin`), not generated at runtime — no ordering dependency on
  anything in `setup()`, confirmed by inspection (they're `#include`d at
  file scope, same as every other build).
- **`#ifdef WINAMP_DISPLAY` scoping:** confirmed via `app/platformio.ini` —
  `cyd2usb_winamp` (`:72-76`, sets `-DWINAMP_DISPLAY`) and every env that
  `extends` it (`_debug`, `_screenlog`, `_webradio`, `_webradio_16k`,
  `_debug_noSpotify`) inherit the flag; `cyd`/`cyd2usb` (plain, non-Winamp)
  and `trinity` (HUB75 matrix, `-DMATRIX_DISPLAY`) do not. This design's new
  code must live inside the same `#ifdef WINAMP_DISPLAY` guard the existing
  `SpotifyApp`/`g_apps[]`/taskbar code already uses (`main.cpp:205-269`,
  `:1820-1828`) — on non-Winamp builds, fall back to the existing
  `spotifyDisplay->showDefaultScreen()` call with no marquee/taskbar (those
  backends have no such concepts; out of scope, matches current behavior).

## Open questions

- **OQ1 — RESOLVED (human decision):** generic `"WI-FI: CONNECTING..."` for
  the whole cascade, not per-fallback-stage text. Overrides this doc's
  original lean (which favored per-stage granularity for the stage-progression
  signal it gave "for free") — simpler, nothing to keep in sync if the
  fallback cascade is ever reordered/renamed. §2's table and §3's Option A/B
  discussion have been updated to match; see §3's added notes on the
  consequence (the WiFi phase now has no stage-progression liveness signal,
  and Option B's scroll-tick has nothing to scroll for this specific string —
  recorded there, not re-litigated here).
- **OQ2 (background-reconnect status during `loop()`, not just `setup()`).**
  The `wifiCredsKnown`-but-failed path (`:2274-2285`) arms
  `wifiDiag::superviseArm()` for a background reconnect that continues into
  normal operation (`loop()`), outside this design's `setup()`-only scope.
  The marquee would sit at `"WI-FI: RETRY IN BG"` until either the
  background reconnect succeeds and a real title arrives, or the user
  navigates away — no live update of *that* ongoing retry inside `loop()`.
  Real, but a `loop()`-side feature (wiring `wifiDiag`'s supervisor state
  back into the marquee continuously), not a `setup()`-boot-sequence one —
  flagged as a natural follow-up, not pulled into this design.
- **OQ3 (measure actual wall-clock delta on DUT, not just reason about it).**
  This design's central empirical claim — "chrome visible within ~1.3 s
  instead of ~4.1 s (or 85+ s worst case)" — should be confirmed with a
  timestamped DUT capture identical in method to the one that motivated this
  design, both on a healthy AP and (if reproducible) a deliberately
  unreachable one, before closing the exit criteria.

## Exit criteria

- **DUT, ≥5 cold boots, healthy AP:** timestamped capture (same method as
  the motivating capture) shows Winamp chrome + taskbar visible by
  ~`t=1.3-1.5s` (vs. today's ~4.1 s), with `"STARTING UP..."` → WiFi phase
  text → `"TIME: SYNCING..."` visible in sequence on the title marquee.
- **DUT, ≥1 deliberately-unreachable-AP boot (or the fastest safe proxy —
  e.g. a wrong password forcing the full cascade):** chrome + taskbar remain
  visible throughout; marquee shows `"WI-FI: CONNECTING..."` per OQ1's
  resolved decision (static for the whole ~85 s worst case — no per-stage
  progression); no black screen at any point after `displaySetup()` returns.
- **DUT, WebRadio-mode boot (`playerMode == WebRadio`, WiFi up):** confirms
  §Related-work's claim — the early-paint boot-status text is cleanly
  superseded by `switchApp(AppId::WebRadio)`'s teardown+repaint at the end
  of `setup()`, no visual glitch/flash/stale-text artifact.
- **DUT, no-WiFi-credentials boot:** confirms `"WI-FI SETUP NEEDED"` briefly
  shows, then `switchApp(AppId::Settings)` takes over cleanly (existing
  behavior, unaffected).
- **Eyeball (BP-048):** one screendump pass across the phase-text table —
  every string renders correctly inside `TITLE_W`, no clipping, no leftover
  pixels from a previous phase's longer string.
- Full serialdbg suite green on `cyd2usb_winamp`; `./run/check` 5-gate green
  (golden-hash gate matters here: this design touches no generated asset,
  so `golden.sha256` should be unaffected — confirm at implementation).

## Registers

**New feature: `boot-ui-001`** — "Chrome-first boot + title-marquee boot
progress." Composes existing capabilities (does not duplicate them): reuses
`chrome-001`'s render primitives from an earlier `setup()` call site, and
surfaces `wifi-001`/`time-001`'s phase transitions as marquee text via the
existing `setTitle()`/`tickMarquee()` mechanism (no new rendering code, no
new persisted state, no new settings field).

- **X039** — `boot-ui-001` × `chrome-001`, `interaction_type: dependency`,
  `risk: low`. `boot-ui-001` calls `chrome-001`'s existing
  `showDefaultScreen()`/`repaintChrome()`/`renderTaskbar()` from a new,
  earlier call site in `setup()`; the later, existing call site
  (`main.cpp:2415-2422`) is unchanged and becomes a harmless idempotent
  repaint. No new rendering logic — a call-site relocation plus reuse.
- **X040** — `boot-ui-001` × `wifi-001`, `interaction_type: dependency`,
  `risk: low`. Marquee text is keyed to WiFi connect-loop phase transitions
  (`main.cpp`'s hardcoded-SSID/NVS/SPIFFS-creds cascade); `tickMarquee()` is
  invoked from the existing per-iteration `esp_task_wdt_reset()` hook inside
  those loops. Read-only with respect to `wifi-001` — this design does not
  change WiFi connect/retry behavior, only observes its phase transitions.
- **X041** — `boot-ui-001` × `time-001`, `interaction_type: dependency`,
  `risk: low`. Same shape as X040, keyed to the NTP sync wait
  (`main.cpp:2308-2332`) and its HTTPS-Date fallback branch.

Developer to add `boot-ui-001` to `feature_inventory.yaml` and the X039-X041
rows to `cross_feature_matrix.yaml` at implementation (`test_coverage` from
VE's Exit-criteria suite above), per the reservation made here.
