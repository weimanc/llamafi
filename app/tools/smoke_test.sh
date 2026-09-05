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

# 3. check-docs harness — T_DOC_01..09 (TASK-475).
# Runs here rather than as its own check_build.sh gate so the documentation
# gate itself (gate 12) stays one slot: gate 9 covers the CHECKER, gate 12
# runs it against the live corpus. Host-side only, no DUT, ~2 s.
# TASK-481: check_*.py + test_check_*.py live in gate/ now.
if ! "$PYTHON" gate/test_check_docs.py; then
    echo "FAIL: test_check_docs.py (T_DOC_01..09) FAILED" >&2
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

# 4i. flake declarations vs gating classes — TASK-623 / M-HARNESS2 R37.
# A RIG/HEALTH/CORE id that is also declared flaky gates nothing: its retry
# resolves FLAKY-PASS, which is neither a PASS nor a FAIL, so it can never set
# the blocker its class exists to set. Lands BLOCKING with a one-row dated
# shrink-only ledger (docs/verification/flake_class_exceptions.md, T091) rather
# than advisory — C3 is this repo's standing demonstration of what advisory
# does to a finding count.
if ! "$PYTHON" gate/test_check_flake_class.py; then
    echo "FAIL: test_check_flake_class.py (TASK-623 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_flake_class.py; then
    echo "FAIL: check_flake_class.py (TASK-623 gating-class flake) FAILED" >&2
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

# 5. app conformance matrix, rows A5/A6 — M-TESTARCH §2.3 (TASK-483).
# The CHECKER's own negative suite (BP-068) is blocking: a conformance gate that
# cannot be shown to fail is not a gate. The MATRIX itself is advisory today —
# it lands with one unexcepted finding (A6/Weather), and warn-only is the same
# bargain check_settings_wiring.py makes. Promote by flipping STRICT_DEFAULT in
# check_app_conformance.py once that cell is closed or excepted; the ledger
# (docs/verification/app_conformance_exceptions.md) states the criterion.
if ! "$PYTHON" gate/test_check_app_conformance.py; then
    echo "FAIL: test_check_app_conformance.py (A5/A6 checker negative suite) FAILED" >&2
    exit 1
fi
if ! "$PYTHON" gate/check_app_conformance.py; then
    echo "FAIL: check_app_conformance.py crashed (findings are warn-only; a" \
         "non-zero exit here means the checker itself broke)" >&2
    exit 1
fi

echo "OK: smoke_test.sh passed"
