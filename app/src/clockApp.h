#pragma once
// clockApp.h — Clock with Digital / Flip / Nixie / VFD styles (M-CLOCK-STYLES).

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "settingsStorage.h"
#include "util/timeFmt.h"   // WIRE2-G2/G3: clockHour/clockAmPm/fmtDate
#include <WiFi.h>
#include <time.h>
#include <math.h>

extern TFT_eSPI tft;

// ── VFD glyph data — Dexter v2 (11 cols × 22 rows, bit 10 = leftmost col) ──
static const uint16_t kVFDGlyphs[10][22] = {
    { 0x03FE,0x07FF,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0607,0x0607,0x0607,0x0607,0x0607,0x07FF,0x03FE }, // 0
    { 0x01E0,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x0060,0x01FC,0x01FC }, // 1
    { 0x01FE,0x01FF,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x07FF,0x07FF,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x07FC,0x03FC }, // 2
    { 0x01FE,0x01FF,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x01FF,0x01FF,0x0003,0x0003,0x0003,0x0007,0x0007,0x0007,0x0007,0x0007,0x01FF,0x01FE }, // 3
    { 0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x07FF,0x07FF,0x0003,0x0003,0x0003,0x0007,0x0007,0x0007,0x0007,0x0007,0x0007,0x0007 }, // 4
    { 0x03FC,0x07FC,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x07FF,0x07FF,0x0003,0x0003,0x0003,0x0007,0x0007,0x0007,0x0007,0x0007,0x01FF,0x01FE }, // 5
    { 0x03FC,0x07FC,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x0600,0x07FF,0x07FF,0x0603,0x0603,0x0603,0x0607,0x0607,0x0607,0x0607,0x0607,0x07FF,0x03FE }, // 6
    { 0x01FE,0x01FF,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x0003,0x000F,0x000F,0x000F,0x000C,0x001C,0x001C,0x001C,0x001C,0x001C,0x001C,0x001C }, // 7
    { 0x03FE,0x07FF,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x07FF,0x07FF,0x0603,0x0603,0x0603,0x0607,0x0607,0x0607,0x0607,0x0607,0x07FF,0x03FE }, // 8
    { 0x03FE,0x07FF,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x0603,0x07FF,0x07FF,0x0003,0x0003,0x0003,0x0007,0x0007,0x0007,0x0007,0x0007,0x01FF,0x01FE }, // 9
};

// ── FlipDigit state ──────────────────────────────────────────────────────────
struct FlipDigit {
    uint8_t shown;    // digit shown in top half (current stable)
    uint8_t next;     // digit to flip to
    uint8_t botShown; // digit shown in bottom half (switches at start of animation)
    uint8_t frame;    // 0=stable; 1..4=animating
};

class ClockApp : public App {
public:
    void init()    override { repaint(); }
    void resume()  override { repaint(); }
    void suspend() override { tft.setTextDatum(TL_DATUM); }

    void tick() override {
        unsigned long now = millis();
        bool anyFlip = (g_settings.clockStyle == ClockStyle::Flip) && _anyFlipActive();
        unsigned long gate = anyFlip ? 30 : 1000;
        if (now - _lastTickMs < gate) return;
        _lastTickMs = now;
        _doTick();
    }

    bool handleInput(TouchPhase, int, int) override { return false; }

private:
    unsigned long _lastTickMs = 0;
    FlipDigit     _fd[4]      = {};
    // W-6 erase-gating cache (Digital): last rendered hour string + AM/PM ptr.
    char          _lastHourStr[4] = "";
    const char*   _lastAmPm       = nullptr;

    bool _anyFlipActive() const {
        for (int i = 0; i < 4; i++) if (_fd[i].frame > 0) return true;
        return false;
    }

    void repaint() {
        switch (g_settings.clockStyle) {
            case ClockStyle::Flip:
                tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
                memset(_fd, 0, sizeof(_fd));
                break;
            case ClockStyle::Nixie:
                tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
                break;
            case ClockStyle::VFD:
                tft.fillRect(0, 0, TASKBAR_X, 240, 0x0022);
                break;
            default: // Digital
                tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
                tft.drawRoundRect(5,   5, 265,  80, 10, 0xF81F);
                tft.drawRoundRect(5,  88, 265,  47, 10, 0x07FF);
                tft.drawRoundRect(5, 138, 265,  97, 10, 0xFFE0);
                break;
        }
        _lastTickMs = 0;
        tick();
    }

    void _doTick() {
        switch (g_settings.clockStyle) {
            case ClockStyle::Flip:
                _drawFlip();
                if (!_anyFlipActive()) { _drawDate(); _drawRssi(); }
                break;
            case ClockStyle::Nixie:
                _drawNixie();
                _drawDate();
                _drawRssi();
                break;
            case ClockStyle::VFD:
                _drawVFD();
                _drawRssi();
                break;
            default:
                _drawDigital();
                _drawSecondsBar();
                _drawDate();
                _drawRssi();
                break;
        }
    }

    // ── Digital ─────────────────────────────────────────────────────────────
    void _drawDigital() {
        struct tm t; if (!getLocalTime(&t)) return;
        char hBuf[4], mBuf[4];
        // WIRE2-G2: 12h drops the leading zero (%d, "9:41"); 24h keeps %02d.
        snprintf(hBuf, sizeof(hBuf), g_settings.fmt24h ? "%02d" : "%d", clockHour(t));
        snprintf(mBuf, sizeof(mBuf), "%02d", t.tm_min);
        const char* ap = clockAmPm(t);   // nullptr in 24h mode
        // W-6: hour is MR-anchored overpaint — a narrower string (12:59→1:00)
        // or an AM/PM mode toggle leaves stale pixels. Explicit erase of the
        // hour + AM/PM areas, gated on content change so the 1 Hz tick doesn't
        // flicker the steady-state face.
        if (strcmp(hBuf, _lastHourStr) != 0 || ap != _lastAmPm) {
            tft.fillRect(16, 21, 113, 48, TFT_BLACK);   // hour area (MR @129, font 6)
            tft.fillRect(228, 10, 38, 20, TFT_BLACK);   // AM/PM area (top-right of cell)
            strncpy(_lastHourStr, hBuf, sizeof(_lastHourStr));
            _lastAmPm = ap;
        }
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.setTextDatum(MR_DATUM);
        tft.drawString(hBuf, 129, 45, 6);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor((t.tm_sec % 2 == 0) ? TFT_WHITE : TFT_BLACK, TFT_BLACK);
        tft.drawString(":", 137, 45, 6);
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.drawString(mBuf, 145, 45, 6);
        if (ap) {   // T-TIME-02: small AM/PM label, top-right of the time cell
            tft.setTextDatum(TR_DATUM);
            tft.drawString(ap, 262, 12, 2);
        }
        tft.setTextDatum(TL_DATUM);
    }

    // ── Seconds bar (Digital) ────────────────────────────────────────────────
    void _drawSecondsBar() {
        struct tm t; if (!getLocalTime(&t)) return;
        for (int i = 0; i < 60; ++i) {
            uint16_t c = (i < t.tm_sec) ? tft.color565(
                (int)(sinf((float)i / 60.0f * TWO_PI)                    * 127 + 128),
                (int)(sinf((float)i / 60.0f * TWO_PI + TWO_PI / 3.0f)   * 127 + 128),
                (int)(sinf((float)i / 60.0f * TWO_PI + 2*TWO_PI / 3.0f) * 127 + 128)
            ) : (uint16_t)0x07FF;
            tft.fillRect(8 + (int)((float)i * 4.3f), 100, 2, 25, c);
        }
    }

    // ── Date (all non-VFD styles) ────────────────────────────────────────────
    void _drawDate() {
        struct tm t; if (!getLocalTime(&t)) return;
        static const char* kDays[] = {"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(TFT_WHITE, TFT_BLACK);
        tft.drawString(kDays[t.tm_wday], 137, 170, 4);
        char dBuf[16];
        fmtDate(t, dBuf, sizeof(dBuf), '/');   // WIRE2-G3: DMY/MDY/YMD per settings
        tft.drawString(dBuf, 137, 200, 4);
        tft.setTextDatum(TL_DATUM);
    }

    // ── RSSI indicator ───────────────────────────────────────────────────────
    void _drawRssi() {
        int rssi = WiFi.RSSI();
        int bars = (rssi > -55) ? 4 : (rssi > -65) ? 3 : (rssi > -75) ? 2 : 1;
        for (int i = 0; i < 4; ++i) {
            uint16_t c = (i < bars) ? TFT_GREEN : (uint16_t)0x4208;
            tft.fillRect(240 + i * 7, 228 - (i + 1) * 5, 5, (i + 1) * 5, c);
        }
    }

    // ── Flip ────────────────────────────────────────────────────────────────
    // Panel layout: 4 panels at kFpX[], y=kFpY, w=kFpW, h=kFpH
    // Split at y=kFpY+kFpMid; gap=kFpGap; corner radius=kFpR
    // Colour palette from M-CLOCK-FLIP.md parameter table
    static constexpr int     kFpY    = 14;
    static constexpr int     kFpW    = 46;
    static constexpr int     kFpH    = 62;
    static constexpr int     kFpMid  = 30;  // top-half height in px
    static constexpr int     kFpGap  = 2;   // split-line gap
    static constexpr int     kFpR    = 5;
    static constexpr uint16_t kFpBgTop  = 0x2945;
    static constexpr uint16_t kFpBgBot  = 0x18C3;
    static constexpr uint16_t kFpDigit  = 0xFFF0;
    static constexpr uint16_t kFpSplit  = 0x0861;
    static constexpr uint16_t kFpBorder = 0x4208;
    static constexpr uint16_t kFpBody   = 0x1082;

    void _drawFlip() {
        static const int kFpX[4] = {10, 60, 130, 180};
        struct tm t; if (!getLocalTime(&t)) return;
        uint8_t hh = clockHour(t);   // WIRE2-G2: digit pair stays two digits ("09")
        uint8_t newDig[4] = {
            (uint8_t)(hh / 10), (uint8_t)(hh % 10),
            (uint8_t)(t.tm_min  / 10), (uint8_t)(t.tm_min  % 10)
        };
        // Start animation for any changed digit
        for (int i = 0; i < 4; i++) {
            if (_fd[i].frame == 0 && _fd[i].shown != newDig[i]) {
                _fd[i].next     = newDig[i];
                _fd[i].botShown = newDig[i]; // bottom switches immediately
                _fd[i].frame    = 1;
            }
        }
        // Clock body background
        tft.fillRect(5, 5, 265, 80, kFpBody);
        // Colon dots — static, no blink (M-CLOCK-FLIP.md)
        tft.fillRect(118, kFpY + 12, 5, 5, kFpDigit);
        tft.fillRect(118, kFpY + 36, 5, 5, kFpDigit);
        // Draw and advance each panel
        for (int i = 0; i < 4; i++) {
            _drawFlipPanel(kFpX[i]);
            if (_fd[i].frame > 0) {
                _fd[i].frame++;
                if (_fd[i].frame >= 5) {
                    _fd[i].shown    = _fd[i].next;
                    _fd[i].botShown = _fd[i].next;
                    _fd[i].frame    = 0;
                }
            }
        }
    }

    // Draws one flip panel for _fd[pi] state.
    // flap is anchored at split line, extends upward by fh pixels.
    void _drawFlipPanel(int px) {
        // Determine which digit index this px belongs to
        static const int kFpX[4] = {10, 60, 130, 180};
        int pi = 0;
        for (int i = 0; i < 4; i++) if (kFpX[i] == px) { pi = i; break; }

        static const uint8_t kFlapH[5] = {30, 24, 10, 10, 24}; // frame 0..4
        FlipDigit& fd  = _fd[pi];
        int  fh        = fd.frame < 5 ? kFlapH[fd.frame] : 30;
        bool isFalling = (fd.frame <= 2);
        int  cx        = px + kFpW / 2;
        int  mid_y     = kFpY + kFpMid;

        // Choose what digit to show on the flap
        uint8_t flapDig = isFalling ? fd.shown : fd.next;
        char fStr[2] = { (char)('0' + flapDig), '\0' };
        char bStr[2] = { (char)('0' + fd.botShown), '\0' };

        // 1. Bottom plate — always shows botShown (new digit after switch)
        tft.fillRect(px, mid_y + kFpGap, kFpW, kFpMid, kFpBgBot);
        tft.setTextColor(kFpDigit, kFpBgBot);
        tft.setTextDatum(MC_DATUM);
        tft.drawString(bStr, cx, mid_y + kFpGap + kFpMid / 2, 4);

        // 2. Flap background
        tft.fillRect(px, mid_y - fh, kFpW, fh, kFpBgTop);

        // 3. Flap digit (centered in full top half, clipped by overpainting)
        tft.setTextColor(kFpDigit, kFpBgTop);
        tft.drawString(fStr, cx, kFpY + kFpMid / 2, 4);

        // 4. Erase overflow above flap rect (reveals clock body colour)
        if (fh < kFpMid)
            tft.fillRect(px, kFpY, kFpW, kFpMid - fh, kFpBody);

        // 5. Split line
        tft.fillRect(px, mid_y, kFpW, kFpGap, kFpSplit);

        // 6. Panel border
        tft.drawRoundRect(px, kFpY, kFpW, kFpH, kFpR, kFpBorder);

        tft.setTextDatum(TL_DATUM);
    }

    // ── Nixie ───────────────────────────────────────────────────────────────
    void _drawNixie() {
        static const int kTx[4] = {6, 62, 128, 184};
        static const int kTy = 10, kTw = 52, kTh = 70, kTr = 26;

        struct tm t; if (!getLocalTime(&t)) return;
        uint8_t hh = clockHour(t);   // WIRE2-G2: digit pair stays two digits ("09")
        uint8_t digs[4] = {
            (uint8_t)(hh / 10), (uint8_t)(hh % 10),
            (uint8_t)(t.tm_min  / 10), (uint8_t)(t.tm_min  % 10)
        };

        tft.fillRect(0, 5, 275, 82, TFT_BLACK);

        // Colon dots — blinking at 0.5 Hz
        bool colonOn = (t.tm_sec % 2 == 0);
        uint16_t colonC = colonOn ? (uint16_t)0xFE60 : (uint16_t)0x4000;
        tft.fillRect(119, kTy + 18, 4, 4, colonC);
        tft.fillRect(119, kTy + 45, 4, 4, colonC);

        for (int i = 0; i < 4; i++) {
            int tx = kTx[i], cx = tx + kTw / 2;
            // 1. Black fill inside tube
            tft.fillRoundRect(tx, kTy, kTw, kTh, kTr, TFT_BLACK);
            // 2. Outer glow
            tft.drawRoundRect(tx - 2, kTy - 2, kTw + 4, kTh + 4, kTr + 1, 0x8000);
            // 3. Inner glow
            tft.drawRoundRect(tx - 1, kTy - 1, kTw + 2, kTh + 2, kTr, 0xFC00);
            // 4. Tube border
            tft.drawRoundRect(tx, kTy, kTw, kTh, kTr, 0xFE60);
            // 5. Digit
            char buf[2] = { (char)('0' + digs[i]), '\0' };
            tft.setTextDatum(MC_DATUM);
            tft.setTextColor(TFT_WHITE, TFT_BLACK);
            tft.drawString(buf, cx, kTy + kTh / 2, 4);
            // 6. Pin shadows
            tft.fillRect(cx - 8, kTy + kTh - 3, 4, 4, 0x2104);
            tft.fillRect(cx + 4, kTy + kTh - 3, 4, 4, 0x2104);
        }
        tft.setTextDatum(TL_DATUM);
    }

    // ── VFD ─────────────────────────────────────────────────────────────────
    // Dot grid: 54 cols × 24 rows, TC=4px, TG=1px, GRID_X0=3, GRID_Y0=10
    // Glyph start cols (dot units): H1=2, H2=14, M1=29, M2=41
    // Colon: 2×2 dot block at rows 7-8 and 15-16, cols 26-27
    // Palette (RGB565): BG=0x0022, ON=0x069C, OFF=0x0061, DATE=0x0473
    void _drawVFD() {
        static const uint8_t kDCol[4] = {2, 14, 29, 41}; // glyph start dot-col

        struct tm t; if (!getLocalTime(&t)) return;
        uint8_t hh = clockHour(t);   // WIRE2-G2: digit pair stays two digits ("09")
        uint8_t digs[4] = {
            (uint8_t)(hh / 10), (uint8_t)(hh % 10),
            (uint8_t)(t.tm_min  / 10), (uint8_t)(t.tm_min  % 10)
        };
        bool colonOn = (t.tm_sec % 2 == 0);

        tft.fillRect(0, 0, TASKBAR_X, 240, 0x0022);

        tft.startWrite();
        for (int r = 0; r < 24; r++) {
            for (int c = 0; c < 54; c++) {
                int px = 3 + c * 5;
                int py = 10 + r * 5;
                uint16_t color = 0x0022; // BG — skip unless it's a dot cell

                // Check digit glyph slots
                for (int d = 0; d < 4; d++) {
                    int gc = c - kDCol[d];
                    if (gc >= 0 && gc < 11) {
                        int gr = r - 1; // GLYPH_ROW_OFFSET=1
                        bool active = false;
                        if (gr >= 0 && gr < 22)
                            active = (kVFDGlyphs[digs[d]][gr] >> (10 - gc)) & 1;
                        color = active ? 0x069C : 0x0061;
                        break;
                    }
                }
                // Colon dots (rows 7-8 and 15-16, dot cols 26-27)
                if ((c == 26 || c == 27) &&
                    ((r >= 7 && r <= 8) || (r >= 15 && r <= 16))) {
                    color = colonOn ? 0x069C : 0x0061;
                }

                if (color != 0x0022)
                    tft.fillRect(px, py, 4, 4, color);
            }
        }
        tft.endWrite();

        // Date below digit block (y≈141 per approved constants)
        static const char* kDays[] = {"Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"};
        char dBuf[12];
        fmtDate(t, dBuf, sizeof(dBuf), '-');   // WIRE2-G3: VFD-only date line (W-10)
        tft.setTextSize(2);
        tft.setTextColor(0x0473, 0x0022);
        tft.setTextDatum(MC_DATUM);
        tft.drawString(kDays[t.tm_wday], 137, 148, 1);
        tft.drawString(dBuf, 137, 166, 1);
        tft.setTextSize(1);
        tft.setTextDatum(TL_DATUM);
    }
};
