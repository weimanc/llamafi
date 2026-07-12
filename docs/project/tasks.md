# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> Completed/closed/fixed/resolved tasks are periodically moved to [tasks-archive.md](tasks-archive.md) to keep this file WIP-only. Last archive pass: 2026-07-12 (moved TASK-143..313 range, 149 entries — see archive file for the batch note).

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

### TASK-314 — WebRadioApp doesn't override hasError()/isConnecting(): player-slot taskbar indicator always reads idle-green in WebRadio mode

Found while wiring the WebRadio active-icon fix (taskbar.h now correctly
lights up the Spotify/player slot when `currentAppId == AppId::WebRadio`,
recoloured orange→red). That fix surfaces a pre-existing gap: `WebRadioApp`
(`app/src/webRadioApp.h`) never overrides the base `App::hasError()` /
`App::isConnecting()` (both default `false`), so `shell::activeError()` /
`shell::activeConnecting()` (main.cpp, TASK-245/ADR-046) always read false
for it. The active-slot indicator bar therefore shows green (idle) the
entire time WebRadio is connecting to a stream or in a sustained error
state — previously invisible only because no slot lit up at all in
WebRadio mode (that bug is now fixed), so this was never observable before.

Needs: `WebRadioApp::isConnecting()` true while establishing a station
connection (no audio yet); `WebRadioApp::hasError()` true on a sustained
stream/fetch failure, matching the sticky/self-clearing contract other
apps use (see StockApp / SpotifyApp's error-state fields for precedent).
Should reuse whatever state WebRadioApp already tracks internally for its
own on-screen connecting/error UI, if it tracks one — check
`app/src/webRadioApp.h` / `app/tools/preview_webradio_*.png` states
(stopped/connecting/playing/error) first rather than adding new state.

**Fix (2026-07-12):** `WebRadioApp::isConnecting()` → `_state == CONNECTING`;
`WebRadioApp::hasError()` → any of `ERROR_WIFI/ERROR_STALL/ERROR_UNREACHABLE/
ERROR_BLOCKED`. No new state added — reuses the existing `WRPlayState`
already tracked for on-screen connecting/error UI, per the sticky/self-
clearing contract `shell::activeError()`/`activeConnecting()` expect (same
pattern as `SpotifyApp`/`PlaneRadarApp`).

**DUT-verified 2026-07-12** (debug firmware, serial dbg surface —
`switchApp 11` into WebRadio, `set wrState N` + `get activeError`):
`wrState=1` (CONNECTING) → `connecting=true,active=false`; `wrState=4/5/6`
(ERROR_STALL/UNREACHABLE/BLOCKED) → `active=true,connecting=false` each;
`wrState=2` (PLAYING) and `wrState=0` (STOPPED) → both `false` (self-clears).
Production firmware (`cyd2usb_winamp`) reflashed and monitor restored after.

**Priority:** P3 — cosmetic/observability gap, not a functional regression
· **Status:** DONE · **Opened:** 2026-07-12 · **Closed:** 2026-07-12 ·
**Milestone:** none (post M-PLANERADAR taskbar-icon cleanup) · **Owner:**
Developer · **Deps:** none · **Branch:** master
