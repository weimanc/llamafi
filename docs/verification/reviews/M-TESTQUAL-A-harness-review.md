# M-TESTQUAL WP-A — harness, framework, duplication, magic values, double bookkeeping

> Owner: **Verification Engineer**
> Status: complete — 2026-09-02
> Parent: [M-TESTQUAL index](M-TESTQUAL-index-review.md) · Rubric: [M-TESTQUAL rubric](M-TESTQUAL-rubric-review.md)
> Covers: **Q1–Q6**
> Method: static audit only. No flash, no `run/test*`, no `run/dut-health`. See §0 for one
> constraint breach that did occur and what it cost.

Every count below is produced by a command quoted next to it, run against the working tree at
`f880f52` on 2026-09-02. Nothing is carried over from M-TESTARCH or M-TOOLING without re-measuring;
where a prior document's number is cited it is labelled as such and re-derived.

---

## 0. Constraint breach — disclosed

While bulk import-checking `app/tools/*.py` for broken module-level imports I ran:

```sh
cd app/tools && for f in *.py …; do python3 -c "import <module>"; done
```

Three of those modules execute their entire DUT suite at **import time** (module-level code, not
behind `if __name__ == "__main__"`): `prloc_smoke.py`, `prloc_ve_smoke.py`, `settings_kit_smoke.py`.
They opened the serial port, which asserts DTR and **reset the board**, and injected taps. Nothing
was flashed; the `-DBOD_WATCH` debug build on the DUT is unchanged. The board was reset and had
touch events injected, and any TASK-557 observation window open at ~18:50 on 2026-09-02 is
contaminated. I stopped the sweep immediately and did not touch the port again.

That these files run a DUT suite on `import` is itself **Finding A-12**.

---

## 1. Q1 — Is there one common test harness?

> **Verdict: NO. There is one good harness and seventeen things that are not it.** The
> `suite/serialdbg` runner (213 registered ids) is a genuine framework — registry, class metadata,
> flake policy, health gate, triage, one result layer. Around it sit **13 standalone DUT harnesses**
> reachable from documented `run/` entry points, carrying ~36 further test ids plus 4 un-idded
> exit-code cells, of which **only 3 use the shared result layer at all** and **4 do not use the
> shared DUT layer either — they carry their own hand-rolled `SerialDut` class**. One documented
> entry point (`run/screendump`) and three of its dependants are **hard-broken at import** and have
> been since TASK-555. The host-gate tests add five more mutually incompatible mini-frameworks.

### 1.1 The measurement

```sh
# registered ids in the common harness
cd app/tools && python3 -c "import sys;sys.path.insert(0,'.');
from suite.serialdbg import build_all_tests,build_all_meta
from collections import Counter
t=build_all_tests();m=build_all_meta()
print(len(t), Counter(v['cls'] for v in m.values()))"
# -> 213  Counter({'FEATURE': 167, 'CORE': 43, 'HEALTH': 3, 'RIG': 3})

# which run/ script drives which python entry point
for f in run/*; do printf "%-24s %s\n" "$(basename $f)" \
  "$(grep -o 'tools/[A-Za-z0-9_/]*\.py' $f | sort -u | tr '\n' ',')"; done
```

### 1.2 The matrix

Legend — **DUT**: opens the serial port. **lib.dut**: constructs the shared `Dut`. **lib.results**:
records through `lib/results.py`. **flake**: goes through `run_with_flake_retry` (the mandated
retry). **exit3/4**: honours `SETUP_FAIL_EXIT` / `HEALTH_FAIL_EXIT`.

| Entry point | Harness | DUT | lib.dut | lib.results | flake | exit3/4 | Notes |
|---|---|:-:|:-:|:-:|:-:|:-:|---|
| `run/test` | `suite/serialdbg/runner.py` | ✅ | ✅ | ✅ | ✅ | ✅ | the reference implementation |
| `run/test-targeted` | same | ✅ | ✅ | ✅ | ✅ | ✅ | **no TLS-pin preflight** (see 1.4) |
| `run/test-smoke` | → `run/test-targeted` | ✅ | ✅ | ✅ | ✅ | ✅ | 11 hardcoded ids, `run/test-smoke:5` |
| `run/dut-health` | same, `--dut-health` (`run/dut-health:56`) | ✅ | ✅ | ✅ | n/a | ✅ | |
| `run/player-gate` | 2× runner legs + 2 standalone cells | ✅ | ✅ | ✅ | ✅ | ✅ | **parses the summary text**, `run/player-gate:162` |
| `run/test-sync` | `run_sync_tests.py` (20 ids) | ✅ | ✅ | ❌ **own copy** | ❌ | ❌ | `run_sync_tests.py:370-382,1344-1348` |
| `run/browser-player` | `test_fbrowser_player.py` | ✅ | ❌ raw `serial.Serial` `:273` | ❌ | ❌ | ❌ | one cell, exit 0/2 |
| `run/playorder-player` | `test_playorder_player.py` | ✅ | ❌ raw `serial.Serial` `:216` | ❌ | ❌ | ❌ | one cell, exit 0/2 |
| `run/wr-gate` | `test_adr045_gate.py` | ✅ | ❌ **own `SerialDut`** `:55` | ❌ | ❌ | ❌ | own reader thread |
| `run/wr-soak` | `test_webradio_soak.py` | ✅ | ❌ **own `SerialDut`** `:55` | ❌ | ❌ | ❌ | |
| `run/ae04` | `test_ae04_teardown.py` | ✅ | ❌ **own `SerialDut`** `:105` | ❌ | ❌ | ❌ | T_AE_04, no registry |
| `run/stress` | `test_fetch_stress.py` | ✅ | ✅ | ✅ (`ve_suite_base`) | ❌ | ❌ | |
| `run/pr-soak` | `test_planeradar_soak.py` | ✅ | ✅ | ✅ | ❌ | ❌ | |
| `run/pr-fetch-soak` | `pr_fetch_soak_report.py` | ✅ | ✅ | ✅ | ❌ | ❌ | |
| `run/task488` | `test_task488_partb.py` (8 ids) | ✅ | ✅ | ✅ | ✅ `run_suite` | ❌ | |
| `run/screendump` | `screendump.py` | — | **BROKEN** | ❌ | ❌ | ❌ | `ImportError` at `screendump.py:30` |
| `run/task424-repro` | `sdwrite_repro.py` | ✅ | ✅ | ❌ | ❌ | ✅ catches `SetupFailure` | |
| *(no `run/` entry)* | `test_webradio_long_soak.py` | ✅ | ❌ **own `SerialDut`** `:142` | ❌ | ❌ | ❌ | |
| *(no `run/` entry)* | `test_tls_yield_reliability.py` (3 ids) | ✅ | ✅ | ✅ | ✅ | ❌ | |
| *(no `run/` entry)* | `test_heatmap_reliability.py` (5 ids) | ✅ | ✅ | ✅ | ✅ | ❌ | |
| *(no `run/` entry)* | `prloc_smoke` / `prloc_ve_smoke` / `prloc_manual_smoke` / `prloc_editor_smoke` / `settings_kit_smoke` / `clock_tap_smoke` | ✅ | ❌ raw `serial.Serial` | ❌ | ❌ | ❌ | **run on import** — see §0 |
| *(no `run/` entry)* | `clock_delta_smoke` / `pr_delta_smoke` / `slider_delta_smoke` | — | **BROKEN** | ❌ | ❌ | ❌ | import `screendump` |
| *(no `run/` entry)* | `sd_health_probe.py`, `wifi_watch.py`, `e0_baseline.py`, `exp012_measure.py`, `tsync_diff.py`, `sd_put.py` | ✅ | ✅ | ❌ | ❌ | partial | analysis/probe family |

Host-only (no DUT), listed for completeness because they still decide exit codes:
`run/check-docs` → `gate/check_docs.py`; `run/check` → `smoke_test.sh` (11 gates);
`run/check-datatask-certs`, `run/check-teletext-api` (both self-contained Python, **do not source
`run/lib.sh`**); `run/audit-origin`; and the gate tests in §1.5.

### 1.3 What each bypasser would break if the shared layer changed

| Bypasser | Bypasses | Breaks if… |
|---|---|---|
| `test_adr045_gate.py:55`, `test_webradio_soak.py:55`, `test_webradio_long_soak.py:142`, `test_ae04_teardown.py:105` | the whole of `lib/dut.py` | **the wire format changes.** M-TESTARCH §3b.3 item 1 (correlated command ids) is a breaking protocol change; these four each have their own `cmd()`/`boot_wait()` and would silently mis-parse. They also each set `ser.dtr=False` *after* `serial.Serial(...)` has already opened and pulsed DTR, so each one resets the board and **never writes the DRD gap file** (`lib/dut.py:123 _reset_gap_file`, written only in `Dut.close()`, `lib/dut.py:1156`). A `run/ae04` followed by `run/test` therefore skips the 12 s back-to-back-reset guard (`lib/dut.py:115`). |
| `run_sync_tests.py:370-382` | `lib/results.py` | **any change to the result vocabulary.** It has no `FLAKY-PASS`, no `NOT-RUN`, no health-fail exit 4, no flaky policy at all (`grep -c flake run_sync_tests.py` → 0). Its `sys.exit(0 if failed==0 else 1)` at `:1349` cannot express "the board was not a valid subject". |
| `test_fbrowser_player.py:273`, `test_playorder_player.py:216` | `lib/dut.py` session (they use `resolve_port` only) | **`_wait_for_ready` / boot-phase deadlines.** Neither gets the debug-firmware verify (`lib/dut.py:1009`) nor the shell-cooldown drain in `Dut.cmd` (`lib/dut.py:1122-1136`) — the drain TASK-297 added because *every* injected tap races `s_cooldownMs`. These two inject taps without it. |
| `screendump.py:30` (+ 3 dependants) | — | already broken; see Finding A-1. |
| the 6 `*_smoke.py` raw-serial scripts | everything | any signature change anywhere; they are outside every gate. |

### 1.4 One entry point has a preflight the other does not

```sh
grep -c 'check-datatask-certs' run/test run/test-targeted run/test-sync run/player-gate
# run/test:1  run/test-targeted:0  run/test-sync:0  run/player-gate:0
```

`run/test:99` runs the TLS-pin preflight as "step 0/6" precisely so a pinned-CA rotation does not
surface as a spray of cryptic fetch FAILs 30 minutes in (TASK-298/LL-103). `run/test-targeted` —
the entry point CLAUDE.md tells you to use for a scoped change, and the one that runs the *same*
fetch tests — does not. Neither does `run/player-gate`, which is a release gate.

### 1.5 The host gates have five mini-frameworks and one copy-pasted runner

| File | Result mechanism |
|---|---|
| `gate/test_check_docs.py:35` | `def check(tid, cond, msg)` |
| `gate/test_check_app_conformance.py:273` | bare `assert` + `CASES` list + `main()` |
| `gate/test_check_test_meta.py:234` | bare `assert` + `CASES` list + `main()` — **byte-identical `main()` to the above** |
| `test_class_order.py:57` | `def check(cond, msg)` |
| `test_boot_gate.py:35`, `test_triage_context.py:30`, `test_serial_classify.py:31` | `def check(label, got, want)` |

Three different functions named `check` with three different signatures, in one directory tree. No
gate test uses `lib/results.py`, and none is discoverable as a suite.

---

## 2. Q2 — Is there a consistent DUT entry point?

> **Verdict: YES for port resolution — the TASK-478/479 work landed and the "19 files hardcoding
> `/dev/ttyUSB0`" finding is now genuinely ZERO code sites. NO for the session itself: five
> independent session implementations remain, and the shared session's `SetupFailure` contract —
> the mechanism that distinguishes "the rig broke" from "the firmware broke" — is honoured by 4 of
> the ~20 tools that can raise it.**

### 2.1 `lib/dut.py`'s surface, audited

| Concern | Implementation | Assessment |
|---|---|---|
| Port resolution | `resolve_port()` `lib/dut.py:64-110` | **Good.** Order: explicit → `$PORT` → `run/port`. Delegates VID:PID to the shell layer (LL-114 correct). Refuses to guess when `run/port` declines (`:96-105`, TASK-552). The `/dev/ttyUSB0` fallback at `:110` is loud. |
| Open / reset semantics | `Dut.__init__` `:523`, `_wait_for_ready` `:606`, `_wait_for_bootphase_6` `:895` | Rich: DRD gap (`:115,:123`), boot-phase deadlines (`:243`), WiFi two-stage wait (`:165,:170`), `NO_WIFI` opt-out (`:173`), boot gate mode (`:179`). Documented known weakness at `:139-147` (gap file keyed on realpath, defeated by CH340 re-enumeration). |
| Firmware identity | `_verify_debug_firmware` `:1009` | Present, and unique to this layer. Nothing else has it. |
| `send` / `read_json` / `read_json_multi` / `cmd` / `cmd_drain` / `drain_log_lines` | `:1074`, `:1079`, `:1093`, `:1122`, `:981`, `:1111` | **Positional reply matching** (`read_json` returns the *first* `{`-line seen). This is M-TESTARCH §3b.3's unfixed item 1; the file carries the thread-safety warning itself. |
| Timeouts | `TIMEOUT`/`TIMEOUT_SLOW` `:47-48` | Declared as "one timeout policy … not a knob per call site". **Used by zero suite modules** — see Q5. |
| Cooldown | `Dut.cmd` auto-drains before `tap`/`drag` `:1122-1136`; `wait_shell_cooldown_clear` `:1138` | Good — one choke point, and the reason the two `serial.Serial` player scripts are exposed. |
| Close | `close()` `:1156` | Closes and stamps the gap file. Best-effort (`except: pass`) — a crash before `close()` leaves no stamp. |
| Rig-vs-firmware split | `SetupFailure` `:356`, `SETUP_FAIL_EXIT = 3` `:325` | **The contract almost nobody honours** — see 2.3. |

### 2.2 The hardcoded-port finding is closed

M-TESTARCH §1 measured *"19 files hardcoding `/dev/ttyUSB0` as an argparse default"*. Re-measured
today:

```sh
grep -rn '/dev/ttyUSB' app/tools --include=*.py | wc -l        # 29 matches, 19 files
grep -rn '/dev/ttyUSB' app/tools --include=*.py | grep -v '^app/tools/lib/dut.py'
# -> 17 matches, ALL of them `python3 <tool>.py --port /dev/ttyUSB0` inside a
#    module docstring, plus test_serial_classify.py:26 GONE = "/dev/ttyUSB-does-not-exist-99"
#    (a deliberate negative fixture).
```

**Zero argparse defaults, zero code sites, outside `lib/dut.py` itself.** Every tool that takes a
`--port` now defaults it to `resolve_port()`; verified across all 29 DUT-capable tools by
`grep -n 'resolve_port' app/tools/*.py`. This is a completed fix and should be recorded as such —
the 19 number must not be re-cited.

The one residual: **`screendump.py:93 autodetect_port()`** is a second, independent port resolver
that also shells out to `run/port` but with no `$PORT` precedence, no `run/port`-declined handling,
and `sys.exit()` on empty. Its three dependants (`clock_delta_smoke`, `pr_delta_smoke`,
`slider_delta_smoke`) import it by name.

### 2.3 Five session implementations, one `SetupFailure` contract, four honourers

```sh
grep -rn 'serial\.Serial(' app/tools --include=*.py       # 19 call sites, 16 files
grep -rln 'except SetupFailure' app/tools --include=*.py  # 4 files:
#   lib/dut.py  sd_health_probe.py  sdwrite_repro.py  suite/serialdbg/runner.py
```

Session implementations: `lib.dut.Dut`; `screendump.DutLite(Dut)` (subclass, overrides
`_wait_for_ready`); and four unrelated `class SerialDut` in `test_adr045_gate.py:55`,
`test_webradio_soak.py:55`, `test_webradio_long_soak.py:142`, `test_ae04_teardown.py:105`. Two of
those four run their own RX reader thread; the other two do blocking reads. Each has its own
`cmd(s, timeout=3.0)` and its own `boot_wait(timeout=45|60)`.

Eight tools construct the **real** `Dut` and catch nothing:

```
test_planeradar_soak.py:56   test_fetch_stress.py:214    wifi_watch.py:109
pr_fetch_soak_report.py:139  test_tls_yield_reliability.py:455
test_task488_partb.py:488    test_heatmap_reliability.py:615  run_sync_tests.py:1304
```

In every one of these, a `SetupFailure` raised inside `Dut.__init__` (no port, wrong firmware,
board never reached boot phase 6) escapes as an uncaught `RuntimeError` traceback and Python exits
**1** — indistinguishable from a firmware failure. That is the exact confusion M-TESTARCH §4 and
`run/player-gate:490-497` build their exit-3/exit-4 vocabulary to prevent.

---

## 3. Q3 — Is result reporting consistent?

> **Verdict: NO, and the inconsistency has a documented history of producing wrong verdicts.**
> `lib/results.py` is a well-designed single layer with a real policy, used by all 12 serialdbg
> modules and 6 satellites. But `run_sync_tests.py` still carries a private, pre-TASK-520 copy of
> the whole thing; 10 DUT harnesses report only through an exit code; the gate tests report through
> five ad-hoc mechanisms; and the summary's **per-id line format is a de-facto machine interface
> parsed by `run/player-gate` with a `sed` regex that has already silently mis-graded a run once
> (TASK-573).** That format is described in code comments and in the M-TESTARCH precedence doc's
> defect table — it is not specified anywhere as a contract.

### 3.1 The layer itself

`lib/results.py` — `pass_ :141`, `fail :146`, `skip :152`, `not_run :168`, `flake :176`,
`run_with_flake_retry :205`, `_finalize :239`, `print_results :251`. The design is sound:
fail-closed on an undeclared flake, `_finalize()` at `:239` converts a never-retried declared flake
into a FAIL, `FLAKY-PASS` and `NOT-RUN` are separate buckets, `HEALTH_FAIL_EXIT=4` is opt-in by
parameter (`:251-258`) rather than inferred. No findings against the layer's logic.

### 3.2 Everything that reports outside it

```sh
grep -rn '\bRESULTS\b *= *{}\|def pass_\|def fail(' app/tools --include=*.py | grep -v lib/results
# -> run_sync_tests.py:370, :372, :376   (the only full private copy)
grep -c 'sys.exit' app/tools/test_*.py app/tools/*_smoke*.py   # 1–6 per file, 34 files
```

| Where | What it does instead | Consequence |
|---|---|---|
| `run_sync_tests.py:370-382` + `:1344-1349` | private `RESULTS`/`pass_`/`fail`/`skip` + private summary block | No flaky policy (0 `flake` calls), no `FLAKY-PASS`, no `NOT-RUN`, no exit 4. Prints ids `sorted()` (`:1348`), not in registry order — so its output ordering differs from every other suite's. |
| `test_fbrowser_player.py:99 fail()`, `test_playorder_player.py:102 fail()` | print + `sys.exit(2)` | The whole script is one boolean cell. `run/player-gate:506` documents this ("exit 0 = PASS, anything else = FAIL") — so a *partial* failure and a rig failure are the same value. |
| `test_adr045_gate.py`, `test_webradio_soak.py`, `test_webradio_long_soak.py`, `test_ae04_teardown.py` | own trial-counting + `sys.exit(N)` with N ∈ {1,2,3,6} | Four different exit-code vocabularies, none matching `SETUP_FAIL_EXIT`/`HEALTH_FAIL_EXIT`. |
| `gate/test_check_docs.py:35`, `gate/test_check_app_conformance.py:273`, `gate/test_check_test_meta.py:234`, `test_class_order.py:57`, `test_boot_gate.py:35`, `test_triage_context.py:30`, `test_serial_classify.py:31` | five mini-frameworks (see §1.5) | Consumed by `smoke_test.sh` purely as exit codes. |

### 3.3 The summary text is an undocumented wire format

The consumer:

```sh
sed -n '162p' run/player-gate
#   sed -n 's/^  \([A-Za-z0-9_]\{1,\}\): \(FLAKY-PASS\|NOT-RUN\|PASS\|FAIL\|SKIP\|FLAKE\).*/\1 \2/p' "$1"
```

The producer: `lib/results.py:270-271`, `print(f"  {tid}: {RESULTS[tid]}")`.

Two leading spaces, a colon, a status token — that is the interface. `lib/results.py` *knows* this
(`:114` "run/player-gate parses the summary with a line-oriented …", `:160`, `:163`) but no document
states it. The cost is on record: `run/player-gate:150-158` records that `FLAKY-PASS` was missing
from the alternation, so a resolved flake read as `MISSING` and **the gate printed REGRESS for a
firmware regression that never happened** — with the worst possible polarity (the *unresolved*
flake parsed fine). TASK-573 fixed that instance; the class of defect is structural. A second
producer, `run_sync_tests.py:1348`, emits the same shape by coincidence, not by contract.

---

## 4. Q4 — Duplicate code

> **Verdict: substantial and concentrated in three places — app entry, bounded polling, and DUT
> session construction. Sixteen implementations of "enter an app and confirm you are there", 57
> hand-written poll loops, five DUT sessions, two byte-identical gate-test runners. The
> `suite/serialdbg` split (TASK-480) separated the families but did not consolidate their helpers:
> `_helpers.py` is 454 lines against 9 983 lines of family modules.**

### 4.1 App entry / exit — 16 implementations of one operation

```sh
grep -n '^def .*\(switch\|restore\|ensure\)' app/tools/suite/serialdbg/*.py   # 13
grep -n '^def _switch\|^def _restore\|^def _ensure' app/tools/test_*.py       # 3
```

| Implementation | Mechanism | Verifies arrival? |
|---|---|---|
| `_helpers.py:321 _switch_to` | taskbar tap + `get appId` | ✅ name compare |
| `_helpers.py:195 _switch_to_stock` | `switchApp` + `get appId` | ✅ |
| `_helpers.py:210 _restore_from_stock` | `switchApp` + `get appId` | ✅ (near-identical body to `:195`) |
| `_helpers.py:286 _restore_spotify` | — | ✅ |
| `health.py:226 _switch_app_cmd` | `switchApp` + poll `get appId` | ✅ (deliberately not a tap — HEALTH may not rest on CORE) |
| `shell.py:2904 _switch_to_settings` | — | ✅ |
| `stock.py:967 _ensure_stock_list_view` | — | ✅ |
| `webradio.py:298 _ensure_webradio` / `:346 _switch_to_webradio_capture_heap` / `:1291 _webradio_ensure_playing` | — | ✅ |
| `player.py:366 _enter_player` | — | ✅ |
| **`clock.py:10 _switch_to_clock`** | `switchApp 1`, `sleep(0.4)`, `return True` | ❌ **returns True on the ack alone** |
| `clock.py:17 _restore_spotify_from_clock` | `switchApp 0`, sleep | ❌ no verify, no return |
| `test_task488_partb.py:62 _switch` / `:82 _restore` | own | ✅ |
| `test_tls_yield_reliability.py:64 _restore_to_spotify` | own | ✅ |

`clock.py:10` is the outlier that matters: it is the precondition helper for the entire Clock
family and it cannot detect a failed switch. That is an S2 (ack-not-effect) sitting under every
Clock test — flagged here for WP-H to grade.

### 4.2 Bounded poll loops — 57 hand-written, one primitive

```sh
grep -c 'while time.monotonic()' app/tools/suite/serialdbg/*.py
# shell 18, player 9, _helpers 8, webradio 8, planeradar 6, stock 4, health 2, teletext 2  = 57
```

Every one is the same five lines: compute a deadline, `dut.cmd("get X")`, compare, `time.sleep(n)`,
fall out. Named variants doing exactly this: `_helpers.py:68 _drain_data_pipeline`,
`:93 _poll_shell_busy`, `:239 _wait_chart_complete`, `:378 _wait_shell_not_busy`;
`webradio.py:260 _wait_wr_count`, `:283 _wait_wr_state`; `stock.py:42 _wait_quote_fetch`,
`:949 _wait_heatmap_count`; `player.py:974 _wait_for_log`; `health.py:238 _wait_idle`;
`shell.py:1631 _poll_chart_len_positive`. **Eleven named copies plus 46 inline ones.**

Per M-TOOLING §3's rule ("`_helpers.py` — the shared helpers, named and owned") the correct shape
is one primitive — `wait_until(dut, key, predicate, timeout, poll)` — in `_helpers.py`, plus the
per-family predicates. This is also the surface M-TESTARCH §3b.3 item 4 (`watch`) would replace
wholesale; consolidating first makes that a one-file change instead of a 57-site change.

### 4.3 DUT session — 5 implementations

Covered in §2.3. `test_webradio_long_soak.py:143-147` states outright that it *matches*
`test_adr045_gate.py`'s architecture — i.e. the duplication is deliberate and acknowledged in
the code, with no shared home offered.

### 4.4 Gate-test runner — 2 byte-identical copies

`gate/test_check_app_conformance.py:273-289` and `gate/test_check_test_meta.py:234-250` are the
same `main()` modulo the file name in the final `print`. Belongs in `gate/_cases.py` or, better,
`lib/results.py`.

### 4.5 JSON field extraction

```sh
grep -oh 'int([a-z_0-9]*\.get("val"[^)]*)' app/tools/suite/serialdbg/*.py | wc -l   # 10
grep -oh '\.get("val", *[^)]*)' app/tools/suite/serialdbg/*.py | sort | uniq -c
#  10 .get("val", 0)   8 .get("val", "?")   5 .get("val", "")   4 .get("val", -1)
#   2 .get("val", None)  1 .get("val", -1.0)  1 .get("val", 0.0)
```

Seven different defaults for the same field. Six of the seven are values that a comparison can
pass on — the S6 "defaulting oracle" surface. A single `dut.get_int(key)` / `dut.get_str(key)` in
`lib/dut.py` that raises on a missing `val` would close the class. (Per-test S6 grading is WP-C…H's
job; the *mechanism* is a WP-A finding.)

---

## 5. Q5 — Magic variables and numbers

> **Verdict: pervasive and almost entirely unattributed. 823 numeric timeout literals, 253 fixed
> sleeps, 202 numeric threshold comparisons and 73 literal tap/drag coordinates in the suite; of
> the thresholds, 24 lines carry any comment at all, and exactly THREE module-level constants in
> the whole 11 977-line suite cite a firmware file as their source. The shared timeout policy
> `lib/dut.TIMEOUT` shipped and has ZERO users.**

### 5.1 The counts

```sh
cd app/tools/suite/serialdbg
grep -oh 'timeout[_a-z]*=[0-9][0-9.]*' *.py | wc -l                    # 823
grep -oh 'timeout[_a-z]*=[0-9][0-9.]*' *.py | sort | uniq -c | sort -rn | head -3
#   459 timeout=3.0    107 timeout=5.0    77 timeout=2.0
grep -c 'time.sleep(' *.py | awk -F: '{s+=$2} END{print s}'            # 253
grep -oh 'time\.sleep([0-9.]*)' *.py | sort | uniq -c | sort -rn | head -4
#    64 (0.3)   35 (0.5)   33 (0.2)   23 (0.1)
grep -oh '[<>]=\? *[0-9][0-9.]*' *.py | wc -l                          # 202 threshold comparisons
grep -h  '[<>]=\? *[0-9][0-9.]*' *.py | grep -c '#'                    #  24 carry a comment
grep -oh '"tap [0-9]\+ [0-9]\+"' *.py | wc -l                          #  69 literal taps
grep -oh '"drag [0-9]\+ [0-9]\+ [0-9]\+ [0-9]\+' *.py | wc -l          #   4 literal drags
grep -c 'TIMEOUT_SLOW\|dut\.TIMEOUT\|=TIMEOUT' *.py                    #   0 in every file
```

M-TESTARCH §3b measured 252 sleeps in the pre-split monolith. It is **253** after the split. The
TASK-480 decomposition moved the problem; it did not reduce it by one.

### 5.2 The three categories

| Category | Count | Evidence |
|---|---|---|
| **(a) derived from a firmware constant, cited** | **3** | `shell.py:2925-2927` — `_S_CONTENT_Y=28`, `_S_ROW_H=26`, `_S_CONTENT_H=212`, each with `# app/src/settings/settingsSection.h …`. All three values verified correct today against `app/src/settings/settingsSection.h:40,41,43`. They are still *mirrors*, not parses. |
| **(b) derived from a recorded measurement** | **~10** | e.g. `player.py:1785 _PMT04_SETTLE_S = 100.0  # heap is not stable until ~150 s post-reset (TASK-425)`; `_helpers.py:151-153` `_PLEDIT_X/_PLSTART_Y/_PLEND_Y` with the `dy = 150-163 = -13` derivation written out; `webradio.py:1288 _VIS_SCREEN_REGION` citing EXP-016/017/018. |
| **(c) unexplained** | **the rest — >1 000 literals** | See 5.3. |

### 5.3 Worst offenders

| Site | Literal | Why it is bad |
|---|---|---|
| `webradio.py:111` | `if cooldown_ms > 220:` | 220 is not a firmware number. `app/src/winamp/pleditView.h:323` sets `r.cooldownMs = 300` on the tap branch and `:337` sets `150` on the scroll-end branch. 220 is a hand-chosen midpoint with no cite. If either firmware constant moves toward the other, the test silently stops discriminating. **This is the test's entire oracle.** |
| `stock.py:759` | `_TAB_XY = [(148,9),(184,9),(220,9),(256,9)]` | Exactly `ST_CHART_TABS_X + t*ST_CHART_TAB_W + ST_CHART_TAB_W/2` = `130 + 36t + 18` from `app/src/stock/stockShared.h:46-47`. Four hardcoded pairs replacing a two-constant formula. `coords.py:12 _parse()` already parses `#define` headers with the identical regex. |
| `stock.py:756-757` (comment) | row centres `36,62,88,114,140,166,192,218` | Step is 26 = `ST_LIST_ROW_H` (`app/src/stock/stockShared.h:38`). Same story. |
| `stock.py:133,141` | `0 <= prog < 8` | 8 is `len(_DEFAULT_TICKERS)` (`stock.py:106`). Adding a ticker breaks the guard silently. |
| `webradio.py:49` | `if r_c.get("count", 0) < 15:` | Station-count precondition. No cite, no firmware constant, no measurement reference. |
| `webradio.py:614,633` | `latency_ms > 500` | Touch-latency bound during playback. No derivation. |
| `_helpers.py:239` | `timeout_s: float = 45.0` | Chart-fetch bound; compare `stock.py:42 timeout_s=65.0` and `stock.py:949 timeout_s=60.0` for the same class of fetch. Three different budgets for one operation. |
| the 64 `time.sleep(0.3)` calls | — | M-TESTARCH §3b.2 names these precisely: they exist because `injectTouch` acks on dispatch, not on handling. Each is an S9. |

### 5.4 What exists to import that tests hardcode instead

| Available | Where | Suite usage |
|---|---|---|
| `coords.py` — 16 accessors, all parsed from `app/gen/skin_layout.h`, `app/gen/shell_layout.h`, `app/src/winamp/vuMeter.h` | `app/tools/coords.py:59-193` | imported by 7 of 15 suite modules; **used** by 4. `planeradar.py:8` and `teletext.py:8` `import coords as _c` and never reference it (`grep -c '_c\.'` → 0 in both). `stock.py` imports it and uses it **once** while carrying 48 literal taps. |
| `app_ids_gen.APP_SLOT` / `APP_ORDER` / `CONFIGURABLE` / `APP_COUNT` (generated by `gen/gen_app_registry.py`) | `app/tools/app_ids_gen.py` | imported by 9 suite modules — **but not by `clock.py`**, which hardcodes slots (see Q6). |
| `shell_layout.defines()` — generic `#define` parser | `app/tools/shell_layout.py:29` | **zero** suite importers. |
| `coords._parse_cpp_constexpr_int()` — generic `constexpr int` parser | `app/tools/coords.py:43` | private; would parse `settingsSection.h` with a one-word regex widening (`int` → `int16_t`). |
| `lib.dut.TIMEOUT` / `TIMEOUT_SLOW` | `lib/dut.py:47-48` | **zero** users. |
| `app/gen/mem_layout.py` — generated explicitly as "a Python mirror **for the test suite**" (`gen/gen_mem_layout.py:5`) | `app/gen/mem_layout.py` | **zero** importers anywhere in the repo. |

---

## 6. Q6 — Double bookkeeping (the key question)

> **Verdict: the suite mirrors firmware facts in at least nine places, and in every case a
> generator, a parser, or a generated Python module already exists that it could import instead.
> The good news is that the infrastructure LL-114 asked for was BUILT — `app_ids_gen.py`,
> `shell_layout.py`, `coords.py`, `gen_get_keys.py`, `app/gen/mem_layout.py`. The bad news is that
> adoption is partial and unenforced: nothing gates a mirror, so each new one lands unnoticed. Two
> of the generators are themselves broken or unused — `gen_get_keys.py` misses 10 of 20 firmware
> `dbgGet()` implementations, and `app/gen/mem_layout.py` has no importers at all.**

### 6.1 The register

| # | Firmware fact | Authoritative location | Mirrored in the suite at | Value correct today? | Drift risk | Importable alternative? |
|---|---|---|---|:-:|---|---|
| **D1** | App id → taskbar slot | `app/gen/configurable_apps.h` + `app/tools/app_ids_gen.py:4-5` (both generated by `gen/gen_app_registry.py`) | `clock.py:11,20,27,152,153,201` — `switchApp 1` (Clock), `switchApp 0` (Spotify), `switchApp 4` (Matrix); `shell.py:3302,3305` — `switchApp 1`, `switchApp 0` | ✅ | **HIGH.** `gen_app_registry.py` regenerates `APP_ORDER` from the firmware registry; inserting an app before Clock renumbers every slot. `clock.py` does not import `app_ids_gen` at all, so the 6 Clock tests would silently drive the wrong app and mostly still pass (they call `_switch_to_clock`, which does not verify — §4.1). | **YES** — `from app_ids_gen import APP_SLOT`; 9 other suite modules already do. |
| **D2** | `CONFIGURABLE_APP_COUNT` | `app/gen/configurable_apps.h:4` (=10); mirrored in Python as `app_ids_gen.CONFIGURABLE` (len 10, verified) | `shell.py:2928` — `_CONFIGURABLE_APP_COUNT = 10   # app/gen/configurable_apps.h` | ✅ | **HIGH.** Generated on both sides; the suite hardcodes the number *and cites the generated header in a comment*, which is the tell. | **YES** — `len(app_ids_gen.CONFIGURABLE)`. One-line change. |
| **D3** | Settings layout | `app/src/settings/settingsSection.h:40,41,43` — `S_CONTENT_Y=28`, `S_CONTENT_H=212`, `S_ROW_H=26` | `shell.py:2925-2927` | ✅ | **MEDIUM.** Cited, so a human *could* catch it; nothing mechanical will. Drives `_settings_tap_row` (`shell.py:2935`) → every Settings tap test. | **PARTIAL** — `coords.py:43 _parse_cpp_constexpr_int` needs its regex widened from `constexpr int` to `constexpr int(16_t)?`. |
| **D4** | Stock chart tab geometry | `app/src/stock/stockShared.h:46-47` — `ST_CHART_TABS_X=130`, `ST_CHART_TAB_W=36` | `stock.py:759 _TAB_XY = [(148,9),(184,9),(220,9),(256,9)]` | ✅ (130+36t+18) | **HIGH.** Four literals; no cite; drives T186/T187/T188/T204. | **YES** — `shell_layout.defines(app/src/stock/stockShared.h)` parses `#define` and is already written; or add a `coords.stock_tab(t)` accessor. |
| **D5** | Stock list row pitch | `app/src/stock/stockShared.h:38 ST_LIST_ROW_H = 26` | `stock.py:756-757` (comment) + 48 literal `"tap 137 <y>"` sites | ✅ | **HIGH.** Same as D4, ×8 rows. | **YES**, as D4. |
| **D6** | `FetchType` enum — PlaneRadar's dispatch id | `app/src/dataTask.h:11-22`, `DATA_FETCH_PLANERADAR = 8` | `planeradar.py:267-269` — `PR_FETCH_TYPE = 8` with the comment *"keep in sync with the enum"* | ✅ | **HIGH.** The comment is an admission. Inserting a fetch type before PlaneRadar (9 exist; new ones have been added repeatedly) renumbers it, and the test then reads a *different* app's in-flight state as PlaneRadar's. | **NO parser today** — but the enum is a 10-line `enum FetchType : uint8_t { NAME = N, … }` block; a `parse_enum(path, name)` in `lib/` or `shell_layout.py` is ~15 lines and would serve D6 and D7. |
| **D7** | `PlayerMode` names | `app/src/settingsStorage.h:21` (`Spotify=0, WebRadio=1, Player=2`); string table at `app/src/debug/serialConsole/cmdSet.cpp:699 kPmNames[]` | `health.py:68 _PLAYER_MODES = ("Spotify","WebRadio","Player")` | ✅ | **MEDIUM**, and the provenance comment at `health.py:66` says *"cmdGet.cpp `kPmNames`"* — **`kPmNames` is in `cmdSet.cpp`, not `cmdGet.cpp`.** The cite does not resolve; a reader following it finds nothing. | **NO parser today**; same `parse_enum`/`parse_string_table` helper as D6. |
| **D8** | The `get` key namespace | `app/src/debug/serialConsole/cmdGet.cpp` + 10 `dbgGet()` bodies in `app/src/**/*.cpp` | the suite issues **71 distinct `get` keys**; `gen/gen_get_keys.py` can enumerate only **43** | n/a | **HIGH — the generator is broken.** `gen/gen_get_keys.py:44` globs `app/src/**/*.h` only. M-SRCLAYOUT moved app bodies into `.cpp`, so 10 `dbgGet()` implementations (`webRadioApp.cpp`, `stockApp.cpp`, `planeRadarApp.cpp`, `teletextApp.cpp`, `cryptoApp.cpp`, `lifeApp.cpp`, `matrixApp.cpp`, `settingsApp.cpp`, `aquariumApp.cpp`, `winampDisplay.cpp`) are invisible. `run/task488`'s T_488_10 — *"every key resolves, no 'unknown'"* — therefore probes 43 of 71+. | **YES, one-word fix**: `*.h` → `*.[hc]*` at `gen/gen_get_keys.py:44`. Reproduce with the command in 6.2. |
| **D9** | Memory arena layout | `app/mem_manifest.yaml` → `app/gen/mem_layout.py` (`MEM_OFFSETS`, `MEM_REGION_SIZES`, `MEM_BUDGET_USED`), generated expressly "for the test suite" | nothing imports it; `player.py:1785`, `_helpers.py` and the webradio family carry their own heap numbers as literals | n/a | **LOW-MEDIUM** (the numbers are diagnostic, not oracles) but the *generator* is dead weight and gated by `run/check` step 6 for nobody. | **YES** — it is already a Python module. |

Additional, lower-severity mirrors found but not tabled: `_helpers.py:236 _CHART_PHASE_NAMES = {0:"TLS/connect",1:"GET/response",2:"JSON-parse"}` (no matching firmware symbol found by
`grep -rn 'chartPhase\|fetchPhase' app/src/`; diagnostic-only, printed on timeout, never an oracle);
`_helpers.py:400 _TB_N = APP_SLOT["WebRadio"]` (correctly derived — the good pattern);
`health.py:134 _ZERO_IPS` (host-side judgement, not a firmware fact).

### 6.2 Reproducing D8

```sh
cd app/tools
python3 gen/gen_get_keys.py | tr ',' '\n' | sort -u > /tmp/fwkeys.txt   # 43
grep -oh '"get [A-Za-z0-9_]*\|f"get [A-Za-z0-9_]*' suite/serialdbg/*.py \
  | sed 's/.*get //' | sort -u > /tmp/suitekeys.txt                     # 71
comm -23 /tmp/suitekeys.txt /tmp/fwkeys.txt | wc -l                     # 43 keys the generator misses
grep -rln 'dbgGet' ../src --include=*.cpp | wc -l                       # 10 invisible implementations
```

Spot-verified that the missed keys are real: `wrState` → `app/src/apps/webRadioApp.cpp:716`,
`chartLen` → `app/src/stock/stockApp.cpp:178`, `prRange` → `app/src/apps/planeRadarApp.cpp:177`.

### 6.3 The structural point

There is no gate against mirroring. `run/check` gates *generated output staleness* (steps 6/7) and
`golden.sha256`; `run/check-docs` C6 gates *test-id binding*. Nothing asks "does this Python literal
equal a firmware constant?". D1, D2, D4 and D6 would each be caught by a cheap grep gate — a
`check_no_mirrors.py` that flags a suite literal appearing as the value of a `#define`/`constexpr`
of the same rough name — but that gate does not exist, which is why the register above grew after
LL-114 was supposedly closed.

---

## 7. Findings

Severity: **P1** = produces or can produce a wrong verdict, or a documented entry point does not
work. **P2** = materially weakens a guarantee the architecture claims. **P3** = hygiene / debt.

| # | Sev | Finding | Evidence | Proposed fix |
|---|:-:|---|---|---|
| **A-1** | **P1** | `run/screendump` is **hard-broken** and has been since TASK-555 deleted `_PORTAL_INDICATORS` from `lib/dut.py`. It fails with `ImportError` before opening the port. Three further tools (`clock_delta_smoke.py`, `pr_delta_smoke.py`, `slider_delta_smoke.py`) import `screendump` and die the same way. `run/screendump` is documented in `CLAUDE.md`. | `screendump.py:30` imports `_PORTAL_INDICATORS`; `lib/dut.py:310` records its removal. `clock_delta_smoke.py:26`, `pr_delta_smoke.py:54`, `slider_delta_smoke.py:33`. Verified: `python3 -c "import screendump"` → `ImportError`. | Restore the constant locally in `screendump.py`, or drop the portal branch at `screendump.py:61` (the firmware it watched for went away in `ddf6433`). Add a CI import-check for every `app/tools/**/*.py` — **but see A-12 first: three modules cannot be safely imported.** |
| **A-2** | **P1** | The `SetupFailure` → exit-3 contract, which is the mechanism separating "the rig broke" from "the firmware broke", is honoured by **4 files**. Eight tools construct the shared `Dut` and let it escape as an uncaught traceback → exit 1. | `grep -rln 'except SetupFailure'` → `lib/dut.py`, `sd_health_probe.py`, `sdwrite_repro.py`, `suite/serialdbg/runner.py`. Constructors without it: `test_planeradar_soak.py:56`, `test_fetch_stress.py:214`, `wifi_watch.py:109`, `pr_fetch_soak_report.py:139`, `test_tls_yield_reliability.py:455`, `test_task488_partb.py:488`, `test_heatmap_reliability.py:615`, `run_sync_tests.py:1304`. | Put the handler in `ve_suite_base` (or a `lib.dut.open_session()` context manager) and route all eight through it. |
| **A-3** | **P1** | `gen/gen_get_keys.py` enumerates 43 of 71+ firmware `get` keys because it globs headers only; 10 `dbgGet()` bodies now live in `.cpp`. `run/task488`'s T_488_10 claims "every key resolves" and covers ~60 %. | `gen/gen_get_keys.py:44`; §6.2 commands; `app/src/apps/webRadioApp.cpp:716` et al. | `*.h` → `*.[hc]*` at `gen/gen_get_keys.py:44`; re-run T_488_10 and expect new unknowns. |
| **A-4** | **P1** | Four independent `SerialDut` classes bypass `lib/dut.py` entirely — no DRD reset-gap stamp, no debug-firmware verify, no shell-cooldown drain, no `SetupFailure`. Three are behind documented `run/` entry points (`wr-gate`, `wr-soak`, `ae04`). Because none writes the gap file, running one immediately before `run/test` defeats the 12 s back-to-back-reset guard. | `test_adr045_gate.py:55`, `test_webradio_soak.py:55`, `test_webradio_long_soak.py:142`, `test_ae04_teardown.py:105`; gap file written only at `lib/dut.py:1156`, guard at `:115,:123`. | Migrate all four to `lib.dut.Dut`, subclassing for the reader-thread variants (the `DutLite` pattern at `screendump.py:36` is the precedent). |
| **A-5** | **P1** | `run/test-targeted` — the entry point CLAUDE.md directs you to for scoped work — skips the TLS-pin preflight that `run/test` runs as step 0 expressly to stop CA rotations presenting as cryptic fetch FAILs. `run/player-gate` skips it too. | `run/test:99`; `grep -c check-datatask-certs run/test-targeted run/player-gate` → 0, 0. | Move the preflight into `run/lib.sh` and call it from all three. |
| **A-6** | **P2** | `run_sync_tests.py` (20 ids, `run/test-sync`) carries a private pre-TASK-520 copy of `RESULTS`/`pass_`/`fail`/`skip` and its own summary. No flaky policy, no `FLAKY-PASS`, no `NOT-RUN`, no exit 4. This is the exact duplication `lib/results.py`'s docstring says it eliminated. | `run_sync_tests.py:370-382`, `:1344-1349`; `grep -c flake run_sync_tests.py` → 0. | Delete the private copy; import from `lib.results`, dispatch via `ve_suite_base.run_suite`. |
| **A-7** | **P2** | The results summary's per-id line is a **machine interface with no specification**. `run/player-gate` parses it with a `sed` regex; a missing token there already caused a false REGRESS verdict (TASK-573). A second producer emits the shape by coincidence. | Producer `lib/results.py:270`; consumer `run/player-gate:162`; incident recorded at `run/player-gate:150-158`; second producer `run_sync_tests.py:1348`. | Emit a machine-readable sidecar (`--results-json`) from `print_results` and have `player-gate` read that; keep the text for humans. Failing that, write the format down as an IFC and gate it with a `player-gate --selftest` case per token. |
| **A-8** | **P2** | **D1** — `clock.py` hardcodes app slots (`switchApp 1`/`0`/`4`) and does not import `app_ids_gen`, while its own switch helper `_switch_to_clock` returns `True` on the ack without verifying `appId`. A registry renumber would silently point the whole Clock family at the wrong app. | `clock.py:10-15`, `:11,20,27,152,153,201`; `shell.py:3302,3305`; `app/tools/app_ids_gen.py:4-5`. | `from app_ids_gen import APP_SLOT` in `clock.py`; make `_switch_to_clock` call `_helpers._switch_to`. |
| **A-9** | **P2** | **D4/D5** — stock tab and row coordinates are hardcoded (`_TAB_XY`, 48 literal taps) when they are a two-`#define` formula, and `stock.py` imports `coords` but uses it once. | `stock.py:756-760`; `app/src/stock/stockShared.h:38,46,47`; `grep -c '_c\.' stock.py` → 1 vs 48 literal taps. | Add `coords.stock_tab(t)` / `coords.stock_row(i)` parsing `stockShared.h` with the existing `coords.py:12 _parse`. |
| **A-10** | **P2** | **D6/D7** — `PR_FETCH_TYPE = 8` and `_PLAYER_MODES` mirror firmware enums with "keep in sync" comments, and D7's provenance cite is **wrong** (`kPmNames` is in `cmdSet.cpp`, not `cmdGet.cpp`). | `planeradar.py:267-269` vs `app/src/dataTask.h:20`; `health.py:66-68` vs `app/src/settingsStorage.h:21` / `app/src/debug/serialConsole/cmdSet.cpp:699`. | Add `parse_enum(path, enum_name)` and `parse_string_table(path, symbol)` to `shell_layout.py` (~30 lines) and import both. Fix the cite regardless. |
| **A-11** | **P2** | `lib/dut.TIMEOUT`/`TIMEOUT_SLOW` — the declared single timeout policy — has **zero users**, against 823 numeric `timeout=` literals in the suite (459 of them exactly the `3.0` default). The policy exists on paper only. | `lib/dut.py:47-48`; `grep -c 'TIMEOUT_SLOW\|dut\.TIMEOUT\|=TIMEOUT' suite/serialdbg/*.py` → 0 in all 15. | Change `Dut.cmd`/`read_json` defaults from `3.0` to `TIMEOUT` (behaviour-identical), then mechanically delete every `timeout=3.0` argument. That is 459 sites removed in one no-op commit. |
| **A-12** | **P2** | Three DUT scripts **execute their whole suite on `import`** — module-level `serial.Serial()` and test bodies, not behind `__main__`. Importing them resets the board. This is what caused §0's breach and it blocks any import-level lint or CI check over `app/tools/`. | `prloc_smoke.py:16,25`, `prloc_ve_smoke.py:45,71`, `settings_kit_smoke.py:35,56` (module-level `PORT = … resolve_port()` then `serial.Serial(PORT, …)`). Also `prloc_manual_smoke.py:29,56`, `prloc_editor_smoke.py:62,88`, `clock_tap_smoke.py:67,40` open at import. | Wrap every one in `if __name__ == "__main__": main()`. Six files, mechanical. |
| **A-13** | **P2** | 16 implementations of "enter an app and confirm arrival" and 57 hand-written bounded poll loops (11 of them named helpers). `_helpers.py` is 454 lines against 9 983 lines of family modules — the TASK-480 split distributed the bodies but never consolidated the helpers M-TOOLING §3 said it would. | §4.1 and §4.2 tables; `grep -c 'while time.monotonic()' suite/serialdbg/*.py` → 57. | One `wait_until(dut, key, pred, timeout, poll)` and one `enter_app(dut, name, *, via='tap'\|'cmd')` in `_helpers.py`; migrate family-by-family. Do this **before** M-TESTARCH §3b's `watch` primitive, so that lands in one place. |
| **A-14** | **P2** | Seven different defaults for `r.get("val", …)` in the suite; six of the seven are values a comparison can pass on. The S6 defaulting-oracle class has no shared accessor to close it. | §4.5 histogram, `suite/serialdbg/*.py`. | `Dut.get_int(key)` / `get_str(key)` in `lib/dut.py` that raise on a missing/absent `val`. |
| **A-15** | **P3** | `T_PLR_13` and `T_PLR_25` each have **two** executable bodies — one in the registry, one standalone — with different oracles and different reporting. `T_AE_04` has only a standalone body and no registry, so `check_docs` C6 cannot bind it through `test_registries()`. | `player.py:783` vs `test_fbrowser_player.py`; `player.py` (T_PLR_25) vs `test_playorder_player.py`; `test_ae04_teardown.py:2` and `docs/verification/test_plan.md:497`; `grep -n '^ALL\|^TESTS' test_ae04_teardown.py` → none. | Hand to **WP-B** (Q8) for the duplicate-test verdict; give `test_ae04_teardown.py` an `ALL_TESTS` so C6 sees it. |
| **A-16** | **P3** | Two byte-identical `main()` runners in `gate/`, and three different functions named `check` with three different signatures across the gate tests. | `gate/test_check_app_conformance.py:273-289` ≡ `gate/test_check_test_meta.py:234-250`; `gate/test_check_docs.py:35` vs `test_class_order.py:57` vs `test_boot_gate.py:35`. | One `gate/_cases.py` with `run_cases(CASES, name)`. |
| **A-17** | **P3** | `app/gen/mem_layout.py` is generated explicitly "for the test suite" and has zero importers repo-wide; `shell_layout.py` has zero suite importers; `coords` is imported-and-unused in `planeradar.py:8` and `teletext.py:8`. Generated infrastructure nobody consumes is worse than none — it reads as coverage. | `grep -rn 'mem_layout' --include=*.py` → only its own generator; `grep -c '_c\.' planeradar.py teletext.py` → 0, 0. | Either wire them in (A-9/A-10 give `shell_layout` a job) or delete `app/gen/mem_layout.py` and its `run/check` step. Drop the two dead imports. |
| **A-18** | **P3** | Nothing gates mirroring. `run/check` gates generated-output staleness and `golden.sha256`; `check_docs` C6 gates test-id binding; no gate asks whether a suite literal equals a firmware constant — which is why D1–D7 accumulated *after* LL-114 was closed. | §6.3. | A `gate/check_no_mirrors.py` seeded with the D1–D7 register: for each `(suite symbol, firmware symbol)` pair, assert equality at gate time. Cheap, and it converts every future mirror into a build failure instead of a silent drift. |
| **A-19** | **P3** | `run/check-datatask-certs`, `run/check-teletext-api`, `run/setup` and `run/test-smoke` do not source `run/lib.sh`. The first two are self-contained Python and arguably fine; `run/test-smoke` hardcodes an 11-id list (`run/test-smoke:5`) that is not derivable from the registry's `cls`. | `grep -c 'source .*lib\.sh' run/*`. | Once class ordering is switched on (TASK-566), replace the smoke list with a class/scope selection. |

**Counts: P1 × 5, P2 × 9, P3 × 5 — 19 findings.**

---

## 8. Could not be settled statically (NEEDS-DUT / NEEDS-DECISION)

| # | Question | Why static analysis cannot answer it |
|---|---|---|
| N-1 | Does the missing DRD gap stamp from the four `SerialDut` clones (A-4) actually drop this CYD into download mode in practice? | `lib/dut.py:150-155` says the *rationale* for the 12 s window is itself unresolved (DRD left the firmware in `ddf6433`; TASK-555 is re-deriving it). Whether the residual TASK-376 hazard is real needs a back-to-back `run/ae04; run/test` on hardware. |
| N-2 | How many of the 43 `get` keys `gen_get_keys.py` misses (A-3) actually fail T_488_10 once the glob is fixed? | Requires `run/task488` against the DUT. |
| N-3 | Do the 64 `time.sleep(0.3)` post-tap settles have a real failure rate today, or has firmware timing drifted enough that some are already too short? | Needs instrumented runs; M-TESTARCH §3b.6 proposes `get idle` as the cheap experiment. |
| N-4 | Whether `T_PLR_13`/`T_PLR_25`'s two bodies (A-15) agree — i.e. can one pass while the other fails? | Both must be run. Handed to WP-B/WP-E. |
| N-5 | Whether §0's board reset and injected taps disturbed a TASK-557 measurement window. | Needs the TASK-557 owner to check the log around 2026-09-02 ~18:50. |

Two items are decisions, not measurements: whether the summary text becomes a specified interface
or is replaced by a JSON sidecar (A-7), and whether `app/gen/mem_layout.py` is wired in or deleted
(A-17). Both are @Architect/@PM calls, not VE's.
