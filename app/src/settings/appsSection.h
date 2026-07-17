#pragma once
#include "settingsSection.h"
#include "settingsWidgets.h"   // TASK-328 kit — first consumer is the TASK-321 location editor
#include "sliderWidget.h"      // M-WEBRADIO-SETTINGS D2: Max-volume row (WR-3 phase-forwarded)
#include "gen/configurable_apps.h"
#include "keyboardWidget.h"
#include "dataTask.h"
#include "planeRadarConfig.h"
#include "logDecode.h"   // httpErr() — TASK-321 geocode error decode
#include "cities.h"      // M-HOME-LOCATION H-4: divergence-hint reference coords (kCities lookup by name)

const char* cgIdToDisplay(const char* id);

class AppsSection : public SettingsSection {
public:
    const char* title() const override {
        if (_sub < 0) return "Applications";
        if (_prLocActive) return _prLocTitle();
        return kConfigurableApps[_sub].display;
    }

    int submenu() const { return (int)_sub; }

    // M-HOME-LOCATION H-5/H-6: divergence-km observable for T-HOME-05 —
    // last value computed by the confirm screen (0 when not applicable).
    // Read by `get prloc` via SettingsApp.
    int prDivKm() const { return _prDivKm; }

    void enter() override { _sub = -1; _prLocActive = false; repaint(); }
    void leave() override {
        if ((_prLocActive || _wrSub()) && g_keyboard.active()) g_keyboard.hide();
        if (g_countryPicker.active()) g_countryPicker.hide();   // M-COUNTRY-PICKER
        _prLocActive = false;
        _sub = -1;
    }

    // Keyboard-driven PrLocView steps (EditLabel / LookupCountry / LookupPostcode)
    // own the full canvas via KeyboardWidget — mirrors wifiSection's
    // `if (_step == WifiStep::Keyboard) return;` guard (TASK-321).
    void repaint() override {
        if (_prLocActive && _prLocIsKeyboardStep()) return;
        // M-COUNTRY-PICKER (CP-1 takeover): an active picker owns the full
        // canvas — never paint under it (same guard as the keyboard steps).
        if (g_countryPicker.active()) return;
        drawHeader();
        clearContent();
        if (_sub < 0)          _repaintAppList();
        else if (_prLocActive) _repaintPrLoc();
        else                   _repaintAppRows();
    }

    SectionResult tick() override {
        if (_prLocActive && _prLocState == PrLocView::LookupPending) {
            _tickPrLookup();
            return SectionResult::Continue;
        }
        if (_editPhase != StockEditPhase::Validating) return SectionResult::Continue;
        dataTask::StockChartResult r;
        if (dataTask::pollStockChart(&r)) {
            // TASK-300: a stale chart result parked by the Stock app (fetch
            // returned after back-out/app-switch) would false-validate any
            // typo ticker here. Only accept the result for OUR symbol.
            if (strcmp(r.symbol, _pendingTicker) != 0)
                return SectionResult::Continue;  // keep waiting until timeout
            if (r.ok && r.len > 0) {
                strlcpy(settings().stockTickers[_editRow], _pendingTicker, 8);
                saveSettings();
                _editPhase = StockEditPhase::None;
                repaint();
            } else {
                _editPhase = StockEditPhase::Error;
                repaint();
            }
        } else if (millis() - _validateStartMs > kValidateTimeoutMs) {
            _editPhase = StockEditPhase::Error;
            repaint();
        }
        return SectionResult::Continue;
    }

    bool isValidating() const { return _editPhase == StockEditPhase::Validating; }

    SectionResult handleInput(TouchPhase phase, int x, int y) override {
        // Keyboard captures all touch while a PrLocView keyboard step is active
        // (mirrors wifiSection's pattern) — checked before back-tap, since the
        // keyboard has its own cancel zone at x<40,y<KB_INPUT_H that overlaps
        // where our header back-zone would otherwise be.
        if ((_prLocActive || _wrSub()) && g_keyboard.active()) {
            g_keyboard.handleInput(phase, x, y);
            return SectionResult::Continue;
        }
        // M-COUNTRY-PICKER (CP-1): an active picker captures ALL phases —
        // same precedent as the keyboard branch above (pierces the
        // Release-only gate below so the scrollbar thumb drag works). The
        // picker owns its own "< back" cancel zone, so this runs before the
        // section's isBackTap() check.
        if ((_prLocActive || _wrSub()) && g_countryPicker.active()) {
            g_countryPicker.handleInput(phase, x, y);
            return SectionResult::Continue;
        }
        // WR-3 (M-WEBRADIO-SETTINGS D2): SliderWidget needs Press/Move/Release,
        // but this section is Release-only below — forward all phases to the
        // Max-volume slider while the WebRadio submenu is showing (the keyboard
        // capture above is the precedent for piercing the Release-only gate;
        // DisplaySection's Level row is the routing idiom). Live volume apply
        // is NOT needed — the radio is never running while Settings is open.
        if (_wrSub() && !g_keyboard.active()) {
            const int volRowY = S_CONTENT_Y + 4 * S_ROW_H;   // row 4 = Max volume
            if (phase == TouchPhase::Press) {
                _wrVolSlider.onPress(x, y, volRowY);
            } else if (phase == TouchPhase::Move && _wrVolSlider.isDragging()) {
                _wrVolSlider.onMove(x);
                _wrVolSlider.render(volRowY, "Max vol");
            } else if (phase == TouchPhase::Release && _wrVolSlider.isDragging()) {
                settings().webRadioMaxVolume = (uint8_t)_wrVolSlider.onRelease(x);
                saveSettings();
                repaint();   // refresh row + the TASK-209 cap hint
                return SectionResult::Continue;   // captured — no row dispatch
            }
        }
        if (phase != TouchPhase::Release) return SectionResult::Continue;
        if (isBackTap(x, y)) {
            if (_prLocActive) { _handlePrLocBack(); return SectionResult::Continue; }
            if (_sub >= 0) { _sub = -1; repaint(); return SectionResult::Continue; }
            return SectionResult::GoBack;
        }
        if (_sub < 0) {
            Rect area = { 0, S_CONTENT_Y, S_CANVAS_W, S_CONTENT_H };
            int row = hitTestRow(area, _appListRowH(), y);
            if (row >= 0 && row < CONFIGURABLE_APP_COUNT) { _sub = (int8_t)row; repaint(); }
        } else if (_prLocActive) {
            _handlePrLocTap(x, y);
        } else {
            _handleAppTap(tapToRow(y));
        }
        return SectionResult::Continue;
    }

private:
    enum class StockEditPhase : uint8_t { None, Validating, Error };

    int8_t          _sub             = -1;
    StockEditPhase  _editPhase       = StockEditPhase::None;
    int8_t          _editRow         = -1;
    char            _pendingTicker[8]= {};
    unsigned long   _validateStartMs = 0;
    static constexpr unsigned long kValidateTimeoutMs = 20000;

    // ---- M-PR-LOCATIONS / TASK-321/322: Locations sub-view + slot editor ---
    // Explicit state machine (DEV-4 — own state machine from the start, not
    // boolean flags). ManualLat/ManualLon/ManualConfirm (TASK-322) are the
    // second coordinate-source path alongside Lookup*; both funnel into the
    // same _prGeoLat/_prGeoLon + _prSaveCoords() confirm/save primitive.
    enum class PrLocView : uint8_t {
        SlotList, EditLabel, SourceFork,
        LookupCountry, LookupPostcode, LookupPending, LookupConfirm, LookupError,
        ManualLat, ManualLon, ManualConfirm
    };

    bool          _prLocActive       = false;   // gates the whole sub-view (PlaneRadar row view otherwise)
    PrLocView     _prLocState        = PrLocView::SlotList;
    uint8_t       _prEditSlot        = 0;
    char          _prPendingLabel[PR_LABEL_MAX + 1] = {};   // label edit is NOT persisted until final Save
    char          _prPendingCountry[3]  = {};
    char          _prPendingPostcode[11] = {};
    char          _prLastCountry[3]  = "NL";    // session-remembered across lookups (Q5)
    uint8_t       _prGeoSeq          = 0;       // seq identity — DEV-1/TASK-300 lesson
    float         _prGeoLat          = 0.0f;
    float         _prGeoLon          = 0.0f;
    int           _prGeoErr          = 0;
    int           _prDivKm           = 0;       // M-HOME-LOCATION H-4/H-6: confirm-screen divergence km; 0 = n/a
    char          _prGeoDisplay[48]  = {};
    SSpinner      _prSpinner;
    unsigned long _prSpinnerMs       = 0;
    SButton       _prForkBtn[3];   // SourceFork: [Lookup][Manual][Delete] stacked
    SButton       _prBar[3];       // reused across Pending(n=1)/Error(n=2)/Confirm(n=3) bottom bars
    mutable char  _prTitleBuf[16]   = {};

    // M-WEBRADIO-SETTINGS D2 row 4: Max-volume slider (1..21). Phase routing
    // lives in handleInput()'s WR-3 forwarding hook, not here.
    SliderWidget  _wrVolSlider;

    // Shrinks below S_ROW_H only once CONFIGURABLE_APP_COUNT no longer fits
    // S_CONTENT_H at the default row height (bug found 2026-07-11: PlaneRadar
    // was the 9th configurable app, and 9*S_ROW_H=234 > S_CONTENT_H=212 — its
    // row was drawn 22px below the visible/tappable content area, making the
    // entry invisible and only reachable via a ~4px sliver at the very bottom
    // edge). Self-scales for any future app count instead of hardcoding a fit
    // for exactly 9.
    int16_t _appListRowH() const {
        int16_t fitted = (int16_t)(S_CONTENT_H / CONFIGURABLE_APP_COUNT);
        return (fitted < S_ROW_H) ? fitted : S_ROW_H;
    }

    void _repaintAppList() {
        int16_t rowH = _appListRowH();
        int y = S_CONTENT_Y;
        for (int i = 0; i < CONFIGURABLE_APP_COUNT; i++) {
            drawChevronRow(y, kConfigurableApps[i].display, rowH);
            y += rowH;
        }
    }

    void _repaintAppRows() {
        if (kConfigurableApps[_sub].id == AppId::Stock &&
            _editPhase == StockEditPhase::Error) {
            drawHeader();
            _repaintStockError();
            return;
        }
        switch (kConfigurableApps[_sub].id) {
            case AppId::Stock:    _repaintStock();    break;
            case AppId::Crypto:   _repaintCrypto();   break;
            case AppId::Aquarium: _repaintAquarium(); break;
            case AppId::Matrix:   _repaintMatrix();   break;
            case AppId::Life:     _repaintLife();     break;
            case AppId::Clock:    _repaintClock();    break;
            case AppId::Teletext: _repaintTeletext(); break;
            case AppId::Spotify:  _repaintPlayer();   break;
            case AppId::PlaneRadar: _repaintPlaneRadar(); break;
            case AppId::WebRadio: _repaintWebRadio(); break;
            default: break;
        }
    }

    void _repaintStock() {
        int y = S_CONTENT_Y;
        for (int i = 0; i < 7; i++) {
            char lbl[12]; snprintf(lbl, sizeof(lbl), "Ticker %d", i + 1);
            drawRow(y, { lbl, settings().stockTickers[i], S_LABEL, S_VALUE });
            y += S_ROW_H;
        }
        static const char* kV[] = { "list","chart","heatmap" };
        uint8_t m = (uint8_t)settings().stockMode % 3;
        drawRow(y, { "Default view", kV[m], S_LABEL, S_VALUE });
    }

    void _repaintStockError() {
        clearContent();
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(0xF800, TFT_BLACK);
        tft.drawString("INVALID TICKER", 137, 100, 2);
        tft.setTextColor(0xFFFF, TFT_BLACK);
        tft.drawString("[tap to retry]", 137, 130, 2);
        tft.setTextDatum(TL_DATUM);
    }

    void _repaintCrypto() {
        int y = S_CONTENT_Y;
        for (int i = 0; i < 6; i++) {
            char lbl[8]; snprintf(lbl, sizeof(lbl), "Coin %d", i + 1);
            drawRow(y, { lbl, cgIdToDisplay(settings().cryptoCoins[i]), S_LABEL, S_VALUE });
            y += S_ROW_H;
        }
        drawRow(y, { "Currency", settings().cryptoCcy, S_LABEL, S_VALUE });
    }

    void _repaintAquarium() {
        int y = S_CONTENT_Y;
        char fbuf[4]; snprintf(fbuf, sizeof(fbuf), "%d", (int)settings().aquariumFish);
        drawRow(y, { "Fish count", fbuf, S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Speed", _speedStr(settings().aquariumSpeed), S_LABEL, S_VALUE });
    }

    void _repaintMatrix() {
        int y = S_CONTENT_Y;
        static const char* kC[] = { "green","white","amber" };
        uint8_t mc = (uint8_t)settings().matrixColor % 3;
        drawRow(y, { "Color", kC[mc], S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Speed", _speedStr(settings().matrixSpeed), S_LABEL, S_VALUE });
    }

    void _repaintLife() {
        int y = S_CONTENT_Y;
        drawRow(y, { "Speed", _speedStr(settings().lifeSpeed), S_LABEL, S_VALUE }); y += S_ROW_H;
        static const char* kSc[] = { "rainbow","mono" };
        uint8_t lc = (uint8_t)settings().lifeColors % 2;
        drawRow(y, { "Colors", kSc[lc], S_LABEL, S_VALUE });
    }

    static void _onTickerSubmit(const char* sym, void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        if (!sym || sym[0] == '\0') { self->_editPhase = StockEditPhase::None; return; }
        strlcpy(self->_pendingTicker, sym, 8);
        self->_editPhase = StockEditPhase::Validating;
        dataTask::enqueueStockChartBySym(sym, 0);
        self->_validateStartMs = millis();
    }

    void _openStockKeyboard(int row) {
        strlcpy(_pendingTicker, settings().stockTickers[row], 8);
        _editRow = (int8_t)row;
        char prompt[12]; snprintf(prompt, sizeof(prompt), "Ticker %d", row + 1);
        g_keyboard.show(prompt, _pendingTicker, KeyboardWidget::Mode::UpperAlpha, 7,
            _onTickerSubmit, nullptr, this);
    }

    void _handleAppTap(int row) {
        if (row < 0) return;
        switch (kConfigurableApps[_sub].id) {
            case AppId::Stock:
                if (_editPhase == StockEditPhase::Error) {
                    _editPhase = StockEditPhase::None;
                    _openStockKeyboard(_editRow);
                    return;
                }
                if (row >= 0 && row < 7) { _openStockKeyboard(row); return; }
                if (row == 7) {
                    settings().stockMode = (StockViewMode)(((uint8_t)settings().stockMode + 1) % 3);
                    saveSettings(); repaint();
                }
                break;
            case AppId::Crypto:   _cycleCrypto(row);   break;
            case AppId::Aquarium: _cycleAquarium(row); break;
            case AppId::Matrix:   _cycleMatrix(row);   break;
            case AppId::Life:     _cycleLife(row);     break;
            case AppId::Clock:    _cycleClock(row);    break;
            case AppId::Teletext: _cycleTeletext(row); break;
            case AppId::Spotify:  _cyclePlayer(row);   break;
            case AppId::PlaneRadar: _cyclePlaneRadar(row); break;
            case AppId::WebRadio: _cycleWebRadio(row); break;
            default: break;
        }
    }

    void _cycleCrypto(int row) {
        static const char* kPool[] = {
            "bitcoin","ethereum","solana","binancecoin","ripple","cardano",
            "dogecoin","avalanche-2","matic-network","chainlink","polkadot","litecoin"
        };
        static const uint8_t kSz = 12;
        if (row < 6) {
            const char* cur = settings().cryptoCoins[row];
            int idx = 0;
            for (uint8_t i = 0; i < kSz; i++) if (strcmp(kPool[i], cur) == 0) { idx = i; break; }
            strlcpy(settings().cryptoCoins[row], kPool[(idx + 1) % kSz], 16);
        } else if (row == 6) {
            if (strcmp(settings().cryptoCcy, "usd") == 0) strlcpy(settings().cryptoCcy, "eur", 4);
            else strlcpy(settings().cryptoCcy, "usd", 4);
        } else return;
        saveSettings(); repaint();
    }

    void _cycleAquarium(int row) {
        static const uint8_t kFish[] = { 4, 8, 12, 16 };
        if (row == 0) {
            uint8_t cur = settings().aquariumFish; uint8_t next = kFish[0];
            for (int i = 0; i < 4; i++) if (kFish[i] == cur) { next = kFish[(i+1)%4]; break; }
            settings().aquariumFish = next;
        } else if (row == 1) {
            settings().aquariumSpeed = _cycleSpeed(settings().aquariumSpeed);
        } else return;
        saveSettings(); repaint();
    }

    void _cycleMatrix(int row) {
        if (row == 0) settings().matrixColor = (MatrixColor)(((uint8_t)settings().matrixColor + 1) % 3);
        else if (row == 1) settings().matrixSpeed = _cycleSpeed(settings().matrixSpeed);
        else return;
        saveSettings(); repaint();
    }

    void _cycleLife(int row) {
        if (row == 0) settings().lifeSpeed = _cycleSpeed(settings().lifeSpeed);
        else if (row == 1) settings().lifeColors = (LifeColors)(((uint8_t)settings().lifeColors + 1) % 2);
        else return;
        saveSettings(); repaint();
    }

    void _repaintClock() {
        static const char* kS[] = { "digital", "flip", "nixie", "vfd" };
        uint8_t cs = (uint8_t)settings().clockStyle % 4;
        drawRow(S_CONTENT_Y, { "Style", kS[cs], S_LABEL, S_VALUE });
    }

    void _cycleClock(int row) {
        if (row != 0) return;
        settings().clockStyle = (ClockStyle)(((uint8_t)settings().clockStyle + 1) % 4);
        saveSettings();
        repaint();
    }

    // M-PLAYER-STATE / TASK-260: the player slot (AppId::Spotify, shown as "Winamp")
    // hosts two modes — Spotify | WebRadio. One "Mode" row toggles the persisted
    // g_settings.playerMode. The change applies on next entry to the player slot (the
    // settings screen is a different app, so no live app-switch is forced from here).
    void _repaintPlayer() {
        bool radio = settings().playerMode == (uint8_t)PlayerMode::WebRadio;
        drawRow(S_CONTENT_Y, { "Mode", radio ? "WebRadio" : "Spotify", S_LABEL, S_VALUE });
    }

    void _cyclePlayer(int row) {
        if (row != 0) return;
        settings().playerMode = (settings().playerMode == (uint8_t)PlayerMode::WebRadio)
                              ? (uint8_t)PlayerMode::Spotify
                              : (uint8_t)PlayerMode::WebRadio;
        saveSettings();
        repaint();
    }

    void _repaintTeletext() {
        int y = S_CONTENT_Y;
        static const char* kPages[] = { "101 News", "601 Sport", "702 Weather", "800 Football" };
        static const uint16_t kPageVals[] = { 101, 601, 702, 800 };
        const char* pageLbl = kPages[0];
        for (int i = 0; i < 4; i++) {
            if (kPageVals[i] == settings().teletextPage) { pageLbl = kPages[i]; break; }
        }
        drawRow(y, { "Start page", pageLbl, S_LABEL, S_VALUE }); y += S_ROW_H;
        char pbuf[8];
        snprintf(pbuf, sizeof(pbuf), "%us", settings().teletextPollSecs);
        drawRow(y, { "Refresh", pbuf, S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Country", "NL (NOS)", S_LABEL, 0x7BEF });  // greyed-out
    }

    void _cycleTeletext(int row) {
        if (row == 0) {
            static const uint16_t kPages[] = { 101, 601, 702, 800 };
            uint16_t cur = settings().teletextPage;
            uint8_t next = 0;
            for (int i = 0; i < 4; i++) if (kPages[i] == cur) { next = (i+1)%4; break; }
            settings().teletextPage = kPages[next];
        } else if (row == 1) {
            static const uint8_t kPoll[] = { 30, 60, 120 };
            uint8_t cur = settings().teletextPollSecs;
            uint8_t next = 1;
            for (int i = 0; i < 3; i++) if (kPoll[i] == cur) { next = (i+1)%3; break; }
            settings().teletextPollSecs = kPoll[next];
        } else { return; }
        saveSettings(); repaint();
    }

    // M-PLANERADAR / TASK-305. Location (lat/lon) is compile-time-default-only
    // for v1 (D4 — no numeric-entry UI); shown greyed-out/read-only, same
    // posture as Teletext's Country row.
    void _repaintPlaneRadar() {
        int y = S_CONTENT_Y;
        // kPrPresetKm/PR_NUM_PRESETS shared with planeRadarApp.h (planeRadarConfig.h,
        // TASK-310 audit finding #6 — was a locally-duplicated kRangeKm[] here).
        char rbuf[8]; snprintf(rbuf, sizeof(rbuf), "%ukm", (unsigned)kPrPresetKm[settings().prRangeIdx % PR_NUM_PRESETS]);
        drawRow(y, { "Range", rbuf, S_LABEL, S_VALUE }); y += S_ROW_H;

        drawRow(y, { "Units", settings().prUnits ? "mi" : "km", S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Runways", settings().prRunwayOverlay ? "on" : "off", S_LABEL, S_VALUE }); y += S_ROW_H;

        static const char* kTagRule[]   = { "a", "b", "c (drop)" };
        drawRow(y, { "Tag rule", kTagRule[(uint8_t)settings().prTagRule % (uint8_t)PrTagRule::Count], S_LABEL, S_VALUE }); y += S_ROW_H;

        static const char* kStaleStyle[] = { "ring", "text", "dim" };
        drawRow(y, { "Stale style", kStaleStyle[(uint8_t)settings().prStaleStyle % (uint8_t)PrStaleStyle::Count], S_LABEL, S_VALUE }); y += S_ROW_H;

        // M-PR-LOCATIONS / TASK-321: Locations row replaces the old greyed-out
        // read-only lat/lon row (D4 superseded). Same chevron+value idiom as
        // TimeSection's City row: drawChevronRow() draws the ">" at
        // S_COL_VALUE, then the value text is drawn separately, right-aligned
        // just to its left.
        const PrLocation& activeLoc = settings().prLocs[settings().prActiveLoc % PR_NUM_LOCS];
        drawChevronRow(y, "Locations");
        tft.setTextDatum(MR_DATUM);
        tft.setTextColor(S_VALUE);
        tft.drawString(activeLoc.label[0] ? activeLoc.label : "HOME", S_COL_VALUE - 14, y + S_ROW_H / 2, 2);
        tft.setTextDatum(TL_DATUM);
    }

    void _cyclePlaneRadar(int row) {
        if (row == 0) {
            settings().prRangeIdx = (uint8_t)((settings().prRangeIdx + 1) % PR_NUM_PRESETS);
        } else if (row == 1) {
            settings().prUnits = settings().prUnits ? 0 : 1;
        } else if (row == 2) {
            settings().prRunwayOverlay = !settings().prRunwayOverlay;
        } else if (row == 3) {
            settings().prTagRule = (PrTagRule)(((uint8_t)settings().prTagRule + 1) % (uint8_t)PrTagRule::Count);
        } else if (row == 4) {
            settings().prStaleStyle = (PrStaleStyle)(((uint8_t)settings().prStaleStyle + 1) % (uint8_t)PrStaleStyle::Count);
        } else if (row == 5) {
            // Locations row: tap opens the SlotList sub-view (TASK-321). Nothing
            // changed yet, so skip the saveSettings()+repaint() at the bottom.
            _prLocActive = true;
            _prLocState  = PrLocView::SlotList;
            repaint();
            return;
        } else return;
        saveSettings(); repaint();
    }

    // ==== M-WEBRADIO-SETTINGS: WebRadio row view (D2) ========================
    // 6 rows: Country (picker, WR-2 reset on select), Autoplay (toggle),
    // Bitrate cap (cycle — the wipe-trap fix row, WR-2 reset on change),
    // Auto-skip (toggle), Max volume (slider — WR-3 phases forwarded in
    // handleInput), HW mod (greyed read-only: a statement about installed
    // hardware, not a preference — stays serial/spiffs-only, Teletext
    // Country posture). Change propagation is the radio app's job (D3
    // resume-diff); this section only edits + saves.

    bool _wrSub() const {
        return _sub >= 0 && kConfigurableApps[_sub].id == AppId::WebRadio;
    }

    void _repaintWebRadio() {
        int y = S_CONTENT_Y;
        drawRow(y, { "Country", settings().webRadioCountry, S_LABEL, S_VALUE });
        y += S_ROW_H;
        drawRow(y, { "Autoplay", settings().webRadioAutoplay ? "on" : "off",
                     S_LABEL, S_VALUE });
        y += S_ROW_H;
        char cbuf[8];
        if (settings().webRadioBitrateCap == 0) strlcpy(cbuf, "off", sizeof(cbuf));
        else snprintf(cbuf, sizeof(cbuf), "%uk", (unsigned)settings().webRadioBitrateCap);
        drawRow(y, { "Bitrate cap", cbuf, S_LABEL, S_VALUE });
        y += S_ROW_H;
        drawRow(y, { "Auto-skip", settings().webRadioAutoSkip ? "on" : "off",
                     S_LABEL, S_VALUE });
        y += S_ROW_H;
        // 1..21 = ESP32-audioI2S setVolume() range (webRadioApp.h WR_VOLUME_MAX).
        // Re-init only outside a drag so mid-gesture repaints can't reset capture.
        if (!_wrVolSlider.isDragging())
            _wrVolSlider.init(1, 21, settings().webRadioMaxVolume);
        _wrVolSlider.render(y, "Max vol");
        y += S_ROW_H;
        drawRow(y, { "HW mod", settings().webRadioHwMod ? "yes" : "no",
                     S_LABEL, S_VALUE_OFF });   // greyed read-only
        y += S_ROW_H;
        // TASK-209 clamp made visible (D2 value-label intent): stock hardware
        // soft-caps effective volume at 12 (wrEffectiveVolume() semantics).
        // Rendered as a footer hint — the slider's fixed value zone is too
        // narrow for a composite "N (cap 12)" label.
        if (!settings().webRadioHwMod && settings().webRadioMaxVolume > 12) {
            tft.setTextDatum(MC_DATUM);
            tft.setTextColor(S_VALUE_OFF);
            tft.drawString("volume capped at 12 (no HW mod)",
                           S_CANVAS_W / 2, y + 10, 2);
            tft.setTextDatum(TL_DATUM);
        }
    }

    void _cycleWebRadio(int row) {
        if (row == 0) {
            // Country picker (M-COUNTRY-PICKER D3) — replaces the free-typed
            // 2-char keyboard; WR-SETTINGS OQ2's "invalid code -> empty
            // station list" failure mode is now unrepresentable. Opens at
            // the currently persisted code (CP-6).
            g_countryPicker.show(kCountries, kCountryCount,
                settings().webRadioCountry,
                _onWrCountryPicked, _onWrCountryPickCancel, this);
            return;   // nothing changed yet — the select handler saves
        } else if (row == 1) {
            settings().webRadioAutoplay = !settings().webRadioAutoplay;
        } else if (row == 2) {
            // find-current-else-default-next (WR-11, _cycleTeletext
            // convention): a serial-set off-list value (e.g. 100) advances to
            // 128 (the default) instead of wedging the row. 0 renders "off".
            static const uint8_t kCaps[] = { 0, 64, 96, 128, 192 };
            uint8_t cur  = settings().webRadioBitrateCap;
            uint8_t next = 3;   // -> 128 when cur is off-list
            for (int i = 0; i < 5; i++)
                if (kCaps[i] == cur) { next = (uint8_t)((i + 1) % 5); break; }
            settings().webRadioBitrateCap = kCaps[next];
            // WR-2 edit-time reset: the persisted index points into the old
            // (differently filtered) list; reset rides this handler's save.
            settings().webRadioLastStation = 0;
        } else if (row == 3) {
            settings().webRadioAutoSkip = !settings().webRadioAutoSkip;
        } else {
            // row 4 (Max volume) is phase-forwarded to the slider in
            // handleInput(); row 5 (HW mod) is read-only — inert.
            return;
        }
        saveSettings(); repaint();
    }

    static void _onWrCountryPicked(int16_t idx, void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        const char* code = kCountries[idx].code;
        if (strcmp(code, self->settings().webRadioCountry) != 0) {
            strlcpy(self->settings().webRadioCountry, code,
                    sizeof(self->settings().webRadioCountry));
            // WR-2 edit-time reset: rides this save (zero extra flash wear)
            // and closes the reboot window a resume()-time RAM reset leaves.
            self->settings().webRadioLastStation = 0;
            self->saveSettings();
        }
        self->repaint();
    }
    static void _onWrCountryPickCancel(void* ctx) {
        static_cast<AppsSection*>(ctx)->repaint();
    }

    // ==== M-PR-LOCATIONS / TASK-321/322: Locations sub-view + slot editor ===
    // Both coordinate-source paths (Lookup and Manual) are live. Kit-fidelity:
    // every button/spinner below is SButton/sButtonBar/sStackedBtnRect/
    // SSpinner from settingsWidgets.h (TASK-328) — no hand-rolled buttons.

    // LookupCountry is no longer a keyboard step — it is a PICKER step
    // (M-COUNTRY-PICKER D3); repaint() early-returns on g_countryPicker
    // .active() instead, and the picker captures touch in handleInput().
    bool _prLocIsKeyboardStep() const {
        return _prLocState == PrLocView::EditLabel ||
               _prLocState == PrLocView::LookupPostcode ||
               _prLocState == PrLocView::ManualLat ||
               _prLocState == PrLocView::ManualLon;
    }

    const char* _prLocTitle() const {
        if (_prLocState == PrLocView::SlotList) return "Locations";
        snprintf(_prTitleBuf, sizeof(_prTitleBuf), "Edit %s",
                 _prPendingLabel[0] ? _prPendingLabel : "");
        return _prTitleBuf;
    }

    void _repaintPrLoc() {
        switch (_prLocState) {
            case PrLocView::SlotList:      _repaintPrSlotList();      break;
            case PrLocView::SourceFork:    _repaintPrSourceFork();    break;
            case PrLocView::LookupPending: _repaintPrPending();       break;
            case PrLocView::LookupConfirm: _repaintPrConfirm();       break;
            case PrLocView::LookupError:   _repaintPrError();         break;
            case PrLocView::ManualConfirm: _repaintPrManualConfirm(); break;
            default: break;   // EditLabel/LookupPostcode/ManualLat/ManualLon — keyboard owns the canvas; LookupCountry — picker owns it
        }
    }

    void _handlePrLocTap(int x, int y) {
        switch (_prLocState) {
            case PrLocView::SlotList:      _handlePrSlotListTap(y);         break;
            case PrLocView::SourceFork:    _handlePrSourceForkTap(x, y);    break;
            case PrLocView::LookupPending: _handlePrPendingTap(x, y);       break;
            case PrLocView::LookupConfirm: _handlePrConfirmTap(x, y);       break;
            case PrLocView::LookupError:   _handlePrErrorTap(x, y);         break;
            case PrLocView::ManualConfirm: _handlePrManualConfirmTap(x, y); break;
            default: break;   // keyboard/picker steps — captured by handleInput()'s g_keyboard/g_countryPicker branches
        }
    }

    // Header back-tap semantics per state (mirrors each screen's own
    // Cancel button where one exists; EditLabel/LookupPostcode/ManualLat/
    // ManualLon are unreachable here — the keyboard owns touch and has its
    // own cancel zone — and so is LookupCountry, whose picker owns its own
    // "< back" zone; both are intercepted earlier in handleInput()).
    void _handlePrLocBack() {
        switch (_prLocState) {
            case PrLocView::SlotList:
                _prLocActive = false;   // back out to the PlaneRadar app row view
                repaint();
                break;
            case PrLocView::SourceFork:
                _prLocState = PrLocView::SlotList;
                repaint();
                break;
            case PrLocView::LookupPending:
                _prAbandonLookup();     // == the screen's own [Cancel] button
                break;
            case PrLocView::LookupConfirm:
            case PrLocView::LookupError:
            case PrLocView::ManualConfirm:
                _prLocState = PrLocView::SlotList;   // == each screen's own Cancel
                repaint();
                break;
            default:
                break;
        }
    }

    // ---- SlotList (editor_slotlist.png) -------------------------------------

    void _repaintPrSlotList() {
        int y = S_CONTENT_Y;
        for (uint8_t i = 0; i < PR_NUM_LOCS; i++) {
            const PrLocation& loc = settings().prLocs[i];
            bool active = (i == settings().prActiveLoc);
            if (active) tft.fillRect(0, y, 3, S_ROW_H, S_VALUE_ON);   // 3px active bar
            if (loc.label[0]) {
                char lbuf[24];
                snprintf(lbuf, sizeof(lbuf), "%.3f,%.3f", loc.lat, loc.lon);
                drawRow(y, { loc.label, lbuf, active ? S_VALUE_ON : S_LABEL, S_VALUE });
            } else {
                tft.setTextDatum(MC_DATUM);
                tft.setTextColor(S_VALUE_OFF);
                tft.drawString("-- empty --", S_CANVAS_W / 2, y + S_ROW_H / 2, 2);
                tft.setTextDatum(TL_DATUM);
            }
            y += S_ROW_H;
        }
        y += 16;
        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_VALUE_OFF);
        tft.drawString("Tap a slot to edit", S_CANVAS_W / 2, y, 2);
        tft.setTextDatum(TL_DATUM);
    }

    void _handlePrSlotListTap(int y) {
        Rect area = { 0, S_CONTENT_Y, S_CANVAS_W, (int16_t)(PR_NUM_LOCS * S_ROW_H) };
        int row = hitTestRow(area, S_ROW_H, y);
        if (row < 0 || row >= PR_NUM_LOCS) return;   // hint text tap — inert
        _openPrEditor((uint8_t)row);
    }

    // Tap ANY slot (incl. empty) → editor flow for that slot, starting at
    // EditLabel (design "sub-view tap = edit only", Q6).
    void _openPrEditor(uint8_t slot) {
        _prEditSlot = slot;
        strlcpy(_prPendingLabel, settings().prLocs[slot].label, sizeof(_prPendingLabel));
        _prLocState = PrLocView::EditLabel;
        g_keyboard.show("Label", _prPendingLabel, KeyboardWidget::Mode::UpperAlpha,
            PR_LABEL_MAX, _onPrLabelSubmit, _onPrLabelCancel, this);
    }

    static void _onPrLabelSubmit(const char* text, void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        strlcpy(self->_prPendingLabel, text, sizeof(self->_prPendingLabel));
        self->_prLocState = PrLocView::SourceFork;
        self->repaint();
    }
    static void _onPrLabelCancel(void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        self->_prLocState = PrLocView::SlotList;
        self->repaint();
    }

    // ---- SourceFork (editor_source_fork.png / editor_source_fork_slot0.png) -

    void _repaintPrSourceFork() {
        int y = S_CONTENT_Y;
        bool hasCurrent = settings().prLocs[_prEditSlot].label[0] != '\0';
        if (hasCurrent) {
            char lbuf[24];
            snprintf(lbuf, sizeof(lbuf), "%.3f,%.3f",
                     settings().prLocs[_prEditSlot].lat, settings().prLocs[_prEditSlot].lon);
            drawRow(y, { "Current", lbuf, S_LABEL, S_VALUE_OFF });
            y += S_ROW_H;
        }
        y += 10;

        // NOTE: individual-field assignment, not aggregate brace-init — this
        // toolchain compiles gnu++11, where a class with default member
        // initializers (SButton has them) is not an aggregate, so
        // `SButton{a,b,c}` has no matching constructor.
        _prForkBtn[0].r     = sStackedBtnRect(0, y);
        _prForkBtn[0].label = "Lookup  (country + postcode)";
        _prForkBtn[0].style = SBtnStyle::Primary;
        _prForkBtn[0].draw();

        // TASK-322: manual lat/lon entry — Neutral (not Primary/accent; Lookup
        // stays the recommended default per the TASK-317 gate frame).
        _prForkBtn[1].r     = sStackedBtnRect(1, y);
        _prForkBtn[1].label = "Manual  (lat / lon)";
        _prForkBtn[1].style = SBtnStyle::Neutral;
        _prForkBtn[1].draw();

        bool slot0 = (_prEditSlot == 0);
        _prForkBtn[2].r     = sStackedBtnRect(2, y);
        _prForkBtn[2].label = "Delete";
        _prForkBtn[2].style = (slot0 || !hasCurrent) ? SBtnStyle::Disabled : SBtnStyle::Danger;
        _prForkBtn[2].draw();

        if (slot0) {
            tft.setTextDatum(MC_DATUM);
            tft.setTextColor(S_VALUE_OFF);
            tft.drawString("slot 0 is always defined", S_CANVAS_W / 2,
                            _prForkBtn[2].r.y + _prForkBtn[2].r.h + 14, 2);
            tft.setTextDatum(TL_DATUM);
        }
    }

    void _handlePrSourceForkTap(int x, int y) {
        if (_prForkBtn[0].hit(x, y)) {
            _prForkBtn[0].flash();
            _openPrCountryPicker();
            return;
        }
        if (_prForkBtn[1].hit(x, y)) {
            _prForkBtn[1].flash();
            _openPrManualLat();
            return;
        }
        if (_prForkBtn[2].hit(x, y)) {
            _prForkBtn[2].flash();
            _prDeleteSlot();
        }
    }

    void _prDeleteSlot() {
        if (_prEditSlot == 0) return;   // slot 0 is always defined — defensive, button is Disabled anyway
        PrLocation& slot = settings().prLocs[_prEditSlot];
        slot.label[0] = '\0';
        slot.lat = 0.0f;
        slot.lon = 0.0f;
        if (_prEditSlot == settings().prActiveLoc) {
            // Fall back active -> 0, then re-derive the ACTIVE mirror through
            // the shared matrix helper so prLat/prLon stay valid (same net
            // effect as the previous inline copy). prSlotWritten(0) also
            // rewrites the HOME mirror from slot 0 — a value no-op: delete
            // never moves home, slot 0 is undeletable (H-2 note).
            settings().prActiveLoc = 0;
            SettingsStorage::prSlotWritten(0);
        }
        saveSettings();
        _prLocState = PrLocView::SlotList;
        repaint();
    }

    // Country step = SPickerList (M-COUNTRY-PICKER D3; replaces the 2-char
    // UpperAlpha keyboard). _prLastCountry session memory (Q5) is the
    // picker's initial position; select feeds the pending code and advances
    // to the Postcode keyboard exactly as the old keyboard submit did.
    void _openPrCountryPicker() {
        _prLocState = PrLocView::LookupCountry;
        g_countryPicker.show(kCountries, kCountryCount, _prLastCountry,
            _onPrCountryPicked, _onPrCountryPickCancel, this);
    }

    static void _onPrCountryPicked(int16_t idx, void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        const char* code = kCountries[idx].code;
        strlcpy(self->_prLastCountry, code, sizeof(self->_prLastCountry));
        strlcpy(self->_prPendingCountry, code, sizeof(self->_prPendingCountry));
        self->_prLocState = PrLocView::LookupPostcode;
        g_keyboard.show("Postcode", "", KeyboardWidget::Mode::Full, 10,
            _onPrPostcodeSubmit, _onPrPostcodeCancel, self);
    }
    static void _onPrCountryPickCancel(void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        self->_prLocState = PrLocView::SourceFork;
        self->repaint();
    }

    static void _onPrPostcodeSubmit(const char* text, void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        strlcpy(self->_prPendingPostcode, text, sizeof(self->_prPendingPostcode));
        self->_prGeoSeq = dataTask::enqueueGeocode(self->_prPendingCountry, self->_prPendingPostcode);
        self->_prLocState  = PrLocView::LookupPending;
        self->_prSpinnerMs = millis();
        self->_prSpinner   = SSpinner{};
        self->repaint();
    }
    static void _onPrPostcodeCancel(void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        self->_prLocState = PrLocView::SourceFork;
        self->repaint();
    }

    // ---- LookupPending (editor_lookup_pending.png) --------------------------

    void _repaintPrPending() {
        int y = S_CONTENT_Y;
        drawRow(y, { "Country",  _prPendingCountry,  S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Postcode", _prPendingPostcode, S_LABEL, S_VALUE }); y += S_ROW_H;
        y += 20;

        _prSpinner.y     = y;
        _prSpinner.label = "Looking up...";
        _prSpinner.draw();

        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(S_VALUE_OFF);
        tft.drawString("fetching from Nominatim", S_CANVAS_W / 2, y + 40, 2);
        tft.setTextDatum(TL_DATUM);

        // [Cancel] — functionally required (VE-PRL-5/T_PRL_08 cancel-mid-
        // lookup) but not present in the frozen TASK-317 PNG, which predates
        // that VE finding; see kit-fidelity note in the TASK-321 report.
        _prBar[0].label = "Cancel";
        _prBar[0].style = SBtnStyle::Neutral;
        sButtonBar(_prBar, 1);
        _prBar[0].draw();
    }

    void _handlePrPendingTap(int x, int y) {
        if (_prBar[0].hit(x, y)) {
            _prBar[0].flash();
            _prAbandonLookup();
        }
    }

    // Cancel mid-lookup: abandon back to SourceFork. _prGeoSeq is left as-is
    // (not cleared) so a late-arriving result for THIS seq is still correctly
    // matched by _tickPrLookup() and then simply not acted on because the UI
    // has moved on — but a subsequent NEW lookup gets a fresh seq from
    // enqueueGeocode(), so a truly stale delivery from an earlier abandoned
    // lookup can never be mistaken for the current one (VE-PRL-5/T_PRL_08).
    void _prAbandonLookup() {
        _prLocState = PrLocView::SourceFork;
        repaint();
    }

    void _tickPrLookup() {
        unsigned long now = millis();
        if (now - _prSpinnerMs >= 250) {
            _prSpinnerMs = now;
            _prSpinner.tick();
        }
        dataTask::GeocodeResult r;
        if (dataTask::pollGeocode(&r)) {
            // Seq identity rule (design "Geocode fetch"): store the seq
            // returned by enqueueGeocode, ignore+discard any polled result
            // with a different seq. It IS consumed by poll — that's fine,
            // we just don't act on it.
            if (r.seq != _prGeoSeq) return;
            if (r.ok) {
                _prGeoLat = r.lat;
                _prGeoLon = r.lon;
                strlcpy(_prGeoDisplay, r.display, sizeof(_prGeoDisplay));
                _prLocState = PrLocView::LookupConfirm;
            } else {
                _prGeoErr   = r.errorCode;
                _prLocState = PrLocView::LookupError;
            }
            repaint();
        }
    }

    // ---- LookupConfirm (editor_lookup_confirm.png) --------------------------

    static void _wrapDisplay(const char* src, char* l1, size_t l1n, char* l2, size_t l2n) {
        size_t len = strlen(src);
        size_t split = len;
        if (len > 23) {
            split = 23;
            while (split > 0 && src[split] != ' ') split--;
            if (split == 0) split = 23;   // no space found — hard break
        }
        size_t n1 = (split < l1n - 1) ? split : l1n - 1;
        memcpy(l1, src, n1); l1[n1] = '\0';
        const char* rest = src + split;
        while (*rest == ' ') rest++;
        strlcpy(l2, rest, l2n);
    }

    void _repaintPrConfirm() {
        int y = S_CONTENT_Y;
        char line1[40], line2[40];
        _wrapDisplay(_prGeoDisplay, line1, sizeof(line1), line2, sizeof(line2));
        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(S_VALUE_ON);
        tft.drawString(line1, S_COL_LABEL, y, 2); y += 16;
        tft.drawString(line2, S_COL_LABEL, y, 2); y += 22;

        char latbuf[16]; snprintf(latbuf, sizeof(latbuf), "%.4f", _prGeoLat);
        drawRow(y, { "Lat", latbuf, S_LABEL, S_VALUE }); y += S_ROW_H;
        char lonbuf[16]; snprintf(lonbuf, sizeof(lonbuf), "%.4f", _prGeoLon);
        drawRow(y, { "Lon", lonbuf, S_LABEL, S_VALUE }); y += S_ROW_H;

        // M-HOME-LOCATION H-4: divergence hint — informs, never blocks (Save
        // still commits). Rendered under the lat/lon rows, above the bar.
        _prComputeDivKm();
        if (_prDivKm > 500) {
            tft.setTextDatum(MC_DATUM);
            tft.setTextColor(S_VALUE_OFF);
            tft.drawString("timezone follows Time & Location",
                           S_CANVAS_W / 2, y + 8, 2);
            tft.setTextDatum(TL_DATUM);
        }

        _prBar[0].label = "Save";   _prBar[0].style = SBtnStyle::Primary;
        _prBar[1].label = "Retry";  _prBar[1].style = SBtnStyle::Neutral;
        _prBar[2].label = "Cancel"; _prBar[2].style = SBtnStyle::Neutral;
        sButtonBar(_prBar, 3);
        for (uint8_t i = 0; i < 3; i++) _prBar[i].draw();
    }

    // M-HOME-LOCATION H-4/H-6: km between the pending geocode result and the
    // picked city's coords. Reference = kCities lookup by NAME — after D1b,
    // g_settings.lat/lon ARE the home mirror, so the city's own coords survive
    // nowhere in settings.json; the check is name-driven. 0 (= skipped) when
    // not editing slot 0, city unset, or city not in the table (pushed-file
    // case). Distance: equirectangular with cosf midpoint-latitude scale —
    // adequate at a 500 km threshold, no haversine import (H-6).
    void _prComputeDivKm() {
        _prDivKm = 0;
        if (_prEditSlot != 0 || settings().city[0] == '\0') return;
        for (uint8_t i = 0; i < kCityCount; i++) {
            if (strcmp(settings().city, kCities[i].city) != 0) continue;
            float midLatRad = 0.5f * (kCities[i].lat + _prGeoLat)
                              * 0.0174533f;   // deg -> rad
            float dx = (_prGeoLon - kCities[i].lon) * cosf(midLatRad);
            float dy = _prGeoLat - kCities[i].lat;
            _prDivKm = (int)(111.19f * sqrtf(dx * dx + dy * dy));
            return;
        }
    }

    void _handlePrConfirmTap(int x, int y) {
        if (_prBar[0].hit(x, y)) {
            _prBar[0].flash();
            _prSaveCoords();
        } else if (_prBar[1].hit(x, y)) {
            _prBar[1].flash();
            _openPrCountryPicker();   // Retry restarts at the country step
        } else if (_prBar[2].hit(x, y)) {
            _prBar[2].flash();
            _prLocState = PrLocView::SlotList;   // Cancel keeps prior coords, nothing persisted
            repaint();
        }
    }

    // Save commits the pending label + coords into the slot — coords come
    // from either the Lookup result or manual entry (TASK-322), both funneled
    // through _prGeoLat/_prGeoLon by the time this runs. Does NOT switch the
    // active slot (Q6 resolved) — only the radar-strip gesture (TASK-323)
    // does that.
    void _prSaveCoords() {
        PrLocation& slot = settings().prLocs[_prEditSlot];
        strlcpy(slot.label, _prPendingLabel, sizeof(slot.label));
        slot.lat = _prGeoLat;
        slot.lon = _prGeoLon;
        // M-HOME-LOCATION H-1/H-2: mirror refresh via the shared matrix
        // helper — ACTIVE mirror iff this slot is active (Q6 — saving !=
        // switching, unchanged), plus HOME mirror unconditionally on slot-0
        // edits, even while a non-zero slot is active (weather follows home,
        // not the active slot).
        SettingsStorage::prSlotWritten(_prEditSlot);
        saveSettings();
        _prLocState = PrLocView::SlotList;
        repaint();
    }

    // ---- LookupError (editor_lookup_error.png) ------------------------------

    const char* _prGeoErrDetail() const {
        return (_prGeoErr == -96) ? "postcode not found" : "lookup failed - check network";
    }

    void _repaintPrError() {
        int y = S_CONTENT_Y;
        drawRow(y, { "Country",  _prPendingCountry,  S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Postcode", _prPendingPostcode, S_LABEL, S_VALUE }); y += S_ROW_H;
        y += 24;

        tft.setTextDatum(MC_DATUM);
        tft.setTextColor(0xF800);   // red — matches wifiSection's Result-screen error idiom
        tft.drawString(httpErr(_prGeoErr), S_CANVAS_W / 2, y, 2);
        y += 20;
        tft.setTextColor(S_VALUE_OFF);
        tft.drawString(_prGeoErrDetail(), S_CANVAS_W / 2, y, 2);
        tft.setTextDatum(TL_DATUM);

        _prBar[0].label = "Retry";  _prBar[0].style = SBtnStyle::Primary;
        _prBar[1].label = "Cancel"; _prBar[1].style = SBtnStyle::Neutral;
        sButtonBar(_prBar, 2);
        _prBar[0].draw();
        _prBar[1].draw();
    }

    void _handlePrErrorTap(int x, int y) {
        if (_prBar[0].hit(x, y)) {
            _prBar[0].flash();
            _openPrCountryPicker();   // Retry restarts at the country step
        } else if (_prBar[1].hit(x, y)) {
            _prBar[1].flash();
            _prLocState = PrLocView::SlotList;
            repaint();
        }
    }

    // ---- Manual lat/lon entry (TASK-322, editor_manual_confirm.png) --------
    // Second coordinate-source path (Q4): lat -> lon via KeyboardWidget Full
    // mode (digits/-/. all reachable via the 123/symbol pages) — a dedicated
    // numeric layout was descoped per the task's own instruction, since
    // TASK-317's prototyping never showed Full mode to be insufficient.
    // Both fields prefill from the slot's CURRENT coords when editing an
    // already-filled slot (same prefill idiom as EditLabel). Range-invalid
    // input re-shows the same field's keyboard rather than advancing —
    // no separate error screen exists for this path (T_PRL_06).

    static bool _prParseCoord(const char* text, float lo, float hi, float* out) {
        if (!text || !*text) return false;
        char* end = nullptr;
        double v = strtod(text, &end);
        if (end == text) return false;   // nothing parsed (e.g. bare "-" or "")
        if (v < lo || v > hi) return false;
        *out = (float)v;
        return true;
    }

    void _openPrManualLat() {
        _prLocState = PrLocView::ManualLat;
        char init[16] = "";
        if (settings().prLocs[_prEditSlot].label[0] != '\0')
            snprintf(init, sizeof(init), "%.4f", settings().prLocs[_prEditSlot].lat);
        g_keyboard.show("Lat (-90..90)", init, KeyboardWidget::Mode::Full, 10,
            _onPrLatSubmit, _onPrLatCancel, this);
    }

    void _openPrManualLon() {
        _prLocState = PrLocView::ManualLon;
        char init[16] = "";
        if (settings().prLocs[_prEditSlot].label[0] != '\0')
            snprintf(init, sizeof(init), "%.4f", settings().prLocs[_prEditSlot].lon);
        g_keyboard.show("Lon (-180..180)", init, KeyboardWidget::Mode::Full, 11,
            _onPrLonSubmit, _onPrLonCancel, this);
    }

    static void _onPrLatSubmit(const char* text, void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        float v;
        if (!_prParseCoord(text, -90.0f, 90.0f, &v)) {
            g_keyboard.show("Lat -90..90 (invalid)", "", KeyboardWidget::Mode::Full, 10,
                _onPrLatSubmit, _onPrLatCancel, self);
            return;
        }
        self->_prGeoLat = v;
        self->_openPrManualLon();
    }
    static void _onPrLatCancel(void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        self->_prLocState = PrLocView::SourceFork;
        self->repaint();
    }

    static void _onPrLonSubmit(const char* text, void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        float v;
        if (!_prParseCoord(text, -180.0f, 180.0f, &v)) {
            g_keyboard.show("Lon -180..180 (invalid)", "", KeyboardWidget::Mode::Full, 11,
                _onPrLonSubmit, _onPrLonCancel, self);
            return;
        }
        self->_prGeoLon    = v;
        self->_prLocState  = PrLocView::ManualConfirm;
        self->repaint();
    }
    static void _onPrLonCancel(void* ctx) {
        AppsSection* self = static_cast<AppsSection*>(ctx);
        self->_prLocState = PrLocView::SourceFork;
        self->repaint();
    }

    void _repaintPrManualConfirm() {
        int y = S_CONTENT_Y;
        char latbuf[16]; snprintf(latbuf, sizeof(latbuf), "%.4f", _prGeoLat);
        drawRow(y, { "Lat", latbuf, S_LABEL, S_VALUE }); y += S_ROW_H;
        char lonbuf[16]; snprintf(lonbuf, sizeof(lonbuf), "%.4f", _prGeoLon);
        drawRow(y, { "Lon", lonbuf, S_LABEL, S_VALUE }); y += S_ROW_H + 12;

        tft.setTextDatum(TL_DATUM);
        tft.setTextColor(S_VALUE_OFF);
        tft.drawString("Range: lat -90..90", S_COL_LABEL, y, 2); y += 18;
        tft.drawString("        lon -180..180", S_COL_LABEL, y, 2);
        tft.setTextDatum(TL_DATUM);

        // 2-across bar (Save/Cancel) — no "Retry" concept for manual entry
        // (nothing to retry against; SourceFork -> Manual re-entry covers it).
        _prBar[0].label = "Save";   _prBar[0].style = SBtnStyle::Primary;
        _prBar[1].label = "Cancel"; _prBar[1].style = SBtnStyle::Neutral;
        sButtonBar(_prBar, 2);
        _prBar[0].draw();
        _prBar[1].draw();
    }

    void _handlePrManualConfirmTap(int x, int y) {
        if (_prBar[0].hit(x, y)) {
            _prBar[0].flash();
            _prSaveCoords();
        } else if (_prBar[1].hit(x, y)) {
            _prBar[1].flash();
            _prLocState = PrLocView::SlotList;   // Cancel keeps prior coords, nothing persisted
            repaint();
        }
    }

    static AppSpeed _cycleSpeed(AppSpeed s) {
        return (AppSpeed)(((uint8_t)s + 1) % 3);
    }

    static const char* _speedStr(AppSpeed s) {
        switch (s) {
            case AppSpeed::Slow: return "slow";
            case AppSpeed::Fast: return "fast";
            default:             return "normal";
        }
    }
};
