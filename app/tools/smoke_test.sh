#!/usr/bin/env bash
# Smoke-test: verify tool scripts resolve paths without FileNotFoundError.
# Does not bake anything — just imports and --help dry-runs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"

#: repo root — app/tools/.. /.. — for the `run/` scripts this file gates.
PROJ_ROOT_SMOKE="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 1. Import check — catches missing-file errors at module load
# TASK-481: bake_skin.py lives in bake/ now; coords.py stays flat.
"$PYTHON" -c "import sys; sys.path.insert(0, 'bake'); import coords; import bake_skin" 2>&1 | grep -q "FileNotFoundError" && {
    echo "FAIL: FileNotFoundError during import" >&2; exit 1
}

# 2. bake_wave.sh --help dry-run — catches stale -o path in shell script
output=$(bash bake/bake_wave.sh --help 2>&1 || true)
if echo "$output" | grep -q "No such file or directory"; then
    echo "FAIL: bake_wave.sh --help reported missing file" >&2
    echo "$output" >&2
    exit 1
fi

# 3. check-docs harness — T_DOC_01..17, minus the retired 08 (TASK-475).
# Runs here rather than as its own check_build.sh gate so the documentation
# gate itself (gate 12) stays one slot: gate 9 covers the CHECKER, gate 12
# runs it against the live corpus. Host-side only, no DUT, ~2 s.
# TASK-481: check_*.py + test_check_*.py live in gate/ now.
if ! "$PYTHON" gate/test_check_docs.py; then
    echo "FAIL: test_check_docs.py (T_DOC_01..17) FAILED" >&2
    exit 1
fi

# 4. player-mode binding gate — M-TESTBASE §8.4 (TASK-512).
# Asserts the resolvePlayerTap -> playerCycle -> playerBind -> T_PMT_00 chain is
# intact. TASK-413 added a dispatch path and left the harness on the old surface
# with every gate green; this is the check that would have caught it.
if ! "$PYTHON" gate/check_player_binding.py; then
    echo "FAIL: check_player_binding.py (M-TESTBASE §8.4) FAILED" >&2
    exit 1
fi

# 4b. suite/serialdbg/ cross-file Name-reference gate (TASK-480/TASK-545).
# A pure code move can't introduce a logic bug but can absolutely drop an
# import — caught 3 times live during TASK-480's split (_drain_data_pipeline,
# _tap_and_wait_log, _tb_precondition), each time only after a DUT run threw
# a NameError hours in. This is the same AST walk that caught them, made
# permanent so the next suite/serialdbg/ change gets the check for free.
if ! "$PYTHON" gate/check_suite_serialdbg_names.py; then
    echo "FAIL: check_suite_serialdbg_names.py (TASK-480/TASK-545) FAILED" >&2
    exit 1
fi

# 4b2. the (cls, scope, effect) test record — TASK-570.
# The record is SEEDED from the family module and id prefix and OVERRIDDEN by
# hand only where the seed is wrong (M-TESTARCH §13.3). Every invariant of that
# split fails silently: an id that resolves to no scope is simply never selected
# by --scope, an override with no reason cannot be told from a typo, and a
# case-only enum collision (`Spotify` vs `spotify`) selects the wrong set with no
# error printed. The negative suite runs first — a gate nobody has seen fail is
# not a gate (BP-068).
if ! "$PYTHON" gate/test_check_test_meta.py; then
    echo "FAIL: test_check_test_meta.py (TASK-570 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_test_meta.py; then
    echo "FAIL: check_test_meta.py (TASK-570 record gate) FAILED" >&2
    exit 1
fi

# 4c. serial-failure classifier — TASK-556.
# runner.py used to label every serial.SerialException `port-busy` and name the
# tmux monitor; a device that VANISHED mid-open (CH340 re-enumeration) got the
# same label as genuine contention, and that wrong label misdirected the same
# investigation more than once on 2026-08-31. Pure logic, no DUT, sub-second.
if ! "$PYTHON" test_serial_classify.py; then
    echo "FAIL: test_serial_classify.py (TASK-556 classifier) FAILED" >&2
    exit 1
fi

# 4d. boot-observation gate — TASK-560.
# _wait_for_ready() used to return silently when no boot banner appeared within
# 2 s, skipping every readiness gate below it with no trace. The bannerless case
# cannot be produced on hardware on demand, so the branch is stubbed here.
if ! "$PYTHON" test_boot_gate.py; then
    echo "FAIL: test_boot_gate.py (TASK-560 boot gate) FAILED" >&2
    exit 1
fi

# 4e. passive triage, mode P — TASK-571.
# Every FAIL now carries the session health verdict, last-phase, gen tag and the
# id's (cls, scope). That record is a STRING run/player-gate parses with a
# line-oriented sed, and TASK-573 was a live gate defect where exactly such a
# status string silently failed to parse — so the format is pinned here rather
# than discovered on a gate run. Also pins that modes D and I stay unbuilt.
if ! "$PYTHON" test_triage_context.py; then
    echo "FAIL: test_triage_context.py (TASK-571 mode P) FAILED" >&2
    exit 1
fi

# 4f. EC-G8, the inversion test — TASK-566.
# The gating property itself: a class-N failure must never be reportable as a
# class-N+1 failure. Every other exit criterion asserts the machinery EXISTS;
# this is the only one that asserts what the machinery is FOR, parameterised
# over the ladder against a stubbed DUT. It also asserts the INERT default
# (--class-order off changes nothing) and that every 0->1-edge candidate is
# adjudicated, which @VE §18.6(c) makes a precondition of the order switch.
if ! "$PYTHON" test_class_order.py; then
    echo "FAIL: test_class_order.py (TASK-566 EC-G8 inversion test) FAILED" >&2
    exit 1
fi

# 4f0. TASK-635 (R14) — the armed-state boundary check's inversion/negative
# suite. `lib/armed.py`'s decision logic (parse `get armed`, FAIL the id that
# leaked an injector while keeping its original record, tolerate `None` with
# a once-per-run notice, attribute a session-start leak to nobody) plus
# `_gate.run_suite`'s `boundary`/`boundary_start` hooks and their inert
# default, all stubbed — no DUT, no port, no build.
if ! "$PYTHON" lib/test_armed.py; then
    echo "FAIL: lib/test_armed.py (TASK-635 R14 armed-state boundary check) FAILED" >&2
    exit 1
fi

# 4f0a. `--shuffle-family`'s pure core — TASK-636 / R20-R21. Reproducibility
# from a seed, family-block preservation/contiguity, an id with no (or
# malformed) meta degrading to its own singleton family rather than crashing
# or merging, and per-family seeding (one family's permutation must not depend
# on which other families are also selected). No DUT, no port, <0.1 s.
if ! "$PYTHON" lib/test_shuffle.py; then
    echo "FAIL: lib/test_shuffle.py (TASK-636 per-family shuffle) FAILED" >&2
    exit 1
fi

# 4f1. the run artifact — TASK-608 / ADR-066 D1 / IFC-008 / R29+R30.
# The artifact is now the SOLE machine interface to a run, so the failure that
# matters is a consumer reading something and being WRONG about it. The stale
# arms are the point: a gate scored against a PREVIOUS run's artifact is silent
# and looks like a result, where a missing one is loud. Also pins that the five
# unrelated print_results callers' rc arithmetic is untouched, that the summary
# LINE keeps its pre-TASK-627 shape, and — mechanically, over the tree — that
# R29's count of summary-text parsers stays at zero. Host-only, no DUT, ~0.3 s.
# Runs BEFORE the comparator selftest below, which now reads artifacts it makes.
# Extended by TASK-636 (T_ART_80-86): the order_dependence() cross-run
# comparison (R20/R21) — same file, per the project's "extend, don't fork"
# rule, since it is another pure consumer of the same artifact shape.
if ! "$PYTHON" test_run_artifact.py; then
    echo "FAIL: test_run_artifact.py (TASK-608 run artifact) FAILED" >&2
    exit 1
fi

# 4f1a. the M-DATATASK-PROGRESS oracle's negatives — TASK-657 / BP-068.
# T_DTP_01/02 + T_WX_06/T_CX_06 are the first ids that ASSERT the four progress
# atoms, and their adjudicator is a pure function, so it can be broken on the
# host. Six deliberate mutations were run against it; the domain arm escaped the
# first version of this suite (the fixture computed the answer it was checking),
# which is why N2b drives the real observer. Host-only, no DUT, ~0.1 s.
if ! "$PYTHON" test_progress_atoms.py; then
    echo "FAIL: test_progress_atoms.py (TASK-657 progress-atom oracle) FAILED" >&2
    exit 1
fi

# 4f2. the comparator's own negative tests — TASK-573, extended by TASK-624.
# `run/player-gate --selftest` has existed since TASK-573 and was gated by
# NOTHING, which is how a gate acquires an inversion nobody sees: the FLAKY-PASS
# defect shipped for years and was found by a run, not by a check. TASK-624 adds
# the UNMET arms (ADR-066 D5 / R38) — "an UNMET cell reads green" is the same
# defect one token later — so the selftest is wired in here rather than left as
# a command someone remembers to type. Host-only, no DUT, no flash, ~0.4 s.
if ! "$PROJ_ROOT_SMOKE/run/player-gate" --selftest; then
    echo "FAIL: run/player-gate --selftest (TASK-573/624 comparator) FAILED" >&2
    exit 1
fi

# 4g. import safety — TASK-609 / M-HARNESS2 R48.
# Six top-level DUT scripts ran their whole suite at module level, so `import
# prloc_smoke` opened the port, asserted DTR and RESET the board; one such
# import did exactly that during the review that found them and cost a TASK-557
# observation window. The negative suite runs first and includes the proof that
# the CHECKER cannot open the real port while checking that nothing else does —
# a checker that opened a port to prove nothing opens a port would have
# reproduced the defect one level up. ~3 s, one guarded child, no DUT.
if ! "$PYTHON" gate/test_check_import_safety.py; then
    echo "FAIL: test_check_import_safety.py (TASK-609 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_import_safety.py; then
    echo "FAIL: check_import_safety.py (TASK-609 import-time board access) FAILED" >&2
    exit 1
fi

# 4g-bis. the readback instrument still WORKS — TASK-589 / WP-A A-1.
# `screendump.py` imported a constant TASK-555 had deleted, so `run/screendump`
# and its three dependants raised ImportError before opening the port, for three
# months, while CLAUDE.md documented the tool as working and ADR-064 made this
# path the project's render-verification mechanism. The gate above ran over the
# file the whole time and filed it as "could not be imported for unrelated
# reasons (reported, not failed)" — correct for ITS subject, useless for this
# one. So this check is blocking on the import AND executes the decode: a
# firmware-accurate transcript through the real band parser, an interleaved
# heartbeat, a corrupted band the retry must heal, the RGB565 conversion against
# ground truth, and TASK-340's byte-swap transform pinned in both directions. The
# negative suite runs first (BP-068) and its central arm is the A-1 defect
# verbatim. No DUT, no port, ~3 s.
if ! "$PYTHON" gate/test_check_screendump_instrument.py; then
    echo "FAIL: test_check_screendump_instrument.py (TASK-589 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_screendump_instrument.py; then
    echo "FAIL: check_screendump_instrument.py (TASK-589 A-1 readback instrument) FAILED" >&2
    exit 1
fi

# 4h. the generated `get`-key list — TASK-600 / M-HARNESS2 R7.
# gen_get_keys.py claimed two sources and delivered one: its glob was `*.h`
# after every dbgGet() body had moved to a `.cpp`, and its definition regex did
# not match an out-of-line `bool CryptoApp::dbgGet(...)` even when pointed at
# the right file. 43 keys enumerated against 111 that exist, so run/task488's
# "every key resolves" check covered ~39 % of the surface and reported clean.
# The gate compares the generator's VISITED bodies against a deliberately
# dumber full-tree scan, so it can only ever accuse the generator.
if ! "$PYTHON" gate/test_check_get_keys.py; then
    echo "FAIL: test_check_get_keys.py (TASK-600 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_get_keys.py; then
    echo "FAIL: check_get_keys.py (TASK-600 get-key enumeration) FAILED" >&2
    exit 1
fi
# 4h+1. every console `set` key is a declared armed injector or says why not
# (TASK-635 / M-HARNESS2 R14 design §2.5).
if ! "$PYTHON" gate/test_check_armed_injectors.py; then
    echo "FAIL: test_check_armed_injectors.py (TASK-635 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_armed_injectors.py; then
    echo "FAIL: check_armed_injectors.py (TASK-635 armed-injector completeness) FAILED" >&2
    exit 1
fi

# 4i. flake declarations vs gating classes, AND vs their own call sites —
# TASK-623 / M-HARNESS2 R37 (F1-F5), extended TASK-595 / C-7 (F6-F8).
# A RIG/HEALTH/CORE id that is also declared flaky gates nothing: its retry
# resolves FLAKY-PASS, which is neither a PASS nor a FAIL, so it can never set
# the blocker its class exists to set (F1). Symmetrically (TASK-595): a
# flaky.yaml entry whose body never calls flake() does nothing (F6, an AST
# scan for real flake() call sites under suite/serialdbg/), and a real
# flake() call site for an UNDECLARED id gets silently converted to
# 'FAIL: UNDECLARED flake' at runtime — a bookkeeping message standing in for
# the real symptom (F7). F8 enforces flaky.yaml's own rule 3 (an entry past
# its review_by is a FAIL) at review time rather than only on a DUT run. Lands
# BLOCKING with a dated, owned, shrink-only ledger
# (docs/verification/flake_class_exceptions.md: one F7 row, T084 — CORE,
# genuinely undecidable host-only, see the ledger's own retirement section)
# rather than advisory — C3 is this repo's standing demonstration of what
# advisory does to a finding count.
if ! "$PYTHON" gate/test_check_flake_class.py; then
    echo "FAIL: test_check_flake_class.py (TASK-623/595 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_flake_class.py; then
    echo "FAIL: check_flake_class.py (TASK-623/595 gating-class + call-site flake) FAILED" >&2
    exit 1
fi

# 4j. defaulted device reads — TASK-596/585 / M-HARNESS2 R18.
# A `.get("val", 0)` on a device reply gives a FAILED read the same type as a
# real one, so the comparison after it cannot tell them apart. WP-G found what
# that costs: `_stock_ok_count` returned -1, `_wait_chart_complete(-1)` was
# satisfied by its own first poll, and the Stock family's central fetch oracle
# was an unconditional pass across nine ids. R18 is a RATCHET, so this lands
# blocking against a dated, per-file, shrink-only ledger
# (docs/verification/defaulted_reads_ratchet.md) that is enforced in BOTH
# directions — a cap above the real count is itself a failure. The negative
# suite runs first and includes the G-2 regression proper: it FAILS on the
# pre-TASK-585 helper, which is the only reason to believe it means anything.
if ! "$PYTHON" gate/test_check_defaulted_reads.py; then
    echo "FAIL: test_check_defaulted_reads.py (TASK-596 checker+accessor negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_defaulted_reads.py; then
    echo "FAIL: check_defaulted_reads.py (TASK-596 R18 defaulted-read ratchet) FAILED" >&2
    exit 1
fi

# 4k. restore through the manager — TASK-602 / M-HARNESS2 R17.
# R17 asks for a mechanism that runs on EVERY exit path, and asks the check to
# assert the mechanism is USED — because a `finally:` that restores the wrong
# variable, restores from a defaulted read, restores to a guessed constant, or
# restores with an unacknowledged `cmd` all match a static "a restore exists"
# grep and all still leak. All four are fixtures in the negative suite, which
# runs first and is blocking; the checker credits exactly one shape,
# `with dut.saved(...)` / `with dut.injected(...)`. R17 is a RATCHET, so the
# gate is blocking against a dated per-module shrink-only ledger
# (docs/verification/unrestored_mutations_ratchet.md, 197 rows' worth today),
# enforced in both directions.
if ! "$PYTHON" gate/test_check_restore_manager.py; then
    echo "FAIL: test_check_restore_manager.py (TASK-602 manager+checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_restore_manager.py; then
    echo "FAIL: check_restore_manager.py (TASK-602 R17 restore-manager ratchet) FAILED" >&2
    exit 1
fi

# 4l. plan integrity — TASK-611 / M-HARNESS2 R46, "ids exist once".
# C6 asks whether every executable id HAS a doc entry; it is id-keyed, so it
# cannot see an id with two bodies, an id with two plan entries, or an entry that
# describes a different test than the body it binds. Four of the five checks read
# ZERO today (A-15's two duplicate bodies were resolved by TASK-603, and the six
# duplicate declarations were fixed in TASK-611 by retitling the `### T176 fix`
# work items) — which makes the negative suite load-bearing rather than
# decorative, since nothing else separates "no violations" from "blind". The
# remaining six are on a dated shrink-only ledger because fixing them means
# RENAMING a live id.
if ! "$PYTHON" gate/test_check_plan_integrity.py; then
    echo "FAIL: test_check_plan_integrity.py (TASK-611 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_plan_integrity.py; then
    echo "FAIL: check_plan_integrity.py (TASK-611 R46 plan integrity) FAILED" >&2
    exit 1
fi

# 4m. a gating class may not need the outside world — TASK-626 / R36.
# A CORE id whose precondition is a 45 s live HTTPS fetch runs at index 14 under
# TASK-566's class order and NOT-RUNs 167 FEATURE ids on a network outage. The
# checker walks each gating id's CALL CLOSURE, not its body: every one of the
# eight ids it finds reaches its dependence through a helper, which is how seven
# of them stayed unwritten-down for a year. It also reads B-2's host-file-layout
# shape, which is at ZERO since T133's demotion and is NOT exemptable — the
# ledger parser refuses a row of that kind. The other three kinds sit on a dated
# shrink-only ledger because demote-or-inject changes what the suite blocks on
# and is the human's ruling (TASK-617), the same way TASK-591's 20 demotions
# were. THE GATE READING ZERO IS AN EXIT CRITERION OF TASK-617; it reads 8.
if ! "$PYTHON" gate/test_check_gating_offline.py; then
    echo "FAIL: test_check_gating_offline.py (TASK-626 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_gating_offline.py; then
    echo "FAIL: check_gating_offline.py (TASK-626 R36 offline-gating) FAILED" >&2
    exit 1
fi

# 4a-ter. TASK-705 — every primitive operation in _meta.OPS (opened from
# TASK-697's coverage inventory) has an id declaring it ALONE, or a dated row on
# docs/verification/primitive_coverage_exceptions.md. A composite id covering
# several ops does not excuse a missing primitive for any one of them — that is
# exactly the gap TASK-697's own investigation found. Blocking at zero except the
# one ledgered op (spotify_token_refresh_fail — cmdSet.cpp's certbreak table
# excludes spotifyTask, owner TASK-675).
if ! "$PYTHON" gate/test_check_primitive_coverage.py; then
    echo "FAIL: test_check_primitive_coverage.py (TASK-705 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_primitive_coverage.py; then
    echo "FAIL: check_primitive_coverage.py (TASK-705 primitive coverage) FAILED" >&2
    exit 1
fi

# 4a-bis. ADR-067/R51 — no DUT entry point flashes, and none restores (TASK-633).
# Blocking at ZERO with NO ledger: there is nothing to shrink from, and a single
# re-introduced restore re-creates the exact obstruction ADR-067 removed — a
# script that cannot be run at all on a board pinned to a debug build (TASK-557).
# The negative suite runs first and is blocking: its central arm re-introduces
# the restore (bare and inside an EXIT trap) and requires the gate to catch both,
# and its second half drives the refusal decision against a FAKED Dut, proving
# the condition -> exit-code mapping on a host with no board attached.
if ! "$PYTHON" gate/test_check_entrypoint_lifecycle.py; then
    echo "FAIL: test_check_entrypoint_lifecycle.py (TASK-633 checker + refusal negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_entrypoint_lifecycle.py; then
    echo "FAIL: check_entrypoint_lifecycle.py (TASK-633 ADR-067 entry-point lifecycle) FAILED" >&2
    exit 1
fi

# 4b. R34 — every registered id can actually go red (TASK-603).
# Blocking on a dated shrink-only ledger. The negative suite runs first and is
# blocking for the same reason as the one above: three of its arms are CONTROLS
# that must NOT flag, and its mutation arm rewrites a live id into each of the
# four defective shapes and requires the count to rise by exactly one. Shape 4 —
# the sole fail() behind an error-swallowing `-> bool` helper — is the shape
# check_defaulted_reads.py structurally cannot see, and reads 0 today; the
# mutation arm is the only evidence that clause works.
if ! "$PYTHON" gate/test_check_no_reachable_fail.py; then
    echo "FAIL: test_check_no_reachable_fail.py (TASK-603 R34 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_no_reachable_fail.py; then
    echo "FAIL: check_no_reachable_fail.py (TASK-603 R34 no-reachable-fail gate) FAILED" >&2
    exit 1
fi

# TASK-671: R34 at RUNTIME. The static gate above proves a fail() is reachable
# in the source; this one runs each recorded body against its poisoned
# transcript and asks whether it ever records an assertion FAIL. Its negative
# suite records synthetic bodies through the real recorder and includes the
# mutation arm (poisons disabled -> RED must disappear).
if ! "$PYTHON" gate/test_check_can_go_red.py; then
    echo "FAIL: test_check_can_go_red.py (TASK-671 runtime R34 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_can_go_red.py; then
    echo "FAIL: check_can_go_red.py (TASK-671 R34 can-go-red gate) FAILED" >&2
    exit 1
fi

# 5. app conformance matrix, rows A5/A6 — M-TESTARCH §2.3 (TASK-483).
# The CHECKER's own negative suite (BP-068) is blocking: a conformance gate that
# cannot be shown to fail is not a gate. The MATRIX is blocking too since
# 2026-09-05: it landed warn-only on one unexcepted A6 cell, with a written
# promotion criterion, and re-measurement found the criterion met and unnoticed
# — 0 unexcepted findings on both rows, 5 dated ledger rows, stale rows failing.
# See STRICT_DEFAULT in check_app_conformance.py.
if ! "$PYTHON" gate/test_check_app_conformance.py; then
    echo "FAIL: test_check_app_conformance.py (A5/A6 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_app_conformance.py; then
    echo "FAIL: check_app_conformance.py (A5/A6 conformance matrix) FAILED" >&2
    exit 1
fi

# ── TASK-628/631 — the replay engine's negative suite (R10's own verification
# clause, BP-068). Blocking at zero from the day it lands: this is the mechanism
# that decides whether a mutation result may be counted, so a broken one
# manufactures the acceptance number the programme exists to disbelieve. 40 arms
# over the real T_MA_03 body; no DUT, no port, ~0.25 s.
if ! "$PYTHON" lib/test_replay.py; then
    echo "FAIL: lib/test_replay.py (TASK-628/631 replay-engine negative suite) FAILED" >&2
    exit 1
fi

# ── TASK-677 — rigwatch's negative suite (PROP-011 §5 P0, BP-068). Kernel-line
# parsing against real captured journalctl text, port-filter correctness (the
# fingerprint-reader-on-1-4 false-positive case), R/U/W metric computation and
# timeline rendering. No DUT, no journalctl subprocess, no network, ~0.01 s.
if ! "$PYTHON" lib/test_rigwatch.py; then
    echo "FAIL: lib/test_rigwatch.py (TASK-677 rigwatch negative suite) FAILED" >&2
    exit 1
fi

# ── TASK-557/677 — the serialburst host checker's negative suite (PROP-011 §2
# UART row: "the host checker was never committed" — it is now, and gated).
# Sequence-gap, checksum-corruption, duplicate and truncated-stream detection
# against a generated fixture matching cmdSerialBurst's exact wire format. No
# DUT, ~0.01 s.
if ! "$PYTHON" probe/test_burst_check.py; then
    echo "FAIL: probe/test_burst_check.py (TASK-557/677 burst_check negative suite) FAILED" >&2
    exit 1
fi

# ── TASK-677/678 H-1 — the PROP-011 experiment drivers' negative suites.
# Every driver's parsing/decision logic is pure and fixture-tested; the
# refusal-based drivers (rig_sweep.py's board-reset guard, rig_ladder.py's
# F-4-not-landed guard) are exercised as subprocesses so the CLI's actual
# exit code and message are pinned, not just the underlying function. No
# DUT, no tmux, no pio — import safety (gate/check_import_safety.py) holds:
# nothing in probe/rig_*.py or lib/monitor_tmux.py touches tmux/serial at
# import, only from inside main()/the *_cell()/run_*() functions it calls.
if ! "$PYTHON" probe/test_rig_p1c.py; then
    echo "FAIL: probe/test_rig_p1c.py (TASK-677 H-1 rig_p1c.py negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" probe/test_rig_sweep.py; then
    echo "FAIL: probe/test_rig_sweep.py (TASK-677 H-1 rig_sweep.py negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" probe/test_rig_uart.py; then
    echo "FAIL: probe/test_rig_uart.py (TASK-677/678 H-1 rig_uart.py negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" probe/test_rig_ladder.py; then
    echo "FAIL: probe/test_rig_ladder.py (TASK-677 H-1 rig_ladder.py negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" probe/test_rig_resetgap.py; then
    echo "FAIL: probe/test_rig_resetgap.py (PROP-011 X-P6 rig_resetgap.py negative suite) FAILED" >&2
    exit 1
fi

# ── TASK-646 / WP-A A-6 — one results layer, not five. The checker's negative
# suite runs first (BP-068) and carries the migration's own identity arms:
# `run_sync_tests.py`'s recorders must BE `lib.results`'s objects, not merely
# look like them. Blocking, on a 1-row dated ledger
# (docs/verification/private_results_exceptions.md). No DUT, ~0.2 s.
if ! "$PYTHON" gate/test_check_private_results.py; then
    echo "FAIL: test_check_private_results.py (TASK-646 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_private_results.py; then
    echo "FAIL: check_private_results.py (TASK-646 A-6 private results layer) FAILED" >&2
    exit 1
fi

# ── TASK-630 — the record scaffold's negative suite (Dev D4, BP-068). Blocking
# at zero from the day it lands, and the arm that matters most is the REFUSAL
# one: if `run/new-test` ever emits a `cls_reason` long enough to satisfy
# check_test_meta's 80-character floor, gating classes start shipping with
# machine-written justifications, which is the declaration becoming theatre
# (QM §4). Runs the real gate code over the emitted text; no DUT, ~0.3 s.
if ! "$PYTHON" suite/test_scaffold.py; then
    echo "FAIL: suite/test_scaffold.py (TASK-630 scaffold negative suite) FAILED" >&2
    exit 1
fi

# ── TASK-669 — the record must not lag the work. Reads the four live boards
# against TASK-NNN in COMMIT SUBJECTS, two inputs the row's author does not
# control, and asserts three contradictions: a row reading OPEN/BLOCKED with
# commit traffic (B1), a closed row citing no hash (B2), a row blocked on a task
# that has closed (B3). B3 reads 0 today and 9 on the tree before the PM audit
# `0dba35a`; B1 reads 4 and B2 68, all on the dated shrink-only ledger
# docs/project/board_currency_exceptions.md. Negative suite first (BP-068),
# including the mutation arms that reconstruct this week's real defects. Its
# LIMITS are in the checker's docstring and matter: a PASS here is not a
# guarantee that the board is true. No DUT, one `git log`, ~0.4 s.
if ! "$PYTHON" gate/test_check_board_currency.py; then
    echo "FAIL: test_check_board_currency.py (TASK-669 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_board_currency.py; then
    echo "FAIL: check_board_currency.py (TASK-669 board currency) FAILED" >&2
    exit 1
fi

# ── TASK-582 — T-BUSY-05's post-switch guard, WP-C finding C-1. The old guard
# (`if any(b is not True for b in results): ...`) was False, and so fell
# through to a silent pass_(), exactly when every post-switch reading was
# True — the amber never clearing, the one outcome the id exists to catch.
# Pins the fixed adjudicator (`_busy05_verdict`) against all four reading
# shapes, including the all-True regression arm and the None (failed-read)
# arm, which is `unmet()` per TASK-596/R18 rather than a silent pass or an
# unearned fail. Host-only, no DUT, ~0.05 s.
if ! "$PYTHON" suite/test_busy05_guard.py; then
    echo "FAIL: test_busy05_guard.py (TASK-582 C-1 guard negative suite) FAILED" >&2
    exit 1
fi

# ── TASK-707 — production ELF carries zero SERIAL_DEBUG symbols (T089,
# docs/verification/test_plan.md), automated: an `nm` over the linked symbol
# table, not a `strings`/`grep` text scan (see the checker's docstring for
# why). Negative suite first (BP-068); the live check needs BOTH ELFs already
# built (cyd2usb_winamp + cyd2usb_winamp_debug, gate 1's env matrix builds
# both earlier in run/check) and refuses cleanly if either is missing — it
# never builds, flashes, or opens a serial port itself.
if ! "$PYTHON" gate/test_check_production_symbols.py; then
    echo "FAIL: test_check_production_symbols.py (TASK-707 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_production_symbols.py; then
    echo "FAIL: check_production_symbols.py (TASK-707 / T089 production-symbol gate) FAILED" >&2
    exit 1
fi

echo "OK: smoke_test.sh passed"
