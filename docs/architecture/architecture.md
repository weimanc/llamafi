# System Architecture

> Owner: Architect
> Living system specification. Reflects accepted ADRs and validated implementation only.
> Full sync 2026-07-16 — the previous baseline-vs-target framing (ADR-001..006 era) is
> retired: the Winamp target shipped (M2–M7, 2026-05) and the system has since grown into
> a multi-app firmware. History lives in `roadmap.md` (completed milestones) and git; this
> doc describes what runs today.

## System Overview

ESP32 firmware for the ESP32-2432S028R "Cheap Yellow Display" (two-USB CYD, 320×240
ILI9341, XPT2046 touch, no PSRAM): a **multi-app appliance** behind a Winamp-2-skinned
face. Twelve registered apps (`appRegistry.h`, single-source codegen): the Winamp player
slot (Spotify controller ⇄ WebRadio, mode-switched by eject — M-PLAYER-STATE), Clock (4
styles), Weather, Crypto, Matrix, Life, Stock (list/chart/heatmap), Aquarium, Teletext
(NOS), PlaneRadar (live ADS-B), Settings, and WebRadio.

Screen splits 275×240 app canvas + 45 px right-hand icon taskbar. Eleven apps have
taskbar slots (scrolling taskbar); **WebRadio is eject-only** — entered via the Winamp
eject toggle, deliberately excluded from the taskbar (`TASKBAR_APP_COUNT`, LL-085).

Two personalities of the player slot:

- **Spotify (controller)** — polls the Web API for playback state, renders the skinned
  UI, sends control intents back. No audio on device for this mode.
- **WebRadio (player)** — the one on-device audio path: MP3 internet radio via
  radio-browser station lists, Helix decode in a 24 K free-list arena (no PSRAM —
  ADR-047 A-lite), mono internal DAC on GPIO26.

**Scope boundary:** only `Spotify-Diy-Thing/` + `app/` are in scope. The sibling
`cspot/` directory is an unrelated vendored project; never built or referenced.

## Component Architecture

```
                    Spotify Web API        open-meteo / coingecko / yahoo /
                          |                NOS teletekst / adsb.fi / radio-browser /
                    HTTPS |                Nominatim          |  HTTPS
                          |                                   |
                 +--------v--------+              +-----------v-----------+
                 |  spotifyTask    |              |  dataTask             |
                 |  (pinned task)  |              |  (pinned task; serial |
                 |  poll + actions |              |   fetch queue, per-   |
                 +--------+--------+              |   host CA registry)   |
                          |  results/queue        +-----------+-----------+
                          |                       enqueue/poll | (seq/epoch identity)
+-------------------------v-----------------------------------v----------------------+
|  loop() — app shell (appShell.h)                                                   |
|  switchApp() lifecycle: init/resume/suspend/tick/handleInput (TouchPhase)          |
|  + taskbar (45px, scrolling)  + screenLog overlay  + LedFlow  + serial debug       |
+---+----------+---------+--------+--------+--------+--------+--------+---------+----+
    |          |         |        |        |        |        |        |         |
 Winamp      Clock    Weather  Crypto/  Aquarium Teletext  Plane   Settings  WebRadio
 (Spotify    (4       (tiles)  Stock/   (canvas) (25x40    Radar   (6 sect., (PLEDIT
  skin, VU,   styles)          Matrix/           cells)    (disc+  /settings  list +
  PLEDIT)                      Life                        strip)  .json)     wrpump
    |                                                                          task)
    +-- eject toggles playerMode (persisted) --------------------------------->|
                                                                               v
                                                                    audioI2S (Helix MP3,
                                                                    24K arena) -> I2S
                                                                    internal DAC GPIO26
Storage: NVS (wifi creds) · SPIFFS (/spotify_diy_config.json, /settings.json,
/cal.json, /wifi_creds.json) · flash .rodata (baked skin atlas, teletext font,
airport DB — gen/ + golden.sha256 determinism gates)
```

Three FreeRTOS tasks beside the Arduino `loop()`: `spotifyTask` (async Spotify HTTP —
poll + control actions, exponential backoff), `dataTask` (all non-Spotify HTTPS, serial
queue), `wrpump` (WebRadio audio pump; created per-play, torn down on suspend). Cross-task
result identity uses seq/epoch echoes (X026/X027); Spotify-vs-other TLS heap coexistence
uses the ref-counted `tlsYield()`/`tlsResume()` protocol (BP-031 lineage).

## Software Stack

| Layer            | Choice                                                                |
|------------------|-----------------------------------------------------------------------|
| Toolchain        | PlatformIO (`~/.platformio/penv/bin/pio`), env `cyd2usb_winamp` (+`_debug`) |
| Platform         | `espressif32 @ 6.9.0` (Arduino-ESP32 2.0.17) — pinned; gnu++11 (no NSDMI aggregate brace-init, LL-112) |
| Framework        | Arduino super-loop + 3 pinned FreeRTOS tasks                          |
| Spotify client   | `witnessmenow/spotify-api-arduino` + LOCAL_PATCHES (getQueue, token helpers) |
| Radio audio      | ESP32-audioI2S v2.3.0 (pinned — TASK-257) + Helix MP3, A-lite arena (ADR-047) |
| JSON             | `bblanchon/ArduinoJson @ 6.x` (heap docs registered in `app/mem_manifest.yaml`) |
| Display          | `bodmer/TFT_eSPI @ 2.5.x`, full `User_Setup.h` in build_flags; `TFT_INVERSION_ON` (2-USB CYD) |
| Touch            | XPT2046 via `CYD28_TouchscreenR` (rotated coords), TouchPhase state machine |
| Provisioning     | on-device WiFi settings UI + SPIFFS creds + optional `wifi_creds.h` shim (WiFiManager retired from the boot path) |
| Album art / JPEG | **removed** (M-NOART) — `lib_ignore = JPEGDEC` in winamp env               |
| Host tooling     | Python venv (`~/proj/esp/venv`): bake tools, preview tools, serialdbg test harness, `run/` scripts |

## Component Interfaces

- **`App` ABC** (`appShell.h`) — the system's primary seam: `init/resume/suspend/tick/
  handleInput(TouchPhase,x,y)` + status hooks (`hasPendingAsync`, `isConnecting`,
  `hasError` — ADR-046 status bar) + `dbgGet/dbgSet` (M-SERIALDBG). Informal contract
  captured in `NEW-APP-CHECKLIST.md`; formalisation → IFC-002 (planned).
- **dataTask API** (`dataTask.h`) — enqueue/poll pairs per fetch type with snapshot-at-
  enqueue configs and seq/epoch result identity. Contract: **IFC-001**
  (`docs/architecture/interfaces/IFC-001.md`).
- **Settings storage** (`settingsStorage.h`) — `AppSettings` ↔ `/settings.json`;
  ownership rules per ADR-050.
- **`spotifyDisplay.h`** — legacy upstream seam; superseded by the app shell but kept
  for upstream compatibility (`winampDisplay.h` is the live renderer).
- **Serial debug** (`get`/`set`/`tap`/`drag`/`switchApp` JSON protocol) — the DUT test
  surface for the whole VE suite (M-SERIALDBG).

## Data Flows

1. **Boot.** SPIFFS mount → `SettingsStorage::load()` + touch-cal load → backlight from
   settings → WiFi (priority chain: `wifi_creds.h` → NVS → SPIFFS `/wifi_creds.json` →
   on-device WiFi settings UI) → TWDT-fed waits (TASK-288) → SNTP (5 s bounded; TZ from
   `posixTz` once M-SETTINGS-WIRE2 G1 lands) → Spotify token refresh → app shell starts
   in the persisted player mode.
2. **Spotify steady state.** `spotifyTask` polls `getCurrentlyPlaying` at 5 s base with
   backoff; UI interpolates position between polls (ADR-005); touch intents enqueue
   actions (ADR-012), optimistic UI flips immediately (ADR-004), speculative 750 ms poll
   after next/prev (ADR-020). Synthetic VU at 20 Hz (ADR-009e).
3. **dataTask fetches.** Apps enqueue; dataTask serialises, applies per-host root CA
   (`dataTaskCerts.h` — ADR-029/034/044 + amendments), parses into fixed result structs
   (manifest-registered heap docs), returns via spinlock-guarded slots; consumers poll
   with seq/epoch identity checks. PlaneRadar adds a parse-error-only single retry
   (TASK-313, Cloudflare edge truncation).
4. **WebRadio playback.** Station list via dataTask (country + bitrateMax filter) →
   `_play()` builds decoder arena + `wrpump` task → ICY title/PLEDIT scroll UI →
   auto-skip dead stations (ADR-045); fetch and playback are mutually exclusive
   (TASK-289); `tlsYield()` brackets every non-Spotify TLS handshake. Real per-block
   peak audio envelope drives `VIS_VU` (ADR-056, amends ADR-009 for this path only —
   Spotify's synthetic VU is unchanged): `wrpump`'s `audio_process_extern` hook writes
   `vu::lLevelRef()`/`rLevelRef()` directly, single-writer swap with the UI thread's
   synthetic path (X043).
5. **Touch.** Shell samples XPT2046, delivers TouchPhase to the active app; taskbar
   gestures switch apps (player slot resolves via persisted mode — X022); Settings
   sections + KeyboardWidget capture per X029 ordering.
6. **Logging/observability.** logSink ring + heartbeat JSON + logServer (LAN) +
   screenLog overlay; serial debug protocol drives the DUT test suites (`run/test*`).

## Cross-cutting concerns

- **Auth bootstrap.** Spotify redirect-URI policy (Apr 2025+): loopback-HTTP only —
  refresh token minted off-device (`get_refresh_token.py`), baked into SPIFFS. On-device
  `refreshToken.h` flow unreachable under current policy.
- **Persistence split.** NVS: wifi creds. SPIFFS: Spotify creds (`configFile.h`),
  app settings (`/settings.json`), touch cal (`/cal.json`, ring-buffer history),
  optional `/wifi_creds.json`. All survive firmware reflash; `run/flash-fs` wipes SPIFFS
  (use `run/spiffs push` instead — non-destructive).
- **Settings ownership (ADR-050, accepted 2026-07-16).** Every `AppSettings` field has a
  named runtime owner outside `app/src/settings/` (global flow / pull-on-resume /
  snapshot-at-enqueue). Sections render/edit/persist only; preview via owner
  `pause()`/`resume()`. No RAM-drift fields. Enforced: `check_settings_wiring.py`
  (run/check, warn-only initially) + T-SETW. Remediation of the five pre-ADR violations:
  M-SETTINGS-WIRE2; location unification: M-HOME-LOCATION.
- **Memory budget (M-MEMPLAN, ADR-047).** No PSRAM; ~290 K INTERNAL ceiling with 60 K
  TLS/system headroom. Heap buffers register in `app/mem_manifest.yaml` (planner-placed
  overlay or `placement: runtime` budget-only); WebRadio decode uses the 24 K A-lite
  arena; unregistered heap docs are an audit finding (LL-111).
- **TLS coexistence.** One Spotify TLS context + one dataTask/audio TLS at a time;
  ref-counted `tlsYield()`/`tlsResume()`; violations historically caused SSL -32512 /
  WDT crashes (TASK-285..299 lineage) — treat the protocol as load-bearing.
- **Codegen determinism.** All baked assets (`app/gen/`: skin atlas, registry, airport
  DB, mem layout) re-bake byte-identical (`golden.sha256`); `run/check` gates staleness.
- **DUT workflow.** All build/flash/monitor/test through `run/` scripts (port
  resolution, monitor lifecycle, trap-guarded test loops) — see
  `docs/process/project_run_scripts.md`.

## Open Questions

- **Settings wiring remediation** — M-SETTINGS-WIRE2 (accepted ADR-050 dependency) and
  M-HOME-LOCATION, M-WEBRADIO-SETTINGS drafts awaiting review/scheduling.
- **Spotify Premium lapse (TASK-243, external)** — live-playback-state paths untestable
  until the owner account is restored; UI/nav suites unaffected.
- **TASK-284 station-list mirror truncation** — intermittent upstream flakiness;
  best-effort mitigation shipped; watch, don't chase.
- **Position snap threshold** — 500 ms initial value stands; tune only if real jitter
  measurements demand it.
- **NFC** — probe gated by `NFC_ENABLED` in the .ino; non-fatal boot noise on unwired
  readers. Remove-vs-keep remains a product call (TASK-004).
- **Publish hygiene** — GitHub publish plan open item #9 (license scanner) +
  OSM/ODbL attribution (geocoding) tracked in `docs/process/github_publish_plan.md`.
