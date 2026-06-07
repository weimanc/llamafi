# Proposal A — Makefile-Based Run Infrastructure

> Author: Architect  
> Status: REJECTED — 2026-06-07. Shell scripts (`run/`) selected instead. Primary reason: `trap EXIT` restore guarantee cannot be cleanly replicated in Make recipes. See comparison summary in [proposal_run_scripts_structure.md](proposal_run_scripts_structure.md).  
> Companion: [Proposal B — Shell scripts](proposal_run_shell.md) (adopted)

---

## Motivation

The DUT workflow (`dut_workflow.md`) is currently a narrative document: humans and agents read it and execute commands by hand. Any deviation (e.g., forgetting to kill the monitor before flashing, hardcoding a port) causes a hard-to-diagnose failure. A `Makefile` at the project root gives every operation a canonical name, enforces ordering via prerequisites, and is invocable by both humans and agents with a single short command.

---

## Design Goals

1. **One canonical verb per DUT operation** — `make flash`, `make monitor`, `make test`, etc.
2. **Port is resolved once, propagated automatically** — no manual `PORT=...` exports.
3. **Non-standard tool paths are encapsulated** — callers never type `~/.platformio/penv/bin/pio`.
4. **`check_build.sh` is a first-class citizen** — `make check` calls it; other targets do not re-implement its logic.
5. **Idempotent teardown** — `make monitor-stop` is safe to call even when no monitor is running.

---

## Port Resolution Pattern

The CH340 is identified by VID:PID `1A86:7523`. `udevadm` is used for reliable lookup (BP-019). Port resolution must happen exactly once per Make invocation and be re-used by all sub-targets that need it.

The canonical pattern is a recursively-expanded variable guarded by a shell-call:

```make
PORT ?= $(shell \
  for p in $$(ls /dev/ttyUSB* 2>/dev/null); do \
    udevadm info -q property "$$p" 2>/dev/null \
      | grep -q "ID_VENDOR_ID=1a86" && echo "$$p" && break; \
  done)
```

Because `$(shell ...)` is evaluated lazily on first use, and because Make evaluates each variable only once per run, this executes exactly once. If the user has already exported `PORT` in their shell, the `?=` assignment honours it — useful for CI or when two devices are plugged in and the wrong one would be auto-selected.

A dedicated `port` target lets agents and humans inspect what was resolved:

```make
.PHONY: port
port:
	@[ -n "$(PORT)" ] || { echo "ERROR: CH340 not found — check USB connection"; exit 1; }
	@echo "$(PORT)"
```

---

## Target Inventory

| Target | Description |
|--------|-------------|
| `make port` | Print resolved CH340 port (errors if not found) |
| `make build` | Build production firmware only |
| `make build-debug` | Build debug firmware only |
| `make check` | Run `check_build.sh` (5-gate build check) |
| `make flash` | Kill monitor → build prod → flash prod → restart monitor |
| `make flash-debug` | Kill monitor → build debug → flash debug (no monitor restart) |
| `make flash-fs` | Kill monitor → upload SPIFFS → restart monitor |
| `make monitor` | Start `spotify-mon` tmux session (errors if already running) |
| `make monitor-stop` | Kill `spotify-mon` tmux session (idempotent) |
| `make monitor-read` | Dump last 200 lines from `spotify-mon` pane |
| `make test` | Full 6-step validation loop (see below) |
| `make test-targeted TESTS=T080,T083` | Targeted test run (steps 1-6, filtered) |
| `make test-sync` | Host-only sync tests (no DUT required) |
| `make bake-skin` | Run `bake_skin.py` with project venv |

`.DEFAULT_GOAL := check` — running bare `make` runs the build check, which is always safe.

---

## How Non-Standard Paths Are Handled

```make
PIO      := $(HOME)/.platformio/penv/bin/pio
VENV_PY  := $(HOME)/proj/esp/venv/bin/python3
PIO_DIR  := $(CURDIR)/app
PROJ_ROOT := $(CURDIR)
```

These are defined once at the top of the Makefile. All recipe lines reference `$(PIO)` and `$(VENV_PY)` — never the literal paths. This makes the Makefile portable across machines that share the same conventions (new dev board, CI runner) while keeping the paths overridable:

```sh
make flash PIO=/opt/custom/pio
```

---

## Composing with `check_build.sh`

`check_build.sh` already implements the 5-gate build check correctly. The Makefile wraps it rather than replicating it:

```make
.PHONY: check
check:
	$(PROJ_ROOT)/check_build.sh
```

`make flash` does **not** call `check` as a prerequisite — that would make every flash slow. Instead, agents and humans are expected to run `make check` before committing structural changes (BP-008), and `make flash` before testing.

---

## The `flash` Target and Its Ordering Dependencies

Flash targets must enforce the kill-before-flash invariant as a recipe sequence (not Make prerequisites, which run in parallel by default):

```make
.PHONY: flash
flash: _require-port
	@echo "[flash] killing monitor..."
	tmux kill-session -t spotify-mon 2>/dev/null; true
	@echo "[flash] building production firmware..."
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp --silent
	@echo "[flash] flashing..."
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp -t upload --upload-port $(PORT)
	@echo "[flash] restarting monitor..."
	$(MAKE) monitor

.PHONY: flash-debug
flash-debug: _require-port
	tmux kill-session -t spotify-mon 2>/dev/null; true
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug --silent
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug -t upload --upload-port $(PORT)
```

The helper `_require-port` guards every DUT target:

```make
.PHONY: _require-port
_require-port:
	@[ -n "$(PORT)" ] || { \
	  echo "ERROR: CH340 port not found. Check USB cable or set PORT=/dev/ttyUSBx"; \
	  exit 1; \
	}
```

---

## The `test` and `test-targeted` Targets

The 6-step validation sequence from `dut_workflow.md §5a` maps directly to a recipe:

```make
BOOT_WAIT := 8

.PHONY: test
test: _require-port
	@echo "[test] step 1/6 — kill monitor"
	tmux kill-session -t spotify-mon 2>/dev/null; true
	@echo "[test] step 2/6 — flash debug firmware"
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug -t upload --upload-port $(PORT)
	@echo "[test] step 3/6 — wait $(BOOT_WAIT)s for boot + WiFi"
	sleep $(BOOT_WAIT)
	@echo "[test] step 4/6 — run full test suite"
	cd $(PIO_DIR) && $(VENV_PY) tools/run_serialdbg_tests.py --port $(PORT)
	@echo "[test] step 5/6 — restore production firmware"
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp -t upload --upload-port $(PORT)
	@echo "[test] step 6/6 — restart monitor"
	$(MAKE) monitor

.PHONY: test-targeted
test-targeted: _require-port
ifndef TESTS
	$(error TESTS is not set. Usage: make test-targeted TESTS=T080,T083)
endif
	tmux kill-session -t spotify-mon 2>/dev/null; true
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug -t upload --upload-port $(PORT)
	sleep $(BOOT_WAIT)
	cd $(PIO_DIR) && $(VENV_PY) tools/run_serialdbg_tests.py --port $(PORT) --run $(TESTS)
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp -t upload --upload-port $(PORT)
	$(MAKE) monitor
```

Note: if step 4 fails (tests fail), Make stops immediately — steps 5 and 6 do **not** run, leaving the DUT in debug firmware with no monitor. This is a fundamental Makefile limitation (recipes are not try/finally). A workaround is to put steps 5 and 6 in a shell trap:

```make
	@{ \
	  cd $(PIO_DIR) && $(VENV_PY) tools/run_serialdbg_tests.py --port $(PORT); \
	  TEST_RC=$$?; \
	  $(PIO) run -e cyd2usb_winamp -t upload --upload-port $(PORT); \
	  $(MAKE) -s monitor; \
	  exit $$TEST_RC; \
	}
```

This is the recommended approach — restore always runs, exit code reflects test result.

---

## Full Makefile Sketch

```make
# =============================================================================
# Spotify-Diy-Thing — project-root Makefile
# =============================================================================

.DEFAULT_GOAL := check

PROJ_ROOT := $(CURDIR)
PIO_DIR   := $(PROJ_ROOT)/app
PIO       := $(HOME)/.platformio/penv/bin/pio
VENV_PY   := $(HOME)/proj/esp/venv/bin/python3
BOOT_WAIT := 8

# ── Port resolution ───────────────────────────────────────────────────────────
PORT ?= $(shell \
  for p in $$(ls /dev/ttyUSB* 2>/dev/null); do \
    udevadm info -q property "$$p" 2>/dev/null \
      | grep -q "ID_VENDOR_ID=1a86" && echo "$$p" && break; \
  done)

.PHONY: port
port:
	@[ -n "$(PORT)" ] || { echo "ERROR: CH340 not found"; exit 1; }
	@echo "$(PORT)"

.PHONY: _require-port
_require-port:
	@[ -n "$(PORT)" ] || { \
	  echo "ERROR: CH340 not found. Check USB or set PORT=/dev/ttyUSBx"; exit 1; }

# ── Build ─────────────────────────────────────────────────────────────────────
.PHONY: check build build-debug
check:
	$(PROJ_ROOT)/check_build.sh

build:
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp --silent

build-debug:
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug --silent

# ── Monitor ───────────────────────────────────────────────────────────────────
.PHONY: monitor monitor-stop monitor-read
monitor:
	tmux new-session -d -s spotify-mon \
	  "cd $(PIO_DIR) && $(PIO) device monitor -e cyd2usb_winamp -p $(PORT)"

monitor-stop:
	tmux kill-session -t spotify-mon 2>/dev/null; true

monitor-read:
	tmux capture-pane -t spotify-mon -p -S -200

# ── Flash ─────────────────────────────────────────────────────────────────────
.PHONY: flash flash-debug flash-fs
flash: _require-port
	tmux kill-session -t spotify-mon 2>/dev/null; true
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp --silent
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp -t upload --upload-port $(PORT)
	$(MAKE) -s monitor

flash-debug: _require-port
	tmux kill-session -t spotify-mon 2>/dev/null; true
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug --silent
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug -t upload --upload-port $(PORT)

flash-fs: _require-port
	tmux kill-session -t spotify-mon 2>/dev/null; true
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp -t uploadfs --upload-port $(PORT)
	$(MAKE) -s monitor

# ── Test ──────────────────────────────────────────────────────────────────────
.PHONY: test test-targeted test-sync
test: _require-port
	@echo "[1/6] kill monitor"; tmux kill-session -t spotify-mon 2>/dev/null; true
	@echo "[2/6] flash debug"
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug -t upload --upload-port $(PORT)
	@echo "[3/6] wait $(BOOT_WAIT)s"; sleep $(BOOT_WAIT)
	@echo "[4/6] run tests + cleanup (trap ensures restore on failure)"
	@{ \
	  cd $(PIO_DIR) && $(VENV_PY) tools/run_serialdbg_tests.py --port $(PORT); RC=$$?; \
	  echo "[5/6] restore prod"; \
	  $(PIO) run -e cyd2usb_winamp -t upload --upload-port $(PORT); \
	  echo "[6/6] restart monitor"; \
	  $(MAKE) -s monitor; \
	  exit $$RC; \
	}

test-targeted: _require-port
ifndef TESTS
	$(error Usage: make test-targeted TESTS=T080,T083)
endif
	@echo "[1/6] kill monitor"; tmux kill-session -t spotify-mon 2>/dev/null; true
	@echo "[2/6] flash debug"
	cd $(PIO_DIR) && $(PIO) run -e cyd2usb_winamp_debug -t upload --upload-port $(PORT)
	@echo "[3/6] wait $(BOOT_WAIT)s"; sleep $(BOOT_WAIT)
	@{ \
	  cd $(PIO_DIR) && $(VENV_PY) tools/run_serialdbg_tests.py --port $(PORT) --run $(TESTS); RC=$$?; \
	  echo "[5/6] restore prod"; \
	  $(PIO) run -e cyd2usb_winamp -t upload --upload-port $(PORT); \
	  echo "[6/6] restart monitor"; \
	  $(MAKE) -s monitor; \
	  exit $$RC; \
	}

test-sync:
	cd $(PIO_DIR) && $(VENV_PY) tools/run_sync_tests.py

# ── Skin bake ─────────────────────────────────────────────────────────────────
.PHONY: bake-skin
bake-skin:
	$(VENV_PY) $(PIO_DIR)/tools/bake_skin.py \
	  -i $(PIO_DIR)/skins/base-2.91.wsz -o $(PIO_DIR)/gen

# =============================================================================
```

---

## Tradeoffs

### What Makefiles handle well in this context

- **Named targets as documentation.** `make flash` is more memorable than the full pio invocation. Agents can call `make test-targeted TESTS=T080` without knowing the underlying tool paths.
- **Variable inheritance.** `PORT ?= ...` lets CI or a user override the port without editing the file.
- **Dry-run.** `make -n flash` prints every command without executing — useful for auditing what would happen.
- **Dependency tracking.** When a `.o`-style dependency model applies (it mostly doesn't here, but `make build` skipping when `.pio/build/` is fresh does save time).
- **Single entry point.** One file at the project root; no PATH changes needed.

### What Makefiles handle poorly in this context

- **No try/finally natively.** The restore-prod step after a failing test suite requires a shell subgroup with `RC=$$?` / `exit $$RC` trick (shown above). Easy to get wrong; fragile if extended.
- **Error messages are sparse.** Make prints the failing recipe line but not the exit code or a human-friendly diagnosis. The `_require-port` pattern compensates, but each target needs its own guards.
- **`$(shell ...)` timing.** Port resolution via `$(shell ...)` runs at parse time when the variable is first referenced. In recipes that use `$(PORT)`, this is fine — but if a recipe spawns a sub-make, the sub-make re-evaluates it, potentially getting a different answer. Use `$(MAKE) PORT=$(PORT) monitor` (explicit pass-through) to avoid this.
- **Recursive make vs. sub-shell.** `$(MAKE) -s monitor` inside a recipe starts a new Make process, which re-evaluates the PORT variable. In this project this is acceptable (the device doesn't move mid-run), but it's worth noting.
- **Parallel execution (`-j`).** Recipe ordering within a single target is guaranteed, but `make flash test` (two targets on the command line) could run in parallel with `-j2`. The workflow requires strict sequencing. Document: never use `-j` with these targets.
- **Windows incompatibility.** All recipes use bash idioms. Not an issue here (Linux-only project), but worth noting for future contributors.

---

## Relationship to Proposal B

Proposal B (`run/` shell scripts) avoids the Makefile complexity at the cost of discoverability — there is no single `make help` equivalent. The two approaches are mutually compatible: a thin Makefile could delegate to the `run/` scripts, giving the best of both (discoverable names, robust shell error handling). See the comparison summary at the bottom of Proposal B.
