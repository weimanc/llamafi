#pragma once
// settingsSection.h — abstract base for all sections within SettingsApp.
//
// Sections are NOT App subclasses — they are internal views managed by SettingsApp.
// Each section owns its render / input / tick logic; the base provides shared chrome
// (header bar, row rendering, hit-testing) and a typed path to g_settings.
//
// Navigation contract:
//   SettingsApp calls enter() on push, leave() on pop, tick() each shell tick,
//   and routes Release events to handleTap(x, y). handleTap() returns GoBack
//   when the section wants to dismiss itself.
//
// Reuse note:
//   hitbox.h (Rect, hitTestRow, hitTest) is used directly — no duplication.
//   Winamp sliders are NOT reused — they are skin-image-specific.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "../touch/hitbox.h"
#include "../touchPhase.h"
#include "../settingsStorage.h"

extern TFT_eSPI tft;

// ============================================================================
// Geometry — all sections share these bounds
// ============================================================================

static constexpr int16_t S_CANVAS_W     = 275;   // left canvas width (x:0..274)
static constexpr int16_t S_CANVAS_H     = 240;

static constexpr int16_t S_HEADER_H     =  28;   // header bar height
static constexpr int16_t S_CONTENT_Y    =  28;   // content area top y
static constexpr int16_t S_CONTENT_H    = 212;   // 240 - S_HEADER_H

static constexpr int16_t S_ROW_H        =  26;   // row height (matches ST_LIST_ROW_H)
static constexpr int16_t S_ROW_HDR_H    =  22;   // sub-section label + rule height
static constexpr int16_t S_MAX_ROWS     =   8;   // 212 / 26 = 8 full rows

static constexpr int16_t S_COL_LABEL    =   8;   // label left edge x
static constexpr int16_t S_COL_VALUE    = 268;   // value right-aligned terminus x
static constexpr int16_t S_BACK_ZONE_W  =  60;   // < back tap zone width

// ============================================================================
// Colour palette
// ============================================================================

static constexpr uint16_t S_BG          = 0x2104;   // background
static constexpr uint16_t S_SEP         = 0x4208;   // separator / rule lines
static constexpr uint16_t S_HDR_TXT     = 0xFFFF;   // header bar text (white)
static constexpr uint16_t S_LABEL       = 0xFFFF;   // row label (white)
static constexpr uint16_t S_VALUE       = 0x07FF;   // neutral value (cyan)
static constexpr uint16_t S_VALUE_ON    = 0x07E0;   // enabled / active (green)
static constexpr uint16_t S_VALUE_OFF   = 0x7BEF;   // disabled / inactive (grey)
static constexpr uint16_t S_SUBHDR      = 0xFFE0;   // sub-section header text (yellow)
static constexpr uint16_t S_CHEVRON     = 0x4208;   // > chevron (grey)

// ============================================================================
// Row descriptor
// ============================================================================

struct SettingsRow {
    const char* label;
    const char* value;
    uint16_t    labelColor = S_LABEL;
    uint16_t    valueColor = S_VALUE;
};

// ============================================================================
// Navigation signal returned by handleTap()
// ============================================================================

enum class SectionResult : uint8_t {
    Continue,   // stay in this section
    GoBack,     // SettingsApp should pop this section
};

// ============================================================================
// SettingsSection — abstract base
// ============================================================================

class SettingsSection {
public:
    virtual ~SettingsSection() = default;

    // Lifecycle — called by SettingsApp on push / pop.
    virtual void enter()  {}
    virtual void leave()  {}

    // Called each shell tick (for spinner, live sensor readout, etc.).
    // Override only if the section needs periodic updates.
    virtual void tick()   {}

    // Called on every touch event (Press / Move / Release) inside the 275×240 canvas.
    // Must return GoBack if the section wants to dismiss itself (typically on back tap).
    // Sections that only care about taps just check (phase == TouchPhase::Release).
    virtual SectionResult handleInput(TouchPhase phase, int x, int y) = 0;

    // Full repaint — called by SettingsApp on entry and after any nav event.
    virtual void repaint() = 0;

    // Title shown in the header bar centre-right.
    virtual const char* title() const = 0;

protected:
    // ---- Header chrome -------------------------------------------------------

    // Draws the 28 px header bar: "< back" on the left, title() on the right.
    void drawHeader() const {
        tft.fillRect(0, 0, S_CANVAS_W, S_HEADER_H, S_BG);
        tft.setTextColor(S_HDR_TXT);
        tft.setTextDatum(ML_DATUM);
        tft.drawString("< back", 4, 14, 2);
        tft.setTextDatum(MR_DATUM);
        tft.drawString(title(), S_CANVAS_W - 4, 14, 2);
        tft.drawFastHLine(0, S_HEADER_H - 1, S_CANVAS_W, S_SEP);
        tft.setTextDatum(TL_DATUM);
    }

    // Blank-fills the content area (y:28..239).
    void clearContent() const {
        tft.fillRect(0, S_CONTENT_Y, S_CANVAS_W, S_CONTENT_H, S_BG);
    }

    // ---- Row rendering -------------------------------------------------------

    // Single label/value row at a given screen y.
    void drawRow(int screenY, const SettingsRow& r) const {
        int mid = screenY + S_ROW_H / 2;
        tft.setTextDatum(ML_DATUM);
        tft.setTextColor(r.labelColor);
        tft.drawString(r.label, S_COL_LABEL, mid, 2);
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(r.valueColor);
        tft.drawString(r.value, S_COL_VALUE, mid, 2);
        tft.setTextDatum(TL_DATUM);
    }

    // Render an array of rows, optionally preceded by a sub-section header.
    // Returns the next available y below the last drawn row.
    int drawRows(const SettingsRow* rows, int count,
                 const char* subHeader = nullptr) const {
        int y = S_CONTENT_Y;
        if (subHeader) {
            tft.setTextDatum(TL_DATUM);
            tft.setTextColor(S_SUBHDR);
            tft.drawString(subHeader, S_COL_LABEL, y + 4, 2);
            tft.drawFastHLine(S_COL_LABEL, y + S_ROW_HDR_H - 1,
                              S_CANVAS_W - S_COL_LABEL, S_SEP);
            y += S_ROW_HDR_H;
        }
        for (int i = 0; i < count; i++) {
            drawRow(y, rows[i]);
            y += S_ROW_H;
        }
        return y;
    }

    // Row with a right-side chevron — indicates deeper navigation.
    void drawChevronRow(int screenY, const char* label) const {
        drawRow(screenY, { label, ">", S_LABEL, S_CHEVRON });
    }

    // Horizontal separator line at screenY (col-aligned to S_COL_LABEL).
    void drawSep(int screenY) const {
        tft.drawFastHLine(S_COL_LABEL, screenY,
                          S_CANVAS_W - S_COL_LABEL, S_SEP);
    }

    // ---- Hit-testing (wraps hitbox.h) ----------------------------------------

    // Returns 0-based row index for a tap at py, or -1 if outside content rows.
    // hasSubHeader: set true if drawRows() was called with a subHeader string.
    int tapToRow(int py, bool hasSubHeader = false) const {
        int16_t firstY = S_CONTENT_Y + (hasSubHeader ? S_ROW_HDR_H : 0);
        int16_t avail  = S_CONTENT_H - (hasSubHeader ? S_ROW_HDR_H : 0);
        Rect area = { 0, firstY, S_CANVAS_W, avail };
        return hitTestRow(area, S_ROW_H, py);
    }

    // True if the tap lands in the < back zone (top-left of header bar).
    bool isBackTap(int px, int py) const {
        Rect backZone = { 0, 0, S_BACK_ZONE_W, S_HEADER_H };
        return hitTest(backZone, px, py);
    }

    // ---- Settings storage access -------------------------------------------

    AppSettings& settings()    { return g_settings; }
    void         saveSettings(){ SettingsStorage::save(); }
};
