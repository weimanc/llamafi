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
Rebuild and reflash. Fallback: SPIFFS `/wifi_creds.json` (written by `run/setup`), then captive portal.

**WiFi — captive portal:**
On first boot (or double-press RST within 10s) device broadcasts SSID `SpotifyDIY` / pw `thing123`. Use **"Configure WiFi"** page (not "Info").

> **DRD trap**: Never open the serial port and immediately press RST. Opening the port triggers a DTR reset; a second RST within 10s triggers the captive portal. Wait ≥12s after port open before any reset. (BP-018)

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
./run/check          # 5-gate check: prod compile, debug compile, golden hash, smoke, app registry
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
- `cal.json` — touch calibration (written by CalibrationFlow at runtime; do not hand-edit)
- `settings.json` — app settings (written by SettingsStorage at runtime; do not hand-edit)
- `drd.dat` — double-reset detector state (written at runtime; do not hand-edit)

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

Use `./run/test` — it enforces the 6-step sequence atomically with a `trap EXIT` restore guarantee (production firmware always restored, even on Ctrl-C or mid-step failure):

```sh
./run/test
```

The script executes internally: kill monitor → flash debug → wait 8s → run suite → restore prod → restart monitor. Never split these steps manually. The 8s wait is overridable: `BOOT_WAIT=12 ./run/test`.

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

---

## 6. Python Tooling

```sh
./run/bake-skin      # bake Winamp skin assets → app/gen/ (no DUT)

# Preview layout has no run/ wrapper — invoke directly (no DUT):
python3 app/tools/preview_layout.py
```

Note: `./run/test-sync` runs the sync/drift/playlist suite (T097-T116) via `run_sync_tests.py` — it **requires DUT** and follows the same 6-step validation loop as `./run/test`.

All tools use the project venv when available. The `run/` scripts source `run/lib.sh` which auto-detects the venv; override with `VENV_PY=/path/to/python3`.

---

## 7. Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `SerialException: device reports readiness but returned no data` | Monitor holds the port | `tmux kill-session -t spotify-mon` |
| `RuntimeError: PRODUCTION FIRMWARE DETECTED` | Debug build not flashed | Flash `cyd2usb_winamp_debug` |
| DUT stuck in captive portal after test run | Double-reset within 10s | Close port, wait 20s, single physical RST press |
| `TouchCalStorage: loaded` missing from boot log | No `/cal.json` on SPIFFS | Run CalibrationFlow in settings, or `./run/spiffs push cal.json` with a pre-baked file |
| Touch maps to wrong position on right side | Old calibration (pre-fix) in SPIFFS | Open Settings → Touch Calibration → Start, redo 4 corners |
| Flash fails with permission error | User not in `dialout` group | `sudo usermod -aG dialout $USER` then re-login |
