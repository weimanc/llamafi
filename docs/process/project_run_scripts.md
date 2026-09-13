# Project Run Scripts — Operator Quick Reference

> Owner: PM / VE  
> For rationale and failure modes: see [dut_workflow.md](dut_workflow.md)  
> Addresses: LL-056

All scripts live in `run/` at the project root. Run from the project root.

---

## Common operations

```sh
./run/setup                   # first-time setup wizard (WiFi + Spotify credentials → app/data/)
./run/port                    # print resolved CH340 port
./run/monitor-start           # start tmux serial monitor
./run/monitor-stop            # kill monitor (releases port)
./run/monitor-read            # dump last 200 lines; ./run/monitor-read 500 for more
./run/build                   # compile production firmware
./run/build-debug             # compile debug firmware
./run/flash                   # flash production firmware (kills + restarts monitor)
./run/flash-debug             # flash debug firmware (kills monitor, does NOT restart)
./run/flash-fs                # upload SPIFFS only — full format/rewrite (use run/spiffs push instead)
./run/spiffs ls               # list files on device (non-destructive)
./run/spiffs pull [file]      # extract all files → app/data/spiffs-dump/, or single file → stdout
./run/spiffs push [file]      # write single file or merge app/data/ — read-modify-write, no format
./run/spiffs rm <file>        # remove single file from device
./run/check                   # 11-gate build check (1-6 firmware env matrix, 7 golden hash,
                               #   8 tool smoke — 17 host scripts (7 checkers, 10 negative
                               #   suites), incl. import-safety, get-keys and flake-class
                               #   (TASK-609/600/623),
                               #   9 app-registry staleness, 10 mem_layout
                               #   staleness+budget, 11 check-docs — see check_build.sh header)
./run/bake-skin               # bake Winamp skin assets into app/gen/
./run/audit-origin            # (re)generate the origin/hit-test audit PNG (never stale)
./run/test-sync               # sync/drift/playlist suite T097-T116 (requires DUT)
./run/dut-health              # PRE-FLIGHT ONLY: the HEALTH class, T_DH_01-03 — exit 0/4
                               #   (3 = rig; 1 = a broken results record, TASK-645). Emits a run
                               #   artifact like every other entry point (R29).
./run/new-test <scope> <ID>   # scaffold a new test's record (TASK-630). Host-only; prints and
                               #   edits nothing. Generates the family module, the scope/cls/effect
                               #   seeds, the registry line, the test_plan.md entry and a body
                               #   skeleton that already satisfies R34/R18/R17. REFUSES the oracle
                               #   and a gating cls_reason — the stub it emits is under
                               #   check_test_meta's 80-character floor, so a scaffolded gating
                               #   test reds run/check until a person writes the sentence.
```

### `run/dut-health` — is this board fit to test?

TASK-565 / [M-TESTARCH](../architecture/designs/M-TESTARCH-precedence-hierarchy.md) §5 E4.
Three checks, in class order: `T_DH_01` the shell answers **correct** data (not merely
answers), `T_DH_02` the device's own view of the network is coherent (`get wifiCfg`),
`T_DH_03` app switching is alive. Exit **0** = fit; exit **4** = `[HEALTH-FAIL]`, and every
result a suite produced against this board would be uninterpretable; exit **3** = a RIG
condition, nothing was measured.

**Cost: ~15 s typical, up to ~60 s on a degraded boot.** That is *boot + checks*: the checks
are ~10 s of round-trips, but opening the port resets the board and TASK-561 measured 46 s to
console on a `NO_AP_FOUND` boot. Inside a suite run the checks would be additive-only (~10 s),
because the boot is already paid for.

**It is PRE-FLIGHT, and that is a hard constraint, not a caveat.** Opening the port asserts
DTR and resets the ESP32 — and per TASK-426 a reset is *precisely* what clears the dead-SSID
wedge. Running it after forming a theory about a misbehaving board destroys the state it was
invoked to diagnose, shows a healthy board, and manufactures a wrong conclusion with a tool's
authority behind it. A wedged board is diagnosed from the monitor's disk log
(`./run/monitor-read`) and the `[bootphase]`/heartbeat stream already being captured — read
that first. The tool prints this warning itself, before every verdict.

It does **not** flash: every check is a `SERIAL_DEBUG` console command, so debug firmware must
already be on the board; on production firmware it aborts with the RIG reason
`prod-firmware-flashed`. It does take the port, so it stops the tmux monitor and restarts it
afterwards. The same three ids are addressable through the suite runner
(`./run/test-targeted T_DH_01`), which is the same phase reached by another name.

---

## Validation loop (the answer to "how do I validate a new feature")

Full suite:
```sh
./run/test
```

Targeted (single feature):
```sh
./run/test-targeted T-SET-01,T-SET-02,T-SET-08
# or
TESTS=T-SET-01,T-SET-02,T-SET-08 ./run/test-targeted
```

Targeted by **scope** — start from the file you changed, not from an id list
(TASK-570, [M-TESTARCH](../architecture/designs/M-TESTARCH-precedence-hierarchy.md) §13.4):
```sh
./run/test-targeted --scope app/src/apps/localPlayerApp.cpp   # file -> app -> its ids
./run/test-targeted --scope LocalPlayer                       # or name the scope
./run/test-targeted --scope spotify-chrome                    # non-app scopes:
                                              # shell | boot | taskbar | spotify-chrome | rig
SCOPE=Stock ./run/test-targeted T169,T170                     # combines: intersection
```
Scope names are case-sensitive (`Spotify` the app vs `spotify-chrome` the shell's
Spotify plumbing); an unresolvable path or a mistyped scope aborts **before** the
port is opened, so a typo never costs a board reset. `--class` and `--upto` were
cut at review and do not exist (design §20).

Quick smoke (< 2 min, always-passing):
```sh
./run/test-smoke
```

All three scripts run the same sequence (BP-020), **as revised by ADR-067/TASK-633 (2026-09-06)**:
1. **Verify the build.** The run declares which env it needs; the board's build identity is read and
   compared. A mismatch is **exit 3** (`elf-mismatch`, RIG) and **no tests run**.
2. Kill monitor
3. Run tests
4. Restart monitor              ← runs even on failure / Ctrl-C (trap)

**Steps 2 and 5 of the old sequence — "flash debug firmware" and "restore production firmware" — are
gone.** A DUT entry point no longer owns firmware lifecycle: it never flashes and it never restores.
Flash what the run needs yourself, first, with `run/flash-debug` (or `run/flash-player`,
`run/flash-webradio`). **The board keeps that build after the run.**

The `BOOT_WAIT` wait is gone from these three as well (TASK-563): readiness is decided by watching
the boot the port open itself causes, not by guessing.

---

## Port override

Scripts resolve the CH340 port automatically via `udevadm`. Override when needed:

```sh
PORT=/dev/ttyUSB1 ./run/flash
PORT=/dev/ttyUSB1 ./run/test-targeted T080,T083
```

---

## Environment variables

| Variable | Default | Effect |
|----------|---------|--------|
| `PORT` | auto-resolved | Skip udevadm lookup; use this port |
| `BOOT_WAIT` | `8` | Seconds to wait after flashing debug firmware |
| `TESTS` | (none) | Test IDs for `test-targeted` (comma-separated) |
| `SCOPE` | (none) | Scope selector for `test-targeted` — app name, non-app scope, or a changed file's path (TASK-570). Same as `--scope` |
| `RESULTS_JSON` | `app/tools/.runs/run-<UTC>-<pid>-<token>.json` | Where the run writes its result artifact (TASK-608 / IFC-008). Set it when you want the artifact at a path you own |
| `RESULTS_RUN_TOKEN` | random per run | The staleness nonce. A consumer that sets it can read back with `python3 -m lib.artifact <path> --token <nonce>`, and an artifact from any **other** run is refused rather than scored |
| `RIGWATCH` | unset (0) | `1` turns on rigwatch (TASK-677) — kernel-event daemon, harness stamps, DUT-line timestamps, the artifact's `rig` section. Set in `run/local.env`, not inline — see below |
| `DUT_BY_PATH` | auto (first CH340 by-id) | Which DUT node rigwatch resolves to a USB topology port for kernel-log filtering. Only matters with two CH340s attached |
| `RIG_EVENTS` | `/tmp/spotify-mon-rig-events.jsonl` | Where rigwatch's kernel + harness events are appended |
| `DUT_SHUFFLE_SEED` | unset | Same as `runner.py --shuffle-family SEED` (TASK-636) — no wrapper change needed, `run/test`/`run/test-targeted` inherit it like `DUT_CLASS_ORDER`. Refused together with `DUT_CLASS_ORDER=1`/`--class-order`. See "Per-family shuffle" below |

---

## Rig watch (TASK-677 / PROP-011 §5 P0)

Host+DUT fault correlation: never open the serial port, only read the kernel's own udev log
(`journalctl -k`) and the plain-text serial logs other processes already write. Off by default —
copy `run/local.env.example` to `run/local.env` (gitignored) and set `RIGWATCH=1` to turn it on.
With it unset, every script behaves exactly as before this task.

```sh
cp run/local.env.example run/local.env    # then edit RIGWATCH=1 in
./run/monitor-start                       # also starts the rigwatch daemon
./run/rig-timeline --since 2h             # merged host+DUT event timeline, files only —
                                           # safe to run at any time, including mid-window
python3 -m lib.rigwatch summary --since 24h --json   # R/U/bod_trips/W as JSON
```

`run/rig-timeline` is the automated form of `dut_workflow.md` §5a's manual "check for a live
window" step: a reset the harness itself caused (flash, port-open) is labelled as such inline; any
other `[bootphase] 0` is flagged `UNEXPLAINED boot`. With `RIGWATCH=1`, every `run/test`/
`run/test-targeted` run's artifact also carries a `run.rig` section (schema 1.3, additive/optional)
summarizing its own window, and prints a `[triage] rig: R=... U=...` annotation when either metric
is nonzero — PROP-011 §4's RIG threshold is `R=0 and U=0`.

---

## The run result artifact (TASK-608, [IFC-008](../architecture/interfaces/IFC-008.md))

Every suite run emits one JSON document and prints its path. **That document — not the printed
summary — is the machine interface** (ADR-066 D1): `run/player-gate` reads it, `lib/baseline.py`
reads it, and nothing parses the `── Results ──` block any more. The summary is still printed,
unchanged, for humans.

```sh
python3 -m lib.artifact <artifact.json> --ids-status   # `<id> <VERDICT>` per line
python3 -m lib.artifact <artifact.json> --exit-code
python3 -m lib.baseline run1.json run2.json run3.json  # fold N runs (artifacts, not logs)
```

It carries the run's **premise** (R30) — ELF hash and build env, board, generation tag, class order
in force, the id set and why it was selected, the flake registry's content hash, any downgraded
gate — plus every id's typed verdict, class, scope, effect, elapsed and structured reason.

**A stale artifact is the failure this is designed against**, because a gate scored against a
previous run's file is silent and looks like a result. Three layers: the default path is unique per
run and never reused (there is deliberately no `latest.json`); a consumer that owns the path passes
a nonce and any other run's document is refused; and a missing or unknown-schema artifact is an
error, never an empty result set.

---

## Per-family shuffle & order-dependence (TASK-636, R20/R21)

R20 (MUST, amended by the architect review to a MUST-capability + SHOULD-campaign split): the
harness must be able to run a class's ids in a shuffled order and report any verdict that differs
from the canonical order's. Landed as `runner.py --shuffle-family SEED` (or `DUT_SHUFFLE_SEED=SEED`,
same style as `DUT_CLASS_ORDER` — no `run/test`/`run/test-targeted` wrapper change needed, both
inherit the env var):

```sh
DUT_SHUFFLE_SEED=42 ./run/test-targeted --scope <family's scope>
# or directly:
python3 tools/suite/serialdbg/runner.py --shuffle-family 42 --tests T1,T2,T3
```

Ids keep their **family blocks** (the `suite/serialdbg/<family>.py` module an id's `TESTS` entry
lives in — `lib/shuffle.py`'s `module` axis, distinct from `scope`) in canonical (first-occurrence)
order; the order **within** each family block is permuted by a seeded RNG, deterministic and
reproducible from the seed alone. Refuses to combine with `--class-order`/`DUT_CLASS_ORDER=1` — the
two axes (gating precedence vs. order-independence audit) have no defined composition. The executed
(post-shuffle) sequence lands in the artifact's existing `premise.class_order` field (that field
records the executed order for every run, not only a `--class-order` one); the seed itself is the
new `premise.shuffle_seed` (schema 1.4, additive, `null` unless `--shuffle-family` was passed).

Comparing a canonical (registry-order) run against a shuffled one — R21's `ORDER-DEPENDENT` outcome,
which per ADR-066 D2a is a **comparison over two-or-more artifacts**, never an eighth verdict:

```sh
python3 -m lib.artifact shuffled-run.json --order-dependence canonical-run-1.json canonical-run-2.json
```

Report only, never a gate/exit code — same posture as `--diff`/`--diff-auto` (TASK-689). TASK-566's
~7% non-stationary-flake rate means a single canonical/shuffled PAIR cannot separate "order-dependent"
from "just flaky today": supply 2+ **agreeing** canonical artifacts to get the bare `ORDER-DEPENDENT`
label; with exactly one, a differing row is still reported but labelled `ORDER-DEPENDENT (single pair
— not separated from flake)`.

---

## Script → dut_workflow.md cross-reference

| Script | Implements |
|--------|-----------|
| `run/port` | §0 Resolve the Serial Port |
| `run/flash` | §3a Firmware only |
| `run/flash-fs` | §3b SPIFFS only (full format — escape hatch) |
| `run/spiffs` | §3b SPIFFS non-destructive read/modify/write |
| `run/monitor-start/stop/read` | §4 Serial Monitor |
| `run/rig-timeline` | §5a Pre-run checklist — automated "check for a live window" (TASK-677) |
| `run/test` | §5a Pre-run checklist (BP-020) |
| `run/test-targeted` | §5b Targeted feature validation (BP-021) |
| `run/test-smoke` | §5b Quick smoke preset |
| `run/test-sync` | §5b Targeted feature validation (sync suite T097-T116) |
| `run/check` | §2 Build (11-gate check_build.sh) |
| `run/new-test` | §5b — scaffold a new test's record (TASK-630) |
| `run/ae04` | §5e Soak & gate scripts |
| `run/wr-soak` | §5e Soak & gate scripts |
| `run/wr-gate` | §5e Soak & gate scripts |
| `run/stress` | §5e Soak & gate scripts |
| `run/pr-soak` | §5e Soak & gate scripts |
| `run/pr-fetch-soak` | §5e Soak & gate scripts |
| `run/task488` | §5e Soak & gate scripts |
| `run/bake-skin` | §6 Python Tooling / skin bake |
