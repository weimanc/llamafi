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
