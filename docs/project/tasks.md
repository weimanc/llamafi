# Task Tracker

> Owner: Project Manager

Tasks ref feature IDs + git branches/commits for traceability. Agents report status changes to PM; keeps file current.

> Completed/closed/fixed/resolved tasks are periodically moved to [tasks-archive.md](tasks-archive.md) to keep this file WIP-only. Last archive pass: 2026-07-12 (moved TASK-143..313 range, 149 entries — see archive file for the batch note).

> **PM sync 2026-07-17 (overnight session — 6 slices landed, ZERO DUT time — handoff for daylight)** —
> Overnight agent session (`Claude Fable 5`) shipped six build-verified slices, each `run/check` 6/6
> (7/7 once the new gate landed): **WIRE2-G1/G2/G3** boot TZ + timeFmt + 12h/dateFmt (`a241b44`),
> **WIRE2-G5** BacklightFlow global owner (`49297a3`), **WIRE2-G4** weather coords from settings
> (`1abfb32`), **HOME** device home = `prLocs[0]` + dual-mirror writer (`dcc12bf`, registry-closed
> `9495774`), **WRSET** WebRadio settings UI + D3 resume-diff contract (`fff0208`, registry-closed
> `a0c729f`), **CPICK** shared country picker, both keyboard call sites retired (`13bb3fd`, registry
> self-updated in the same commit). One slice (WRSET) was orphaned mid-session by the Fable-5 usage
> limit right before its build gate; the work was complete and unmodified, so it was gated + review-
> contract-verified + committed post-hoc rather than re-run. Session close-out (`0935a18`, this
> session, Sonnet 5): finished the one dangling piece — `check_settings_wiring.py` (ADR-050 static
> gate: every `AppSettings` field needs load()+save()+a runtime consumer outside `settings/`), wired
> as `run/check` step `[7/7]` (warn-only), plus the city-name label on the TIME tile (M-HOME-LOCATION
> §6 visible confirmation) that made `city` wire clean, and a `NEW-APP-CHECKLIST.md` item documenting
> the gate for future settings fields.
>
> **None of tonight's six slices have touched a DUT.** Everything above is `run/check`-clean
> (build + static gates only) — no serial-dbg suite has run, no eyeball pass has happened. The city
> label in particular is a brand-new visible surface with zero eyeball verification (BP-048 posture).
> *(Resolved 2026-07-17, daylight session: city label eyeballed by human on DUT — correct city shown
> on the Weather TIME tile, not clipped, tile chrome intact, no weather-screen regression. T-CPICK-01
> eyeball half also PASSED same pass. DUT suites ran — see test_plan.md T-SETW/T-WRSET/T-HOME/T-CPICK.)*
>
> **VE/DUT queue for daylight** (all spec'd already — none written into `test_plan.md` yet):
> - **T-SETW-10** — boot applies `posixTz` via `configTzTime` (X031/WIRE2-G1, `cross_feature_matrix.yaml`).
> - **T-SETW-13** — weather fetch uses settings coords, snapshot-at-enqueue, resume()-diff refetch on
>   mismatch (X032/WIRE2-G4).
> - **T-SETW-14/15** — `BacklightFlow` global owner honours `dispAuto` at boot and in every app;
>   `DisplaySection` pause/applyManual/resume handshake doesn't fight the controller (X033/WIRE2-G5).
> - **T-WRSET-01..06** — WebRadio settings UI: result-identity discard (WR-1), edit-time
>   `lastStation` reset (WR-2), resume-diff + abort + refetch, coalesced suspend save, no-edit
>   round-trip must NOT refetch (X034). **Also still owed**: the WR-4 coordinate re-derivation
>   across settings suites, flagged at design time and not yet scheduled — do it alongside this suite.
> - **T-HOME-01..06** — home = `prLocs[0]`, writer×mirror matrix via `prSlotWritten()`, D4 migration,
>   >500 km divergence hint (X035). **T-HOME-05 must also disposition** the noted gap: the manual-
>   entry confirm path (TASK-322) shows no divergence hint — only the Lookup path does.
> - **T-CPICK-01..05** — spec'd in `M-COUNTRY-PICKER.md` §7: opens scrolled to current selection
>   (eyeball half per BP-048/CP-8), scrollbar drag+arrows page correctly at 249 entries, select
>   round-trips at both call sites (WebRadio Country + prloc Lookup, incl. both Retry paths),
>   back-tap cancels without mutating state, bake determinism (`gen_countries.py` re-run byte-
>   identical against `golden.sha256`).
>
> Next agent: write the above into `test_plan.md` as new suites, then run on DUT. `settings-widgets-001`,
> `settings-webradio`, and `home-location-001` all show `test_ids: []` in `feature_inventory.yaml` —
> fill those in as the suites land, per the existing per-feature notes.

> **VE/DUT queue — CLEARED 2026-07-17 (real-data DUT session, snapshot-guarded, human-authorized).**
> T-HOME-02/04/05 (the three real-data-risk deferrals) and T-CPICK-03's remaining prloc Lookup + both
> Retry legs all ran and PASS this session; the WR-4 coordinate re-derivation audit also ran (DONE —
> only `app-settings-wire-001.md` was stale; `m-clock-styles.md`/`m-pr-locations-dut.md` were already
> clean). **M-HOME-LOCATION and M-COUNTRY-PICKER suites are now both fully dispositioned** — see
> `test_plan.md` per-suite status lines. `feature_inventory.yaml`'s `test_ids` were already filled in
> for `home-location-001`/`settings-widgets-001` by the time of this session (the "still `[]`" note
> above was stale). Session followed the mandatory snapshot protocol throughout: `./run/spiffs pull`
> at session start, real `settings.json`/`cal.json` snapshotted aside with timestamps, one deliberate
> authorized Save (T-HOME-02) plus three synthetic-fixture reboots (T-HOME-04), byte-identical restore
> confirmed via sha256 at session end, production firmware reflashed. One pre-existing test-tool
> coordinate-drift bug (**TASK-330**, `run_serialdbg_tests.py`) was found already filed and
> Developer-owned — not touched this session, cross-referenced from the WR-4 entry so it isn't
> mistaken for a duplicate.

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

**DONE 2026-07-13 → EXP-013 (`docs/rnd/reports/EXP-013-audioI2S-version-ab.md`). CONFIRMED: version is
not a lever.** 3 valid trials/arm on the EXP-009 rig, same station (groovesalad-128), lib_deps-only swap:
Δ `usable`@CP2 ≈ +1.3 K mean for v2.0.6 — inside the ±2.4 K per-trial jitter both arms share; `maxAlloc`@CP2
**byte-identical (102,388) every trial**; CP1 delta (+530 B) = its −520 B static image. Keep the v2.3.0 pin.
The `SD_MMC.h` blocker did NOT reproduce — no shim needed (default chain LDF resolves bundled SD/FS libs;
rig doesn't set `AUDIO_NO_SD_FS` so both arms link the same stack). Production firmware restored + verified.

**Priority:** P3 — optional confirmation; not on any critical path · **Status:** **DONE 2026-07-13 —
CONFIRMED EXP-009 (keep v2.3.0); Lane C closed** · **Opened:** 2026-06-27 · **Closed:** 2026-07-13
· **Milestone:** M-WEBRADIO-NOPSRAM · **Rig:** `~/proj/webradio-bare/`
**Owner:** R&D · **Deps:** TASK-258 (done) · **Parent:** TASK-258 step 4 · **Record:** EXP-013

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

---

## Done — M-PR-LOCATIONS (+ M-CERT-ERRCODE slice) — filed 2026-07-14, closed 2026-07-16 (TASK-324 gate; roadmap entry closed same day)

> Source: `docs/architecture/designs/M-PR-LOCATIONS-location-presets.md` (r2) +
> 4-reviewer panel (`M-PR-LOCATIONS-{DEV,VE,QM,PM}-review.md`, unanimous
> PASS-with-actions; all blockers/majors folded into r2). Breakdown per PM
> review with two amendments: TASK-325 (kbText hook, VE blocker) added as an
> editor prerequisite; TASK-315 absorbs the QM-2 evidence requirements.
> DUT plan: group into 2–3 sessions (storage+fetcher / UI+strip / final gate),
> not per-task reflashes.

### TASK-315 — M-PR-LOCATIONS Phase-0: geocode probe script + report

Formalize the 2026-07-13 ad-hoc probes: repeatable script + committed report
(`M-PR-LOCATIONS/phase0-geocode-probe.md`) — query matrix (NL/UK/DE, full vs
truncated postcodes), URL-encoding, response contract + measured sizes (parse
buffer freeze, BP-001), HTTP/1.0 compat, UA acceptance, rate behaviour, and
the strict cert verify with committed output (QM-2/BP-039). Same task adds
`nominatim.openstreetmap.org` to `run/check-datatask-certs` ENDPOINTS
(VE-PRL-12). Manual/on-demand cadence only — never wired into run/test.
**Result:** `app/tools/geocode_probe.py` built + run once, 9/9 checks landed
on expected outcome (exit 0) — "full postcode" rule confirmed NL/UK/DE; max
response 459 B, ~1 KB parse buffer frozen (not shrunk, BP-001); cert chain
strict-verified against `OPEN_METEO_ROOT_CA`, `ISRG Root YR` cross-sign
evidenced; a real `http.client` Host-header bug was caught and fixed in the
probe itself. `run/check-datatask-certs` ENDPOINTS got the Nominatim row
gated by a new `PENDING_CERTS` guard (missing `NOMINATIM_ROOT_CA` alias
reports PENDING, not FAIL, until TASK-320 lands it). Report:
`docs/architecture/designs/M-PR-LOCATIONS/phase0-geocode-probe.md`.
**Status:** done · **Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** Developer · **Deps:** — · **Size:** S · **DUT:** n

### TASK-316 — M-PR-LOCATIONS Phase-0: preview tool — strip layout

Extend `app/tools/preview_planeradar.py`: slot label rows (~26px pitch, 4
slots), active-slot highlight variants, N^ marker removed, empty-slot and
single-slot degenerate cases. Human eyeball gate (BP-048) freezes layout +
highlight style before any planeRadarApp.h edit.
**Status:** DONE — eyeball gate PASSED 2026-07-14, human chose **variant
(a) inverse box**; layout frozen for TASK-323 (labels y68/94/120/146,
26 px pitch, box highlight). Gate detail kept below for the record.
Tool extended (N^ removed outright per
Q3; 4 slot-label rows at y68/94/120/146 px, `_location_slots()`, both
highlight variants wired, selectable via `radar.highlight` / `h` key in
interactive mode); 4 gate PNGs rendered against the busy_33km fixture at
10 km:
  - `docs/architecture/designs/M-PR-LOCATIONS/img/strip_4slots_highlight-box.png`
    — 4 filled slots, active = WORK, variant (a) inverse box (filled rect,
    field-coloured text)
  - `docs/architecture/designs/M-PR-LOCATIONS/img/strip_4slots_highlight-colour.png`
    — same scene, variant (b) bright/dimmed text + left-edge marker bar
  - `docs/architecture/designs/M-PR-LOCATIONS/img/strip_2slots.png` —
    empty-slot case (slots 3-4 undefined, nothing drawn), active = HOME,
    variant (a)
  - `docs/architecture/designs/M-PR-LOCATIONS/img/strip_1slot.png` —
    single-slot degenerate case, variant (a)
  Decision needed from human: **which highlight variant ships, (a) inverse
  box or (b) colour emphasis + marker bar** — freezes the style TASK-323
  transcribes into `planeRadarApp.h`. Layout note: band y55..185 easily
  fits 4 rows at 26 px pitch (rows span y68..146 incl. glyph height) with
  ~50 px of untouched clearance down to the AGE row — no pitch/AGE
  collision risk at this slot count.
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** Developer · **Deps:** — · **Size:** S · **DUT:** n

### TASK-317 — M-PR-LOCATIONS Phase-0: preview tool — slot-editor screen-flow frames

Static frames for the Settings location sub-view + ~8-state editor (slot
list, source fork, lookup chain, manual chain, confirm, delete): layout,
wording, tap-target sizes. Eyeball gate before appsSection.h geometry.

**Done (tool + frames) 2026-07-14 — awaiting eyeball gate.** New standalone
`app/tools/preview_prloc_editor.py` (does not touch `preview_planeradar.py`
or any existing tool). Geometry hardcoded from `settingsSection.h`
(`S_CONTENT_Y`/`S_ROW_H`/palette) and the button/spinner conventions in
`wifiSection.h` (Retry/Cancel layout, `_drawSpinner`) and `keyboardWidget.h`
(accent/neutral key colour language); text rendered with `dut_fonts.Font2`
(pixel-accurate TFT_eSPI Font16, the only font size Settings rows ever use).
Content uses the real phase-0 probe result (NL postcode 2513AA / The Hague,
`display_name` truncated to the firmware's 47-char `GeocodeResult.display[48]`
buffer) — see `docs/architecture/designs/M-PR-LOCATIONS/phase0-geocode-probe.md`.

Rendered to `docs/architecture/designs/M-PR-LOCATIONS/img/`:
- `editor_slotlist.png` — Locations sub-view, 4 slot rows (3 filled + 1
  `-- empty --`), green 3px active-bar marker on slot 0 (taskbar
  active-indicator visual language reused).
- `editor_source_fork.png` — non-empty-slot fork: stacked [Lookup] (accent
  green, default) / [Manual] (neutral grey) / [Delete] (red, destructive).
- `editor_source_fork_slot0.png` — same fork for slot 0: Delete rendered
  **disabled/greyed** (not absent) with a "slot 0 is always defined" caption
  — the disabled-vs-absent choice is one of the things to eyeball.
- `editor_lookup_pending.png` — Country/Postcode rows + spinner block
  (M-DATATASK-PROGRESS / `wifiSection.h` spinner pattern).
- `editor_lookup_confirm.png` — wrapped truncated `display_name`, Lat/Lon
  rows, 3-across Save/Retry/Cancel (81px × 40px each).
- `editor_lookup_error.png` — decoded error line `-96 GEOCODE_NO_MATCH —
  postcode not found` in the error-red palette colour, Retry/Cancel.
- `editor_manual_confirm.png` — entered Lat/Lon, range-validation hint text,
  Save/Cancel.
- `editor_frames_sheet.png` — one-page 3-col contact sheet, all 7 frames +
  captions (PIL default font — host review aid only, not on-device UI).

**What the human is deciding (before any `appsSection.h`/new-section C++ is
written):**
1. **Fork-screen button style** — vertical stacked 243×40 buttons vs a
   plain chevron-row list (current design borrows a "button" visual
   language not used elsewhere in Settings, which is otherwise all
   label/value/chevron rows — worth a second look for consistency).
2. **Delete-on-slot-0: disabled/greyed vs absent entirely** — only the
   disabled variant was rendered; if "absent" (row just not drawn) is
   preferred, that's a one-line change once decided.
3. **Confirm-screen button height (40px)** vs the rest of Settings' 30px
   (`wifiSection.h` Retry/Cancel) — deliberately sized larger here per the
   task's "finger-sized tap targets" ask for Save/Retry/Cancel; flagged as
   a departure from the existing convention, not silently matched to it.
4. **`display_name` wrap to 2 lines** vs single-line ellipsis truncation —
   2-line wrap was chosen to show more of the real OSM string; confirm this
   reads better than a harder truncation.
5. **Wording**: "Current" (source-fork context row), "Looking up...",
   "fetching from Nominatim", "slot 0 is always defined", the Range hint
   text — all first-draft, all cheap to change now vs after firmware lands.
6. Em dash (`—`) is not in Font2's ASCII-only glyph table — confirmed by
   this tool (rendered as `?` before the fix); the empty-slot string is
   ASCII `-- empty --`, a real constraint for any future wording pass too.

**Status:** DONE — eyeball gate PASSED 2026-07-14 ("looking good"),
frames approved as rendered: stacked-button fork screen, slot-0 Delete
*disabled* (not absent), 40 px confirm buttons, 2-line display_name wrap
all accepted. Follow-up: the stacked-button/confirm-bar idiom is to be
extracted into a shared widget kit (TASK-328) so TASK-321 builds on it
rather than hand-rolling — see TASK-328/327.
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** Developer · **Deps:** — · **Size:** S · **DUT:** n

### TASK-318 — M-CERT-ERRCODE minimal slice: -120 CERT_VERIFY_FAILED sentinel

Pulled forward from M-CERT-ERRCODE (PM review): `openHttps()` checks
`tls.lastError()` for -0x2700 on failed GET → returns -120; `httpErr()`
decode case; dataTask.h errorCode-convention comment (reserve -120..-129
TLS band). Hard prerequisite of TASK-320 so the Nominatim call site is born
with correct cert-failure surfacing. Rest of M-CERT-ERRCODE (build-hook
preflight, offline expiry check, --propose-fix, call-site audit, DUT test)
stays on the roadmap, off this milestone's critical path.
**Status:** DONE 2026-07-14 (`5cb6060`) — sentinel + httpErr decode +
dataTask.h band comment + dataTaskCerts.h pointer; run/check 6/6 PASS.
**Opened:** 2026-07-14 · **Milestone:** M-CERT-ERRCODE ·
**Owner:** Developer · **Deps:** — · **Size:** S · **DUT:** n (DUT assert
folded into TASK-324's gate)

### TASK-319 — M-PR-LOCATIONS: settings storage PrLocation[4] + migration + prloc serialdbg

`PrLocation prLocs[4]` + `prActiveLoc` in AppSettings (64 B), prLat/prLon
kept as write-through mirror of the active slot; load-time migration seeds
slot 0 ("HOME") from prLat/prLon when prLocs absent. Bundled serialdbg (PM
call #3 — hooks land with the state they inspect): `get prloc`,
`set prloc <i> <label> <lat> <lon>`, `set prloc active <i>` (the latter
calls the shared `_setActiveLoc()` once TASK-323 lands; until then settings
side only).
**Status:** **DONE — closed 2026-07-16 with the TASK-324 gate (migration/persistence legs T_PRL_04/07).** Code landed, run/check 6/6; **intermediate DUT smoke PASS 2026-07-14** (migration seeded HOME from stored coords; slot set/get/active round-trip; reboot persistence; bad-index + long-label rejected) — `PrLocation prLocs[4]`/`prActiveLoc` added to
`AppSettings`, load/save + DEV-PRL-6 migration-order-safe seeding wired in
`settingsStorage.cpp`, `get prloc` / `set prloc <i> <label> <lat> <lon>` /
`set prloc active <i>` (settings-side only, TODO(TASK-323) marks the
`_setActiveLoc()` hook point) added to `main.cpp`'s `cmdGet`/`cmdSet`.
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** Developer · **Deps:** — · **Size:** S/M · **DUT:** y

### TASK-320 — M-PR-LOCATIONS: dataTask geocode fetcher + stub injection

Pending-config-mux pattern (NOT stock Request.symbol — 7 chars can't hold
"SW1A 1AA"); GeocodeResult with seq identity (TASK-300 lesson); minimal
percent-encoder (none exists in firmware); NOMINATIM_ROOT_CA alias +
cross-sign comment; UA header; -96 GEOCODE_NO_MATCH; parse buffer sized
from TASK-315 measurements. Bundled serialdbg: `set geocode <lat> <lon>` /
`set geocode err <code>` with structural isolation (parked slot checked
before real result; enqueue no-op while parked — TASK-276 lesson).
**Status:** **DONE — closed 2026-07-16 with the TASK-324 gate (live leg T_PRL_01b, failure paths T_PRL_03).** Code landed 2026-07-14, run/check 6/6; **intermediate DUT smoke PASS 2026-07-14** (live Nominatim 2513AA→52.0795,4.3132 seq-matched; stub parked -96; enqueue no-op while parked). Landed: DATA_FETCH_GEOCODE + fetchGeocode()
(openHttps + NOMINATIM_ROOT_CA alias w/ cross-sign comment, mandatory UA,
geoUrlEncode, 1 KB doc per probe measurement, -96 no-match + new -97
parse-failed in httpErr); enqueueGeocode returns seq (pending-config-mux);
pollGeocode (parked injected result wins, consume-once);
debugInjectGeocode + dbgGeocodeState peek; serialdbg `set geocode <lat>
<lon> [display]` / `set geocode err <code>` / `get geocode`
(non-consuming). check-datatask-certs nominatim row graduated
PENDING→PASS on live strict verify; PENDING_CERTS dict emptied, kept for
the next pin.
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** Developer · **Deps:** TASK-315 (done), TASK-318 (done) ·
**Size:** M · **DUT:** y

### TASK-321 — M-PR-LOCATIONS: Settings Locations sub-view + slot editor (Lookup path)

Locations row replaces the grey lat/lon row; sub-view + explicit ~8-state
editor enum (DEV-4 — own state machine, not boolean flags; Stock's 3-state
StockEditPhase is the nearest precedent at 1/3 the size). Lookup path only:
label → country → postcode → pending spinner → confirm (display_name +
coords) with Save/Retry/Cancel; delete with slot-0 refusal; late/stale seq
results ignored (VE-PRL-5). Editor testable end-to-end via TASK-325 +
TASK-320 stubs. Error states must include -97 GEOCODE_PARSE_FAILED via the
generic decoded-error path — the TASK-317 frames only eyeballed -96 (QM
check-in 2026-07-14). Kit-fidelity check at acceptance: buttons must match
the TASK-317 gate-approved PNGs (stacked, 40 px, delete disabled-not-absent
on slot 0), checked against the PNGs, not re-derived from prose.
**Status: DONE — closed 2026-07-16 with the TASK-324 gate (T_PRL_01a cited from this smoke). Code landed, run/check 6/6; intermediate DUT smoke PASS 2026-07-15**
(`app/tools/prloc_editor_smoke.py`, 14/14 — drives the real state machine via
`tap`/`kbText`/`kbOk` touch+keyboard injection, not a synthetic harness:
SlotList render+tap into an empty slot; EditLabel keyboard prefill/maxLen/
mode; SourceFork hasCurrent-gated "Current" row; Lookup→Country→Postcode→
LookupPending→`_tickPrLookup()`→LookupConfirm round trip via the
`set geocode <lat> <lon> [display]` stub — isolation confirmed, no live
Nominatim call; Save persists label+coords into the target slot and
write-through-mirrors only when the edited slot is active; slot-0 Delete
confirmed inert — disabled, not absent (`get prloc` unchanged after the
tap); non-active non-zero slot Delete confirmed working and confirmed NOT
touching `prActiveLoc`; `-97 GEOCODE_PARSE_FAILED` stub → LookupError →
Cancel confirmed to leave the target slot untouched (generic decoded-error
path, no special-casing). Full T_PRL_01..11 VE matrix (network leg,
migration, epoch/seq edge cases, tlsYield coexistence) is still TASK-324's
job — this smoke is state-machine/UI-flow coverage only, not a substitute.
Explicit `PrLocView` 8-state enum (SlotList/EditLabel/
SourceFork/LookupCountry/LookupPostcode/LookupPending/LookupConfirm/
LookupError) added to `AppsSection` (`app/src/settings/appsSection.h`).
Lookup path only — the SourceFork [Manual] button is wired but rendered
`SBtnStyle::Disabled` with a `// TASK-322` comment (disabled-renders-but-
never-hits is the kit's semantic, so it's inert until that task lands).
Entry: the PlaneRadar row-view's old greyed-out lat/lon row is now a
"Locations  <active label>  >" chevron row (same idiom as TimeSection's
City row) — tap opens SlotList. Kit-fidelity self-check against the
TASK-317 gate-approved PNGs, screen by screen:
- SlotList → `editor_slotlist.png`: match (4 rows, `-- empty --` for empty
  slots, 3px green active bar, "Tap a slot to edit" hint).
- SourceFork / slot-0 SourceFork → `editor_source_fork.png` /
  `editor_source_fork_slot0.png`: match (stacked Lookup/Manual/Delete via
  `sStackedBtnRect`, slot-0 Delete Disabled + caption, non-empty-slot
  "Current" row).
- LookupPending → `editor_lookup_pending.png`: match on Country/Postcode
  rows + `SSpinner` + "fetching from Nominatim" caption; **one deliberate
  addition beyond the frozen PNG**: a `[Cancel]` button (`sButtonBar` n=1),
  since the PNG predates the VE-PRL-5/T_PRL_08 cancel-mid-lookup finding
  that requires one — noted in-code at the call site.
- LookupConfirm → `editor_lookup_confirm.png`: match (2-line wrapped
  `display_name`, Lat/Lon rows, 3-across Save/Retry/Cancel via
  `sButtonBar`).
- LookupError → `editor_lookup_error.png`: match (2-across Retry/Cancel);
  the error line renders via `httpErr(errorCode)` + a generic second line
  ("postcode not found" for -96, else "lookup failed - check network") —
  **-97 GEOCODE_PARSE_FAILED routes through this same generic path with no
  special-casing**, confirming the QM check-in note.
Seq identity (design "Geocode fetch"): the seq returned by
`enqueueGeocode()` is stored in `_prGeoSeq`; `_tickPrLookup()`'s
`pollGeocode()` result is consumed either way but only acted on when
`r.seq == _prGeoSeq`, otherwise silently discarded. Cancel-mid-lookup
(`_prAbandonLookup()`) returns to SourceFork without clearing `_prGeoSeq`;
a late delivery for that seq is still consumed by poll but the UI has
already moved on, and any subsequent lookup gets a fresh seq from a new
`enqueueGeocode()` call, so it can never be mistaken for current
(VE-PRL-5/T_PRL_08). Geometry: no S_MAX_ROWS tension — SlotList is 4 rows
(well under the 8-row cap) and the stacked/bar screens use their own
`sStackedBtnRect`/`sButtonBar` geometry, not the row grid. One toolchain
finding (not a kit gap): this build compiles `-std=gnu++11`, under which a
class with default member initializers (SButton, SSpinner) is not an
aggregate, so `SButton{a,b,c}` / `x = {a,b,c}` brace-init doesn't resolve
— worked around with individual field assignment
(`btn.r=...; btn.label=...; btn.style=...;`) at every call site; flagging
in case TASK-327's migration pass hits the same wall. No kit API gaps
found — `settingsWidgets.h` was not modified. `run/check` 6/6 PASS.
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** Developer · **Deps:** TASK-316 (done), TASK-317 (done),
TASK-319, TASK-320, TASK-325, TASK-328 (widget kit — build the editor ON
it, don't hand-roll buttons) · **Size:** M · **DUT:** y

### TASK-322 — M-PR-LOCATIONS: manual lat/lon entry path

Second editor source path (Q4): lat → lon numeric entry, −90..90/−180..180
validation, same confirm screen. Isolates the "does KeyboardWidget need a
numeric layout or does Full mode suffice" question (DEV minor: Full mode's
decimal-point friction) — descope a new keyboard layout unless TASK-317
prototyping proves it necessary.
**Status: DONE — closed 2026-07-16 with the TASK-324 gate (T_PRL_06 cited from this smoke). Code landed, run/check 6/6; intermediate DUT smoke PASS 2026-07-16**
(`app/tools/prloc_manual_smoke.py`, 13/13). Three new `PrLocView` states —
`ManualLat`, `ManualLon`, `ManualConfirm` — added alongside the TASK-321
Lookup* states; both source paths now funnel through the same
`_prGeoLat`/`_prGeoLon` fields and the (renamed) shared `_prSaveCoords()`
persist primitive, so Save/Cancel and the write-through-mirror-on-active-
slot rule are one implementation, not two. SourceFork's `[Manual]` button is
now `SBtnStyle::Neutral` (was `Disabled` as the TASK-321 stub). No numeric
keyboard layout added — descoped per this task's own instruction, since
TASK-317's prototyping never showed `KeyboardWidget::Mode::Full` to be
insufficient; digits/`-`/`.` are all reachable via Full's existing 123/
symbol pages. Range validation (`_prParseCoord()`, `strtod`-based, rejects
unparseable input too — a bare `-` doesn't silently become `0.0`) re-shows
the *same* field's keyboard with an inline range hint in the prompt on a
bad value rather than a separate error screen (no such frame exists in the
TASK-317 gate set for this path) — confirmed on-device that 999° lat and
-200° lon are both rejected and re-prompt cleanly, not just at the type
level. Manual entry omits the Lookup confirm screen's "Retry" button (2-
across Save/Cancel, not 3-across) — nothing to retry against for a value
the user typed themselves; re-opening `[Manual]` from SourceFork covers
that case. DUT smoke covers: empty-slot Manual entry end to end (invalid
lat → reject → valid lat → invalid lon → reject → valid lon → Save →
persisted); re-entry into an already-filled slot correctly prefills from
its current coords; Cancel at ManualConfirm leaves the slot untouched.
Full T_PRL_06 (out-of-range boundary values, projection) matrix stays
TASK-324's job.
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** Developer · **Deps:** TASK-321 (done) · **Size:** S · **DUT:** y

### TASK-323 — M-PR-LOCATIONS: radar strip switcher

Remove N^ (Q3); render slot labels + active highlight per TASK-316 frozen
layout; strip tap hit-test → shared `_setActiveLoc()` (single primitive,
two call sites — QM-1/BP-047): guard, write-through+save, reset
`_result/_everHadResult/_lastGoodMs/_prErr` (DEV-3), epoch bump,
`_repaintDisc()` (runways included — no separate `_drawRunways()`),
re-enqueue. `enqueuePlaneRadar`/`PlaneRadarResult` gain the epoch byte;
poll discards old-epoch results (VE-PRL-6, TASK-308/309 lineage).
**Status:** **DONE — closed 2026-07-16 with the TASK-324 gate (T_PRL_02/05/09).** Code landed 2026-07-14, run/check 6/6 PASS. `planeRadarApp.h`:
N^ marker removed; `_drawLocSlots()` renders the 4 label rows (font 1,
box-variant highlight, frozen y68/94/120/146) from `_drawGridOnce()` and
after every switch; public `_setActiveLoc(uint8_t slot)` is the single
primitive (guard → mirror+save → result/staleness reset → epoch bump →
`_repaintDisc()`+`_drawLocSlots()`+`_updateStripDynamic()` → re-enqueue),
called from `handleInput()`'s strip hit-test (named `PR_STRIP_ROW_LOC0..3_Y`
+ `PR_STRIP_ROW_LOC_Y[]` array, `PR_STRIP_LOC_HIT_HALF=13` half-pitch zones,
tiling y55..159 with no gaps) and from `main.cpp`'s `set prloc active <i>`
(TODO removed) — guarded there on `currentAppId == AppId::PlaneRadar`
before calling `_setActiveLoc()` (else settings-side mirror+save only,
same shape as the existing `clockStyle` cross-app guard; PlaneRadar's own
`resume()` picks up the new location on next entry). Epoch: `uint8_t
epoch` added to `PlaneRadarResult` and to `enqueuePlaneRadar()`'s signature
(defaulted `= 0`, so the one pre-existing call site needed no changes
beyond passing `_locEpoch`); `dataTaskStorage.cpp` snapshots it into
`s_pendingPrEpoch` alongside lat/lon/distNm and echoes it into the result
after the TASK-313 retry-or-not settles; `tick()`'s poll compares
`result.epoch != _locEpoch` and discards with a `LOG_D "stale epoch"` line
(leaves `_pendingFetch` alone — it now tracks the newer-epoch fetch
`_setActiveLoc()` already enqueued). DUT asserts (T_PRL_02/05/09) deferred
to grouped TASK-324 session.
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** Developer · **Deps:** TASK-316, TASK-319 · **Size:** M · **DUT:** y

### TASK-324 — M-PR-LOCATIONS: VE suite T_PRL_01a..11 + DUT gate

Full suite per design r2 verification sketch: 01a stubbed editor round-trip
(gate) / 01b live [NETWORK] smoke incl. space-postcode encoding / 02 switch
/ 03 failure paths / 04 migration / 05 no-op+delete-fallback / 06 manual
range validation / 07 persistence layers (reflash vs flash-fs wipe) / 08
late-result-after-cancel / 09 old-epoch discard / 10 slot-0 delete refusal
/ 11 geocode-during-Spotify tlsYield coexistence. Deferred-item ledger
(QM check-in 2026-07-14, LL-102 guard — each individually-deferred DUT
assert must be exercised BY NAME, not absorbed): TASK-318 -120 assert (via
`set certbreak` if the M-CERT-ERRCODE remainder has landed, else explicitly
re-deferred to that milestone with a note); TASK-319 migration + prloc
serialdbg on-device; TASK-320 live geocode + stub isolation on-device;
TASK-325 kbText/kbOk/kbCancel on-device (and unparks stock T232/233/246/247
— run or explicitly hand back to their own suite). Regression entry in
`docs/verification/regression_suite/`.
**Status: closed 2026-07-16** — T_PRL_01a/02/03/04/05/06/07/09/10 **PASS**;
T_PRL_01b **PASS (cited)** minus the space-postcode-encoding leg specifically;
T_PRL_08 **PASS for the DUT-provable half**, seq-mismatch half code-verified
only (the debug injection hook can't manufacture a genuinely stale seq —
see design note); T_PRL_11 **BLOCKED** (TASK-243 external, Spotify Premium
lapsed). T_PRL_07's destructive `flash-fs`-wipe leg was run in a follow-up
session with explicit human go-ahead, wrapped in a raw byte-exact
`esptool.py read_flash`/`write_flash` backup-restore around it (independent
of `run/spiffs`, which only round-trips through git-tracked `app/data/` —
using that would have meant overwriting tracked template files with live
device secrets to stage a restore, so a raw partition image was used
instead): pre-wipe SPIFFS captured → `run/flash-fs` → confirmed the
documented wipe+migration (`slot0="HOME"` reseeded from the stale
`app/data/settings.json` template's compile-time lat/lon, slots 1-3 empty —
incidentally re-exercising T_PRL_04's migration path live) → backup image
written back → post-restore raw read verified **byte-identical** (`cmp`) to
the pre-wipe backup → production firmware reflashed. Full
write-up: `docs/verification/regression_suite/m-pr-locations-dut.md`;
`test_plan.md` got the T_PRL_01a..11 suite entries. New this session:
`app/tools/prloc_ve_smoke.py` (22/22 PASS) covering T_PRL_02/03/05/08/09 —
device state (all 4 in-use location slots + active index) captured and
restored exactly at the end, not left dirtied. T_PRL_01a/04/06/10 cited from
TASK-319/320/321/322's own close-out smokes rather than re-run (LL-102
guard — cited by name, not absorbed). Deferred-item ledger disposition:
TASK-318's -120 `CERT_VERIFY_FAILED` assert — no `set certbreak` hook exists
(M-CERT-ERRCODE remainder hasn't landed) — **explicitly re-deferred to that
milestone**, per this task's own ledger instruction; TASK-319/320 on-device
legs — covered (T_PRL_04/01b above); TASK-325 kbText/kbOk/kbCancel — proven
at its own close-out and exercised continuously across every T_PRL_* leg in
this session; the parked stock-ticker tests (T232/233/246/247) are **handed
back to their own suite** — out of scope for this task, unrelated feature.
Notable finding (documented in the regression-suite doc, worth carrying into
future VE work on this app): `g_shellBusy` silently drops a second
interactive `tap` while a fetch is pending — correct product behaviour, but
it means an epoch-race test needs the `set prloc active <i>` serial path,
not back-to-back tap injection.
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS ·
**Owner:** VE · **Deps:** TASK-320 (done), TASK-321 (done), TASK-322 (done),
TASK-323 (done), TASK-325 (done) · **Size:** M · **DUT:** y

### TASK-325 — M-SERIALDBG: KeyboardWidget serial injection (set kbText / kbOk / kbCancel)

VE-PRL-1 blocker: no serial path exists to drive KeyboardWidget text entry;
the stock-ticker editor tests (T232/233/246/247) have been non-executable
for this exact reason since they were planned. Inject into the active
keyboard's buffer + commit/cancel, following handleSerialCommands
conventions (mind the drain-all-bytes-at-once lesson, T157-159). Unblocks
TASK-321/322/324 here AND the parked stock editor tests.

Landed: `set kbText <text>` (verbatim rest-of-line after "kbText ", may
contain spaces — UK postcodes; mode-filtered through the widget's own
`injectChar`/`appendChar` path, e.g. UpperAlpha uppercases + drops digits/
symbols exactly as the on-screen key tables would), `set kbOk` (fires the
same `submit()` commit path/callback as tapping OK; no-op when buffer empty,
same as the on-screen disabled state), `set kbCancel` (same `cancel()`
path/callback as the on-screen cancel zone), and `get kb` → `{"active",
"len","maxLen","mode"}`. All four error `{"ok":false,...}` when no keyboard
is active. New KeyboardWidget public methods are additive only
(`injectChar`, `injectText`, `commitFromHost`, `cancelFromHost`,
`len`/`maxLen`/`mode` accessors) — no touch-path behaviour change.
`docs/verification/test_plan.md` got one added note line above T232 pointing
at the new command syntax (T232/233/246/247 are live test_plan.md entries,
not an archived tasks list, so the "leave archive alone" fallback didn't
apply — no separate archived task entry for these tests was found).
`./run/check` 6/6 PASS. DUT execution of T232/233/246/247 and the VE-PRL-1
assert deferred to the grouped TASK-324 session.
**Status:** **DONE — closed 2026-07-16 with the TASK-324 gate** (kbText/kbOk/kbCancel exercised across every T_PRL_* editor leg; stock T232/233/246/247 handed back to their own suite per the ledger). Code landed, run/check 6/6; **intermediate DUT smoke PASS 2026-07-14** (kbShow helper added; UpperAlpha filter+maxLen, Full-mode verbatim, submit/cancel callbacks fire, inactive after cancel) · **Opened:** 2026-07-14 · **Milestone:** M-SERIALDBG /
M-PR-LOCATIONS · **Owner:** Developer · **Deps:** — · **Size:** S · **DUT:** y

---

## Done — M-MEMPLAN hygiene — filed 2026-07-14 (QM audit: manifest coverage gap, LL-111), closed 2026-07-18

### TASK-326 — M-MEMPLAN: backfill unregistered heap parse docs (weather, webradio stations) into mem_manifest

Found during the LL-111 audit (PlaneRadar's 4 KB parse doc shipped
unregistered; fixed same session — `planeradar_doc` placed in the
ANY/foreground overlay, region 2560→4096). Sweep of `dataTaskStorage.cpp`
shows two remaining heap docs outside the manifest:

- `fetchWeather()` `DynamicJsonDocument(1024)` — pure scratch, result copied
  to `WeatherResult`; same shape as `crypto_doc`, likely a straight
  conversion to the overlay region (fits inside the 4096 region, no growth).
- `fetchWebRadioStations()` `DynamicJsonDocument(WR_DOC_CAP=5120)` — NOT a
  straight conversion: allocated deliberately after `tlsYield()` and live
  across the mirror TLS handshakes; and as a WebRadio buffer in group
  `foreground` it would SUM with the decoder/inbuf runtime budget
  (M-MEMPLAN §2 coexist rule) unless modelled `sequential`. Needs Architect
  call: placed vs `placement: runtime` budget-only entry.

**Architect ruling 2026-07-16:**
- `weather_doc` (1024) → **placed**: `{ app: Weather, caps: ANY, group:
  foreground, kind: scratch }` — identical exclusivity argument to
  crypto_doc/heatmap_doc (dataTask serial, pure scratch, result copied out);
  fits the existing 4096 overlay region, no growth.
- `webradio_stations_doc` (5120) → **`placement: runtime`** budget-only,
  joining webradio_decoder/inbuf. It is runtime-JIT inside
  fetchWebRadioStations() and deliberately live across the mirror TLS
  handshakes — the same "one member is heap-resident TLS" reason the design
  doc gives for why the fetch-vs-decoder overlay cannot be made static.
  Summing does overstate the WebRadio foreground budget by 5120 B (TASK-289
  made fetch and playback mutually exclusive, so doc and decoder never
  coexist) — accept that as documented conservatism via a manifest comment.
  Do NOT build `sequential` modelling for this: the planner has no such
  mechanism today (design-doc concept only), and 5 KB of modelled slack does
  not justify new planner machinery. Revisit only if the INTERNAL ceiling
  ever binds. NOTE (M-SETTINGS-WIRE2 G4): weather_doc's app tag stays
  Weather and its size is unaffected by the coords change — same endpoint,
  same response shape.

Stack-based `StaticJsonDocument`s (stock 2×2048, teletext 1536, filters) are
dataTask *stack* budget (TASK-240), out of manifest scope — document that
boundary in the manifest header comment while here.
**Status:** **DONE 2026-07-18.** Landed in two halves: the weather half +
manifest scope-note header (stack-vs-heap boundary) went in earlier with
WIRE2-G4 (`1abfb32` — `weather_doc` placed entry, fetchWeather() converted
to `StaticRegionAllocator{MEM_weather_doc}`, fits the 4096 ANY/foreground
region with no growth, per the Architect ruling). This session added the
remaining piece: `webradio_stations_doc` (5120 B) as a `placement: runtime`
budget-only entry joining webradio_decoder/inbuf, with the documented-
conservatism comment (sums +5120 B into the WebRadio foreground budget even
though TASK-289 made fetch and playback mutually exclusive — accepted, no
`sequential` planner machinery for 5 KB of slack) and a pointer comment at
the `WR_DOC_CAP` definition in `dataTaskStorage.cpp`. Runtime entries emit
no placed region, so `mem_layout.h`/`.py` are byte-identical (verified by
regen) and `golden.sha256` is untouched; WCMU budget check passes
(INTERNAL runtime now 34 736 B + 60 000 B headroom ≪ 290 000 B ceiling).
`run/check` 6/6 PASS. All five heap parse docs in `dataTaskStorage.cpp`
are now manifest-registered — the LL-111 coverage gap is closed.
· **Opened:** 2026-07-14 · **Closed:** 2026-07-18 · **Milestone:** M-MEMPLAN ·
**Owner:** Developer (Architect consult on the webradio entry) · **Deps:** —
· **Size:** S · **DUT:** n (`run/check` gate [6/6] covers)

### TASK-328 — Settings widget kit: shared button/spinner/confirm primitives

Human direction 2026-07-14 (at the TASK-317 gate): enforce a common
Settings UI style. Today `settingsSection.h` enforces the ROW style by
construction (geometry, palette, header, drawRow, hitbox) but buttons are
hand-rolled 4x over — wifiSection Retry/Cancel (30 px, own constants),
ledSection OFF/ON/SAVE (own bar + 100 ms invert feedback), timeSection
up/down arrows, calibrationFlow's buttons — each with private layout +
hit-test + feedback. The TASK-317 frames' 40-vs-30 px divergence is the
symptom: no constant to obey.

Extract `app/src/settings/settingsWidgets.h`: `SButton` (rect, label,
style enum primary/neutral/danger/disabled; draw + hitTest + shared press
feedback), a 1–3-across button-bar layout helper at a standard bar Y, a
spinner/progress row (M-DATATASK-PROGRESS idiom), and the standard
S_BTN_H (decide 30 vs 40 once — the approved TASK-317 frames use 40 for
finger targets; lean 40 and let the migration pass resize the old ones).
API proven by the first consumer (TASK-321 location editor). Preview-tool
note: `preview_prloc_editor.py` mirrors geometry by hand — keep its
constants in one obvious block referencing this header until a shared
constants export exists.
**Status:** **DONE — closed 2026-07-16**: API + visual contract proven by TASK-321 (first consumer, kit-fidelity check vs the gate PNGs) and the TASK-327 migration (all four legacy sites). Code landed 2026-07-14 (settings/settingsWidgets.h: SButton
w/ Primary/Neutral/Danger/Disabled + shared 100ms flash, sButtonBar 1-3
across @S_BTN_BAR_Y, sStackedBtnRect, SSpinner; S_BTN_H=40 per TASK-317
gate; visual contract comment points at the frozen gate PNGs, QM note 10).
Compile-proven via appsSection.h include, run/check 6/6. API proof +
visual check ride TASK-321 (first consumer).
**Opened:** 2026-07-14 · **Milestone:** M-PR-LOCATIONS
/ M-SETTINGS-STYLE · **Owner:** Developer · **Deps:** — (before or with
TASK-321) · **Size:** S/M · **DUT:** n (visual check rides TASK-321's)

### TASK-327 — Settings style enforcement pass: migrate sections onto the widget kit

Second half of the human direction: once TASK-328's kit is proven by the
location editor, migrate the existing hand-rolled button sites onto it —
wifiSection (Retry/Cancel), ledSection (OFF/ON/SAVE + invert feedback
becomes the kit's shared feedback), timeSection (arrows), calibrationFlow
— deleting per-section button constants and hit-test code. Pure reuse/
style pass: zero behaviour change intended; run/check + targeted
touch-path tests gate it (mind the settings-nav coordinate-drift lesson —
if any button moves to the standard bar Y, audit tests/docs that encode
old coordinates). Candidate BP if it holds: "new Settings UI = kit
widgets only; hand-rolled buttons are a review flag" (QM to propose).
Registry (Architect review 2026-07-16): kit reserved as
`settings-widgets-001` in feature_inventory.yaml — close-out updates listed
in its notes (move migrated files into that entry, update settings-001 /
settings-wifi, coordinate-drift test audit). No new matrix entry — kit↔section
coupling is intra-settings build-time idiom, not a runtime interaction.
**Status:** DONE 2026-07-16.** All four sites migrated, per-site geometry
constants + hand-rolled hit-tests deleted:
- wifiSection Result Retry/Cancel → `sButtonBar` n=2 on the standard bar
  (Retry=Primary/Cancel=Neutral, the kit's error-screen idiom; was a 30px
  pair at y=178). Moved to bar Y → coordinate audit done, see below.
- ledSection picker OFF/ON/SAVE → `sButtonBar` n=3 at y=32 (active state
  = Primary, same palette as before); the private 100ms SAVE invert is now
  the kit's shared `flash()`. S_BTN_H=40 pushed the SV square from y=61 to
  y=78 (height 168→151; the hardcoded 167 scale divisors were
  parameterised to kPickH-1/kSvW-1 as part of this).
- calibrationFlow Review Accept/Retry/Cancel → `sButtonBar` n=3 on the
  standard bar; Accept renders `Disabled` while `_sanityFailed` (the kit's
  disabled-never-hits semantic replaced the manual guard). CAL_BTN_*
  deleted; CAL_BG_COLOR == S_BG so Disabled's fill matches.
- timeSection city-picker scroll arrows → `SButton` draw/hit at the
  scrollbar's own 18x20 rects (S_BTN_H is a bar-button contract; doesn't
  apply inside a scrollbar column). Deliberately no `flash()` — a 100ms
  block per step would make repeated scrolling sluggish; noted in-code.
Coordinate-drift audit (801f378 lesson): no serialdbg test taps any moved
button (T-SET-* touch only category rows + the back zone — verified by
inspection); manual regression docs reference buttons by name, not
coordinates; design docs (wifi-settings.md, led-settings.md,
touch-calibration.md, time-settings.md) got supersession notes. Gates:
`run/check` 6/6 PASS; DUT T-SET-01/02/03/06/07/08 6/6 PASS post-migration;
new `app/tools/settings_kit_smoke.py` 14/14 PASS on DUT (drives LED picker
OFF/ON/SAVE incl. kit flash, and city-picker arrows, via tap injection;
side effect: parks ledMode=Off). wifiSection Result and calibrationFlow
Review buttons are NOT serial-reachable (need a failed connect / raw
XPT2046 taps) — they remain on the manual eyeball checklist (BP-048), same
pattern as TASK-328's visual check riding TASK-321. BP candidate now ready
for QM: "new Settings UI = kit widgets only; hand-rolled buttons are a
review flag".
**Opened:** 2026-07-14 · **Milestone:** M-SETTINGS-STYLE
· **Owner:** Developer · **Deps:** TASK-328, TASK-321 (kit proven) ·
**Size:** M · **DUT:** y (touch regression on migrated sections)

### TASK-329 — `settingsStorage.{h,cpp}` JSON capacity silently truncates on save (real data loss found on DUT)

Found 2026-07-17 during the overnight WIRE2/HOME/WRSET/CPICK VE session (this DUT session, not a prior task). `SettingsStorage::load()` and `::save()` (`app/src/settingsStorage.cpp:140`, `:368`) both allocate a fixed `DynamicJsonDocument doc(3072)` with **no `doc.overflowed()` check** after building/parsing. Tonight's features (WIRE2 G1-G5, M-HOME-LOCATION, M-WEBRADIO-SETTINGS, M-COUNTRY-PICKER) all added fields to the persisted schema; combined with a fully-populated real device (4 `prLocs` slots, full `webRadio` block), the tree ArduinoJson needs to serialize now appears to exceed 3072 bytes. ArduinoJson v6 does not error on overflow — `createNestedObject`/assignment calls past capacity silently no-op, and `serializeJson()` happily writes whatever fragment did fit. The result is a **syntactically valid but incomplete** `settings.json`: on the next load, missing keys fall through per-field `containsKey()` checks to compile defaults, with no crash and no obviously-alarming log line (a `parse error` message only fires on a hard syntax error, which this is not).

**Evidence**: mid-session, a `get prloc` read came back with `label:"HOME"` at the compile-default Amsterdam coordinate (`52.367599,4.9041`, not the user's real, more-precise `52.37,4.92 (precision redacted for publish)`), all three other `prLocs` slots emptied (`label:""`), `dispLevel` reverted to the compile default `7`, `teletextPage` reverted to `101`, and `webRadioBitrateCap` reverted to `128` (the compile default) while `webRadioCountry` stayed correctly at `"NL"` — consistent with the overflow hitting mid-way through the `webRadio` object in `save()`'s field-write order (country writes fine, `bitrateCap` onward and the entire trailing `planeRadar.locs[]` array silently dropped). No firmware crash, no visible error; discovered only because the DUT operator happened to `get prloc` and noticed real location labels were gone. **User's real settings were recovered this session** from a `settings.json` snapshot captured at session start (`run/spiffs push`, verified byte-identical + a clean `SettingsStorage: loaded` on reboot) — this was a close call, not a today-only cosmetic bug.

**Fix sketch**: bump `DynamicJsonDocument` capacity in both `load()` and `save()` (a conservative size — 6144 or so, re-measured against the current full schema, not just bumped-and-forgotten) and add an explicit `if (doc.overflowed()) Serial.println("SettingsStorage: doc overflowed — data truncated!");` guard (in `save()` especially) so a future schema-growth regression fails loudly instead of quietly eating user data again. Consider whether the schema should track its own worst-case size (a `static_assert`-style budget check, mirroring how `mem_layout.h`/`gen_mem_layout.py` already track heap budgets elsewhere in this repo) rather than a hand-picked constant.

**Fix landed (2026-07-17, code-only session):** single `kSettingsJsonCapacity = 6144` constant shared by `load()`/`save()` (derivation documented at the constant); `save()` now checks `doc.overflowed()` **before** `SPIFFS.open(..., "w")` and aborts without touching the file (the open itself truncates, so the guard must precede it — the previous settings.json stays intact on flash); `load()` gets a warn-only overflow line, and the parse-error message now prints the `DeserializationError` name (makes `NoMemory` distinguishable from a syntax error); `save()` logs `doc memoryUsage/capacity` so future schema growth is visible in every save line. **Measurement finding (re-measured, not guessed):** worst-case doc for the current full schema is ≈ 2271 B — 90 slots × 16 B = 1440 B structure (slot size + structure sum verified by `static_assert` compiled with xtensa-esp32-elf-g++ against the vendored ArduinoJson 6.21.3) + ≈ 466 B key strings + ≈ 365 B max-length string values (load() copies both, no-dedup assumed). So 3072 was analytically *sufficient* for today's schema: the incident truncation is most consistent with the ctor's 3072 B heap allocation **failing under fragmentation** (capacity 0 → every add silently no-ops → valid-but-defaulted file — matches the all-compile-defaults evidence above, `webRadioCountry "NL"` included since NL *is* the default), rather than pool exhaustion. `overflowed()` returns true in both cases, so the new guards catch either mode. 6144 ≈ 2.7× worst case. Heap note: the doc is transient (one load() at boot, occasional UI saves), covered by mem_manifest.yaml's 60 K `headroom` reserve — deliberately not a manifest tenant (same scoping as before; the manifest registers resident/overlay buffers).

**Status:** **DONE — DUT-verified 2026-07-17** (VE session, fix build `8da3cf4` flashed as `cyd2usb_winamp_debug`). Protocol: SPIFFS snapshot first (`run/spiffs pull`, settings.json copied aside), then a full save→reboot→load round-trip against the user's real fully-populated config (all 4 `prLocs` slots filled: AMS/HH/CAM/WFD). Results: (1) clean boot on the fix build — `SettingsStorage: loaded`, no overflow/parse line, and every ground-truth value read back correct via `get prloc` (all 4 slots, `active:0`, `home` mirror) — the incident recovery held; (2) mutated `teletextPage` 601→604 (`set teletextPage` + `set settingsSave 1`), save logged **`saved (doc 1561/6144 B)`** — measured N=1561 B, under the ~2271 B analytic worst case as expected (real strings shorter than max), 25% of capacity; (3) `reboot` → 604 persisted AND all other fields intact (full `get prloc` sweep); (4) reverted 601, second identical `saved (doc 1561/6144 B)`, reboot → all values match the original snapshot; (5) final `run/spiffs pull settings.json` **byte-identical** to the session-start snapshot. Note: `get teletextPage` reads the Teletext app's lazy-inited copy — must `switchApp 9` first or it shows the compile default 101 regardless of `g_settings` (surface quirk, not a settings bug; cost one false alarm this session). Production firmware (fix included — verified `saved (doc %u/%u B)` / OVERFLOWED strings in the prod ELF; boot banner shows a stale 10:32 `__DATE__` from an unrecompiled TU, ignore it) reflashed at session end, clean `SettingsStorage: loaded`, monitor restored.
**Opened:** 2026-07-17 · **Closed:** 2026-07-17 · **Milestone:** — (cross-cutting, not tied to one feature) · **Owner:** Developer · **Deps:** none · **Size:** S (fix) — but worth re-measuring the real schema size rather than guessing · **DUT:** y (verified as above; long-string worst case covered analytically by the static_assert measurement, not exercised on-device)

### TASK-330 — `run_serialdbg_tests.py` `_settings_tap_row()` uses stale 26px row formula — T-SET-07 taps the wrong app row

Found 2026-07-17 while fixing the same drift in the three `prloc_*_smoke.py` tools (commit e929792, T-CPICK-01 fallout). The shared helper `_settings_tap_row()` in `app/tools/run_serialdbg_tests.py` (~line 4917) still computes `y = 28 + row*26 + 13`, i.e. the uncompressed `S_ROW_H=26` layout. The settings **Applications** list compresses rows to `_appListRowH() = min(S_ROW_H, S_CONTENT_H / CONFIGURABLE_APP_COUNT) = min(26, 212/10) = 21` px (`app/src/settings/appsSection.h`, hit-testing confirmed in `app/src/touch/hitbox.h`). Consequences: T-SET-03/T-SET-06 call it with app-list row 0 and still land correctly by luck (both formulas put row 0's midline in row 0's hitbox); **T-SET-07** calls it with row 2 (targeting "Aquarium") → y=93, which falls in row 3's range under the real 21 px height — the test taps the wrong app. Category rows (non-Applications sections) still use the uncompressed 26 px formula legitimately — the helper is used for both, which is why the fix isn't a one-line constant swap.

**Fix sketch**: give `_settings_tap_row()` a notion of context (category list vs compressed app list) — e.g. a second helper `_settings_tap_app_row()` using `28 + row*21 + 10` (midline per `drawRow()`'s `screenY + rowH/2`), or a `row_h` parameter — mirroring the `row_y()`/`APP_LIST_ROW_H` pattern now in the prloc smoke tools (e929792). Audit ALL `_settings_tap_row()` call sites in the file and classify each as category-row vs app-row before switching any. Then re-run T-SET-03/06/07 on DUT to confirm no regression (03/06) and the actual fix (07).

**Status:** **DONE — DUT-verified 2026-07-18**. Fixed by parameter/context split, not a constant swap: added `_settings_tap_app_row(dut, row)` (mirrors the `row_y()`/`APP_LIST_ROW_H` pattern from e929792 — `y = 28 + row*21 + 10`, `APP_LIST_ROW_H = min(26, 212//10) = 21`), left `_settings_tap_row()` for genuine category-list rows (still `y = 28 + row*26 + 13`).

**Call-site audit (all 7 in `run_serialdbg_tests.py`, none elsewhere in the repo)** — classified category-row vs app-row and switched only the latter:
| Line (post-fix) | Call | Context | Classification | Action |
|---|---|---|---|---|
| 4980 | `_settings_tap_row(dut, idx)` in `t_set_02`'s `for idx in range(5)` | taps the 5 top-level category-list stub rows | category-row | unchanged |
| 5003 | `_settings_tap_row(dut, 5)` in `t_set_03` | opens Applications from the category list | category-row | unchanged |
| 5014 | `_settings_tap_row(dut, 0)  # Stock` in `t_set_03` | row 0 **inside** the Applications app list | app-row (was mis-typed, passed "by luck" — row 0's midline lands in row 0's hitbox under both formulas) | → `_settings_tap_app_row(dut, 0)` |
| 5042 | `_settings_tap_row(dut, 5)  # Applications` in `t_set_06` | opens Applications from the category list | category-row | unchanged |
| 5043 | `_settings_tap_row(dut, 0)  # Stock submenu` in `t_set_06` | row 0 inside the Applications app list | app-row (same "by luck" case as 5014) | → `_settings_tap_app_row(dut, 0)` |
| 5071 | `_settings_tap_row(dut, 5)  # Applications` in `t_set_07` | opens Applications from the category list | category-row | unchanged |
| 5072 | `_settings_tap_row(dut, 2)  # Aquarium` in `t_set_07` | row 2 inside the Applications app list | app-row — **the actual bug** (y=93 lands in row 3's hitbox under the real 21px height) | → `_settings_tap_app_row(dut, 2)` |

Aside (out of scope, not fixed): row 0/row 2's inline comments ("Stock"/"Aquarium") don't match `kConfigurableApps[]`'s current order (`Stock` is index 5, `Aquarium` is index 6 — see the WR-4 audit table in test_plan.md line ~4369). This is a stale-comment/app-identity mismatch, not a coordinate bug — the tests only assert `settingsSection`/`settingsAppSubmenu` **indices**, not which app rendered, so it doesn't affect pass/fail. *(Resolved 2026-07-18, follow-up commit: comments and T-SET-07's docstring/print strings corrected to the real row identities — row 0 = Spotify `kConfigurableApps[0]`, row 2 = Crypto `kConfigurableApps[2]`; the historical "targeting Aquarium" wording above and the quoted PASS line below reflect the old strings.)*

**DUT re-run (2026-07-18, `cyd2usb_winamp_debug` via `./run/test-targeted T-SET-03,T-SET-06,T-SET-07`)**: snapshot-protected (`./run/spiffs pull` before, byte-identical after — diff clean). All three **PASS**:
```
[PASS] T-SET-03  Applications drill: section 5, submenu 0 confirmed; back×2 unwinds to -1/-1
[PASS] T-SET-06  suspend() reset confirmed: section==-1 submenu==-1 on re-entry
[PASS] T-SET-07  back×2 from Aquarium submenu: submenu→-1, section→-1 confirmed
```
T-SET-03/06 confirm no regression from the app-row split (they only ever tapped row 0, which happened to work under the old formula too). T-SET-07 is the actual fix under DUT proof — row 2's tap now lands at y=80 (was y=93, which fell in row 3's hitbox). No `OVERFLOWED` log line seen (TASK-329 guard). Production firmware + monitor restored at session end.

**Bundled in the same pass (tools-only, not filed separately)**: `app/tools/prloc_editor_smoke.py` destructive-scope hygiene, flagged by VE during T-CPICK-03 (see its test_plan.md entry) — the script would delete real slot 1 (`HH`) in addition to its documented empty-slot-2 assumption. Added a DESTRUCTIVE SCOPE banner enumerating exactly which slots are written (2) / deleted (1), plus an upfront `get prloc` read that aborts before any hardware mutation if slot 1 or slot 2 is non-empty (`--force` bypasses for a disposable/synthetic fixture). Script itself not re-run against this live device — the fix's entire point is that it no longer runs destructively by default.

**Opened:** 2026-07-17 · **Closed:** 2026-07-18 · **Milestone:** — (test-harness hygiene, cross-cutting) · **Owner:** Developer · **Deps:** none · **Size:** S-M (helper split + call-site audit + 3 DUT test re-runs) · **DUT:** y (T-SET-03/06/07 re-run, all PASS)

### TASK-331 — M-ICON-PIXELART: bake tooling — WYSIWYG pass-through, fill-ratio warn, host contact sheet

First slice of ADR-051 (2026-07-18 decision: 36×36 / Option B / warn-only
fill check). Tooling lands **before** the size bump so the host inspection
surface exists when the re-bake triage (TASK-332) needs it. Three changes,
no icon or golden churn (existing sources don't dimension-match 24×24, so
the bake output stays byte-identical — assert `run/check` golden gate clean
as proof):

1. **Pass-through on exact match**: `gen_taskbar_icons.py` skips the LANCZOS
   resample when source PNG dims == `TASKBAR_ICON_W`×`_H` — the source *is*
   the shipped icon (Option B WYSIWYG guarantee; host preview becomes exact
   by construction).
2. **Warn-only fill check**: per-icon bbox fill (alpha>128, per axis) printed
   at every bake; warn when the **major axis** lands outside [85%, 97%]
   (100% = the PlaneRadar edge-to-edge overshoot mode; minor axis unchecked
   so wide-flat glyphs like aquarium stay legal). Never fails the build.
3. **`--sheet` mode**: writes `app/tools/icon_drafts/BAKED_SHEET.png` — all
   baked icon pairs at true baked size, nearest-neighbor upscaled, each in a
   simulated slot (taskbar bg + 3px active-indicator + 1px separator, per
   `taskbar.h`). This is the host inspection surface for TASK-332/333/334;
   DUT is demoted to final eyeball gate only.

Also: `gen_icon_drafts.py` reads its target size from `gen/shell_layout.h`
(it currently hardcodes canvas sizes — the exact failure mode the milestone
exists to kill).
**Status:** **DONE — 2026-07-18.** All four pieces landed in
`gen_taskbar_icons.py` (`prepare_icon` pass-through + `fill_ratios` +
per-icon bake log with WARN lines + `--sheet`/`--sheet-out` →
`BAKED_SHEET.png`, true RGB565-decoded pixels in simulated 45×40 slots with
separator + 3px indicator) and `gen_icon_drafts.py` (`BAKE_W/H` +
`TASKBAR_BG` parsed from `shell_layout.h`; draft canvas = baked size —
native authoring, no intermediate-canvas resample; `simulate_baked`
mirrors the pass-through). Byte-identity proven two ways: `sha256sum -c
golden.sha256` clean after a fresh bake AND `app/gen/` untouched in git
(no current source is exactly 24×24, so pass-through is latent until a
native-size source exists — `weather_active.png` at 36×36 will be the
first to exact-match after TASK-332's bump). Fill warnings fire exactly
per the design-doc measured table (life 58% undersized, planeradar 100%
edge-to-edge, 83%-cluster flagged) — early triage signal for TASK-332/334.
`run/check` 6/6 PASS. Sheet visually verified on host (icon centring,
separator, indicator bar, fill labels all correct).
**Opened:** 2026-07-18 · **Closed:** 2026-07-18 · **Milestone:**
M-ICON-PIXELART · **Owner:** Developer · **Deps:** — · **Size:** S ·
**DUT:** n (host tooling only; golden byte-identity + `run/check` gate)

### TASK-332 — M-ICON-PIXELART: grow icon budget to 36×36, re-bake, host triage, DUT eyeball

ADR-051 point 1. Bump `TASKBAR_ICON_W`/`_H` 24 → 36 in `gen/shell_layout.h`
(via `preview_layout.py`'s export path or direct edit — keep the header's
comment format), re-bake all icons, regen `golden.sha256` (covers
`shell_layout.h` + `taskbar_icons.cpp/h` — verified 2026-07-18), `run/check`.
No layout code changes: `iconOffX/Y` in `taskbar.h` derive from the
constants (36×36 centres at x+4/y+2, clearing the 3px indicator bar and 1px
separator). Flash +~31.7 KB across 11 pairs — negligible.

**Host inspection step (before any flash):** generate `BAKED_SHEET.png`
(TASK-331 `--sheet`) and human-triage all 22 upscaled icons — every source
is smaller than 36, so all go through LANCZOS upscale and render softer.
Triage output = the explicit list of icons whose softness is unacceptable →
that list **is** TASK-334's scope. Accepted interim state per ADR-051: soft
is legal, no flag day.

**DUT step (last):** flash, one eyeball pass over the taskbar (BP-048 —
init must paint; host PNG ≠ TFT: RGB565 quantization + inversion + real
backlight), confirm active-indicator/separator clearance on real panel.
**Status:** **DONE — 2026-07-18.** Bump landed in 118dc07 (with
`preview_common.py` mirror constants fixed in the same commit — a future
`preview_layout.py --export` would have silently regressed the header to
24). `weather_active.png` (36×36) was the first PASS-THROUGH source, as
predicted. Host triage happened on BAKED_SHEET.png + the repaired
`preview_layout.py` (48e724d — it was still pasting TEXT.BMP letter
glyphs; now renders real icons, with ,/. scroll through TASKBAR_ORDER =
APP_ORDER minus eject-only WebRadio). Triage verdict (human): life bad;
clock/matrix/settings/stock/weather-inactive mildly soft; user widened
scope to weather-active, aquarium, teletext, crypto → all executed under
TASK-334. DUT eyeball 2026-07-18 after the TASK-334 install flash
(build Jul 18 07:20, d60b96d): human PASS on real panel — no clipping of
indicator bar or separators. `run/check` 6/6 at every step.
**Opened:** 2026-07-18 · **Closed:** 2026-07-18 · **Milestone:**
M-ICON-PIXELART · **Owner:** Developer (triage: human) · **Deps:**
TASK-331 · **Size:** S-M · **DUT:** y (single eyeball flash, shared with
TASK-334's — PASS)

### TASK-333 — M-ICON-PIXELART: re-author PlaneRadar icon pair natively at 36×36 (first test case)

ADR-051 exit criterion: the icon that surfaced the whole milestone
(TASK-302 follow-up) is the first authored under the new workflow.
`gen_icon_drafts.py` (target size now read from `shell_layout.h`, per
TASK-331) renders `planeradar` / `planeradar_active` candidates **directly
at 36×36** — no supersample-then-shrink-to-target-through-intermediate
canvas, the double-LANCZOS trap is structurally gone (supersampling for AA
within a single resize to the true target is fine).

**Host inspection loop (all iteration here):** candidates land on the
`icon_drafts/` contact sheet (true-size + NN-upscaled, in simulated slot)
— human approves on host **before** anything is copied into
`app/icons/taskbar/`. Fill target: major axis inside [85%, 97%] (the
TASK-331 warn band; shipped 24×24 planeradar is 100% edge-to-edge — this
re-author fixes that too). On approval: copy in, bake (pass-through — baked
bytes == approved PNG), golden regen, `run/check`.

**DUT step (last):** flash, one eyeball pass of the new pair
(inactive + active states).
**Status:** **DONE — 2026-07-18, milestone-closing task.** Executed via
`gen_icon_natives.py` (the pipeline TASK-334 proved), not the drafts
tool: `draw_planeradar()` re-anchors the drafts' ratio geometry (ring-w
0.125 / inner 0.5625 / cross 0.0625 of outer; dart 0.759R @127°,
0.44R/0.26R nose/tail) to a native 33px outer-edge bbox — 92%, matching
the clock/crypto ring family; the drafts' `TARGET_FILL=1.02` overshoot
hack died with the resize step it compensated for. Shipped 100%
edge-to-edge overshoot resolved (baked 89×86% / 92×92%, in band, no
WARN). Landed 6c2fc29; bakes PASS-THROUGH; other 18 natives regenerated
byte-identical (pipeline determinism check). `run/check` 6/6, prod
flash, **human eyeball PASS 2026-07-18** ("active icon look great" —
green rings/cross + blue disc + red dart confirmed on panel). Process
note (QM ledger): BP-051 sheet approval was a blanket mid-turn "proceed"
delegation rather than per-sheet sign-off — the BP-048 eyeball backstop
held as designed.
**Opened:** 2026-07-18 · **Closed:** 2026-07-18 · **Milestone:**
M-ICON-PIXELART (closes it) · **Owner:** Developer (approval: human) ·
**Deps:** TASK-331, TASK-332 · **Size:** S · **DUT:** y (eyeball PASS)

### TASK-334 — M-ICON-PIXELART: opportunistic re-touch of soft upscaled icons (scope from TASK-332 triage)

Backlog under ADR-051's no-flag-day rule: sources smaller than 36 (the
32×32 set — clock, weather, stock, teletext — plus any others the triage
flags) render soft after the TASK-332 upscale. Re-touch **only** the icons
the TASK-332 host triage marked unacceptable, each natively at 36×36 via
the TASK-333-proven workflow (draft → host contact-sheet approval → copy →
pass-through bake → golden → `run/check`). Imported hi-res art
(`spotify_active.png` Winamp bolt) keeps its master + resize path per
Option B — exempt unless triage says the 36×36 resize product itself is
unacceptable. Batch the DUT eyeball: one pass at the end for all re-touched
icons, not per icon.
**Status:** **DONE — 2026-07-18.** Scope from triage grew to **9 pairs**
(life, clock, weather, matrix, settings, stock, aquarium, teletext +
crypto added in review round 2); only spotify untouched (planeradar =
TASK-333). Executed via new `app/tools/gen_icon_natives.py` (65ede54 +
018de46 + 958db9f), which renders all candidates natively at
`TASKBAR_ICON_W/H` from `shell_layout.h`: rectilinear pixel art (life
glider, teletext lines) drawn 1:1 with zero resampling; curves at
integer SS=8 with exactly one LANCZOS down; settings/stock/crypto-₿ from
their Material SVG masters via inkscape; active palette sampled from the
shipped PNGs (life's blue→orange per-block gradient preserved).
Notable calls: teletext deliberately at 83% fill (square glyphs read
optically larger — its WARN is accepted); aquarium fish is **literal
text** — '><((( *>' in Noto Sans Mono, auto-sized until the ink-packed
glyphs fit 35px (getmask ink boxes, NOT textbbox which returns the
constant mono advance), gap-0 compressed packing, binarized to hard
pixels, '*' eye one font size up (binarization otherwise amputates it to
'^'). Human approval loop ran entirely on NATIVE_SHEET.png (3 rounds);
`--install` copied the approved set (d60b96d), all 18 bake
PASS-THROUGH, golden regen, `run/check` 6/6, prod flash + human DUT
eyeball PASS 2026-07-18. Note: deps assumed TASK-333 would prove the
workflow first; in practice 334 ran before 333 and proved it instead —
333 now reuses `gen_icon_natives.py`'s pipeline.
**Opened:** 2026-07-18 · **Closed:** 2026-07-18 · **Milestone:**
M-ICON-PIXELART · **Owner:** Developer (approval: human) · **Deps:**
TASK-332 · **Size:** M (9 pairs, 3 review rounds) · **DUT:** y (batched
eyeball with TASK-332 — PASS)

### TASK-335 — host preview tools: parse shell_layout.h instead of mirroring constants + inventory refresh

LL-114 structural fix. `preview_common.py` hardcodes `TASKBAR_ICON_W/H`
(and bg/indicator/sep colours) as comment-bound mirrors of
`gen/shell_layout.h`; `preview_layout.py --export` WRITES the header from
those mirrors, so a drifted mirror is a write-path regression (the
ADR-051 bump dodged this only because 118dc07 bumped both in one commit).
Fix: `preview_common.py` parses the generated header at import (the
`gen_taskbar_icons.py`/`gen_icon_drafts.py`/`gen_icon_natives.py` pattern
— reuse one shared parse helper rather than a fourth regex copy);
`load_icon_pil`/`load_icon_pygame` then track the header automatically.
Check `--export` round-trips the parsed values byte-identically against
the current header (it must not clobber the ADR-051 comments — decide:
preserve annotations or regenerate them).

Bundled (same Developer pass): feature_inventory.yaml description sweep
for the taskbar arc — `taskbar-001` still says "6 icon slots
(S/C/W/$/M/G via TFT font 4)" (two generations stale: pre-M-TASKBAR-ICONS
PNG icons, pre-ADR-051 36×36); the preview-tool entry still describes
TEXT.BMP glyph rendering. Update to current truth (baked 36×36 RGB565
pairs, pass-through bake, real-icon preview per 48e724d).
**Status:** **DONE — 2026-07-18.** New shared module
`app/tools/shell_layout.py` (`defines()` parser + `rgb565_to_rgb8`); all
four consumers migrated off private regex/mirrors: `preview_common.py`
(the load-bearing one — constants parsed at import; SCREEN_W/H stay
literal, they're hardware not header), `gen_taskbar_icons.py` (keeps its
per-key defaults for partial headers), `gen_icon_drafts.py`,
`gen_icon_natives.py`. `--export` template updated to carry the ADR-051
annotations; round-trip gate PASS: `_export()` output diffs
**byte-identical** against the live `gen/shell_layout.h`. Golden still
clean after a fresh bake (parser swap changed no output). Inventory
refreshed: `preview-tooling-001` (real-icon render, parsed constants,
correct `app/tools/` paths — old entry pointed at nonexistent
`Spotify-Diy-Thing/tools/`, status flipped planned→implemented) and
`taskbar-001` (baked 36×36 pairs + kTaskbarIcons; TFT-font glyphs noted
as the historical stopgap).
**Opened:** 2026-07-18 · **Closed:** 2026-07-18 · **Milestone:**
M-ICON-PIXELART (hygiene tail) · **Owner:** Developer · **Deps:** — ·
**Size:** S · **DUT:** n (`--export` round-trip byte-identity gate PASS)

---

### TASK-336 — Nixie clock: bake wire-glyph + hex-mesh + 3-pass-bloom sprite pipeline

M-CLOCK-NIXIE.md documented the gap since TASK-193: shipped `_drawNixie()`
was a flat `drawRoundRect` outline + plain `tft.drawString` digit — none
of the wire-glyph/hex-mesh/bloom pipeline `_clock_nixie.py` already
implements for the host preview tool. TFT_eSPI has no Gaussian blur, so
the fix reuses the pattern already proven for the Winamp skin
(`bake_skin.py`) and taskbar icons (`gen_taskbar_icons.py`): render the
expensive part on the host with PIL, bake to a flash-resident RGB565 C
array, `pushImage()` it at runtime.

New `app/tools/bake_nixie.py` reuses `_clock_nixie.py`'s bloom renderer
verbatim (same math as the host preview tool, so they can't drift) but
targets the **shipped** firmware tube geometry (52×70, r26 —
`ClockApp::_drawNixie` `kTw/kTh/kTr`), not the old concept-doc geometry
(48×110, r18) `_clock_nixie.py`'s own constants still use. Outputs
`app/gen/nixie_glyphs.cpp/.h` (10 digits × 52×70×2B = 71.1 KB flash, zero
extra RAM — ESP32 flash is memory-mapped, `pushImage` reads straight out
of `.rodata`). `_drawNixie()` step 1+5 (black fill + plain digit text)
replaced with one `pushImage()` call; glass outline/glow strokes/pin
shadows stay as cheap runtime primitives (baking those would cost flash
for no visual gain — they're just 1-2px strokes, not gradients).

**Status:** DONE — 2026-07-18. Flash 67.3%→70.0% (both debug and
production envs rebuild clean under budget). DUT-confirmed correct
(warm amber wire-glow, hex mesh visible) **by human eyeball** at the
time — the `screendump` tool's own capture of this exact screen was
colour-wrong (TASK-340), so automated verification wasn't possible then;
a person at the physical device confirmed it matched the host bake
preview (`app/tools/icon_drafts/NIXIE_SHEET.png`).

**Re-verified 2026-07-18, same day, post-TASK-340 fix:** with the
`screendump` colour-readback bug fixed, pulled a fresh capture of the
live Nixie clock and sampled the brightest pixel inside tube 0 — exactly
`(255, 210, 8)`, matching the ground-truth peak value TASK-340 itself
cited from the baked sprite's source array. No hollow-green-outline
artifact (the original symptom that led to discovering TASK-340).
Confirms the bake pipeline was correct all along — it was purely a
`screendump` capture-path bug, not a rendering bug.
**Opened:** 2026-07-18 · **Closed:** 2026-07-18 · **Milestone:**
M-CLOCK-STYLES (follow-on) · **Owner:** Developer · **Deps:** — ·
**Size:** M · **DUT:** y (human eyeball + `screendump` pixel-exact
re-verification post-TASK-340)

---

### TASK-337 — Flip clock: fix duplicate-digit render bug + Phase 2 visual polish

User report: "each digit on the DUT is shown twice." Root cause:
`_drawFlipPanel()` centred the **full** digit glyph independently in
each half-card's own 30px box (`MC_DATUM` at each box's own local
centre), with no clipping — since font 4 fits inside 30px without visual
cropping, the complete digit rendered whole in both the top and bottom
card. Fix: both halves now draw the SAME glyph anchored at the shared
split-line centre (`mid_y`) via `tft.setViewport(..., false)` — each
half is clipped to show only its physical half of one glyph, which is
what a real split-flap card does (top card = upper half of the numeral,
bottom card = lower half, meeting at the hinge).

Bundled Phase 2 polish (M-CLOCK-FLIP.md spec, previously undelivered
per that doc's "shipped" notes): 4-stop luminance-ramp gradient on each
card face (brightest at the outer edge, dimmest at the hinge — `M-CLOCK-FLIP.md`'s
"amplitude ≤15%, edges inward"); a shrinking drop-shadow cast on the
bottom plate during the falling-flap animation frames; round blinking
colon dots at 1Hz (was: static squares, per the doc's own admission
"no rotation, no blink, no ON/OFF cadence" — this uses the existing 1s
tick cadence rather than the doc's spec'd 500ms animated-disc version,
which would need a tick-gate architecture change, out of scope here).
Per human feedback the digit font was also swapped 4→6 (26px→48px, the
same bold font Digital style uses) — fits within the 62px combined card
height with margin to spare.

**Status:** PARTIAL. Dupe-digit fix: DONE, DUT-confirmed. Gradient/
shadow/colon polish (first pass): DONE and DUT-confirmed pixel-exact for
colour (2026-07-18, post-TASK-340 fix) — but then **superseded same
day** by a follow-up pass (below) after a side-by-side against the
`preview_clock.py` concept tool showed the concept never used a
gradient at all (flat card colours + a 3-tone hinge bevel instead). User
directed "match the DUT to the concept" over keeping the
already-verified gradient.

**Follow-up pass (2026-07-18, same day):** removed the 4-stop gradient
and `_scaleColor565`/`_fpGradientFill` entirely; replaced with the
concept's flat `BG_TOP`/`BG_BOT` fills + 3-tone hinge bevel
(shadow/groove/highlight). Resynced panel geometry to the concept's
exact pixel constants (`kFpW` 46→56, `kFpH` 62→78, `kFpMid` 30→38, `kFpR`
5→6, panel x-positions `{10,60,130,180}`→`{13,73,147,207}`, colon
recentred to the concept's gutter midpoint). Digit colour switched
amber→warm-white (`0xFFF0`→`0xF79D`, concept's `C_TEXT`). Flap-height
frame table and falling-flap shadow formula rescaled/rederived to match
(shadow now flat black via `max(2,flap_h/4)`, per the concept and per
this doc's own original shadow spec — the gradient-era shadow had
drifted from that). DUT-verified pixel-exact via `screendump`: 7/7
sampled points (housing bg, flat top/bottom card fill, all 3 bevel
rows, border) matched the new firmware constants exactly. Side-by-side
screenshot vs. the concept confirmed close visual parity. Production
firmware reflashed after verification.
`docs/architecture/designs/M-CLOCK-FLIP.md` updated to match (Parameters
table, static-render pipeline, frame table, status header) — see that
doc's 2026-07-18 changelog entry for full detail.

**Font-size root cause found and fixed (2026-07-18, same day, third
pass).** The card resize alone did *not* fix the "still needs
adjustment" complaint — font 6 is a fixed 48px TFT_eSPI bitmap font
(27px-wide digit glyphs) that doesn't rescale with its container, so it
stayed pinned at its old absolute size while the card grew around it,
making digits look proportionally *smaller* and thinner than before,
not bigger — the opposite of the intended effect, and exactly what the
user's own side-by-side screenshot caught (this was missed in the
resync pass; the user had to point it out). Root cause: no font-metrics
check was done when picking the resize target. Fix: switched
`_drawFlipPanel()`'s two `drawString()` calls from font 6 to font 8
(TFT_eSPI's other built-in digit-only font — 75px tall, 55px-wide
glyphs, already available via `-DLOAD_FONT8` in `platformio.ini`, no
new flash cost). Verified via side-by-side `screendump` against
`preview_clock.py` at matching digit values — size and boldness now
track the concept closely.
**Opened:** 2026-07-18 · **Milestone:** M-CLOCK-STYLES (follow-on) ·
**Owner:** Developer · **Deps:** — · **Size:** M · **DUT:** y
(side-by-side screendump verified; final user sign-off on the new look
still pending — don't close without it, this was a subjective
complaint originally)

---

### TASK-338 — VFD clock: fix full-canvas flicker tied to the colon blink

User report: "annoying screen refresh... tied to `:`." Root cause:
`_drawVFD()` did a full 275×240 `fillRect` clear **and** a full
54×24-cell redraw (1296 `fillRect` calls) on every 1000ms tick — not
just when the colon toggled, which happens to share the same 1s period,
making the two look linked. Fix: cache last-drawn digit values +
colon on/off state (same W-6 erase-gating pattern already used by
Digital style); only repaint a digit slot's cells when that digit's
value actually changes (~once/minute) and only repaint the colon's 8
cells when its state changes (~once/second) — removed the unconditional
full-canvas clear entirely (only needed once, in `repaint()`, on style
switch).

**Status:** DONE — code-verified (the root cause, an unconditional
full-redraw every tick, is structurally eliminated; delta-redraw is a
mechanical fix, not a judgement call). **Not re-confirmed live on DUT
this session** — flicker is a temporal artifact a still screenshot
can't prove either way, and the session moved on to other work before
circling back for a live glance. Low risk, but flag for a quick visual
check next time someone's at the device.
**Opened:** 2026-07-18 · **Closed:** 2026-07-18 · **Milestone:**
M-CLOCK-STYLES (follow-on) · **Owner:** Developer · **Deps:** — ·
**Size:** S · **DUT:** n (structural fix; live re-confirmation pending)

---

### TASK-339 — SERIAL_DEBUG `screendump` command + host tool + TWDT-panic fix

New capability, built to close the "I have to be the feedback loop"
problem raised mid-session: `tft.readRect()` GRAM readback (MISO wired
on this board — `TFT_MISO=12`, `SPI_READ_FREQUENCY=20000000` in
`app/platformio.ini` — previously unused anywhere in this codebase)
streamed out as base64 RGB565 bands over serial via a new `screendump`
debug command; `app/tools/screendump.py` (+ `run/screendump` wrapper)
reassembles bands into a PNG host-side. Lets structural/content DUT
state get verified without a human at the physical screen.

**Bug found + fixed:** `cmdScreenDump()` blocked synchronously for
~18s per full-canvas dump (30 bands × ~590ms of `Serial.write` at
115200 baud) without feeding the loop task's watchdog
(`esp_task_wdt_init(15, true)`, 15s **panic** timeout, `main.cpp`
`setup()`) — it panicked and hard-reset the device mid-capture on
nearly every dump. The host kept reading serial output straight through
the reboot with no way to detect it, silently capturing whatever the
fresh boot's default screen (WebRadio) showed instead of the requested
one — diagnosed via a coherent, fully-legible "wrong app" capture with
no `[shell] leaving/entered` log anywhere near it, plus two back-to-back
captures of a static screen differing by 94% of pixels. Fixed:
`esp_task_wdt_reset()` once per band (same pattern as TASK-288). Verified:
post-fix back-to-back diff dropped to 0.24% (160/66000 px — just the
colon blink), phantom-frame captures gone.

Also handled: cross-task Serial-write interleaving (spotifyTask/dataTask
log lines with no mutex guarding raw `Serial` writes across tasks) can
corrupt a band's base64 mid-transmission; `dump_with_retry()` detects a
malformed band and re-requests just that sub-region rather than the
whole dump.

New build env `cyd2usb_winamp_debug_noSpotify` (`-DDISABLE_SPOTIFY` on
top of `cyd2usb_winamp_debug`) for quiet DUT iteration — debug-only,
not a production variant, not on any `rnd/` branch (just a local dev
convenience, reuses the existing TASK-255 flag).

**Status:** DONE for structural/content capture — reliable, verified.
Colour capture was a separate bug (TASK-340: `readRect()`'s pushRect-compat
byte swap streamed uncorrected, compounded by an unreliable 20MHz SPI read
frequency) — **now fixed and closed**, same day. `screendump` colours are
trustworthy for gradient/bloom content too as of the TASK-340 fix;
re-verified pixel-exact on both Flip (TASK-337 follow-up) and Nixie
(TASK-336 re-verification) afterward.
**Opened:** 2026-07-18 · **Closed:** 2026-07-18 (structural scope only;
colour scope closed same day via TASK-340) · **Milestone:** — (tooling)
· **Owner:** Developer · **Deps:** — · **Size:** M · **DUT:** y

---

### TASK-340 — [CLOSED] `screendump` colour-readback bug: `tft.readRect()` returns wrong colours for non-flat content

Standalone hardware/firmware investigation, spun out of TASK-339/336.
**Never blocked any clock-style work** — TASK-336/337/338 were all
already DUT-confirmed correct by human eyeball; only the `screendump`
tool's own colour channel was wrong, discovered because it made
Nixie's baked amber bloom look like a hollow green outline when the
physical device showed correct amber.

**Root cause — two compounding bugs, found via the task's own
suggested "systematic palette sweep" experiment, run through a new
`colorprobe` SERIAL_DEBUG command (`app/src/main.cpp` `cmdColorProbe`,
~line 3706):**

1. **Real bug (software, always present):** `tft.readRect()` (vendored
   `TFT_eSPI.cpp` ~line 1412-1413) deliberately returns each pixel
   *byte-swapped* — the comment right there says why: "Swapped colour
   byte order for compatibility with `pushRect()`", so a captured
   buffer can be fed straight back into `pushRect()` with no
   correction. `cmdScreenDump()` streamed that swapped buffer raw, and
   because a 5-6-5 field layout doesn't align on byte boundaries, a
   plain byte-swap of it does **not** look like a clean channel
   permutation when decoded with the standard bit-shifts — it looks
   like scrambled noise (exactly what the original 5-point probe
   found, e.g. green `(0,255,0)` → `(0,129,8)`). This is why manual
   inspection never spotted "it's just byteswap()" — the corruption
   pattern from a mid-field byte swap doesn't read as one.
2. **Confounding bug (hardware/timing, was masking #1):**
   `SPI_READ_FREQUENCY=20000000` (`app/platformio.ini`) was genuinely
   unreliable on this board — actual bit errors on the MISO read at
   20MHz, not a deterministic transform. This is why earlier ad-hoc
   probing (at 20MHz) never found *any* clean formula, permutation or
   otherwise: the raw signal itself was noisy, so there was no clean
   transform to find until the read was made reliable.

**How isolated:** `colorprobe` fills/pushes 25 known RGB565 values
(16 via `fillRect` — exercises write+read together; 9 via `pushRect`
with raw words like `0xDEAD`/`0xBEEF` — exercises a pure write/read
round trip, bypassing colour semantics entirely) and reads each back
raw via `tft.readRect()`, printing expected vs. actual as JSON. At the
original 20MHz: 0/25 matched any clean transform. At 1MHz: 25/25
matched `actual == byteswap(expected)` exactly (push-probe values
round-tripped byte-for-byte). At 2500000 (reusing the
already-DUT-proven `SPI_TOUCH_FREQUENCY` value on this same board):
25/25 clean again, confirmed on two independent runs — settled on
2.5MHz as the fix (smaller change than 1MHz, same margin evidence).

**Fix applied:**
- `app/platformio.ini` (`common_cyd` `build_flags`): `SPI_READ_FREQUENCY`
  20000000 → 2500000, with a comment recording the finding and pointing
  at this task.
- `app/src/main.cpp` `cmdScreenDump()` (~line 3697-3701): undoes
  `readRect()`'s internal swap in-place on `s_band` before base64
  encoding, so the stream this command emits is true RGB565 — no
  change needed to `screendump.py`'s `rgb565_to_rgb888()`, which
  already assumed standard (non-swapped) RGB565.
- Kept `colorprobe` as a permanent SERIAL_DEBUG command (cheap,
  registered in `kCmds[]` with a real help string like its siblings)
  — useful if `SPI_READ_FREQUENCY` or the read path is ever touched
  again.

**DUT verification (2026-07-18, `cyd2usb_winamp_debug`):**
1. `colorprobe` sweep at the fixed 2.5MHz: **25/25 clean**, confirmed
   on two independent runs (`actual == byteswap(expected)` for fills,
   `actual == expected` for raw pushes).
2. Live `./run/screendump` of the Nixie clock (`switchApp 1` +
   `set clockStyle nixie`): dumped PNG shows correct amber digits with
   a clean glow bloom, **not** the previously-reported hollow green
   outline. Numerically sampled the brightest digit pixel: **exact
   match** to the task's own cited ground-truth peak, `(255, 210, 8)`,
   with clean amber (no green) throughout the surrounding bloom.

Production firmware (`cyd2usb_winamp`, which inherits the same
`SPI_READ_FREQUENCY` fix from `common_cyd`) rebuilt and reflashed;
monitor restored. Device confirmed booting normally post-flash.

**Opened:** 2026-07-18 · **Closed:** 2026-07-18 · **Milestone:** —
(tooling / hardware investigation) · **Owner:** unassigned (session
agent) · **Deps:** — · **Size:** M (two-part root cause, one debug
command, one platformio.ini flag, one firmware post-correction) ·
**DUT:** y (colorprobe sweep 25/25 clean ×2 runs; live Nixie
screendump visually + numerically confirmed correct)
