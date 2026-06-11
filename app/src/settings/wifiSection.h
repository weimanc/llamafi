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
#include "settingsSection.h"
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
            case WifiStep::Scanning:   return "Scanning...";
            case WifiStep::List:       return "Select network";
            case WifiStep::Keyboard:   return "Password";
            case WifiStep::Connecting: return "Connecting...";
            case WifiStep::Result:     return _connectOk ? "Connected" : "Failed";
            default:                   return "WiFi";
        }
    }

    void enter() override {
        WiFi.scanDelete();
        _step      = WifiStep::Status;
        _netCount  = 0;
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

    void tick() override {
        // Scanning: synchronous scan runs in _startScan(); tick() is a no-op here.
        if (_step == WifiStep::Scanning) return;

        if (_step == WifiStep::Connecting) {
            wl_status_t st = WiFi.status();
            if (st == WL_CONNECTED) {
                _connectOk = true;
                _step      = WifiStep::Status;
                repaint();
                return;
            }
            if (millis() - _connectStart > 15000 ||
                st == WL_CONNECT_FAILED || st == WL_NO_SSID_AVAIL) {
                _failReason = st;
                _connectOk  = false;
                _step       = WifiStep::Result;
                repaint();
            }
        }
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
            _step = WifiStep::Status;
            repaint();
            return SectionResult::Continue;
        }

        switch (_step) {
            case WifiStep::Status:   _handleStatusTap(y);   break;
            case WifiStep::Scanning: break;
            case WifiStep::List:     _handleListTap(y);      break;
            case WifiStep::Result:   _handleResultTap(x, y); break;
            default: break;
        }
        return SectionResult::Continue;
    }

private:
    // ---- State ---------------------------------------------------------------

    WifiStep      _step        = WifiStep::Status;
    uint8_t       _spinFrame   = 0;
    unsigned long _lastSpin    = 0;
    WifiNet       _nets[16];
    uint8_t       _netCount    = 0;
    int16_t       _scanRowY    = 0;
    int16_t       _forgetRowY  = 0;

    // Phase 2
    char          _pendingSsid[33]  = {};
    unsigned long _connectStart     = 0;
    wl_status_t   _failReason       = WL_IDLE_STATUS;
    bool          _connectOk        = false;

    // Result button regions (fixed layout constants)
    static constexpr int16_t kBtnY      = 178;
    static constexpr int16_t kBtnH      =  30;
    static constexpr int16_t kRetryX    =  16;
    static constexpr int16_t kCancelX   = 148;
    static constexpr int16_t kBtnW      = 110;

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

        // Buttons
        tft.fillRect(kRetryX,  kBtnY, kBtnW, kBtnH, S_SEP);
        tft.fillRect(kCancelX, kBtnY, kBtnW, kBtnH, S_SEP);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_LABEL);
        tft.drawString("Retry",  kRetryX  + kBtnW / 2, kBtnY + kBtnH / 2, 2);
        tft.drawString("Cancel", kCancelX + kBtnW / 2, kBtnY + kBtnH / 2, 2);
        tft.setTextDatum(TL_DATUM);
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
        if (py < kBtnY || py >= kBtnY + kBtnH) return;
        if (px >= kRetryX && px < kRetryX + kBtnW) {
            _step = WifiStep::List;
            repaint();
        } else if (px >= kCancelX && px < kCancelX + kBtnW) {
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
        // Clear NVS credentials + remove SPIFFS wifi_creds.json so boot doesn't
        // restore them, then restart.
        WiFi.disconnect(/*wifioff=*/false, /*eraseap=*/true);
        if (SPIFFS.exists("/wifi_creds.json")) SPIFFS.remove("/wifi_creds.json");
        ESP.restart();
    }

    // Static keyboard callbacks (function pointer — not lambda).
    static void _onPasswordSubmit(const char* pass, void* ctx) {
        static_cast<WifiSection*>(ctx)->_startConnect(pass);
    }
    static void _onPasswordCancel(void* ctx) {
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
        for (int16_t i = 0; i < n && _netCount < 16; i++) {
            int32_t rssi = WiFi.RSSI(i);
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
