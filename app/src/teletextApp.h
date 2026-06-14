#pragma once
// teletextApp.h — NOS Teletekst live reader (M-TELETEXT, ADR-044).
// Single-header App class. Slots into appRegistry.h at index 9.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "dataTask.h"
#include "settingsStorage.h"
#include "gen/teletext_layout.h"
#include "logSink.h"

extern TFT_eSPI tft;

// ── RGB565 teletext colour palette ────────────────────────────────────────────
static const uint16_t kTTColors[8] = {
    0x0000,  // 0 black
    0xF800,  // 1 red
    0x07E0,  // 2 green
    0xFFE0,  // 3 yellow
    0x001F,  // 4 blue
    0xF81F,  // 5 magenta
    0x07FF,  // 6 cyan
    0xFFFF,  // 7 white
};

// ── Mosaic sub-rects within a CHAR_W×CHAR_H (6×8) cell ──────────────────────
// Bit order: 0=top-left, 1=top-right, 2=mid-left, 3=mid-right, 4=bot-left, 5=bot-right
static const int8_t kMosaicRect[6][4] = {  // { dx, dy, w, h }
    { 0, 0, 3, 3 },  // bit 0 top-left
    { 3, 0, 3, 3 },  // bit 1 top-right
    { 0, 3, 3, 3 },  // bit 2 mid-left
    { 3, 3, 3, 3 },  // bit 3 mid-right
    { 0, 6, 3, 2 },  // bit 4 bot-left
    { 3, 6, 3, 2 },  // bit 5 bot-right
};

// ── Fast-text bar colours (red/green/yellow/cyan) ────────────────────────────
static const uint16_t kFtlBarColors[4] = { 0xF800, 0x07E0, 0xFFE0, 0x07FF };

// ── Strip UI colours ─────────────────────────────────────────────────────────
static const uint16_t kStripBg      = 0x1082;  // dark grey ≈ (28,28,28)
static const uint16_t kStripActive  = 0xDEFB;  // light grey ≈ (220,220,220)
static const uint16_t kStripDim     = 0x2104;  // dim grey ≈ (70,70,70) — same as taskbar bg
static const uint16_t kStripBack    = 0x07FF;  // cyan for back zone when history non-empty
static const uint16_t kStripPageNum = 0xA514;  // mid-grey for page number text

// ── Preset start pages ───────────────────────────────────────────────────────
static const uint16_t kPagePresets[] = { 101, 601, 702, 800 };
static const uint8_t  kPollPresets[] = { 30, 60, 120 };

class TeletextApp : public App {
public:
    void init() override {
        memset(&_st, 0, sizeof(_st));
        _st.page = g_settings.teletextPage;
        _histDepth = 0;
        _lastTapMs = 0;
        _lastFetch = _forceNow();
        _pendingFetch = false;
        _lastAction[0] = '\0';
        _injectedContent = false;
    }

    void resume() override {
        _st.page   = g_settings.teletextPage;
        _pollSecs  = g_settings.teletextPollSecs;
        _lastFetch = _forceNow();  // force immediate fetch
        _pendingFetch = false;
        _injectedContent = false;
        _draw();
    }

    void suspend() override {}

    void tick() override {
        unsigned long now = millis();

        // Enqueue fetch when poll interval has elapsed
        if (!_pendingFetch && (now - _lastFetch >= (unsigned long)_pollSecs * 1000UL)) {
            dataTask::enqueueTeletextPage(_st.page);
            _lastFetch = now;
            _pendingFetch = true;
        }

        // Consume result
        dataTask::TeletextState result;
        if (dataTask::pollTeletext(&result)) {
            _pendingFetch = false;
            if (result.ready) {
                _st = result;
                _draw();
            }
        }
    }

    bool handleInput(TouchPhase phase, int x, int y) override {
        if (phase != TouchPhase::Release) return false;

        // 300 ms debounce
        unsigned long now = millis();
        if (now - _lastTapMs < 300) {
            strlcpy(_lastAction, "DEBOUNCE", sizeof(_lastAction));
            return false;
        }
        _lastTapMs = now;

        if (x >= TTXT_STRIP_X && x < TTXT_STRIP_X + TTXT_STRIP_W && y < TTXT_BAR_Y0) {
            return _handleStrip(y);
        }
        if (y >= TTXT_BAR_Y0 && y <= TTXT_BAR_Y1) {
            return _handleBar(x);
        }
        if (y < TTXT_BAR_Y0) {
            return _handleGrid(x, y);
        }
        strlcpy(_lastAction, "NONE", sizeof(_lastAction));
        return false;
    }

    // ── Serial debug accessors ────────────────────────────────────────────────
    bool dbgGet(const char* var, char* buf, int len) const {
        if (strcmp(var, "teletextReady") == 0) {
            snprintf(buf, len, "\"var\":\"teletextReady\",\"ready\":%s,\"last\":true",
                     _st.ready ? "true" : "false");
            return true;
        }
        if (strcmp(var, "teletextPage") == 0) {
            snprintf(buf, len, "\"var\":\"teletextPage\",\"page\":%u,\"last\":true",
                     (unsigned)_st.page);
            return true;
        }
        if (strcmp(var, "teletextPollSecs") == 0) {
            snprintf(buf, len, "\"var\":\"teletextPollSecs\",\"pollSecs\":%u,\"last\":true",
                     (unsigned)_pollSecs);
            return true;
        }
        if (strcmp(var, "teletextHttpCode") == 0) {
            snprintf(buf, len, "\"var\":\"teletextHttpCode\",\"val\":%d,\"last\":true",
                     dataTask::lastTeletextHttpCode());
            return true;
        }
        if (strcmp(var, "teletextLastAction") == 0) {
            snprintf(buf, len, "\"var\":\"teletextLastAction\",\"val\":\"%s\",\"last\":true",
                     _lastAction);
            return true;
        }
        if (strcmp(var, "teletextHasSubpages") == 0) {
            bool has = (_st.subpageNext || _st.subpagePrev);
            snprintf(buf, len, "\"var\":\"teletextHasSubpages\",\"val\":%s,\"last\":true",
                     has ? "true" : "false");
            return true;
        }
        if (strcmp(var, "teletextSubpage") == 0) {
            snprintf(buf, len, "\"var\":\"teletextSubpage\",\"next\":%u,\"prev\":%u,\"last\":true",
                     (unsigned)_st.subpageNext, (unsigned)_st.subpagePrev);
            return true;
        }
        return false;
    }

    bool dbgSet(const char* var, const char* val) {
        if (strcmp(var, "teletextPage") == 0) {
            int pg = atoi(val);
            if (pg >= 100 && pg <= 899) {
                _st.page = (uint16_t)pg;
                g_settings.teletextPage = _st.page;
                _lastFetch = _forceNow();
            }
            return true;
        }
        if (strcmp(var, "triggerTeletextFetch") == 0 && strcmp(val, "1") == 0) {
            _lastFetch = _forceNow();
            _pendingFetch = false;  // allow tick() to enqueue even if prior fetch pending
            return true;
        }
        if (strcmp(var, "teletextPageContent") == 0) {
            // Inject synthetic page content from hex-encoded 2000-char string.
            // Encoding: contiguous hex pairs, e.g. "204e4f53..."
            // 2000 hex chars = 1000 bytes = 25×40 grid.
            int vlen = strlen(val);
            if (vlen == 2000) {
                for (int r = 0; r < 25; r++) {
                    for (int ci = 0; ci < 40; ci++) {
                        int idx = (r * 40 + ci) * 2;
                        char hi = val[idx], lo = val[idx+1];
                        auto hexv = [](char c) -> uint8_t {
                            if (c >= '0' && c <= '9') return c - '0';
                            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
                            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
                            return 0;
                        };
                        _st.cells[r][ci] = (uint8_t)((hexv(hi) << 4) | hexv(lo));
                    }
                }
                _st.ready = true;
                _injectedContent = true;
                _draw();
            }
            return true;
        }
        return false;
    }

private:
    dataTask::TeletextState _st      = {};
    uint8_t  _pollSecs   = 60;
    uint16_t _history[10]= {};
    uint8_t  _histDepth  = 0;
    unsigned long _lastFetch  = 0;
    unsigned long _lastTapMs  = 0;
    bool     _pendingFetch    = false;
    bool     _injectedContent = false;
    char     _lastAction[16]  = {};

    // Returns a _lastFetch sentinel that makes tick()'s elapsed check immediately
    // true regardless of millis() value (handles early-boot case where millis() <
    // pollSecs*1000 and a plain 0 would not trigger the condition).
    unsigned long _forceNow() const {
        return millis() - (unsigned long)_pollSecs * 1000UL;
    }

    // ── Navigation helpers ────────────────────────────────────────────────────
    void _navigate(uint16_t page) {
        if (!page || page < 100 || page > 899) return;
        if (_histDepth < 10) _history[_histDepth++] = _st.page;
        _st.page   = page;
        _lastFetch = 0;  // force fetch
        _pendingFetch = false;
        dataTask::enqueueTeletextPage(page);
    }

    void _goBack() {
        if (_histDepth == 0) return;
        _st.page   = _history[--_histDepth];
        _lastFetch = 0;
        _pendingFetch = false;
        dataTask::enqueueTeletextPage(_st.page);
    }

    // ── Input handlers ───────────────────────────────────────────────────────
    bool _handleStrip(int y) {
        if (y >= TTXT_STRIP_SUBUP_Y0 && y <= TTXT_STRIP_SUBUP_Y1) {
            strlcpy(_lastAction, "STRIP_SUBUP", sizeof(_lastAction));
            if (_st.subpagePrev) _navigate(_st.subpagePrev);
            return true;
        }
        if (y >= TTXT_STRIP_PAGE_Y0 && y <= TTXT_STRIP_PAGE_Y1) {
            strlcpy(_lastAction, "STRIP_PAGE", sizeof(_lastAction));
            // Keypad not yet implemented — cycle through presets as fallback
            uint8_t next = 0;
            for (uint8_t i = 0; i < 4; i++) {
                if (kPagePresets[i] == _st.page) { next = (i + 1) % 4; break; }
            }
            _navigate(kPagePresets[next]);
            return true;
        }
        if (y >= TTXT_STRIP_BACK_Y0 && y <= TTXT_STRIP_BACK_Y1) {
            strlcpy(_lastAction, "STRIP_BACK", sizeof(_lastAction));
            if (_histDepth > 0) _goBack();
            return true;
        }
        if (y >= TTXT_STRIP_PREV_Y0 && y <= TTXT_STRIP_PREV_Y1) {
            strlcpy(_lastAction, "STRIP_PREV", sizeof(_lastAction));
            if (_st.prevPage) _navigate(_st.prevPage);
            return true;
        }
        if (y >= TTXT_STRIP_NEXT_Y0 && y <= TTXT_STRIP_NEXT_Y1) {
            strlcpy(_lastAction, "STRIP_NEXT", sizeof(_lastAction));
            if (_st.nextPage) _navigate(_st.nextPage);
            return true;
        }
        if (y >= TTXT_STRIP_SUBDN_Y0 && y <= TTXT_STRIP_SUBDN_Y1) {
            strlcpy(_lastAction, "STRIP_SUBDN", sizeof(_lastAction));
            if (_st.subpageNext) _navigate(_st.subpageNext);
            return true;
        }
        strlcpy(_lastAction, "NONE", sizeof(_lastAction));
        return false;
    }

    bool _handleBar(int x) {
        int btn = x / TTXT_FTL_BTN_W;
        if (btn < 0) btn = 0;
        if (btn > 3) btn = 3;
        char act[16]; snprintf(act, sizeof(act), "BAR_FTL%d", btn);
        strlcpy(_lastAction, act, sizeof(_lastAction));
        if (_st.ftlTargets[btn]) _navigate(_st.ftlTargets[btn]);
        return true;
    }

    bool _handleGrid(int x, int y) {
        int row = y / TTXT_CHAR_H;
        int tap_col = x / TTXT_CHAR_W;
        if (row < 0 || row >= 25) { strlcpy(_lastAction, "NONE", sizeof(_lastAction)); return false; }

        // Scan row for isolated 3-digit page ref within ±3 cols of tap point
        const uint8_t* rowData = _st.cells[row];
        uint16_t found = 0;
        for (int ci = 0; ci <= 37; ci++) {
            uint8_t c0 = rowData[ci], c1 = rowData[ci+1], c2 = rowData[ci+2];
            if (c0 >= '1' && c0 <= '8' && c1 >= '0' && c1 <= '9' && c2 >= '0' && c2 <= '9') {
                uint16_t pg = (c0-'0')*100 + (c1-'0')*10 + (c2-'0');
                if (pg >= 100 && pg <= 899) {
                    int ref_col = ci + 1;  // centre of 3-digit ref
                    if (abs(ref_col - tap_col) <= 3) { found = pg; break; }
                }
            }
        }
        if (found) {
            strlcpy(_lastAction, "GRID_LINK", sizeof(_lastAction));
            _navigate(found);
            return true;
        }
        strlcpy(_lastAction, "GRID_NONE", sizeof(_lastAction));
        return false;
    }

    // ── Renderer ──────────────────────────────────────────────────────────────
    void _draw() {
        _drawGrid();
        _drawStrip();
        _drawBar();
    }

    void _drawGrid() {
        tft.setTextFont(1);
        tft.setTextDatum(TL_DATUM);
        for (int ri = 0; ri < 25; ri++) {
            uint8_t fg = 7, bg = 0;
            bool gfxMode = false;
            for (int ci = 0; ci < 40; ci++) {
                uint8_t c = _st.cells[ri][ci];
                int px = ci * TTXT_CHAR_W;
                int py = ri * TTXT_CHAR_H;

                // Process control codes (consume; render as background cell)
                if (c >= 0x01 && c <= 0x07) { fg = c; gfxMode = false;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c == 0x10) { fg = 0; gfxMode = true;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c >= 0x11 && c <= 0x17) { fg = c & 0x07; gfxMode = true;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c == 0x1C) { bg = 0;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c == 0x1D) { bg = fg;
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }
                if (c < 0x20) {
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]); continue; }

                if (gfxMode) {
                    // Mosaic: extract 6-bit pattern (bit5 always 1 to stay printable)
                    uint8_t pat = (c & 0x1F) | ((c & 0x40) >> 1);
                    tft.fillRect(px, py, TTXT_CHAR_W, TTXT_CHAR_H, kTTColors[bg]);
                    for (int b = 0; b < 6; b++) {
                        if (pat & (1 << b)) {
                            tft.fillRect(px + kMosaicRect[b][0], py + kMosaicRect[b][1],
                                         kMosaicRect[b][2], kMosaicRect[b][3], kTTColors[fg]);
                        }
                    }
                } else {
                    // Text mode: draw char with fg/bg (Font1 = 6×8 GLCD)
                    tft.drawChar(px, py, (char)c, kTTColors[fg], kTTColors[bg], 1);
                }
            }
        }
    }

    void _drawStrip() {
        tft.fillRect(TTXT_STRIP_X, 0, TTXT_STRIP_W, TTXT_GRID_H, kStripBg);

        int cx = TTXT_STRIP_X + TTXT_STRIP_W / 2;

        // Zone 0 — subpage ▲ (y=0..33)
        {
            uint16_t col = (_st.subpagePrev) ? kStripActive : kStripDim;
            int mid = (TTXT_STRIP_SUBUP_Y0 + TTXT_STRIP_SUBUP_Y1) / 2;
            _drawTriUp(cx, mid - 4, 8, col);
        }
        // Zone 1 — page number (y=34..66)
        {
            int mid = (TTXT_STRIP_PAGE_Y0 + TTXT_STRIP_PAGE_Y1) / 2;
            char pbuf[4]; snprintf(pbuf, sizeof(pbuf), "%u", (unsigned)_st.page);
            tft.setTextFont(1);
            tft.setTextColor(kStripPageNum, kStripBg);
            tft.setTextDatum(MC_DATUM);
            tft.drawString(pbuf, cx, mid, 1);
            tft.setTextDatum(TL_DATUM);
        }
        // Zone 2 — ◄◄ back (y=67..99)
        {
            uint16_t col = (_histDepth > 0) ? kStripBack : kStripDim;
            int mid = (TTXT_STRIP_BACK_Y0 + TTXT_STRIP_BACK_Y1) / 2;
            _drawTriLeft(cx - 2, mid, 6, col);
            _drawTriLeft(cx + 3, mid, 6, col);
        }
        // Zone 3 — ◄ prev page (y=100..132)
        {
            uint16_t col = (_st.prevPage) ? kStripActive : kStripDim;
            int mid = (TTXT_STRIP_PREV_Y0 + TTXT_STRIP_PREV_Y1) / 2;
            _drawTriLeft(cx, mid, 8, col);
        }
        // Zone 4 — ► next page (y=133..165)
        {
            uint16_t col = (_st.nextPage) ? kStripActive : kStripDim;
            int mid = (TTXT_STRIP_NEXT_Y0 + TTXT_STRIP_NEXT_Y1) / 2;
            _drawTriRight(cx, mid, 8, col);
        }
        // Zone 5 — subpage ▼ (y=166..199)
        {
            uint16_t col = (_st.subpageNext) ? kStripActive : kStripDim;
            int mid = (TTXT_STRIP_SUBDN_Y0 + TTXT_STRIP_SUBDN_Y1) / 2;
            _drawTriDown(cx, mid + 4, 8, col);
        }
    }

    void _drawBar() {
        for (int i = 0; i < 4; i++) {
            int x0 = i * TTXT_FTL_BTN_W;
            tft.fillRect(x0, TTXT_BAR_Y0, TTXT_FTL_BTN_W, TTXT_BAR_H, kFtlBarColors[i]);
            if (_st.ftlLabels[i][0]) {
                tft.setTextFont(1);
                tft.setTextColor(TFT_BLACK, kFtlBarColors[i]);
                tft.setTextDatum(MC_DATUM);
                tft.drawString(_st.ftlLabels[i], x0 + TTXT_FTL_BTN_W / 2,
                               TTXT_BAR_Y0 + TTXT_BAR_H / 2, 1);
                tft.setTextDatum(TL_DATUM);
            }
        }
        // Fill right strip bar area (between grid and taskbar, below grid)
        tft.fillRect(TTXT_STRIP_X, TTXT_BAR_Y0, TTXT_STRIP_W, TTXT_BAR_H, kStripBg);
    }

    // ── Arrow glyph helpers (fillTriangle) ───────────────────────────────────
    void _drawTriUp(int cx, int tip_y, int h, uint16_t col) {
        int base_y = tip_y + h;
        int half_w = h / 2;
        tft.fillTriangle(cx, tip_y, cx - half_w, base_y, cx + half_w, base_y, col);
    }
    void _drawTriDown(int cx, int tip_y, int h, uint16_t col) {
        int base_y = tip_y - h;
        int half_w = h / 2;
        tft.fillTriangle(cx, tip_y, cx - half_w, base_y, cx + half_w, base_y, col);
    }
    void _drawTriLeft(int cx, int cy, int h, uint16_t col) {
        int half_w = h / 2;
        tft.fillTriangle(cx - half_w, cy, cx + half_w, cy - half_w, cx + half_w, cy + half_w, col);
    }
    void _drawTriRight(int cx, int cy, int h, uint16_t col) {
        int half_w = h / 2;
        tft.fillTriangle(cx + half_w, cy, cx - half_w, cy - half_w, cx - half_w, cy + half_w, col);
    }
};
