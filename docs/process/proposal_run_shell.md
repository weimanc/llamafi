# Proposal B — `run/` Shell Script Infrastructure

> Author: Verification Engineer  
> Status: ADOPTED — implemented 2026-06-07. This proposal was selected over Proposal A.  
> Companion: [Proposal A — Makefile](proposal_run_makefile.md) (rejected — see comparison summary)  
> Last-minute adjustments vs proposal: `run/test-sync` rewritten as a full 6-step DUT validation loop (was incorrectly described as host-only); `sleep 1` added after `tmux kill-session` in all flash scripts to ensure port release before pio upload.

---

## Motivation

The DUT workflow (`dut_workflow.md`) defines a strict 6-step validation sequence. Agents and humans routinely skip or mis-order steps, causing port contention errors, PRODUCTION FIRMWARE DETECTED failures, and DUT stuck in captive-portal mode. The solution is a `run/` folder of small, focused shell scripts that each own exactly one DUT operation, compose cleanly via sourcing, and enforce ordering in `run/test.sh`.

This design prioritises robustness of the validation loop above discoverability (cf. Makefile). It is the VE's primary recommendation because it allows `set -euo pipefail` + explicit `trap` for cleanup, which Makefiles cannot do cleanly.

---

## Folder Structure

```
run/
├── port.sh               # resolve + print CH340 port; sourceable
├── monitor-start.sh      # start spotify-mon tmux session
├── monitor-stop.sh       # kill spotify-mon (idempotent)
├── monitor-read.sh       # dump last N lines from spotify-mon pane
├── flash.sh              # kill monitor → flash prod → restart monitor
├── flash-debug.sh        # kill monitor → flash debug (no monitor restart)
├── flash-fs.sh           # kill monitor → uploadfs → restart monitor
├── test.sh               # full 6-step validation loop
├── test-targeted.sh      # targeted validation loop (accepts test IDs)
├── test-sync.sh          # host-only sync tests (no DUT)
├── check.sh              # thin wrapper around check_build.sh
└── bake-skin.sh          # bake Winamp skin assets
```

Every script:
- Has a `#!/usr/bin/env bash` shebang and `set -euo pipefail`
- Is executable (`chmod +x`)
- Sources `run/port.sh` if it needs the port (rather than re-implementing lookup)
- Prints `[script-name] step N/M — description` progress lines
- Exits non-zero on any failure

Naming convention: verb-noun, kebab-case, matching the DUT workflow section names. No `.sh` extension required for callers (`./run/test` works if the shebang is present), but `.sh` is kept for editor highlighting.

---

## `run/port.sh` — Port Resolution

This script is the single authoritative source of `PORT`. It can be **executed** (prints the port) or **sourced** (exports `PORT` into the calling environment).

```sh
#!/usr/bin/env bash
# run/port.sh — resolve CH340 port by VID:PID (1A86:7523)
# Usage: PORT=$(./run/port.sh)   OR   source ./run/port.sh

_resolve_port() {
  local p
  for p in /dev/ttyUSB*; do
    [ -e "$p" ] || continue
    udevadm info -q property "$p" 2>/dev/null \
      | grep -q "ID_VENDOR_ID=1a86" && echo "$p" && return 0
  done
  return 1
}

if [ -z "${PORT:-}" ]; then
  PORT=$(_resolve_port) || {
    echo "ERROR [port.sh]: CH340 not found. Check USB cable (VID:PID 1A86:7523)." >&2
    exit 1
  }
fi

export PORT

# When executed directly, print the result.
# When sourced, caller gets $PORT in environment.
[[ "${BASH_SOURCE[0]}" == "${0}" ]] && echo "$PORT"
```

The `${PORT:-}` guard means the script is a no-op if the caller has already exported `PORT` — useful for CI or multi-device setups where the caller manages port selection.

### Usage patterns

```sh
# Inspect port
./run/port.sh

# In another script
source "$(dirname "$0")/port.sh"
echo "Flashing to $PORT"

# Override for CI / multi-device
PORT=/dev/ttyUSB1 ./run/test.sh
```

---

## Tool Path Constants

A shared constants block is inlined at the top of each script that needs it (not a sourced file — keeping scripts self-contained for agent invocation):

```sh
PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIO_DIR="$PROJ_ROOT/app"
PIO="$HOME/.platformio/penv/bin/pio"
VENV_PY="$HOME/proj/esp/venv/bin/python3"
BOOT_WAIT="${BOOT_WAIT:-8}"
```

`BOOT_WAIT` is overridable via the environment — useful when running on a known-fast network where 5s is enough, or a slow network where 12s is needed.

---

## `run/test.sh` — Full 6-Step Validation Loop

This is the most important script in the folder. It implements BP-020 exactly, with a `trap` ensuring production firmware is always restored even if tests fail.

```sh
#!/usr/bin/env bash
# run/test.sh — Full DUT validation loop (BP-020)
# Usage: ./run/test.sh
#        BOOT_WAIT=12 ./run/test.sh
#        PORT=/dev/ttyUSB1 ./run/test.sh
# Exit code mirrors the test runner exit code.

set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIO_DIR="$PROJ_ROOT/app"
PIO="$HOME/.platformio/penv/bin/pio"
VENV_PY="$HOME/proj/esp/venv/bin/python3"
BOOT_WAIT="${BOOT_WAIT:-8}"

# ── Resolve port ──────────────────────────────────────────────────────────────
source "$PROJ_ROOT/run/port.sh"

# ── Cleanup trap — always restores prod firmware + monitor ────────────────────
_TEST_RC=0
_cleanup() {
  local rc=$_TEST_RC
  echo ""
  echo "[test] step 5/6 — restoring production firmware (rc=$rc so far)"
  cd "$PIO_DIR"
  "$PIO" run -e cyd2usb_winamp -t upload --upload-port "$PORT" || {
    echo "ERROR [test]: prod restore failed — DUT is still in debug firmware" >&2
    rc=99
  }

  echo "[test] step 6/6 — restarting monitor"
  tmux new-session -d -s spotify-mon \
    "cd $PIO_DIR && $PIO device monitor -e cyd2usb_winamp -p $PORT" \
    2>/dev/null || echo "WARN [test]: monitor start failed (tmux issue?)" >&2

  exit "$rc"
}
trap _cleanup EXIT INT TERM

# ── Step 1 — kill monitor ─────────────────────────────────────────────────────
echo "[test] step 1/6 — killing monitor"
tmux kill-session -t spotify-mon 2>/dev/null || true

# ── Step 2 — flash debug firmware ────────────────────────────────────────────
echo "[test] step 2/6 — flashing debug firmware"
cd "$PIO_DIR"
"$PIO" run -e cyd2usb_winamp_debug -t upload --upload-port "$PORT"

# ── Step 3 — wait for boot + WiFi settle ─────────────────────────────────────
echo "[test] step 3/6 — waiting ${BOOT_WAIT}s for boot + WiFi"
sleep "$BOOT_WAIT"

# ── Step 4 — run tests ────────────────────────────────────────────────────────
echo "[test] step 4/6 — running full test suite"
"$VENV_PY" tools/run_serialdbg_tests.py --port "$PORT" || _TEST_RC=$?

# EXIT trap fires here — steps 5 and 6 run unconditionally
```

Key design decisions:

1. **`trap _cleanup EXIT`** — the cleanup function fires on `EXIT`, `INT` (Ctrl-C), and `TERM`. This means `set -e` triggering on any unexpected failure (e.g. flash fails in step 2) will still reach the trap, which restores prod and restarts the monitor. This is the primary advantage over the Makefile approach.

2. **`_TEST_RC` pattern** — the test runner's exit code is captured before the trap runs `set -e`-safe subsequent steps. The trap forwards this exit code as the script's final exit code. Agents can check `$?` from `./run/test.sh` and know whether tests passed or failed, independent of whether prod-restore succeeded.

3. **No `set -e` inside `_cleanup`** — the cleanup function should not abort on partial failure; it logs and continues to the next restore step.

4. **`cd "$PIO_DIR"` inside the trap** — the working directory may have changed between step 3 and the trap invocation. Explicitly `cd` before every `pio` call.

---

## `run/test-targeted.sh` — Targeted Validation Loop

```sh
#!/usr/bin/env bash
# run/test-targeted.sh — Targeted DUT validation (BP-021)
# Usage: ./run/test-targeted.sh T080,T083,T091
#        TESTS=T080,T083 ./run/test-targeted.sh
# Runs the same 6-step loop as test.sh but with --run filter.

set -euo pipefail

PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIO_DIR="$PROJ_ROOT/app"
PIO="$HOME/.platformio/penv/bin/pio"
VENV_PY="$HOME/proj/esp/venv/bin/python3"
BOOT_WAIT="${BOOT_WAIT:-8}"
TESTS="${TESTS:-${1:-}}"

[ -n "$TESTS" ] || {
  echo "Usage: $0 T080,T083  OR  TESTS=T080,T083 $0" >&2
  exit 1
}

source "$PROJ_ROOT/run/port.sh"

_TEST_RC=0
_cleanup() {
  local rc=$_TEST_RC
  echo "[test-targeted] step 5/6 — restoring production firmware"
  cd "$PIO_DIR"
  "$PIO" run -e cyd2usb_winamp -t upload --upload-port "$PORT" || rc=99
  echo "[test-targeted] step 6/6 — restarting monitor"
  tmux new-session -d -s spotify-mon \
    "cd $PIO_DIR && $PIO device monitor -e cyd2usb_winamp -p $PORT" 2>/dev/null || true
  exit "$rc"
}
trap _cleanup EXIT INT TERM

echo "[test-targeted] running: $TESTS"
tmux kill-session -t spotify-mon 2>/dev/null || true
cd "$PIO_DIR"
"$PIO" run -e cyd2usb_winamp_debug -t upload --upload-port "$PORT"
sleep "$BOOT_WAIT"
"$VENV_PY" tools/run_serialdbg_tests.py --port "$PORT" --run "$TESTS" || _TEST_RC=$?
```

---

## Agent Invocation — Single Command for Full Validation Loop

An agent (or human) running the full validation cycle issues exactly:

```sh
cd /home/weiman/proj/esp_spotify && ./run/test.sh
```

For targeted validation after implementing a single feature:

```sh
./run/test-targeted.sh T-SET-01,T-SET-02,T-SET-03,T-SET-06,T-SET-07,T-SET-08
```

For the quick smoke preset:

```sh
TESTS=T080,T083,T091,T092,T133,T147,T148,T162,T-SET-01,T-SET-02,T-SET-08 \
  ./run/test-targeted.sh
```

No path manipulation, no PORT export, no manual tmux session management. The script handles it all.

---

## Other Script Sketches

### `run/flash.sh`

```sh
#!/usr/bin/env bash
set -euo pipefail
PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIO_DIR="$PROJ_ROOT/app"
PIO="$HOME/.platformio/penv/bin/pio"
source "$PROJ_ROOT/run/port.sh"

echo "[flash] killing monitor"
tmux kill-session -t spotify-mon 2>/dev/null || true
echo "[flash] flashing production firmware to $PORT"
cd "$PIO_DIR"
"$PIO" run -e cyd2usb_winamp -t upload --upload-port "$PORT"
echo "[flash] restarting monitor"
tmux new-session -d -s spotify-mon \
  "cd $PIO_DIR && $PIO device monitor -e cyd2usb_winamp -p $PORT"
echo "[flash] done"
```

### `run/monitor-stop.sh`

```sh
#!/usr/bin/env bash
# Idempotent — safe to call when monitor is not running.
tmux kill-session -t spotify-mon 2>/dev/null || true
echo "[monitor-stop] done"
```

### `run/check.sh`

```sh
#!/usr/bin/env bash
PROJ_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$PROJ_ROOT/check_build.sh"
```

---

## Tradeoffs vs Makefile

| Dimension | `run/` scripts | Makefile |
|-----------|---------------|----------|
| try/finally (restore on failure) | Native `trap EXIT` | Requires shell subgroup trick |
| Discoverability | `ls run/` or tab-complete | `make help` (if implemented) |
| Named arguments | Positional / env vars | `make test TESTS=...` |
| Dry-run | Not built-in (add `DRY_RUN=1` toggle) | `make -n` |
| Dependency tracking | Not applicable here | Inapplicable (no file targets) |
| Sub-process PORT propagation | `source port.sh` or `export PORT` | `$(MAKE) PORT=$(PORT)` pass-through |
| Agent invocation complexity | `./run/test.sh` | `make test` |
| Error messages | Full shell control | Make hides recipe output by default |
| Parallel-job risk | None (each script is sequential) | `make -j` can mis-order targets |
| Entry point at project root | No (must `cd` to root or use path) | Yes (`make` from anywhere in tree) |
| Windows compatibility | Bash-only | Also bash-only here |
| Test isolation | Natural (new shell per script) | Natural (new shell per recipe) |

The primary VE recommendation is the `run/` approach because:

1. The 6-step test loop's **restore guarantee** is critical for DUT hygiene. A debug-firmware DUT left running after a test failure will hit `PRODUCTION FIRMWARE DETECTED` on the next test run — a confusing cascade. `trap EXIT` is the cleanest way to prevent this.
2. Scripts are independently readable and reviewable. An agent reading `run/test.sh` sees the entire validation procedure in one file, not scattered across Makefile syntax.
3. The scripts can be tested individually (unit-testable steps) and composed in CI pipelines without requiring Make.

---

## Comparison Summary Pending PM Proposal

Proposal A (Makefile) and Proposal B (`run/` scripts) are not mutually exclusive. A thin Makefile at the project root can expose `make test` / `make flash` etc. as human-friendly aliases that delegate to the `run/` scripts for actual execution. This hybrid gives:

- Discoverability via `make help` (Makefile strength)
- Robustness via `trap EXIT` in shell (shell strength)
- Single canonical implementation (no duplication)

PM to decide: implement one approach, both, or the hybrid. Architect and VE can design the hybrid if requested.
