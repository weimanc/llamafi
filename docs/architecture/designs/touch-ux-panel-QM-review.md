# QM Panel Review — Touch-UX design trio (TASK-277 / TASK-278 / TASK-279)

> Owner: QM
> Date: 2026-07-03
> Scope: process/quality compliance review of the three 2026-07-02 draft designs
> (commit a1cf11c), following the finding/disposition style of the M-WIFI-DIAG panel
> (M-WIFI-DIAG-outage-attribution.md §7–8). Findings labelled QM-<doc#>-<n>,
> classified blocker / major / minor, one-line proposed resolution each.
> Architect dispositions; QM does not edit the design docs.
> Companion review: [touch-ux-panel-VE-review.md](touch-ux-panel-VE-review.md) —
> testability findings live there; where the two reviews converge, this doc
> concurs and cross-references rather than restating.

Review bar applied: (a) designs/ template + artifact ownership (architect.md);
(b) claims traceability — every "measured/verified" claim needs a source, same bar as
M-WIFI-DIAG QM-4/5 (evidence overclaims); (c) repeated-lesson risk against
lessons_learned.md; (d) scope discipline — deferred items parked with owner/trigger,
not prose (BP-003/BP-035/BP-040 family); (e) golden-hash rule for asset/colour changes
(ADR-046 wording verified in `docs/architecture/decisions/ADR-046.md:29-49`).

Code claims were independently spot-checked on the tree at review time. Verified
accurate: all cited `main.cpp` line refs (1819 `switchApp`, 1860 `appHandleInput`,
1909-1919 release path, 2289-2334 `drainInjectionQueue`, 2386-2390 `cmdTap`);
`winampDisplay.h` 532-553/693-707/414-415/63; `webRadioApp.h` 390-426/310/727-732/80;
`spotifyTaskStorage.cpp:38-40` and `dataTaskStorage.cpp:100-105` (core 1, prio 1);
TWDT 15 s + loopTask + CPU0-idle subscription (`main.cpp:1941-1948`); taskbar
`TASKBAR_APP_COUNT` + both TASK-242 `static_assert`s present (`taskbar.h:26-36`);
`gen/` file is `shell_layout.h` as claimed; no `xTaskCreate` in the vendored
`app/lib/ESP32-audioI2S/src/` (doc 2's "v2.3.0 has no built-in audio task" is true,
though uncited — QM-2-4). The trio's factual grounding is well above the bar the
M-WIFI-DIAG panel had to enforce; the findings below are mostly about the residue.

---

## Doc 1 — M-WR-PLEDIT-SCROLL (TASK-277)

**What it gets right (recorded per the repeated-lesson brief):** the injection-routing
fix (§Serial debug #1) is the correct, in-design application of LL-023/LL-061/BP-004 —
the touch-injection path is updated in the same design that adds the new touch consumer,
not backfilled. The dbg surface (`wrScroll`, `wrSpeedK`, `cmdTick` routing) is
designed-in per BP-024/LL-060, not retrofit. Option A's promotion trigger ("third
consumer") is a named trigger, not vague prose. Rejecting Option B on the
`winampDisplay` state-collision is consistent with the LL-035 shared-state lesson.
`./run/check` in exit criteria satisfies BP-008 for the constants-header move.

### QM-1-1 (major) — Goal 4 self-contradicts once the harness reroute is in scope

Goal 4: "Zero change to the DUT-validated Spotify gesture path (T155–T161 must stay
green **without re-validation being load-bearing**)." But §Serial debug #1 reroutes
`drainInjectionQueue` — the substrate under every T155–T161 drag test — and the exit
criteria correctly demand a T155–T161 re-run. That re-run *is* load-bearing precisely
because of the reroute (production physical dispatch already goes through
`g_apps[]->handleInput`, `main.cpp:1888-1891`; only the injected path changes — the
claim "Spotify behaviour identical" is code-verified via `main.cpp:254-262`, but
"verified identical" is established by the re-run, not by inspection). Same evidence
bar as M-WIFI-DIAG QM-4: don't state as already-true what the exit gate exists to prove.
**Resolution:** amend Goal 4 to "zero change to the Spotify *gesture logic*; the
injection-path reroute makes the T155–T161 re-run a mandatory gate, not a formality."
(VE-1-1/1-6 own the mechanics of the reroute itself.)

### QM-1-2 (minor) — lean diverges from the roadmap framing; update at acceptance or drift

Roadmap M-WR-PLEDIT-SCROLL: "ideally by extracting/reusing the existing gesture machine
rather than duplicating it." The lean (Option C) is deliberate bounded duplication —
well argued, and design docs exist to overturn framings — but LL-045 (+ its recurrence
note) is exactly this drift class: doc and lean diverge, nobody reconciles.
**Resolution:** when the lean is accepted, PM/Architect update the roadmap blurb (and
TASK-277 body, which repeats "extract vs route") in the same commit.

### QM-1-3 (minor) — auto-follow bullet ships its own rejected reasoning (BP-028 hazard)

The §Gesture-spec auto-follow bullet contains the abandoned line of thought inline:
"guard … is unnecessary since `_play` from auto-skip can't coincide with a finger down
on rows... it can (auto-skip is tick-driven)." The final rule (cancel gesture, zero
accumulators, before the clamp) is correct, but design prose gets transcribed into
code (BP-028); a reader skimming to the first "is unnecessary" implements the wrong half.
**Resolution:** rewrite the bullet as the single final rule; move the reasoning to a
parenthetical or drop it.

### QM-1-4 (minor) — dbg surface needs VE sign-off before implementation (BP-024 ownership)

The doc *proposes* the `wrScroll`/`wrSpeedK`/`tick` surface (good), but BP-024 puts
authorship/sign-off of the debug-variable spec with VE before implementation begins —
and the VE review is already requesting changes to it (VE-1-4/1-5).
**Resolution:** add an explicit "VE signs off the dbg surface (BP-024)" gate to the
exit criteria or the implementation-task template.

### QM-1-5 (minor) — inherited VE-C5 defect parked as prose, no owner/trigger

OQ4 inherits the at-limit release defect (M-LIST-v4 §Known limitation VE-C5) into the
copy with "Default: accept, document." BP-003/BP-035: a known defect deferred as prose
has no owner and no trigger. Two sites will now carry it and only one is documented.
**Resolution:** on acceptance, record the second site in the M-LIST-v4 VE-C5 known-
limitation note (or the WebRadio regression-suite doc) and name that artefact in OQ4 —
or file the fix-in-both task and reference it.

**Verdict: approve-with-changes.**

---

## Doc 2 — M-WR-AUDIO-TASK (TASK-278)

**What it gets right:** E0 baseline-before-any-change with targets set *after* the
baseline run is textbook measurement-first discipline (the LL-088/LL-089 lesson family,
BP-040's gate-consistency clause). Phase 2 is explicitly deferred behind a named
measurement (`wr.connect`) rather than designed in full — the exact corrective LL-089
asked for ("design to the depth the next gate needs"). Core placement is argued against
the TWDT facts, which check out in-tree. Option (b) is kept as a *measured fallback with
a concrete trigger* — BP-040-conformant. BP-042 (frozen fork) cited correctly. E3
re-runs the freshly validated ADR-045/TASK-275 gate instead of assuming it survives.

### QM-2-1 (major) — teardown invariant is prose without an enforcing mechanism (LL-085 class)

The lifecycle bullet states the invariant ("the Audio object is never destroyed … while
the pump could be inside an Audio method") but the described sequence — stop flag →
pump acks (semaphore) at top-of-cycle → `vTaskDelete` from `suspend()` — leaves a window
as written: after giving the ack, the prio-2 pump keeps running until it blocks, and
nothing in the prose forbids it re-entering the mutex/`loop()` before the delete lands.
LL-085's core lesson is that a design constraint without a mechanism defaults to
violated; BP-028 says this snippet-shaped prose will be transcribed verbatim.
**Resolution:** specify the mechanism: after acking, the pump either self-deletes
(`vTaskDelete(NULL)` as its last statement) or parks in a terminal block it never
leaves; `suspend()` proceeds only after the ack semaphore — state it as the enforced
sequence, not an invariant sentence.

### QM-2-2 (major) — cross-doc E0/baseline ordering unstated in both docs and the roadmap

This doc's E0 (STOPPED vs PLAYING `loopMax` on current master) and M-TASKBAR-FEEDBACK's
baseline matrix (which includes "WebRadio PLAYING — the loop-starvation case" and calls
it "the M-WR-AUDIO-TASK cross-reference number") measure the same window and both must
run **before either implementation lands** — if TASK-278 lands first, doc 3's starved-
state "before" row is unmeasurable forever. Neither doc, nor the three roadmap entries,
states the ordering. Concurs with VE-2-1/VE-3-2 (which own the statistical/windowing
mechanics); the QM angle is consistency: three artefacts + roadmap must agree on what
gates what. (Doc 1 is genuinely order-independent via dt-integration and says so — the
gap is only between docs 2 and 3.)
**Resolution:** one combined baseline DUT session on current master, named in both docs'
exit criteria and in the roadmap milestone entries ("Deps: shared E0 baseline session"),
before either TASK-278 or TASK-279 implementation merges.

### QM-2-3 (minor) — "dataTask is idle" sits in the verified-facts block but is an inference

"**Facts that bound the design** (verified in tree)" includes "dataTask is idle after
the station fetch." That is an inference from suspend semantics (suspended apps don't
enqueue fetches), not an in-tree fact, and it is load-bearing for the core-placement
argument. M-WIFI-DIAG QM-4/5 bar: label inference vs verified.
**Resolution:** move it out of the facts block or mark "(inference — suspended apps
enqueue nothing; E0/E1 confirm)".

### QM-2-4 (minor) — two uncited claims inside the otherwise-cited facts

"v2.3.0 has no built-in audio task (upstream added one in 3.x)" and "ESP32-audioI2S's
own guidance warns about [WiFi starving decode]" carry no source. The first is true —
QM verified no `xTaskCreate` in `app/lib/ESP32-audioI2S/src/` — a one-line grep citation
makes it BP-001-grade; the second needs the upstream doc/README pointer or softer wording.
**Resolution:** add the grep as the citation for the first; cite or soften the second.

### QM-2-5 (minor) — the cited ICY evidence (`webRadioApp.h:80`) contains a stale comment

The comment reads "Written from ESP32-audioI2S callback (Core 0/audio task)" — false
today (the callback fires on loopTask/core 1) and only becomes true-ish after this
design. Citing it as "written for exactly this" is fine; leaving the wrong comment is
how the next LL-045 starts.
**Resolution:** note in the implementation scope that the comment gets corrected to the
actual producer task.

### QM-2-6 (minor) — header missing the Deps line its siblings carry

Docs 1 and 3 carry `> Deps:` headers matching their roadmap entries; doc 2 does not,
though its roadmap entry names M-WEBRADIO + M-WEBRADIO-NOPSRAM (the arena ceiling is
load-bearing in §Goals 4).
**Resolution:** add `> Deps: M-WEBRADIO (done), M-WEBRADIO-NOPSRAM (A-lite arena)`.

*(Perf-path budget overflow — proposed `wr.pump` + `wr.connect` + doc 3's `shell.switch`
against `MAX_PATHS=8` with silent drop — is VE-2-3; QM concurs it is major and notes
`perf.h:51`'s own comment promises the count stays "conservatively above" the paths.)*

**Verdict: approve-with-changes.**

---

## Doc 3 — M-TASKBAR-FEEDBACK (TASK-279)

**What it gets right:** the cooldown correction is the panel bar working as intended —
the original task/roadmap claim ("cooldowns silently drop taps") was checked against
dispatch order, found false, and the correction was propagated to *both* the roadmap
entry and TASK-279's body in the same batch (the anti-LL-045 move). The golden-hash
claim is accurate to ADR-046's actual wording (firmware-only `#define` in `taskbar.h`,
NOT generated `shell_layout.h` — verified) and `gen/golden.sha256` is untouched.
L-b is instrument-first with optimisation explicitly gated on numbers (LL-089/BP-001
discipline: "blind restructuring … is how regressions happen" is the right posture).
ADR-035's spinner/animation rejection is respected. L-a is derived as a hard constraint
of the shared zone, not a preference.

### QM-3-1 (major) — F-b paints "the **target** slot" — but the target app may have no slot (LL-085)

At tap-commit the release path runs `resolvePlayerSlot()` (`main.cpp:1916`), whose
output can be **WebRadio** — deliberately excluded from the taskbar
(`TASKBAR_APP_COUNT = (int)AppId::WebRadio`, LL-085/TASK-242). If "the target slot" is
implemented as a reverse app→slot lookup, it is undefined for WebRadio — the exact
no-slot-for-WebRadio edge that produced the LL-085 null-icon crash. The intended
behaviour (paint the *tapped* slot) is almost certainly what F-b means, but the doc
says "target".
**Resolution:** specify the amber bar paints the **tapped slot index** (resolved from
release y + `tbScrollOffset()`), never derived from the post-`resolvePlayerSlot` AppId;
add the WebRadio-player-mode case to the T-TBFB-03 test notes.

### QM-3-2 (major) — pressed-slot blit leaves the slot→app/icon mapping implicit (LL-085: prose vs mechanism)

F-a says `slot = y / TASKBAR_SLOT_H` … "re-blit of the icon" and relies on "a
parameterised single-slot variant of the `renderTaskbar()` loop body" to imply the rest.
The load-bearing part is unstated: the app/icon index must be
`(tbScrollOffset() + slot) % TASKBAR_APP_COUNT` — the exact mapping `renderTaskbar` and
`cmdTap` (`main.cpp:2388-2389`) use — and the new blit must sit behind the TASK-242
null-guard/`static_assert` defenses. LL-085's lesson is that an implied constraint on
the taskbar's index math is precisely what rotted into a crash; one sentence closes it.
**Resolution:** state the index formula and that the pressed-slot painter reuses (not
reimplements) the guarded `renderTaskbar` slot body.

### QM-3-3 (minor) — cost figures mix labelled and unlabelled estimates

The canvas-wipe saving is labelled "~10-20 ms estimated"; the press-blit cost
("single-digit ms of SPI") and F-b's "≈ zero" are asserted unlabelled in a doc whose
own thesis is "nothing in the switch path is measured today." BP-001/M-WIFI-DIAG QM-4
bar: label estimates as estimates and point them at the baseline matrix that will
replace them.
**Resolution:** tag both as "estimate — superseded by the §Measurement-plan tables".

### QM-3-4 (minor) — OQ4 side-finding must become a filed task at acceptance, not float (BP-003/BP-035)

The `cmdTap`-skips-`resolvePlayerSlot` divergence (verified real, `main.cpp:2390` vs
`:1916`) is dispositioned as "flag to PM/VE for a small follow-up task." That is the
prose-with-no-owner pattern BP-003/BP-035 exist to kill. Concurs with VE-3-6.
**Resolution:** PM files the task when dispositioning this review; the doc's OQ4 is
updated to reference the TASK id.

*(The perf slot-count arithmetic error in L-d is VE-3-5 / cross-doc VE-2-3; QM concurs —
QM's independent count also gets 5 production paths + `screenlog.tick`, not 6 + 7.)*

**Verdict: approve-with-changes.**

---

## Verdict summary

| Doc | Task | Verdict | Blockers | Majors |
|---|---|---|---|---|
| M-WR-PLEDIT-SCROLL | TASK-277 | **approve-with-changes** | — | QM-1-1 |
| M-WR-AUDIO-TASK | TASK-278 | **approve-with-changes** | — | QM-2-1, QM-2-2 |
| M-TASKBAR-FEEDBACK | TASK-279 | **approve-with-changes** | — | QM-3-1, QM-3-2 |

No blockers from the QM lane (VE-1-1 is the panel's sole blocker). The trio is notably
strong on the disciplines past retrospectives paid for: measurement-before-optimisation,
deferred-with-trigger phasing, injection-path co-design, and honest correction of the
original task framing. The majors cluster where prose stands in for mechanism
(QM-2-1, QM-3-2 — the LL-085 lesson) and where cross-doc coordination has no owner
(QM-2-2).

---

## QM housekeeping (QM-owned files; not Architect dispositions)

1. **Duplicate LL ids — LL-069 *and* LL-070 each exist twice** in
   `docs/quality/lessons_learned.md`: LL-069 at line 409 (2026-06-13, "Tasks not filed
   before milestone implementation") and line 1724 (2026-06-28, "Sensor-blind gate
   criteria"); LL-070 at line 422 (2026-06-13, "Runtime exercise caught a crash") and
   line 1733 (2026-06-28, "Fresh agent handover prompts"). The M-WIFI-DIAG panel's QM-8
   flagged the LL-069 duplicate as "handled outside this doc" — it was never handled,
   and the LL-070 duplicate is a new find. **BP-043 cites "Adopted from: LL-070"**,
   which now resolves ambiguously. Action (QM): renumber the 2026-06-28 pair to the
   next free ids (LL-094/LL-095 — LL-093 is the current max), update BP-043's citation
   and the memory-index/M-WIFI-DIAG references, record in audit_log.
2. **audit_log currency**: last entry is 2026-06-27; neither the 2026-07-02 M-WIFI-DIAG
   3-agent panel (whose dispositions are recorded only inside the design doc §8) nor
   this touch-UX panel has an audit_log entry, breaking the house precedent of logging
   panel outcomes ("quality win recorded in audit_log" pattern, 2026-06-26/27). Action
   (QM): one entry covering both panels once the Architect dispositions land.
3. **Minor**: the M-WIFI-DIAG QM-8 disposition promised out-of-doc handling with no
   owner artefact — itself an instance of the BP-003 prose-with-no-owner pattern QM
   keeps citing. Item 1 above is the corrective; noting it here for the retrospective.
