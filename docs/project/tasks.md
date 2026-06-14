# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> **PM sync 2026-06-14 (session 5)** — M-HOST-WINAMP deferred; TASK-201 targeted fix approved.
> Architect review: M-HOST-WINAMP is correct long-term but 6–7 dev-days before WebRadio preview is
> usable. Two concrete misses in preview_webradio.py: (1) PIL default font instead of Winamp LED
> bitmap font (TEXT.BMP glyphs); (2) synthetic grey rectangles instead of POSBAR/PLEDIT skin sprites.
> Coordinates are correct — originX=0, skin_layout.h constants are pixel-accurate. Root fix:
> add `--wsz` arg, import `build_glyph_table` from bake_skin.py, implement `_draw_led_text()` via
> TEXT.BMP glyph crop+paste, and restore POSBAR/PLEDIT chrome from actual skin BMP sprites.
> ~100-120 lines added to existing script; no WinampRenderer.py needed for this gate.
> M-HOST-WINAMP deferred to post-M-WEBRADIO-ship as a long-term preview framework.
> TASK-203–206 deferred. TASK-201 reopened as in-progress.
>
> **PM sync 2026-06-14 (session 4)** — M-WEBRADIO preview blocked; pivot to host Winamp renderer.
> TASK-199 done (flash gate clear). TASK-200 done (API + ICY probes). TASK-202 done (country list, 65 entries, 0 gaps).
> TASK-201 (preview_webradio.py) produced a naive PIL overlay — rejected. Root cause: no Python port of
> WinampDisplay.h exists. Preview tools cannot composite correctly without the actual sprite blitting logic.
> New milestone M-HOST-WINAMP opened. TASK-203 (sprite/font inventory), TASK-204 (WinampRenderer.py),
> TASK-205 (Spotify host preview sign-off), TASK-206 (WebRadio preview v2 on WinampRenderer) filed.
> TASK-201 downgraded to blocked — reopens after TASK-205 sign-off.
>
> **PM sync 2026-06-14 (session 3)** — M-WEBRADIO scheduled (shift-left phase).
> Design draft complete (M-WEBRADIO.md). R&D done (EXP-005 + EXP-006). Open items 4+6 resolved by design.
> Shift-left pre-implementation plan captured in M-WEBRADIO.md. TASK-199–202 opened.
> TASK-199 (flash budget gate) is the sole P1 blocker — must pass before firmware work.
> TASK-200–202 unblock in parallel once TASK-199 clears.
>
> **PM sync 2026-06-14 (session 2)** — M-CLOCK-STYLES + M-PREVIEW-FRAMEWORK close-out.
> TASK-192 (preview_common.py + 6-tool migration) done. TASK-193 (ClockStyle enum, Flip/Nixie/VFD
> renderers, Settings wiring) done. TASK-194 (T_CLK_01–14 VE suite) done, 14/14 PASS.
> M-CLOCK-STYLES milestone complete. Visual criteria C1/C4/C5/C6/C8 deferred (require person at screen).
> M-PREVIEW-FRAMEWORK milestone complete.
> No open tasks remain. Next: M-WEBRADIO (pending PM scheduling).
>
> **PM sync 2026-06-14 (session 1)** — M-TELETEXT complete close-out.
> TASK-191 (P3 TLS heap contention test) closed. T272 PASS. Three bugs surfaced and
> fixed during execution: (1) `fetchTeletext()` missing `tlsYield()`/`tlsResume()` —
> TLS heap contention confirmed, fixed (ADR-044 item 9 revised); (2) `_lastFetch=0`
> early-boot no-enqueue bug in TeletextApp — fixed via `_forceNow()` unsigned-underflow
> helper; (3) null-byte parser bug — NOS body contains `\x00\x00` before `</pre>`,
> breaking `String::indexOf()` via `strstr()` — fixed with null-safe `memcmp` scan.
> No open tasks remain. M-TELETEXT milestone complete.
> Roadmap M-TELETEXT status updated to done.
> Next: M-WEBRADIO (design draft; R&D spike EXP-005 done; pending PM scheduling).
>
> **PM sync 2026-06-13 (sign-off + team review session)** — Major close-out.
> Preview signed off (TASK-175), ADR-044 accepted (TASK-185). P1 firmware gate cleared.
> Parallel team review (Architect/VE/Developer/QM) produced 10 document fixes and 7 new tasks
> (TASK-185–191). Key fixes: 6-zone strip table in ADR-044, scan range corrected to
> tap-column model (conclusive fix for two-column index pages 600/800), TeletextState
> struct spec added to DS-3, TASK-177 step 6 corrected (teletextAutoAdvance added),
> TASK-181 dep relaxed. Test plan: G3 resolved, T249–T251 → ready to run, T261
> updated with concrete tap coords, T269–T271 added.
> TASK-179 closed (teletext.png/active icons baked to slot 9).
> TASK-181 closed (app/gen/teletext_layout.h — all strip zone constants locked).
> TASK-182 closed (dedicated ◄◄ back zone, even spacing).
> Architect proposes TELETEXT_ENABLED build flag (5 touch-points; single knob) — not
> yet filed as a task, pending human scheduling decision.
> Open: TASK-177 (firmware — now unblocked), TASK-180/183/184/186/187/188/189/190/191.
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
>
> **PM sync 2026-06-13 (design follow-up)** — M-TELETEXT open questions resolved.
> All 5 design open questions (OQ1–OQ5) closed via parallel research: fillTriangle()
> confirmed for right-strip arrows (Font1 has no ▲/▼); 10-entry uint16_t history ring
> on TeletextAppState; subpage auto-advance off by default; root CA confirmed as
> USERTrust RSA Certification Authority (not DigiCert — TASK-176 done); R&D spike
> EXP-004 filed (TASK-178 done) — SVT (SE) viable second entry, RAI incompatible,
> ORF/ARD blocked on-device, YLE needs API key.
> M-TELETEXT.md and ADR-044 updated with confirmed decisions. EXP-004 at
> `docs/rnd/reports/EXP-004-teletext-multi-country-spike.md`.
> Open: TASK-175 (preview iteration — P1 gate), TASK-177 (firmware), TASK-179 (icons).
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
>
> **PM sync 2026-06-13 (PoC session)** — M-TELETEXT proof-of-concept session.
> TASK-169 (WiFi auto-navigate) closed — done 2026-06-12.
> New milestone M-TELETEXT opened: NOS Teletekst live reader as the 10th multiapp slot.
> PoC validated entirely on-host before firmware: NOS API reverse-engineered, teletext
> control codes (text vs mosaic graphics modes) decoded, preview tool
> (`app/tools/preview_teletext.py`) built with full 320×240 canvas + taskbar + live
> navigation. Resource impact assessed (1.1 KB/fetch, fits dataTask pattern, ~4 KB SRAM).
> Design doc M-TELETEXT.md written; ADR-044 proposed; roadmap entry added.
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
>
> **PM sync 2026-06-12 (end of session)** — Major close-out: all "Open Tasks" sections
> from ADR-042 follow-on, settings-001 polish, SPIFFS hygiene, M-SETUP-WIZARD VE, M-SETTINGS
> WiFi Phase 2, M-TASKBAR-ICONS, M-SETTINGS-APP-WIRE, and M-DATATASK-PROGRESS are now done.
> TASK-173/174 (volatile progress indicators for all long-running dataTask fetches) implemented
> and DUT-verified (T170, T_WX_05, T_CX_05 all PASS). Roadmap milestone M-DATATASK-PROGRESS
> closed. Sole open task: TASK-169 (UX auto-navigate after WiFi connect).
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).
>
> **PM sync 2026-06-09 (end of session)** — Roadmap retrofitted (6 missing milestones added,
> 3 superseded proposal docs deleted). M-SETUP-WIZARD designed: `run/setup` wizard, SPIFFS
> primary WiFi path, PATCH-003 registered in upstream-patches.md (not yet applied).
> SPIFFS hygiene: live DUT dump confirmed partition layout + file inventory; TASK-160/161/162
> filed. TASK-161 (`run/spiffs` non-destructive manager) is P1 blocker for M-SETUP-WIZARD.
> DUT visual verify batch closed 2026-06-09: TASK-150 (backlight PWM) PASS, TASK-152 (LDR row
> rename) PASS, TASK-153 (city picker drag) PASS, TASK-154 (UTC offset column) PASS.
> Completed and closed tasks are in [tasks-archive.md](tasks-archive.md).

---

## Deferred — M-HOST-WINAMP (backburner — see session-5 note above)

> TASK-203–206 deferred 2026-06-14 (session 5). M-HOST-WINAMP is the correct long-term
> preview framework but costs 6–7 dev-days before the WebRadio preview gate (T275) can clear.
> Decision: fix TASK-201 with targeted sprite extraction instead. Reopen M-HOST-WINAMP
> after M-WEBRADIO ships.

### TASK-203 — M-HOST-WINAMP: sprite + font inventory (research complete, document pending)

Trace the full pipeline from `.wsz` → `bake_skin.py` → `gen/skin_assets.c` + `gen/skin_layout.h`
→ `WinampDisplay.h` blitSprite calls. Produce a single reference document at
`docs/architecture/designs/M-HOST-WINAMP.md` covering:

1. **Bake pipeline** — which BMP files from the .wsz are extracted, what C arrays they become,
   and their dimensions.
2. **Sprite blit table** — for every visual element in the Winamp UI: source atlas, UV rect,
   screen position, which WinampDisplay method controls it.
3. **Font inventory** — distinguish between the Winamp LED bitmap font (TEXT.BMP → SKIN_FONT /
   SKIN_GLYPH) and TFT_eSPI system fonts (Font 1 in PLEDIT rows; Font 2+ in other apps).
4. **Computed elements** — elements with no sprite atlas: VU bars (computed colour gradient),
   PLEDIT row fill (fillRect), PLEDIT row text (Font 1).
5. **Feature element map** — table of every visible Winamp UI element with its method, atlas,
   and whether it is relevant to the WebRadio remap.

Research is largely complete from code reading (2026-06-14). Document needs authoring.

**Priority:** P1 — gates TASK-204 (can't implement renderer without the map)
**Status:** deferred — M-HOST-WINAMP on backburner per 2026-06-14 session-5 decision
**Opened:** 2026-06-14
**Milestone:** M-HOST-WINAMP
**Owner:** Architect + Developer
**Deps:** —

---

### TASK-204 — M-HOST-WINAMP: WinampRenderer.py — Python port of WinampDisplay.h

Create `app/tools/winamp_renderer.py`: a Python class that mirrors `WinampDisplay.h`
sprite-for-sprite, using PIL instead of TFT_eSPI `pushImage`.

**Architecture:**
- Re-use extraction functions already in `bake_skin.py` to read sprites from the `.wsz`
  into PIL Image objects (not RGB565 C arrays — keep as RGBA/RGB PIL for host rendering).
- One method per WinampDisplay method: `blit_main_bg()`, `draw_transport_buttons(pressed=-1)`,
  `draw_title_text(text, scroll_offset=0)`, `draw_time_digits(seconds)`,
  `draw_status_indicator(playing)`, `draw_posbar(pct)`, `draw_volume(pct)`,
  `draw_vu(l_level, r_level)`, `draw_playlist(rows, active_idx, scroll_offset)`.
- Coordinate system: same as firmware (originX=0, originY=0; PLEDIT_Y=116 etc. from skin_layout.h).
- Output: a PIL Image (320×240 RGB) that matches what the DUT renders pixel-accurately.
- Uses `app/gen/skin_layout.h` constants (parsed via regex, same as `preview_vis.py` pattern).

**Not in scope:** interaction / touch / animation — static render only.

**Priority:** P1 — gates TASK-205 and TASK-206
**Status:** deferred — M-HOST-WINAMP on backburner per 2026-06-14 session-5 decision
**Opened:** 2026-06-14
**Milestone:** M-HOST-WINAMP
**Owner:** Developer
**Deps:** TASK-203

---

### TASK-205 — M-HOST-WINAMP: preview_spotify.py — full Spotify state preview (human sign-off gate)

Create `app/tools/preview_spotify.py`: interactive pygame preview of the Spotify/Winamp app
using `WinampRenderer` from TASK-204.

Mock data to show in the playing state:
- Track: "BIRDS OF A FEATHER" by "Billie Eilish", 3:14
- Playlist: 5 entries, entry 0 active
- Progress: 1:23 / 3:14 (seek thumb at ~43%)
- Volume: 72%
- Shuffle: off, Repeat: off
- VU: active sine envelope

Keyboard: P=playing, S=stopped, Q=quit. Taskbar drawn via `draw_taskbar_pil`.

**Gate:** Human looks at the preview and compares it to a DUT screenshot or `skin_hitzones.png`.
If all elements land in the right zones, TASK-206 is unblocked.

**Priority:** P1 — gates TASK-206 and TASK-201 reopen
**Status:** deferred — M-HOST-WINAMP on backburner per 2026-06-14 session-5 decision
**Opened:** 2026-06-14
**Milestone:** M-HOST-WINAMP
**Owner:** Developer + human sign-off
**Deps:** TASK-204

---

### TASK-206 — M-HOST-WINAMP / M-WEBRADIO: preview_webradio.py v2 on WinampRenderer

Rewrite `app/tools/preview_webradio.py` using `WinampRenderer` from TASK-204.

WebRadio remaps:
- `draw_title_text()` → station name marquee (line 1)
- New `draw_icy_title()` helper → ICY StreamTitle in the 7px gap (y=33..42) between title and VU
- `draw_posbar()` replaced by `draw_buffer_bar(fill_pct)` at same POSBAR zone
- `draw_vu()` → unchanged (audio.getVUlevel() feeds same zone)
- `draw_playlist()` → station list (PLEDIT rows, PLEDIT chrome)
- New `draw_country_badge()` → small label in top-right of main area

Transport buttons, volume, shuffle/repeat: rendered from skin but labelled/ignored for radio
(tap targets will be remapped in firmware; preview just shows them as they are).

States: stopped / connecting / playing / error (same keyboard as TASK-205).

**Priority:** P2 — unblocks after TASK-205 human sign-off
**Status:** deferred — M-HOST-WINAMP on backburner per 2026-06-14 session-5 decision
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer + human sign-off (T275 gate)
**Deps:** TASK-205

---

## Open — M-WEBRADIO shift-left phase (2026-06-14)

### TASK-199 — M-WEBRADIO: flash budget gate

Add `esphome/ESP32-audioI2S` to `lib_deps` in `platformio.ini` (under the
`cyd2usb_winamp` env). Run `pio run -e cyd2usb_winamp`. Report binary size vs
partition budget. If it fits: gate clears, unblock TASK-200–202 and firmware
implementation. If tight: evaluate stripped MP3-only fork before scheduling
firmware work.

**Priority:** P1 — sole blocking gate for M-WEBRADIO
**Status:** done — 2026-06-14. Build SUCCESS at 55.6% flash (1,458,409 / 2,621,440 bytes). Library
compiles clean with two workarounds baked into `cyd2usb_winamp` env: `-DAUDIO_NO_SD_FS` (suppresses
SD/MMC/FS/SPIFFS/FFat includes in Audio.h — we only need WiFi streaming) + `SD_MMC` added to
`lib_ignore` (prevents `deep+` mode from auto-compiling framework SD_MMC, which has an FS.h include-path
issue). Linker dead-strips unused Audio symbols; actual flash delta measurable only when WebRadio app
is wired. At EXP-005 estimated 500 KB peak, projected ceiling ~75% — budget safe. Gate clears.
**Opened:** 2026-06-14
**Closed:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer
**Deps:** —

---

### TASK-200 — M-WEBRADIO: radio-browser.info API probe + TLS cert + ICY metadata probe

Two host-only validations:

1. `app/tools/test_radiobrowser_api.py` (follow `test_yahoo_finance_api.py` pattern):
   - Confirm HTTPS + print TLS cert issuer → root CA for `dataTaskCerts.h`
   - Validate JSON shape: `name`, `url_resolved`, `bitrate`, `votes` present in 100-station response
   - Measure raw response body size (expect ~220–240 KB); confirm ArduinoJson filter reduces to budget
   - Test `de1` → `nl1` → `at1` mirror fallback
   - Spot-check 5 country codes from the baked list

2. Python ICY metadata probe: connect to a live MP3 stream with `Icy-MetaData: 1`
   header, parse and print `StreamTitle` from the inline metadata — confirms format
   before the ESP32-side parser is written.

Deliverable: TLS root CA identified; API contract and ICY format confirmed on host.

**Priority:** P2
**Status:** done — 2026-06-14. TLS root CA: Let's Encrypt R13 (ISRG Root X1 chain); body 109.5 KB for 100 NL stations; ICY format confirmed — `StreamTitle='Artist - Title';` at metaint=64000, via NPO Radio 2.
**Opened:** 2026-06-14
**Closed:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer
**Deps:** TASK-199 (pass first)

---

### TASK-201 — M-WEBRADIO: preview_webradio.py canvas layout

New pygame preview tool following the `preview_vis.py` pattern (not clock — web
radio reuses the Winamp skin frame). Takes `--skin gen/skin_preview.png` as the
base layer (baked 320×240 chrome); draws radio-specific content on top:

- PL panel: station list rows + scroll indicator
- Station name marquee (line 1) + ICY `StreamTitle` (line 2)
- Buffer bar (replaces seek bar) + bitrate field
- VU meter (mocked envelope)
- Country badge (top-right of title area)
- Keyboard shortcuts to cycle states: stopped / connecting / playing / error

Requires `./run/bake-skin` to have been run (produces `gen/skin_preview.png`).
Human signs off on layout before firmware work starts — avoids coordinate rework
after first flash.

**Priority:** P2
**Status:** done — 2026-06-14. T275 human sign-off obtained after targeted fix. All T273–T282 passing.

Five bugs caught during T275 sign-off and fixed before gate cleared:
1. Text overflow past TITLE_W — `composite_text` not truncating; fixed with `[:TITLE_W//(GLYPH_W+1)]`.
2. POSBAR used a synthetic blue fill-rect — firmware uses `POSBAR_BG blit + POSBAR_THUMB_N at position`; fixed to match.
3. PLEDIT title bar had a preview-invented text overlay ("10 stations • NL") — no firmware counterpart; removed.
4. Row `fillRect` used `SCREEN_W-1` (319) instead of `PLEDIT_DISPLAY_W-1` (274) — overwrote the taskbar strip.
5. ICY StreamTitle rendered as a second LED row — DUT has one scrolling row only (`drawTitleText`); collapsed to single combined string mirroring `lastTitle` construction.

Country badge and "buf" label also removed (no firmware counterpart).
Architect added `§Firmware rendering notes` to M-WEBRADIO.md (commit 572379c).
**Opened:** 2026-06-14
**Closed:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer + human sign-off
**Deps:** TASK-199 (pass first)

---

### TASK-202 — M-WEBRADIO: country list generator

Host script that:
1. Reads `kCities[]` from `app/src/settings/cities.h`
2. Deduplicates the `country` ISO 3166-1 alpha-2 field → unique country code list
3. Cross-checks each code against radio-browser.info's available `countrycode` values
   (one API call); flags any cities.h codes with zero stations
4. Outputs a static `kWebRadioCountries[]` C array of `{code, displayName}` pairs,
   sorted and ready to paste into firmware

Deliverable: `app/tools/gen_webradio_countries.py` + generated array block.
Coverage gaps (codes with few stations) noted — may inform filtering defaults.

**Priority:** P3
**Status:** done — 2026-06-14. gen_webradio_countries.py written; app/gen/webradio_countries.h generated with 65 entries; 0 codes had zero stations (full coverage — all 65 codes from cities.h are live on radio-browser.info). Notable finding: IN (India) was present in cities.h but missing from the initial COUNTRY_NAMES dict — caught by the script's warning and fixed before final output.
**Opened:** 2026-06-14
**Closed:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer
**Deps:** TASK-200 (API reachable confirmed)

---

### TASK-193 — M-CLOCK-STYLES: phases 2–4 firmware implementation

Implement ClockStyle enum + storage (Phase 2), Flip/Nixie/VFD renderers (Phase 3), and
Settings wiring (Phase 4) for the M-CLOCK-STYLES milestone.

Deliverables (all done):
1. `ClockStyle` enum added to `settingsStorage.h` (Digital/Flip/Nixie/VFD).
2. `clockStyle` field added to `AppSettings`; default Digital; load/save under `"clock"` JSON key.
3. `app/src/clockApp.h` created — full ClockApp with all four renderers:
   - `_drawDigital()` — existing fixed-position HH/colon/MM (Phase 1 bug fix preserved).
   - `_drawFlip()` — 5-frame split-flap animation; FlipDigit struct; 30ms tick gate while animating.
   - `_drawNixie()` — four round-rect tubes with inner/outer glow; amber colon dots; blinking.
   - `_drawVFD()` — Dexter v2 dot-matrix glyphs (kVFDGlyphs[10][22]); teal ON/OFF palette;
     date lines at y=148/166 in 2× Font1; no bloom (option 3 from firmware note in M-CLOCK-VFD.md).
4. `main.cpp` — inline ClockApp (~75 lines) replaced with `#include "clockApp.h"`.
5. `appRegistry.h` — Clock configurable flag 0 → 1.
6. `gen_app_registry.py` re-run → `configurable_apps.h` CONFIGURABLE_APP_COUNT 6 → 7.
7. `appsSection.h` — `_repaintClock()` (single "Style" row) + `_cycleClock()` + dispatch cases.
8. `run/check` 5/5 gates pass. Flash 55.6% (+2.7% for VFD glyph table + new renderers).

**Priority:** P2
**Status:** done
**Opened:** 2026-06-13
**Closed:** 2026-06-13
**Milestone:** M-CLOCK-STYLES
**Owner:** Developer
**Deps:** TASK-192 (preview framework pattern used for concept tools)

---

### TASK-194 — M-CLOCK-STYLES: VE suite T_CLK_01–14

Serial-driven DUT verification of the clock style system.

Deliverables (all done):
1. `get clockStyle` / `set clockStyle` serial commands added to main.cpp cmdGet/cmdSet.
2. 14 test functions added to `run_serialdbg_tests.py` (t_clk_01..t_clk_14).
3. `docs/verification/regression_suite/m-clock-styles.md` created.
4. All 14 tests pass: style cycle, persistence, app-switch preservation, heap stability,
   device responsiveness during Flip animation, response format, error rejection.
5. Visual criteria C1/C4/C5/C6/C8 deferred to operator physical screen review.

Result: **14/14 PASS**. Heap leak=0B across 8 style switches.

**Priority:** P2
**Status:** done
**Opened:** 2026-06-13
**Closed:** 2026-06-13
**Milestone:** M-CLOCK-STYLES
**Owner:** VE
**Deps:** TASK-193

---

### TASK-192 — M-PREVIEW-FRAMEWORK: implement preview_common.py and port 6 tools

Retroactive task — implementation completed in session 2026-06-13 before task was filed.

Deliverables (all done):
1. `app/tools/preview_common.py` created — full public API: constants, `APP_ORDER`,
   `load_icon_pil`, `load_icon_pygame`, `draw_taskbar_pil`, `draw_taskbar_pygame`,
   `write_gif`, `PreviewWindow`.
2. Six tools ported — no tool defines `SCREEN_W`, taskbar constants, or `write_gif` locally.
3. `preview_heatmap.py` taskbar upgraded: PNG icons, canonical `(32,32,32)` palette,
   `scroll_offset=2` so Stock is in last visible slot with active indicator.
4. `preview_clock.py` taskbar call changed to `draw_taskbar_pil(img, "Clock")`.
5. `preview_teletext.py` uses `_APP_ORDER = APP_ORDER + ["Teletext"]` extension pattern.
6. Verify pass: all imports clean, all render paths exercised headlessly. One bug found
   and fixed (`pygame.K_Q` → `pg.K_q` in `PreviewWindow.handle_event`).

**Priority:** P2
**Status:** done
**Opened:** 2026-06-13 (retroactive)
**Closed:** 2026-06-13
**Milestone:** M-PREVIEW-FRAMEWORK
**Owner:** Developer
**Deps:** M-APP-REGISTRY, M-TASKBAR-ICONS

---

## Closed This Cycle

### settings-001 new-items — Cancel button, cal history, KB ESC, TouchDebugOverlay
- **Commits:** `fd93679` (feat), `c07c903` (bug fix + VE results)
- **Status:** done — all 6 new-items features implemented and design-audited
- **VE suite:** `docs/verification/regression_suite/settings-001-new-items.md`
  - 8 serial-driven tests: PASS
  - Physical (cal corner taps) + visual (TDBG, cal history): deferred — require person at screen
  - KB cancel: BLOCKED-PHASE2 (keyboard not reachable until WiFi Phase 2)
  - Bug found and fixed during VE: `DisplaySection::tick()` map() crash when `ldrLow==ldrHigh`
- **Design audit:** all 6 features strong-match spec

### TASK-155 — KB cancel `<` press-highlight
- **Commit:** `3962903`
- **Status:** done — input-bar repaint path fixed; `cancelPressed` check added to `repaintInputBar()`
- **Validation:** BLOCKED-PHASE2 (full visual confirm when keyboard reachable)

---

## Closed — ADR-042 Harness & Firmware Follow-on

### TASK-156 — E3 harness refactor: wrap affected tests in `_bgpoll_suspended`, cut sleep budget
- **Related:** ADR-042 E3, `docs/process/harness_sync_contract.md`
- **Priority:** P1 — remaining ADR-042 exit criterion
- **Status:** done — 5/5 targeted runs, zero FAILs, no retry triggered
- **Opened:** 2026-06-08
- **VE results (2026-06-08, 5 runs):**

  | Test | R1 | R2 | R3 | R4 | R5 |
  |---|---|---|---|---|---|
  | T_WX_01 | PASS | PASS | PASS | PASS | PASS |
  | T_CX_01 | PASS | PASS | PASS | PASS | PASS |
  | T-BUSY-01b | SKIP | SKIP | PASS | SKIP | SKIP |
  | T-BUSY-05 | PASS | PASS | PASS | PASS | PASS |
  | T-CDWN-02 | SKIP | PASS | PASS | PASS | PASS |
  | T-CDWN-03 | PASS | PASS | PASS | PASS | PASS |

  T-BUSY-01b SKIPs: cold Yahoo Finance TLS >45 s (pre-existing network condition).
  T-CDWN-02 SKIP R1: warm connection cleared before tap2 (preserved skip path, correct).
  No retry branches triggered across all 5 runs.

- **Sleep budget (static grep, post-refactor):** T-BUSY-01 0.40 + T-BUSY-01b 0.70 + T-CDWN-02 1.30 + T169 3.00 = 5.40 s. Drops to 2.40 s after TASK-157 (T169 retry removal). ≤ 4 s criterion requires TASK-157.
- **Owner:** Developer (harness) / VE (verify run)

---

### TASK-157 — Remove E1-redundant retry loops: T169, T-BUSY-03
- **Related:** ADR-042 E1, commit bfe6320
- **Priority:** P2 — dead-code cleanup; E1 log suppression makes these loops unnecessary
- **Status:** done — retry loops removed; T-BUSY-03 PASS, T169 SKIP (no track, expected precondition)
- **Opened:** 2026-06-08
- **Root cause resolved:** E1 HTTPClient log suppression eliminates the Core 0/Core 1 UART race
  that caused garbled `switchApp` responses. Retry branches are dead code. Removed.
- **Changes:** T169 converted to single-attempt with `_bgpoll_suspended`; T-BUSY-03 inner loop
  simplified — blind 3 s sleep and retry removed, `_bgpoll_suspended` context used instead.

---

### TASK-158 — Firmware: taskbar scroll failures (T163, T165)
- **Priority:** P1
- **Status:** done — T162–T166 all PASS (1 DUT run, 5/5)
- **Opened:** 2026-06-08
- **Root causes:**
  1. `drainInjectionQueue` was routing all injected touch samples through `handleWinampInput`
     instead of the taskbar gesture API (`tbGesturePress/Continue/End`). Fixed: samples with
     `sx >= TASKBAR_X` now route to the gesture API.
  2. `appHandleInput` fired `tbGestureEnd` on the physical `!touched` branch even during an
     active serial drag injection, cancelling the gesture early. Fixed: guard with
     `!winampDisplay._injectingDrag` (`#ifdef SERIAL_DEBUG` only).
  3. `_TB_N` in the test harness was stale (`APP_COUNT - 1 = 8`) from when there were 8 apps.
     All 9 apps are in the taskbar; firmware correctly uses `AppId::COUNT = 9`. Fixed:
     `_TB_N = APP_COUNT` (= 9).
- **VE results (2026-06-08, 1 DUT run):** T162 PASS, T163 PASS, T164 PASS, T165 PASS, T166 PASS.

---

### TASK-159 — Firmware: settings navigation failures (T-SET-03, T-SET-07)
- **Priority:** P1
- **Status:** done — T-SET-03 PASS, T-SET-07 PASS
- **Opened:** 2026-06-08
- **Root cause:** `SettingsApp::dbgGet` did not handle `settingsAppSubmenu` query — the harness
  could not read the `AppsSection` submenu depth. Added handler returning `_apps.submenu()`.
  Added `submenu()` accessor to `AppsSection`.
- **VE results (2026-06-08):** T-SET-03 PASS, T-SET-07 PASS.

---

## Closed — settings-001 DUT Bugs & Polish

### TASK-150 — Fix backlight PWM: LEDC channel setup
- **Feature:** settings-001 / display-settings
- **Priority:** P1
- **Status:** done — T-DISP-01 PASS (2026-06-09 DUT). Slider controls brightness ✓.
- **Opened:** 2026-06-06 (DUT feedback)
- **VE results (2026-06-09):**
  - T-DISP-01: slider drag changes backlight duty — PASS
  - T-DISP-04 (boot persistence): deferred — requires physical reset sit
  - Auto-brightness (T-DISP-02/03): confirmed functional on DUT ✓ (see additional fixes below)
- **Additional fixes applied 2026-06-09 during DUT session:**
  1. LDR polarity inverted — this hardware reads low ADC in ambient, high ADC when covered.
     `map(..., 1, 10)` changed to `map(..., 10, 1)` in auto tick.
  2. Hardware-correct defaults: `ldrLow=0`, `ldrHigh=120` (was 200/3800 — wrong for this device).
  3. Settings migration: old saves with `ldrHigh==0` reset to 120 on load.
  4. Auto-brightness now maps LDR directly to 8-bit PWM duty (25–255), bypassing
     the 10-step slider abstraction. Hysteresis threshold: 3 PWM units.
  5. Cal rows changed from read-only to tap-to-capture:
     `Cal: bright` (tap in ambient) → stores ldrLow; `Cal: dark` (tap while covering) → stores ldrHigh.
     Guard prevents Cal: dark storing an invalid low reading.
- **Owner:** Developer

---

### TASK-151 — Investigate LDR: always reads 0 on DUT
- **Feature:** settings-001 / display-settings
- **Priority:** P2
- **Status:** closed — resolved in TASK-150 DUT session (2026-06-09)
- **Resolution (corrected 2026-06-09):** Previous note (2026-06-07: "1018/1404, no inversion")
  was wrong — likely measured under different firmware/conditions. Actual hardware behaviour:
  ambient light → ADC ≈ 0; fully covered → ADC ≈ 140+. Polarity IS inverted (low ADC = bright).
  All fixes applied in TASK-150.

---

### TASK-152 — Rename LDR calibration rows; clarify purpose
- **Feature:** settings-001 / display-settings
- **Priority:** P3 (UX clarity)
- **Status:** done — DUT confirmed 2026-06-09. Labels "Cal: bright" / "Cal: dark", sub-header "Calibration" visible. Rows are tap-to-capture (implemented as part of TASK-150 LDR fixes).
- **Opened:** 2026-06-06 (DUT feedback — "what is LDR Low High for?")

---

### TASK-153 — City picker: scrollbar drag gesture
- **Feature:** settings-001 / time-settings
- **Priority:** P2 (UX — 78 cities, 13 pages via button-only is slow)
- **Status:** done — T-CITY-DRAG-01 PASS (2026-06-09 DUT). Scrollbar drag scrolls city list proportionally ✓.
- **Opened:** 2026-06-06 (DUT feedback)
- **Scope:** Phase 1 design explicitly deferred drag (open question 4 in
  `time-settings.md`). Promote to in-scope based on DUT feedback.
- **Design:** Pointer-capture pattern (same as SliderWidget):
  - `handleInput` now handles `TouchPhase::Press/Move/Release` (not just Release).
  - On Press in `px >= kSbX` (scrollbar zone), above `kSbUpY1` and below `kSbDnY0`
    (thumb track): record `_sbDragAnchorY = py` and `_sbDragAnchorOffset = _cityOffset`.
    Set `_sbDragging = true`.
  - On Move with `_sbDragging`: compute delta = `(py - _sbDragAnchorY)` mapped to
    city-index delta using track height and city count. Update `_cityOffset`.
    Repaint picker (full or scrollbar-only).
  - On Release: commit `_cityOffset`; clear `_sbDragging`.
  - On Press in ▲/▼ button zones: existing tap logic (only on Release still fine —
    or change to Press for snappier response).
- **Member additions to TimeSection:**
  ```cpp
  bool    _sbDragging        = false;
  int16_t _sbDragAnchorY     = 0;
  uint8_t _sbDragAnchorOffset = 0;
  ```
- **Spec update:** Close open question 4 in `time-settings.md`.
- **Validation:** T-CITY-DRAG-01 (new test): drag scrollbar thumb moves city list
  proportionally; release commits. VE to add to settings-sections-001 suite.
- **Owner:** Developer

---

### TASK-154 — City picker: UTC offset prefix column + group separators
- **Feature:** settings-001 / time-settings
- **Priority:** P2 (UX — user can't tell offset at a glance)
- **Status:** done — T-CITY-OFFSET-01 PASS (2026-06-09 DUT). UTC offset column + group separators visible ✓.
- **Opened:** 2026-06-06 (DUT feedback)
- **Design changes required:**

  **1. CityEntry struct** (`cities.h`): Add offset fields:
  ```cpp
  struct CityEntry {
      const char* city;
      const char* country;
      float       lat;
      float       lon;
      const char* posixTz;
      const char* tzName;
      int8_t      utcHours;    // e.g. +9, -5, 0  (signed, whole hours part)
      uint8_t     utcMins;     // 0, 30, or 45
      bool        groupBreak;  // true = first city in a new UTC offset group
  };
  ```
  Populate all 78 rows. Reference: current cities.h comments already group by
  UTC offset, so `groupBreak` is a mechanical annotation.

  **2. UTC offset display string** — helper in `timeSection.h`:
  ```cpp
  // Fills buf with e.g. "+12", " +9", "+9:30", " -5", " +0"
  // Right-aligns the hours digit at a fixed column position.
  static void fmtUtcOffset(char* buf, int len, int8_t h, uint8_t m) {
      if (m == 0)
          snprintf(buf, len, "%+3d", (int)h);      // "+12" or " -5" or " +0"
      else
          snprintf(buf, len, "%+d:%02d", (int)h, (int)m);  // "+9:30"
  }
  ```
  Note: `½` not used — `:30`/`:45` is clear and ASCII-safe.

  **3. City picker row layout** — revise `_repaintPicker()`:
  ```
  x=8      x=52    x=60          x=246   x=250..256
  |UTC off |  sep  | City name   | CC     |
  " +9"        "  Tokyo         JP"
  "+9:30"      "  Adelaide      AU"    ← first in UTC+9:30 group
  ```
  - UTC offset column: x=8..50, MR_DATUM, font 2 (small)
  - Vertical separator line: x=54, height of row, colour S_SEP
  - City name: x=58, ML_DATUM, font 2
  - Country: x=246 (before scrollbar at 257), MR_DATUM, font 2

  **4. Group separator** — before rendering a `groupBreak=true` city row, draw a
  1px horizontal line at the top of that row (colour S_SEP, x=8..256). This
  signals a UTC offset transition visually without requiring a header row.

  **5. Row width** — all city text stays within x<257 (scrollbar at x=257).

- **Spec update:** Update `time-settings.md` §City picker, §CityEntry struct.
- **Validation:** T-CITY-OFFSET-01 (new): picker shows UTC offset for each row;
  group breaks visible. T-TIME-01 unblocked (city selection unchanged). VE to
  add to settings-sections-001 suite.
- **Owner:** Architect (spec update for CityEntry) + Developer (implementation).

---

## Closed — SPIFFS hygiene

### TASK-160 — Retire `host_overrides.json` DNS-override path

`dnsOverride.h` + `host_overrides.json` was a one-off field hack (AT&T cellular tether, Marriott portal, 2026-05-05/06). It was never regression-tested; the VE backlog item was never closed. The IPs in the current SPIFFS dump are stale (CDN GSLB rotates every few hours/days). The path is dev-only and has no place in a production or published project.

- Remove `dnsOverride.h` from `app/src/` and its `#include` from `main.cpp`.
- Remove `tools/refresh_host_overrides.sh`.
- Remove `app/data/host_overrides.json` (gitignored, but document removal).
- Update `.gitignore`: drop `app/data/host_overrides.json` entry (will be covered by `app/data/*` wildcard once TASK-161 lands).
- Update `CLAUDE.md` §DNS override section — replace with a brief note: removed, was dev-only hack.
- VE: confirm build clean; DUT boots and connects normally without the file.

**Priority:** P2  
**Status:** done — `dnsOverride.h` removed, `refresh_host_overrides.sh` deleted, gitignore entries dropped, CLAUDE.md §DNS override removed. Build PASS.  
**Opened:** 2026-06-09  
**Owner:** Developer  

---

### TASK-161 — `run/spiffs`: non-destructive SPIFFS file manager

Current `run/flash-fs` formats the entire SPIFFS partition before writing, silently wiping runtime-written files (`/settings.json`, `/cal.json`, `/drd.dat`). This is unacceptable once users have configured settings or performed touch calibration.

Replace the blanket-upload model with a read–inspect–selective-write workflow using `esptool.py` (already in PlatformIO) and `mkspiffs_espressif32_arduino` (already in PlatformIO).

Confirmed working via live DUT dump (2026-06-09):
- Partition: `spiffs` at `0x290000`, size `0x160000`
- `mkspiffs` default params match the device (no `-b`/`-p` flags needed)
- 5 files on device: `spotify_diy_config.json`, `host_overrides.json`, `cal.json`, `settings.json`, `drd.dat`

**Subcommands:**

```sh
./run/spiffs ls               # list all files on device with sizes
./run/spiffs pull             # extract all files → app/data/spiffs-dump/ (read-only, non-destructive)
./run/spiffs pull <file>      # extract single file → stdout or app/data/spiffs-dump/<file>
./run/spiffs push <file>      # read-modify-write: update single file, all others preserved
./run/spiffs push             # merge app/data/ into live SPIFFS (read-modify-write, no format)
./run/spiffs rm <file>        # remove single file from SPIFFS (read-modify-write)
```

**Implementation:** shell script wrapping `esptool.py read_flash` → `mkspiffs -u` → modify → `mkspiffs -c` → `esptool.py write_flash`. Resolves port via `run/lib.sh`. Kills/restores monitor.

**`run/flash-fs` fate:** deprecate in favour of `run/spiffs push`; keep as escape hatch for corrupted filesystem (add a `--format` flag or separate `run/spiffs format`).

**Docs to update:** `project_run_scripts.md`, `CLAUDE.md`, `dut_workflow.md`, `README.md`.

**Priority:** P1 — blocks M-SETUP-WIZARD implementation (setup wizard must not wipe cal/settings)  
**Status:** done — `run/spiffs` implemented and VE-verified (TASK-165, 2026-06-09). T-SPIFFS-01–10, T-SPIFFS-12 passing. Safety invariants confirmed: push/rm preserve untargeted files byte-identically; mkspiffs round-trip clean.  
**Opened:** 2026-06-09  
**Deps:** TASK-160 (retire host_overrides path before designing the managed file set)  
**Owner:** Developer  

---

### TASK-162 — Update `.gitignore`: `app/data/*` wildcard + `.gitkeep`

Currently `.gitignore` names credential files individually (`app/data/spotify_diy_config.json`, `app/data/host_overrides.json`). Any new credential or runtime file needs a manual entry — a silent footgun.

Replace with a directory-level wildcard:
```gitignore
# app/data/ — runtime credentials and data; never commit
app/data/*
!app/data/.gitkeep
```

Add `app/data/.gitkeep` to keep the directory tracked on a clean clone.
Remove the now-redundant named entries.

**Priority:** P2  
**Status:** done — `app/data/*` wildcard + comment in both `.gitignore` and `app/.gitignore`. Note: `.gitkeep` skipped — `app/data` is a tracked symlink, not an empty directory; symlink itself keeps the path present on clone.  
**Opened:** 2026-06-09  
**Deps:** TASK-160 (retire host_overrides so we're not gitignoring a removed file)  
**Owner:** Developer  

---

## Closed — TASK-161 VE follow-up (audit 2026-06-09)

### TASK-163 — Fix EXIT trap in `run/spiffs`: restore monitor on implicit failure

`run/spiffs` uses `set -euo pipefail`. The EXIT trap is `rm -rf "$WORK_DIR"` only. If `_read_flash`, `_unpack`, `_pack`, or `_write_flash` fail after `_kill_monitor` has already run, the monitor is left dead — breaking all subsequent serial-debug tests in the same session.

Fix: add `_start_monitor` to the EXIT trap (or a dedicated cleanup function), guarded so it doesn't double-start if the happy path already called it.

**Priority:** P1 — ESCALATION-161-1; error-path VE tests (T-SPIFFS-07, T-SPIFFS-09) cannot run safely until resolved  
**Status:** done — `_MONITOR_KILLED` flag added; EXIT trap calls `_start_monitor` if flag set; `_kill_monitor`/`_start_monitor` clear/set the flag.  
**Opened:** 2026-06-09  
**Deps:** none  
**Owner:** Developer  

---

### TASK-164 — Update `M-SETUP-WIZARD.md`: replace `run/flash-fs` with `run/spiffs push`

`M-SETUP-WIZARD.md` references `./run/flash-fs` in 7 places (lines 14, 22, 35, 196, 199, 200, 208, and exit criterion E3). TASK-161 deprecated `run/flash-fs` in favour of `run/spiffs push`. If the wizard is implemented from the current design doc it will wipe `cal.json`/`settings.json` on every credential update — the opposite of TASK-161's goal.

Update all occurrences to `./run/spiffs push`. Update E3 to read: "Single `./run/spiffs push` offer at end uploads both files non-destructively."

**Priority:** P1 — ESCALATION-SETUP-2; blocks M-SETUP-WIZARD implementation  
**Status:** done — all 7 occurrences updated; E3 updated; subprocess call updated to `["./run/spiffs", "push"]`.  
**Opened:** 2026-06-09  
**Deps:** TASK-161 (run/spiffs must exist before the design doc references it — done)  
**Owner:** Developer  

---

### TASK-165 — VE: run T-SPIFFS suite against DUT; add test_plan.md entries; re-close TASK-161

TASK-161 was closed on "ls confirmed 5 files." The core safety invariants were never verified:
- T-SPIFFS-05: `push <file>` updates only the target; all other files preserved byte-identically
- T-SPIFFS-06: `push` (merge) preserves device-only files (`cal.json`, `settings.json`, `drd.dat`)
- T-SPIFFS-10: mkspiffs round-trip fidelity — no-op push leaves all files byte-identical

Full suite T-SPIFFS-01–12 defined in VE review (2026-06-09). Add all 12 as `planned` entries to `docs/verification/test_plan.md`, then run against DUT. TASK-161 is not truly closed until T-SPIFFS-05, T-SPIFFS-06, and T-SPIFFS-10 pass.

**Priority:** P1 — verifies TASK-161 safety claim  
**Status:** done — T-SPIFFS-01–10, T-SPIFFS-12 passing (DUT 2026-06-09). T-SPIFFS-11 deferred (DUT was connected). Additional fix: `_read_flash` baud reduced to 460800 (CH340 drops bytes at 921600 for reads; writes are unaffected). All 12 entries in test_plan.md.  
**Opened:** 2026-06-09  
**Deps:** TASK-163 (trap fix required before error-path tests T-SPIFFS-07/09 can run safely)  
**Owner:** VE  

---

### TASK-166 — VE: DUT boot confirm for TASK-160 (GAP-160-2)

TASK-160 required "VE: confirm build clean; DUT boots and connects normally without the file." Build PASS was noted but DUT boot was not confirmed. `dnsOverride.h` had an active DNS intercept during Spotify polling — a missed regression here would be silent.

Steps:
1. Flash current firmware to DUT.
2. Monitor boot log — confirm no crash, WiFi connects, Spotify poll succeeds (HTTP 200 or `isPlaying` visible).

Stale docstring in `app/tools/run_serialdbg_tests.py:23` already fixed (host_overrides.json reference removed).

**Priority:** P2  
**Status:** done — firmware flashed (2026-06-09); WiFi up, token POST 200, Spotify polls 200/204 no crash. No dnsOverride trace in boot log. Docstring fix previously committed.  
**Opened:** 2026-06-09  
**Deps:** none  
**Owner:** VE

---

## Closed — M-SETUP-WIZARD VE follow-up (2026-06-11)

### TASK-167 — Fix PATCH-003: WiFi.persistent(false) to avoid NVS corruption on bad SPIFFS creds

Found during T-SETUP-10 (2026-06-11): PATCH-003 calls `WiFi.persistent(true)` before `WiFi.begin(ssid, pass)`. If `wifi_creds.json` contains a wrong password, the bad credentials are written to NVS. WiFiManager's subsequent `autoConnect()` then also fails (it loads the now-corrupted NVS), causing a 60s delay before the portal instead of ~30s. On a device that previously had valid NVS creds, this silently destroys them.

Fix: change `WiFi.persistent(true)` to `WiFi.persistent(false)` in the PATCH-003 block of `WifiManagerHandler.h`. SPIFFS credentials should be tried transiently — NVS is WiFiManager's responsibility, not PATCH-003's.

**Priority:** P1 — correctness bug; bad SPIFFS creds corrupt device NVS  
**Status:** done — `WiFi.persistent(false)` applied to PATCH-003 block in `WifiManagerHandler.h` (2026-06-11). Build + DUT verified (T-SETUP-07 re-baseline shows no regression).  
**Opened:** 2026-06-11  
**Deps:** none  
**Owner:** Developer  

---

## Closed — M-SETTINGS WiFi Phase 2 (2026-06-11)

### TASK-168 — M-SETTINGS WiFi Phase 2: remove WiFiManager/DRD, add on-device connect UI

Replace the WiFiManager + DoubleResetDetector boot flow with:
- NVS reconnect (`WiFi.begin()` no-args) → SPIFFS `/wifi_creds.json` read → open WiFi settings.
- On-device `WifiSection` UI: scan → tap network → keyboard (encrypted) / direct connect (open) → CONNECTING poll → RESULT (retry/cancel).
- If boot reaches `!wifiConnected`: auto-switch to Settings app → WiFi section.

Changes:
- `app/src/main.cpp`: replaced WiFiManager/DRD boot sequence; removed `drd->loop()`; added `clientId[200]`/`clientSecret[200]` globals; added post-init nav.
- `app/platformio.ini`: removed `khoih-prog/ESP_DoubleResetDetector` and `wnatth3/WiFiManager` from lib_deps.
- `app/src/settings/wifiSection.h`: Phase 2 rewrite (Keyboard, Connecting, Result states).
- `Spotify-Diy-Thing/SpotifyDiyThing/spotifyDisplay.h`: PATCH-004 — removed `drawWifiManagerMessage` pure virtual.
- `Spotify-Diy-Thing/SpotifyDiyThing/cheapYellowLCD.h`: PATCH-004 — removed `drawWifiManagerMessage` implementation.
- `Spotify-Diy-Thing/SpotifyDiyThing/WifiManagerHandler.h`: retired (deleted).
- `docs/architecture/designs/M-MULTIAPP/upstream-patches.md`: PATCH-002 status corrected (applied); PATCH-003 retired; PATCH-004 added.

**Priority:** P1 — replaces first-run WiFi setup path  
**Status:** done — build PASS + DUT verified (2026-06-11). T-WIFI-P2-01..06 all passing. Bug found and fixed: async `WiFi.scanNetworks()` cancelled by concurrent Spotify task socket calls on same core; switched to synchronous scan.  
**Opened:** 2026-06-11  
**Deps:** TASK-167, TASK-161  

## Closed — M-TASKBAR-ICONS, M-SETTINGS-APP-WIRE, M-DATATASK-PROGRESS (2026-06-12)

### TASK-170 — M-TASKBAR-ICONS: source + place candidate icon PNGs for review

Source one 32×32 px PNG per app (9 total: Spotify, Clock, Weather, Crypto, Matrix, Life, Settings, Stock, Aquarium) and place them in `app/icons/taskbar/`.

**Priority:** P2  
**Status:** done (2026-06-12) — 9 inactive + 9 active icons designed and placed in `app/icons/taskbar/`. B&W for inactive, coloured for active.  
**Opened:** 2026-06-11  
**Owner:** human (icon design) + Developer (generation)

---

### TASK-171 — M-TASKBAR-ICONS: bake script + taskbar.h update

Write `app/tools/gen_taskbar_icons.py` bake script; update `taskbar.h` to use `pushImage()` from baked arrays.

**Priority:** P2  
**Status:** done (2026-06-12) — `gen_taskbar_icons.py` written; `app/gen/taskbar_icons.{cpp,h}` generated; `taskbar.h` updated; `run/bake-icons` script added; `golden.sha256` updated; DUT flashed and verified.  
**Opened:** 2026-06-12  
**Owner:** Developer

---

### TASK-172 — M-SETTINGS-APP-WIRE: wire per-app settings to app behaviour

Implement ADR-043. Connect `g_settings` per-app fields to Matrix, Life, Aquarium,
Stock, and Crypto app behaviour. Nine work items (W1–W9); see design doc.

**Work items:**

| ID | Area | Change | File(s) |
|----|------|--------|---------|
| W1 | Matrix | `resume()` seeds `_headColor`/`_tailColor`/`_tickMs`; speed-range in `initMatrixState()` | `main.cpp` |
| W2 | Life | `resume()` seeds `_tickMs`/color mode; color branch in render/step | `main.cpp` |
| W3 | Aquarium | `resume()` seeds `_activeFish`/`_speedMult`; loops use `_activeFish` | `aquariumApp.h` |
| W4 | Stock-settings | Replace `_cycleStock()` with keyboard+validation; `StockEditPhase`; `tick()` polls chart; error+retry | `appsSection.h` |
| W4b | Stock-app | `init()`/`resume()` seed `_s.tickers` from `g_settings`; re-fetch on change; `hasPendingAsync()` | `main.cpp` |
| W5 | Stock-dataTask | `configureStockTickers()` + `s_stockTickers` runtime array under spinlock | `dataTask.h`, `dataTaskStorage.cpp` |
| W6 | Crypto-storage | `cryptoCoins[6][8]→[16]`; defaults to word IDs; load/save updated | `settingsStorage.h`, `settingsStorageStorage.cpp` |
| W7 | Crypto-app | `cgIdToDisplay()`; `repaintCrypto()` uses it; `init()`/`resume()` call `configureCrypto()` | `main.cpp` |
| W8 | Crypto-settings | `_cycleCrypto()` pool → word IDs; value column uses `cgIdToDisplay()` | `appsSection.h` |
| W9 | Crypto-dataTask | `configureCrypto()` + dynamic URL + JSON key from ID + magnitude price format | `dataTask.h`, `dataTaskStorage.cpp` |

**Priority:** P2  
**Status:** done  
**Opened:** 2026-06-12  
**Closed:** 2026-06-12  
**Design:** [M-SETTINGS-APP-WIRE.md](../architecture/designs/M-SETTINGS-APP-WIRE.md)  
**ADR:** ADR-043 (accepted)  
**Deps:** M-SETTINGS-001 (done)  
**Owner:** Developer  
**VE scope:** T-SET-01 to T-SET-08 (M-SETTINGS-APP-WIRE regression suite)  
**VE results (2026-06-12):** T-SET-01 PASS, T-SET-02 PASS, T-SET-03 PASS, T-SET-06 PASS, T-SET-07 PASS, T-SET-08 PASS (T-SET-04/05 not in targeted run; passed in full suite). During VE: stale SPIFFS settings.json caused T170/T186/T187 failures; removed and added defensive load() guards. T_CX_05 required separate fix (CoinGecko TLS cert rotation GTS→ISRG Root X1, commit a708657).

---

### TASK-173 — M-DATATASK-PROGRESS phase 1: stockQuoteProgress indicator

Add `volatile int8_t s_stockQuoteProgress` (-1=idle, 0–7=ticker index) to `fetchStockQuote()` in `dataTaskStorage.cpp`. Update at the start of each ticker loop iteration. Expose via `dataTask::stockQuoteProgress()` + `get stockQuoteProgress` global serial handler. Update T170 failure path to report the stalled ticker index and name.

**Work items:**
1. `dataTaskStorage.cpp` — add `s_stockQuoteProgress`; set to ticker index at loop top, -1 on exit
2. `dataTask.h` — add `int8_t stockQuoteProgress()` declaration
3. `main.cpp` — add `get stockQuoteProgress` to global serial handler
4. `run_serialdbg_tests.py` T170 — query `stockQuoteProgress` on timeout; report "stuck on ticker N (SYM)"

**Priority:** P2  
**Status:** done — 2026-06-12 (build clean, both envs)  
**Opened:** 2026-06-12  
**Design:** [M-DATATASK-PROGRESS.md](../architecture/designs/M-DATATASK-PROGRESS.md)  
**Milestone:** M-DATATASK-PROGRESS  
**Owner:** Developer  
**VE scope:** T170 (improved failure message); no new tests required for phase 1

---

### TASK-174 — M-DATATASK-PROGRESS phase 2: fetchWeather, fetchCrypto, fetchStockChart progress indicators

Extend the `volatile int8_t` progress pattern to three remaining fetch functions. Each uses phase values 0=TLS, 1=GET, 2=parse (stream-read for StockChart), -1=idle.

**Work items:**
1. `fetchWeather()` — `s_weatherFetchPhase`; expose as `get weatherFetchPhase`; update T_WX_05 failure path
2. `fetchCrypto()` — `s_cryptoFetchPhase`; expose as `get cryptoFetchPhase`; update T_CX_05 failure path
3. `fetchStockChart()` — `s_stockChartProgress`; expose as `get stockChartProgress`; update `_wait_chart_complete` failure path (affects T176, T185, T188, T192, T193, T194, T204, T-BUSY-01b, T-CDWN-02)

**Priority:** P2  
**Status:** done — 2026-06-12 (build clean, both envs)  
**Opened:** 2026-06-12  
**Design:** [M-DATATASK-PROGRESS.md](../architecture/designs/M-DATATASK-PROGRESS.md)  
**Milestone:** M-DATATASK-PROGRESS  
**Deps:** TASK-173  
**Owner:** Developer  
**VE scope:** improved failure messages on 10 existing tests; no new tests required

---

## Closed — TASK-169 + M-TELETEXT PoC (2026-06-13)

### TASK-169 — UX: auto-navigate to previous app after successful WiFi connect

After a successful WiFi connect in WifiSection (`_startConnect()` → RESULT state shows success), the user must navigate back manually. The device should automatically return to the app that was active before Settings was opened (or to the Spotify app if navigating from boot).

**Priority:** P2 — UX improvement; device is functional without it  
**Status:** done — 2026-06-12. 1.5 s auto-navigate after connect: `_navHomeAt` timer in `WifiSection::tick()` returns `SectionResult::NavigateHome`; SettingsApp dispatches to `switchApp(g_previousAppId)`. `tick()` base signature changed to `SectionResult` across all 6 section subclasses.  
**Opened:** 2026-06-11  
**Closed:** 2026-06-12  
**Deps:** TASK-168  
**Owner:** Developer

---

## Closed — M-TELETEXT firmware + VE prep (2026-06-13)

### TASK-175 — M-TELETEXT: preview iteration — right-strip nav + inline row links

Pre-firmware gate (per ADR-044). Implement two remaining UI elements in
`app/tools/preview_teletext.py` so the layout can be signed off before firmware:

1. **Right-strip nav** (35 × 200 px, right of the teletext grid): subpage ▲,
   current page number, prev ◄ / next ► page, subpage ▼. Arrows as coloured
   triangles; dim when target unavailable.
2. **Inline row-tap links**: tap in grid area → compute row + tap column → search
   for 3-digit page ref within ±3 cols of tap point → navigate. Works for both
   right-edge index layout (101, 601) and two-column layout (600, 800). Cyan tint
   rendered at actual ref column positions.
3. **History**: back navigation (10-entry ring; ◄◄ strip zone + keyboard Backspace).
4. **Keypad**: numeric page-entry overlay; page-number zone in strip triggers it.

**Signed off:** 2026-06-13 — human approval. All 7 checkpoints passed.
Link detection upgraded to tap-column model (conclusive fix, not whack-a-mole).

**Priority:** P1 — gates firmware start  
**Status:** closed — 2026-06-13  
**Opened:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** —

---

### TASK-176 — M-TELETEXT: confirm root CA for teletekst-data.nos.nl

Run `openssl s_client -connect teletekst-data.nos.nl:443 -showcerts` to identify
the root CA, extract the PEM, and add it to `dataTaskCerts.h` alongside the
existing ISRG Root X1 / GTS Root R4 entries.

**Priority:** P1 — gates firmware start  
**Status:** done — 2026-06-13. Chain confirmed: leaf → Sectigo Public Server
Authentication CA DV R36 → Sectigo Public Server Authentication Root R46 →
**USERTrust RSA Certification Authority** (self-signed root, 2010–2038). Not
DigiCert. PEM extracted. Add `TELETEXT_NOS_ROOT_CA` to `dataTaskCerts.h` as
part of TASK-177. DS-4 in M-TELETEXT.md updated (commit 8ed7be6).  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** —

---

### TASK-177 — M-TELETEXT: firmware implementation

Implement `TeletextApp` following ADR-044:

1. Add `Teletext` to `appRegistry.h` (slot 10, configurable=1); re-run codegen.
2. Extend `dataTask` with `FETCH_TELETEXT_PAGE`, `TeletextState` struct,
   `pollTeletext()` accessor, `enqueueTeletextPage(uint16_t page)`.
3. Add root CA (TASK-176) to `dataTaskCerts.h`.
4. `TeletextApp`: `init()`, `resume()` (reads settings), `tick()` (polls +
   renders), `handleInput()` (fast-text bar, right-strip, row-tap links, history).
5. Renderer: 6×8 cells, Font1 for text mode, `fillRect` for mosaic mode.
6. Extend `AppSettings` with `teletextPage`, `teletextPollSecs`,
   `teletextCountry`, `teletextAutoAdvance` (all four fields per ADR-044 item 6);
   add Settings UI rows under Applications → Teletext: start-page tap-cycle,
   poll-interval tap-cycle, country row (greyed-out, shows "NL (NOS)" only).
7. Source + bake teletext taskbar icons (TASK-179).
8. `run/check` clean.

**Priority:** P2  
**Status:** done — 2026-06-13. `TeletextApp` implemented in `app/src/teletextApp.h`.
`dataTask` extended with `DATA_FETCH_TELETEXT_PAGE`, `TeletextState`, `enqueueTeletextPage()`,
`pollTeletext()`, `lastTeletextHttpCode()`. USERTrust RSA root CA added to `dataTaskCerts.h`.
4 settings fields added; Settings UI rows for start-page, refresh, country (greyed).
`appRegistry.h` updated; codegen re-run; `golden.sha256` refreshed. All 5 `run/check` gates pass.  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** TASK-175 (preview sign-off), TASK-176 (root CA), TASK-179 (icons)

---

### TASK-178 — M-TELETEXT R&D spike: multi-country teletext API compatibility

Probe the wire format of active teletext services in AT, DE, SE, IT, FI to
determine which share the NOS format (ISO-8859-1, 25×40 `<pre>` block, same
control codes). Services to probe: ORF (AT), ARD/ZDF (DE), SVT (SE), RAI (IT),
YLE (FI). Write a short report to `docs/rnd/reports/`.
If at least one matches: propose a multi-country design. If none match: document
why and close the `teletextCountry` settings field as permanently inert.

**Priority:** P3 — future enhancement; does not block M-TELETEXT v1  
**Status:** done — 2026-06-13. EXP-004 filed at
`docs/rnd/reports/EXP-004-teletext-multi-country-spike.md` (commit 875bb32).
No service is drop-in compatible with NOS. SVT (SE) via texttv.nu JSON is the
viable second entry (separate JSON fetch path required). RAI incompatible
(PNG-only). ORF/ARD blocked on-device (need proxy). YLE gated (API key).
`teletextCountry` stays reserved; DS-6 in M-TELETEXT.md updated with full findings.  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT (future)  
**Owner:** R&D  
**Deps:** —

---

### TASK-180 — M-TELETEXT: serial debug accessors for TeletextApp [VE gap G1]

VE design review (2026-06-13) identified that without serial debug accessors, no
automated DUT tests for the Teletext app are possible. Required additions to the
`SERIAL_DEBUG` command surface (same pattern as `get weatherReady`, `get cryptoReady`,
`set triggerHeatmap 1`):

- `get teletextReady` → `{"ok":true,"ready":bool}` — true after first successful fetch
- `get teletextPage` → `{"ok":true,"page":uint16}` — current page in `TeletextState`
- `set teletextPage <N>` → `{"ok":true,"page":N}` — writes `g_settings.teletextPage` transiently
- `get teletextPollSecs` → `{"ok":true,"pollSecs":uint8}`
- `get teletextHttpCode` → last HTTP response code from `fetchTeletext()` (pattern from `get cryptoHttpCode`)
- `set triggerTeletextFetch 1` → force immediate `FETCH_TELETEXT_PAGE` enqueue

Must ship in the same commit as `dataTask::pollTeletext()`. T252–T253, T256–T265, T268 all block on this.

**Priority:** P1 — gates all automated DUT tests  
**Status:** done — 2026-06-13. All accessors implemented in `TeletextApp::dbgGet/dbgSet()`:
`get teletextReady`, `get teletextPage`, `set teletextPage <N>`, `get teletextPollSecs`,
`get teletextHttpCode`, `set triggerTeletextFetch 1`. Also includes TASK-188 expansions.  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** TASK-177

---

### TASK-181 — M-TELETEXT: publish pixel-exact touch zone constants [VE gap G2]

VE review found that touch zone coordinates in M-TELETEXT.md are approximate (e.g.,
right-strip y-values marked "y=50 approx"). The DUT tap harness requires pixel-exact
values before any tap test can be written.

Deliverable: a constants block (in `app/gen/teletext_layout.h` or equivalent, following
the `skin_layout.h` pattern) defining:
- Right-strip zone boundaries — values are firm from `preview_teletext.py` (no firmware
  needed to know these; only the Applications submenu order requires TASK-177):
  - `TTXT_STRIP_SUBUP_Y0=0`,  `TTXT_STRIP_SUBUP_Y1=33`
  - `TTXT_STRIP_PAGE_Y0=34`,  `TTXT_STRIP_PAGE_Y1=66`   (page num / keypad)
  - `TTXT_STRIP_BACK_Y0=67`,  `TTXT_STRIP_BACK_Y1=99`   (◄◄ back)
  - `TTXT_STRIP_PREV_Y0=100`, `TTXT_STRIP_PREV_Y1=132`
  - `TTXT_STRIP_NEXT_Y0=133`, `TTXT_STRIP_NEXT_Y1=165`
  - `TTXT_STRIP_SUBDN_Y0=166`,`TTXT_STRIP_SUBDN_Y1=199`
- Fast-text bar x-boundaries: `TTXT_FTL0_X0/X1` … `TTXT_FTL3_X0/X1`
- Fast-text bar y-range: `TTXT_BAR_Y0` (=200), `TTXT_BAR_Y1` (=239)
- Grid origin: `TTXT_GRID_X`, `TTXT_GRID_Y`, `TTXT_CHAR_W` (=6), `TTXT_CHAR_H` (=8)

Applications submenu row order must also be confirmed (Teletext is configurable=1;
VE must know the order to audit T-SET-03 / T-SET-07 regression risk — see TASK-177).

The strip zone header can be authored and committed **before** TASK-177 (values are
already known). Only the submenu-row section requires TASK-177 to be complete first.

**Priority:** P1 — gates all tap tests (T254–T262)  
**Status:** closed — 2026-06-13. Strip zone header written at `app/gen/teletext_layout.h`.
Submenu row coordinates remain TBD (comment in header, populated by TASK-177).  
**Opened:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** TASK-177 (submenu row order only — strip zone header can precede firmware)

---

### TASK-182 — M-TELETEXT: specify back-navigation mechanism [VE gap G3]

DS-2 (inline hyperlinks) describes a 10-entry page-history ring and enables back
navigation, but M-TELETEXT.md and ADR-044 do not specify the UI gesture for "go back."
The VE cannot write T261 (history back navigation) until the mechanism is designed.

Options: (a) dedicated back-button in the right-strip (replaces one of the 5 nav zones);
(b) long-press on current page number display; (c) swipe gesture; (d) fast-text button
if one target is always blank. Each has different tap-zone implications.

Architect to decide and update M-TELETEXT §DS-2 + ADR-044 item 5 with the chosen
mechanism. Once decided, Developer adds the zone to `teletext_layout.h` (TASK-181).

**Resolution:** Dedicated ◄◄ back zone (y=67..99) between page-number and prev-page.
All 6 strip zones evenly spaced (34/33/33/33/33/34 px). ◄◄ double-arrow distinguishes
back from single ◄ prev. Cyan tint when history available, dim otherwise.
Page-number zone (y=34..66) solely triggers keypad. Preview tool updated 2026-06-13.

**Priority:** P2 — blocks T261; does not block MVP render  
**Status:** closed — 2026-06-13  
**Opened:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Architect  
**Deps:** —

---

### TASK-183 — M-TELETEXT: set teletextPageContent debug stub [VE gap G4]

Inline row-link tests (T259–T260) are network-content-dependent: the correct
3-digit page reference must be at a known column/row in the fetched page. Using live
page 101 is fragile (NOS could change layout). Preferred approach: a
`set teletextPageContent "<blob>"` debug accessor that injects a synthetic 1000-byte
page into `TeletextState`, bypassing the network, so harness tests control the exact
content.

Blob format: 25 rows × 40 bytes, same encoding as the live `<pre>` block (ISO-8859-1,
control codes 0x01–0x17). The harness then taps a known row and asserts page navigation.

**Priority:** P2 — enables robust inline link tests without network dependency  
**Status:** done — 2026-06-13. Implemented as `set teletextPageContent <hex>` in
`TeletextApp::dbgSet()`. Blob encoding: contiguous 2000-char hex string (see TASK-189).
Injects directly into `_st.cells[25][40]`, sets `ready=true`, redraws.  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** TASK-180

---

### TASK-184 — M-TELETEXT: 300ms debounce serial accessor [VE gap G5]

T268 (debounce test) requires the app-level 300 ms debounce in `TeletextApp::handleInput()`
to be observable via serial. The existing `set cooldown <ms>` only arms the hardware
touch-screen gate — not the application-layer debounce.

Minimum: add `get teletextLastTapMs` (returns `millis()` of last accepted tap) so the
harness can assert that a second tap within 300 ms did not update the timestamp.
Alternatively: `set teletextDebounceMs <N>` to allow the harness to shrink the window
to 0 and verify the logic independently.

**Priority:** P3 — nice-to-have; T268 can remain [MANUAL] if not implemented  
**Status:** done — 2026-06-13. `get teletextLastTapMs` not implemented; `teletextLastAction`
(TASK-188 scope) provides equivalent observability for debounce testing. T268 remains [MANUAL].  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** TASK-180

---

### TASK-179 — M-TELETEXT: source teletext taskbar icons

Source or create `teletext.png` + `teletext_active.png` (24×24, RGBA) for the
taskbar slot. Style: consistent with existing icons (B&W inactive, coloured
active). Re-run `run/bake-icons`; update `golden.sha256`.

**Priority:** P2 — needed before DUT flash of TASK-177  
**Status:** closed — 2026-06-13. `teletext.png` + `teletext_active.png` (40×40 RGBA,
page-outline with 4 text-row lines) created in `app/icons/taskbar/`. Baked into
`app/gen/taskbar_icons.h/.cpp` at slot 9 (`AppId::Teletext`).  
**Opened:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** —

---

### TASK-185 — M-TELETEXT: accept ADR-044 (human sign-off)

ADR-044 is still "proposed." Firmware (TASK-177) begins against an unaccepted ADR.
Human operator reviews ADR-044 and promotes status to "accepted." Should happen at
the same time as TASK-175 preview sign-off — both are the same conversation.

**Priority:** P1 — gates firmware start  
**Status:** closed — 2026-06-13. ADR-044 accepted by human operator.  
**Opened:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Human → Architect  
**Deps:** TASK-175

---

### TASK-186 — M-TELETEXT: apply 4 architecture.md update triggers from ADR-044

ADR-044 Consequences lists four post-acceptance updates to `docs/architecture/architecture.md`:
1. Add `teletekst-data.nos.nl` / USERTrust RSA CA to the TLS endpoint inventory.
2. Document the `dataTask` pattern in the Data Flow section (currently Spotify-path only).
3. Note `dataTaskCerts.h` as the cert registry for all non-Spotify HTTPS endpoints.
4. Close the "TLS root CA for non-Spotify endpoints" open question with a reference to ADR-044.

**Priority:** P2  
**Status:** done — 2026-06-13  
**Opened:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Architect  
**Deps:** TASK-185

---

### TASK-187 — M-TELETEXT: add feature_inventory.yaml entry

`feature_inventory.yaml` has no M-TELETEXT entry. Per BP-005/BP-010, the feature
cannot be declared done at roadmap level without an inventory entry linking to test IDs.

Deliverable: add entry for M-TELETEXT with `test_ids: [T249..T271]` and correct
`status`, `milestone`, and `dependencies` fields.

**Priority:** P2  
**Status:** done — 2026-06-13. Entry `teletext-001` added to `feature_inventory.yaml`
with `test_ids: [T249..T271]`, status=implemented, all cross-features and dependencies listed.  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** VE  
**Deps:** TASK-177 (to confirm final test count)

---

### TASK-188 — M-TELETEXT: expand TASK-180 serial accessor scope

Three accessors required by tests are missing from TASK-180's defined list:
- `get teletextLastAction` — required by T254, T255, T271 (last strip/bar action taken)
- `get teletextHasSubpages` — required by T258 preconditions
- `get teletextSubpage` — required by T270 (subpage active-case test)

These must be added to the same commit as TASK-180. Update TASK-180 body to include
all three, then close this task.

**Priority:** P2 — blocks T258, T270, T271  
**Status:** done — 2026-06-13. All three added to `TeletextApp::dbgGet()`: `get teletextLastAction`,
`get teletextHasSubpages`, `get teletextSubpage`. Shipped in same commit as TASK-180.  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** TASK-177

---

### TASK-189 — M-TELETEXT: specify blob encoding for set teletextPageContent (TASK-183)

TASK-183 defines a `set teletextPageContent "<blob>"` debug accessor but does not
specify how the blob is encoded over the serial command channel. Raw bytes (some
non-printable, 0x01–0x17 control codes) cannot be passed as a plain string argument.

Decision needed before TASK-183 is implemented: raw bytes / hex-escaped / base64.
Recommendation: hex-encoded 1000-char string (`"01 02 20 ..."` or continuous
`"0102200720..."`) — matches existing debug patterns and is easy to generate in Python.
Document the chosen encoding in the TASK-183 body.

**Priority:** P2 — must be decided before TASK-183 implementation  
**Status:** done — 2026-06-13. **Decision: contiguous hex string, 2000 chars = 1000 bytes.**
Format: `set teletextPageContent "204e4f53..."` — 2 hex chars per byte, no spaces.
Matches existing debug patterns; easy to generate in Python with `bytes.hex()`.
Implemented in TASK-183 with this encoding.  
**Opened:** 2026-06-13  
**Closed:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** —

---

### TASK-190 — M-TELETEXT: NOS API stability canary script

The NOS Teletekst API (`teletekst-data.nos.nl/page/{N}`) is undocumented and
reverse-engineered. A format change would cause `TeletextApp` to silently render
garbage with no alert.

Deliverable: a host-side Python script (`run/check-teletext-api` or similar) that:
1. Fetches page 101.
2. Asserts response contains a `<pre>` block of exactly 1000 bytes.
3. Asserts at least one navigation metadata key (`pn=`) is present.
4. Exits non-zero on failure (can be wired into `run/check` or run independently).

**Priority:** P3  
**Status:** done — 2026-06-13  
**Opened:** 2026-06-13  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** —

---

### TASK-191 — M-TELETEXT: TLS heap contention test (spotifyTask + fetchTeletext concurrent)

ADR-044 item 9 defers to "revisit if TLS heap pressure testing reveals contention."
No test exercises simultaneous `spotifyTask` TLS session + `dataTask fetchTeletext()`
TLS spike. On-device: both can overlap if a teletext poll fires while Spotify is
actively streaming.

Deliverable: a DUT test that:
1. Starts Spotify playback (active TLS session in spotifyTask).
2. Forces an immediate `set triggerTeletextFetch 1`.
3. Asserts `get teletextReady` becomes true within 30 s (fetch completed without OOM/watchdog).
4. Asserts Spotify playback did not drop (monitor `lastPlaylistDraw`).

If the test reveals contention, apply `tlsYield()` / `tlsResume()` around
`fetchTeletext()` (same pattern as stock app).

**Priority:** P3  
**Status:** complete  
**Opened:** 2026-06-13  
**Closed:** 2026-06-14  
**Milestone:** M-TELETEXT  
**Owner:** Developer  
**Deps:** TASK-180

**Result:** T272 PASS. Two bugs found and fixed during implementation:
1. **TLS heap contention confirmed** — `fetchTeletext()` lacked `tlsYield()`/`tlsResume()`; debug build maxAlloc ~39–51k < 50k TLS floor. Fixed: `tlsYield()` before TLS alloc, `tlsResume()` after `http.end()`. ADR-044 item 9 revised.
2. **`_lastFetch=0` early-boot bug** — `init()`/`resume()`/`triggerTeletextFetch` set `_lastFetch=0`; when `millis()<pollSecs*1000` (first 60 s after boot), the poll condition `now-_lastFetch>=pollSecs*1000` was false, so no fetch was enqueued. Fixed via `_forceNow()` helper using unsigned underflow arithmetic.
3. **Null-byte parser bug** — NOS response body contains `\x00\x00` before `</pre>` (teletext control codes); `String::indexOf("</pre>")` (via `strstr`) stopped at the null, returning -1 → `no <pre> block`. Fixed: null-safe `memcmp` scan for `</pre>`.

---

## Closed — M-TELETEXT post-ship DUT fixes + QM retrospective (2026-06-14)

Three defects found in first manual DUT use after M-TELETEXT milestone close (LL-074/075/076).

### TASK-195 — M-TELETEXT post-ship: taskbar busy indicator + subpage nav + numpad

Three defects fixed in one session:

1. **Busy indicator not wired** — `TeletextApp` defaulted `hasPendingAsync()` to `false`. Fixed: override returns `_pendingFetch`. Also fixed latent double-enqueue: `_navigate()`/`_goBack()` now set `_pendingFetch=true` (not `false`) after direct-enqueue, so `tick()` correctly skips re-enqueue while a fetch is in flight. `touch-004` status updated to `implemented`. X016 added to cross_feature_matrix.yaml.
2. **Subpage navigation broken** — `parsePage("617-2")` via `atoi` returned `617`, dropping the `-2` sub-index. Every subpage tap re-navigated to page 617 subpage 1. Fixed: `parseSubpage()` helper extracts the dash-suffix; `TeletextState` gains `subpageNextSub`/`subpagePrevSub` fields; `enqueueTeletextPage(page, sub)` encodes sub in high nibble of `param0`; `fetchTeletext` builds URL as `617-2` when `sub>0`. `_handleStrip` SUBUP/SUBDN pass the sub index through `_navigate()`.
3. **Numpad not implemented** — strip PAGE zone cycled presets with a comment "not yet implemented." Fixed: tapping the page-number zone now opens a 3×4 digit-entry overlay (1-9 / DEL / 0 / GO). Auto-navigates on 3rd digit. Strip nav stays live during numpad; back button and fast-text tap dismiss it.

**Priority:** P1 (blocking DUT usability)
**Status:** closed — 2026-06-14
**Commits:** 728a278 (busy indicator), 3633cf6 (subpage nav + numpad)
**Opened:** 2026-06-14
**Closed:** 2026-06-14
**Milestone:** M-TELETEXT
**Owner:** Developer
**Deps:** —

---

### TASK-196 — QM retrospective: M-TELETEXT post-ship (LL-074/075/076 + BP-034/035/036)

QM retrospective on three post-ship defects. LL-074/075/076 filed and adopted. BP-034/035/036 promoted with human sign-off.

**Priority:** P2
**Status:** closed — 2026-06-14
**Commits:** 8f071be (retrospective), 1bb0420 (BP sign-off)
**Opened:** 2026-06-14
**Closed:** 2026-06-14
**Owner:** QM
**Deps:** TASK-195

---

## Closed — M-TELETEXT TASK-197 synthetic tests + busy fix (2026-06-14)

### TASK-197 — M-TELETEXT: synthetic injection path for T270 (subpage nav) and T271 (numpad boundary)

Per BP-034 (LL-074): blocked tests with no synthetic fallback are coverage gaps. T270 (subpage ▲/▼ active when subpages present) and T271 (numpad boundary px check) are both blocked `[NETWORK][G1,G2]` with no injection alternative.

Deliverables:

1. **T270 synthetic variant** — Use `set teletextPageContent <hex>` to inject a page body that contains `pn=ns617-2` and `pn=ps617-1` metadata headers. Tap SUBDN zone; assert `get teletextPage` changes and `get teletextSubpage` next/prev values update. This tests the subpage parse + navigate path without live network.

2. **T271 harness implementation** — Now that `get teletextLastAction` is available (TASK-188) and numpad is implemented, T271's boundary checks (`tap 257 66` → `STRIP_PAGE`, `tap 257 67` → `STRIP_BACK`) can be automated. Update T271 status from `planned` to harness-runnable; add to `run_serialdbg_tests.py`.

**Priority:** P2 — closes BP-034 gap for teletext
**Status:** open
**Opened:** 2026-06-14
**Milestone:** M-TELETEXT (VE follow-up)
**Owner:** VE + Developer
**Deps:** TASK-183 (injection accessor — done), TASK-181 (layout constants — done), TASK-188 (lastAction accessor — done)

---

### TASK-198 — Developer: new-app cross-cutting integration checklist (BP-036)

Per BP-036 (LL-076): when a new app is registered, Developer must verify it satisfies all active cross-cutting shell integrations. Currently this check is implicit and untracked.

Deliverable: a short checklist block added to `docs/architecture/designs/` (or as a comment block in `appRegistry.h`) listing required per-app integrations:

1. `hasPendingAsync()` — override if app enqueues async work from `handleInput()`
2. `tlsYield()`/`tlsResume()` — required for any new dataTask HTTPS fetcher (BP-031)
3. Serial debug `dbgGet`/`dbgSet` surface for VE testability (BP implicit from LL-060)

Checklist must be referenced at milestone close for any future app additions.

**Priority:** P3 — process hygiene; no new app is pending
**Status:** done — `docs/architecture/designs/NEW-APP-CHECKLIST.md` created; pointer comment added to `appRegistry.h` (2026-06-14)
**Opened:** 2026-06-14
**Owner:** Developer / Architect
**Deps:** —
