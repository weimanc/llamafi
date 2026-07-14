#pragma once
#include <Arduino.h>
#include <TFT_eSPI.h>
#include <cctype>
#include "../touchPhase.h"
#include "../touch/hitbox.h"
#include "settingsSection.h"

extern TFT_eSPI tft;

// ============================================================================
// KeyboardWidget — modal full-canvas on-screen keyboard
//
// Canvas: 275×240 left canvas (taskbar strip x≥275 untouched).
// Activation: call show(); keyboard captures all touch input while active.
// ============================================================================

#define KB_INPUT_H    40
#define KB_ROW_H      40
#define KB_KEY_W      27
#define KB_CANVAS_W  275

// ---- Key tables (static file-scope to avoid ODR issues with constexpr) ----

static constexpr char kRow1[10] = {'Q','W','E','R','T','Y','U','I','O','P'};
static constexpr char kRow2[9]  = {'A','S','D','F','G','H','J','K','L'};
static constexpr char kRow3[7]  = {'Z','X','C','V','B','N','M'};

// kSym[page-2][row][col];  '\0' = empty / non-interactive cell
static constexpr char kSym[2][4][10] = {
    {   // page 2
        {'1','2','3','4','5','6','7','8','9','0'},
        {'!','@','#','$','%','^','&','*','(',')'},
        {'-','_','=','+','[',']','{','}','\\','|'},
        {'\0','\0','\0','\0','\0','\0','\0','\0','\0','\0'},
    },
    {   // page 3
        {';',':','\'','"',',','.','/','>','<','?'},
        {'~','`','\0','\0','\0','\0','\0','\0','\0','\0'},
        {'\0','\0','\0','\0','\0','\0','\0','\0','\0','\0'},
        {'\0','\0','\0','\0','\0','\0','\0','\0','\0','\0'},
    },
};

class KeyboardWidget {
public:
    enum class Mode : uint8_t {
        Full,       // a-z, A-Z (shift), 0-9, symbols — WiFi passwords
        UpperAlpha, // A-Z only + backspace/OK — tickers, short codes
    };

    // Action codes returned by internal _hitTest()
    static constexpr uint8_t ACT_SHIFT     = 1;
    static constexpr uint8_t ACT_BACKSPACE = 2;
    static constexpr uint8_t ACT_SYM       = 3;
    static constexpr uint8_t ACT_SPACE     = 4;
    static constexpr uint8_t ACT_OK        = 5;
    static constexpr uint8_t ACT_ABC       = 6;
    static constexpr uint8_t ACT_NEXT      = 7;
    static constexpr uint8_t ACT_CANCEL    = 8;

    // ---- Public interface ---------------------------------------------------

    // Activate the keyboard. Caller retains ownership of prompt/initial strings.
    void show(const char*  prompt,
              const char*  initial,
              Mode         mode,
              uint8_t      maxLen,
              void (*onSubmit)(const char* text, void* ctx),
              void (*onCancel)(void* ctx),
              void*        ctx)
    {
        _active    = true;
        _mode      = mode;
        _maxLen    = (maxLen < 64) ? maxLen : 64;
        _onSubmit  = onSubmit;
        _onCancel  = onCancel;
        _ctx       = ctx;

        // Copy prompt (truncate to fit)
        strncpy(_prompt, prompt ? prompt : "", sizeof(_prompt) - 1);
        _prompt[sizeof(_prompt) - 1] = '\0';

        // Copy initial value
        _len = 0;
        if (initial) {
            while (_len < _maxLen && initial[_len]) {
                _buf[_len] = initial[_len];
                _len++;
            }
        }
        _buf[_len] = '\0';

        // Page setup
        _page           = (mode == Mode::UpperAlpha) ? 1 : 0;
        _oneShot        = false;
        _blinkVisible   = true;
        _blinkMs        = millis();
        _pressHighlight = false;
        _pressRow       = -1;
        _pressCol       = -1;
        _dirty          = false;

        repaint();
    }

    void hide() {
        _active = false;
        // Caller is responsible for repainting their own canvas after hide()
    }

    bool active() const { return _active; }

    // Called every loop iteration. Handles cursor blink and press-highlight revert.
    void tick() {
        if (!_active) return;

        // Cursor blink — 500 ms toggle (same millis()-delta idiom as wifiSection.h:72)
        uint32_t now = millis();
        if (now - _blinkMs >= 500) {
            _blinkMs      = now;
            _blinkVisible = !_blinkVisible;
            repaintInputBar();   // partial repaint — key rows unchanged
        }

        // Press-highlight: revert key cell on the tick after the press
        if (_pressHighlight) {
            bool wasInputBar = (_pressRow < 0);
            _pressHighlight = false;
            repaintKeys();
            if (wasInputBar) repaintInputBar();
        }
    }

    // Returns true if the keyboard consumed the input.
    bool handleInput(TouchPhase phase, int x, int y) {
        if (!_active) return false;

        if (phase == TouchPhase::Press) {
            // Highlight the pressed key for one tick
            _pressRow       = (y >= KB_INPUT_H) ? (y - KB_INPUT_H) / KB_ROW_H : -1;
            _pressCol       = _pressColForXY(x, y);
            _pressHighlight = true;
            repaintKeys();
            if (_pressRow < 0) repaintInputBar();   // cancel / bksp shortcut zones
            return true;
        }

        if (phase == TouchPhase::Release) {
            char    ch  = '\0';
            uint8_t act = 0;
            if (_hitTest(x, y, &ch, &act)) {
                if (ch) {
                    appendChar(ch);
                } else {
                    _handleAction(act);
                }
            }
            return true;
        }

        // Move — consume but no action
        return true;
    }

    // ---- Host/serial injection (TASK-325 — VE-PRL-1 blocker) ---------------
    // Routes through the SAME internal paths touch input uses (appendChar(),
    // submit(), cancel()) — no duplicated commit/cleanup logic, per BP-047/
    // LL-110 (don't grow a second inline copy of a primitive that already
    // exists). Kept additive/minimal: no behaviour change for touch users.

    uint8_t len()    const { return _len; }
    uint8_t maxLen() const { return _maxLen; }
    Mode    mode()   const { return _mode; }

    // Append one character exactly as if the matching on-screen key were
    // tapped: mode-filtered first, then through appendChar() (which owns
    // maxLen truncation, page auto-revert and the input-bar repaint).
    // Returns false when the character has no on-screen key in this mode —
    // e.g. UpperAlpha has no digit/symbol keys (see kRow1..3 + _handleAction:
    // ACT_SYM only fires for Mode::Full) — mirroring a tap that lands on
    // nothing.
    bool injectChar(char c) {
        if (!_active) return false;
        if (_mode == Mode::UpperAlpha) {
            if (c == ' ') { appendChar(' '); return true; }
            if (isalpha((unsigned char)c)) {
                appendChar((char)toupper((unsigned char)c));
                return true;
            }
            return false;   // no digit/symbol keys exist in this mode on-screen
        }
        // Full mode: letters (either case, via shift), digits and the kSym
        // symbol pages together cover essentially all printable ASCII, so
        // accept any printable character rather than re-deriving the exact
        // key tables here.
        if (!isprint((unsigned char)c)) return false;
        appendChar(c);
        return true;
    }

    // Inject a run of characters (`set kbText`). Characters with no on-screen
    // equivalent in the current mode are silently dropped (same as a tap
    // landing off any key); appendChar() silently no-ops once _maxLen is hit
    // (same as fast-typing past the limit on-screen).
    void injectText(const char* text) {
        if (!_active || !text) return;
        for (const char* p = text; *p; p++) injectChar(*p);
    }

    // Fire the same commit path as tapping OK — same _onSubmit callback,
    // same hide()/cleanup via submit(). No-op when the buffer is empty,
    // matching the on-screen OK key which is disabled/greyed in that state.
    void commitFromHost() { if (_active) submit(); }

    // Fire the same cancel path as tapping the cancel zone — same _onCancel
    // callback, same hide()/cleanup via cancel().
    void cancelFromHost() { if (_active) cancel(); }

private:
    bool     _active         = false;
    Mode     _mode           = Mode::Full;
    uint8_t  _maxLen         = 64;
    char     _buf[65]        = {};      // maxLen <= 64 + NUL
    uint8_t  _len            = 0;
    uint8_t  _page           = 0;      // 0=lower alpha, 1=upper alpha, 2..3=symbol pages
    bool     _dirty          = false;
    bool     _oneShot        = false;  // auto-revert page 1->0 after one char
    bool     _blinkVisible   = false;
    uint32_t _blinkMs        = 0;
    bool     _pressHighlight = false;
    int      _pressRow       = -1;     // grid row of pressed key (-1 = none)
    int      _pressCol       = -1;     // virtual col ID of pressed key (-1 = none)
    void   (*_onSubmit)(const char*, void*) = nullptr;
    void   (*_onCancel)(void*)             = nullptr;
    void*    _ctx            = nullptr;
    char     _prompt[48]     = {};

    // ---- Drawing -----------------------------------------------------------

    // Draw a single key cell at pixel (px, py) with given w/h, bg, label colour.
    void _drawKey(int px, int py, int w, int h,
                  uint16_t bg, uint16_t fg, const char* label) const
    {
        tft.fillRect(px, py, w - 1, h - 1, bg);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(fg);
        tft.drawString(label, px + w / 2, py + h / 2, 2);
    }

    // Full repaint of keyboard canvas
    void repaint() {
        tft.fillRect(0, 0, KB_CANVAS_W, 240, S_BG);
        repaintInputBar();
        repaintKeys();
    }

    // Partial repaint — input bar only (y: 0..KB_INPUT_H-1)
    void repaintInputBar() {
        tft.fillRect(0, 0, KB_CANVAS_W, KB_INPUT_H, S_BG);
        int cy = KB_INPUT_H / 2;

        // Prompt (left, greyed)
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(S_VALUE_OFF);
        tft.drawString(_prompt, 8, cy, 2);

        // Input text (right-aligned to x=238)
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(S_HDR_TXT);
        tft.drawString(_buf, 238, cy, 2);

        // Cursor blink
        if (_blinkVisible) {
            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(S_HDR_TXT);
            tft.drawString("|", 240, cy, 2);
        }

        // Cancel zone (x=0..39, left) — escape the keyboard
        tft.setTextDatum(MC_DATUM);
        bool cancelPressed = (_pressHighlight && _pressRow < 0 && _pressCol == -20);
        tft.setTextColor(cancelPressed ? S_HDR_TXT : S_VALUE_OFF);
        tft.drawString("<", 20, cy, 2);

        // Backspace shortcut zone (x=248..274) — draw "<x" as backspace indicator
        tft.setTextColor(S_SEP);
        tft.drawString("<x", 261, cy, 2);

        tft.setTextDatum(TL_DATUM);
        tft.drawFastHLine(0, KB_INPUT_H - 1, KB_CANVAS_W, S_SEP);
    }

    // Partial repaint — key rows only (y: KB_INPUT_H..239)
    void repaintKeys() {
        if (_page <= 1) {
            _repaintAlphaKeys();
        } else {
            _repaintSymbolKeys();
        }
        _dirty = false;
    }

    void _repaintAlphaKeys() {
        int rowW = KB_CANVAS_W / 10;   // 27px per key (integer division)

        // ---- Row 1 (y=40..79): Q W E R T Y U I O P ----
        {
            int y = KB_INPUT_H;
            tft.fillRect(0, y, KB_CANVAS_W, KB_ROW_H, S_BG);
            for (int i = 0; i < 10; i++) {
                int px = i * rowW;
                int w  = (i == 9) ? (KB_CANVAS_W - px) : rowW;
                char label[2] = { (_page == 0) ? (char)tolower(kRow1[i]) : kRow1[i], '\0' };
                bool pressed  = (_pressHighlight && _pressRow == 0 && _pressCol == i);
                uint16_t bg   = pressed ? S_HDR_TXT : S_BG;
                uint16_t fg   = pressed ? (uint16_t)0x0000 : S_HDR_TXT;
                _drawKey(px, y, w, KB_ROW_H, bg, fg, label);
            }
        }

        // ---- Row 2 (y=80..119): A S D F G H J K L (centred) ----
        {
            int y  = KB_INPUT_H + KB_ROW_H;
            int x0 = (KB_CANVAS_W - 9 * KB_KEY_W) / 2;   // = 16
            tft.fillRect(0, y, KB_CANVAS_W, KB_ROW_H, S_BG);
            for (int i = 0; i < 9; i++) {
                int px = x0 + i * KB_KEY_W;
                char label[2] = { (_page == 0) ? (char)tolower(kRow2[i]) : kRow2[i], '\0' };
                bool pressed  = (_pressHighlight && _pressRow == 1 && _pressCol == i);
                uint16_t bg   = pressed ? S_HDR_TXT : S_BG;
                uint16_t fg   = pressed ? (uint16_t)0x0000 : S_HDR_TXT;
                _drawKey(px, y, KB_KEY_W, KB_ROW_H, bg, fg, label);
            }
        }

        // ---- Row 3 (y=120..159): [Shift 40] Z X C V B N M [Bksp 39] ----
        {
            int y = KB_INPUT_H + 2 * KB_ROW_H;
            tft.fillRect(0, y, KB_CANVAS_W, KB_ROW_H, S_BG);

            // Shift — only in Full mode
            if (_mode == Mode::Full) {
                bool shiftActive = (_page == 1);
                bool pressed     = (_pressHighlight && _pressRow == 2 && _pressCol == -2);
                uint16_t bg = pressed     ? S_HDR_TXT :
                              shiftActive ? S_VALUE_ON : S_SEP;
                uint16_t fg = (pressed || shiftActive) ? (uint16_t)0x0000 : S_HDR_TXT;
                _drawKey(0, y, 40, KB_ROW_H, bg, fg, "^");
            }

            // 7 letter keys (each 28px wide, starting at x=40)
            for (int i = 0; i < 7; i++) {
                int px = 40 + i * 28;
                char label[2] = { (_page == 0) ? (char)tolower(kRow3[i]) : kRow3[i], '\0' };
                bool pressed  = (_pressHighlight && _pressRow == 2 && _pressCol == i);
                uint16_t bg   = pressed ? S_HDR_TXT : S_BG;
                uint16_t fg   = pressed ? (uint16_t)0x0000 : S_HDR_TXT;
                _drawKey(px, y, 28, KB_ROW_H, bg, fg, label);
            }

            // Backspace — remaining width to right edge
            int bsX = 40 + 7 * 28;   // = 236
            bool bsPressed = (_pressHighlight && _pressRow == 2 && _pressCol == -3);
            uint16_t bsBg  = bsPressed ? S_HDR_TXT : S_SEP;
            uint16_t bsFg  = bsPressed ? (uint16_t)0x0000 : S_HDR_TXT;
            _drawKey(bsX, y, KB_CANVAS_W - bsX, KB_ROW_H, bsBg, bsFg, "<x");
        }

        // ---- Action row (y=160..199) ----
        {
            int y = KB_INPUT_H + 3 * KB_ROW_H;
            tft.fillRect(0, y, KB_CANVAS_W, KB_ROW_H, S_BG);

            if (_mode == Mode::UpperAlpha) {
                // [SPACE 202px][OK 73px]
                bool spPressed = (_pressHighlight && _pressRow == 3 && _pressCol == 0);
                _drawKey(0, y, 202, KB_ROW_H,
                         spPressed ? S_HDR_TXT : S_SEP,
                         spPressed ? (uint16_t)0x0000 : S_HDR_TXT, "SPACE");

                bool okEmpty   = (_len == 0);
                bool okPressed = (_pressHighlight && _pressRow == 3 && _pressCol == 1);
                uint16_t okBg  = okPressed ? S_HDR_TXT : (okEmpty ? S_SEP : S_VALUE_ON);
                uint16_t okFg  = (okPressed || okEmpty) ? S_HDR_TXT : (uint16_t)0x0000;
                _drawKey(202, y, KB_CANVAS_W - 202, KB_ROW_H, okBg, okFg, "OK");
            } else {
                // Full mode: [SYM 46px][SPACE 156px][OK 73px]
                bool symPressed = (_pressHighlight && _pressRow == 3 && _pressCol == 0);
                _drawKey(0, y, 46, KB_ROW_H,
                         symPressed ? S_HDR_TXT : S_SEP,
                         symPressed ? (uint16_t)0x0000 : S_HDR_TXT, "123");

                bool spPressed = (_pressHighlight && _pressRow == 3 && _pressCol == 1);
                _drawKey(46, y, 156, KB_ROW_H,
                         spPressed ? S_HDR_TXT : S_SEP,
                         spPressed ? (uint16_t)0x0000 : S_HDR_TXT, "SPACE");

                bool okEmpty   = (_len == 0);
                bool okPressed = (_pressHighlight && _pressRow == 3 && _pressCol == 2);
                uint16_t okBg  = okPressed ? S_HDR_TXT : (okEmpty ? S_SEP : S_VALUE_ON);
                uint16_t okFg  = (okPressed || okEmpty) ? S_HDR_TXT : (uint16_t)0x0000;
                _drawKey(202, y, KB_CANVAS_W - 202, KB_ROW_H, okBg, okFg, "OK");
            }
        }

        // ---- Row 4 (y=200..239): dark fill — no keys in alpha mode ----
        tft.fillRect(0, KB_INPUT_H + 4 * KB_ROW_H, KB_CANVAS_W, KB_ROW_H, S_BG);
    }

    void _repaintSymbolKeys() {
        int rowW     = KB_CANVAS_W / 10;   // 27px per key (integer division)
        int pageIdx  = _page - 2;          // 0 or 1

        // ---- Rows 0-3 (y=40..199): uniform 10-key grid ----
        for (int row = 0; row < 4; row++) {
            int y = KB_INPUT_H + row * KB_ROW_H;
            tft.fillRect(0, y, KB_CANVAS_W, KB_ROW_H, S_BG);
            for (int col = 0; col < 10; col++) {
                char c = kSym[pageIdx][row][col];
                if (c == '\0') continue;    // empty cell — already filled
                int px = col * rowW;
                int w  = (col == 9) ? (KB_CANVAS_W - px) : rowW;
                char label[2] = { c, '\0' };
                bool pressed  = (_pressHighlight && _pressRow == row && _pressCol == col);
                uint16_t bg   = pressed ? S_HDR_TXT : S_BG;
                uint16_t fg   = pressed ? (uint16_t)0x0000 : S_HDR_TXT;
                _drawKey(px, y, w, KB_ROW_H, bg, fg, label);
            }
        }

        // ---- Action row (y=160..199): [ABC 40][NEXT 40][SPACE 100][Bksp 35][OK 60] ----
        // Overwrite row 3 (already filled above) with action buttons
        {
            int y = KB_INPUT_H + 3 * KB_ROW_H;
            tft.fillRect(0, y, KB_CANVAS_W, KB_ROW_H, S_BG);

            bool abcPressed = (_pressHighlight && _pressRow == 3 && _pressCol == -10);
            _drawKey(0, y, 40, KB_ROW_H,
                     abcPressed ? S_HDR_TXT : S_SEP,
                     abcPressed ? (uint16_t)0x0000 : S_HDR_TXT, "ABC");

            const char* nextLabel = (_page == 2) ? "#+=" : "123";
            bool nextPressed = (_pressHighlight && _pressRow == 3 && _pressCol == -11);
            _drawKey(40, y, 40, KB_ROW_H,
                     nextPressed ? S_HDR_TXT : S_SEP,
                     nextPressed ? (uint16_t)0x0000 : S_HDR_TXT, nextLabel);

            bool spPressed = (_pressHighlight && _pressRow == 3 && _pressCol == -12);
            _drawKey(80, y, 100, KB_ROW_H,
                     spPressed ? S_HDR_TXT : S_SEP,
                     spPressed ? (uint16_t)0x0000 : S_HDR_TXT, "SPACE");

            bool bsPressed = (_pressHighlight && _pressRow == 3 && _pressCol == -13);
            _drawKey(180, y, 35, KB_ROW_H,
                     bsPressed ? S_HDR_TXT : S_SEP,
                     bsPressed ? (uint16_t)0x0000 : S_HDR_TXT, "<x");

            bool okEmpty   = (_len == 0);
            bool okPressed = (_pressHighlight && _pressRow == 3 && _pressCol == -14);
            uint16_t okBg  = okPressed ? S_HDR_TXT : (okEmpty ? S_SEP : S_VALUE_ON);
            uint16_t okFg  = (okPressed || okEmpty) ? S_HDR_TXT : (uint16_t)0x0000;
            _drawKey(215, y, KB_CANVAS_W - 215, KB_ROW_H, okBg, okFg, "OK");
        }
    }

    // ---- Hit-testing -------------------------------------------------------

    // Returns a virtual column ID for press-highlight tracking.
    // Non-negative = letter grid column; negative = action key sentinel.
    int _pressColForXY(int x, int y) const {
        if (y < KB_INPUT_H) return (x < 40) ? -20 : -1;   // -20 = cancel sentinel
        int row = (y - KB_INPUT_H) / KB_ROW_H;
        if (_page <= 1) {
            switch (row) {
                case 0: return x / (KB_CANVAS_W / 10);
                case 1: {
                    int x0 = (KB_CANVAS_W - 9 * KB_KEY_W) / 2;
                    if (x < x0 || x >= x0 + 9 * KB_KEY_W) return -1;
                    return (x - x0) / KB_KEY_W;
                }
                case 2:
                    if (x < 40)             return -2;   // shift
                    if (x >= 40 + 7 * 28)   return -3;   // backspace
                    return (x - 40) / 28;
                case 3:
                    if (_mode == Mode::UpperAlpha) {
                        return (x < 202) ? 0 : 1;
                    }
                    if (x < 46)  return 0;   // SYM
                    if (x < 202) return 1;   // SPACE
                    return 2;                // OK
                default: return -1;
            }
        } else {
            if (row <= 2) return x / (KB_CANVAS_W / 10);
            if (row == 3) {
                // Symbol action row — sentinels match _repaintSymbolKeys
                if (x < 40)  return -10;   // ABC
                if (x < 80)  return -11;   // NEXT
                if (x < 180) return -12;   // SPACE
                if (x < 215) return -13;   // Backspace
                return -14;                // OK
            }
            // row 4 — symbol grid row 3 (kSym rows 0..3; action overwrites row index 3)
            return x / (KB_CANVAS_W / 10);
        }
    }

    // Returns true if (x,y) hits a key. Sets *outChar (printable) or *outAction.
    bool _hitTest(int x, int y, char* outChar, uint8_t* outAction) const {
        *outChar   = '\0';
        *outAction = 0;

        // Input bar zones
        if (y < KB_INPUT_H) {
            if (x < 40)    { *outAction = ACT_CANCEL;    return true; }
            if (x >= 248)  { *outAction = ACT_BACKSPACE;  return true; }
            return false;
        }

        int row = (y - KB_INPUT_H) / KB_ROW_H;   // 0..4
        if (row < 0 || row > 4) return false;

        if (_page <= 1) {
            // ---- Alpha pages ----
            if (row == 0) {
                Rect g = { 0, (int16_t)KB_INPUT_H, (int16_t)KB_CANVAS_W, (int16_t)KB_ROW_H };
                int col = hitTestCol(g, KB_CANVAS_W / 10, x);
                if (col < 0 || col > 9) return false;
                char c = kRow1[col];
                *outChar = (_page == 0) ? (char)tolower(c) : c;
                return true;
            }
            if (row == 1) {
                int x0 = (KB_CANVAS_W - 9 * KB_KEY_W) / 2;
                if (x < x0 || x >= x0 + 9 * KB_KEY_W) return false;
                char c = kRow2[(x - x0) / KB_KEY_W];
                *outChar = (_page == 0) ? (char)tolower(c) : c;
                return true;
            }
            if (row == 2) {
                if (_mode == Mode::Full) {
                    if (x < 40)            { *outAction = ACT_SHIFT;     return true; }
                    if (x >= 40 + 7 * 28)  { *outAction = ACT_BACKSPACE; return true; }
                } else {
                    // UpperAlpha: no shift key
                    if (x < 40)            return false;
                    if (x >= 40 + 7 * 28)  { *outAction = ACT_BACKSPACE; return true; }
                }
                int idx = (x - 40) / 28;
                if (idx < 0 || idx > 6) return false;
                char c = kRow3[idx];
                *outChar = (_page == 0) ? (char)tolower(c) : c;
                return true;
            }
            if (row == 3) {
                if (_mode == Mode::UpperAlpha) {
                    if (x < 202) { *outAction = ACT_SPACE; return true; }
                    *outAction = ACT_OK; return true;
                }
                if (x < 46)  { *outAction = ACT_SYM;   return true; }
                if (x < 202) { *outAction = ACT_SPACE;  return true; }
                *outAction = ACT_OK; return true;
            }
            // row == 4 — dark fill, no keys
            return false;

        } else {
            // ---- Symbol pages ----
            if (row <= 2) {
                Rect g = { 0, (int16_t)(KB_INPUT_H + row * KB_ROW_H),
                           (int16_t)KB_CANVAS_W, (int16_t)KB_ROW_H };
                int col = hitTestCol(g, KB_CANVAS_W / 10, x);
                if (col < 0) return false;
                char c = kSym[_page - 2][row][col];
                if (c == '\0') return false;
                *outChar = c;
                return true;
            }
            if (row == 3) {
                // Action row: [ABC 40][NEXT 40][SPACE 100][Bksp 35][OK 60]
                if (x < 40)  { *outAction = ACT_ABC;       return true; }
                if (x < 80)  { *outAction = ACT_NEXT;      return true; }
                if (x < 180) { *outAction = ACT_SPACE;     return true; }
                if (x < 215) { *outAction = ACT_BACKSPACE; return true; }
                *outAction = ACT_OK; return true;
            }
            // row == 4 — kSym row 3
            {
                Rect g = { 0, (int16_t)(KB_INPUT_H + 4 * KB_ROW_H),
                           (int16_t)KB_CANVAS_W, (int16_t)KB_ROW_H };
                int col = hitTestCol(g, KB_CANVAS_W / 10, x);
                if (col < 0) return false;
                char c = kSym[_page - 2][3][col];
                if (c == '\0') return false;
                *outChar = c;
                return true;
            }
        }
        return false;
    }

    // ---- Input helpers -----------------------------------------------------

    void appendChar(char c) {
        if (_len >= _maxLen) return;    // silently ignore when full
        _buf[_len++] = c;
        _buf[_len]   = '\0';
        if (_oneShot && _page == 1) {
            _page  = 0;
            _dirty = true;
        }
        _oneShot = false;
        repaintInputBar();
        if (_dirty) repaintKeys();
    }

    void backspace() {
        if (_len > 0) _buf[--_len] = '\0';
        repaintInputBar();
    }

    void submit() {
        if (_len == 0) return;      // OK disabled when empty
        char    tmp[65];
        memcpy(tmp, _buf, _len + 1);
        auto cb  = _onSubmit;
        auto ctx = _ctx;
        hide();
        if (cb) cb(tmp, ctx);
    }

    void cancel() {
        auto cb  = _onCancel;
        auto ctx = _ctx;
        hide();
        if (cb) cb(ctx);
    }

    void _handleAction(uint8_t act) {
        switch (act) {
            case ACT_SHIFT:
                if (_mode == Mode::Full) {
                    if (_page == 0) { _page = 1; _oneShot = true; }
                    else            { _page = 0; _oneShot = false; }
                    _dirty = true;
                    repaintKeys();
                }
                break;
            case ACT_BACKSPACE:
                backspace();
                break;
            case ACT_SYM:
                if (_mode == Mode::Full) {
                    _page  = 2;
                    _dirty = true;
                    repaintKeys();
                }
                break;
            case ACT_SPACE:
                appendChar(' ');
                break;
            case ACT_OK:
                submit();
                break;
            case ACT_ABC:
                _page  = 0;
                _dirty = true;
                repaintKeys();
                break;
            case ACT_NEXT:
                _page  = (_page == 2) ? 3 : 2;
                _dirty = true;
                repaintKeys();
                break;
            case ACT_CANCEL:
                cancel();
                break;
            default:
                break;
        }
    }
};

extern KeyboardWidget g_keyboard;
