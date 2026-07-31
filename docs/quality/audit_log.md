# Audit Log

> Owner: Quality Manager

All audits: scope, findings, actions, results.

### Audit — 2026-07-11 — M-PLANERADAR TASK-307 DUT validation / milestone close

**Triggered by**: human ("QM PM happy?") after TASK-307 (DUT validation, the
last open task) closed and the milestone was reported done.

**Scope**: TASK-307's DUT run (6 exit criteria), the two new VE test-logic bugs
found and fixed mid-session, and doc/inventory hygiene at milestone close
(`tasks.md`, `roadmap.md`, `feature_inventory.yaml`, `test_plan.md`,
`docs/verification/regression_suite/m-planeradar-dut.md`).

**Findings**:
1. LL-107 (new): two VE tests (T_PR_02, T_PR_05) were initially written against
   `prLastHttp==200`/a diff of it — `fetchPlaneRadar()` never writes 200 into
   the result struct on success (only into a log line), so `errorCode==0` is
   ambiguous between "never fetched" and "fetched fine." Both failed on real
   hardware (one as a false-positive "error"), diagnosed via a manual serial
   log correlation, and rewritten to gate on `get activeError`'s
   `connecting`/`active` fields instead (the same ADR-046 signal already
   DUT-proven for 4 other apps). Fixed and re-verified same session.
2. LL-108 (new): T_PR_03 (range-cycle-by-tap) stuck after tap #1 on the first
   DUT run — `handleInput()`'s per-tap re-enqueue armed shell-busy, and with
   TASK-243's 403-retrying Spotify holding `tlsYield()` in contention, a
   second tap arrived before the first fetch resolved and was silently
   dropped. Fixed by injecting synthetic aircraft first (`prInjectAircraft`)
   so the tap-cycle test is isolated from the network side-effect entirely,
   rather than tuning wait-timeouts to the current contention level.
3. **Defect found + fixed**: `feature_inventory.yaml`'s `planeradar-001` entry
   had `test_ids: []` and a `notes:` block explicitly stating "OPEN: TASK-307
   ... BLOCKED this session, no CH340 device attached" — both stale the
   moment TASK-307 actually ran and closed in *this* session. This is exactly
   QM's audit dimension 2 (features `implemented` with no `test_ids`). Found
   by re-reading the entry after adding the DUT-validation paragraph to its
   `description:` — the `test_ids:`/`notes:` fields weren't touched in the
   first pass. Fixed same session: `test_ids` now lists T_PR_01-06 +
   T162-T166/T242; `notes` updated to reflect closure.
4. `cross_features:` for `planeradar-001` was already correctly populated
   (app-registry-001, data-task-001, taskbar-icons-001, touch-004,
   tls-yield-001, settings-001) at TASK-303/304 time — NEW-APP-CHECKLIST §5
   was followed correctly the first time; no finding here, noted as a GOOD
   for contrast with finding 3.
5. T_PR_05 (fetch-error exit criterion) is a SKIP, not a PASS — network-
   dependent (adsb.fi rate limit not hit in 20 rapid-fire attempts this run).
   Correctly recorded as SKIP with reasoning in both `test_plan.md` and the
   regression suite doc, not silently upgraded to PASS or hidden. GOOD.
6. Watch item (not yet a defect): the 30-min coexistence soak (exit
   criterion 4) ran against a 403-retrying Spotify session (TASK-243,
   Premium lapsed, external/still-open) rather than literal playback — a
   representative but not literal satisfaction of "alongside Spotify
   playback." Disclosed in-doc, not silently absorbed as a full pass. Same
   disclosed-scope-cut discipline as the phase-0 audit's finding 2.

**Actions assigned**: none new required — fixes for findings 1-3 already
applied in-session. LL-107/LL-108 promotion to `best_practices.md` requires
human sign-off (QM does not self-promote).

**Resolution**: Findings presented to human 2026-07-11. Feature-inventory
staleness (finding 3) corrected same session. LL-107/LL-108 remain open
candidates pending human decision on promotion.

---

### Audit — 2026-07-11 — M-PLANERADAR phase 0 close-out retrospective

**Triggered by**: human ("QM, PM, are you happy?") after phase 0 closed and
ADR-048/049 were accepted.

**Scope**: Quality review of the M-PLANERADAR phase-0 campaign (2026-07-10..11):
four sub-design docs (`phase0-api-probe`, `phase0-parse-heap`,
`phase0-preview-ui`, `phase0-airport-db`), the parent design doc, two ADRs,
and the 7-task PM breakdown (TASK-301..307). No firmware code exists yet —
this is a docs/tooling-only milestone.

**Findings**:
1. Designer-review discipline: 4 rounds including independent re-execution of
   the parse harness and API oracle before anything was committed; caught a
   ~21% fetch-radius undercount, an unmeasurable heap-allocator claim, and a
   filter field list that would've broken the ground-speed fallback on-device
   — all fixed pre-commit. GOOD.
2. Deliberate scope cuts recorded honestly, not silently absorbed: the
   shortened evening soak (350/2 160 requests) and Q5's stale-indicator
   default (chosen without a rendered comparison) are both flagged in-doc as
   named cuts with rationale, distinguishable from "criterion fully met."
   Same discipline as this project's established practice around disclosed
   gaps. GOOD.
3. LL-105 (new): two of six preview-UI design questions (Q4 runway overlay,
   Q6 heading precision) had "confirmed" language in the doc before the tool
   actually exercised the claimed code path — Q4 had no runway-drawing code
   at all (only a stray color constant), Q6 was eyeballed against full float
   precision instead of the whole-degree rounding firmware actually ships.
   Both caught by reading the tool's source against the specific claim, both
   fixed and re-verified same session before being recorded as closed. Same
   failure shape as finding 1 (measurement-technique-vs-claim mismatch),
   recurring across this milestone.
4. LL-106 (new): the second TLS cert-chain observation (must happen on a
   different calendar day) was first scheduled via `CronCreate`, a
   session-only primitive that silently stops existing if the session ends —
   wrong tool for cross-session work. Caught by the human, not self-caught;
   corrected to a durable `tasks.md` entry (TASK-301) before any damage (the
   job would have just quietly never fired).
5. ADR discipline: both crystallised decisions (D1(b′) parse lean, V-europe
   airport-DB variant) captured as ADRs rather than left as verbal/design-doc-
   only decisions, per the "no verbal-only decisions" rule — proposed, then
   accepted 2026-07-11 with the human's explicit go-ahead, and every
   cross-reference (parent doc, sub-docs, tasks.md, roadmap.md) updated in
   the same pass rather than left to drift. GOOD.
6. Watch item (not yet a defect): TASK-302 (taskbar icon assets) blocks
   TASK-304 (app registration) at compile time via `taskbar.h`'s
   `static_assert` — correctly noted as a dependency in tasks.md, but the 7
   tasks were filed without enforced ordering beyond the `Deps:` line. If
   implementation starts on TASK-304 before TASK-302 lands, the build breaks
   immediately (by design, not silently) — low risk, flagging for awareness
   only.
7. Watch item (not yet a defect): TASK-301 is calendar-gated with no active
   trigger now that the cron job was cancelled (finding 4) — relies on a
   human or future session checking `tasks.md`. Same class of risk LL-102
   already generalised ("deferred status flips rot"); no new LL warranted,
   just a pointer to the existing one.

**Actions assigned**: none new required — TASK-301/302 already stand as
filed. LL-105/LL-106 promotion to `best_practices.md` requires human
sign-off (QM does not self-promote).

**Resolution**: Findings presented to human 2026-07-11. ADR-048/049
acceptance already given in this session. **LL-105 promoted to BP-046**
(human, 2026-07-11) — see `best_practices.md`. LL-106 remains an open
candidate, pending human decision.

---

### Audit — 2026-07-07 — M-TASKBAR-FEEDBACK (TASK-279) milestone close-out retrospective

**Triggered by**: human ("PM, QM, are you happy?") after the TASK-279 implementation campaign.

**Scope**: Quality review of the five-commit TASK-279 close (`1d07433..da4deca`): BP-024
gate, firmware blits + instrumentation, T_TBFB suite, latency matrix, docs.

**Findings**:
1. Process adherence: BP-024 honoured *as a separate commit before any code* (first time
   the gate is cleanly visible in history); `./run/check` 6/6 before all five commits;
   BP-043 clean (nothing left uncommitted); master local-only. GOOD.
2. BP-044 discipline: no "root-caused" claims made. The one defect found (T_TBFB_04
   false-FAIL) was fixed and re-verified on the DUT (PASS remainingMs=278) before merge;
   the +11–13 ms external-clock delta is labelled *attribution* with the internal
   `shell.switch` clock recorded in-session as the control. GOOD.
3. LL-100 (new): data-dependent assertion surface false-failed under the standing
   TASK-243 blocker — same family as TASK-277's T_WR_ERR_x isolation defect; pattern
   recorded for test-authoring time.
4. LL-101 (new): instrumentation wire-time shifted the external latency clock; internal
   perf clock kept the before/after honest. Candidate measurement-plan discipline —
   **brought to human, not self-promoted**.
5. Dispositions D1–D3 properly recorded in the design doc and flagged; **D1 (human glance
   at the highlight treatment) is the only open verification item** — the milestone's
   headline exit criterion is visual and no serial assertion can close it (T168 precedent
   correctly cited).
6. Watch item (not a regression): wr_playing in-window `loop_max` median read 44.5 ms
   (4-hb sample, different live station) vs E1's 24 ms; the gating tail statistic held
   (max 50 ms, 0 iterations >50 ms). Re-check opportunistically at the next 10-min
   PLAYING window; if the median holds ≥40 on a fast station, file it.
7. DUT-throughput tax confirmed again: 3 of 6 DUT sessions aborted on boot-WiFi flakes
   (`BOOT_WAIT=30` + rc-scoped retry recovered all); TASK-283 (link supervisor) remains
   the standing fix, no new task warranted.

**Actions assigned**: none new (TASK-280/281 pre-exist and stand; TASK-294 remains free).
LL-101 discipline → human decision on BP promotion.

**Resolution**: **All items closed (human, 2026-07-07).** D1 ratified — pressed
highlight + amber commit bar confirmed visible on device; visual exit criterion closed,
OQ1 halo treatment stands. D2 (2-min AFTER windows) and D3 (T_TBFB_04 in-run test fix,
no task) ratified. **LL-101 promoted to BP-045** (internal clock alongside external
clock in every latency before/after). Audit closed, no open items.

---

### Audit — 2026-07-07 — M-WR-AUDIO-TASK (TASK-278) milestone close-out retrospective

**Triggered by**: human ("PM, QM are you happy?") after the E1-E5 exit-criteria campaign.

**Scope**: Quality review of the TASK-278 close and the six-commit crash-fix chain that
preceded it (TASK-285/286 → 287 → 288 → 289 → 290), commits `9838637..05f5a78`.

**Findings**:
1. Process adherence: every commit gated on `./run/check` 6/6; user WIP kept out of agent
   commits via index-only staging (twice); master local-only respected. GOOD.
2. LL-097 (new): "root-caused via source reading" granted without DUT falsification — wrong
   twice in one day; the corrected discipline (fix must stop the original repro + include a
   control case) is a best-practice candidate — **brought to human, not self-promoted**.
3. LL-098 (new): `wr-soak` balance gate false-FAILs (verifier defect, TASK-292 filed to VE).
   The E2 PASS-with-disposition override is **documented in the design doc and awaits human
   ratification** (QM view: evidence is sufficient — diff distribution + lfb invariant).
4. LL-099 (new): run/-wrapper bypass near-miss, self-corrected; confirming instance of an
   existing rule, no new BP needed.
5. E3 scored PASS on pump/mutex objectives while its literal spec text ("assert TASK-218
   debounce fires") failed against a pre-existing detection gap (TASK-291, answers OQ5).
   Scoping judgment disclosed in the design doc; **awaits human ratification**.
6. Verification-tooling debt: three DUT campaign aborts were AP/boot-path environment, not
   product code; TASK-290 fixed one class permanently. TASK-283 (link supervisor) remains
   the biggest DUT-throughput tax.

**Actions assigned**: TASK-291 (Developer, P2), TASK-292 (VE, P3) — both filed in tasks.md.
BP candidate from LL-097 → human decision.

**Resolution**: Human ratified all three items 2026-07-07: E2 PASS-with-disposition
(verifier false-FAIL, TASK-292) and E3 scoped pass (TASK-291 carries the detection gap)
stand as final verdicts; LL-097 adopted as **BP-044**. Audit closed, no open items.

---

### Audit — 2026-06-27 — TASK-258 / EXP-009 bottom-up bare-rig (no-PSRAM ceiling)

**Triggered by**: human ("QM: LL-087/088 + the platformio.ini pin note → human")

**Scope**: Quality close-out of the bottom-up bare-rig experiment that settled the no-PSRAM
WebRadio hardware question. Records the experiment + its process wins as a quality event. The
rig is out-of-tree (`~/proj/webradio-bare/`, own throwaway git repo `1c25982`); no project
firmware shipped. Both bare configs (no-display, +CYD TFT) PASS — hardware plays MP3 radio;
ADR-045's NO-GO is footprint-bound, not silicon-bound.

**Areas checked**:
- [x] Process adherence (PROP rev2 panel-approved before execution; R&D out-of-tree rig per AGENTS.md; EXP report written; PM task topology updated)
- [x] Hygiene per PROP R3 / LL-002/003 / LL-007 — rig outside the repo, `.gitignore` excludes `secrets.h` + `.pio/`, `git ls-files` confirms only 3 files tracked (no creds), not added to `run/check`, EXP-009 + commits contain no WiFi creds (the `192.168.1.181` in the log is the device DHCP LAN IP, not a secret)
- [x] Measurement discipline — caps dead-block re-probed per build (caught the 38,900-is-not-fixed misread → LL-088); CP1/CP2/CP3 capture matched the PROP

**Findings**:
- LL-087 (measure the hardware ceiling bottom-up with a bare control before grinding a top-down strip) and LL-088 (a state-dependent `usable = free − maxAlloc` figure was read as a fixed constant) filed this retrospective.
- BP-042 (PROPOSED) filed: a defensive dependency pin carries an inline why-not-newer note (version that breaks / failure mode / safe range). Originates from the bare rig's `ESP32-audioI2S@2.3.0` pin-note, whose value was proven by the v2.0.6 `SD_MMC.h` swap failure.
- No hygiene defects. Task topology correctly updated: TASK-258 DONE, TASK-255 parked (superseded), TASK-257 filed (optional Lane C-1).

**Actions assigned**:
- QM: bring LL-087, LL-088, and BP-042 (PROPOSED) to human for sign-off. ← this row.
- PM/Architect (downstream, not this audit): the product decision (stripped boot-direct-to-WebRadio variant vs ADR-045 stands for the multi-app board) is open and unowned — flag to human as a decision, not yet a task.

**Resolution**: Human sign-off 2026-06-27 — **BP-040, BP-041, BP-042 all adopted** (final numbers assigned, promoted above the candidates line; latest adopted BP is now BP-042). BP-041 adopted with an added escape hatch (a short-lived variant may instead be registered in a tracked exceptions list with explicit expiry/owner). LL-087/LL-088 retained as standing lessons (no separate BP). Candidates section now empty.

---

### Audit — 2026-06-26 — M-WEBRADIO-SPOTIFY-DISABLE design-review cycle (5-agent panel)

**Triggered by**: human ("do the rest" of quality follow-ups for the consensus-approved design)

**Scope**: Quality review of the multi-round design-review process for
`docs/architecture/designs/M-WEBRADIO-SPOTIFY-DISABLE.md` (M-WEBRADIO-NOPSRAM — a
`-DDISABLE_SPOTIFY` / `cyd2usb_webradio` experiment to free no-PSRAM RAM for WebRadio
playback and sidestep the TASK-243 Premium blocker). This row records the **review cycle
itself as a quality event**, not a feature/code audit — no firmware shipped; the design is
scheduled as an `rnd/webradio-nopsram` experiment (EXP-008), not yet implemented.

**Areas checked**:
- [x] Process adherence (design-before-code; R&D-on-branch per AGENTS.md; ADR supersede path)
- [x] BP/LL conformance of the proposal (BP-031, BP-016, BP-024, LL-006, LL-084, LL-085)
- [x] Experiment lifecycle (kill criterion + FAIL artefact disposition)
- [x] Review-process effectiveness (did the panel catch real defects before scheduling?)

**Process record**:
- **5-agent panel**: PM, Developer, VE, QM, R&D. Two rounds.
- **Round 1** (rev1): 4× NEEDS-CHANGES + 1× AGREE-WITH-NITS. QM verdict: NEEDS-CHANGES
  (2 blocking — B1 no kill/cleanup criterion on FAIL; B2 `tlsYield` no-op not reconciled
  with the human-approved BP-031 invariant).
- **Round 2** (rev2/rev3): consensus — Developer AGREE; PM/VE/QM/R&D AGREE-WITH-NITS.
  Both QM blockers resolved (§Step-1 hard-kill pre-gate + §Process FAIL disposition;
  §Approach BP-031 reconciliation paragraph + per-site `// DISABLE_SPOTIFY: …BP-031 n/a`
  comment convention guarding against the LL-084 mislead). rev1 → rev3.

**Findings**:

1. **Review process caught a load-bearing hypothesis error — GREEN (decisive quality win).**
   rev1's mechanism claim was "removing the TLS session reduces fragmentation → enlarges the
   contiguous block (`maxAlloc`)." This **directly contradicted EXP-007's measured finding**
   that `maxAllocHeap` is *pinned at 38,900 bytes* in both the 8 KB and 16 KB input-buffer
   runs (caps-restricted, not the audio allocator's source). R&D's round-1 challenge forced a
   correction to the defensible **usable-pool** mechanism (`usable = free − dead_block`), which
   in turn produced a falsifiable quantified prediction (+~8 KB margin vs the 22.7 KB decoder
   demand) and a cheap measurable kill gate. Had the panel rubber-stamped rev1, the experiment
   would have measured the wrong metric and produced an uninterpretable result. This is the
   single strongest argument for the multi-role review discipline in recent memory: an
   experiment hypothesis was checked against the *prior* experiment's measured data and found
   inconsistent **before** any DUT time was spent. Captured as LL-086.

2. **FAIL kill/cleanup criterion was absent in rev1, resolved in rev3 — AMBER (resolved).**
   QM B1. rev3 §Measurement now has a hard-kill Step-1 pre-gate (abort on `usable < decoder +
   buffer`) and §Process states the disposition: branch abandoned, env+guards never merged to
   trunk → nothing to clean; cleanup-task placeholder named at scheduling. Generalised as
   BP-040 (PROPOSED).

3. **BP-031 invariant reconciliation was missing in rev1, resolved in rev3 — AMBER (resolved).**
   QM B2. Making `tlsYield`/`tlsResume` global no-ops in the variant risked misleading a future
   BP-031 auditor (cf. LL-084, where BP-031's own cited evidence was unverified). rev3 adds the
   default-governed / disabled-variant-vacuous reconciliation + per-site comment convention.

4. **Two new BP candidates surfaced — recorded as PROPOSED, NOT adopted.** BP-040 (experiment
   names gate + FAIL disposition + cleanup-task id before scheduling) and BP-041 (build-flag
   variant gated in `run/check` or removed; cf. LL-085 rot). Both in `best_practices.md`
   under "Candidates — proposed, pending human adoption." Latest adopted remains BP-039.

5. **Process adherence — GREEN.** Design-before-code honoured (no code written; experiment
   scheduled on an `rnd/` branch per AGENTS.md). Supersede path for ADR-045 correctly
   anticipated and correctly *narrowed* in rev3 from "supersede" to "amend" (a PASS proves
   no-PSRAM WebRadio is viable *in a Spotify-free build*, not for the default Spotify-enabled
   board — avoids the over-claim). The supersede/amend ADR reconciles two predecessors
   (ADR-045 and the ADR-029 cleartext-media amendment), correctly flagged to Architect.

**Actions assigned**:
- QM: record BP-040 + BP-041 as PROPOSED candidates (self — done this session).
- QM: file LL-086 (experiment hypothesis must be checked against the prior experiment's
  measured findings before scheduling) — done this session.
- human: review BP-040 / BP-041 for adoption; review LL-086 for promotion.
- R&D: EXP-008 method must specify *how* the caps-restricted dead-block is re-measured on the
  disabled build (do not assume 38,900 transfers) — QM non-gating nit, handoff to R&D.
- Developer: `T_WR_PLAY_SUSTAIN` queryable PLAYING-duration is a Developer deliverable, not a
  VE assumption (BP-024) — to be listed as a Developer sub-item at scheduling (PM owns
  tasks.md; flagged, not filed here).

**Resolution**: review cycle closed at consensus (rev3). Quality docs updated this session
(BP-040/041 proposed, LL-086 filed, this audit row). Experiment not yet implemented; no
firmware/feature audit applies until EXP-008 runs. tasks.md scheduling owned by PM (parallel).

---

### Retrospective — 2026-06-14 — M-TELETEXT (TASK-177–191)

**Triggered by**: human (post-milestone retrospective request)

**Scope**: Full M-TELETEXT milestone — NOS Teletekst firmware implementation (TASK-177–191), icons (TASK-179), VE suite (T249 planned, T272 executed), ADR-044 accepted.

**Areas checked**:
- [x] Design process quality (PoC before firmware)
- [x] Bug classes introduced and found
- [x] Test coverage
- [x] ADR accuracy post-test
- [x] Pattern reuse and gaps

**Findings**:

1. **On-host PoC before firmware was executed** — GREEN. `preview_teletext.py`, NOS API reverse-engineering, resource impact assessment all completed before TASK-177 (firmware) began. Practice applied from prior lessons. No rendering surprises on first DUT flash.

2. **ADR-044 item 9 was architecturally wrong at design time** — RED (resolved). Design stated "fetchTeletext follows weather pattern (no tlsYield)." T272 confirmed real TLS heap contention. ADR-044 item 9 revised post-test. LL-071 filed: default for all dataTask HTTPS fetchers should be *with* tlsYield; omitting it requires measured justification.

3. **`_lastFetch = 0` silently fails as "force immediate fetch" during early uptime** — AMBER (resolved). Used in three places in teletextApp.h; `resume()` comment explicitly promised "force immediate fetch" but the condition was unsatisfied within first 60s. Fixed by `_forceNow()` unsigned-underflow helper. LL-072 filed: `_lastFetch = 0` idiom is an early-boot footgun.

4. **`String::indexOf()` null-unsafe; NOS body has embedded null bytes** — RED at test time (resolved). ISO-8859-1 teletext control codes include `\x00\x00` at positions 1065–1066, before `</pre>` at 1067. `strstr()` stopped at null; `indexOf()` returned -1. Fixed with null-safe `memcmp` scan. LL-073 filed.

5. **Three bugs found in single T272 run; none reached production** — GREEN (quality outcome). T272 was designed for TLS contention; it also surfaced two unrelated bugs. All three fixed in-session before commit.

6. **T249–T271 planned but not executed** — AMBER (known gap). VE suite has 23 planned/ready-to-run tests beyond T272. Blocked on test harness gaps or marked manual. Not a blocker for milestone close; filed as known gap in test_plan.md.

7. **tlsResume() missing from two early-return paths** — RED at code review time (resolved). After adding `tlsYield()` at function entry, the `http.begin` failure path and the "no `<pre>` block" early-return path were missing the matching `tlsResume()`. Would have permanently suspended Spotify's TLS session on any fetch failure. Fixed in same session.

**Actions assigned**:
- LL-071 filed (tlsYield default for all dataTask fetchers). Open — BP candidate.
- LL-072 filed (`_lastFetch = 0` early-boot footgun). Open — BP candidate.
- LL-073 filed (String::indexOf null-unsafe). Open — BP candidate.
- Audit remaining apps for `_lastFetch = 0` with "force immediate fetch" intent — CryptoApp, WeatherApp init() paths. (Developer handoff — not scheduled.)

**Resolution**: All RED findings resolved same session. Milestone complete. Three LL entries open for human BP promotion.

---

### Audit — 2026-06-13 — M-PREVIEW-FRAMEWORK (TASK-192)

**Triggered by**: human (post-milestone sign-off request)

**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage
- [x] Documentation currency

**Findings**:

1. **No `feature_inventory.yaml` entry for M-PREVIEW-FRAMEWORK** — AMBER. This is a host-side tooling refactor, not a firmware feature, so its absence is defensible; however the inventory has no note explaining scope. No action required unless team decides to track host tools in inventory.

2. **No VE test plan for preview_common** — AMBER (accepted gap). Host-only Python module; no serial/DUT test path applies. Verify step exercised all public API functions and render pipelines headlessly. Documented in TASK-192.

3. **No tasks filed before implementation** — AMBER (LL-069 filed). TASK-192 is retroactive. State would have been unrecoverable on interrupt.

4. **`pygame.K_Q` crash** — RED at implementation time; resolved. Found by verify step before commit. `PreviewWindow.handle_event` would have crashed every tool using keyboard input. Fixed to `pg.K_q`. LL-070 filed.

5. **Design doc exit-criteria pixel off-by-one** — AMBER. Spec says separator at y=39; implementation and both reference tools draw at y=40. Doc should be corrected to `(275, 40)` to prevent future false-fail if test is automated. Action: Developer to update M-PREVIEW-FRAMEWORK.md exit criterion line.

6. **Design doc status not updated** — AMBER. Still reads "reviewed — pending Architect revision pass." Needs update to "done" now that implementation is verified. Action: Architect to update.

7. **Roadmap updated** — GREEN. M-PREVIEW-FRAMEWORK status changed from "not started" to "done" this session.

**Actions assigned**:
- Developer: correct `(275, 39)` → `(275, 40)` in M-PREVIEW-FRAMEWORK.md exit criteria
- Architect: update M-PREVIEW-FRAMEWORK.md status to "done — implemented 2026-06-13"

**Resolution**: closed — both doc corrections applied this session (separator pixel y=39→y=40; design doc status updated to "done").

### Audit — 2026-06-12 — M-TASKBAR-ICONS (TASK-170/171)

**Triggered by**: human (post-milestone audit request)

**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage
- [x] Documentation currency

**Findings**:

1. **`taskbar-icons-001` missing from `feature_inventory.yaml`** — RED. Feature shipped without an inventory entry. Fixed this session: entry added.

2. **No automated VE tests for icon rendering** — AMBER (accepted gap). Icons are visual; no serial test path exists for `pushImage()` output. Documented in inventory as `test_ids: []` with rationale note. No action required unless a VE harness for visual regression is added in future.

3. **TASK-171 referenced in TASK-170 body but never formally filed** — AMBER. The bake-script task existed only as a cross-reference. Implemented inline without a tracked task entry. Fixed this session: TASK-171 added to `tasks.md` as done.

4. **Human review gate bypassed** — AMBER (LL-066). `tasks.md` stated "Review gate: @Architect signs off on icon set before bake script written." Agent resumed cold session and implemented past the gate on "continue" + empty-message ambiguity. User was surprised but did not reject the output. New lesson filed: LL-066. No rework needed; DUT verified.

5. **Construction artifacts committed to source** — AMBER (PM resolved). Overview build intermediates (`row_*/col_*/header_*/slot_*` PNGs) were staged. PM caught and removed before commit (24 files deleted).

6. **`golden.sha256` workflow for icon rebakes undocumented** — GREEN (noted). Adding new icons or changing existing ones requires re-running `./run/bake-icons` then `cd app/gen && sha256sum taskbar_icons.cpp taskbar_icons.h >> golden.sha256`. This is the same pattern as `bake-skin`; no new doc needed, but a comment in `run/bake-icons` would help. Low priority.

**Actions assigned**:
- LL-066 filed (agent gate-skip pattern). Open — awaiting human review for BP promotion.
- Feature inventory entry added (self, resolved).
- TASK-171 filed in tasks.md as done (PM, resolved).
- Construction artifacts cleaned before commit (PM, resolved).

**Resolution**: All RED/AMBER findings either resolved or tracked. No outstanding blockers.

---

### Retrospective — 2026-05-31 — M-TOUCH-UX milestone (TASK-114–118)

**Triggered by**: PM request at TASK-118 partial close.

**Scope**: TASK-114 (hitbox + cooldown gate), TASK-115 (shell busy infrastructure), TASK-116 (app integration), TASK-117 (SERIAL_DEBUG deliverables), TASK-118 (VE execution). Six commits `aab35b0..afe35b6`.

**Areas checked**:
- [x] Design-to-implementation fidelity (ADR-035 vs actual code)
- [x] VE harness correctness post-gate-introduction
- [x] Doc sync state at close
- [x] LL recurrence tracking (LL-045)

**Findings**:

1. **T076/T079/T081 harness failures after `g_shellBusy` gate wired into `cmdTap`** — AMBER (harness gap, not firmware defect). Sequential-tap tests did not poll for idle between taps. New lesson filed: LL-046. Fix applied: `_poll_shell_busy(False)` before each tap in T076/T081; initial poll at T079 entry. Commit `afe35b6`.

2. **`_actionDispatched` chain over-engineered; simplified during VE** — AMBER (design gap caught under test). Direct `spotifyTask::hasPendingActions()` query replaced the two-hop flag chain. Firmware correct; design doc reflected reality only after retro. New lesson filed: LL-047.

3. **ADR-035 + M-TOUCH-UX both stale after implementation-driven simplification** — RED (LL-045 recurrence). Code changed during TASK-118 but docs lagged until afe35b6. Second incident of same root cause (LL-045 was filed earlier today for a review-driven change; this is an implementation-driven change with identical outcome). Escalation recommended: promote LL-045 + this recurrence to BP together.

4. **T-CDWN-02 rate-limit flake** — AMBER (external dependency). Yahoo Finance rate-limiting prevented fetchOkCount from incrementing during the test window. Gate behaviour confirmed (`skipped:true` returned). Re-run pending when network clear. No firmware action.

**Actions**:
- LL-046 filed (sequential-tap idle-wait). Open.
- LL-047 filed (direct query vs flag chain). Open.
- LL-045 escalation note filed. Both LL-045 and recurrence recommended for BP promotion. Awaiting human sign-off.
- T076/T079/T081 fixed in `afe35b6`. Closed.
- Doc sync (ADR-035, M-TOUCH-UX) fixed in `afe35b6`. Closed.
- T-CDWN-02 re-run and T-BUSY-04 manual remain open in TASK-118.

---

### Audit — 2026-05-29 — StockApp -99 NET ERR incident: host test + VE stress test gap

**Triggered by**: human (annoyance report — verification test did not catch issue; `test_yahoo_finance_api.py` did not highlight memory issue)

**Scope**: `app/tools/test_yahoo_finance_api.py` (T_SF_01–T_SF_07), `run_serialdbg_tests.py` T186 (StockApp rapid range-tab stress). Focused audit, not full inventory sweep.

**Areas checked**:
- [x] Budget constant in host test vs firmware source
- [x] Capacity model correctness (raw bytes vs ArduinoJson tree vs heap pressure)
- [x] Stress test coverage (queue depth vs taps fired)
- [x] Harness serial-stream concurrency assumptions

**Findings**:

1. **`test_yahoo_finance_api.py` CHART_BUDGET_B = 8192 does not match firmware — RED.**
   `fetchStockChart()` in `dataTaskStorage.cpp` uses `DynamicJsonDocument(16384)`. The test constant is half the firmware value. A payload that T_SF_06 passes can still fail on DUT.
   _Action: Developer — update `CHART_BUDGET_B` to 16384, add cross-reference comment citing `dataTaskStorage.cpp` line. File LL-040._

2. **Budget model checks raw payload bytes, not ArduinoJson capacity or peak heap pressure — RED.**
   `len(body)` is not the right operand. ArduinoJson's parsed tree requires more memory than the raw JSON. `http.getString()` additionally allocates a heap `String` before parsing; peak heap pressure = String + DynamicJsonDocument simultaneously.
   _Action: Developer — replace `http.getString()` with `http.getStream()` in `fetchStockChart()` to eliminate the double allocation. Host test — add a capacity safety factor (≥ 1.5×) to the budget check with an explanatory comment. File LL-040._

3. **T186 stress test never exercised Mo1 or Ytd ranges — AMBER.**
   dataTask queue depth is 4. 32 taps fired; only 4 fetches executed; all D1/D5. The ranges most likely to trigger heap pressure were never run under the stress condition. Test reported PASS with unknown coverage.
   _Action: VE — redesign T186 to drive one range at a time and assert on `lastChartFetch` advancing (not tap count). File LL-041._

4. **T186 took three implementation iterations due to undocumented serial stream exclusivity — AMBER.**
   Background-thread log collection and concurrent `cmd()` calls both read `dut.ser`, producing ACK loss and timeouts. The constraint (stream is not thread-safe) is not documented in the harness.
   _Action: VE — add docstring to `Dut` class noting serial stream is not thread-safe. Document fire-and-forget + drain-phase pattern as the canonical approach for async log capture. File LL-042._

**Actions assigned**:
- Developer: fix `CHART_BUDGET_B` in `test_yahoo_finance_api.py`; replace `http.getString()` with `http.getStream()` in `fetchStockChart()`
- VE: redesign T186 with fetch-counter assertion; add `Dut` thread-safety note
- PM: file tasks for above two actions

**Resolution**: pending.

---

### Audit — 2026-05-25 — M-MULTIAPP milestone retrospective (all 6 apps complete)

**Triggered by**: human (`@QM: retrospective — 6 apps are in`)

**Scope**: TASK-093 (MatrixApp), TASK-094 (LifeApp), TASK-095 (WeatherApp + CryptoApp + dataTask + ADR-029), TASK-096 (canvas fix). Also checks resolution of prior TASK-090 audit findings.

**Areas checked**:
- [x] Feature inventory completeness (matrix-001, gol-001, weather-001, crypto-001)
- [x] Test coverage per feature (4 new apps)
- [x] Cross-feature matrix (dataTask shared by weather-001 + crypto-001)
- [x] Documentation currency (tasks.md, test_plan.md, lessons_learned.md)
- [x] Prior audit finding resolution (TASK-090 audit, 2026-05-25)

**Findings**:

1. **`matrix-001`, `gol-001`, `weather-001`, `crypto-001` NOT in `feature_inventory.yaml` — RED ×4.**
   All four features are implemented (committed, DUT-verified) but unregistered. Third recurrence of this pattern (previously: LL-032 → BP-010). BP-010 governs the VE side; no enforcement on the Developer registration step.
   _Owner: Developer. Action: add entries for all four features. See LL-036._

2. **No test suites for MatrixApp, LifeApp, WeatherApp, CryptoApp — RED ×4.**
   No test_plan.md suites exist; no harness functions written. Four implemented features with `test_ids: []` (once registered). WeatherApp + CryptoApp specifically need lifecycle tests covering: `"---"` pre-fetch state, live data render, dataTask queue delivery, app-switch residue.
   _Owner: VE. Action: file VE tasks per BP-005; write suites after features are registered (finding 1 precedes this)._

3. **Cross-feature matrix missing: dataTask ↔ weather-001, dataTask ↔ crypto-001, weather-001 ↔ crypto-001 — AMBER.**
   `dataTask` is a shared FreeRTOS resource (queue + spinlock) serving both WeatherApp and CryptoApp. No cross_feature_matrix.yaml entries document this interaction. If dataTask behaviour changes (queue depth, error handling), both consumers are affected with no traceability.
   _Owner: Developer. Action: add three interaction entries to cross_feature_matrix.yaml._

4. **Prior TASK-090 audit findings — RESOLVED ✓.**
   - Finding 1 (app-interface-001 not in inventory): registered with full entry, test_ids populated.
   - Finding 2 (T_BI tests not in test_plan.md): suite `app-interface-001` added (lines 2178–2259).
   - Finding 3 (T147/T148 status dates): updated.
   - Finding 4 (intermittent tests): TASK-091 done — `[FLAKE]` category and comment blocks added.
   - Finding 5 (TASK-089 stale paths): TASK-089 done — smoke_test.sh integrated into check_build.sh.
   All five prior findings closed.

5. **LL-035 (TFT shared-state) status still `open` — AMBER.**
   ADR-027 accepted and fix committed (TASK-092). LL-035 documents the lesson but status was not updated to `reviewed`. Minor housekeeping.
   _Owner: QM. Noted — update status when human reviews._

**Actions assigned**:
- Developer: register matrix-001, gol-001, weather-001, crypto-001 in feature_inventory.yaml (finding 1)
- Developer: add three dataTask cross-feature matrix entries (finding 3)
- PM: file VE tasks for matrix-001, gol-001, weather-001, crypto-001 test coverage (finding 2)
- VE: write test suites once features registered (finding 2)

**Resolution**: findings 1–3 open; finding 4 fully resolved; finding 5 housekeeping.

---

### Audit — 2026-05-25 — TASK-090 retrospective (App Interface ABC + AppShell refactor)

**Triggered by**: human (`@QM: retrospective on TASK-090`)

**Areas checked**:
- [x] Feature inventory completeness (app-interface-001)
- [x] Test coverage per feature (T_BI_01–T_BI_04)
- [x] Documentation currency (test_plan.md, tasks.md, lessons_learned.md)
- [x] Process patterns (handoff quality, intermittent test signal)

**Findings**:

1. **`app-interface-001` not registered in `feature_inventory.yaml` — RED.**
   TASK-090 declares `feature: app-interface-001 (new)` in tasks.md. No entry exists in `feature_inventory.yaml`. This leaves the feature invisible to all downstream audit, test coverage, and cross-feature matrix checks.
   _Owner: Developer. Action: add entry for app-interface-001 to feature_inventory.yaml, referencing app-interface.md and the TASK-090 commit (163ce67)._

2. **T_BI_01–T_BI_04 not in test_plan.md — RED.**
   All four tests pass in the harness (`run_serialdbg_tests.py`) but no corresponding test plan entries exist in `docs/verification/test_plan.md`. T147 and T148 have entries (suite: multiapp-002); T_BI tests belong in the same suite or a new `app-interface-001` suite.
   _Owner: VE. Action: add T_BI_01–T_BI_04 entries to test_plan.md under suite `app-interface-001`._

3. **T147/T148 status dates stale — AMBER.**
   test_plan.md T147/T148 show `**Status**: **pass** (2026-05-24)`. Both confirmed passing again on 2026-05-25 (TASK-090h). Minor housekeeping — not blocking.
   _Owner: VE. Action: update status dates to 2026-05-25 alongside T_BI additions._

4. **Intermittent test failures (T084/T087/T091/T092) dilute regression signal — AMBER.**
   Four known intermittent tests in a 31-test suite mean P(all-green) ≈ 66% per run with zero new regressions. The TASK-090h run showed 30/31 with an intermittent failure; the receiving agent had to name-check which test failed to confirm T148 was actually fixed. See LL-034.
   _Owner: VE + Developer. Action: tag known-intermittents with comment blocks; consider `[FLAKE]` result category. File as sub-task under tooling-001 or standalone._

5. **TASK-089 (stale tool-script paths) still overdue — RED (pre-existing, not TASK-090).**
   Noted in prior audit; unchanged. Functional stale paths in `preview_vis.py`, `bake_wave.sh`, `preview_wave.py`, `bake_skin.py` remain unresolved. Not introduced by TASK-090.
   _Owner: Developer. Action: execute TASK-089 per tasks.md spec._

6. **Process positive: PM handoff note pattern worked — GREEN.**
   The `pm(TASK-090): handoff note` commit was precise, numbered, and included exact shell commands. The 090h receiving agent executed it without re-reading history. Recorded as LL-033 for potential promotion.

**Actions assigned**:
- Developer: register `app-interface-001` in `feature_inventory.yaml` (finding 1)
- VE: add T_BI_01–T_BI_04 entries to `test_plan.md`; update T147/T148 status dates (findings 2, 3)
- VE + Developer: tag known-intermittent tests; file tooling sub-task (finding 4)
- Developer: execute TASK-089 (finding 5, pre-existing)
- PM: track findings 1–4 as tasks if not already filed

**Resolution**: pending — actions assigned above; no resolved findings at time of audit.

---

### Audit — 2026-05-16 — M-VIS design update: supersession correctness (Architect R&D integration)

**Triggered by**: human (`@QM to check if this latest M-VIS supersedes previous work`)

**Scope**: The Architect updated `docs/architecture/designs/M-VIS-visualization.md` and `docs/project/tasks.md` TASK-050a/b/c on 2026-05-16 using pixel-accurate R&D measurements from `M-VIS-spectrum-analysis.md` and `M-VIS-waveform-analysis.md`. Audit checks whether the supersession is complete and correct, and whether any gaps were opened by the update.

**Areas checked**:
- [x] Supersession technical correctness (every correction verified against R&D data)
- [x] Feature inventory completeness (vis-001)
- [x] Cross-feature matrix (new interactions introduced by vis-001)
- [x] Documentation currency (tasks.md, roadmap.md, design doc consistency)
- [x] Process pattern (new LL candidate)

**Findings**:

1. **Supersession technical correctness — GREEN.** All 10 corrections verified against the R&D reports:

   | Correction | R&D evidence | Verdict |
   |---|---|---|
   | VIS_H: 13→16 (y=43..58) | Spectrum report: active area y=43..58 (16px) | ✓ correct |
   | Hit-test y bound: 43..56 → 43..58 | Follows from VIS_H=16 | ✓ correct |
   | 38 bins → 19 bars | Spectrum report: 76px / 4px unit = 19 | ✓ correct |
   | Bar: 2px wide, i*2 → 3px wide + 1px gap, i*4 step | Spectrum report: bar_width=3, gap=1, unit=4 | ✓ correct |
   | Colour: threshold green/yellow/red → VIS_ROW_COLOR[absolute_row] | Spectrum report: colour by absolute row, VISCOLOR[2..17] table | ✓ correct |
   | Peak decay: 0.008f → 1.0f/VIS_H (~0.0625f) | Spectrum report: ~50 ms/row at 60 Hz; at 20 Hz = 1 row/tick | ✓ correct |
   | Peak dot: 1px drawPixel → 3px drawFastHLine | Spectrum report: width = 3 skin px (full bar width) | ✓ correct |
   | Dedup arrays: [38] → [19] | Follows from bar count correction | ✓ correct |
   | Wave colour: TFT_GREEN → 0xFFFF (white) | Waveform report: VISCOLOR[18] = (255,255,255) | ✓ correct |
   | Wave render: single drawPixel → drawFastVLine between y[x-1] and y[x] | Waveform report: 1-px line, Winamp fills vertically between samples | ✓ correct |
   | Wave midline: originY+49 → originY+50 | Waveform report: skin y=50.2 ≈ 50; formula (VIS_H-1)/2=7; 43+7=50 | ✓ correct |

   The correction table in the design doc is well-structured and developer-actionable. The design doc is correctly marked authoritative with R&D provenance. Roadmap bar count (`38 bars → 19 bars`) is updated correctly.

2. **Feature inventory — RED. `vis-001` not registered.**
   Searching `feature_inventory.yaml`: no `vis-001` entry. TASK-050a, TASK-050b, TASK-050c all reference `vis-001 (new)` in their Feature field, but the feature was never registered. This is the same recurring gap pattern (LL-005, LL-011 — 4th consecutive feature set to be planned/implemented without a pre-implementation inventory entry). The Architect's update did not add the inventory entry either — this task falls to Developer but the gap is caught here.

3. **Cross-feature matrix — RED. No X-entries for vis-001 interactions.**
   Two structural interactions are absent from `cross_feature_matrix.yaml`:
   - **vis-001 ↔ vu-001**: `vis-001` extends `vuMeter.h` directly — VisMode enum, `nextMode()`, `tickSpectrum()`, `tickWave()`, `blitVisBackground()` all live inside the same file as the VU envelope engine. The spectrum and wave synthesis consume `lLvl`, `rLvl`, `beat`, and LFO values defined in `vu-001`'s `tick()`. Any change to the envelope parameters or the `tick()` call signature directly alters all three vis-001 renderer outputs.
   - **vis-001 ↔ m3-001**: `hitTestVis()` and the mode-cycle touch dispatch live in `winampDisplay.h` alongside all other M3 hit-tests. The vis area (y=originY+43..58) is inside the Winamp chrome region that `m3-001` owns. Any origin-offset change, tft.startWrite/endWrite restructuring, or chrome-height change in `m3-001` affects vis-001's hit-test correctness and its background-restore blits.

4. **Documentation currency — GREEN (conditioned).**
   - `roadmap.md`: updated correctly (38→19 bars, status updated). ✓
   - `tasks.md` TASK-050a/b/c: notes updated, authoritative design doc cross-referenced. ✓
   - `M-VIS-visualization.md`: R&D provenance cited, corrections table present, per-mode specs complete. ✓
   - One minor naming note: design doc uses `VIS_LEFT_Y` but `vuMeter.h` calls it `LEFT_Y`. Design doc acknowledges this with `VIS_LEFT_Y = 43 (LEFT_Y in vuMeter.h)`. Not a bug — design convention vs code convention. Developer should follow the code name.

5. **Process pattern — new LL candidate (LL-019).**
   TASK-050a/b/c were written on 2026-05-15 as implementation specs *before* R&D pixel measurements were taken (R&D reports dated 2026-05-16). The pre-R&D specs contained **5 wrong values** in TASK-050b alone (bar count, bar width/step, colour method, decay rate, peak dot width) and 3 in TASK-050c (colour, render method, midline). None of the errors were individually implausible — they were all reasonable guesses from first principles. But the aggregate error rate was high enough that the spec as written would have produced a visibly wrong result. No gate existed to prevent implementation from starting before R&D completed. LL-019 captures this as a process rule.

**Actions assigned**:

| Action | Owner | Priority |
|--------|-------|----------|
| Register `vis-001` in `feature_inventory.yaml` (before TASK-050a implementation starts) | Developer | before impl |
| Add X007 (`vis-001 ↔ vu-001`): envelope engine shared, `tick()` signature coupling | Developer | before impl |
| Add X008 (`vis-001 ↔ m3-001`): hit-test + background-restore inside m3-001's chrome region | Developer | before impl |
| Write planned T-entries for TASK-050a (vis tap-cycle), 050b (spectrum bars + peaks), 050c (wave vertical fill, colour) | VE | before impl closes |
| Capture LL-019 in `lessons_learned.md` | QM | this audit |

**Promotion candidate flagged**:
- **LL-019** (new): "Implementation specs that depend on pixel-accurate asset measurements should be explicitly marked provisional until R&D validates them, with an implementation gate." Five wrong values in a single planned spec, caught only by a post-hoc R&D report — first instance on this project, worth capturing immediately.

**Resolution**: open — LL-019 captured; inventory/matrix/VE actions assigned; no implementation has started so all gaps are preventive, not retroactive.

---

### Audit — 2026-05-15 — M-LIST close + M-LIST-v2 close (TASK-020, TASK-047a/b/c/d)

**Triggered by**: human (`@QM audit last of the M-LIST work`)

**Areas checked**:
- [x] Feature inventory completeness (features in code not in inventory)
- [x] Test coverage per feature (implemented features with no test_ids)
- [x] Cross-feature test coverage (interactions with no test_coverage)
- [x] Documentation currency (docs lagging behind code)
- [x] Inter-agent protocol adherence

**Findings**:

1. **Feature inventory — red. Three shipped features unregistered.**
   - `playlist-001` (M-LIST tier 1: `QueueSnapshot` + `getQueue()` + `drawPlaylist()`, TASK-020, done 2026-05-15) — no entry in `feature_inventory.yaml`.
   - `playlist-002` (M-LIST-v2: PLEDIT chrome skin, TASK-047a/b/c/d, done 2026-05-15) — no entry.
   - `chrome-001` (M-CHROME: shuffle/repeat, volume slider, eject, TASK-023 through TASK-046) — no entry despite being heavily implemented and DUT-verified. T070a/T070b/T074/T075 reference `chrome-001` in `test_plan.md` but the inventory has no corresponding record. This is the most significant gap — the feature has code, tests, an ADR, and tasks but zero inventory presence.
   - Same class as LL-005/LL-010/LL-011 (features ship without inventory back-fill). **Third consecutive milestone with this failure mode.**

2. **Test coverage — red. All three unregistered features have zero test IDs.**
   - `playlist-001`: no test suite. DUT verification at TASK-020 close was ad-hoc user eyeball only ("user confirmed playlist panel visible"). Not regression-able.
   - `playlist-002`: no test suite. TASK-047a/b/c/d DUT verification was ad-hoc commit notes only. The drawPlaylist() redesign, PLEDIT chrome, duration column, and total-time bottom bar have no planned or written test entries.
   - `chrome-001` shuffle/repeat (TASK-025): DUT-verified by user ("shuffle/repeat sprites visible, tap-toggle confirmed working") but no T-entry written in `test_plan.md` for either the render or the tap-toggle path. T070a/T070b/T073/T074/T075 cover the volume slider — the shuffle/repeat surface is uncovered.
   - Registered features continue to carry `test_ids: []` across the board (chronic gap noted in all prior audits; not escalating further here — already on the backlog).

3. **Cross-feature test coverage — yellow. Matrix not updated for new interactions.**
   - `playlist-001` introduces at minimum two new interactions: (a) `playlist-001 ↔ api-002` (getQueue() lib patch touches SpotifyArduino — same patch family as LOCAL_PATCHES); (b) `playlist-001 ↔ m3-001` (drawPlaylist() is inside `winampDisplay.h`). Neither in `cross_feature_matrix.yaml`.
   - `playlist-002 ↔ m2-001` (PLEDIT bake pipeline extension — new `build_pledit_atlas` function added to `bake_skin.py`). Not in matrix.
   - Existing matrix entries all retain `test_coverage`; no entries are broken — the gap is additive omission.

4. **Documentation currency — yellow. Roadmap M-LIST-v2 table stale.**
   - `roadmap.md` M-LIST-v2 sub-task table still lists TASK-047a, 047b, 047c, 047d as "planned". `tasks.md` correctly shows all four done (2026-05-15). One-line status update needed in the roadmap table.
   - `roadmap.md` M-LIST status line says "done (TASK-020 DUT-verified 2026-05-15; M-LIST-v2 PLEDIT skin in progress per ADR-018)" — correctly notes M-LIST-v2 as in-progress; but that's now fully done too. Should be updated to fully-done.
   - ADR-017 and ADR-018 currency: both accepted per tasks/roadmap; no currency issue.

5. **Inter-agent protocol — yellow.**
   - M-LIST close (TASK-020 done 2026-05-15): PM did NOT trigger QM audit after milestone close. This audit was triggered directly by the human. Same skip as the post-M5 skip (audit 2026-05-08, Finding 5 — "PM prompts QM after every feature/milestone close" was red). Third consecutive milestone without a PM→QM prompt.
   - M-LIST-v2 close (TASK-047a/b/c/d all done 2026-05-15): same — no VE test-plan write after "done" status was set. VE was not explicitly notified.
   - ADR-018 was accepted pre-implementation (noted in roadmap/tasks). Architect → PM flow was followed.
   - LL-010's "pre-commit checklist for cross-role hand-offs" remains unadopted as a best practice (human sign-off still pending from 2026-05-07). Two more instances of the same skip have occurred since it was raised.

6. **Build and bake artefacts — green (conditioned).**
   - Tasks note flash at 50.0% after TASK-020 — comfortable after TASK-035 partition expansion.
   - `golden.sha256` was regenerated after TASK-047a (notes: "Regenerate `gen/golden.sha256`; confirm `sha256sum -c golden.sha256` passes").
   - No independent verification of the regeneration was performed in this audit — QM trusts the developer's note but flags: per LL-017/LL-009 discipline, `sha256sum -c` should be confirmed by a second agent or by a CI step, not just noted in a commit message. This is a soft finding, not a red flag.

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Register `playlist-001` in `feature_inventory.yaml` (M-LIST tier 1 feature) | Developer | new |
| Register `playlist-002` in `feature_inventory.yaml` (M-LIST-v2 PLEDIT skin) | Developer | new |
| Register `chrome-001` in `feature_inventory.yaml` (M-CHROME all tiers) | Developer | new |
| Write T-suite for `playlist-001`: queue display seqno gate, keepalive re-fetch, row 0 highlight, row formatting | VE | new |
| Write T-suite for `playlist-002`: PLEDIT chrome visible, 5-row row format, duration column, total time in bottom bar | VE | new |
| Write T-entries for TASK-025 shuffle/repeat render + tap-toggle (under `chrome-001` suite in `test_plan.md`) | VE | new |
| Add `playlist-001 ↔ api-002`, `playlist-001 ↔ m3-001`, `playlist-002 ↔ m2-001` interactions to `cross_feature_matrix.yaml` | Developer | new |
| Update `roadmap.md` M-LIST-v2 sub-task table: all four TASK-047 entries to "done"; M-LIST-v2 status to "done" | PM | new |
| PM must prompt QM after every milestone close — LL-010 repeat violation (3rd instance). Escalate LL-010 promotion to human. | human | LL-010 |

**Promotion candidate flagged (for human sign-off)**:
- **LL-010** — "Pre-commit checklist for cross-role hand-offs": Three consecutive milestones (M5, M-LIST, M-LIST-v2) have repeated the PM→QM skip and the inventory/test back-fill skip. The pattern is now a structural gap, not an oversight. This is the strongest single promotion case in the queue — more concrete instances than any other LL.

**Resolution**: open — actions assigned; no implementation in this audit. Roadmap + inventory + test plan updates to be committed by respective owners. LL-010 promotion decision held for human.

---

### Audit — 2026-05-10 — TASK-041 verification surfaced upstream data-source bug (LL-013 v2)

**Triggered by**: human ("have QM audit the work and recommend next step"); follow-up after T070a/T070b execution attempted on DUT.

**Areas checked**:
- [x] Did TASK-041 verification follow the planned T070a/T070b protocol?
- [x] Was the failure mode captured in the right place (lib parser vs. data source vs. firmware)?
- [x] Were the lessons captured and the right next-step structure produced?
- [x] Is the proposed fix (ADR-015) scoped to the actual bug or is it scope creep?

**Findings**:

1. **TASK-041 implementation is structurally correct against ADR-014 Amendment 1.** Verified by inline architect re-review (commits b8f37d3..8075176). The four-commit ordering, the dedup gate, the keyframe synthesis, the snapshot-writer placement — all faithful. PASS.

2. **TASK-039's lib-side parser patch is correct as written, but patched the wrong endpoint.** The filter `device.volume_percent` and the null-guard at `SpotifyArduino.cpp:636-640` work exactly as documented. But the URL hard-coded into `getCurrentlyPlaying` (`/v1/me/player/currently-playing?additional_types=episode`) returns a response that does not include the `device` field at all — wire-captured 2026-05-10 against a working session. Spec says `CurrentlyPlayingContextObject` (which includes `device`); server returns a subset. The patch was written to the spec, not to the wire. This is the **second concrete instance** of the LL-013 spec-vs-server divergence pattern.

3. **The bug was caught by VE running T070a/T070b on the DUT, not by review.** Pre-impl review of TASK-039 + ADR-014 Amendment 1 trusted the spec. No `curl` dump of the actual response shape was captured at any review stage. Add as discipline rule: any lib-filter patch must include wire capture in its review surface (ADR or LOCAL_PATCH entry) before merge. LL-018 captures this; promotion candidate.

4. **The fix is one URL change.** ADR-015 §1: switch `SPOTIFY_CURRENTLY_PLAYING_ENDPOINT` from `/v1/me/player/currently-playing` to `/v1/me/player`. `/me/player` is a strict superset of `/me/player/currently-playing` for every field the firmware reads — verified by side-by-side wire capture. No parser change. Zero round-trip cost increase, ~150-byte payload growth. Scope discipline preserved (no rename, no `repeat_state` / `shuffle_state` surfacing, no `getPlayerDetails` refactor).

5. **Process compliance — green.** The fix path was produced through the architect → ADR → PM → VE → QM flow rather than directly committing the URL change. ADR-015 has inline multi-role review per LL-010; T073 added as a new VE gate; tasks.md updated with TASK-043 referencing the ADR; LL-018 captures the underlying pattern; this audit row records the retrospective.

6. **Diagnostic instrumentation.** The temporary `[D][chrome.diag]` Serial.printf added to `spotifyLogic.h` during the T070a/T070b session is currently uncommitted. Should be reverted as part of the TASK-043 commit (it served its purpose; leaving it in is dead-cost output every poll). Captured here as a TASK-043 sub-action.

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Implement ADR-015 §1 (URL change) | Developer | TASK-043 |
| Document patch #8 in `lib/SpotifyArduino/LOCAL_PATCHES.md` | Developer | TASK-043 |
| Revert temporary `[D][chrome.diag]` log line in `spotifyLogic.h` | Developer | TASK-043 (same commit) |
| Run T073 (host-side wire-comparison) | VE | this commit's verification gate |
| Re-run T070a / T070b on DUT post-impl | VE | TASK-043 close gate |
| Promote LL-013 + LL-009 + LL-018 to best-practice rules | human | candidate, deferred |
| Future filter-touching ADRs MUST include wire-capture evidence inline | Architect | discipline rule (ADR-015 sets the precedent) |

**Resolution**: closed (2026-05-10). TASK-043 implemented (lib URL change + LOCAL_PATCHES patch #8 + diag-log revert + T073 host-side test + 204-handler side-fix discovered during T070b). All three VE gates PASS:
- **T073** PASS — `/me/player` confirmed strict superset of `/me/player/currently-playing` for firmware-consumed fields; `device.volume_percent` present (Web Player Firefox, supports_volume=true).
- **T070a** PASS — DUT captured drawVolume transitions `pct=10 keyframe=0` → `pct=90 keyframe=4` (red max-fill bar) against host-side toggle script.
- **T070b** PASS — both directions: NONE→real (`pct=-1 keyframe=NONE` → `pct=65 keyframe=3` orange) and real→NONE (Web Player closed, 204 fired, 204-handler reset volume to -1, dedup gate fired, NONE rendered).

The 204-handler fix in `spotifyTaskStorage.cpp::doPoll` was a small implementation gap not anticipated in ADR-014 Amendment 1 §A1.2 — the original wording assumed the 204 path would naturally surface a sentinel transition, but the existing 204 handler did not bump `seq` nor reset `volumePercent`, so the dedup gate suppressed the redraw. Five lines added; no further follow-up.

LL-013 / LL-009 / LL-018 promotion remains a deferred human decision; this audit closes its scope without that step.

---

### Audit — 2026-05-09 — TASK-042 process-skip retrospective (silent BMP-decoder corruption)

**Triggered by**: user (`@AGENTS.md how much of the process was skipped`)

**Areas checked**:
- [x] Was the fix scoped through PM (tasks.md entry before edits)?
- [x] Was the bake-tool dependency change reviewed against the existing ADR?
- [x] Were VE regression tests added before close?
- [x] Were lessons-learned + audit-log entries written before commit?
- [x] Was the multi-role review pre-implement step (LL-010) honoured?

**Findings**:

1. **TASK-042 was edited and run on disk before any tracking artefact was created.** The bake_skin.py change to add a manual BI_RLE8 decoder was made directly, the bake re-ran, the user confirmed visually — all before a TASK-### was opened, before ADR-008 was reviewed, and before VE was given a chance to challenge the testability of the fix. The team-review workflow described in `AGENTS.md` was bypassed entirely. Same shape as the issue captured in LL-016 (mono/stereo swap done solo without looking at the asset first); different surface (tooling, not chrome) but same root cause: solo-agent fast path skipped team checks.

2. **ADR-008 decision #8 was factually wrong from the day it was written, and not detected for two days.** It said: "Pillow's BI_RLE8 BMP decoder fails on Winamp's `TEXT.BMP` (raises `ValueError`). Tool falls back to `magick`." The "raises" framing implicitly modelled PIL as binary-success-or-error. Decision #8 didn't ask the question "how do we know PIL's output is *correct*, not just non-erroring?" — and so the silent-corruption mode for BALANCE.BMP shipped undetected through the M-CHROME tier 2 work. ADR-008 Amendment 1 corrects this; LL-017 captures the general principle.

3. **The existing T025 determinism check kept passing on garbage.** Byte-identical bake-to-bake is a necessary condition for correctness, but not sufficient. The PIL-broken decode was deterministically wrong: every bake produced the same wrong bytes, golden hash matched, and the test gate stayed green. Determinism without a separate ground-truth check is just stable-corruption. T071 + T072 (added 2026-05-09) plug the gap by validating against a second decoder (ffmpeg) and asserting positive content (green pixels in the balance bar).

4. **Magick fallback was load-bearing in name only.** ADR-008 listed magick as a hard dep on the bake step. For BALANCE.BMP, magick rejected the file outright with `unable to runlength decode`. The fallback never triggered because PIL never raised. So neither path actually decoded the file correctly until the manual decoder went in. The dependency was paying for the wrong failure mode.

5. **Build artefacts — green** on the fix. `python3 tools/bake_skin.py -i ../skins/base-2.91.wsz -o ../SpotifyDiyThing/gen` runs clean; per-element `gen/composite/balance_bar_frame0.png` now contains the canonical Winamp green slider track (rows y=3-7), confirmed via per-row pixel summary against ffmpeg's decode (byte-identical).

6. **Stale `gen/golden.sha256`.** SKIN_MAIN_BG[] bytes changed (correct content now). T025 will fail until VE regenerates the golden. Not regenerated yet — pending visual sign-off from user that the new bake is correct (open `gen/skin_preview.png` + `gen/composite/balance_bar_frame0.png`).

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Open TASK-042 in tasks.md | PM | this commit |
| Amend ADR-008 (decision #8 superseded) | Architect | this commit |
| Add T071 (manual decoder vs ffmpeg) + T072 (positive-content green-pixel assertion) to test_plan.md | VE | this commit |
| Mark T028 superseded (magick-fallback test no longer load-bearing) | VE | this commit |
| Regenerate `SpotifyDiyThing/gen/golden.sha256` after user visual sign-off | VE | this commit |
| Add LL-017 to lessons_learned.md | QM | this commit |
| Promote LL-017 once a second project sees the same class of bug | human | candidate, deferred |
| Future ADRs touching data-pipeline libs MUST answer "how do we know the library produced *correct* output?" | Architect | discipline rule |

**Resolution**: closed (2026-05-10). User visually confirmed the new bake (green balance bar visible in `gen/composite/balance_bar_frame0.png`). `gen/golden.sha256` regenerated; `sha256sum -c golden.sha256` passes both files. Determinism re-verified by a second bake → identical hashes. Process artefacts committed: PM (TASK-042 in tasks.md), Architect (ADR-008 Amendment 1), VE (T028 superseded; T071 + T072 added; golden regen), QM (LL-017 + this audit row). Future ADRs touching data-pipeline libs are expected to answer the *"how do we know the library produced correct output?"* question — discipline rule, no specific ticket.

---

### Audit — 2026-04-28 — Session-end self-audit (ADR-006 + M0 close + M1 spike + time-001)

**Triggered by**: human ("do retrospective, what went well, what could be done better")

**Areas checked**:
- [x] Feature inventory completeness (features in code not in inventory)
- [x] Test coverage per feature (implemented features with no test_ids)
- [x] Cross-feature test coverage (interactions with no test_coverage)
- [x] Documentation currency (docs lagging behind code)
- [x] Secret-hygiene posture
- [x] Build artefacts in sync with source (both PlatformIO envs)

**Findings**:

1. **Inventory completeness — minor gap.** All in-tree features have entries: `deploy-001`, `auth-001`, `cfg-001`, `wifi-001`, `poll-001`, `disp-001`, `touch-001`, `nfc-001`, `time-001`, `api-001`. Spike code (`spikeMode.h`, `spikeRawHttp.h`) is registered under `api-001`. No orphaned feature folders or files.

2. **Test coverage — substantial gap on baseline features.** Of nine baseline features (`deploy-001` through `nfc-001`), **zero have test_ids**. Test plan only covers `api-001` (T001-T018) and `time-001` (T019, T020). VE backlog: at minimum a smoke test per baseline feature. Acceptable for a project that came in with a working firmware (verification was implicit "it works on the dev unit") but should be flagged.

3. **Cross-feature test coverage — adequate for what's recorded.** Two interactions (`X001`, `X002`) both have `test_coverage` populated (T020 and T016/T017/T018 respectively). No matrix entries lack test linkage.

4. **Documentation currency — green.** Architecture (ADR-006), inventory, matrix, tasks, roadmap, test plan all updated this session. ADR-003 was promoted from proposed to accepted; ADR-002 trimmed. ADRs 001/004/005 marked superseded.

5. **Secret hygiene — yellow.**
   - `.gitignore` correctly excludes `data/spotify_diy_config.json`. Verified with `git check-ignore`.
   - `data/spotify_diy_config.example.json` template committed.
   - **However**: leaked refresh-token-and-secret pair was carried forward through this entire session in `data/spotify_diy_config.json` and dumped to serial logs on every TLS retry due to `SPOTIFY_DEBUG` being on in the vendored library. Spotify auto-revoked. Rotation (TASK-006) deferred pending user account access. See `lessons_learned.md` LL-002 and LL-003.

6. **Build artefacts in sync — green.** `cyd2usb` and `cyd2usb_spike` envs both build clean post-`time-001`. Flash usage 86.9% on `cyd2usb_spike`; comfortable headroom for now, must re-verify after M3 (skin atlas).

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Add baseline-feature smoke tests to `test_plan.md` (Finding 2) | VE | not yet ticketed; flag PM at next planning |
| Disable `SPOTIFY_DEBUG` or redact secret-bearing log lines in vendored lib | Developer | fold into TASK-006 procedure (run after rotation) |
| Resume TASK-006 rotation when user account access restored | Developer | TASK-006 already exists, status `pending` |
| Human review of LL-001..LL-007; promote candidates to `best_practices.md` | QM ↔ human | tracked in `lessons_learned.md` Best-practice candidates section |

**Resolution**: open — actions remain pending. Audit re-runs on next milestone close (M1 exit when TASK-006 + spike run complete).

---

### Audit — 2026-05-07 — Process self-audit triggered by user "@PM how much of the process was followed"

**Triggered by**: human (direct-invoke `@PM`)

**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage (matrix)
- [x] Documentation currency
- [x] Inter-agent protocol adherence (per AGENTS.md)
- [x] Build artefacts in sync

**Findings**:

1. **Feature inventory — yellow.** Three new features shipped without inventory entries: `poll-002` (M4, Spotify-Diy-Thing@f84b112), `m2-001` (M2 tier 1, @a9682be), `dev-001` (network shims, @bf5d5ca). Back-filled this session.

2. **Test coverage — yellow.** New features had zero test entries before this audit. Back-filled T021–T031 across three new suites (poll-002, m2-001, dev-001). Most entries are `passing` or `planned-deferred`; deterministic regression for the bake tool (T025 byte-identical re-bake) is `planned` — needs a checked-in golden hash.

3. **Cross-feature matrix — green.** No new cross-feature interactions beyond the existing `poll-001 ↔ disp-001` link, which `poll-002` and `disp-001` extend rather than introduce. Matrix unchanged.

4. **Documentation currency — yellow → green after this audit.**
   - ADR for the bake tool's implementation choices was missing — back-filled as ADR-008.
   - Roadmap M2 status updated (in_progress, tier 1 done) and M4 (done) on 2026-05-07.
   - Tasks file: TASK-011 moved to Completed; TASK-012, TASK-013 added.

5. **Inter-agent protocol — red.** Substantial gaps caught by the user's `@PM` query, captured as LL-010 and LL-011:
   - No Architect consult before bake-tool implementation (ADR-003 deferred items decided without ADR).
   - No VE testability challenge before either M4 or M2 tier 1 finalized.
   - No QM prompt after TASK-011 (M4) closed.
   - Dev-001 (cellular/captive-portal infra) shipped with no PM tracking at all.
   - Best-practices file (`docs/quality/best_practices.md`) not consulted this session.

6. **Build artefacts — green.** `cyd2usb` env builds clean post-M4 and post-M2 tier 1. Album art temporarily disabled via `DISABLE_ALBUM_ART` define in `.ino` — orthogonal i.scdn.co fetch hang, tracked separately (no task ID yet — VE follow-up to register).

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Commit checked-in golden hash for bake tool output (T025) | VE | not yet ticketed; flag PM at next planning |
| Register the album-art fetch hang as a task | PM | not yet ticketed |
| Pre-commit checklist for cross-role hand-offs (LL-010) | human review | LL candidate, awaiting promotion |
| Tasks-file entry rule for any new sketch/tools file (LL-011) | human review | LL candidate, awaiting promotion |
| Read `best_practices.md` at session start as standing practice | Developer | discipline change, no ticket |

**Resolution**: open — back-fill complete (this commit), follow-up actions remain pending.

---

### Audit — 2026-05-08 — Process self-audit (TASK-009 close, M-LOG/2, M-IO, M5)

**Triggered by**: human (`@docs/agents/AGENTS.md how much of the process did we skip?`)

**Scope**: everything between the 2026-05-07 audit and now — TASK-016 a/b/c/d/e/f (M-LOG tier 1), TASK-018 (M-LOG2), TASK-019 tier 1 (M-IO, ADR-011), TASK-009 close-out (3 lib patches beyond ADR-007), M5 (touch-002) close, skin source swap.

**Process scorecard (per AGENTS.md inter-agent protocol)**:

| Protocol rule | Followed? | Notes |
|---|---|---|
| Developer notifies VE when feature `implemented` | ✗ | Six features shipped (log-001, log-002, io-001, touch-002, plus the api-002 lib patches and the bake-tool tier 3 sprites earlier) without explicit VE handoff. VE got pulled in once via the ADR-010 mini-review; that's it. |
| VE challenges Developer on testability before finalised | partial | ADR-010 review did this — caught the build-time `CORE_DEBUG_LEVEL` gate retroactively, not before. Every other ship cycle skipped this entirely. |
| Architect reviews R&D proposals before PM schedules | n/a | No R&D this session. |
| Developer consults Architect before cross-component changes | ✗ | The TASK-009 close-out (3 lib patches in the request-construction path) and M5 (touch-002 reaching into spotifyLogic's `songStartMillis` for optimistic-UI freeze) were both cross-component. Neither paused for an Architect ping. |
| VE challenges Architect on testability of interfaces | ✗ | ADR-011 (M-IO tier 1) shipped with "mini multi-role review folded into the ADR itself for speed". Self-conducted. T046–T049 were named but never written into `test_plan.md`. |
| PM prompts QM after every feature/milestone close | ✗ | M5 was closed (commit `b37b66a`) with no QM prompt. This audit is the manual user catch. |
| QM brings best-practice candidates to human | partial | LL-010 was flagged for promotion; never resolved. Multiple new LL candidates surfaced this session and weren't captured (see Findings 4 below). |

**Findings**:

1. **Feature inventory — red.** Four shipped features missing from `feature_inventory.yaml`: `log-001` (M-LOG tier 1), `log-002` (on-screen overlay), `io-001` (M-IO tier 1), `touch-002` (M5). All four were referenced by ADRs, tasks, and commit messages — but never registered. Same class of skip as LL-005/LL-011 (cross-feature matrix, dev-infra not tracked).

2. **Test plan — red.** Three planned test suites never landed:
   - T036–T040 (M-LOG tier 1) — named in `ADR-010-review.md`, never written.
   - T046–T049 (M-IO tier 1) — named in ADR-011, never written.
   - T0xx (M5 / touch-002) — never named, never written.
   The visual confirmations during this session were ad-hoc DUT eyeball checks recorded in commit messages — not in the test plan, not regression-able.

3. **ADR review gating — red.** The very thing LL-010 was raised for. ADR-010 reached `accepted` ahead of multi-role review and was amended *four times* retroactively as findings emerged from implementation (build-time level gate, exact-tag matching, log_e/log_w bypass, ESP_LOGx blast radius). ADR-011 took a "mini multi-role review folded into the ADR itself for speed" shortcut and shipped without a real VE/Developer pass. ADR-007 was assumed to fully fix non-GET TLS — turned out three more structural lib bugs were stacked on the same numeric error (covered by the new LL-013 below).

4. **Lessons captured — red.** At least four LL-worthy findings from this session went uncaptured before this audit:
   - "WiFiClientSecure::lastError() returns last *result* not last *error* — sticky stale success fd." (`fd=49` mistaken for an error code, sent us down a dead-end "rc=49 unknown" path for two reflashes.)
   - "Arduino-ESP32 redefines ESP_LOGx to its own log_x macros that bypass esp_log_writev." (Caused the screenlog overlay to render an empty ringbuffer for several reflash cycles before being diagnosed.)
   - "Same numeric error code can mask multiple independent root causes." (mbedtls 0x0050 NET_CONN_RESET appeared in three distinct lib bugs; ADR-007 was assumed to fix all instances of it.)
   - "When the SDK spec says 204 No Content but the server returns 200, the server wins." (Lib's `return statusCode == 204` made every successful PUT/POST look like a failure.)

5. **Network-blame antipattern.** When the spike harness retest failed all 15 rows, my first hypothesis was "Marriott captive portal blocks non-GET methods over HTTPS". User pushed back. AP-level method filtering of HTTPS is implausible without TLS MITM, and we had no MITM evidence — the hypothesis was lazy. The actual cause was three structural lib bugs (caught by spec cross-check and request-byte tracing). LL-014 below.

6. **Build artefacts — green.** Both `cyd2usb` and `cyd2usb_winamp` and `cyd2usb_winamp_screenlog` and `cyd2usb_spike` envs build clean. Flash 88.8 % / 97.8 % / 97.8 % / 90.4 % respectively.

7. **Heartbeat / observability — green.** TASK-016d's `block_max_ms` field is now in every heartbeat; the `/log` endpoint exists (HTTP-test deferred until a non-AP-isolated network); on-screen overlay populated and DUT-verified.

**Actions assigned**:

| Action | Owner | Tracked as |
|--------|-------|------------|
| Register `log-001`, `log-002`, `io-001`, `touch-002` in `feature_inventory.yaml` | Developer | this commit |
| Write T036–T040 (M-LOG), T046–T049 (M-IO), T050+ (M5) into `test_plan.md` | VE | this commit |
| Add LL-012 / LL-013 / LL-014 / LL-015 to `lessons_learned.md` | QM | this commit |
| Promote LL-010 (multi-role review pre-`accepted`) — already a candidate; user-decision pending | human | already pending |
| Re-run multi-role review on ADR-011 properly (currently "self-conducted") | Architect ↔ VE | not yet ticketed |
| Fold TASK-009 close-out lib patches back into ADR-007 as amendments (or ADR-007-review.md) | Architect | not yet ticketed |
| Prompt QM at the next milestone close (any of M6, M7) — habit fix | PM | discipline |

**Resolution**: open — back-fill ships in this commit; ADR-011 review and ADR-007 amendment remain pending.

---

## Entry Format

```
### Audit — 2026-05-22 — TASK-021/TASK-066/TASK-067 retrospective (tap-to-play bug lifecycle)

**Triggered by**: PM (post-feature, per AGENTS.md protocol)

**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage
- [x] Documentation currency

**Findings**:
1. `playlist-001` carried `test_ids: []` from 2026-05-15 to 2026-05-22 (7 days). No VE task was filed at feature close to track this gap. (LL-024)
2. TASK-021 was closed `done` with a documented functional regression (queue cleared on tap). No separate bug task was filed; the bug returned to the user 6 days later. The fix was 5 lines. (LL-022)
3. `injectTouch()` in `winampDisplay.h` lacked the PLEDIT row-tap branch for 7 days after TASK-021 shipped. Physical path and injection path diverged silently; VE harness hit DEADZONE instead of PLEDIT until T115 ran. (LL-023)

**Actions assigned**:
- Developer: add co-location comment to `checkForInput()` and `injectTouch()` enforcing the mirror invariant (LL-023 immediate action — low cost, structural risk mitigation). Filed as low-priority standalone; no new task needed if done at next code touch.
- PM: at next feature close, verify `test_ids` is non-empty OR a VE task is in `tasks.md` before marking done (LL-024 process gate).
- PM/Developer: at next task close with a known regression, file a separate bug task rather than prose-only caveat (LL-022 process gate).

**Resolution**: LL-022, LL-023, LL-024 filed in `lessons_learned.md`. Added as best-practice candidates pending human sign-off. `playlist-001.test_ids` now `[T115, T116]`; TASK-067 closed.

---

### Audit — 2026-05-23 — TASK-077: scrollbar thumb position bug — design/implementation/validation chain

**Triggered by**: human (validate TASK-077 claims; audit design → impl → VE chain for scrollbar thumb)

**Scope**: TASK-051e (thumb blit impl), TASK-075 (R&D measurement), TASK-077 (bug report), T120 (VE test case), `winampDisplay.h`, `gen/skin_layout.h`, `docs/rnd/resources/winamp-skin-format/PLEDIT-BMP-spec.md`.

**Areas checked**:
- [x] Formula correctness — code vs spec vs first principles
- [x] Design → implementation traceability (R&D → spec → code)
- [x] VE exit-criterion execution (T120 status)
- [x] Bug root-cause substantiation in TASK-077
- [x] Serial-debug readiness for verification

---

**Findings**:

**1. Formula: code matches spec — GREEN (with one unverified premise)**

Code in `winampDisplay.h` (both `drawPlaylist()` line 1035 and `drawScrollThumbOnly()` line 964):

```cpp
constexpr int track_h = PLEDIT_ROW_COUNT * PLEDIT_ROW_H;   // 5 × 13 = 65 px
constexpr int travel  = track_h - SKIN_PLEDIT_THUMB_H;      // 65 − 17 = 48 px
const int denom  = max(1, (int)count - PLEDIT_ROW_COUNT);
const int thumb_y = PLEDIT_ROWS_Y + scrollOffset * travel / denom;
```

`PLEDIT-BMP-spec.md §"Scrollbar thumb"` states the identical formula: `PLEDIT_ROWS_Y + scrollOffset × (track_h − thumb_h) / max(1, count − PLEDIT_ROW_COUNT)` where `track_h = 65px`, `thumb_h = 17`. The code is a verbatim translation.

Mathematical correctness confirmed: at `scrollOffset=0`, thumb top = PLEDIT_ROWS_Y (136). At `scrollOffset=maxOffset`, thumb top = 136 + 48 = 184; thumb bottom = 184 + 17 − 1 = 200. The track bottom (inclusive) = PLEDIT_BOTTOM_Y − 1 = 200. Thumb bottom aligns with track bottom at max scroll. ✓

**One unverified premise**: both code and spec assume the scrollbar track starts at exactly `PLEDIT_ROWS_Y` (136). This is derived as `PLEDIT_Y + PLEDIT_TITLE_H = 116 + 20 = 136`. The right-side tile (`SKIN_PLEDIT_RIGHT_SIDE`) is drawn from `PLEDIT_ROWS_Y`, but BMP row y=42 (the tile's first pixel row) may contain a 1-pixel visual separator before the track body. No R&D measurement has been taken of this. If the effective track starts at y=137, the formula's base offset is 1px high.

**2. VE gate T120 never executed — RED (process miss)**

`docs/verification/test_plan.md` T120 status: `planned`. T120 requires TASK-051e to be applied (explicitly listed in preconditions) and tests thumb movement through the full `scrollOffset` range (0 → mid → max), not just at zero. The task was never executed before TASK-051e was closed.

TASK-051e was closed "done (2026-05-23, commit 3b49719) — human sign-off: thumb visible at correct position." A human visual check at `scrollOffset = 0` (thumb at top) was accepted as sufficient. This is not equivalent to T120. Thumb-at-top is consistent with both a correct and a wrong formula; the formula only shows an error at `scrollOffset > 0`.

**3. `get scrollOffset` serial command not implemented — blocking T120 and T136–T140**

`WinampDisplay::dbgGet` (`winampDisplay.h:840`) handles `cooldown`, `dragState`, `optimisticVolume`, `songDuration`. `scrollOffset` is absent. T136–T140 (TASK-076) and partial T120 verification all require this key. TASK-076 notes list it as a prerequisite ("Tests T136–T140 require `scrollOffset` to be exposed via `dbgGet` — add to `winampDisplay.h::dbgGet`") but it was not implemented before those tasks were closed as "done (TASK-076: DUT confirmed scrolling after TASK-076 fix)".

**4. TASK-077 bug symptom lacks captured evidence — YELLOW**

TASK-077 ("BUG: scrollbar thumb position wrong") was filed 2026-05-23. It contains no captured serial log, no measured screen coordinates, no screenshot. The notes say only "verify against PLEDIT.BMP spec... check PLEDIT_ROWS_Y offset and whether travel denominator is correct." As shown in Finding 1, the denominator is correct per the spec. The observation of "incorrect Y position" has not been formally substantiated with a T120 run or any DUT measurement.

Possible alternative explanations for the DUT observation that have not been ruled out:
- Thumb X misalignment perceived as Y error: thumb blit at `rightX + 1 = 279` is 4px left of the right-side tile's visual centre (287.5). The 9px thumb occupies the left half of the 19px track tile.
- Transparency key false-positive: `PLEDIT_TRANSPARENT_RGB565 = 0x063F`. If any non-transparent thumb pixel happens to be that colour, it would render as a hole, distorting perceived position.
- Single-state sign-off accepted at scrollOffset=0; first DUT scroll moved the thumb to a position that looked proportionally wrong (possibly due to integer truncation artefacts at low count values).

None of these are confirmed. Root cause is undiagnosed.

**5. TASK-051e had no explicit VE exit criterion — process miss (repeated pattern)**

TASK-051e notes do not list T120 as a required gate. T120 was planned in `test_plan.md` but the connection from task → test was never wired. This matches the LL-024 pattern ("'VE: no test suite written' prose notes are not actionable without a task") but in the opposite direction: the test existed but was not linked as a blocking exit criterion.

**Actions assigned**:

| # | Owner | Action |
|---|-------|--------|
| 1 | Developer | Add `get scrollOffset` to `WinampDisplay::dbgGet` (`winampDisplay.h:868` else branch). No new task needed — low-risk, ~5 LOC, resolves T136–T140 and T120 blockers simultaneously. |
| 2 | VE | Execute T120 on DUT with TASK-051e firmware once `get scrollOffset` is available. Step through scrollOffset 0 → mid → max, record thumb y-coordinate vs expected. Required before TASK-077 can be closed. |
| 3 | R&D or Developer | Measure whether BMP y=42 (right-side tile first row) is a 1-px visual separator. If yes, patch `PLEDIT_ROWS_Y + 1` as the thumb base offset and update `PLEDIT-BMP-spec.md`. |
| 4 | PM | Link T120 as the explicit exit criterion in TASK-077 notes. Update TASK-077 status to `blocked` (by `get scrollOffset` impl) rather than open with no dependency. |
| 5 | PM | File LL-025 candidate for human sign-off (see `lessons_learned.md`). |

**Correction (2026-05-23 — post-audit human clarification)**:
TASK-077 was misfiled. The original user observation was "slider needs to move a bit to the right" — an X-axis concern. The PM agent incorrectly recorded it as a Y-position bug. The QM audit above checked the Y formula (which is correct per spec) and identified the X misalignment in Finding 5 as an alternative explanation. The human clarification confirms Finding 5 was the actual defect.

Fix applied to `winampDisplay.h`:
- `drawScrollThumbOnly()` line 965: `rightX + 1` → `rightX + (PLEDIT_SIDE_RIGHT_W - SKIN_PLEDIT_THUMB_W) / 2` (= rightX + 5)
- `drawPlaylist()` line 1034: `+ 1` → `+ (PLEDIT_SIDE_RIGHT_W - SKIN_PLEDIT_THUMB_W) / 2`

This centres the 9px thumb within the 19px right-side tile. TASK-077 status updated to `done`.

**Residual action**: T120 still unexecuted. VE should run T120 to confirm corrected render across scroll range. `get scrollOffset` still missing from `dbgGet`.

**New LL candidate from this episode** (added to LL-025 scope): PM misfiling of user-reported visual bugs. The user said "X" (right/left), the agent recorded "Y" (up/down). Symptom transcription error. Mitigation: PM should quote the user's exact wording in the Symptom field, not paraphrase into a coordinate.

---

### Audit — 2026-05-24 — M-RESTRUCTURE milestone retrospective (TASK-083)
**Triggered by**: human (post-milestone)
**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature (audit_origin.py T141–T146)
- [x] Cross-feature impact (originX shift vs all draw-call coordinates)
- [x] Documentation currency (CLAUDE.md, upstream-patches.md, tasks.md, roadmap.md)

**Findings**:

1. **[POSITIVE] Gate discipline held throughout all 5 steps.** `check_build.sh` was run and passed after every step before proceeding. `audit_origin.py --grep-only` (T141) was run as the step-4 gate. Full T141–T146 suite ran as the step-5 gate. BP-008 was followed without exception. No step produced a broken intermediate state.

2. **[POSITIVE] Parallel-agent handoff succeeded cleanly.** TASK-080 and TASK-082 were completed by a parallel agent and landed as uncommitted working-tree changes. The main agent integrated them (committed as part of 709027b) without conflict or rework. The blocking relationship between step-5 and TASK-080/082 was correctly enforced.

3. **[ISSUE — process] `.gitignore` missing before first `git add app/`.** The `app/.gitignore` did not exist when `git add app/` was first run. This caused `.pio/` (embedded git repos — Seeed_Arduino_NFC) to be staged. The error was caught before commit and corrected by writing `.gitignore` and re-staging, but the recovery required manual `git rm --cached` on the embedded git repos. Had it not been caught, `.pio/` would have been committed.

4. **[ISSUE — spec gap] Step-5 file attribution in TASK-083 was wrong.** The task spec stated the originX change was "in `app/src/main.cpp`". The actual location is `app/src/winamp/winampDisplay.h` (line 49, `displaySetup()`). The spec was written before full implementation — a reasonable planning shortcut — but the discrepancy meant the step-5 description could not be followed literally. No rework resulted (the correct location was identified immediately by grep), but spec accuracy matters for agent hand-offs.

5. **[OBSERVATION] `app/.gitignore` was subsequently amended by external tooling** (linter added `gen/origin_audit.png`). The file was therefore under-specified at commit time. Not a defect — the gitignore is correct now — but suggests the initial `.gitignore` was drafted from the Spotify-Diy-Thing precedent rather than a full audit of what `app/` would generate.

6. **[POSITIVE] Upstream revert verified against pinned ref.** `Spotify-Diy-Thing/SpotifyDiyThing/SpotifyDiyThing.ino` and `platformio.ini` were both reverted to `6eb95ffd` (upstream origin/main as of 2026-05-24). The ref was recorded in `upstream-patches.md`. PATCH-001 (`cheapYellowLCD.h`) was preserved correctly — it is tracked in the patch registry and not in the revert scope.

7. **[OBSERVATION] DUT smoke test is manual-only; no automated regression.** The step-4 and step-5 DUT smoke tests (Spotify polling live, chrome renders, NEXT/PREV works, no crash on track change) have no automated harness. Confirmation was by serial log capture only. For a structural refactor with "no firmware behaviour change" as a stated goal, this is the expected level — but VE should note that T102 (queue content integration) was last run under HTTP/1.0 pre-INV-A Step 3, and a post-restructure re-run has not been scheduled.

**Actions assigned**:
- Developer: when adding a new generated-output path to `app/`, audit `app/.gitignore` first — confirm the generated files are excluded before the first `git add`. (Finding 3 prevention.)
- Architect/PM: spec for a step that changes a specific line must name the file accurately. If the file is uncertain at spec-write time, mark `[FILE TBD — confirm at implementation]` rather than guessing. (Finding 4.)
- VE: schedule T102 re-run against restructured firmware. Unblocked now that M-RESTRUCTURE is complete.

**Resolution**: Findings 1, 2, 6 are positive — no action. Finding 3 → LL-027. Finding 4 → LL-028. Finding 5 resolved by external tooling. Finding 7 → VE action assigned.

---

### Audit — 2026-05-24 — M-RESTRUCTURE tool-script path staleness (post-T102 crash)

**Triggered by**: human (T102 re-run crash; further investigation requested)

**Scope**: Tool scripts in `app/tools/` that were moved from `Spotify-Diy-Thing/tools/` during M-RESTRUCTURE (TASK-083). Audit checks whether internal path strings were updated to reflect the new directory layout. Specifically: all `pathlib.Path`, shell `-o`, argparse `default=`, and docstring/help references to `SpotifyDiyThing/gen/` or `../SpotifyDiyThing/gen/`.

**Areas checked**:
- [x] Functional path references (runtime-breaking if wrong): `pathlib.Path`, shell `-o`, argparse `default=` with no user override
- [x] Documentation/help path references (misleading but not runtime-breaking): docstrings, argparse `help=` strings
- [x] Whether the existing restructure gate (`check_build.sh` / BP-008) covers this class of break
- [x] Root cause and process gap

**Findings**:

1. **Functional stale paths — RED. Six instances across four scripts.**

   | File | Line(s) | Stale string | Correct string |
   |------|---------|--------------|----------------|
   | `app/tools/preview_vis.py` | 65 | `"../SpotifyDiyThing/gen/skin_layout.h"` | `"../gen/skin_layout.h"` |
   | `app/tools/bake_wave.sh` | 19 | `"$SCRIPT_DIR/../SpotifyDiyThing/gen"` | `"$SCRIPT_DIR/../gen"` |
   | `app/tools/preview_vis.py` | 340 | `default="SpotifyDiyThing/gen/skin_preview_animated.gif"` | `default="../gen/skin_preview_animated.gif"` |
   | `app/tools/preview_wave.py` | 128 | `default="SpotifyDiyThing/gen/skin_preview_wave.gif"` | `default="../gen/skin_preview_wave.gif"` |
   | `app/tools/preview_wave.py` | 129 | `help="... SpotifyDiyThing/gen/skin_preview_wave.gif"` | update to match new default |
   | `app/tools/bake_skin.py` | 773 | `path="SpotifyDiyThing/gen/shell_layout.h"` | `path="../gen/shell_layout.h"` (or relative via `Path(__file__)`) |

   Note: `app/tools/coords.py:9` was already correct (`"../gen/skin_layout.h"`) at the time of this audit — it was fixed during TASK-083 step 2. It is recorded here as the original T102 trigger for traceability.

2. **Docstring / help text stale paths — YELLOW. Eight instances across four scripts.**

   | File | Line(s) | Nature |
   |------|---------|--------|
   | `app/tools/bake_skin.py` | 8–9 | Module docstring usage examples reference `../SpotifyDiyThing/gen` |
   | `app/tools/bake_vis.py` | 7–8 | Module docstring usage examples reference `../SpotifyDiyThing/gen` |
   | `app/tools/bake_wave.py` | 6–7 | Module docstring usage examples reference `SpotifyDiyThing/gen` |
   | `app/tools/preview_vis.py` | 20–22, 26–27, 32, 37–38 | Docstring multi-mode examples reference `SpotifyDiyThing/gen/` |

   These do not cause crashes but will mislead any developer following the usage examples. Low priority relative to the functional fixes; should be caught in the same pass.

3. **Gate coverage — RED. `check_build.sh` / BP-008 does not cover tool-script path correctness.**
   The build gate compiles PlatformIO firmware and checks `golden.sha256`. It has no visibility into Python module import success or shell script path resolution. The TASK-083 restructure checklist did not include a "run tool scripts from their new location" step. There is currently no `tools/smoke_test.sh` or equivalent. The first consumer of the stale paths (T102 via `coords.py`, now fixed) was the one that surfaced the breakage.

4. **Process gap — LL-029 candidate.** The root cause is that "move files" was treated as sufficient for migration. Path strings inside scripts are structural coupling to the old directory layout — equivalent to a broken `#include` — and require an explicit update step. No restructure checklist item covered "grep moved scripts for old path strings." See LL-029 for the full lesson and suggested improvements.

**Actions assigned**:

| # | Owner | Action | Priority |
|---|-------|--------|----------|
| 1 | Developer | Fix six functional stale paths (table in Finding 1) in `preview_vis.py`, `bake_wave.sh`, `preview_wave.py`, `bake_skin.py` | HIGH — file as TASK-NNN |
| 2 | Developer | Update eight docstring/help stale paths (Finding 2) in same pass | MEDIUM — same task |
| 3 | Developer | Add `tools/smoke_test.sh` (or equivalent gate in `check_build.sh`) that imports each Python module and runs each shell script with `--help` | MEDIUM — file as TASK-NNN or fold into fix task |
| 4 | PM | File a task for Finding 1+2+3 above; assign Developer; status `planned` | before next tool-script use |
| 5 | QM | Capture LL-029 in `lessons_learned.md` | this audit (done) |
| 6 | Human | Review LL-029 for BP promotion | deferred — human sign-off required |

**Promotion candidate flagged**:
- **LL-029** (new): "Structural refactors must include a grep-for-old-paths step on moved files, plus a tool-script smoke-test gate before close." First concrete instance; preventive class applies to any future milestone involving file moves.

**Resolution**: open — LL-029 captured; fix task not yet filed (pending PM action). Functional stale paths remain in six locations across four files as of 2026-05-24.

---

### Audit — 2026-05-24 — TASK-087 salvage + project quality health check

**Triggered by**: human ("quality is absolutely a mess — audit the work and come up with a plan to salvage")

**Scope**: TASK-087 (M-MULTIAPP step 2) post-implementation review. Two defects found, one resolved, one deferred. Cascading test failures from stale T088 expectations. Rolling backlog of open findings from prior audits reviewed. Strategic observation on project health trajectory requested.

**Areas checked**:
- [x] TASK-087 implementation vs spec (app-lifecycle.md, taskbar.md)
- [x] Firmware correctness: input routing for non-Spotify apps
- [x] Test harness currency: T088 expected values vs new taskbar feature
- [x] Open actions from prior audits (LL-029, stale tool paths)
- [x] "Done" criterion discipline
- [x] Project quality trajectory across milestones M3–M-MULTIAPP

**Findings**:

1. **BUG-1 — RESOLVED.** `checkForInput()` and `injectTouch()` ran all Winamp hit-tests unconditionally regardless of which app was active. Clock canvas taps could enqueue Spotify actions (skip, pause, seek). Fixed: 4-line guard in each path (`currentAppId != AppId::Spotify → return early`). T148 confirms. **No regression: 15/15 tests pass.**

2. **BUG-2 — DEFERRED (TASK-088).** `switchApp()` missing `saveAppState()`/`restoreAppState()`. Design-spec gap; works by accident for Spotify↔Clock because `WinampDisplay` class members survive the round-trip. Risk materialises at M-MULTIAPP step 5 when Matrix/GoL/Weather/Crypto apps need their own state round-trips. Filed as TASK-088 (open, blocking step 5).

3. **T088 stale expectations — FIXED.** T088 tested corner coords (319,0), (319,239), and (276,58) as DEADZONE. These are now inside the taskbar strip. `injectTouch()` correctly dispatched them to `switchApp()`, poisoning app state for T134–T140 (cascading FAIL). Fixed by splitting T088 into DEADZONE (x<275) and TASKBAR (x≥275) groups; added `_restore_spotify()` teardown. **Root cause**: T088 was written before the taskbar existed and was not updated when the taskbar feature was added. Pattern: **tests are not being kept current with new hit-zones.**

4. **"Done" declared before DUT smoke test — PATTERN.** TASK-087 was closed with "DUT flash + smoke test pending" in the status line. Same pattern appeared in prior tasks (TASK-042, TASK-009). The distinction between "build passes" and "DUT verified" is consistently blurred at task close. No `pending-dut` status exists; done is declared when the build is clean, with DUT as an afterthought parenthetical.

5. **Open actions from prior audits accumulating — RED.** Six functional stale tool-script paths (LL-029, audit 2026-05-24) remain unresolved. The PM action to file a fix task was assigned but not executed. The tool-script smoke-test gate (recommended in LL-029 Finding 3) does not exist. These open items are now >0 days old with no assigned task.

6. **Strategic project quality observation — FLAGGED FOR HUMAN.** *(See below.)*

**Strategic observation — flagged to human:**

Across the TASK-087 salvage and the prior audits, a pattern is visible: each milestone is shipping with a residual of open defects, deferred spec items, and stale test coverage, each individually justified as "acceptable for current scope." The accumulated residual is now:

- TASK-088: BUG-2 (saveAppState/restoreAppState — deferred)
- Open: 6 functional stale tool-script paths (LL-029 — no task filed, no fix)
- Open: T088 class of problem (tests not updated when features add new hit-zones — no checklist item)
- Open: tool-script smoke-test gate not implemented
- Deferred: icon glyphs in taskbar (TFT font 4, not SKIN_GLYPH)
- Deferred: PLEDIT Y-coordinate absolute addressing (latent originY≠0 debt, TASK-080 finding)
- Historical: TASK-021/066/067 (tap-to-play with context — partial fix, deferred M-LIST-v3)

Before M-MULTIAPP step 3 (Matrix, GoL, Weather, Crypto apps), **the QM recommends a consolidation sprint** rather than continuing to add features. Specific actions that belong in such a sprint:

| Item | Type | Urgency |
|------|------|---------|
| Fix 6 functional stale tool-script paths (LL-029) | Correctness | High — blocks next tool invocation |
| Add `tools/smoke_test.sh` (import + --help each script) | Process gate | High — prevents recurrence |
| Implement TASK-088 (saveAppState/restoreAppState) | Spec compliance | Required before step 5 |
| Add "test-currency" checklist item to any task that adds a hit-zone | Process | Medium — prevents T088 class |
| Formalise `pending-dut` task status or VE sign-off as done gate | Process | Medium — prevents premature close |

This is a recommendation, not a decision. PM/human determines whether to sprint-clean before step 3 or continue and accept the accumulating debt. QM notes the debt is currently serviceable but the trajectory — each feature adding 2-3 deferred items — will make it unserviceable by step 5/6.

**Actions assigned**:

| # | Owner | Action | Priority |
|---|-------|--------|----------|
| 1 | PM | File task for LL-029 stale tool-script paths (overdue from prior audit) | immediate |
| 2 | QM | Add LL-030 (premature "done" pattern) and LL-031 (test currency on hit-zone changes) | this audit |
| 3 | Human | Decide: consolidation sprint before step 3, or continue feature work and accept debt | human decision |
| 4 | PM | If consolidation approved: sequence the sprint tasks in `tasks.md` and block step 3 on completion | after human decision |

**Promotion candidates flagged**:
- **LL-030** (new): "done before DUT test" pattern.
- **LL-031** (new): "test hit-zone currency" pattern.

**Resolution**: BUG-1 resolved. LL-030/031 captured. Strategic observation filed for human. Items 1, 3, 4 remain open pending human decision.

---

### Audit — 2026-05-25 — PLEDIT empty rows regression (getQueue malloc failure)

**Triggered by**: human (bug report: PLEDIT shows chrome but no track rows during active playback)

**Areas checked**:
- [x] Bug root cause (why `onQueue` was never called despite status=200)
- [x] Introduction point (which commit / milestone introduced the regression)
- [x] Test coverage gap (was T114 positioned to catch this?)
- [x] Fix adequacy (does the streaming approach eliminate the failure class?)
- [x] Lessons learned (LL-038, LL-039 extracted)

**Findings**:

1. **Root cause: `malloc(65536)` silently fails on fragmented heap — RED.**
   `getQueue()` allocated a 65 536-byte `bodyBuf` to buffer the raw Spotify queue response. On M-MULTIAPP firmware (5 App subclasses + `dataTask`), heap fragmentation causes `malloc` to return `NULL`. The `!bodyBuf` path returns status=200 silently — `onQueue` never fires, `g_queueSnapshot.count` stays 0, PLEDIT renders all rows empty. No `LOG_W` existed on the failure path; the condition was invisible in production logs.
   _Fixed: `BlockingChunkedStream` streams directly from TLS socket into `deserializeJson` with filter — heap cost drops from 65 KB + 10 KB to ~10 KB. See `app/lib/SpotifyArduino/src/SpotifyArduino.cpp` (LOCAL_PATCHES note)._

2. **Regression introduced by M-MULTIAPP, not by a code change to `getQueue()` — AMBER.**
   The `malloc(65536)` bodyBuf was introduced in the TASK-065 dechunker fix (2026-05-20) and verified by T114 at the time. M-MULTIAPP (TASK-087–095) increased heap fragmentation without any change to `getQueue()`. The fix that passed T114 was no longer safe under the new firmware's heap profile.
   _Action: LL-038 filed. See "Suggested improvement" — large heap allocations on resource-constrained targets require re-verification after significant subsystem growth._

3. **T114 not re-run after M-MULTIAPP — AMBER.**
   T114 asserts `count >= 1` and would have caught this regression immediately. Its precondition pins a firmware commit (`ab3864e`) rather than a firmware capability class. No re-run was scheduled when M-MULTIAPP landed.
   _Action: LL-039 filed. T114 should be annotated `[RESOURCE-SENSITIVE]` and re-run whenever a new FreeRTOS task or App subclass is added. PM to file a task for VE to re-run T114 + annotate._

4. **Silent failure path in `getQueue()` masked the bug class — RED.**
   The `!bodyBuf` code path existed but emitted no log. Had a `LOG_W` been present, the first keepalive would have surfaced it. The absence of error logging converted a recoverable resource failure into an invisible one.
   _Fixed incidentally by removing the path (streaming approach has no malloc). Future patches: any `malloc ≥ 16 KB` failure on ESP32 must log `LOG_W` with `largest_free_block`._

**Also noted**: PLEDIT blank-for-1s on quick app switch (separate bug, same session) — fixed in `invalidatePlaylist()` via `lastPlaylistDrawMs = 0` reset. Commit `208a8ae`. Root cause: TASK-090 "Fix B3" was incomplete — bypassed seqno guard but not the 1-Hz rate limit. LL candidates not extracted (simpler fix, less systemic pattern).

**Actions assigned**:
- VE: annotate T114 `[RESOURCE-SENSITIVE]`; add it to re-run checklist for any new App/task addition
- VE: re-run T114 against current `cyd2usb_winamp_debug` firmware to confirm fix
- PM: file task for T114 annotation + re-run

**Resolution**: Finding 1 fixed (streaming parse, commit to follow). Finding 4 fixed as a side effect. Findings 2–3 open pending VE/PM actions.

---

### Audit — 2026-05-30 — serialdbg test suite coverage quality

**Triggered by**: human (post LL-040/041/042 resolution — question: "how many tests are fire-and-forget?")

**Areas checked**:
- [x] All 78 test functions in `run_serialdbg_tests.py` classified by assertion strength
- [x] Tests that assert only serial ACK receipt (not DUT behavior)
- [x] Tests using enqueue-proxy timestamps instead of completion counters (LL-041 pattern)
- [x] Tests permanently skipped in automation (interactive / pixel-only)
- [x] Tests with weak or trivially-true assertions

**Findings**:

1. **2 fire-and-forget / ACK-only tests — AMBER.**
   - T090: asserts `reconnect` returns `ok=true` and `cmd="reconnect"` — only proves the serial command was received, not that reconnection occurred.
   - T083: asserts `help` response is parseable JSON with correct command names — functional smoke, not a behavioral test.
   _These provide minimal signal. T090 should assert post-reconnect state (e.g. `consecutiveFailures=0`). T083 is acceptable as a smoke check but should be labelled as such._

2. **2 enqueue-proxy tests (LL-041 pattern not yet fixed here) — RED.**
   - T170: asserts `lastQuoteFetch > 0` — proves `init()` set the timestamp, not that a quote fetch completed.
   - T176: asserts `lastChartFetch > 0` — same enqueue-proxy pattern that LL-041 identified and fixed in T186–T188. Inconsistency: T186–T188 use `fetchOkCount`; T176 still uses the stale proxy.
   _Direct fix: upgrade T176 to use `fetchOkCount` (already in firmware). T170 needs a quote ok-counter equivalent or a data-presence check._

3. **9 weak-state assertion tests — AMBER.**
   - T078: drag sends; asserts `dragState=D_IDLE` only — VOLUME action not confirmed.
   - T082: volume drag; counts `"enqueue"` log lines — dispatched Spotify action not confirmed.
   - T134: PLEDIT tap; asserts `hit=PLEDIT` only — `action` value not checked.
   - T136: asserts `scrollOffset=0` initial value — observes state, proves nothing.
   - T178: asserts `chartRange=D1` default — trivially true, no causal assertion.
   - T_BI_04: PLAY tap; asserts `action ∈ {PLAY, PAUSE}` — state toggle not verified.
   - T_GOL_04: asserts `golAlive >= 0` — field presence only; 0 is valid even if simulation didn't run.
   - T_WX_04, T_CX_04: assert `ready=false` before fetch — timing-dependent; skipped if data arrive fast.
   _Varying severity. T136 and T178 are pure observation with no assertion value. T_WX_04/T_CX_04 are inherently racy. T082/T078 require Spotify playing to verify fully — acceptable to leave as partial coverage with explicit annotation._

4. **5 permanently-skipped tests in automation — GREEN (by design).**
   - T093, T094, T095: `--interactive` flag only; require human operator. By design.
   - T171, T179: pixel verification; no automated path. By design.
   _No action needed, but these should be annotated `[MANUAL]` explicitly in test_plan.md so future agents don't attempt to automate them._

**Actions assigned**:
- VE: fix T176 (enqueue proxy → `fetchOkCount`); propose T170 fix; annotate weak tests; add `[MANUAL]` tags — see TASK-112
- PM: file TASK-112 for VE fix pass
- QM: extract promotion candidates from this audit if pattern recurs

**Resolution**: open — TASK-112 filed.

---

### Audit — 2026-06-08 — ADR-042 follow-on retrospective (TASK-156/157/158/159)
**Triggered by**: PM (post-milestone)
**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage
- [x] Documentation currency

**Findings**:

1. **Doc currency — test_plan.md T-SET-03/T-SET-07 stale status**: Both tests were marked "failing [STALE — superseded by T-APPS-07]" but the `settingsAppSubmenu` debug var was re-implemented (TASK-159) and both now PASS. Status corrected in this session.

2. **Design gap — injection dispatcher missed when taskbar gesture API added (LL-061)**: `drainInjectionQueue` was not updated when `tbGesturePress/Continue/End` replaced direct touch handling in the taskbar zone. Gap existed from M-TASKBAR-SCROLL commit to TASK-158 fix. No existing process required updating the injection path when a new touch zone is added.

3. **Design gap — `_injectingDrag` flag written without consuming guard (LL-062)**: Flag was `#ifdef SERIAL_DEBUG` dead state. No test verified the suppression behavior, so the gap survived multiple DUT runs undetected.

4. **Test maintenance gap — `_TB_N` preserved at numeric value instead of updated symbolically (LL-063)**: When Aquarium was added (APP_COUNT 8→9), `_TB_N` was preserved at 8 via `APP_COUNT - 1`. Correct value was `APP_COUNT`. Pattern: count-derived constants should be symbolic, not numeric.

5. **Open BP candidates not yet promoted**: LL-059 and LL-060 (from prior session) remain at "open — BP candidate". New candidates from this session: LL-062 and LL-063.

**Actions assigned**:
- VE: test_plan.md T-SET-03/T-SET-07 status corrected (done this session).
- QM: present LL-059, LL-060, LL-062, LL-063 as BP candidates to human (done this session).
- Developer: no new tasks filed; LL-061/062/063 are process lessons, not open code gaps.

**Resolution**: closed — BP-023/024/025/026 promoted 2026-06-08 on human sign-off. LL-059/060/062/063 marked adopted.

---

### Audit — 2026-06-11 — SPIFFS hygiene + run/spiffs VE (TASK-160–166)
**Triggered by**: human  
**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage
- [x] Documentation currency

**Findings**:

- **AMBER — `dev-001` inventory entry stale**: `feature_inventory.yaml` still lists `dnsOverride.h` and `tools/refresh_host_overrides.sh` under `dev-001`. Both were deleted by TASK-160 (commit `6a5b858`). Owner: Developer — update files list and description.

- **AMBER — `run/spiffs` unregistered**: The new SPIFFS manager has no `feature_inventory.yaml` entry despite having a 12-test VE suite and a blocking relationship to M-SETUP-WIZARD. Precedent set by `tooling-001` (smoke_test.sh). Owner: Developer — add inventory entry with `test_ids: [T-SPIFFS-01..T-SPIFFS-12]`.

- **GREEN — Test coverage**: T-SPIFFS-01–10 and T-SPIFFS-12 passing. T-SPIFFS-11 correctly deferred (requires DUT disconnected). No coverage gaps on the verified feature set.

- **GREEN — Cross-feature interactions**: M-SETUP-WIZARD ↔ run/spiffs inconsistency (ESCALATION-SETUP-2) corrected by TASK-164. No remaining cross-feature gaps in this work batch.

- **GREEN — Documentation currency**: `CLAUDE.md`, `project_run_scripts.md`, `M-SETUP-WIZARD.md`, `tasks.md`, `test_plan.md` all updated within the session. No doc lag detected.

- **RED — TASK-161 premature closure (process incident)**: TASK-161 was closed by an LLM agent with "ls confirmed 5 files." The feature's primary claim is non-destruction — that claim was never tested at closure. The EXIT trap defect (monitor left dead on `set -e` failure) also existed at closure and was found only by a subsequent VE challenge review. Three recovery tasks (TASK-163/164/165) were required. Lesson recorded as LL-064.

**Actions assigned**:
- Developer: update `dev-001` inventory entry (remove deleted files)
- Developer: add `run/spiffs` entry to `feature_inventory.yaml`
- VE: close T-SPIFFS-11 at next hardware-absent opportunity

**Resolution**: closed 2026-06-11 — `dev-001` inventory updated (deleted files removed), `tooling-002` entry added with T-SPIFFS-01..12. T-SPIFFS-11 remains deferred (host-only, DUT-disconnected; not a blocker).

---

### Audit — 2026-06-11 — M-SETUP-WIZARD milestone retrospective
**Triggered by**: PM (post-milestone)
**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage
- [x] Documentation currency

**Findings**:

1. **GREEN — Exit criteria coverage**: All 7 exit criteria (E1–E7) verified. E1/E6 DUT-confirmed (T-SETUP-07/08 passing). E3/E4/E5/E7 confirmed by implementation review. E2 manually testable only (real Spotify account + browser; permanent manual status, not a gap).

2. **GREEN — Feature inventory**: `setup-wizard-001` entry added this session with full test_ids, cross-feature ref to tooling-002, PATCH-003 file reference. No inventory lag.

3. **GREEN — Documentation currency**: All six doc targets updated in implementation commit (README.md, CLAUDE.md, project_run_scripts.md, dut_workflow.md, get_refresh_token.py, upstream-patches.md). No lag detected.

4. **GREEN — PATCH-003 upstream registration**: Registered in `upstream-patches.md` before implementation, as required by design spec. No process gap.

5. **AMBER — Design doc pseudocode not reviewed as production code**: The PATCH-003 snippet in `M-SETUP-WIZARD.md` used `WiFi.persistent(true)`. This was copied directly into `WifiManagerHandler.h`. The NVS side-effect — that a failed `WiFi.begin()` with `persistent(true)` overwrites NVS with bad credentials — was not caught at design time or implementation time. It was found during VE (T-SETUP-10). Fix was straightforward (`persistent(false)`, TASK-167), but it required an extra DUT cycle and corrupted the test device's NVS during the test. No prior LL or BP covers this pattern.

6. **GREEN — VE process**: T-SETUP suite defined before DUT testing began. Bug found and fixed within the same VE session. Recovery was orderly — no new escalations or additional recovery tasks beyond TASK-167.

7. **GREEN — Safety-property discipline (BP-027)**: PATCH-003 fallthrough claims were tested with both the missing-file case (T-SETUP-09) and the bad-credentials case (T-SETUP-10). BP-027 applied correctly.

**Actions assigned**:
- QM: present finding 5 (design doc code review) to human as LL candidate.

**Resolution**: closed — one LL candidate (finding 5) presented to human below.

---

### Audit — 2026-06-11 — SETUP consistency sweep (post M-SETUP-WIZARD VE close)
**Triggered by**: human
**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage
- [x] Documentation currency

**Findings**:

1. **AMBER → fixed — Roadmap M-SETUP-WIZARD status stale**: Entry read "not started"; description referenced `wifi_creds.h` write and `run/flash-fs`. Both wrong. Updated to "done (2026-06-11)" with correct implementation summary. Fixed this session.

2. **AMBER → fixed — README.md step 9 misrepresented portal as primary path**: "If you did not hardcode WiFi credentials" framed the captive portal as the normal first-boot flow. With PATCH-003, users who ran `./run/setup` connect automatically via SPIFFS. Step 9 rewritten to present SPIFFS as primary, portal as fallback. Fixed this session.

3. **AMBER → fixed — CLAUDE.md "Runtime configuration" omitted `./run/setup`**: Section listed two ways to populate config (portal, raw `pio uploadfs`). `./run/setup` was absent. `pio run ... uploadfs` replaced with `./run/spiffs push`. Updated to three ways with wizard as primary. Fixed this session.

4. **AMBER → fixed — CLAUDE.md "Hardcoded station WiFi" priority chain incomplete**: Described fallback as "compile-time → portal", omitting the SPIFFS intermediate step (PATCH-003). Updated to full chain: `wifi_creds.h` → SPIFFS → portal. Fixed this session.

5. **AMBER → fixed — CLAUDE.md / dut_workflow.md stale `uploadfs` references**: `get_refresh_token.py` "next steps" still said `uploadfs from app/`; dut_workflow.md failure-modes table said `uploadfs with a pre-baked file`; dut_workflow.md §3b said `uploadfs does NOT touch firmware`. All updated to `./run/spiffs push` or genericised. Fixed this session.

6. **GREEN — Test coverage**: T-SETUP-01..10 in test_plan.md. T-SETUP-07..10 passing on DUT. T-SETUP-01..06 correctly marked manual (wizard CLI + OAuth require human interaction). No coverage gaps relative to implemented features.

7. **GREEN — Feature inventory**: `setup-wizard-001` entry present with T-SETUP-01..10 test IDs, cross-feature ref to tooling-002, PATCH-003 file reference. No inventory lag.

8. **GREEN — BP compliance**: BP-027 (safety-property tests) and BP-028 (design doc code review) both applied in this session. LL-065 → BP-028 promoted same session.

**Actions assigned**: all fixed inline (findings 1–5).

**Resolution**: closed — all findings resolved this session.

---

### Audit — 2026-06-11 — M-SETTINGS-WIFI-P2 (TASK-168)

**Triggered by**: human (post-milestone QM request).

**Scope**: M-SETTINGS WiFi Phase 2 — WiFiManager/DRD removal + on-device connect UI. Commits since `463ba0b` (M-SETUP-WIZARD) to `ddf6433` (M-SETTINGS-WIFI-P2 close). Files: `app/src/main.cpp`, `app/src/settings/wifiSection.h`, `app/platformio.ini`, upstream-patches (disk-only), docs.

**Areas checked**:
- [x] Implementation completeness vs TASK-168 spec
- [x] DUT verification coverage (T-WIFI-P2 suite)
- [x] Documentation currency (CLAUDE.md, dut_workflow.md, test_plan.md, tasks.md, roadmap.md)
- [x] Bug introduced and fixed (async scan root cause)
- [x] BP / LL recurrence

**Findings**:

1. **AMBER → fixed — CLAUDE.md §Runtime configuration: WiFiManager NVS reference**: Line 159 said "written by WiFiManager into ESP32 NVS". Updated to "written by `WiFi.begin()` into ESP32 NVS on intentional user connect via on-device WiFi settings UI". Also removed stale `WM_CLIENT_ID_LABEL` / `WifiManagerHandler.h:9` sentence. Fixed this session.

2. **AMBER → fixed — CLAUDE.md §Runtime configuration: captive portal option**: Method 3 described the full captive portal flow (DRD, SSID `SpotifyDIY`, `ESP_DRD_USE_SPIFFS=true`, "Configure WiFi" page caveat). Replaced with on-device WiFi settings UI description. Fixed this session.

3. **AMBER → fixed — CLAUDE.md §Hardcoded station WiFi: section heading + priority chain**: Heading said "bypass captive portal"; body referenced `WifiManagerHandler.h`; priority chain ended "→ WiFiManager captive portal". Updated heading, body reference (`main.cpp`), and chain (NVS + WiFi settings UI). Fixed this session.

4. **AMBER → fixed — dut_workflow.md §1 WiFi compile-time fallback**: Line 50 said "then captive portal". Updated to "then WiFi settings UI on device". Fixed this session.

5. **AMBER → fixed — dut_workflow.md §7 failure table**: Row "DUT stuck in captive portal after test run" with DRD-specific cause/fix. Replaced with WiFi settings UI equivalent. Fixed this session.

6. **AMBER → fixed — test_plan.md T-WIFI-P2-02 expected result**: Said "CONNECTING transitions to Spotify app (connected). WiFi section closed." — wrong on both counts. Actual: transitions to STATUS (connected info). User navigates manually. Fixed this session; TASK-169 filed for the UX gap.

7. **GREEN — Build gate clean**: `./run/check` passed all 5 gates post-implementation.

8. **GREEN — DUT verification coverage**: T-WIFI-P2-01..06 all passing (2026-06-11). Covers: boot-to-settings nav, encrypted connect, wrong password, NVS persist across reboot, forget-network, open network.

9. **BP CANDIDATE — synchronous WiFi scan when Spotify task running**: `WiFi.scanNetworks(async=true)` is silently cancelled by concurrent `WiFiClientSecure::connect()` calls from the Spotify FreeRTOS task when both are pinned to core 1. Use synchronous scan (`WiFi.scanNetworks(false)`) in this architecture. Presenting to human for BP promotion.

**Actions assigned**: findings 1–6 fixed inline. TASK-169 filed (finding 6 UX gap). BP candidate 9 presented to human.

**Resolution**: closed — all doc findings resolved this session. TASK-169 open for UX follow-up.

---

### Audit — 2026-06-14 — M-TELETEXT post-ship DUT defect retrospective
**Triggered by**: human ("how did we miss these?") after 3 defects found in first DUT use
**Areas checked**:
- [x] Feature inventory completeness
- [x] Test coverage per feature
- [x] Cross-feature test coverage
- [x] Documentation currency

**Findings**:
1. **Subpage nav broken (silent data loss)** — `parsePage("617-2")` via `atoi` returned 617, dropping sub-index. T270 covered this case but was blocked `[NETWORK][G1,G2]` with no synthetic injection fallback. Gap: no `set teletextPageContent` path to simulate a subpage-bearing response.
2. **Numpad placeholder shipped as complete** — `_handleStrip()` contained `// Keypad not yet implemented`. No task filed, no feature_inventory partial flag, no known-gap note in test plan. T271 expected `KEYPAD_OPEN` but was blocked and never run.
3. **touch-004 not wired to TeletextApp** — `hasPendingAsync()` defaulted to `false`. `touch-004` correctly marked `proposed` in feature_inventory but no new-app checklist enforces the integration. T-BUSY suite was pending Developer deliverable; never run against TeletextApp.

**Root cause pattern**: All three were "planned but not enforced." Tests existed (T270, T271, T-BUSY) but were blocked or pending. No process step at milestone close verified that blocked tests had synthetic alternatives or that cross-cutting integrations were satisfied.

**Actions assigned**:
- Developer: file tasks for injection-based subpage nav test (T270 synthetic alternative) — Owner: Developer
- Developer: adopt `// TODO(TASK-NNN):` convention for any "not yet implemented" placeholder — Owner: Developer
- Developer: add new-app cross-cutting integration checklist to milestone close procedure — Owner: Developer / PM
- QM: propose BP candidates from LL-074, LL-075, LL-076 to human for sign-off

**Resolution**: LL-074, LL-075, LL-076 filed and adopted. Three defects fixed (commits 728a278, 3633cf6). BP-034, BP-035, BP-036 promoted with human sign-off (2026-06-14).

---

### Audit — 2026-07-02 — M-WIFI-DIAG design 3-agent panel review (PM/QM/VE)
**Triggered by**: Architect (pre-implementation feasibility/quality panel on the outage-attribution design)
**Areas checked**:
- [x] Documentation currency (design vs. code claims)
- [x] Test coverage / gate criteria (agent-executable exit rules)
- [x] Cross-cutting process compliance (BP conformance, evidence discipline)

**Findings**: PM/QM/VE returned approve-with-changes; blockers/majors applied in place (VE-1 harness-reset destroys async evidence; VE-3/QM-3 firmware bucket = absence-of-evidence; QM-1 gate not agent-executable; QM-2 sensor positive control). QM-8: duplicate LL-069 id flagged, deferred as "handled outside this doc."
**Actions assigned**: Architect — disposition into design §7-8 (done); QM — action the duplicate-LL flag (deferred → TASK-281).
**Resolution**: Design approved (human, 2026-07-02); TASK-274/275 filed and closed. QM-8 carried to TASK-281.

---

### Audit — 2026-07-03 — Touch-UX design trio 3-agent panel review (VE/DEV/QM)
**Triggered by**: Architect (panel on M-WR-PLEDIT-SCROLL / M-WR-AUDIO-TASK / M-TASKBAR-FEEDBACK, TASK-277/278/279)
**Areas checked**:
- [x] Documentation currency (every code line-ref verified against tree)
- [x] Test coverage / testability (exit criteria agent-executable via run/ + serialdbg)
- [x] Cross-cutting process compliance (BP/LL conformance, evidence discipline)

**Findings**: all three docs approve-with-changes ×3. 1 blocker (VE-1-1/DEV-1-1: injected-drag Release reroute + gesture-captures-Release), several cross-doc majors (perf MAX_PATHS silent overflow; shared-baseline sequencing; ESP32-audioI2S mutex-hold under `connecttohost`). **New find: LL-070 duplicate id** (second dup alongside the never-actioned LL-069) → both carried to TASK-281. BP-043's "Adopted from: LL-070" cite noted as ambiguous.
**Actions assigned**: Architect — disposition all findings (done, commit 31a4b41); QM — file the duplicate-LL housekeeping (TASK-281).
**Resolution**: Designs accepted (human, 2026-07-03). Panel reviews retained under `docs/architecture/designs/touch-ux-panel-*-review.md`.

---

### Audit — 2026-07-11/12 — M-PLANERADAR code audit vs reference + human visual review (TASK-309..312)
**Triggered by**: human ("I suspect code duplication and magic numbers"; second pass: compare vs `~/proj/esp/ESP32-Plane-Radar/`)
**Areas checked**:
- [x] Code duplication (planeRadarApp.h, dataTaskStorage.cpp planeradar sections, appsSection.h)
- [x] Magic numbers / named-constant coverage
- [x] Behavioural parity vs reference implementation (projection, clipping, vector semantics, runway overlay, edge insets)
- [x] Human on-device visual review (the gate no agent pass covers — see LL-109)

**Findings**: 3 bug-class defects (edge-inset strip corruption; range-tap aircraft blank, permanent under injection; dbgSet/handleInput repaint divergence — a 24-hour-old fix that had diverged across duplicated sites, LL-110), 8 duplication findings (incl. a cross-file preset-table duplicate that could silently desync the Settings UI), ~8 magic-number clusters, 2 wrong/stale comments. Reference comparison: our projection is MORE accurate than the reference's (cos-lat corrected — kept, documented as deliberate divergence). Human visual review then caught what every agent pass missed: `init()` painted nothing — first-entry sequence broken since TASK-304, invisible to the serial-only T_PR suite (LL-109). Human style directives issued and implemented (uniform rings, black surround, PR_R−1 containment invariant).
**Actions assigned**: Developer (Sonnet subagent ×2, orchestrator-reviewed) — TASK-309/310/311 (audit findings), TASK-312 (first-entry paint + style unification). QM — LL-109/LL-110 filed; T_PR_05 added to the flaky watchlist ([NETWORK]: SKIP/PASS/FAIL/PASS across 4 runs, triage recipe recorded).
**Resolution**: All four tasks DONE 2026-07-12 (code commits `2fb504c`, `2eed48f`). `run/check` 6/6 at every gate; T_PR suite green (T_PR_05 first-run FAIL triaged environmental: host probe 200 minutes later, solo re-run PASS); human visual sign-off on TASK-312 ("looking good"). BP candidates LL-109/LL-110 await human promotion decision.

---

### Audit — 2026-07-14 — mem_manifest coverage vs actual heap consumers (M-PLANERADAR trigger)
**Triggered by**: human — "for the planeradar implementation, did we make use of the memory budgeting and memory python framework?"
**Areas checked**:
- [x] `mem_manifest.yaml` buffer list vs grep sweep of `DynamicJsonDocument`/`BasicJsonDocument`/heap allocs in `app/src/dataTaskStorage.cpp`
- [x] M-PLANERADAR artefacts (ADR-048, phase0-parse-heap) for measured budget numbers that never reached the manifest

**Findings**: PlaneRadar's chunked-parse doc (4096 B, measured to the byte in ADR-048 phase 0) never entered the manifest — the WCMU gate under-counted by 4 KB while reporting green; unregistered consumers make the budget look *better*, so the gate cannot flag its own coverage gap. Sweep found two more unregistered heap docs: weather (1024 B) and webradio stations (`WR_DOC_CAP`=5120 B) — manifest covered 2 of 5 heap parse docs. Root cause and BP candidate filed as LL-111 (registration is opt-in; no forcing function in the new-app flow).
**Actions assigned**: Developer — register `planeradar_doc` and convert `prParseStream()` to the placed-overlay pattern (done in-session); TASK-326 filed for the weather/webradio backfill (Architect consult on the webradio entry's group/placement). QM — LL-111 filed, BP candidate flagged for human promotion decision.
**Resolution**: `planeradar_doc` registered + placed same session (manifest, `gen_mem_layout` regen, `StaticRegionAllocator` conversion, `golden.sha256`; ANY/foreground region 2560→4096). `run/check` 6/6. TASK-326 closed 2026-07-18: weather_doc placed (landed with WIRE2-G4 `1abfb32`), webradio_stations_doc registered `placement: runtime` per Architect ruling, stack-vs-heap scope note in the manifest header — all five heap parse docs now registered.

---

### Audit — 2026-07-18 — M-PR-LOCATIONS + M-SETTINGS-STYLE milestone retrospective
**Triggered by**: PM (bookkeeping close-out pass; milestones closed 2026-07-16, retro not yet logged)
**Areas checked**:
- [x] Process compliance vs the r2 panel-review actions (all blockers/majors folded pre-implementation)
- [x] Deferred-item ledger discipline (LL-102 guard — every deferred DUT assert dispositioned BY NAME in TASK-324)
- [x] tasks.md/roadmap status consistency at close
- [x] Defects found during or adjacent to the milestone window

**Findings**:
1. **Process — green, best cycle to date.** Design r2 → 4-reviewer panel (unanimous PASS-with-actions) → blockers folded into r2 *before* code → preview-first eyeball gates (BP-048, TASK-316/317) froze layout before any C++ → per-task intermediate DUT smokes → one grouped VE gate (TASK-324). The LL-102 ledger held: every deferred assert was either run, cited from a named smoke, or explicitly re-deferred with a destination (TASK-318 -120 → M-CERT-ERRCODE; T232/233/246/247 → own suite).
2. **Bookkeeping lag (this audit's trigger).** Roadmap said closed 2026-07-16 but seven task entries (TASK-319/320/321/322/323/325/328) still read "code landed / intermediate smoke" two days later — flipped to DONE in this pass. Minor; harmless because the TASK-324 gate entry carried the truth, but grep-for-open-status (the standing PM recall rule) would have miscounted open work.
3. **Adjacent defects caught by milestone VE sessions, not by the milestone itself**: TASK-329 (settings JSON silent truncation — real data loss, recovered from session-start snapshot → BP-049 adopted) and TASK-330 (stale 26px tap-row formula in the shared test harness — same drift class as the e929792 prloc-smoke fix and the 801f378 coordinate-drift lesson). Both DONE and DUT-verified. Pattern worth noting: the app-list row compression (21px) has now bitten three separate host tools; any future settings-list geometry change must sweep *all* tap-injection helpers in one pass.
4. **Toolchain lesson carried**: gnu++11 NSDMI-struct brace-init wall (found TASK-321, re-confirmed TASK-327 migration) — field-assignment idiom is the standing workaround.

**Actions assigned**: PM — task statuses flipped, M-SETTINGS-STYLE roadmap entry added (done, was never stubbed) [this pass]. QM — BP candidate "new Settings UI = kit widgets only; hand-rolled buttons are a review flag" (from TASK-327) awaits human promotion decision. Developer — TASK-326 (mem_manifest backfill) is the next open item.
**Resolution**: closed with this entry; no new tasks filed. TASK-326 was then closed the same day (webradio_stations_doc runtime entry; see the 2026-07-14 audit's resolution).

---

### Audit — 2026-07-18 — M-ICON-PIXELART TASK-331/332/334 retrospective (milestone still open: TASK-333 remains)
**Triggered by**: human ("QM PM, happy?")
**Areas checked**:
- [x] git log vs tasks.md/roadmap consistency (8 commits, 874181d..d87f5d0)
- [x] Gate discipline (run/check at every landing; golden regen twice; BP-048 eyeball named + executed)
- [x] Host tooling the milestone leaned on (preview surfaces, bake pipeline)
- [x] Feature inventory currency for touched areas

**Findings**:
1. **Process — green, and a pattern worth keeping.** Decision → ADR-051 → four filed tasks → execution, same day, with the human decision gate up front (size/authoring/fill asked once, before any code). The host-first inspection loop did what it promised: 3 approval rounds ran entirely on contact sheets (NATIVE_SHEET.png), the DUT was flashed **once**, and the eyeball gate passed first try.
2. **Two host-preview drift defects found mid-milestone**: `preview_layout.py` still rendered TEXT.BMP placeholder glyphs (~5 weeks after real icons shipped), and `preview_common.py`'s hardcoded 24×24 mirrors feed `--export`'s *write* path — a habitual export would have silently regressed the ADR-051 bump. Third instance of the "host tool encodes firmware truth by copy" class (after the 21px tap-row arc). **LL-114** filed; structural fix (parse, don't mirror) = **TASK-335**.
3. **feature_inventory.yaml stale by two generations** for taskbar rendering: `taskbar-001` still documents "6 icon slots (S/C/W/$/M/G via TFT font 4)" (pre-M-TASKBAR-ICONS, pre-ADR-051); the preview-tool entry still documents TEXT.BMP glyph rendering. Refresh folded into TASK-335.
4. **Deliberate fill-band outliers recorded in three places** (tasks.md close-outs, memory, bake WARNs): teletext 83% (square-glyph optical correction), aquarium 97% (wide-flat text fish) — so a future pass doesn't "fix" them.
5. **PM state**: milestone NOT closed — TASK-333 (PlaneRadar re-author) open and unblocked; inherits the proven `gen_icon_natives.py` pipeline. Roadmap says exactly this; no premature close.

**Actions assigned**: QM — LL-114 logged; BP candidate "visual-asset work: approval iterates on host contact sheets, single batched DUT flash carries the BP-048 eyeball" brought to human. Developer — TASK-335. PM — none; bookkeeping current as of d87f5d0.
**Resolution**: closed 2026-07-18, same day. BP candidate **adopted as BP-051** (human). TASK-335 landed (cf07d30 — shared `shell_layout.py` parser, byte-identical `--export` round-trip, inventory refreshed). TASK-333 landed (6c2fc29) with human eyeball PASS → **M-ICON-PIXELART closed**. Process deviation noted for the record: TASK-333's BP-051 sheet approval was a blanket mid-turn "proceed" delegation; the BP-048 eyeball backstop held as designed (human confirmed active icon on panel before task close).

---

### Audit — 2026-07-31 — M-CEEFAX close-out: a feature accepted "closed" without ever being functionally tested

**Triggered by**: human ("run the QM retro on the process miss"), after M-CEEFAX
was cut (ADR-058 D, commit 41448f5).

**Scope**: the M-CEEFAX close-out arc — ADR-057's "Option A accepted / M-CEEFAX
closed" disposition (2026-07-31), the secondary analysis that preceded it (PROP-008
DMA-leak / EXP-019 no-leak / TASK-374 coexistence soaks / arduinoWebSockets #864
research), and how the miss was caught and recovered (human functional-test prompt →
TASK-376 crash root-cause + first real connect → EXP-020 non-viability proof → cut).

**Findings**:
1. **LL-115 (new) — headline miss**: M-CEEFAX was accepted as "closed" while it had
   **never once connected or rendered a page**. A large, internally-consistent body
   of memory/leak/coexistence analysis characterized a permanently-failing feature
   and mis-read its failure signatures (freeDma oscillation, Spotify `SSL -32512`) as
   legitimate coexistence findings. The **rigor of that analysis masked the absence
   of any primary functional test**. Same family as LL-064 (happy-path smoke accepted
   as proof) and BP-048's rationale (a coherent but wrong source-read root cause),
   one step worse — there was no functional test at all to over-trust.
2. **Contributing cause**: ADR-057's acceptance criterion ("accept best-effort
   connectivity") was never operationalized into a concrete "connect + acquire +
   render once" check; nothing gated the behavioral characterization behind "does the
   feature perform its primary function at all."
3. **What worked (not just blame)**: the human's one-line "I've never seen it working"
   prompt caught it; the recovery was disciplined and did **not** repeat the miss
   (crash root-caused + fixed → feature genuinely connected for the first time →
   EXP-020 *functionally* proved non-viability → cut). A standing acceptance gate,
   `app/tools/ceefax_connect_check.py` (exit 0 only on real connect+acquire+no-crash),
   was built and is the forcing function that should have existed from the start.

**Actions assigned**:
- **QM** — LL-115 logged (above). **BP candidate brought to human** (awaiting
  sign-off; QM does not self-adopt): *"A feature may not be marked done/accepted —
  and its non-functional characterization (perf, memory, coexistence, leak/no-leak)
  may not be treated as meaningful — until its primary function has been demonstrated
  end-to-end on the target at least once, captured as a named acceptance gate (an
  automated harness or an explicit human eyeball). Extends BP-048 part 2 from
  pixel-level UI to functional correctness."* Candidate BP-052, or an amendment to
  BP-048 — human's call.
- **PM** — M-CEEFAX filed **Closed (CUT)**; tasks.md milestone header + disposition
  banner, roadmap M-TELETEXT annotations, and the current-state memory all reconciled;
  next free task number **TASK-377**. (Done this session.)
- **Developer/Architect** — none open. Ceefax backend + settings + WebSockets dep
  removed; NOS Teletekst DUT-verified as the sole teletext source.

**Resolution**: closed 2026-07-31. LL-115 logged. BP candidate **folded into BP-048
(human)** — part (2) generalized from pixel-level to primary-function correctness,
new part (3) added (non-functional characterization is meaningless until the
primary-function gate is green). No further code action — feature cut, project state
consistent across tasks.md, roadmap.md, ADR-058, EXP-020, and memory.

---

### Audit — [YYYY-MM-DD] — [Scope]
**Triggered by**: human | PM | self
**Areas checked**:
- [ ] Feature inventory completeness (features in code not in inventory)
- [ ] Test coverage per feature (implemented features with no test_ids)
- [ ] Cross-feature test coverage (interactions with no test_coverage)
- [ ] Documentation currency (docs lagging behind code)

**Findings**: (specific gaps — named by feature ID, file path, or responsible agent)

**Actions assigned**: (owner and action per finding)

**Resolution**: (completed actions and outcome — filled in after closure)
```