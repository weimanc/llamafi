#pragma once
// clockApp.h — Clock with Digital / Flip / Nixie / VFD styles (M-CLOCK-STYLES).
// Self-contained per D0/SF.11 (M-SRCLAYOUT Stage E / TASK-471). Method bodies
// and the two static-constexpr theme-table definitions live in clockApp.cpp —
// this header is now included from more than one translation unit
// (shell/appTable.h's composition root AND clockApp.cpp itself), so anything
// with storage must be defined exactly once, out-of-line.

#include <Arduino.h>
#include <TFT_eSPI.h>
#include "appShell.h"
#include "settingsStorage.h"
#include "util/timeFmt.h"   // WIRE2-G2/G3: clockHour/clockAmPm/fmtDate
#include "gen/nixie_glyphs.h"   // TASK-336: baked wire-glyph+bloom sprites (bake_nixie.py)
#include "util/tftViewportRepair.h"   // TASK-359: Flip digit-clip migrated onto the shared helper
#include <WiFi.h>
#include <time.h>
#include <math.h>

#include "display/tft.h"

// ── FlipDigit state ──────────────────────────────────────────────────────────
struct FlipDigit {
    uint8_t shown;    // digit shown in top half (current stable)
    uint8_t next;     // digit to flip to
    uint8_t botShown; // digit shown in bottom half (switches at start of animation)
    uint8_t frame;    // 0=stable; 1..4=animating
};

// M-CLOCK-TAP-CYCLE (TASK-346): in-app cycling zones. Canvas splits at this
// y — above: cycle the active face's colour theme (Nixie/VFD only; strict
// no-op elsewhere, Q1), below: cycle the face itself. Named constant so
// hit-test and VE tests reference geometry, not magic numbers.
static constexpr int16_t CLK_TAP_SPLIT_Y = 120;

class ClockApp : public App {
public:
    // TASK-518 (P4): no hasInFlightOp() override — Clock is entirely local
    // (RTC read + render; taps only mutate g_settings in RAM and the one
    // persist is a synchronous save in suspend()). No network, no task, no
    // queue: it inherits the App default (== hasPendingAsync() == false),
    // which is the true answer. isConnecting() is not implemented here either.

    void init()    override { _snapshotPersisted(); repaint(); }
    void resume()  override { _snapshotPersisted(); repaint(); }
    void suspend() override {
        tft.setTextDatum(TL_DATUM);
        _flushStyleIfDirty();   // ADR-050 rule 3: one coalesced save per session, iff changed
    }

    void tick() override;

    // M-CLOCK-TAP-CYCLE (TASK-346): Release-phase tap zones + debounce
    // (teletext idiom). Mutates g_settings in RAM only — persistence is
    // deferred to suspend()'s _flushStyleIfDirty().
    bool handleInput(TouchPhase phase, int x, int y) override;

    // VE observables (`get clockStyle` dirty field / `get clockLastAction`).
    const char* dbgLastAction() const { return _lastAction; }
    bool dbgStyleDirty() const {
        // Snapshot only exists once the app has run (init/resume) — before
        // that, comparing g_settings against constructor defaults would
        // report a phantom dirty at boot.
        if (!_snapshotValid) return false;
        return g_settings.clockStyle != _savedStyle ||
               g_settings.nixieTheme != _savedNixie ||
               g_settings.vfdTheme   != _savedVfd;
    }

private:
    unsigned long _lastTickMs = 0;
    unsigned long _lastTapMs  = 0;
    char          _lastAction[16] = "";
    // Persisted-state snapshot, refreshed on init/resume and after every
    // flush — dirty = current g_settings differs from it, so cycling full
    // circle back costs zero flash writes (design D4 wear guard).
    ClockStyle    _savedStyle = ClockStyle::Digital;
    uint8_t       _savedNixie = 0;
    uint8_t       _savedVfd   = 0;
    bool          _snapshotValid = false;

    void _snapshotPersisted();
    void _flushStyleIfDirty();
    bool _cycleFace();
    bool _cycleTheme();

    FlipDigit     _fd[4]      = {};
    // W-6 erase-gating cache (Digital): last rendered hour string + AM/PM ptr.
    char          _lastHourStr[4] = "";
    const char*   _lastAmPm       = nullptr;
    // Delta-engine FaceFrame cache (TASK-354): last-drawn digits + colon
    // parity, shared by every face. Sentinels (>9 / -1) = invalidated by
    // repaint(), forcing a full redraw on the next tick. Absorbs what used
    // to be the VFD-only _vfdDigs/_vfdColonOn private cache.
    uint8_t       _lastDigs[4]    = {0xFF, 0xFF, 0xFF, 0xFF};
    int8_t        _lastColon      = -1;

    bool _anyFlipActive() const {
        for (int i = 0; i < 4; i++) if (_fd[i].frame > 0) return true;
        return false;
    }

    // Static layer only (TASK-354: the engine's drawStatic hook) — per-face
    // backgrounds and frames that never change between full repaints. The
    // per-second dynamic content is owned by _doTick()'s delta engine.
    void repaint();

    // ── Delta engine (TASK-354, M-CLOCK-FACE-COMMON pt 1) ──────────────────
    // Computes the FaceFrame (4 digits + colon parity) ONCE, diffs it against
    // the cached previous frame, and hands the per-face renderers only what
    // changed. This is what VFD privately implemented (and Digital half-did
    // with string caches) while Flip/Nixie redrew their whole face every
    // second to blink an 8-px colon — the fix is structural, not a third and
    // fourth private cache. Faces own HOW to draw; the engine owns WHEN.
    void _doTick();

    // ── Digital ─────────────────────────────────────────────────────────────
    void _drawDigital();

    // ── Seconds bar (Digital) ────────────────────────────────────────────────
    void _drawSecondsBar();

    // ── Date (all non-VFD styles) ────────────────────────────────────────────
    void _drawDate();

    // ── RSSI indicator ───────────────────────────────────────────────────────
    void _drawRssi();

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

    // Colon — round flip-dots, 1Hz blink. Self-erasing: both states fully
    // overdraw the same two circles, so no background wipe is needed.
    // M-CLOCK-FLIP.md specs an animated 45deg-rotating disc at 500ms on/off;
    // that needs the tick gate to run at <=500ms even when no digit is
    // flipping (currently 1000ms) — out of scope, deferred (pre-existing).
    // X/Y/radius match the concept's colon geometry (_COLON_CX/_COLON_Y1/Y2/DOT_R).
    void _drawFlipColon(bool on);

    // TASK-354 delta renderer: the engine says which digits changed; panels
    // repaint only while animating (each _drawFlipPanel call fully covers
    // its own card rect, so no body wipe — that moved to repaint()). The
    // per-second steady-state cost drops from full-face to two fillCircles.
    void _tickFlip(const uint8_t* digs, uint8_t changed, bool colonOn,
                   bool colonChanged, bool force);

    // Draws one flip panel for _fd[pi] state.
    // flap is anchored at split line, extends upward by fh pixels.
    void _drawFlipPanel(int px);

    // ── Nixie ───────────────────────────────────────────────────────────────
    // Tube geometry resynced 2026-07-18 to the concept tool
    // (app/tools/_clock_nixie.py TUBE_W/H/R/XS) per user direction, same
    // pattern as the Flip clock's TASK-337 concept resync — was previously a
    // flatter 52x70/r26 shipped geometry, documented as a deliberate
    // deviation; that override is gone now (see M-CLOCK-NIXIE.md).
    //
    // Colour themes (M-CLOCK-THEMES, TASK-345): names/values copied verbatim
    // from M-CLOCK-NIXIE.md's theme table. bake_nixie.py bakes luminance
    // only (uint8_t, C_WIRE=white) — _tintNixieGlyph() reconstructs any
    // theme's colour at runtime (color565(R*lum/255, G*lum/255, B*lum/255)),
    // exact for the glyph/bloom/mesh layers (see bake_nixie.py docstring for
    // the linearity argument and one documented near-invisible exception).
    // Outline/pin-shadow colours stay fixed regardless of theme — the
    // concept's _draw_tube() hardcodes those independent of C_WIRE too.
    struct NixieTheme { const char* name; uint8_t r, g, b; };
    static constexpr NixieTheme kNixieThemes[4] = {
        { "amber", 255, 125,   8 },
        { "red",   255,  45,  10 },
        { "green",  50, 255,  80 },
        { "blue",   70, 150, 255 },
    };

    // Tints `rows` rows starting at `rowStart` (band-wise, not the whole
    // 48x110 tube at once — a full-tube uint16_t scratch buffer is 10.6 KB,
    // enough to overflow this board's tight DRAM budget when added to the
    // rest of the debug build's static buffers; bands keep it small, same
    // pattern as screendump's kBandRows).
    //
    // TASK-353 (M-CLOCK-FACE-COMMON pt 2): source is 4-bit packed luminance
    // (two px/byte, high nibble = left pixel; NIXIE_GLYPH_W is even so rows
    // never straddle a byte). The 16-entry per-theme RGB565 LUT replaces the
    // previous three-multiplies-per-pixel tint — decode l = nibble*17 is
    // folded into the table, so the hot loop is two table fetches per byte.
    static void _tintNixieGlyph(uint8_t digit, int rowStart, int rows, uint16_t* out);

    // Nixie tube geometry — shared by the per-tube renderer and the colon.
    static constexpr int kNxTy = 8, kNxTw = 48, kNxTh = 110, kNxTr = 18;

    // Colon dots — round, with a poor-man's bloom (dim halo + bright core,
    // same trick the tube uses for its glow rings). Colour is the active
    // theme's C_WIRE: halo ~30% scale, core full brightness. Blinks at
    // 0.5Hz (concept's smooth ramp/decay afterglow is a separate, deferred
    // change — see M-CLOCK-NIXIE.md colon afterglow gap). Both circles are
    // always redrawn (even "off", in black) so the previous frame's glow is
    // fully erased regardless of state — self-erasing, so the engine can
    // call this alone on parity flips with no band wipe. X/Y match the
    // concept's COLON_CX (gutter midpoint between H2 and M1) and
    // TUBE_Y+TUBE_H/3, TUBE_Y+2*TUBE_H/3.
    void _drawNixieColon(bool on);

    // One tube (TASK-354: the engine's drawDigit hook). Erases just this
    // tube's column (sprite + glass ring + pin shadows all live inside it;
    // the colon gutter at x132..142 is clear of every tube), then:
    // 1. Baked wire-glyph + hex-mesh + 3-pass-bloom sprite (TASK-336,
    //    bake_nixie.py), 4-bit packed, tinted to the active theme via the
    //    16-entry LUT (TASK-353) band-wise through the small scratch buffer
    //    (a full-tube buffer overflowed this board's DRAM budget).
    // 2. Glass outline — single subtle stroke matching the concept's
    //    _draw_tube() (outline=(50,22,5), width=1).
    // 3. Pin shadows below the tube, near-black per the concept.
    void _drawNixieTube(int tx, uint8_t digit);

    // TASK-354 delta renderer: was a full-width wipe + all-four-tubes
    // re-tint/re-push every second (~42 KB SPI + the tint loop, dragged in
    // by the colon blink); now a changed tube redraws at most twice a
    // minute and the steady-state second tick is four fillCircles.
    void _tickNixie(const uint8_t* digs, uint8_t changed, bool colonOn,
                    bool colonChanged);

    // ── VFD ─────────────────────────────────────────────────────────────────
    // Dot grid: 54 cols × 24 rows, TC=4px, TG=1px, GRID_X0=3, GRID_Y0=10
    // Glyph start cols (dot units): H1=2, H2=14, M1=29, M2=41
    // Colon: 2×2 dot block at rows 7-8 and 15-16, cols 26-27
    // Palette (RGB565): BG=0x0022 fixed for all themes (M-CLOCK-VFD.md:
    // "same for all themes"); ON/OFF/DATE derived from the active theme's
    // C_ON at runtime (M-CLOCK-THEMES, TASK-345) via the doc's own formulas
    // (OFF = C_ON x 0.06 "standard" contrast, DATE = C_ON x 0.68) — the old
    // hardcoded 0x069C/0x0061/0x0473 were exactly teal (theme 0) run through
    // these same formulas, confirmed by hand-decoding before this change.
    struct VfdTheme { const char* name; uint8_t r, g, b; };
    static constexpr VfdTheme kVfdThemes[4] = {
        { "teal",   0, 210, 230 },
        { "amber", 230, 160,   0 },
        { "blue",   60, 120, 255 },
        { "green",   0, 220,  80 },
    };
    uint16_t _vfdOnColor()   const { const VfdTheme& t = kVfdThemes[g_settings.vfdTheme % 4]; return tft.color565(t.r, t.g, t.b); }
    uint16_t _vfdOffColor()  const { const VfdTheme& t = kVfdThemes[g_settings.vfdTheme % 4]; return tft.color565(t.r * 6 / 100, t.g * 6 / 100, t.b * 6 / 100); }
    uint16_t _vfdDateColor() const { const VfdTheme& t = kVfdThemes[g_settings.vfdTheme % 4]; return tft.color565(t.r * 68 / 100, t.g * 68 / 100, t.b * 68 / 100); }

    // Redraw a single digit slot's 11×24 dot cells (glyph rows 1..22, plus
    // the always-off margin rows 0/23). Only called when that digit's value
    // actually changed — see delta-redraw note on _tickVFD().
    void _drawVFDDigitSlot(int d, uint8_t digitVal, uint8_t dcol);

    // Redraw just the colon's 8 dot cells (cols 26-27, rows 7-8 & 15-16).
    // Only called when colon on/off state actually changed.
    void _drawVFDColon(bool colonOn);

    // TASK-354: VFD was the face that pioneered delta redraw (its header
    // comment records the whole-screen flicker it fixed) — this renderer is
    // that same logic, minus the private _vfdDigs/_vfdColonOn cache the
    // shared engine now owns. Digit slots change at most once/minute; colon
    // toggles once/second but is only 8 cells.
    void _tickVFD(const struct tm& t, const uint8_t* digs, uint8_t changed,
                  bool colonOn, bool colonChanged);
};
