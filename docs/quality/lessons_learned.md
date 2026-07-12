# Lessons Learned

> Owner: Quality Manager

Populated during retrospectives. Entries reviewed w/ human for promotion to `best_practices.md`. No promotion without explicit human sign-off.

## Retrospective — 2026-07-12 — M-PLANERADAR post-close audit arc (TASK-309..312)

### LL-109 — 2026-07-12 — An app that painted nothing in init() passed two code reviews and a full DUT suite; the human's eyes were the only gate that could catch it
**Context**: `switchApp()` calls `init()` on an app's first-ever entry and `resume()` on every later entry. PlaneRadarApp put ALL of its painting in `resume()` — copied from TeletextApp's init/resume shape, where the same gap is masked because Teletext's first fetch repaints the full screen anyway. On PlaneRadar's incremental renderer, first entry showed: black screen → one stray highlight ring (tick()'s age readout) → grid lines with no field fill (first fetch's statics redraw) → correct disc only after the first range tap ran `_repaintDisc()`. This survived: the TASK-304 implementation review, the 2026-07-11 audit (which compared draw paths within the file and against the reference project), the TASK-309/310/311 refactor review, and two full T_PR_01..06 DUT runs. The human saw it in the first ten seconds of looking at the screen.
**Observation**: Every automated/agent gate in the chain reasons about the file's internal consistency or its serial-observable state. The bug lived in neither — it was a mismatch between the app and its CALLER's contract (`init()` must produce a complete first paint), visible only as pixels. T_PR_02 even "verified render within one poll" — by reading `prAircraftCount` over serial, which is true while the screen is wrong.
**Root cause**: Two structural blind spots stacked: (1) reviews scoped to the app file never checked the shell's first-entry contract, and the checklist has no item for it; (2) the DUT suite's observability boundary is the serial debug surface — pixel-level exit criteria silently degrade to state-level proxies unless a human-eyeball step is an explicit, named part of the gate.
**Suggested improvement**: (a) NEW-APP-CHECKLIST: add "first entry paints completely — either `init()` paints or explicitly routes through `resume()`'s paint path; verify against `switchApp()`'s init-vs-resume dispatch, and audit TeletextApp's shape before copying it." (b) For any task whose exit criteria are pixel-level (paint, palette, layout), the task entry must carry an explicit "human eyeball" criterion that blocks DONE — TASK-312 did this and it worked; TASK-304/307 didn't and the bug shipped through both.
**Status**: fixed in-session (TASK-312, init()→resume() single paint path); TeletextApp shares the latent shape (masked) — flagged; LL flagged to human as BP candidate

### LL-110 — 2026-07-12 — A bug fix applied to one of two duplicated sites diverged within 24 hours; the audit that caught it was looking for duplication, not bugs
**Context**: TASK-308 fix 5 (disc repaint on range change) went into `handleInput()` but not `dbgSet("prRange")` — the same action duplicated at two call sites. The next day's code audit (hunting duplication and magic numbers per the human's hunch, not hunting bugs) found the divergence as a *consequence* of the duplication finding: the debug path still reproduced the exact bug the fix had closed on the touch path. Same pattern one layer down: the `init()`/`resume()` preset-clamp duplication is what made TASK-308 fix 2 necessary in the first place.
**Observation**: Both divergences were created by fixing/patching one copy of duplicated logic under time pressure while its sibling stayed stale. Neither was findable by testing the path that got the fix — only by asking "where else does this logic exist?"
**Root cause**: A bug fix to logic that exists in N places is N fixes, but nothing in the fix workflow forces enumerating the other N−1. Duplication converts every future fix into a divergence lottery.
**Suggested improvement**: When a fix lands in code that a quick grep shows duplicated elsewhere (same field written, same sequence of calls), either extract the shared helper IN the fix commit or list the sibling sites in the task resolution as explicitly out-of-scope — silent siblings are how TASK-308→TASK-309 happened. The human's instinct ("I suspect duplication") was the effective bug-finder here; a periodic duplication audit is cheap relative to what it caught.
**Status**: fixed in-session (TASK-310 extracted `_setPreset()`/`_applyRangeSetting()` etc.); flagged to human as BP candidate

## Retrospective — 2026-07-11 — M-PLANERADAR TASK-307 (DUT validation, milestone close)

### LL-107 — 2026-07-11 — A dataTask fetcher's "success" sentinel was the same value as its "never fetched" sentinel, and two VE tests were written against the wrong one before the DUT caught it
**Context**: PlaneRadar's `dbgGet prLastHttp` surfaces `PlaneRadarResult.errorCode`. `fetchPlaneRadar()` only ever writes a non-zero `errorCode` on failure (HTTP status or a negative internal code); a successful fetch leaves the struct's default-constructed `errorCode=0` untouched — the raw HTTP 200 appears only in a `LOG_D` line, never in the value any test can read back. Two VE tests (T_PR_02: wait for `prLastHttp==200`; T_PR_05: diff `prLastHttp` against a prior value to detect an error) were written and run against real hardware before this was noticed — both failed, one of them (T_PR_05) on a false-positive "error" that was actually the init sentinel.
**Observation**: The bug was invisible from reading the design doc or the dbgGet/dbgSet surface documentation alone — `dbgGet` returning "the errorCode field" reads as complete and reasonable. A manual serial diagnostic (watching raw `[D][dataTask.planeradar] GET 200 elapsed=...` log lines against simultaneous `get prLastHttp` polls) was what exposed that the field never changed to 200 on success. This is the same shape as LL-105 (a claim about what a surface reports vs. what it actually contains) but on a firmware debug interface instead of a design-doc/tool pairing.
**Root cause**: A "return the raw errorCode" dbgGet implementation is not the same as "return a success/failure signal" — the two coincide everywhere EXCEPT the specific default-value collision (0 = both "ok" and "never happened"). No app-independent VE convention exists for which field a test should gate on when checking "did the fetch resolve" vs. "did it resolve OK."
**Suggested improvement**: For any dataTask-backed app, a VE test asserting "fetch succeeded" or "fetch failed" should gate on `isConnecting()`/`hasError()` (exposed uniformly via `get activeError`'s `connecting`/`active` fields, ADR-046) rather than an app-specific raw error/status field — the latter is for diagnostic detail in failure messages, not for pass/fail logic. Consider flagging in NEW-APP-CHECKLIST §3 (serial debug surface) that a raw errorCode dbgGet is not a substitute for the activeError-based success/failure signal.
**Status**: fixed in-session (T_PR_02/T_PR_05 rewritten); flagged to human as BP candidate

### LL-108 — 2026-07-11 — Under a real external blocker (403-retrying Spotify), an app's own busy-gate closed a window a VE test's timing assumption didn't account for
**Context**: T_PR_03 (range-cycle-by-tap) taps the PlaneRadar disc 4× expecting the range preset to advance each time. On the first DUT run it advanced once then stuck — `handleInput()` re-enqueues a dataTask fetch on every range-changing tap (`!_injected` guard), which arms `hasPendingAsync()`/shell-busy; with Spotify's 403 retry loop (TASK-243, external/Premium-lapsed) holding `tlsYield()` in overdue-poll contention, that fetch stayed pending long enough for the shell to silently drop the next tap.
**Observation**: The test's implicit assumption — "the app's own state-changing action completes fast enough that a follow-up tap 200ms later is safe" — held in isolation but not under a real, currently-active external condition already present in this environment (TASK-243). Nothing about the test looked wrong until it actually ran on hardware in that state.
**Root cause**: A test that drives a UI action which happens to also enqueue async work will inherit that work's timing dependencies (including contention on a shared resource like the TLS session) even when the test's actual assertion has nothing to do with networking.
**Suggested improvement**: When a VE test needs to fire a rapid sequence of app-driven UI actions and only cares about the UI-visible state change (not the side-effect fetch), prefer isolating from the side effect first (here: `prInjectAircraft` before tapping, since `_injected` skips the re-enqueue) rather than adding `_wait_shell_not_busy` calls tuned to the current contention level — the latter is a timing band-aid that breaks again the next time the contention gets worse.
**Status**: fixed in-session (T_PR_03 injects synthetic aircraft before tapping); flagged to human as BP candidate

## Retrospective — 2026-07-11 — M-PLANERADAR phase 0 (host-first exploration)

### LL-105 — 2026-07-11 — "The preview tool confirms X" was true of the doc's prose twice before it was true of the tool
**Context**: `phase0-preview-ui.md` closed six design questions (Q1-Q6) against `preview_planeradar.py`. Two of the six didn't hold up on inspection: Q4 (runway label density) had a design doc claiming it as an open question the tool would answer, but the tool contained only a `COL_RUNWAY` color constant — no runway-drawing code existed at all. Q6 (whole-degree heading rendering) had a human "looks fine" verdict, but `nose_deg()`/`track_deg()` passed fixture floats straight through unrounded — the render being judged was full float precision, not the whole-degree `int16_t` storage the parse-heap design (`phase0-parse-heap.md:108`) actually commits to for firmware. Both were caught by reading the tool's source against the specific claim before accepting the "confirmed" line, not by re-running the tool.
**Observation**: In both cases the doc's prose was internally consistent and the screenshot/eyeball step *looked* like it had happened — nothing about the workflow signaled a gap. The gap was between what the design doc said the tool would test and what the tool's code actually exercised. This is the same failure shape the earlier designer-review round caught elsewhere in this same milestone (a ~21% fetch-radius undercount, and a v6-allocator heap claim that measured the wrong thing) — a recurring pattern across this project, not a one-off.
**Root cause**: A design doc's "renderer confirms X" or "tool validates Y" line is a claim about the tool's *code path*, not about the render happening at all. Reviewing the screenshot (or accepting a verbal eyeball) checks that *a* render happened; it doesn't check that the render exercises the specific production-representative value or that the feature exists in the tool at all.
**Suggested improvement**: When a design doc says a preview/PoC tool "confirms" or "validates" something specific (a precision choice, a data-driven overlay, a threshold), grep the tool's source for the claimed code path before accepting the doc's "closed" status — don't accept a screenshot or a verbal sign-off as proof the right thing was measured. This is the UI/PoC-tooling analogue of LL-103's "a verification tool that isn't attached to a gate effectively doesn't exist" — here the gate is a design doc's own closure claim.
**Status**: adopted → BP-046 (human, 2026-07-11)

### LL-106 — 2026-07-11 — A session-scoped scheduling primitive was reached for first, for work that must outlive the session
**Context**: M-PLANERADAR's second TLS cert-chain observation (`phase0-api-probe.md` exit criterion 6) needs to happen on a calendar day different from the first observation — genuinely cross-session work. First instinct was `CronCreate`, a session-only scheduler that silently stops existing if the session ends before it fires. The user caught this and asked to track it as a todo instead; the job was cancelled and refiled as a durable `tasks.md` entry (TASK-301) plus a Task-tool item, either of which survives independent of this session.
**Observation**: The tool that was reached for first matched the surface request ("schedule this for tomorrow") but not the actual requirement (survive an unknown gap until a human re-engages). The mismatch was caught by the user, not self-caught before offering the cron option.
**Suggested improvement**: Before scheduling any follow-up work, ask whether the task must survive beyond the current session (cross-day, cross-conversation, no guaranteed re-engagement). If yes, default to a durable tracker entry (`tasks.md` / the Task tool) and treat a cron/wakeup primitive as an optional *reminder on top*, not the primary mechanism — the reverse of what happened here.
**Status**: applied in-session (fb4b4692 cancelled, TASK-301 + Task #1 filed instead) — flagged to human as BP candidate

## Retrospective — 2026-07-08 — Full-suite failure investigation (TASK-296/297/298/299)

### LL-103 — 2026-07-08 — A guard script built for exactly this failure class sat outside every routine gate; the failure surfaced as 7 cryptic test FAILs instead of one preflight line
**Context**: `run/check-datatask-certs` was written 2026-06-20 to replicate mbedTLS's strict offline chain verification for every pinned dataTask endpoint — precisely to catch CA rotations like CoinGecko's ISRG→GTS flip (TASK-298). It was never wired into `run/check`, `run/test`, or any cadence. The rotation was instead diagnosed from scratch: two contaminated 40-minute suite runs, per-endpoint DUT isolation, ssl_client error capture — several hours to rediscover what the script reports in ~10 seconds.
**Observation**: The tool was not just available but purpose-built, documented in the cert header comment, and referenced from dataTaskCerts.h. Nothing in the failure path (suite FAIL output, test names, task filing) pointed at it; it was found by reading the cert file while writing the fix.
**Root cause**: A verification tool that isn't attached to a gate, a cadence, or the failure's diagnostic path effectively doesn't exist at diagnosis time. The house pattern exists (BP-030 quarterly cert check) but the script was never registered as that check's implementation.
**Suggested improvement**: When a diagnostic/preflight script is created, it must be attached to something that runs: a gate (`run/check`), a harness preamble (`run/test` step 0), or a documented cadence with an owner. For this case: wire `check-datatask-certs` as a `run/test` preflight once the yahoo-pin exception (TASK-109c vs strict verify) is resolved — until then even a warn-only line would have named the cause instantly.
**Status**: case remediation applied 2026-07-08 (yahoo repinned per human-approved TASK-298 follow-up; preflight wired as `run/test` step 0, warn-only) — the general rule remains flagged to human as BP candidate

### LL-104 — 2026-07-08 — Two independent failure causes stacked; the first plausible attribution (AP storms) nearly closed the investigation while the deterministic defect hid under it
**Context**: TASK-298. Full-suite run 1: 10 network-test failures + a genuinely storming AP (verified: DUT parked, boot storms, host scans). Everything fit "environment outage" — the classic LL-096 network-blame direction, except this time with real supporting evidence. Only the decision to re-run in a clean window (which returned the IDENTICAL 10 failures) falsified the sufficient-cause assumption and exposed the deterministic CoinGecko cert failure underneath; per-endpoint DUT isolation then split the set into 1 cert defect + 8 environment + 1 timing flake + 1 inter-test latch (four distinct causes total).
**Observation**: A true-but-insufficient cause is more dangerous than a wrong one — the AP storms were REAL (TASK-296 came out of them) and explained 8/10 failures, which made stopping there feel evidence-based. The identical-failure-set-across-two-runs signature is what broke the story: environment noise doesn't reproduce a 10-test set exactly.
**Root cause**: Attribution was being done at the run level ("this run failed because of X") instead of per failure. Nothing in the process demanded that each failing test individually be consistent with the claimed cause; determinism across runs was never checked against a noise hypothesis.
**Suggested improvement**: When attributing a multi-test failure to an environmental cause, check the reproduction signature first: re-run (or re-test the failing subset) and compare failure SETS. Identical sets ⇒ deterministic cause (at least in part) — disposition each failure individually. Also: an environmental cause explaining most failures licenses no conclusion about the rest.
**Status**: open — flagged to human as BP candidate

---

## Retrospective — 2026-07-08 — QM/PM status-currency sweep (TASK-281/294 close + reconciliation)

### LL-102 — 2026-07-08 — Deferred status flips rot: one session found five stale tracker claims, each individually rational
**Context**: A housekeeping session (TASK-281, TASK-294, then "what is left to do?") found the tracker wrong in five places: TASK-281 open though its work was committed two days prior (flip deferred because tasks.md was agent-dirty); TASK-290 "pending commit" though committed in 05f5a78 (bundled into the E-gate campaign commit); TASK-282 "awaiting DUT validation run" after the LL-096 root cause mooted that validation; roadmap M-TASKBAR-FEEDBACK still carrying "D1–D3 pending human sign-off" and "TASK-280 remains open" after both were resolved; LL-098's status lagging TASK-292's landing.
**Observation**: Every deferral had a sound local reason (dirty file, bundled commit, overtaken by events, doc not on the touch path). But the debt compounds silently: answering "what is left to do?" required git archaeology to refute the tracker, and two of the five were only found because the human happened to ask.
**Root cause**: Status lives in three places (tasks.md, roadmap.md, quality docs) with no reconciliation step. A deferred flip is an untracked TODO — the same gap class LL-069 recorded for untracked implementation work, recurring at the tracker layer. Nothing prompts a re-read of a roadmap milestone block when its follow-up tasks close.
**Suggested improvement**: (1) A commit that intentionally defers a status flip must name the debt in the commit message ("status flip deferred — reconcile TASK-NNN next session"), and the next session starts by clearing it. (2) Session-start PM step: diff `git log` since tasks.md was last touched against open statuses; treat any fix/feat commit naming an open task as a flag. (3) When a task closes, grep roadmap.md for its ID and re-read the enclosing milestone block.
**Status**: open — flagged to human as a BP candidate (QM does not self-promote)

---

## Retrospective — 2026-07-07 — M-TASKBAR-FEEDBACK (TASK-279) close

### LL-100 — 2026-07-07 — Test assertion anchored on a data-dependent surface false-failed while a standing external blocker empties that surface
**Context**: T_TBFB_04's canvas half asserted "a consumed canvas gesture arms the cooldown" by tapping the PLEDIT playlist area. PLEDIT arms the cooldown only when playlist rows exist — and the playlist has been empty on every DUT run since 2026-06-25, because TASK-243 (Spotify Premium lapsed, 403) starves it. First DUT run: FAIL `remainingMs=0`. The fix was one line: anchor on the VIS window instead, which arms +300 ms at Press with no data dependency (T-CDWN-01 had already made this exact choice).
**Observation**: The blocker was known, ratified, and cited elsewhere in the same test file — yet a brand-new test still picked a surface whose behaviour silently depends on it. Cost was low (one flash cycle) only because the suite run isolated it immediately.
**Root cause**: When choosing an assertion surface, "does this control respond to touch" was checked against the code, but "does it respond *in the device state the DUT is actually parked in*" was not. Standing external blockers change the ambient device state for every future test, not just the tests that mention them.
**Suggested improvement**: While a standing external blocker is open (grep tasks.md for blocked-external), new tests must anchor assertions on surfaces that are provably data-independent (VIS, transport sprites, taskbar) or explicitly SKIP citing the blocker. Same family as the T_WR_ERR_x isolation defect (TASK-277 retro): harness code inherits the device's ambient state, not the state the author imagines.
**Status**: applied in-run (`2e92f01`); recorded as the pattern to check at test-authoring time

---

### LL-101 — 2026-07-07 — New debug log lines shifted the external latency clock by their own wire time; the internal clock was the control that kept the comparison honest
**Context**: TASK-279's before/after table showed tap-to-switch-committed +11–13 ms in every idle state. The three new SERIAL_DEBUG lines per tap (~126 bytes) cost ≈11 ms at 115200 baud on a TX path the existing heap lines already saturate during a switch — arithmetic matching the delta. The falsifier that kept this from being hand-waving: the *device-internal* `shell.switch` clock (median 84–98 ms) landed on the BEFORE external medians (83.5–97.8 ms), showing switch cost itself unchanged; and the production build compiles none of the lines.
**Observation**: The instrumentation added to measure the feature was itself the largest measured "regression". Without the internal clock recorded in the same session, the +13 ms would have read as a real cost of the feedback blits and invited a pointless optimisation hunt.
**Root cause**: Serial writes on a saturated 115200 TX buffer are ~0.087 ms/byte of blocking wire time inside the measured window; any external (host-side) clock includes them. Stable-prefix lines are an interface, but they are not free inside latency-measured regions.
**Suggested improvement**: Before/after latency comparisons on SERIAL_DEBUG builds must record a device-internal clock (perf slot) alongside the external clock in the *same* session, and attribute any external-only delta to wire bytes before treating it as regression. When adding log lines inside a measured region, count their bytes into the measurement plan.
**Status**: adopted → BP-045 (human, 2026-07-07)

---

## Retrospective — 2026-07-03 — M-WIFI-DIAG root cause (MX5600 auto-channel) + E0 unblock

### LL-097 — 2026-07-07 — "Root cause confirmed by source reading" was wrong twice; only DUT re-verification of each fix found the real chain
**Context**: TASK-285/286. A device-rebooting `task_wdt` crash was "root-caused, confirmed via source reading" to a vendored-lib timeout guard (`Audio.cpp` version check mis-firing on 2.0.17). The fix was implemented, compiled clean, passed all static gates — and the crash reproduced identically on the original repro, including on a control URL that had no reason to be slow. Timestamped serial probes then found the actual blocker (`tlsYield()`'s unfed 150 s semaphore take), whose fix exposed a second bug (single-flag yield race, TASK-287), whose fix exposed a third (wr-idle yield-ack deadlock, TASK-289) — each found only because every fix was re-run against the original crash repro on hardware.
**Observation**: The written root-cause analysis was internally coherent, cited real code, and was still wrong about causation. The falsifying evidence cost one 30-second DUT run. Static analysis identified *a* real bug (kept, it was worth fixing) but not *the* bug.
**Root cause**: "Confirmed" was granted on source coherence alone. A plausible mechanism that explains the symptom is not causation until the fix demonstrably stops the original repro — and the cheap experiment that tests this (re-run the repro) was initially treated as optional verification rather than part of the root-cause claim itself.
**Suggested improvement**: A crash/defect may be recorded as "root-caused" only after its fix stops the original repro on hardware. Until then the status is "hypothesis (source-supported)". Additionally: always include a known-good control case in the verification set — the control URL is what falsified the theory here.
**Status**: adopted → BP-044 (human, 2026-07-07)

---

### LL-098 — 2026-07-07 — Soak gate false-FAILs because it counts device events over a serial channel the harness itself truncates
**Context**: TASK-278 E2. Both 30-min `wr-soak` runs printed `VERDICT: FAIL` solely on the arena acquire/release balance clause (81/77, 90/89). The verbose per-cycle trace showed the counter diff was only ever 0 or exactly 1, flipping once mid-run and never growing; lfb ended *above* its start in both runs, mathematically refuting a real 24 K leak. The harness's `cmd()` calls `reset_input_buffer()` before each send, discarding in-flight serial lines — including the counter lines it scores.
**Observation**: A healthy gate produced a FAIL verdict twice from its own measurement channel. Disposition required per-cycle tracing plus an independent physical invariant (lfb trend) to overturn — documented in M-WR-AUDIO-TASK §E2 and filed as TASK-292.
**Root cause**: The invariant (acquires == releases) lives on the device, but the gate counts wire-observed log lines over a deliberately-lossy read pattern. Any event-counting gate built this way false-FAILs at a rate set by serial contention, not by the property under test.
**Suggested improvement**: Gates that count discrete events must read device-side counters (e.g. a `get arenaStats` serialdbg pair sampled at start/end), not tally log lines. Where wire-counting is unavoidable, the gate spec must state the expected loss mode and a disposition rule (here: mismatch ≤ small-N with non-decaying lfb ⇒ line loss, not leak).
**Re-disposition (QM, 2026-07-08, TASK-295 follow-up)**: TASK-295 found a real crash-reboot in the same churn path whose wire signature (acquires = releases + 1) is identical to line loss — raising the question whether E2's "false-FAIL" was a reboot all along. Ruled out for those runs: the crash is reachable ONLY via TASK-291's stall-retry, which postdates the E2 soaks; and both soaks completed 88/92 paced cycles with sustained-playback medians a reboot would have disrupted. E2's line-loss attribution stands. The ambiguity class itself is closed by TASK-292 (gate reads device-side `arenaStats` start/end + explicit `!! DUT RESET/PANIC` reboot detection → line loss, reboot, and real leak are no longer confoundable); the post-TASK-295 churn + wr-soak verify ran clean under the new gate.
**Status**: adopted — TASK-292 (commit 0904684) implemented the device-counter gate; E2 attribution re-confirmed post-TASK-295

---

### LL-099 — 2026-07-07 — Bypassing the run/ wrappers to pass one extra flag cost a flash cycle; extending the wrapper cost one line
**Context**: TASK-278 E2 rerun needed `--verbose` on the soak, which `run/wr-soak` didn't expose. The DUT lifecycle was hand-rolled (manual tmux kill + pio upload) to pass the flag; the guessed tmux session name was wrong (`cyd-monitor` vs the actual `spotify-mon`), the monitor kept the port, the flash failed in 3 s, and a `| tail` pipe masked the failure past `set -e`, cascading into a dead soak run.
**Observation**: CLAUDE.md's "always use the run/ scripts — they handle port resolution, monitor lifecycle, and DUT safety" rule was violated and bit exactly as documented. The compliant fix was a one-line opt-in in the wrapper (`${WR_SOAK_VERBOSE:+--verbose}`), which also produced the trace that resolved LL-098.
**Root cause**: A missing wrapper capability was treated as a reason to bypass the wrapper, rather than as a one-line wrapper gap.
**Suggested improvement**: When a run/ wrapper lacks a needed option, extend the wrapper (env-var opt-in keeps the default path byte-identical) and keep the lifecycle guarantees. Never re-implement kill-monitor/flash/restore inline; the session name alone is a landmine.
**Status**: adopted in practice (wrapper extended in `05f5a78`); rule already covered by CLAUDE.md — recorded as a confirming instance

---

### LL-096 — 2026-07-03 — A network-correlated failure blamed on firmware for weeks was an external router defect never instrumented

**Context**: The 2.4 GHz outages that plagued M-WEBRADIO (connect-fails, mid-stream stalls, "flaky
stations", post-idle EHOSTUNREACH, the 7/10 ADR-045 gate) were finally root-caused 2026-07-03 to the
**router**: a Linksys MX5600 with 2.4 GHz on `channel: 0` (auto-select), whose channel-optimisation
sweeps took the radio off-air 5–40 s every 1–2 min. Proven only once a *second independent vantage*
(a host laptop on the same LAN + a DUT promiscuous beacon watcher) observed the AP absent at the same
timestamps, and the router's own JNAP API confirmed the auto-channel setting. Before that, individual
failures had been attributed across ≥4 tasks to plausible on-device causes: TASK-272 (modem power-save
idle-kill), TASK-232/233 ("per-station" stream drops / no-PSRAM heap wall), TASK-234 (station deadness
driving auto-skip aggressiveness).

**Observation**: Some of those attributions were partly real (the no-PSRAM heap wall reproduced on the
bare rig; power-save was a genuine contributor). But the **dominant driver** — an external AP defect —
went uninstrumented for the entire milestone because each symptom pattern-matched an on-device story
that was accepted without a second vantage. The M-WIFI-DIAG work (TASK-274/275) correctly *suspected*
H-A (the AP) but even it stopped at "suspected AP-side"; nobody put a second radio on the problem until
now. This is the fourth instance of the same habit already recorded here: LL-001 (TLS blamed on certs
before checking the clock), LL-082 (chasing the network before reading the test spec), and the
"diagnosis-ahead-of-verification" family — *treating a plausible cause as a confirmed one*.

**Root cause**: A single-vantage observer cannot distinguish "my device failed" from "the thing my
device talks to failed." Every WebRadio failure was observed only from the DUT, which sees an AP
dropout and a local fault identically (both present as BEACON_TIMEOUT / connect-fail / stall). Without
an independent observer of the *shared dependency* (the AP, the API, the upstream), attribution
defaults to the component you can see — the firmware.

**Suggested improvement**: When a failure correlates with a shared external dependency (WiFi AP, a
web API, an upstream stream), get a **second independent vantage on that dependency before attributing
to firmware** — cheapest first: the host laptop is already on the same LAN (`resource/wifi-monitor/`
patterns: nmcli band scan, `jnap.sh` router API, `openssl s_client` for a TLS host). A DUT-only
symptom that the host also sees is not your bug. Candidate BP: "external-dependency failures require a
second-vantage check before a firmware root-cause is recorded." Pairs with LL-093 (instrument
perturbation) — the second vantage must itself not perturb (the promiscuous beacon watcher broke STA
reconnect; the host nmcli scan did not).

**Status**: open — brought to human 2026-07-03; candidate BP + retro-annotation of TASK-272/232/233/234

## Retrospective — 2026-07-02 — TASK-275 close (M-WIFI-DIAG Phase 1 + TASK-238 gate)

### LL-093 — 2026-07-02 — The instrument was also a treatment: declare probe perturbation up front

**Context**: TASK-275's attribution harness added a 1 Hz host→DUT ping as the LAN-truth sensor. The gate
run under instrumentation went 10/10 with zero link events — where the un-instrumented run 2 h earlier
went 7/10 with beacon-timeout storms. The leading failure hypothesis was AP-side *idle* disassociation;
a 1 Hz ping is continuous link traffic, i.e. precisely the stimulus that defeats an idle-kick. The probe
plausibly suppressed the failure mode it was deployed to observe.

**Observation**: The run was still decisive — but as *evidence*, not as the planned measurement: "outages
vanish when the link is kept warm" + the sensor's earlier no-keepalive capture (BEACON_TIMEOUT/NO_AP_FOUND
storms) jointly support the AP-inactivity attribution better than the planned outage table would have. The
confound was recognized at trial 1 and recorded in TASK-238/275 closures rather than discovered post-hoc.
Also validated this session: instrument-first paid for itself within 33 s of the sensor going live (first
spontaneous reason=200 capture), and the pre-registered five-class taxonomy + exit rule again made closure
mechanical (no deliberation on "does 10/10 count").

**Root cause**: The design reviewed probe *mechanics* (VE-6: IP changes, client isolation, host band) but
nobody asked whether the probe's traffic interacts with the hypothesis under test. Ping-as-keepalive is a
known phenomenon; the miss was not connecting it to H-A's idle trigger during panel review.

**Suggested improvement**: For any instrumented run, the design must state what the instrumentation
*injects* into the system (traffic, timing, load) and check that against each live hypothesis; where the
probe stimulus overlaps a hypothesis trigger, either add a probe-off control arm or pre-register the
"probe-suppresses-failure" outcome as an evidence branch (as accidentally happened here). Candidate panel
checklist item for experiment designs.

**Status**: open — brought to human at TASK-275 close

## Retrospective — 2026-07-02 — EXP-012 input-ring 16 K A/B (closed same-day, no promotion)

### LL-090 — 2026-07-02 — A/B against a live external service needs a same-session paired control and stable identity keys

**Context**: EXP-012 planned to compare the 16 K input-ring trial against Phase 0's baseline, captured 3 days earlier, keyed on station list indices (st5/st7/st10). At run time the list *order* happened to be identical, but individual stations flapped dead↔alive on a minutes timescale: 2 of the 3 pre-picked slow-soak targets were corpses (120 s wasted holding each), 8/16 vs 11/16 stations played in two passes 40 min apart, and the Phase 0 `buf%` figures were incomparable anyway (the metric's denominator is the ring size under test). Separately, the first pass polled `get wrCount` and proceeded at the first non-zero value, catching a partial page (4 of 16 stations) and burning a full survey.

**Observation**: The experiment was recovered cleanly by (a) running an 8 K control **immediately after** the 16 K pass, same session, (b) keying station identity on **URL**, never index, (c) letting the harness auto-pick slow-soak targets from its *own* survey rather than a prior run's, and (d) waiting for the station count to **stabilize** (unchanged across 3 polls) instead of merely appear. The resulting same-day pairing gave unambiguous attribution: identical underruns, station availability noise clearly station-side.

**Root cause**: The plan treated the baseline as a fixed artifact when the measurement substrate (live internet radio) drifts on an hours timescale; and "count > 0" was treated as "fetch complete" for incrementally-arriving data.

**Suggested improvement**: For any experiment whose metrics ride on a live external service: (1) baseline and trial must be captured in the same session as a paired A/B; (2) identity must be keyed on a stable identifier (URL/id), never list position; (3) test targets are picked by the harness from its own survey; (4) incrementally-filled data is ready when it *stabilizes*, not when it first appears.

**Status**: open — BP candidate, brought to human this retrospective

### LL-091 — 2026-07-02 — Log the knob's on-wire ground truth as the first metric of any A/B trial

**Context**: The 16 K trial's first captured heap metric (`lfbInt` at decoder-init) came back byte-identical to baseline (38,900), which pattern-matched "the build flag didn't take" and nearly triggered a false debug spiral. Phase 0's written prediction — `lfbInt` would drop to ~30.9 K at 16 K — was simply wrong: the allocator satisfied the ring from a different free region, leaving the big block untouched.

**Observation**: The library's own `inputBufferSize: 14783 bytes` boot line settled the question in one event (16384 − 1600 reserve − 1). The harness didn't parse that line at first; it was added mid-experiment, after the ambiguity had already cost a killed run's worth of doubt.

**Root cause**: The plan verified the knob by its *predicted side-effect on a proxy metric* (largest-free-block) instead of by direct observation of the applied value. Heap-proxy predictions are allocator-layout-dependent and unreliable in both directions.

**Suggested improvement**: Every A/B knob experiment captures the knob's directly-observable applied value (buffer size on the wire, config echo-back, etc.) as the *first row* of the results table, before any effect metric. Proxy-metric predictions are hypotheses to test, never verification.

**Status**: open — BP candidate, brought to human this retrospective

### LL-092 — 2026-07-02 — A script whose numbers are cited in a committed report must be committed with the report

**Context**: EXP-012 Phase 0's measurement script lived in the session scratchpad and was lost to context compaction between sessions. Phase 2 had to rebuild the harness from the report's prose plus the TASK-271 soak script — re-discovering already-solved details (the run_serialdbg `Dut` ELF-hash gate rejecting non-canonical builds) and reconstructing the survey procedure (18 s holds) from the report so the trial column would be comparable.

**Observation**: The rebuild cost a meaningful slice of the session and risked silent procedure drift between the Phase 0 and Phase 2 measurements. The rebuilt harness (`app/tools/exp012_measure.py`) is now committed, so the 8 K↔16 K comparison is reproducible in minutes; the Phase 0 survey is not.

**Root cause**: "Throwaway experiment script" defaulted to scratchpad. But any script that produced numbers cited in a committed EXP report is part of that experiment's reproducibility, whatever its code quality.

**Suggested improvement**: Any script whose output is cited in an EXP report gets committed alongside the report (`app/tools/` or next to the report) at first run — not at promotion time.

**Status**: open

**What went well (recorded, no action)**: (1) The pre-registered falsifiable hypotheses + decision matrix (written in the plan, before any data) made closure *mechanical* — H1 true + H2 false landed on a predefined row ("do not promote; revert input change") with zero deliberation. (2) The default-off `-DWR_INBUF_16K` knob made trial↔baseline a single build switch with nil production risk, and stays in-tree as a zero-cost re-arm. (3) The ur=1-per-session startup artifact (LL-094's grace-window rule, TASK-266's metric refinement) was re-confirmed systematically — every station, both builds, exactly 1 — strengthening TASK-266's case for excluding the initial-fill window from `wrUnderruns`.

## Retrospective — 2026-06-27 — M-MEMBUDGET design-batch panel review (3-agent)

### LL-089 — 2026-06-27 — Mechanism designed ahead of the gate that decides whether it is needed (design outrunning the product decision)

**Context**: A single session produced three design docs (M-MEMBUDGET, M-RECLAIM, M-PLAYER-STATE) + a spike PROP + ADR-047, for a feature (no-PSRAM WebRadio coexistence) whose product go/no-go is *still pending human direction* — ADR-047 is PROPOSED and its entire purpose is the unmade A-lite-vs-B call. M-RECLAIM in particular designed the Q3-b (vTaskDelete + null-safety audit) and Q2 (dataTask ref-count sequencing) mechanisms in full, while the batch's own ordering says those are "second priority, only if the spike's Phase 1 shows a shortfall after Q4 + Q3-a." The independent QM and PM both flagged the same shape.

**Observation**: This is design investment ahead of two gates: (1) the human product decision (ADR-047), and (2) the cheap Phase-1 measurement that determines whether the deeper reclaim (Q3-b/Q2) is even needed. It is *partly* justified — the ADR needs enough design detail to quantify A-lite's cost honestly, and the player-mode work (TASK-259/260) proceeds regardless of direction. But elaborating Q3-b/Q2 mechanism before the measurement that gates them is effort that the gate may render moot, and it is the same over-design shape the team has paid for before. The panel review itself was high-value (it caught a real allocator correctness bug), so the design depth was not wasted — but the *reclaim-mechanism* depth specifically was ahead of its gate.

**Root cause**: Momentum. Exploratory design is productive and the operator was driving it, so each "what about X" produced a full mechanism sketch rather than stopping at "X is gated on the spike — sketch only until then." There was no explicit depth-cap tied to the decision/measurement gates.

**Suggested improvement**: When an ADR exists specifically to tee up an unmade human go/no-go, **cap upstream design depth to what the decision needs**; defer mechanism-level design of anything gated on a *later* measurement until that measurement runs. Concretely applied this session: M-RECLAIM now carries a "scope discipline" note keeping Q3-b/Q2 at sketch depth until the spike's Phase 1 shows a shortfall. Candidate rule for the human: *"Design to the depth the next gate needs, not the depth the idea allows."*

**Status**: open — candidate; brought to human this retrospective (QM, alongside the panel-review dispositions). Note: independently corroborated by the PM state-assessment the same session.

## Retrospective — 2026-06-27 — Bottom-up bare-rig settles the no-PSRAM ceiling (TASK-258 / EXP-009)

### LL-087 — 2026-06-27 — Measure the hardware ceiling bottom-up with a bare control before grinding a top-down strip

**Context**: The no-PSRAM WebRadio viability question (does ADR-045's "no-PSRAM playback = NO-GO" hold?) was being pursued **top-down**: strip our 11-app build toward headless (`-DDISABLE_SPOTIFY`, then a full app strip) and re-measure free heap at `_play()`. EXP-008 showed this was a confirmed ~25–30 `#ifdef`-site M-effort grind whose outcome was a coin-flip — and each strip step left the *interpretation* confounded (a FAIL could be footprint, fragmentation, or a port artefact). The pivot was to build the **bare ESP32-audioI2S radio on our actual hardware** (same platform/board/library/DAC) as a true control — outside the repo, throwaway — and measure the ceiling directly.

**Observation**: The bare control answered in **one afternoon** what the top-down strip had not in several sessions: both configs (no-display and +full-CYD-TFT) **play** — decoder inits at ~165 K free and holds. That is decisive and confound-free: there is no app shell, no dataTask, no Spotify TLS to blame, so a PASS cleanly attributes "hardware + library work" and a FAIL would have cleanly killed the milestone. The top-down strip could never produce that clean attribution because every intermediate build still carried most of the confounds. It also corrected a measurement misread that had survived two prior experiments (see LL-088).

**Root cause**: We started from the artefact we had (our complex multi-app build) and tried to subtract our way down to the answer, because that build was in front of us. The cheaper, more decisive move was to *add up* from zero on the same hardware — a bare existence-proof control — which isolates the variable under test (the silicon/library ceiling) from the variable we actually care about reducing (our resident footprint). Same family as LL-082 (diagnosed the network when the bug was in the precondition): reaching for the complicated path when a minimal isolating control was available and cheaper.

**Suggested improvement**: When the open question is "can the hardware/library do X at all" (a ceiling/existence question) and the production artefact is a confound-heavy strip target, build a **minimal bare control on the real hardware first** — out-of-tree, throwaway, parity-pinned (same platform/board/lib/pinout) — and measure the ceiling bottom-up. Only spend strip effort once the bare control proves the ceiling exists *and* quantifies the budget the strip must hit. Reserve the top-down strip for the *fit* question (does our app fit under the bare budget), which is a different question (LL-086 / R2 bounded-claim: a bare PASS sets the budget, it does not prove our app fits).

### LL-088 — 2026-06-27 — A derived "budget" metric (usable = free − maxAlloc) was read as a fixed quantity when it was a state-dependent artefact

**Context**: EXP-007/008 framed the no-PSRAM decoder gate as `usable = free − 38,900`, where 38,900 was the `maxAllocHeap` / caps-restricted dead-block observed on our fragmented 11-app build, treated as a fixed hardware constant the audio path must clear. The bare-rig control (EXP-009) re-probed `heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)` on the *bare* build and got **110,580**, not 38,900 — the "dead block" was never a fixed quantity, it was the largest free block *of our fragmented heap state*. The real gate is total free heap at connect plus contiguity for the ~41 K audio path.

**Observation**: A number that was actually an *output of a particular heap state* (fragmentation under 11 live apps) was carried forward across two experiments as an *input constant of the hardware*. Decisions (budget math, the `usable < demand → abort` kill gate) were built on it. Because the bare control re-measured the metric from scratch instead of inheriting the figure, it exposed the misread; had it assumed "38,900 transfers," it would have computed a wrong budget and possibly mis-killed the milestone. (The PROP had explicitly flagged "re-probe the caps dead-block per build — do not assume EXP-007's 38,900 transfers," which is why it was caught.)

**Root cause**: A state-dependent measurement was promoted to a named constant ("the 38.9 K dead block") and the name made it feel fixed; subsequent reasoning used the name, not the measurement-in-context. Same family as LL-086 (a hypothesis built on a prior number without reconciling its meaning) — here the failure is one level down: the number was real but its *scope of validity* (this heap state only) was dropped when it was given a durable label.

**Suggested improvement**: Any heap/perf figure that is a function of runtime state (fragmentation, allocation order, which tasks are live) must be labelled with the state it was measured under, and **re-measured, never inherited, when the state changes** (different build, different live-app set). Treat `largest-free-block` / `maxAlloc` / "usable" as per-build observations, not constants. When carrying a number across experiments, restate the conditions it was measured under in the same sentence as the number. Pairs with LL-086 (reconcile a follow-on hypothesis against prior measurements) and the platformio.ini pinned-dep BP candidate below.

**Status (LL-087 + LL-088)**: reviewed with human 2026-06-27. **BP-042 adopted** (the pin-note rule, from the LL-088 / EXP-009 thread). LL-087 and LL-088 retained as standing lessons (no separate BP — they are reasoning-discipline lessons that inform BP-040's "gate mechanism must be consistent with prior measurements" clause rather than a new mechanical rule). Quality win recorded in audit_log 2026-06-27.

---

## Retrospective — 2026-06-26 — M-WEBRADIO-SPOTIFY-DISABLE design review (5-agent panel)

### LL-086 — 2026-06-26 — An experiment hypothesis must be checked against the prior experiment's measured findings before it is scheduled

**Context**: The `M-WEBRADIO-SPOTIFY-DISABLE` design (a `-DDISABLE_SPOTIFY` experiment to free no-PSRAM RAM for WebRadio playback) went through a 2-round, 5-agent panel review. Its rev1 hypothesis was: "not creating `spotifyTask` reduces TLS-session fragmentation → enlarges the largest contiguous DMA-capable block (`maxAlloc`), which is the wall the MP3 decoder hits." The immediately-prior experiment, **EXP-007 / TASK-233**, had already *measured* the opposite: `maxAllocHeap` was **pinned at 38,900 bytes in both the 8 KB and 16 KB input-buffer runs** — it is a caps-restricted region the audio allocator cannot use, and growing/shrinking allocations did not move it. The real lever EXP-007 identified was the *usable pool* (`free − 38.9 KB`) against the decoder's 22.7 KB demand.

**Observation**: The new experiment was built on a mechanism (`maxAlloc` is the wall and fragmentation drives it) that the prior experiment's own numbers contradicted. Had the panel not caught it, the experiment would have been scheduled to measure and optimise the wrong metric — and worse, a PASS or FAIL would have been *uninterpretable* because the predicted lever (`maxAlloc` rising) was one the prior data said is constant. R&D's round-1 challenge forced the correction to the usable-pool mechanism, which then yielded a falsifiable quantified prediction (+~8 KB margin) and a cheap, correct kill gate (`usable < decoder + buffer → abort`). The defect was a reasoning error sitting on top of available, contradicting measurements — not a lack of data.

**Root cause**: The follow-on experiment's hypothesis was written from a plausible first-principles intuition ("less fragmentation → bigger contiguous block") without cross-checking it against the measured outcome of the experiment it directly builds on. EXP-007's pinned-`maxAlloc` finding was in the report and in ADR-045's context, but it was not used as the gate the new hypothesis had to pass. This is the same family as LL-009 (architecture assumed an API surface without testing it), LL-071 (a "small fetch = low contention" intuition contradicted by measurement), and LL-084 (a BP rationale asserted conformance of code that was never checked): an intuition presented as a mechanism without reconciling it against the data already on hand.

**Suggested improvement**: When a design proposes a follow-on experiment or a memory/perf hypothesis that builds on a prior measured result, the hypothesis must explicitly state the prior experiment's relevant *measured* numbers and show the new mechanism is consistent with them (or explain why the prior measurement does not apply). The design-review panel treats "hypothesis contradicts the prior experiment's data" as a blocking finding. Concretely for this project: any M-WEBRADIO-NOPSRAM follow-on must reconcile against EXP-007's `maxAllocHeap`-pinned / usable-pool finding before scheduling. (Pairs with the experiment-lifecycle candidate BP-040: a scheduled experiment must name its gate; this lesson adds that the gate's *mechanism* must be consistent with prior measurements.)

**Status**: open — candidate; brought to human alongside BP-040/BP-041. Quality win recorded in audit_log 2026-06-26.

---

## Retrospective — 2026-06-24 — WebRadio taskbar crash (latent, shipped)

### LL-085 — 2026-06-24 — A design constraint with no enforcing mechanism + a test that bypassed the crash path

**What happened.** WebRadio (the 11th `AppId`) was designed as a taskbar-*hidden* app — entered only
via the Winamp eject toggle (M-WEBRADIO §). But the taskbar derived its slot count from `AppId::COUNT`,
so WebRadio leaked into the scroll cycle. Its `kTaskbarIcons[10]` entry was never baked (zero-filled
to null), so scrolling the taskbar to the WebRadio slot did `pushImage(nullptr)` → hard crash. Latent
for ~10 days; surfaced only when a user scrolled the taskbar there.

**Why it wasn't caught — three compounding gaps:**
1. **The "no taskbar slot" rule was prose, not code.** No `TASKBAR_APP_COUNT` distinct from the total
   app count; nothing enforced the exclusion, so it defaulted to leaking in.
2. **The test exercised a path that structurally can't crash.** The serialdbg harness entered WebRadio
   via `tap_taskbar_slot(WebRadio)`, which computes an *off-screen* y (420 > 240) that the tap handler
   maps via modulo to appId 10 → `switchApp` — entering WebRadio **without ever rendering its taskbar
   slot**. The crash lives in the *render* path (user scroll/gesture), which the tests never ran. The
   tests "passed" against a path that shouldn't exist (taskbar entry contradicts the eject-only design).
3. **No gate / checklist.** `run/check` didn't verify icon↔app-count conformance; NEW-APP-CHECKLIST had
   no taskbar item; the icon generator silently produced a short initializer (C++ zero-fill, no error).

**How to apply.**
- A design constraint (X is excluded / hidden / mutually-exclusive) is not done until there is a
  **mechanism** (a constant, a `static_assert`, a gate) that makes violating it fail loudly. Prose in a
  design doc enforces nothing.
- Tests must exercise the **user-reachable path**, not whatever the harness finds convenient. A harness
  shortcut (off-screen tap → modulo) that bypasses the rendering/interaction the user actually performs
  is worse than no test — it manufactures false confidence. (Compounds [[LL-064]]: happy-path-as-proof.)
- A "missing asset" for a new integration point should be a **compile error**, not a runtime null.
  Fixed here via `static_assert(TASKBAR_ICON_COUNT == TASKBAR_APP_COUNT)` + NEW-APP-CHECKLIST §6.

**Corrective actions (TASK-242):** `TASKBAR_APP_COUNT` excludes WebRadio at all taskbar call sites;
null-guard in `renderTaskbar` (defense-in-depth); two `static_assert`s (WebRadio stays last; icon count
== taskbar app count); NEW-APP-CHECKLIST §6; VE to switch the harness to eject-entry + add a
taskbar-scroll-cycle test.

## Retrospective — 2026-06-21 — Codebase-quality audit (DUT downtime, parallel sub-agents)

### LL-084 — 2026-06-21 — A promoted BP cited existing code as conforming evidence that was never audited

**Context**: BP-031 (tlsYield/tlsResume on every dataTask HTTPS fetcher) was adopted from LL-071. Its rationale text names `fetchWeather`, `fetchCrypto`, `fetchHeatmap`, `fetchStockChart` as fetchers that "already established the pattern." A code-quality audit (TASK-222) found `fetchWeather()` calls **neither** `tlsYield()` nor `tlsResume()` — it never conformed — and `fetchHeatmapQuote()` skipped `tlsResume()` on its `http.begin()` early-return path, which BP-031's own "how to apply" explicitly requires.

**Observation**: The BP was written and promoted citing four functions as positive examples without verifying all four. Two of the four cited/implied conformant fetchers were actually in violation. Worse, the act of adopting the BP did not trigger a sweep of the *existing* fetchers it governed — only new fetchers got scrutiny, so the pre-existing gaps survived from 2026-06-14 until this audit. The violations are real heap-contention/starvation hazards (the heatmap one is the same class as TASK-218).

**Root cause**: Two compounding habits. (1) A best-practice rationale asserted conformance of named code as supporting evidence without running the check — the same assert-without-verifying pattern BP-039 was promoted against, here inside the BP-promotion process itself. (2) Promoting a rule was treated as forward-looking only; no back-fill audit of the code already in scope was scheduled, so the rule documented an aspiration as if it were the current state.

**Suggested improvement**: (a) When a BP's rationale cites specific existing code as conforming, that conformance is part of the claim and must be verified at promotion time — ideally with a grep/command captured in the BP. (b) Promoting a BP that governs a known set of existing call sites should file a one-time back-fill audit task to bring the existing set into compliance, not just guard new additions. A standing check would help here: a host grep that lists every `fetchXxx()` in `dataTaskStorage.cpp` and flags any lacking balanced `tlsYield`/`tlsResume` on all exit paths (cf. `run/check-datatask-certs` for the cert analogue).

**Status**: open — improvement (a)+(b) proposed to QM/human; TASK-222 fixed the two violations; back-fill grep not yet built.

---

## Retrospective — 2026-06-20 — M-WEBRADIO TASK-214 root-cause re-check (downtime session)

### LL-083 — 2026-06-20 — A TLS root cause was accepted and committed without a host-side strict-verify

**Context**: TASK-214's DUT symptom was `get wrCount` returning 0 after every station fetch. Commit `dafa4a4` (2026-06-19) diagnosed the cause as "radio-browser.info omits the R13 intermediate from the TLS handshake, so `setCACert()` can't build the chain to ISRG Root X1," and landed an unconditional `tls.setInsecure()` fix — a path ADR-029 rejects categorically for non-Spotify endpoints. The commit message itself flagged "Not yet DUT-verified."

**Observation**: A downtime host re-check (`openssl s_client -connect de1.api.radio-browser.info:443 -CAfile <ISRG-Root-X1-only> -verify_return_error` — the exact strict offline build `setCACert()` performs) returned `Verify return code: 0 (ok)` against a **complete** chain (leaf → R13 → ISRG Root X1). The server *was* sending the intermediate, at least for `de1` (mirror[0], tried first) from this network. The committed root cause was contradicted in about two minutes by a check that could have been run before the fix was written. The original TASK-200 host probe *had* the right tool (`openssl s_client -showcerts`) but only read the issuer string and chain depth from it — never the strict offline verify result.

**Root cause**: The diagnosis relied on reasoning about mbedtls behaviour ("can't build the chain") without reproducing the failing verification on the host first. `openssl -showcerts` shows what the server *sends*; only `-CAfile <root> -verify_return_error` reproduces what `setCACert()` actually *does*. The two were conflated. This is the same diagnosis-ahead-of-verification pattern as LL-082 (chasing the network before reading the test spec) and LL-001 (TLS failures blamed on certs before checking the clock) — a recurring M-WEBRADIO habit of treating a plausible cause as a confirmed one.

**Caveat (kept honest)**: radio-browser.info is a federation of independently-run mirrors; chain completeness can legitimately differ by mirror/edge/time, and `nl1`/`at1` were not reachable from the sandbox to compare. So the original diagnosis is *disputed*, not *disproven*. The point of the lesson is not "the fix was wrong" — it is "a categorical-ADR-violating fix shipped on an unverified cause that a 2-minute host check would have challenged." The fix was re-scoped to try-`setCACert()`-first-then-fallback and `run/check-datatask-certs` was written so the strict check is now a standing, repeatable artifact rather than an ad-hoc command.

**Suggested improvement**: Promote to BP — a TLS/cert root cause is not accepted (and certainly not shipped as a verification-disabling fix) until reproduced on the host with the strict offline verify that mirrors on-device behaviour, not an issuer/`-showcerts` grep. ADR-029's quarterly check (BP-030) inherits the same blind spot and should adopt `run/check-datatask-certs`.

**Status**: adopted — BP-039 (2026-06-20, human-approved this session). Architect engaged on the ADR-029 governance consequence (conditional `setInsecure()` path) — see ADR-029 amendment note 2026-06-20.

---

## Retrospective — 2026-06-15 — M-WEBRADIO TASK-211/212 test session

### LL-081 — 2026-06-15 — State-injection test given a live-data precondition

**Context**: T_WR_ERR_01–04 test `set wrState N` — a serial debug command that directly assigns `_state` on the WebRadio app object. The implementation called `_webradio_enter_with_stations()` and skipped with "station list unavailable" whenever `get wrCount` returned `count=0`. The radio-browser.info API was returning 0 stations on the DUT (network/TLS issue unrelated to the feature under test), so all 4 tests skipped on every run.

**Observation**: The precondition `count >= 1` was copied from the helper used by station-dependent tests (COEX, HEAP_03/04, VOL_03). It has no logical connection to `set wrState`: the command sets a local enum field on the active app object. No station data is read or required. The test plan doc (`m-webradio-eject-errors.md`) states the precondition as "WebRadio app active" — not "stations loaded." The implementation diverged from the spec.

**Root cause**: The VE author reused `_webradio_enter_with_stations()` as a convenience entry point without checking whether its `count >= 1` gate was appropriate for injection-only tests. The helper name describes a superset of what ERR tests need.

**Suggested improvement**: When writing a test helper for a group of tests, check each caller's actual requirements against every guard in the helper. A guard appropriate for "play a station" is not automatically appropriate for "inject a state." Alternatively: split into `_webradio_enter()` (just switches app) and `_webradio_enter_with_stations()` (switches + requires count≥1), and have callers choose the minimum-sufficient helper.

**Status**: adopted — BP-037 (2026-06-15)

---

### LL-082 — 2026-06-15 — Agent diagnosed the network when the bug was in the test precondition

**Context**: Session began with 4 passed / 10 skipped on the WebRadio DUT suite. The 10 skips included T_WR_ERR_01–04 (state injection) and T_WR_COEX/HEAP_03/04/VOL_03 (live playback). The agent in auto mode diagnosed the skips by chasing why radio-browser.info returned 0 stations on the DUT: live API tests from host, openssl cert chain inspection, socket exhaustion analysis, TLS handshake theory, passive serial watch attempts across multiple sessions.

**Observation**: The ERR tests were skipping due to a wrong precondition in the test script, not due to a network or firmware bug. The fix was ~10 lines. The diagnosis consumed the bulk of two sessions — an estimated 90%+ of tokens spent — before the user intervened and asked "are we converging or in a silly debug loop?" Reading `m-webradio-eject-errors.md` at the start of the session would have surfaced the discrepancy in under 2 minutes.

**Root cause**: The agent treated all test failures as firmware or infrastructure bugs. It did not distinguish between "test is blocked on network" (correct SKIP) and "test has wrong precondition" (fixable in the test script). The observable symptom was the same in both cases (SKIP with "station list unavailable"), so the agent chased the symptom rather than validating the test's own logic against the spec first. Auto mode removed the human interaction point that would have triggered a re-read of the spec.

**Suggested improvement**: When tests skip or fail, the first diagnostic step must be: read the test's spec doc and verify the test implementation matches the intent. Only after confirming the test logic is correct should the agent investigate firmware or infrastructure. A 2-minute spec read before any DUT diagnosis is not optional. This is especially critical in auto mode where there is no human check-in to redirect misdiagnosis.

**Status**: adopted — BP-038 (2026-06-15)

---

## Retrospective — 2026-06-14 — M-WEBRADIO TASK-201 preview sign-off

Five bugs caught during T275 human sign-off that automated tests missed.

### LL-077 — 2026-06-14 — Boundary test verified code intent, not pixel output

**Context**: T277 ("canvas stays within 275×240 app area") passed a "numpy slice confirmed canvas shape (240,275,3)" check before TASK-201 sign-off. The check confirmed the PIL Image had the right dimensions. Meanwhile, `_draw_station_list` used `SCREEN_W - 1` (319) as the right edge of the row `fillRect`, overwriting the 45 px taskbar strip with black.

**Observation**: The test verified that no radio-drawing *function* explicitly targeted x≥275. It did not pixel-sample the rendered output at x=275..319 to confirm the taskbar was intact. The fillRect overflow was invisible to a shape check and invisible to a code-intent check.

**Root cause**: The test was written as a structural assertion ("canvas shape is 240×320") rather than a behavioral assertion ("taskbar pixels after render match expected taskbar content"). These are different claims; only the second one catches accidental overflow from a too-wide rectangle.

**Suggested improvement**: Any "no overflow" boundary test must pixel-sample the actual rendered output in the boundary zone, not just inspect canvas dimensions or code logic. Concretely: render all states, compare x=275..319 strip before and after radio drawing; assert the strip differs only where `draw_taskbar_pil` is known to write. A shape check does not substitute for this.

**Status**: candidate for BP — awaiting human sign-off

---

### LL-078 — 2026-06-14 — Preview-invented elements masked firmware rendering contract

**Context**: `preview_webradio.py` originally drew a second LED text row (ICY StreamTitle at y=36) and a "10 stations • NL" text overlay on the PLEDIT title bar. Neither element has a firmware counterpart. The POSBAR showed a synthetic blue fill-rect rather than the `POSBAR_BG blit + POSBAR_THUMB_N at position` sequence the firmware uses.

**Observation**: T275 is the layout sign-off gate before firmware implementation. If the preview shows elements the firmware will not render, sign-off approves a canvas that doesn't match the product. The ICY second row and title-bar text were only caught because the human sign-off reviewer asked "does the DUT actually draw this?", triggering a winampDisplay.h audit. The POSBAR fill-rect was caught because the reviewer recognised it was not a skin sprite.

**Root cause**: The preview was built iteratively and convenience overlays (labels, extra text rows) accumulated without being checked against the firmware rendering path. No process step required "compare every preview element to a concrete firmware call before T275."

**Suggested improvement**: Before T275 sign-off, require the Developer or Architect to produce a render element table: each element in the preview mapped to a concrete firmware call (or explicitly marked "preview-only / not in firmware"). Any "preview-only" entry that is not explicitly approved is a defect. The M-WEBRADIO.md §Firmware rendering notes section (added 2026-06-14) is the correct home for this contract.

**Status**: candidate for BP — awaiting human sign-off

---

## Retrospective — 2026-06-14 — M-TELETEXT post-ship DUT review

Three defects surfaced in first DUT use after milestone close (TASK-177–191, retrospective 2026-06-13/14). All three were invisible to the serial-debug test suite and only caught by manual use.

### What went wrong

- **Subpage navigation silently broken.** `parsePage("617-2")` via `atoi` returned 617, dropping the sub-index. Tapping SUBUP/SUBDN re-navigated to page 617 subpage 1 in a loop.
- **Numpad never implemented.** Code had an explicit comment "Keypad not yet implemented — cycle through presets as fallback." No task, no feature_inventory gap flag, no known-incomplete note in the test plan. Shipped as if complete.
- **Busy indicator not wired to TeletextApp.** `touch-004` was `proposed` in feature_inventory; TeletextApp never overrode `hasPendingAsync()`. Amber indicator never fired.

### Why the test suite didn't catch them

- **T270 (subpage nav)** existed but was blocked: `[NETWORK]` + `[Blocked: G1, G2]`. No injection-based alternative was designed to run synthetically.
- **T271 (numpad)** expected `KEYPAD_OPEN` in `teletextLastAction` — the test would have caught the gap — but was never executed (also blocked G2).
- **T-BUSY** suite (touch-004) was a pending Developer deliverable; never ran for TeletextApp.

---

### LL-074 — 2026-06-14 — Blocked test with no synthetic fallback = no coverage

**Context**: T270 (subpage navigation) and T271 (numpad boundary) were written but blocked by G1 (live network) and G2 (touch inject infrastructure). Neither had a synthetic injection-based path that could run without those preconditions.

**Observation**: The subpage parsing bug — `parsePage("617-2")` drops the sub-index via `atoi` — would have been caught by T270 if it could run. But "planned" + "blocked" effectively means "not tested." The gap persisted until first real DUT use.

**Root cause**: Tests that require live network data (G1) have no fallback path using `set teletextPageContent` injection to simulate the scenario synthetically. When infrastructure prerequisites are missing, the test is skipped, not approximated.

**Suggested improvement**: For any navigation test that requires live network data, design a synthetic fallback using the injection interface (`set teletextPageContent`). Inject a page body that contains the relevant `pn=ns…`/`pn=ps…` metadata, then exercise the zone. The injection mechanism already exists (TASK-183). A blocked test with no synthetic path is a test gap, not a blocked test.

**Status**: adopted → BP-034 (2026-06-14)

---

### LL-075 — 2026-06-14 — "Not yet implemented" comment in code = invisible tech debt

**Context**: `_handleStrip()` PAGE zone contained: `// Keypad not yet implemented — cycle through presets as fallback`. No task filed. `feature_inventory.yaml` did not flag the keypad zone as partial. No note in the test plan. The milestone closed and the feature shipped.

**Observation**: T271 expected `KEYPAD_OPEN` in `teletextLastAction` — the VE had correctly designed a test that would have caught the absence — but neither the code comment nor the missing implementation triggered a stop. The comment was invisible to the milestone close checklist.

**Root cause**: "Not yet implemented" in source code is not surfaced by any process step (feature_inventory review, audit, milestone gate). Code comments are not tracked artifacts. The placeholder behavior (preset cycling) was functional enough to pass all tests that could run, so the milestone appeared clean.

**Suggested improvement**: Any placeholder with "not yet implemented" must be backed by a filed task in `tasks.md` before the milestone closes. Alternatively, include a `// TODO(TASK-NNN):` reference so the gap is machine-traceable. A comment without a task is a wish, not a plan.

**Status**: adopted → BP-035 (2026-06-14)

---

### LL-076 — 2026-06-14 — Cross-cutting shell integration not audited when a new app ships

**Context**: `touch-004` (shell busy indicator, `hasPendingAsync()`) was designed as a cross-cutting mechanism that each app must opt into by overriding `hasPendingAsync()`. `TeletextApp` was the 10th app added. It did not override the method (default: `false`). `touch-004` remained `proposed` in feature_inventory — correctly flagged, but not connected to any new-app checklist.

**Observation**: The pattern "new app added → check cross-cutting integrations" does not exist. TLS yield (`tlsYield`/`tlsResume`) is checked because it's a compile-time pattern (you add the calls or the fetch has contention). `hasPendingAsync()` is silent — a missing override compiles cleanly, returns `false`, and nothing breaks at the test level.

**Root cause**: No checklist item at new-app integration time. cross_feature_matrix.yaml had no entry for teletext-001 × touch-004 until this session. The gap was structural: the connection was implied by the design but not enforced.

**Suggested improvement**: Add a Developer checklist item: when a new app is registered, review all `proposed`/`implemented` cross-cutting features and confirm the new app satisfies them (or explicitly defers). Candidates at this point: `hasPendingAsync()` for any app with async input, `touch-004` busy indicator, TLS yield for any dataTask fetcher.

**Status**: adopted → BP-036 (2026-06-14)

---

## Retrospective — 2026-06-13/14 — M-TELETEXT (TASK-177–191)

Triggering work: full M-TELETEXT milestone — NOS Teletekst live reader (10th multiapp slot). Firmware implemented across TASK-177–191. TASK-191 (T272 TLS heap contention test) closed last; three bugs surfaced and fixed during that single test run.

### What went well

- **Full on-host PoC before any firmware was written.** NOS API reverse-engineered, teletext control codes decoded, `preview_teletext.py` built with full 320×240 render + navigation, resource impact assessed — all before a single line of firmware was written. No rendering approach was discovered on hardware. This was the deliberate practice established from prior lessons.
- **T272 was well-designed and found the thing it was testing.** The test was scoped to confirm TLS heap contention under concurrent Spotify + teletext load. It confirmed real contention in debug build (`maxAlloc` 39–51 k, below the ~50 k TLS floor needed for a new NOS handshake while Spotify holds its session). Test design was correct and paid off.
- **T272 caught two additional bugs not in its original scope.** The early-boot no-enqueue bug and the null-byte parser bug were both found during T272 execution — not during a separate debugging session. Good test design creates free spillover coverage.
- **All three bugs fixed before anything shipped.** Nothing reached the user in a broken state. The test-then-fix sequence worked as intended.
- **tlsYield fix was mechanical.** < 10 lines; matched the existing pattern in `fetchWeather`, `fetchCrypto`, `fetchHeatmap` exactly. Well-established pattern absorbed the fix without architecture rework.
- **ADR-044 item 9 revised to match post-test reality.** The ADR did not stay stale; the test result drove a correction to the architecture record.

### What could have been better

- **ADR-044 item 9 was wrong at design time.** The design said "fetchTeletext follows weather pattern (no tlsYield)" — a reasoning error (see LL-071 below). The test had to correct the architecture.
- **`_lastFetch = 0` pattern was used in three places with a misleading comment.** `resume()` comment said "force immediate fetch" but the code did not deliver that guarantee during the first 60s of uptime (see LL-072 below).
- **Null-byte content was not anticipated.** ISO-8859-1 teletext content with binary control codes is a documented format; the parser used `String::indexOf()` which stops at null bytes (see LL-073 below).

---

### LL-071 — 2026-06-13 — Any new dataTask HTTPS fetcher should use tlsYield by default, not by exception

**Context**: ADR-044 item 9 stated that `fetchTeletext()` follows the "weather pattern (no tlsYield)" — the reasoning being that the fetch is small (1.1 KB, the smallest in the project) and fast, so TLS heap contention is unlikely. T272 confirmed real contention: debug build `maxAlloc` ranged 39–51 k while Spotify's persistent session held ~40 k; a new NOS TLS handshake needs ~50–70 k contiguous, which the fragmented heap could not satisfy.

**Observation**: Response body size is irrelevant to tlsYield necessity. TLS contention is about *concurrent open sessions*, not response duration. Spotify's session is held across its 60 s poll cycle. Any new TLS connection initiated while that session is open competes for the same ~40 k contiguous block — regardless of how quickly the new connection would complete once established.

**Root cause**: The design reasoning conflated "small response = fast fetch = low contention risk." The actual contention axis is "Spotify session open simultaneously with new handshake", which is always true while the Spotify task is running.

**Suggested improvement**: Any new HTTPS fetch in `dataTaskStorage.cpp` should match the `tlsYield()`/`tlsResume()` pattern already used by `fetchWeather`, `fetchCrypto`, `fetchHeatmap`, and `fetchStockChart`. The burden of proof should be on *removing* `tlsYield` (with measured evidence), not on *adding* it. "Small fetch" or "fast fetch" is not sufficient justification to omit it. ADR-044 item 9 has been corrected; this generalises to all future fetchers.

**Status**: adopted → BP-031 (2026-06-14)

---

### LL-072 — 2026-06-13 — `_lastFetch = 0` does not force an immediate fetch during the first `pollSecs` seconds of uptime

**Context**: `TeletextApp::init()` and `resume()` set `_lastFetch = 0`. `resume()`'s comment explicitly said "force immediate fetch." T272 triggered `set triggerTeletextFetch 1` at ~30s uptime with `_pollSecs = 60`. The fetch condition `millis() - _lastFetch >= pollSecs * 1000` was false at 30s (`30000 - 0 < 60000`). No fetch was enqueued within the test's 30s window; T272 failed.

**Observation**: `millis()` starts near 0 at boot. Setting `_lastFetch = 0` means "last fetch happened at the epoch" — not "last fetch happened a long time ago." The condition `now - _lastFetch >= pollSecs*1000` is only satisfied once `millis() >= pollSecs*1000`, i.e., after the first full interval has elapsed since boot. Within the first 60s, the intent ("fetch immediately") and the behavior ("not yet") are mismatched.

**Root cause**: The `_lastFetch = 0` idiom is only correct as an "immediate fetch" signal after the device has been running for at least `pollSecs` seconds. This is a semantic mismatch between intent and behavior during early uptime that is invisible to code review — zero looks like a "force-reset" sentinel but is actually "boot time."

**Fix**: `_lastFetch = millis() - (unsigned long)_pollSecs * 1000UL`. When `millis() < pollSecs*1000`, unsigned subtraction wraps to a large value; `now - _lastFetch = pollSecs*1000` exactly, satisfying the condition immediately at any uptime.

**Suggested improvement**: Any app with a periodic fetch timer that wants "fetch immediately on next tick" must use the `_forceNow()` helper pattern (or inline equivalent), not `_lastFetch = 0`. The `0` assignment silently fails during early boot and passes code review without a flag. Other apps that set fetch timers to `0` with the same intent should be audited (CryptoApp, WeatherApp `init()` paths).

**Status**: adopted → BP-032 (2026-06-14)

---

### LL-073 — 2026-06-13 — `String::indexOf()` stops at null bytes; binary or ISO-8859-1 bodies require `memcmp` scan

**Context**: NOS Teletekst response body (ISO-8859-1 encoding, ~1.1 KB) contains `\x00\x00` at byte positions 1065–1066 — teletext color/mode control codes — immediately before `</pre>` at position 1067. `body.indexOf("</pre>", preStart + 5)` returned -1. The body was fetched successfully (HTTP 200, full length); the parse step failed with "no `</pre>` block."

**Observation**: Arduino `String::indexOf()` delegates to `strstr()`, which treats `\0` as a C-string terminator. The search stopped at position 1065. ISO-8859-1 teletext content legitimately uses bytes 0x00–0x1F as control codes (text color, mosaic graphics mode, character set switching). These are content bytes, not terminators — but `strstr()` cannot distinguish them.

**Root cause**: The parser assumed the response body was a C-string–compatible format. It is not: it is a byte stream from an ISO-8859-1 document with embedded control bytes. Any function that wraps `strstr()`, `strchr()`, `strlen()`, or `String::indexOf()` will silently truncate or misreport on such content.

**Fix**: Null-safe `memcmp` scan: `for (int i = start; i <= rawLen - 6; i++) if (memcmp(raw + i, "</pre>", 6) == 0) { preEnd = i; break; }` over `body.c_str()` with `body.length()` as the length guard.

**Suggested improvement**: Any HTTP response body that could contain null bytes — binary content, legacy encodings (ISO-8859-1, Latin-1, Windows-1252), protocols that use 0x00 as a control code — is incompatible with Arduino `String::indexOf()`, `lastIndexOf()`, `strstr()`, `strchr()`, and anything built on C-string semantics. For such bodies: hold the raw buffer pointer via `body.c_str()` and use `memchr()`/`memcmp()` with the `body.length()` bound. Document the content type in the comment. Sister lesson to LL-017 ("a library that produces output is more dangerous than one that errors"): `String::indexOf()` returned -1 silently, not a crash, with no indication that the search stopped early.

**Status**: adopted → BP-033 (2026-06-14)

---

## Retrospective — 2026-06-13 — M-PREVIEW-FRAMEWORK

### What went well

- **Design doc was the right input.** The design was thorough — duplication map with exact line numbers, per-tool migration table, scroll-offset invariants — and implementation followed it exactly. No scope ambiguity mid-flight.
- **Verify skill caught a real crash.** `PreviewWindow.handle_event` referenced `pygame.K_Q`, which does not exist in pygame. Would have crashed on any keypress. Caught and fixed before commit.
- **Headless test strategy was sound.** Running each tool's render pipeline without a display (dummy SDL driver + proper sequencing after `pygame.display.set_mode()`) gave real signal. The first test run exposed the display-not-initialized problem and guided the correct assertion order.
- **Heatmap pixel invariants verified.** scroll_offset=2 computation, active indicator at (275,201), canonical palette — all confirmed in-process.

### What could have been better

- **No tasks filed before implementation.** Work was done directly from the design doc without creating tasks. TASK-192 is retroactive. PM flag.
- **Design doc exit criteria had a pixel off-by-one.** Spec said separator at y=39; both reference implementations (and this one) draw at y=40. Typo in the doc that would have caused a false-fail if someone automated the pixel check literally.
- **`pygame.K_Q` error is a class of bug.** The implementation and design doc both assumed `K_Q` exists. Pygame only has lowercase key constants. Neither code review nor the design caught it — only runtime exercise did.

---

### LL-069 — 2026-06-13 — Tasks not filed before milestone implementation
> ✔ Duplicate ID resolved (TASK-281, 2026-07-06): the 2026-06-28 reuse ("sensor-blind gate criteria")
> was renumbered to **LL-094**; this LL-069 is the sole 2026-06-13 "tasks not filed" entry. Historical
> citations of "LL-069 (sensor-blind gates)" now point to LL-094.

**Context**: M-PREVIEW-FRAMEWORK implemented in a single session directly from the design doc without creating tasks first.
**Observation**: TASK-192 is retroactive. If the session had been interrupted mid-implementation, there would be no tracked state of what was in progress.
**Root cause**: Design doc was immediately available and scope was unambiguous; the task-creation step was skipped as "overhead."
**Suggested improvement**: Even for single-session milestones, file a task stub (status: in_progress) before writing code. The overhead is one paragraph; the benefit is recoverable mid-flight state.
**Status**: open

---

### LL-070 — 2026-06-13 — Runtime exercise caught a crash that code review missed

**Context**: `PreviewWindow.handle_event` used `pygame.K_Q`, which is not a valid pygame constant. Design doc and code both contained the error.
**Observation**: The verify step (headless render + handle_event exercise) found the `AttributeError` immediately. Would have crashed the clock, heatmap, teletext, and vis live tools on any keypress.
**Root cause**: pygame key constants are all lowercase (`K_q`, not `K_Q`). Easy assumption error; not caught by reading because the typo looks plausible.
**Suggested improvement**: When implementing a new event-handling class, explicitly test each key branch at the surface (not just import). A five-line test covering `+`, `-`, `q`, unhandled is enough.
**Status**: open

---

## Retrospective — 2026-06-12 — M-TASKBAR-ICONS

### What went well

- **Icon design iteration was efficient.** B&W inactive / coloured active split gave a clear visual language. All 9 icons decided in one session with concrete feedback loops (overview PNG rebuilt after each decision).
- **Alpha-clipped gradient technique** solved the two-tone SVG problem cleanly (weather active: yellow sun, white cloud from one `partly_cloudy_day` SVG path).
- **Bake script matched existing pipeline pattern** — `.cpp` extension, `Pillow + numpy`, `shell_layout.h` parsed for constants, `golden.sha256` updated, `run/bake-icons` wrapper. Zero friction adding to build.
- **Build passed first time** after `.c` → `.cpp` rename (C++ scoping of `AppId::COUNT`).

---

### LL-066 — 2026-06-12 — Agent implemented full feature from ambiguous "continue" without explicit approval

**Context**: At end of prior session, the icon overview had been shown to the user. Their last message was empty (no text — reviewing). Session ran out of context. Next session opened with the user typing "continue". Agent interpreted this as permission to proceed with TASK-171 (bake script + `taskbar.h` wiring) and implemented the full feature end-to-end. User's first response was "wait, did you go ahead and implemented everything?"

**Observation**: An empty message at end of a session + a cold "continue" at the start of the next session was taken as implicit approval to cross the icon-review gate and implement. The user was surprised. They then said "flash DUT, I want to see" — indicating they were willing to proceed, but they had not consciously made that decision.

**Root cause**: "Continue" in an ambiguous context was treated as "continue with the next planned task", not "continue the conversation so I can tell you what to do next." The task sequence in `tasks.md` had a human review gate (TASK-170: "Review gate: @Architect signs off on icon set before bake script is written") that was not checked before proceeding.

**Suggested improvement**: When resuming a session after an explicit review gate, check `tasks.md` for the gate status before proceeding. A gate marked "open — waiting on human" is a stop signal, not a green light. "Continue" from a cold session start means resume context — it does not mean skip the next gate.

**Status**: adopted — BP-029 (2026-06-12)

---

## Retrospective — 2026-04-28 — ADR-006 direction change + M0 close + M1 spike + time-001 fix

Triggering work: re-scope of the Winamp UI architecture (ADR-006), creation and partial run of the M1 API capability spike, and the time-001 NTP fix that unblocked TLS on the DUT. Below: what went well, what didn't, individual lessons. All entries `open` until human sign-off promotes any to `best_practices.md`.

### What went well (no LL needed, recorded for balance)

- **Plan-first caught a costly redirection cheaply.** The original M1 ADRs prescribed a portable `core/` + `platform/` leaves layout with a PC-mirror build target. Asking the user "stay close to baseline?" *before* writing any code surfaced ADR-006 in one short exchange, superseding three ADRs (001/004/005) without rework.
- **Vendoring + tiny patch worked.** One 3-line `getBearerToken()` getter added to the vendored `SpotifyArduino`, documented in `LOCAL_PATCHES.md`, was sufficient to enable raw `audio-features` / `audio-analysis` GETs without forking semantics.
- **time-001 fix was definitive.** The DUT run produced a clear verdict: the TLS-layer error was 100% clock-related; the residual failure is purely credentials. No ambiguity; no further diagnostic loops needed.
- **Build-verify before flash.** Both env compiles caught no errors but the discipline ensured the DUT trip was strictly a verification step, not iterative debugging.

---

### LL-001 — 2026-04-28 — Diagnose ESP32 TLS failures by checking the clock first

**Context**: First DUT run of the M1 spike returned `ssl_client.cpp:37 _handle_error 0x0050` and `Status Code: -2` on every refresh attempt. Initial hypothesis tree included cert-trust, library bug, network flakiness, and only after host-side cert chain inspection did the system-clock theory surface.

**Observation**: ~30 minutes of diagnostic time + one user round-trip spent ruling out cert and network issues before naming the right cause. The fix itself (3 lines: `configTime()` + bounded wait) took five minutes to write.

**Root cause**: ESP32 has no RTC and the firmware never called `configTime()`. mbedTLS rejects certs whose `notBefore` is in the future and surfaces the failure as a generic send error rather than a cert-validation error code, which misleads the diagnostic order.

**Suggested improvement**: For any ESP32 / RTC-less Arduino target that does TLS, the very first diagnostic question on a TLS failure (especially first-after-boot) should be "is `time(nullptr)` past a sane epoch?" The fix is a one-liner template; ranking it ahead of cert trust saves time.

**Status**: open

---

### LL-002 — 2026-04-28 — Rotate leaked credentials immediately, do not defer

**Context**: TASK-006 was opened on the day of bring-up (TASK-001) when the refresh token was first pasted into a chat transcript. It sat as a backlog item for the rest of the session. Today's DUT run revealed Spotify's leak scanner had auto-revoked the token: `invalid_grant — Refresh token revoked`. The blocker now sits on user account access, which itself is currently impaired.

**Observation**: The leak window between exposure and revocation was the entire session. Had the rotation been done at TASK-001 close, M1 would not be blocked today. The deferral cost a milestone of progress.

**Root cause**: TASK-006 was treated as housekeeping rather than incident response. Rotation was framed as "do this before going public" rather than "do this *now* because the secret is in the wild."

**Suggested improvement**: Treat any credential exposure as a P0 incident-response item, not a queueable task. Specifically: a leaked OAuth refresh token requires (a) dashboard secret rotation and (b) re-issuing the refresh token, both before any further work. Don't pair it with other DUT work as "convenient batch" — block on it.

**Status**: open

---

### LL-003 — 2026-04-28 — Disable library-level secret debug output before flashing

**Context**: The vendored `SpotifyArduino` had `SPOTIFY_DEBUG` enabled, which causes the library to `Serial.print()` the full refresh-token-grant POST body — including refresh token AND client secret — on every auth attempt. With the auth path looping at 5 s, the leaked credentials were re-exposed to anyone watching the serial log on every retry, including in tmux capture buffers.

**Observation**: Even after we knew the credentials were leaked, the firmware kept loudly re-leaking them in cleartext on serial. Multiple capture-pane outputs in this session contain them.

**Root cause**: We accepted the upstream library's debug-default without auditing its log surface for sensitive output before the first flash.

**Suggested improvement**: When vendoring a library with auth handling, audit its debug logging before first flash. Specifically check for any `Serial.print` of client_secret, refresh_token, access_token, or auth bodies. If present, either disable the debug flag or redact the offending lines. Add to `LOCAL_PATCHES.md` if patched.

**Status**: open

---

### LL-004 — 2026-04-28 — Surface human-dependent prerequisites earlier in planning

**Context**: When TASK-006 (rotation) was queued for the next DUT trip, no one asked "do you currently have working Spotify dashboard access?" When the DUT was actually present and rotation was the next step, the user revealed they were having Spotify account/password issues, blocking the work mid-flight.

**Observation**: A 15-second up-front check would have re-ordered the session — we'd have done time-001 first (no account access required), then queued rotation for whenever it became viable. Instead, time-001 happened anyway but only after a stalled rotation attempt.

**Root cause**: Plans surfaced *technical* prerequisites (DUT, build env, library vendoring) but missed *human* prerequisites (account access, dashboard permissions, physical hardware presence).

**Suggested improvement**: For tasks that depend on humans clicking external dashboards, paying for services, or accessing personal accounts, add a pre-flight question to the plan or the AskUserQuestion call: "is access to X working right now?" Treat it on equal footing with technical preconditions.

**Status**: open

---

### LL-005 — 2026-04-28 — Populate `cross_feature_matrix.yaml` from feature creation, not retrospectively

**Context**: The matrix was untracked and empty until the time-001 fix. The api-001 ↔ poll-001 interaction (`X002`, spike reads `lastTrackUri`) was a known coupling at api-001 creation time but only got recorded when X001 forced the file to exist.

**Observation**: AGENTS.md / `developer.md` says: "Two+ features share state, have dependency, or could conflict, record immediately. Call interactions out explicitly — no mental notes." This was violated for ~2 hours by carrying api-001 ↔ poll-001 as a mental note.

**Root cause**: Habit. The first matrix entry feels heavyweight when the file is empty; subsequent entries are easy. Inertia.

**Suggested improvement**: When introducing the *first* feature with any cross-feature link, promote `cross_feature_matrix.yaml` from untracked to tracked in the same commit, and add the entry. Don't wait for a "second" interaction to justify the file.

**Status**: open

---

### LL-006 — 2026-04-28 — `#ifdef NFC_ENABLED` vs `#define NFC_ENABLED 0`

**Context**: Disabling NFC for TASK-004 required commenting out the `#define`, not setting it to 0, because the codebase uses `#ifdef` (which is true for any value). A comment was added at the define explaining this.

**Observation**: This worked but only because the developer noticed the gotcha mid-edit. A user instruction "set NFC_ENABLED 0" would have silently failed if executed literally.

**Root cause**: Mixing `#ifdef` for presence-check with a value-bearing macro `#define X 1` is a known C-preprocessor footgun. The codebase shipped with this pattern; we inherited it.

**Suggested improvement**: When encountering `#ifdef X` with `#define X 1`, flag the inconsistency. Either standardise on `#if X` (value-aware) or strip the value (`#define X` with no payload). For now, leave the comment block at the define so the next reader doesn't repeat the trap.

**Status**: open

---

### LL-007 — 2026-04-28 — `pio run` vendored copy: strip nested `.git` before staging

**Context**: When vendoring `SpotifyArduino` from `.pio/libdeps/cyd2usb/SpotifyArduino` to `lib/SpotifyArduino`, the upstream's `.git/` directory came along. `git add lib/` then warned about an embedded repository and would have left it as a submodule-ish reference rather than vendoring the contents. Caught and fixed by removing the nested `.git` and re-staging.

**Observation**: A second's friction; but the alternative outcome — committing a submodule pointer to upstream — would have left the patches floating outside git.

**Root cause**: PlatformIO clones lib_deps from git when given a URL; the cache retains the upstream `.git/`.

**Suggested improvement**: When vendoring out of `.pio/libdeps/`, always: `cp -r src dst && rm -rf dst/.git` before `git add`. Add to a project-level "how to vendor" note if vendoring becomes a recurring pattern.

**Status**: open

---

### LL-008 — 2026-04-29 — `WiFiClientSecure` reuse breaks non-GET on Arduino-ESP32

**Context**: TASK-007 spike run. Library makes a `getCurrentlyPlaying` GET successfully, then any subsequent `nextTrack` (POST) or `pause` (PUT) on the same client object fails at `client->println()` with mbedTLS `0x0050 (NET_CONN_RESET)`. GETs still succeed indefinitely; non-GETs fail consistently.

**Observation**: A whole class of API calls — every control endpoint the Winamp UI needs — is broken on the current stack despite the library's API surface looking complete. `audio-features` / `audio-analysis` (both GET, made via raw `makeGetRequest`) DID reach Spotify and return authoritative HTTP responses, confirming the issue is specifically non-GET on the shared client, not GETs in general.

**Root cause** (hypothesised, to be confirmed during TASK-009): Arduino-ESP32 2.0.17 `WiFiClientSecure` does not always reset its TLS context cleanly across `stop() → connect()` cycles. The library's `makeRequestWithBody` path (PUT/POST) calls `client->flush()` then `client->connect()` then writes headers — the write fails because the prior TLS context isn't fully torn down. The GET path happens to work, possibly because of how its specific timing or buffer state aligns. This is a documented class of bug in the ESP32 Arduino TLS stack.

**Suggested improvement**: For any Arduino-ESP32 firmware doing both GETs and POST/PUTs to the same TLS host, do **not** share a single long-lived `WiFiClientSecure` across request types. Either allocate a fresh client per request (heap fragmentation risk to manage), or — better — use `HTTPClient` which manages connection lifecycle internally. Spike-style harnesses should test at least one GET and one non-GET before declaring a library "works."

**Status**: open

---

### LL-009 — 2026-04-29 — Spotify deprecated `audio-features` / `audio-analysis` for new Developer apps

**Context**: TASK-007 spike run. Both `GET /v1/audio-features/{id}` and `GET /v1/audio-analysis/{id}` return HTTP 403 for the dev account's app `db2ff394...` (created during TASK-001 in 2026-04-26). ADR-002 had architected the entire VU-meter feature around `audio-analysis` data, with `audio-features` as a fallback — both gates closed.

**Observation**: An architecture decision (ADR-002) that looked solid at design time was based on an API capability Spotify has since revoked for new app registrations. The deprecation was announced in late 2024 (Spotify Web API change-log) and our app, registered post-deprecation, has never had access. The architecture review missed the policy/access dimension entirely.

**Root cause**: Architecture review treated Spotify's API as a given technical surface, not a policy surface that the API provider can constrain by app age, by approval status, or by quota tier. We did not check the API change-log against our app's registration date, or test the endpoints during architecture (they would have returned 403 then, too).

**Suggested improvement**: For any architecture decision that depends on a third-party API endpoint, the architect should — as part of the decision — verify the endpoint actually returns data for the app in question, not just that it exists in the documentation. Where the provider distinguishes app tiers (Spotify Extended Quota Mode, Twitter elevated access, etc.), record which tier the project assumes and what happens if that tier becomes unavailable.

**Status**: open

---

## Retrospective — 2026-05-07 — Multi-day session, M4 close + M2 tier 1 + dev-001 back-fill

Triggering work: M4 polish (TASK-011), M2 skin bake tool tier 1 (TASK-012), and back-filled tracking for the cellular/captive-portal dev infra (TASK-013, dev-001) shipped during the 2026-05-05/06 field-debug session.

### What went well

- **Bake tool delivered on first attempt with working preview.** Pillow + ImageMagick fallback handled all three Winamp BMPs; output compiled clean; preview composite matched layout on visual check.
- **DNS override + HTTPS-Date stack designed iteratively against real failures.** Each shim was pulled out only when a specific upstream condition (DNS block, NTP block, captive-portal MAC gating) was confirmed by a separate experiment. No speculative infrastructure.
- **MAC-spoof workaround for Marriott captive portal was diagnosed correctly.** TLS error -9984 with a now-correct clock pointed at portal interception; pre-auth via NetworkManager `cloned-mac-address` resolved it without firmware changes. Captured as procedure (memory file), not committed code.

### LL-010 — 2026-05-07 — Multi-role inter-agent protocol skipped under "single-voice" execution

**Context**: M4 close (TASK-011) and M2 tier 1 (TASK-012) both shipped without an Architect consult, VE testability challenge, or QM prompt. The 2026-05-05/06 dev-infra work shipped without *any* PM tracking — no task entry, no feature_inventory entry, no test plan. All caught by a 2026-05-07 self-audit, then back-filled.

**Observation**: When one operator plays every role, the inter-agent protocol from `AGENTS.md` (Developer→VE notification, Developer→Architect consult, PM→QM prompt, etc.) collapses into one internal voice. The mechanical conventions (commit messages with feature IDs, ADR consultation before scope decisions) survived; the structured hand-offs did not. Result: ~50% of the documented protocol followed, with the gaps clustered in cross-role notifications.

**Root cause**: Direct-invoke model (`@PM`, `@Architect`, `@VE`) is a discipline, not a tool. Without an explicit "switch hat" prompt at boundaries (feature implemented → notify VE, scope decision → consult Architect, milestone partial-complete → prompt QM), the operator stays in whichever role started the work and skips the cross-role steps.

**Suggested improvement**: For Developer-initiated work, add a checklist gate before commit: (a) Architect consulted on any scope-defining decision not covered by an existing ADR? (b) VE notified with a test entry (even if `planned-deferred`)? (c) `feature_inventory.yaml` updated? (d) PM informed via `tasks.md` entry? Failing any of these is fine — but should be a deliberate "skip with reason," not an oversight. Same gate applies in reverse for tasks PM tracks but no one implements.

**Status**: open

### LL-011 — 2026-05-07 — Dev-environment infra still belongs in PM tracker

**Context**: The 2026-05-05/06 cellular + captive-portal mitigation work (~300 lines of code, three new modules, one helper script) shipped with no `tasks.md` entry, no feature_inventory entry, no test plan. Rationale at the time: "this is dev-environment infra, not roadmap-bearing." Caught and back-filled as TASK-013 / dev-001 a day later.

**Observation**: The "not on the roadmap" framing led to "not tracked at all," but the work is in tree, has cross_features (`wifi-001`, `time-001`), and will need maintenance the moment a future user hits a different hostile-network condition. Treating it as untracked left the PM and VE with no signal that this surface area exists.

**Root cause**: PM tracking conflated with milestone tracking. The roadmap is milestone-level; `tasks.md` is broader and should cover any work that produces durable artefacts.

**Suggested improvement**: Any commit that introduces a new file under `Spotify-Diy-Thing/SpotifyDiyThing/` or `tools/` gets a `tasks.md` entry, regardless of whether it advances a milestone. If it doesn't fit any milestone, it goes in a "Dev infra" section.

**Status**: open

### LL-012 — 2026-05-08 — `WiFiClientSecure::lastError()` is a misleading name

**Context**: TASK-018 follow-up, debugging `HTTP -1` from the vendored Spotify lib. We added `client.lastError(buf, sizeof(buf))` to surface the underlying mbedtls code on `-1` returns.

**Observation**: Every `-1` reported `rc=49 (0x0031)`. mbedtls_strerror printed "UNKNOWN ERROR CODE (0031)". Spent two reflash cycles theorising about exotic socket errnos before realising 49 was the lwip socket fd from the *previous successful* `start_ssl_client` call. Arduino-ESP32 stores `_lastError = ret` where `ret` is the start_ssl_client return value — positive socket fd on success, negative on mbedtls error. The function name implies "last error" but the value is "last result", retained even when the previous call succeeded.

**Root cause**: API name doesn't match semantics. Doc string for `lastError()` doesn't clarify; we trusted the name.

**Suggested improvement**: For sticky-state APIs whose names suggest a single semantic, confirm by reading the source before building diagnostic chains on top. Treat any positive return from `lastError()` as "stale success state, not a current error." Comment the discriminator at every call site.

**Status**: open — fix already in `spotifyLogic.h` (rc>0 prints as "stale connect fd"). Promotion candidate.

### LL-013 — 2026-05-08 — Same numeric error code can mask multiple root causes

**Context**: ADR-007 patched the `WiFiClientSecure` reuse bug — fixed mbedtls `0x0050 NET_CONN_RESET` on the *first* write of a stale TLS session. Spike harness retest (one week later) still produced `0x0050` on every PUT/POST. Knee-jerk: "ADR-007 didn't actually fix it." Reality: three independent lib bugs (trailing-CRLF health check; `Content-Type: application/json` with `Content-Length: 0`; strict `204`-only status check) all produced `0x0050` at the same `send_ssl_data():382` log line. Different root causes, same numeric symptom.

**Observation**: When a fix doesn't move the needle, "the fix didn't work" is the easy hypothesis. "The same error number is masking a different bug" is the harder, more often correct one. ADR-007 *was* working; the next bug in the chain just wore the same uniform.

**Root cause**: TLS-level errors are a small enumeration; many distinct code paths funnel through the same layer and report the same code. mbedtls 0x0050 means "peer reset" — that can happen at any write, for any reason that prompts the peer to close.

**Suggested improvement**: Treat numeric error codes as the *symptom*, never the *cause*. Cross-check with: where in the request stream did the failure happen (first write vs last write — different cause); did the server send a response before the close (means a different protocol-level reject); does the lib's request shape match what the server documents and accepts (spec cross-check)? Don't accept "the fix didn't work" until each of those is checked.

**Status**: open — caught and patched (LOCAL_PATCHES.md #4–6). Promotion candidate.

### LL-014 — 2026-05-08 — Don't blame the network without a positive test

**Context**: After the ADR-007 retest failed all 15 spike rows on Marriott guest WiFi, my first hypothesis was "captive portal blocks non-GET HTTPS methods". User pushed back: AP-level method filtering of HTTPS is implausible without TLS MITM, and we had no MITM evidence (cert validation was passing on GETs). The "method filtering" hypothesis required a mechanism inconsistent with other observed facts.

**Observation**: A flaky network is a tempting target. Hard to falsify (every retry is a new chance to see the same flake). Easy to write up as "network was bad, network was bad again." Real diagnosis is more demanding — it requires a chain of mechanism, not a chain of correlations.

**Root cause**: Cognitive cheap shortcut. Network blame is the embedded equivalent of "have you tried turning it off and on again."

**Suggested improvement**: Before blaming the network for a *consistent* failure mode (sporadic ones really often are network), require either (a) a positive test that excludes the firmware/lib (e.g. curl from host succeeds where DUT fails), or (b) a mechanism explanation consistent with every other observed fact. If neither is available, treat "it's the network" as a hypothesis on equal footing with "it's the lib", not the default.

**Status**: open — directly applicable to TASK-019 / future M-IO investigations. Promotion candidate.

### LL-016 — 2026-05-09 — "Swap X" is under-specified when a feature has multiple layers

**Context**: M-CHROME tier 1 mono/stereo indicator. User said "mono and stereo needs to be swapped." I changed it. User said "swapped again." I changed it back differently. User said "both unlit." I added a default + snapshot-seq refresh. User said "stereo lit, mono dim. just swap stereo and mono please." Final fix: swap two `blitSprite` call positions. **Four reflash cycles to land a one-line change.**

**Observation**: the visible state of a sprite-based indicator is the composition of *three* layers: (a) where the labelled pixels live in the source BMP atlas (UV mapping), (b) the runtime state assignment (which sprite is "lit" given the current data), (c) the on-screen position (where each sprite gets blitted). "Swap" is ambiguous across all three. I picked the wrong layer twice, lost ~5 minutes of DUT-iteration churn each time, and burned the user's patience.

**Root cause** (multi-stage):
1. **First round, didn't even look at the asset.** Picked layer (a) on intuition before examining the BMP. Should have extracted + zoomed the bitmap *first* — the visual ground truth was 30 seconds away.
2. **Conflated bugs.** "Both unlit, swapped again" is two reports. I treated it as "fix the swap, the unlit will resolve when polls land." I should have decoupled them — the unlit was a separate timing bug (snapshot.valid=false at boot before any poll).
3. **Defaulted to canonical-Winamp layout instead of asking.** Even after the atlas was correct, on-screen position is a UX preference. The canonical Winamp main window has stereo-left, mono-right. The user's preference is the opposite. That's not wrong; that's a choice. I shouldn't have argued with the visual layout via implementation — should have just asked.
4. **Test cycle is expensive when the request is ambiguous.** Each guess cost: edit → bake → build → flash → wait for WiFi + first poll → user observes. ~30–60 seconds. With ambiguity, that's a terrible feedback loop. **Asking one clarifying question costs five seconds.**

**Suggested improvement**: when a user request maps onto a sprite-based feature, default-question is *"do you mean the source atlas, the data → sprite mapping, or the on-screen position?"* Ask before changing. Cheaper than guessing. Also: for any request involving an asset, look at the asset before changing code. The thirty-second image-extract path beats the five-minute reflash-and-test path every single time.

**Status**: open — promotion candidate. Same family as LL-014 (don't blame the network without a positive test): "diagnose before guessing" generalises.

### LL-015 — 2026-05-08 — Optimistic-UI mutations must outlive the same loop iteration

**Context**: M5 implementation. Touch handler set `songStartMillis = 0` to freeze the M4 interpolator on pause-touch and set `requestDueTime = 0` to force-poll. Both inside the same `checkForInput()` call. Bar continued ticking visibly post-pause anyway.

**Observation**: Loop order is `checkForInput()` → `updateCurrentlyPlaying()` → `updateProgressBar()`. The `requestDueTime = 0` triggered an immediate GET in the *same* loop iteration; the GET raced Spotify's pause-commit, re-anchored `songStartMillis` from `is_playing=true`, and `updateProgressBar` at the end of the same iteration resumed ticking. The optimistic mutation got steamrolled before the very next render.

**Root cause**: "Optimistic UI" only works if the optimistic state survives long enough for the user to see it. In a single-task super-loop, "long enough" is at least one render — i.e., the optimistic state must NOT be invalidated by something else later in the same iteration.

**Suggested improvement**: When applying an optimistic mutation, check the loop's downstream code paths for anything that can rewrite the same state in the same iteration. If a force-action (force-poll, force-redraw) is part of the same handler, delay it past the next render or guard the optimistic state against the rewrite explicitly. Tier-1 fix here: defer the re-poll by ~1500 ms instead of firing immediately. Tier-2 (deferred): a `local-state-authoritative-until` window that suppresses poll re-anchoring during the optimistic phase.

**Status**: open — partial fix shipped (deferred re-poll). Promotion candidate.

*Second concrete instance (2026-05-10, TASK-045)*: drag-to-set volume slider exhibits the same risk shape on continuous-touch input rather than single tap. Solved here with a tier-2-style mechanism: `WinampDisplay::optimisticVolumeUntilMs` is set to `now + 2000` on every drag sample, and `spotifyLogic.h::updateCurrentlyPlaying` skips the snap-driven `drawVolume` dedup gate when `millis() < getOptimisticVolumeUntil()`. The optimistic state is now authoritative for a bounded window across loop iterations, regardless of how many polls land in between. ADR-016 §10 captures the decision; the abstraction (`getOptimisticVolumeUntil()` virtual on the display interface) is reusable for any future per-element optimistic-write surface (e.g., scrub-to-seek's progress bar). Promotes the LL-015 suggestion's tier-2 idea into delivered code.

### LL-017 — 2026-05-09 — A library that produces output is more dangerous than one that errors

**Context**: TASK-042. User reported BALANCE.BMP composite was wrong on screen ("thin 2-pixel strip surrounded by cyan"). Four prior rounds of investigation had me adjusting crop coordinates, transparency keys, and on-screen positions — none of which were the actual bug. The bug was that Pillow 11.3.0 silently mis-decodes BI_RLE8 streams that use the delta opcode (`00 02 dx dy`) — ~56 % of pixels in BALANCE.BMP came out at the wrong x coordinates, but `Image.open(...).load()` returned successfully and an `Image` object containing garbage was used downstream as if it were correct.

**Observation**: ImageMagick fails with an explicit error on the same file (`unable to runlength decode`). That's a clean failure — caught instantly, easy to route around. PIL's behaviour is the opposite: success-with-wrong-output. The `try/except (ValueError, OSError)` fallback to magick existed in the bake tool, but never fired because PIL never raised. Every bake produced byte-identical (and consistently wrong) output, so the existing T025 determinism check happily kept passing on garbage.

**Root cause**: my mental model of the decoder was binary — "PIL decodes, or raises." A third state ("PIL decodes wrong, silently") wasn't on my failure-mode list. Once it was, the right action was to *not trust the library* — own the decode in our own 30 LOC, byte-validate against a third-party reference (ffmpeg), and only then trust the output.

**Suggested improvement**:
- For any third-party data-pipeline library handling formats with corner cases (rare opcodes, exotic chroma subsampling, weird metadata), produce a **second independent decode** for the file class actually in use, and assert byte-equality at integration time. If the library disagrees with the second source, treat the library as suspect — don't reach for "must be a config flag we missed" reflexively.
- For binary inputs whose pixels we ship in flash, prefer to **own the decoder for the format subset we depend on**. The maintenance cost of 30 LOC of opcode-walking is much lower than the cost of debugging a silent-corruption bug in production firmware.
- When a fix changes only crop coordinates / placement values without explaining the new pixel data, that's a signal the bug is upstream of the placement layer. Re-check the data extraction before adjusting placement.

Sister rule to LL-014 (don't blame network without a positive test) and LL-016 (look at the asset before changing code). Theme: **diagnose at the actual data, don't accept what a layer above says without independent confirmation.**

**Status**: open — promotion candidate. Process implication: when introducing a library dependency on a data-pipeline path, the ADR for that decision should call out *"how do we know the library produced correct output, not just non-error output?"* — that question wasn't asked in ADR-008 and the silent-corruption bug landed undetected.

### LL-018 — 2026-05-10 — Spec-vs-server divergence is structural, not exceptional (LL-013 v2)

**Context**: TASK-041 (M-CHROME tier 2 dynamic VOLUME) shipped end-to-end at commits b8f37d3..8075176, faithful to ADR-014 Amendment 1. T070a/T070b verification on the DUT (2026-05-10) found `Snapshot.volumePercent` stays at the `-1` sentinel on every successful 200 OK poll, regardless of which Spotify Connect device is active or what its volume is.

The lib parser is correct. The bug is upstream: `/me/player/currently-playing` does **not** include the `device` field at all, even though the OpenAPI spec (`resource/web-api/official-open-api.yaml:4701, 4967-4985`) declares the response shape as `CurrentlyPlayingContextObject` which has `device` as a top-level property. The server returns a subset; the spec describes the union. `device` is only actually returned by `/me/player`.

**Observation**: This is the **second concrete instance** of the same pattern that drove LL-013. First instance (M1 spike, 2026-05-08): the spec said player-control endpoints return 204, server actually returns 200, and the lib's strict `return statusCode == 204` flagged every successful call as failure. Second instance (here): the spec said `/me/player/currently-playing` returns the full `CurrentlyPlayingContextObject`, server returns a subset.

**Root cause**: The Spotify OpenAPI spec models multiple endpoints with the same response schema reference (`CurrentlyPlayingContextObject`) for documentation convenience. The server actually returns *different* shapes for those endpoints. The spec is a description of the *union* of fields any of those endpoints might surface — not a contract any single endpoint guarantees. Treating the spec as a contract for one specific endpoint is the trap.

**Suggested improvement**:

1. **Pre-merge wire capture for any lib-filter patch.** Any ADR or LOCAL_PATCH that depends on a documented field being present in a specific endpoint's response must include a `curl` dump showing the field is *actually* in that endpoint's response, captured against the project's own credentials. 30 seconds of work per patch; would have caught both LL-013 instances at design time.
2. **Treat the OpenAPI spec as an over-approximation, not a contract.** When designing an endpoint consumer, ask "what does the server return for *this specific endpoint*?" and verify, rather than "what does the spec say the response shape is?".
3. **Promote LL-013 + LL-009 to best-practice rules.** Two concrete instances of LL-013, plus the same family as LL-009 (verify endpoint access for the project's actual app, not just the documented API surface). Three data points across the project. Strong promotion case — these aren't isolated mistakes, they're a recurring class.

Sister rule to LL-013 / LL-009 / LL-014 (don't blame the network without a positive test). Theme: **the wire is the source of truth; documentation is one input among many.**

**Status**: open — strong promotion candidate. Process implication: ADR-015 establishes the precedent of including wire capture inline in the ADR's evidence section; subsequent ADRs touching API filters should follow the same pattern.

*Verification evidence (2026-05-10)*: ADR-015's URL change verified end-to-end on the DUT. T073 (host-side wire-comparison) caught the bug class directly in ~3 seconds without needing a flash cycle — exactly the discipline this LL prescribes. T070a / T070b PASS on first attempt against the new endpoint. The 30-second wire-capture step at design time would have prevented this entire investigation cycle.

---

### LL-019 — 2026-05-16 — Implementation specs written before R&D measurements produce high error rates

**Context**: TASK-050a/b/c (M-VIS) were written on 2026-05-16 as detailed implementation specs before any pixel-accurate R&D measurements were taken. R&D reports (M-VIS-spectrum-analysis.md, M-VIS-waveform-analysis.md) landed the same day after the specs were already in tasks.md. The Architect's comparison found 5 wrong values in TASK-050b alone (bar count 38→19, bar width 2px→3px+1px gap, colour method threshold→row-lookup, decay constant 0.008f→0.0625f, peak dot size 1px→3px) and 3 wrong values in TASK-050c (colour TFT_GREEN→white, render method single-pixel→vertical-fill, midline y=49→y=50). None of the wrong values were individually implausible — they were all reasonable from first principles. The aggregate was wrong enough to produce a visibly incorrect result on DUT.

**Observation**: Specs written from memory, analogies, or first principles before measurement are unreliable for pixel-level behaviour. In this case "38 bars" came from halving a round-number estimate; "green/yellow/red threshold colouring" from a generic spectrum convention; "drawPixel per column" from a minimal interpretation of the oscilloscope spec. Each looked reasonable alone. The actual Winamp behaviour (19 bars, absolute-row colour table, vertical fill between samples) was only discoverable by measuring the real renderer. No gate existed to prevent the spec from being treated as authoritative.

**Root cause**: The spec was written in the same session as the R&D was ordered, with the implicit assumption that the spec could be drafted from knowledge and corrected after. The tasks.md format does not distinguish "measured" from "estimated" values, and nothing flagged the spec as provisional while R&D was in flight.

**Suggested improvement**:
1. When a design spec depends on pixel-accurate measurements (vis geometry, colour values, animation rates), mark it explicitly as `[PROVISIONAL — awaiting R&D]` until the R&D report is available. Do not write specific numbers until they are measured.
2. Implementation gates: Developer should not start a task whose spec carries a `[PROVISIONAL]` tag. The R&D measurement must arrive and be incorporated by the Architect before coding begins.
3. This applies especially to any spec derived from observing a third-party renderer (Winamp, Media Player, etc.) — "it looks like X" without frame-by-frame analysis is always provisional.

Sister rule to LL-016 ("look at the asset before changing code") and LL-017 ("a library that produces output is more dangerous than one that errors"). Theme: **measure the ground truth before writing implementation numbers.**

**Status**: open — promotion candidate. First instance on this project; preventive catch (no implementation had started when caught). Strong promotion case for projects with any asset-measurement-dependent feature work.

---

### LL-020 — 2026-05-16 — Derived values in R&D reports must be independently verified before spec adoption

**Context**: M-VIS spectrum colours. The R&D report `M-VIS-spectrum-analysis.md` correctly measured 16 RGB888 pixel values from video frames. It then provided a computed RGB565 column — the values that went into the design doc and the code. All 16 RGB565 values were wrong: the conversion formula was misapplied (e.g. row 0 RGB888=(239,49,16) → correct RGB565=0xE982; report said 0xE903, which decodes to (239,32,24)). The design doc propagated all 16 wrong values verbatim. The code matched the spec correctly. Error caught on DUT visual inspection after flash; fix was a 4-line Python one-liner.

**Observation**: The R&D report contained two kinds of data in the same table: *measured* values (RGB888 — correct, derived from video frames) and *computed* values (RGB565 — wrong, derived by formula from the measured values). Nothing in the table distinguished them. The design doc consumed the RGB565 column as measurement output, not as a derived step that could have its own error. The pipeline was: measure → compute → spec → code — with no verification gate between compute and spec.

**Root cause**: Format-conversion steps inside R&D reports are treated as reporting of facts, not as computations that can contain errors. No convention exists requiring derived values to include the formula used or a verification command. Because both columns were in the same table under the same "measured" framing, the computed column inherited the credibility of the measured column.

**Suggested improvement**:
1. R&D reports must distinguish *measured* values (from direct observation) from *derived* values (computed from measurements). Label columns accordingly.
2. Any derived value that goes into a spec must include the derivation formula or a one-line verification command in the report. For RGB888→RGB565: `python3 -c "r,g,b=239,49,16; print(hex((r>>3<<11)|(g>>2<<5)|b>>3))"`. This makes the derivation auditable in 30 seconds.
3. The Architect adopting derived values into a design doc should run the verification before including the value. If no verification command is provided, flag the R&D report and request one before the spec is finalised.

Sister rule to LL-019 (mark provisional specs before R&D is complete) and LL-017 (a library that produces output is more dangerous than one that errors). Theme: **computed values can silently be wrong; always verify derivations independently.**

**Status**: adopted → BP-001 (2026-05-16)

---

### LL-021 — 2026-05-17 — Bake pipeline parameters lost on rebake (wave_atlas)

**Context**: `wave_atlas` rebaked today to fix a frozen-frames bug (30 identical lead-in frames in source video). A `--frame-start 30` flag was added to `bake_wave.py` and the atlas regenerated. Only `--dc-offset 3` was passed; `--boost 2.0 --spatial-smooth 3 --error-diffusion` were silently omitted. The regression was caught by the user ("did you undo the AE effects?") and corrected immediately, but a full reflash cycle was wasted.

**Observation**: The canonical bake invocation existed only in the `feat(wave): M-WAVE-ATLAS bake pipeline and host preview` commit message body. Nobody consults git log before running a tool. The tool's own `--help` lists flags but gives no indication which combination was used to produce the committed output.

**Root cause**: No machine-readable record of the exact bake invocation is committed alongside the generated artifacts. The artifact (`wave_atlas.c`) is reproducible in principle but the reproduction recipe lives only in narrative prose (commit message), which is not consulted at tool-invocation time.

**Suggested improvement**: For every bake tool that produces committed generated artifacts, commit a companion shell script or Makefile target (e.g. `tools/bake_wave.sh`) containing the exact invocation. The script is the canonical recipe; the commit message may reference it but is not the source of truth. When flags change, the script is updated in the same commit as the regenerated artifact.

**Status**: adopted → BP-002 (2026-05-17)

---

## Retrospective — 2026-05-22 — TASK-021/TASK-066/TASK-067 — tap-to-play queue-clear bug lifecycle

Triggering work: TASK-066 (fix `ACT_PLAY_URI` context_uri wire-up) + TASK-067 (T115/T116 DUT verification). The bug was first observed at TASK-021 close-out (2026-05-16) and re-surfaced by the user on 2026-05-22 (6 days later). Both the fix (5 lines in `spotifyTaskStorage.cpp`) and the DUT regression suite (T115 PASS, T116 PASS) landed on the same day.

### What went well

- **Fix was minimal and targeted.** The `s_lastTrackContextUri` infrastructure was already in place — the bug was a single missing wire in `ACT_PLAY_URI`. Once identified, the fix was 5 lines with no refactoring required.
- **Both symptoms resolved by one change.** Queue-cleared and 5-identical-rows were two manifestations of the same root cause; the single fix resolved both without hunting for a second bug.
- **T116 made fully self-contained.** Adding `_play_adhoc_uri()` to the harness meant T116 required no manual Spotify state setup — the test drives its own precondition via the host API. All future re-runs are automated.
- **Bug was well-documented at deferral time.** The TASK-021 notes and M-LIST-v3 design doc recorded the DUT observation, both symptoms, and both resolution options accurately. The diagnosis cost was low when the bug was revisited.

---

### LL-022 — 2026-05-22 — Known bug deferred as prose caveat without a blocking task

**Context**: TASK-021 (tap-to-play) was marked `done` on 2026-05-16 with a documented caveat: "`playAdvanced` replaces context; queue-aware skip deferred to M-LIST-v3." The fix required — wiring `s_lastTrackContextUri` into `ACT_PLAY_URI` — was already identified in the notes. No separate bug task was filed. M-LIST-v3 was marked "planned" with no scheduled start. The user re-reported the bug on 2026-05-22.

**Observation**: A known, identified, 5-line fix lived unresolved for 6 days because the deferral path ("M-LIST-v3, TASK-051a–f") was not backed by a concrete task with an owner and priority. The bug returned to the user rather than being resolved proactively.

**Root cause**: Closing a task as `done` with a known functional regression in the notes, deferred to a future milestone that has no scheduled work, effectively orphans the bug. There is no mechanism in the current process to surface deferred-bug notes as actionable items.

**Suggested improvement**: When a task is closed with a documented functional regression ("caveat"), a separate bug task must be filed at close time with status `planned` (not buried in the deferred milestone). The bug task should reference the parent task but stand alone in the tracker. Tasks with known un-fixed regressions should not be marked `done`; use `done-with-known-issue(TASK-NNN)` or equivalent, or hold `done` until the bug task is also closed.

**Status**: adopted → BP-003 (2026-05-22)

---

### LL-023 — 2026-05-22 — `injectTouch()` diverged from physical touch path — new actions not mirrored

**Context**: `injectTouch()` (`winampDisplay.h`) is the serial-debug touch injection path used by the VE harness. It was introduced in TASK-056d and mirrors the physical `checkForInput()` touch handler. When TASK-021 added the PLEDIT row-tap branch to `checkForInput()`, the same branch was not added to `injectTouch()`. As a result, any serial `tap X Y` command into the PLEDIT area silently fell through to DEADZONE and dispatched `ACT_FORCE_POLL` instead of `ACT_PLAY_URI`. T115's first run exposed this: `'hit': 'DEADZONE'` for coordinates that should have hit PLEDIT.

**Observation**: The physical touch path and `injectTouch()` are now structurally coupled — any new touch action added to one must be added to the other — but there is no enforcement or checklist for this. The divergence was invisible until a test was actually written and run.

**Root cause**: The `injectTouch()` pattern was introduced to mirror the physical path, but the mirroring requirement was never made explicit in code comments, docs, or a review checklist. New touch-path additions are made in `checkForInput()` without consulting `injectTouch()`.

**Suggested improvement**: Add a co-location comment in `winampDisplay.h` at the top of both `checkForInput()` and `injectTouch()` stating: *"These two methods must be kept in sync. Any new touch-action branch added to one must be mirrored in the other."* Additionally: add to the Developer pre-commit checklist (LL-010 / BP) the item: *"If touching the physical touch path: mirror the change in `injectTouch()`."*

**Status**: adopted → BP-004 (2026-05-22)

---

### LL-024 — 2026-05-22 — "VE: no test suite written" prose notes are not actionable without a task

**Context**: The `feature_inventory.yaml` entry for `playlist-001` carried `test_ids: []` and the note *"VE: no test suite written — action from 2026-05-15 audit."* No VE task was filed for TASK-021 at close-out time. The test gap persisted for 7 days. When T115/T116 were eventually written, the `injectTouch()` gap (LL-023) was also discovered — meaning the test infrastructure itself was defective during that window, so even if tests had been written earlier they could not have run correctly without the `injectTouch()` fix.

**Observation**: Audit findings that identify test gaps ("action from audit") recorded only in prose — in a feature YAML note, not as a VE task in `tasks.md` — have no owner, no deadline, and no mechanism to surface as work. They age silently.

**Root cause**: The team convention is to file tasks for implementation work but to record VE actions as prose annotations. VE actions are treated as lower-priority follow-ups rather than first-class tasks. The `test_ids: []` field visually signals a gap but does not create pressure to fill it.

**Suggested improvement**: Any `test_ids: []` entry in `feature_inventory.yaml` for an `implemented` feature must have a corresponding VE task in `tasks.md` with status at least `planned`. The feature should not reach `done` in the roadmap with `test_ids: []`. PM is responsible for filing the VE task at feature close. VE task must reference the feature ID so it is traceable.

**Status**: adopted → BP-005 (2026-05-22)

---

### LL-025 — 2026-05-23 — Two related gaps: single-state visual sign-off, and PM paraphrase vs. exact-quote for visual bugs

**Context**: TASK-051e (scrollbar thumb blit) was closed on a human eyeball at `scrollOffset = 0`. TASK-077 was filed the same day. The bug was actually an X-axis offset (`thumb_x = rightX + 1`, 4px too far left); the PM agent paraphrased "needs to move a bit to the right" as "Y position wrong" — an axis flip that caused the QM audit to verify the Y formula (correct) rather than immediately fixing the X offset (trivial).

**Observation A — single-state sign-off**: A visual check at one boundary state passes trivially for almost any formula. The actual defect (`+ 1` off in X) would not have been caught even with a correct Y-formula audit because they are orthogonal. The "thumb visible at correct position" sign-off at offset=0 is not a VE gate for any parameter-dependent renderer.

**Observation B — symptom transcription**: The PM agent paraphrased the user's spatial description ("needs to move a bit to the right") into a technical coordinate frame ("incorrect Y position"). Right/left → X axis; up/down → Y axis. The paraphrase introduced an axis error that misdirected the QM audit.

**Root cause A**: No explicit VE exit criterion in TASK-051e. T120 existed but was not linked as a gate. Closure accepted at the easiest single state.

**Root cause B**: PM filed the Symptom field from inference ("this seems like a position problem") rather than quoting the user verbatim. The verbatim quote would have immediately identified the axis.

**Suggested improvement A**: For any renderer whose output is a function of a runtime parameter, the VE gate must cover zero, max, and one intermediate value. Task notes must name the test ID explicitly. "Visually correct at rest" is not a regression guard.

**Suggested improvement B**: PM's Symptom field for visual/UI bugs must include the user's exact quoted wording alongside any technical translation. Quote first, interpret second. If the interpretation changes after clarification, update both fields.

**Status**: open

---

### LL-026 — 2026-05-23 — Reference image available, pixel positions still guessed; human forced to iterate

**Context**: `resource/winamp_reference_cropped.png` was provided at project start and used by R&D during TASK-075 (scroll arrows + thumb sprite identification). Despite this, the thumb's horizontal inset within the scrollbar track was implemented as `rightX + 1` with no derivation — a guess. The value was wrong. TASK-077 was filed (itself misfiled as a Y bug) and required 5+ flash-and-observe cycles with human pixel-level feedback to land on the correct value (`+4`). The reference image was available throughout and could have answered the question directly.

**Observation**: R&D measured *what* the thumb sprite was (BMP x=52, y=54, 9×17) but not *where* it should sit within the 19px scrollbar track on screen. The horizontal inset is visible in the reference image: the thumb occupies the inner portion of the track strip. A one-time measurement at TASK-075 or TASK-051e time would have produced the constant. Instead, the implementation shipped with a magic `+ 1` and the user paid for the error in session time.

**Root cause**: R&D task scope was "identify the sprite" (extract coordinates from BMP), not "specify all rendering parameters" (inset, centering, transparency handling). The gap between "sprite found" and "sprite correctly placed" was not identified as a work item. No one asked: "what is the correct X position relative to the track tile?"

**Suggested improvement**: For every sprite blit introduced by a TASK, the implementation spec must include ALL rendering parameters: X offset, Y offset, transparency key, and — for positioned elements — derivation from a reference image measurement. "Sprite found at BMP (x,y,w,h)" is not a complete spec. If a reference image exists, the spec writer must consult it. If a parameter is truly ambiguous, mark it `[VISUAL CALIBRATION NEEDED]` so it is not silently guessed.

**Structural fix (user direction)**: When a reference image is used as the basis for any rendered element, a paired VE/audit item is required to validate the rendered output against that image. "Reference image consumed → visual validation test" is a mandatory pair, not optional. The test does not need pixel-perfect automation; a manual overlay or side-by-side screenshot comparison is sufficient. Without this gate, an element can ship visually wrong and only human frustration eventually surfaces the error.

**User feedback (direct)**: *"I've had 4 agent sessions getting the slider sprite drawn. It's been an uphill battle. The reference image was given at the start. R&D examined it. And yet I still had to iterate a bunch more times, including using my human feedback on pixel differences — while you have all the resources to make the validation."*

**Status**: open

---

## Best-practice candidates (for human sign-off)

Per AGENTS.md, QM does not self-promote. Below are LL items that look durable enough to become best-practice rules:

- **LL-001** → "ESP32 TLS first-diagnostic = check the clock before anything else." Universally applicable on RTC-less boards.
- **LL-002** → "Credential leak = P0 incident, rotate before next task." Universal.
- **LL-003** → "Audit vendored library debug-log surface for secret output before first flash." Universal for any auth-handling library.
- **LL-005** → "Promote and populate `cross_feature_matrix.yaml` on the first cross-feature link, not the second." Process rule, applies to Developer.
- **LL-008** → "On Arduino-ESP32, do not share a single `WiFiClientSecure` across GET and non-GET requests." Library/integration rule, applies to Developer.
- **LL-009** → "Architecture decisions that depend on third-party API endpoints must verify endpoint access for the project's actual app, not just the documented API surface." Process rule, applies to Architect.
- **LL-010** → "Pre-commit checklist for cross-role hand-offs (Architect / VE / PM / inventory). Skips allowed but must be deliberate." Process rule, applies to Developer.
- **LL-011** → "Any new file under sketch/tools dirs gets a tasks.md entry, even if it doesn't advance a milestone." Process rule, applies to PM (and to Developer at commit time).
- **LL-012** → "Read the source for any sticky-state API named `lastError`, `lastResult`, `state`, etc. before building diagnostic chains on its return value." Library rule, applies to Developer.
- **LL-013** → "When a fix doesn't change a numeric error code, distinguish 'fix failed' from 'next bug in the chain shares the symptom'. Trace request bytes; cross-check spec." Process rule, applies to Developer + Architect.
- **LL-014** → "Network blame for a *consistent* failure mode requires a positive test (curl from host) or a mechanism consistent with other facts. Default-network-blame is banned." Process rule, applies to Developer.
- **LL-015** → "Optimistic-UI mutations must survive the same loop iteration. Audit the downstream code path before shipping; defer force-actions or guard optimistic state explicitly." Architecture rule, applies to Developer.
- **LL-016** → "Look at the asset before changing code; ask which layer (atlas / data-mapping / on-screen position) when 'swap' is ambiguous." Process rule, applies to Developer.
- **LL-017** → "A library that produces output is more dangerous than one that errors. For data-pipeline libraries on the file classes we actually depend on, validate output against a second independent decoder; don't trust no-exception as success." Process rule, applies to Developer + Architect.
- **LL-018** → "Treat the OpenAPI spec as an over-approximation, not a contract. Any lib-filter patch that depends on a documented field must include a wire-capture proof that the field is actually returned by the specific endpoint being patched." Process rule, applies to Developer + Architect. Two concrete instances (LL-013 was the first). Strongest promotion case in the candidate set.
- **LL-019** → "Implementation specs that depend on pixel-accurate asset measurements must be marked `[PROVISIONAL — awaiting R&D]` and blocked from implementation until R&D validates the numbers. First-principles estimates produce high error rates on pixel-level behaviour." Process rule, applies to Developer (implementation gate) and Architect (provisional tagging). First instance on this project; preventive catch.
- **LL-020** → "R&D reports must distinguish measured values from derived/computed values. Any derived value entering a spec must include its derivation formula or a one-line verification command. Architect verifies before adopting." Process rule, applies to R&D Engineer (labelling + formula) and Architect (verification gate). Concrete incident: 16/16 RGB565 values wrong in M-VIS spec; 30-second Python check would have caught it.
- **LL-021** → "Bake pipeline parameters must be recorded in a committed, executable form (shell script or Makefile target), not only in a commit message. Commit messages are not consulted before re-running tools." Process rule, applies to Developer + R&D Engineer. Concrete incident: wave_atlas rebaked with only `--dc-offset 3`; `--boost 2.0 --spatial-smooth 3 --error-diffusion` lost because the canonical invocation only existed in the git commit body. → **BP-002**
- **LL-022** → adopted → **BP-003** (2026-05-22)
- **LL-023** → adopted → **BP-004** (2026-05-22)
- **LL-024** → adopted → **BP-005** (2026-05-22)
- **LL-025** → "Visual sign-off for range-dependent renderers must cover zero, max, and one intermediate value. 'Correct at rest' is not a VE gate." Strong promotion case: same failure mode as LL-024 (test gap at closure) but from the opposite direction — test existed, exit criterion link was missing.
- **LL-027** → "Write `.gitignore` before first `git add` on any new build-tool project directory. For PlatformIO: `.pio/` excluded by default. Build outputs are predictable; exclude them proactively." Process rule, applies to Developer.
- **LL-028** → "Spec steps that name a specific file for a code change must either be verified against the actual codebase or marked `[FILE TBD — confirm at implementation]`. Plausible-but-unverified file paths in specs are silent latent risks for agent hand-offs." Process rule, applies to Architect + PM (spec writers).
- **LL-048** → "Host test constants and comments for firmware JSON doc sizes are interface contracts — update them in the same commit as the firmware change. A firmware parse-strategy change that does not update the host test is an incomplete migration." Process rule, applies to Developer (update test constants at firmware change time) and VE (flag any test constant whose comment references a non-existent `DynamicJsonDocument` or `StaticJsonDocument` allocation). Concrete incident: LL-040 resolution said quote path used `DynamicJsonDocument(8192)` with no filter; quote path acquired a filter the next day; test was not updated. BP candidate — bring to human.
- **LL-049** → "ArduinoJson filtered parses have two separately-sized documents: the filter doc and the data doc. Both must be sized deliberately and documented. The host test's budget check only validates the data doc; filter doc truncation is a separate failure mode invisible to the test. Extend BP-015 to require: compute minimum filter doc capacity from path depth × leaf count; record it as a comment alongside every `StaticJsonDocument<N> filter` declaration." Process rule, applies to Developer (sizing + documentation at introduction) and VE (extend host-test scope). Concrete incident: `StaticJsonDocument<64>` for a 5-level/2-leaf filter tree silently dropped both fields; DUT returned zeros. Host test passed. No gate existed between 64B declaration and DUT observation.
- **LL-026** → "Reference image used → paired visual validation item required. Any element rendered from a reference image must have a VE/audit item that validates the rendered output against that image. No reference image consumed without a closing verification step." Strong promotion case: directly addresses a recurring human frustration; cost of the check is low (side-by-side screenshot); cost of skipping is 4+ wasted sessions. Applies to Developer (spec completeness) + VE (validation item creation).
- **LL-029** → "Structural refactors must include a grep-for-old-paths step on moved files, plus a tool-script smoke-test gate (e.g. `python3 -c 'import coords'`) before close. A file move that does not update internal path strings is an incomplete migration. BP candidate — applicable to any project with host-side Python/shell tooling."
- **LL-071** → adopted → **BP-031** (2026-06-14)
- **LL-072** → adopted → **BP-032** (2026-06-14)
- **LL-073** → adopted → **BP-033** (2026-06-14)
- **LL-032** → adopted → **BP-010** (2026-05-25)
- **LL-033** → adopted → **BP-011** (2026-05-25)
- **LL-034** → adopted → **BP-012** (2026-05-25)

---

### LL-027 — 2026-05-24 — `.gitignore` must exist before first `git add` on a new directory

**Context**: M-RESTRUCTURE TASK-083 created `app/` as a new PlatformIO project directory. `git add app/` was run before `app/.gitignore` was written. PlatformIO's `.pio/libdeps/` contains git repos (Seeed_Arduino_NFC), which git staged as embedded repositories with a warning.

**Observation**: The embedded git repos were caught before commit and removed with `git rm --cached`. Recovery required manual intervention. The `.gitignore` was then written and the directory re-staged correctly. Had the commit landed with `.pio/` included, reverting would have required `git rm -r --cached app/.pio/` and a corrective commit.

**Root cause**: The `.gitignore` was created reactively (after seeing the staging warning) rather than proactively (before `git add`). For any directory that runs a build tool, the build tool's output directories are predictable in advance.

**Suggested improvement**: When creating a new build-tool project directory, write `.gitignore` as part of the skeleton step — before any `git add`. For PlatformIO: `.pio/` is always excluded. For any tool that fetches or generates files, audit what it produces and exclude it. Rule: `.gitignore` before `git add`, not after.

**Status**: open

---

### LL-028 — 2026-05-24 — Implementation specs that name a specific file must be verified against actual code structure

**Context**: TASK-083 step 5 stated "one-line canvas rect change in `app/src/main.cpp` shell: `originX` 22 → 0." The actual location of the `originX` assignment is `app/src/winamp/winampDisplay.h:49` (`displaySetup()`), not `main.cpp`. The spec was written before the file structure existed — a reasonable planning shortcut — but the named file was wrong.

**Observation**: No rework resulted (grep immediately found the correct location), but a spec naming the wrong file is a latent risk for agent hand-offs where the receiving agent may not re-verify the file attribution and may either fail to find the symbol or make a change in the wrong place.

**Root cause**: The spec was authored at planning time without being able to verify against the actual implementation. The guess (`main.cpp`, which is the shell entry point) was plausible but wrong.

**Suggested improvement**: If a spec step names a specific file for a change, it must either (a) be verified against the actual codebase before the task is assigned, or (b) be marked `[FILE TBD — confirm at implementation]` so the implementer knows to locate it rather than trust the attribution. Plausible-but-unverified file paths in specs are silent landmines.

**Status**: open

---

### LL-029 — 2026-05-24 — Structural refactors must include a tool-script path audit as a mandatory gate

**Context**: M-RESTRUCTURE (TASK-083) moved the project's tool scripts and generated artifacts from `Spotify-Diy-Thing/tools/` and `Spotify-Diy-Thing/SpotifyDiyThing/gen/` to `app/tools/` and `app/gen/`. The migration was mechanically correct for source files and the build system. However, the tool scripts themselves contain hardcoded path strings referencing their *own* outputs and sibling inputs. These strings were not updated.

Discovered 2026-05-24 during a T102 re-run: the test harness imports `coords.py`, which — at the time — had a stale `pathlib.Path` pointing to `../SpotifyDiyThing/gen/skin_layout.h` (line 9) instead of `../gen/skin_layout.h`. The import crashed immediately, blocking T102.

Further investigation found six additional functional (runtime-breaking) stale paths across four scripts:
- `app/tools/preview_vis.py:65` — `pathlib.Path(__file__).parent / "../SpotifyDiyThing/gen/skin_layout.h"`
- `app/tools/bake_wave.sh:19` — `-o "$SCRIPT_DIR/../SpotifyDiyThing/gen"`
- `app/tools/preview_vis.py:340` — argparse `default="SpotifyDiyThing/gen/skin_preview_animated.gif"`
- `app/tools/preview_wave.py:128-129` — argparse `default` and `help` referencing `SpotifyDiyThing/gen/skin_preview_wave.gif`
- `app/tools/bake_skin.py:773` — `parse_shell_layout(path="SpotifyDiyThing/gen/shell_layout.h")` default arg

Plus docstring/help text staleness in `bake_skin.py:8-9`, `bake_vis.py:7-8`, `bake_wave.py:6-7`, `preview_vis.py:20-22,26-27,32,37-38`.

Note: `coords.py` itself had already been fixed (line 9 now reads `"../gen/skin_layout.h"`) before this retrospective was written, likely as part of TASK-083 step 2. The other files were not fixed in the same pass.

**Observation**: The TASK-083 restructure checklist (step 2) explicitly listed updating `CLAUDE.md` path references but did not include a step to audit and update path strings *inside* the tool scripts being moved. The tool scripts were treated as opaque files to be relocated, not as code containing embedded path assumptions that become wrong when the file's working-context changes.

The `check_build.sh` gate (BP-008) caught compile errors but has no visibility into Python or shell script path correctness. No tool-script smoke test exists that would catch a broken import at restructure time. The first consumer (T102) surfaced the breakage.

**Root cause**: The TASK-083 restructure scope definition treated "move files" as sufficient. Path strings inside scripts are a form of structural coupling between a script and its directory context — equivalent to a `#include` path in C. A file move that does not update internal path strings is an incomplete migration. The checklist had no explicit "grep moved scripts for old path strings" step.

**Suggested improvement**:
1. Any task that moves a file or directory must include an explicit sub-step: grep the moved files for hardcoded path strings referencing the old location. The grep can be one command: `grep -rn "OldPath" movedDir/`.
2. For PlatformIO / tool-script projects, the restructure checklist should include: "run each tool script with `--help` or a dry-run invocation from its new location and confirm no `FileNotFoundError` on import."
3. Path strings in tool scripts should be derived from `pathlib.Path(__file__).parent` (relative to the script file), not from the caller's working directory. A script that uses `"SpotifyDiyThing/gen/..."` as a literal string instead of `Path(__file__).parent / "../gen/..."` is fragile to any invocation from a non-standard cwd.
4. The restructure gate (`check_build.sh`) should be complemented by a `tools/smoke_test.sh` that imports each Python module (e.g. `python3 -c "import coords"`) and runs each shell script with `--help` or `--dry-run`. Absence of this gate is what allowed the stale paths to survive TASK-083.

**Status**: open — six functional stale paths remain unresolved in `app/tools/`. A fix task should be filed (see recommendations in this retrospective).

---

### LL-030 — 2026-05-24 — "Build passes" and "DUT verified" are not the same done criterion

**Context**: TASK-087 was closed with status `done (2026-05-24 — check_build.sh 3/3 pass; DUT flash + smoke test pending)`. The same pattern appeared in TASK-042 and TASK-009: the parenthetical "(DUT ... pending)" is treated as a note rather than a blocking exit criterion. Same pattern: task is marked done when the build is clean, DUT verification left as follow-up.

**Observation**: The "DUT smoke test pending" parenthetical is structurally a known gap dressed as a footnote. Any subsequent reader of the task list sees `done` and moves on. When VE or PM picks up the task later, the pending DUT item is invisible in the status. TASK-087's BUG-1 defect was also missed because the DUT run that would have surfaced it (Clock canvas touch enqueuing Spotify actions) hadn't happened yet.

**Root cause**: The project has no `pending-dut` intermediate status and no enforcement that VE sign-off is required before `done` when a task's own notes include a DUT gate. The build gate (`check_build.sh`) is a hard automated gate; DUT verification is informal. The distinction allows "done" to mean different things in different tasks.

**Suggested improvement**:
1. Add `pending-dut` as a recognised task status between `in-progress` and `done`. A task with a DUT exit criterion goes to `pending-dut` after `check_build.sh` passes; VE updates it to `done` after the DUT run.
2. Any task that lists a "DUT smoke test" in its notes must have that smoke test in its exit criterion, not as a parenthetical.
3. PM should reject `done` status on any task whose notes contain "DUT ... pending" without a VE sign-off comment.

**Status**: open — pattern not yet addressed in process docs. Promote to BP if human approves.

---

### LL-031 — 2026-05-24 — Tests must be updated when a feature adds new hit-zones

**Context**: T088 (DEADZONE positive cases) was written before the taskbar strip existed. When TASK-087 added the 45px taskbar at x≥275, three of T088's test coordinates — corner-TR (319,0), corner-BR (319,239), and 1px-right-chrome (276,58) — moved from genuine dead zones into valid taskbar slots. T088 continued to expect `hit=DEADZONE` for these coords. When run against the new firmware, T088's TASKBAR hits triggered `switchApp()`, contaminating `currentAppId` for T134–T140 (cascade: 5 tests failed, 2 of which were spurious cascades from the corrupted state).

**Observation**: The failure chain — T088 poisons app state → T134–T140 fail with `hit=CLOCK` — was not obviously connected to the new feature. The root cause (stale T088 coordinates now in the taskbar strip) required inspection of the test's coordinate values against the new layout constants. The contamination was silent: T088 itself would have passed its own assertions if we'd only updated the expected values, but the side effect (switchApp) persisted into subsequent tests.

**Root cause**: No checklist item requires updating existing tests when a new feature adds or changes hit-zones. The implicit assumption is that new features add new tests; existing tests are assumed stable. This fails when a new feature claims screen area that existing tests probe as dead zone.

**Suggested improvement**:
1. Any task that adds, moves, or resizes a hit-zone must include a sub-step: "grep `run_serialdbg_tests.py` for coordinates that fall inside the new zone's bounds and update or retire those cases."
2. `T088` specifically should be treated as a live inventory of dead zones, not a static set of coordinates. When a new hit-zone is added to the firmware, T088's coordinate list must be audited and the dead-zone coords that are now inside the new zone must be removed or reclassified.
3. The fix pattern is `_restore_spotify()` (or analogous state-restore helpers) as teardown in any test that may switch the active app as a side effect. Tests that exercise taskbar coords should always restore state before returning.

**Status**: open — sub-step not yet added to task template. Promote to BP if human approves.

---

## Retrospective — 2026-05-25 — TASK-090 — App Interface ABC + AppShell refactor

Triggering work: TASK-090 complete — App ABC (`init/resume/suspend/tick/handleInput`), SpotifyApp + ClockApp classes, `appHandleInput()` gesture loop, B1–B4 fixed structurally, T_BI_01–T_BI_04 VE tests implemented and passing. Production build flashed. Three agent sessions (090a–090g, handoff, 090h VE close).

### What went well (no LL needed, recorded for balance)

- **B1–B4 fixed structurally.** All four TASK-087 post-mortem bugs were consequences of a missing `App` lifecycle interface. The Architect correctly diagnosed this and designed the App ABC to make the bugs impossible rather than patching each symptom. No new bugs introduced; confirmed by the full DUT regression suite.
- **Design doc had executable test sequences.** `app-interface.md §Verification impact` named specific `dbgGet` keys, exact serial commands, and observable assertions for T_BI_01–T_BI_04. VE implemented all four tests directly from the spec without clarification. Correct order: Architect names the observable, VE implements it.
- **Handoff note was precise and actionable.** The `pm(TASK-090): handoff note` commit had a numbered TODO block with exact shell commands. The 090h session executed the full sequence without re-reading conversation history.
- **check_build.sh 3/3 on a 618-line winampDisplay.h refactor.** The build gate caught nothing new — the refactor was structurally clean before hitting the DUT.

---

### LL-032 — 2026-05-25 — VE-written tests must be entered in test_plan.md in the same session

**Context**: TASK-090h: VE implemented T_BI_01–T_BI_04 in `run_serialdbg_tests.py`. All four pass on DUT. `test_plan.md` was not updated; no T_BI entries exist there. Additionally, `app-interface-001` was not registered in `feature_inventory.yaml` despite being the named feature for TASK-090.

**Observation**: The passing test functions exist in the harness. But from an audit perspective, `test_plan.md` is the canonical test registry and `feature_inventory.yaml` is the canonical feature registry. Both are missing entries. A future QM audit will find `app-interface-001` absent from the inventory and T_BI tests with no plan entries, breaking traceability from test to feature.

This is the reverse of LL-024 (VE actions not filed as tasks): here the tests *were* written, but not registered in the canonical artifacts.

**Root cause**: VE task scope was treated as "write the Python functions and confirm they pass." Updating `test_plan.md` and `feature_inventory.yaml` are follow-on steps that belong to the same session but are easy to drop when the DUT is the target and docs feel like overhead.

**Suggested improvement**: A VE task is not complete until:
1. Test functions written and passing.
2. Entries added to `test_plan.md` (feature ID, objective, steps, status per test ID).
3. `test_ids` list in `feature_inventory.yaml` populated for the covered feature.

This extends BP-005: the VE task itself is not `done` until the `test_ids` list is populated. VE owns both the harness code and the inventory/plan updates in the same session.

**Status**: adopted → BP-010 (2026-05-25)

---

### LL-033 — 2026-05-25 — Handoff notes with numbered TODO blocks are reliable inter-session mechanisms

**Context**: TASK-090 spanned three sessions. The 090a–090g session ended with a port disconnect mid-run; T148 status was UNKNOWN. The PM agent wrote a dedicated commit (`pm(TASK-090): handoff note`) containing: current regression status with raw counts and interpretation, a numbered NEXT AGENT TODO block with exact shell commands and expected outcomes, and what hadn't been done and why.

**Observation**: The 090h session executed from the handoff without reading conversation history. All four handoff steps completed in order without ambiguity. The port disconnect was characterised precisely ("T148 was the only failure, now fixed — port disconnected mid-run") which let the next agent interpret the 26/27 count correctly rather than treating it as a regression.

**Root cause**: N/A — positive pattern. Recorded because the format is not documented and should be replicable.

**Suggested improvement**: When a DUT session ends with unfinished verification (port disconnect, hardware issue, test not yet written), write a PM handoff commit before closing:
- Status per numbered sub-task.
- Current regression count with interpretation (which test failed and why, if known).
- NEXT AGENT TODO block: numbered, exact shell commands, expected output.
- Any context the receiving agent needs to interpret partial results.

Format: `pm(TASK-NNN): handoff note — [one-line status]`. Separate commit from the implementation commit.

**Status**: adopted → BP-011 (2026-05-25)

---

### LL-034 — 2026-05-25 — Pre-existing intermittent failures dilute regression signal in the test suite

**Context**: The regression suite has four known intermittent failures: T084, T087, T091, T092 (reconnect race, TLS reset log-line timing). On each full run 1–2 fire. The headline count varies across runs: 26/27, 27/27, 30/31, 29/31.

When T148 was fixed by TASK-090, the first clean run still showed 26/27 — T087 had fired. A reader could not tell from the count whether a new regression was present or a known flake had fired. The agent had to cross-reference which test failed to confirm T148 was actually fixed.

**Observation**: Four intermittent tests in a 31-test suite means P(all-green) ≈ 66% even with zero new regressions. "Not all green" is the expected baseline, not a signal. The suite has lost its ability to say "something new broke."

**Root cause**: No mechanism to distinguish "known intermittent, tolerated" from "new failure, investigate." Every failure looks identical in the results table.

**Suggested improvement**:
1. Tag known-intermittent tests in `run_serialdbg_tests.py` with a comment block: `# KNOWN INTERMITTENT: <reason> <date first observed>`.
2. Optionally add a `[FLAKE]` result category (separate from PASS/FAIL/SKIP) when a known-intermittent test fails. Summary shows "30 passed, 0 failed, 1 flaked" — unambiguous signal.
3. For T084/T091/T092 (reconnect timing): consider `--retry 2` logic for this class so a single timing miss doesn't count as a failure.

Flag to PM to track this as a sub-task under tooling-001 or a standalone task.

**Status**: adopted → BP-012 (2026-05-25)

---

### LL-035 — 2026-05-25 — TFT shared hardware state leaks between apps in multi-app shell

**Context**: M-MULTIAPP step 2 (TASK-087/TASK-090) introduced `ClockApp` alongside `WinampDisplay`, both drawing to a single `TFT_eSPI` singleton. `TFT_eSPI` maintains ~6 process-global state fields: `textdatum`, `textfont`, `textsize`, `textcolor`, `swapBytes`, `cursor_x/y`. ADR-026 defined layering rules (no `appShell.h` in `WinampDisplay`, taskbar hit-testing in shell only) but said nothing about TFT hardware state.

**Observation**: After a Clock→Spotify app switch, PLEDIT playlist rows rendered 2–3 characters off the left edge of the content area and ~2 px above the expected baseline. Bug was triggered by a user-reported visual regression; root-caused by code audit. `ClockApp::drawTime()` and `drawDate()` called `tft.setTextDatum(MC_DATUM)` and returned without resetting to `TL_DATUM`. `drawPlaylist()` called `tft.drawString()` with `MC_DATUM` still active, shifting every row's text left by `textWidth/2`.

**Root cause**: ADR-026 addressed *structural* isolation (dependency direction, hit-testing ownership) but left TFT hardware state as an implicit shared resource with no ownership contract. No convention existed: neither "producer resets after use" nor "consumer asserts at entry."

**Suggested improvement**:
1. **Producer rule**: any function that calls `tft.set*(non-default)` must reset that field to its default before returning. Concrete default: `textdatum` → `TL_DATUM`, `swapBytes` saved/restored (screenLog.h already does this correctly).
2. **Consumer rule**: any rendering function that cares about a specific TFT state field must assert that state at function entry — don't inherit. Both rules together give defense-in-depth; producer-only is insufficient because callers can forget; consumer-only is correct but relies on every new function knowing the contract.
3. Capture this as a binding architectural invariant (ADR-027) so new app authors have a named rule to follow.
4. Code-review checklist item: any `tft.set*()` call that sets a non-default value must have a matching reset in the same scope.

**Status**: open

---

## Retrospective — 2026-05-25 — M-MULTIAPP complete: Matrix, Life, Weather, Crypto apps

Triggering work: TASK-093 (MatrixApp), TASK-094 (LifeApp), TASK-095 (WeatherApp + CryptoApp + dataTask + ADR-029), TASK-096 (canvas full-height fix). All 6 `g_apps[]` slots now filled and DUT-verified.

### What went well (no LL needed, recorded for balance)

- **App ABC paid off immediately.** MatrixApp, LifeApp, WeatherApp, CryptoApp each landed as a clean subclass with no structural friction. TASK-090's design investment was justified by four successive apps that needed no shell rework.
- **`dataTask` pattern required no new architecture.** Mirroring `spotifyTask`'s queue + spinlock pattern let Weather + Crypto HTTP work land without a blocking design review. One pattern, two consumers, no surprises.
- **ADR-029 TLS root CA strategy written upfront.** ISRG Root X1 + GTS Root R4 PEMs were hardcoded before implementation started. No TLS debugging during app work — the ca-cert lesson (LL-001) was applied preventively.
- **Canvas bug caught and fixed same session.** TASK-096 top-half-black regression was identified by user visual inspection and fixed same commit cycle. No deferred regression.
- **Prior audit actions largely resolved.** `app-interface-001` registered in feature_inventory.yaml; T_BI_01–T_BI_04 added to test_plan.md; TASK-091 tagged known-intermittent tests (BP-012). All three RED findings from the TASK-090 audit were closed.

---

### LL-036 — 2026-05-25 — Feature inventory registration recurred as a miss for all 4 new app classes

**Context**: TASK-093/094/095 implemented MatrixApp, LifeApp, WeatherApp, CryptoApp. None of the four features (`matrix-001`, `gol-001`, `weather-001`, `crypto-001`) were registered in `feature_inventory.yaml`. This is a direct recurrence of LL-032 (app-interface-001 missing from inventory, TASK-090) which was adopted as BP-010 in the same session.

**Observation**: BP-010 covers the VE side ("VE task not done until test_ids populated"), but there is no corresponding enforceable rule on the Developer side for the feature entry itself. BP-010 assumes the entry exists; it does not require the Developer to create it. The gap was invisible until this audit — tasks.md entries exist, code is in tree, DUT-verified, but from an audit perspective all four features are unregistered.

**Root cause**: BP-010 was adopted to close the loop after feature implementation; the open loop is that implementation can be completed and committed without a feature_inventory.yaml entry ever being written. The Developer checklist (LL-010) lists inventory update as item (c), but that checklist has no enforcement mechanism.

**Suggested improvement**: Developer's `done` criterion for any task tagged `feature: <id> (new)` must include a `feature_inventory.yaml` entry with `status: implemented`, `git_ref`, `files`, and at minimum `test_ids: []`. This is not optional housekeeping — it is the registration act that makes the feature exist to PM, VE, and QM. A task that ships code without this entry is `in_progress`, not `done`.

**Status**: open — promotion candidate alongside LL-032/BP-010. Together they close both ends: Developer registers at implementation (this LL), VE populates test_ids at test-time (BP-010).

---

### LL-037 — 2026-05-25 — Canvas sub-region inherited from prior design era and not updated when app became standalone

**Context**: WeatherApp and CryptoApp were initially implemented (TASK-095) rendering into `y:116..239` — the bottom half of the 275×240 app canvas. This sub-region originated in an earlier design where these apps were conceived as sharing the canvas with Winamp chrome above. Under the App ABC (TASK-090), each app owns the full 275×240 canvas exclusively. The sub-region constraint was not removed from the implementation when the design shifted. TASK-096 was filed and fixed the same session; the user observed the top half black on DUT.

**Observation**: The implementation was correct relative to an older design assumption that was never explicitly invalidated. Nothing in the task spec or code review surfaced the stale constraint. The bug was only visible on DUT with the screen active.

**Root cause**: Design constraints written for one architecture epoch (shared canvas) survived into a new epoch (standalone apps) because there was no gate asking: "given this app now owns the full canvas, is its coordinate origin still appropriate?" The canvas bounds are a precondition that changed when the App ABC landed, but the implementation was written without re-checking that precondition.

**Suggested improvement**: When an app class moves from a "shared display" context to a "standalone full-canvas" context, the implementation spec must explicitly state the expected canvas dimensions (`x: 0..274, y: 0..239`) as a precondition, not an assumption. VE exit criteria for any new App subclass must include: "app fills the full 275×240 app canvas; no unexplained blank regions at any edge." A `fillRect(0,0,275,240,color)` in `init()`/`resume()` is a useful smoke test of the full extent.

Sister rule to LL-025 (visual sign-off must cover the full range, not a single state). Here the "range" is the spatial extent of the canvas; "correct at the bottom half" is not a full-canvas sign-off.

**Status**: open — promotion candidate.

---

## Retrospective — 2026-05-25 — PLEDIT empty rows (getQueue malloc regression)

Triggering work: user bug report — PLEDIT shows chrome but no track rows during active playback. Root-caused to `malloc(65536)` silently failing on fragmented heap; `onQueue` never called; snapshot stays at `count=0`. Fixed by replacing the bodyBuf approach with a streaming `BlockingChunkedStream` that reads directly from the TLS socket. Two lessons extracted.

### What went well

- **Log-driven diagnosis.** `LOG_D("spotify.queue", "status=200 elapsed=490ms")` without a following `snapshot updated` line uniquely identified the silent return path — no SERIAL_DEBUG build needed.
- **Root cause found before fixing.** Full analysis of three plausible hypotheses (malloc failure, JSON parse error, `onQueue` not called) narrowed to one before any code was changed.

---

### LL-038 — 2026-05-25 — Large heap malloc on ESP32 fails silently when the heap is fragmented

**Context**: `getQueue()` in `SpotifyArduino.cpp` allocated a 65 536-byte `bodyBuf` to accumulate the raw Spotify queue response before passing it to `deserializeJson`. The allocation was introduced by the TASK-065 dechunker fix (2026-05-20) and passed T114 at the time. After M-MULTIAPP added five new App subclasses plus `dataTask` (TASK-087–095), heap fragmentation increased enough that `malloc(65536)` started returning `NULL`. The failure path (`!bodyBuf`) returned `statusCode` (200) immediately, calling neither `onQueue` nor any error log — PLEDIT showed 0 rows every keepalive cycle.

**Observation**: `malloc` returning `NULL` is a contract violation that the caller must handle explicitly. The code did handle it, but silently: it closed the connection and returned the HTTP status code unchanged. From the outside, the call looked successful (status=200, elapsed=490ms). Without a `LOG_W` or `LOG_E` on the failure path, the symptom was indistinguishable from "parse succeeded but Spotify returned 0 tracks."

**Root cause**: Two compounding factors: (1) the fix chose a large heap buffer when a streaming parse would have required only ~10 KB (the filtered doc); (2) the silent failure path made the condition unobservable without source-level knowledge of the code. Neither was caught because T114 passed on less-fragmented firmware — the test verified correct behaviour, but not behaviour under resource pressure.

**Suggested improvement**:
- On ESP32, treat any `malloc` of ≥ 16 KB as a risk point. Prefer streaming/incremental approaches that allocate only the output (filtered result), not the full raw input. `deserializeJson(doc, stream, Filter)` costs ~10 KB vs 65 KB + 10 KB.
- Any `malloc` failure path that returns silently must emit at least a `LOG_W` with `heap_caps_get_largest_free_block(MALLOC_CAP_DEFAULT)`, so failures are observable in production logs without a debug build.
- When a fix introduces a heap allocation to solve a correctness bug, file a follow-up note asking: "does this allocation still fit after the next feature wave?" The answer may change as subsystems grow.

**Status**: open — promotion candidate.

### LL-039 — 2026-05-25 — T114 not re-run after M-MULTIAPP; resource-sensitive tests need a re-run trigger

**Context**: T114 was written for TASK-065 and asserts `getQueue() count >= 1` after one keepalive cycle. It passed on 2026-05-21 against firmware `ab3864e`. M-MULTIAPP (TASK-087–095) added five App subclasses and `dataTask`, increasing heap fragmentation. The TASK-065 dechunker fix started failing under the new firmware, producing the same symptom T114 was designed to catch. T114 was never re-run against the multiapp build; the regression was only discovered via a user bug report.

**Observation**: T114 would have caught the regression immediately — its assertion (`count >= 1`) fails when `onQueue` is not called. The test was correct; it was not triggered. No regression schedule existed for "re-run these tests when heap usage or subsystem count increases."

**Root cause**: T114's precondition names a specific firmware commit (`≥ ab3864e`), not a firmware *capability* class. When new subsystems landed, no mechanism asked: "which existing tests are sensitive to system-resource changes and should be re-verified?" The gap is scheduling, not test design.

**Suggested improvement**:
- Tests that exercise resource-constrained paths (heap allocation, stack depth, timing jitter) should be annotated `[RESOURCE-SENSITIVE]` analogously to `[FLAKE]`. A new milestone or significant feature addition (any new FreeRTOS task, large static allocation, or app subclass) should trigger a re-run of all `[RESOURCE-SENSITIVE]` tests as part of the merge checklist.
- T114 specifically: update its precondition from a commit hash to a firmware capability description, and add it to the resource-sensitive re-run list for any future App or task addition.

**Status**: open — promotion candidate. Closely related to LL-034 (VE test gap on App ABC) — the pattern of "test written, not re-run after subsequent changes" is recurring.

---

## Retrospective — 2026-05-29 — StockApp -99 NET ERR: host API test and VE stress test both failed to surface root cause

Triggering incident: user observed "NET ERR -99" on screen while manually cycling range tabs in StockApp chart view. Two existing tools were expected to catch this class of issue and did not. Three lessons extracted.

### What went wrong

- **`test_yahoo_finance_api.py` checked the wrong budget** — used `CHART_BUDGET_B = 8192` for chart fetches, but the firmware uses `DynamicJsonDocument(16384)`. A payload that the test passed could still fail in firmware.
- **The budget model was wrong even if the constant were correct** — the test compares raw HTTP payload bytes against the `DynamicJsonDocument` capacity. ArduinoJson's capacity must accommodate the parsed tree, not just the raw JSON. `http.getString()` also allocates a separate heap `String` before parsing. Neither of these was modelled.
- **T186 stress test took three iterations to work**, and still didn't trigger the failure — queue depth=4 silently drops most taps; "32 taps fired" produced only 4 actual fetches, all D1/D5. Mo1 and Ytd were never exercised under pressure.

---

### LL-040 — 2026-05-29 — Host API test used wrong budget constant and wrong capacity model

**Context**: `test_yahoo_finance_api.py` T_SF_06 checks that chart payloads fit the "DUT budget" of 8192 bytes. The firmware's `fetchStockChart()` uses `DynamicJsonDocument(16384)` — 2× the constant in the test. Additionally, the test measures raw HTTP response bytes, not the ArduinoJson capacity requirement (which is larger than raw JSON due to the parsed-tree representation) nor the peak heap pressure (which includes the `http.getString()` String allocation stacked on top of the document).

**Observation**: The test passed for all ranges including Ytd, giving false confidence. On DUT, the same request may fail because the heap can't satisfy both the `String` and the `DynamicJsonDocument` allocation concurrently, or because ArduinoJson runs out of capacity parsing a complex document.

**Root cause**: The budget constant was written during an earlier design pass and not updated when the firmware was changed to use 16384. The conceptual model ("does the payload fit?") is correct but the operationalisation is wrong — payload bytes ≠ ArduinoJson capacity ≠ peak heap pressure.

**Suggested improvement**:
- `CHART_BUDGET_B` in the test must match `DynamicJsonDocument(N)` in firmware exactly. Owner: Developer updates the constant whenever the firmware doc size changes; host test must cross-reference the firmware value (comment citing the source line).
- The payload size check should apply a safety factor (≥ 1.5×) to approximate ArduinoJson tree overhead. A comment should explain why.
- Eliminate the intermediate `String` in firmware: replace `deserializeJson(doc, http.getString())` with `deserializeJson(doc, http.getStream())`. This removes the double-allocation (no `String` heap cost) and makes the host budget check more accurate.

**Resolution (2026-05-30)**: The ADR-034 `getStream()` fix (already landed) plus a JSON filter (`StaticJsonDocument<128>` filter + `StaticJsonDocument<2048>` doc) made raw payload bytes entirely irrelevant for chart fetches — only the non-null `close[]` point count matters. `CHART_BUDGET_B=16384` removed; replaced with `CHART_MAX_POINTS=110` mirroring `chartPoints[110]` in `StockAppState` and the `if (r.len >= 110) break` cap in firmware. T_SF_06 now counts non-null `close[]` entries and asserts `<= 110`. `QUOTE_BUDGET_B=8192` retained — quote fetch had no filter at this point, so raw bytes vs `DynamicJsonDocument(8192)` was correct at time of writing. Committed `50ce839`.

**⚠ Resolution note stale as of 2026-05-31** (commits 08f8d22, c745b2f): `fetchStockQuote` was reworked to use `StaticJsonDocument<128> filter + StaticJsonDocument<256> doc` with streaming. The quote fetch now has a filter; `DynamicJsonDocument(8192)` no longer exists in the path. `QUOTE_BUDGET_B=8192` in the host test is now an incorrect proxy — it describes a non-existent allocation. See LL-048 for the coverage gap this created and LL-049 for the related filter-doc sizing gap.

**Status**: adopted → BP-015 (2026-05-30).

---

### LL-041 — 2026-05-29 — ESP32 stress test assumed "taps fired = fetches executed"; queue depth not accounted for

**Context**: T186 fires 32 taps (8 rounds × 4 tabs) to stress-test rapid range switching. The dataTask queue depth is 4. After the first 4 enqueues, all subsequent taps are silently dropped (`LOG_W "queue full — dropped"`). The 30s drain window captured only 4 chart fetches — all D1 or D5. Mo1 and Ytd (the ranges most likely to exhaust heap) were never executed.

**Observation**: The test reported PASS because `fetchFailed` was not set for the 4 fetches that did run. The stress condition the test was designed to create (heap pressure from back-to-back fetches of large ranges) was never actually reached.

**Root cause**: The test was designed from the tap side ("fire N taps") rather than from the fetch side ("confirm N fetches actually executed"). The queue-depth limit is a firmware constant that the VE should consult when designing throughput stress tests. No assertion on the number of actual fetches was made.

**Suggested improvement**:
- Stress tests targeting a queue-backed task must assert on *completed* fetch count (e.g. `lastChartFetch` counter advancing), not on *commands fired*. A stress test that can't verify its own load level has unknown coverage.
- VE should read the firmware's `xQueueCreate(depth, ...)` call when designing queue-driven tests. If queue depth < intended rounds, either reduce round rate to let the queue drain between rounds, or accept that only `depth` concurrent fetches will run and size ROUNDS accordingly.
- For coverage of all ranges under pressure: send one tap per range, wait for the fetch counter to advance, repeat — rather than firing a burst that floods the queue.

**Resolution (2026-05-30)**: Added `fetchOkCount` monotonic counter to `StockAppState` (incremented on every successful chart parse in `stockTickChart()`; exposed via `get`/`set` serial commands). Replaced `_wait_chart_enqueue()` (enqueue proxy via `lastChartFetch`) with `_wait_chart_complete(before)` which polls `fetchOkCount` until it advances past a pre-tap snapshot — proven HTTP+parse completion, independent of queue depth. T186, T187, T188 all updated: snapshot → tap → assert count advanced. Blind 35 s sleep eliminated. Constraint is now structurally enforced by the counter, not by the test author's knowledge of queue depth. Committed `6c3c70f`.

**Status**: adopted → BP-013 (2026-05-30).

---

### LL-042 — 2026-05-29 — VE stress test took three implementation iterations due to serial port contention assumptions

**Context**: T186 was written three times before it ran correctly. Iteration 1 polled `fetchFailed` inside the tap loop — the DUT was too busy to answer serial queries in 3s. Iteration 2 used a background `threading.Thread` to collect log lines while `cmd()` ran concurrently — the thread consumed JSON ACKs from the serial stream, causing the same timeout. Iteration 3 separated the test into three serial phases (setup with generous timeouts / fire-and-forget taps / stream-read drain) and worked.

**Observation**: The serial port is not a concurrent resource. Any test design that reads from `dut.ser` on two threads simultaneously will produce intermittent ACK loss. This is a structural constraint of the harness, not a timing issue that can be fixed with longer timeouts.

**Root cause**: The harness's `Dut.cmd()` and `Dut.read_json()` assume exclusive ownership of the serial stream. When a background thread also reads from `dut.ser`, ACKs intended for `cmd()` are silently consumed. The constraint was not documented.

**Suggested improvement**:
- Add a note to the `Dut` class header: "Serial stream is not thread-safe. Never read `dut.ser` from a background thread concurrently with `cmd()`/`read_json()`."
- For tests that need to both send commands and collect asynchronous log lines: use the fire-and-forget + drain-phase pattern (send → don't wait for ACK → read stream directly → flush → query state). Do not use threads.
- DUT queries inside hot-firing tap loops should be avoided entirely; always post-check after a drain window.

**Resolution (2026-05-30)**: `Dut.__init__` now captures `_owner_thread = threading.current_thread()`. `_assert_owner()` is called at the top of `send()`, `read_json()`, and `drain_log_lines()` — any cross-thread access raises `RuntimeError` immediately with a LL-042 reference rather than silently consuming ACKs. The constraint is now machine-enforced at the call site, not reliant on documentation. Committed `6c3c70f`.

**Status**: adopted → BP-014 (2026-05-30).

### LL-043 — 2026-05-30 — VE agent spent first 10 minutes diagnosing a wrong DUT state claim before running any tests

**Context**: TASK-112 VE rerun. PM handoff stated "DUT is running a May 30 2026-06:39:34 debug build (aquarium agent flashed it)." The prior session was the aquarium CRAB-FIX-011–014 agent, which would have flashed the production target (`cyd2usb_winamp`) for visual verification — the debug target was never relevant to that work. The build timestamp in the heartbeat matched, which looked like confirmation.

**Observation**: The DUT had production firmware (`cyd2usb_winamp`, no `SERIAL_DEBUG`). The VE agent's first test run failed with `set cooldown 0 failed: {'ok': False, 'error': 'unknown command', 'cmd': 'set'}`. Diagnosing this required tracing through firmware source to distinguish `unknown command` (command not in `kCmds[]` at all — implies no `SERIAL_DEBUG`) from `unknown var` (command found, variable not found — implies debug firmware running but variable not registered). The agent correctly identified the root cause and reflashed the debug build, but consumed ~10 minutes and multiple tool calls before the first real test ran. The user notes this is a recurring pattern — prior agents have hit the same wall.

**Root cause**: Two compounding factors:
1. **Stale DUT state in handoff**: The prior agent (aquarium) flashed production firmware for its own testing, left the DUT in that state, and the PM handoff did not verify the build type — it inherited the claim from context. Build timestamps match between production and debug builds (same source, same date), so the heartbeat `build=May 30 2026-06:39:34` gave false confidence.
2. **No explicit SERIAL_DEBUG probe at harness startup**: `run_serialdbg_tests.py` connects, waits for DUT ready, then runs tests. It never explicitly checks that debug-only commands are available. The smoke check (T169) exercises `set cooldown 0` but the failure message is ambiguous to an agent without firmware-source context.

**Suggested improvement**:
1. **Harness-level preflight**: Add a `_verify_debug_firmware()` step to `Dut._wait_for_ready()` or as the first step in `main()`. Send `get heap` and check the response. If `ok: false, error: "unknown command"` → raise `RuntimeError("Production firmware detected — SERIAL_DEBUG not active. Reflash cyd2usb_winamp_debug before running tests.")`. This makes the diagnostic self-contained in ≤1s with zero firmware-source knowledge required.
2. **PM handoff: always state the flash command used**: The PM handoff should record the exact `pio run -e <ENV>` command the prior agent ran, not just the build timestamp. `cyd2usb_winamp` (production) vs `cyd2usb_winamp_debug` is the critical distinction.
3. **Agent briefings: treat DUT state as unverified**: Any briefing note that says "DUT is running X" should be treated as a *claim to verify*, not a *fact*. The first VE step should be preflight verification regardless of what the context says.

**Resolution (2026-05-30)**: `Dut._verify_debug_firmware()` added to `run_serialdbg_tests.py` — called at end of `__init__` after `_wait_for_ready()`. Sends `get heap`; raises `RuntimeError` with exact reflash commands if `unknown command` is returned. BP-017 adopted; PM handoff guidance added to the BP.

**Status**: adopted → BP-017 (2026-05-30)

---

### LL-044 — 2026-05-31 — Mechanism written but only exercised in debug path — never fires in production

**Context**: Touch UX design review (ADR-035 / M-TOUCH-UX). `touchScreenCoolDownTime` in `winampDisplay.h` is set by three handlers (VIS: 300 ms, Shuffle: 250 ms, Repeat: 250 ms) with correct, intentional durations. The variable had been in the codebase through multiple shipping milestones.

**Observation**: The variable is only checked inside `#ifdef SERIAL_DEBUG injectTouch()`. In every production build the check never executes. Users reported VIS cycling was too easy to skip past — the 200 ms shell cooldown (not the intended 300 ms) was the only gate. The bug was undetected because SERIAL_DEBUG tests ran the intended path; no test exercised the production path specifically.

**Root cause**: The guard (`if (millis() <= touchScreenCoolDownTime)`) was placed in the debug-injection path rather than in the production hot-path (`handleWinampInput()` Phase 2). Because the mechanism worked correctly under `injectTouch()`, it was never flagged as incomplete.

**Suggested improvement**: When adding a new timing gate or rate-limiter, verify the check lives in the path that production code actually executes — not only in a test-injection shim. A single comment at the write site (`touchScreenCoolDownTime = millis() + 300; // checked at Phase 2 top`) is cheaper than rediscovering the gap later.

**Status**: open

---

### LL-045 — 2026-05-31 — ADR and design doc drifted after VE-driven design change

**Context**: Touch UX design review round 2 (ADR-035 / M-TOUCH-UX). VE-CH2 changed the SpotifyApp signal chain: the original `wasLastInputAsync()` direct return was replaced by `_actionDispatched && spotifyTask::hasPendingActions()`. M-TOUCH-UX.md was updated in the same pass. ADR-035 Decision 4 was not.

**Observation**: Developer review (DEV-01) caught the divergence: M-TOUCH-UX described the new chain; ADR-035 still described the old one. A reviewer reading only the ADR would have implemented the wrong chain.

**Root cause**: The design revision was made in M-TOUCH-UX (the detail doc) while the ADR (the decision record) was treated as already-settled and not revisited. Two docs for the same decision with no enforced sync point.

**Suggested improvement**: After any design revision driven by a review finding, update both the ADR and the design doc in the same edit pass before closing the finding. Treat "update ADR" as a mandatory step of resolving a decision-level finding — not an optional follow-up. A checklist item on the review template would enforce this.

**Status**: open — second incident recorded under LL-046 (same root cause; code change during VE run). Escalate to BP.

---

## Retrospective — 2026-05-31 — TASK-114–118 (M-TOUCH-UX: hitbox + debounce + busy indicator)

Triggering work: full M-TOUCH-UX milestone — hitbox.h primitive (TASK-114), shell busy indicator infrastructure (TASK-115), SpotifyApp + StockApp integration (TASK-116), SERIAL_DEBUG deliverables (TASK-117), VE execution (TASK-118). Six commits across five phases. TASK-118 partially closed; two items (T-CDWN-02 re-run, T-BUSY-04 manual) remain open.

### What went well (no LL needed, recorded for balance)

- **Phase-gated delivery worked.** Each of the five implementation phases had an independent exit criterion (build, flash, smoke). No phase produced a regression that blocked the next. The amber indicator came up correctly on the first DUT flash.
- **Design review round paid off.** VE + Developer pre-implementation challenges (DEV-01..05, VE-CH1..CH3) caught five specification gaps before any code was written — `mutable` keyword, thread-safety for `_actionPending`, timer-reset guard on Move events, file list, and ADR sync. Five changes cheaper than five bugs.
- **VE automated 7 of 9 exit criteria.** T-BUSY-01/01b/02/03/05 and T-CDWN-01/03 all executed by the harness without manual observation. Only T-BUSY-04 (auto-clear with network-blocked DUT) is genuinely manual by design.
- **Simplification caught under test, not after shipping.** The `_actionDispatched` / `wasLastInputAsync()` chain (4 files, mutable flag, two-hop signal) was simplified to a direct `spotifyTask::hasPendingActions()` query during TASK-118 — before the task closed. The simpler code is in the tree; the complex design stayed on paper.
- **Harness fix was harness-only.** T076/T079/T081 failures were correctly diagnosed as a harness gap (no poll-for-idle between taps), not a firmware defect. The gate itself (shellBusy blocks sequential canvas taps) was correct and intentional.

---

### LL-046 — 2026-05-31 — Sequential-tap tests need poll-for-idle when a busy gate exists on the tap path

**Context**: TASK-118 VE execution. T076 (hit-zone boundary sweep, 8 taps) and T081 (transport suite, 5 taps) ran sequential `cmd tap` calls with only `set_cooldown_zero()` between them. After TASK-117 wired `g_shellBusy` into `cmdTap` (correct — T-CDWN-02 requires it), any transport tap that enqueues a Spotify action sets `g_shellBusy=true`. The next tap in the sweep arrived while busy was still true and was returned as `skipped:true, hit:CANVAS` — a test failure for the wrong reason.

**Observation**: T076/T079/T081 were written for a world where `cmdTap` had no busy gate. The gate was a new constraint added by TASK-117. No one checked whether existing tests remained valid under the new gate. The harness fix (`_poll_shell_busy(False)` before each tap) was mechanical and correct, but the gap between "gate added" and "existing tests audited" was never closed.

**Root cause**: Existing tests are not systematically re-evaluated when a new tap-path gate is introduced. The gate is an implicit precondition for every `cmd tap` call; existing tests inherited an undocumented precondition mismatch.

**Suggested improvement**: When a new gate is added to the `cmdTap` path (busy gate, cooldown gate, app-state guard), treat it as a breaking change for existing sequential-tap tests. The Developer or VE adding the gate must grep `run_serialdbg_tests.py` for bare `dut.cmd("tap ...")` calls that do not precede the tap with an idle-wait, and add `_poll_shell_busy(dut, False)` (or equivalent) where needed. This is a subset of BP-004 (mirror physical-touch path in inject path) applied to the harness level.

**Status**: open — promotion candidate.

---

### LL-047 — 2026-05-31 — Intermediate dispatch flag was unnecessary; terminal signal was directly observable

**Context**: TASK-116 implemented `SpotifyApp::hasPendingAsync()` as `_actionDispatched && spotifyTask::hasPendingActions()`. `_actionDispatched` was a `mutable bool` in SpotifyApp, set when `wasLastInputAsync()` reported an async dispatch, cleared when the queue drained. `WinampDisplay._lastInputWasAsync` was a per-call bool set at all async dispatch sites. The design required: two new state variables across two classes, `wasLastInputAsync()` checked after both Press and Release delegate calls, `mutable` qualifier on the flag, and `suspend()` to reset it.

During TASK-118 VE, the Developer recognised that `spotifyTask::hasPendingActions()` is the authoritative, self-clearing signal: the queue is non-empty exactly when a user action is in flight. The `_actionDispatched` gate added no information — it only filtered "was there ever a dispatch since the last reset," which is always true when the queue is non-empty and false when it is empty (the same condition the queue reports directly). The entire two-hop chain was replaced with one line.

**Observation**: The design introduced an intermediate tracking variable because the design assumed WinampDisplay's per-call async signal was the only available hook into "did an async dispatch happen." The queue-level signal was already present and directly observable, but was not considered as the primary signal during the review.

**Root cause**: Design reviews focused on "how does the shell know a tap dispatched async work" (signal path up from WinampDisplay) rather than "what is the authoritative source of truth for async work in flight" (spotifyTask queue). The authoritative signal was always one call away. The per-call `_lastInputWasAsync` approach was designed for a world where the queue might have other callers; in practice the queue is exclusively user-initiated, making the queue depth a direct proxy for "user tap in flight."

**Suggested improvement**: Before designing a signal chain to propagate state from a component (WinampDisplay) up through layers (SpotifyApp → shell), ask: "is the terminal state already queryable at the point of consumption?" If `hasPendingActions()` on the task is observable at SpotifyApp scope, prefer `return spotifyTask::hasPendingActions()` over any intermediate flag. The intermediate flag earns its keep only when: (a) the terminal signal is not accessible from the consumer, or (b) the consumer needs "was async dispatched at all" independently of whether it has drained. Neither applied here.

**Status**: open.

---

## Retrospective — 2026-05-31 — Reactive StaticJsonDocument sizing: three quote-path bugs, host test coverage gap

Triggering work: three DUT-discovered bugs in `dataTaskStorage.cpp fetchStockQuote()`, all fixed reactively on-device during the 2026-05-31 session:

1. `DynamicJsonDocument(8192)` → `-94 NoMemory` under heap fragmentation (~4 min uptime). Fix: switch to streaming filter + `StaticJsonDocument<256>` (commit 08f8d22).
2. `StaticJsonDocument<64> filter` too small for 5-level nested filter tree → silent truncation → all prices 0.0. Fix: upsize filter to `StaticJsonDocument<128>`, data to `StaticJsonDocument<256>` (commit c745b2f).
3. `fetchStockChart` had already been reworked to streaming filter (ADR-034); the same pattern was not applied to `fetchStockQuote`. Bug 1 is the direct consequence.

`test_yahoo_finance_api.py` exists specifically to surface this class of failure before any DUT flash (see LL-040, BP-015). None of the three bugs were caught by it. Two lessons extracted.

### What went well

- **Streaming filter pattern (ADR-034) was the right architecture.** Applying it to fetchStockQuote fixed two independent bugs simultaneously (heap pressure + doc sizing). One pattern; two symptoms resolved without hunting separately.
- **Error code decomposition (-91..-95, -100) made root-cause identification immediate.** Without the decomposition (865e403, 9864e29), NoMemory and filter-truncation would both surface as opaque `-99`.

---

### LL-048 — 2026-05-31 — LL-040 resolution note became stale when quote path acquired a filter

**Context**: LL-040 (2026-05-29) was adopted as BP-015 (2026-05-30). Its resolution note reads: *"QUOTE_BUDGET_B=8192 retained — quote fetch has no filter so raw bytes vs DynamicJsonDocument(8192) remains correct. Committed 50ce839."* On 2026-05-31 (commit 08f8d22), `fetchStockQuote` was reworked to use `StaticJsonDocument<128> filter + StaticJsonDocument<256> doc` with streaming. The note is now wrong: the quote fetch has a filter; `DynamicJsonDocument(8192)` no longer exists in the path.

**Observation**: `test_yahoo_finance_api.py` line 49 still reads `QUOTE_BUDGET_B = 8192` with the comment `# Raw payload bytes are the right proxy here: no filter, full parse into doc(8192).` Both the comment and the constant describe firmware code that no longer exists. T_SF_03 passes for any payload ≤ 8192 bytes — which is every real quote payload — while the actual firmware constraints (filter doc ≤ 128 bytes, data doc ≤ 256 bytes) are untested. This is a direct BP-015 violation: the test is asserting a proxy metric rather than the actual firmware constraint.

The stale note also breaks the cross-reference chain: LL-040's resolution is the only record that explains why QUOTE_BUDGET_B exists at all. Future readers of the test will believe the model is correct, because the lesson that established it says it is.

**Root cause**: The LL-040 resolution note was written in one session; the firmware change that invalidated it landed in the very next session. No rule requires updating the host test (or its companion lesson note) when the firmware parse strategy changes. BP-015 says "read the firmware parse path before writing the host budget check" — but it only triggers at test-creation time, not at firmware-change time.

**Suggested improvement**:
1. Whenever `fetchStockQuote()` or `fetchStockChart()` doc types or sizes change in firmware, the host test constants and comments must be updated in the same commit. Treat `QUOTE_BUDGET_B`, `CHART_MAX_POINTS`, and their comments as interface contracts between firmware and test, not static documentation.
2. Add a reverse-lookup comment in the firmware alongside each `StaticJsonDocument` declaration: `// HOST TEST: test_yahoo_finance_api.py QUOTE_BUDGET_B / CHART_MAX_POINTS`. This makes the coupling visible at both ends of the contract.
3. Update LL-040's resolution note to reflect the current (post-08f8d22) state: "Quote path now also uses streaming filter. T_SF_03 QUOTE_BUDGET_B=8192 is no longer the right model; see LL-048."

**Status**: open — BP candidate. See LL-049 for the related filter-doc sizing gap.

---

### LL-049 — 2026-05-31 — Filter document capacity not modelled in host test; StaticJsonDocument<64> filter truncation not catchable

**Context**: `fetchStockQuote()` uses `StaticJsonDocument<128> filter` to hold the filter tree before passing it to `deserializeJson(..., Filter(filter))`. The original size was `StaticJsonDocument<64>`. The filter tree is 5 levels deep (`chart → result[0] → meta → regularMarketPrice / chartPreviousClose`). ArduinoJson needs approximately 80 bytes to represent this tree; `StaticJsonDocument<64>` silently truncated it. The filtered fields were dropped; all prices parsed as 0.0. Fix: upsize to `StaticJsonDocument<128>`.

The host test has no check for filter document capacity. T_SF_03 checks raw payload bytes; even a perfectly-calibrated T_SF_03 could not catch a filter doc that is too small for its own tree — the filter doc is a firmware-internal allocation that is independent of payload size. BP-015 ("assert the actual firmware constraint") covers the *output* document (`StaticJsonDocument<256>` holding the two float fields) but does not extend to the *filter* document.

**Observation**: There is a class of `StaticJsonDocument` sizing bug that is structurally invisible to the host test: filter doc truncation. The filter tree topology (path depth × number of leaves) determines the minimum required capacity; this is derivable at design time from the filter structure, but is not currently recorded anywhere. A developer can set `StaticJsonDocument<64>` on a 5-level filter and the host test gives no signal. The only gate is the DUT.

**Root cause**: BP-015 was designed around the output document ("what buffer does the parsed result land in?"). It did not consider the filter document as a separate, independently-sized resource with its own capacity floor. The ArduinoJson documentation provides a capacity estimator formula; it was not applied when the filter was introduced.

**Suggested improvement**:
1. For each `StaticJsonDocument<N> filter` in firmware, add a comment recording the minimum required N and how it was derived. For the quote filter: `// 5-level path × 2 leaves → ~80B ArduinoJson minimum; <128> gives headroom`. For the chart filter: `// 5-level path × 1 leaf → ~56B minimum; <128> fine`. This makes the sizing auditable without a DUT.
2. Add a T_SF_03b check to `test_yahoo_finance_api.py`: parse one quote body in Python, extract only the filter fields (`chart.result[0].meta.regularMarketPrice/chartPreviousClose`), compute the minimal JSON size of that sub-tree, and assert it is well within `StaticJsonDocument<256>`. This does not catch filter-doc truncation directly but validates the output-doc sizing end-to-end.
3. Extend BP-015's scope: "Identify: is there a filter? What is the filter tree's depth and leaf count? Compute minimum filter doc capacity via ArduinoJson's estimator. Record it as a comment alongside the `StaticJsonDocument<N> filter` declaration." Add this as a checklist item when any new JSON filter is introduced in firmware.

Sister lesson to LL-040 (proxy metric vs actual constraint) and LL-038 (large heap alloc fails silently). Theme: **ArduinoJson has two separately-sized documents per filtered parse; both must be sized deliberately, both must be documented.**

**Status**: open — BP candidate. Bring to human for sign-off before promoting.

---

### LL-045 recurrence note — 2026-05-31 — Code change during VE run left both ADR and design doc stale

**Context**: LL-045 (filed today, same session) describes ADR/design doc drift after a VE-driven design change. This is a second incident of the same root cause: the `_actionDispatched` simplification made during TASK-118 was a code change, not a design-review finding, but it had the same outcome — both ADR-035 and M-TOUCH-UX.md described the old chain after the code was live. The fix was made same-session (afe35b6) but only after the retro surfaced the gap.

**Observation**: LL-045 was filed as an open lesson with a suggested improvement ("update ADR in the same edit pass as the design doc"). That improvement was not applied here because the code change happened during a test run, not a formal review pass. The suggested improvement is correct but only covers review-driven changes; it does not cover implementation-driven simplifications.

**Root cause addition to LL-045**: Doc drift is not limited to review rounds. Any code change that contradicts a named design decision (ADR or design doc) — including simplifications discovered during implementation — must trigger a doc sync before the commit that makes the change. The rule is: "code and doc always agree at commit boundary."

**Suggested improvement (extension to LL-045)**: The sync rule must apply to implementation-driven changes as well as review-driven changes. Add to the Developer checklist (LL-010): "if this commit changes an interaction described in an ADR or design doc, update the doc in the same commit." The git diff is the enforcement point — if an ADR is named in the commit context but not in the diff, that is a flag.

**Status**: escalate to BP together with LL-045. Two incidents of the same root cause, two days apart, same codebase.

---

### LL-050 — 2026-06-03 — LL-038 recurrence: 4 KB DynamicJsonDocument malloc failed after 60+ min TLS cycling; getMaxAllocHeap() not logged

**Context**: `fetchHeatmapQuote()` used `DynamicJsonDocument doc(4096)` allocated per call. After ~60 min of TLS session cycling (Spotify + Yahoo Finance fetches each temporarily consuming ~32 KB), heap fragmentation left no contiguous 4 KB block despite 123 KB total free. `malloc(4096)` returned null; `doc.capacity() == 0`; `deserializeJson` failed immediately with `NoMemory`. LL-038 (2026-05-25) diagnosed the same failure class for a 64 KB allocation in `getQueue()` and recommended streaming parse + avoiding large per-call heap buffers. The 4 KB heatmap doc was within the revised approach (streaming filter, small output doc) but was still allocated per call rather than statically.

**Observation**: Three things caused this to consume hours of RnD time instead of minutes:
1. **`getFreeHeap()` alone is misleading.** Heartbeat logged `heap=123k` — appeared healthy. `getMaxAllocHeap()` was not logged; fragmentation was invisible until EXP-003 analysis.
2. **No `doc.capacity()` log after construction.** A malloc failure produces `capacity()==0`, which is distinguishable from a pool-too-small failure (`capacity()==4096`, `memoryUsage()>4096`). Without that log, both hypotheses (malloc fail vs undersized pool) required hours to distinguish analytically.
3. **LL-038's suggested improvement only named ≥16 KB as a risk threshold.** The `DynamicJsonDocument(4096)` was within what felt like "safe" territory, so LL-038 didn't trigger a review of the heatmap path.

**Root cause**: LL-038 was partially absorbed: streaming parse and small output docs were used, but the lesson "prefer static allocation for any document that will be repeatedly constructed alongside TLS sessions" was not applied because the 4 KB size was below the named threshold. The fragmentation check (`getMaxAllocHeap()`) recommended in LL-038 was also never added to the heartbeat, so recurrence had no early-warning signal.

**Suggested improvement**:
1. **`ESP.getMaxAllocHeap()` in every heartbeat.** Now done (`maxAlloc=Nk` field, commit `dcf8e72`). This is the direct fragmentation indicator; `getFreeHeap()` alone should not be the only heap metric.
2. **Log `doc.capacity()` immediately after any `DynamicJsonDocument` construction.** Cost: one `LOG_D`. Value: instantly separates malloc failure from pool overflow. Now done for `s_heatmapDoc`.
3. **Revise LL-038's threshold.** The 16 KB threshold is not the right rule. The rule is: *any `DynamicJsonDocument` constructed inside a function called repeatedly alongside TLS sessions should be static + `clear()`*. Size is not the criterion — cycling frequency and TLS coexistence are. Add this as BP candidate.
4. **T-HEAT-* suite gap.** Tests ran on fresh-booted DUT. A long-uptime fragmentation failure is not catchable by any current test. This is the same gap as LL-039 ([RESOURCE-SENSITIVE] tests not re-run under different heap conditions). Note it in test_plan.md: T192-T196 should be re-run after 60 min of continuous DUT operation before any M-HEATMAP milestone sign-off.

**Status**: open — items 1–3 are BP candidates; item 4 is a VE handoff.

---

### LL-051 — 2026-06-04 — DoubleResetDetector trap: host-side serial port open + DTR toggle = two resets = portal stuck

**Context**: During test harness iteration (TASK-138f), the DUT ended up stuck in `startConfigPortal()` (no-timeout, blocking). The immediate cause was a Python one-liner that opened `/dev/ttyUSB0` and toggled RTS to reset the ESP32. This was issued to recover the DUT after a previous reset.

**Observation**: Every attempt to reset the DUT via host tooling re-triggered the portal instead of escaping it. After multiple iterations the DUT was still stuck. Root cause was not identified in the session; repeated "reset" commands compounded the problem.

**Root cause**: Three mechanisms interact to create the trap:

1. **CH340 DTR-on-open**: When any program opens `/dev/ttyUSB0`, the OS asserts DTR. On the CYD board (CH340 with standard EN/IO0 circuit), asserting DTR triggers an EN (chip enable) reset pulse. This counts as **reset #1**.

2. **DRD_TIMEOUT = 10s**: Any second reset within 10 seconds causes `DoubleResetDetector::detectDoubleReset()` to return `true`.

3. **`startConfigPortal()` has no timeout**: When `forceConfig=true`, the code calls `wm.startConfigPortal("SpotifyDIY","thing123")` — this blocks indefinitely. There is no escape without entering credentials in the form, OR issuing a single clean reset from outside the 10s window.

The compounding error: once in `startConfigPortal()`, `drd->stop()` has already been called (DRD state cleared). A single clean reset at this point would escape the portal. But every host-side "reset attempt" reopened the serial port (= implicit DTR pulse reset #1), then toggled RTS within milliseconds (= reset #2) — retriggering the DRD on every attempt.

**Suggested improvement**:

1. **Never issue two resets within 10 seconds.** Any host-initiated reset (DTR toggle, RTS pulse, port open/close) counts. If the DUT was reset within the last 10 seconds — by any means — wait out the full 10s window before the next reset.

2. **Prefer physical button press** when recovering from portal: a deliberate single press of the EN/RST button on the board has no implicit second pulse. Host-side serial port tooling should be closed (port not open) when the physical reset is pressed.

3. **Escaping force portal**: `startConfigPortal()` calls `drd->stop()` before blocking. So once in the force portal, the DRD state is cleared. One clean reset (≥10s after ANY prior reset) is sufficient — it exits to `autoConnect()` which connects to saved NVS WiFi creds. Do NOT open the serial port and immediately reset; open port, wait ≥12s, then test.

4. **Harness note for `run_serialdbg_tests.py`**: `Dut.__init__()` opens the serial port. If the DUT was recently reset, opening the port triggers DTR reset #1. The `_wait_for_ready()` drain loop waits for the WiFi-connected banner, but it does NOT prevent DRD triggering on a rapid second reset. Harness reconnect / restart logic must respect the 10s gap.

**Status**: open — items 1–3 are BP candidates

---

## Retrospective — 2026-06-06 — settings-001 DUT validation (LedSection / KeyboardWidget / CalibrationFlow)

Triggering work: implementation and first DUT validation of the three new settings sections and PATCH-002. Human observer flagged the validation session as "amateur hours." Below: what went wrong, the waste, and what to fix.

---

### LL-052 — 2026-06-06 — USB port discovery done manually every session

**Context**: Every validation session required a separate `ls /dev/ttyUSB*` invocation to confirm the port before flashing or monitoring. Port varied between `ttyUSB0` and `ttyUSB1` across sessions with no explanation.

**Observation**: Three separate port-lookup commands were issued across the session. Each command produced output that had to be read and threaded into the next command. The `run_serialdbg_tests.py` error message even suggested the wrong port (`/dev/ttyUSB0`) while the real device was on `/dev/ttyUSB1`.

**Root cause**: No canonical "what port is the DUT?" helper exists. The CH340 USB-serial adapter for this board always has VID:PID `1A86:7523`; that fact is documented in CLAUDE.md but no command uses it.

**Suggested improvement**: Add a one-liner to `app/tools/dut_port.sh` that resolves the port by VID:PID and prints it:
```sh
#!/usr/bin/env bash
# Resolves the CYD2USB CH340 serial port by USB VID:PID 1A86:7523.
port=$(ls /dev/ttyUSB* 2>/dev/null | while read p; do
  udevadm info -q property "$p" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" && echo "$p" && break
done)
[ -n "$port" ] && echo "$port" || { echo "ERROR: DUT not found" >&2; exit 1; }
```
All other tools (`flash.sh`, monitor alias, test harness) call `$(dut_port.sh)` instead of hardcoding the port. Document in `docs/process/dut_workflow.md`.

**Status**: open — BP candidate (BP-019)

---

### LL-053 — 2026-06-06 — Monitor session not killed before flash; two serial-port collisions

**Context**: `run_serialdbg_tests.py` was called while the tmux `spotify-mon` session held `/dev/ttyUSB1`. The test harness received `SerialException: device reports readiness to read but returned no data` and died. A second attempt failed because the wrong firmware (production, not `SERIAL_DEBUG`) was running.

**Observation**: Three separate attempts were needed before a test run succeeded: (1) port busy → error, (2) debug firmware not flashed → `RuntimeError`, (3) success. Each attempt wasted ~30-60s of iteration.

**Root cause**: No pre-validation checklist. The steps "kill monitor → flash debug build → run tests" exist in CLAUDE.md piecemeal but not as a single ordered procedure with guards.

**Suggested improvement**: Codify a `validate.sh` wrapper (or section in `docs/process/dut_workflow.md`) that enforces the sequence:
```
1. kill tmux spotify-mon  (idempotent)
2. flash cyd2usb_winamp_debug
3. sleep 8                (boot + WiFi settle)
4. run_serialdbg_tests.py [--filter <ids>]
5. flash cyd2usb_winamp   (restore prod)
6. restart tmux spotify-mon
```
A `--filter` flag already exists (or should); targeted test runs for new features avoid the full 10-minute suite during development.

**Status**: open — BP candidate (BP-020)

---

### LL-054 — 2026-06-06 — Test harness is a black box; no targeted new-feature run

**Context**: After implementing three new sections, the full 100+ test suite was launched. The settings-specific tests (T-SET-01..08) are at the very end of the suite, so ~8 minutes of stock/crypto/weather/GoL tests ran before reaching the relevant tests.

**Observation**: The new code's test coverage (T-SET-01/02/08 pass; T-LED, T-KB, T-CAL all manual-only) was visible only after the full suite completed. Time wasted on pre-existing failures and Spotify-not-playing skips that have nothing to do with the new feature.

**Root cause**: The harness has no documented way to run a named subset. The LLM agent launched the full suite without knowing a filter existed or could be added.

**Suggested improvement**:
1. Document `run_serialdbg_tests.py --run T-SET-01,T-SET-02,T-SET-08` (or add this flag if not present) in `docs/process/dut_workflow.md` under "Targeted feature validation."
2. Each VE test plan entry should cross-reference which harness test ID covers it (or mark "manual only — no harness test").
3. Add a "smoke" preset: a minimal fast-passing subset (T080/T083/T091/T092/T147/T162/T-SET-01/02/08) that confirms basic shell health in <2 min.

**Status**: open — BP candidate (BP-021)

---

### LL-055 — 2026-06-06 — Two separate calibration bugs found only at DUT runtime

**Context**: The calibration `_computeCalibration()` had two bugs: (1) xMax extrapolated to x=274 instead of x=319 (45px short), (2) `_drawTapMarker` mapped raw to 0..274 instead of 0..319, compressing every marker leftward. Both required a DUT flash cycle to diagnose.

**Observation**: Both bugs were pure arithmetic, detectable by desk-check or unit test without hardware:
- The extrapolation targets (x=274 vs x=319) could be verified by comparing `S_CANVAS_W` (275), `sizeX_px` (320), and `kCalTX[]` values on paper.
- The marker formula `map(..., 0, 274)` vs `(raw - min)*320/range` is a one-line discrepancy visible in code review.

**Root cause**: No code review pass was done before flash. The audit after LED+Keyboard (Task 4) was not extended to CalibrationFlow; it was called complete before the flash cycle. The design doc did not state the driver's `sizeX_px=320` constraint explicitly, so the implementation assumed canvas-width (275).

**Suggested improvement**:
1. CalibrationFlow design doc (or inline in the header): explicitly state "driver maps raw → 0..(sizeX_px-1); sizeX_px=320; all extrapolation targets must use 319, not 274 (= S_CANVAS_W-1)."
2. Pre-flash arithmetic check for any calibration-related change: write out the four edge targets and verify they equal 0, 319, 0, 239.
3. Code review checklist item: "any `map(raw, calMin, calMax, 0, X)` — confirm X matches driver sizeXY_px."

**Status**: open — BP candidate (BP-022)

---

### LL-056 — 2026-06-06 — Process documentation is scattered; no single workflow reference

**Context**: CLAUDE.md documents commands for build, flash, monitor, SPIFFS, and serialdbg tests, but as disconnected snippets across a long file. The LLM agent had to re-derive the correct sequence each session from memory or re-read the file.

**Observation**: A first-time operator (or agent starting cold) has no single page that says: "to validate a new feature, do steps 1-N." Setup (WiFi, Spotify keys), build variants, SPIFFS management, debug vs production firmware, and test harness operation are all described in different sections.

**Root cause**: Documentation grew organically alongside the codebase. No process-level document was ever written.

**Suggested improvement**: Create `docs/process/dut_workflow.md` as the single DUT operations reference covering: first-time setup, build variants, flash (with/without SPIFFS), serial monitor, targeted feature validation, regression suite, and how to interpret results. See new file created alongside this retrospective.

**Status**: open — adopted (dut_workflow.md created this session)

---

### LL-057 — 2026-06-07 — run/ scripts invisible to cold-start agents; CLAUDE.md still had raw commands

**Context**: `run/` folder created with 15 scripts implementing the full DUT workflow. QM audit found that a cold-start agent reading CLAUDE.md would see the original raw `pio`/`tmux` command blocks and have no indication that `run/` existed — it would bypass the safety `trap` in `run/test` and issue raw commands with no restore guarantee.

**Observation**: Three layers of documentation (CLAUDE.md, dut_workflow.md, best_practices.md BP-020/021) all still referenced raw commands after `run/` was implemented. `dut_workflow.md` cross-ref pointed to the proposal file, not the live quick-reference. CLAUDE.md had zero mention of `run/`.

**Root cause**: New tooling was implemented without updating the primary agent entry point (CLAUDE.md). Agent discoverability depends entirely on what CLAUDE.md surfaces — if it isn't there, agents won't find it regardless of how well-documented the tool is internally.

**Suggested improvement**: Any new `run/` script or process document must include a CLAUDE.md update in the same commit. Rule: "if CLAUDE.md doesn't mention it, it doesn't exist to agents."

**Status**: adopted — CLAUDE.md updated (raw commands replaced with `run/` references), dut_workflow.md cross-ref fixed, BP-020/021 updated to cite `./run/test` and `./run/test-targeted`.

---

### LL-058 — 2026-06-07 — run/test-sync mislabeled "host-only"; requires DUT

**Context**: `run/test-sync` was written and documented as "host-only sync tests (no DUT required)" in CLAUDE.md, `project_run_scripts.md`, and `dut_workflow.md`. VE no-DUT validation caught the error: `run_sync_tests.py` opens the serial port immediately on startup and fails with `SerialException` if no device is connected. Every test function in the file takes a `Dut` object — there is no host-only mode.

**Observation**: The mislabeling would have caused an agent to invoke `./run/test-sync` expecting it to complete without hardware, receive a crash, and misdiagnose the failure as a script or environment issue rather than a missing device.

**Root cause**: The label "sync tests" refers to the test suite name (sync-001/drift-001/playlist-001), not to DUT independence. The author assumed "sync" implied host-side only without verifying the runner's actual startup behavior.

**Suggested improvement**: Before labeling any test script "host-only" or "no DUT required", verify by running it without the device connected. A script that calls `serial.Serial().open()` at module load or `__init__` time is never host-only regardless of what the tests themselves do.

**Status**: adopted — `run/test-sync` rewritten with full 6-step validation loop; "host-only" label removed from all three docs in the same session before the commit landed.

---

---

### LL-059 — 2026-06-08 — Harness sync model grew by trial-and-error; no contract at inception

**Context**: The regression harness's state-synchronisation approach — `shellBusy` polling, `fetchOkCount` counters, `time.sleep` margins — was never formally specified. Each test was written and tuned locally until it passed, then committed.

**Observation**: Over 30 commits, 8 fix commits targeted the same four tests (T-BUSY-*, T-CDWN-02, T169), each fix stacking additional waits or retries on top of the last. The underlying race conditions (background poll contamination, UART garbling) were never surfaced as root causes — only their symptoms were patched. The problem was identified only by an external audit, not by the team's own process.

**Root cause**: No synchronisation contract was written when the harness was first built. Without a spec, tests had no shared reference for "which mechanism proves what." Trial-and-error produced locally-working tests whose assumptions were invisible and fragile.

**Suggested improvement**: When introducing any harness mechanism that depends on DUT state (polling, counters, flags), write a two-sentence contract before writing the first test that uses it: "this mechanism proves X; it is unreliable when Y." Commit the contract alongside the mechanism. See `docs/process/harness_sync_contract.md` (ADR-042 E3 deliverable) as the retroactive baseline.

**Status**: adopted — BP-023 (2026-06-08)

---

### LL-060 — 2026-06-08 — Debug interface was retrofit, not designed-in; observability gaps discovered during testing

**Context**: The serial debug interface (M-SERIALDBG, ADR-021) was added to enable testing of an already-implemented firmware. Variables were added to `get`/`set` as tests needed them. No master inventory of observable state was ever defined.

**Observation**: VE's DFT readiness review (2026-06-08) identified four gaps: no fixture/reset command, no event channel, incomplete debug var inventory, no DFT-first process for new features. All four gaps are symptoms of a debug interface designed around what tests happened to ask for, not around the firmware's full observable state space.

**Root cause**: "Design For Testing" was not a gate for feature implementation. Features shipped, then the debug interface was backfilled by whoever needed to test them.

**Suggested improvement**: For each new feature, VE authors a debug variable spec *before* implementation begins — answering: what state must be readable, what state must be writable, what events must be emitted. Developer implements the debug interface as part of the feature (not as a follow-up). This closes the gap without requiring a dedicated testability milestone.

**Status**: adopted — BP-024 (2026-06-08)

---

### LL-061 — 2026-06-08 — Touch injection path not updated when second touch consumer (taskbar gesture API) was added

**Context**: TASK-158 investigation into T163/T165 failures. `cmdDrag` was originally implemented during M-SERIALDBG when `handleWinampInput` was the only touch consumer. Later, M-TASKBAR-SCROLL added a separate gesture state machine (`tbGesturePress/Continue/End`) for the taskbar zone. `drainInjectionQueue` was never updated.

**Observation**: All injected touch samples routed through `handleWinampInput` regardless of x-coordinate. Taskbar-zone samples (`sx >= TASKBAR_X`) never reached the gesture API, so `cmdDrag` on the taskbar had no effect. The bug was invisible until T163 exercised it.

**Root cause**: Adding a new touch zone with its own state machine is a compound change: the gesture API, the physical touch dispatcher, and the injection dispatcher must all be updated together. The last site was missed.

**Suggested improvement**: When adding a new touch zone that owns its own state machine, treat the injection dispatcher (`drainInjectionQueue`) as a required update site alongside the physical dispatcher (`appHandleInput`). Checklist: physical dispatcher updated? injection dispatcher updated?

**Status**: open

---

### LL-062 — 2026-06-08 — Suppression flag added without the consuming guard

**Context**: TASK-158, bug 2. `_injectingDrag` was added to suppress premature `tbGestureEnd` during serial drag injection. The flag was set in `drainInjectionQueue` and cleared on release, but the guard `!winampDisplay._injectingDrag` was never written into `appHandleInput`'s `!touched` branch.

**Observation**: The flag was dead state for the entire period between M-TASKBAR-SCROLL and TASK-158. The `!touched` branch fired `tbGestureEnd` on every physical scan cycle where `touched == false` during a serial drag, cancelling the gesture. T165 exposed this (scroll offset wrong after wrap).

**Root cause**: "Add suppression flag" was treated as a complete unit of work. It is not — the flag has no effect until the guard that reads it is also implemented. Without a test for the guarded behavior, the gap was invisible.

**Suggested improvement**: A suppression flag and its consuming guard are a single atomic unit of change. Never commit the writer without the reader. If the reader cannot be implemented in the same commit, leave the flag out entirely — dead state is actively harmful.

**Status**: adopted — BP-025 (2026-06-08)

---

### LL-063 — 2026-06-08 — Test constant preserved at hardcoded value instead of symbolic expression when APP_COUNT changed

**Context**: TASK-158, bug 3. When Aquarium was added (APP_COUNT 8 → 9), the test constant `_TB_N` was updated from `8` to `APP_COUNT - 1` — preserving the numeric value 8 while updating the expression. The comment also changed from `# AppId::COUNT` to `# AppId::COUNT - 1`, which was wrong.

**Observation**: `_TB_N = APP_COUNT - 1 = 8` caused T165 to expect `tbScrollOffset = 7` (wrap-down from 0 mod 8), but firmware wraps mod 9, giving 8. The test failed; the firmware was correct.

**Root cause**: The updater's intent was to keep `_TB_N = 8`. The correct update was `_TB_N = APP_COUNT` (letting it grow to 9). The `- 1` was cargo-culted from the idea that "this excluded the 9th app" — but no app is excluded from the taskbar scroll.

**Suggested improvement**: Test constants that are derived from a count (APP_COUNT, AppId::COUNT) should always be expressed symbolically as `APP_COUNT` (or `APP_COUNT - k` with a documented reason for k). Never preserve a numeric value when the underlying count changes — update the expression to stay truthful. If `k != 0`, the comment must explain which app is excluded and why.

**Status**: adopted — BP-026 (2026-06-08)

### LL-065 — 2026-06-11 — Design doc code snippet copied to production without reviewing side effects

**Context**: M-SETUP-WIZARD design doc (`M-SETUP-WIZARD.md`) contained a PATCH-003 pseudocode snippet using `WiFi.persistent(true)`. The snippet was copied directly into `WifiManagerHandler.h` during implementation. `WiFi.persistent(true)` causes `WiFi.begin()` to write credentials to NVS before the connection attempt succeeds. When SPIFFS credentials are wrong, the NVS is overwritten with bad credentials, destroying the device's prior saved WiFi state.

**Observation**: The bug was not caught at design review or implementation — it was found during VE (T-SETUP-10). The test device's NVS was corrupted during testing, requiring a recovery flash with `wifi_creds.h`. The fix (change to `WiFi.persistent(false)`) was one line but required an extra DUT cycle.

**Root cause**: Design doc code snippets are treated as illustrative pseudocode during design review, but are often copied verbatim during implementation. The reviewer and implementer may have different mental models of which review standard applies. Side effects that are invisible in happy-path tests (NVS corruption only manifests when credentials are wrong) bypass normal build and smoke verification.

**Suggested improvement**: Any code snippet in a design doc that is likely to be copied verbatim into production should be reviewed with the same rigour as production code — specifically: identify all side effects, check whether those effects are conditional on success or unconditional. If a snippet cannot be reviewed to that standard at design time, annotate it explicitly as "pseudocode — do not copy; verify side effects at implementation."

**Status**: adopted — BP-028 (2026-06-11)

---

### LL-064 — 2026-06-11 — Happy-path smoke test accepted as proof of safety-property claim
**Context**: TASK-161 (`run/spiffs` non-destructive SPIFFS manager) was closed by an LLM agent after `./run/spiffs ls` returned 5 filenames. The feature's primary claim — that push and rm operations are non-destructive (untargeted files preserved byte-identically) — was never tested. An EXIT trap defect (monitor not restored on implicit `set -e` failure) also existed at closure.  
**Observation**: A VE challenge review (triggered the same session by human) identified the gap. Three recovery tasks were required: TASK-163 (trap fix), TASK-164 (design doc correction), TASK-165 (full T-SPIFFS suite). All were completed on DUT.  
**Root cause**: The closing agent treated "happy path exercised" as equivalent to "safety claim verified." The feature spec explicitly used the word "non-destructive" — that word is a testability signal that was not recognised as requiring a preservation test.  
**Suggested improvement**: When a feature's spec, description, or task body contains a safety-property word (non-destructive, preserving, atomic, idempotent, safe, clean), the VE exit criteria must include at minimum: (1) one test that verifies the property under normal use, and (2) one test that verifies correct behaviour when the target does not exist. A happy-path smoke test does not satisfy a safety-property claim.  
**Status**: adopted — BP-027 (2026-06-11)

## Entry Format

---

### LL-067 — 2026-06-12 — Pinned TLS root CA became stale when CoinGecko rotated from GTS to Let's Encrypt
**Context**: TASK-172 VE run. T_CX_05 (CryptoApp receives live data within 30 s) failed persistently. CoinGecko API returned HTTP -1 (ESP32 WiFiClientSecure "connection refused") from `http.GET()`. `COINGECKO_ROOT_CA` in `dataTaskCerts.h` was GTS Root R4. Live cert chain (`openssl s_client`) showed CoinGecko had rotated to Let's Encrypt YE1 / ISRG Root X1.  
**Observation**: The test failure presented as "fetch never completes" with no visible error — the only diagnostic was the raw LOG_D serial line (`GET -1 elapsed=…`) which the test harness does not capture. Diagnosis required adding a `cryptoHttpCode` dbgGet surface.  
**Root cause**: TLS root CA was pinned by copy-pasting the cert in force at the time the code was written. No mechanism exists to detect CA rotation before it causes failures in production or test.  
**Suggested improvement**: (1) When a TLS endpoint starts returning -1 and the API URL is otherwise valid, check the live cert chain first (`openssl s_client` or `curl -vI`). (2) The ADR-029 rotation table should include a periodic validation step (e.g., quarterly `openssl s_client` check for each pinned host). (3) `lastCryptoHttpCode()` diagnostic (now exposed via `get cryptoHttpCode` serial command) should be checked when T_CX_05 fails.  
**Status**: open — propose BP-030 on TLS cert rotation check cadence (see best_practices.md)

---

### LL-068 — 2026-06-12 — App `resume()` must reset fetch timer so re-entry always triggers a fresh request
**Context**: TASK-172 VE. CryptoApp `init()` enqueued a fetch and set `_s.lastCryptoFetch = millis()`. T_CX_04 briefly switched to CryptoApp then switched away. T_CX_05 switched back (calling `resume()`). `resume()` did not reset `_s.lastCryptoFetch`, so `cryptoTick()` calculated elapsed time from the `init()` call and skipped the enqueue for ~60 s. If the `init()` fetch failed (as it did here — wrong root CA), no retry occurred within the 30 s test window.  
**Observation**: The fix was one line: `_s.lastCryptoFetch = 0` in `resume()`. Without it, re-entering an app feels broken even when the underlying API is healthy, because the user may wait up to CRYPTO_FETCH_MS (60 s) for a refresh.  
**Root cause**: `resume()` was designed to restore display state cheaply. The assumption was that a fetch already in-flight from `init()` would complete. That assumption breaks when (a) the fetch failed, (b) the app was exited before the result arrived, or (c) the prior result was consumed by `pollCrypto()` before re-entry.  
**Suggested improvement**: Apps with a periodic fetch timer should reset the timer to 0 in `resume()` so the first `tick()` after re-entry always enqueues. This is low cost (one extra fetch) and prevents the "stale for up to 60 s" experience.  
**Status**: adopted — applied in `CryptoApp::resume()` (commit a708657)

---

### LL-094 — 2026-06-28 — Sensor-blind gate criteria need a startup-transient definition
**Context**: TASK-263 DUT validation of the halved I2S DMA ring (8×256) at 128 kbps. Gate was `underruns == 0`. All 3 trials returned `underruns = 1` — a single event at T < 5 s during initial buffer fill, never recurring. The spec acknowledged "agent can't listen; counter is the quantified gate" but left the startup-transient boundary undefined, forcing a PARTIAL verdict requiring human interpretation to clear the gate.  
**Observation**: The gate ambiguity cost one human decision cycle. The data was unambiguous in hindsight (single event at connect time, counter frozen for 120+ s), but the spec gave no rule for distinguishing it from a recurrent failure.  
**Root cause**: The spec author deferred the "what counts as recurrent" definition to execution time because the underrun pattern wasn't known in advance. When underruns fired (even just once), the written gate couldn't distinguish a transient from a real failure.  
**Suggested improvement**: For any sensor-blind gate (agent cannot hear audio, see a display, etc.), the spec must pre-define a startup grace window, e.g. "underruns occurring within the first 10 s of PLAYING entry are startup transients and excluded from the gate count." Conservative values are fine — the point is that the agent can render a verdict without escalating.  
**Status**: open

---

### LL-095 — 2026-06-28 — Fresh agent handover prompts must require an explicit commit
**Context**: TASK-264 (Q3-a TLS-drop). The implementation was correct, run/check 5/5 green, but the fresh agent left all three changed files uncommitted. PM caught it via `git status` and committed manually. This is the second recorded occurrence of this pattern.  
**Observation**: The handover prompt specified files to read, the implementation approach, constraints, and verification steps — but said nothing about committing. Agents complete and verify code then stop; committing feels like an optional follow-on unless explicitly required.  
**Root cause**: Handover prompt templates do not include a commit step. The omission is systematic, not task-specific — any prompt that lacks "commit your changes" reproduces this gap.  
**Suggested improvement**: Every fresh-agent handover prompt for an implementation task must include an explicit final step: "Commit all changes on `<branch>` with a conventional commit message referencing the task ID." One line; eliminates the gap reliably.  
**Status**: adopted → BP-043

## Entry Format

```
### LL-001 — [YYYY-MM-DD] — [Topic]
**Context**: What was happening at the time
**Observation**: What went wrong or what worked well
**Root cause**: Underlying reason
**Suggested improvement**: Actionable change
**Status**: open | reviewed | adopted | dismissed
```