#pragma once
// settingsWidgets.h — shared Settings UI widget kit (TASK-328, M-SETTINGS-STYLE).
//
// Why this exists: settingsSection.h enforces the ROW style by construction,
// but buttons were hand-rolled 4x over (wifiSection Retry/Cancel @30px,
// ledSection OFF/ON/SAVE @20px with a private invert flash, timeSection
// arrows, calibrationFlow) — each with its own layout constants, hit-test and
// press feedback. The TASK-317 editor frames' 40-vs-30px divergence was the
// symptom: there was no constant to obey. This header is now THE Settings
// button/spinner idiom: new Settings UI uses these widgets only; a
// hand-rolled button is a review flag (BP candidate; TASK-327 migrated the
// four legacy sites onto this kit 2026-07-16).
//
// Visual contract is FROZEN by the TASK-317 eyeball gate (2026-07-14,
// docs/architecture/designs/M-PR-LOCATIONS/img/editor_*.png) — check changes
// against those PNGs, not against prose:
//   - buttons are 40 px tall (finger targets; supersedes wifiSection's 30),
//   - bar buttons sit 1–3 across on a standard bottom bar,
//   - stacked buttons are full-width rows (the source-fork screen),
//   - Primary = green fill/black text, Neutral = S_SEP fill/white text,
//     Danger = red fill/white text, Disabled = outline only/grey text
//     (disabled renders but never hits — "disabled, not absent", slot-0
//     Delete decision).
//
// First consumer: the TASK-321 location editor. Reuse note: Rect/hitTest come
// from touch/hitbox.h via settingsSection.h — no duplication here.

#include "settingsSection.h"
#include "gen/countries.h"   // CountryEntry — SPickerList row shape (M-COUNTRY-PICKER)

// ---- Geometry ---------------------------------------------------------------

static constexpr int16_t S_BTN_H       = 40;  // TASK-317 gate: finger-sized, not 30
static constexpr int16_t S_BTN_GAP     = 12;  // horizontal gap between bar buttons
static constexpr int16_t S_BTN_MARGIN  = 8;   // bar/stack side margin (matches S_COL_LABEL)
// Standard bottom bar: baseline for Save/Retry/Cancel rows (TASK-317 frames).
static constexpr int16_t S_BTN_BAR_Y   = S_CANVAS_H - S_BTN_H - 10;   // 190
static constexpr int16_t S_STACK_PITCH = S_BTN_H + 12;                // stacked-row pitch

// ---- Colours ----------------------------------------------------------------

static constexpr uint16_t S_BTN_PRIMARY_BG  = S_VALUE_ON;  // green (ledSection active idiom)
static constexpr uint16_t S_BTN_PRIMARY_FG  = 0x0000;      // black on green
static constexpr uint16_t S_BTN_NEUTRAL_BG  = S_SEP;       // grey fill
static constexpr uint16_t S_BTN_NEUTRAL_FG  = S_HDR_TXT;   // white
static constexpr uint16_t S_BTN_DANGER_BG   = 0xB0E3;      // muted red (TASK-317 Delete)
static constexpr uint16_t S_BTN_DANGER_FG   = S_HDR_TXT;
static constexpr uint16_t S_BTN_DISABLED_FG = S_VALUE_OFF; // grey text, outline only

enum class SBtnStyle : uint8_t { Primary, Neutral, Danger, Disabled };

// ---- SButton ----------------------------------------------------------------
// Plain value type — sections keep an array/members of these, draw() them in
// their repaint, and hit() them in handleTap. No global state, no callbacks:
// the section's tap handler owns what a hit means (matches the section
// model — SettingsApp routes Release events to the section, not to widgets).
//
// gnu++11 note (LL-112): this firmware compiles -std=gnu++11, under which a
// type with default member initializers (the fields below all have one) is
// NOT an aggregate — `SButton{ rect, "label", SBtnStyle::Primary }` will not
// compile here even though it looks like ordinary aggregate init and works
// on newer standards. Construct via field assignment instead:
//   btn.r = rect; btn.label = "label"; btn.style = SBtnStyle::Primary;
// Same applies to SSpinner below.

struct SButton {
    Rect        r     = {0, 0, 0, 0};
    const char* label = "";
    SBtnStyle   style = SBtnStyle::Neutral;

    void draw() const {
        uint16_t bg, fg;
        switch (style) {
            case SBtnStyle::Primary:  bg = S_BTN_PRIMARY_BG; fg = S_BTN_PRIMARY_FG; break;
            case SBtnStyle::Danger:   bg = S_BTN_DANGER_BG;  fg = S_BTN_DANGER_FG;  break;
            case SBtnStyle::Disabled:
                tft.fillRect(r.x, r.y, r.w, r.h, S_BG);
                tft.drawRect(r.x, r.y, r.w, r.h, S_SEP);
                tft.setTextDatum(MC_DATUM);
                tft.setTextColor(S_BTN_DISABLED_FG, S_BG);
                tft.drawString(label, r.x + r.w / 2, r.y + r.h / 2, 2);
                tft.setTextDatum(TL_DATUM);
                return;
            case SBtnStyle::Neutral:
            default:                  bg = S_BTN_NEUTRAL_BG;  fg = S_BTN_NEUTRAL_FG; break;
        }
        tft.fillRect(r.x, r.y, r.w, r.h, bg);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(fg, bg);
        tft.drawString(label, r.x + r.w / 2, r.y + r.h / 2, 2);
        tft.setTextDatum(TL_DATUM);
    }

    // Disabled buttons render but never hit ("disabled, not absent").
    bool hit(int16_t px, int16_t py) const {
        return style != SBtnStyle::Disabled && hitTest(r, px, py);
    }

    // Shared press feedback — the ledSection ~100 ms invert, now in ONE place
    // (BP-047: this was previously a private per-section flourish). Draws the
    // button inverted, blocks briefly (loopTask idiom, matches ledSection),
    // redraws normal. Call from the tap handler on a confirmed hit, BEFORE
    // acting, so slow follow-up work (saveSettings etc.) doesn't eat the
    // visual acknowledgement.
    void flash() const {
        SButton inv = *this;
        // Invert by style swap: Primary<->Neutral reads as a clear blink for
        // all three enabled styles; Danger blinks to Neutral.
        inv.style = (style == SBtnStyle::Neutral) ? SBtnStyle::Primary
                                                  : SBtnStyle::Neutral;
        inv.draw();
        delay(100);
        draw();
    }
};

// ---- Layout helpers ----------------------------------------------------------

// Lay out n (1..3) buttons evenly across the standard bottom bar (or a custom
// y): equal widths, S_BTN_GAP between, S_BTN_MARGIN sides. Sets ONLY r —
// label/style are the caller's. 3-across at 275 px canvas ≈ 81 px each,
// matching the TASK-317 confirm frame.
inline void sButtonBar(SButton* btns, uint8_t n, int16_t y = S_BTN_BAR_Y) {
    if (n == 0) return;
    if (n > 3) n = 3;
    int16_t w = (S_CANVAS_W - 2 * S_BTN_MARGIN - (n - 1) * S_BTN_GAP) / n;
    for (uint8_t i = 0; i < n; i++)
        btns[i].r = { (int16_t)(S_BTN_MARGIN + i * (w + S_BTN_GAP)), y, w, S_BTN_H };
}

// Full-width stacked button rect for row k below y0 (the source-fork screen
// idiom: [Lookup] / [Manual] / [Delete] as full-width rows).
inline Rect sStackedBtnRect(uint8_t k, int16_t y0) {
    return { S_BTN_MARGIN, (int16_t)(y0 + k * S_STACK_PITCH),
             (int16_t)(S_CANVAS_W - 2 * S_BTN_MARGIN), S_BTN_H };
}

// ---- SSpinner ----------------------------------------------------------------
// Pending-fetch row (TASK-317 editor_lookup_pending frame; M-DATATASK-PROGRESS
// idiom): a centred label plus a rotating glyph the section advances from its
// tick(). Caller decides cadence (every ~250 ms reads well at font 2).

struct SSpinner {
    int16_t     y      = 0;      // row top (centred text at y + 12)
    const char* label  = "";     // e.g. "Looking up..."
    uint8_t     _phase = 0;

    void draw() {
        static const char glyphs[4] = {'|', '/', '-', '\\'};
        tft.fillRect(0, y, S_CANVAS_W, 28, S_BG);
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_HDR_TXT, S_BG);
        tft.drawString(label, S_CANVAS_W / 2, y + 8, 2);
        char g[2] = { glyphs[_phase & 3], '\0' };
        tft.setTextColor(S_VALUE, S_BG);
        tft.drawString(g, S_CANVAS_W / 2, y + 24, 2);
        tft.setTextDatum(TL_DATUM);
    }
    void tick() { _phase++; draw(); }
    void clear() const { tft.fillRect(0, y, S_CANVAS_W, 34, S_BG); }
};

// ---- SPickerList --------------------------------------------------------------
// Modal full-canvas scroll picker (M-COUNTRY-PICKER D1) over CountryEntry-shaped
// (name, code) rows. Deliberate EXCEPTION to the "no global state, no callbacks"
// kit contract above (CP-11): like KeyboardWidget, an active picker owns the
// whole canvas and ALL touch phases — host sections integrate via the
// g_keyboard capture precedent (forward every phase while active(); early-
// return their repaint()). Cancel is the picker's own "< back" header zone,
// checked here — the host's back-tap code is unreachable while it captures.
//
// Mechanics transcribed from timeSection's city picker (paged rows, right-edge
// scrollbar with thumb drag + arrow taps, tap-to-select), with two deliberate
// changes: int16_t offsets/count (CP-7 — the donor's uint8_t clears 249 rows
// with only 6 to spare; a kit widget doesn't inherit that cliff) and opens
// scrolled to the current selection, highlighted (CP-6 — NEW code, the donor
// always opens at offset 0; unset/unknown selection opens at the top).
// The donor (TimeSection) is intentionally untouched in v1.

class SPickerList {
public:
    void show(const CountryEntry* items, int16_t count, const char* currentCode,
              void (*onSelect)(int16_t idx, void* ctx),
              void (*onCancel)(void* ctx),
              void* ctx)
    {
        _items      = items;
        _count      = count;
        _onSelect   = onSelect;
        _onCancel   = onCancel;
        _ctx        = ctx;
        _sbDragging = false;
        _highlight  = -1;
        _offset     = 0;
        if (items && currentCode && currentCode[0]) {
            for (int16_t i = 0; i < count; i++) {
                if (strcasecmp(items[i].code, currentCode) == 0) { _highlight = i; break; }
            }
        }
        // CP-6: open scrolled to the current selection (clamped so the last
        // page stays full); no/unknown selection opens at the top.
        if (_highlight >= 0) {
            int16_t maxOff = _maxOffset();
            _offset = (_highlight < maxOff) ? _highlight : maxOff;
        }
        _active = true;
        repaint();
    }

    void hide() { _active = false; _sbDragging = false; }
    bool active() const { return _active; }

    void repaint() {
        if (!_active) return;
        // Own header — "< back" is the cancel zone (the host never paints
        // under an active picker, CP-1 takeover contract).
        tft.fillRect(0, 0, S_CANVAS_W, S_HEADER_H, S_BG);
        tft.setTextColor(S_HDR_TXT);
        tft.setTextDatum(ML_DATUM);
        tft.drawString("< back", 4, 14, 2);
        tft.setTextDatum(MR_DATUM);
        tft.drawString("Select country", S_CANVAS_W - 4, 14, 2);
        tft.drawFastHLine(0, S_HEADER_H - 1, S_CANVAS_W, S_SEP);
        tft.setTextDatum(TL_DATUM);
        tft.fillRect(0, S_CONTENT_Y, S_CANVAS_W, S_CONTENT_H, S_BG);
        _drawScrollbar();
        _drawRows();
    }

    // Owns ALL phases while active (CP-1) — the host forwards unconditionally.
    void handleInput(TouchPhase phase, int x, int y) {
        if (!_active) return;

        // Cancel via the picker's own back zone (Release only, never mid-drag).
        if (phase == TouchPhase::Release && !_sbDragging
                && x < S_BACK_ZONE_W && y < S_HEADER_H) {
            _cancel();
            return;
        }

        // Scrollbar zone (x >= kSbX) — donor logic, int16_t offsets.
        if (x >= kSbX || _sbDragging) {
            if (phase == TouchPhase::Press && x >= kSbX
                    && y > kSbUpY1 && y < kSbDnY0) {
                _sbDragging         = true;
                _sbDragAnchorY      = (int16_t)y;
                _sbDragAnchorOffset = _offset;
            } else if (phase == TouchPhase::Move && _sbDragging) {
                int trackH = kSbDnY0 - kSbUpY1 - 4;
                int maxOff = _maxOffset();
                if (maxOff > 0 && trackH > 0) {
                    int delta  = ((y - _sbDragAnchorY) * maxOff + trackH / 2) / trackH;
                    int newOff = constrain((int)_sbDragAnchorOffset + delta, 0, maxOff);
                    if (newOff != (int)_offset) {
                        _offset = (int16_t)newOff;
                        repaint();
                    }
                }
            } else if (phase == TouchPhase::Release) {
                _sbDragging = false;
                // Arrow taps (only on Release, not after a drag)
                if (_sbUp.hit(x, y) && _offset > 0) {
                    _offset--;
                    repaint();
                } else if (_sbDn.hit(x, y) && _offset + kRows < _count) {
                    _offset++;
                    repaint();
                }
            }
            return;
        }

        // Row tap — Release only
        if (phase != TouchPhase::Release) return;
        if (y < S_CONTENT_Y) return;   // header outside the back zone — inert
        int16_t row = (int16_t)((y - S_CONTENT_Y) / S_ROW_H);
        if (row < 0 || row >= kRows) return;
        int16_t idx = (int16_t)(_offset + row);
        if (idx >= _count) return;
        _select(idx);
    }

#ifdef SERIAL_DEBUG
    // CP-8 observables (`get pick`) + CP-4 injection (`set pick <CC>`).
    int16_t dbgOffset()    const { return _offset; }
    int16_t dbgHighlight() const { return _highlight; }
    // Selects by code exactly as if the row were tapped — same onSelect
    // callback, same hide()/cleanup (the kbText/kbOk submit-equivalent idiom,
    // BP-047/LL-110: no duplicated commit logic).
    bool pickByCode(const char* code) {
        if (!_active || !_items || !code || !code[0]) return false;
        for (int16_t i = 0; i < _count; i++) {
            if (strcasecmp(_items[i].code, code) == 0) { _select(i); return true; }
        }
        return false;
    }
#endif

private:
    // Donor geometry (timeSection city picker) — 6 paged rows, 18px scrollbar
    // column at x=257 with 20px arrow zones top/bottom.
    static constexpr int16_t kRows   = 6;
    static constexpr int16_t kSbX    = 257;
    static constexpr int16_t kSbW    = 18;
    static constexpr int16_t kSbUpY0 = S_CONTENT_Y;
    static constexpr int16_t kSbUpY1 = S_CONTENT_Y + 20;
    static constexpr int16_t kSbDnY0 = 220;
    static constexpr int16_t kSbDnY1 = 240;

    const CountryEntry* _items = nullptr;
    int16_t _count      = 0;
    int16_t _offset     = 0;      // first visible row index
    int16_t _highlight  = -1;     // index of the current selection, -1 = none
    bool    _active     = false;
    bool    _sbDragging = false;
    int16_t _sbDragAnchorY      = 0;
    int16_t _sbDragAnchorOffset = 0;
    // Scrollbar step arrows as kit buttons at the scrollbar's own 18x20
    // geometry (timeSection precedent — S_BTN_H is a bar-button contract).
    SButton _sbUp, _sbDn;
    void  (*_onSelect)(int16_t idx, void* ctx) = nullptr;
    void  (*_onCancel)(void* ctx)              = nullptr;
    void*   _ctx = nullptr;

    int16_t _maxOffset() const {
        return (_count > kRows) ? (int16_t)(_count - kRows) : (int16_t)0;
    }

    // KeyboardWidget submit()/cancel() idiom: copy the callback, hide FIRST,
    // then fire — the callback may immediately show() another modal (the
    // prloc country -> postcode keyboard hand-off).
    void _select(int16_t idx) {
        auto  cb  = _onSelect;
        void* ctx = _ctx;
        hide();
        if (cb) cb(idx, ctx);
    }
    void _cancel() {
        auto  cb  = _onCancel;
        void* ctx = _ctx;
        hide();
        if (cb) cb(ctx);
    }

    void _drawRows() {
        int y = S_CONTENT_Y;
        int16_t end = (int16_t)(_offset + kRows);
        if (end > _count) end = _count;
        for (int16_t i = _offset; i < end; i++) {
            bool cur = (i == _highlight);
            int mid = y + S_ROW_H / 2;
            // Name (left) + code (right-aligned at x=246, before the
            // scrollbar) — the city picker's country-code column idiom.
            tft.setTextDatum(ML_DATUM);
            tft.setTextColor(cur ? S_VALUE_ON : S_LABEL);
            tft.drawString(_items[i].name, S_COL_LABEL, mid, 2);
            tft.setTextDatum(MR_DATUM);
            tft.setTextColor(cur ? S_VALUE_ON : S_VALUE_OFF);
            tft.drawString(_items[i].code, 246, mid, 2);
            tft.setTextDatum(TL_DATUM);
            y += S_ROW_H;
        }
    }

    void _drawScrollbar() {
        tft.fillRect(kSbX, S_CONTENT_Y, kSbW, S_CONTENT_H, S_SEP);

        _sbUp.r = { kSbX, kSbUpY0, kSbW, (int16_t)(kSbUpY1 - kSbUpY0) };
        _sbUp.label = "^";
        _sbDn.r = { kSbX, kSbDnY0, kSbW, (int16_t)(kSbDnY1 - kSbDnY0) };
        _sbDn.label = "v";
        _sbUp.draw();
        _sbDn.draw();

        // Thumb
        int trackY0 = kSbUpY1 + 2;
        int trackH  = kSbDnY0 - trackY0 - 2;
        if (_count > kRows && trackH > 0) {
            int thumbH = max(8, trackH * kRows / (int)_count);
            int thumbY = trackY0 + ((int)_offset * (trackH - thumbH))
                         / ((int)_count - kRows);
            tft.fillRect(kSbX + 3, thumbY, kSbW - 6, thumbH, S_VALUE);
        }
    }
};

extern SPickerList g_countryPicker;
