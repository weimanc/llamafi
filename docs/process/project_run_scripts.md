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
./run/flash                   # flash production firmware (kills + restores monitor)
./run/flash-debug             # flash debug firmware (kills monitor, does NOT restart)
./run/flash-fs                # upload SPIFFS only — full format/rewrite (use run/spiffs push instead)
./run/spiffs ls               # list files on device (non-destructive)
./run/spiffs pull [file]      # extract all files → app/data/spiffs-dump/, or single file → stdout
./run/spiffs push [file]      # write single file or merge app/data/ — read-modify-write, no format
./run/spiffs rm <file>        # remove single file from device
./run/check                   # 5-gate build check (compile, hash, smoke, registry)
./run/bake-skin               # bake Winamp skin assets into app/gen/
./run/audit-origin            # (re)generate the origin/hit-test audit PNG (never stale)
./run/test-sync               # sync/drift/playlist suite T097-T116 (requires DUT)
```

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

Quick smoke (< 2 min, always-passing):
```sh
./run/test-smoke
```

All three scripts run the same 6-step sequence (BP-020):
1. Kill monitor
2. Flash debug firmware
3. Wait `BOOT_WAIT` seconds (default 8) for boot + WiFi
4. Run tests
5. Restore production firmware  ← runs even on failure / Ctrl-C (trap)
6. Restart monitor              ← runs even on failure / Ctrl-C (trap)

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

---

## Script → dut_workflow.md cross-reference

| Script | Implements |
|--------|-----------|
| `run/port` | §0 Resolve the Serial Port |
| `run/flash` | §3a Firmware only |
| `run/flash-fs` | §3b SPIFFS only (full format — escape hatch) |
| `run/spiffs` | §3b SPIFFS non-destructive read/modify/write |
| `run/monitor-start/stop/read` | §4 Serial Monitor |
| `run/test` | §5a Pre-run checklist (BP-020) |
| `run/test-targeted` | §5b Targeted feature validation (BP-021) |
| `run/test-smoke` | §5b Quick smoke preset |
| `run/test-sync` | §5b Targeted feature validation (sync suite T097-T116) |
| `run/check` | §2 Build (5-gate check_build.sh) |
| `run/bake-skin` | §6 Python Tooling / skin bake |
