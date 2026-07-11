#pragma once
#include "settingsSection.h"
#include "gen/configurable_apps.h"
#include "keyboardWidget.h"
#include "dataTask.h"

const char* cgIdToDisplay(const char* id);

class AppsSection : public SettingsSection {
public:
    const char* title() const override {
        return (_sub < 0) ? "Applications" : kConfigurableApps[_sub].display;
    }

    int submenu() const { return (int)_sub; }

    void enter() override { _sub = -1; repaint(); }
    void leave() override { _sub = -1; }

    void repaint() override {
        drawHeader();
        clearContent();
        if (_sub < 0) _repaintAppList();
        else          _repaintAppRows();
    }

    SectionResult tick() override {
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
        if (phase != TouchPhase::Release) return SectionResult::Continue;
        if (isBackTap(x, y)) {
            if (_sub >= 0) { _sub = -1; repaint(); return SectionResult::Continue; }
            return SectionResult::GoBack;
        }
        if (_sub < 0) {
            int row = tapToRow(y);
            if (row >= 0 && row < CONFIGURABLE_APP_COUNT) { _sub = (int8_t)row; repaint(); }
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

    void _repaintAppList() {
        int y = S_CONTENT_Y;
        for (int i = 0; i < CONFIGURABLE_APP_COUNT; i++) {
            drawChevronRow(y, kConfigurableApps[i].display);
            y += S_ROW_H;
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
        static const uint16_t kRangeKm[] = { 5, 10, 15, 25 };
        char rbuf[8]; snprintf(rbuf, sizeof(rbuf), "%ukm", (unsigned)kRangeKm[settings().prRangeIdx % 4]);
        drawRow(y, { "Range", rbuf, S_LABEL, S_VALUE }); y += S_ROW_H;

        drawRow(y, { "Units", settings().prUnits ? "mi" : "km", S_LABEL, S_VALUE }); y += S_ROW_H;
        drawRow(y, { "Runways", settings().prRunwayOverlay ? "on" : "off", S_LABEL, S_VALUE }); y += S_ROW_H;

        static const char* kTagRule[]   = { "a", "b", "c (drop)" };
        drawRow(y, { "Tag rule", kTagRule[(uint8_t)settings().prTagRule % 3], S_LABEL, S_VALUE }); y += S_ROW_H;

        static const char* kStaleStyle[] = { "ring", "text", "dim" };
        drawRow(y, { "Stale style", kStaleStyle[(uint8_t)settings().prStaleStyle % 3], S_LABEL, S_VALUE }); y += S_ROW_H;

        char lbuf[24]; snprintf(lbuf, sizeof(lbuf), "%.3f,%.3f", settings().prLat, settings().prLon);
        drawRow(y, { "Location", lbuf, S_LABEL, 0x7BEF });  // greyed-out (D4: run/spiffs push only)
    }

    void _cyclePlaneRadar(int row) {
        if (row == 0) {
            settings().prRangeIdx = (uint8_t)((settings().prRangeIdx + 1) % 4);
        } else if (row == 1) {
            settings().prUnits = settings().prUnits ? 0 : 1;
        } else if (row == 2) {
            settings().prRunwayOverlay = !settings().prRunwayOverlay;
        } else if (row == 3) {
            settings().prTagRule = (PrTagRule)(((uint8_t)settings().prTagRule + 1) % 3);
        } else if (row == 4) {
            settings().prStaleStyle = (PrStaleStyle)(((uint8_t)settings().prStaleStyle + 1) % 3);
        } else return;   // row 5 (Location) is read-only — no-op, same as Teletext's Country
        saveSettings(); repaint();
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
