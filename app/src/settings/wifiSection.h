#pragma once
// wifiSection.h — WiFi scan + status section within SettingsApp.
//
// Phase 1: STATUS → SCANNING → LIST (read-only; no connect).
// Phase 2: KEYBOARD → CONNECTING → RESULT (planned; stubs below).
//
// Lifecycle driven by SettingsSection base (ADR-040):
//   enter()        — reset to Status, read live WiFi state
//   leave()        — cancel in-flight scan if any
//   tick()         — Scanning: advance spinner + check WiFi.scanComplete()
//   repaint()      — dispatch to repaint*() per _step
//   handleInput()  — tap dispatch; back tap → GoBack or back-to-Status

#include <WiFi.h>
#include "settingsSection.h"

// ============================================================================
// Enums and data structs
// ============================================================================

enum class WifiStep : uint8_t {
    Status,     // Phase 1
    Scanning,   // Phase 1
    List,       // Phase 1
    // ---- Phase 2 ----
    // Keyboard,
    // Connecting,
    // Result,
};

struct WifiNet {
    char    ssid[33];
    int32_t rssi;
    bool    encrypted;
};

// ============================================================================
// WifiSection
// ============================================================================

class WifiSection : public SettingsSection {
public:
    // ---- SettingsSection contract -------------------------------------------

    const char* title() const override {
        switch (_step) {
            case WifiStep::Scanning: return "Scanning...";
            case WifiStep::List:     return "Select network";
            default:                 return "WiFi";
        }
    }

    void enter() override {
        WiFi.scanDelete();   // discard stale scan buffer from a previous session
        _step      = WifiStep::Status;
        _netCount  = 0;
        repaint();
    }

    void leave() override {
        if (_step == WifiStep::Scanning) {
            // Async scan still in flight — abort it (no blocking wait).
            WiFi.scanNetworks(false, false);   // restart in sync mode = cancels async
            WiFi.scanDelete();
        }
    }

    void tick() override {
        if (_step != WifiStep::Scanning) return;

        // Advance spinner every 200 ms.
        unsigned long now = millis();
        if (now - _lastSpin >= 200) {
            _lastSpin = now;
            _spinFrame = (_spinFrame + 1) & 3;
            _drawSpinner();
        }

        // Check scan completion.
        int16_t n = WiFi.scanComplete();
        if (n == WIFI_SCAN_RUNNING) return;
        if (n == WIFI_SCAN_FAILED)  { _step = WifiStep::Status; repaint(); return; }

        // n ≥ 0: populate _nets[], sort by RSSI descending.
        _netCount = 0;
        for (int16_t i = 0; i < n && _netCount < 16; i++) {
            int32_t rssi = WiFi.RSSI(i);
            // Insertion-sort into _nets by RSSI descending.
            uint8_t pos = _netCount;
            while (pos > 0 && _nets[pos - 1].rssi < rssi) {
                if (pos < 16) _nets[pos] = _nets[pos - 1];
                pos--;
            }
            if (pos < 16) {
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

    void repaint() override {
        drawHeader();
        clearContent();
        switch (_step) {
            case WifiStep::Status:   repaintStatus();   break;
            case WifiStep::Scanning: repaintScanning(); break;
            case WifiStep::List:     repaintList();      break;
        }
    }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return SectionResult::Continue;

        if (isBackTap(x, y)) {
            if (_step == WifiStep::Status) return SectionResult::GoBack;
            _step = WifiStep::Status;
            repaint();
            return SectionResult::Continue;
        }

        switch (_step) {
            case WifiStep::Status:   _handleStatusTap(y);   break;
            case WifiStep::Scanning: /* no-op — scanning */ break;
            case WifiStep::List:     _handleListTap(y);      break;
        }
        return SectionResult::Continue;
    }

private:
    // ---- State ---------------------------------------------------------------

    WifiStep      _step      = WifiStep::Status;
    uint8_t       _spinFrame = 0;
    unsigned long _lastSpin  = 0;
    WifiNet       _nets[16];
    uint8_t       _netCount  = 0;
    int16_t       _scanRowY  = 0;   // screen Y of "Scan networks" row; set in repaintStatus()

    // Phase 2 fields (commented out until needed):
    // char          _pendingSsid[33];
    // unsigned long _connectStart;

    // ---- Repaint helpers -----------------------------------------------------

    void repaintStatus() {
        bool connected = (WiFi.status() == WL_CONNECTED);
        int y = S_CONTENT_Y;

        // Row: Connected
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

        // "Scan networks >" — track Y so the tap handler can hit-test it exactly.
        _scanRowY = (int16_t)y;
        drawChevronRow(y, "Scan networks");
        y += S_ROW_H;

        // "Forget network >" — Phase 2 placeholder (greyed when not connected).
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
        // Spinner glyph will be updated each tick via _drawSpinner().
        _drawSpinner();
        tft.setTextDatum(TL_DATUM);
    }

    void repaintList() {
        int y = S_CONTENT_Y;
        int maxRows = S_MAX_ROWS;   // 8
        uint8_t show = (_netCount < maxRows) ? _netCount : (uint8_t)maxRows;

        for (uint8_t i = 0; i < show; i++) {
            int mid = y + S_ROW_H / 2;

            // Encrypted marker
            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(_nets[i].encrypted ? S_VALUE : S_VALUE_OFF);
            tft.drawString(_nets[i].encrypted ? "[E]" : "   ", S_COL_LABEL, mid, 2);

            // SSID
            tft.setTextColor(S_LABEL);
            tft.drawString(_nets[i].ssid, S_COL_LABEL + 26, mid, 2);

            // Signal bars (right-aligned)
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

    // ---- Spinner (in-place update during Scanning) ---------------------------

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

    // Draws 4 stacked rectangles at (x, y), each 5 px wide, 2 px gap.
    // Heights: 4 / 7 / 10 / 13 px, bottom-aligned.
    // Filled bars = active (S_VALUE_ON); empty = S_SEP.
    void drawSignalBars(int16_t x, int16_t y, int32_t rssi) const {
        int barCount = 1;
        if (rssi > -70) barCount = 2;
        if (rssi > -60) barCount = 3;
        if (rssi > -50) barCount = 4;

        static const int16_t kH[4]   = { 4, 7, 10, 13 };   // bar heights
        static const int16_t kBW     = 5;
        static const int16_t kGap    = 2;
        static const int16_t kBase   = 13;                  // total height

        for (int b = 0; b < 4; b++) {
            int16_t bx = x + b * (kBW + kGap);
            int16_t by = y + kBase - kH[b];
            uint16_t c = (b < barCount) ? S_VALUE_ON : S_SEP;
            tft.fillRect(bx, by, kBW, kH[b], c);
        }
    }

    // ---- Tap handlers --------------------------------------------------------

    void _handleStatusTap(int py) {
        // _scanRowY is set during repaintStatus(); compare directly.
        if (py >= _scanRowY && py < _scanRowY + S_ROW_H) {
            _startScan();
        }
        // Phase 2: "Forget network" tap at _scanRowY + S_ROW_H when connected.
    }

    void _handleListTap(int y) {
        // Phase 1: no-op placeholder.
        // Phase 2: connectTo(tapToRow(y));
        (void)y;
    }

    void _startScan() {
        _step      = WifiStep::Scanning;
        _spinFrame = 0;
        _lastSpin  = millis();
        repaint();
        WiFi.scanNetworks(/*async=*/true);
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
};
