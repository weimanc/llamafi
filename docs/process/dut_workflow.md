# DUT Workflow — Spotify-Diy-Thing

> Owner: QM / VE  
> Scope: `Spotify-Diy-Thing/` firmware only (`app/` PlatformIO project).  
> Hardware: ESP32-2432S028R "Cheap Yellow Display" two-USB variant, CH340 USB-serial.

This is the single reference for all DUT operations. Read this before issuing any flash, monitor, or test command.

For executable entry points (the `run/` scripts that implement every operation described here), see [`project_run_scripts.md`](project_run_scripts.md).

---

## 0. Resolve the Serial Port

The CH340 port is non-deterministic (`ttyUSB0`, `ttyUSB1`, …). All `run/` scripts resolve it automatically — you never need to look it up manually for normal operations.

```sh
./run/port          # print the resolved port
```

To inspect or override: `PORT=/dev/ttyUSB1 ./run/flash`. Never hardcode `/dev/ttyUSB0` or `/dev/ttyUSB1` — it changes between sessions. (BP-019)

**Implementation detail** (used internally by `run/lib.sh::resolve_port()`):
```sh
for p in /dev/ttyUSB*; do
  udevadm info -q property "$p" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" && echo "$p" && break
done
```

---

## 1. First-Time Setup

Run the setup wizard:
```sh
./run/setup
```
Prompts for WiFi credentials and Spotify API keys, handles the OAuth flow, and offers `./run/spiffs push` at the end. No manual file editing needed.

Prereq in the Spotify Developer Dashboard: add `http://127.0.0.1:8888/callback/` to the app's Redirect URIs.

### Manual / fallback paths

**WiFi — compile-time hardcode (dev boards):**
Create `Spotify-Diy-Thing/SpotifyDiyThing/wifi_creds.h` (gitignored, highest priority):
```c
#define HARDCODED_WIFI_SSID "YourSSID"
#define HARDCODED_WIFI_PASS "YourPass"
```
Rebuild and reflash. Fallback: NVS (saved by prior connect), then SPIFFS `/wifi_creds.json` (written by `run/setup`), then WiFi settings UI on device.

**WiFi — on-device settings UI:**
If no credentials are found at boot (no `wifi_creds.json`, no NVS entry), the device
automatically switches to the Settings app → WiFi section. Select a network from the
scan list, enter the password, and connect. Credentials are saved to NVS on success.

**Spotify — headless re-auth:**
```sh
# Requires http://127.0.0.1:8888/callback/ in Redirect URIs
./get_refresh_token.py <CLIENT_ID> <CLIENT_SECRET>
./run/spiffs push spotify_diy_config.json
```

---

## 2. Build

```sh
./run/build          # production firmware (cyd2usb_winamp)
./run/build-debug    # debug firmware (cyd2usb_winamp_debug) — required for test harness
./run/check          # 11-gate check: 1-6 full firmware env matrix, 7 golden hash, 8 tool
                      #   smoke, 9 app-registry staleness, 10 mem_layout staleness+budget,
                      #   11 check-docs (see check_build.sh header for the authoritative count)
```

**Do not bump `platform = espressif32` above 6.9.x** — newer cores split `WiFi`/`Network` headers in a way the installed libs don't support. (CLAUDE.md)

---

## 3. Flash

### 3a. Firmware only

```sh
./run/flash          # production firmware (kills monitor, flashes, restarts monitor)
./run/flash-debug    # debug firmware (kills monitor; does NOT restart — port free for test harness)
```

Port is resolved automatically. Override: `PORT=/dev/ttyUSB1 ./run/flash`.

### 3b. SPIFFS only (credentials)

SPIFFS is a separate partition — reflashing firmware does NOT touch it, and SPIFFS writes do NOT touch firmware.

```sh
# Populate app/data/ first, then:
./run/spiffs push           # non-destructive: updates only files present in app/data/
./run/spiffs push <file>    # update a single file; all others preserved
```

`./run/flash-fs` (full format + rewrite) is the escape hatch for a corrupted filesystem — avoid for routine credential updates as it wipes `cal.json` and `settings.json`.

Files in `app/data/` (symlinked from `Spotify-Diy-Thing/data/`):
- `spotify_diy_config.json` — Spotify keys + refresh token (gitignored)
- `wifi_creds.json` — WiFi SSID + password (gitignored, written by `run/setup`)
- `cal.json` — touch calibration (written by CalibrationFlow at runtime; do not hand-edit)
- `settings.json` — app settings (written by SettingsStorage at runtime; do not hand-edit)

### 3c. When to update SPIFFS

| Scenario | Action |
|----------|--------|
| New Spotify refresh token | Edit `data/spotify_diy_config.json`, `./run/spiffs push spotify_diy_config.json` |
| Wipe calibration | `./run/spiffs rm cal.json` |
| Touch calibration via UI | No action — CalibrationFlow writes it at runtime |

---

## 4. Serial Monitor

The monitor holds the port exclusively — all `run/flash*` and `run/test*` scripts kill it automatically. Manual control:

```sh
./run/monitor-start       # start detached tmux session (session: spotify-mon)
./run/monitor-stop        # kill session — idempotent, safe when not running
./run/monitor-read        # dump last 200 lines
./run/monitor-read 500    # dump last 500 lines
```

---

## 5. Validation Testing

### 5a. Pre-run checklist (BP-020)

Use `./run/test`. **It does not flash and it does not restore** (ADR-067/TASK-633, 2026-09-06). It
*declares* the build it needs, *reads* what the board is actually running, and **refuses with exit 3**
(`elf-mismatch` — a RIG condition, not a test failure) if they differ. Flash the debug build yourself
first:

```sh
./run/flash-debug
```

```sh
./run/test
```

> **A reflash costs a TASK-557 observation window.** TASK-557's measurement *is* the board's
> uptime, so `run/flash-debug` — like any reset — ends whatever window is running. On 2026-09-07
> a reconcile-and-reflash under TASK-589 spent **9 h 33 m**. Nothing warns you, and nothing in
> `run/` can: the scripts cannot tell an intended reset from a costly one.
>
> The trigger is routine and **expected, not a defect**: the debug env injects the git hash into
> the build id, so any HEAD move (a commit, a checkout) invalidates the artifact already on the
> board and the next `run/test*` refuses with `elf-mismatch`. That refusal means "the board is
> stale", not "the board is broken".
>
> Before reflashing: check whether a window is running (`./run/monitor-read` — uptime and how long
> it has been climbing; never `run/dut-health`, whose own port open resets the board). If one is,
> either wait, or reflash deliberately and **say so in the session record** — the window's length
> at the moment you ended it is the datum TASK-557 loses.
>
> With `RIGWATCH=1` (TASK-677 / PROP-011 §5 P0 — see `run/local.env.example` and
> `docs/process/project_run_scripts.md`'s "Rig watch" section), `./run/rig-timeline` does this
> check for you: it merges the kernel's own USB-attach/detach log with every harness flash/monitor
> action and the DUT's own boot-phase/BOD/heartbeat lines into one ordered, file-only view (it never
> opens the port), and labels each reset as harness-caused or `UNEXPLAINED`.

The script executes internally: verify build (refuse if wrong) → snapshot settings → kill monitor →
run suite → restore **settings** → restart monitor. Never split these steps manually.

**What changed, and why it matters to you:** the old sequence was *kill monitor → flash debug → wait
8s → run suite → **restore prod** → restart monitor*, with an EXIT trap that reflashed production no
matter how the script ended. That trap is **deleted, not guarded**. Two consequences:

* **The board stays on the debug build after a run.** Nothing puts production back. If you want
  production on the board, `./run/flash` it — deliberately.
* **A pinned board is no longer unrunnable.** TASK-557 pins this rig to `-DBOD_WATCH`; the old trap
  made every test script refuse to co-exist with that pin, which is what ADR-067 was written to fix.

`DUT_NO_RESTORE=1`, the dated interim exception that let Phase 2 run before this landed, **has met
its retirement condition and is gone.** Nothing reads it.

Note the settings restore is *not* the firmware restore: the suite mutates persisted settings on a
board it does not own, and putting those back is the suite cleaning up after itself (BP-049), not an
entry point owning firmware lifecycle.

### 5b. Targeted feature validation (BP-021)

After implementing a specific feature, run only its tests:

```sh
./run/test-targeted T-SET-01,T-SET-02,T-SET-08   # settings example
./run/test-targeted T169,T170,T173,T174           # stock app example
TESTS=T169,T170 ./run/test-targeted               # env-var form
```

Quick smoke preset (< 2 min, always-passing, confirms basic shell health):
```sh
./run/test-smoke
```

### 5c. Regression suite

Full suite only at milestone boundaries or after cross-cutting refactors:

```sh
./run/test
```

**Expected baseline (2026-06-06 post-settings-001):** 59 pass / 20 fail / 28 skip / 1 flake.

Known always-failing tests (pre-existing, not regressions):
- T076/T079/T086/T088 — Winamp hit-zone (Spotify not playing required)
- T134/T137/T138/T155-T160 — playlist scroll (queue empty required; need active Spotify session)
- T163/T165 — taskbar drag (known open issue)
- T_WX_01/T_CX_01/T180/T-BUSY-01b — intermittent API timeout
- T-BUSY-05/T-CDWN-02/T-CDWN-03 — shellBusy race (timing-dependent)
- T-SET-03/T-SET-07 — stale (settingsAppSubmenu var removed; superseded by T-APPS-07)

A new failure in any previously-passing test is a regression — investigate before merging.

### 5d. Manual-only tests

Many new features have no harness coverage — they require physical DUT interaction:

| Feature | Manual test IDs | What to verify |
|---------|----------------|----------------|
| LedSection | T-LED-01..11 | LED modes, picker drag, SAVE, persist |
| KeyboardWidget | T-KB-01..12 | Keys, shift, sym pages, OK/Cancel |
| CalibrationFlow | T-CAL-01..11 | 4-corner tap, review, accept, persist |
| Brightness / LDR | T-DISP-01..05 | Slider, auto mode, LDR live value |
| City / time | T-TIME-01..05, T-CITY-DRAG-01 | TZ switch, picker drag |
| App settings | T-APPS-01..08 | Per-app settings, persist |

For manual tests: consult `docs/verification/test_plan.md` for exact steps and expected results.

### 5e. Soak & gate scripts (TASK-502)

Unattended long-running DUT scripts. **Since ADR-067 none of them flashes and none of them restores**
— each verifies the build named below and refuses with exit 3 if the board is running something else.
Flash the required build first with the matching `run/flash*` script. Not otherwise referenced by
this doc:

| Script | Requires (flash it first) | Purpose |
|--------|---------|---------|
| `run/ae04` | `cyd2usb_webradio` | T_AE_04 (ADR-059) — teardown ordering under eject-mid-CONNECTING |
| `run/wr-soak` | `cyd2usb_webradio` | TASK-271 — unattended WebRadio playback + A-lite arena-churn soak |
| `run/wr-gate` | `cyd2usb_webradio` | TASK-238 — ADR-045 MVP exit-criterion gate, N cold-entry WebRadio cycles |
| `run/stress` | debug | TASK-248 — unattended multi-app fetch stress/soak, latency + TLS-error report |
| `run/pr-soak` | debug | TASK-307 exit criterion 4 — PlaneRadar + Spotify coexistence soak |
| `run/pr-fetch-soak` | debug | TASK-361 — PlaneRadar fetch-failure-rate quantification |
| `run/task488` | debug | TASK-488 Part B — T_488_04..11, the M-SRCLAYOUT refactor DUT verification |

---

## 6. Python Tooling

```sh
./run/bake-skin      # bake Winamp skin assets → app/gen/ (no DUT)

# Preview layout has no run/ wrapper — invoke directly (no DUT):
python3 app/tools/preview/preview_layout.py
```

Note: `./run/test-sync` runs the sync/drift/playlist suite (T097-T116) via `run_sync_tests.py` — it **requires DUT** and follows the same 6-step validation loop as `./run/test`.

All tools use the project venv when available. The `run/` scripts source `run/lib.sh` which auto-detects the venv; override with `VENV_PY=/path/to/python3`.

---

## 7. Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `SerialException: device reports readiness but returned no data` | Monitor holds the port | `tmux kill-session -t spotify-mon` |
| `RuntimeError: PRODUCTION FIRMWARE DETECTED` | Debug build not flashed | Flash `cyd2usb_winamp_debug` |
| DUT opens WiFi settings unexpectedly after test run | NVS credentials were cleared or not written | Re-enter credentials via on-device WiFi settings UI, or `./run/spiffs push wifi_creds.json` |
| `TouchCalStorage: loaded` missing from boot log | No `/cal.json` on SPIFFS | Run CalibrationFlow in settings, or `./run/spiffs push cal.json` with a pre-baked file |
| Touch maps to wrong position on right side | Old calibration (pre-fix) in SPIFFS | Open Settings → Touch Calibration → Start, redo 4 corners |
| Flash fails with permission error | User not in `dialout` group | `sudo usermod -aG dialout $USER` then re-login |
