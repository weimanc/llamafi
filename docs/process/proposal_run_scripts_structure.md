# Proposal: Run Scripts Structure

> Owner: PM  
> Status: ADOPTED — implemented 2026-06-07. Decision: shell scripts (`run/`), Makefile rejected. See [proposal_run_shell.md](proposal_run_shell.md) for implementation detail.  
> Addresses: LL-056 (scattered process docs, no single executable entry point)  
> Last-minute adjustments: `run/test-sync` was initially mislabeled "host-only" — VE caught this during no-DUT validation; it requires DUT and was rewrapped with the full 6-step loop.

---

## Problem

A cold-start operator (human or agent) has no single executable reference for the
full workflow: port discovery → build → flash → test → monitor restore. The
canonical reference (`dut_workflow.md`) is excellent for reading but is not
executable — it contains raw multi-line shell snippets that require manual assembly.

---

## Decision: Shell scripts over Makefile

**Shell scripts win for this project.** Reasoning:

| Factor | Makefile | Shell scripts |
|--------|----------|---------------|
| Dynamic PORT (resolved at runtime via `udevadm`) | Awkward — `make` evaluates vars at parse time; shell expansion in recipes is clunky | Natural — scripts are pure bash, `PORT=$(...)` works as expected |
| Non-standard Python venv (`~/proj/esp/venv`) | Must pass as Make var or bake in; brittle | Baked into script constant, easy to override via env |
| PIO not on PATH (`~/.platformio/penv/bin/pio`) | Same — must define `PIO=...` everywhere | Same constant pattern; centralized in one `lib.sh` |
| tmux lifecycle (start/stop/read) | Make has no tmux concept; would be phony recipes calling shell functions | Direct bash — natural fit |
| Composability for agent invocation | Agents can't interactively invoke `make` targets cleanly | Scripts are discrete, predictable, directly callable |
| Existing precedent | `check_build.sh` already at root | Consistent with what's already there |

A Makefile would be a thin wrapper over shell anyway. The indirection buys nothing
here. One `lib.sh` + discrete per-operation scripts is cleaner.

---

## Proposed Folder Structure

```
run/                        ← new directory, all scripts executable
  lib.sh                    ← shared constants (PIO, VENV_PY, SESSION)
  port                      ← resolve and print the DUT port
  build                     ← build production firmware
  build-debug               ← build debug firmware
  flash                     ← flash production firmware to DUT
  flash-debug               ← flash debug firmware to DUT
  flash-fs                  ← upload SPIFFS partition only
  monitor-start             ← start tmux serial monitor
  monitor-stop              ← kill tmux serial monitor
  monitor-read              ← capture and print last N lines from monitor
  test                      ← run full serialdbg test suite
  test-smoke                ← run smoke preset (< 2 min)
  test-sync                 ← run sync tests (host-only, no DUT)
  validate                  ← full DUT validation cycle (steps 1-8 in order)
check_build.sh              ← stays at root (5-gate CI gate, existing)
```

`run/` scripts are thin — they source `run/lib.sh` then issue one logical operation.
No hidden sequencing inside leaf scripts except `validate`, which orchestrates the
full test cycle.

---

## `run/lib.sh` — Shared Constants

```sh
#!/usr/bin/env bash
# run/lib.sh — sourced by all run/* scripts. Not executed directly.

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIO="$HOME/.platformio/penv/bin/pio"
VENV_PY="$HOME/proj/esp/venv/bin/python3"
PIO_DIR="$PROJ_ROOT/app"
SESSION="spotify-mon"
ENV_PROD="cyd2usb_winamp"
ENV_DEBUG="cyd2usb_winamp_debug"

resolve_port() {
  local port
  port=$(ls /dev/ttyUSB* 2>/dev/null | while read p; do
    udevadm info -q property "$p" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" && echo "$p" && break
  done)
  [[ -n "$port" ]] || { echo "ERROR: CH340 device not found" >&2; exit 1; }
  echo "$port"
}
```

PORT is never hardcoded. Every script that needs it calls `resolve_port` at
invocation time. The operator can also override: `PORT=/dev/ttyUSB1 run/flash`.

---

## Named Targets

| Script | What it does | Calls |
|--------|-------------|-------|
| `run/port` | Print resolved port and exit | `resolve_port` |
| `run/build` | Production firmware compile | `pio run -e cyd2usb_winamp` |
| `run/build-debug` | Debug firmware compile | `pio run -e cyd2usb_winamp_debug` |
| `run/flash` | Kill monitor, flash prod, restart monitor | monitor-stop → pio upload → monitor-start |
| `run/flash-debug` | Kill monitor, flash debug | monitor-stop → pio upload (debug env) |
| `run/flash-fs` | Kill monitor, upload SPIFFS | monitor-stop → pio uploadfs |
| `run/monitor-start` | Start detached tmux session | `tmux new-session -d` |
| `run/monitor-stop` | Kill tmux session (releases port) | `tmux kill-session` |
| `run/monitor-read` | Dump last N lines (default 200) | `tmux capture-pane` |
| `run/test` | Full serialdbg suite | monitor-stop implied by caller |
| `run/test-smoke` | Smoke preset (T080,T083,…) | `run_serialdbg_tests.py --run <ids>` |
| `run/test-sync` | Host-only sync tests | `run_sync_tests.py` |
| `run/validate` | Full DUT validation cycle | Sequenced: monitor-stop → flash-debug → sleep 8 → test → flash → monitor-start |

`run/validate` is the answer to "how do I validate a new feature, steps 1-N" —
it is the executable form of `dut_workflow.md §5a`.

---

## `project_run_scripts.md` — Role and Placement

`docs/process/project_run_scripts.md` is the **operator quick-reference** for the
`run/` folder. It is not duplicated narrative — it contains:

1. How to run any script (`./run/port`, `PORT=... ./run/flash`, etc.)
2. The `run/validate` sequence written out as a numbered checklist
3. A one-liner table: script → purpose → §reference in `dut_workflow.md`

`dut_workflow.md` remains the authoritative reference (the "why"). `project_run_scripts.md`
is the entry point (the "how to invoke"). Cross-reference both ways:
- `dut_workflow.md` top: points to `project_run_scripts.md` for the executable entry point
- `project_run_scripts.md` top: defers to `dut_workflow.md` for rationale and failure modes

---

## Dynamic Port — Design Rules

1. PORT is never hardcoded in any script or doc.
2. `resolve_port()` in `lib.sh` is the single implementation (DRY).
3. All scripts that need PORT call it internally — the operator should not need to
   look up the port manually to run common operations.
4. Override escape hatch: `PORT=/dev/ttyUSBn ./run/flash` — scripts check `$PORT`
   first and skip `resolve_port` if already set.

---

## Implementation Notes

- All scripts: `set -euo pipefail`, `chmod +x`.
- `run/validate` calls sub-scripts via their paths, not shell functions, so each
  step is independently auditable in the log.
- No PlatformIO project directory `cd` inside scripts — use `-C` flags or
  subshells: `(cd "$PIO_DIR" && "$PIO" run ...)`.
- `run/monitor-start` uses the resolved PORT at start time — if the port changes
  between sessions, stop and restart the monitor.

---

## What This Does Not Change

- `check_build.sh` stays at root — it is a CI gate, not an operator workflow tool.
- `app/scripts/inject_git_hash.py` stays where it is — called by PlatformIO build hooks.
- `dut_workflow.md` is not restructured — it gains one cross-reference line only.
- Python tools in `app/tools/` are unchanged — scripts in `run/` call them.

---

## Comparison Summary — Proposal A (Makefile) vs Proposal B (`run/` scripts)

> Added by Architect + VE after reviewing both proposals.

1. **Both proposals converge on the same `run/` folder structure** — Proposal A's Makefile is a thin alias layer over the same scripts Proposal B defines directly; the scripts are the canonical implementation in both cases.
2. **Port resolution** is cleaner in shell: `PORT ?= $(shell ...)` in Make evaluates at parse time and has sub-make propagation quirks; `source run/port.sh` in bash is deterministic and composable.
3. **Restore guarantee (steps 5-6 after test failure)** is the decisive difference: `trap EXIT` in bash is bulletproof; the Makefile equivalent requires a shell subgroup `{ ...; RC=$$?; ...; exit $$RC; }` that is fragile and easy to break on extension.
4. **Discoverability**: Makefile wins — `make help` and tab-complete on `make` are more visible than `ls run/`. This is the main argument for keeping a thin Makefile as a front-end.
5. **Named arguments**: `make test-targeted TESTS=T080,T083` reads more naturally than `TESTS=T080,T083 ./run/test-targeted.sh`, though both work.
6. **Agent invocation**: Both are equivalent — one-word commands either way. Agents prefer the shell scripts because they can check `$?` and parse stdout without Make's decorator output.
7. **Dry-run**: `make -n` is a clear win for Makefile; shell scripts need a `DRY_RUN=1` convention added explicitly.
8. **Hybrid is optimal**: thin Makefile at root (discoverability, `make -n`, named vars) delegating to `run/` scripts (robustness, trap, readability). Zero duplication.
9. **This PM proposal already chose shell scripts** — Proposal B is the implementation target; Proposal A's Makefile sketch can be built on top as a convenience layer if PM decides the ergonomics are worth it.
10. **Recommendation**: implement `run/` scripts per this proposal and Proposal B; add a 10-target thin Makefile as a second pass only if agent/human ergonomics prove to need it.
