#pragma once
// clockApp.h — Clock with Digital / Flip / Nixie / VFD styles (M-CLOCK-STYLES).

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "settingsStorage.h"
#include "util/timeFmt.h"   // WIRE2-G2/G3: clockHour/clockAmPm/fmtDate
#include "gen/nixie_glyphs.h"   // TASK-336: baked wire-glyph+bloom sprites (bake_nixie.py)
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
    // VFD delta-redraw cache: sentinel values force a full draw on first tick
    // after repaint() (style switch / resume).
    uint8_t       _vfdDigs[4]     = {0xFF, 0xFF, 0xFF, 0xFF};
    int8_t        _vfdColonOn     = -1;

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
                memset(_vfdDigs, 0xFF, sizeof(_vfdDigs));
                _vfdColonOn = -1;
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
    // Geometry + colour palette resynced to the concept tool
    // (app/tools/_clock_flip.py / preview_clock.py) per TASK-337 follow-up —
    // flat card faces (no luminance-ramp gradient) + a 3-tone hinge bevel
    // instead, matching the concept's _draw_card() pipeline.
    static constexpr int     kFpY    = 8;
    static constexpr int     kFpW    = 56;
    static constexpr int     kFpH    = 78;
    static constexpr int     kFpMid  = 38;  // top-half height in px
    static constexpr int     kFpGap  = 2;   // split-line gap
    static constexpr int     kFpR    = 6;
    static constexpr uint16_t kFpBgTop        = 0x31A7;  // concept C_TOP    (55,55,62)
    static constexpr uint16_t kFpBgBot        = 0x2945;  // concept C_BOT    (40,40,46)
    static constexpr uint16_t kFpDigit        = 0xF79D;  // concept C_TEXT   (242,242,235)
    static constexpr uint16_t kFpSplitEdgeTop = 0x1082;  // concept (18,18,20) — shadow at base of top flap
    static constexpr uint16_t kFpSplitGap     = 0x0020;  // concept (5,5,6)   — groove fill
    static constexpr uint16_t kFpSplitEdgeBot = 0x4A4A;  // concept (72,72,84) — highlight at crown of bottom
    static constexpr uint16_t kFpBorder       = 0x4A4B;  // concept C_OUTLINE (75,75,88)
    static constexpr uint16_t kFpBody         = 0x0841;  // concept housing bg (10,10,12)

    void _drawFlip() {
        static const int kFpX[4] = {13, 73, 147, 207};
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
        tft.fillRect(5, 4, 265, 86, kFpBody);
        // Colon — round flip-dots, 1Hz blink (was: static squares, never blinked).
        // M-CLOCK-FLIP.md specs an animated 45deg-rotating disc at 500ms on/off;
        // that needs the tick gate to run at <=500ms even when no digit is
        // flipping (currently 1000ms) — out of scope for this pass, deferred.
        // This still fixes "never blinks at all" with the existing 1Hz cadence
        // Digital already uses (t.tm_sec parity), just via fillCircle instead
        // of fillRect for a rounder, more dot-like face.
        // X/Y/radius match the concept's colon geometry (_COLON_CX/_COLON_Y1/Y2/DOT_R).
        bool colonOn = (t.tm_sec % 2 == 0);
        uint16_t colonC = colonOn ? kFpDigit : (uint16_t)0x2104;
        tft.fillCircle(138, kFpY + 19, 5, colonC);
        tft.fillCircle(138, kFpY + 59, 5, colonC);
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
        static const int kFpX[4] = {13, 73, 147, 207};
        int pi = 0;
        for (int i = 0; i < 4; i++) if (kFpX[i] == px) { pi = i; break; }

        // Flap-height sequence rescaled from the concept's own frame table
        // (38,27,14,4,38 @ CARD_HALF_H=38) to this panel's kFpMid — same
        // proportions, same 5-frame cadence already tuned/approved.
        static const uint8_t kFlapH[5] = {38, 30, 13, 13, 30}; // frame 0..4
        FlipDigit& fd  = _fd[pi];
        int  fh        = fd.frame < 5 ? kFlapH[fd.frame] : kFpMid;
        bool isFalling = (fd.frame <= 2);
        int  cx        = px + kFpW / 2;
        int  mid_y     = kFpY + kFpMid;

        // Choose what digit to show on the flap
        uint8_t flapDig = isFalling ? fd.shown : fd.next;
        char fStr[2] = { (char)('0' + flapDig), '\0' };
        char bStr[2] = { (char)('0' + fd.botShown), '\0' };
        tft.setTextDatum(MC_DATUM);

        // 1. Bottom plate — flat card colour (concept _clock_flip.py draws
        // flat top/bottom halves, no luminance ramp), then glyph anchored at
        // the shared split-line centre (mid_y), clipped to the bottom box via
        // viewport. Both halves draw the SAME anchor point so together they
        // read as one digit split in two, not two complete digits stacked
        // (that was the original bug: each half centred the *full* glyph in
        // its own box with no clip, so the whole digit rendered twice).
        tft.fillRect(px, mid_y + kFpGap, kFpW, kFpMid, kFpBgBot);
        // Falling-flap drop shadow: a shrinking pure-black band cast onto the
        // bottom plate near the hinge while the flap is falling (concept:
        // shadow_h = max(2, top_h/4), flat black — frames 1-2 only here;
        // zero once the flap passes the midpoint or is stable).
        if (isFalling && fd.frame > 0) {
            int sh = max(2, fh / 4);
            tft.fillRect(px, mid_y + kFpGap, kFpW, sh, TFT_BLACK);
        }
        // Text bg matches the flat bottom-card colour directly (no gradient
        // band to track anymore).
        tft.setViewport(px, mid_y + kFpGap, kFpW, kFpMid, false);
        tft.setTextColor(kFpDigit, kFpBgBot);
        tft.drawString(bStr, cx, mid_y, 6);
        tft.resetViewport();

        // 2. Flap background — flat card colour, same as concept's top half.
        tft.fillRect(px, mid_y - fh, kFpW, fh, kFpBgTop);

        // 3. Flap digit — same shared anchor (mid_y), clipped to the flap
        // rect (which shrinks toward mid_y as fh decreases during the fall).
        tft.setViewport(px, mid_y - fh, kFpW, fh, false);
        tft.setTextColor(kFpDigit, kFpBgTop);
        tft.drawString(fStr, cx, mid_y, 6);
        tft.resetViewport();

        // 4. Erase overflow above flap rect (reveals clock body colour)
        if (fh < kFpMid)
            tft.fillRect(px, kFpY, kFpW, kFpMid - fh, kFpBody);

        // 5. Layered hinge bevel (concept's 3-tone split: shadow at the base
        // of the top flap / dark groove / highlight at the crown of the
        // bottom plate) — inset 1px in x so the card border's own left/right
        // edge pixels aren't part of this fill (border is redrawn last anyway
        // since the plate fills above are full-width and would otherwise
        // paint over it, but keeping this inset mirrors the concept exactly).
        tft.fillRect(px + 1, mid_y - 1,            kFpW - 2, 1,       kFpSplitEdgeTop);
        tft.fillRect(px + 1, mid_y,                kFpW - 2, kFpGap,  kFpSplitGap);
        tft.fillRect(px + 1, mid_y + kFpGap - 1,    kFpW - 2, 1,       kFpSplitEdgeBot);

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
            // 1. Baked wire-glyph + hex-mesh + 3-pass-bloom sprite (TASK-336,
            // app/tools/bake_nixie.py) — replaces the flat fillRoundRect+
            // drawString the old steps 1+5 did. Flash-resident RGB565, zero
            // extra RAM (ESP32 flash is memory-mapped, pushImage reads
            // straight out of .rodata).
            tft.pushImage(tx, kTy, kTw, kTh, nixie_glyph_ptrs[digs[i]]);
            // 2. Outer glow
            tft.drawRoundRect(tx - 2, kTy - 2, kTw + 4, kTh + 4, kTr + 1, 0x8000);
            // 3. Inner glow
            tft.drawRoundRect(tx - 1, kTy - 1, kTw + 2, kTh + 2, kTr, 0xFC00);
            // 4. Tube border
            tft.drawRoundRect(tx, kTy, kTw, kTh, kTr, 0xFE60);
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
    // Redraw a single digit slot's 11×24 dot cells (glyph rows 1..22, plus
    // the always-off margin rows 0/23). Only called when that digit's value
    // actually changed — see delta-redraw note on _drawVFD().
    void _drawVFDDigitSlot(int d, uint8_t digitVal, uint8_t dcol) {
        tft.startWrite();
        for (int r = 0; r < 24; r++) {
            int gr = r - 1; // GLYPH_ROW_OFFSET=1
            for (int gc = 0; gc < 11; gc++) {
                bool active = false;
                if (gr >= 0 && gr < 22)
                    active = (kVFDGlyphs[digitVal][gr] >> (10 - gc)) & 1;
                int px = 3 + (dcol + gc) * 5;
                int py = 10 + r * 5;
                tft.fillRect(px, py, 4, 4, active ? 0x069C : 0x0061);
            }
        }
        tft.endWrite();
    }

    // Redraw just the colon's 8 dot cells (cols 26-27, rows 7-8 & 15-16).
    // Only called when colon on/off state actually changed.
    void _drawVFDColon(bool colonOn) {
        uint16_t color = colonOn ? 0x069C : 0x0061;
        tft.startWrite();
        for (int c = 26; c <= 27; c++) {
            for (int r = 7; r <= 8; r++)
                tft.fillRect(3 + c * 5, 10 + r * 5, 4, 4, color);
            for (int r = 15; r <= 16; r++)
                tft.fillRect(3 + c * 5, 10 + r * 5, 4, 4, color);
        }
        tft.endWrite();
    }

    // Delta redraw: the full-grid fillRect + full 1296-cell repaint every
    // 1 s tick (tied to the colon blink period, since that's the only thing
    // that changes most seconds) caused a visible whole-screen flicker.
    // Cache last-drawn digit values + colon state; only repaint the cells
    // that actually changed. Digit slots change at most once/minute; colon
    // toggles once/second but is only 8 cells.
    void _drawVFD() {
        static const uint8_t kDCol[4] = {2, 14, 29, 41}; // glyph start dot-col

        struct tm t; if (!getLocalTime(&t)) return;
        uint8_t hh = clockHour(t);   // WIRE2-G2: digit pair stays two digits ("09")
        uint8_t digs[4] = {
            (uint8_t)(hh / 10), (uint8_t)(hh % 10),
            (uint8_t)(t.tm_min  / 10), (uint8_t)(t.tm_min  % 10)
        };
        bool colonOn = (t.tm_sec % 2 == 0);

        for (int d = 0; d < 4; d++) {
            if (digs[d] != _vfdDigs[d]) {
                _drawVFDDigitSlot(d, digs[d], kDCol[d]);
                _vfdDigs[d] = digs[d];
            }
        }
        if ((int8_t)colonOn != _vfdColonOn) {
            _drawVFDColon(colonOn);
            _vfdColonOn = (int8_t)colonOn;
        }

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
