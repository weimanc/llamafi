# Design — WiFi Settings

> Owner: Architect
> Status: draft
> Date: 2026-06-04
> Part of: M-MULTIAPP Settings (`wifi` tab)
> See also: [settings.md](settings.md), [keyboard-widget.md](keyboard-widget.md)

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

## Architecture — WifiFlow as a SettingsApp component

`WifiFlow` is a full-canvas component owned by `SettingsApp`, following the
same pattern as `CalibrationFlow` ([touch-calibration.md](touch-calibration.md)).
It is not a separate `AppId`. Activated when the user enters the `wifi` tab.

```cpp
class WifiFlow {
public:
    void start();
    bool active() const;
    void tick();
    bool handleInput(TouchPhase phase, int x, int y);
private:
    WifiFlowState _s;
    void repaintStatus();
    void repaintScanning();
    void repaintList();
    void repaintConnecting();
    void repaintResult();
    void startScan();
    void connectTo(int networkIdx);
    void onPasswordSubmit(const char* pass);
    void onPasswordCancel();
};
```

---

## State machine

```
STATUS ──"Scan"──► SCANNING
                      │
               (scanComplete ≥ 0)
                      ▼
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

`< back` in the status bar always returns to STATUS (cancels mid-flow without
connecting).

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

Lock icon: small 8×10 px bitmap for `encryptionType != WIFI_AUTH_OPEN`.

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

## State struct

```cpp
enum class WifiStep : uint8_t {
    Status, Scanning, List, Keyboard, Connecting, Result
};

struct WifiFlowState {
    WifiStep     step = WifiStep::Status;
    char         pendingSsid[33];
    unsigned long connectStart;
    wl_status_t  failReason;
    uint8_t      spinnerFrame;
    unsigned long lastSpinMs;
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

- **C1** — `WiFi.scanNetworks(true)` called; LIST populates within 5s on a
  typical home network.
- **C2** — Tapping an open network connects without keyboard; `WiFi.localIP()`
  non-zero within 10s.
- **C3** — Tapping an encrypted network opens `KeyboardWidget`; submitted
  password passed to `WiFi.begin()`.
- **C4** — Successful connection persists across `ESP.restart()` (NVS-backed).
- **C5** — "Forget network" clears NVS; device boots to wifi tab on next start.
- **C6** — Wrong password shows RESULT(fail) with "Wrong password" message;
  "Retry" returns to LIST with same scan results.
- **C7** — `WiFiManager` and `DoubleResetDetector` removed from `lib_deps`;
  `check_build.sh` passes.
