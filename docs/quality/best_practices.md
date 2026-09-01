# Best Practices

> Owner: Quality Manager

Entries promoted from `lessons_learned.md` on explicit human approval. All agents read+apply. QM owns file, invalidates outdated practices.

### BP-049 — DUT sessions snapshot persisted state at start and verify a fully-populated round-trip at end

**Adopted from**: LL-113
**Date adopted**: 2026-07-18 (human)
**Rule**: Three parts. (1) Before any DUT work that reboots the device or exercises settings saves, snapshot persisted state: `./run/spiffs pull` and copy `settings.json` (plus any file the session may touch, e.g. `cal.json`) aside with a timestamp — this snapshot is the session's restoration source of record. (2) At session end, verify the device's `settings.json` against the snapshot (`./run/spiffs pull settings.json` + diff; byte-identical unless the session intentionally changed something, in which case restore and re-verify) — and verify against a FULLY-POPULATED real config, never fresh defaults: defaults fit any capacity by construction and structurally cannot reveal truncation-to-defaults. (3) Treat `SettingsStorage: loaded` as absence-of-syntax-error only, never as state-integrity evidence — a valid-but-truncated JSON loads cleanly into compile defaults with no alarming log line; when integrity matters, gate on actual values (`get prloc` sweep etc.).
**Rationale**: TASK-329 — settings saves silently truncated to compile defaults (ArduinoJson v6 no-ops past capacity; likely trigger was the doc's heap allocation failing under fragmentation) and ate real user data (all 4 prLocs slots, dispLevel, teletextPage, bitrateCap) with zero error output. Detection was pure luck (an unrelated mid-session `get prloc`); recovery was possible ONLY because a session-start snapshot happened to exist. Every DUT session on 2026-07-17/18 then ran this protocol deliberately: cost ~a minute each, and the end-of-session byte-identical diff is what proved five separate mutation-bearing sessions left the device clean.
**Applies to**: VE + Developer (every DUT session, step 0 and close-out), PM (exit-criteria wording on tasks touching persisted schema: require the fully-populated round-trip, not "loads without error")

---

### BP-048 — Apps must paint completely from init(); pixel-level AND primary-function exit criteria carry an explicit acceptance gate

**Adopted from**: LL-109; part (2) generalized from LL-115
**Date adopted**: 2026-07-12 (human); **amended 2026-07-31 (human)** — widened part (2) from pixel-level to primary-function correctness
**Rule**: Three parts. (1) Every app must produce its complete first paint on the shell's FIRST-entry path: `switchApp()` calls `init()` on first entry and `resume()` thereafter, so `init()` must either paint everything or explicitly route through `resume()`'s paint path — verify against the dispatch in `switchApp()`, not just the app file's internal consistency, and do not copy TeletextApp's init/resume shape blind (it has the same latent gap, masked only by its full-screen fetch redraws). Goes on NEW-APP-CHECKLIST. (2) Any task whose exit criteria are pixel-level (paint, palette, layout, erase artifacts) **or whose feature has a primary function only the real target can exercise** (does it connect? does it play? does it render the fetched content?) must carry an explicit acceptance gate that blocks DONE — a named harness that exits non-zero until the primary function is demonstrated end-to-end on-device, or an explicit human eyeball. Serial-dbg suites and behavioral soaks observe *state and signatures*, not "it works"; their "verified" assertions silently degrade to proxies for a feature that may never have functioned. (3) **Corollary (LL-115): a feature's *non-functional* characterization — performance, memory, coexistence, "leak / no-leak" — is meaningless until part (2)'s gate is green, and must not be produced before, or accepted in place of, a demonstration that the feature performs its primary function at all.** Rigor spent characterizing a non-working feature masks that it doesn't work.
**Rationale**: (part 1/2) PlaneRadar shipped with `init()` painting nothing — a stray ring, then a field-less grid, broken since TASK-304. It survived implementation review, a code audit against the reference project, a refactor review, and two full T_PR_01..06 DUT runs (T_PR_02 "verified render" by reading an aircraft count over serial while the screen was wrong). The human saw it within seconds (TASK-312); where a human-eyeball criterion WAS written into the exit criteria, the gate worked exactly as designed. (part 3) M-CEEFAX (LL-115) was accepted "closed" after an exhaustive DMA-leak / coexistence analysis while it had **never once connected** — the analysis characterized a permanently-failing feature and mis-read its failure signatures as findings; its very rigor created false confidence. The acceptance harness (`ceefax_connect_check.py`, exit 0 only on real connect+acquire+no-crash) that would have caught it on day one was only built during the recovery, after a one-line human "I've never seen it working" prompt exposed the miss.
**Applies to**: Developer (new apps, NEW-APP-CHECKLIST; build the primary-function gate before characterization work), VE (test-plan honesty about the serial/soak observability boundary — signatures are not "it works"), PM (exit-criteria wording on render AND transport/playback tasks; do not accept a feature or trust its perf/memory characterization without the gate green), Architect (operationalize ADR acceptance criteria into a concrete on-device demonstration, not a prose standard), QM (review-scope audits)

---

### BP-047 — A fix landing in duplicated logic either extracts the shared helper in the same commit or names the sibling sites

**Adopted from**: LL-110
**Date adopted**: 2026-07-12 (human)
**Rule**: Before committing a fix, grep for other sites that duplicate the logic being fixed (same field written, same call sequence, same table). Either (a) extract the shared helper so the fix lands once, in the same commit, or (b) apply the fix to every sibling, or (c) name the unfixed siblings in the task resolution as explicitly out-of-scope. A fix silently applied to one of N copies is a divergence, not a fix.
**Rationale**: TASK-308 fix 5 (disc repaint on range change) went into `handleInput()` while its duplicate in `dbgSet("prRange")` kept the bug — caught only by the next day's duplication audit (TASK-309 finding 3). One layer down, the `init()`/`resume()` preset-clamp duplication is what created TASK-308 fix 2 in the first place. Both divergences were created by patching one copy under time pressure; neither was findable by testing the fixed path. The audit that caught them was hunting duplication on a human hunch, not hunting bugs — periodic duplication audits are cheap relative to what this one caught (3 bug-class defects).
**Applies to**: Developer (fix workflow), QM (retrospectives: check fresh fixes for sibling sites), PM (scheduling periodic duplication audits on mature apps)

---

### BP-046 — A design doc's "the preview/PoC tool confirms X" claim must be checked against the tool's source, not just its screenshot

**Adopted from**: LL-105
**Date adopted**: 2026-07-11 (human)
**Rule**: Before accepting a design-doc line that says a preview or PoC tool "confirms," "validates," or "closes" a specific claim (a precision choice, a data-driven overlay, a threshold), grep the tool's source for the code path the claim depends on. A rendered screenshot or a verbal eyeball proves *a* render happened, not that the render exercised the claimed, production-representative value or that the feature exists in the tool at all.
**Rationale**: M-PLANERADAR's `phase0-preview-ui.md` closed six design questions against `preview_planeradar.py`; two didn't hold up. Q4 (runway label density) was written up as a question the tool would answer, but the tool had no runway-drawing code at all — only a stray color constant. Q6 (whole-degree heading rendering) got a human "looks fine" verdict against full float precision, not the whole-degree `int16_t` rounding the firmware design actually commits to (`phase0-parse-heap.md:108`). Both were only caught by reading the tool's source against the specific claim, after the doc already read as closed — the same failure shape the designer-review round had already caught twice earlier in the same milestone (a fetch-radius undercount, an unmeasurable heap-allocator claim).
**Applies to**: Architect (design docs citing tool-confirmed claims), Developer (building the PoC tool itself), QM (spot-check tool-confirmed claims during doc-currency audits)

---

### BP-045 — Latency before/after comparisons record a device-internal clock alongside the external clock, in the same session

**Adopted from**: LL-101  
**Date adopted**: 2026-07-07 (human)  
**Rule**: Any before/after latency measurement on a SERIAL_DEBUG build must record a device-internal clock (a `perf::record` slot or equivalent on-device timestamp delta) in the *same session* as the host-side external clock, and any delta that appears only on the external clock must be attributed (e.g. to serial wire time — ~0.087 ms/byte at 115200 on a saturated TX buffer) before being treated as a regression. When adding log lines inside a latency-measured region, count their bytes into the measurement plan.  
**Rationale**: TASK-279: the instrumentation added to measure the feature was itself the largest measured "regression" — three new debug lines (~126 bytes/tap) shifted tap-to-switch-committed by +11–13 ms on the host clock. The in-session `shell.switch` internal clock (median 84–98 ms, matching the BEFORE external medians) is what proved switch cost unchanged; without it the delta would have read as real feature cost and invited a pointless optimisation hunt.  
**Applies to**: VE (measurement-plan checklist: internal clock named before the campaign runs), Developer (a perf slot accompanies any new stable-prefix lines inside measured regions), Architect (design measurement plans specify both clocks)

---

### BP-044 — No "root-caused" status without the fix stopping the original repro on hardware

**Adopted from**: LL-097  
**Date adopted**: 2026-07-07 (human)  
**Rule**: A crash/defect may be recorded as "root-caused" only after its candidate fix demonstrably stops the *original* repro on the DUT. Until then the status is "hypothesis (source-supported)". The verification set must include at least one known-good control case (an input expected to work) — a fix that "works" only on the failing cases and a theory that never faced a control are both unfalsified.  
**Rationale**: TASK-286: a source-reading root cause for a device-rebooting watchdog crash was internally coherent, cited real code, was written up as "confirmed" — and was wrong. The falsifying evidence cost one 30-second DUT run; the control URL (a fast, healthy stream that still crashed) is what broke the theory. The real chain (tlsYield starvation → yield refcount race → wr-idle ack deadlock) was only found because every fix was re-run against the original repro before being believed.  
**Applies to**: Developer (status discipline in tasks.md/commit messages), VE (repro + control case in every crash verification plan), QM (challenge any "root-caused" claim lacking a repro-stopped-on-DUT citation)

---

### BP-001 — Verify derived values before adopting into specs

**Adopted from**: LL-020  
**Date adopted**: 2026-05-16  
**Rule**: Any R&D report value that is *computed* from measurements (format conversions, scale factors, timing calculations) must include the derivation formula or a one-line verification command; the Architect runs that command before adopting the value into a design doc.  
**Rationale**: Measured and computed values can coexist in the same table and look equally authoritative. Computed values can silently be wrong — 16/16 RGB565 colour values in M-VIS were incorrect due to a misapplied conversion formula, caught only on DUT visual inspection. A 30-second Python check at spec time would have prevented the bug.  
**Applies to**: R&D Engineer (label columns as measured vs derived; include formula), Architect (do not adopt a derived value without running the verification)

---

### BP-002 — Commit a canonical bake script alongside generated artifacts

**Adopted from**: LL-021  
**Date adopted**: 2026-05-17  
**Rule**: For every bake tool that produces committed generated artifacts, commit a companion shell script containing the exact invocation. The script is the canonical recipe; update it in the same commit as any regenerated artifact.  
**Rationale**: Bake flags (boost, smoothing, offsets, frame trimming) are invisible inside the generated C/header files and are not consulted from commit messages before re-running a tool. A shell script is a file — it gets read, diffed, and updated as part of normal workflow.  
**Applies to**: Developer, R&D Engineer

---

### BP-003 — File a separate bug task for every known regression at close time

**Adopted from**: LL-022  
**Date adopted**: 2026-05-22  
**Rule**: A task with a documented functional regression in its notes must not be closed as `done`. File a separate bug task at close time — owner, status `planned`, reference to parent task — before marking the parent done.  
**Rationale**: Prose caveats in task notes have no owner and no deadline. They are not surfaced by any dashboard or review step. A known, identified fix can sit unresolved for days and return to the user as a re-reported bug. A task entry creates pressure and traceability. Concrete incident: TASK-021 closed `done` with a 5-line fix named in the notes; bug returned to user 6 days later.  
**Applies to**: Developer (file the bug task before closing), PM (reject `done` status if a regression caveat has no associated bug task)

---

### BP-004 — Mirror every physical-touch branch in `injectTouch()` in the same commit

**Adopted from**: LL-023  
**Date adopted**: 2026-05-22  
**Rule**: Any new action branch added to `checkForInput()` (physical touch path) must be mirrored in `injectTouch()` in the same commit. Both methods carry a co-location comment enforcing this invariant.  
**Rationale**: `injectTouch()` is the VE harness's only path for injecting touch events. A branch absent from `injectTouch()` silently falls to DEADZONE — the harness dispatches `ACT_FORCE_POLL` and reports no error, so tests can appear to pass while the action under test never fires. Divergence is invisible without a running test. Concrete incident: PLEDIT tap branch missing from `injectTouch()` for 7 days; T115's first run exposed it via `'hit':'DEADZONE'`.  
**Applies to**: Developer

---

### BP-005 — `test_ids: []` on an implemented feature requires a VE task before `done`

**Adopted from**: LL-024  
**Date adopted**: 2026-05-22  
**Rule**: An `implemented` feature in `feature_inventory.yaml` with `test_ids: []` must have a corresponding VE task in `tasks.md` (status at least `planned`) before the feature is declared `done` at the roadmap level. PM files the VE task at feature close; VE populates `test_ids` when tests pass.  
**Rationale**: `test_ids: []` is a visible signal in the YAML but creates no work item and no deadline. VE audit notes recorded only as YAML prose age silently — no owner, no trigger to act. A tasks.md entry gives the gap a deadline and an owner. Concrete incident: `playlist-001` test gap open 7 days with only a YAML annotation; tests found an additional infra bug (`injectTouch` divergence) when finally written.  
**Applies to**: PM (file VE task at feature close), VE (own and close the task), Developer (do not ship features expecting `test_ids` to be filled in "later")

---

### BP-006 — Visual sign-off for range-dependent renderers must cover zero, max, and one intermediate state

**Adopted from**: LL-025  
**Date adopted**: 2026-05-23  
**Rule**: Any renderer whose output depends on a runtime value (scroll offset, volume, position) must be sign-off tested at three states — minimum (0), maximum, and one mid-range value — before the implementing task is closed. PM records user sign-off using the user's exact words, not a paraphrase.  
**Rationale**: "Correct at rest" does not validate range-dependent code paths. A bug in the scrollbar thumb X offset was missed because sign-off was given only at the resting/zero state; the visual defect only appeared during scrolling. Additionally, PM paraphrasing "moves to the right" as "Y position wrong" misfiled the axis, wasting a full audit cycle and multiple flash iterations. Exact-quote policy eliminates the paraphrase error class.  
**Applies to**: VE (define test cases covering min/max/mid before task closes), PM (record user sign-off verbatim, never paraphrase visual bug descriptions), Developer (do not close range-dependent renderer tasks without VE sign-off on all three states)

---

### BP-007 — Reference image consumed → paired visual validation item required

**Adopted from**: LL-026  
**Date adopted**: 2026-05-23  
**Rule**: Any element whose position, size, or colour is derived from a reference image must have a paired VE or audit item that validates rendered output against that image before the task is closed. The validation item is filed at the same time the reference image is first cited in the design.  
**Rationale**: Reference images contain the ground-truth pixel data needed to verify placement. When validation is skipped, implementation values are guessed and the human is forced to iterate through flash-observe cycles to converge on the correct pixel offset. This is expensive and degrading. Concrete incident: `resource/winamp_reference_cropped.png` was available from project start and examined by R&D (TASK-075), but no VE item was filed for thumb X placement; 5+ flash cycles with human pixel feedback were required to arrive at `PLEDIT_THUMB_X_INSET = 4`. A single image measurement would have produced the correct value immediately.  
**Applies to**: R&D Engineer (flag reference images as requiring paired validation when cited in reports), Architect (do not finalise a design that cites a reference image without a linked VE validation item), VE (own the validation item; measure from the image, do not accept "looks right"), PM (reject task close if reference image was cited and no validation item exists)

---

### BP-008 — Run check_build.sh before and after every structural change

**Adopted from**: restructure pre-gate (2026-05-24)
**Date adopted**: 2026-05-24
**Rule**: Run `./check_build.sh` from the project root before starting any structural change (file moves, `#include` edits, entry-point rewrites) and again after completing it. Do not commit a structural change that fails the script.
**Rationale**: The DUT-based test suite requires physical hardware and cannot catch compile errors during a refactor. `check_build.sh` is the only automated gate that runs on the local machine without a board. When it was first run, it immediately surfaced a pre-existing compile error (`PLEDIT_THUMB_X_INSET` undefined) that had gone undetected because no build check existed. Without this gate, `#include` breakage, missing constants, and symbol errors accumulate silently until someone next flashes the board.
**Applies to**: Developer (run before/after every structural change), PM (do not close restructure tasks without confirming check_build.sh exit 0 on the final state)

### BP-009 — Structural refactors must include a grep-for-old-paths step and tool-script smoke test

**Adopted from**: LL-029
**Date adopted**: 2026-05-24
**Rule**: Any task that moves a file or directory must include an explicit sub-step: `grep -rn "OldPath" movedDir/` before the task is closed. For Python tool scripts, confirm `python3 -c "import module"` from the new location. For shell scripts, confirm `--help` (or a dry-run invocation) completes without `No such file or directory` errors.
**Rationale**: Path strings inside scripts are structural coupling to the file's old directory context. A file move that does not update internal path strings is an incomplete migration — equivalent to leaving a broken `#include`. The class of breakage is silent until the first consumer runs: no compile error, no git warning, no `check_build.sh` failure. M-RESTRUCTURE moved six scripts with stale path strings; the T102 harness crash on 2026-05-24 was the first consumer to hit it. A one-command grep would have caught all six in under 10 seconds.
**Applies to**: Developer (add grep + smoke-test step to every restructure task), PM (reject restructure task `done` without grep confirmation or smoke-test evidence), Architect (include the grep step in any source-ownership migration design doc)

---

### BP-010 — VE task is not done until test_plan.md and feature_inventory.yaml are updated

**Adopted from**: LL-032
**Date adopted**: 2026-05-25
**Rule**: A VE task is complete only when: (1) test functions are written and passing; (2) an entry exists in `test_plan.md` for each new test ID (feature ID, objective, steps, status); (3) the feature's `test_ids` list in `feature_inventory.yaml` is populated. Writing passing harness functions without updating the canonical registries is step 1 of 3, not done.
**Rationale**: The harness (`run_serialdbg_tests.py`) is the execution path; `test_plan.md` and `feature_inventory.yaml` are the canonical record of what tests exist and what they cover. Tests absent from these registries are invisible to future audits — QM sees `test_ids: []` and flags a gap that no longer exists. Concrete incident: T_BI_01–T_BI_04 all pass on DUT but are absent from `test_plan.md` and `app-interface-001` is absent from `feature_inventory.yaml`. A future audit would miss them entirely.
**Applies to**: VE (own all three steps in the same session), PM (reject VE task `done` if `test_ids` list is still empty), Developer (do not accept a feature as tested without VE confirming registry updates)

---

### BP-011 — Write a PM handoff commit when a DUT session ends with unfinished verification

**Adopted from**: LL-033
**Date adopted**: 2026-05-25
**Rule**: When a DUT session ends with unfinished verification (port disconnect, hardware issue, test not yet written), write a dedicated PM commit before closing the session. Required content: (1) status per numbered sub-task; (2) current regression count with interpretation (which test failed and why); (3) NEXT AGENT TODO block — numbered, exact shell commands, expected output; (4) any context needed to interpret partial results. Format: `pm(TASK-NNN): handoff note — [one-line status]`.
**Rationale**: The receiving agent has no access to the prior session's conversation. Without a precise handoff, it must reconstruct context from git log and docs, and may misinterpret a partial count (e.g. 26/27 with a known fix committed but not confirmed) as a regression. A well-formed handoff commit eliminated that risk entirely in TASK-090h: the agent executed a four-step sequence from the handoff without reading history, and interpreted the 26/27 count correctly because the failing test was named.
**Applies to**: PM (write the handoff commit), Developer (prompt PM if closing a session with incomplete DUT verification)

---

### BP-012 — Tag known-intermittent tests; keep regression signal unambiguous

**Adopted from**: LL-034
**Date adopted**: 2026-05-25
**Rule**: Known-intermittent tests in `run_serialdbg_tests.py` must be tagged with a `# KNOWN INTERMITTENT: <reason> — first observed <date>` comment block. The pass/fail count in any session note must name the failing test, not just the number. If the suite grows to ≥5 intermittents, add a `[FLAKE]` result category distinct from FAIL so summary lines read "N passed, 0 failed, M flaked."
**Rationale**: Four known-intermittent tests in a 31-test suite means P(all-green) ≈ 66% per run with zero new regressions. "Not all green" becomes the expected baseline rather than a signal. When a real fix is confirmed by the count, any reader must cross-reference which test failed to distinguish flake from regression — one extra step that should not be necessary. Concrete incident: TASK-090h's first run was 26/27 with T087 as the intermittent; without naming T087, the 26/27 count was ambiguous.
**Applies to**: VE (tag intermittents at discovery; own the FLAKE threshold decision), Developer (add `# KNOWN INTERMITTENT` comment before merging any test known to fail intermittently), PM (require the failing test name — not just a count — in any session note or handoff)

---

### BP-013 — Queue-backed firmware tasks: assert completed fetch count, not commands fired

**Adopted from**: LL-041  
**Date adopted**: 2026-05-30  
**Rule**: Any test that drives a queue-backed firmware task (dataTask, etc.) must assert that the expected number of operations *completed*, not that the expected number of commands were *sent*. Use a monotonic ok-counter in firmware state, snapshot it before the triggering command, and poll until it advances.  
**Rationale**: FreeRTOS queues silently drop items when full. A burst of N taps may produce only `queue_depth` actual fetches — all subsequent taps are dropped with no error visible to the test. A test that asserts "N taps fired → all N ranges covered" will pass even when only 4 ranges were fetched. This pattern produced a false PASS in T186 (32 taps fired; only 4 D1/D5 fetches ran; Mo1/Ytd — the high-heap-pressure ranges — were never exercised). Fix: firmware `fetchOkCount` + `_wait_chart_complete(before)` in the harness. Pattern generalises to any queue-backed subsystem.  
**How to apply**: (1) Add a `uint16_t xyzOkCount` field to the relevant firmware state struct. (2) Increment it on every successful operation completion. (3) Expose via `dbgGet`/`dbgSet`. (4) In the test: `before = get xyzOkCount` → trigger → poll until `xyzOkCount > before`. Check `queue_depth` before sizing burst tests.  
**Applies to**: VE (own the counter pattern; never assert on commands-fired), Developer (add ok-counters when implementing queue-backed tasks), Architect (include ok-counter in interface spec for any queue-backed subsystem)

---

### BP-014 — Serial test harness: enforce thread ownership by assertion, not comment

**Adopted from**: LL-042  
**Date adopted**: 2026-05-30  
**Rule**: The `Dut` serial harness is not thread-safe. Ownership is enforced by recording `_owner_thread` at construction and calling `_assert_owner()` at the top of every method that reads or writes `self.ser`. Any cross-thread access must raise immediately — not produce a silent ACK loss 30 seconds later.  
**Rationale**: `Dut.cmd()` and `Dut.read_json()` assume exclusive ownership of the serial stream. A background thread reading `dut.ser` concurrently silently consumes ACKs intended for `cmd()`, causing intermittent `TimeoutError`s that look like timing issues and resist longer-timeout fixes. T186 required three implementation iterations before the root cause (background thread + serial contention) was identified. Once `_assert_owner()` was added, cross-thread misuse raises `RuntimeError` at the call site with an immediate diagnostic.  
**How to apply**: Fire-and-forget + drain-phase pattern for async log collection: send command → do not wait for ACK → sleep → read stream directly → query state. Never spawn a thread to read `dut.ser` while `cmd()` runs on the main thread.  
**Applies to**: VE (own the fire-and-forget pattern; never read `dut.ser` from a background thread), Developer (preserve `_assert_owner()` calls when adding new `Dut` methods)

---

### BP-015 — Test the actual firmware constraint, not a payload or capacity proxy

**Adopted from**: LL-040  
**Date adopted**: 2026-05-30  
**Rule**: Before writing a budget or size check in a host test, identify the *exact* constraint the firmware enforces and assert that — not a proxy metric that correlates loosely with it. When firmware uses a JSON filter, raw payload bytes are irrelevant; when firmware caps an array at N elements, assert element count ≤ N.  
**Rationale**: `test_yahoo_finance_api.py` T_SF_06 checked `len(raw_body) <= CHART_BUDGET_B`. After ADR-034 switched chart fetching to a JSON filter + `StaticJsonDocument<2048>`, raw payload size became irrelevant — the filter extracts only `close[]` before ArduinoJson allocates. The test gave false confidence for months. The real constraint was `non_null_close_count <= 110` (firmware's `chartPoints[110]` buffer cap). Fixing T_SF_06 to assert element count exposed the correct invariant in one line.  
**How to apply**: (1) Read the firmware parse path before writing the host budget check. (2) Identify: is there a filter? What buffer does the output land in? What is the firmware's cap? (3) Assert that cap directly. (4) If the firmware uses `DynamicJsonDocument(N)` with no filter, raw bytes ≤ N is a reasonable (if imprecise) proxy — but add a comment explaining why and apply a 1.5× safety factor.  
**Applies to**: VE (read firmware parse path before writing budget checks), Developer (document the effective constraint in a comment alongside any `StaticJsonDocument` or buffer-capped array)

---

### BP-016 — Tests must assert causal behavior, not initial state or trivially-true defaults

**Adopted from**: serialdbg audit 2026-05-30  
**Date adopted**: 2026-05-30  
**Rule**: A test that only reads a value that the firmware always initialises to a fixed constant, or that only asserts a field is non-negative, is not a test — it is an observation. Every test function must contain at least one assertion whose failure would indicate a real firmware defect, not just an unexpected initial condition.  
**Rationale**: The 2026-05-30 audit found 9 weak-assertion tests in the 78-test serialdbg suite. Representative examples: T136 asserts `scrollOffset=0` on startup (trivially true; proves nothing); T178 asserts `chartRange=D1` after `drillToChart()` (hardcoded in the function; cannot fail); T_GOL_04 asserts `golAlive >= 0` (asserts a uint is non-negative). None of these can catch a real regression. A test that cannot fail is not providing coverage — it is consuming run-time and creating false confidence.  
**How to apply**: For each test, ask: "What firmware defect would cause this assertion to fail?" If the answer is "nothing realistic", the assertion is wrong. Fix options: (a) replace the trivial assertion with a causal one (assert state *after* an action, not the initial state before it); (b) fold the initial-state check into the *setup* block of the test that exercises the behavior; (c) remove the test and document why the coverage is intentionally absent.  
**Applies to**: VE (apply the "what defect would break this?" test before finalising any assertion), QM (flag trivially-true assertions in audits as AMBER; escalate to RED if a suite has > 10% trivial tests)

---

### BP-017 — Verify SERIAL_DEBUG firmware is active before any VE test execution

**Adopted from**: LL-043  
**Date adopted**: 2026-05-30  
**Rule**: `run_serialdbg_tests.py` must probe for debug firmware immediately after DUT ready by sending `get heap` and raising `RuntimeError` with exact reflash commands if `unknown command` is returned. Any PM handoff that involves flashing must record the exact `pio run -e <ENV>` string used — a build timestamp alone is insufficient. Agent briefings that claim DUT state are claims to verify, not facts.  
**Rationale**: Production (`cyd2usb_winamp`) and debug (`cyd2usb_winamp_debug`) builds share the same build timestamp when compiled same-day. The heartbeat `build=<date>` output is identical; only a SERIAL_DEBUG command probe distinguishes them. Without the preflight, an agent receives `unknown command` from `set cooldown 0` and must trace firmware source to understand why — consuming 5–10 minutes before the first real test runs. This pattern recurred across multiple VE sessions (LL-043). With the preflight, the failure is instant and self-diagnosing.  
**Applies to**: VE (harness preflight is now automatic — no action needed beyond keeping `_verify_debug_firmware()` in `Dut.__init__`), PM (record exact `pio run -e <ENV>` in any handoff that involves a flash; "debug build" with no env name is not sufficient), All agents (treat any briefing claim about DUT state as a hypothesis; the harness verifies it at startup)

---

### BP-018 — DUT reset via host tools: wait ≥12s between any two resets; prefer physical button

**Adopted from**: LL-051  
**Date adopted**: 2026-06-04 · **Amended 2026-09-01 (TASK-555) — the original rationale is void and the replacement did not reproduce. Read the amendment before citing this.**  
**Rule**: Wait ≥12 s between any two DUT resets (opening a serial port on CH340 boards is a reset — the DTR pulse on open). **Retained as an unverified precaution, no longer as a derived requirement** — see the amendment. Enforced in code by `run/lib.sh::stamp_reset_gap()` + `lib/dut.py`'s gap file (TASK-559), not by hand-counting seconds.  
**Rationale — SUPERSEDED, recorded because it was acted on for three months**: `DoubleResetDetector` (DRD_TIMEOUT=10 s) treats two resets inside the window as a deliberate double-press and calls `startConfigPortal()`, which has no timeout and blocks indefinitely, so rapid resets turn a recoverable state into an infinite loop.

**Amendment, 2026-09-01 (TASK-555).** Both halves of the justification are now unsupported:

1. **The stated mechanism no longer exists.** `DoubleResetDetector` and `WiFiManager` were removed from the firmware in `ddf6433` ("remove WiFiManager/DRD; on-device connect UI", 2026-06-11) — **one week after this BP was adopted**. Nothing in `app/src/` has printed a portal banner since; the only surviving mentions are three stale comments. The harness's matching machinery (`_PORTAL_INDICATORS`, the `portal_seen` branch, its RTS-pulse auto-recovery and `portal-recurred` failure) was therefore unreachable for ~3 months while still reading as live safety code, and has been deleted.
2. **The replacement hazard did not reproduce.** The surviving candidate was TASK-376's note that back-to-back resets drop this CYD into download mode (silent port). Measured directly: two hard resets separated by 1/2/4/8/12 s, 3 trials each, then probed with `esptool --before no_reset` (a sync means the board is sitting in the ROM bootloader; a failure means the application is running). **0/3 wedged at every gap, including 1 s** — 15 trials, 30 resets, zero occurrences. The same run produced **zero USB re-enumerations**.

**Why the wait is kept anyway**: 15 trials is thin cover for a rare event, the measurement was taken on a rig whose stability is itself under investigation (TASK-557), and the gap now costs ~4 s per run and is enforced automatically. Cheap insurance beats re-deriving this under pressure.
**Retirement criterion**: if a larger sample (≥30 trials at ≤2 s, spanning both a quiet and a flapping rig) also shows zero wedges, retire the rule and delete the gap file machinery. **Coupling to check first (TASK-563)**: nine `run/` scripts no longer sleep after their flash — the gap file is now the *only* thing separating esptool's reset from the harness's port open in those. Retiring the gap therefore removes that separation entirely, rather than falling back to the old 8 s sleep. Either restore a post-flash wait in the same change, or satisfy yourself the separation is not needed at all. (The three raw-`serial.Serial` scripts — `ae04`, `wr-gate`, `wr-soak` — kept their sleep and are unaffected.) Until then **the number 12 is not derived from anything measured** — it is inherited from `DRD_TIMEOUT=10 s` plus margin, for a mechanism that is gone. Do not cite it as evidence-based, and do not tune other timeouts against it.  
**Applies to**: VE (harness startup: open port, wait ≥12s before any `cmd()` that might trigger a reset; document in `Dut.__init__` if it opens port on construction), Developer (any reset helper script must enforce the 12s gap), All agents (DUT recovery SOP: close port → single physical button press → wait 20s → reopen port → proceed). The former "recovering a DUT stuck in the WiFiManager portal" clause is deleted — that firmware left in ddf6433 and the state it described is unreachable (TASK-555)

---

### BP-019 — Resolve DUT serial port by USB VID:PID, never hardcode

**Adopted from**: LL-052
**Date adopted**: 2026-06-06 (pending human sign-off)
**Rule**: Use `./run/port` to print the resolved port, or `PORT=/dev/ttyUSBn ./run/<script>` to override. All `run/` scripts resolve the port automatically via `run/lib.sh::resolve_port()` (CH340 VID:PID `1A86:7523`). Never hardcode `/dev/ttyUSB0` or `/dev/ttyUSB1` in commands, scripts, or agent briefings.
**Rationale**: The port number is non-deterministic across sessions and hardware configurations. Re-discovering it manually costs time every session and introduces copy-paste errors (wrong port in flash command after looking it up for monitor). A VID:PID lookup is deterministic and self-documenting.
**Applies to**: All agents and humans — use `./run/<script>` and port resolution is automatic. Only use `./run/port` directly when you need to inspect or log the port value.

---

### BP-020 — Pre-validation sequence: kill monitor → debug flash → test → prod flash → restart monitor

**Adopted from**: LL-053
**Date adopted**: 2026-06-06 (pending human sign-off)
**Rule**: Use `./run/test` (full suite) or `./run/test-targeted T1,T2,...` (feature-specific). These scripts enforce the 6-step sequence atomically with a `trap EXIT` restore guarantee — do not issue the raw steps manually. If the `run/` scripts are unavailable, the manual sequence is: (1) `tmux kill-session -t spotify-mon`, (2) `pio run -e cyd2usb_winamp_debug -t upload`, (3) `sleep 8`, (4) `tools/suite/serialdbg/runner.py` (TASK-480), (5) `pio run -e cyd2usb_winamp -t upload`, (6) restart monitor. Never skip steps 1 or 2.
**Rationale**: Two of the three failed launch attempts in the 2026-06-06 session were caused by skipping steps 1 and 2 respectively. Each failure consumed a serial-port-open + Python startup + error-read cycle (~30-60s each). The `run/test` trap ensures prod firmware is restored even on Ctrl-C or mid-step failure.
**Applies to**: VE (mandatory pre-run checklist), All agents (treat this as an atomic operation — do not split across turns)

---

### BP-021 — Use targeted test IDs for new-feature validation; reserve full suite for regression

**Adopted from**: LL-054
**Date adopted**: 2026-06-06 (pending human sign-off)
**Rule**: When validating newly implemented features, run only the relevant test IDs: `./run/test-targeted T-SET-01,T-SET-02,T-SET-08` (example). For the always-passing smoke preset: `./run/test-smoke`. Run `./run/test` (full suite) only for regression checks after refactors or cross-cutting changes.
**Rationale**: The full suite takes 8-10 minutes; settings tests are near the end. Launching the full suite after implementing settings sections made the agent wait through stock/crypto/weather/GoL tests before seeing any relevant output. Targeted runs give signal in < 30s.
**Applies to**: VE (document filter presets in `docs/process/dut_workflow.md`: smoke, settings, stock, per-feature), PM (schedule full regression suite only at milestone boundaries, not after every feature)

---

### BP-022 — Calibration arithmetic: desk-check extrapolation targets before flash; state sizeX/Y_px explicitly

**Adopted from**: LL-055
**Date adopted**: 2026-06-06 (pending human sign-off)
**Rule**: Any calibration computation that extrapolates from tap targets to screen edges must state the driver's `sizeX_px` / `sizeY_px` values (320/240) explicitly in a comment, and must be desk-checked: verify that each of the four extrapolated edges equals 0, 319, 0, 239. Any `map(raw, calMin, calMax, 0, X)` where X ≠ sizeX_px (or sizeY_px) is a bug.
**Rationale**: Two separate calibration bugs (xMax extrapolation and marker mapping) both stemmed from using 274 (canvas width − 1) instead of 319 (screen width − 1). Both were detectable without hardware. Neither was caught before flash because no desk-check step existed.
**Applies to**: Developer (calibration or coordinate-transform code: comment the driver contract, desk-check the four edge values), VE (code review checklist: check any `map(raw, ...)` against driver sizeXY)

---

### BP-023 — Write a harness sync contract before the first test that uses a new sync mechanism

**Adopted from**: LL-059
**Date adopted**: 2026-06-08
**Rule**: Before writing any test that relies on a new harness synchronisation mechanism (polling flag, fetch counter, context manager, sleep margin), write a two-sentence contract: "this mechanism proves X; it is unreliable when Y." Commit the contract alongside the mechanism.
**Rationale**: The regression harness accumulated 8 fix commits on 4 tests because the sync assumptions were never written down. Locally-working tests with invisible assumptions are fragile; the contract makes failure modes explicit so later authors know when they can and cannot rely on the mechanism.
**Applies to**: VE (contract author), Developer (must not merge sync mechanism without contract)

---

### BP-024 — VE authors a debug variable spec before implementation; Developer ships it with the feature

**Adopted from**: LL-060
**Date adopted**: 2026-06-08
**Rule**: For each new feature, VE authors a debug variable spec before implementation begins, stating: what state must be readable (`get`), what state must be writable (`set`), what events must be emitted. Developer implements `dbgGet`/`dbgSet` handlers as part of the feature — not as a follow-up task.
**Rationale**: Every "missing debug var" bug in this project was caused by shipping firmware without a matching observability interface, then backfilling it when a test needed it. Backfilling always introduces a gap period where the feature is untestable. Front-loading the spec closes this gap at zero extra cost.
**Applies to**: VE (spec author, gate on testability before feature is marked done), Developer (debug interface is part of the feature, not optional)

---

### BP-025 — A suppression flag and its consuming guard are one atomic commit

**Adopted from**: LL-062
**Date adopted**: 2026-06-08
**Rule**: Never commit a suppression flag (`_injectingDrag`, `_skipXxx`, etc.) without also committing the guard that reads it in the same PR/commit. If the guard cannot be written yet, leave the flag out entirely.
**Rationale**: `_injectingDrag` was dead state for the entire period between its introduction and TASK-158. The `!touched` branch kept firing `tbGestureEnd` during serial drag injection, producing wrong scroll offsets. The flag conveyed false confidence that the problem was handled. Dead state is actively harmful — it misleads readers and masks bugs.
**Applies to**: Developer (never ship the writer without the reader), VE (flag-without-guard is a code review finding)

---

### BP-026 — Express count-derived test constants symbolically; never hardcode a numeric value when the count can change

**Adopted from**: LL-063
**Date adopted**: 2026-06-08
**Rule**: Any test constant derived from `APP_COUNT`, `AppId::COUNT`, or a similar registry-driven count must be written as `APP_COUNT` (or `APP_COUNT - k` with a comment explaining which items are excluded and why). Never substitute the current numeric value — it will silently diverge the next time an app is added or removed.
**Rationale**: `_TB_N = APP_COUNT - 1` preserved the value 8 when APP_COUNT became 9, causing T165 to expect wrap-at-8 while the firmware wrapped at 9. The fix was one character (`APP_COUNT` instead of `APP_COUNT - 1`), but the bug survived multiple DUT runs undetected because the numeric form looked plausible.
**Applies to**: VE (write `APP_COUNT` not `8`; grep for hardcoded count values when appRegistry.h changes), Developer (same; announce appRegistry.h changes to VE)

---

### BP-027 — Safety-property claims require a preservation test and a missing-target test at feature close

**Adopted from**: LL-064  
**Date adopted**: 2026-06-11  
**Rule**: When a feature's spec, description, or task body contains a safety-property word — *non-destructive, preserving, atomic, idempotent, safe, clean* — the VE exit criteria must include (1) a test that verifies the property holds under normal use, and (2) a test that verifies correct behaviour when the target does not exist. A happy-path smoke test does not satisfy a safety-property claim.  
**Rationale**: TASK-161 (`run/spiffs`) was closed after `ls` returned 5 filenames. The feature's primary claim was "non-destructive." That claim was never tested. An EXIT trap defect (monitor not restored on failure) also existed at closure. Three recovery tasks (TASK-163/164/165) were required.  
**Applies to**: VE (write the required tests before approving closure), Developer (do not close a safety-property feature without VE sign-off on preservation test), PM (reject closure if VE sign-off absent on safety-property features)

---

### BP-028 — Design doc code snippets intended for direct use must be reviewed for unconditional side effects before implementation

**Adopted from**: LL-065
**Date adopted**: 2026-06-11
**Rule**: Any code snippet in a design doc that is likely to be copied verbatim into production must be reviewed for unconditional side effects at design time. If it cannot be reviewed to that standard, annotate it explicitly: *"pseudocode — do not copy; verify side effects at implementation."* The implementer must then treat the snippet as a starting point, not a ready-to-paste solution.
**Rationale**: The PATCH-003 snippet in `M-SETUP-WIZARD.md` used `WiFi.persistent(true)`. Copied verbatim, this flag writes credentials to NVS unconditionally — before the connection attempt succeeds. A wrong SPIFFS password silently destroyed the device's saved WiFi state. The bug was invisible to build checks and happy-path tests; only a deliberate bad-credentials VE test (T-SETUP-10) caught it. Fix was one word (`false`), but required a recovery flash.
**Applies to**: Architect (annotate design doc snippets that cannot be fully reviewed at design time), Developer (treat design doc code as a starting point; audit side effects before committing), VE (include an error-path test whenever implementation was driven by a design doc code snippet)

---

### BP-029 — "Continue" on a cold session resume does not skip a pending human gate

**Adopted from**: LL-066  
**Date adopted**: 2026-06-12  
**Rule**: Before proceeding with the next planned task at session start, check `tasks.md` for any gate marked *"waiting on human"*, *"review gate"*, or *"human step"*. If one exists, surface it to the human before implementing — do not treat "continue" or a resumption prompt as implicit approval to cross the gate.  
**Rationale**: At end of M-TASKBAR-ICONS, the icon overview had been shown and the user sent an empty message (reviewing). Session ran out of context. Next session the user typed "continue" — the agent implemented the full bake script and `taskbar.h` wiring past an explicit review gate in `tasks.md`. The user was surprised. The work was acceptable, but the decision was the user's to make, not the agent's to infer.  
**Applies to**: All agents (read `tasks.md` at session start before the first tool call on a new task), PM (mark gates explicitly with the word "gate" or "waiting on human" so they are unambiguous stop signals)

---

### BP-030 — Validate pinned TLS root CA against the live cert chain before closing a feature that adds a new HTTPS endpoint

**Adopted from**: LL-067  
**Date adopted**: 2026-06-12  
**Rule**: When a new pinned root CA is added to `dataTaskCerts.h` (or any similar cert store), run `openssl s_client -connect <host>:443 -showcerts 2>/dev/null | grep issuer` at commit time and verify the root matches. Add the host to the ADR-029 rotation table with a quarterly check date. When a TLS-backed test fails with HTTP -1 ("connection refused"), check the live cert chain first before diagnosing code.  
**Rationale**: CoinGecko rotated from Google Trust Services (GTS Root R4 / WE1 intermediate) to Let's Encrypt (ISRG Root X1 / YE1 intermediate). The pinned CA was stale; every CoinGecko fetch returned -1 silently. Diagnosis required adding a `cryptoHttpCode` dbgGet surface because the raw HTTP code was only visible in serial LOG_D output, which the test harness does not capture.  
**Applies to**: Developer (validate cert at pin time; add to ADR-029 rotation table), VE (when a network-backed test returns HTTP -1 persistently, run `openssl s_client` before filing a code bug)

---

### BP-031 — All dataTask HTTPS fetchers call tlsYield/tlsResume; omitting either requires measured justification

**Adopted from**: LL-071
**Date adopted**: 2026-06-14
**Rule**: Every new HTTPS fetch added to `dataTaskStorage.cpp` must call `spotifyTask::tlsYield()` before allocating `WiFiClientSecure` and `spotifyTask::tlsResume()` after `http.end()` (and in every early-return path). Omitting either call requires a measured, ADR-recorded justification — "small fetch" or "fast fetch" is not sufficient.
**Rationale**: TLS contention is about concurrent open sessions, not response size. Spotify's persistent session holds ~40 k contiguous heap. A new TLS handshake for any host needs ~50–70 k contiguous. If Spotify's session is open simultaneously, the new connection will fail under heap fragmentation — regardless of how small or fast the intended transfer is. T272 confirmed real contention for `fetchTeletext()` (the smallest fetch in the project, 1.1 KB) after ADR-044 explicitly said it was safe to omit tlsYield. The pattern is already established by `fetchWeather`, `fetchCrypto`, `fetchHeatmap`, `fetchStockChart` — new fetchers must match it by default.
**How to apply**: Before `WiFiClientSecure client; HTTPClient http;` → call `spotifyTask::tlsYield();`. After `http.end();` (and in any early-return or error path) → call `spotifyTask::tlsResume();`. If the code path exits via multiple branches, add tlsResume to every exit point before the function returns.
**Applies to**: Developer (implementation default for any new `fetchXxx()` in dataTaskStorage), Architect (any ADR that proposes omitting tlsYield for a new fetcher must include measured maxAlloc evidence)

---

### BP-032 — Use unsigned underflow to force an immediate fetch on app entry; never assign `_lastFetch = 0`

**Adopted from**: LL-072
**Date adopted**: 2026-06-14
**Rule**: To make a periodic-fetch app enqueue immediately on `init()` or `resume()`, assign: `_lastFetch = millis() - (unsigned long)_pollSecs * 1000UL;`. Never assign `_lastFetch = 0` with the intent of forcing an immediate fetch.
**Rationale**: `_lastFetch = 0` means "last fetch happened at device boot (millis≈0)." The fetch condition `millis() - _lastFetch >= pollSecs*1000` is only satisfied after the device has been running for `pollSecs` seconds — if the device just booted and uptime < pollSecs, the condition is false and no fetch is enqueued. The unsigned underflow form sets `_lastFetch` such that `millis() - _lastFetch = pollSecs*1000` exactly at any uptime, guaranteeing the condition is true on the very next `tick()`. `TeletextApp` used `_lastFetch = 0` in three places (including `resume()` with an explicit "force immediate fetch" comment) and failed to enqueue within the first 60s — diagnosed only by T272. Apps to audit: any `init()` or `resume()` that assigns `_lastFetch = 0`, `_lastWeatherFetch = 0`, or similar.
**How to apply**: Use a `_forceNow()` inline helper: `unsigned long _forceNow() const { return millis() - (unsigned long)_pollSecs * 1000UL; }`. Call `_lastFetch = _forceNow();` in `init()`, `resume()`, and any trigger path that must force an immediate fetch.
**Applies to**: Developer (required pattern for all periodic-fetch apps; audit existing apps with `_lastFetch = 0` pattern), VE (test that switching to an app immediately enqueues a fetch within 5 s, not only after the first full poll interval)

---

### BP-033 — Use memchr/memcmp for HTTP response bodies that may contain null bytes; never String::indexOf()

**Adopted from**: LL-073
**Date adopted**: 2026-06-14
**Rule**: Any HTTP response body in a non-ASCII or binary-capable encoding (ISO-8859-1, Latin-1, Windows-1252, protocol with embedded control codes) must be parsed using `memchr()`/`memcmp()` over the raw buffer (`body.c_str()` + `body.length()` bound). Never use `String::indexOf()`, `String::lastIndexOf()`, `strstr()`, or `strchr()` on such bodies.
**Rationale**: Arduino `String::indexOf()` delegates to `strstr()`, which treats `\0` as a C-string terminator. ISO-8859-1 teletext content legitimately uses bytes 0x00–0x1F as color and mode control codes. The NOS Teletekst response body has `\x00\x00` at positions 1065–1066, immediately before `</pre>` at 1067. `body.indexOf("</pre>")` returned -1; the parse failed silently with "no `<pre>` block" despite a successful HTTP 200 fetch. The failure is silent (returns -1, not an exception) and is indistinguishable from a format change in the API — making it especially difficult to diagnose. Sister rule to BP-015 (test the actual firmware constraint) and LL-017 (a library that produces output is more dangerous than one that errors).
**How to apply**: After `http.getString()`, work via raw pointer: `const char* raw = body.c_str(); int rawLen = (int)body.length();`. Search for a tag: `for (int i = 0; i <= rawLen - tagLen; i++) if (memcmp(raw + i, tag, tagLen) == 0) { found = i; break; }`. Document the encoding in a comment alongside the parse code.
**Applies to**: Developer (any new HTTP response parser: check the server's `Content-Type` encoding and apply this rule if ISO-8859-1 or binary is possible), Architect (ADRs introducing new API endpoints must note the response encoding and flag if memcmp is required)

### BP-034 — A blocked test that covers a DUT behaviour must have a synthetic injection fallback; "blocked" is not coverage

**Adopted from**: LL-074
**Date adopted**: 2026-06-14
**Rule**: When a VE test is blocked by infrastructure prerequisites (live network G1, touch inject G2, etc.), a synthetic injection-based alternative must be designed that exercises the same code path before the parent feature milestone closes.
**Rationale**: T270 (subpage navigation) was correctly designed and would have caught the `parsePage("617-2")` data-loss bug. It was blocked on live network data with no fallback path using `set teletextPageContent` injection — the injection mechanism already existed. The bug persisted until first human DUT use. A test marked `[Blocked: G1]` with no alternative is a coverage gap masquerading as a plan.
**How to apply**: For any test blocked on G1/G2, ask: "Can I inject a synthetic response that exercises this code path?" If yes, design the injection variant as a sibling test and mark the G1/G2 variant as `[NETWORK]` optional. Injection interfaces (`set teletextPageContent`, `set cryptoPrice`, `dbgSet` variants) exist specifically to enable this. If no injection path is possible, flag the gap explicitly in the test plan and in the feature's `notes:` in feature_inventory.yaml.
**Applies to**: VE (required at test plan authoring time), Developer (must expose injection interfaces for any new complex input format at feature implementation time)

---

### BP-035 — Every "not yet implemented" placeholder in shipped code must be backed by a filed task

**Adopted from**: LL-075
**Date adopted**: 2026-06-14
**Rule**: Any code comment containing "not yet implemented", "TODO", "fallback", or "stub" must reference a filed task (`// TODO(TASK-NNN):`) before the feature milestone closes. Comments without a task reference are not tracked and will not be discovered by any process step.
**Rationale**: `_handleStrip()` shipped with `// Keypad not yet implemented — cycle through presets as fallback`. No task was filed. The feature_inventory did not flag it as partial. T271 expected `KEYPAD_OPEN` from VE's design — the correct test existed — but the implementation gap was invisible to the milestone close checklist. The placeholder was only caught by human DUT use. A comment is a note to self; a task is a commitment the PM and QM can track.
**How to apply**: At milestone close, `grep -r "not yet\|TODO\|FIXME\|fallback\|stub" app/src/` over changed files. Any hit that is not `TODO(TASK-NNN):` format must either (a) be replaced with a filed task reference before close, or (b) be explicitly marked `// intentional — no task needed` with a reason. QM includes this grep in post-milestone audits.
**Applies to**: Developer (at implementation time and milestone close), PM (milestone close gate), QM (post-milestone audit)

---

### BP-036 — When a new app is registered, verify it satisfies all active cross-cutting shell integrations

**Adopted from**: LL-076
**Date adopted**: 2026-06-14
**Rule**: When a new app is added to appRegistry.h, the Developer must check every cross-cutting shell integration that requires an app-side override and confirm the new app satisfies it (or explicitly defers with a filed task).
**Rationale**: `TeletextApp` was the 10th app added. It did not override `hasPendingAsync()` (default: `false`). `touch-004` was correctly marked `proposed` in feature_inventory but no new-app checklist enforced the connection. Missing `hasPendingAsync()` compiles cleanly and produces no visible failure at test level — the amber indicator simply never fires. The gap was only caught by DUT use. Silent default-returning overrides are the most dangerous kind of missing integration: they produce no error, no warning, no test failure.
**How to apply**: Maintain a short checklist in `docs/architecture/designs/` (or appRegistry.h comment) of required per-app integrations. Current list: (1) `hasPendingAsync()` — override if the app enqueues async work from `handleInput()`; (2) `tlsYield()`/`tlsResume()` — required for any new dataTask HTTPS fetcher (BP-031); (3) serial debug `dbgGet`/`dbgSet` surface for VE testability (BP implicit from LL-060). Add to this list as new cross-cutting mechanisms are introduced. QM audits the list against new apps at each milestone retrospective.
**Applies to**: Developer (at new-app integration time), Architect (must update checklist when new cross-cutting mechanisms are introduced), QM (retrospective audit)

---

### BP-037 — Use the minimum-sufficient helper: don't inherit live-data gates for injection-only tests

**Adopted from**: LL-081
**Date adopted**: 2026-06-15
**Rule**: A test that exercises state injection (`set wrState`, `set cryptoPrice`, etc.) must not call a helper that gates on live data (`count >= 1`, `get cryptoPrice > 0`). The helper must match the minimum precondition the test actually needs.
**Rationale**: T_WR_ERR_01–04 skipped on every run because `_webradio_enter_with_stations()` required `count >= 1`. The tests only needed the WebRadio app to be active; no station data was read. The gate was inherited by copy-paste from station-dependent tests without checking applicability.
**How to apply**: Before using a shared entry-point helper in a new test, list the helper's guards and verify each one is load-bearing for that specific test. If a guard is unnecessary, either use a leaner helper or extract one. Name helpers to make the distinction obvious: `_enter_app()` vs `_enter_app_with_stations()`.
**Applies to**: VE

---

### BP-038 — Read the test spec before diagnosing infrastructure

**Adopted from**: LL-082
**Date adopted**: 2026-06-15
**Rule**: When a test skips or fails, the first action is to read the test's spec doc and verify the implementation matches the stated preconditions and steps. Infrastructure or firmware diagnosis comes only after the test logic is confirmed correct.
**Rationale**: T_WR_ERR_01–04 skipped with "station list unavailable." The agent diagnosed radio-browser.info connectivity across two sessions before the user intervened. The actual fault was a wrong precondition in the test script — visible in under 2 minutes by reading `m-webradio-eject-errors.md`. The same observable symptom (SKIP) can indicate either a correct gate or a wrong gate; only the spec distinguishes them.
**How to apply**: On any unexpected SKIP or FAIL: (1) open the corresponding regression suite doc, (2) check each precondition against the test implementation, (3) check each assertion against what the firmware command actually does. Only proceed to DUT/network diagnosis if the test logic is confirmed correct.
**Applies to**: VE, Developer, All (especially in auto mode where human check-ins are absent)

---

### BP-039 — Reproduce a TLS/cert root cause with a host-side strict offline verify before accepting or shipping a fix

**Adopted from**: LL-083
**Date adopted**: 2026-06-20
**Rule**: A TLS or certificate-chain root cause is not accepted — and must never be shipped as a verification-disabling fix (`setInsecure()`, pin removal, etc.) — until it is reproduced on the host with the strict offline verification that mirrors on-device `setCACert()` behaviour: `openssl s_client -connect HOST:443 -servername HOST -CAfile <root-only.pem> -verify_return_error`. An issuer string or `-showcerts` chain-depth read is **not** sufficient — it shows what the server *sends*, not whether the pinned root *verifies*. Use `run/check-datatask-certs`, which runs this against every pinned endpoint using PEMs parsed from `dataTaskCerts.h`.
**Rationale**: TASK-214 shipped an unconditional `setInsecure()` (which ADR-029 rejects categorically) on the diagnosis that radio-browser.info omitted an intermediate cert. A 2-minute host strict-verify against the same root already pinned in firmware showed the chain verifying clean — contradicting the committed root cause. `-showcerts` (used in the original TASK-200 probe) had been available all along, but only its issuer/depth output was read, never the verify result. Only an offline strict verify reproduces what mbedtls does on the device.
**How to apply**: On any HTTP -1 / TLS handshake / "chain can't build" symptom: (1) run `run/check-datatask-certs` (or raw `openssl … -CAfile <root> -verify_return_error` for a one-off); (2) only if it genuinely fails to verify is a chain/cert change warranted; (3) if a verification-disabling fallback is truly unavoidable, make it conditional on the strict path failing, record which path fired (e.g. a `tlsInsecure` flag surfaced over serial), and escalate to the Architect for the ADR consequence before merge. Fold this check into ADR-029's quarterly cert review (supersedes the issuer-grep step in BP-030).
**Applies to**: Developer, VE, Architect, All

---

### BP-040 — An experiment/spike names its decision gate, FAIL artefact-disposition, and cleanup-task id before it is scheduled

**Adopted from**: M-WEBRADIO-NOPSRAM design-review cycle (QM blocker B1)
**Date adopted**: 2026-06-27
**Rule**: Any task tagged R&D / experiment / spike must, before it is scheduled, name (a) its decision gate (the measurable PASS/FAIL condition), (b) the artefact disposition on FAIL — branch abandoned / guards reverted / env removed, and (c) the cleanup-task id that executes (b) if any artefact already reached the trunk. A prose "it will be shelved" is not a disposition.
**Rationale**: An experiment without a teardown mechanism rots into a half-supported second code path. This is the same failure class as LL-085 (an under-exercised path that drifted into a latent crash) and the "prose-with-no-owner" pattern behind BP-003/BP-035 — a caveat in a doc has no owner and no trigger to act. Naming the cleanup task at schedule time gives the FAIL branch a deadline and an owner instead of leaving a dormant env/flag on the trunk. (Validated in practice: TASK-255 named TASK-256 as its cleanup id up front; when TASK-255 was parked/superseded, the incomplete `#ifndef WEBRADIO_ONLY` dispatch guard had a clear disposition and was reverted off trunk cleanly.)
**How to apply**: PM requires the three items before scheduling an experiment; Architect states them in the experiment design doc; R&D owns the EXP report and the branch disposition; QM audits for orphaned experiment branches/envs at retrospective. Pairs with BP-042 (the gate's *mechanism* must also be consistent with prior measurements — LL-086).
**Applies to**: PM, Architect, R&D, QM

---

### BP-041 — A `-D`-flag build variant kept past its experiment is added to `run/check` in the same change, or the flag is removed

**Adopted from**: M-WEBRADIO-NOPSRAM design-review cycle (QM candidate M2)
**Date adopted**: 2026-06-27
**Rule**: Any compile-time `-D` build variant (e.g. a new `[env:...]` with a distinguishing `build_flags` define) that is kept beyond its experiment must be added to the `./run/check` build-check gates in the same change that promotes it. If it is not added to the check, the variant and its flag must be removed. A build variant with no CI/check gate is not maintained. **Escape hatch:** a deliberately short-lived variant may instead be registered in a tracked exceptions list with an explicit expiry/owner — but the default is gate-it-or-delete-it.
**Rationale**: The two-variant build matrix is a maintenance liability that silently rots without a gate exercising it. LL-085 is the canonical instance: an under-exercised second path (the WebRadio taskbar slot) drifted for ~10 days into a latent null-pointer crash because nothing exercised it. The project already runs a multi-gate `run/check`; a flag-guarded variant that is not one of those gates will diverge from the default build the next time the shared code changes. The rule forces a binary choice — gate it or delete it — so a half-supported second firmware cannot linger.
**How to apply**: Developer adds the gate in the same change that promotes a variant, or removes the flag; Architect — any design that introduces a build-flag variant states its gate-or-remove disposition; QM audits `platformio.ini` envs against `run/check` gates at retrospective. (The `cyd2usb_webradio` env stays on its branch under TASK-255/256 precisely so it is not an ungated trunk variant.)
**Applies to**: Developer, Architect, QM

---

### BP-042 — A dependency pin that exists to dodge a known-bad version carries an inline note stating the version, the failure, and the safe range

**Adopted from**: TASK-258 / EXP-009 bare-rig
**Date adopted**: 2026-06-27
**Rule**: When a dependency (`lib_deps` / `platform` / toolchain) is pinned **specifically to avoid a known-bad version** (not just for general stability), the pin carries an inline comment in the same file stating: (a) the version/range that breaks, (b) the concrete failure mode (the error or the resource it blows), and (c) the known-safe range or the last-good version. A bare pin with no note is treated as incomplete — the next maintainer cannot tell a deliberate dodge from an arbitrary freeze and will bump it.
**Rationale**: A version number alone records *what* but not *why-not-newer*; the prohibition lives only in someone's memory or a buried experiment report. This is the "prose-with-no-owner / caveat-with-no-trigger" family (BP-003/BP-035, and the gate-or-remove logic of BP-041): the constraint must travel with the artefact it constrains. The project has already paid for this twice — the `espressif32@6.9.0` `Network.h` split *was* documented and saved a bump; the audio-lib v3.x boot-alloc was *not* until the EXP-009 rig added the note, and its value was promptly proven when a v2.0.6 swap failed on `SD_MMC.h: No such file` (v2.0.6 predates `AUDIO_NO_SD_FS`).
**How to apply**: Developer writes the note on any defensive pin and checks it before bumping; Architect — any design that pins a dep to dodge a version states the three items; QM audits pinned deps for bare-number pins lacking a why-not-newer note at retrospective.
**Applies to**: Developer, Architect, QM

---

### BP-043 — Fresh-agent handover prompts must include an explicit commit step

**Adopted from**: LL-095  
**Date adopted**: 2026-06-28  
**Rule**: Every handover prompt written for a fresh agent performing an implementation task must include an explicit final step: "Commit all changes on `<branch>` with a conventional commit message referencing the task ID."  
**Rationale**: Agents complete and verify code but treat committing as optional unless instructed. The omission is systematic — any prompt without a commit step reproduces the gap. Silent uncommitted state is caught only by `git status`, not by a passing build check, and requires PM to clean up manually.  
**Applies to**: PM

---

### BP-050 — Verify shared kit/library code at a real call site, not just at the include line

**Adopted from**: LL-112  
**Date adopted**: 2026-07-16 (renumbered 2026-07-18: originally mis-assigned "BP-047", colliding with the LL-110 duplication rule above — all repo-wide BP-047 citations mean LL-110)  
**Rule**: A shared header/widget kit's "compiles" close-out claim must be backed by at least one real call site exercising its actual intended construction syntax — not a bare `#include` with zero instantiations. If the type has toolchain-sensitive construction (e.g. structs with default member initializers under this firmware's pinned `-std=gnu++11` aggregate-init rules), that call site is exactly what would catch it.  
**Rationale**: TASK-328's Settings widget kit closed out as "compile-proven via appsSection.h include, run/check 6/6 PASS" while the header had zero actual widget instantiations at that point — the claim was true but hollow. TASK-321, the kit's first real consumer, broke on ordinary-looking `SButton{a,b,c}` brace-init because `SButton`/`SSpinner` have default member initializers, which disqualifies them from aggregate status under `-std=gnu++11`. One real button constructed and drawn in TASK-328 itself would have caught this before it reached a consumer.  
**Applies to**: Developer, QM (close-out review)

### BP-051 — Visual-asset work iterates approval on host contact sheets; a single batched DUT flash carries the BP-048 eyeball gate

**Adopted from**: M-ICON-PIXELART retrospective (2026-07-18 audit; companion to LL-114)
**Date adopted**: 2026-07-18 (human)
**Rule**: For work whose exit criteria are pixel-level assets (icons, skins, layout art): (1) all design/approval iteration happens on host-rendered contact sheets that show the **true shipped pixels** — rendered through the real bake pipeline (post-quantization, in simulated device context: real background, indicators, separators), not hand-approximated previews; (2) the human approves on the sheet BEFORE any asset lands in the source tree (`--install`-style gated copy, candidates live in a drafts dir); (3) the DUT is flashed **once per approved batch**, and that flash carries the BP-048 human-eyeball gate (host PNG ≠ TFT: RGB565 quantization, panel inversion, real backlight — the device look is still a named, blocking criterion; it just isn't the iteration loop). Preview tools used for this must obey LL-114: parse generated headers, render from the real source assets.
**Rationale**: M-ICON-PIXELART TASK-332/334 — nine icon pairs went through three full human review rounds (size triage, shape/spacing critique, per-glyph fixes like the asterisk-eye amputation) entirely on `BAKED_SHEET.png`/`NATIVE_SHEET.png`, with exactly one production flash at the end; the DUT eyeball passed first try. Contrast the pre-ADR-051 workflow the milestone was opened to kill: bake-flash-squint loops where fill ratios and double-resample artifacts were discovered on the panel, one flash per guess.
**Applies to**: Developer, VE (gate design), QM (close-out review)

### BP-052 — On subagent death, check for salvageable work before relaunching from scratch

**Adopted from**: LL-116
**Date adopted**: 2026-08-05 (human)
**Rule**: When a subagent with file-editing tool access dies mid-task (session/credit limit, crash, or any other non-report termination), check `git status`/`git diff` on its target files before deciding whether to relaunch. Review the diff for correctness and completeness against the original brief. If it's substantially complete, finish and verify it directly (host-side build gate at minimum, DUT verification where the task calls for it) rather than discarding it and re-running the same brief from a cold context.
**Rationale**: TASK-401's implementing subagent completed the entire feature — migration, storage, new UI sub-steps, debug getter, later confirmed correct against the design doc and the codebase's real interfaces — and was mid-way through a build-budget fix when it hit its session credit limit and never reported. Its terminal status (didn't finish) said nothing about whether the work product was usable; reviewing and finishing it in place took a fraction of a from-scratch relaunch and preserved implementation choices a fresh agent might not reproduce identically.
**Applies to**: PM (orchestration), any role driving subagents

### BP-053 — `.dram0.bss` overflow fix priority: shrink over-provisioned existing capacity before lazy-allocating new state, and don't bother relocating a pointer between class-member and file-scope

**Adopted from**: LL-117
**Date adopted**: 2026-08-05 (human)
**Rule**: When a new `SettingsApp` section (or any always-resident static object) overflows `cyd2usb_winamp_debug`'s `.dram0.bss` region at link time: (1) first look for existing static arrays sized larger than what they ever actually display/use (e.g. a scan-result buffer tracking more candidates than the UI ever renders) and shrink to the true need — verify behavior-preservation by reading the consuming code, don't guess; (2) only then reach for lazy heap-allocation (a single pointer, `new`d on first use, never freed) for the new feature's own bulk static data; (3) do NOT spend time relocating an already-necessary pointer between being a class member and a file-scope `static` as a space-saving move — measured twice (TASK-400 and TASK-401, 2026-08-05) to change the total link-time footprint by exactly zero, since the pointer's bytes exist somewhere in `.dram0.bss` either way. Measure with `nm --size-sort -S`/`size` diffed against a clean baseline build to find the real contributor, rather than assuming from `sizeof()` deltas alone.
**Rationale**: This is at least the fourth occurrence of this exact failure class on this board (three prior fixes — `TeletextApp::_nosSource()`, `webRadioApp.h`'s `wrPumpConnectUrlBuf()`, TASK-400's own `_confirmBtns()` — are cited as precedent directly in code comments but were never written up here), and TASK-401 additionally burned real effort on two plausible-looking fixes that turned out to be no-ops, because nothing recorded that pointer relocation doesn't work. `app/mem_manifest.yaml` explicitly scopes itself to heap-allocated JIT-arena buffers only — this static-segment failure class has no tracking mechanism at all.
**Applies to**: Developer, Architect (design docs adding new Settings sections should flag this risk explicitly, as M-SYS-REBOOT.md's own layout-capacity note already does for row budget)

---

### BP-054 — A task-closeout note that flags new, real, out-of-scope work needs a `TASK-NNN` or an explicit deferred marker — not free-form prose

**Adopted from**: LL-118
**Date adopted**: 2026-08-06 (human)
**Rule**: When a task's own closing write-up identifies a new, real issue that's out of that task's scope, don't leave it as free-form prose ("flagging for a separate task", "no task filed for it yet"). Either (a) file a `TASK-NNN` for it in the same editing session, or (b) if it's genuinely not worth tracking, say so explicitly and reasoned (e.g. "doesn't warrant tracked backlog on its own") — but if it IS worth tracking and isn't filed yet, mark the line `**Deferred, not filed:**` so it's greppable the same way `TODO(TASK-NNN)` already is in code (see the code-comment BP above this one). A closeout is not actually finished closing while a real flagged follow-up sits unfiled and unmarked.
**Rationale**: TASK-396's full audit of `tasks.md`/`tasks-archive.md` for this exact prose pattern found 7 instances: 3 already correctly filed later (just never cross-referenced), 1 already a deliberate reasoned drop, and 2 genuine gaps that sat unfiled for 2-4 weeks each (TASK-361's PlaneRadar-compression note → TASK-403; TASK-364's WiFi-cascade note → TASK-404) — one of which (a third instance, TASK-347's stale-`switchApp` note) was only discovered because a human hit the live bug on the DUT by eye, six days after it was first correctly identified and never filed. The failure mode is structural, not a one-off: nothing in the note's own prose distinguishes "new tracked-worthy finding" from "incidental color," and neither is discoverable by the task-number search this project's process actually relies on.
**Applies to**: PM (owns filing), Developer/VE/Architect/QM (whoever writes a task closeout)

---

## Candidates — proposed, pending human adoption

> These entries are **NOT yet adopted**. Per QM discipline ("QM brings best-practice
> candidates to human — never self-promotes"), they are recorded here in proposed form
> awaiting explicit human sign-off before being assigned a final BP number and promoted
> above this line. The latest **adopted** BP is BP-054 (BP-054 adopted 2026-08-06 from
> LL-118; BP-052/053 adopted 2026-08-05 from LL-116/LL-117; BP-051 adopted 2026-07-18;
> BP-050 is the 2026-07-16 LL-112 rule, renumbered from a colliding second "BP-047").

**LL-106** (M-PLANERADAR, 2026-07-11) — session-scoped scheduling primitives
(`CronCreate`) are the wrong default for work that must survive across
sessions/days; default to a durable tracker entry instead. Proposed, awaiting
human decision.

_(BP-044 adopted 2026-07-07 from LL-097; BP-045 adopted 2026-07-07 from
LL-101; BP-046 adopted 2026-07-11 from LL-105.)_

---

### BP-055 — An error value is not a diagnosis until you have named which return site produced it

**Adopted from**: LL-119 (LL-121 folded in as the third clause)
**Date adopted**: 2026-08-08 (human)
**Rule**: When a library or framework call returns an error value, open the callee and enumerate that value's return sites **before** forming a theory about the cause. If more than one site can produce it, identify which one fired and state it explicitly in the write-up; a diagnosis that cannot name its return site is a hypothesis, not a finding. If the evidence that distinguishes the sites is behind a suppressed log level, raising that level is the **first** diagnostic step, not an afterthought. And before attributing a below-bar measurement to a hardware component, obtain one independent measurement of that component off-target (host PC, second board, known-good reference part) and record it — where that is impossible, name it as an untested variable and hold the task open rather than closing on the negative.
**Rationale**: TASK-408 was handed off BLOCKED for a session on "runtime heap/concurrency corruption" that did not exist. `esp_vfs_fat_register()` returns `ESP_ERR_NO_MEM` from two unrelated sites — the `FF_VOLUMES` table being full, and a plain `calloc()` failing — and the first was assumed, then reasoned from ("on a table that should be empty"), then built on with a workaround whose 27 712 B cost was recorded as unexplained. It was the second site: the mount needs 24 964 B **contiguous** at Arduino's default `max_files=5`. The callee is fifteen lines and ships in the framework package on disk. Two things reinforced the wrong story: free memory was measured with `MALLOC_CAP_INTERNAL`, which counts the 32-bit-only D/IRAM region and so over-reports what a byte-addressable allocation can use (use `MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT` when the question is "can this allocation succeed"); and the one line naming the true site is a `log_e`, invisible at that build's `CORE_DEBUG_LEVEL=0`. The hardware clause comes from the same task: a clean, well-instrumented 5.9×-under result was written up as a hardware negative, and the card in question reads 9.5 MB/s on a host PC — the real cause was a second driver defect, and the fixed result came in 6.9× *over* the bar. Same family as BP-048 part 1 (a coherent but wrong source-read), with a cheaper disproof available than either prior instance.
**Applies to**: All

---

### BP-056 — A gate or acceptance report is written against the canonical id table, one row per id, including the rows with no evidence

**Adopted from**: LL-120
**Date adopted**: 2026-08-08 (human)
**Rule**: When reporting a gate, milestone acceptance, or any criteria-keyed result, source the id list from the **owning design or test document** — not from a task's restatement of it — and produce one row per canonical id, with the criterion quoted or paraphrased alongside the measurement. Ids with no evidence get explicit `NOT RUN` / `NOT MET` rows. Rows may not be renamed, merged, or dropped. If the report's id list is not literally as long as the gate's, it is incomplete by construction.
**Rationale**: TASK-408's post-fix report claimed "GATE PASSED" with 4 of 9 ids actually satisfied. The ids were taken from `tasks.md`'s one-line restatement — "**Gate:** `T_SD_01`–`09`", a range with no criteria — so the table got built outward from whatever the session had measured rather than inward from what was required. That construction *cannot* emit a NOT RUN row, which is exactly how `T_SD_09` (absent/unformatted card) disappeared from the report entirely. Worse, the two ids the VE had specified most carefully were the two mis-reported most confidently, because the restatement preserved the id and dropped the criterion: `T_SD_02` was claimed PASS on ~15 esptool hard-resets when its criterion reads "20 **power-cycles** (not esptool RTS reset — straps latch on reset and 'probably re-latches' is not a test)", and `T_SD_04`/`T_SD_05` were run under "actively redrawing", the exact phrasing VE-6 had already rejected as unreproducible after naming Aquarium at natural frame rate as the fixed load. `T_SD_07` was silently relabelled "directory walk" and answered with a 52-entry measurement against a ~200-file criterion. GPIO5 strapping is boot-loop class; that is not a formality to wave through.
**Applies to**: All (Developer/VE report gates, PM accepts them)

---

### BP-057 — Observing an asynchronous firmware trace needs one continuous capture; "the output never appeared" must be proven against raw serial before it is blamed on firmware

**Adopted from**: LL-122
**Date adopted**: 2026-08-11 (human)
**Rule**: When a test must observe a firmware log line that is emitted asynchronously — by a different FreeRTOS task than the one answering the command — the capture must span the command and the wait as a **single continuous read**. Never `dut.cmd(...)` followed by a separate reader loop: `read_json()` discards every non-JSON line while hunting for its ack, and anything printed in that window is gone. Use `_tap_and_wait_log()` (`app/tools/suite/serialdbg/_helpers.py`, TASK-480) or the same pattern. Independently of the harness: before attributing a "missing output" symptom to firmware, capture the raw serial stream once (`--log-file`) and confirm the output is genuinely **absent** rather than merely **unobserved**. A read helper that discards unmatched input must say so in its docstring and name what it is safe for.
**Rationale**: TASK-417's gate cost four agents and ~3 h on `T_PLR_17`/`T_PLR_06`/`T_WR_EJECT_01` failing as "dispatch did not reach spotifyTask" and "no TLS-reset log line within 8 s". A `LOG_FILE` capture showed the firmware had printed `[D][spotify.task] dequeued action=SHUFFLE param=1`, `action=REPEAT` and `hard reset — stopping client`, in order, in the exact second the tests reported them absent. The evidence was being consumed by the test's own transport before the test looked for it, which makes the defect invisible from inside the harness by construction — better assertions, longer timeouts and cleaner preconditions could never have found it, and three successive root-cause theories were built and discarded before anyone changed instrument rather than hypothesis. It also retro-explains a long tail of "flakiness" on this suite: `T_WR_EJECT_01` sat on the pre-declared flaky list in both 2026-08-11 full-suite baselines and is the same race.
**Applies to**: VE (owns the harness), Developer (writes gate tests), All (reading a "missing output" symptom)

---

### BP-058 — A heap comparison states the mount state and the time-since-reset for both sides, and is taken at ≥150 s settle

**Adopted from**: LL-123
**Date adopted**: 2026-08-11 (human)
**Rule**: Any A/B heap measurement on this device must record, **for both sides**, the SD mount state and the elapsed time since reset, and must be taken at **≥150 s post-reset** unless the transient itself is the subject. `lfb8` is not stable before then: on one build and one boot it reads **69 620 B at ~30 s, 32 756 B at ~90 s, and 29 684–30 708 B from ~150 s onward**, as the Spotify TLS working set becomes resident. Where an escalation rests on a delta between two measurements, re-take both sides back-to-back in one session before escalating. Pairs with BP-055's `MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT` clause — same family: the number is real, the comparison is not.
**Rationale**: TASK-425 reported that LocalPlayer's screen costs ~12 KB of largest-free-block on its own, concluded no `max_files` value could work, and escalated it as an Architect-level blocker requiring a lifecycle redesign. The two sides of that comparison differed in **SD mount state**, not in active app; with mount state held constant, arena-hold results are byte-identical with Spotify vs LocalPlayer active. Both numbers were real. The escalation was quantified, well-written and wrong, and it nearly took a correct and more important finding down with it — that arena 24 576 B + the smallest usable FATFS context 12 556 B need 37 132 B contiguous against 30 708 B available, a **6 424 B shortfall no acquisition ordering can close**, which disproves ADR-059 D1 amendment #2's premise that ordering is the lever.
**Applies to**: Developer, Architect (memory-budget rulings rest on these numbers)

---

### BP-059 — A `skip()` reason states what the test observed, not a cause it has not verified

**Adopted from**: LL-124
**Date adopted**: 2026-08-11 (human)
**Rule**: A skip message may state only what the test **actually observed**. If it names a cause, that cause must be verified independently first — and where a test skips on a precondition failure, probe that precondition through a path that does **not** go through the code under test. A skip reads as "nothing to see here" in every summary, so an unverified cause in a skip reason is the most effective way to hide a defect in this project's reporting.
**Rationale**: `T_PLR_13` and `T_PLR_15` guarded on `set fbOpen <path>` and, on failure, reported `skip("fixture /probe200 not on the card")` — neither test ever checked whether the fixture was on the card. In one run `T_PLR_13` opened `/probe200` successfully and `T_PLR_15` failed to open the same path minutes later, reporting it as missing. The full-suite baseline then failed all three browser tests on that cause while the same ids pass targeted from a fresh flash. It became TASK-433 at P1, blocking TASK-418, whose auto-advance puts the same path on the end-of-track path with no user gesture. The implementing agent's own gate run had reported 6 passed / 0 skipped, so it was invisible there, and two separate readers absorbed the skip without investigating — while the same session's stale *assertion* in `T_PLR_06` produced a loud FAIL and was diagnosed in minutes. The fix probes with `sdls`, which does not touch `fileBrowser`'s state or allocation.
**Applies to**: VE, Developer (anyone writing a guarded test)

---

### BP-060 — A handover prompt labels every diagnostic claim as measured, inferred or assumed, and grants the receiving agent standing permission to contradict it

**Adopted from**: LL-125
**Date adopted**: 2026-08-11 (human)
**Rule** *(scope widened 2026-08-16, LL-134)*: When briefing a fresh or continuing agent, **or writing any document a cold agent will treat as fact — an ADR, a design doc, an interface contract —** mark each diagnostic claim with how it was established — **measured** (with the evidence), **inferred from X**, or **assumed**. Any instruction to act on a theory must carry an explicit instruction to verify it first and to report back if it does not hold; the receiving agent needs stated permission to contradict the brief. On a symptom of "expected output never appeared", capture the raw stream (BP-057) **before** writing any theory into a prompt at all. Delegation multiplies the cost of an unverified assertion: a theory a single engineer would test in five minutes instead becomes hours of plausible-looking work across several agents. **Where a document would need to state something not actually verified, say so and reserve the space** (`STUB`, "blocked on TASK-NNN") rather than filling the gap with a plausible construction.
**Rationale**: During TASK-417 the orchestrator wrote three successive root-cause theories into handover prompts, each justified and each wrong: `hit='CANVAS'` means the eject zone is dead (it is the shell-busy swallow marker); the persisted `playerMode` leaks across tests (disproved by direct measurement — `appId=Spotify`, `playerMode=Spotify`, `shellBusy=False` immediately before every failing tap); and the shuffle-commit's 250 ms cooldown swallows the following repeat tap (same race as BP-057). Every receiving agent acted on them unchallenged, because a prompt reads as briefing rather than hypothesis. Three agents rewrote `winampDisplay.h` chasing a firmware defect that did not exist, and two of those iterations introduced real regressions into shipped behaviour that the control tests caught. The agent that resolved the task was the one that instrumented the state and reported "this disproves the leading hypothesis". The task's two substantive claims (`T_PLR_18`, `T_PLR_19`) had been green since the first gate run. Rig noise amplified it further — the harness's 25 s post-reset WiFi wait (`_DUT_WIFI_WAIT_S`) aborting as a bare `RuntimeError: DUT WiFi not connected` traceback, plus serial-port contention from a peer session and from the orchestrator's own probing, produced non-results that were read as test results.
**Rationale addendum (2026-08-16, LL-134)**: the same disease one altitude up. A false claim that certain headers "cannot be included from a second `.cpp`" — they already are, from two — became a four-stage refactor plan before anyone checked. Two overgeneralised IFC-002 invariants became five reserved test ids, two of which were discarded once VE checked them. The mitigation that worked was already in use in the same session: `IFC-004/005/006` were reserved as stubs saying "not yet contracted, blocked on TASK-NNN", and nobody could implement the wrong thing against them.
**Applies to**: All (anyone writing a handover prompt, orchestrating subagents, or authoring an ADR / design doc / IFC)

### BP-061 — Close a task on the path it was filed from, or say so in the status word

**Adopted from**: LL-129
**Date adopted**: 2026-08-15 (human)
**Rule**: A task closes on the code path it was filed from. If that path is blocked and a shared or adjacent path is gated instead, the status stays something other than DONE — `FIXED, GATE SUBSTITUTED (real path blocked by TASK-N)` — until the original path runs. A caveat in the prose is not enough: the status word is what propagates into the board, the milestone view and everyone else's planning.
**Rationale**: TASK-432 was filed from a `set plPlay` crash on the FILE arm. That arm could not be tested (the harness could not target `cyd2usb_player`), so the fix was gated on the WebRadio arm, which shares `aeEnsureAudio()`. That gate passed 4/4 and the task was marked DONE with the substitution recorded honestly in prose. When the FILE arm finally ran it did not merely fail to confirm — it exposed two defects in the shipped fix (the arena was never released on failure, poisoning every later play; the fault injector bypassed that very rollback) and then a P1 discovery that the variant could not construct the audio engine at all. A shared code path is equivalent for the *guard* and not for the caller-side rollback, the memory conditions, or the state machine around it — and those are where the defects were.
**Applies to**: Developer, VE, PM

### BP-062 — A DUT measurement carries its conditions or it is not a measurement

**Adopted from**: LL-132
**Date adopted**: 2026-08-15 (human)
**Rule**: Any DUT number that will be cited later records, in the same line or table: commit, build variant, seconds since reset, network state (SSID/RSSI, or "cascade failed, supervisor connected"), and **which heap cap was read** (BP-055 — the 32-bit and byte-addressable figures differ by tens of KB). A number without them is quotable as "observed once", never as a baseline. When a later run contradicts such a number, suspect the environment before suspecting the commits in between.
**Rationale**: TASK-427 closed with "DUT-verified: MP3 plays" and `lfbBefore=69620` at commit `510afef`, recording nothing about the conditions. Four days later the same variant could not construct the audio engine, and the two commits that had landed since became the obvious suspects. A bisect built `510afef` in a clean worktree and ran the same fixture on the same board: it crashed at the same allocation. The suspects were innocent; the baseline had moved ~26 KB with no code change. Three separate task write-ups had by then reasoned from "it played at `510afef`" as if it were a property of the commit rather than of that afternoon. The eventual cause (a boot TLS session, TASK-447) was environment-dependent in exactly the way the missing conditions would have exposed.
**Applies to**: All

### BP-063 — Account for the memory before proposing a mechanism

**Adopted from**: LL-133
**Date adopted**: 2026-08-15 (human)
**Rule**: On any "not enough memory" symptom, the first action is to diff the existing milestone probes end to end and account for the total — before proposing any mechanism. If that accounting does not exist, build it before theorising: it is cheaper than one DUT session and it bounds every later argument. When a subsystem is compiled out, explicitly check what still runs on its behalf; the guard that skips the task is rarely the only one needed.
**Rationale**: `cyd2usb_player` could not start local playback. The investigation ran two DUT sessions, a git bisect, an Architect ruling with a drafted ADR amendment, three team reviews, five filed tasks and two new debug instruments — all inside a contiguity frame that was true, measured and irrelevant. The actual cause was a Spotify OAuth token refresh at boot, 43 596 B of mbedTLS working set, on a build with `DISABLE_SPOTIFY`, printed in every capture taken during the investigation as `Refreshing Access Tokens` / `POST /api/token -> 200` **immediately before `[boot] spotify=off`**. The `[membudget]` milestone probes had been printing the correct 8-bit figures since TASK-261 (`MALLOC_CAP_DMA` *is* the 8-bit-capable internal pool on ESP32); diffing four consecutive lines located the step in under a minute. It was only done because the human asked whether the allocations had ever been accounted for. Team review amplified the frame rather than breaking it: each reviewer improved the arena argument, none asked where the memory went. The compiled-out check then had to be repeated twice more — `DISABLE_SPOTIFY` skipped `spotifyTask::begin()` but not the token refresh (TASK-447), and not `switchApp`'s poll-suppression predicate (TASK-448).
**Applies to**: All

### BP-064 — Cite symbols, not coordinates

**Adopted from**: LL-134
**Date adopted**: 2026-08-16 (human)
**Rule**: In any document intended to be true *now* — ADR, design doc, IFC, task entry, `CLAUDE.md` — refer to code by **symbol**: `cmdGet`, `dataTaskStorage.cpp :: fetchWeather`. Do not cite a bare `file.ext:NNN` coordinate as the primary reference; a line number may follow a symbol as a convenience, but the symbol must carry the reference on its own. Historical records — `tasks-archive.md`, `lessons_learned.md`, `audit_log.md`, `docs/rnd/` — are **exempt**: they describe the tree as it was, and their coordinates are correct as history. When a broken citation is found, **grep the corpus for the same error before calling it fixed** — two errors found on 2026-08-16 each recurred at a second site.
**Rationale**: Measured over the gated corpus (223 live docs) on 2026-08-16: **274 of 576 `file:line` citations — 48 % — were already broken.** The mechanism was demonstrated end-to-end inside one session: `M-CODEQUAL` was written citing `main.cpp:3484` / `:4101` / `:2976` / `:5769`, and the *same author's next three commits* moved every one; in the same document every symbol reference survived unchanged. The asymmetry is not about care — the line-number document was written carefully — it is that a coordinate is a mirror of a fact that moves, and a symbol is the fact. Enforced going forward by `run/check-docs` C1 in `delta` mode, which fails only on newly introduced coordinates so the existing backlog decays opportunistically instead of needing its own milestone. <!-- check-docs: ignore-line -->
**Applies to**: All

---

### BP-065 — A document describing landed work says so, and names the commit

**Adopted from**: LL-134
**Date adopted**: 2026-08-16 (human)
**Rule**: The moment work described by a design doc or ADR lands, its status changes to `accepted` or `done`/`implemented`/`resolved`/`closed`/`applied`/`retired` (whichever fits) **and names the commit(s)**, with an as-built section recording what shipped and — explicitly — **how it deviated from the document**. Architecture documents use a closed status vocabulary: `proposed` | `accepted` | `done` | `implemented` | `resolved` | `closed` | `applied` | `retired` | `superseded` | `rejected`. `draft` and `planned` retire into `proposed`. **The `Status:` field itself holds only the bare word — TASK-508 (2026-08-23, human ruling): C4 matches exact, not prefix, and header-only, not anywhere in the file.** Commit hashes, dates and rationale belong in the as-built section, not appended to the same line. Status changes in the same commit as the work, never as a follow-up task.
**Rationale**: Two observed failure shapes. (1) `M-NOART` sat at `draft` from 2026-05-20 while half of it shipped under TASK-062; a later session had to re-derive from source which half, and concluded wrongly at first that `cheapYellowLCD.h` was droppable — it still owns the global `tft` object and `WinampDisplay`'s base class. (2) The July 2026 sweep found **nine** ADRs stuck at `proposed` after being implemented, needing a nine-way disposition pass with code evidence. Follow-up status tasks do not get done: M-PR-LOCATIONS shipped TASK-315..325 with zero matrix entries and was backfilled weeks later, which is why `docs/agents/architect.md:20` exists at all. A stale `proposed` is not cosmetic — a cold agent reads it as "not yet built" and may rebuild it.
**Applies to**: All

---

### BP-066 — No architecture document gates other work, or is cited as fact, until an independent review has run against it

**Adopted from**: LL-134
**Date adopted**: 2026-08-16 (human)
**Rule**: An ADR, design doc or interface contract may be written and committed freely, but it does **not** gate other work, get cited as established fact in another agent's brief, or have tasks scheduled from it, until at least one **independent** (non-author) review has run against it. Self-review does not satisfy this. The review's job is to attack the framing, not refine inside it, and to verify claims against source rather than accept them as asserted. Track reviewer hit-rate (confirmed / raised) across passes: a sustained near-100 % rate means the authoring pace needs a brake, not that review should be trusted less.
**Rationale**: On 2026-08-16 a one-day architecture pass produced nine design docs, two ADRs and three IFCs. Four independent reviewers raised 16 findings and **15 held** — including an interface invariant that was false about one of its own named examples, another that asserted a universal while citing a source whose own table contradicted it, a consolidation design that missed a live behavioural divergence between two functions it proposed to merge, a memory budget measuring the wrong axis (`-fno-lto` is unconditional here; the cost is flash, ~45:1 against the DRAM figure being gated), and a task board whose own table contradicted its own prose. **None was caught by the author.** Cost is real — this serialises authoring behind review — and it is the only measure that would have prevented all fifteen.
**Applies to**: All (Architect especially)

---

### BP-067 — A review finding of the form "X exists, therefore Y" states how BOTH halves were established

**Adopted from**: LL-138
**Date adopted**: 2026-08-17 (human)
**Rule**: When a review raises a finding whose force depends on an inference — "this flag is set, therefore that is compiled out"; "this grep is empty, therefore the symbol does not exist" — the finding names the verified fact **and** the inference separately, and says how each was checked. A finding that **gates, blocks or withdraws** other work must have its *consequence* verified at the mechanism: read the enum, not the build flag; grep the delegated call chain, not the directory.
**Rationale**: On 2026-08-17 two independent reviews of the same plan each made exactly this error. One read `-DDISABLE_SPOTIFY` in `app/platformio.ini:193` and concluded the three player modes could not coexist in a build — withdrawing an exit criterion and blocking an item — when `kPlayerModes[]` gates on `PLAYER_*` flags, not that one. The other grepped `app/src/debug/` for an observable and reported it missing; it lives in a per-app `dbgGet` chain. Both facts were true. Neither conclusion was. The first error additionally survived acceptance by a third party who verified the flag and not its effect. This is M-CODEQUAL §13.2's counting note generalised: **a verified fact is still only a hypothesis about its consequence.**
**Applies to**: All (reviewers especially); pairs with BP-066

---

### BP-068 — A gate ships with negative tests, and they break it the way it is meant to catch

**Adopted from**: LL-139
**Date adopted**: 2026-08-17 (human)
**Rule**: A new gate, checker or staleness test is not complete until at least one **negative test per assertion** has been run by deliberately breaking the tree, and the negative tests are committed with it. The break must be the *specific* failure the gate exists to catch, not a convenient proxy. A gate that has only ever been observed passing has been read, not tested.
**Rationale**: `check_player_binding.py` (M-TESTBASE §8.4) passed on the clean tree and looked correct to its author on two readings. Four deliberate breaks found **three defects**: adding a second dispatch call inside `main.cpp` — the exact TASK-413 failure the gate exists to prevent — was invisible because it compared filenames rather than call counts; unregistering `T_PMT_00` was invisible because a substring check still matched the id inside the test body's own strings; and the gate miscounted its own subject, scoring a `kCmds[]` help string containing "resolvePlayerTap (surface-independent)" as a dispatch site. Separately and on the same day, `T_DOC_02` — a gate shipped 24 hours earlier — broke on routine documentation growth because it asserted live-corpus counts (LL-141). Both gates were reviewed. Neither was broken on purpose before shipping.
**Applies to**: All (Developer, VE); `test_check_docs.py`'s `T_DOC_01..09` is the in-tree template

---

### BP-069 — A task-board row is a pointer: id, priority, status, title, design-doc link, commit hash — nothing else

**Adopted from**: LL-145
**Date adopted**: 2026-08-25 (human)
**Rule**: A `tasks*.md` row holds only: task id, priority, status, a one-line title/summary, a link to the governing design doc (only when one exists), and the landing commit hash(es). It does not hold the verification narrative — diff summaries, byte-deltas, DUT logs, judgment-call rationale. That evidence lives in the commit message (which already carries it in full on this project) and, for tasks with a governing design doc, in that doc's `BP-065` as-built section, updated by the agent executing the task **in the same commit that lands the work** — not as a follow-up, and not duplicated a third time into the board. A design doc under `docs/architecture/designs/*.md` is warranted only for a genuine design or architectural decision; a mechanical or hygiene task (a stale count, a doc-comment sync, a one-line promotion) gets a thin row and no separate doc at all — its record is the commit message alone. Applies **going forward only**: already-landed verbose rows are handled by ordinary archive passes (moved to `tasks-archive.md` per the existing convention), never retroactively rewritten to fit this shape.
**Rationale**: A single session landed ~30 tasks and several rows in `tasks-architecture.md` grew past 1,000 words each, because the row was the only place execution evidence had anywhere to go once a task closed — the same failure shape that grew `main.cpp` to 5,880 lines and `run_serialdbg_tests.py` to 10,229: one file absorbs everything of a kind because nothing else is designated to hold it. Unpacking a bloated row showed it was three different kinds of content pasted together — design intent (already has a home: the design doc), execution evidence (the commit message already has this, in full — the row was a second, worse copy), and scheduling state (the only thing a board actually needs). `BP-065` already put the as-built record in the design doc at landing time; this rule is the direct extension of that pattern to the board itself, closing the gap that let the duplication happen.
**Applies to**: All (PM especially — board maintenance; Developer/Architect — commit-time as-built updates)

---

### BP-070 — A task that moves or deletes code names the docs it invalidates in its exit criteria

**Adopted from**: M-DOCLIFE §3/§6 rec 2 (TASK-474, split 2026-08-27)
**Date adopted**: 2026-08-27 (PM)
**Rule**: Any task whose scope moves, deletes, or renames code carries a `docs-touched:` line in its
exit criteria, naming the specific documents it invalidates — not "update docs" as a vague follow-up.
If no doc is invalidated, the line says so explicitly (`docs-touched: none`) rather than being
omitted, so its absence is never ambiguous between "checked, none" and "not checked."
**Rationale**: M-PR-LOCATIONS shipped TASK-315..325 with zero matrix entries, backfilled weeks later
— a doc update filed as a follow-up task competes with feature work and reliably loses. A follow-up
task for documentation is the failure mode this rule exists to prevent, the same way BP-069 prevents
verification narrative from having nowhere to live but the row.
**Applies to**: PM (files the criteria) — Developer/Architect (fills `docs-touched:` at task filing,
not at close-out)

---

### BP-071 — A task-id or feature-id reservation lands in its board the moment it's claimed, not at close-out

**Adopted from**: M-DOCLIFE §1/§3/§6 rec 5 (TASK-474, split 2026-08-27)
**Date adopted**: 2026-08-27 (PM)
**Rule**: The moment a design doc or session claims a task id (or a `feature_inventory.yaml`/
`cross_feature_matrix.yaml` entry), a placeholder row lands in the owning board (`tasks.md` or the
relevant split board) immediately — not staged in an unpushed document until the work closes.
**Rationale**: M-DOCLIFE's own case study collided on TASK-451/452 because the reservation lived only
in an unpushed document while a parallel session took the same numbers — 18 references had to be
renumbered. The split-board pattern (`tasks-winamp-player.md`, `tasks-architecture.md`) already does
this informally by construction; this rule makes it an explicit, general requirement rather than an
accident of how those two boards happened to get built. `docs/agents/architect.md`'s existing
reservation rule for `feature_inventory.yaml`/`cross_feature_matrix.yaml` entries is the same
principle already in force for registry ids — this extends it to task ids on any board.
**Applies to**: PM (owns board placeholder rows) — Architect (owns registry-entry reservations,
per existing `architect.md` responsibility 10)

---

### BP-072 — A correction to an interface contract propagates, in the same pass, to the design doc it names as its origin

**Adopted from**: M-CONCURRENCY §8 R5 (TASK-543, 2026-08-27)
**Date adopted**: 2026-08-27 (Architect/PM)
**Rule**: When a review corrects a claim in an IFC (`docs/architecture/interfaces/*.md`), and that
IFC names a design doc as the claim's origin (a `**Worked out in**:`/`**Defined by**:` reference, or
equivalent), the same review pass lands a matching correction in that design doc — not a follow-up
task, not "it's now right in the interface so it's fine." If the IFC doesn't name a single governing
design doc in a resolvable way, this rule doesn't apply and there is nothing to propagate to (that
gap is its own, separate finding — see M-DOCLIFE D6's note on IFC-001/003).
**Rationale**: On 2026-08-16, @VE reviewed IFC-002 and raised one BLOCKER and two MAJORs against
claims that all originate in M-CONCURRENCY-task-ownership-contract.md. All three corrections landed
in IFC-002 and in `test_plan.md` (which discarded the three stale test ids they invalidated) — **none
landed in M-CONCURRENCY itself.** For ten days the design doc and the interface it supposedly derives
from stated opposite things about two invariants, and a reader arriving through the design doc first
(the normal path — TASK-473's board row links it first) read the wrong one. BP-065 covers code→doc
propagation and BP-066 covers review→doc gating; neither one covers doc→doc. This is the same
class of failure LL-114/BP-065 already fixed for firmware truths mirrored into host tools and design
docs, one hop further down the reference chain — a correction that stops at the first document it
touches, instead of reaching the one that's actually the source of the claim.
**Applies to**: Architect, VE (whoever performs the review that finds the correction)

---

## Entry Format

```
### BP-001 — [Title]
**Adopted from**: LL-XXX
**Date adopted**: YYYY-MM-DD
**Rule**: The actionable guidance (one clear sentence where possible)
**Rationale**: Why this matters
**Applies to**: Developer | VE | PM | QM | All
```