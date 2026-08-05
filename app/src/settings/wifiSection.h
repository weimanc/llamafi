#pragma once
// wifiSection.h — WiFi scan + status + connect within SettingsApp.
//
// Phase 1: STATUS → SCANNING → LIST (read-only; no connect).
// Phase 2: LIST tap → KEYBOARD (encrypted) or CONNECTING (open); RESULT on fail.
//
// Lifecycle driven by SettingsSection base (ADR-040):
//   enter()        — reset to Status, read live WiFi state
//   leave()        — cancel scan, hide keyboard, abort connect
//   tick()         — Scanning spinner; Connecting poll; Keyboard cursor blink
//   repaint()      — dispatch to repaint*() per _step
//   handleInput()  — tap dispatch; keyboard capture when active

#include <WiFi.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>   // TASK-401: /wifi_networks.json read/write
#include <esp_wifi.h>      // TASK-401: esp_wifi_get_config() reads the just-set NVS
                            // password back out in _onConnectSuccess() -- avoids
                            // keeping a second plaintext copy in a member field
#include "settingsSection.h"
#include "settingsWidgets.h"
#include "keyboardWidget.h"

extern KeyboardWidget g_keyboard;

// ============================================================================
// Enums and data structs
// ============================================================================

enum class WifiStep : uint8_t {
    Status,
    Scanning,
    List,
    Keyboard,
    Connecting,
    Result,
    SavedList,           // TASK-401: "Saved networks" list (Status -> here)
    SavedEntry,          // TASK-401: tapped a saved row -> [Connect]/[Delete]
    SavedDeleteConfirm,  // TASK-401: Danger-styled confirm before delete
};

struct WifiNet {
    char    ssid[33];
    int32_t rssi;
    bool    encrypted;
};

// ============================================================================
// Saved WiFi networks (TASK-401 / M-WIFI-MULTI-AP) — manual-switch-only list,
// separate from both NVS (ESP-IDF holds exactly one active STA profile) and
// the legacy single-entry /wifi_creds.json (host-wizard seed; kept as the
// one-time migration source, see _migrateLegacyIfNeeded() below). Read/write
// only ever happens from WifiSection — no boot-chain or wifiDiag involvement
// (M-WIFI-MULTI-AP §Lean/decision).
// ============================================================================

#define WIFI_NETWORKS_JSON "/wifi_networks.json"
static constexpr uint8_t WIFI_MAX_SAVED = 5;   // OQ3: fits S_MAX_ROWS(8), "home+work+hotspot" recall

struct SavedWifiNet {
    char          ssid[33];
    char          pass[64];
    unsigned long lastUsedMs;
};

static constexpr uint8_t kWifiSavedNotLoaded = 0xFF;   // count sentinel; WIFI_MAX_SAVED caps real counts at 5
struct SavedWifiState {
    SavedWifiNet nets[WIFI_MAX_SAVED];
    uint8_t      count  = kWifiSavedNotLoaded;
    int8_t       selIdx = -1;   // Saved-list sub-view UI state (selected row)
};

// ---- JSON document capacity (mirrors the TASK-329 discipline in
// settingsStorage.cpp's SettingsStorage::save() — a named constant, sized
// with a documented worst-case, never a guessed number) -------------------
// Worst-case measurement (ArduinoJson 6.21.3; 16 B/slot on ESP32):
//   structure: root object (1) + "networks" array (1) +
//              WIFI_MAX_SAVED(5) x (1 object slot + 3 value slots
//              [ssid,pass,lastUsedMs]) = 2 + 5*4 = 22 slots x 16 B = 352 B
//   strings:   "networks" key (~9 B) + 5 x ("ssid"+"pass"+"lastUsedMs" key
//              text, ~21 B) = 114 B, + 5 x (ssid[33] + pass[64] value
//              copies, 97 B) = 485 B
//   worst case                                               ~= 951 B
// 2048 ~= 2.15x that — same "headroom for schema growth" margin as
// kSettingsJsonCapacity. The doc.overflowed() guards in
// _writeSavedToFile()/_loadSavedFromFile() below catch both failure modes
// (undersized capacity AND a failed ctor alloc under fragmentation), same as
// TASK-329's fix.
static constexpr size_t kWifiNetworksJsonCapacity = 2048;

// ============================================================================
// WifiSection
// ============================================================================

class WifiSection : public SettingsSection {
public:
    // ---- SettingsSection contract -------------------------------------------

    const char* title() const override {
        switch (_step) {
            case WifiStep::Scanning:   return "Scanning...";
            case WifiStep::List:       return "Select network";
            case WifiStep::Keyboard:   return "Password";
            case WifiStep::Connecting: return "Connecting...";
            case WifiStep::Result:     return _connectOk ? "Connected" : "Failed";
            case WifiStep::SavedList:  return "Saved networks";
            case WifiStep::SavedEntry:         return _savedSelSsidLive();
            case WifiStep::SavedDeleteConfirm: return "Delete network?";
            default:                   return "WiFi";
        }
    }

    void enter() override {
        WiFi.scanDelete();
        _step      = WifiStep::Status;
        _netCount  = 0;
        // TASK-401: lazy one-time migration + saved-list load. Chosen over a
        // setup()/boot-chain hook — the design's own §Lean/decision requires
        // main.cpp's boot chain get ZERO changes, and this way the first
        // migration touch is a deliberate Settings->WiFi navigation, never
        // part of the boot path. Idempotent (no-op on every visit after the
        // first). See task report for the full "where does migration run"
        // reasoning.
        _ensureSavedLoaded();
        repaint();
    }

    void leave() override {
        if (_step == WifiStep::Scanning) {
            WiFi.scanNetworks(false, false);
            WiFi.scanDelete();
        }
        if (_step == WifiStep::Keyboard && g_keyboard.active()) {
            g_keyboard.hide();
        }
        if (_step == WifiStep::Connecting) {
            WiFi.disconnect();
        }
    }

    SectionResult tick() override {
        // Scanning: synchronous scan runs in _startScan(); tick() is a no-op here.
        if (_step == WifiStep::Scanning) return SectionResult::Continue;

        if (_navHomeAt && millis() >= _navHomeAt) {
            _navHomeAt = 0;
            return SectionResult::NavigateHome;
        }

        if (_step == WifiStep::Connecting) {
            wl_status_t st = WiFi.status();
            if (st == WL_CONNECTED) {
                _connectOk = true;
                _step      = WifiStep::Status;
                // TASK-401: this is the "_startConnect()'s success path" the
                // design's §Lean/decision step 4 names — the single hook that
                // covers BOTH a fresh scan-connect (adds a new saved entry)
                // and a tap-to-connect from the Saved networks list (refreshes
                // lastUsedMs on the existing entry). NVS persistence above is
                // unchanged/untouched.
                _onConnectSuccess();
                _navHomeAt = millis() + 1500;  // show "Connected: Yes" briefly, then return
                repaint();
                return SectionResult::Continue;
            }
            if (millis() - _connectStart > 15000 ||
                st == WL_CONNECT_FAILED || st == WL_NO_SSID_AVAIL) {
                _failReason = st;
                _connectOk  = false;
                _step       = WifiStep::Result;
                repaint();
            }
        }
        return SectionResult::Continue;
    }

    void repaint() override {
        if (_step == WifiStep::Keyboard) return;  // keyboard owns the canvas
        drawHeader();
        clearContent();
        switch (_step) {
            case WifiStep::Status:     repaintStatus();     break;
            case WifiStep::Scanning:   repaintScanning();   break;
            case WifiStep::List:       repaintList();        break;
            case WifiStep::Connecting: repaintConnecting();  break;
            case WifiStep::Result:     repaintResult();      break;
            case WifiStep::SavedList:          repaintSavedList();          break;
            case WifiStep::SavedEntry:         repaintSavedEntry();         break;
            case WifiStep::SavedDeleteConfirm: repaintSavedDeleteConfirm(); break;
            default: break;
        }
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        // Keyboard captures all touch while active.
        if (g_keyboard.active()) {
            g_keyboard.handleInput(phase, x, y);
            return SectionResult::Continue;
        }

        if (phase != TouchPhase::Release) return SectionResult::Continue;

        if (isBackTap(x, y)) {
            if (_step == WifiStep::Status)  return SectionResult::GoBack;
            if (_step == WifiStep::Result) { _step = WifiStep::Status; repaint(); return SectionResult::Continue; }
            // TASK-401: back-tap on the two new sub-steps steps back one level
            // (Confirm's back mirrors its own Cancel — same convention as
            // systemSection.h's reboot-confirm back-tap), not straight to
            // Status like every pre-existing step below.
            if (_step == WifiStep::SavedDeleteConfirm) { _step = WifiStep::SavedEntry; repaint(); return SectionResult::Continue; }
            if (_step == WifiStep::SavedEntry)         { _step = WifiStep::SavedList;  repaint(); return SectionResult::Continue; }
            _step = WifiStep::Status;
            repaint();
            return SectionResult::Continue;
        }

        switch (_step) {
            case WifiStep::Status:   _handleStatusTap(y);   break;
            case WifiStep::Scanning: break;
            case WifiStep::List:     _handleListTap(y);      break;
            case WifiStep::Result:   _handleResultTap(x, y); break;
            case WifiStep::SavedList:          _handleSavedListTap(y);          break;
            case WifiStep::SavedEntry:         _handleSavedEntryTap(x, y);      break;
            case WifiStep::SavedDeleteConfirm: _handleSavedDeleteConfirmTap(x, y); break;
            default: break;
        }
        return SectionResult::Continue;
    }

private:
    // ---- State ---------------------------------------------------------------

    WifiStep      _step        = WifiStep::Status;
    uint8_t       _spinFrame   = 0;
    unsigned long _lastSpin    = 0;
    // TASK-401: shrunk 16->S_MAX_ROWS(8) to reclaim .dram0.bss headroom for
    // the new saved-networks pointer below -- behavior-preserving, not a
    // functional cut: repaintList() below only ever renders
    // min(_netCount, S_MAX_ROWS) rows, so a >8-slot bounded insertion sort
    // and an 8-slot one select the identical top-8-by-RSSI set (any network
    // that would land in the true top 8 is by definition stronger than
    // whatever's in slot 8 of an 8-slot array, so it always survives the
    // insertion-sort shift regardless of cap width >= 8). The extra 8..16
    // capacity was already dead weight for anything ever displayed.
    WifiNet       _nets[S_MAX_ROWS];
    uint8_t       _netCount    = 0;
    int16_t       _scanRowY    = 0;
    int16_t       _forgetRowY  = 0;
    // TASK-401: no separate _savedRowY member -- "Saved networks" is always
    // laid out immediately below "Scan networks" (repaintStatus() below),
    // so _scanRowY + S_ROW_H IS its y with no extra .dram0.bss tenant.

    // Phase 2
    char          _pendingSsid[33]  = {};
    unsigned long _connectStart     = 0;
    unsigned long _navHomeAt        = 0;    // non-zero: millis() target to auto-return after connect
    wl_status_t   _failReason       = WL_IDLE_STATUS;
    bool          _connectOk        = false;

    // ---- Saved networks (TASK-401) --------------------------------------
    // Backing store is a single lazily heap-allocated block, never freed —
    // an embedded SavedWifiNet[5] (~520 B) as a plain member would land in
    // WifiSection's (== g_SettingsApp's) .dram0.bss, which this board's
    // debug build has repeatedly overflowed by mere tens of bytes (see
    // systemSection.h's _confirmBtns() / TeletextApp::_nosSource() /
    // webRadioApp.h's wrPumpConnectUrlBuf() — the established precedent for
    // exactly this failure class). count/selIdx are folded into this same
    // heap block rather than kept as separate members, purely to avoid two
    // extra always-resident bytes — mutable so the const debug accessors
    // (dbgSavedCount()/dbgSavedEntry(), below) can still trigger the lazy
    // load/migrate on first touch. The actual budget fix that made this fit
    // was shrinking the pre-existing _nets[] scan buffer (below), not this
    // pointer's placement — see that comment.
    mutable SavedWifiState* _savedState = nullptr;

    // Result Retry/Cancel — kit buttons on the standard bar (TASK-327; was a
    // hand-rolled 30px pair at y=178). TASK-401: also reused (relabelled) for
    // SavedEntry's [Connect]/[Delete] and SavedDeleteConfirm's [Cancel]/
    // [Delete] — Result, SavedEntry and SavedDeleteConfirm are mutually
    // exclusive steps (never on canvas together), so one 2-slot array covers
    // all three rather than adding a second lazy-allocated one.
    SButton       _resultBtns[2];

    // ---- Repaint helpers -----------------------------------------------------

    void repaintStatus() {
        bool connected = (WiFi.status() == WL_CONNECTED);
        int y = S_CONTENT_Y;

        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(S_LABEL);
        tft.drawString("Connected", S_COL_LABEL, y + S_ROW_H / 2, 2);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(connected ? S_VALUE_ON : S_VALUE_OFF);
        tft.drawString(connected ? "Yes" : "No", S_COL_VALUE, y + S_ROW_H / 2, 2);
        tft.setTextDatum(TL_DATUM);
        y += S_ROW_H;

        if (connected) {
            _drawKV(y, "SSID", WiFi.SSID().c_str()); y += S_ROW_H;
            _drawKV(y, "IP",   WiFi.localIP().toString().c_str()); y += S_ROW_H;

            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(S_LABEL);
            tft.drawString("Signal", S_COL_LABEL, y + S_ROW_H / 2, 2);
            drawSignalBars(S_COL_VALUE - 44, y + (S_ROW_H - 13) / 2, WiFi.RSSI());
            y += S_ROW_H;

            drawSep(y); y += 4;
        }

        _scanRowY = (int16_t)y;
        drawChevronRow(y, "Scan networks");
        y += S_ROW_H;

        // "Saved networks" row: y == _scanRowY + S_ROW_H, always (see the
        // _handleStatusTap() tap-test below) -- no separate stored row-y.
        drawChevronRow(y, "Saved networks");
        y += S_ROW_H;

        _forgetRowY = (int16_t)y;
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(connected ? S_LABEL : S_VALUE_OFF);
        tft.drawString("Forget network", S_COL_LABEL, y + S_ROW_H / 2, 2);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(connected ? S_CHEVRON : S_VALUE_OFF);
        tft.drawString(">", S_COL_VALUE, y + S_ROW_H / 2, 2);
        tft.setTextDatum(TL_DATUM);
    }

    void repaintScanning() {
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_LABEL);
        tft.drawString("Scanning for", S_CANVAS_W / 2, 100, 2);
        tft.drawString("networks...",  S_CANVAS_W / 2, 118, 2);
        _drawSpinner();
        tft.setTextDatum(TL_DATUM);
    }

    void repaintList() {
        int y = S_CONTENT_Y;
        uint8_t show = (_netCount < S_MAX_ROWS) ? _netCount : (uint8_t)S_MAX_ROWS;

        for (uint8_t i = 0; i < show; i++) {
            int mid = y + S_ROW_H / 2;
            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(_nets[i].encrypted ? S_VALUE : S_VALUE_OFF);
            tft.drawString(_nets[i].encrypted ? "[E]" : "   ", S_COL_LABEL, mid, 2);
            tft.setTextColor(S_LABEL);
            tft.drawString(_nets[i].ssid, S_COL_LABEL + 26, mid, 2);
            drawSignalBars(S_COL_VALUE - 44, y + (S_ROW_H - 12) / 2, _nets[i].rssi);
            y += S_ROW_H;
        }

        if (show == 0) {
            tft.setTextDatum(MC_DATUM);
            tft.setTextColor(S_VALUE_OFF);
            tft.drawString("No networks found", S_CANVAS_W / 2, 130, 2);
            tft.setTextDatum(TL_DATUM);
        }
    }

    void repaintConnecting() {
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_LABEL);
        tft.drawString("Connecting to", S_CANVAS_W / 2, 96, 2);
        tft.setTextColor(S_VALUE);
        tft.drawString(_pendingSsid, S_CANVAS_W / 2, 114, 2);
        _drawSpinner();
        tft.setTextDatum(TL_DATUM);
    }

    void repaintResult() {
        const char* reason = "Timed out";
        if (_failReason == WL_CONNECT_FAILED)  reason = "Wrong password";
        if (_failReason == WL_NO_SSID_AVAIL)   reason = "Network not found";

        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(0xF800);  // red
        tft.drawString("Could not connect to", S_CANVAS_W / 2, 80, 2);
        tft.setTextColor(S_VALUE);
        tft.drawString(_pendingSsid, S_CANVAS_W / 2, 98, 2);
        tft.setTextColor(S_VALUE_OFF);
        tft.drawString(reason, S_CANVAS_W / 2, 120, 2);
        tft.setTextDatum(TL_DATUM);

        // Retry=Primary / Cancel=Neutral: the kit's error-screen idiom
        // (matches the location editor's LookupError bar).
        _resultBtns[0].label = "Retry";  _resultBtns[0].style = SBtnStyle::Primary;
        _resultBtns[1].label = "Cancel"; _resultBtns[1].style = SBtnStyle::Neutral;
        sButtonBar(_resultBtns, 2);
        _resultBtns[0].draw();
        _resultBtns[1].draw();
    }

    // ---- Saved networks (TASK-401) --------------------------------------

    // Reuses repaintList()'s layout constants (S_CONTENT_Y/S_ROW_H/S_MAX_ROWS,
    // ML/MR-datum label+chevron shape) rather than duplicating the row
    // renderer — no live RSSI for a saved-but-out-of-range entry, so the
    // signal-bar column is replaced with an OQ5 "currently active" marker
    // instead (recommended-not-blocking in the design; implemented here).
    void repaintSavedList() {
        int y = S_CONTENT_Y;
        uint8_t show = (_st().count < S_MAX_ROWS) ? _st().count : (uint8_t)S_MAX_ROWS;
        SavedWifiNet* nets = _saved();
        bool connected = (WiFi.status() == WL_CONNECTED);
        String curSsid = connected ? WiFi.SSID() : String();

        for (uint8_t i = 0; i < show; i++) {
            int mid = y + S_ROW_H / 2;
            bool active = connected && curSsid == nets[i].ssid;
            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(active ? S_VALUE_ON : S_VALUE_OFF);
            tft.drawString(active ? "*" : " ", S_COL_LABEL, mid, 2);
            tft.setTextColor(active ? S_VALUE_ON : S_LABEL);
            tft.drawString(nets[i].ssid, S_COL_LABEL + 16, mid, 2);
            tft.setTextDatum(MR_DATUM);
            tft.setTextColor(S_CHEVRON);
            tft.drawString(">", S_COL_VALUE, mid, 2);
            tft.setTextDatum(TL_DATUM);
            y += S_ROW_H;
        }

        if (show == 0) {
            tft.setTextDatum(MC_DATUM);
            tft.setTextColor(S_VALUE_OFF);
            tft.drawString("No saved networks", S_CANVAS_W / 2, 130, 2);
            tft.setTextDatum(TL_DATUM);
        }
    }

    void _handleSavedListTap(int py) {
        int row = tapToRow(py);
        if (row < 0 || row >= _st().count) return;
        _st().selIdx = (int8_t)row;
        _step = WifiStep::SavedEntry;
        repaint();
    }

    // Stacked [Connect]/[Delete] rows — same full-width-stacked-row idiom as
    // appsSection.h's SourceFork screen ([Lookup]/[Manual]/[Delete]), just
    // two rows instead of three.
    static constexpr int16_t kSavedEntryBtnY = 90;

    void repaintSavedEntry() {
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_LABEL);
        tft.drawString(_savedSelSsidLive(), S_CANVAS_W / 2, 60, 2);
        tft.setTextDatum(TL_DATUM);

        SButton* btns = _resultBtns;   // reused — see the class-field comment on _resultBtns
        btns[0].r     = sStackedBtnRect(0, kSavedEntryBtnY);
        btns[0].label = "Connect";
        btns[0].style = SBtnStyle::Primary;
        btns[0].draw();

        btns[1].r     = sStackedBtnRect(1, kSavedEntryBtnY);
        btns[1].label = "Delete";
        btns[1].style = SBtnStyle::Danger;
        btns[1].draw();
    }

    void _handleSavedEntryTap(int x, int y) {
        if (_st().selIdx < 0 || _st().selIdx >= (int8_t)_st().count) return;
        SButton* btns = _resultBtns;   // reused — see the class-field comment on _resultBtns
        // Rects were laid out by the repaint() that must have preceded this
        // tap (same "hit-test against last-drawn rects" idiom used
        // throughout this file, e.g. _resultBtns).
        if (btns[0].hit(x, y)) {
            btns[0].flash();
            SavedWifiNet& e = _saved()[_st().selIdx];
            strlcpy(_pendingSsid, e.ssid, sizeof(_pendingSsid));
            _startConnect(e.pass);   // same call shape as a fresh manual connect, sourced from storage
            return;
        }
        if (btns[1].hit(x, y)) {
            btns[1].flash();
            _step = WifiStep::SavedDeleteConfirm;
            repaint();
        }
    }

    // Danger-styled confirm before delete. The design doc cites
    // appsSection.h:900 (PrLoc's Delete button) as the pattern to reuse, but
    // that site is an immediate-delete Danger BUTTON with no confirm step —
    // there is no actual confirm-screen code there to reuse. The real
    // "message + 2-across Danger confirm bar" idiom in this codebase is
    // systemSection.h's reboot confirm (TASK-400, landed the same day),
    // which itself documents mirroring appsSection.h's ManualConfirm/
    // LookupError confirm-frame shape — that's what this mirrors.
    void repaintSavedDeleteConfirm() {
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(0xF800);  // red
        tft.drawString("Delete this network?", S_CANVAS_W / 2, 70, 2);
        tft.setTextColor(S_VALUE, S_BG);
        tft.drawString(_savedSelSsidLive(), S_CANVAS_W / 2, 96, 2);
        tft.setTextColor(S_VALUE_OFF, S_BG);
        tft.drawString("Saved credentials will be", S_CANVAS_W / 2, 118, 2);
        tft.drawString("removed from this device.", S_CANVAS_W / 2, 136, 2);
        tft.setTextDatum(TL_DATUM);

        SButton* btns = _resultBtns;   // reused — see the class-field comment on _resultBtns
        btns[0].label = "Cancel"; btns[0].style = SBtnStyle::Neutral;
        btns[1].label = "Delete"; btns[1].style = SBtnStyle::Danger;
        sButtonBar(btns, 2);
        btns[0].draw();
        btns[1].draw();
    }

    void _handleSavedDeleteConfirmTap(int x, int y) {
        SButton* btns = _resultBtns;   // reused — see the class-field comment on _resultBtns
        if (btns[0].hit(x, y)) {
            btns[0].flash();
            _step = WifiStep::SavedEntry;
            repaint();
            return;
        }
        if (btns[1].hit(x, y)) {
            btns[1].flash();
            _deleteSavedIdx((uint8_t)_st().selIdx);
            _step = WifiStep::SavedList;
            repaint();
        }
    }

    // ---- Spinner -------------------------------------------------------------

    void _drawSpinner() {
        static const char* kFrames = "|/-\\";
        char buf[2] = { kFrames[_spinFrame & 3], 0 };
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_VALUE);
        tft.fillRect(S_CANVAS_W / 2 - 8, 140, 16, 16, S_BG);
        tft.drawString(buf, S_CANVAS_W / 2, 148, 2);
        tft.setTextDatum(TL_DATUM);
    }

    // ---- Signal bars ---------------------------------------------------------

    void drawSignalBars(int16_t x, int16_t y, int32_t rssi) const {
        int barCount = 1;
        if (rssi > -70) barCount = 2;
        if (rssi > -60) barCount = 3;
        if (rssi > -50) barCount = 4;

        static const int16_t kH[4] = { 4, 7, 10, 13 };
        static const int16_t kBW   = 5;
        static const int16_t kGap  = 2;
        static const int16_t kBase = 13;

        for (int b = 0; b < 4; b++) {
            int16_t bx = x + b * (kBW + kGap);
            int16_t by = y + kBase - kH[b];
            tft.fillRect(bx, by, kBW, kH[b], (b < barCount) ? S_VALUE_ON : S_SEP);
        }
    }

    // ---- Tap handlers --------------------------------------------------------

    void _handleStatusTap(int py) {
        if (py >= _scanRowY && py < _scanRowY + S_ROW_H) {
            _startScan();
            return;
        }
        int16_t savedRowY = (int16_t)(_scanRowY + S_ROW_H);   // see repaintStatus()
        if (py >= savedRowY && py < savedRowY + S_ROW_H) {
            _ensureSavedLoaded();
            _step = WifiStep::SavedList;
            repaint();
            return;
        }
        if (WiFi.status() == WL_CONNECTED &&
            py >= _forgetRowY && py < _forgetRowY + S_ROW_H) {
            _doForget();
        }
    }

    void _handleListTap(int py) {
        int row = (py - S_CONTENT_Y) / S_ROW_H;
        if (row < 0 || row >= _netCount) return;
        _connectTo(row);
    }

    void _handleResultTap(int px, int py) {
        if (_resultBtns[0].hit(px, py)) {
            _resultBtns[0].flash();
            _step = WifiStep::List;
            repaint();
        } else if (_resultBtns[1].hit(px, py)) {
            _resultBtns[1].flash();
            _step = WifiStep::Status;
            repaint();
        }
    }

    // ---- Connect flow --------------------------------------------------------

    void _connectTo(int i) {
        strlcpy(_pendingSsid, _nets[i].ssid, sizeof(_pendingSsid));
        if (!_nets[i].encrypted) {
            _startConnect("");
        } else {
            char prompt[48];
            snprintf(prompt, sizeof(prompt), "Password: %.32s", _pendingSsid);
            g_keyboard.show(prompt, "", KeyboardWidget::Mode::Full, 64,
                _onPasswordSubmit, _onPasswordCancel, this);
            _step = WifiStep::Keyboard;
            // Keyboard draws itself; no repaint() needed here.
        }
    }

    void _startConnect(const char* pass) {
        // WiFi.persistent(true): intentional user-initiated connect — acceptable to
        // write to NVS immediately (contrast PATCH-003 which used persistent(false)
        // for unverified file-read credentials).
        WiFi.persistent(true);
        WiFi.mode(WIFI_STA);
        if (pass[0])
            WiFi.begin(_pendingSsid, pass);
        else
            WiFi.begin(_pendingSsid);
        _connectStart = millis();
        _step         = WifiStep::Connecting;
        repaint();
    }

    void _doForget() {
        // TASK-401: scope change only — this used to be the only credential
        // that existed at all; now it removes just the currently-connected
        // entry from the saved list (in addition to what it already did to
        // NVS/wifi_creds.json/reboot, all unchanged below). Read SSID BEFORE
        // disconnect() clears it.
        if (WiFi.status() == WL_CONNECTED) {
            String ssid = WiFi.SSID();
            if (ssid.length()) {
                _ensureSavedLoaded();
                _removeSavedBySsid(ssid.c_str());
            }
        }
        // Clear NVS credentials + remove SPIFFS wifi_creds.json so boot doesn't
        // restore them, then restart.
        WiFi.disconnect(/*wifioff=*/false, /*eraseap=*/true);
        if (SPIFFS.exists("/wifi_creds.json")) SPIFFS.remove("/wifi_creds.json");
        ESP.restart();
    }

    // Static keyboard callbacks (function pointer — not lambda).
    static void _onPasswordSubmit(const char* pass, void* ctx) {
#ifdef SERIAL_DEBUG
        Serial.printf("[wifi] kb:submit pass_len=%u\n", (unsigned)strlen(pass));
#endif
        static_cast<WifiSection*>(ctx)->_startConnect(pass);
    }
    static void _onPasswordCancel(void* ctx) {
#ifdef SERIAL_DEBUG
        Serial.println("[wifi] kb:cancel");
#endif
        WifiSection* self = static_cast<WifiSection*>(ctx);
        self->_step = WifiStep::List;
        self->repaint();
    }

    void _startScan() {
        _step        = WifiStep::Scanning;
        _spinFrame   = 0;
        _lastSpin    = millis();
        repaint();
        // Synchronous scan: blocks ~2-3s but immune to async-scan cancellation
        // by concurrent Spotify task socket attempts on the same core.
        int16_t n = WiFi.scanNetworks(/*async=*/false);
        if (n < 0) { _step = WifiStep::Status; repaint(); return; }
        _netCount = 0;
        for (int16_t i = 0; i < n && _netCount < S_MAX_ROWS; i++) {
            int32_t rssi = WiFi.RSSI(i);
            uint8_t pos = _netCount;
            while (pos > 0 && _nets[pos - 1].rssi < rssi) {
                if (pos < S_MAX_ROWS) _nets[pos] = _nets[pos - 1];
                pos--;
            }
            if (pos < S_MAX_ROWS) {
                strlcpy(_nets[pos].ssid, WiFi.SSID(i).c_str(), sizeof(_nets[0].ssid));
                _nets[pos].rssi      = rssi;
                _nets[pos].encrypted = (WiFi.encryptionType(i) != WIFI_AUTH_OPEN);
                _netCount++;
            }
        }
        WiFi.scanDelete();
        _step = WifiStep::List;
        repaint();
    }

    // ---- Utility -------------------------------------------------------------

    void _drawKV(int y, const char* label, const char* val) const {
        int mid = y + S_ROW_H / 2;
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(S_LABEL);
        tft.drawString(label, S_COL_LABEL, mid, 2);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(S_VALUE);
        tft.drawString(val, S_COL_VALUE, mid, 2);
        tft.setTextDatum(TL_DATUM);
    }

    // ---- Saved-network storage (TASK-401) -------------------------------
    // Everything below is const-qualified (mutable backing fields) so the
    // #ifdef SERIAL_DEBUG accessors at the bottom — called from
    // SettingsApp::dbgGet(), itself `const` — can trigger the lazy
    // migrate+load on first touch (e.g. `get wifiSaved` issued before the
    // user has ever opened Settings -> WiFi this boot).

    // Lazy heap allocation, never freed — see the class-field comment above
    // _savedState for why.
    SavedWifiState& _st() const {
        if (!_savedState) _savedState = new SavedWifiState();
        return *_savedState;
    }
    SavedWifiNet* _saved() const { return _st().nets; }

    // SavedEntry/SavedDeleteConfirm display text — reads _st().selIdx's SSID
    // live out of the saved-list backing store instead of a cached member.
    const char* _savedSelSsidLive() const {
        if (_st().selIdx < 0 || _st().selIdx >= (int8_t)_st().count) return "Saved network";
        return _saved()[_st().selIdx].ssid;
    }

    // Idempotent: migrates the legacy single credential (if present and not
    // already migrated) then loads /wifi_networks.json. Safe to call from
    // enter(), a Status-row tap, or a debug getter — whichever happens first
    // each boot does the work, everything after is a cheap no-op guarded by
    // the kWifiSavedNotLoaded sentinel.
    void _ensureSavedLoaded() const {
        if (_st().count != kWifiSavedNotLoaded) return;
        if (!SPIFFS.exists(WIFI_NETWORKS_JSON)) _migrateLegacyIfNeeded();
        _loadSavedFromFile();   // always runs; sets _st().count to a real 0..WIFI_MAX_SAVED value
    }

    // One-time migration source: the host-wizard's single-entry
    // /wifi_creds.json (main.cpp's boot-chain fallback reads this same file
    // with the same StaticJsonDocument<256> capacity — read-only mirror of
    // that number here, not a new guess). Writes /wifi_networks.json with
    // the migrated entry so this branch never runs again once the file
    // exists (guarded by the caller, _ensureSavedLoaded()).
    void _migrateLegacyIfNeeded() const {
        if (!SPIFFS.exists("/wifi_creds.json")) return;
        File f = SPIFFS.open("/wifi_creds.json", "r");
        if (!f) return;
        StaticJsonDocument<256> doc;
        DeserializationError err = deserializeJson(doc, f);
        f.close();
        if (err != DeserializationError::Ok) return;
        const char* ssid = doc["ssid"] | "";
        if (!ssid[0]) return;
        const char* pass = doc["pass"] | "";
        SavedWifiNet* nets = _saved();
        strlcpy(nets[0].ssid, ssid, sizeof(nets[0].ssid));
        strlcpy(nets[0].pass, pass, sizeof(nets[0].pass));
        // OQ4 (lastUsedMs semantics): no historical connect time exists for
        // the legacy single-file credential — millis() ("now", i.e. this
        // boot) is the least-wrong value; migration counts as first use.
        nets[0].lastUsedMs = millis();
        _st().count = 1;
        _writeSavedToFile();
        Serial.printf("[wifi] migrated legacy /wifi_creds.json -> " WIFI_NETWORKS_JSON " (ssid=%s)\n", ssid);
    }

    void _loadSavedFromFile() const {
        _st().count = 0;
        if (!SPIFFS.exists(WIFI_NETWORKS_JSON)) return;
        File f = SPIFFS.open(WIFI_NETWORKS_JSON, "r");
        if (!f) return;
        DynamicJsonDocument doc(kWifiNetworksJsonCapacity);
        DeserializationError err = deserializeJson(doc, f);
        f.close();
        if (err != DeserializationError::Ok) {
            Serial.printf("[wifi] wifi_networks.json parse error (%s) -- treating as empty\n", err.c_str());
            return;
        }
        // TASK-329 discipline: warn-only, same as SettingsStorage::load() --
        // deserializeJson() should already have returned NoMemory on pool
        // exhaustion, but a silent truncation must never pass unremarked.
        if (doc.overflowed())
            Serial.println("[wifi] wifi_networks.json doc OVERFLOWED on load -- data truncated!");

        SavedWifiNet* nets = _saved();
        for (JsonVariantConst v : doc["networks"].as<JsonArrayConst>()) {
            if (_st().count >= WIFI_MAX_SAVED) break;
            const char* ssid = v["ssid"] | "";
            if (!ssid[0]) continue;
            strlcpy(nets[_st().count].ssid, ssid, sizeof(nets[0].ssid));
            strlcpy(nets[_st().count].pass, v["pass"] | "", sizeof(nets[0].pass));
            nets[_st().count].lastUsedMs = v["lastUsedMs"] | 0UL;
            _st().count++;
        }
    }

    void _writeSavedToFile() const {
        DynamicJsonDocument doc(kWifiNetworksJsonCapacity);
        auto arr = doc.createNestedArray("networks");
        SavedWifiNet* nets = _saved();
        for (uint8_t i = 0; i < _st().count; i++) {
            auto o = arr.createNestedObject();
            o["ssid"]       = nets[i].ssid;
            o["pass"]       = nets[i].pass;
            o["lastUsedMs"] = nets[i].lastUsedMs;
        }
        // TASK-329 discipline, verbatim: never persist a truncated tree.
        // SPIFFS.open(..., "w") truncates the existing file the moment it
        // opens, so this guard MUST run before the open -- abort here and
        // the previous wifi_networks.json stays intact on flash.
        if (doc.overflowed()) {
            Serial.println("[wifi] wifi_networks.json doc OVERFLOWED -- save aborted, previous file kept!");
            return;
        }
        File f = SPIFFS.open(WIFI_NETWORKS_JSON, "w");
        if (!f) { Serial.println("[wifi] failed to open wifi_networks.json for write"); return; }
        size_t written = serializeJson(doc, f);
        f.close();
        if (written == 0) { Serial.println("[wifi] wifi_networks.json write failed"); return; }
        Serial.printf("[wifi] wifi_networks.json saved (doc %u/%u B, %u entries)\n",
                      (unsigned)doc.memoryUsage(), (unsigned)kWifiNetworksJsonCapacity,
                      (unsigned)_st().count);
    }

    // Called from tick()'s WL_CONNECTED branch — see the design's §Lean/
    // decision step 4 ("scan-connect success appends/updates an entry").
    // OQ4 (exact lastUsedMs update timing): chosen to update on EVERY
    // successful connect, not just the first save — otherwise LRU eviction
    // (below) would be meaningless: an entry the user reconnects to often
    // must not look "oldest" just because it was added to the list first.
    void _onConnectSuccess() {
        _ensureSavedLoaded();
        // Read the password back out of the NVS config _startConnect() just
        // wrote (WiFi.persistent(true) + WiFi.begin() above) rather than
        // keeping a second plaintext copy in a member field for the interval
        // between _startConnect() and this tick() callback — one fewer
        // in-RAM copy of a secret, and one fewer .dram0.bss tenant (a 64 B
        // char[] member was the difference between fitting and overflowing
        // the debug build, see the DRAM budget note in the task report).
        wifi_config_t cfg = {};
        const char* pass = "";
        if (esp_wifi_get_config(WIFI_IF_STA, &cfg) == ESP_OK)
            pass = (const char*)cfg.sta.password;

        SavedWifiNet* nets = _saved();
        int idx = -1;
        for (uint8_t i = 0; i < _st().count; i++) {
            if (strcmp(nets[i].ssid, _pendingSsid) == 0) { idx = (int)i; break; }
        }
        unsigned long now = millis();
        if (idx >= 0) {
            // Existing entry: refresh password (may have been retyped/changed)
            // + lastUsedMs.
            strlcpy(nets[idx].pass, pass, sizeof(nets[0].pass));
            nets[idx].lastUsedMs = now;
        } else if (_st().count < WIFI_MAX_SAVED) {
            strlcpy(nets[_st().count].ssid, _pendingSsid, sizeof(nets[0].ssid));
            strlcpy(nets[_st().count].pass, pass, sizeof(nets[0].pass));
            nets[_st().count].lastUsedMs = now;
            _st().count++;
        } else {
            // Full: LRU-evict the entry with the smallest lastUsedMs.
            uint8_t oldest = 0;
            for (uint8_t i = 1; i < _st().count; i++)
                if (nets[i].lastUsedMs < nets[oldest].lastUsedMs) oldest = i;
            strlcpy(nets[oldest].ssid, _pendingSsid, sizeof(nets[0].ssid));
            strlcpy(nets[oldest].pass, pass, sizeof(nets[0].pass));
            nets[oldest].lastUsedMs = now;
        }
        _writeSavedToFile();
    }

    // Used only by _doForget() — removes one entry by SSID (the
    // currently-connected one), never the whole file.
    void _removeSavedBySsid(const char* ssid) {
        SavedWifiNet* nets = _saved();
        for (uint8_t i = 0; i < _st().count; i++) {
            if (strcmp(nets[i].ssid, ssid) == 0) {
                for (uint8_t j = i; j < _st().count - 1; j++) nets[j] = nets[j + 1];
                _st().count--;
                _writeSavedToFile();
                return;
            }
        }
    }

    // Used by the Saved networks list's per-entry Danger-confirm-delete.
    // Deliberately does NOT touch the live connection either way (per the
    // design's exit criteria: "deleting a non-active entry doesn't
    // disconnect" — this path never disconnects, active or not; only
    // "Forget network" does that, and only for the active entry).
    void _deleteSavedIdx(uint8_t idx) {
        if (idx >= _st().count) return;
        SavedWifiNet* nets = _saved();
        for (uint8_t j = idx; j < _st().count - 1; j++) nets[j] = nets[j + 1];
        _st().count--;
        _writeSavedToFile();
    }

public:
#ifdef SERIAL_DEBUG
    // Debug observable (VE-2-1, mandatory per the design): row index <-> SSID
    // mapping + LRU state for an automated harness, same dbgGet-chain
    // pattern as AppsSection::submenu()/prDivKm(). Also doubles as the
    // trigger for the lazy migrate+load if this is the very first touch this
    // boot (keeps `get wifiSaved` usable standalone — see TASK-401 report).
    uint8_t dbgSavedCount() const {
        _ensureSavedLoaded();
        return _st().count;
    }
    // By value, not const&: a static fallback object for the out-of-range
    // guard would itself be a fixed .bss tenant (measured 104 B) — not worth
    // it for a debug-only accessor returning a ~100 B POD by copy.
    SavedWifiNet dbgSavedEntry(uint8_t i) const {
        _ensureSavedLoaded();
        if (i >= _st().count) { SavedWifiNet empty = {}; return empty; }
        return _saved()[i];
    }
#endif
};
