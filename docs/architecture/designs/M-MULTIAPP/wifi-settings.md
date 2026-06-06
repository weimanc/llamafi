# Design — WiFi Settings

> Owner: Architect
> Status: draft
> Date: 2026-06-04 (updated 2026-06-05 — WifiSection base-class adoption; phase split; updated 2026-06-06 — implementation audit)
> Part of: M-MULTIAPP Settings (`wifi` tab)
> See also: [settings.md](settings.md), [keyboard-widget.md](keyboard-widget.md), ADR-040

---

## Phase split

| Phase | Scope | Exit criteria |
|-------|-------|---------------|
| **Phase 1** — read-only PoC | STATUS + SCANNING + LIST. Async scan, signal bars, lock indicator. LIST tap is a no-op placeholder. No connect, no keyboard, no NVS write. | C1 — networks populate within 5 s |
| **Phase 2** — connect + persist | KEYBOARD + CONNECTING + RESULT states. `WiFi.begin()` wired up. NVS persist. "Forget network". Remove WiFiManager. | C2..C7 |

Phase 1 delivered first; Phase 2 builds on the same file.

---

## Context / pain points

WiFiManager is a captive-portal library — it forces the user onto a separate
SSID and uses a phone browser to enter credentials. It is a blocking call that
takes over the ESP32 and cannot be invoked from within the app loop. It also
bundles Spotify OAuth parameters into the portal form, which conflates WiFi
setup with Spotify setup.

This design replaces WiFiManager with a native on-device flow: scan → list →
select → password via `KeyboardWidget` → connect.

---

## Goals

1. Scan available networks and present a sorted list on-device.
2. User selects SSID by tap; password entered via `KeyboardWidget`.
3. Connect via `WiFi.begin(ssid, pass)` with `WiFi.persistent(true)` (NVS-backed).
4. On reboot: `WiFi.begin()` (no args) reconnects from NVS automatically.
5. No phone, no captive portal, no blocking boot-time call.
6. Replaces `WiFiManager` and `DoubleResetDetector` dependencies entirely.

---

## Integration prerequisite — remove WiFiManager

`WiFiManager` and `ESP_DoubleResetDetector` are removed from `lib_deps`.
`WifiManagerHandler.h` is retired. Boot sequence in `main.cpp::setup()` changes:

**Before (WiFiManager):**
```cpp
setupWiFiManager(forceConfig, refreshToken, &saveConfigFile, &drawWifiManagerMessage);
```

**After:**
```cpp
WiFi.persistent(true);
WiFi.begin();                        // reconnect from NVS (no args)
unsigned long t = millis();
while (WiFi.status() != WL_CONNECTED && millis() - t < 10000) delay(100);
if (WiFi.status() != WL_CONNECTED) {
    // No saved credentials or connect failed — switch to Settings wifi tab
    switchApp(AppId::Settings);
    g_settingsApp.openTab(0);        // wifi tab
}
```

Spotify credentials (`clientId`, `clientSecret`, `refreshToken`) are already
exclusively SPIFFS-backed (`configFile.h`). No change required there.

`DRD_TIMEOUT` / `DoubleResetDetector` removed. Double-press reset is no longer
needed — the user can reach WiFi settings from the taskbar at any time.

---

## Architecture — WifiSection as a SettingsSection subclass

`WifiSection` extends `SettingsSection` (ADR-040). It is not a separate
`AppId`. `SettingsApp` pushes it when the user taps the WiFi category row.

```cpp
// app/src/settings/wifiSection.h

enum class WifiStep : uint8_t {
    Status,                          // Phase 1
    Scanning,                        // Phase 1
    List,                            // Phase 1
    // --- Phase 2 ---
    Keyboard,
    Connecting,
    Result,
};

struct WifiNet {
    char    ssid[33];
    int32_t rssi;
    bool    encrypted;
};

class WifiSection : public SettingsSection {
public:
    // SettingsSection contract
    const char*   title()  const override;
    void          enter()        override;   // → Status; WiFi.scanDelete() safety
    void          leave()        override;   // cancel in-flight scan
    void          tick()         override;   // Scanning spinner + completion check
    void          repaint()      override;   // dispatch to repaint*()
    SectionResult handleInput(TouchPhase phase, int x, int y) override;

private:
    WifiStep      _step      = WifiStep::Status;
    uint8_t       _spinFrame = 0;
    unsigned long _lastSpin  = 0;
    WifiNet       _nets[16];
    uint8_t       _netCount  = 0;

    // Phase 2 additions (declared here, implemented later):
    // char          _pendingSsid[33];
    // unsigned long _connectStart;
    // wl_status_t   _failReason;

    void startScan();
    void repaintStatus();
    void repaintScanning();
    void repaintList();
    void drawSignalBars(int16_t x, int16_t y, int32_t rssi) const;
    // Phase 2: repaintConnecting(), repaintResult(), connectTo(int), ...
};
```

`title()` is state-dependent:

| `_step`    | returns            |
|------------|--------------------|
| `Status`   | `"Status"`         |
| `Scanning` | `"Scanning..."`    |
| `List`     | `"Select network"` |

The `drawHeader()` call in `repaint()` uses `title()` so the header string
updates automatically on each repaint.

---

## State machine

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ PHASE 1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUS ──"Scan networks" tap──► SCANNING
                                    │
                            (scanComplete ≥ 0)
                                    ▼
                                  LIST   ← tap row: placeholder (no-op Phase 1)
                  back ◄──────────────────────
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ PHASE 2 adds ━━━━━━━━━━━━━━━━━━━━━━━━
                                  LIST ──tap open network──► CONNECTING
                                    │
                             tap encrypted network
                                    │
                                    ▼
                                KEYBOARD (KeyboardWidget active)
                                    │
                            submit password
                                    │
                                    ▼
                                CONNECTING
                               /          \
                         success          failure
                            │                │
                            ▼                ▼
                         STATUS           RESULT(fail)
                                             │
                                          "Retry"──► LIST
                                          "Cancel"──► STATUS
```

`< back` at Status → `SectionResult::GoBack` (SettingsApp pops section).
`< back` at Scanning/List → cancel/ignore and return to Status.

---

## Canvas layout

Full 275×240 canvas. Status bar (h=28) shows flow title + back zone.

```
y=0  +-----------------------------------+
     |  < wifi      [title]              |   status bar h=28
y=28 +-----------------------------------+
     |                                   |
     |        content area               |   h=212
     |                                   |
y=240+-----------------------------------+
```

---

## STATUS view

Shows current connection info and a "Scan" action row.

```
+-----------------------------------+
|  < wifi      Status               |
+-----------------------------------+
|  Connected       ●                |   green dot if WL_CONNECTED
|  SSID            MyNetwork        |
|  IP              192.168.1.42     |
|  Signal          ▂▄▆█  -52 dBm   |
|  ──────────────────────────────── |
|  Scan networks   >                |
|  Forget network  >                |   only if connected
+-----------------------------------+
```

"Forget network" calls `WiFi.disconnect(/*wifioff=*/false, /*eraseap=*/true)`
+ `ESP.restart()` to clear NVS credentials.

Signal bars rendering:

```cpp
// RSSI → bar count (1..4)
int bars(int32_t rssi) {
    if (rssi > -50) return 4;
    if (rssi > -60) return 3;
    if (rssi > -70) return 2;
    return 1;
}
// Draw 4 small rectangles (h=4/8/12/16px, w=5px, 2px gap), grey for inactive
```

---

## SCANNING view

Async scan — no blocking. `WiFi.scanNetworks(/*async=*/true)` called on entry.

```
+-----------------------------------+
|  < wifi      Scanning...          |
+-----------------------------------+
|                                   |
|         Scanning for              |
|         networks...               |
|                                   |
|         ◌  (spinner glyph)        |
|                                   |
+-----------------------------------+
```

Each `tick()`: call `WiFi.scanComplete()`.
- Returns `-1` → still scanning, advance spinner frame.
- Returns `-2` → not started (shouldn't happen).
- Returns `≥ 0` → sort results by RSSI descending, transition to LIST.

Spinner: 4-frame cycle using chars `|`, `/`, `─`, `\` drawn at centre.

---

## LIST view

Sorted by RSSI descending. Up to 8 rows visible (212 / 26 = 8.15).
Scrolling deferred — if > 8 networks, show top 8 by signal strength.

```
+-----------------------------------+
|  < wifi      Select network       |
+-----------------------------------+
|  🔒 MyNetwork           ▂▄▆█     |
|  🔒 Neighbour_5G        ▂▄▆░     |
|  🔒 SKY_HD_482F         ▂▄░░     |
|     OpenGuest           ▂▄▆░     |
|  🔒 OFFICE_2G           ▂░░░     |
+-----------------------------------+
```

Encrypted marker: `[E]` text string for `encryptionType != WIFI_AUTH_OPEN` (ASCII fallback; 8×10 bitmap was original intent but not implemented).

Row tap:
- Open network → jump to CONNECTING state directly (`WiFi.begin(ssid)`)
- Encrypted → activate `KeyboardWidget` in `Full` mode, prompt = `"Password: <ssid>"`

```cpp
struct WifiNetwork {
    char     ssid[33];
    int32_t  rssi;
    bool     encrypted;
    uint8_t  channel;
};
WifiNetwork _nets[16];   // top 16 by RSSI; display top 8
uint8_t     _netCount;
```

After scan, populate `_nets` sorted by RSSI:

```cpp
// Sort indices by RSSI descending, copy top 16 into _nets[]
WiFi.scanDelete();  // free library scan buffer after copying
```

---

## KEYBOARD state

Delegates entirely to `KeyboardWidget` (see [keyboard-widget.md](keyboard-widget.md)).

```cpp
// Called when user taps an encrypted network at index i:
void WifiFlow::connectTo(int i) {
    _pendingSsid = _nets[i].ssid;
    char prompt[48];
    snprintf(prompt, sizeof(prompt), "Password: %s", _nets[i].ssid);
    g_keyboard.show(prompt, "", KeyboardWidget::Mode::Full, 64,
        [this](const char* pass) { onPasswordSubmit(pass); },
        [this]()                 { onPasswordCancel(); });
    _s.step = WifiStep::Keyboard;
}

void WifiFlow::onPasswordSubmit(const char* pass) {
    WiFi.begin(_pendingSsid, pass);
    WiFi.persistent(true);   // write to NVS on success
    _s.connectStart = millis();
    _s.step = WifiStep::Connecting;
}

void WifiFlow::onPasswordCancel() {
    _s.step = WifiStep::List;
    repaintList();
}
```

`KeyboardWidget` owns the full canvas while active. `WifiFlow::tick()` and
`handleInput()` forward to `g_keyboard` when `g_keyboard.active()`.

---

## CONNECTING view

Polls `WiFi.status()` each tick with 15s timeout.

```
+-----------------------------------+
|  < wifi      Connecting...        |
+-----------------------------------+
|                                   |
|         Connecting to             |
|         MyNetwork                 |
|                                   |
|         ◌  (spinner)              |
|                                   |
+-----------------------------------+
```

On `WL_CONNECTED` → transition to STATUS, repaint with IP.
On timeout or `WL_CONNECT_FAILED` / `WL_NO_SSID_AVAIL` → transition to
RESULT(fail).

```cpp
// In tick():
if (_s.step == WifiStep::Connecting) {
    wl_status_t st = WiFi.status();
    if (st == WL_CONNECTED) {
        _s.step = WifiStep::Status;
        repaintStatus();
    } else if (millis() - _s.connectStart > 15000 ||
               st == WL_CONNECT_FAILED || st == WL_NO_SSID_AVAIL) {
        _s.failReason = st;
        _s.step = WifiStep::Result;
        repaintResult();
    }
}
```

---

## RESULT (failure) view

```
+-----------------------------------+
|  < wifi      Failed               |
+-----------------------------------+
|                                   |
|   Could not connect to            |
|   MyNetwork                       |
|                                   |
|   Wrong password / out of range   |
|                                   |
|   [  Retry  ]   [  Cancel  ]      |
+-----------------------------------+
```

Error reason from `wl_status_t`:
- `WL_CONNECT_FAILED` → "Wrong password"
- `WL_NO_SSID_AVAIL` → "Network not found"
- timeout → "Timed out"

"Retry" → back to LIST (re-uses cached `_nets[]`).
"Cancel" → STATUS.

---

## State

Phase 1 state is kept as direct members of `WifiSection` (no nested struct):

```cpp
// Phase 1 fields
WifiStep      _step      = WifiStep::Status;
uint8_t       _spinFrame = 0;
unsigned long _lastSpin  = 0;
WifiNet       _nets[16];
uint8_t       _netCount  = 0;

// Phase 2 additions
// char          _pendingSsid[33];
// unsigned long _connectStart;
// wl_status_t   _failReason;
```

`WifiNet` per entry:
```cpp
struct WifiNet {
    char    ssid[33];
    int32_t rssi;
    bool    encrypted;
};
```

---

## Open questions

1. **List scrolling** — top-8 by RSSI covers most cases; if > 8 networks
   are common in the target environment, add scroll gestures in a follow-up pass.
2. **Hidden SSIDs** — `WiFi.scanNetworks(async, /*show_hidden=*/true)` surfaces
   them but they appear with empty SSID string. Show as `[hidden]` row; if
   tapped, launch `KeyboardWidget` for SSID entry first, then password.
3. **Already-connected network** — if the scanned SSID matches `WiFi.SSID()`,
   show "Connected" badge on that row instead of a tap-to-connect action.
4. **WPA3 / enterprise** — `WIFI_AUTH_WPA3_PSK` behaves like WPA2 for our
   purposes; enterprise (802.1X) is not supported by Arduino WiFi.
5. **`WiFi.persistent()` caveat** — credentials written to NVS only after a
   successful connection. If `WiFi.begin()` is called but never connects, NVS
   is unchanged. Current saved network is preserved on failed attempts.

---

## Exit criteria

### Phase 1

- **C1** — `WiFi.scanNetworks(true)` called on "Scan networks" tap; spinner
  advances each tick; LIST populates within 5 s on a typical home network.
- **C1a** — STATUS view shows: connected dot, SSID, IP, signal bars
  (reads live from `WiFi.*` on `enter()`/`repaintStatus()`).
- **C1b** — LIST shows up to 8 networks sorted by RSSI; each row shows SSID
  + signal bars + `[E]` encrypted marker.
- **C1c** — `< back` from Status → SettingsApp category list. `< back` from
  Scanning or List → Status.
- **C1d** — `check_build.sh` passes; no new link errors.

---

## Implementation Status (audit 2026-06-06)

| Area | Status | Notes |
|------|--------|-------|
| Phase 1: STATUS / SCANNING / LIST views | ✅ DONE | |
| Async scan, spinner, signal bars | ✅ DONE | |
| `[E]` encrypted marker | ✅ DONE | Spec body corrected (was "8×10 bitmap") |
| "Forget network" row render | ✅ DONE | Renders greyed when not connected |
| "Forget network" tap handler | ❌ STUB | No-op; marked Phase 2 in impl |
| Phase 2 (connect, keyboard, NVS) | ❌ NOT STARTED | |
| `title()` for Status step | ⚠ DIVERGED | Impl returns `"WiFi"`; spec table says `"Status"` |

### Phase 2

- **C2** — Tapping an open network connects without keyboard; `WiFi.localIP()`
  non-zero within 10 s.
- **C3** — Tapping an encrypted network opens `KeyboardWidget`; submitted
  password passed to `WiFi.begin()`.
- **C4** — Successful connection persists across `ESP.restart()` (NVS-backed).
- **C5** — "Forget network" clears NVS; device boots to wifi tab on next start.
- **C6** — Wrong password shows RESULT(fail) with "Wrong password" message;
  "Retry" returns to LIST with same scan results.
- **C7** — `WiFiManager` and `DoubleResetDetector` removed from `lib_deps`;
  `check_build.sh` passes.
