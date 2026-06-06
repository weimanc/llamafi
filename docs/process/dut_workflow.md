# DUT Workflow — Spotify-Diy-Thing

> Owner: QM / VE  
> Scope: `Spotify-Diy-Thing/` firmware only (`app/` PlatformIO project).  
> Hardware: ESP32-2432S028R "Cheap Yellow Display" two-USB variant, CH340 USB-serial.

This is the single reference for all DUT operations. Read this before issuing any flash, monitor, or test command.

---

## 0. Resolve the Serial Port

The CH340 port is non-deterministic (`ttyUSB0`, `ttyUSB1`, …). Always resolve by VID:PID:

```sh
# One-shot lookup (CH340 VID:PID 1A86:7523)
ls /dev/ttyUSB* | while read p; do
  udevadm info -q property "$p" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" && echo "$p" && break
done
```

Substitute the result as `PORT` in every command below. Never hardcode `/dev/ttyUSB0` or `/dev/ttyUSB1` — it changes between sessions. (BP-019)

```sh
PORT=$(ls /dev/ttyUSB* | while read p; do
  udevadm info -q property "$p" 2>/dev/null | grep -q "ID_VENDOR_ID=1a86" && echo "$p" && break
done)
echo "DUT on $PORT"
```

---

## 1. First-Time Setup

### 1a. WiFi credentials

WiFi is stored in NVS (survives firmware reflash). Two options:

**Option A — Hardcoded (dev boards, recommended):**
Create `Spotify-Diy-Thing/SpotifyDiyThing/wifi_creds.h` (gitignored):
```c
#define HARDCODED_WIFI_SSID "YourSSID"
#define HARDCODED_WIFI_PASS "YourPass"
```
Rebuild and reflash firmware. On connect timeout (30s) it falls through to captive portal.

**Option B — Captive portal:**
On first boot (or double-press RST within 10s) device broadcasts SSID `SpotifyDIY` / pw `thing123`. Join it, navigate to the router IP. Use **"Configure WiFi"** page (not "Info") — only that page shows the Client ID / Secret / Refresh Token fields. See warning below.

> **DRD trap**: Never open the serial port and immediately press RST. Opening the port triggers a DTR reset; a second RST within 10s triggers the captive portal. Wait ≥12s after port open before any reset. (BP-018)

### 1b. Spotify credentials

Get a refresh token on the host (device's LAN IP redirect is no longer accepted by Spotify as of Apr 2025):
```sh
# Requires http://127.0.0.1:8888/callback/ added to your Spotify app's Redirect URIs
python3 get_refresh_token.py
```
Copy the printed token into `app/data/spotify_diy_config.json`:
```json
{ "refreshToken": "...", "clientId": "...", "clientSecret": "..." }
```
Then upload SPIFFS (see §3b). This survives future firmware reflashes.

---

## 2. Build

```sh
cd app

# Production build (target for flashing and monitoring)
~/.platformio/penv/bin/pio run -e cyd2usb_winamp

# Debug build (required for serialdbg test harness)
~/.platformio/penv/bin/pio run -e cyd2usb_winamp_debug

# Build check (5 gates: prod compile, debug compile, golden hash, smoke, app registry)
cd ..
./check_build.sh
```

**Do not bump `platform = espressif32` above 6.9.x** — newer cores split `WiFi`/`Network` headers in a way the installed libs don't support. (CLAUDE.md)

---

## 3. Flash

### 3a. Firmware only

```sh
# Kill monitor first — it holds the port exclusively
tmux kill-session -t spotify-mon 2>/dev/null

cd app
~/.platformio/penv/bin/pio run -e cyd2usb_winamp -t upload --upload-port $PORT
```

For debug firmware (needed for test harness):
```sh
~/.platformio/penv/bin/pio run -e cyd2usb_winamp_debug -t upload --upload-port $PORT
```

### 3b. SPIFFS only (credentials / host overrides)

SPIFFS is a separate partition — reflashing firmware does NOT touch it, and `uploadfs` does NOT touch firmware.

```sh
# Populate data/ first, then:
~/.platformio/penv/bin/pio run -e cyd2usb_winamp -t uploadfs --upload-port $PORT
```

Files in `app/data/` (symlinked from `Spotify-Diy-Thing/data/`):
- `spotify_diy_config.json` — Spotify keys + refresh token
- `host_overrides.json` — DNS override table (gitignored; regenerate with `tools/refresh_host_overrides.sh`)
- `cal.json` — touch calibration (written by CalibrationFlow; do not hand-edit)
- `settings.json` — app settings (written by SettingsStorage; do not hand-edit)

### 3c. When to reflash SPIFFS

| Scenario | Action |
|----------|--------|
| New Spotify refresh token | Edit `data/spotify_diy_config.json`, `uploadfs` |
| New DNS overrides | Run `tools/refresh_host_overrides.sh`, `uploadfs` |
| Wipe calibration | Delete `cal.json` from data/, `uploadfs` |
| Touch calibration via UI | No action — CalibrationFlow writes it at runtime |

---

## 4. Serial Monitor

The monitor holds the port exclusively. Run it in a detached tmux session:

```sh
tmux new-session -d -s spotify-mon \
  "cd ~/proj/esp_spotify/app && ~/.platformio/penv/bin/pio device monitor -e cyd2usb_winamp -p $PORT"

# Read last ~200 lines
tmux capture-pane -t spotify-mon -p -S -200

# Kill before flashing or running tests
tmux kill-session -t spotify-mon
```

---

## 5. Validation Testing

### 5a. Pre-run checklist (BP-020)

Always execute in this exact order — skipping any step causes the next to fail:

```sh
# 1. Kill monitor (releases port)
tmux kill-session -t spotify-mon 2>/dev/null

# 2. Flash debug firmware (harness rejects production build immediately)
cd app
~/.platformio/penv/bin/pio run -e cyd2usb_winamp_debug -t upload --upload-port $PORT

# 3. Wait for boot + WiFi settle
sleep 8

# 4. Run tests (see §5b / §5c)
~/proj/esp/venv/bin/python3 tools/run_serialdbg_tests.py --port $PORT

# 5. Restore production firmware
~/.platformio/penv/bin/pio run -e cyd2usb_winamp -t upload --upload-port $PORT

# 6. Restart monitor
tmux new-session -d -s spotify-mon \
  "cd ~/proj/esp_spotify/app && ~/.platformio/penv/bin/pio device monitor -e cyd2usb_winamp -p $PORT"
```

### 5b. Targeted feature validation (BP-021)

After implementing a specific feature, run only its tests — do not launch the full suite:

```sh
# Example: validate settings shell + new sections only
~/proj/esp/venv/bin/python3 tools/run_serialdbg_tests.py --port $PORT \
    --run T-SET-01,T-SET-02,T-SET-03,T-SET-06,T-SET-07,T-SET-08

# Example: validate stock app
~/proj/esp/venv/bin/python3 tools/run_serialdbg_tests.py --port $PORT \
    --run T169,T170,T173,T174,T175,T176,T177,T183,T184,T185,T186,T187,T188,T196
```

**Quick smoke preset** (< 2 min, always-passing, confirms basic shell health):
```sh
~/proj/esp/venv/bin/python3 tools/run_serialdbg_tests.py --port $PORT \
    --run T080,T083,T091,T092,T133,T147,T148,T162,T-SET-01,T-SET-02,T-SET-08
```

### 5c. Regression suite

Run the full suite only at milestone boundaries or after cross-cutting refactors:

```sh
~/proj/esp/venv/bin/python3 tools/run_serialdbg_tests.py --port $PORT
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

All host-side Python tools use the project venv:

```sh
# Skin bake
~/proj/esp/venv/bin/python3 app/tools/bake_skin.py -i app/skins/base-2.91.wsz -o app/gen

# Preview layout
~/proj/esp/venv/bin/python3 app/tools/preview_layout.py

# Serialdbg tests
~/proj/esp/venv/bin/python3 app/tools/run_serialdbg_tests.py --port $PORT

# Sync tests (host-only, no DUT)
~/proj/esp/venv/bin/python3 app/tools/run_sync_tests.py
```

---

## 7. Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `SerialException: device reports readiness but returned no data` | Monitor holds the port | `tmux kill-session -t spotify-mon` |
| `RuntimeError: PRODUCTION FIRMWARE DETECTED` | Debug build not flashed | Flash `cyd2usb_winamp_debug` |
| DUT stuck in captive portal after test run | Double-reset within 10s | Close port, wait 20s, single physical RST press |
| `TouchCalStorage: loaded` missing from boot log | No `/cal.json` on SPIFFS | Run CalibrationFlow in settings, or `uploadfs` with a pre-baked file |
| Touch maps to wrong position on right side | Old calibration (pre-fix) in SPIFFS | Open Settings → Touch Calibration → Start, redo 4 corners |
| Flash fails with permission error | User not in `dialout` group | `sudo usermod -aG dialout $USER` then re-login |
