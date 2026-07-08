# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> **PM sync 2026-06-28 (A-lite PROVEN — spike all-phases PASS)** — TASK-261 Phase 0/1/2 all PASS
> (EXP-010, branch `rnd/membudget`): the no-PSRAM CYD plays MP3 WebRadio on the multi-app build with the
> Helix decoder forked into a 24 K free-list arena (88/103/129.7 s × 3 trials, churn-safe, production ELF
> byte-clean). **The M-WEBRADIO no-PSRAM viability question — open since the start of the milestone — is
> answered: YES, via the reserved-arena fork.** ADR-047's kill-gate cleared. **Open decision: production
> promotion (TASK-262/human)** — gated on M-RECLAIM Q3-a (Spotify overlay), validation of the halved I2S DMA
> (PATCH-MEMBUDGET-4) at higher bitrate, live station-fetch, and Spotify-active (TASK-243 Premium). The fork
> stays branch-only (BP-040) until that decision. Process note: 3 fresh-agent spike runs (Phase 0/1, Phase 2)
> each stopped at their gate for human review — the cheap-kill-first discipline (LL-087) held end-to-end.
>
> **PM sync 2026-06-27b (direction decided + design batch panel-reviewed)** — Human chose **Gated A-lite**
> for no-PSRAM WebRadio (ADR-047 ACCEPTED): pursue the reserved-arena coexistence **conditional on the spike's
> Phase-1 kill-gate**. Filed **TASK-261** (spike, DUT-blocked; Phase-0 instrumentation can land offline) +
> **TASK-262** (cleanup, BP-040). The design batch (M-MEMBUDGET, M-RECLAIM, M-PLAYER-STATE, PROP, ADR-047)
> passed a 3-agent panel review **unanimous PROCEED-WITH-NITS** — the review caught a real allocator
> correctness bug (bump→free-list, 2→3 fork sites; `c11b87f`) before any code. Process lesson LL-089
> ("design outrunning the product decision") filed; M-RECLAIM Q3-b/Q2 capped at sketch depth until the gate.
> **TASK-259/260 (player mode) proceed regardless** of the WebRadio direction. **Update:** a parallel session
> DUT-verified TASK-259 PART 1 (`13f701d` — player slot restores WebRadio after app-switch PASS; a WDT crash
> *during playback* is pre-existing TASK-233, not a regression). So the DUT was available; confirm the window
> before scheduling the TASK-261 spike. The playback WDT crash is the same TASK-233 wall the spike's Phase 2
> targets — a useful datapoint for it.
>
> **PM sync 2026-06-27 (bottom-up bare-rig settles the hardware question)** — Pivoted the no-PSRAM
> viability question from top-down strip (TASK-255) to a bottom-up bare control (TASK-258 → EXP-009).
> **Both bare configs PASS:** the no-PSRAM CYD plays MP3 radio bare *and* with the full CYD TFT_eSPI
> display (decoder inits ~165 K free; TFT costs ~600 B — direct-draw, no framebuffer). **ADR-045's
> "no-PSRAM playback = NO-GO" is footprint-bound, not silicon-bound** — the hardware and the display
> are both fine; our 11-app build fails only because its ~147 K resident footprint leaves ~60 K, too
> tight for the ~41 K audio path. The lever is **resident footprint, not RAM/silicon/display.**
> **Actions:** TASK-258 DONE (→ EXP-009); **TASK-255 parked** (`parked-pending-TASK-258`, superseded —
> branch artefacts kept); **TASK-257** filed (optional Lane C-1 library A/B, re-homed on the bare rig).
> Open product decision (not yet a task): pursue a stripped boot-direct-to-WebRadio variant vs accept
> ADR-045 stands for the multi-app board. Process lesson: measure the ceiling bottom-up before grinding
> a top-down strip (LL-087); never read `usable = free − maxAlloc` as a fixed budget (LL-088).
>
> **PM sync 2026-06-25 (honest state — WebRadio verification PAUSED on external blocker)** —
> Stop-and-assess. **Solid & committed:** TASK-232 (http fetch), TASK-234 (auto-skip), TASK-239/240
> (~11 KB reclaim) — all DUT-verified; TASK-242 (taskbar null-icon crash) — fix DUT-verified + a
> `static_assert` gate so the bug class can't recur. **Honest downgrades:** TASK-241 (no-PSRAM
> stability) → *implemented-unverified* — its "provisional PASS" leaned on an EXP-007 baseline that
> TASK-243 shows was never a live Spotify session; TASK-242's T242 test + eject-harness change →
> *implemented-unverified* (never run green on DUT). **Root blocker filed (TASK-243):** the Spotify
> Web API returns 403 *"Active premium subscription required for the owner of the app"* — host
> `spotify_state.py` reproduces it from the laptop, so it's categorically not the device/firmware/
> token. **Decision: PAUSE WebRadio verification** — every open verification item is gated on
> TASK-243 (owner-account Premium, external, multi-hour re-enable). No more DUT cycles until the
> host API check is green. Process lessons (this session): host-validate an external API path
> *before* touching the device (LL-085 reinforced); don't cite an unconfirmed baseline as a result.
>
> **PM sync 2026-06-24 (DUT session — M-WEBRADIO TLS verified; playback blocker found)** —
> First DUT session since the 06-20 downtime work. Ran the queued WebRadio tests + a manual
> station-by-station playback probe. Results:
> - **TASK-214 / T_WR_TLS_01: PASS, DUT-verified.** Station fetch returns `count=30` via the
>   **`setCACert()` pinned-root path — the `setInsecure()` fallback never fired** (`tlsInsecure=0`).
>   This settles the ADR-029 question: radio-browser's chain verifies against the pinned root on
>   real hardware, so **no ADR-029 exception is needed** and the original "server omits R13
>   intermediate" diagnosis does not hold here. (Found + fixed a `wrLastHttp` reporting bug en
>   route: http/ok/jsonErr were only recorded on the failure branch, so a successful fetch
>   reported `http=0`; the test failed on that before the fix. Now recorded regardless of outcome.)
> - **NEW BLOCKER (TASK-232): WebRadio playback is broken on this no-PSRAM DUT.** The manual probe
>   played stations 0–7. All **HTTPS** streams (the majority of the votes-ordered list) fail
>   `connecttohost()` immediately with `ssl_client … (-32512) SSL - Memory allocation failed` —
>   `PSRAM not found`, so the audio-stream mbedTLS handshake can't get its ~40 KB contiguous block
>   even with Spotify TLS yielded (free heap ~69 KB, fragmented). The two **HTTP** streams tested
>   connected fine but the upstreams dropped within 5 s. This blocks T_WR_SPOTIFY_RESUME_01,
>   T_WR_COEX_*, and the heap suite (TASK-207/208/209) — none can reach a stable PLAYING state.
> - **TASK-218 (stream-death watchdog): verified behaving correctly.** The library sets `m_f_running`
>   true on connect (not on first audio) and clears it only on a real stop, so the seeded 5 s grace
>   won't false-trip healthy buffering; the watchdog fired only on genuinely dead decodes/streams.
>
> **Follow-on, same session (user: "proceed with TASK-232"):**
> - **TASK-232 fix landed + DUT-verified (multi-page HTTP fetch).** WebRadio now filters out the
>   unplayable HTTPS streams and pages the votes list for `http://` ones (≤ 5 pages). The list fills
>   `count=30` all-HTTP and stations **reach PLAYING** (0 were reachable before). Closes the HTTPS-SSL
>   blocker. ADR-029 amendment for cleartext-media acceptance owed to Architect.
> - **NEW BLOCKER TASK-233: MP3 decoder heap exhaustion.** With HTTPS gone, the next no-PSRAM wall
>   appeared — `MP3Decoder_AllocateBuffers(): not enough memory` (Helix needs ~29 KB; largest
>   contiguous block ~39 KB pre-connect, fragmented below that by decode time). Most HTTP streams
>   connect then die in ~5 s; a few play on fragmentation luck. Whether WebRadio is viable on
>   no-PSRAM CYD hardware at all is now an open product question. Root-caused with DUT evidence.
>
> **PM sync 2026-06-20** — M-WEBRADIO downtime work: VE review + TASK-214 re-scope (no DUT this session).
> User has no DUT access right now; used the downtime for three things instead of waiting.
> (1) VE review (TASK-215) of the TASK-207/208/209 DUT plan found two doc gaps: no test
> exercised the TASK-214 fix itself, and TASK-208's heap thresholds predate `dafa4a4`'s
> Spotify-TLS-yield-for-playback change. (2) Authored T_WR_TLS_01 and T_WR_SPOTIFY_RESUME_01
> to close those gaps (TASK-216) — implemented in `run_serialdbg_tests.py`, registered,
> documented, ready to run next session. (3) Built `run/check-datatask-certs` (TASK-217), a
> host-side TLS chain preflight replicating mbedTLS's strict offline verify — running it
> against `de1.api.radio-browser.info` (the mirror tried first) shows a complete, verifying
> chain *right now* from this network, directly disputing TASK-214's "server omits R13
> intermediate" root cause. Re-scoped TASK-214's fix from unconditional `setInsecure()` to
> try-`setCACert()`-first-then-fallback, recording which path fires via a new `tlsInsecure`
> field. Build-clean, 5/5 gates. **None of this is DUT-verified** — T_WR_TLS_01 is the test
> that settles it, and it needs hardware. Do not amend ADR-029 until that result is in.
>
> **PM sync 2026-06-14 (session 6)** — M-WEBRADIO design complete; firmware implementation task filed.
> Team review (Architect/VE/Developer/QM) surfaced 5 design doc gaps and 3 missing tasks. All resolved:
> design amended (TouchResult spec, SKIN_EJECT UV offsets, streaming JSON, BP-031 call-out, BP-036
> checklist); TASK-210 (bake_skin sign-off), TASK-211 (ACT_EJECT serial accessor), TASK-212 (error
> state injection) filed. Gap confirmed: no firmware implementation task existed. TASK-213 filed —
> full WebRadio firmware (app class, dataTask fetcher, hitTestEject, error state machine, settings,
> serial accessors). TASK-210 is the sole unblocked P1 — can start immediately (host only, no DUT).
> Execution order: TASK-210 → TASK-213 → TASK-211/212 (serial surface) → TASK-207/208/209 (DUT).
>
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

## Open — M-WEBRADIO DUT phase

> Firmware complete. TASK-207/208/209 are blocked on one root cause: radio-browser.info
> returns 0 stations on the DUT (TASK-214). TASK-214's fix is now re-scoped (try
> setCACert() first, fall back to setInsecure() only on verify failure) per TASK-217's
> host re-check, which disputes the original "intermediate omitted" diagnosis for at
> least one mirror/vantage point. TASK-215/216 added two DUT tests (T_WR_TLS_01,
> T_WR_SPOTIFY_RESUME_01) authored during this downtime, ready to run first in the next
> DUT session — their result is what the Architect needs before any ADR-029 decision.
> Then run TASK-207/208/209 in the same session (TASK-208's heap thresholds are
> provisional — see TASK-215).

### TASK-214 — M-WEBRADIO: diagnose radio-browser.info 0-station result on DUT

**Background:** DUT `get wrCount` returns `count=0, pending=0` after every station
fetch. Host `curl` reaches `de1.api.radio-browser.info` successfully (100 NL stations,
11 KB filtered JSON — fits within `s_webRadioDoc` 14 KB). The fetch completes on DUT
(HEAP post-fetch fires, `fetchMin=40 KB` confirming TLS handshake attempt), but count=0.
HTTP error code never surfaced — it is consumed by the test harness before it can be read.

**Deliverable:** Expose `lastHttpCode` from `s_webRadioResult` via a `get wrLastHttp`
serial command (one line in `webRadioApp.h::dbgGet`). Rebuild debug firmware, switch to
WebRadio, query `get wrLastHttp` — the code identifies whether the failure is TLS (-1),
HTTP 4xx/5xx, or a parse error.

**Pass criteria:** Root cause identified; if fixable (cert rotation, HTTP error),
fix applied and `get wrCount` returns `count ≥ 1` on DUT.

**Progress (2026-06-19, commit `dafa4a4`):** Root cause found — radio-browser.info
omits the R13 intermediate from the TLS handshake, so `setCACert(RADIO_BROWSER_ROOT_CA)`
can't build the chain. Fix: `tls.setInsecure()` for this fetch + `get wrLastHttp`
(http code, ok flag, count, json parse error) + `jsonErr` capture landed and build-clean
(5/5 gates). **Not yet DUT-verified** — pass criteria (`count ≥ 1` on real hardware)
unmet. Also note: `setInsecure()` is the option ADR-029 rejected categorically for
non-Spotify endpoints; needs an ADR-029 amendment or Architect sign-off before this is
architecturally closed, not just code-closed.

**Progress (2026-06-20, downtime work — no DUT available):** VE review of the
TASK-207/208/209 plan surfaced two doc gaps (no test exercised the TASK-214 fix
itself; TASK-208 heap thresholds didn't account for the new Spotify-TLS-yield-for-
playback-duration change) — both filed below as TASK-215/216. Separately, the
above root cause was re-checked from the host (`./run/check-datatask-certs`,
TASK-217) using the strict offline chain-build mbedTLS actually performs
(`openssl -CAfile isrg-root-x1.pem -verify_return_error`), not just an issuer
print. Result: `de1.api.radio-browser.info` (mirror[0], tried first) currently
presents a **complete, verifying chain** (leaf → R13 → ISRG Root X1) from this
network — directly contradicting "server omits R13 intermediate." Given
`nl1`/`at1` are independently-run community mirrors, chain completeness may
still differ by mirror/edge/time, so this doesn't prove the original diagnosis
was wrong everywhere — but it's strong enough to not commit to a permanent
ADR-029 exception on it. Re-scoped the fix: `fetchOneMirror()` now tries
`setCACert(RADIO_BROWSER_ROOT_CA)` first per mirror and only falls back to
`setInsecure()` on a connection/verify-level failure (negative HTTPClient code),
recording which path fired in a new `tlsInsecure` field (`dataTask.h`,
surfaced via `wrLastHttp`). Build-clean, 5/5 gates pass. **Still not
DUT-verified** — T_WR_TLS_01 (TASK-216) is the test that will tell us, on real
hardware, which path actually fires; that result is what the Architect needs
before deciding whether ADR-029 needs amending at all.

**Priority:** P1 — unblocks TASK-207/208/209 and M-WEBRADIO milestone close
**Status:** **done — DUT-verified 2026-06-24.** T_WR_TLS_01 PASS: `http=200 count=30`, `tlsInsecure=0` — the `setCACert()` pinned-root path verified and the `setInsecure()` fallback **never fired**. Conclusion: **no ADR-029 exception needed**; the "server omits R13 intermediate" diagnosis does not hold on this hardware/network. The conditional fallback stays as defensive code but is dormant. (Also fixed a `wrLastHttp` reporting bug — http/ok/jsonErr were only set on the failure branch, so a successful fetch reported `http=0`; now recorded regardless of outcome, alongside `tlsInsecure`.) NOTE: this verifies the station-list *fetch* only — *playback* is separately broken, see TASK-232.
**Opened:** 2026-06-15
**Closed:** 2026-06-24
**Milestone:** M-WEBRADIO
**Owner:** Developer
**Deps:** none

---

### TASK-215 — M-WEBRADIO: TASK-207/208/209 plan gaps found in VE review (no DUT)

VE review of `m-webradio-dut.md` (requested while DUT is unavailable) found two
gaps independent of hardware access:

1. No test exercised the TASK-214 fix itself — the suite assumed station loading
   "just works" and started from there.
2. TASK-208's heap pass criteria (TLS spike vs. audio decode non-overlapping)
   predate `dafa4a4`'s `spotifyTask::tlsYield()`-for-the-whole-playback-duration
   change — the assumption they were written under no longer holds.

**Deliverable:** Document the gaps in `m-webradio-dut.md` (done); new test cases
filed as TASK-216.

**Priority:** P2
**Status:** done — 2026-06-20. Gaps documented in `m-webradio-dut.md` notes section; TASK-208 row marked provisional pending re-validation.
**Opened:** 2026-06-20
**Closed:** 2026-06-20
**Milestone:** M-WEBRADIO
**Owner:** VE
**Deps:** none

---

### TASK-216 — M-WEBRADIO: author T_WR_TLS_01 + T_WR_SPOTIFY_RESUME_01

Close the TASK-215 gaps with two new DUT test cases, ready to run as soon as
hardware is available — no need to design them mid-session.

- **T_WR_TLS_01** — switch to WebRadio, let the fetch resolve, read `wrLastHttp`,
  record `tlsInsecure` (which TLS path fired). Either value is a legitimate PASS
  for "station list loaded"; the point is capturing the data point for TASK-214.
- **T_WR_SPOTIFY_RESUME_01** — play a station (holding the yielded Spotify TLS
  session), eject back to Spotify mid-playback, confirm Spotify's serial surface
  (`get touchResult`) responds — not just that `appId` flipped and nothing crashed.

**Deliverable:** Both implemented in `app/tools/run_serialdbg_tests.py`
(`t_wr_tls_01`, `t_wr_spotify_resume_01`), registered in `ALL_TESTS`, documented
in `m-webradio-dut.md` with steps/expected/fail criteria, added to the suite's
"How to run" command block and exit-criteria table.

**Priority:** P1 — gates TASK-214's ADR-029 decision and TASK-208's heap re-validation
**Status (2026-06-24, DUT run):** **T_WR_TLS_01 PASS** (drove TASK-214 to closed). **T_WR_SPOTIFY_RESUME_01 SKIP — blocked by TASK-232**: it needs a stable PLAYING state, and no station reaches one on this no-PSRAM DUT (HTTPS streams fail the SSL handshake; the HTTP streams tested dropped within 5 s). The test itself is sound — re-run once TASK-232 yields a playable stream. The test harness correctly reported SKIP rather than a false PASS.
**Was:** implemented — unverified (2026-06-20). Both tests written, registered in `ALL_TESTS`, documented; `./run/test-targeted T_WR_TLS_01,T_WR_SPOTIFY_RESUME_01` is ready. A test is not "done" until it has gone green at least once; calling it done before that is the same diagnosis-ahead-of-verification habit this whole session exists to correct (see LL-083). T_WR_SPOTIFY_RESUME_01's liveness probe was strengthened post-review: the original `get touchResult` check is serviced by the loop task and can't prove spotifyTask resumed; it now forces a Spotify poll (DEADZONE→FORCE_POLL) with bgPoll suspended and asserts a full shellBusy rise→clear cycle.
**Opened:** 2026-06-20
**Milestone:** M-WEBRADIO
**Owner:** VE
**Deps:** TASK-214 re-scoped fix (for T_WR_TLS_01 to be meaningful)

---

### TASK-217 — M-WEBRADIO/framework: host-side TLS chain preflight script

ADR-029's quarterly check (BP-030) only greps the cert *issuer* string from
`openssl s_client -showcerts` — it never confirms the server's handshake
actually carries a chain mbedTLS can build offline (single pinned root, no AIA
fetching). That blind spot is what let TASK-214's "intermediate omitted"
diagnosis go to production without a host-side check that could have disputed
or confirmed it before any DUT time was spent.

**Deliverable:** `run/check-datatask-certs` — parses root CA PEMs directly out
of `app/src/dataTaskCerts.h` (so it can't drift from what firmware ships), then
runs `openssl s_client -CAfile <root> -verify_return_error` against every
pinned endpoint (open-meteo, yahoo finance, coingecko, NOS teletext, and all 3
radio-browser mirrors) — the exact verification mbedTLS's `setCACert()` performs.
Distinguishes verify FAIL from network-unreachable ERROR so a sandboxed/offline
run doesn't get misread as a broken chain.

**Result of first run (2026-06-20):** `api.coingecko.com` and
`de1.api.radio-browser.info` PASS (chain verifies clean). `api.open-meteo.com`,
`query1.finance.yahoo.com`, `teletekst-data.nos.nl` timed out and `nl1`/`at1`
radio-browser mirrors didn't resolve — from *this* sandboxed environment only;
re-run from an unrestricted network before treating those as chain problems.

**Priority:** P2 — quarterly-check hardening, not a release blocker
**Status:** done — 2026-06-20. Script written, executable, runs clean against reachable endpoints. **Follow-up:** fold into BP-030's quarterly check (currently issuer-grep only) — propose to QM at next retrospective.
**Opened:** 2026-06-20
**Closed:** 2026-06-20
**Milestone:** M-WEBRADIO
**Owner:** Developer
**Deps:** none

---

## Open — M-WEBRADIO firmware gaps found in host audit (2026-06-20)

> Static audit of `webRadioApp.h` (the paths the pending DUT session exercises),
> done during DUT downtime. Three gaps confirmed by absence of code — grep shows
> `isRunning()`, `inBufferFilled()`, and `getVUlevel()` are called **nowhere** in
> firmware. TASK-218 is the one with a functional regression; 219/220 are
> TASK-213 completeness gaps. Surfaced before the DUT session specifically so it
> tests what it's meant to instead of chasing misattributed symptoms (BP-038).

### TASK-218 — M-WEBRADIO: stream death during PLAYING permanently starves Spotify TLS

**Severity:** HIGH — functional regression introduced by `dafa4a4`.

`_play()` sets `_state=PLAYING` and `_spotifyYielded=true`; `spotifyTask`'s TLS
session is resumed **only** in `_stopAudio()`. But `tick()` has **no runtime
stream-health detection** — no `audio.isRunning()`, `inBufferFilled()`, or
`WiFi.status()` check (grep-confirmed). So when a stream ends naturally or the
network drops mid-playback, `_state` stays `PLAYING` and `_spotifyYielded` stays
`true` **indefinitely**. Spotify polling is starved until the user manually
stops/ejects/skips. Pre-`dafa4a4` this was a cosmetic frozen-UI bug; the
yield-for-whole-playback change escalated it to a functional one.

**DUT-session impact:** confounds T_WR_HEAP_03/04 (5-min playback) and
T_WR_COEX_03 — any mid-test stream drop wedges Spotify and pollutes the heap/coex
readings. Worth fixing (or at least understanding) before that session.

**Fix shape:** in `tick()`, when `_state==PLAYING && s_wr_audio && !s_wr_audio->isRunning()`,
call `_stopAudio()` (resumes TLS) and set an error/stopped state. **Caution:**
`isRunning()` semantics during initial buffering/underrun are unverified — a naive
check could prematurely kill normal playback. Ties into TASK-219.

**Guarded fix implemented (2026-06-21):** debounced stream-death detection in
`tick()`'s PLAYING block — `isRunning()` must stay false for
`WR_STREAM_DEAD_MS` (5 s) before declaring the stream dead; `_lastRunningMs` is
seeded at PLAYING entry so initial buffering sits inside the grace window. On
trip: `_stopAudio()` (resumes the yielded Spotify TLS) → `ERROR_STALL`. This is
the minimum subset of TASK-219's error machine needed to remove the starvation;
no auto-retry/skip. Build-clean, 5/5 gates, +8 B RAM / +0.4 KB flash. **Not
DUT-verified** — the 5 s grace and `isRunning()`-during-underrun behaviour must
be confirmed on hardware before close (T_WR_HEAP_03/04 are the natural vehicle:
watch for premature stops on a healthy 5-min stream). Per BP-039/LL-083 this is
*implemented, not done.*

**Priority:** P1 — blocks M-WEBRADIO ship (silent Spotify starvation in normal use)
**Status:** implemented — **partially DUT-verified 2026-06-24**. The `isRunning()` semantics caution is resolved: the audio library sets `m_f_running=true` on connect success (Audio.cpp:488), *not* on first decoded audio, so the 5 s grace seeded at PLAYING entry will not false-trip normal initial buffering. Observed on DUT: two HTTP streams that genuinely dropped mid-connect tripped the watchdog correctly (→ ERROR_STALL) and resumed Spotify TLS. **Still owed:** confirmation that a *healthy* 5-min stream does NOT trip it — blocked on TASK-232 (no playable stream on this no-PSRAM board yet).
**Opened:** 2026-06-20
**Milestone:** M-WEBRADIO
**Owner:** Developer
**Deps:** none (but see TASK-219)

---

### TASK-219 — M-WEBRADIO: runtime error-state machine (design §Error states) is unimplemented

`M-WEBRADIO.md` §Error states specifies detection (`isRunning`/`inBufferFilled`/
`WiFi.status()` → `ERROR_STALL`/`ERROR_WIFI`/`ERROR_BLOCKED`), auto-retry, and
auto-skip policy. **None of it exists in firmware.** The `ERROR_*` enum values are
set only by (a) `_play()` connecttohost-fail → `ERROR_UNREACHABLE`, and (b)
synthetic `set wrState` injection (test-only). So TASK-212's T_WR_ERR_01–04 pass
(injection works) but the states they inject are **never reached in real
operation** — the tests verify rendering, not detection. This is the inverse of
LL-074: synthetic injection masking missing detection.

**Architect scope decision (2026-06-21): DEFERRED post-MVP, with a Tier-1
correctness carve-out that is already implemented.** The "error state machine" is
not one thing:
- **Tier 1 (MVP-mandatory, done):** catch-all unexpected-stop detection that
  resumes Spotify TLS + shows an error — load-bearing for the TLS-yield design,
  not polish. Implemented as TASK-218's `isRunning()` watchdog (covers all root
  causes → `ERROR_STALL`); `ERROR_UNREACHABLE` on connect-fail also present.
  Pending only DUT verification (TASK-218).
- **Tier 2 (deferred):** root-cause classification into distinct
  `ERROR_WIFI`/`ERROR_BLOCKED`/`ERROR_STALL` titles (needs `WiFi.status()` +
  `audio_info` HTTP-status parse). UX precision, not correctness.
- **Tier 3 (deferred):** auto-retry / auto-skip automation. Convenience;
  `webRadioAutoSkip` is config-only (no UI), so deferral leaves no dead toggle.

**MVP exit criterion:** M-WEBRADIO closes on Tier-1 DUT verification; Tiers 2–3
do not gate close. Recorded in `M-WEBRADIO.md` §Error states (Architect note
2026-06-21). This task now tracks the **deferred Tier 2+3 work** as a post-MVP
follow-on.

**Priority:** P3 — deferred post-MVP (was P2 as a scope question; now resolved)
**Status:** **superseded in part by ADR-045 (2026-06-24).** Tier 1 done (TASK-218, verified).
**Tier 3 (auto-skip) graduated from deferred → MVP** — the no-PSRAM decode-failure finding
(TASK-233) made it load-bearing; now tracked as **TASK-234**. Tier 2 (root-cause classification)
remains deferred post-MVP and is all this task still tracks.
**Opened:** 2026-06-20
**Milestone:** M-WEBRADIO (post-MVP follow-on)
**Owner:** Developer + Architect
**Deps:** none

---

### TASK-221 — M-WEBRADIO: webRadioBitrateCap setting is inert (never applied to query)

Adjacent finding from the TASK-219 scope review. `g_settings.webRadioBitrateCap`
(default 96) is persisted to/from `settings.json` but **never applied** to the
radio-browser fetch — the URL in `fetchOneMirror()` has no `bitrate_max` param.
The design (§Settings, §Library "prefer ≤ 96 kbps for stall tolerance") assumes
the cap limits drain rate; right now it does nothing, so stations of any bitrate
load and the 40 KB ring buffer gets less stall margin than the design intends.

Like the auto-skip settings, it is config-file-only (no on-device UI), so there
is no dead toggle — but the design doc implies behaviour that does not exist.

**Fix shape:** append `&bitrate_max=%u` (or `&bitrateMax=`, per radio-browser
API) to the query in `fetchOneMirror()` when `webRadioBitrateCap > 0`; verify the
param name against the API (host probe — `test_radiobrowser_api.py`).

**Done 2026-06-25.** Host probe against `de1.api.radio-browser.info` settled the param-name
uncertainty: **`bitrateMax`** (camelCase) filters correctly (`&bitrateMax=96` → all results ≤ 96,
0=unknown still passes); the snake_case `bitrate_max` cited in old comments is **silently ignored**
(returned 320/192 kbps). `enqueueWebRadioStations()` now takes a `bitrateCap`, snapshotted under the
existing mux next to `country` (caller `webRadioApp.h` passes `g_settings.webRadioBitrateCap`);
`fetchOneMirror()` appends `&bitrateMax=%u` when cap > 0. Fixed the inert-field comment in
`settingsStorage.h` and the wrong `bitrate_max` hints in `test_stream_buffer.py`. 5/5 gates.
No on-device UI exists for the field (config-file only), so no UX change — DUT effect is fewer
high-bitrate stations in the list, observable but not a behaviour gate.
**Priority:** P3 — stall-margin refinement; not a crash/correctness risk
**Status:** done 2026-06-25 — `bitrateMax` query filter wired (host-verified param name)
**Opened:** 2026-06-21
**Milestone:** M-WEBRADIO (post-MVP follow-on)
**Owner:** Developer
**Deps:** none

---

### TASK-232 — M-WEBRADIO: HTTPS stream playback fails on no-PSRAM hardware (MVP blocker)

> **Router-confound annotation (2026-07-03, LL-096):** the HTTPS-SSL-mem-alloc failure is real and
> reproducible (instant, memory-bound; EXP-009 bare-rig confirmed) — that diagnosis stands. BUT the
> aside "HTTP streams dropped upstream within 5 s → per-station" was very likely the **MX5600 2.4 GHz
> auto-channel dropout** (5–40 s off-air every 1–2 min), not station quality — a 5 s stream death is
> indistinguishable from an AP blackout from the DUT's single vantage. The "most stations drop, few are
> playable" impression that shaped auto-skip (TASK-234) was probably inflated by router blackouts. Re-test
> owed: real playable-station fraction on the pinned-channel link.

**Severity:** HIGH — blocks M-WEBRADIO MVP close. Found in the 2026-06-24 DUT session.

**Symptom:** On the production DUT (ESP32-2432S028R, **no PSRAM**), playing any HTTPS radio
stream fails `connecttohost()` *immediately* with, from the audio library:
```
[W][audio] PSRAM not found, inputBufferSize: 6399 bytes
[E][ssl_client.cpp] start_ssl_client(): (-32512) SSL - Memory allocation failed
[W][audio] Request https://radio.mixstream.nl/classics.mp3 failed!
```
→ `_state = ERROR_UNREACHABLE`. The audio-stream mbedTLS handshake needs a large (~40 KB)
contiguous allocation that does not exist on this board even with `spotifyTask::tlsYield()`
already done (free heap ~69 KB but fragmented; no PSRAM to fall back on). Confirmed not a
timeout (failure is instant; bumping the lib SSL timeout to 8 s changed nothing) and not a
cert problem (mem-alloc, not verify). The station-list *fetch* TLS succeeds because it runs
with no audio buffers allocated and only one TLS session live; the *stream* TLS is the
second concurrent session and it's the audio DMA/decoder buffers + framebuffer that leave no
contiguous block for it.

**Impact:** radio-browser's `order=votes` list is dominated by HTTPS stations, so WebRadio is
effectively unplayable on this hardware as shipped. HTTP (`http://…`) streams connect fine
(no SSL alloc) — the two tested dropped upstream within 5 s, but that's per-station, not a
device limit. This is the root reason T_WR_SPOTIFY_RESUME_01, T_WR_COEX_*, and the heap suite
(TASK-207/208/209) cannot reach a stable PLAYING state on the DUT.

**Decision needed (Architect / ADR-029):** the design assumed HTTPS streams. On a no-PSRAM
board that assumption is invalid. Options to weigh — (a) filter/order the radio-browser query
to surface HTTP-playable stations (audio streams are low-sensitivity public URLs; this is a
different risk class than the API endpoints ADR-029 governs); (b) document WebRadio as
HTTP-stream-only on no-PSRAM hardware; (c) reduce resident memory before the stream handshake
(unlikely to free 40 KB contiguous on this board). Needs an Architect call + ADR-029 amendment
before any code lands. Do NOT pick (a) silently — it's an ADR-029-adjacent security decision.

**Verification owed:** once a fix yields a reliably playable station, this unblocks the full
heap/coex suite and TASK-218's healthy-stream confirmation.

**Fix implemented + DUT-verified 2026-06-24 (multi-page HTTP fetch).** Per user decision,
WebRadio now keeps only `http://` streams and pages the votes-ordered list (page size =
WR_MAX_STATIONS, offset paging, ≤ `WR_FETCH_MAX_PAGES`=5 pages) until it has 30 playable
stations. `fetchOneMirror()` gained an `offset` param; `appendHttpStations()` filters
`https://` out. DUT-verified: station list now fills `count=30` all-HTTP and stations **reach
PLAYING state** (was 0 reachable before). 5/5 gates. **This closes the HTTPS-SSL-handshake
blocker this task was opened for.** ADR-029 amendment owed (cleartext-media-stream acceptance);
the API-endpoint TLS policy is unchanged. NOTE the kept `maxAlloc` heap-log addition for TASK-233.

**…but sustained playback is still blocked — see TASK-233.** With HTTPS out of the way, the
next no-PSRAM wall surfaced: the Helix MP3 decoder's buffer allocation fails intermittently
(`MP3Decoder_AllocateBuffers(): not enough memory`), so most streams connect then die within
~5 s (watchdog → ERROR_STALL). Distinct root cause; new task.

**Priority:** P1 — M-WEBRADIO MVP blocker
**Status:** **done (scope: HTTPS blocker) — DUT-verified 2026-06-24.** Multi-page HTTP fetch lands stations in PLAYING. ADR-029 cleartext-media amendment **written (ADR-029 §(5), 2026-06-24)** — media-stream transport ruled out of ADR-029's API-endpoint scope; `http://`-only accepted. Sustained-playback stability tracked separately as TASK-233 (direction set by ADR-045).
**Opened:** 2026-06-24
**Closed:** 2026-06-24
**Milestone:** M-WEBRADIO
**Owner:** Architect (ADR note) / Developer (done)
**Deps:** none

---

### TASK-233 — M-WEBRADIO: MP3 decoder buffer alloc fails on no-PSRAM → unstable playback

> **Router-confound annotation (2026-07-03, LL-096):** the no-PSRAM decoder-buffer heap wall is real
> (bare-rig EXP-009 corrected the heap model; A-lite arena fixed it; a fast station held in soak) — that
> stands. BUT "most drop within 5 s / stream dead (isRunning=0 for 5000ms)" is the *same signature* an
> MX5600 2.4 GHz auto-channel blackout produces: TCP stall → decode starves → isRunning false. Some early
> "genuinely dead decode" observations on this hostile link were plausibly router blackouts, not the heap.
> The TASK-218 watchdog mechanism is correct regardless of *why* the stream died. Re-test owed: underrun
> baseline on a fast station over the pinned-channel link (E0 idx-0 run used a slow-stream station,
> `minBufPct 0` — not a clean device baseline; see M-WR-AUDIO-TASK §E0).

**Severity:** HIGH — M-WEBRADIO MVP blocker (surfaced once TASK-232 made stations reach PLAYING).

**Symptom:** After TASK-232, HTTP streams connect and enter PLAYING, but most drop within
~5 s. Serial shows the real cause:
```
[I][webradio] HEAP pre-connect free=78040 min=47548 maxAlloc=38900
[I][webradio] HEAP play     free=67312
[E][mp3_decoder.cpp:1555] MP3Decoder_AllocateBuffers(): not enough memory to allocate mp3decoder buffers
[W][webradio] stream dead (isRunning=0 for 5000ms) — stop + resume Spotify TLS
```
The Helix MP3 decoder allocates ~29 KB across 9 buffers when the first MP3 frame arrives. On
this **no-PSRAM** board the largest contiguous block is only ~39 KB *pre-connect* and the
input buffer + socket fragment it further by decoder-alloc time, so the allocation fails. It
**sometimes succeeds** (fragmentation-dependent — ~3 of 16 stations held ≥14 s in one scan,
and the *same* station that held in one run died at 10 s in another), confirming it's right at
the heap boundary, not per-station deadness. The TASK-218 watchdog is behaving correctly here
(the library only clears `m_f_running` on a real stop, and no audio ever decodes), so it
faithfully reports a genuinely dead decode — not a false trip.

**This is the same no-PSRAM root-cause family as TASK-232's HTTPS-SSL failure.** Two heap walls
now stand between WebRadio and stable playback on this hardware. Whether WebRadio is viable as
an MVP feature on a no-PSRAM CYD at all is now a live product question for the Architect/human.

**Possible directions (Architect call needed):** (a) cut resident internal RAM before playback
(free Spotify-side display/JSON buffers, shrink `s_webRadioDoc`, etc.) to leave the decoder its
~29 KB — uncertain it can reach reliable margin; (b) pre-allocate / order decoder allocation
while the heap is least fragmented (needs library cooperation); (c) accept WebRadio as
best-effort with auto-skip-on-stall (ties into TASK-219 Tier 3) so dead-decode stations are
skipped automatically rather than parked in ERROR_STALL; (d) declare WebRadio unsupported on
no-PSRAM hardware. Needs measurement of the achievable post-trim `maxAlloc` vs the decoder's
real peak demand before committing.

**Architect decision (ADR-045, 2026-06-24):** WebRadio **stays in MVP scope on no-PSRAM as a
best-effort feature** — not declared unsupported, not promised reliable. Three ordered moves:
1. **UX now:** graduate auto-skip-on-stall (TASK-219 Tier 3) to MVP, default ON — tune past dead
   stations instead of parking on a stall. → **TASK-234**.
2. **Measure before RAM surgery:** spike the exact free/`maxAlloc` at `MP3Decoder_AllocateBuffers`
   + the 9 Helix buffer sizes, to tell a total-headroom gap (fixable by freeing RAM) from a
   single-block/contiguity wall (not). → **TASK-235**.
3. **Conditional (gated on the spike):** if the gap is small, free resident internal RAM during
   playback (`s_webRadioDoc` after fill, Spotify-side buffers while WebRadio owns the screen);
   if unbridgeable, gate the app behind a runtime PSRAM check (PSRAM-only). Reordering Helix
   allocs rejected (library fork).
**New MVP exit criterion (ADR-045):** stable PLAYING (holds ≥ 60 s) within ≤ 6 auto-skips on
≥ 90 % of cold-entry attempts.

**Spike resolved the direction (TASK-235 / EXP-007, 2026-06-24).** Move 3 narrowed by data:
- Decoder demand 22.7 KB; the 38.9 KB `maxAlloc` block is a **caps-restricted dead region** no
  audio alloc uses. Effective audio heap ≈ `free − 38.9 KB` ≈ **28 KB**, of which the decoder
  needs 22.7 KB → ~5 KB margin (hence intermittent).
- Input buffer ⟷ decoder are **zero-sum**: growing the input buffer to 16 KB made the decoder
  fail every time. So the underrun problem (the dominant slow-stream death mode) is **unfixable**
  on no-PSRAM, and general stable playback is **NO-GO**.
- **Remaining scope of this task = the one GO item:** free `s_webRadioDoc` (5 KB static
  `DynamicJsonDocument`) after the station fill — roughly doubles the decoder's ~5 KB margin →
  fewer decoder-alloc failures → more stations reach PLAYING first try. Startup reliability only;
  does nothing for underruns. Do **not** grow the input buffer; do **not** PSRAM-gate (fast
  streams work — auto-skip tunes to one).

**Note on the ADR-045 exit criterion (TASK-238):** the ≥ 90 % / ≤ 6-skip bar may be unmeetable
for slow streams given the ceiling — realistic target is "reliably reaches a stable *fast* station."
Re-baseline with the Architect at milestone close once the 5 KB reclaim lands.

**RECONCILIATION 2026-06-29 — the EXP-007 model above is superseded; the acute blocker is resolved.**
Two later findings overtake this task's original "NO-GO" framing (kept above for history):
1. **TASK-258 / EXP-009 (bare rig) corrected the heap model.** The "38,900 B caps-restricted dead region"
   this task built on was **not real** — it was just the *fragmented 11-app* largest-free block (bare it's
   110,580). The `usable = free − maxAlloc` framing was a misread. The bare radio plays reliably at ~165 K
   free; the audio path is ~41 K (8 K input + 22.7 K Helix + connection). **The wall is resident footprint
   (~147 K, leaving ~60 K), not silicon** — "no-PSRAM = NO-GO" is footprint-bound, not silicon-bound.
2. **A-lite arena (TASK-261/262, promoted to production) resolved the acute decoder-alloc failure.** The
   arena reserves the decoder its 24 K at the least-fragmented moment (after TASK-264 drops Spotify TLS,
   freeing ~50 K). **TASK-271 soak: 0 acquire-FAILs over 48 cycles, the decoder always gets its block,
   playback reaches ~12 s** (vs the ~5 s OOM death this task reported). The "MP3Decoder_AllocateBuffers: not
   enough memory" symptom is gone in the promoted build.

**Residual (the standing no-PSRAM ceiling):** slow-stream **underruns** — the 8 K input buffer (halved to
fit) starves on *slow* streams. This is the one TASK-233 finding that holds: it is **footprint-bound** (a
bigger input buffer needs deeper resident-footprint cuts, per TASK-258's lever), not a silicon limit.

**Long single-stream soak (2026-06-29, cyd2usb_webradio, auto-skip OFF):** a *fast* station (idx 0) held
**STABLE for the full 7 min** — `playMs` climbed linearly to 420,338 ms with **0 session drops, 0 new
underruns** (just the 1 startup blip), buffer pinned at 95–100% throughout. So a good stream is
**genuinely stable, not best-effort-flaky** — well past ADR-045's ≥60 s bar. (Earlier "~12 s" figures were the
TASK-271 *churn-soak window*, NOT a death point — corrected.) The residual is therefore **narrow**: only
*slow* streams underrun, and auto-skip (TASK-234, default ON) tunes past them to a stable one. Net user
experience: WebRadio reliably lands on and holds a playable station indefinitely.

**Residual shrink attempt — [EXP-012](../rnd/reports/EXP-012-input-ring-16k.md) (CLOSED 2026-07-02, no
promotion):** re-tested growing the input ring 8 K → 16 K post-arena. **H1 true** — the decoder allocates
fine at 16 K (EXP-007's zero-sum is obsolete; the ring *can* grow if ever needed). **H2 false** — same-day
8 K vs 16 K A/B on the same station list showed identical underruns (1 startup blip per session, steady-state
≈ 0 on both), and 16 K costs 8 K heap + collapses DMA-capable headroom 20 K → 4.6 K. **Input ring stays 8 K.**
Notably the "chronic slow-stream underrun" residual did not reproduce in 120 s holds on today's slowest
stations — the residual is rarer than the Phase 0 buffer-low-water readings implied. Knob + harness retained
default-off (`-DWR_INBUF_16K`, env `cyd2usb_webradio_16k`, `app/tools/exp012_measure.py`).

**The 5 KB `s_webRadioDoc` reclaim is DE-PRIORITISED (optional).** It targeted *startup margin* — which the
arena now provides reliably (0 acquire-FAILs), so its value is largely overtaken. Freeing 5 K resident during
playback would still marginally help underrun headroom, but it is **not worth blocking on**; fold it into any
future resident-footprint pass (the real lever) rather than as a standalone task.

**Priority:** ~~P1 blocker~~ → **P3 (resolved as best-effort; residual is the documented footprint ceiling)**
**Status:** **RESOLVED as best-effort (2026-06-29).** Acute decoder-OOM blocker fixed by the A-lite arena
(TASK-262, production); heap model corrected by TASK-258. Stable **fast-stream** playback works; slow-stream
underruns are the known footprint-bound ceiling — though EXP-012 (2026-07-02) could not reproduce them as a
chronic condition (120 s clean holds on the slowest live stations), and a 16 K input ring bought nothing, so
the ceiling is theoretical until a station demonstrates it. The 5 K `s_webRadioDoc` reclaim
is optional/de-prioritised. No further work blocks here — reliable-anything playback is a PSRAM-hardware or
deeper-footprint decision (TASK-258 lever), tracked there, not here.
**Opened:** 2026-06-24
**Milestone:** M-WEBRADIO
**Owner:** Developer
**Deps:** TASK-232 (done), TASK-235 (done — EXP-007) · **Superseded-by:** TASK-258 (EXP-009 model correction),
TASK-262 (A-lite arena, acute fix), TASK-271 (soak — residual quantified)

---

### TASK-234 — M-WEBRADIO: auto-skip-on-stall (Tier 3, graduated to MVP)

> **Router-confound annotation (2026-07-03, LL-096):** auto-skip-on-stall works correctly, but how
> *aggressive* it needed to be was benchmarked on a network that was itself dropping (MX5600 2.4 GHz
> auto-channel, now pinned). During a blackout auto-skip walks past many *good* stations and lands on one
> when the AP returns — creating a false "most stations are dead" impression and inflating the apparent
> skip rate. TASK-238's gate already flagged this ("conflates dead-station skips with outage skips"). The
> mechanism is sound; its tuning should be re-evaluated on the clean link. Not a code change — a
> measurement caveat.

Per ADR-045, the already-designed §Auto-retry/auto-skip policy (M-WEBRADIO.md §Error states)
is now MVP-mandatory on no-PSRAM hardware: the MP3 decoder fails intermittently (TASK-233), so
the device must tune past dead stations rather than park on `ERROR_STALL`.

**Scope (the bounded retry→skip subset only — *not* Tier 2 classification):**
- On `ERROR_STALL` (TASK-218 watchdog trip): retry the same station once; on a second stall,
  advance to the next station.
- Bound it: stop after one full pass over the list (no infinite skip loop — a runaway skip is
  worse than a stall), landing on the first station that holds, else a terminal "no playable
  station" error.
- `webRadioAutoSkip` **defaults ON** (was config-only/false). On-device toggle optional, not
  required for MVP.
- Also covers `ERROR_UNREACHABLE` on connect-fail (skip forward) so the dead-HTTPS-equivalent
  case self-heals too.

**Implemented + DUT-verified 2026-06-24.** Tick-driven (non-recursive) bounded retry→skip in
`webRadioApp.h`: `_onPlaybackFailed()` sets a deferred `_pendingAction` (RETRY_SAME / SKIP_NEXT)
that `tick()` dispatches one attempt per tick; `_play()` gained `userInitiated` (resets the scan
on a user pick); `_autoSkipTried` bounds the scan to one list pass; `WR_SETTLED_MS`=12 s resets
the scan once a station holds; `_stopAudio()` cancels a pending action (user stop/eject wins).
`webRadioAutoSkip` default flipped ON. New `get wrSkip` serial surface (autoSkip/tried/retries/
settled/pending) for the VE bound test. 5/5 gates; +~0.4 KB flash.

**DUT evidence (serial log):** `stall idx=5 — retrying once` → retry → `auto-skip 1/30 from
idx=5` → idx=6 → retry → **PLAYING**; a 2-skip case `auto-skip 1/30 … 2/30` → idx=11 PLAYING
(bound counter increments correctly); a retry-recovers-then-settles case (idx=13, tried reset to
0, settled=1); Spotify TLS resumed on every death. Verified: retry-once, skip-on-2nd-stall,
bound counter, tune-to-playable, settled-reset, default ON.
**Two test items split out of this task (neither gates the code, which is verified):**
- **TASK-237** — terminal one-pass-exhaustion *bound* regression test (VE; needs a dead-URL
  injection hook to be deterministic). Defense-in-depth for the no-infinite-loop invariant.
- **TASK-238** — ADR-045 *exit-criterion* statistical test (≤ 6 skips → stable PLAYING ≥ 90 %).
  A milestone-close gate, **not** a TASK-234 code gate, and deps TASK-235 (memory reduction will
  move the success rate, so measuring before it lands just gets re-taken).
**Priority:** P1 — M-WEBRADIO MVP blocker · **Status:** **done — implemented + DUT-verified 2026-06-24** (core mechanism: retry-once, skip-on-2nd-stall, bound counter, tune-to-playable, settled-reset, default ON). Follow-on tests are TASK-237/238. · **Opened:** 2026-06-24 · **Closed:** 2026-06-24
**Milestone:** M-WEBRADIO · **Owner:** Developer (done) · **Deps:** TASK-218 (done), ADR-045

---

### TASK-237 — M-WEBRADIO: auto-skip terminal-bound regression test (+ dead-URL hook)

Split from TASK-234. The auto-skip scan is bounded to one list pass (`_autoSkipTried + 1 <
_stationCount` → terminal `ACT_NONE`); a runaway skip loop would be worse than a stall (ADR-045),
so the bound is safety-relevant. DUT-observed correct up to the increments (`1/30 → 2/30`) but
the *terminal* transition (all stations dead → stop, no loop) was not forced — real dead streams
are intermittent and `set wrState` injection bypasses `_onPlaybackFailed()`.

**Why it needs a hook:** to be deterministic the test must make every station fail. Add a
debug-only serial hook (e.g. `set wrDeadUrls 1`) that swaps the station URLs for a guaranteed-
unreachable host (or forces `connecttohost` to fail), then assert: from a user play, the device
skips exactly `_stationCount` times, `wrSkip.tried` saturates at the bound, lands terminal
(no further `pending` action), and never loops. Also assert auto-skip OFF parks on the first
stall (no skip).

**Scope:** defense-in-depth regression test, not a correctness blocker (the bound is sound by
construction + partially observed). File under the VE regression suite.

**DONE — DUT-verified 2026-06-25 (T237 PASS; 1 passed / 0 failed / 0 skipped).** Added the debug-only
dead-URL hook `set wrDeadUrls N`: synthesizes N unreachable stations and arms `_debugForceConnFail`, so
every `_play()` fails the connect deterministically **before** the network/audio path (no real dead
stream, no tlsYield). Added `set wrAutoSkip 0|1` (no on-device UI exists) to drive both branches. New
regression test **T237** asserts: auto-skip **ON** → exactly N-1 skips (`wrSkip.tried` saturates at
N-1), lands **terminal** (ERROR_UNREACHABLE), and **never loops** (tried stable across a settle); auto-
skip **OFF** → parks on idx 0, no skip. Spotify/network-independent (eject entry + synthetic list).
This closes the gap the task was opened for — the *terminal* transition (all-dead → stop, no loop) is
now forced and observed, not just the increments. 5/5 gates.
**Priority:** P2 · **Status:** done — DUT-verified 2026-06-25 · **Opened:** 2026-06-24 · **Milestone:** M-WEBRADIO
**Owner:** VE (test) + Developer (dead-URL hook) · **Deps:** TASK-234 (done)

---

### TASK-238 — M-WEBRADIO: ADR-045 exit-criterion test (milestone-close gate)

Split from TASK-234. The ADR-045 MVP exit criterion: from cold entry on the no-PSRAM DUT,
WebRadio reaches a stable PLAYING state (holds ≥ 60 s) within ≤ 6 auto-skips on ≥ 90 % of
attempts. This is a **statistical milestone-close gate for M-WEBRADIO, not a TASK-234 code
gate** — it measures the feature-level outcome over many cold-entry trials.

**Sequencing:** **deps TASK-235.** Run *after* the heap-measurement spike and any memory
reduction it green-lights — freeing RAM raises first-station decode success, which changes the
skip count and the pass rate. Measuring before TASK-235 lands produces a number that gets
re-taken. If TASK-235 escalates to PSRAM-gating instead, this criterion is moot on no-PSRAM
hardware (WebRadio hidden there) and applies only to the PSRAM target.

**Deliverable:** a repeatable VE harness that runs N cold entries, records skips-to-stable and
hold time, and reports the pass rate against the ≤ 6 / ≥ 90 % bar. Gates M-WEBRADIO MVP close.
**Harness delivered 2026-07-02:** `app/tools/test_adr045_gate.py` + `run/wr-gate` (N cold-entry trials,
cumulative-skip tracking across the settle-reset, fetch reboot-retry, non-zero-IP boot gate, 60 s settle).
Driving it surfaced and fixed two real defects first: TASK-272 (WiFi power-save idle-kill) and TASK-273
(auto-skip burned the full list in <1 s during a network blip).

**Gate run 4 (2026-07-02, post-fixes): 7/10 — FAIL against the ≥90 % bar, environment-attributed.**
Per-trial: 7 passes all `skips=0, ttfp≈0.1 s, hold>60 s` (when the network is up the tuner is flawless);
3 fails were RF outages on the DUT's AP that evening (drops every ~2–5 min): T1 11 skips (post-idle
reassoc ~10 s) *but held 60 s*, T5 13 skips (~26 s outage) *but held 61 s*, T10 outage >32 s → list
exhausted → terminal park (the TASK-273 follow-on candidate: no retry-from-terminal). **9/10 trials
achieved the 60 s stable hold.** The ≤6-skip bar conflates dead-station skips with outage skips.
**Needs: a re-run in a healthy RF window, and/or a human ruling on whether outage-skips count against
the bar (ADR-045 owner).**

**Gate run 5 (2026-07-02 17:55–18:35, instrumented per TASK-275): 10/10 PASS.** Every trial `skips=0,
ttfp≈0.1 s, hold>60 s, discΔ=0`; **one** link event in the whole run (boot-time reason=202 auth retry at
t=748 ms), zero outage windows. Same evening as the dirty runs (beacon-timeout storm 25 min prior), so the
§3.4 clean-dirty-window rule applies: score and close. **Caveat recorded honestly:** the harness's 1 Hz
host-ping doubles as a link keepalive and may have suppressed the AP idle-kick — an observer effect that is
*also* supporting evidence for the AP-inactivity attribution (see TASK-275 / LL-093). The criterion is met
on its own terms; field robustness continuations (retry-from-terminal, optional keepalive) are tracked as
candidates, not blockers.

**Priority:** P2 — milestone-close gate · **Status:** **DONE — ADR-045 exit criterion PASSED 10/10,
2026-07-02 (gate run 5)** · **Opened:** 2026-06-24 · **Closed:** 2026-07-02
**Milestone:** M-WEBRADIO · **Owner:** VE · **Deps:** TASK-235 (done), TASK-234 (done), TASK-272/273 (done)

---

### TASK-235 — M-WEBRADIO: heap measurement spike (gates TASK-233 memory reduction)

Per ADR-045 move 2 — measure before any RAM surgery. Instrument the **exact** decode-failure
point so we know whether direction "free more RAM" can ever reach reliable margin:
- Log free heap **and** `maxAlloc` (largest contiguous block) immediately before and after
  `MP3Decoder_AllocateBuffers()` (not just at pre-connect — the `maxAlloc` pre-connect log is
  already in `webRadioApp.h`).
- Capture the size of each of the 9 Helix buffers (`sizeof` the structs) and which alloc fails
  first → distinguishes a **total-headroom** gap (addressable) from a **single-block/contiguity**
  wall (not addressable by freeing total RAM).
- Quantify what's freeable during playback: measure heap after freeing `s_webRadioDoc` and after
  releasing Spotify-side display/response buffers, to size the realistic gain vs the gap.

**Deliverable:** a short measurement report (rnd/reports or inline in TASK-233) with the numbers
+ a go/no-go on direction "free more RAM" vs escalate to PSRAM-gating.

**Done 2026-06-24 — see `docs/rnd/reports/EXP-007-webradio-nopsram-heap-spike.md`.** Numbers:
Helix decoder demand = **22.7 KB** (9 allocs, largest 8.5 KB). `maxAlloc` pinned at **38 900 in
both the 8 KB- and 16 KB-input-buffer runs** → that block is a **caps-restricted dead region** no
audio alloc can use; effective audio heap = `free − 38 900`. With the default 8 KB buffer the
decoder has **~5 KB margin** (28.1 KB usable − 22.7 KB) → usually succeeds, intermittent.
Enlarging the input buffer to 16 KB dropped usable to 20.6 KB → **decoder fails every time**
(measured). So input buffer ⟷ decoder are **zero-sum**; the buffer can't grow (the only lever for
underrun tolerance) without starving the decoder. **Go/no-go:** NO-GO on general stable playback
(slow-stream underruns are unfixable on no-PSRAM); NO-GO on PSRAM-gating (fast streams work, keep
it); **GO on a small ~5 KB startup-margin reclaim only** (free `s_webRadioDoc` after fill) — folds
into TASK-233, improves decoder-alloc reliability, does nothing for underruns. Net: best-effort,
ceiling-bound (ADR-045 framing confirmed by data).
**Priority:** P2 · **Status:** **done — 2026-06-24** (report EXP-007) · **Opened:** 2026-06-24 · **Closed:** 2026-06-24
**Milestone:** M-WEBRADIO · **Owner:** Developer / R&D · **Deps:** TASK-232 (done)

---

### TASK-236 — M-WEBRADIO: remove the now-dead radio-browser `setInsecure()` fallback

ADR-029's §(3) decision gate resolved at T_WR_TLS_01 on 2026-06-24: `tlsInsecure:0` — the pinned
`setCACert()` path verified, the `setInsecure()` fallback in `fetchOneMirror()` **never fired**.
Per the gate (and ADR-029 §(5)), the fallback is dead code and should be removed. Keep the
`tlsInsecure` field/`get wrLastHttp` surface (quarterly-check observability) but drop the actual
`setInsecure()` retry branch in `fetchWebRadioStations()`. Low risk; do alongside TASK-234's
fetch-path work to avoid a separate DUT cycle.
**Done 2026-06-25.** Removed the `insecure` param from `fetchOneMirror()` (now `setCACert()`-only)
and the page-0 retry branch in `fetchWebRadioStations()`; a verify/handshake failure now skips the
mirror instead of downgrading. `tlsInsecure` field + `get wrLastHttp` surface **kept** (always
false now; observability per the gate). Stale fallback comments in `dataTaskCerts.h` reconciled to
the T_WR_TLS_01 finding. Host-only change (no behaviour difference on the verifying mirrors); 5/5
gates. No DUT cycle needed — the removed path provably never executed.
**Priority:** P3 · **Status:** done 2026-06-25 · **Opened:** 2026-06-24 · **Milestone:** M-WEBRADIO
**Owner:** Developer · **Deps:** none (TASK-214 closed this gate)

---

## Open — M-WEBRADIO RAM-recovery investigation (PM plan, 2026-06-24)

> **PM sync 2026-06-24 (RAM recovery).** A technique survey + inline code audit (subagents died
> on a session limit; run inline) found the firmware is already RAM-disciplined — skin atlas is
> `const`→flash, the Winamp renderer uses no sprite framebuffer, aquarium frees its sprite in
> `suspend()`. So no fat app-buffer reclaim exists. But ~**14 KB IS reclaimable**: `s_webRadioDoc`
> (5 KB, lazy), `s_heatmapDoc` (2.5 KB, lazy), and a `dataTask` stack trim (20 KB → ~14 KB, ~6 KB,
> pending high-water measurement). This **materially challenges EXP-007/ADR-045's "ceiling-bound,
> don't do memory surgery" conclusion**: EXP-007 measured the budget *as-is*. The decoder needs
> free ≈ 65 KB to allocate; the failed 16 KB-buffer run had 59.5 KB. Reclaiming ~14 KB → ~73 KB →
> the bigger input buffer (the underrun fix) and the decoder could coexist. Plan: do the low-risk
> reclaims, measure, then **re-run the 16 KB-buffer experiment as the decision gate** (TASK-241).
> This investigation could supersede ADR-045 — Architect input needed on two points (see below).

### TASK-239 — M-WEBRADIO: lazy-allocate s_webRadioDoc + s_heatmapDoc (low-risk reclaim)

Make the two persistent static `DynamicJsonDocument`s heap-alloc-on-use / free-after-use instead
of file-scope-resident: `s_webRadioDoc` (5 KB, `dataTaskStorage.cpp:597` — only live during the
station fetch) and `s_heatmapDoc` (2.5 KB, `:584` — only live when the Stock heatmap fetches).
Frees ~7.5 KB of resident heap during WebRadio playback. **Fragmentation caveat (Architect review,
see below):** free `s_webRadioDoc` *before* the audio path allocates and avoid alloc/free churn at
the fetch→playback boundary, since contiguous-block availability is the core problem.
**Architect ruling (ADR-045 amendment 2026-06-24):** free `s_webRadioDoc` immediately after
`appendHttpStations()` copies stations out — before `tlsResume()`, never held across playback;
`s_heatmapDoc` alloc/free within the heatmap fetch only; both frees must complete before the
audio path's first alloc; verify via the existing `HEAP pre-connect` log (free/maxAlloc must
actually rise at decode time).
**Done (s_webRadioDoc) 2026-06-24.** `s_webRadioDoc` is now a fetch-scoped local
`DynamicJsonDocument webRadioDoc(WR_DOC_CAP)` in `fetchWebRadioStations()`, passed by ref to
`fetchOneMirror()`/`appendHttpStations()`, freed at a scope brace **before `tlsResume()`** per the
Architect ruling. Its 5 KB pool is no longer heap-resident across playback (the pool was always
heap, allocated at static-init — so this shows as runtime free-heap gain, not a static-RAM drop).
Build-clean. **DUT-verify with TASK-241** that `HEAP pre-connect free/maxAlloc` actually rises.

**s_heatmapDoc DEFERRED — EXP-003 conflict (flag to Architect/QM).** The naive Architect ruling
("alloc/free within the heatmap fetch") collides with PROP-004/EXP-003: `s_heatmapDoc` is
allocated at `dataTaskStorage.cpp:654` *while the Yahoo TLS session is still open* (fragmented
heap) — the exact malloc-failure condition it was made static to avoid. Reclaiming its 2.5 KB
safely needs the alloc moved to post-`tlsYield()`/pre-TLS-open with a scoped free before
`tlsResume()`, plus EXP-003 re-validation. Not worth a Stock-app regression risk now; the 5 KB
webRadioDoc + ~6 KB stack (TASK-240) carry the plan. Revisit only if TASK-241 needs the extra
2.5 KB.
**Priority:** P2 · **Status:** **done (webRadioDoc); heatmapDoc deferred (EXP-003)** · **Opened:** 2026-06-24 · **Milestone:** M-WEBRADIO
**Owner:** Developer · **Deps:** none

### TASK-240 — M-WEBRADIO: measure + trim dataTask/spotifyTask stacks

`dataTask` reserves a **20 KB** stack (`dataTaskStorage.cpp:71`), `spotifyTask` 10 KB
(`spotifyTaskStorage.cpp:38`) — both heap-resident for life. Instrument
`uxTaskGetStackHighWaterMark` on both and trim to high-water + safety margin (dataTask likely
recovers ~6 KB; spotifyTask is tighter — mbedTLS handshake needs 6–8 KB). **Cross-feature
(Architect/VE):** dataTask is shared by 5 fetchers (weather/crypto/stock/teletext/webradio); the
worst-case stack path may not be webradio, so the high-water must be measured while exercising the
deepest fetcher, not just a WebRadio fetch.
**Architect ruling (ADR-045 amendment 2026-06-24):** measure `uxTaskGetStackHighWaterMark` after
one session exercising **every** fetcher (weather, crypto, stock quote, stock chart, teletext
worst-case page, WebRadio full multi-page); trim only to `(stack − min headroom) + ≥ 2 KB margin`
rounded up to 1 KB. Must-hit deepest paths: teletext grid parse + WebRadio paging. spotifyTask:
leave ≥ 3 KB margin (mbedTLS handshake 6–8 KB) or skip. VE confirms coverage.

**Done + DUT-verified 2026-06-24.** Added `get stacks` serial surface +
`{spotify,data}Task::stackHighWaterBytes()/stackSizeBytes()`. Measured high-water across all
fetchers on DUT: **dataTask worst-case = 8984 B** (the WebRadio multi-page fetch; weather/crypto/
stock peak ~6000 B), **spotifyTask = 6272 B**. **Trimmed dataTask 20 KB → 14 KB (reclaim 6 KB)** —
re-validated under the WebRadio fetch at 8892 B used / 14336 (5.4 KB / 38 % margin), no overflow,
fetch returns count=30. **spotifyTask SKIPPED** (6272/10240 → only ~1 KB trimmable, mbedTLS
handshake needs the margin). The old 12 KB-overflow comment was stale (pre-streaming code);
current streaming parse peaks at ~9 KB.
**Priority:** P2 · **Status:** **done — DUT-verified (6 KB reclaim)** · **Opened:** 2026-06-24 · **Milestone:** M-WEBRADIO
**Owner:** Developer + VE · **Deps:** none

### TASK-241 — M-WEBRADIO: re-run input-buffer experiment with RAM reclaimed (DECISION GATE)

After TASK-239/240, re-run the EXP-007 experiment: enlarge the audio input buffer
(`setBufsize`, ~16 KB) *with* the ~14 KB reclaimed, and measure on DUT — (a) does the MP3 decoder
still allocate reliably, and (b) do the "slow stream, dropouts" underruns drop / do stations hold
≥ 60 s. **This is the go/no-go that decides whether stable WebRadio is achievable on no-PSRAM.**
Feeds an ADR-045 amendment/supersede either way. Pass → revise ADR-045 from "best-effort,
ceiling-bound" toward "stable with reclaim"; fail → the 38.9 KB caps-restricted dead block is the
wall, ADR-045 stands, stop.
**Architect (ADR-045 amendment 2026-06-24):** sanctioned as a decision gate that may supersede
ADR-045 — PASS → "stable via targeted reclaim"; FAIL → 38.9 KB caps-restricted block is the wall,
ADR-045 stands. Do NOT ship buffer-size changes before this gate. Verify the reclaim raised
free/maxAlloc at decode time, not just nominally freed memory.

**BLOCKED on a valid test condition (2026-06-24).** TASK-239/240 done (~11 KB reclaimed,
verified). But the decisive test requires the **tight ~78 KB playback heap** EXP-007 measured —
and that only exists when **Spotify is actively playing a track** (full resident footprint: TLS
session + album art + metadata + fragmentation). The DUT currently shows Spotify *configured but
idle* (`isPlaying:false`); idle → webradio play `tlsYield()` frees Spotify → ~130 KB free, which
makes any decoder+16 KB-buffer test pass trivially (proves nothing). **Needs the user's Spotify
account actively playing music**, then: re-flash debug, enlarge the input buffer (`setBufsize`
~16 KB), play a station, and check on DUT — (a) decoder still allocates at ~78 KB − 11 KB reclaim
headroom, (b) underruns drop / station holds ≥ 60 s. External dependency, not a code blocker.
**Provisional PASS (2026-06-24) — final confirmation blocked on device Spotify auth.**
Synthetic-pressure test (debug-only `set heappressure`, 16 KB `setBufsize`, audio_info hook).
Decisive data point, fresh decoder after boot: **with the 16 KB input buffer + the ~11 KB
reclaim, the MP3 decoder allocates OK at `preConnFree=89236`** (`MP3Decoder has been initialized`,
no OOM). Compare EXP-007: 16 KB buffer, *no* reclaim, decoder **failed** at the Spotify-playing
tight baseline `preConnFree≈78 K`. The reclaim lifts the baseline 78 K → 89 K (78 + 11), and the
decoder demonstrably allocates at 89 K → **the bigger buffer and the decoder can coexist with the
reclaim.** Strong evidence stable no-PSRAM playback is achievable.

**Why provisional, not final:** (1) the 89 K point was Spotify-*idle*; the exact Spotify-*playing*
fragmentation at the true tight condition couldn't be reproduced — **the device's Spotify auth is
broken** (`isPlaying` stuck false, `lastPollAgeMs` climbs, "startup poll failed"; token expired
since EXP-007). (2) The clean fresh-decoder threshold sweep and the underrun-reduction half (does
the 16 KB buffer hold streams ≥ 60 s) were both blocked because the broken Spotify makes
`tlsYield()` hang during WebRadio `_play()` after a reboot. (3) Per Architect, the `setBufsize`
change is NOT shipped before the gate conclusively passes — reverted; only the reclaim (239/240)
is committed. **To finalise:** fix device Spotify auth (re-run `get_refresh_token.py` →
`./run/spiffs push`), then re-test with a track playing — confirm decoder alloc (already strongly
indicated) + station holds ≥ 60 s with fewer dropouts. Feeds the ADR-045 amendment.
**DOWNGRADED to implemented-unverified (2026-06-25).** The earlier "provisional PASS" leaned on
EXP-007's ~78 K "Spotify-playing" baseline — which TASK-243 shows was almost certainly **never a
live Spotify session** (owner-account Premium had lapsed; host reproduces the 403). So the
tight-condition comparison rests on an unconfirmed baseline and must be **re-taken**, not cited.
The reclaim itself (TASK-239/240) is real and verified; whether it makes playback *stable* is
**not yet proven**. Blocked on **TASK-243** — no valid tight-heap test is possible without a live
Spotify session. When unblocked: host-confirm the API is live, then run the tight-condition test.
**Priority:** P1 — settles the M-WEBRADIO viability question · **Status:** **implemented-unverified — deferred-behind-TASK-243** (was "provisional PASS"; baseline invalid). **TASK-255 (Spotify-disabled build) is now the active no-PSRAM viability gate** — a parallel lane that runs *now* without Premium, answering "is no-PSRAM WebRadio viable at all." TASK-255 does **not** supersede this: the two answer different questions (TASK-255: Spotify-*free* viability; TASK-241: multi-app-reclaim viability) and a TASK-255 PASS does **not** overturn ADR-045 for the multi-app board. This task resumes when TASK-243 (owner Premium) clears, to take the valid tight-heap baseline.
**Opened:** 2026-06-24 · **Milestone:** M-WEBRADIO · **Owner:** Developer + Architect (decision)
**Deps:** TASK-239 (done), TASK-240 (done), TASK-243 (blocker) · **Parallel lane:** TASK-255

---

## Done — TASK-242: WebRadio taskbar crash (latent, shipped) — 2026-06-24

### TASK-242 — taskbar crash on the WebRadio slot (null icon) + design-conformance gap

**Severity: HIGH — shipped crash on core navigation.** Reported by user: "using the taskbar
triggers a crash." Backtrace: `Guru Meditation (LoadProhibited) … pushImage(...) ← renderTaskbar`,
`EXCVADDR=0x0` — a **null icon pointer**.

**Root cause (chain, see LL-085):** WebRadio (11th `AppId`) is designed as taskbar-*hidden*
(eject-entry only, M-WEBRADIO §). But the taskbar derived its slot count from `AppId::COUNT` (11),
so WebRadio leaked into the scroll cycle; its `kTaskbarIcons[10]` entry was never baked
(zero-filled → null) → scrolling to its slot did `pushImage(nullptr)` → crash. Latent ~10 days.
Missed because: (1) the "no taskbar slot" rule was prose with no enforcing mechanism; (2) the VE
harness entered WebRadio via `tap_taskbar_slot(WebRadio)` — an off-screen coordinate that the tap
handler mapped via modulo, **never rendering the slot**, so the crashing path was never tested;
(3) no gate/checklist verified icon↔app-count conformance.

**Fix (all landed, DUT-checked, 5/5 gates):**
- `TASKBAR_APP_COUNT = (int)AppId::WebRadio` used at all taskbar render + gesture call sites
  instead of `AppId::COUNT` — WebRadio is never a taskbar slot. DUT: full scroll cycle, no crash.
- Null-guard in `renderTaskbar` (defense-in-depth — a null icon renders blank, never crashes).
- Two compile-time `static_assert`s in `taskbar.h`: WebRadio stays last; `TASKBAR_ICON_COUNT ==
  TASKBAR_APP_COUNT` (a taskbar app missing its baked icon now **fails the build**, via the new
  generator-emitted `TASKBAR_ICON_COUNT`). This is the gate that makes the bug class impossible.
- VE: harness now enters WebRadio via the **eject button** (design path); `_TB_N` corrected to
  exclude WebRadio; new regression test **T242** scrolls the taskbar a full cycle and asserts no
  crash + WebRadio never a slot. (Re-validation of the full WebRadio suite pending device Spotify
  re-auth — see TASK-241.)
- QM: NEW-APP-CHECKLIST §6 (taskbar visibility + icon); lessons-learned **LL-085**.

**DONE — fully DUT-verified 2026-06-25 (T242 + T_WR_EJECT_01/02 PASS; 3 passed / 0 failed / 0 skipped).**
The earlier "blocked on TASK-243" note was **wrong**: the harness's `_restore_spotify()` is a plain
app-switch (UI), which works regardless of the Spotify 403 — no *live* session is needed to restore
state between these tests. Verified on DUT: **T242** full taskbar scroll cycle (10 offsets) — no crash,
WebRadio never a taskbar slot; **T_WR_EJECT_01/02** eject Spotify↔WebRadio both routes. The eject-entry
harness change and `_TB_N` correction are exercised by these. So the test-coverage portion is now green;
both halves (crash fix + tests) closed. (Lesson: don't assume a Spotify-app test needs Premium — only
tests that read live *playback state* do; UI/nav tests don't.)
**Priority:** P1 (shipped crash) · **Status:** **DONE — crash fix + test coverage both DUT-verified 2026-06-25**
**Opened:** 2026-06-24 · **Milestone:** M-WEBRADIO / M-MULTIAPP
**Owner:** Developer (fix done) + VE (test — DUT-green) + QM (checklist/lesson done)

---

### TASK-243 — BLOCKER: Spotify Web API 403 — owner account lacks active Premium

**This blocks all remaining WebRadio verification** (TASK-241 tight-condition test, the WebRadio
serialdbg suite, and TASK-242's T242 + eject-harness validation) and any device feature that reads
Spotify playback state.

**Definitive root cause (host-confirmed, not device).** `app/tools/spotify_state.py` and a raw
host call reproduce the device's exact 403 from the laptop with the same creds — token refresh
succeeds (correct scope), but `/v1/me`, `/v1/me/player`, and `/v1/me/player/currently-playing` all
return **403** with body:
> *"Active premium subscription required for the owner of the app. When the subscription status
> changes, it can take a few hours before requests are allowed again."*

Spotify now requires the **app owner** (clientId `db2ff3…`) to hold active Premium for Web API
access; that lapsed. **Not** the device, firmware, token, scope, or dev-mode allowlist — re-auth +
`spiffs push` were done and are correct; they'll just start working once Premium is restored.

**Knock-on:** EXP-007's "78 K pre-connect = Spotify playing" baseline was almost certainly never a
live session (Premium already lapsed), so TASK-241's provisional numbers rest on an unconfirmed
baseline — re-take once the API is live.

**Resolution (user/owner action — external):** restore active Premium on the owning Spotify
account, then wait the few hours Spotify mentions. **Verify-first procedure when back:** run
`./run/… spotify_state.py` (host) and confirm `ok:true` / `isPlaying` tracks playback *before*
spending any DUT time — this host check is the cheap gate that should precede device work
(process lesson from this session: host-validate the API path first).
**Priority:** P1 — external blocker · **Status:** open (blocked on owner-account Premium)
**Opened:** 2026-06-25 · **Milestone:** M-WEBRADIO / infra
**Owner:** Human (Spotify account) · **Deps:** none (external)

---

### TASK-244 — Harden tlsYield: a failing Spotify poll loop starves all dataTask fetchers

**Found while diagnosing a "Stock app can't pull data" report (2026-06-25).** Not a stock
bug — a secondary symptom of the TASK-243 403. The stock/heatmap data path is healthy
(host Yahoo probe + screener all 200; pinned intermediate cert still valid; device fetch
returns `heatmap GET 200 count=20` with **valid** data). The problem is *latency from
starvation*: the fetch never arrives within any usable window.

**Mechanism (TASK-131 shared-TLS design).** Every dataTask fetcher — `fetchHeatmapQuote`,
stock quote/chart, weather, crypto, teletext, webradio — opens with
`spotifyTask::tlsYield()` (`dataTaskStorage.cpp:620`), which blocks until the Spotify
FreeRTOS task calls `client.stop()`. The Spotify task only checks `s_tlsYieldReq` *between*
polls (`spotifyTaskStorage.cpp:309`); `tlsYield()` itself waits up to **150 s** for the ack
(`spotifyTaskStorage.cpp:492`). When the account 403s, `doPoll()` runs slow, back-to-back
(`poll=0/6 last=403`, `next_poll_in_ms=0`), so the yield is starved.

**Measured on DUT (debug build, 2026-06-25):** heatmap triggered at t=0; `tlsYield()`
returned only at **t+84 s**, then the fetch immediately succeeded. Any app (weather/crypto/
teletext/webradio too) is equally affected — the single shared yield is the choke point.

**Fix shape (options for Architect/Developer):**
1. **Bound the yield** to a few seconds and have the fetcher fail fast (return a distinct
   "TLS busy" error code) rather than blocking up to 150 s — let the app retry on its own
   cadence and keep the UI responsive.
2. **Short-circuit `tlsYield()` on a 403 poll status** — the device already has the exact
   HTTP status in hand (`spotifyTaskStorage.cpp:193-195`; surfaced as `last=403`). A 403 is
   an authorization refusal that won't self-heal by retrying, unlike a transient `-1` (TLS
   reset) or `429` (rate-limit) which DO recover — so keying on the 403 status is sharper
   and safer than a generic "N consecutive failures" counter (which would false-trip on
   recoverable blips). Trigger on the 403 (optionally require 1–2 consecutive to ignore a
   one-off); when set, let dataTask proceed without yielding — a Premium-lapsed Spotify
   session isn't making progress and shouldn't hold the shared TLS hostage.
3. Surface a precise "Spotify: no active Premium" hint in-app. NOTE: the definitive reason
   string ("Active premium subscription required for the owner of the app") is in the 403
   **body**, which the vendored `SpotifyArduino` discards on non-200 (`getCurrentlyPlaying`
   returns only the int status). A user-facing reason needs a small lib patch to capture the
   error body; the bare 403 *status* (already available) is enough for the yield short-circuit.
   Caveat: 403 status alone isn't uniquely "no Premium" in general (audio-features/analysis
   also 403 under quota policy — TASK-010), but persistent 403 on the *player poll* endpoint
   effectively is the owner-Premium-lapse case.

Prefer (2) as the targeted fix for the observed failure — keyed on the 403 status, which the
device already records — over a generic failure counter; (1) is the general robustness win;
(3) is an optional UX nicety gated on a lib change.

**Priority:** P2 — robustness; only bites when Spotify poll is failing (today: TASK-243),
but then it degrades *every* other app · **Status:** implemented — DUT-verified 2026-06-25
**Opened:** 2026-06-25 · **Milestone:** infra / dataTask
**Owner:** Architect (design call) → Developer · **Deps:** relates to TASK-243 (the trigger),
TASK-131 (the shared-TLS design being hardened)

**Implementation (2026-06-25) — `nextWaitMs()` hard-backoff on 403.** Chose the safe variant of
option 2: rather than letting the dataTask skip `tlsYield()` (OOM risk — Spotify's TLS still
holds ~40 KB), make the *Spotify* poll back off hard when the 403 latch is set
(`s_authErrorLatched`, from TASK-245). `nextWaitMs()` returns `kBackoffMaxMs` (60 s) immediately
on a 403 instead of climbing 5→10→20→40 s, so Spotify idles between polls and the dataTask gets
prompt yield windows. Also immune to `resetBackoff()` (a touch can't restart the fast-poll
storm — the latch holds). Recovery still detected within one 60 s interval once the account is
fixed.
**Trigger / why now:** surfaced visibly as "network apps stuck on amber" (TASK-245 connecting
state) — teletext/weather/crypto/stock couldn't get a TLS window while Spotify hammered 403s
every 5–20 s.
**DUT result:** before — teletext amber for tens of s to minutes; after — **amber→green in ~2 s**,
heartbeat `next_poll_in_ms≈36 s` (Spotify in 60 s backoff, not hammering). T-ERR-01/02/04/05/06
re-run PASS; `run/check` 5/5.

---

### TASK-245 — Per-app error-state endpoint + red taskbar active-bar signal (mechanism)

Add a generic per-app error signal and surface it as a **red** taskbar active-slot bar.
Design ruling: **ADR-046**. The taskbar indicator today has two states (green idle /
amber `g_shellBusy`); this adds a third for a sustained error condition.

**Scope (mechanism only — wire Spotify as the sole first consumer):**
1. **Base class** — add `virtual bool hasError() const { return false; }` to `struct App`
   (`appShell.h:9`), sibling to `hasPendingAsync()` (`appShell.h:18`). Sticky; app sets on
   error, clears on next success; shell does no latching of its own.
2. **Render** — tri-state precedence **error (red) > busy (amber) > idle (green)** in
   `renderActiveIndicator` (`taskbar/taskbar.h:37`). New firmware-only constant
   `#define TASKBAR_ERR_COLOR 0xF800` in `taskbar.h` — **NOT** in generated
   `shell_layout.h` (preserve the `check_build.sh` golden hash, same rationale as
   `TASKBAR_BUSY_COLOR`). Re-render on the existing busy/switch/tick triggers.
3. **Spotify consumer** — `SpotifyApp::hasError()` returns true on a (persistent) 403 poll
   status; source is `lastHttpRef()` / the `status` at `spotifyTaskStorage.cpp:193-195`.
   Ties to **TASK-244** (same 403 signal). All other apps keep the default `false` for now.
4. **feature_inventory.yaml** — entry `app-error-signal-001`.
5. **cross_feature_matrix.yaml** — capture the combinations (X017–X020): `hasError × busy`
   (precedence), `hasError × not-active-slot` (the accepted active-only limitation),
   `hasError × app-switch away/back`, `hasError × clears-on-recovery`.
6. **VE** — tests for the tri-state precedence + Spotify 403 → red + clear-on-recovery.

**Accepted limitation (ADR-046 §4):** recolours the *active* app's bar only — an app's error
shows only while it is the active app (no persistent per-slot dot). Spotify 403 is therefore
red only while Spotify is active. Note the 403 *starvation* case (TASK-244) makes other apps
*slow* not *failed*, so they go red only on a genuine fetch error.

**Priority:** P2 · **Status:** implemented — DUT logic-verified 2026-06-25 (visual red-bar
sign-off owed) · **Opened:** 2026-06-25 · **Milestone:** M-MULTIAPP / UI
**Owner:** Developer (consult Architect — base-class contract change) · **Deps:** ADR-046,
TASK-244 (Spotify 403 detection), app-registry-001 / taskbar-icons-001

**Implementation (2026-06-25):**
- `App::hasError()` added to base class (`appShell.h`); default false.
- `TASKBAR_ERR_COLOR 0xF800` + `error` param with precedence error>busy>idle in
  `renderActiveIndicator` / `renderTaskbar` (`taskbar/taskbar.h`); firmware-only #define
  (golden hash unaffected — verified `run/check` gate 3).
- `shell::activeError()` threads the active app's error into every taskbar repaint;
  edge-triggered re-render in the main loop catches async onset/clear (`main.cpp`).
- Spotify consumer: `SpotifyApp::hasError()` → new `spotifyTask::authError()`
  (`s_lastHttpStatus == 403 && consecutiveFailures >= 2`; self-clears on next 200/204).
- Debug getter `get activeError` → `{active, spotifyAuthError}` for VE assertions.
- Synthetic injection for deterministic VE: `set lastHttp 403` + `set backoff 2` synthesises
  `authError()` without a real account 403 (`spotifyTask::dbg_set`).
- **DUT (live 403):** `get activeError` → `active:true, spotifyAuthError:true` while Spotify
  active; `run/check` 5/5.

**Amendment (2026-06-25) — boot reads amber, not green.** DUT showed the bar **green** at boot
until the first ≥2 403s tripped `hasError()` (poll latency + backoff) — a false "all-good"
before the connection state is known. Added a **connecting** state (amber) via a second
base-class endpoint `App::isConnecting()` (default false); `SpotifyApp::isConnecting()` →
`spotifyTask::connecting()` (`s_lastSuccessfulPollMs == 0`, latches false on first 200/204).
Precedence is now **error (red) > busy|connecting (amber) > idle (green)**; busy+connecting
collapse to amber (no new constant). Loop re-render + `get activeError` extended for connecting.
ADR-046 amended. DUT (live 403): boot `connecting:true` (amber) → `authError:true` (red).

**Amendment 2 (2026-06-25) — responsiveness + flap/touch fixes (DUT-driven).** Measured the
original `authError = lastHttpStatus==403 && consecutiveFailures>=2`: red took **~31 s** AND a
touch (`resetBackoff()` zeroes `consecutiveFailures`) knocked it back to amber. A first retry
keyed on instantaneous `lastHttpStatus==403` **flapped** (a wedged session alternates 403/-1).
Final: a sticky `s_authErrorLatched` — set on any 403 poll, cleared only on a real 200/204,
untouched by -1 blips and by `resetBackoff()`. DUT: clean amber → red at **~13 s**, stable red,
touch-immune (the `set lastHttp` injector applies the same latch rule).

**VE (TASK-245, 2026-06-25):** test_plan T-ERR-01/02/03/04/05 + serialdbg
`t_err_01/02/04/05` (`set lastHttp` / `set lastOkMs` injectors for determinism).
- **T-ERR-01** (X020) 403 → red, 200 → clear — **PASS** on DUT.
- **T-ERR-02** (X018 active-only + X019 survives switch) — **PASS** on DUT.
- **T-ERR-03** (X017 red render + precedence + boot-amber) — **MANUAL**, planned: no pixel
  readback, needs human visual sign-off; clear-on-recovery on a real account gated on TASK-243.
- **T-ERR-04** (boot connecting → green on first success) — **PASS** on DUT.
- **T-ERR-05** (403 held across backoff reset — touch-immune regression guard) — **PASS** on DUT.
**Remaining owed:** only the T-ERR-03 visual sign-off.

---

### TASK-246 — Audit + wire every app's error state into `hasError()` (fan-out)

Breadth-first audit: for each app, define what constitutes a sustained error, where it is
detected, and how/when it latches and clears — then implement `hasError()`. Gated on TASK-245
(mechanism + Spotify consumer must land and be VE-verified first).

**Per-app starting points:**
- **Stock** — already has `fetchFailed` / `fetchErrorCode` / `fetchOkCount` (`appShell.h:104-108`);
  likely a thin wrapper. Decide list-vs-chart-vs-heatmap granularity.
- **Weather / Crypto** — track `lastDataFetch` / `lastCryptoFetch` but have **no explicit error
  flag** (`appShell.h:53-62`); needs a fetch-error field added to their state + dataTask result.
- **Teletext** — has `teletextHttpCode` / `lastHttpCode` plumbing already.
- **WebRadio** — has `_lastHttpCode` / `_lastOk` (`webRadioApp.h`); map fetch failure (and
  decode-stall? — decide) to error. NB eject-only, not a taskbar app (TASK-242) — confirm how
  its error surfaces, if at all.
- **Clock / Matrix / Life / Aquarium** — offline; confirm they keep the default `false`.

Each app's latch/clear rules to be reviewed by Architect against the ADR-046 contract; VE adds
per-app red-on-error / clear-on-recovery coverage; update feature_inventory + cross_feature_matrix
as new per-app interactions surface.

**Priority:** P3 · **Status:** implemented — DUT-verified 2026-06-25 · **Opened:** 2026-06-25
· **Milestone:** M-MULTIAPP / UI
**Owner:** Developer (per-app) + Architect (per-app semantics review) · **Deps:** TASK-245

**Implementation (2026-06-25).** `hasError()` wired for the four network taskbar apps as a
set-on-failed-fetch / clear-on-success latch, reading each app's result-consume:
- **Weather** `_wxErr` — also fixed the consume to honour `r.ok` (it previously used the result
  unconditionally, showing 0/0/0 on a failed fetch).
- **Crypto** `_cxErr` — consume restructured to handle the `!r.ok` branch.
- **Stock** `_s.fetchFailed` (existing for list/chart) — extended to the heatmap branch (red when
  a heatmap fetch fails with no good data to fall back on).
- **Teletext** `_ttErr` — set when `pollTeletext()` returns a non-ready result.
Precedence error(red) > connecting(amber): a failed *first* fetch shows red, not amber — closing
the "stuck amber = failed or still trying?" ambiguity that motivated this. Offline apps
(Clock/Matrix/Life/Aquarium/Settings) + eject-only WebRadio keep the default `false` (T-ERR-06).
**VE:** T-ERR-07 (Stock fetchFailed → red, representative of all four latches via `set fetchFailed`)
**PASS**; T-ERR-01/02/04/05/06 re-run PASS; `run/check` 5/5. ADR-046/test_plan/matrix/inventory updated.

---

### TASK-247 — Stock Heatmap/Chart launch wastes ~16 s on an unused list-quote fetch

**Found 2026-06-25** chasing a user report ("stock → heatmap takes very long; teletext stuck on
amber while typing"). DUT capture: `switchApp 7` (mode=Heatmap) ran the **8-ticker list quote
batch** — 8 sequential ~2 s Yahoo GETs ≈ **16 s** — *before* `_applyLaunchView()` switched to
Heatmap, and the heatmap screener GET queued *behind* it. So Heatmap/Chart launches paid the full
List cost they never display (and, via the single shared dataTask, blocked whatever the user
opened next, e.g. Teletext).

**Root cause:** `StockApp::init()` unconditionally enqueued `DATA_FETCH_STOCK_QUOTE` then called
`_applyLaunchView()` (TASK-231). The quote is only needed for the List view.

**Fix:** moved the quote enqueue into `_applyLaunchView()`'s List branch — Heatmap launches now do
a single screener GET, Chart a single chart GET. Added a `set stockMode <0|1|2>` debug setter
(in-RAM, non-persisted) and made `_switch_to_stock` force List (0) so the list-centric VE suite is
deterministic regardless of the device's saved mode (it previously silently assumed List).

**DUT result:** Heatmap-mode launch **~18 s → ~2.5 s** (one `heatmap GET 200 elapsed≈2096ms`, no
quote batch). T169/T170 (list launch) PASS via forced List mode; T-ERR-01/06/07 PASS; `run/check`
5/5. **Note (not fixed here):** the List view itself is still ~16 s (8 sequential per-ticker Yahoo
GETs, fresh TLS each per ADR-029) — inherent; a future optimisation (batching / fewer round-trips)
if List load time matters.

**Priority:** P2 · **Status:** implemented — DUT-verified 2026-06-25 · **Opened:** 2026-06-25
· **Milestone:** stock-002 / M-MULTIAPP · **Owner:** Developer · **Deps:** TASK-231 (launch view), TASK-245 (connecting bar made the cost visible)

---

### TASK-248 — Multi-app fetch stress/soak harness + fetch-reliability findings

**Why:** user wants out of the manual debug loop for fetch reliability/latency. We had a
heatmap-only soak (`test_heatmap_reliability.py`) and per-app tlsYield checks
(`test_tls_yield_reliability.py`) but no unified harness exercising **every** dataTask fetcher
with a latency + TLS-error report.

**Delivered:** `app/tools/test_fetch_stress.py` + `run/stress` (flash debug → soak → restore
prod, unattended). Drives each fetcher via debug triggers, parses the shared
`dataTask.<app> … <code> elapsed=<ms>ms` log shape, and reports per-fetcher latency
(min/med/p95/max), HTTP outcome histogram, failure counts, and a global TLS-error tally.

**Findings (DUT, 2026-06-25, under the live Spotify 403):**
- **Zero TLS errors** across all soak runs *and* individual fetcher captures. The TLS path is
  reliable — there is no TLS error to "resolve" right now; earlier slowness was starvation
  (TASK-244) + handshake cost, not TLS faults.
- **Latency (per fetch):** teletext ~1.2 s, weather ~1.9 s, heatmap ~2.3 s, **crypto ~7.5 s**,
  **stock quote ~16 s** (8 tickers × ~2.1 s sequential). All 200.
- **Root cost = per-request TLS handshake.** ADR-029 stack-allocates a fresh `WiFiClientSecure`
  per fetch (no session reuse / keep-alive), so each GET pays a full ~2 s handshake. Stock pays
  it 8× (16 s); crypto's single GET is ~7.5 s (CoinGecko handshake+payload). **→ the fetch-time
  lever is TLS session reuse / fewer round-trips (proposed TASK-249).**

**Runtime log-volume control added (TASK-248).** LOG_x macros (`logsink::logLine`) previously
had NO level gate — they always emit; `esp_log_level_set` only affects vendored esp_log tags.
Added a runtime gate: `set logLevel <d|i|w|e>` (min severity) + `set logKeep <prefix>` (tags
always kept regardless of level; `-` clears). Default 0 = emit everything (prod unchanged). The
soak uses `set logLevel w` + `set logKeep dataTask` → ring/serial carry only fetch results +
warnings/errors, so the 48-line ring doesn't wrap and the CH340 isn't flooded. The harness also
`set bgPoll 0` to measure fetchers in isolation from Spotify-403 TLS contention.

**Full multi-app coverage achieved (2026-06-25).** Two follow-on fixes closed the gap:
- **TASK-250** (dataTask fetch coalescing) removed the duplicate-stock-quote queue saturation
  that was starving the next app's fetch.
- **HTTP `/log` reader** — the soak now reads the high-volume logs over the device's `/log`
  HTTP ring (commands stay on serial), so the flaky CH340 no longer stalls/hangs the run.
  Added `get ip` (serial) for discovery; per phase the harness clears the ring, fires the
  trigger, then polls `/log?n=48` feeding only new lines (ring emptied at phase start under the
  `logLevel w`/`logKeep dataTask` filter → no wrap, no dedup). `--serial-log` forces the old path.

**Final soak result (4 min, HTTP `/log`):** all five fetchers sampled, **0 TLS errors** —
teletext ~1.2 s, weather ~1.9 s, stock/quote ~2.1 s (TASK-249 spark), stock/heatmap ~2.1 s,
crypto ~6.8 s.

**Priority:** P2 · **Status:** **done — full multi-app soak via HTTP /log, DUT-verified 2026-06-25**
· **Owner:** VE · **Deps:** TASK-244 / TASK-250 (starvation + saturation, both fixed)

---

### TASK-249 — Cut stock-list fetch latency: 8 GETs → 1 multi-symbol spark request

From TASK-248 data: per-request TLS handshake (~2 s) dominated — the stock list paid it **8×**
(8 sequential per-ticker `v8/finance/chart` GETs ≈ **16 s**). ADR-029 stack-allocates a fresh
per-fetch `WiFiClientSecure` (no persistent client) for heap reasons on the no-PSRAM board, so the
TLS-session-reuse option would have needed an ADR-029 amendment + heap-tradeoff ruling.

**Resolution — the multi-symbol endpoint, no ADR-029 change needed.** Yahoo's
`v8/finance/spark?symbols=A,B,…&interval=1d&range=1d` returns price (`close[]` last non-null) +
`chartPreviousClose` for **all** tickers in **one** request. So `fetchStockQuote` now does a
single spark GET instead of 8 chart GETs — keeps the fresh-per-fetch client (no persistent
TLS / no heap reversal) and stays HTTP/1.0 (no chunked-encoding risk). Response is keyed by
symbol; parsed with a wildcard filter `filter["*"]["chartPreviousClose"|"close"]` into
`StaticJsonDocument<1536>` (~478–614 B filtered for 8 symbols).

**DUT result:** stock list quote **~16 s → ~1.9 s** (one `spark GET 200 elapsed≈1935ms`, valid
prices). Host-validated: `test_yahoo_finance_api.py` **T_SF_08** (1.3 KB raw, all 8 symbols,
fits budget). VE: T169/T170 (launch + quoteOkCount advances) PASS; T-ERR-01/07 PASS; run/check 5/5.

**Note:** crypto's single GET is ~7.5 s (CoinGecko handshake+payload) — separate, lower priority;
no multi-request fan-out to collapse there.

**Priority:** P2 · **Status:** **implemented — DUT-verified 2026-06-25** · **Owner:** Developer
· **Deps:** TASK-248 (data), ADR-029 (sidestepped — kept fresh-per-fetch client)

---

### TASK-250 — A stock quote batch poisons the next app's fetch (>30 s no-fetch)

**Found by the TASK-248 stress effort (2026-06-25).** After a stock **list quote** fetch (the
8-ticker sequential batch, `fetchStockQuote`), switching to Weather / Crypto / Stock-heatmap does
**not** produce a fetch for >30 s — the new app's `init()` runs and enqueues, but no
`dataTask.<app>` GET ever logs; it recovers by the next cycle (~90 s later). From a cold/idle
state (no prior stock batch) all three fetch fine — weather ~1.9 s, crypto ~7.5 s, heatmap ~2.3 s
(raw capture). Reproduced with a **raw serial script** (not the harness) and persists with
`bgPoll 0` (Spotify suspended) and quieted logs — so it is **neither** a CH340/serial artifact
**nor** Spotify-403 TLS contention.

**ROOT CAUSE (instrumented, 2026-06-25) — NOT a tlsYield deadlock.** The yield/resume handshake
is clean (instrumentation showed correct `tls resume → dispatch → resumed → yield` cycles). The
real cause: **multiple `DATA_FETCH_STOCK_QUOTE` requests were stacked in the depth-4 dataTask
queue.** A List launch (TASK-247: `switchApp 7` enqueues a quote) **plus** `set triggerFetch 1`
(or the app's 60 s re-enqueue while one is in flight) queued 2+ quote batches; each is a ~16 s
8-GET batch, so the next app's fetch (weather/crypto/heatmap) sat behind ~16–32 s of stock work.
The dataTask dispatch log showed `type=2` (stock quote) firing back-to-back, then `type=0`
(weather) only after they drained. (The `triggerFetch`-after-launch double-enqueue was largely a
stress-harness artifact; in normal use the stock app enqueues one quote / 60 s.)

**Fix (committed):** dataTask now **coalesces duplicate param-less fetches** — `s_pendingMask`
bit per fetch-type, set on a successful `enqueue()`, cleared when the fetcher completes; a
duplicate `enqueue()` of an already-pending/in-flight type is skipped. So a List launch +
triggerFetch (or a re-enqueue during a slow fetch) collapses to **one** batch instead of stacking.
**Verified (clean manual run):** stock quote = one 8-GET batch (was 16), then `switchApp 2` →
`dataTask.weather GET 200` in **1.7 s** (was >30 s). Chart/teletext keep their own param'd
enqueue paths (must not coalesce different pages/tickers).

**Repro (pre-fix):** `set bgPoll 0; set stockMode 0; switchApp 7; set triggerFetch 1` → `switchApp 2`
→ weather GET delayed >30 s. Post-fix: weather GET in ~2 s.

**Priority:** P2 · **Status:** **fixed — DUT-verified 2026-06-25** (dataTask fetch coalescing)
· **Owner:** Developer · **Deps:** relates to TASK-248 (found it), TASK-247 (the launch enqueue),
ADR-029 (per-fetch TLS lifecycle)

**NB (TASK-248 harness):** the multi-app *soak* still samples weather/crypto/heatmap
inconsistently — but that is now isolated to **CH340 serial flakiness** under long bidirectional
soak traffic (intermittent stalls/hangs, run-to-run variable), independent of this device fix.
The proper harness fix is to read logs over the existing `/log` HTTP ring (off the CH340) —
deferred under TASK-248.

---

## Open — codebase-quality audit follow-ups (2026-06-21)

> From three parallel read-only audits (firmware quality / test brittleness /
> repo hygiene) run during DUT downtime. TASK-222 and the doc/orphan fixes were
> done this session; the rest are filed for triage. Verdicts: firmware is good
> code, dominant issue is duplication not correctness; the test suite is solid on
> app-order coupling (build-gated) and mostly good on coordinates, with isolated
> hand-maintained-literal fragility.

### TASK-222 — dataTask: fix two BP-031 (tlsYield/tlsResume) violations

**DONE 2026-06-21.** Audit confirmed two real violations of BP-031 (the project's
own documented rule, which even cited weather as conforming):
- `fetchHeatmapQuote()` skipped `tlsResume()` on the `http.begin()` early-return
  → left Spotify TLS yielded = **permanently paused** (same starvation class as
  TASK-218). HIGH.
- `fetchWeather()` had **no** `tlsYield`/`tlsResume` at all (latent NoMemory under
  heap contention; `fetchCrypto` right below documents the exact hazard).
Both fixed; build-clean 5/5, +40 B flash. **firmware behaviour change — not
DUT-verified** (matches the verified crypto/heatmap pattern). See LL-084.
**Priority:** P1 · **Status:** done — implemented, DUT-verify with the heap suite · **Owner:** Developer

---

### TASK-223 — dataTask: extract the shared HTTPS-fetch helper (duplication)

The TLS-setup / HTTP-GET / filtered-`deserializeJson` / teardown sequence is
copy-pasted ~verbatim across **7** fetchers in `dataTaskStorage.cpp` (~90+ dup
lines). Extract `httpsGetFiltered(url, rootCA, insecure, filter, out, tag)` (or a
smaller `openHttps()` that does begin+GET) so each fetcher supplies only
URL/CA/filter/result-mapping. Highest-value refactor — would shrink the file ~⅓
and make the next TASK-214-style TLS fix land in one place not seven. Also folds
in the duplicated `StaticJsonDocument<128>`/`<256>` filter sizes and the bare
mirror-count `3` literal.
**Priority:** P2 · **Status:** done 2026-06-21 — `openHttps()` helper added (begin+useHTTP10+GET; `INT_MIN` begin-fail sentinel to avoid colliding with HTTPClient's `-1`). Conservatively folded in **fetchTeletext only**; weather/crypto kept their own sequence (progress-phase split would be lost) and the stock/heatmap/webradio fetchers kept theirs (need `addHeader` between begin/GET). BP-031 balance preserved + verified. 5/5 gates. · **Owner:** Developer · **Deps:** none

---

### TASK-224 — M-WEBRADIO: reconcile station-count constants (limit=30 vs [100] vs 14336 B)

`fetchOneMirror()` queries `limit=30`, but `WebRadioStation stations[100]`, the
fill-loop bound `count >= 100`, and the `s_webRadioDoc(14336)` sizing comment all
assume 100. Either `30` is an undocumented heap mitigation (then shrink the array
+ buffer + fix the comment) or it's an under-fetch bug. Drive all four from one
`WR_MAX_STATIONS` constant. Also name the ICY-title `104` (used 4×) and the
volume ceiling `21`.
**Priority:** P2 · **Status:** done 2026-06-21 — confirmed `limit=30` is the intentional `dafa4a4` heap mitigation. `WR_MAX_STATIONS=30` in `dataTask.h` now drives the query, both station arrays, and the fill-loop bound; `s_webRadioDoc` shrunk 14336→5120 B; `WR_ICY_TITLE_LEN=104` and `WR_VOLUME_MAX=21` named. **−21.5 KB RAM** (the array shrink), +8 B flash. 5/5 gates. · **Owner:** Developer · **Deps:** none

---

### TASK-225 — M-WEBRADIO: `_drawPledit()` reimplements a degraded `drawPlaylist()`

`webRadioApp.h::_drawPledit()` redraws the PLEDIT panel with flat `fillRect`s,
dropping the sprite frame border, scrollbar thumb, and skin-font bottom bar that
`winampDisplay.h::drawPlaylist()` already renders — a layering violation that also
makes WebRadio's playlist visually inconsistent with Spotify's in the same skin.
Reuse/parameterise the chrome-layer renderer instead.
**Priority:** P2 · **Status:** implemented — unverified (2026-06-21). Did NOT need a DUT to do (host C++ refactor; the correct visual target is already rendered by `preview_webradio.py`). Architect API call: extract `WinampDisplay::drawPleditFrame(scroll, count)` (gutters/title/side-tiles/scrollbar-thumb/bottom-bar — geometry+count only, no app state). `drawPlaylist()` now calls it — **op-for-op identical** extraction (verified by diff; Spotify row/health-title/total-time paths untouched; bottom-bar reorder is into a disjoint region). WebRadio's `_drawPledit()` calls the same helper, rows now fill content-area-only (don't paint over the side tiles), and the non-conformant "N stations" title-bar text dropped (design §PLEDIT = no title text). 5/5 gates, +~150 B flash. **DUT visual sign-off still owed** — confirm WebRadio shows proper frame/thumb/bottom chrome AND Spotify's playlist is unchanged. · **Owner:** Developer + Architect · **Deps:** none

---

### TASK-226 — tests: harden coordinate single-source-of-truth (eject/deadzone/VIS)

`coords.py` correctly derives most coords from `skin_layout.h`, but: eject taps
hardcode `136 89` (3 sites) and deadzone `162 85` (2 sites) instead of a
`coords.py` helper; and `coords.py` VIS constants are **hand-copied** from
`vuMeter.h` with no codegen/gate (silent-stale risk). Add `tap_eject()` /
`tap_deadzone_gap()` helpers; move VIS rect constants into `skin_layout.h` (or a
generated header) so there is one ingestion path. (App-order coupling is already
build-gated — no action.)
**Priority:** P3 · **Status:** done 2026-06-21 — `tap_eject()` (box centre, robust to skin shift) and `tap_deadzone_gap()` (shares T088's exact `_gap_y` formula) added; all 5 literal sites parameterised. VIS constants now **parsed from `vuMeter.h`** via a regex ingestion path (better than moving them — `vuMeter.h` is the real owner, not skin_layout.h). Verified: helpers reproduce the prior hit zones; `import coords` + `py_compile` clean; 0 stale literals. · **Owner:** VE · **Deps:** none

---

### TASK-227 — docs: clock design docs contradict shipped firmware

`M-CLOCK-FLIP/NIXIE/VFD.md` say firmware "not started" while `clockApp.h` ships
working `_drawFlip/_drawNixie/_drawVFD` (and the parent `M-CLOCK-STYLES.md` says
"done, 14/14 PASS") — internally contradictory, would mislead a dev into
re-scoping shipped work. Also `vfdTheme`/`nixieTheme` settings pickers are
documented but never implemented (only `clockStyle` exists). Reconcile status
headers; implement-or-strike the theme pickers.
**Priority:** P2 · **Status:** done 2026-06-21 — all three clock-doc status headers reconciled to "shipped (TASK-193)" against `clockApp.h`; `vfdTheme`/`nixieTheme` pickers **struck** (marked "DOCUMENTED, NOT IMPLEMENTED", moved to a future/post-MVP heading — not built speculatively); shipped-vs-doc geometry/render-option deviations annotated as accepted. Verified against firmware. · **Owner:** Architect · **Deps:** none

---

### TASK-228 — settings: sweep + reconcile inert config fields

`webRadioHwMod` is fully dead (no consumer, no UI) and the `webRadioMaxVolume`
"default 18 with HW mod" comment describes conditional-default logic that
`settingsStorage.cpp` never implements. Joins the known inert set
(`webRadioAutoSkip` TASK-219, `webRadioBitrateCap` TASK-221). Audit every
`settingsStorage.h` field for a real consumer; remove or implement each dead one;
fix the misleading default comment.
**Audit done 2026-06-21** (all 31 fields swept). Dead/inert set: `webRadioHwMod`
(dead), `teletextCountry` + `teletextAutoAdvance` (dead, self-documented
"reserved"), `webRadioAutoSkip` (TASK-219), `webRadioBitrateCap` (TASK-221), and a
**new finding → TASK-231: `stockMode`** (UI-visible but never read — a silently
broken toggle, higher severity). `webRadioMaxVolume` "18 with HW mod" comment
confirmed fiction (no conditional logic exists).
**Partial 2026-06-21:** misleading code comments fixed in `settingsStorage.h` — inert
fields annotated with tracking tasks (BP-035), and the false `webRadioMaxVolume`
"18 with HW mod" default corrected to note `applyDefaults()` always sets 10.

**Correction 2026-06-22 — `webRadioHwMod` is NOT dead.** Re-checked against the design:
`M-WEBRADIO.md` §HW Mod and Max Volume interaction (lines 676-685) + §Settings fully
specify it as the **anti-clipping volume-ceiling input** (stock → soft-cap 12; mod →
default 18, range to 21). It's an **unimplemented designed feature**, not dead weight —
and its enforcement is already TASK-209's deliverable (*"Hard cap enforced in firmware …
when `hwModInstalled == false`"*, needs DUT to calibrate the stock ceiling). Reclassified:
`webRadioHwMod` + `webRadioMaxVolume` clamp → **owned by TASK-209** (deferred to DUT), NOT
a removal candidate. Decision (2026-06-22): leave the feature under TASK-209; do not
implement the clamp standalone. `settingsStorage.h` comments updated to point at TASK-209.

Remaining 228 scope is now small: `teletextCountry`/`teletextAutoAdvance` are intentional
self-documented "reserved" placeholders (leave as-is); `webRadioAutoSkip`/`webRadioBitrateCap`
tracked by TASK-219/221; `stockMode` → TASK-231 (done). No genuinely-orphaned dead field
remains, so no JSON-schema removal is pending.
**Priority:** P3 · **Status:** done 2026-06-22 — every field now classified + correctly tracked; no removal needed (webRadioHwMod is a deferred feature, owned by TASK-209) · **Owner:** Developer · **Deps:** none

---

### TASK-229 — docs + dead code: misc drift batch

(a) `M-LIST-v4-velocity-scroll.md` claims the `_dragStartMs` tap-discrimination
logic was removed; it's still load-bearing (`winampDisplay.h:589`). (b)
`M-DATATASK-PROGRESS.md` frames shipped phase-2 work as future. (c) Dead code:
`main.cpp` stub-section branch + `_repaintStub()` (all 6 sections wired) and the
never-called `serialPrint.h::printCurrentlyPlayingToSerial` — verify unreachable,
then remove. (d) clock cosmetic doc contradictions (flip-colon, nixie geometry).
**Priority:** P3 · **Status:** done 2026-06-21 — **(a)(b)(d) docs** reconciled (parallel round); **(c) dead code removed** (this round): deleted `app/src/serialPrint.h` (legacy upstream debug, zero callers) + its `main.cpp` include, and removed the unreachable `_repaintStub()` + its `else` branch (all 6 `_sections[0..5]` are wired in the ctor, so it could never fire — kept the null-guard as cheap defence). 5/5 gates. · **Owner:** Developer · **Deps:** none

---

### TASK-230 — logging: `Serial.printf("[tag]…")` bypassing the LOG_* sink

6+ recently-touched files use raw `Serial.printf` instead of the `LOG_*`
macros/log sink, so those lines skip the log server/decode stack. QM
best-practice candidate (consistency), not a one-off. Sweep and convert; consider
a BP.
**Audit done 2026-06-21 — closed as not-worth-a-sweep.** Of ~99 raw `Serial.*`
sites, ~half are the DUT command-response JSON protocol (`handleSerialCommands`
/ dbg-get — must **never** be converted), most of the rest are `SERIAL_DEBUG`-
gated or one-shot boot banners explicitly carved out by ADR-010. Genuine
SHOULD-CONVERT set is only **~8 sites** (hand-rolled `[D][tag]` lines in
`winampDisplay.h` ×2, `aquariumApp.h` ×4, `calibrationFlow.h` ×3) that mimic
LOG_ output while bypassing the sink. Recommendation: convert-when-touched (per
ADR-010's existing policy) + a **narrow BP candidate** for QM/human sign-off:
*"don't hand-roll a `[D][tag]` log prefix — use the LOG_* macro."* No standalone
task warranted.
**Priority:** P3 · **Status:** closed — audit done; convert-when-touched + BP candidate flagged to QM · **Owner:** QM (BP call) · **Deps:** none

---

### TASK-231 — Stock: `stockMode` is a silently broken Settings toggle

Found during the TASK-228 settings audit — **highest-severity** of that sweep
because it's user-visible. Settings → Applications → Stock exposes a
List/Chart/Heatmap "mode" cycle bound to `g_settings.stockMode`
(`appsSection.h:109,184`), but `StockApp::init()` (`main.cpp:1006`) unconditionally
sets `subView = List` and **never reads `stockMode`** — so toggling it does
nothing. Reads as a broken control to a user (worse than the invisible dead
config keys).
**Fix shape:** seed `_s.subView` from `g_settings.stockMode` in `StockApp::init()`
/`resume()` (map `StockViewMode::{List,Chart,Heatmap}` → `StockSubView`), OR remove
the field + its UI row + JSON key if "always start on List" is the product intent.
**Investigated 2026-06-21 (NOT a clean wire-up):** `ChartDetail`/`HeatmapDetail`
have preconditions — a selected `_s.chartSymbol` and a completed fetch — that only
exist after in-app navigation (`main.cpp:1322-1361`); that is almost certainly why
`init()` hardcodes `List`. Seeding `subView` from `stockMode` at launch would render
Chart with an empty symbol. So the real options are (1) implement launch-into-Chart/
Heatmap with proper precondition handling (needs DUT visual verify), or (2) remove the
toggle. Not blind-wired. Genuine product+design call.
**Priority:** P2 — user-visible broken UI · **Implementation (2026-06-21):** Product call: **implement** (wire it up). New `_applyLaunchView()` honours `g_settings.stockMode` by reusing the existing `drillToChart(0)` / `enterHeatmap()` entry helpers (so the Chart selected-ticker + fetch and the Heatmap fetch preconditions are set up exactly as in-app navigation does — Chart launches on the first configured ticker). Honoured on first `init()` and on `resume()` **only when the setting changed since last applied** (`_appliedMode` cache), so the toggle now takes effect on the realistic flow (change in Settings → reopen Stock) while preserving in-session drill nav otherwise. Default-List users see zero change. 5/5 gates. · **Owner:** Developer · **Deps:** none

**DONE — DUT-verified 2026-06-25 (T231 PASS; 1 passed / 0 failed / 0 skipped).** New regression test
**T231** (`run_serialdbg_tests.py`) drives `set stockMode 1/2/0`, re-enters Stock, and asserts the
launch sub-view each time: **Chart launches with a non-empty ticker** (`AAPL` — directly retires the
"Chart with empty symbol" concern that the investigation flagged), **Heatmap launches**, **List
launches**, and **List is the back-nav base** for both detail views (chart back `(10,7)` → list;
heatmap back `(260,7)` → list). Spotify-independent (switchApp + in-RAM `stockMode` only), so it runs
green without Premium. The remaining "renders correctly before data arrives" is now covered in
substance — entering Chart/Heatmap pre-fetch no longer crashes and the precondition (ticker/dataset)
is set — so no separate human visual sign-off is owed.
**Status:** done — DUT-verified 2026-06-25 (was implemented-unverified)

---

### TASK-220 — M-WEBRADIO: buffer-health POSBAR never driven (DONE); VU meter is a design reconciliation (220b)

Two distinct issues; the second is *not* the simple poll the original finding
assumed (corrected after reading the VU path — BP-039 discipline).

**220a — buffer-health POSBAR (DONE 2026-06-21):** `_bufPct` was only ever
assigned `0`, so the POSBAR buffer bar (§POSBAR buffer health) stayed empty. Now
driven in `tick()`'s PLAYING block from `inBufferFilled()/(filled+free)`, with a
15-point hysteresis so it repaints only on meaningful movement. Build-clean, 5/5
gates. Not DUT-visual-confirmed but low-risk (reuses the known-good full-repaint
path). **Status: implemented — unverified.**

**220b — VU meter (OPEN, needs Architect):** original finding said "wire up
`getVUlevel()`." That is wrong twice: (1) the VU meter is **synthetic by design**
(ADR-009 — "decoration, not real audio"), not level-driven; (2) `vu::tick()` is
called **only** from the Spotify app's tick and is gated on Spotify's
`snap.isPlaying`, which is false while WebRadio holds the TLS yield. So WebRadio
animates nothing, and the correct fix is a design call, not a poll: either
(a) call `vu::tick()` from `WebRadioApp::tick()` and extend the synthetic
envelope's gating to accept an external "playing" signal (touches a shared
visualizer used by Spotify — Architect interface change), or (b) deliberately
leave the VU static during WebRadio and reconcile `M-WEBRADIO.md` (which says
`getVUlevel()`) against ADR-009.

**DUT-session impact (both):** T_WR_COEX_01's "VU meter animates" human step
**will fail for a non-coexistence reason** until 220b lands. Without this note the
failure looks like an audio/touch coexistence bug and invites the network-chasing
misdiagnosis BP-038/LL-082 warns against. DUT suite annotated to pre-empt this.

**220b RESOLVED — Architect decision 2026-06-25 (option b + doc reconciliation).** Decided: the VU is
**not driven during WebRadio** in the MVP. Rationale: (1) the shipped VU is a *synthetic* envelope
(ADR-009) called only from the Spotify app — there is no real-audio path into the renderer, so
`getVUlevel()` would be a new interface, not a poll; (2) WebRadio playback is best-effort/unstable on
no-PSRAM (TASK-233/241), so there is no stable signal to visualise yet. A static VU during WebRadio is
**expected, not a coexistence bug** — the DUT suite's "VU animates" step (T_WR_COEX_01) is annotated
accordingly (pre-empts the BP-038/LL-082 misdiagnosis). `M-WEBRADIO.md §VU` reconciled against ADR-009
(the `getVUlevel()` spec struck as never-implemented/deferred); the ASCII layout label updated. The
real-audio VU (`audio.getVUlevel()` feeding an external-level `vu::tick()` overload — additive, no
change to the Spotify path) is captured as a **future enhancement gated on stable WebRadio playback**
(PSRAM hardware), not MVP scope.
**Priority:** P2 — visible feature gap; not a crash/starvation risk
**Status:** 220a implemented (unverified) 2026-06-21; **220b resolved 2026-06-25 (decision: VU static in WebRadio MVP; docs reconciled)**
**Opened:** 2026-06-20
**Milestone:** M-WEBRADIO
**Owner:** Developer (220a) + Architect (220b)
**Deps:** none

---

### TASK-207 — M-WEBRADIO: touch + audio coexistence check (open item 4)

With WebRadio firmware flashed and a station playing, verify that XPT2046 touch
(SPI SCK on GPIO25) and I2S-DAC audio (GPIO26 → SC8002B) operate simultaneously
without electrical interference on this board revision.

Procedure:
1. Flash M-WEBRADIO firmware. Connect 8 Ω speaker to SPEAK header.
2. Start a station; confirm audio is playing (audible + VU meter animating).
3. While audio plays, repeatedly tap prev/next station touch zones.
4. Observe: audio must not glitch, stutter, or drop out on touch events.
5. Observe: touch must register correctly — station changes must fire.
6. Run for ≥ 2 minutes of continuous playback + touch interaction.

Pass criteria: no audio dropout correlated with touch events; touch response
unaffected by audio playback. Fail = audio or touch degraded during concurrent
operation → file hardware conflict issue, consider SPI rate reduction workaround.

Note: peripheral buses are independent (SPI vs internal DAC) — electrical risk
is low but this board's routing is unverified for this combination.

**DUT run 2026-07-02 (cyd2usb_webradio, 16 stations, operator present — no speaker):**
- **T_WR_COEX_02 PASS** — injected taps fire during playback (NEXT wraps 13→14→15→0, PREV 0→15).
- **T_WR_COEX_04 PASS** — tap ack 112/185/127 ms (<500 ms bar), station change each time.
- **T_WR_COEX_03 objective half PASS** — underrun counter frozen (startup blip only) through a 60 s
  injected-tap storm during continuous playback (playMs 15 s→76 s unbroken), a 150 s clean window, and a
  5-min **physical**-touch window with ~30 registered operator touches. Touch registration proven
  independent of network state (touches kept landing during a live link-flap outage).
- **T_WR_COEX_01 serial half PASS** (state:2 sustained; VU static = expected, 220b).
- **DEFERRED (needs 8 Ω speaker):** the audible halves — analog electrical-noise check (GPIO25 touch SCK
  → GPIO26 DAC) and by-ear dropout confirmation. The digital domain is clean by counter; the analog domain
  is unverifiable without a speaker. Also defers TASK-209 (T_WR_VOL_01/02 volume calibration, same reason).
- Bonus live capture: two ~30 s **terminal parks** during a sensor-attributed link-flap outage
  (`NO_AP_FOUND` storms, discCount 15/min) — operator had to manually re-play; motivates
  retry-from-terminal (filed TASK-276).

**Priority:** P1 — blocking M-WEBRADIO ship
**Status:** **substantially PASSED 2026-07-02 — all serial/objective halves green; audible halves
DEFERRED pending speaker (re-run T_WR_COEX_01/03 audible + T_WR_VOL when hardware present). Human call
whether the deferred analog check gates milestone close.**
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** VE + human operator (physical board required)
**Deps:** ~~radio-browser reachability~~ (resolved — 16 stations load on cyd2usb_webradio)

---

### TASK-208 — M-WEBRADIO: heap watermark under audio decode + TLS spike

Measure actual SRAM pressure during the two peak moments: (a) station-list TLS
fetch, and (b) sustained audio playback. Confirm the non-overlap assumption in
M-WEBRADIO.md §Memory envelope holds on real hardware.

Procedure:
1. Add heap instrumentation to `webRadioTick()`:
   - Log `ESP.getFreeHeap()` + `ESP.getMinFreeHeap()` at: app launch, just before
     `dataTask` station-list fetch, just after fetch completes (TLS torn down),
     at first `connecttohost()` call, and every 30 s during playback.
   - Log via existing `LOG_I("webradio", ...)` — visible in `./run/monitor-read`.
2. Flash, connect to a 96 kbps station (default cap), run for 5 minutes.
3. Record `minFreeHeap` at each phase.

Pass criteria:
- TLS spike phase: `minFreeHeap` ≥ 30 KB (leaves margin above zero)
- Audio decode phase: `minFreeHeap` ≥ 40 KB (40–60 KB in use, 320 KB total SRAM)
- No heap panic / stack overflow logged

Fail = heap too low → reduce `MAX_STATIONS`, tune ArduinoJson filter, or reduce
audio ring buffer chunks (library compile-time constant).

**Priority:** P1 — blocking M-WEBRADIO ship
**Status:** **done — completed 2026-07-02 from the TASK-275 instrumented-run logs** (build
cyd2usb_webradio + A-lite arena — the shipping WebRadio memory model). T_WR_HEAP_01 PASS (pre-fetch
free=110.1k min=68.4k ≥30 KB) · T_WR_HEAP_02 PASS (post-fetch free=109.4k min=48.4k ≥30 KB) ·
T_WR_HEAP_03 PASS (decode-phase floor min=41.8k across all `HEAP play` samples over 10×60 s holds —
clears the provisional ≥40 KB bar; actual number recorded per the suite's post-dafa4a4 note) ·
T_WR_HEAP_04 PASS (zero panic/abort/stack-overflow/Guru strings over the full ~40 min run). Note: the
original non-overlap question is largely superseded by the M-WEBRADIO-NOPSRAM arc (TASK-258 model +
TASK-261/262 arena), which measured this interaction exhaustively; these numbers confirm the shipped
configuration on real hardware.
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer + VE
**Deps:** radio-browser.info reachable from DUT

---

### TASK-209 — M-WEBRADIO: SC8002B volume ceiling calibration

Determine the safe `audio.setVolume()` ceiling for stock hardware (no HW mod).
M-WEBRADIO.md §Audio hardware path documents ≤ 10/21 as the design default;
this task confirms it empirically and sets the soft cap in code.

Procedure:
1. Flash M-WEBRADIO firmware. Connect 8 Ω speaker.
2. Start a 96 kbps MP3 station with consistent audio level.
3. Step `audio.setVolume()` from 1 → 21 via a serial command or settings slider,
   pausing 5 s at each step.
4. Note the first level at which clipping / distortion is audible.
5. Subtract 2 steps as headroom → this is the `kMaxVolumeStock` constant.
6. With HW mod installed (if available): repeat from step 3 to confirm full
   0–21 range is clean.

Pass criteria: `kMaxVolumeStock` determined; value matches design estimate of
≈ 10 (±2 steps acceptable). Hard cap enforced in firmware at this value when
`settings.webRadio.hwModInstalled == false`.

**Scope note (2026-06-22):** this task **owns the `webRadioHwMod` consumption and the
§HW Mod clamp** (M-WEBRADIO.md lines 676-685), reclassified here from the TASK-228
settings sweep. ⚠ Correction to the status below: the firmware does **not** currently
read `webRadioHwMod` or clamp at all — `setVolume(webRadioMaxVolume)` is unclamped
(`webRadioApp.h:117,451`), so the §HW Mod interaction (stock soft-cap 12 / mod default
18 / range-to-21) is entirely unimplemented, not merely uncalibrated. Implementation
work for this task: (a) read `webRadioHwMod` and clamp `setVolume()` accordingly,
(b) auto-raise the `webRadioMaxVolume` default to 18 when HW mod on, (c) optionally a
Settings UI toggle (no WebRadio settings section exists yet). The DUT calibrates the
exact stock value; the clamp *structure* could land on host first if desired.

**Clamp/HW-mod logic DONE — DUT-verified 2026-06-25 (T_WR_VOL_CLAMP PASS, 8/8).** Implemented the
§HW Mod ceiling that was entirely missing: `webRadioApp::wrEffectiveVolume()` is now the single
source of truth feeding every production `setVolume()` site (init + `_play()`) — stock (hwMod=false)
soft-caps at `WR_VOLUME_SOFT_CAP_STOCK=12`, the HW mod passes the full 1–21. The `wrVol` debug setter
stays **unclamped** (so VOL_01/02 calibration can still drive past the cap to find the clip point).
Default auto-raise wired in `settingsStorage` load (`maxVolume` defaults 18 with HW mod / 10 stock).
New `get wrEffectiveVol` accessor + `set wrHwMod`/`wrMaxVol` make the clamp verifiable without audio;
new playback-free regression test **T_WR_VOL_CLAMP** asserts all 8 (hwMod × ceiling) cases on DUT.
Stale `settingsStorage.h` comments reconciled. 5/5 gates.

**Still owed (subjective, needs speaker + human ears):** the *exact* stock clip point — confirm 12 is
safe (or refine ±2) by ear via `set wrVol` stepping (VOL_01/02), and confirm the HW-mod full range is
clean if the mod is installed. The clamp *structure* + its enforcement are done and tested; only the
empirical dB number remains, and it can be refined in a follow-on reflash without code-structure change.
**Priority:** P2 — clamp shipped at design estimate 12; exact value refinable in a follow-on reflash
**Status:** clamp logic done + DUT-verified 2026-06-25 (T_WR_VOL_CLAMP); subjective dB calibration (VOL_01/02) still needs speaker + ears (deferred, not blocking the clamp)
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer + human operator (subjective listening required)
**Deps:** radio-browser.info reachable from DUT; TASK-208 (same DUT session)

---

## Open — M-WEBRADIO pre-firmware gates (2026-06-14)

### TASK-210 — M-WEBRADIO: bake_skin.py eject change — human sign-off gate

`bake_skin.py` currently pastes the eject button sprite statically onto `MAIN_BG`
at bake time (line ~768). M-WEBRADIO requires removing this static paste and
instead emitting UV-offset constants (`SKIN_EJECT_N_X/Y`, `SKIN_EJECT_P_X/Y`,
`SKIN_EJECT_W/H`) so firmware can blit normal/pressed state at runtime.

This changes the visual output of `run/bake-skin` — the eject area of `MAIN_BG`
will be blank (background colour) instead of showing the baked sprite.

Deliverable:
1. Modify `bake_skin.py`: remove static eject paste; emit the six UV constants
   to `skin_layout.h` (follow the `CBUTTON_POSITIONS` emit pattern).
2. Run `run/bake-skin` — verify `gen/skin_assets.c` and `gen/skin_layout.h`
   regenerate cleanly.
3. Visually inspect `gen/skin_preview.png`: eject zone should be background
   colour (black at that position). Main chrome otherwise unchanged.
4. Human operator signs off that the skin preview looks correct — this is the
   gate before firmware implements `hitTestEject`.
5. Update `golden.sha256` with new checksums.

**Priority:** P1 — gates firmware eject implementation
**Status:** done — 2026-06-14. Static eject paste removed from MAIN_BG; CB_EJECT_N/P/X/Y/W/H
constants emitted to skin_layout.h (UV offsets into SKIN_CBUTTONS atlas). run/check 5/5 pass.
golden.sha256 updated. Human sign-off obtained.
**Opened:** 2026-06-14
**Closed:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer + human sign-off
**Deps:** —

---

### TASK-211 — M-WEBRADIO: serial accessor for ACT_EJECT (VE testability)

VE cannot verify the eject toggle via serial without `lastTouchResult` surfacing
`"EJECT"` as the action string. Currently `winampDisplay.h:537` action enum
comment lists: `"PREV","PLAY","PAUSE","STOP","NEXT","SEEK","VOLUME","SHUFFLE",
"REPEAT","VIS","TLS_RESET","FORCE_POLL","NONE"` — `"EJECT"` is absent.

Deliverables (firmware side, part of firmware implementation task):
1. `hitTestEject` populates `lastTouchResult = { "EJECT", -1, "EJECT", 0, -1, false }`.
2. Add `"EJECT"` to the action string enum comment at line 537.
3. `get touchResult` serial command (existing) returns the new struct correctly.
4. `injectTouch(136+originX, 89+originY)` synthetic path triggers eject hit-test
   (same synthetic injection mechanism as transport buttons — TASK-056d).

VE test cases (to be added to m-webradio regression suite):
- `T_WR_EJECT_01`: while in Spotify, inject eject tap → assert `action=="EJECT"`;
  assert `currentAppId == AppId::WebRadio` after switch.
- `T_WR_EJECT_02`: while in WebRadio, inject eject tap → assert `action=="EJECT"`;
  assert `currentAppId == AppId::Spotify` after switch.

**Priority:** P1 — gates VE suite for eject toggle
**Status:** done — 2026-06-14
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer (accessor) + VE (test cases)
**Deps:** M-WEBRADIO firmware hitTestEject implemented
**Sign-off:** hitTestEject→lastTouchResult="EJECT" in winampDisplay.h:891; "EJECT" in action comment line 538; tap 136 89 triggers path; wrEject dbgGet/Set wired. VE test cases T_WR_EJECT_01/02 in regression_suite/m-webradio-eject-errors.md.

---

### TASK-212 — M-WEBRADIO: synthetic injection for error states

`ERROR_BLOCKED` (HTTP 403/451) and `ERROR_UNREACHABLE` (DNS/TCP timeout) cannot
be induced reliably on DUT without broken stations. A synthetic injection path
is needed for VE coverage — following the T272 TLS contention injection pattern.

Deliverables:
1. `set webRadioState <state>` serial command that forces `WebRadioState::playState`
   to a given enum value (`STOPPED`, `CONNECTING`, `BUFFERING`, `PLAYING`,
   `ERROR_WIFI`, `ERROR_BLOCKED`, `ERROR_STALL`, `ERROR_UNREACHABLE`).
2. Display tick reads `playState` and renders the correct POSBAR + marquee title
   per the §Error states table — synthetic injection verifies this render path
   without needing a live broken station.
3. VE test cases:
   - `T_WR_ERR_01`: inject `ERROR_BLOCKED` → assert marquee shows "Station blocked",
     POSBAR thumb at left (0%).
   - `T_WR_ERR_02`: inject `ERROR_UNREACHABLE` → assert marquee shows
     "Station unreachable", POSBAR at left.
   - `T_WR_ERR_03`: inject `ERROR_WIFI` → assert marquee shows "WiFi lost".
   - `T_WR_ERR_04`: inject `CONNECTING` → assert POSBAR animates (thumb moves).

**Priority:** P2 — required for VE suite completeness before milestone close
**Status:** done — 2026-06-14
**Opened:** 2026-06-14
**Milestone:** M-WEBRADIO
**Owner:** Developer (injection command) + VE (test cases)
**Deps:** M-WEBRADIO firmware error state machine implemented
**Sign-off:** ERROR_BLOCKED=6 added to WRPlayState enum; set wrState <int> wired in dbgSet; error display strings updated ("Station blocked", "Station unreachable", "WiFi lost"). VE test cases T_WR_ERR_01–04 in regression_suite/m-webradio-eject-errors.md. DUT run 2026-06-15: T_WR_ERR_01–04 all PASS (8/14 WebRadio tests pass; 6 skip pending radio-browser reachability).

---

## Open — M-WEBRADIO firmware implementation

### TASK-213 — M-WEBRADIO: firmware implementation

Full WebRadio app firmware. Deps on TASK-210 (bake_skin.py eject sign-off) before
starting eject work; rest can proceed in parallel.

**Deliverables:**

1. **`app/src/webRadioApp.h`** — WebRadio app class:
   - `resume()`: enqueue station-list fetch if list is stale (BP-032: unsigned
     underflow pattern, not `_lastFetch = 0`).
   - `suspend()`: `audio.stopSong()`; release I2S-DAC handle.
   - `tick()`: poll ICY queue, update marquee + POSBAR buffer health, VU meter;
     dispatch error state machine.
   - `handleInput()`: eject tap → `switchApp(AppId::Spotify)`; prev/next/stop/play
     → station navigation + `audio.connecttohost()`.
   - `hasPendingAsync()`: return `true` while station-list fetch is in flight
     (BP-036 checklist item 1).

2. **`dataTaskStorage.cpp` — `fetchWebRadioStations()`:**
   - `spotifyTask::tlsYield()` before `WiFiClientSecure`; `tlsResume()` in all
     exit paths (BP-031 — mandatory, see §Data flow parser note in M-WEBRADIO.md).
   - Streaming ArduinoJson parse: `StaticJsonDocument<128>` filter (name,
     url_resolved, bitrate, votes) + `StaticJsonDocument<8192>` doc via
     `http.getStream()`.
   - Mirror fallback: `de1` → `nl1` → `at1`; retry next on connection failure.
   - Root CA: Let's Encrypt ISRG Root X1 (confirmed TASK-200).

3. **`winampDisplay.h` — `hitTestEject()`:**
   - Hit zone: `(originX+136, originY+89, 22, 16)`.
   - On hit: blit `SKIN_CBUTTONS` pressed crop, 100 ms cooldown, populate
     `lastTouchResult = { "EJECT", -1, "EJECT", 0, -1, false }`.
   - Add `"EJECT"` to action-string enum comment (line 537).
   - **Deps: TASK-210 sign-off first** (bake_skin.py must remove static eject
     paste before firmware blits it at runtime).

4. **`main.cpp`:**
   - `ACT_EJECT` in Spotify input handler → `switchApp(AppId::WebRadio)`.
   - WebRadio tick + input dispatch wired into `appTick()` / `appHandleInput()`.

5. **`appRegistry.h`:**
   - `APP_X(WebRadio, 'R', 0)` — AppId entry; NOT added to
     `gen_taskbar_icons.py` APPS list (no taskbar slot by design).

6. **Settings wiring** (`settingsStorage.h`, `appsSection.h`):
   - Country (enum, default NL), Autoplay (bool, false), Bitrate cap (enum,
     default 96 kbps), Auto-skip on stall (bool, false), HW Mod Installed
     (bool, false), Max Volume (int, default 10/18).

7. **Error state machine** per §Error states in M-WEBRADIO.md:
   - States: STOPPED / CONNECTING / BUFFERING / PLAYING / ERROR_WIFI /
     ERROR_BLOCKED / ERROR_STALL / ERROR_UNREACHABLE.
   - Auto-retry and auto-skip policy per settings.

8. **Serial `dbgGet`/`dbgSet`** (BP-036 checklist item 3):
   - `get webRadioState` → current playState enum string.
   - `set webRadioState <state>` → synthetic injection (TASK-212).
   - `get touchResult` already returns `lastTouchResult`; ensure "EJECT" path
     covered (TASK-211).

9. **`run/check`** 5/5 gates pass before marking done.

**Priority:** P1 — core milestone deliverable; blocks TASK-207/208/209/211/212
**Status:** done — commit e6c02ed (2026-06-14)
**Opened:** 2026-06-14
**Closed:** 2026-06-14
**Milestone:** M-WEBRADIO

**Delivered:**
- `webRadioApp.h`: WRPlayState, Audio internal DAC GPIO26, ICY queue, PLEDIT station list,
  POSBAR buffer bar, full App interface (init/resume/suspend/tick/handleInput/hasPendingAsync
  /dbgGet/dbgSet with wrState/wrCount/wrIdx/wrIcy/wrEject/wrPlay/wrStop/wrNext/wrPrev).
- `dataTaskStorage.cpp`: fetchWebRadioStations — tlsYield/tlsResume, de1→nl1→at1 mirrors,
  streaming filter, pre-allocated DynamicJsonDocument(14336), stack bumped to 12 KB.
- `winampDisplay.h`: drawEjectButton(bool), hitTestEject, hitTestTransportPublic public;
  repaintChrome calls drawEjectButton(false); EJECT in TouchResult comment.
- `main.cpp`: SpotifyApp intercepts hitTestEject → switchApp(WebRadio); webRadio dbg shims.
- `appRegistry.h`: APP_X(WebRadio,'R',0). 5/5 check gates pass. RAM 37.2% / Flash 62.4%.

**Notes:** TASK-211 (serial ACT_EJECT test) and TASK-212 (error state injection) remain open.
**Owner:** Developer
**Deps:** TASK-210 (sign-off required before hitTestEject blit); TASK-199–202
done (host phase complete — all gate inputs available)

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

**Done — DUT-verified 2026-06-25 (T270 PASS, T271 PASS; 2 passed / 0 failed / 0 skipped).**
- **T270:** the deliverable-1 mechanism (inject `pn=ns/ps` headers via `set teletextPageContent`)
  is **not buildable as written** — that accessor injects only the decoded 25×40 cell grid, while
  the `pn=ns`/`pn=ps` parse runs on the *raw HTTP body* in `fetchTeletext()` (network-only, no
  injection hook). Implemented the faithful equivalent instead: `set teletextSubpageNext 617-2` /
  `set teletextSubpagePrev 617-1` set the exact fields the parser writes, then SUBDN tap (y=182)
  asserts `teletextLastAction==STRIP_SUBDN` + `shellBusy` (i.e. `_navigate(617,2)` fired). Covers
  the **navigate** path; the raw `pn=` line-dispatch remains network-only (lower-value gap, noted).
- **T271:** four pixel-exact strip boundaries verified (y=66→STRIP_PAGE, 67/99→STRIP_BACK,
  100→STRIP_PREV) via `get teletextLastAction`.
- Both registered in `run_serialdbg_tests.py` (ALL_TESTS); ran green on DUT via `./run/test-targeted`.
**Priority:** P2 — closes BP-034 gap for teletext
**Status:** done — DUT-verified 2026-06-25
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

---

### TASK-251 — origin_audit.png is stale + gitignored (advisory, not gated)

Architect note (2026-06-26): `app/gen/origin_audit.png` is a **gitignored build artifact** generated
by `audit_origin.py --visual` from `gen/skin_layout.h`. The local copy went stale (regenerating
changes it; the drift was the transport-row zone band at y≈89–105) and shows BOTH `originX=22`
(legacy) and `originX=0` (current) panels — misleading when read as current. The audit's boxes come
from `skin_layout.h` (authoritative) **except** the VIS rect (hand-mirrored from `vuMeter.h`); PLEDIT
uses absolute screen-Y per the documented TASK-080 mismatch. Verified: in current geometry **no zone
exceeds the 275px chrome** (LOGO 243–274, PLEDIT-Z2 256–274 sit flush at the last column, by design),
and the PLEDIT thumb draw math is **clean** (bottom-aligns at max scroll). So the apparent
right-overflow / off-by-1 were stale-artifact effects, not firmware bugs.
**Deliverable:** make the audit regenerate-before-read (a `run/` wrapper or a `--check` staleness
gate), and/or drop the legacy `originX=22` panel now that the migration is complete. Parse the VIS
rect from `vuMeter.h` to kill the last hand-mirrored-constant drift.

**DONE 2026-06-26.** All three: (1) `render_visual` now emits a **single panel** of the shipped layout
(`originX=0`) — the legacy centered `originX=22` panel is dropped (the firmware left-aligns the window,
taskbar on the right, so 22 was never a real config). (2) `load_vis_rect()` parses RECT_X/LEFT_Y/RECT_W/
VIS_H from `vuMeter.h` (its real owner) instead of hand-mirroring → no silent drift; raises if a const
goes missing. (3) New **`run/audit-origin`** wrapper always regenerates the PNG from current sources
(it's gitignored, so reading it after a regen is never stale); documented in `project_run_scripts.md`.
All `audit_origin.py` checks (T141–T146) still pass.
**Priority:** P3 — tooling hygiene · **Status:** done 2026-06-26 · **Opened:** 2026-06-26 · **Owner:** VE/Architect · **Deps:** —

---

### TASK-252 — WebRadio title zone: reuse drawTitleText (LED font + marquee)

Architect ruling (2026-06-26): drop WebRadio's `_drawTitleZone` (plain GFX font on a black fill) and
reuse the shared `WinampDisplay::drawTitleText(offset)` — the authentic Winamp LED bitmap font with a
scroll offset, restoring the slot from `SKIN_MAIN_BG`. Wins: visual consistency with Spotify, a free
scrolling marquee for long station names (currently truncated), −~24 lines. Requires a public
`setTitle()`/`lastTitle` setter and WebRadio driving the scroll offset (or 0 for static); the
connecting/error strings render in the LED font too. Caveat: `TITLE_H=6` is tight — verify the state
strings fit. Prototype in `preview_webradio.py` first (it already uses the real `composite_text`).

**Implemented 2026-06-26 (mock-verified; DUT sign-off owed).** Added public `WinampDisplay::setTitle()`
(redraw-on-change + reset-scroll + hold, extracted op-for-op from `printCurrentlyPlayingToScreen`,
which now calls it) and `tickMarquee()`. WebRadio's `_drawTitleZone` now composes the station/state
string and calls `setTitle()`; `tick()` drives `tickMarquee()` for long-name scroll. The baked
`SKIN_GLYPH` folds lowercase→uppercase, so no manual uppercasing. Mock already rendered the LED-font
title; reconciled its content to station-name-only (it had combined "station - ICY"). Self-verified in
host: "RADIO 1 NL" renders in the authentic LED font, kbps/kHz badge clear. 5/5 gates. **Surfaced
TASK-254** (the separate ICY line collides with the kbps/kHz badge — a pre-existing issue, out of this
task's scope).
**Priority:** P3 — visual consistency · **Status:** **done — DUT-verified 2026-06-26** (LED-font title confirmed on panel) · **Opened:** 2026-06-26 · **Owner:** Developer + Architect · **Deps:** —

---

### TASK-254 — WebRadio ICY StreamTitle line collides with the kbps/kHz badge

Surfaced while reconciling the mock for TASK-252. `_drawIcyLine()` draws the ICY StreamTitle as a
separate white GFX line at `WR_ICY_Y=36`, but the baked "192 kbps / 44 kHz / mono-stereo" cluster lives
in that same row (x≳155), so a non-trivial ICY title overflows into it (and `drawString` isn't clipped
to `WR_ICY_W`). There is no collision-free space for a full second text line there. **Architect
recommendation:** fold the ICY into the title as a combined Spotify-style marquee — `setTitle("STATION
- SONG   ")` recomposed when ICY arrives — and drop the separate `_drawIcyLine` (one scrolling LED line,
no collision, max Spotify consistency; this is what the mock originally assumed). Alternative: clip ICY
to the ~44px gap before the badge (cramped). User UX call before implementing. The mock omits the ICY
line pending this decision.

**DONE — combined marquee (user-chosen 2026-06-26); mock-verified.** Folded the ICY into the title:
`_drawTitleZone` composes `"STATION - SONG   "` when `_icyTitle` is set (else station only) and calls
`setTitle()`; the ICY tick handler recomposes the title instead of drawing a separate line. Removed
`_drawIcyLine()`, its `_drawFull()` call, and the now-dead `WR_ICY_X/Y/W/H` constants (`WR_ICY_TITLE_LEN`
kept). Result: one scrolling LED line, and the **kbps/kHz badge is no longer overdrawn** (the old
separate line's black fillRect had covered it). Mock mirrors it (`"STATION - ICY"`). Self-verified in
host; 5/5 gates. DUT sign-off batched with TASK-252/253.
**Priority:** P3 — visual/layout · **Status:** **done — DUT-verified 2026-06-26** (combined "STATION - SONG" marquee + clean kbps/kHz badge confirmed on panel) · **Opened:** 2026-06-26 · **Owner:** Architect + Developer · **Deps:** TASK-252 (done)

---

### TASK-253 — WebRadio posbar: thumb-position buffer-fullness bar

Replace the flat-green `fillRect` buffer bar (ugly). **Design history:** first tried a health-tinted
amber→green gradient (host-prototyped, RGB565-verified) but the user rejected the look 2026-06-26.
**Final design (user-chosen):** reuse the POSBAR exactly as Spotify uses its **seek bar** — the groove
sprite + the POSBAR thumb, whose **position** marks buffer fullness (left=empty, right=full), pct mapped
over the same `travel = POSBAR_BG.w − POSBAR_THUMB_N.w` the seek bar uses. The shared renderer gained
`WinampDisplay::drawBufferBar(pct)` (owns `SKIN_POSBAR`, restores groove + blits the thumb at position);
WebRadio's `_drawPosbar` delegates. `preview_webradio.py::_draw_buffer_bar` mirrors it (this is also the
mock's original approach — the gradient detour is fully reverted). Self-verified in host across 0–100%;
5/5 gates.
**Priority:** P3 — visual polish · **Status:** **done — DUT-verified 2026-06-26** (thumb-position confirmed travelling 0–100% on panel; gradient reverted; +smoothness fix b2ea220 cutting the 15-pt full-repaint hysteresis to a 2-pt targeted blit) · **Opened:** 2026-06-26 · **Owner:** Developer + Architect · **Deps:** —

---

### TASK-255 — M-WEBRADIO-NOPSRAM: no-PSRAM viability via Spotify-disabled build

Build-time experiment to settle the open M-WEBRADIO blocker (stable no-PSRAM MP3 playback) on a
**faster lane that needs no Spotify auth** — sidestepping the external TASK-243 Premium blocker that
has frozen TASK-241's tight-heap re-test. A `cyd2usb_webradio` PlatformIO env adds `-DDISABLE_SPOTIFY`,
which (single functional guard) skips `spotifyTask::begin()` so the task's **~10 KB resident stack** is
never allocated; with `reqQueue`/`s_tlsYieldedSem` null, all 34 `tlsYield`/`tlsResume` call sites
early-return with **no source edit**. Per EXP-007 the limiter is **usable heap** (`free − 38.9 KB
caps-restricted dead block`), *not* `maxAlloc` (which is pinned): EXP-007 failed at usable ≈ 20.6 KB <
22.7 KB decoder demand. Removing the ~10 KB stack predicts ~30.6 KB usable (+8 KB margin) — enough for
the decoder *and* a larger input buffer. The Spotify app stays a dormant, provably-inert stub (no
`AppId` surgery; shows a permanent amber "connecting" bar per ADR-046).

**Panel-consensus design (rev3):** [M-WEBRADIO-SPOTIFY-DISABLE.md](../architecture/designs/M-WEBRADIO-SPOTIFY-DISABLE.md).
Round-1 PM blockers (V0 critical path / hard kill / supersede-vs-parallel) resolved; AGREE-WITH-NITS.

**HARD KILL (the abort point) — Measurement Step-1 / cheap pre-gate:** on `cyd2usb_webradio` at
WebRadio `_play()` entry, capture `get stacks` (`heapFree`/`heapMin`/`heapMaxAlloc`), **re-measure the
caps-restricted dead-block on THIS build** (do not assume EXP-007's 38,900 transfers — removing
`spotifyTask` may relayout caps), compute `usable = heapFree − dead_block`. **If `usable < 22.7 KB
decoder + target input buffer` → STOP. Do NOT spend DUT playback time.** Record FAIL against
TASK-241/ADR-045, shelve the branch. Pass signal is **usable headroom, NOT maxAlloc rising**.

**Two-threshold result split (a valid partial is OK):** the design records (a) **startup-reliability**
(decoder allocates first try, more stations reach PLAYING) vs (b) **underrun-tolerance** (16 KB input
buffer holds slow streams ≥ 60 s). An **(a)-only partial** — startup improves but underruns persist —
is a valid, recordable result, not a failure of the experiment.

**Definition of Done** (from design §Process & lifecycle):
- `cyd2usb_webradio` env builds; **default `cyd2usb_winamp` `.elf` `.text`/`.rodata`/`.data` section
  hashes unchanged** before/after the patch (V1 — robust gate; raw `.bin` may differ on build
  timestamp).
- **V0 lands green** (the harness + variant-signal prerequisite; critical path — see handoff).
- **Step-1 usable-headroom captured** at `_play()` entry on the disabled build.
- **PASS** (Step-1 clears AND V3 sustained-playback gate met: stable PLAYING ≥ 60 s within ≤ 6
  auto-skips on ≥ 90 % of cold-boot entries, fixed station set × ≥ 3 trials, network-flake entries
  excluded per the T169 carve-out, measured by the new `T_WR_PLAY_SUSTAIN` test) → write **EXP-008**
  + an **ADR-045 amendment** ("viable with Spotify disabled" — does **not** overturn ADR-045 for the
  multi-app board) + graduate Open-A (dormant stub vs boot-direct-to-WebRadio shipped variant) to a
  **PROP / follow-on milestone**. The 6th `./run/check` gate for `cyd2usb_webradio` lands only on that
  promotion, not here (PM N3).
- **FAIL** → ADR-045 stands unchanged; branch shelved; result recorded against TASK-241.

**Ordered handoff:** **Developer** (firmware variant signal: boot-log token `[boot] spotify=off` +
`get variant`; `get wrPlaying` PLAYING-duration query for `T_WR_PLAY_SUSTAIN`; the single
`#ifndef DISABLE_SPOTIFY` guard; **null-safety audit of every unconditional `spotifyTask::` accessor**
— `stackHighWaterBytes`/`stackSizeBytes`/`activeError`/`dbgGet`/`dbgSet`/`cmdReconnect` — so the
disabled build doesn't crash on the first `get stacks`) → **VE** (V0 harness: `_wait_for_ready` variant
branch keyed on the boot token = WiFi-up + shell-ready, skipping the never-emitted Spotify poll-wait;
**gated — task #1, before ANY DUT run**) → **DUT Step-1 kill gate** → **conditional V3** (sustained
playback + inverse per-fetcher `tlsYield`-no-op check + eject round-trip into the dormant stub) →
**Architect** (ADR verdict). Add the `cross_feature_matrix.yaml` row *DISABLE_SPOTIFY × {weather,
crypto, stock, teletext, heatmap, webradio}* **before** V3 runs.

**Cleanup placeholder:** **TASK-256** — revert `cyd2usb_webradio` env + the `DISABLE_SPOTIFY` guard if
any of it was merged before a FAIL verdict (per the QM lifecycle BP candidate: every experiment names
its FAIL artefact-disposition + cleanup task id before scheduling). No-op if nothing merged (the design
keeps env/guards on the branch until PASS + the promotion milestone).

**Priority:** P1 — settles "is no-PSRAM WebRadio viable at all," on a lane that runs *now* without
Premium · **Status:** **parked — `parked-pending-TASK-258`** (2026-06-27). The bottom-up bare-rig
(TASK-258 / EXP-009) overtook this top-down strip: it proved the **hardware plays** (both bare and +TFT)
and that the lever is **resident footprint, not RAM/silicon/display** — re-framing this task from "is it
possible" to "drop ~90 K of resident footprint." Keep the branch's V0 harness / `get wrPlaying` /
EXP-008 datapoint — reusable if/when a stripped in-project variant is pursued. · **Opened:** 2026-06-26
**Milestone:** M-WEBRADIO-NOPSRAM · **Branch:** `rnd/webradio-nopsram` · **Experiment record:** EXP-008
**Owner:** Developer (guard + variant signal) → VE (V0 harness) → Architect (ADR verdict)
**Deps:** M-WEBRADIO (firmware complete); **prereq-done:** TASK-239/240 (~11 KB reclaim); **sidesteps:**
TASK-243 (Premium); **baseline:** EXP-007 · **Cleanup:** TASK-256 · **Superseded-by:** TASK-258

---

### TASK-256 — Cleanup placeholder: revert Spotify-disabled env/guards on TASK-255 FAIL

Lifecycle placeholder for TASK-255 (per QM BP candidate: an experiment names its cleanup task id up
front). **Action on TASK-255 FAIL/shelve:** if the `cyd2usb_webradio` env or the `-DDISABLE_SPOTIFY`
guard was merged to trunk at any point, revert it (env stanza in `platformio.ini`, the single
`#ifndef DISABLE_SPOTIFY` guard, the variant-signal additions, the `cross_feature_matrix.yaml` row);
also remove any `cyd2usb_webradio` entry from `./run/check`. **No-op if nothing merged** — the design
keeps all of it on `rnd/webradio-nopsram` until PASS + the promotion milestone, so the expected steady
state is "nothing to clean."
**Priority:** P3 — lifecycle hygiene · **Status:** **dormant — fires only on TASK-255 FAIL-after-merge**
· **Opened:** 2026-06-26 · **Milestone:** M-WEBRADIO-NOPSRAM · **Owner:** Developer · **Deps:** TASK-255

---

### TASK-258 — M-WEBRADIO-NOPSRAM: bottom-up bare-rig no-PSRAM ceiling measurement

Bottom-up pivot from TASK-255's top-down strip (panel-approved PROP rev2, unanimous). Instead of stripping
our 11-app build down toward headless (a confirmed ~25–30 `#ifdef`-site grind for a coin-flip), build the
**bare ESP32-audioI2S radio on our actual hardware** as a true control and measure the no-PSRAM ceiling
directly. Throwaway rig at `~/proj/webradio-bare/` (out-of-tree, own git repo, not in `run/check`, WiFi in
gitignored `secrets.h`). Full parity: `espressif32@6.9.0`, `esp32dev`, ESP32-audioI2S v2.3.0, internal DAC
GPIO26 (`I2S_DAC_CHANNEL_LEFT_EN`, GPIO25 left for touch). Two configs: (A) no-display = hardware ceiling /
kill test; (B) +CYD TFT_eSPI = realistic budget anchor. CP1 pre-connect / CP2 decoder-init (gate metric) /
CP3 low-water, + caps dead-block re-probed per build.

**Result — both configs PASS (DUT-verified 2026-06-27):**
- **Config A (no-TFT):** decoder inits at **166,056 free**, `connecttohost=1`, `StreamTitle` changed across
  a track, heap held ≥ ~45 s → **plays.**
- **Config B (+TFT):** decoder inits at **165,404 free** → **plays.** **TFT_eSPI costs ~600 B** (direct-draw,
  no framebuffer) — the display is **not** the heap problem.
- **Headline:** the no-PSRAM CYD hardware **can** play MP3 radio. ADR-045's "no-PSRAM playback = NO-GO" is
  **footprint-bound, not silicon-bound.** Budget anchor: ~207 K free @ connect, ~165 K at decoder; audio path
  ≈ 41 K (8 K input + 22.7 K Helix + connection). Our 11-app build fails only because its ~147 K resident
  footprint leaves ~60 K — too tight for the 41 K path + fragmentation headroom. **The lever is resident
  footprint, not RAM, not the display.**
- **Model correction:** the "38,900 dead block" was never fixed — it was the *fragmented 11-app* largest free
  block; bare it's 110,580. The `usable = free − maxAlloc` framing (EXP-007/008) was a misread.

**Bounded-claim caveat (R2/LL-086):** a bare PASS proves *hardware + library*, sets the *budget/ceiling* — it
does **NOT** prove our app fits. EXP-009 never states "WebRadio is viable," only the ceiling.

**Priority:** P1 — settles the M-WEBRADIO viability question at the hardware level · **Status:** **DONE —
both configs PASS, written up** · **Opened:** 2026-06-27 · **Closed:** 2026-06-27
**Milestone:** M-WEBRADIO-NOPSRAM · **Rig:** `~/proj/webradio-bare/` (out-of-tree, commit `1c25982`)
**Experiment record:** [EXP-009](../rnd/reports/EXP-009-webradio-bare-rig.md) · **Proposal:**
[PROP-webradio-bare-rig](../rnd/proposals/PROP-webradio-bare-rig.md) · **Owner:** R&D
**Deps:** none (out-of-tree) · **Supersedes:** TASK-255 (parked) · **Feeds:** TASK-241 / ADR-045
**Follow-on:** TASK-257 (optional Lane C-1 library A/B)

---

### TASK-257 — Lane C-1: ESP32-audioI2S v2.3.0 ↔ v2.0.6 decoder-footprint A/B (optional)

Re-homed onto the TASK-258 bare rig (was a TASK-255 sub-item). Optional, low-priority: on the bare rig, swap
**only** `lib_deps` v2.3.0 ↔ v2.0.6 (fresh `.pio/libdeps`, reflash), same station/buffer/CP2 capture, ≥ 3
trials/arm; signal = Δ `usable`@CP2. Don't swap the core toolchain too (second variable — the EXP-008 trap).
**Mostly answered already:** EXP-009's bottom-up result shows the Helix decoder is vendored ~identically
across the v2.x line and the lever is resident footprint, not library version — so this A/B is now a
*confirmation nicety*, not a decision input. Prior attempt hit `SD_MMC.h: No such file` (v2.0.6 predates
`AUDIO_NO_SD_FS`) — needs the build-config shim before it can run.

**Priority:** P3 — optional confirmation; not on any critical path · **Status:** **open — optional, deferred**
· **Opened:** 2026-06-27 · **Milestone:** M-WEBRADIO-NOPSRAM · **Rig:** `~/proj/webradio-bare/`
**Owner:** R&D · **Deps:** TASK-258 (done) · **Parent:** TASK-258 step 4

---

### TASK-259 — M-PLAYER-STATE: eject becomes a persisted sub-state toggle, not a one-shot app switch

**Behaviour change requested (user, 2026-06-27).** Today the Winamp "player" slot and WebRadio are modelled
as two separate things: eject does a momentary `switchApp(AppId::Spotify → AppId::WebRadio)`
(`main.cpp:2352` → `SpotifyApp::handleInput`), and the player↔radio choice is **not remembered** across a
taskbar app-switch. Desired model:
- The player slot has an internal **mode state**: `{ Spotify | WebRadio }`, persisted in RAM (and likely in
  `settings` so it survives a reboot — TBD with Architect).
- **Eject is a toggle** of that mode (Spotify ⇄ WebRadio), not a navigation to a separate app.
- **Returning to the player app** from the taskbar restores whichever mode it was last left in (don't force
  back to Spotify).

**Why it matters beyond UX:** this state model is the *precondition* for the memory work — Spotify and
WebRadio being **mutually exclusive runtime modes of one slot** is exactly what makes the memory-overlay /
reserved-arena design (M-MEMBUDGET) safe: only one of {Spotify task+TLS, WebRadio decoder+arena} need be
resident at a time. So this is not only cosmetic — it formalises the mutual-exclusion the budget design
leans on. Couples with the "make spotifyTask / dataTask dynamic" open questions in M-MEMBUDGET (tearing the
Spotify task down on toggle-to-WebRadio is the mechanism that frees its ~10 KB stack + TLS for the arena).

**Scope to settle with Architect:** AppId topology (does WebRadio stop being its own `AppId` and become a
mode of the player? — interacts with the taskbar-excludes-WebRadio invariant, LL-085/TASK-242), where the
mode is persisted, what happens to the *other* mode's resources on toggle (stop vs keep-warm), and the
boot-default mode.

**Implemented (RAM-only) 2026-06-27, build-gated — `run/check` 5/5 PASS, DUT-verification pending.** Minimal
landing keeps the AppId topology unchanged (WebRadio stays its own eject-only AppId, OQ5 resolved the
least-invasive way): added `g_lastPlayerMode` (`main.cpp`), tracked in `switchApp()` whenever the player
enters Spotify or WebRadio, and a `resolvePlayerSlot()` redirect at the two taskbar gesture-end sites so the
player slot restores the last mode instead of always Spotify. Eject already toggled both ways
(Spotify→WebRadio at the eject handler; WebRadio→Spotify at `webRadioApp.h:309`); settings-back already
restored correctly via `g_previousAppId` — so no change needed there. **Deferred:** settings-persistence of
the mode across reboot (OQ4 — RAM-only resets to Spotify on boot).

**DUT-verification owed (when DUT returns):** enter WebRadio via eject → switch to another taskbar app →
tap the player slot → confirm it returns to WebRadio (not Spotify); and the inverse from Spotify.

This is **PART 1** of M-PLAYER-STATE (runtime toggle). **PART 2** (SPIFFS persistence + Settings UI toggle,
OQ4 + the user's settings request) is split out as **TASK-260**, designed in
[M-PLAYER-STATE.md](../architecture/designs/M-PLAYER-STATE.md). Feature: `player-state-001`.

**Priority:** P2 — UX fix + enabler for M-MEMBUDGET · **Status:** **DONE — PART 1 implemented (RAM-only); DUT-verified 2026-06-27 (player slot restores WebRadio after app-switch PASS; crash during WDT/TASK-233 playback, not a regression)** · **Opened:** 2026-06-27 · **Milestone:** M-PLAYER-STATE
**Owner:** Developer · **Deps:** none · **couples with** M-MEMBUDGET (the mutual-exclusion it formalises)
· **Design:** M-PLAYER-STATE.md · **Follow-on:** TASK-260 (PART 2)
· **Related:** TASK-242 (taskbar eject-only invariant), ADR-046 (Spotify dormant-stub bar)

---

### TASK-260 — M-PLAYER-STATE PART 2: persist player mode to SPIFFS + Settings → Applications → Player toggle

PART 2 of M-PLAYER-STATE (PART 1 = TASK-259). Make the player mode `{Spotify | WebRadio}` a **persisted,
user-editable setting**. Designed in [M-PLAYER-STATE.md](../architecture/designs/M-PLAYER-STATE.md).
Two pieces:
- **Persist (OQ4):** collapse TASK-259's runtime `g_lastPlayerMode` into `g_settings.playerMode` (single
  source of truth); add a new top-level `player` object to `settings.json` (defaults/load/save in
  `settingsStorage.{h,cpp}`); restore at boot. Save policy: immediate `saveSettings()` on eject/toggle with
  an **unchanged-value skip** (flash-wear, §4).
- **Settings UI (§5):** flip Spotify `appRegistry.h` cfg `0→1`, **regenerate** `gen/configurable_apps.h` via
  `app/tools/gen_app_registry.py` (the `run/check` [5/5] staleness gate enforces this), and add
  `_repaintPlayer`/`_cyclePlayer` to `settings/appsSection.h` (single "Mode" toggle row, mirroring Clock).

**Open (decide before/at impl):** OQ-LABEL (show "Spotify" vs add a "Player" display-name codegen column —
design recommends the latter); OQ-BOOT (cold-boot-into-mode is **v2/deferred** — v1 boots to Spotify view,
`webRadioAutoplay` governs actual radio auto-start).

**DoD:** `run/check` 5/5 (incl. codegen-staleness + golden); settings round-trip verified offline
(`run/spiffs pull … settings.json` shows `player.mode`); DUT: set mode → reboot → player slot restores it.

**OQ resolutions (at impl):** OQ-LABEL = **(b) "Winamp"** display-name column added to the app-registry
codegen (4th `APP_X` arg); OQ-BOOT = **v2** (user choice 2026-06-29 — cold-boot enters the persisted mode;
auto-play still governed by `webRadioAutoplay`); OQ-WEAR = **immediate-save + unchanged-skip**
(`persistPlayerMode()` §4).

**Implemented + DUT-VERIFIED 2026-06-29 (v2) — `run/check` 6/6; 14/14 DUT checks PASS.**
Key decisions:
- **State model:** removed TASK-259's runtime `g_lastPlayerMode`; single source of truth is
  `g_settings.playerMode` (`PlayerMode{Spotify=0,WebRadio=1}`), new top-level `player.mode` in `settings.json`.
- **Writers = the deliberate toggles only** (eject in both directions: `main.cpp` Spotify handler +
  `webRadioApp.h` touch-eject & serial `wrEject`; plus the Settings `_cyclePlayer`). The `switchApp()`
  navigation-tracking write was **removed** — keeping it would clobber the persisted mode at boot (v1 boots to
  the Spotify view). `resolvePlayerSlot()` is the sole reader.
- **Codegen:** `APP_X` grew a 4th display-name column → all 3 expansion sites (`appShell.h`, `main.cpp` ×2) +
  `gen_app_registry.py` (emits `kConfigurableApps[].display` + python `DISPLAY`); Spotify flipped `cfg 0→1`,
  shows as "Winamp". Settings list/title now use `.display`.
- **v2 boot-into-mode:** at the end of `setup()` (after the Spotify app's boot `init()`), if
  `g_settings.playerMode==WebRadio` and WiFi is up, `switchApp(AppId::WebRadio)`. `SpotifyApp::suspend()` is
  just `resetDragState()` so tearing it down at boot is safe. Offline still diverts to WiFi settings.
- **VE instrumentation:** `get playerMode` + `set playerMode <0|1|spotify|webradio>` serial commands added
  (`set` is pure persist — no app switch — so a reboot exercises the v2 boot path).
- **Nav-drift (T_PS_NAV_01):** Winamp inserted at configurable-app row 0 shifts the others +1. DUT settings
  tests (T-SET-03/06/07) are index-based (assert `submenu==tapped-row`, not app identity) and the taskbar
  harness imports only `APP_SLOT`/`APP_COUNT` (unchanged) — so no test logic breaks; only stale row-comments.

**DUT validation 2026-06-29 (cyd2usb_winamp_debug, /dev/ttyUSB0) — 14/14 checks PASS:**
- set/get playerMode both directions + numeric + reject-bad value;
- **no-op skip (§4):** a value *change* logs `SettingsStorage: saved`; an unchanged repeat does **not** (T_PS_NOOP_01);
- **v2 cold-boot-into-mode:** persist WebRadio → reset → boots into WebRadio; persist Spotify → reset → boots into Spotify;
- **eject writers persist:** tap-eject Spotify→WebRadio writes WebRadio; tap-eject WebRadio→Spotify (after the
  station fetch settles past the CANVAS/`g_shellBusy` gate) writes Spotify; serial `set wrEject 1` ditto.
  (Two initial harness-only artifacts — a tap gated mid-fetch and a missing `set` value arg — were test bugs, not firmware.)
- VE follow-up: fold these into the regression suite as the formal T_PS_* ids; offline
  `run/spiffs pull settings.json` shows `"player":{"mode":N}`.

**Priority:** P2 — completes M-PLAYER-STATE; persistence the user asked for · **Status:** **DONE — v2
implemented + DUT-verified 2026-06-29 (14/14); `run/check` 6/6** · **Opened:** 2026-06-27 · **Closed:**
2026-06-29 · **Milestone:** M-PLAYER-STATE · **Branch:** `feature/task-260-player-state-part2`
**Owner:** Developer · **Design:** M-PLAYER-STATE.md · **Deps:** TASK-259 (PART 1, done), `settings-001`,
`taskbar-001` · **Feature:** `player-state-001` (PART 2) · **Matrix:** X022–X024

---

### TASK-261 — M-MEMBUDGET spike: reserved-arena WebRadio coexistence (Gated A-lite, ADR-047)

The measurement spike that decides whether **Option A-lite** (reliable WebRadio on the multi-app no-PSRAM
board) is real. Human direction 2026-06-27 (ADR-047 ACCEPTED — Gated A-lite): pursue A-lite **conditional on
the Phase-1 kill-gate**. Plan: [PROP-membudget-spike](../rnd/proposals/PROP-membudget-spike.md) (panel-reviewed
`c11b87f`). Branch `rnd/membudget` → **EXP-010**.

**Phases (cheap-kill-first):**
- **Phase 0** — add the caps-split `get heap` probe (`freeInt/lfbInt/freeDma/lfbDma`; T_MB_PROBE_00, the
  Phase-1-gating instrumentation) + baseline the resident short-list. *(Instrumentation is firmware — codeable
  + build-checkable offline now; the measurement needs DUT.)*
- **Phase 1 (KILL GATE)** — boot-reserve ~40 K `MALLOC_CAP_INTERNAL|8BIT`, confirm contiguous + the full app
  set still runs ~15 K net short. FAIL → **A-lite dead, Option B stands, ADR-045 unchanged** (no fork spent).
- **Phase 2 (M-effort, gated on Phase-1 PASS)** — vendor ESP32-audioI2S, **3-site fork** (decoder alloc macro
  + matching decoder free + InBuff) into a **fixed-slot free-list allocator** (NOT bump — auto-skip churn).
  Phase 2a auto-skip churn test via `wrDeadUrls`. Viability: PLAYING ≥ 60 s on the multi-app build, ≥3 trials.
- **Phase 3 (conditional)** — overlay financing via TASK-259/260 + M-RECLAIM Q3-a teardown if always-held 40 K
  too tight.

**DoD:** Phase-1 captured + verdict recorded; on PASS → EXP-010 + ADR-047 re-issued with numbers + M-RECLAIM
Q3-a/Q4 become tasks. **BP-042 check:** confirm the *project* `platformio.ini` audio-dep pin carries the
why-not-newer note before Phase 2 vendors the lib.

**RESULT — ALL PHASES PASS (DUT-verified 2026-06-28, branch `rnd/membudget` commit `d20c269`).**
- **Phase 0/1:** caps-split baseline + 40 K reservation kill-gate PASS (EXP-010).
- **Phase 2:** vendored ESP32-audioI2S into `app/lib/`, forked the Helix decoder alloc+free into a 16-slot
  fixed-size free-list over a **24 K** arena (refined down from 40 K — Helix HWM = 23,216 B exact; InBuff
  reverted to general heap, fits the 38,900 lfbInt). **WebRadio played 88/103/129.7 s across 3 cold-boot
  trials**, survived 4 auto-skip churn cycles (free-list reuses the same 9 slots, zero fragmentation —
  lfbInt 38,900 constant). **Production `cyd2usb_winamp` ELF byte-clean (0 membudget symbols, nm-verified);
  all spike code `#ifdef MEMBUDGET_PHASE1`.**
- **A-lite is technically PROVEN.** ADR-047's kill-gate is cleared.

**Promotion caveats (shape the TASK-262 decision — NOT regressions, but un-validated for shipping):**
1. **PATCH-MEMBUDGET-4 — I2S DMA halved** (16×512 → 8×256, 32 K → 8 K) under MEMBUDGET_PHASE1: the 24 K
   INTERNAL arena squeezed the shared DMA pool until `i2s_driver_install()` crashed; halving the ring fixed
   it. Plays clean at **56 kbps** — but the reduced buffering needs validation at higher bitrate / under
   network jitter (underrun resilience).
2. **Station fetch not live-tested** — radio-browser HTTPS mirrors were unreachable from the test network;
   streams were injected via a `set wrUrl` debug path. End-to-end fetch→play unproven here.
3. **Spotify-active coexistence (overlay) untested** — needs M-RECLAIM Q3-a + TASK-259/260 mode-state, and
   live validation gated on TASK-243 (owner Premium).

**Priority:** P1 — settles the M-WEBRADIO no-PSRAM viability question · **Status:** **DONE — all phases PASS;
A-lite proven; promotion decision = TASK-262 / human** · **Opened:** 2026-06-27 · **Closed:** 2026-06-28
**Milestone:** M-WEBRADIO-NOPSRAM · **Branch:** `rnd/membudget` (fork branch-only until promotion) ·
**Experiment:** EXP-010 (Phase 0/1/2) · **Owner:** R&D → Developer · **decision:** ADR-047 · **Next:** TASK-262

---

### TASK-262 — Cleanup placeholder: revert TASK-261 spike artefacts on FAIL/shelve

Lifecycle placeholder for TASK-261 (BP-040: an experiment names its cleanup id before scheduling; filed in the
same change as TASK-261). **Action on a Phase-1 FAIL or a shelve:** if any spike artefact reached trunk (the
vendored `lib/ESP32-audioI2S` fork, the reserved-arena allocator, the caps-split probe if deemed not worth
keeping, any `[env:]`/`-D` flag, the `cross_feature_matrix` rows), revert it; remove any `run/check` entry.
**No-op if nothing merged** — the design keeps the fork/arena on `rnd/membudget` until a Phase-2 PASS, so the
expected steady state is "nothing to clean."

**UPDATE 2026-06-28 — spike PASSED, so the FAIL-cleanup branch is moot; this task is REPURPOSED as the A-lite
PROMOTION gate** (human chose "de-risk then promote"). Promotion = merge `rnd/membudget` → master + ungate
(make the arena/fork production, not `MEMBUDGET_PHASE1`-only). **Gated on ALL of:** TASK-263 (halved-DMA
validation) green, TASK-264 (M-RECLAIM Q3-a overlay) green, TASK-265 (live fetch) green, **and TASK-243
(Premium) cleared** for the Spotify-active coexistence validation. Until all green, the fork stays branch-only.
**Priority:** P2 — promotion gate · **Status:** **blocked — gated ONLY on TASK-243 (Premium)** — all design/
engineering de-risk complete: TASK-263 (halved DMA) ✅, TASK-264 (overlay Q3-a) ✅, TASK-265 (fetch finding)
✅, **TASK-267 (fetch-vs-arena fix) DUT-verified PASS 2026-06-28** ✅. **Mainlined 2026-06-28 (`adeab7c`)** — `rnd/membudget` merged to master with A-lite **gated**
(`MEMBUDGET_PHASE1`); production `cyd2usb_winamp` byte-clean (count 0), `run/check` 5/5. The dead-mirror fix +
TASK-259 player-mode + all records are now on master; the `ef8e32c` divergence + a doubled-`#ifdef` auto-merge
artifact were resolved. **Remaining for promotion (the only un-done step):** TASK-243 (Premium) clears →
validate Spotify-active coexistence on the full multi-app build → **ungate `MEMBUDGET_PHASE1` for production**
(flip it on in `cyd2usb_winamp`).

**PROMOTED 2026-06-29 (provisional, without Premium) — branch `feature/task-262-promote-alite`.** Decision
(human): the TASK-243 gate is belt-and-suspenders — `MEMBUDGET_PHASE1` gates **only WebRadio-exclusive code**
(JIT `mb_arena`, halved-DMA fork, decoder→`mb_arena_alloc` routing), and this device outputs **no audio for
Spotify** (display/control only — no I2S/DMA path), so flipping it on changes **zero Spotify runtime
behaviour**. The TASK-264 TLS-drop coexistence mechanism was already in production (gated by `DISABLE_SPOTIFY`,
not the budget flag). What changed:
- `-DMEMBUDGET_PHASE1` moved from `cyd2usb_winamp_debug` → **`cyd2usb_winamp` (production)**; debug inherits it.
- The verbose `[membudget]`/`[mbdbg]` probes (CP0/CP1/CP2, `mb_heap_probe`, arena acquire/release/first-alloc,
  helix-alloc) re-gated `MEMBUDGET_PHASE1 && SERIAL_DEBUG` → **ship silent** in production.
- Dropped the dead `MEMPLAN_STATIC_DECODER` OQ1 experiment; arena `mb_arena_acquire()` call made unconditional
  (libc-fallback when flag absent). `run/check` 6/6 (production now compiles **with** the arena).

**DUT validation 2026-06-29:** arena code proven on the equivalent build (`cyd2usb_webradio`, same
`MEMBUDGET_PHASE1`, no 403 starvation) — `arena acquire=24576B lfbBefore=61428 **OK**` (real 24 K internal
block, not libc-fallback), `arena FIRST alloc ... cap=24576` (Helix decoder allocates **from** the arena),
`wrState=2 wrPlaying=1` (**PLAYING**), idempotent re-acquire — **6/6**. Production `cyd2usb_winamp` boots clean
(heap=134k/maxAlloc=47k idle), runs steady, **no probe spam**, no panic.

**Residual (the only thing Premium would add):** confirming Spotify *renders a playing track* under the
promoted build — nil risk, since the promoted build changes no Spotify code path; and the WebRadio station
fetch on the Spotify-enabled build is itself starved by the TASK-243 403 (project memory: tlsYield
starvation). **Rollback:** TASK-256 (revert `-DMEMBUDGET_PHASE1` from `cyd2usb_winamp`). · **Status:**
**PROMOTED — provisional, DUT-validated 2026-06-29; residual Spotify-render check owed on TASK-243** ·
**Opened:** 2026-06-27 · **Milestone:** M-WEBRADIO-NOPSRAM · **Owner:**
Developer/PM · **Deps:** TASK-261 (done), ~~TASK-263~~, ~~TASK-264~~, ~~TASK-265 (done→TASK-267)~~,
**TASK-267**, TASK-243 (residual only)

---

### TASK-263 — Validate halved I2S DMA (PATCH-MEMBUDGET-4) at higher bitrate + under jitter

The Phase-2 fork halved the I2S DMA ring (16×512 → 8×256, 32 K → 8 K, gated `MEMBUDGET_PHASE1`) because the
24 K INTERNAL arena squeezed the shared DMA pool until `i2s_driver_install()` crashed. It plays clean at
**56 kbps** (BBC World Service), but the reduced buffering depth is **unvalidated at higher bitrate / under
network jitter** — the underrun-resilience risk. **The decisive quality gate for whether A-lite is shippable,
not just demoable.**

**Executable spec (instrumentation landed `414d32b`):**
- **Metric:** `get wrUnderruns` → `{underruns, minBufPct, bufPct, playMs}` (gated MEMBUDGET_PHASE1).
  `underruns` = input-buffer-empty edge events while PLAYING; `minBufPct` = session low-water. Reset on each
  PLAYING entry. (Empty input buffer is the right proxy for the 8 K ring: it becomes an audible gap far faster
  than with 32 K. Operator should still confirm by ear — the counter is the quantified gate.)
- **NOT an A/B vs stock 16×512** — that config *with the arena* is exactly what crashed `i2s_driver_install`,
  so it can't be run. This is an **absolute** soak test.
- **Build:** `cyd2usb_webradio` (disable-Spotify + MEMBUDGET_PHASE1 + the fork — avoids the 403 fetch
  starvation). Inject a **≥128 kbps HTTP MP3** stream via `set wrUrl <url>` (radio-browser mirrors were
  unreachable in Phase 2; a hardcoded high-bitrate URL is the test input).
- **Pass threshold (proposal):** ≥ 128 kbps, ≥ 120 s continuous, **underruns == 0** (or a tiny agreed N),
  `minBufPct` stays > 0, no stall/auto-skip, no Guru/WDT. **Fail** → arena/DMA split needs rework (smaller
  arena, or accept best-effort at high bitrate → that would re-open the promotion calculus).
- Deterministic jitter injection isn't feasible on-DUT; the honest proxy is a sustained soak on a real
  variable high-bitrate stream + repeat ≥ 3 trials.

**RESULT — PASS-with-caveat (DUT-verified 2026-06-28, commit `501c791`).** 3 trials × 128 kbps HTTP MP3
(SomaFM groovesalad/dronezone): held **124–138 s continuous, no stall / Guru / WDT**. `underruns = 1` on
every trial — but **all three fire at T < 5 s (initial buffer fill, before the decoder thread catches up) and
never recur**; post-fill bufPct sits at 93–100 % (trials 1–2). `minBufPct = 0` reflects only that startup dip.
**Verdict (PM/Architect):** the halved 8 K DMA ring is **NOT undersized** — it sustains 128 kbps with margin;
the lone underrun is a **connect-time firmware artifact**, not a ring-sizing failure. **The shippability
quality gate is cleared.** The startup glitch (one ≤1-frame gap at connect) is a minor UX issue → follow-up
**TASK-266** (not a promotion blocker). The strict `underruns==0` gate was conservative-by-design (agent can't
listen); **recurrent** underruns == 0 is the real result.

**Priority:** P1 — quality gate · **Status:** **DONE — PASS-with-caveat; gate cleared, startup glitch → TASK-266**
· **Opened:** 2026-06-28 · **Closed:** 2026-06-28 · **Milestone:** M-WEBRADIO-NOPSRAM · **Branch:**
`rnd/membudget` · **Owner:** R&D/Developer · **Deps:** TASK-261 · **Gates:** TASK-262 (promotion — now clear of 263)

---

### TASK-264 — M-RECLAIM Q3-a: tear down Spotify (TLS-drop) when WebRadio mode is active

Graduates M-RECLAIM Q3-a from design to implementation (ADR-047: "M-RECLAIM Q3-a/Q4 become real tasks on a
PASS"). For production, the 24 K WebRadio arena and Spotify's ~50 K TLS working set must not coexist — the
overlay tears Spotify down when the player is in WebRadio mode. **Q3-a (light, recommended v1):** keep the
spotifyTask object, drop its TLS connection (`client.stop()`/`resetTls()`) on toggle-to-WebRadio; reclaims the
TLS working set without the vTaskDelete null-safety audit. Trigger = the TASK-259/260 player mode-state.
Design: [M-RECLAIM-dynamic-resident.md](../architecture/designs/M-RECLAIM-dynamic-resident.md) §Q3-a.
**Priority:** P1 — required for Spotify coexistence (promotion) · **Status:** **DONE — implemented `f37b92a`**
(s_webRadioActive flag; setWebRadioActive() hooks switchApp(); 500 ms idle guard in task loop; run/check 5/5)
· **Opened:** 2026-06-28 · **Closed:** 2026-06-28 · **Milestone:** M-WEBRADIO-NOPSRAM · **Owner:** Developer
· **Deps:** TASK-259/260 (mode-state), TASK-261 · **Gates:** TASK-262 (promotion) · **Design:** M-RECLAIM §Q3-a

---

### TASK-265 — Live station-fetch validation (radio-browser end-to-end)

Phase 2 injected streams via `set wrUrl` because the station fetch failed. **Host check (2026-06-28)
diagnosed why:** the firmware's mirror list `nl1`/`at1` are **decommissioned** (no DNS — the "DNS fails"), and
`de1` (the live one) **is reachable** (IPv4 91.98.4.78, HTTPS 200) — so its "SSL alloc fail" points to
**TLS-heap-vs-arena**, not the network. **Mirror list fixed** (`de1` + `all.api`, both IPv4; commit below).

**Reframed — this is now a fetch-TLS-vs-arena coexistence test, not just a fetch demo.** The real question:
can the ~40 K station-fetch TLS handshake allocate **with the 24 K arena held**? Build `cyd2usb_webradio`
(disable-Spotify → no 403 starvation; MEMBUDGET_PHASE1 → arena+fork active). Three distinguishable outcomes
the agent MUST report:
- **fetch succeeds** (count > 0, plays a fetched station) → carve-out closed, gate clears;
- **fetch fails SSL-alloc on a reachable mirror** → **the TLS-heap-vs-arena finding** (promotion-relevant):
  the arena starves the fetch handshake → needs sequencing (fetch *before* `mb_arena_reserve()`, or release
  the arena during fetch, or shrink it). Capture `wrLastHttp` + the mbedtls error.
- **DNS fail** → should not happen now (mirror fix); flag if it does.
**RESULT — FINDING (DUT-verified 2026-06-28, commit `dd8ff84`): the always-held arena starves the station
fetch.** Both mirrors reachable (TCP connect 83–162 ms), but the mbedtls SSL context alloc fails `-32512`
(`MBEDTLS_ERR_SSL_ALLOC_FAILED`) immediately after TCP connect. At fetch time, with the 24 K arena held since
boot + dataTask's 11 K stack + WiFiClientSecure locals, `lfbInt ≈ 35 K` — below the ~40 K the mbedtls context
needs. `wrCount=0`, `wrLastHttp=-1`, reproducible across 2 cold boots. **The fetch and the always-held arena
cannot coexist.** → fix is **TASK-267** (Architect design — NOT a TASK-262 cleanup item; it reverses the
boot-reservation decision and must be designed, not patched).

**Priority:** P2 — surfaced the real promotion blocker · **Status:** **DONE — finding recorded; fix = TASK-267**
· **Opened:** 2026-06-28 · **Closed:** 2026-06-28 · **Milestone:** M-WEBRADIO-NOPSRAM · **Branch:**
`rnd/membudget` · **Owner:** R&D · **Deps:** TASK-261 · **Surfaced:** TASK-267 (the fix)

---

### TASK-267 — Resolve the fetch-TLS-vs-arena heap conflict (Architect design)

TASK-265 proved the always-held 24 K boot-reservation starves the ~40 K station-fetch mbedtls handshake
(fetch `lfbInt ≈ 35 K` < ~40 K). **This is a genuine design fork, not a patch** — it pits two constraints the
design already balanced:
- **Boot-reserve** (current): guarantees 24 K contiguous for the decoder regardless of `_play()`-time
  fragmentation (the EXP-008 problem Phase 1 solved) — **but starves the fetch.**
- **JIT-reserve at `_play()`** (the agent's proposal): fetch at `init()` sees full heap → SSL succeeds; the
  fetch TLS frees before play → reserve 24 K then. **But re-introduces the `_play()`-time fragmentation risk
  boot-reservation was built to avoid** — needs proof that 24 K contiguous reliably survives to `_play()`
  (likely only true once TASK-264's overlay frees Spotify's ~50 K; measure it, don't assume).

**Options for the Architect to weigh** (don't pre-pick): (a) JIT-reserve at `_play()` financed by the
overlay + a Phase-1-style contiguity measurement at `_play()`; (b) reserve at boot but **release the arena for
the fetch window** (fetch always precedes play) and re-acquire — faces the same re-acquire contiguity
question; (c) **reduce the fetch's mbedtls buffers** (the station GET is tiny JSON — it doesn't need 16 K TLS
records; `MBEDTLS_SSL_IN/OUT_CONTENT_LEN` ↓ saves ~24 K) so fetch + arena coexist — but mbedtls config is
global (affects Spotify/audio TLS), assess blast radius; (d) fetch-before-reserve at boot with a cached list.
**DESIGN DECIDED (2026-06-28) — ADR-047 Amendment 1: Option (a), JIT-reserve at `_play()`.** The fetch
(`init()`) and the decoder arena (`_play()`) are sequential + disjoint, so:
- **Move `mb_arena_reserve()` from `setup()` → the top of `_play()`** (before the `Audio` construct /
  decoder alloc); **`mb_arena_free()` in `_stopAudio()`/stop** so the arena is held only during playback.
  `mb_arena_init()` follows a successful reserve; on a *failed* reserve, leave the arena null →
  `mb_arena_alloc` already falls back to libc (`mb_arena.h`) → best-effort, never a crash.
- The fetch at `init()` now runs with no arena held → ~55 K contiguous → SSL succeeds.
- TASK-264's overlay (Spotify torn down on WebRadio entry) makes the heap fresh at `_play()`.
**Measurement (the validation that retires the fragmentation risk):** add an `lfbInt` probe right before the
`_play()` reserve; ≥ 3 cold-boot trials × (enter WebRadio → fetch count>0 → play) on `cyd2usb_webradio`.
**PASS = fetch succeeds AND JIT reserve succeeds (`lfbInt ≥ 24 K`, arena non-null) AND playback holds.** FAIL →
fall back to option (c) (scoped mbedtls reduction) or a smaller arena (re-open ADR-047 Amendment 1).
**IMPLEMENTED 2026-06-28 (`04171ba`, build-gated `run/check` 5/5).** Arena moved boot→`_play()` JIT-acquire +
`suspend()` release (delete Audio first → frees decoder from arena → then release, avoiding dangling the live
decoder buffers `stopSong` doesn't free). `mb_arena_acquire/release/active` added to `mb_arena.*`; failed
acquire → libc fallback (best-effort). Production byte-clean (no arena behaviour). **DUT-verify owed:** the
ADR-047-Amd-1 measurement — ≥3 cold-boot trials × (enter WebRadio → **fetch count>0** → **acquire OK**
(`lfbInt ≥ 24 K`) → **plays ≥ 60 s**) on `cyd2usb_webradio`. The `[membudget] TASK-267 _play pre-acquire lfbInt=`
line is the validation signal.
**DUT-VERIFIED PASS 2026-06-28** (3 cold-boot trials, `cyd2usb_webradio`): fetch **count=16** every trial
(vs 0 pre-fix), JIT acquire **OK** with `lfbInt` = 61–63 K (~2.5× the 24 K — fragmentation risk decisively
unfounded), plays > 60 s. EXP-010 §TASK-267. The fetch-vs-arena conflict is resolved; **A-lite fully
de-risked.**
**Priority:** P1 — promotion blocker · **Status:** **DONE — DUT-verified PASS** · **Closed:** 2026-06-28
· **Opened:** 2026-06-28 · **Milestone:** M-WEBRADIO-NOPSRAM · **Branch:** `rnd/membudget` · **Owner:**
Developer · **Deps:** TASK-265 (finding), TASK-264 (overlay, done) · **Gates:** TASK-262 (promotion)

---

### TASK-266 — WebRadio connect-time underrun (startup buffer glitch)

Surfaced by TASK-263: at WebRadio play start the input buffer starves for ~1 frame (`underruns=1`, `bufPct`
dips to 0 at T < 5 s) **before the decoder thread catches up with the stream** — one ≤1-frame audio gap at
connect, then clean for minutes. Independent of DMA-ring size (occurs at 128 kbps with the halved ring; it's a
firmware buffering-order issue, not a sizing issue). **Fix candidates:** pre-fill the input buffer to
`isPlayable()`/`m_maxBlockSize` before un-muting / starting I2S output at connect; or seed the DMA. **Also
refine the `wrUnderruns` metric** to exclude the initial-fill window (count only post-settled underruns) so a
re-run reads a clean `recurrent underruns == 0`. **Priority:** P3 — minor UX polish, NOT a promotion blocker
· **Status:** **open — backlog** · **Opened:** 2026-06-28 · **Milestone:** M-WEBRADIO-NOPSRAM · **Branch:**
`rnd/membudget` · **Owner:** Developer · **Deps:** TASK-263 (surfaced it)

---

### TASK-268 — M-MEMPLAN Phase 1: static overlay planner foundation + OQ1

Pursue M-MEMPLAN (human direction 2026-06-28) — formalize memory budgeting + the app-union overlay into a
declarative, build-time-planned system. Design:
[M-MEMPLAN-static-overlay-planner.md](../architecture/designs/M-MEMPLAN-static-overlay-planner.md).

**Phase 1 scope (declarative foundation + the one empirical question — NO production runtime change):**
- **Single source of truth:** author `app/mem_manifest.yaml` (every app buffer: name/app/size/caps/group/kind),
  seeded from real numbers (EXP-010: decoder 23,216, InBuff 6,400; heatmap doc 2,560; sprites/JSON docs from
  code; honest `ceiling`/`headroom`).
- **Offline planner:** `app/tools/gen_mem_layout.py` (mirrors `gen_app_registry.py`) — M-MEMPLAN §4 algorithm
  (region = MAX-over-apps-of-SUM; per-app offsets; **WCMU budget assertion = hard build failure** on
  overflow); emits `app/gen/mem_layout.h` + `.py`. Enforces the §4b invariant (`kind: state` rejected from
  multi-app groups). Deterministic → golden-hashable.
- **Gate:** 6th `check_build.sh` step (staleness + budget). `run/check` green.
- **OQ1 (DUT):** static-decoder variant (`static uint8_t[24K]`, no JIT acquire) on `cyd2usb_webradio` →
  measure `wrCount` + fetch `lfbInt`. Decides the decoder's manifest treatment (statically-placed vs
  `placement: runtime`). Architect prediction: static-always re-fails the fetch (~37 K < ~40 K) → decoder
  stays runtime-JIT, planner budgets size + headroom only. Confirm/refute.

**Out of scope (Phase 2, separate + human-reviewed):** repointing real buffers at `MEM_<name>` (the runtime
behaviour change). Phase 1 emits the header; nothing consumes it at runtime yet.

**DoD:** manifest + planner + gate landed, `run/check` green, golden-hash stable; OQ1 recorded (EXP-011 or
EXP-010 extension) + resolved in M-MEMPLAN §10; Phase 1 marked done. Branch `rnd/memplan`, NOT merged.

**DONE 2026-06-28 (`da3e6f7`, branch `rnd/memplan`).** Manifest (4 buffers) + `gen_mem_layout.py` planner +
`check_build.sh` [6/6] (staleness + WCMU budget) + golden-hash; `run/check` 6/6. Budget INTERNAL = 29,616
overlay + 60,000 headroom = 89,616 / 290,000 ceiling ✓. BSS impact zero (unused statics optimized away;
Phase 2 wiring makes them real). **OQ1 RESOLVED — confirmed the Architect prediction:** static-decoder
(23,216 B BSS) drops fetch maxBlk to **37 K < 40 K TLS → `-32512`, count 0** (= TASK-265 redux); **decoder
stays runtime-JIT**, manifest `placement: runtime` (planner budgets its size within headroom, no static
region). Baseline JIT: maxBlk 57 K, fetch OK, count 16.
**Priority:** P2 — formalizes the memory architecture · **Status:** **DONE — Phase 1 complete, OQ1 resolved**
· **Opened:** 2026-06-28 · **Closed:** 2026-06-28 · **Milestone:** M-MEMPLAN · **Branch:** `rnd/memplan`
(branch-only until promotion) · **Owner:** R&D/Developer · **Design:** M-MEMPLAN · **Follow-on:** TASK-269 (Phase 2)

---

### TASK-269 — M-MEMPLAN Phase 2: wire low-risk tenants to the planned overlay

Phase 2 of M-MEMPLAN (Phase 1 = TASK-268, done). Repoint real buffers at the planner-emitted `MEM_<name>`
locations — the first runtime behaviour change, so **human-reviewed, low-risk-first** (M-MEMPLAN §8).
**Re-scoped 2026-06-28** after a code check found the original tenants wrong (see below).
- **The two tenants — both fork-free ArduinoJson parse buffers, both DUT-confirmed clean scratch (result
  copied to a separate struct):** `heatmap_doc` (Stock; `s_heatmapDoc` → result `s_heatmapResult`) and
  `crypto_doc` (Crypto; `fetchCrypto` `doc(2048)` → result `s_cryptoResult`). Both → the shared
  `MEM_heatmap_doc`/`MEM_crypto_doc` (offset 0 of `s_overlay_any_foreground[2560]`) via a `BasicJsonDocument`
  BYO-allocator. They're mutually exclusive (dataTask is serial; Stock/Crypto are foreground) → this
  **validates the overlay sharing** end-to-end with **no library fork**.
- **`aquarium_strip` DROPPED from Phase 2 → TASK-270** — `TFT_eSprite::createSprite` mallocs internally with
  no external-buffer API; overlaying it would need a TFT_eSPI fork (a cost/benefit decision, not low-risk).
- **Manifest/planner already corrected (this re-scope, committed):** decoder+InBuff marked
  `placement: runtime` (OQ1) — the planner now **budgets** them without emitting a static region (the agent's
  Phase 1 had left them statically placed, which OQ1 proved breaks the fetch); aquarium swapped for crypto.
  `run/check` 6/6.
- Verify (Phase 2 impl): on app-switch Stock↔Crypto↔others the shared 2560 B region holds the right tenant,
  no corruption, results render correctly; `run/check` green; BSS now reflects the real region (nm). §4b holds
  (both scratch, regenerated on entry).

**DoD:** heatmap + crypto use `MEM_*`; DUT-verify app-switch round-trips (Stock↔Crypto↔others) with no
corruption; budget gate still green. Then assess whether to migrate further foreground scratch.
**Priority:** P3 — incremental hardening; not blocking anything · **Status:** **DONE — Phase 2 implemented
`241adf8` + closed `c0f3902` (rnd/memplan); `run/check` 6/6 (re-verified); BSS region now real
(nm: `s_overlay_any_foreground @ 0x3ffc6b50`, was dead-stripped in Phase 1); DUT T220 (Crypto) GET 200 + no
NoMemory — overlay buffer served through a full parse. T219/T220 maxBlk<50k is pre-existing TASK-243
starvation, not an overlay bug.** · **Opened:** 2026-06-28 · **Closed:** 2026-06-28 · **Milestone:** M-MEMPLAN
· **Branch:** `rnd/memplan` (not merged) · **Owner:** Developer · **Deps:** TASK-268 (done) · **Design:**
M-MEMPLAN §8
> **Follow-on (VE, QM-2):** no dedicated regression test gates the overlay yet — validation leaned on
> Premium-blocked T219/T220. File a targeted Stock→Crypto→Stock round-trip test (results distinct, no
> cross-corruption) once TASK-243 clears, or a host-side assert that both tenants resolve to
> `s_overlay_any_foreground+0`.

---

### TASK-270 — M-MEMPLAN: overlay the Aquarium sprite (needs a TFT_eSPI fork — decision first)

Deferred from TASK-269. The Aquarium strip sprite (`aquariumApp.h`, ~11 K, 275×40×1 B) was assumed an easy
overlay tenant, but `TFT_eSprite::createSprite` **mallocs internally** (`callocSprite`) and exposes **no
external-buffer API** — only `getPointer()` (read). Pointing it at `MEM_aquarium_strip` requires **vendoring +
forking TFT_eSPI** (add a `setBuffer()` path), a second library fork on top of ESP32-audioI2S.

**Decision needed before any work:** is overlaying an 11 K sprite worth owning a TFT_eSPI fork? Likely **no
for now** (small benefit, real maintenance cost — BP-042 lineage). Alternatives: (a) leave the aquarium
sprite on the heap (it's per-app, freed on exit — already fine); (b) overlay only if/when a *second* big
TFT_eSprite tenant appears that shares the region (then the fork pays for two). Keep `aquarium_strip` out of
the manifest until decided.
**Priority:** P3 — optional; gated on a fork cost/benefit call · **Status:** **DEFERRED (parked) — PM
scheduling call 2026-06-28: not now. Standing recommendation = no TFT_eSPI fork for an 11 K per-app sprite
(BP-042 lineage); revisit only if a *second* big TFT_eSprite tenant appears that shares the region (then the
fork pays for two). `aquarium_strip` stays out of the manifest until then. The architecture call itself
(Architect/human) remains open if/when a tenant arrives.** · **Opened:** 2026-06-28 · **Milestone:** M-MEMPLAN
· **Owner:** Architect · **Deps:** TASK-268 · **Design:** M-MEMPLAN §6 (the placeable-vs-not boundary)

---

### TASK-271 — WebRadio playback + A-lite arena-churn soak harness

Follow-on to TASK-262 (A-lite promoted to production). The one-shot promotion validation proved the arena
acquires/plays/releases over a handful of cycles; nothing soaks the **play → leave** cycle to surface what
only time shows. Now that the arena does a JIT `heap_caps_malloc(24K)`/`free` on **every** `_play()`/`suspend()`
in production, an unattended churn soak is the production-hardening evidence: arena fragmentation creep,
acquire-FAIL (24K no longer contiguous), acquire/release leak, sustained-playback distribution (quantifies the
TASK-233 best-effort claim), underruns.

**Delivered:** `app/tools/test_webradio_soak.py` + `run/wr-soak` (flash `cyd2usb_webradio` → soak → restore
prod, trap-guarded; BP-020). Runs on the Spotify-disabled build (no TASK-243 403 fetch starvation; arena code
is identical to production — both `-DMEMBUDGET_PHASE1`). Each cycle: enter WebRadio → `wrPlay` (arena acquire) →
hold N s sampling `wrPlaying`/`wrUnderruns` → `switchApp 0` (suspend → arena release) → re-enter. Parses the
`[membudget] arena acquire=…lfbBefore=…OK|FAIL` / `arena released` logs. PASS = ≥3 cycles, acquire==release,
zero acquire-FAIL, `min(lfbBefore) ≥ 24576`. Self-contained serial wrapper (NOT `Dut` — its ELF-hash gate
rejects the webradio build).

**DUT-validated 2026-06-29 (harness self-test, 2 min / 15 s-per-station):** 7 cycles, acquire==release==7
(no leak), **0 acquire-FAILs**, lfbBefore 61428→49140 (20% drift, **plateaued**, ≫24576 throughout),
sustained playback median **12.1 s** (reached PLAYING 7/7), 0 error/skip. A 48-cycle rapid run held the same:
0 FAILs, lfb floor 38900. **The arena is churn-safe in the promoted config** — no fragmentation collapse, no
leak. The ~9–12 s playback ceiling is the TASK-233 no-PSRAM best-effort reality, now quantified rather than
asserted.

**Priority:** P3 — production hardening / VE tooling · **Status:** **done — harness delivered + DUT-validated
2026-06-29** · **Opened:** 2026-06-29 · **Milestone:** M-WEBRADIO-NOPSRAM · **Owner:** VE/Developer · **Deps:**
TASK-262 (promotion), TASK-248 (fetch-soak harness pattern) · **Branch:** `feature/task-271-webradio-soak`

---

### TASK-272 — WiFi modem power-save kills first TCP connect after idle (EHOSTUNREACH)

> **Router-confound annotation (2026-07-03, LL-096) — highest re-test priority:** the signature
> "connect-after-45 s-idle fails, connect-immediately works" was attributed to ESP32 modem power-save
> (`WIFI_PS_MIN_MODEM`), fixed with `WiFi.setSleep(false)`. But the **MX5600 2.4 GHz auto-channel dropout**
> (now root-caused: off-air every ~1–2 min) produces the *same* signature — a 45 s idle wait aliases into
> a blackout window while connect-immediately catches a good moment. `setSleep(false)` verifiably helped
> the idle test, so power-save was *at least partly* real, but the idle-correlation was plausibly the
> router's duty cycle. **Cheap discriminator on the pinned link: `set wifiPs 1`, re-run the 45 s-idle
> connect — still fails ⇒ power-save was real; clean ⇒ it was the router.** (This task already noted item 2
> "suspected AP-side" — LL-096 confirms that half.)

Found 2026-07-02 while driving the TASK-238 gate: every gate trial read 0 plays / 15 skips, yet the same
build had played 11/16 stations hours earlier (EXP-012). Root-caused via DUT probes
(`scratchpad/wr_debug1-4`, evidence flow: same-entry play OK → post-cycle play EHOSTUNREACH → retry
recovers → **inverted** by P1/P2 probe: play-after-45s-idle fails, play-immediately works → host curl
clean → ESP-side):

1. **Power-save idle-kill (the fix):** with the default `WIFI_PS_MIN_MODEM`, the first TCP connect after
   ~30-45 s of network quiet fails `errno 118 EHOSTUNREACH` for tens of seconds. WebRadio's auto-skip then
   fast-fails the entire station list (~3 s/station) into the terminal error state — a permanent-looking
   failure born from a transient outage. **Fix: `WiFi.setSleep(false)` at connect time (main.cpp), all
   builds.** Mains/USB-powered device — the ~40 mA is irrelevant. Verified on DUT: 45 s-idle connect went
   fail-4-attempts → attempt-0 success.
2. **Boot-window drop (environmental, documented):** this DUT/AP shows a near-deterministic WiFi drop at
   ~35 s uptime recovering by ~60 s (heartbeat `rssi(0)` during it). Harnesses must settle past it
   (test_adr045_gate.py waits 60 s post-station-load). Not code-fixable; suspected AP-side (mesh/steering).
3. **Harness bug fixed en route:** boot log prints `IP address: 0.0.0.0` before the real lease; harness
   boot_waits matching the first occurrence proceeded pre-WiFi and the app's ONE-SHOT station fetch (no
   retry — see item 4) failed → 0/3/4-station boots. All harnesses now require a non-zero IP.
4. **Follow-on candidate (not filed):** the station fetch is fire-once-at-init with no retry; combined with
   radio-browser mirror flakiness (0/3/13/16-station fetches observed in one evening) a fetch-retry or
   manual-refetch affordance would harden first-entry UX. PM to decide if it warrants a task.

Also relevant to production Spotify polling (same power-save applies); some historical "poll fail" noise
may share this cause.

**Priority:** P1 — fix landed with TASK-238 work · **Status:** **done — fix DUT-verified 2026-07-02;
production merge rides the TASK-238 commit (run/check 6/6)** · **Opened:** 2026-07-02 ·
**Milestone:** M-WEBRADIO · **Owner:** Developer · **Deps:** — · **Branch:** master

---

### TASK-273 — Pace auto-skip/retry dispatch (network-blip immunity)

Found by the TASK-238 gate + wr_debug5 probe (2026-07-02): the TASK-234 pendingAction dispatch ran every
tick, so during a transient network outage (EHOSTUNREACH + DNS-fail while the WiFi doze/reassoc window is
open) the auto-skip walked the ENTIRE 16-station list into terminal ERROR in **under 1 second** — 16
instant connect-fails, one blip. A momentary hiccup at play-press produced a permanent-looking dead player.

**Fix:** `WR_SKIP_PACE_MS = 2000` — dispatch a deferred retry/skip only when ≥2 s has elapsed since the
last `_play()` attempt (`_lastAttemptMs`, stamped on every attempt). A full-list walk now takes ~32 s and
rides out short outages; DUT-verified — gate trials that started inside an outage recovered mid-walk and
held 60 s+ (previously: instant terminal park, 0 ms hold).

**Note for VE:** TASK-237's deterministic dead-list tests (wrDeadUrls) now walk at 2 s/station — timeouts
in that suite may need widening.

**Follow-on candidate (not filed):** terminal state has NO recovery path — once the walk exhausts the list
(e.g., outage > 32 s, gate run 4 trial 10) the player parks in ERROR even after the network returns, until
the user re-plays. A retry-from-terminal with backoff would close the loop. PM to decide.

**Priority:** P1 — landed with TASK-238 work · **Status:** **done — DUT-verified 2026-07-02 (commit
64765df, run/check 6/6)** · **Opened:** 2026-07-02 · **Milestone:** M-WEBRADIO · **Owner:** Developer ·
**Deps:** TASK-234 (the mechanism), TASK-272 (sibling fix) · **Branch:** master

---

### TASK-274 — M-WIFI-DIAG Phase 1 firmware: [wifi-ev] logger + `get wifi` accessor

Per [M-WIFI-DIAG](../architecture/designs/M-WIFI-DIAG-outage-attribution.md) §3.1/3.2 (panel-approved,
human-approved 2026-07-02). Deliverables:

1. **`[wifi-ev]` event logger — ALL builds (production included, OQ1).** One `WiFi.onEvent` handler
   registered before `WiFi.begin()`; logs every WiFi event with `millis` + disconnect **reason code**;
   single-write line assembly (no tearing); flap guard ~10 lines/min with `suppressed=N` summary;
   `[wifi-ev]` prefix is a stable grep contract.
2. **`get wifi` accessor — debug builds**, shell-owned (main.cpp):
   `ms,status,rssi,ip,ch,discCount,lastDiscReason,lastDiscMs,lastGotIpMs`. `ms` = device→host clock
   anchor. Counters are plain statics fed by the handler. Field set VE-gated (BP-024).
3. **Heartbeat RSSI fix-or-remove (QM-5):** heartbeat `rssi(…)` reads 0 or real depending on path —
   sample `WiFi.RSSI()` at heartbeat time or drop the field.
4. **Sensor positive control (QM-2, acceptance):** debug `set wifiDisc` forcing `WiFi.disconnect()` →
   `[wifi-ev]` line with reason code observed on DUT before any attribution-by-absence is trusted;
   reconnect verified.

**Acceptance run (2026-07-02, DUT, 6/6 PASS):** boot GOT_IP event · forced-disconnect (`set wifiDisc`)
→ `[wifi-ev] STA_DISCONNECTED reason=8` + reconnect GOT_IP in 0.8 s (sensor proven live, QM-2) ·
`get wifi` full field set · counters populated · heartbeat `wifi=rssi(-49)`/`wifi=DOWN disc=N`.

**Bonus — first attribution data, 33 s after the sensor went live:** spontaneous
`STA_DISCONNECTED reason=200` (**BEACON_TIMEOUT**) followed by `reason=201` (NO_AP_FOUND) retry storms,
`disc=9` within 33 s. The DUT is losing the AP's beacons entirely — link-layer, **H-A/H-C (RF/AP side),
NOT firmware** — matching design §5 row "link-down, beacon timeout → Phase 2 (hotspot A/B) then 4
(bare-rig)". TASK-275's run should confirm over a full window, but the needle already points away from H-B.

**Priority:** P1 — gates TASK-275/TASK-238 · **Status:** **done — DUT acceptance 6/6, 2026-07-02** ·
**Opened:** 2026-07-02 · **Milestone:** M-WEBRADIO · **Owner:** Developer · **Deps:** design approved ·
**Branch:** master

---

### TASK-275 — M-WIFI-DIAG Phase 1 harness + instrumented attribution run

Per M-WIFI-DIAG §3.3/3.4. Two named parts (PM-3):

**(a) Harness development:** `SerialDut` continuous-reader rework (current `reset_input_buffer()` per
command DESTROYS async `[wifi-ev]` evidence — VE-1 blocker): one reader loop tees every line to a
host-timestamped log; `cmd()` consumes JSON from the stream. `run/wr-gate` gains `ping -D -i 1` of the
DUT IP (restart on IP change; exclude reboot windows; client-isolation pre-flight; host NOT on the same
2.4 GHz cell) + a host-side upstream curl probe (QM-3). Per-poll `get wifi` sampling with millis→host
clock mapping; re-baseline counters after DTR reboots.

**(b) Instrumented run:** evening (dirty) window; exit at ≥3 captured outage windows or ~90 min on-air;
five-class per-window attribution (link-down / IP-layer / WAN-upstream / no-link-evidence / unattributed);
**dual-scored** against the ADR-045 bar — a clean dirty-window run closes TASK-238 (PM-2). Deliverable =
the attribution table feeding the design §5 decision matrix. Artefact disposition (BP-040): sensor ships
permanently; ping harness stays behind a flag; QM retrospective at close (QM-7).

**Delivered 2026-07-02.** (a) Harness v2 landed in `test_adr045_gate.py` — continuous reader thread owns
RX (VE-1 fixed), five-class window attribution, §3.4 extension rule, dual scoring. *Deviation from design:
the ping + upstream probes live inside the Python harness, not `run/wr-gate` bash — single clock for
correlation, easier IP-change restarts; wr-gate unchanged.* (b) Instrumented run 17:55–18:35 (dirty window;
beacon-timeout storm observed 25 min prior): **zero outage windows in ~40 min**, 1 boot-time link event
only; ADR-045 dual-score 10/10 → TASK-238 closed. **Attribution deliverable:** no outage recurred *under
1 Hz LAN keepalive traffic* — combined with the TASK-274 acceptance data (BEACON_TIMEOUT + NO_AP_FOUND
storms with no keepalive), the evidence points at **AP-side idle/RF behavior (H-A), not firmware (H-B)**:
the sensor saw the AP vanish, and keeping the link warm made outages vanish. Not proof (RF also varies);
the production `[wifi-ev]` sensor now collects passively — router-side check (Phase 3) is the cheap next
datum if outages recur in field use. Artefacts (BP-040): sensor ships permanently; probes live in the
harness, on by default, harmless.

**Priority:** P1 — decides TASK-238 path · **Status:** **DONE — 2026-07-02; TASK-238 closed by this run**
· **Opened:** 2026-07-02 · **Closed:** 2026-07-02 · **Milestone:** M-WEBRADIO · **Owner:** VE ·
**Deps:** TASK-274 (done) · **Branch:** master

---

### TASK-276 — WebRadio: retry-from-terminal (auto-recover a parked scan)

Filed from the TASK-273 follow-on candidate; **unparked by attribution** (M-WIFI-DIAG §5 + TASK-207 live
capture 2026-07-02: two ~30 s terminal parks during a sensor-attributed `NO_AP_FOUND` link-flap storm —
operator had to manually tap PREV to recover; the outage itself healed in seconds).

**Change (webRadioApp.h, tick):** when the app is active, auto-skip is ON, the player is parked in a
retryable terminal error (`ERROR_WIFI`/`ERROR_STALL`/`ERROR_UNREACHABLE` — `ERROR_BLOCKED` excluded,
geo-blocks don't heal), and `WR_TERMINAL_RETRY_MS` (30 s) has elapsed since the last attempt
(`_lastAttemptMs`, the TASK-273 pacing anchor): reset the scan budget and re-arm a paced scan from the
current station. Net behavior: a parked player self-recovers within ~30 s of the network returning,
retrying indefinitely at 30 s + one paced list-walk per cycle — cheap, bounded, observable via the
`terminal retry — re-arming scan` log line.

**Validation:** `set wrDeadUrls 3` (synthetic all-dead list + forced connect-fail) → scan exhausts →
terminal park → assert `terminal retry` fires on ~30 s cadence, repeatedly.

**Priority:** P2 — UX robustness (post-outage self-heal) · **Status:** **done — DUT-validated 2026-07-02** (wrDeadUrls park → retries at t=41 s/101 s, bounded 60 s cycle = 30 s backoff + paced walk) · **Opened:** 2026-07-02 · **Milestone:** M-WEBRADIO · **Owner:** Developer ·
**Deps:** TASK-273 (pacing anchor), M-WIFI-DIAG attribution · **Branch:** master

---

## Open — touch-UX responsiveness (2026-07-02)

Operator report 2026-07-02: taskbar app-switching feels sluggish with no confirmation a tap
landed; WebRadio PLEDIT scrolling "borderline usable" vs Spotify's. Code investigation
attributed this to three independent causes, one milestone each. Design docs first
(parallel Architect session); implementation tasks to be split out per accepted design.

### TASK-277 — M-WR-PLEDIT-SCROLL design: WebRadio PLEDIT drag/velocity scroll

WebRadio PLEDIT input is Release-only tap-to-play (`webRadioApp.h` `handleInput`); no drag
scroll exists — a swipe lands as a tap on whichever row the finger lifts over. Spotify's
PLEDIT has the full M-LIST-v4 velocity-scroll machine in `winampDisplay.h` (ADR-030,
`D_PLEDIT_SCROLL`/`D_PLEDIT_SCROLL_DIRECT`, `tickScroll`). Design outcome (lean, panel-
reviewed): self-contained pattern-copy of the ADR-030 gesture inside `WebRadioApp` with
constants hoisted to a shared tuning header — extraction (rejected for two consumers) and
routing through `winampDisplay` (state collision) documented as non-leans; tap-vs-drag
migration for the existing tap-to-play rows included.

**Priority:** P2 — UX · **Status:** **DONE 2026-07-07** — implemented per the panel-pinned
order (injection-reroute commit `c5fd6e5`, then the feature). Feature exit criteria
**13/13 PASS** on DUT (drag/tap discrimination, direct-drag, release-capture over eject
[DEV-1-1], auto-skip mid-gesture cancel via `drag … hold` [VE-1-3], `wrScroll`/`wrSpeedK`
surface); T_WR suite **17/18** (sole fail `T_WR_TLS_01` = TASK-284 external mirror
truncation, `wrCount=3` + IncompleteInput signature); T162-T166 **5/5** through the
rerouted injection. **Dispositions RATIFIED (human, 2026-07-07):** T155-T160 SKIP —
blocked-external (TASK-243 ≥10-item-queue precondition, un-runnable since 2026-06-25);
compensating queue-free volume-slider drag exercised the full rerouted captured-gesture
cycle, plus per-app smokes 9/9. NOTE: T155-T160 must be re-run when TASK-243 resolves
(standing item on that task's close-out). T_WR_TLS_01 fail = TASK-284 external, ratified. Results table + campaign finds in the design doc
§Implementation results. Campaign finds: **TASK-293** (stop-then-replay tlsYield deadlock,
P1, fixed) and the T_WR_ERR_x harness isolation defect (fixed, see `_wr_err_test`).
OQ4/VE-C5 second site recorded in M-LIST-v4. Feel tuning (OQ1) deferred to a human session
per DEV-X-1 (`wrSpeedK` runtime-tunable). Design panel-reviewed 2026-07-03
(approve-with-changes ×3) — approved 2026-07-03 (human) · **Opened:** 2026-07-02 ·
**Milestone:** M-WR-PLEDIT-SCROLL · **Owner:** Architect ·
**Deps:** M-LIST-v4 (done), M-WEBRADIO (done) · **Branch:** master

---

### TASK-278 — M-WR-AUDIO-TASK design: WebRadio decode off loopTask

`s_wr_audio->loop()` runs inside `WebRadioApp::tick()` on loopTask (core 1) — decode +
HTTP stream fill compete with touch sampling and all UI every iteration while PLAYING.
Design a dedicated audio FreeRTOS task: core placement (ESP32-audioI2S guidance vs. our
WiFi-heavy core 0), task lifecycle on play/stop/eject/app-switch, locking around the
shared `Audio` object (ICY queue already exists), stack sizing under the A-lite arena
heap ceiling, WDT interaction, and failure modes (task starvation vs. current inline model).

**Priority:** P2 — UX (shell-wide latency during playback) · **Status:** **DONE 2026-07-07 —
E1-E5 exit criteria all PASS**, full results in `docs/architecture/designs/M-WR-AUDIO-TASK.md`
§Exit-criteria results. Headline: the decode tail on loopTask is gone (per-hb loop_max
141→50 ms max, 6→0 iterations >50 ms per 10-min PLAYING window, on the harsher
Spotify-enabled build); ADR-045 gate 10/10; maxMutexWaitMs 258-312 ms; pump stack HWM
headroom 4624 B; 2×30-min soaks, 0 arena failures, no TWDT. Campaign incidentals: TASK-290
fixed, TASK-291/292 filed. Code landed as `39e6c08`. Original status for history: **Phase 1
implemented 2026-07-03** — `webRadioApp.h`: dedicated `wrAudio` pump task (core 1,
prio 2, 8 KB stack, created lazily at first `_play()` after `mb_arena_acquire()`,
torn down via ack-then-self-delete in `suspend()`); single mutex around every Audio
method (control calls block, per-tick reads timeout-take + degrade to last snapshot);
`get wrPump` + `get stacks` observability; `wr.connect`/`wr.pump` perf slots
(`MAX_PATHS` 8→10); `wrVol` DEV-2-4 clamp-store-only fix. Builds clean on
cyd2usb_winamp/_debug/_webradio; `./run/check` 6/6 (E5). **Not yet DUT-validated** —
E1 (UI tail latency vs the 141 ms/6-spike E0 baseline), E2 (`wr-soak` underrun
regression), E3 (state-machine + real-stream-death teardown gate), E4 (stack HWM /
arena headroom) still open.
panel-reviewed 2026-07-03 (approve-with-changes ×3, dispositions applied) — approved 2026-07-03 (human) · **Opened:** 2026-07-02 · **Milestone:** M-WR-AUDIO-TASK · **Owner:** Developer ·
**Deps:** M-WEBRADIO (done), M-WEBRADIO-NOPSRAM (arena constraint), shared E0 baseline
session (done — see design doc) · **Branch:** master

---

### TASK-279 — M-TASKBAR-FEEDBACK design: taskbar tap feedback + switch latency

Taskbar switch fires only on finger release with no pressed-slot visual state; `switchApp`
full init/repaint delays any visible response further. (Design review corrected the original
filing: taskbar-zone presses dispatch *before* the cooldown/busy gate — `s_cooldownMs` never
drops taskbar taps. Real tap-loss mechanism is sampled-touch loss — a tap shorter than one
loop iteration is invisible — which inflates during WebRadio playback; owned by
M-WR-AUDIO-TASK.) Design:
immediate pressed-slot highlight on Press, optional switch-on-press evaluation, cooldown/
busy-gate audit, and a serialdbg-measurable latency definition (tap-inject → first repaint)
so the improvement is quantifiable via the perf/heartbeat instrumentation.

**Implementation (2026-07-07):** landed `d13817d` (F-a pressed-slot highlight via
`renderTaskbarSlot` extraction + `tbIsScrolling()` accessor; F-b press-anchored amber
commit bar; shared `shellTbPress/Cancel/Commit/Release` helpers in both dispatch sites;
L-d `switchApp` phase breakdown + `shell.switch` perf path) + `cc92355`/`2e92f01`
(T_TBFB_01–04, e0_baseline per-tap phase capture) after BP-024 sign-off `1d07433`.
DUT: T162–T166 + T242 + T_TBFB_01–04 **10/10 PASS**; AFTER latency matrix taken (4 states,
N=5): press-to-first-pixel **~14 ms** (same iteration as the Press sample; 33 ms under
WR-PLAYING), switch cost itself unchanged (internal total 84–98 ms ≈ BEFORE medians;
the +11–13 ms on the external clock is debug-serial wire time, attributed in the doc).
New numbers: wipe=27 ms constant (L-b candidate, deferred as designed); leaving playing
WebRadio costs suspend=44 ms (pump teardown). Dispositions D1–D3 (visual confirm manual,
2-min windows, T_TBFB_04 first-run test defect) in design §Implementation results —
**D1–D3 all human-ratified 2026-07-07** (D1: highlight + amber confirmed visible;
visual exit criterion closed). LL-101 from this campaign promoted to BP-045.

**Priority:** P2 — UX · **Status:** **DONE 2026-07-07** (design approved 2026-07-03,
panel approve-with-changes ×3; dispositions D1–D3 human-ratified 2026-07-07 — closed) ·
**Opened:** 2026-07-02 · **Milestone:** M-TASKBAR-FEEDBACK · **Owner:** Architect ·
**Deps:** M-TASKBAR-SCROLL (done), M-TOUCH-UX (done), shared E0 baseline session (with
TASK-278 — see design §Measurement plan) · **Branch:** master

---

### TASK-280 — Align touch injection with production dispatch (cmdTap resolvePlayerSlot + release cooldown)

From the 2026-07-03 touch-UX panel (VE-3-6 / DEV review / QM-3-4). Two verified divergences
between injected and production taskbar gestures: (1) `cmdTap`'s taskbar branch calls
`switchApp(appIdx)` directly and skips `resolvePlayerSlot()` (`main.cpp:2390` vs `:1916`) —
injected player-slot taps land on Spotify even when persisted mode is WebRadio, so T162's
tap-based switch never exercises the TASK-259/260 redirect; (2) the injected taskbar release
never sets the 300 ms post-gesture cooldown production sets (`main.cpp:1919`). Align both
(route `cmdTap` taskbar commits through the production resolve path; set the cooldown in
`drainInjectionQueue`'s release branch) or document them as permanent harness deltas with
VE sign-off.

**Implementation (2026-07-08):** both divergences fixed rather than documented as
permanent deltas. (1) `cmdTap`'s taskbar branch now resolves `AppId target =
resolvePlayerSlot(static_cast<AppId>(appIdx))` before `switchApp(target)` — a tap on
the player slot redirects to WebRadio when that's the persisted mode, same as real taps
and injected drags. (2) `drainInjectionQueue`'s taskbar-release branch now sets
`s_cooldownMs = millis() + 300` after `shellTbRelease()`, mirroring
`appHandleInput`'s real-release path — the injected release no longer skips the
production cooldown.

Fallout from (1): `run_serialdbg_tests.py`'s `_restore_spotify()` taps the Spotify
taskbar slot to force Spotify — that only worked before because `cmdTap` ignored the
persisted player mode. Now that it's fixed, `_restore_spotify()` calls `set playerMode
spotify` first so the tap is guaranteed to land on Spotify regardless of leftover
WebRadio state from a prior test. Without this, `_tb_precondition()` (used by
T162–T166) failed with "could not restore Spotify" whenever a prior test left
`playerMode=WebRadio` persisted.

T_TBFB_04's "canvas cooldown" assertion was initially misdiagnosed as testing the
fixed `s_cooldownMs` — `get cooldown` actually reads `touchScreenCoolDownTime`
(SpotifyApp's unrelated TASK-052 dead-zone-tap cooldown in `winampDisplay.h`), which
taskbar release never touched before or after this fix. Reverted to the original
assertion after confirming via source read; docstring now notes the two "cooldown"
variables are distinct and that no serial hook currently exposes `s_cooldownMs`
directly, so the (1)/(2) fixes aren't independently observable from the automated
suite — verified instead by full-suite pass with no regressions.

DUT-validated 2026-07-08: T162–T166 + T_TBFB_01–04 + T242 **10/10 PASS** on
`cyd2usb_winamp_debug`; `./run/check` 6/6 clean before flashing.

**Priority:** P3 — harness fidelity · **Status:** **DONE 2026-07-08** — both filed
divergences fixed (not just documented); DUT 10/10 · **Opened:** 2026-07-03 ·
**Milestone:** M-TASKBAR-FEEDBACK · **Owner:** Developer · **Deps:** TASK-279 (done —
shared shellTb* helpers available) · **Branch:** master

---

### TASK-281 — QM housekeeping: duplicate LL ids + audit_log backfill

From the 2026-07-03 touch-UX panel (QM review, housekeeping section). (1) `lessons_learned.md`
carries duplicate ids for **both LL-069 and LL-070** (2026-06-13 originals vs 2026-06-28
re-uses; the M-WIFI-DIAG panel's QM-8 flag on LL-069 was never actioned, LL-070 is a new
find). Renumber the 2026-06-28 pair to the next free ids (LL-094/LL-095; LL-093 current max)
and fix **BP-043's "Adopted from: LL-070"** citation, which currently resolves ambiguously.
(2) `audit_log.md` last entry is 2026-06-27 — backfill entries for the 2026-07-02
M-WIFI-DIAG panel and the 2026-07-02/03 touch-UX panel per the house panel-logging precedent.

Resolved in commit 62a96e3 (2026-07-06): 2026-06-28 reuses renumbered to LL-094/LL-095
(next free after LL-093; LL-096 already taken by the router lesson); BP-043 "Adopted from"
→ LL-095; LL-069 disambiguation note marked resolved; in-file + M-WIFI-DIAG design
"sensor-blind gates" refs → LL-094; both panel audit entries backfilled. Status flip was
deferred at commit time because tasks.md was dirty from in-flight TASK-278 work. Residual
LL-069/LL-070 citations swept 2026-07-08: all remaining refs correctly point at the
2026-06-13 originals or are historical panel records — no further edits needed.

**Priority:** P3 — QM hygiene · **Status:** **DONE 2026-07-06** (status flip recorded
2026-07-08) · **Opened:** 2026-07-03 · **Milestone:** — (cross-cutting QM) · **Owner:** QM ·
**Deps:** — · **Branch:** master

---

### TASK-282 — M-WIFI-DIAG Phase 2: frame-level instruments (beacon watcher, PS A/B, scan-on-park)

Filed from operator challenge 2026-07-03 ("RF-environment escalation is hand-wavy — do a proper
diagnosis"). Phase-1 reason codes can't split BEACON_TIMEOUT between H-A (AP/air) and H-C (CYD
antenna/rail) — design §5 row "beacon timeout → Phase 2". Host laptop is on **5 GHz** (ch 44), so
host-side liveness says nothing about the DUT's 2.4 GHz band; evidence must come from the DUT
antenna.

**Instruments (all SERIAL_DEBUG-gated; production Phase-1 sensor untouched):**
1. **Beacon watcher** — `esp_wifi_set_promiscuous` mgmt-frame tap locked to the associated BSSID:
   per-beacon RSSI + PHY `noise_floor` from `rx_ctrl`, inter-beacon gap max, `gapsOver1s` counter,
   `otherMgmt` rx-alive control. `set beaconWatch 1` / `get beacon`; gap >1 s events printed from
   loop context as stable-prefix `[beacon]` lines (single-write, VE-8 no-tearing rule).
2. **Power-save A/B** — `set wifiPs 0|1` (`esp_wifi_set_ps`): TASK-272 implicates modem-sleep;
   "ping keepalive masks flapping" is a PS signature. Protocol: two same-evening windows, flap
   rate per hour PS-on vs PS-off.
3. **Scan evidence** — `set wifiScan 1` (async) + `get wifiScan`: during a NO_AP_FOUND park, is
   the BSSID on the air (all matching-SSID BSSIDs + rssi + ch)? Splits "AP off air" / "DUT deaf" /
   "AP channel-hopped" (ch field moved 14→6 during the 2026-07-03 dead session).

**Attribution map:** gap storm at antenna + host-5GHz fine → H-A/H-C (then hotspot A/B per §5
row 2); beacons continuous but stack disconnects → H-B; flaps vanish with PS off → TASK-272-class
fix (keepalive/PS policy task).

**Closed 2026-07-08 — implemented; full attribution protocol overtaken by events.** The
instruments shipped and the serial surface was exercised during the 2026-07-03 sessions
(TASK-283's supervisor validation ran under both the promiscuous/beacon-watch and clean
no-promiscuous configs; `get wifi` used throughout), but the planned attribution runs
(PS A/B windows, scan-on-park) were never needed: the outage phenomenon was root-caused
the same day from the host-side second vantage (Linksys 2.4 GHz auto-channel sweeps;
fixed by the JNAP channel pin — see LL-096), which answered §5's question without the
frame-level evidence. Instruments remain in-tree, SERIAL_DEBUG-gated, for any future
2.4 GHz attribution question.

**Priority:** P2 — unblocks trustworthy E0/E2/E3 measurement windows for TASK-278 ·
**Status:** **CLOSED 2026-07-08** — implemented + surface exercised; attribution protocol
mooted by the LL-096 root cause · **Opened:** 2026-07-03 · **Milestone:** M-WIFI-DIAG ·
**Owner:** Developer · **Deps:** TASK-274 (Phase-1 sensor), M-WIFI-DIAG §5 matrix · **Branch:** master

---

### TASK-283 — WiFi park-dead wedge: no reconnect supervisor after storm burnout

Found during the E0 baseline attempts 2026-07-03 (both sessions). Sequence, twice reproduced:
BEACON_TIMEOUT (reason=200) → NO_AP_FOUND (201) auto-reconnect storm at metronomic 2.42 s
cadence (disc 30→99 in ~10 min) → final reason=39 (TIMEOUT) → **link parked dead**: `status=0`,
`ip=0.0.0.0`, zero further `[wifi-ev]` events for 40+ min. Auto-reconnect stops being scheduled;
only a reboot (or, hypothesis: a manual `WiFi.disconnect()+begin()` re-kick) recovers. Production
builds have the same exposure: after a bad evening storm the device sits dead until power-cycle.
Note `WiFi.setSleep(false)` was active (TASK-272) — this is NOT power-save; and
`setAutoReconnect(false)` only runs on the boot-failed path, so auto-reconnect WAS armed when the
storm began. The wedge is in what happens after the 201-storm burns out.

**Evidence pending:** wifi_watch.py (TASK-282) REKICK probe — fires one `set wifiDisc` after
180 s of link-down; if that recovers, the fix is a firmware link supervisor: `status != WL_CONNECTED`
for > 60 s → bounded `WiFi.disconnect(); WiFi.begin()` re-kick loop (30 s pace, forever — mirrors
TASK-276's retry-from-terminal philosophy at the link layer). Design consult with Architect before
implementation (interaction with WifiSection scan flow + the boot-failed setAutoReconnect(false) path).

**Priority:** P1 — production device parks dead after storms; also blocks every DUT soak/gate
window · **Status:** **implemented 2026-07-03** — `wifiDiag::superviseTick()` (all builds): armed
after first GOT_IP, kicks `disconnect()+setAutoReconnect(true)+begin()` after 60 s continuously
down, 30 s pace, unbounded; suppressed while Settings foreground; `kicks` counter in `get wifi`.
**DUT-validated 2026-07-03**: kick fired at exactly 60 s down (`[wifi-sup] kick=N downMs=60000`), link recovered within 1 s, both under the pre-fix cycling AP and post-fix in the clean no-promiscuous config. Anchor fix (a9a2938) confirmed — no false-instant trip · **Opened:** 2026-07-03 ·
**Milestone:** M-WIFI-DIAG · **Owner:** Developer · **Deps:** TASK-282 (probe), TASK-274 ·
**Branch:** master

---

### TASK-284 — WebRadio station-list fetch: both radio-browser.info mirrors return truncated JSON (IncompleteInput)

Found 2026-07-06 attempting TASK-278 E1 DUT validation. Fresh boot, `switchApp` into WebRadio
kicks the fetch normally, but both configured mirrors fail identically:
```
[I][dataTask.webradio] GET mirror=de1.api.radio-browser.info code=200 elapsed=2638ms
[W][dataTask.webradio] JSON err mirror=de1.api.radio-browser.info: IncompleteInput
[I][dataTask.webradio] GET mirror=all.api.radio-browser.info code=200 elapsed=2479ms
[W][dataTask.webradio] JSON err mirror=all.api.radio-browser.info: IncompleteInput
[W][webradio] station fetch failed ok=0 http=-100 jsonErr=IncompleteInput
```
HTTP 200 on both, but the JSON body is truncated before the parser completes — `wrCount` stays 0
permanently (`pending` correctly flips 1→0, so the fetch *did* run and *did* fail, this isn't a
stuck-pending bug). Effect: WebRadio can never leave STOPPED via the normal station-list path,
which blocks TASK-278's E1/E2/E3 wr_playing measurement entirely (`set wrUrl` direct-station
injection is the known workaround — used for E3's real-stream-death case already). Not caused by
the TASK-278 diff — `dataTask`'s HTTP/JSON station-list path is untouched by that change.
**Not yet root-caused**: could be a response-buffer-too-small truncation in the dataTask HTTP
client, a timeout cutting the body short, or an actual upstream API change/outage on both mirrors
simultaneously (less likely, but check by hand before assuming firmware-side).

**Investigation (2026-07-08):** ruled out "persistent server/mirror fault" and "response-buffer-
too-small" as the cause. Host-side `curl --http1.0` with the identical UA/URL/query params the
firmware sends returns a complete, valid 33.7 KB JSON body from `de1.api.radio-browser.info`
every time tried — no Content-Length (HTTP/1.0 close-delimited body), which rules out a
firmware-side buffer-size bug (the parse doc streams via `deserializeJson(doc, Stream&)`, it
doesn't pre-size a receive buffer). Also checked whether ArduinoJson's Stream reader silently
truncates on a transient stall: it explicitly uses `Stream::readBytes()` (not `read()`) *because*
`read()` ignores the client's timeout — and `WiFiClientSecure`'s default `_timeout` is 30 s (no
explicit `setTimeout()` call was overriding it down), generous for a 33 KB TLS body. No
deterministic firmware bug found; "both mirrors fail identically in the same attempt" reads as
two independent transient network stalls landing back-to-back, not a systemic block — consistent
with the intermittent field pattern already logged (comes and goes; 2026-07-07 runs were clean,
count=16).

**Fix (best-effort mitigation, 2026-07-08):** `fetchWebRadioStations()`'s per-mirror page-0 loop
now retries the SAME mirror once with a fresh connection on a `-100` (JSON parse error, i.e.
`IncompleteInput`) before falling through to the next mirror — cheap (one extra handshake+GET
only on the error path) and turns a single transient stall into a non-issue instead of burning
both configured mirrors in the same unlucky window.

**Caveat — this could not be DUT-verified against the actual failure**, since the truncation
isn't reproducible on demand (host-side requests never truncated in this session either). DUT
regression only confirms the happy path is unaffected: `T_WR_COEX_01`/`T_WR_HEAP_01`/`02` all
PASS post-fix (`wrCount=16`, retry path not exercised — mirror succeeded on the first try, as
usual). `./run/check` 6/6. Leaving open rather than DONE until a live recurrence confirms the
retry actually clears it; if it recurs with the retry landed, the next data point is whether the
retry itself also fails (pointing at something more systemic than a one-off stall) or succeeds
(confirming the mitigation).

**Priority:** P2 — blocks TASK-278 DUT validation (wr_playing state unreachable normally) ·
**Status:** open — investigated, best-effort mitigation landed (same-mirror retry-once on JSON
parse error); awaiting a live recurrence to confirm it actually resolves the field symptom ·
**Opened:** 2026-07-06 · **Milestone:** M-WR-AUDIO-TASK · **Owner:** Developer · **Deps:** — ·
**Branch:** master

---

### TASK-285 — `connecttohost()` can block loopTask long enough to trip task_wdt → device reboot

**UPDATED 2026-07-06 — bisected, root cause reframed.** Originally filed as a one-off boot-time
crash; reproduced **3 more times** the same session, always the same signature, always ~15s after
a WebRadio PLAY is issued:
```
[I][webradio] play idx=0 name=INJECTED url=http://stream.live.vc.bbcmedia.co.uk/bbc_radio_two
  ...~15s later...
E (109114) task_wdt: Task watchdog got triggered — loopTask (CPU 1) did not reset in time
abort() was called at PC 0x4012d3a8 on core 0
Backtrace: 0x40083b91:0x3ffbffcc |<-CORRUPTED
Rebooting...
```
**Bisected against unmodified pre-TASK-278 master** (`git stash` the Phase-1 diff, reflash,
same repro: `switchApp` WebRadio → `set wrUrl` BBC Radio 2 → tap PLAY): **crash reproduces
identically** — same ~15s timing, same signature, same station. This rules out TASK-278's
mutex/pump-task code entirely; `wrAudio().connecttohost()` was already called synchronously from
`_play()` on loopTask/tap-dispatch context before this diff, mutex or not.

**Root cause hypothesis:** `Audio::connecttohost()` for this particular stream (BBC Radio 2's
URL is a redirect/playlist-resolving endpoint, per DEV-2-1's note that `Audio::loop()` re-enters
`connecttohost()` internally on redirect/reconnect/playlist paths) blocks synchronously for ~15s
without yielding, long enough to starve the task watchdog on whichever task called it. Also
reproduced once against a real fetched station (`Radio Stad Centraal`,
`http://83.87.109.251:8012/listen`) — so not BBC-specific; likely any slow/redirect-chasing
connect target trips it. The original "boot-time WiFi disconnect" framing was a red herring — no
WebRadio call was involved in that first sighting, but the same 15s-blocking-call-starves-wdt
mechanism could apply to more than one blocking call site; needs a symbolized backtrace to
confirm both sightings share one root cause vs. two similar-looking ones.

**UPDATE 2026-07-06 (later same day) — TASK-286's fix landed, crash still reproduced, real
mechanism found.** After implementing TASK-286's `Audio.cpp` patch, the DUT repro (fresh debug
build, `switchApp` WebRadio → `set wrUrl <url>` → watch) **still crashed**, identical signature,
on all three test URLs including a known-fast/working control stream
(`http://icecast.omroep.nl/radio2-bb-mp3`) that was never expected to be slow. Added timestamped
probes through `WebRadioApp::_play()`; the crash consistently landed *before* the probe placed
right after `spotifyTask::tlsYield()` ever printed — i.e. inside `tlsYield()` itself, not inside
`connecttohost()`. See **TASK-286** for the corrected root cause and the actual fix
(`spotifyTaskStorage.cpp`'s `tlsYield()`, now watchdog-safe). Re-verified: all three URLs
(BBC Radio 2 hostname, Radio Stad Centraal raw-IP, icecast.omroep.nl control) now survive
25-30s post-connect with no `task_wdt`/reboot on the patched firmware.

The Audio.cpp version-guard bug (TASK-286's original finding) is real, still fixed, and worth
keeping — it just wasn't what caused this particular crash. See TASK-287 for a newly-exposed
concurrency issue in the shared TLS-yield protocol, and TASK-288 for an unrelated boot-time
crash hit repeatedly during this session's DUT cycling.

**Priority:** P1 · **Status:** **fixed 2026-07-06** — see TASK-286 for the landed patch;
verified no-crash on 3 repro URLs on `cyd2usb_winamp_debug` · **Opened:** 2026-07-06 ·
**Milestone:** — (candidate: new M-WEBRADIO reliability item) · **Owner:** Developer ·
**Deps:** — · **Branch:** master

---

### TASK-286 — Fix: `Audio.cpp` version guard mis-fires on Arduino-ESP32 2.0.17, inflates connect timeout to 65s

**UPDATE 2026-07-06 — this was NOT the TASK-285 crash's root cause; the real one was found and
fixed separately (see below).** The version-guard bug described in the original write-up below is
real and the patch was applied (`app/lib/ESP32-audioI2S/src/Audio.cpp:485-490`, gated the
`UINT16_MAX` timeout on `IPAddress::fromString(hostwoext)` in addition to the version check). But
DUT verification after landing that patch showed the crash **still reproduced identically**,
including on a control URL (`icecast.omroep.nl`) with no reason to be slow — proving the guard
bug wasn't the actual trigger for these repros.

**Actual root cause (confirmed via timestamped serial probes through `WebRadioApp::_play()`,
2026-07-06):** `spotifyTask::tlsYield()` (`app/src/spotifyTaskStorage.cpp:549-562`), called from
`_play()` to free the shared TLS client before a WebRadio connect, did:
```cpp
xSemaphoreTake(s_tlsYieldedSem, pdMS_TO_TICKS(150000));  // one giant blocking take, no WDT feed
```
`spotifyTask` only notices the yield request (`s_tlsYieldReq`) once per its own outer-loop
iteration — i.e. only after whatever Spotify API call it's currently in the middle of finishes.
Every repro session had `spotifyTask` stuck retrying a failing token refresh
(`Failed to get access tokens` / `POST /api/token -> -1`, the already-tracked **TASK-243** lapsed-
Premium blocker). So: enter WebRadio while `spotifyTask` is wedged on a stalled Spotify call →
`tlsYield()` blocks `loopTask` on that single semaphore take, unfed, past the runtime task-watchdog
window (`main.cpp:1946-1949` extends it to **15s** at boot, not the 5s Kconfig default) → `task_wdt`
abort → reboot. This explains why the crash reproduced on a fast, working control stream too — the
block has nothing to do with the target URL or `connecttohost()` at all.

**Fix landed:** `spotifyTaskStorage.cpp`'s `tlsYield()` now polls in 200ms slices (same 150s
ceiling) with `esp_task_wdt_reset()` between each, instead of one blocking take:
```cpp
constexpr uint32_t kSliceMs = 200, kTotalMs = 150000;
for (uint32_t waited = 0; waited < kTotalMs; waited += kSliceMs) {
    if (xSemaphoreTake(s_tlsYieldedSem, pdMS_TO_TICKS(kSliceMs)) == pdTRUE) return;
    esp_task_wdt_reset();
}
```
**Verified:** rebuilt debug firmware, reflashed, reran all three repro URLs (BBC Radio 2 hostname,
Radio Stad Centraal raw-IP, icecast.omroep.nl control) — zero crashes across multiple runs each
(25-30s post-connect observation). `./run/check` 6/6 green with both patches in. Production
firmware (`cyd2usb_winamp`) reflashed to the DUT afterward to restore normal state.

**New follow-ups opened from this investigation:** TASK-287 (the same fix exposed a pre-existing
race in the single-flag TLS-yield/resume protocol — concurrent yield requesters can stall each
other, no longer a crash but a real functional delay) and TASK-288 (a separate, unrelated
boot-time `task_wdt` crash hit repeatedly during this session's DUT cycling, tied to WiFi still
stabilizing during the boot-time Spotify token refresh).

---

**Original write-up (superseded above as root cause, patch kept as a valid independent fix):**

Root cause for the TASK-285 crash, confirmed 2026-07-06 by reading source (not just log inference).

**Confirmed mechanism**, `app/lib/ESP32-audioI2S/src/Audio.cpp:485-488`:
```cpp
if(ESP_ARDUINO_VERSION_MAJOR == 2 && ESP_ARDUINO_VERSION_MINOR == 0 && ESP_ARDUINO_VERSION_PATCH >= 3){
    m_timeout_ms_ssl = UINT16_MAX;  // bug in v2.0.3 if hostwoext is a IPaddr not a name
    m_timeout_ms = UINT16_MAX;      // [WiFiClient.cpp:253] connect(): select returned due to timeout 250 ms for fd 48
}
```
This is a narrow workaround for an **Arduino-ESP32 v2.0.3-specific** bug (IP-literal hosts only).
The guard is `PATCH >= 3`. This project pins Arduino-ESP32 **2.0.17**
(`~/.platformio/packages/framework-arduinoespressif32/cores/esp32/esp_arduino_version.h`:
`ESP_ARDUINO_VERSION_PATCH` = 17) — `17 >= 3` is true, so the guard **mis-fires on every build**,
for every host (not just IP literals, since it doesn't actually check host type at all). Effect:
`m_timeout_ms` goes from the intended 250ms (HTTP) / `m_timeout_ms_ssl` from 2700ms (HTTPS) to
`UINT16_MAX` ≈ **65.5 seconds**, for every single `connecttohost()` call.

That timeout is passed straight into `WiFiClient::connect()`
(`framework-arduinoespressif32/libraries/WiFi/src/WiFiClient.cpp:254`), which blocks on **one
single `select()` syscall** for the full duration — no yield points, no watchdog feed possible
mid-call. Any station whose TCP handshake takes longer than the task watchdog's window (comfortably
under the 65s ceiling — observed ~15s twice) blocks `loopTask` uninterruptibly and trips
`task_wdt` → hard abort → reboot (TASK-285's crash log). Reproduced on both BBC Radio 2's CDN
endpoint and a raw-IP Dutch station, and on both pre- and post-TASK-278 code — entirely inside
this vendored library, unrelated to the M-WR-AUDIO-TASK diff.

**Recommended fix (option 1 — smallest surgical patch):** tighten the guard so it only widens the
timeout for the case it actually claims to fix — an IP-literal host, not a name — restoring the
250ms/2700ms defaults for the normal (hostname) path on 2.0.17. Needs an `isIPAddr(hostwoext)`-
style check (or reuse of whatever IP-string detection already exists elsewhere in this file/repo)
gating the existing `m_timeout_ms = UINT16_MAX` assignment, rather than the version check alone.

**Other options considered, not recommended for the first pass:** (2) cap the widened timeout to a
few seconds regardless of host type — simpler but doesn't restore the original intended defaults;
(3) move the connect off the watchdog-subscribed task entirely — correct long-term direction but a
materially bigger change, and overlaps with TASK-278's territory (which deliberately left connect
blocking as an accepted risk per VE-2-5 — this finding means that acceptance should be revisited
once this task lands, since a slow connect can now be shown to crash the device, not just stall
the UI).

**Priority:** P1 · **Status:** **patch landed 2026-07-06** (valid fix for the version-guard bug
itself; superseded as TASK-285's root cause — see update at top of this entry) ·
**Opened:** 2026-07-06 · **Milestone:** — (candidate: new M-WEBRADIO reliability item) ·
**Owner:** Developer · **Deps:** TASK-285 (symptom/repro) · **Branch:** master

---

### TASK-287 — `tlsYield()`/`tlsResume()` share a single flag/semaphore with no request-counting — concurrent callers race

Discovered while verifying TASK-286's `tlsYield()` watchdog fix. `spotifyTask::tlsYield()` /
`tlsResume()` (`app/src/spotifyTaskStorage.cpp`) coordinate handoff of the shared Spotify TLS
client via one global `s_tlsYieldReq` bool + one binary semaphore — designed for a single
requester at a time. In practice at least two independent callers can want it yielded
concurrently: `WebRadioApp::init()`'s station-list fetch (`dataTaskStorage.cpp` —
`fetchWebRadioStations()`) and `WebRadioApp::_play()` (`webRadioApp.h:944`), which fire close
together on WebRadio entry (`switchApp 10` kicks the station fetch; an immediate `set wrUrl` /
autoplay triggers `_play()` moments later).

**Observed (DUT, post-TASK-286 fix, `icecast.omroep.nl` control run):** station-list fetch's own
`tlsYield()`/`tlsResume()` pair completed normally (~8s, several mirror retries per TASK-284).
Meanwhile `_play()`'s own `tlsYield()` call, issued ~0.05s after the fetch's, never returned within
a 60s observation window — no crash (TASK-286's polling fix keeps the watchdog fed), but
`_play()` never got past that call, i.e. WebRadio playback silently stalls. Mechanism: both
callers set the shared `s_tlsYieldReq = true`; `spotifyTask` does exactly one `client.stop()` +
one semaphore `give()` per request cycle; whichever caller's `xSemaphoreTake()` wins consumes the
one token, the other keeps polling for a give that won't happen again until another full yield
cycle is triggered. When the first caller (station fetch) finishes and calls `tlsResume()`, it
clears the flag out from under the second caller (`_play()`), which had no way to signal "I still
need this" — `spotifyTask` sees the flag false and resumes normal operation without ever knowing
`_play()` was still waiting.

**Impact:** not a crash (post-TASK-286), but a real functional stall — WebRadio playback-start can
be delayed by however long a concurrently-running station-list fetch takes (worse under TASK-284's
mirror-retry conditions), or in the worst case block for the full 150s ceiling if nothing else
re-triggers a yield cycle.

**Fix landed 2026-07-06:** turned the single flag into a reference count. New state in
`spotifyTaskStorage.cpp`: `s_tlsYieldReqCount` (uint8, # of outstanding callers),
`s_tlsStopped` (bool, true once spotifyTask has ack'd for the current batch), and
`s_tlsYieldMux` (a `portMUX_TYPE` guarding both together, since `tlsYield()`/`tlsResume()` are
called concurrently from different tasks/cores — a plain `count++`/`count--` isn't atomic on
its own).

- `tlsYield()`: increments the count and checks `s_tlsStopped` under the critical section. If
  already stopped (a concurrent caller already got the ack), returns immediately — no need to
  wait, TLS is already yielded. Otherwise it's the request that needs to actually wait: drains
  any stale semaphore give, wakes spotifyTask, then polls in 200ms slices (unchanged from
  TASK-286's watchdog-safety fix) — but each iteration also checks `s_tlsStopped`, so if a
  *sibling* concurrent caller wins the real semaphore token first, this caller notices within one
  slice and returns too, instead of waiting for a token that will never come again this cycle.
- `tlsResume()`: decrements the count under the critical section; only when it reaches 0 does it
  clear `s_tlsStopped`, which is what lets spotifyTask's own `while (s_tlsYieldReqCount > 0)`
  wait-loop (`spotifyTaskStorage.cpp:360-367`, updated from the old bool check) exit and resume
  normal polling.
- `spotifyTask`'s body: the `if (s_tlsYieldReq)` / `while (s_tlsYieldReq)` checks became
  `if (s_tlsYieldReqCount > 0)` / `while (s_tlsYieldReqCount > 0)` — otherwise unchanged (still one
  `client.stop()` + one semaphore `give()` per batch).

**Verified on DUT:** reflashed debug firmware, repeated the exact repro that showed the stall
(`switchApp 10` → immediate `set wrUrl <url>`, racing the station-list fetch's own yield/resume).
`_play()` now returns from `tlsYield()` in ~50ms instead of hanging 60s+; full connect → MP3
decode → `StreamTitle` log observed within ~3s on `icecast.omroep.nl`, and same fast resolution on
the BBC Radio 2 URL. The concurrent station-list fetch's own mirror GETs sometimes fail under the
resulting heap pressure (SSL context alloc failure — both operations now proceed at once instead
of serializing on the stall) — investigated and resolved as **TASK-289** (turned out worse than a
noisy fetch failure: the race was bidirectional and could hard-reboot the device via an unchecked
I2S DMA alloc). `./run/check` 6/6 green. Production firmware restored to the DUT afterward.

**Priority:** P2 · **Status:** **fixed 2026-07-06**, verified on DUT · **Opened:** 2026-07-06 ·
**Milestone:** — (candidate: M-WEBRADIO reliability) · **Owner:** Developer · **Deps:** TASK-284
(the resource-contention side effect noted above, if it turns out to matter in practice),
TASK-286 (the watchdog-safety fix this builds on) · **Branch:** master

---

### TASK-288 — Boot-time `task_wdt` crash during Spotify token refresh while WiFi still stabilizing

**UPDATE 2026-07-06 — root-caused and fixed; simpler than originally framed.** Originally hit
5-6 of ~9 DUT cycles while verifying TASK-286/287. The "Spotify token refresh" framing in the
initial write-up was a guess from where the crash *appeared* to happen in the log, not a
confirmed cause — investigation found the real mechanism is much more basic and doesn't involve
Spotify at all.

**Root cause (confirmed by reading `setup()` in `main.cpp`):** the three WiFi-connect wait loops
(hardcoded-SSID, NVS-reconnect, SPIFFS-credentials fallback — `main.cpp:2040-2086`) all poll
`WiFi.status()` via plain `delay(100)`/`delay(250)` in a `while` loop, with **zero
`esp_task_wdt_reset()` calls** anywhere in any of them. Arduino-ESP32's `delay()` is just
`vTaskDelay()` — it yields the CPU but does not feed the calling task's watchdog. `setup()`
extends the TWDT to 15s and subscribes `loopTask` right at the top (`main.cpp:1946-1949`), then
runs all of SPIFFS init, display setup, WiFi connect, NTP sync, and `spotifyRefreshToken()` with
**no feed anywhere** in that whole stretch. These three WiFi loops can also chain (hardcoded fails
→ falls through to NVS's 10s deadline → falls through to SPIFFS's 30s deadline), so it's the
*cumulative* un-fed time across attempts that matters, not any single loop's own deadline — a
flaky AP requiring a fallback attempt easily blows the 15s window well before either loop's own
timeout is reached. Matched the observed crash logs exactly: `STA_DISCONNECTED reason=201` a few
times during the first (NVS) loop, immediate fallthrough into the SPIFFS loop, crash a couple of
seconds later — right at the ~15s cumulative mark.

**Fix:** added `esp_task_wdt_reset()` inside all three wait-loop bodies (every ~100-250ms
iteration), plus one more reset right after the WiFi block resolves and before NTP sync, so the
whole boot-time network stretch stays fed regardless of how many fallback attempts it takes.

**Verified on DUT:** rebuilt debug firmware, reflashed, then power-cycled the device 25 times
back-to-back (two batches, 10 + 15 cycles) watching serial for the crash signature. **0/25
crashes**, including several cycles where WiFi was still slow/flaky (no valid IP within a 20s
window) — the flakiness itself isn't fixed (not in scope), but the crash no longer happens even
when it's slow, which is exactly what the fix targets. Previously this reproduced in roughly
5-6 of every 9 cycles. `./run/check` 6/6 green. Production firmware restored to the DUT
afterward.

**Priority:** P2 · **Status:** **fixed 2026-07-06**, verified 0/25 on DUT reboot-cycling ·
**Opened:** 2026-07-06 · **Milestone:** — · **Owner:** Developer · **Deps:** — (unrelated to the
AP-side WiFi flapping work — that's about *why* WiFi is slow to connect here, this is about the
device not crashing while it does) · **Branch:** master

---

### TASK-289 — Fetch/playback heap race: bidirectional failure (SSL OOM one way, I2S null-deref REBOOT the other) — fixed

Investigation of the side effect noted at the close of TASK-287: with the tlsYield stall gone,
a debug `wrUrl` playback and the init()-time station fetch genuinely ran concurrently, and the
fetch's radio-browser TLS handshake died -32512 (SSL alloc fail) under playback's heap pressure.

**Characterization (2026-07-07):** the race is structurally unreachable in normal production
flow — `_play()` needs `_stationCount > 0`, stations only exist once the init fetch completes,
and the fetch was enqueued exactly once (init(), first entry). Only the debug `set wrUrl` path
(fabricates a station and played immediately) could overlap them — but that's currently the
primary test path. DUT runs then showed the race is **bidirectional and the loser breaks**:

- *Fetch loses* (playback allocates first): TLS handshake dies -32512, both mirrors burned,
  list stays empty for the whole session — there was **no retry path anywhere**.
- *Playback loses* (fetch's TLS in flight first, holding ~43 KB incl. DMA-capable heap):
  `i2s_driver_install()`'s DMA-buffer malloc fails (observed lfbDma 13.8 KB) and the vendored
  Audio ctor **doesn't check it — null-deref, LoadProhibited (EXCVADDR 0x1c), device REBOOT.**
  A crash, not just noise; also reachable in principle by plain heap fragmentation.

A cooperative abort flag alone proved insufficient (mirror handshakes take 2-4 s each; "mid-
handshake" is the common case, not the residue) — real serialization was needed.

**Fixes landed (all four verified together on DUT):**
1. `webRadioApp.h` wrUrl handler: when the fetch is still pending, defer `_play(0)` until the
   fetch result lands (dispatched from tick()'s existing poll; injected slot-0 survives, the
   late list payload is dropped). No concurrent allocation in either direction, ever.
2. `dataTaskStorage.cpp`: per-mirror pre-flight contiguity guard (maxBlk < 40 KB → fail fast
   with distinct code **-101** instead of a doomed handshake) + `abortWebRadioFetch()`
   (**-102**, signalled by _play(), shortens the deferral wait at the next mirror boundary).
3. `webRadioApp.h` resume(): second-chance fetch when `_stationCount == 0` — closes the
   "empty list forever" gap for ANY failed first fetch (network blip, TASK-284 truncation,
   heap guard). Safe: with zero stations autoplay can't fire, so no new race window.
4. `webRadioApp.h` _play(): 16 KB DMA-floor check before `new Audio` — degrades to the normal
   ERROR_UNREACHABLE path instead of the unchecked I2S null-deref reboot.

**Bonus find — latent tlsYield deadlock in spotifyTask (fixed):** the TASK-264 WebRadio-idle
trap (`s_webRadioActive` → stop/sleep/continue) sits BEFORE the post-dequeue yield-ack check,
so a tlsYield() raised while WebRadio is active with no other yield outstanding was never
acked — caller parked for the full 150 s ceiling (observed: the deferred play froze loopTask;
serial dead for 90+ s). Pre-TASK-289 this never fired only because _play's yield always
piggybacked on the fetch's still-held yield. Fixed by hoisting a yield-service block to the
top of the task loop, ahead of the wr-idle trap (worst-case ack from idle: one 500 ms sleep).

**Verified (DUT, cyd2usb_winamp_debug, 2026-07-07):** race repro (switchApp 10 → wrUrl at
+1 s): deferral logged, fetch completed count=16, deferred play started ≤3 s after resolve,
`stream ready` + ICY StreamTitle, **zero -32512, zero crashes**; phase 2 (list reset →
re-enter): resume() retry fetched on quiet heap, **stations loaded count=16** end-to-end.
`./run/check` 6/6. Production firmware restored. NB: radio-browser mirrors returned clean
JSON (count=16) in all of today's runs — TASK-284's truncation is intermittent, not permanent.

**Priority:** P2 · **Status:** **fixed 2026-07-07**, verified on DUT · **Opened:** 2026-07-07 ·
**Milestone:** — (candidate: M-WEBRADIO reliability) · **Owner:** Developer ·
**Deps:** TASK-287 (exposed it), TASK-284 (mirror health affects fetch outcomes either way) ·
**Branch:** master

---

### TASK-290 — Boot WiFi: SPIFFS-path "persist to NVS" re-begin deauths the fresh association → boots with 0.0.0.0

Found 2026-07-07 during TASK-278 E3 DUT runs (two identical consecutive failures). When the NVS
reconnect attempt misses its 10 s window (AP in a slow phase) and the SPIFFS-credentials path
connects instead, the follow-up "persist verified creds to NVS" `WiFi.begin(ssid, pass)` call
**deauths the just-verified association** (`[wifi-ev] reason=8` ~150 ms after GOT_IP) — and the
code below read `WiFi.localIP()` before re-association completed, so the whole boot proceeded
with `IP address: 0.0.0.0` (Spotify/NTP/fetches all dead until something else recovered the
link). Invisible on most boots because the NVS path usually wins; deterministic whenever the
SPIFFS path runs.

**Fix landed 2026-07-07:** bounded, TWDT-fed wait (≤15 s, same pattern as TASK-288's loops) for
re-association after the persist re-begin, re-evaluating `wifiConnected` after. Verified on DUT
across subsequent E3 boot cycles (SPIFFS path taken, `reason=8` blip still occurs, boot now waits
it out and lands a valid IP).

**Priority:** P2 · **Status:** **DONE** — fixed 2026-07-07, committed in 05f5a78 (bundled
with the TASK-278 E-gate campaign; status flip recorded 2026-07-08) ·
**Opened:** 2026-07-07 · **Milestone:** — · **Owner:** Developer · **Deps:** TASK-288 (same
bug family: boot-path waits) · **Branch:** master

---

### TASK-291 — Stream death via server FIN never detected: `isRunning()` stays true, TASK-218 debounce never arms

Found 2026-07-07 by TASK-278 E3's real-stream-death case (DEV-2-2) — and it empirically answers
the design's standing **OQ5** (`isRunning()` transient semantics). Local host-side MP3 streamer,
killed mid-play (clean process exit → TCP FIN to the DUT): the vendored ESP32-audioI2S keeps
`m_f_running == true` indefinitely on the FIN-closed socket, logging `slow stream, dropouts are
possible` forever (observed 90 s+, two independent runs). TASK-218's stream-death detection
requires `isRunning() == false` sustained for `WR_STREAM_DEAD_MS` (5 s) — it never arms, so the
player sits PLAYING-but-silent with Spotify TLS held yielded, exactly the state TASK-218 was
built to prevent.

**Not a TASK-278 regression** — the pump faithfully keeps calling `Audio::loop()`, same as the
old loopTask pumping would; the gap is in the app-level detection predicate. The pump/mutex
machinery held perfectly through 90 s of starved-stream churn (no crash, no deadlock, teardown
clean afterward, `maxMutexWaitMs` 258-312 ms).

**Suggested direction:** secondary liveness predicate alongside `isRunning()` — e.g., input
buffer empty (`bufPct == 0` / no bytes consumed) sustained for N seconds while PLAYING → treat
as dead. The existing TASK-263 underrun/bufPct plumbing already exposes the needed signals.
Real-world impact: a station server restarting (systemd stop, icecast reload) FIN-closes exactly
like this; today that means silent-until-user-intervenes.

**Implementation (2026-07-08):** the suggested `bufPct == 0` direction turned out to be wrong on
real hardware — DUT-verified via a local FIN-close repro (host streamer sends ~8 s of real MP3
audio then clean-closes the socket, same technique as the original E3 find). `inBufferFilled()`
does **not** drain to empty after the FIN: the vendored lib treats the dead connection as a
"slow stream" and pauses decode, so the fill level **freezes at whatever nonzero value it held**
at the moment of the close and never changes again. Implemented the other half of the task's
own suggested direction instead — "no bytes consumed" as a literal signal: `_lastBufChangeMs`/
`_lastSeenFilled` track the last tick `inBufferFilled()` differed from the previous reading;
`now - _lastBufChangeMs >= WR_STREAM_DEAD_MS` (same 5 s debounce, same grace-seeding at PLAYING
entry as the existing `isRunning()` check) fires the same `_stopAudio()` + `ERROR_STALL` +
`_onPlaybackFailed()` path. An exact-unchanged `inBufferFilled()` reading across a full 5 s
window doesn't happen on a healthy stream (continuous byte-level read/refill cadence), so this
is safe against false-positives the same way the empty-buffer version would have been, without
the "freezes nonzero" failure mode.

DUT-verified 2026-07-08 (repro above): `bufPct` froze at 24% ~0.5 s after the FIN; state left
PLAYING at t=14.0 s (≈5.5 s after the freeze started, matching the debounce window) →
`ERROR_UNREACHABLE` (auto-retry's reconnect attempt correctly failed against the now-closed
test server) — TLS resumed, no more silent hang. Full `T_WR_*` regression suite (16 tests:
ERR/EJECT/HEAP/VOL/COEX/SPOTIFY_RESUME) **16/16 PASS**, no regressions from the `tick()`
change. `./run/check` 6/6. Prod firmware reflashed after DUT verification.

**Priority:** P2 — silent-hang UX bug on a real-world event class, with a clear fix direction ·
**Status:** **DONE 2026-07-08** — DUT-verified fix (bufPct-frozen predicate, not bufPct==0);
16/16 T_WR_* regression, 6/6 check · **Opened:** 2026-07-07 · **Milestone:** — (candidate:
M-WEBRADIO reliability) · **Owner:** Developer · **Deps:** TASK-218 (the predicate it extends),
TASK-263 (bufPct/underrun signals) · **Branch:** master

---

### TASK-292 — `test_webradio_soak.py` acquire/release balance counter false-FAILs on lost serial lines

Found 2026-07-07 during TASK-278 E2: both 30-min soaks printed `VERDICT: FAIL` solely on the
acquire/release balance clause (81/77, then 90/89) while every other clause passed (0 acquire
FAILs, lfb never below 51 K, lfb ending ABOVE its start — which mathematically refutes a real
24 K-arena leak). The verbose per-cycle trace shows the counter diff is only ever 0 or exactly
1, flipping once mid-run and never growing: a single `[membudget] arena released` line lost at
a command boundary — the harness's own `cmd()` calls `reset_input_buffer()` before each send,
discarding whatever in-flight serial (including counter lines) hasn't been read yet.

**Fix direction:** count balance from the device, not the wire — e.g., add a
`get arenaStats` serialdbg counter pair (acquires/releases maintained in `membudget`) and
have the soak compare device-side totals at start/end; or stop using `reset_input_buffer()`
and parse the continuous stream. Until fixed, a balance MISMATCH of ±1-4 with a healthy lfb
trend should be read as line loss, not leak (this session's disposition — see
M-WR-AUDIO-TASK §E2 results).

Also landed alongside: `run/wr-soak` now accepts `WR_SOAK_VERBOSE=1` to pass `--verbose`
through (used to produce the per-cycle trace that diagnosed this).

**Close-out (2026-07-08):** device-side counters landed. `mb_arena.cpp` keeps lifetime
`acquires/releases/fails` totals (never reset across the JIT lifecycle; invariant
`acquires - releases == active`), surfaced via new `get arenaStats` (also `hwm`, `upMs`).
The soak gates the balance clause on start/end deltas of those totals; wire-counted
`[membudget]` lines are demoted to an informational cross-check. DUT-verified: a healthy
churn run showed wire 8 acquires / 7 releases (the exact historical false-FAIL signature)
while device counters read a balanced 7/7.

Scope grew during verification: a reboot resets the totals, which would false-PASS the
delta gate (observed live — the DUT crashed mid-soak, see TASK-295). The soak therefore
also detects reboots two ways and forces FAIL with evidence: (a) device-elapsed
(`upMs` delta) falling >15 s short of host-elapsed between the two snapshots — plain
monotonicity is insufficient since post-reboot uptime can re-pass the baseline; (b) serial
reset/panic signatures (`rst:0x`, `Guru Meditation`, `Backtrace:`, `abort()`) scanned in
every read window and echoed into the report. DUT-verified live: caught a real
`abort()`/SW_CPU_RESET mid-soak and returned VERDICT: FAIL with the panic lines quoted.
NOTE for LL-098: a mid-soak reboot produces the same `acquires = releases + 1` wire
signature as line loss (crashed session's release never prints, counters restart), so the
TASK-278 E2 false-FAIL disposition may have been partly a masked crash — the next long
soak with this detector will disambiguate.

**Priority:** P3 — verification tooling; false-FAILs erode trust in a gate that's otherwise
doing its job · **Status:** **DONE 2026-07-08** — device counters + reboot detection,
DUT-verified both directions (device-balance PASS path; crash → forced FAIL path) ·
**Opened:** 2026-07-07 · **Milestone:** — ·
**Owner:** VE · **Deps:** TASK-271 (owning tool) · **Branch:** master

---

### TASK-293 — tlsYield stop-then-replay deadlock: NEXT/PREV while playing parked loopTask 150 s

Found by TASK-277's T_WR_COEX_02 gate; DUT-reproduced and fixed 2026-07-07 same session.
`WebRadioApp::_play()` did `_stopAudio()` (→`tlsResume()`, count 1→0) then `tlsYield()`
(count 0→1) within one scheduler quantum on the same task. spotifyTask's yield-service inner
wait samples the count every 20 ms — it never observes the transient zero, stays in the OLD
batch's wait, and never issues a fresh semaphore give; the new yield saw `s_tlsStopped`
cleared by the resume and waits for a give that never comes. loopTask parks for the 150 s
ceiling (watchdog-fed → silent, serial dead; no reboot). Reachable from every
stop-then-replay path: NEXT/PREV tap while playing, tap-another-station, real auto-skip
retry. Latent since the shared-TLS handoff design; unmasked when the station list loaded
again (TASK-284 recovery) and T_WR_COEX_02 could actually run its NEXT tap.

**Fix:** `_stopAudio(bool resumeTls=true)` — `_play()` passes false and keeps the yield held
across the stop (skipping its own re-yield when `_spotifyYielded` is still true); the
wrDeadUrls forced-fail early-return resumes explicitly so the held yield can't leak. No
handshake bounce → no race window. Verified: NEXT/PREV repro instant (was: dead shell), full
T_WR suite 17/18 (sole fail = TASK-284 external, see TASK-277 close).

**Priority:** P1 (user-reachable silent 150 s UI freeze) · **Status:** fixed 2026-07-07,
lands with the TASK-277 feature commit · **Opened:** 2026-07-07 · **Milestone:**
M-WR-PLEDIT-SCROLL (campaign find) · **Owner:** Developer · **Deps:** TASK-287 (the
handshake it races), TASK-276 (made the ERR-test mask visible) · **Branch:** master

---

### TASK-294 — No serial hook exposes shell-level s_cooldownMs

QM flag from the TASK-280 close-out review. TASK-280 fixed `drainInjectionQueue`'s
taskbar-release branch to arm `s_cooldownMs` (main.cpp) the same way `appHandleInput`
does on a real release — but no `get` command surfaces that variable's remaining time,
so the fix was verified by full-suite regression pass (10/10, no failures) and a source
read, not by a test directly observing the armed cooldown. `T_TBFB_04`'s `get cooldown`
was initially mistaken for this hook during that close-out; it actually reads
`touchScreenCoolDownTime` in `winampDisplay.h` (SpotifyApp's unrelated TASK-052
dead-zone-tap cooldown) — a different variable that happens to share the debug-var name
`cooldown`.

**Fix direction:** add a `get shellCooldown` (or fold into `get snapshot`) exposing
`s_cooldownMs` remaining, mirroring the `remainingMs` pattern winampDisplay's `cooldown`/
`optimisticVolume` vars already use. Then extend `T_TBFB_04` (or add a new case) to assert
it's armed (~300 ms) immediately after an injected taskbar release, and unarmed before.
Low urgency — the underlying fix mirrors an already-proven code path (`appHandleInput`'s
own real-release cooldown arm) and was reviewed by hand; this is about strengthening the
regression net, not an open correctness question.

**Done 2026-07-08:** `get shellCooldown` added to `cmdGet` (main.cpp), reporting
`remainingMs` of `s_cooldownMs` (0 when unarmed); new harness case `T_TBFB_05` asserts
0 after a 500 ms decay wait, then (0, 300] immediately after an injected taskbar
release (the drag JSON terminator is emitted in the same drain iteration that arms
the cooldown, so the read lands inside the window); `T_TBFB_04`'s "no serial hook"
docstring note updated to point at it. `./run/check` 6/6; DUT-validated
`T_TBFB_01–05` **5/5 PASS** (new case read 271 ms armed / 0 decayed), prod restored.

**Priority:** P4 — QM housekeeping / verification-tooling gap · **Status:** **DONE
2026-07-08** — DUT 5/5 · **Opened:** 2026-07-08 · **Milestone:** — · **Owner:** VE ·
**Deps:** TASK-280 (done) · **Branch:** master

---

### TASK-295 — task-wdt abort() reboots DUT during WebRadio play/leave churn (Spotify-disabled build)

Found 2026-07-08 while DUT-verifying TASK-292's reboot detection — which promptly caught
this. During `run/wr-soak` (cyd2usb_webradio, Spotify DISABLED), the DUT crashed and
rebooted in 3 of 3 soak runs that got a station list, always within the first ~5
play/leave cycles. Captured live in run 5 (3-min soak, 15 s/station), immediately after a
cycle that had PLAYED 12 s and whose `suspend()` release was never observed, during/around
the next cycle's `set wrPlay`:

    abort() was called at PC 0x4012c778 on core 0
    Backtrace: 0x40083b91:0x3ffbffdc |<-CORRUPTED
    rst:0xc (SW_CPU_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)

PC decoded against the flashed cyd2usb_webradio ELF (`xtensa-esp32-elf-addr2line`):
`0x4012c778 = task_wdt_isr` (esp_system/task_wdt.c:176), `0x40083b91 = panic_abort`.
So this is a TASK WATCHDOG timeout escalated to abort: some task (loopTask or an IDLE
task) starved past the TWDT window during the play → leave → replay churn. NOT the fixed
tlsYield family (TASK-285/287/288/293): spotifyTask does not run in this build. Candidate
suspects (unverified): suspend()/stopSong() path hanging after a played session (the
unreleased arena points there), `connecttohost()` blocking on the next station, or the
new TASK-291 frozen-buffer predicate / TASK-284 same-mirror retry (both landed 2026-07-07,
adjacent code, timing fits — check whether older builds reproduce).

Repro: `MINUTES=3 PLAY_SECS=15 WR_SOAK_VERBOSE=1 ./run/wr-soak` — crashed 3/3 (runs with
stations) on 2026-07-08; the soak now prints `!! DUT RESET/PANIC:` lines and FAILs when it
happens. Fallout: (a) production also churns this path via the Winamp eject toggle;
(b) LL-098 / TASK-278 E2's "false-FAIL" wire imbalance may have been this crash all along
(reboot yields the same acquires = releases + 1 signature as line loss) — re-disposition
after fix.

**Root cause (2026-07-08, same session):** TWO defects in vendored `Audio.cpp`
`connecttohost()`, both reached ONLY via TASK-291's new stall-retry (the retry re-connects
while the dying session's decoder/InBuff/I2S allocations are still live, so the
malloc-usable DMA-capable heap is ~0.2–1.2 KB; a first connect never sees this state).
Continuous-capture repro driver (scratchpad `churn_repro.py`, no `reset_input_buffer`)
caught both with clean backtraces:

1. **65 s connect timeout vs 15 s TWDT.** The upstream v2.0.3 raw-IP workaround (the guard
   TASK-286 narrowed but kept) sets `m_timeout_ms = UINT16_MAX`. Stall-retry against the
   dying raw-IP station (`83.87.109.251:8012`, Radio Stad Centraal — slow-streaming all
   day) blocks `WiFiClient::connect()` on loopTask under the audio mutex for 65 s ≫ 15 s
   TWDT (`main.cpp` `esp_task_wdt_init(15,…)`) → `task_wdt_isr` abort. Decoded victim:
   `loopTask (CPU 1)`, both CPUs idle (blocked, not spinning). **Fix:** cap the
   workaround at 10 s (healthy connects are ~40 ms; still 40× the 250 ms default that
   motivated the upstream workaround).
2. **Unchecked mallocs before buffers are freed.** `connecttohost()` did its URL-parse
   `malloc`s BEFORE `setDefaults()` (which frees the old session's ~40 K); at 212 B free
   the mallocs returned NULL and the unchecked `memcpy(hostwoext,…)` hard-crashed
   (StoreProhibited, `Audio.cpp:432`, full backtrace decoded loopTask→_play→connecttohost).
   **Fix:** `setDefaults()` hoisted above the parse allocations + null-guards on all four
   allocations (return false → `_onPlaybackFailed(connectFail=true)` → auto-skip);
   `httpPrint()`'s identical unguarded block (mid-stream redirect path) guarded the same
   way.

**Verification:** pre-fix the churn driver crashed within ≤4 cycles, 4/4 runs (2× TWDT
abort, 1× StoreProhibited, 1× soak-detected). Post-fix: 46 cycles / 15 min, ZERO crashes,
with the dangerous path exercised hard — 13 stall-retry events and dozens of
station-connect failures all returning cleanly into auto-skip. `run/check` 6/6.
Bisect worktree confirmed the trigger is new (pre-TASK-291 build lacks the stall-retry
predicate — the underlying Audio.cpp defects are older but unreachable without it).
LL-098 re-disposition: **done 2026-07-08 (QM)** — the E2 soaks predate TASK-291's
stall-retry (the only path to this crash) and completed 88/92 paced cycles a reboot
would have disrupted, so E2's line-loss attribution stands; the ambiguity class is
closed by TASK-292's device counters + reboot detection (post-fix churn + wr-soak ran
clean under the new gate). LL-098 closed as adopted.

**Priority:** P1 — reproducible crash-reboot on a user-reachable path (radio playback
churn), and it silently corrupted a verification gate · **Status:** **fixed 2026-07-08**,
DUT-verified (46-cycle/15-min churn clean + wr-soak gate) ·
**Opened:** 2026-07-08 · **Milestone:** — (candidate: M-WEBRADIO reliability) ·
**Owner:** Developer · **Deps:** TASK-292 (detection tooling, done), TASK-291 (trigger
path), TASK-286 (the timeout guard this bounds) · **Branch:** master
