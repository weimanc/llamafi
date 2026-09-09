// clockApp.cpp — ClockApp method bodies, out-of-line (M-SRCLAYOUT Stage E).
#include "apps/clockApp.h"
#include "debug/timeInject.h"   // ADR-064 D5: host-injectable, freezable time (TASK-638)

// Out-of-class definitions for the static constexpr theme tables — required
// pre-C++17 (this project targets gnu++11) whenever a static constexpr array
// member is ODR-used, which binding `const NixieTheme& th = kNixieThemes[i]`
// does. Now that clockApp.h is included from two translation units
// (shell/appTable.h's composition root AND this file), these definitions
// must live in exactly one place — here, not the header — or every TU that
// compiles them would emit its own copy and the link would fail on the
// duplicate symbol.
constexpr ClockApp::NixieTheme ClockApp::kNixieThemes[4];
constexpr ClockApp::VfdTheme ClockApp::kVfdThemes[4];

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

void ClockApp::tick() {
    unsigned long now = millis();
    bool anyFlip = (g_settings.clockStyle == ClockStyle::Flip) && _anyFlipActive();
    unsigned long gate = anyFlip ? 30 : 1000;
    if (now - _lastTickMs < gate) return;
    _lastTickMs = now;
    _doTick();
}

bool ClockApp::handleInput(TouchPhase phase, int x, int y) {
    (void)x;
    if (phase != TouchPhase::Release) return false;
    unsigned long now = millis();
    if (now - _lastTapMs < 300) {
        strlcpy(_lastAction, "DEBOUNCE", sizeof(_lastAction));
        return false;
    }
    _lastTapMs = now;
    return (y < CLK_TAP_SPLIT_Y) ? _cycleTheme() : _cycleFace();
}

void ClockApp::_snapshotPersisted() {
    _savedStyle = g_settings.clockStyle;
    _savedNixie = g_settings.nixieTheme;
    _savedVfd   = g_settings.vfdTheme;
    _snapshotValid = true;
}

void ClockApp::_flushStyleIfDirty() {
    if (!dbgStyleDirty()) return;
    SettingsStorage::save();
    _snapshotPersisted();
}

bool ClockApp::_cycleFace() {
    g_settings.clockStyle =
        (ClockStyle)(((uint8_t)g_settings.clockStyle + 1) % 4);
    strlcpy(_lastAction, "TAP_FACE", sizeof(_lastAction));
    repaint();
    return true;
}

bool ClockApp::_cycleTheme() {
    switch (g_settings.clockStyle) {
        case ClockStyle::Nixie:
            g_settings.nixieTheme = (uint8_t)((g_settings.nixieTheme + 1) % 4);
            break;
        case ClockStyle::VFD:
            g_settings.vfdTheme = (uint8_t)((g_settings.vfdTheme + 1) % 4);
            break;
        default:
            // Q1: faces without themes — consumed no-op, no repaint.
            strlcpy(_lastAction, "TAP_THEME_NA", sizeof(_lastAction));
            return true;
    }
    strlcpy(_lastAction, "TAP_THEME", sizeof(_lastAction));
    repaint();
    return true;
}

void ClockApp::repaint() {
    switch (g_settings.clockStyle) {
        case ClockStyle::Flip:
            tft.fillRect(0, 0, TASKBAR_X, 240, TFT_BLACK);
            // Clock body plate behind the cards — was re-filled every
            // tick by _drawFlip() (the whole-face flicker); static now.
            tft.fillRect(5, 4, 265, 86, kFpBody);
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
    // Invalidate the engine's delta cache: next _doTick() force-redraws
    // every digit slot + colon for the active face.
    memset(_lastDigs, 0xFF, sizeof(_lastDigs));
    _lastColon  = -1;
    _lastTickMs = 0;
    tick();
}

void ClockApp::_doTick() {
    struct tm t; if (!dbgLocalTime(&t)) return;
    uint8_t hh = clockHour(t);   // WIRE2-G2: digit pair stays two digits ("09")
    uint8_t digs[4] = {
        (uint8_t)(hh / 10), (uint8_t)(hh % 10),
        (uint8_t)(t.tm_min / 10), (uint8_t)(t.tm_min % 10)
    };
    bool colonOn = (t.tm_sec % 2 == 0);

    bool force = (_lastDigs[0] > 9);   // cache invalidated by repaint()
    uint8_t changed = 0;               // per-slot bitmask
    for (int i = 0; i < 4; i++)
        if (force || digs[i] != _lastDigs[i]) changed |= (uint8_t)(1 << i);
    bool colonChanged = force || ((int8_t)colonOn != _lastColon);

    switch (g_settings.clockStyle) {
        case ClockStyle::Flip:
            _tickFlip(digs, changed, colonOn, colonChanged, force);
            break;
        case ClockStyle::Nixie:
            _tickNixie(digs, changed, colonOn, colonChanged);
            _drawDate();
            _drawRssi();
            break;
        case ClockStyle::VFD:
            _tickVFD(t, digs, changed, colonOn, colonChanged);
            _drawRssi();
            break;
        default:
            // Digital predates the engine and is already delta-clean
            // internally (string-cache erase gating + self-overdrawing
            // colon glyph); its seconds bar changes every tick anyway,
            // so it keeps its own per-second path unchanged.
            _drawDigital();
            _drawSecondsBar();
            _drawDate();
            _drawRssi();
            break;
    }

    memcpy(_lastDigs, digs, sizeof(_lastDigs));
    _lastColon = (int8_t)colonOn;
}

void ClockApp::_drawDigital() {
    struct tm t; if (!dbgLocalTime(&t)) return;
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

void ClockApp::_drawSecondsBar() {
    struct tm t; if (!dbgLocalTime(&t)) return;
    for (int i = 0; i < 60; ++i) {
        uint16_t c = (i < t.tm_sec) ? tft.color565(
            (int)(sinf((float)i / 60.0f * TWO_PI)                    * 127 + 128),
            (int)(sinf((float)i / 60.0f * TWO_PI + TWO_PI / 3.0f)   * 127 + 128),
            (int)(sinf((float)i / 60.0f * TWO_PI + 2*TWO_PI / 3.0f) * 127 + 128)
        ) : (uint16_t)0x07FF;
        tft.fillRect(8 + (int)((float)i * 4.3f), 100, 2, 25, c);
    }
}

void ClockApp::_drawDate() {
    struct tm t; if (!dbgLocalTime(&t)) return;
    static const char* kDays[] = {"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString(kDays[t.tm_wday], 137, 170, 4);
    char dBuf[16];
    fmtDate(t, dBuf, sizeof(dBuf), '/');   // WIRE2-G3: DMY/MDY/YMD per settings
    tft.drawString(dBuf, 137, 200, 4);
    tft.setTextDatum(TL_DATUM);
}

void ClockApp::_drawRssi() {
    int rssi = WiFi.RSSI();
    int bars = (rssi > -55) ? 4 : (rssi > -65) ? 3 : (rssi > -75) ? 2 : 1;
    for (int i = 0; i < 4; ++i) {
        uint16_t c = (i < bars) ? TFT_GREEN : (uint16_t)0x4208;
        tft.fillRect(240 + i * 7, 228 - (i + 1) * 5, 5, (i + 1) * 5, c);
    }
}

void ClockApp::_drawFlipColon(bool on) {
    uint16_t colonC = on ? kFpDigit : (uint16_t)0x2104;
    tft.fillCircle(138, kFpY + 19, 5, colonC);
    tft.fillCircle(138, kFpY + 59, 5, colonC);
}

void ClockApp::_tickFlip(const uint8_t* digs, uint8_t changed, bool colonOn,
               bool colonChanged, bool force) {
    static const int kFpX[4] = {13, 73, 147, 207};
    // Start animation for any changed digit (skip straight-set on force:
    // after repaint() the panels draw their target digit directly).
    for (int i = 0; i < 4; i++) {
        if (force) {
            _fd[i].shown = _fd[i].botShown = _fd[i].next = digs[i];
            _fd[i].frame = 0;
        } else if ((changed & (1 << i)) && _fd[i].frame == 0 && _fd[i].shown != digs[i]) {
            _fd[i].next     = digs[i];
            _fd[i].botShown = digs[i]; // bottom switches immediately
            _fd[i].frame    = 1;
        }
    }
    if (colonChanged) _drawFlipColon(colonOn);
    // Draw animating panels (or all, on force) and advance frames.
    for (int i = 0; i < 4; i++) {
        if (!force && _fd[i].frame == 0) continue;
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
    if (!_anyFlipActive()) { _drawDate(); _drawRssi(); }
}

void ClockApp::_drawFlipPanel(int px) {
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
    // band to track anymore). Font 8 (75px tall / 55px wide digits) —
    // font 6 (48px) was sized for the old 46x62 card and never rescaled
    // when the card grew to 56x78, leaving digits looking small and thin
    // against the concept's bold, near-full-height glyphs. Font 8 is the
    // closest built-in TFT_eSPI match to that proportion.
    withViewportRepair(tft, px, mid_y + kFpGap, kFpW, kFpMid, [&]{
        tft.setTextColor(kFpDigit, kFpBgBot);
        tft.drawString(bStr, cx, mid_y, 8);
    });

    // 2. Flap background — flat card colour, same as concept's top half.
    tft.fillRect(px, mid_y - fh, kFpW, fh, kFpBgTop);

    // 3. Flap digit — same shared anchor (mid_y), clipped to the flap
    // rect (which shrinks toward mid_y as fh decreases during the fall).
    withViewportRepair(tft, px, mid_y - fh, kFpW, fh, [&]{
        tft.setTextColor(kFpDigit, kFpBgTop);
        tft.drawString(fStr, cx, mid_y, 8);
    });

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

void ClockApp::_tintNixieGlyph(uint8_t digit, int rowStart, int rows, uint16_t* out) {
    static uint16_t s_lut[16];
    static uint8_t  s_lutTheme = 0xFF;
    uint8_t themeIdx = g_settings.nixieTheme % 4;
    if (themeIdx != s_lutTheme) {
        const NixieTheme& th = kNixieThemes[themeIdx];
        for (int i = 0; i < 16; i++) {
            uint8_t l = (uint8_t)(i * 17);   // dequant: 0..15 -> 0..255
            s_lut[i] = tft.color565((uint16_t)th.r * l / 255,
                                    (uint16_t)th.g * l / 255,
                                    (uint16_t)th.b * l / 255);
        }
        s_lutTheme = themeIdx;
    }
    const uint8_t* packed = nixie_glyph_ptrs[digit % 10]
                          + (size_t)rowStart * (NIXIE_GLYPH_W / 2);
    int n = rows * (NIXIE_GLYPH_W / 2);
    for (int i = 0; i < n; i++) {
        uint8_t b = packed[i];
        out[2 * i]     = s_lut[b >> 4];
        out[2 * i + 1] = s_lut[b & 0x0F];
    }
}

void ClockApp::_drawNixieColon(bool on) {
    const NixieTheme& theme = kNixieThemes[g_settings.nixieTheme % 4];
    uint16_t coreFull = tft.color565(theme.r, theme.g, theme.b);
    uint16_t haloDim  = tft.color565(theme.r * 3 / 10, theme.g * 3 / 10, theme.b * 3 / 10);
    uint16_t colonHalo = on ? haloDim : TFT_BLACK;
    uint16_t colonCore = on ? coreFull : TFT_BLACK;
    for (int cy : {kNxTy + kNxTh / 3, kNxTy + 2 * kNxTh / 3}) {
        tft.fillCircle(137, cy, 5, colonHalo);
        tft.fillCircle(137, cy, 2, colonCore);
    }
}

void ClockApp::_drawNixieTube(int tx, uint8_t digit) {
    static const int kTintBandRows = 5;
    static uint16_t s_nixieTintBuf[NIXIE_GLYPH_W * kTintBandRows];
    int cx = tx + kNxTw / 2;
    tft.fillRect(tx - 2, 4, kNxTw + 4, kNxTh + 8, TFT_BLACK);
    for (int ry = 0; ry < kNxTh; ry += kTintBandRows) {
        int rows = min(kTintBandRows, kNxTh - ry);
        _tintNixieGlyph(digit, ry, rows, s_nixieTintBuf);
        tft.pushImage(tx, kNxTy + ry, kNxTw, rows, s_nixieTintBuf);
    }
    tft.drawRoundRect(tx, kNxTy, kNxTw, kNxTh, kNxTr, 0x30A0);
    tft.fillRect(cx - 7, kNxTy + kNxTh, 3, 3, 0x0800);
    tft.fillRect(cx + 4, kNxTy + kNxTh, 3, 3, 0x0800);
}

void ClockApp::_tickNixie(const uint8_t* digs, uint8_t changed, bool colonOn,
                bool colonChanged) {
    static const int kTx[4] = {24, 78, 148, 202};
    for (int i = 0; i < 4; i++)
        if (changed & (1 << i)) _drawNixieTube(kTx[i], digs[i]);
    if (colonChanged) _drawNixieColon(colonOn);
    tft.setTextDatum(TL_DATUM);
}

void ClockApp::_drawVFDDigitSlot(int d, uint8_t digitVal, uint8_t dcol) {
    uint16_t onC = _vfdOnColor(), offC = _vfdOffColor();
    tft.startWrite();
    for (int r = 0; r < 24; r++) {
        int gr = r - 1; // GLYPH_ROW_OFFSET=1
        for (int gc = 0; gc < 11; gc++) {
            bool active = false;
            if (gr >= 0 && gr < 22)
                active = (kVFDGlyphs[digitVal][gr] >> (10 - gc)) & 1;
            int px = 3 + (dcol + gc) * 5;
            int py = 10 + r * 5;
            tft.fillRect(px, py, 4, 4, active ? onC : offC);
        }
    }
    tft.endWrite();
}

void ClockApp::_drawVFDColon(bool colonOn) {
    uint16_t color = colonOn ? _vfdOnColor() : _vfdOffColor();
    tft.startWrite();
    for (int c = 26; c <= 27; c++) {
        for (int r = 7; r <= 8; r++)
            tft.fillRect(3 + c * 5, 10 + r * 5, 4, 4, color);
        for (int r = 15; r <= 16; r++)
            tft.fillRect(3 + c * 5, 10 + r * 5, 4, 4, color);
    }
    tft.endWrite();
}

void ClockApp::_tickVFD(const struct tm& t, const uint8_t* digs, uint8_t changed,
              bool colonOn, bool colonChanged) {
    static const uint8_t kDCol[4] = {2, 14, 29, 41}; // glyph start dot-col

    for (int d = 0; d < 4; d++)
        if (changed & (1 << d)) _drawVFDDigitSlot(d, digs[d], kDCol[d]);
    if (colonChanged) _drawVFDColon(colonOn);

    // Date below digit block (y≈141 per approved constants)
    static const char* kDays[] = {"Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"};
    char dBuf[12];
    fmtDate(t, dBuf, sizeof(dBuf), '-');   // WIRE2-G3: VFD-only date line (W-10)
    tft.setTextSize(2);
    tft.setTextColor(_vfdDateColor(), 0x0022);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(kDays[t.tm_wday], 137, 148, 1);
    tft.drawString(dBuf, 137, 166, 1);
    tft.setTextSize(1);
    tft.setTextDatum(TL_DATUM);
}
