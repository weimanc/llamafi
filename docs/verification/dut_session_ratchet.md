# `serial.Serial(` constructions outside `lib/` — the R47 ratchet

> Owner: **@Developer** · Machine-read by `app/tools/gate/check_dut_session.py` ·
> Opened **2026-09-20** · Programme: [M-HARNESS2](M-HARNESS2-requirements.md) R47, TASK-599

## What this file is

[R47](M-HARNESS2-requirements.md:781-786) ("one DUT session layer. MUST.") asks that all DUT access
go through `app/tools/lib/dut.py`'s shared session (`Dut`, `resolve_port`, the `TIMEOUT`/
`TIMEOUT_SLOW` policy from [R24](timeout_literal_ratchet.md)) — no tool constructs its own serial
session. Measured 2026-09-20 with
`grep -rln 'serial\.Serial(' app/tools --include='*.py' | wc -l` -> **20 files**. Three are the
session layer itself and the checker that polices import-time board access, never findings:
`app/tools/lib/dut.py` (the session layer), `app/tools/gate/check_import_safety.py` and
`app/tools/gate/test_check_import_safety.py` (TASK-609/R48 — they mention the string because their
whole job is stubbing it out at import time; the gate is now AST-based, so this exemption is
structural, not a hand-kept allowlist — see `check_dut_session.py`'s module docstring). That leaves
**17 tools**, 19 construction sites (`run_sync_tests.py` and `test_adr045_gate.py` each construct
twice — an initial open plus a reconnect-after-reboot path). Recount with
`~/proj/esp/venv/bin/python app/tools/gate/check_dut_session.py --verbose`.

WP-A's `A-4` names four of these — `test_adr045_gate.py`, `test_webradio_soak.py`,
`webradio_long_soak.py`, `test_ae04_teardown.py` — as "four independent `SerialDut` classes [that]
bypass `lib/dut.py` entirely": no DRD reset-gap stamp, no debug-firmware verify, no shell-cooldown
drain, no `SetupFailure`. Three sit behind documented `run/` entry points (`wr-gate`, `wr-soak`,
`ae04`), so a bypassing run immediately before `run/test` defeats the 12s back-to-back-reset guard
(`lib/dut.py:115,123,1156`). `A-2` names a related but distinct gap — the `SetupFailure` -> exit-3
rig/firmware contract is honoured by only 4 files tree-wide — that this ledger does not by itself
close (see "What TASK-599 did NOT do" below).

## Why this landed as a ratchet, not a migration (TASK-599's finding)

Unlike [R24](timeout_literal_ratchet.md)'s `timeout=` literals, a `serial.Serial(...)` call site is
not a value that can be swapped for a named constant with the same effect. `lib.dut.Dut.__init__`
does substantially more than open a port: it enforces the DRD reset-gap wait, then calls
`_wait_for_ready()` (a firmware-readiness poll), `_verify_debug_firmware()` (an ELF/build-id check
against the debug env — TASK-608/R30) and `_read_board_id()` (a `get boardId` round-trip — TASK-645)
before the constructor returns. Swapping a hand-rolled class for `Dut` therefore changes what
happens to the device on open, not just how the code is spelled — and TASK-599 ran with **no
hardware attached**, so no such change could be exercised and confirmed behaviour-preserving. Per
its own ruling ("prefer a small number of carefully-verified migrations over many unverifiable
ones... a tool that needs raw byte-level access ... may not fit the session layer — say so per
file"), it landed the gate and ledgered all 17 with the specific structural reason each one does not
fit `Dut`/`DutLite` (the `screendump.py:36` precedent) today, rather than forcing 17 unverifiable
rewrites. **Zero were migrated in this pass** — the ledger is the honest count of the gap, not a
finding to be argued away.

## Rows

| module | cap | owner | since | why it does not fit `Dut`/`DutLite` today |
|---|---|---|---|---|
| `test_adr045_gate.py` | 2 | TASK-599 | 2026-09-20 | `A-4`. Purpose-built continuous background reader thread (`SerialDut._reader`) that tees every line, host-timestamps `[wifi-ev]`/fail/ok/boot signatures as they arrive, and never calls `reset_input_buffer()` — the docstring calls this out explicitly as a "VE-1 blocker fix" over the request/response shape `Dut.cmd()` uses. A `reboot()` path re-opens the port directly without the DRD gap wait, by design (the attribution logic needs the exact reboot timestamp). |
| `test_webradio_soak.py` | 1 | TASK-599 | 2026-09-20 | `A-4`. Same `SerialDut` continuous-reader shape as `test_adr045_gate.py`, tuned with a 0.4s pyserial read timeout for soak-scale polling; migrating to `Dut`'s synchronous `cmd()` queue would drop the async event capture this soak depends on. |
| `webradio_long_soak.py` | 1 | TASK-599 | 2026-09-20 | `A-4`. Same `SerialDut` family (`raw_log_path`-backed tee), long-run soak variant behind `run/wr-soak`. |
| `test_ae04_teardown.py` | 1 | TASK-599 | 2026-09-20 | `A-4`. Same `SerialDut` family, 0.3s pyserial timeout tuned for the teardown-ordering probe's tighter polling window. |
| `prloc_smoke.py` | 1 | TASK-599 | 2026-09-20 | Hand-rolled `Dut.wait_event()` reads raw lines directly off `self.ser` outside `cmd()`'s reply path to catch async `evt` lines mid-sequence; `lib.dut.Dut`'s `_TeeSerial` wraps the stream for its own tee/ring-buffer bookkeeping and offers no equivalent raw-line async-event API. |
| `prloc_ve_smoke.py` | 1 | TASK-599 | 2026-09-20 | Same `wait_event()`-on-raw-lines shape as `prloc_smoke.py`. |
| `prloc_manual_smoke.py` | 1 | TASK-599 | 2026-09-20 | Same `wait_event()`-on-raw-lines shape as `prloc_smoke.py`. |
| `prloc_editor_smoke.py` | 1 | TASK-599 | 2026-09-20 | Same `wait_event()`-on-raw-lines shape as `prloc_smoke.py`. |
| `settings_kit_smoke.py` | 1 | TASK-599 | 2026-09-20 | Same hand-rolled `Dut` shape (raw-line polling for async confirmation events) as the `prloc_*` family. |
| `clock_tap_smoke.py` | 1 | TASK-599 | 2026-09-20 | Minimal hand-rolled `Dut` with a bespoke `cmd()` loop; TASK-609/R48 already wrapped its executable body behind `if __name__ == "__main__":`. Migrating changes the readiness contract (`Dut` adds an ELF check + board-id read this smoke test never made) with no hardware available to confirm the tap-injection timing still holds. |
| `exp012_measure.py` | 1 | TASK-599 | 2026-09-20 | `SerialDut` opened with a 0.4s pyserial timeout deliberately tuned for EXP-012's measurement cadence; `Dut`'s readiness sequence (boot wait + ELF verify + board-id read) adds device round-trips ahead of the measurement window this tool is timing. |
| `run_sync_tests.py` | 2 | TASK-599 | 2026-09-20 | Its own `Dut._wait_for_ready()` waits for a Spotify-specific readiness signal ("first SUCCESSFUL Spotify poll + queue fetch") that `lib.dut.Dut`'s generic wait does not check — and per `screendump.py:36-49`'s `DutLite`, that exact Spotify-poll wait is known to time out under TASK-243's Premium lapse, which is why `DutLite` was written to skip it. Migrating this file onto plain `Dut` would silently drop the readiness signal `run_sync_tests.py` is built around. The second construction (~line 925) is a mid-run reconnect after `tsync_diff.py` reboots the DUT on its own port open — coupled to that subprocess's behaviour, not just this file's. |
| `tsync_diff.py` | 1 | TASK-599 | 2026-09-20 | Own `Dut` class with a 5.0s timeout, invoked as a subprocess by `run_sync_tests.py` specifically to reboot the DUT and read a fresh sync snapshot; `run_sync_tests.py`'s comment above its reconnect ("tsync_diff.py rebooted DUT on its port open and left it in steady state") shows the reboot-on-open is load-bearing for the caller, not incidental. |
| `sd_put.py` | 1 | TASK-599 | 2026-09-20 | `Dut.__init__(self, port, boot_wait)` takes a caller-supplied `boot_wait`, not a firmware-readiness poll — an SD-file-push utility invoked from `run/spiffs`-adjacent tooling where the caller already knows how long to wait. `Dut`'s ELF/board-id checks assume a full debug-console handshake this one-shot utility doesn't otherwise need. |
| `test_fbrowser_player.py` | 1 | TASK-599 | 2026-09-20 | No wrapper class at all — `serial.Serial(args.port, args.baud, timeout=1.0)` opened directly in `main()` with an argparse-supplied `--baud`, then driven by free functions (`cmd(ser, ...)`). Folding it into `Dut` is a bigger rewrite (module-level function signatures all take `ser`, not a `Dut`) than a call-site swap. |
| `test_playorder_player.py` | 1 | TASK-599 | 2026-09-20 | Same no-class, argparse-`--baud`, free-function shape as `test_fbrowser_player.py`. |
| `probe/rig_ladder.py` | 1 | TASK-599 | 2026-09-20 | Targets a DIFFERENT physical rig entirely — a bare test board flashed with the `bare` PlatformIO env (not the CYD's `cyd2usb_*` debug console), reset via a manual RTS/EN pulse (`s.rts = True` then `False`) rather than the CYD's DTR-reset-on-open convention. `lib.dut.Dut` assumes the CYD debug-console protocol (`get boardId`, ELF/build-id verify) which this rig does not speak at all — it is not "the DUT" R47 means. |

**Total: 17 modules, 19 constructions** on the day this ledger was opened. Zero migrated in TASK-599
(see "Why this landed as a ratchet" above) — every row is a structural reason, not a promise.

## What TASK-599 did NOT do

`A-2` (eight bare `Dut()` constructors that let `SetupFailure` escape as an uncaught traceback
instead of the exit-3 rig/firmware contract) is a **different** finding from the `serial.Serial(`
constructions this ledger prices — those eight already use `lib.dut.Dut`, so `check_dut_session.py`
correctly does not count them. TASK-599's board row cites both `A-2` and `A-4`, but this pass's
scope (the gate + ledger this file backs) is `A-4`'s shape: raw session construction outside `lib/`.
`A-2`'s exit-contract gap is tracked separately (see `docs/project/tasks-harness2.md`'s TASK-599 row
and TASK-601, which is blocked on this task).

## How to shrink a row

A row drops to 0 and is deleted only when hardware is available to verify the replacement session
preserves the tool's actual behaviour (same commands, same order, same effective timeouts) — not by
editing the count. If a future pass finds a smaller `DutLite`-shaped subclass that covers one of the
"continuous reader thread" rows (`test_adr045_gate.py`, `test_webradio_soak.py`,
`webradio_long_soak.py`, `test_ae04_teardown.py`) without dropping the async event capture, that is
the most promising lever — `A-4`'s own recommendation names the `DutLite` pattern as precedent for
"subclassing for the reader-thread variants". `run_sync_tests.py`/`tsync_diff.py`'s pairing (one
reboots, the other expects it) should migrate together or not at all.

## Findings this gate raises

| code | condition |
|---|---|
| T1 | a module's `serial.Serial(` count exceeds its ledgered cap |
| T2 | a ledger row's cap sits above the module's real count (stale — shrink it) |
| T3 | a row names a module that does not exist under `app/tools/` (outside `lib/`) |
| T4 | a row without an owning `TASK-` id and an ISO `since` date, or with a wildcard |
| T5 | a row names a file under `lib/`, or one of the two `check_import_safety`-family files — those are structurally exempt and must never carry a row |
